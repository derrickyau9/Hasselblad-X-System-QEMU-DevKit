"""Import the UI filesystem from a user-supplied official full OTA package."""
from pathlib import Path
import hashlib
import io
import json
import shutil
import zipfile
import brotli
from dissect.extfs import ExtFS
from elftools.elf.elffile import ELFFile
from . import cim
from .core import ASSETS, Task, checked_child, write_json
from .guest.software_ui import build as adapt_software

TESTED_VERSION = "1.2.7.16"
TESTED_SHA256 = "68aa9bce63c303a7d13ca4c14aae76be935925d596094bdcb92549cff42e1bc1"
PROFILES = {TESTED_SHA256: TESTED_VERSION,
            '9789d6a9843d388034bc12341ad9a97585c25cb98cf11a0da8b768399b4842f6': '1.3.16.2'}
MAX_IMAGE = 2 * 1024**3

def ranges(text):
    values = [int(x) for x in text.split(",")]
    if values[0] != len(values)-1 or values[0] % 2:
        raise ValueError("Malformed OTA block ranges")
    pairs = list(zip(values[1::2], values[2::2]))
    if any(a < 0 or b <= a or b*4096 > MAX_IMAGE for a, b in pairs):
        raise ValueError("OTA block range exceeds supported image size")
    return pairs

def reconstruct(transfer, source, destination, task):
    lines = transfer.splitlines()
    if len(lines) < 4 or lines[0] not in ("3", "4"):
        raise ValueError("Only full Android OTA transfer lists v3/v4 are supported")
    operations, end = [], 0
    for line in lines[4:]:
        if not line.strip():
            continue
        fields = line.split()
        if len(fields) != 2 or fields[0] not in ("new", "zero", "erase"):
            raise ValueError("Incremental OTA is unsupported; download a full official firmware")
        blocks = ranges(fields[1])
        operations.append((fields[0], blocks))
        end = max(end, *(b for _, b in blocks))
    if not end:
        raise ValueError("Empty OTA filesystem")
    with Path(destination).open("wb") as output:
        output.truncate(end*4096)
        for operation, blocks in operations:
            task.check()
            if operation != "new":
                continue
            for a, b in blocks:
                output.seek(a*4096)
                remaining = (b-a)*4096
                while remaining:
                    chunk = source.read(min(remaining, 1024**2))
                    if not chunk:
                        raise ValueError("Truncated OTA block data")
                    output.write(chunk)
                    remaining -= len(chunk)
    if source.read(1):
        raise ValueError("Unconsumed OTA block data")

def extract_system(image, root, task):
    """Read regular files only; never create links or device nodes on Windows."""
    root.mkdir()
    seen, total = set(), 0
    with image.open("rb") as stream:
        fs = ExtFS(stream)
        def walk(node, prefix="", depth=0):
            nonlocal total
            if depth > 32:
                raise ValueError("Filesystem nesting exceeds limit")
            for child in node.iterdir():
                task.check()
                if child.filename in (".", ".."):
                    continue
                relative = prefix + child.filename
                target = checked_child(root, relative)
                key = relative.casefold()
                if key in seen:
                    raise ValueError("Duplicate Windows filesystem path")
                seen.add(key)
                if len(seen) > 100000:
                    raise ValueError("Too many filesystem entries")
                if child.filetype == 0o040000:
                    target.mkdir()
                    walk(child, relative + "/", depth+1)
                elif child.filetype == 0o100000:
                    with child.open() as src, target.open("xb") as dest:
                        while chunk := src.read(1024**2):
                            total += len(chunk)
                            if total > MAX_IMAGE:
                                raise ValueError("Filesystem extraction exceeds limit")
                            dest.write(chunk)
        walk(fs.get("/"))

def stage(root, payload, task):
    out = payload / "camera"
    (out / "lib").mkdir(parents=True)
    queue = [root / "bin" / n for n in ("camera-gui", "dbus-daemon")]
    queue += [root / "lib64" / n for n in ("libweston.so", "libdbus.so")]
    seen = set()
    while queue:
        task.check()
        path = queue.pop()
        if path.name in seen:
            continue
        seen.add(path.name)
        with path.open("rb") as stream:
            elf = ELFFile(stream)
            if elf['e_machine'] != 'EM_AARCH64':
                raise ValueError("Expected AArch64 firmware binaries")
            dynamic = elf.get_section_by_name(".dynamic")
            for tag in dynamic.iter_tags() if dynamic else []:
                if tag.entry.d_tag == "DT_NEEDED" and tag.needed not in {"libc.so", "libm.so", "libdl.so", "liblog.so"}:
                    dependency = checked_child(root / "lib64", tag.needed)
                    queue.append(dependency)
        shutil.copy2(path, (out if path.parent.name == "bin" else out / "lib") / path.name)
    for src, dest in (("lib64/qt/lib/fonts", "fonts"), ("usr/share/X11/xkb", "xkb")):
        shutil.copytree(root / src, out / dest)
    (out / "etc").mkdir()
    for name in ("VERSION", "dji.json"):
        shutil.copy2(root / "etc" / name, out / "etc" / name)
    for src, dest in (("camera_run.sh", "run.sh"), ("dbus-local.conf", "dbus-local.conf")):
        (out / dest).write_bytes((ASSETS / "guest" / src).read_bytes().replace(b"\r\n", b"\n"))
    for name in ("mini_compositor", "mock_services", "dbus_launcher"):
        shutil.copy2(ASSETS / "helpers" / name, payload / name)
    adapt_software(out / "camera-gui", out / "camera-gui-software")
    write_json(out / "dependencies.json", sorted(seen))

def import_firmware(source, library, task=None):
    task = task or Task()
    source, library = Path(source), Path(library)
    if not 2048 <= source.stat().st_size <= 1024**3:
        raise ValueError("Unexpected firmware size (supported: 2 KB–1 GB)")
    task.report("Reading firmware / 读取固件…")
    raw = source.read_bytes()
    public, encrypted, iv, private, items = cim.load_container(raw)
    if not public['size_matches'] or public['product'] != '1800000_PVF':
        raise ValueError("Unsupported or truncated X2D II firmware container")
    digest = hashlib.sha256(raw).hexdigest()
    if digest not in PROFILES:
        raise ValueError(f"This firmware is not yet validated. Supported official full packages: {', '.join(PROFILES.values())}. Original file unchanged.")
    device = library / digest[:16]
    if (device / "device.json").exists():
        return device
    library.mkdir(parents=True, exist_ok=True)
    import tempfile
    with tempfile.TemporaryDirectory(prefix="import-", dir=library) as temporary:
        work = Path(temporary)
        ota = [i for i in items if i['name'] == 'ota.zip']
        if len(ota) != 1:
            raise ValueError("Expected one full OTA component")
        item = ota[0]
        task.report("Unpacking the local OTA / 解包本地 OTA…")
        data = cim.decrypt_component(raw, item, iv) if encrypted else raw[item['offset_in_cim']:item['offset_in_cim']+item['length']]
        del raw
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            required = ("system.transfer.list", "system.new.dat.br")
            for name in required:
                matches = [i for i in archive.infolist() if i.filename == name]
                if len(matches) != 1 or matches[0].file_size > MAX_IMAGE:
                    raise ValueError(f"Missing or oversized OTA member: {name}")
            transfer = archive.read(required[0]).decode("ascii")
            task.report("Expanding system blocks / 还原系统分区…")
            decoder, expanded = brotli.Decompressor(), 0
            dat = work / "system.dat"
            with archive.open(required[1]) as compressed, dat.open("wb") as output:
                while chunk := compressed.read(65536):
                    task.check()
                    result = decoder.process(chunk)
                    expanded += len(result)
                    if expanded > MAX_IMAGE:
                        raise ValueError("OTA expansion limit exceeded")
                    output.write(result)
            if not decoder.is_finished():
                raise ValueError("Truncated Brotli stream")
        del data
        with dat.open("rb") as stream:
            reconstruct(transfer, stream, work / "system.img", task)
        task.report("Reading the UI filesystem / 提取 UI 文件…")
        extract_system(work / "system.img", work / "system_root", task)
        root = work / "system_root"
        version = (root / "etc/VERSION").read_text().strip()
        if version != PROFILES[digest]:
            raise ValueError(f"Firmware version mismatch: {version}; original file unchanged.")
        task.report("Preparing original UI / 准备原厂 UI…")
        prepared = work / "prepared"
        prepared.mkdir()
        stage(root, prepared / "payload-stage", task)
        write_json(prepared / "device.json", {"name": "Hasselblad X2D II", "version": version,
                   "sha256": digest, "filename": source.name, "renderer": "Qt Quick software", "validated": True})
        task.check()
        prepared.rename(device)
    task.report("Firmware ready / 固件准备完成")
    return device
