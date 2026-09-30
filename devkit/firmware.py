"""Import the UI filesystem from a user-supplied official full OTA package."""
from pathlib import Path
import hashlib
import io
import json
import shutil
import zipfile
import brotli
import bz2
import tarfile
from dissect.extfs import ExtFS
from elftools.elf.elffile import ELFFile
from . import cim
from .core import ASSETS, Task, checked_child, write_json
from .guest.software_ui import build as adapt_software, legacy_window

TESTED_VERSION = "1.2.7.16"
TESTED_SHA256 = "68aa9bce63c303a7d13ca4c14aae76be935925d596094bdcb92549cff42e1bc1"
PROFILES = {
    TESTED_SHA256: ('Hasselblad X2D II 100C', TESTED_VERSION, '1800000_PVF'),
    '9789d6a9843d388034bc12341ad9a97585c25cb98cf11a0da8b768399b4842f6':
        ('Hasselblad X2D II 100C', '1.3.16.2', '1800000_PVF'),
    '688eb3dec9dba21ac84ed6f11e57926ca4f1b68a9ddaaf2969083bfa8a38da24':
        ('Hasselblad X2D 100C', '1.0.5', '1800000_PVF'),
    '5ae67d16a24b00f9300e3e9c1323e7d149248ad36975e12c4fa8da633b438e03':
        ('Hasselblad X2D 100C', '4.2.0', '1800000_PVF'),
    '1bb69d26627d3af69dec75fd78653cd9769bd205f54ee4d6b1c5beae87b98cda':
        ('Hasselblad X1D II / 907X 50C', '1.5.2', '1700000_PVF'),
}
MAX_IMAGE = 2 * 1024**3
for digest, version in [
    ('74c964414ca62790b9f20b94ff92e719a27306e33c6a5f2612ebedbfd15cdbdd','1.20.0'),
    ('e6bea3675dec9fb2f8f1868e44fcd9a174b8df3278f7dac61f4f9c132abad900','1.21.0'),
    ('1b224ebe1f53d04a4352897c1ac1f50bc858d08048957382e4cb51ab16a5adf2','1.25.0'),
]:
    PROFILES[digest] = ('Hasselblad X1D 50C',version,'1601254_PVF')
for digest, version, product in [
    ('e8c9e5ac5add0e497e62ccea80904aebc8096133339d7171b44a725cb857a916','1.0.1','1600000_PVF'),
    ('a769877f9b5605fd2b105a4fcd2cf33ac0cf73bce6293867f93df5d314e24836','1.0.2','1700000_PVF'),
    ('0517ab6d72e39659f9edab5455a5bbbc9927097e46fe85c49f350fce79746ee2','1.1.0','1700000_PVF'),
    ('6a2c905bde9e255b5b15bf345f563ad1b27918899c43a4757dfcdb19593e0c09','1.2.0','1700000_PVF'),
    ('0020f1b09ea29ea70bf86d40c4a89125a303d39db1c20e3a3acae255eb131406','1.3.0','1700000_PVF'),
    ('5edcf0a309d0589df09748eca1686b1e305ff09de0d41acb10a1604835661164','1.4.0','1700000_PVF'),
]:
    PROFILES[digest] = ('Hasselblad X1D II 50C',version,product)

def profile_metadata(name, version, digest, filename, abi):
    model = 'x1d' if abi == 'linux-arm32' else ('x1dii' if abi == 'arm32' else ('x2d' if name == 'Hasselblad X2D 100C' else 'x2dii'))
    models = ['x1dii','907x50c'] if digest.startswith('1bb69d26627d3af6') else [model]
    if filename.lower().startswith('cfv_ii') and '907x50c' in models: model = '907x50c'
    return {'name':name,'version':version,'sha256':digest,'filename':filename,'abi':abi,
            'model':model,'available_models':models,'renderer':'Qt Quick software',
            'validated': model == 'x2dii', 'ui_status':'verified' if model == 'x2dii' else 'experimental'}

def stage_legacy(data, payload, task):
    """Preserve Unix links inside a guest-only tar; never extract them on the host."""
    payload.mkdir(parents=True)
    target = payload / 'rootfs.tar'
    total = 0
    with bz2.BZ2File(io.BytesIO(data)) as source, target.open('wb') as dest:
        while chunk := source.read(1024**2):
            task.check(); total += len(chunk)
            if total > MAX_IMAGE: raise ValueError('Legacy filesystem expansion exceeds limit')
            dest.write(chunk)
    camera = payload / 'camera'; camera.mkdir()
    with tarfile.open(target) as archive:
        names = {m.name.removeprefix('./') for m in archive}
        if 'usr/bin/victory-gui' not in names:
            raise ValueError('Legacy firmware has no supported original UI')
        gui = next(m for m in archive.getmembers() if m.name.removeprefix('./') == 'usr/bin/victory-gui')
        if not gui.isfile() or gui.size>100*1024**2: raise ValueError('Invalid legacy UI executable')
        (camera / 'victory-gui').write_bytes(archive.extractfile(gui).read())
    legacy_window(camera / 'victory-gui',camera / 'victory-gui-software')
    for src, dest in [('legacy_run.sh','run.sh'),('linux_ui.sh','linux_ui.sh'),('dbus-local.conf','dbus-local.conf')]:
        (camera / dest).write_bytes((ASSETS / 'guest' / src).read_bytes().replace(b'\r\n',b'\n'))

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
    gui = root / 'bin/camera-gui'
    if not gui.exists():
        gui = root / 'bin/victory-gui-static'
    with gui.open('rb') as stream:
        machine = ELFFile(stream)['e_machine']
    if machine not in ('EM_AARCH64', 'EM_ARM'):
        raise ValueError('Unsupported UI architecture')
    abi = 'arm32' if machine == 'EM_ARM' else 'arm64'
    libdir = 'lib' if abi == 'arm32' else 'lib64'
    queue = [gui, root / 'bin/dbus-daemon']
    queue += [root / libdir / n for n in ("libweston.so", "libdbus.so", "libwayland-client.so")]
    seen = set()
    while queue:
        task.check()
        path = queue.pop()
        if path.name in seen:
            continue
        seen.add(path.name)
        with path.open("rb") as stream:
            elf = ELFFile(stream)
            if elf['e_machine'] != machine:
                raise ValueError("Mixed firmware binary architectures")
            dynamic = elf.get_section_by_name(".dynamic")
            for tag in dynamic.iter_tags() if dynamic else []:
                if tag.entry.d_tag == "DT_NEEDED" and (abi == 'arm32' or tag.needed not in {"libc.so", "libm.so", "libdl.so", "liblog.so"}):
                    dependency = checked_child(root / libdir, tag.needed)
                    queue.append(dependency)
        shutil.copy2(path, (out if path.parent.name == "bin" else out / "lib") / path.name)
    for src, dest in ((f"{libdir}/qt/lib/fonts", "fonts"), ("usr/share/X11/xkb", "xkb")):
        shutil.copytree(root / src, out / dest)
    (out / "etc").mkdir()
    for name in ("VERSION", "dji.json"):
        shutil.copy2(root / "etc" / name, out / "etc" / name)
    for src, dest in (("camera_run.sh", "run.sh"), ("dbus-local.conf", "dbus-local.conf")):
        (out / dest).write_bytes((ASSETS / "guest" / src).read_bytes().replace(b"\r\n", b"\n"))
    for name in ("mini_compositor", "mock_services", "dbus_launcher"):
        helper_dir = ASSETS / 'helpers' / 'arm32' if abi == 'arm32' else ASSETS / 'helpers'
        shutil.copy2(helper_dir / name, payload / name)
    if abi == 'arm32':
        shutil.copy2(root / 'bin/linker', out / 'linker')
    adapt_software(out / gui.name, out / "camera-gui-software")
    write_json(out / "dependencies.json", sorted(seen))
    return abi

def import_firmware(source, library, task=None):
    task = task or Task()
    source, library = Path(source), Path(library)
    if not 2048 <= source.stat().st_size <= 1024**3:
        raise ValueError("Unexpected firmware size (supported: 2 KB–1 GB)")
    task.report("Reading firmware / 读取固件…")
    raw = source.read_bytes()
    public, encrypted, iv, private, items = cim.load_container(raw)
    if not public['size_matches']:
        raise ValueError("Truncated firmware container")
    digest = hashlib.sha256(raw).hexdigest()
    if digest not in PROFILES:
        raise ValueError("This firmware has not been validated for the DevKit. Original file unchanged.")
    name, expected_version, expected_product = PROFILES[digest]
    if public['product'] != expected_product:
        raise ValueError("Firmware product identifier does not match its validated profile")
    device = library / digest[:16]
    if (device / "device.json").exists():
        return device
    library.mkdir(parents=True, exist_ok=True)
    import tempfile
    with tempfile.TemporaryDirectory(prefix="import-", dir=library) as temporary:
        work = Path(temporary)
        if expected_product == '1601254_PVF':
            roots = [i for i in items if i['name'] == 'rootfs']
            if len(roots) != 1: raise ValueError('Expected one legacy root filesystem')
            item = roots[0]
            data = cim.decrypt_component(raw,item,iv) if encrypted else raw[item['offset_in_cim']:item['offset_in_cim']+item['length']]
            prepared = work / 'prepared'
            stage_legacy(data,prepared / 'payload-stage',task)
            write_json(prepared / 'device.json',profile_metadata(name,expected_version,digest,source.name,'linux-arm32'))
            task.check(); prepared.rename(device)
            task.report('Firmware imported / 固件已导入')
            return device
        ota = [i for i in items if i['name'] == 'ota.zip']
        if len(ota) != 1:
            raise ValueError("Expected one full OTA component")
        item = ota[0]
        task.report("Unpacking the local OTA / 解包本地 OTA…")
        data = cim.decrypt_component(raw, item, iv) if encrypted else raw[item['offset_in_cim']:item['offset_in_cim']+item['length']]
        del raw
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            dat_member = 'system.new.dat.br' if 'system.new.dat.br' in archive.namelist() else 'system.new.dat'
            required = ("system.transfer.list", dat_member)
            for member_name in required:
                matches = [i for i in archive.infolist() if i.filename == member_name]
                if len(matches) != 1 or matches[0].file_size > MAX_IMAGE:
                    raise ValueError(f"Missing or oversized OTA member: {member_name}")
            transfer = archive.read(required[0]).decode("ascii")
            task.report("Expanding system blocks / 还原系统分区…")
            decoder = brotli.Decompressor() if dat_member.endswith('.br') else None
            expanded = 0
            dat = work / "system.dat"
            with archive.open(required[1]) as compressed, dat.open("wb") as output:
                while chunk := compressed.read(65536):
                    task.check()
                    result = decoder.process(chunk) if decoder else chunk
                    expanded += len(result)
                    if expanded > MAX_IMAGE:
                        raise ValueError("OTA expansion limit exceeded")
                    output.write(result)
            if decoder and not decoder.is_finished():
                raise ValueError("Truncated Brotli stream")
        del data
        with dat.open("rb") as stream:
            reconstruct(transfer, stream, work / "system.img", task)
        task.report("Reading the UI filesystem / 提取 UI 文件…")
        extract_system(work / "system.img", work / "system_root", task)
        root = work / "system_root"
        version = (root / "etc/VERSION").read_text().strip()
        if version != expected_version:
            raise ValueError(f"Firmware version mismatch: {version}; original file unchanged.")
        task.report("Preparing original UI / 准备原厂 UI…")
        prepared = work / "prepared"
        prepared.mkdir()
        abi = stage(root, prepared / "payload-stage", task)
        write_json(prepared / 'device.json',profile_metadata(name,version,digest,source.name,abi))
        task.check()
        prepared.rename(device)
    task.report("Firmware ready / 固件准备完成")
    return device
