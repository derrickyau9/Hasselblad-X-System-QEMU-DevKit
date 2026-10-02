"""Install explicitly selected guest apps into the disposable QEMU payload.

This module does not communicate with or install anything on a camera.  Packages
are native code, so validation establishes format and guest compatibility, not
trustworthiness of the code itself.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import struct
import tempfile
import unicodedata
import zipfile

from .core import GuestLock, Task, checked_child, read_json, write_json
from .models import MODELS, available_models, model_id


MAX_ARCHIVE_BYTES = 256 * 1024 * 1024
MAX_CONTENT_BYTES = 512 * 1024 * 1024
MAX_FILE_BYTES = 256 * 1024 * 1024
MAX_MANIFEST_BYTES = 64 * 1024
MAX_FILES = 512
_IDENTIFIER = re.compile(r"[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*\Z")
_VERSION = re.compile(r"[0-9][a-z0-9]*(?:[._+-][a-z0-9]+)*\Z")
_ENTRY = re.compile(r"[A-Za-z0-9._/-]+\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_ELF_TARGETS = {
    'arm32': (1, 40, '/system/bin/linker'),
    'arm64': (2, 183, '/system/bin/linker64'),
    'linux-arm32': (1, 40, '/lib/ld-linux-armhf.so.3'),
}


def _name(value, pattern, maximum, what):
    if not isinstance(value, str) or len(value) > maximum or not pattern.fullmatch(value):
        raise ValueError(f'Invalid {what}: {value!r}')
    return value


def _relative(value):
    if not isinstance(value, str) or not value or len(value.encode('utf-8', errors='surrogatepass')) > 240:
        raise ValueError('Invalid package path')
    if '\\' in value or unicodedata.normalize('NFC', value) != value or any(len(p) > 100 for p in value.split('/')):
        raise ValueError(f'Invalid package path: {value!r}')
    # checked_child rejects traversal, device names, ADS and unsafe Windows names.
    checked_child(Path(tempfile.gettempdir()) / 'xdevapp-path-check', value)
    return value


def _json_unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'Duplicate JSON key: {key}')
        result[key] = value
    return result


def _validate_manifest(manifest):
    if not isinstance(manifest, dict) or set(manifest) != {'schema', 'id', 'version', 'abi', 'models', 'entry', 'files'}:
        raise ValueError('Package manifest must contain schema, id, version, abi, models, entry and files')
    if type(manifest['schema']) is not int or manifest['schema'] != 1:
        raise ValueError('Unsupported package schema')
    _name(manifest['id'], _IDENTIFIER, 80, 'app ID')
    _name(manifest['version'], _VERSION, 64, 'app version')
    abi = manifest['abi']
    if not isinstance(abi, str) or abi not in _ELF_TARGETS:
        raise ValueError(f'Unsupported guest ABI: {abi!r}')
    models = manifest['models']
    if not isinstance(models, list) or not models or len(models) != len(set(str(m) for m in models)):
        raise ValueError('models must be a nonempty list of distinct model IDs')
    if any(not isinstance(m, str) or m not in MODELS or MODELS[m]['abi'] != abi for m in models):
        raise ValueError('models and abi do not agree')
    entry = _relative(manifest['entry'])
    if not _ENTRY.fullmatch(entry) or '..' in entry:
        raise ValueError('Entrypoint path must use shell-safe ASCII characters')
    files = manifest['files']
    if not isinstance(files, list) or not files or len(files) > MAX_FILES:
        raise ValueError('Invalid package file list')
    seen = {'manifest.json'}
    total = 0
    for item in files:
        if not isinstance(item, dict) or set(item) != {'path', 'size', 'sha256'}:
            raise ValueError('Each file needs path, size and sha256')
        path = _relative(item['path'])
        folded = path.casefold()
        if folded in seen:
            raise ValueError(f'Duplicate or reserved package path: {path}')
        seen.add(folded)
        size = item['size']
        if type(size) is not int or size < 0 or size > MAX_FILE_BYTES:
            raise ValueError(f'Invalid size for {path}')
        total += size
        if total > MAX_CONTENT_BYTES:
            raise ValueError('Package contents exceed size limit')
        if not isinstance(item['sha256'], str) or not _SHA256.fullmatch(item['sha256']):
            raise ValueError(f'Invalid SHA-256 for {path}')
    if entry not in {f['path'] for f in files}:
        raise ValueError('Entrypoint is missing from package files')
    if next(f['size'] for f in files if f['path'] == entry) == 0:
        raise ValueError('Entrypoint is empty')
    for item in files:
        parts = item['path'].split('/')
        if any('/'.join(parts[:i]).casefold() in seen for i in range(1, len(parts))):
            raise ValueError(f'File conflicts with parent directory: {item["path"]}')
    return manifest


def _elf_check(stream, size, abi, executable):
    """Read only bounded ELF headers and the PT_INTERP string."""
    stream.seek(0)
    head = stream.read(64)
    if len(head) < 52 or head[:4] != b'\x7fELF' or head[5] != 1 or head[6] != 1:
        raise ValueError('Entrypoint is not a little-endian ELF executable')
    elf_class, machine, interpreter = _ELF_TARGETS[abi]
    if head[4] != elf_class:
        raise ValueError('ELF class does not match guest ABI')
    if struct.unpack_from('<H', head, 18)[0] != machine:
        raise ValueError('ELF machine does not match guest ABI')
    if struct.unpack_from('<H', head, 16)[0] not in (2, 3):
        raise ValueError('ELF file is not an executable or PIE')
    if elf_class == 1:
        offset, ent_size, count, standard = struct.unpack_from('<I', head, 28)[0], *struct.unpack_from('<HH', head, 42), 32
    else:
        if len(head) < 64:
            raise ValueError('Truncated ELF header')
        offset, ent_size, count, standard = struct.unpack_from('<Q', head, 32)[0], *struct.unpack_from('<HH', head, 54), 56
    if not 1 <= count <= 128 or not standard <= ent_size <= 128 or offset + ent_size * count > size:
        raise ValueError('Invalid ELF program header table')
    interpreters = []
    for index in range(count):
        stream.seek(offset + index * ent_size)
        program = stream.read(standard)
        if len(program) != standard:
            raise ValueError('Truncated ELF program header')
        if struct.unpack_from('<I', program)[0] != 3:  # PT_INTERP
            continue
        if elf_class == 1:
            start, length = struct.unpack_from('<I', program, 4)[0], struct.unpack_from('<I', program, 16)[0]
        else:
            start, length = struct.unpack_from('<Q', program, 8)[0], struct.unpack_from('<Q', program, 32)[0]
        if length < 2 or length > 256 or start + length > size:
            raise ValueError('Invalid ELF interpreter path')
        stream.seek(start)
        raw = stream.read(length)
        if len(raw) != length or raw[-1:] != b'\0' or b'\0' in raw[:-1]:
            raise ValueError('Invalid ELF interpreter string')
        interpreters.append(raw[:-1].decode('ascii', errors='strict'))
    if len(interpreters) > 1 or (interpreters and interpreters[0] != interpreter):
        raise ValueError(f'ELF interpreter must be {interpreter}')
    if executable and interpreters != [interpreter]:
        raise ValueError(f'Entrypoint must use guest interpreter {interpreter}')


def _validate_zip_info(info):
    mode = (info.external_attr >> 16) & 0o170000 if info.create_system == 3 else 0
    if mode not in (0, stat.S_IFREG, stat.S_IFDIR) or info.flag_bits & 1:
        raise ValueError(f'Unsupported archive member type: {info.filename}')
    if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
        raise ValueError(f'Unsupported ZIP compression: {info.filename}')
    name = info.filename[:-1] if info.is_dir() else info.filename
    _relative(name)
    if info.is_dir() and info.file_size:
        raise ValueError(f'Directory contains bytes: {name}')
    if not info.is_dir() and info.file_size > MAX_FILE_BYTES:
        raise ValueError(f'Archive member too large: {name}')
    return name


def _read_zip(package):
    package = Path(package)
    if not package.is_file() or package.stat().st_size > MAX_ARCHIVE_BYTES:
        raise ValueError('Package is missing or exceeds archive size limit')
    archive = zipfile.ZipFile(package)
    try:
        if len(archive.infolist()) > MAX_FILES * 4 + 1:
            raise ValueError('Too many archive members')
        members = {}
        directories = set()
        seen = set()
        total = 0
        for info in archive.infolist():
            name = _validate_zip_info(info)
            folded = name.casefold()
            if folded in seen:
                raise ValueError(f'Case-insensitive archive path collision: {name}')
            seen.add(folded)
            if info.is_dir():
                directories.add(name)
            else:
                members[name] = info
                total += info.file_size
                if total > MAX_CONTENT_BYTES or len(members) > MAX_FILES + 1:
                    raise ValueError('Package contents exceed size limit')
        info = members.get('manifest.json')
        if not info or info.file_size > MAX_MANIFEST_BYTES:
            raise ValueError('Missing or oversized manifest.json')
        with archive.open(info) as source:
            raw = source.read(MAX_MANIFEST_BYTES + 1)
        if len(raw) != info.file_size:
            raise ValueError('Truncated manifest.json')
        manifest = _validate_manifest(json.loads(raw.decode('utf-8'), object_pairs_hook=_json_unique))
        expected = {item['path'] for item in manifest['files']}
        if set(members) != expected | {'manifest.json'}:
            raise ValueError('ZIP members must match the manifest file list')
        if any(not any(path.startswith(directory + '/') for path in expected) for directory in directories):
            raise ValueError('Unreferenced archive directory')
        for item in manifest['files']:
            name = item['path']
            info = members[name]
            if info.file_size != item['size']:
                raise ValueError(f'Size mismatch: {name}')
            digest = hashlib.sha256()
            with archive.open(info) as source:
                first = source.read(min(65536, info.file_size))
                digest.update(first)
                actual = len(first)
                while chunk := source.read(1024 * 1024):
                    actual += len(chunk)
                    if actual > item['size']:
                        raise ValueError(f'Size mismatch: {name}')
                    digest.update(chunk)
            if actual != item['size'] or digest.hexdigest() != item['sha256']:
                raise ValueError(f'SHA-256 mismatch: {name}')
            if first.startswith(b'\x7fELF') or name == manifest['entry']:
                with archive.open(info) as source:
                    _elf_check(source, item['size'], manifest['abi'], name == manifest['entry'])
        return archive, manifest, members
    except BaseException:
        archive.close()
        raise


def inspect_package(package):
    """Validate every ZIP byte and return the schema-1 manifest."""
    archive, manifest, _ = _read_zip(package)
    archive.close()
    return manifest


def _apps_root(device, create=False):
    device = Path(device).resolve()
    payload = device / 'payload-stage'
    if create and not payload.is_dir():
        raise FileNotFoundError(f'Firmware payload is missing: {payload}')
    root = payload / 'apps'
    if payload.is_symlink() or root.is_symlink() or not root.resolve().is_relative_to(device):
        raise ValueError('App directory escapes selected guest')
    if create:
        root.mkdir(exist_ok=True)
    return root


def _version_dir(device, app_id, version, create=False):
    _name(app_id, _IDENTIFIER, 80, 'app ID')
    _name(version, _VERSION, 64, 'app version')
    root = _apps_root(device, create)
    parent = root / app_id
    if parent.is_symlink() or not parent.resolve().is_relative_to(root.resolve()):
        raise ValueError('App directory escapes selected guest')
    if create:
        parent.mkdir(exist_ok=True)
    target = parent / version
    if target.is_symlink() or not target.resolve().is_relative_to(root.resolve()):
        raise ValueError('App version escapes selected guest')
    return target


def _installed(device, app_id, version, verify=True):
    folder = _version_dir(device, app_id, version)
    if not folder.is_dir() or folder.is_symlink():
        raise FileNotFoundError(f'App is not installed: {app_id} {version}')
    manifest_path = folder / 'manifest.json'
    if manifest_path.is_symlink() or not manifest_path.is_file() or manifest_path.stat().st_size > MAX_MANIFEST_BYTES:
        raise ValueError('Installed app manifest is missing or invalid')
    manifest = _validate_manifest(json.loads(manifest_path.read_text(encoding='utf-8'), object_pairs_hook=_json_unique))
    if (manifest['id'], manifest['version']) != (app_id, version):
        raise ValueError('Installed app identity does not match its directory')
    expected = {item['path'] for item in manifest['files']}
    for root, directories, files in os.walk(folder, followlinks=False):
        for name in directories + files:
            if (Path(root) / name).is_symlink():
                raise ValueError('Installed app contains a symlink')
        for name in files:
            relative = (Path(root) / name).relative_to(folder).as_posix()
            if relative != 'manifest.json' and relative not in expected:
                raise ValueError(f'Undeclared installed app file: {relative}')
    for item in manifest['files']:
        path = folder / item['path']
        if not path.is_file() or path.is_symlink() or path.stat().st_size != item['size']:
            raise ValueError(f'Installed app file is missing or changed: {item["path"]}')
        if verify:
            digest = hashlib.sha256()
            with path.open('rb') as source:
                first = source.read(min(65536, item['size']))
                digest.update(first)
                while chunk := source.read(1024 * 1024):
                    digest.update(chunk)
            if digest.hexdigest() != item['sha256']:
                raise ValueError(f'Installed app hash changed: {item["path"]}')
            if first.startswith(b'\x7fELF') or item['path'] == manifest['entry']:
                with path.open('rb') as source:
                    _elf_check(source, item['size'], manifest['abi'], item['path'] == manifest['entry'])
    return {**manifest, 'payload_entry': f"apps/{app_id}/{version}/{manifest['entry']}"}


def _device_profile(device):
    profile = read_json(Path(device) / 'device.json')
    if not profile:
        raise ValueError('Select an imported firmware before installing guest apps')
    derived = MODELS[model_id(profile)]['abi']
    abi = profile.get('abi', derived)
    if abi != derived or abi not in _ELF_TARGETS:
        raise ValueError('Firmware model and ABI do not agree')
    # Earlier X2D II imports have no ABI field. Keep their on-disk metadata intact.
    return {**profile, 'abi': abi}


def _compatible(manifest, profile, active=False):
    if manifest['abi'] != profile['abi']:
        raise ValueError('Package ABI does not match the selected firmware')
    supported = [model_id(profile)] if active else available_models(profile)
    if not any(model in manifest['models'] for model in supported):
        raise ValueError('Package does not support the selected firmware model')


def install_package(device, package, task=None):
    """Validate and atomically stage a ZIP. Installing does not activate it."""
    device = Path(device)
    task = task or Task(lambda *_: None)
    with GuestLock(device):
        archive, manifest, members = _read_zip(package)
        try:
            _compatible(manifest, _device_profile(device))
            target = _version_dir(device, manifest['id'], manifest['version'], create=True)
            if target.exists():
                existing = _installed(device, manifest['id'], manifest['version'])
                if existing != {**manifest, 'payload_entry': existing['payload_entry']}:
                    raise FileExistsError('This app version is already installed with different contents')
                return existing
            parent = target.parent
            temporary = Path(tempfile.mkdtemp(prefix='.staging-', dir=parent))
            try:
                for item in manifest['files']:
                    task.check()
                    name = item['path']
                    destination = checked_child(temporary, name)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    digest = hashlib.sha256()
                    actual = 0
                    with archive.open(members[name]) as source, destination.open('xb') as output:
                        while chunk := source.read(1024 * 1024):
                            actual += len(chunk)
                            if actual > item['size']:
                                raise ValueError(f'Size changed during install: {name}')
                            digest.update(chunk)
                            output.write(chunk)
                    if actual != item['size'] or digest.hexdigest() != item['sha256']:
                        raise ValueError(f'Package changed during install: {name}')
                (temporary / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
                task.check()
                os.replace(temporary, target)
            finally:
                if temporary.exists():
                    shutil.rmtree(temporary)
            task.report(f"Installed guest app / 已安装虚拟机应用: {manifest['id']} {manifest['version']}")
            return _installed(device, manifest['id'], manifest['version'])
        finally:
            archive.close()


def _pointer_path(device):
    return Path(device) / 'active-app.json'


def _read_pointer(device):
    path = _pointer_path(device)
    if path.is_symlink() or (path.exists() and path.stat().st_size > MAX_MANIFEST_BYTES):
        raise ValueError('Invalid active app pointer')
    pointer = read_json(path)
    if not pointer:
        return None
    if not isinstance(pointer, dict) or set(pointer) != {'schema', 'id', 'version', 'previous'} or type(pointer['schema']) is not int or pointer['schema'] != 1:
        raise ValueError('Invalid active app pointer')
    _name(pointer['id'], _IDENTIFIER, 80, 'app ID')
    _name(pointer['version'], _VERSION, 64, 'app version')
    previous = pointer['previous']
    if previous is not None:
        if not isinstance(previous, dict) or set(previous) != {'id', 'version'}:
            raise ValueError('Invalid previous app pointer')
        _name(previous['id'], _IDENTIFIER, 80, 'app ID')
        _name(previous['version'], _VERSION, 64, 'app version')
    return pointer


def _set_pointer(device, pointer):
    path = _pointer_path(device)
    if pointer is None:
        path.unlink(missing_ok=True)
    else:
        write_json(path, pointer)


def active_package(device):
    """Return validated active package details, or None."""
    pointer = _read_pointer(device)
    if pointer is None:
        return None
    record = _installed(device, pointer['id'], pointer['version'])
    _compatible(record, _device_profile(device), active=True)
    return record


def list_packages(device):
    """List validated installed packages for the selected firmware library."""
    root = _apps_root(device)
    if not root.exists():
        return []
    pointer = _read_pointer(device)
    result = []
    for app_dir in sorted(root.iterdir()):
        if app_dir.name.startswith('.staging-'):
            continue
        if not app_dir.is_dir() or app_dir.is_symlink():
            raise ValueError(f'Invalid app directory: {app_dir.name}')
        for version_dir in sorted(app_dir.iterdir()):
            if version_dir.name.startswith('.staging-'):
                continue
            record = _installed(device, app_dir.name, version_dir.name, verify=False)
            record['active'] = bool(pointer and (pointer['id'], pointer['version']) == (record['id'], record['version']))
            result.append(record)
    return result


def activate_package(device, app_id, version):
    """Select an installed package for the next QEMU app session."""
    device = Path(device)
    with GuestLock(device):
        record = _installed(device, app_id, version)
        _compatible(record, _device_profile(device), active=True)
        current = _read_pointer(device)
        if current and (current['id'], current['version']) == (app_id, version):
            return record
        previous = {'id': current['id'], 'version': current['version']} if current else None
        _set_pointer(device, {'schema': 1, 'id': app_id, 'version': version, 'previous': previous})
        return record


def rollback_package(device):
    """Re-select the previously active app; the current app remains installed."""
    device = Path(device)
    with GuestLock(device):
        pointer = _read_pointer(device)
        if not pointer or not pointer['previous']:
            raise ValueError('No previous app to restore')
        previous = pointer['previous']
        record = _installed(device, previous['id'], previous['version'])
        _compatible(record, _device_profile(device), active=True)
        _set_pointer(device, {'schema': 1, **previous,
                              'previous': {'id': pointer['id'], 'version': pointer['version']}})
        return record


def remove_package(device, app_id, version):
    """Uninstall one version; restore previous selection when possible."""
    device = Path(device)
    with GuestLock(device):
        _installed(device, app_id, version)
        pointer = _read_pointer(device)
        selected = bool(pointer and (pointer['id'], pointer['version']) == (app_id, version))
        if selected:
            previous = pointer['previous']
            replacement = None
            if previous:
                try:
                    record = _installed(device, previous['id'], previous['version'])
                    _compatible(record, _device_profile(device), active=True)
                    replacement = {'schema': 1, **previous, 'previous': None}
                except (FileNotFoundError, ValueError):
                    pass
            _set_pointer(device, replacement)
        elif pointer and pointer['previous'] == {'id': app_id, 'version': version}:
            _set_pointer(device, {**pointer, 'previous': None})
        folder = _version_dir(device, app_id, version)
        shutil.rmtree(folder)
        if not any(folder.parent.iterdir()):
            folder.parent.rmdir()
