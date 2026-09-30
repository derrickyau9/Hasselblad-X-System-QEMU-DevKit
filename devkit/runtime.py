"""Download pinned official runtimes into a per-user directory, without installers."""
from pathlib import Path
import hashlib
import os
import sys
import shutil
import tempfile
import urllib.request
import zipfile
from .core import ASSETS, Task, checked_child, read_json, write_json

MANIFEST = read_json(ASSETS / "downloads.json")

def _host_binary(name):
    """Return the executable name used by the current host."""
    return name + '.exe' if os.name == 'nt' else name

def _default_sdk_root():
    if os.name == 'nt':
        return Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'Android/Sdk'
    if sys.platform == 'darwin':
        return Path.home() / 'Library/Android/sdk'
    return Path.home() / 'Android/Sdk'

def checksum(path, algorithm):
    h = hashlib.new(algorithm)
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024**2), b""):
            h.update(chunk)
    return h.hexdigest()

def download(name, cache, task):
    spec = MANIFEST[name]
    target = cache / spec['url'].rsplit('/', 1)[1]
    cache.mkdir(parents=True, exist_ok=True)
    if target.exists() and checksum(target, spec['algorithm']) == spec['digest']:
        task.report(f"Cached / 已缓存: {name}")
        return target
    temporary = target.with_suffix(target.suffix + '.part')
    task.report(f"Downloading / 下载: {name}")
    request = urllib.request.Request(spec['url'], headers={"User-Agent": "X2DII-DevKit/0.1"})
    with urllib.request.urlopen(request, timeout=30) as response, temporary.open('wb') as output:
        size = int(response.headers.get('Content-Length', 0))
        downloaded, last_report = 0, -1
        while chunk := response.read(1024**2):
            task.check()
            output.write(chunk)
            downloaded += len(chunk)
            if downloaded > 3*1024**3:
                raise ValueError("Runtime download exceeds limit")
            percent = downloaded*100//size if size else 0
            if percent//5 != last_report:
                last_report = percent//5
                task.report(f"{name}: {percent}% · {downloaded//1024**2} MB")
    task.check()
    if checksum(temporary, spec['algorithm']) != spec['digest']:
        raise ValueError(f"Checksum failed: {name}. Retry the download.")
    temporary.replace(target)
    return target

def unzip(source, destination, task):
    total, seen = 0, set()
    with zipfile.ZipFile(source) as archive:
        for entry in archive.infolist():
            task.check()
            path = checked_child(destination, entry.filename.rstrip('/'))
            key = str(path).casefold()
            total += entry.file_size
            if key in seen or total > 6*1024**3 or (entry.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("Unsafe runtime archive")
            seen.add(key)
            if entry.is_dir():
                path.mkdir(parents=True, exist_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(entry) as src, path.open('xb') as dest:
                    shutil.copyfileobj(src, dest, 1024**2)

def validate(config):
    required = [Path(config['qemu']) / _host_binary(n) for n in ('qemu-system-aarch64', 'qemu-img', 'qemu-io')]
    required += [Path(config['image']) / n for n in ('kernel-ranchu', 'system.img', 'vendor.img', 'encryptionkey.img')]
    required.append(Path(config['mke2fs']))
    missing = [p.name for p in required if not p.is_file()]
    if missing:
        raise FileNotFoundError('Missing runtime files: ' + ', '.join(missing))
    # QEMU drive option syntax treats commas specially; don't silently misparse paths.
    if any(',' in str(p) for p in required):
        raise ValueError('Choose a runtime directory without commas')
    return config

def discover(home):
    configured = read_json(home / 'runtime.json')
    if configured:
        try:
            return validate(configured)
        except (KeyError, ValueError, FileNotFoundError):
            pass
    sdk = Path(os.environ.get('ANDROID_SDK_ROOT', os.environ.get('ANDROID_HOME', str(_default_sdk_root()))))
    qemu = shutil.which(_host_binary('qemu-system-aarch64'))
    if qemu:
        try:
            mke2fs = shutil.which(_host_binary('mke2fs')) or str(sdk / 'platform-tools' / _host_binary('mke2fs'))
            return validate({'qemu': str(Path(qemu).parent), 'image': str(sdk / 'system-images/android-28/default/arm64-v8a'), 'mke2fs': mke2fs})
        except (ValueError, FileNotFoundError):
            pass
    return None

def setup(home, task=None):
    task = task or Task()
    if os.name != 'nt':
        qemu = shutil.which(_host_binary('qemu-system-aarch64'))
        qemu_img = shutil.which(_host_binary('qemu-img'))
        qemu_io = shutil.which(_host_binary('qemu-io'))
        mke2fs = shutil.which(_host_binary('mke2fs'))
        sdk = Path(os.environ.get('ANDROID_SDK_ROOT', os.environ.get('ANDROID_HOME', str(_default_sdk_root()))))
        image = sdk / 'system-images/android-28/default/arm64-v8a'
        if not all((qemu, qemu_img, qemu_io, mke2fs)):
            raise FileNotFoundError('Install QEMU and mke2fs first (for example: brew install qemu e2fsprogs).')
        if not image.is_dir():
            raise FileNotFoundError(f'Android ARM64 API 28 image not found: {image}. Install it with sdkmanager or set ANDROID_SDK_ROOT.')
        config = {'qemu': str(Path(qemu).parent), 'image': str(image), 'mke2fs': str(mke2fs)}
        validate(config)
        write_json(home / 'runtime.json', config)
        task.report('Runtime ready / 运行环境准备完成')
        return config
    root, cache = home / 'runtime', home / 'downloads'
    root.mkdir(parents=True, exist_ok=True)
    # Each component is promoted only after a successful extraction.
    for name in ('7zip', 'qemu', 'android', 'platform-tools'):
        task.check()
        destination = root / name
        if (destination / '.complete').exists():
            continue
        with tempfile.TemporaryDirectory(prefix=f'{name}-', dir=root) as temp:
            stage = Path(temp) / 'files'
            stage.mkdir()
            if name == '7zip':
                small = download('7zr', cache, task)
                archive = download(name, cache, task)
                task.run([small, 'x', archive, '-o' + str(stage), '-y'])
            elif name == 'qemu':
                archive = download(name, cache, task)
                task.report('Extracting QEMU / 解包 QEMU…')
                task.run([root / '7zip/7z.exe', 'x', archive, '-o' + str(stage), '-y'], timeout=600)
            else:
                archive = download(name, cache, task)
                task.report(f'Extracting / 解包: {name}…')
                unzip(archive, stage, task)
            (stage / '.complete').touch()
            stage.rename(destination)
    config = {'qemu': str(root / 'qemu'), 'image': str(root / 'android/arm64-v8a'),
              'mke2fs': str(root / 'platform-tools/platform-tools/mke2fs.exe')}
    validate(config)
    write_json(home / 'runtime.json', config)
    task.report('Runtime ready / 运行环境准备完成')
    return config
