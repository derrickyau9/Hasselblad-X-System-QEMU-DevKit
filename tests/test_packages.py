"""Native guest packages must be bounded, verifiable and reversible."""

import hashlib
import json
import stat
import struct
import zipfile

import pytest

from devkit.core import write_json
from devkit.models import MODELS
from devkit.packages import (
    active_package, activate_package, inspect_package, install_package,
    list_packages, remove_package, rollback_package,
)


INTERPRETER = {
    'arm32': ('/system/bin/linker', 1, 40),
    'arm64': ('/system/bin/linker64', 2, 183),
    'linux-arm32': ('/lib/ld-linux-armhf.so.3', 1, 40),
}


def elf(abi, *, loader=None, machine=None):
    """A small valid ELF header with a PT_INTERP segment for package tests."""
    expected, elf_class, target_machine = INTERPRETER[abi]
    name = (loader or expected).encode() + b'\0'
    data = bytearray(256)
    data[:7] = b'\x7fELF' + bytes((elf_class, 1, 1))
    struct.pack_into('<HH', data, 16, 3, machine or target_machine)
    if elf_class == 1:
        struct.pack_into('<I', data, 28, 52)
        struct.pack_into('<HH', data, 42, 32, 1)
        struct.pack_into('<II', data, 52, 3, 160)
        struct.pack_into('<I', data, 52 + 16, len(name))
    else:
        struct.pack_into('<Q', data, 32, 64)
        struct.pack_into('<HH', data, 54, 56, 1)
        struct.pack_into('<IIQ', data, 64, 3, 0, 160)
        struct.pack_into('<Q', data, 64 + 32, len(name))
    data[160:160 + len(name)] = name
    return bytes(data)


def package(tmp_path, abi, model, *, version='1.0.0', entry=None,
            entries=None, manifest_changes=None, extra=None):
    entries = entries or {'bin/demo': elf(abi), 'assets/README.txt': b'example'}
    entry = entry or 'bin/demo'
    manifest = {
        'schema': 1, 'id': 'org.example.demo', 'version': version,
        'abi': abi, 'models': [model], 'entry': entry,
        'files': [{'path': name, 'size': len(value),
                   'sha256': hashlib.sha256(value).hexdigest()}
                  for name, value in entries.items()],
    }
    if manifest_changes:
        manifest.update(manifest_changes)
    target = tmp_path / f'{abi}-{version}-{len(list(tmp_path.iterdir()))}.xdevapp'
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('manifest.json', json.dumps(manifest))
        for name, value in entries.items():
            archive.writestr(name, value)
        for name, value in (extra or {}).items():
            archive.writestr(name, value)
    return target


def device(tmp_path, model):
    target = tmp_path / 'library' / model
    (target / 'payload-stage').mkdir(parents=True)
    write_json(target / 'device.json', {'abi': MODELS[model]['abi'], 'model': model})
    return target


@pytest.mark.parametrize('model', ['x1d', 'x1dii', 'x2dii'])
def test_package_install_select_rollback_and_remove(tmp_path, model):
    target = device(tmp_path, model)
    abi = MODELS[model]['abi']
    first = package(tmp_path, abi, model)
    assert inspect_package(first)['abi'] == abi
    record = install_package(target, first)
    assert record['payload_entry'] == 'apps/org.example.demo/1.0.0/bin/demo'
    assert active_package(target) is None
    assert list_packages(target)[0]['active'] is False
    activate_package(target, 'org.example.demo', '1.0.0')
    assert active_package(target)['version'] == '1.0.0'
    second = package(tmp_path, abi, model, version='2.0.0')
    install_package(target, second)
    activate_package(target, 'org.example.demo', '2.0.0')
    assert rollback_package(target)['version'] == '1.0.0'
    assert rollback_package(target)['version'] == '2.0.0'
    remove_package(target, 'org.example.demo', '2.0.0')
    assert active_package(target)['version'] == '1.0.0'
    assert [r['version'] for r in list_packages(target)] == ['1.0.0']
    remove_package(target, 'org.example.demo', '1.0.0')
    assert active_package(target) is None


@pytest.mark.parametrize('abi,model', [
    ('arm32', 'x1dii'), ('arm64', 'x2dii'), ('linux-arm32', 'x1d'),
])
def test_elf_machine_and_interpreter_must_match_guest(tmp_path, abi, model):
    wrong_machine = 183 if abi != 'arm64' else 40
    bad_machine = package(tmp_path, abi, model, entries={'bin/demo': elf(abi, machine=wrong_machine)})
    with pytest.raises(ValueError, match='machine'):
        inspect_package(bad_machine)
    bad_loader = package(tmp_path, abi, model, entries={'bin/demo': elf(abi, loader='/wrong/loader')})
    with pytest.raises(ValueError, match='interpreter'):
        inspect_package(bad_loader)


@pytest.mark.parametrize('bad_path', ['../escape', '/absolute', 'bin\\demo', 'bin/CON', 'bin/demo.', 'bin/a..b'])
def test_unsafe_archive_path_is_rejected_before_install(tmp_path, bad_path):
    entries = {bad_path: elf('arm64')}
    source = package(tmp_path, 'arm64', 'x2dii', entry=bad_path, entries=entries)
    target = device(tmp_path, 'x2dii')
    with pytest.raises(ValueError):
        install_package(target, source)
    assert not (target / 'payload-stage/apps').exists()


def test_casefold_collision_and_symlink_are_rejected(tmp_path):
    source = package(tmp_path, 'arm64', 'x2dii',
                     extra={'BIN/DEMO': b'collision'})
    with pytest.raises(ValueError, match='collision'):
        inspect_package(source)
    linked = tmp_path / 'symlink.xdevapp'
    manifest = {'schema': 1, 'id': 'org.example.demo', 'version': '1.0.0',
                'abi': 'arm64', 'models': ['x2dii'], 'entry': 'bin/demo',
                'files': [{'path': 'bin/demo', 'size': 256,
                           'sha256': hashlib.sha256(elf('arm64')).hexdigest()}]}
    with zipfile.ZipFile(linked, 'w') as archive:
        archive.writestr('manifest.json', json.dumps(manifest))
        info = zipfile.ZipInfo('bin/demo')
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(info, elf('arm64'))
    with pytest.raises(ValueError, match='member type'):
        inspect_package(linked)


def test_hash_mismatch_or_unlisted_content_cannot_stage(tmp_path):
    target = device(tmp_path, 'x2dii')
    source = package(tmp_path, 'arm64', 'x2dii',
                     manifest_changes={'files': [{'path': 'bin/demo', 'size': 256, 'sha256': '0' * 64}]},
                     entries={'bin/demo': elf('arm64')})
    with pytest.raises(ValueError, match='SHA-256'):
        install_package(target, source)
    source = package(tmp_path, 'arm64', 'x2dii', extra={'unexpected.txt': b'x'})
    with pytest.raises(ValueError, match='members'):
        inspect_package(source)
    assert not (target / 'payload-stage/apps').exists()


def test_active_package_detects_changed_payload(tmp_path):
    target = device(tmp_path, 'x2dii')
    source = package(tmp_path, 'arm64', 'x2dii')
    install_package(target, source)
    activate_package(target, 'org.example.demo', '1.0.0')
    binary = target / 'payload-stage/apps/org.example.demo/1.0.0/bin/demo'
    binary.write_bytes(binary.read_bytes()[:-1] + b'X')
    # Listing stays responsive; activation is the integrity gate.
    assert list_packages(target)[0]['id'] == 'org.example.demo'
    with pytest.raises(ValueError, match='hash changed'):
        active_package(target)


def test_model_gate_uses_selected_profile(tmp_path):
    target = device(tmp_path, '907x50c')
    write_json(target / 'device.json', {'abi': 'arm32', 'model': '907x50c',
                                        'available_models': ['x1dii', '907x50c']})
    source = package(tmp_path, 'arm32', 'x1dii')
    install_package(target, source)
    with pytest.raises(ValueError, match='model'):
        activate_package(target, 'org.example.demo', '1.0.0')
    write_json(target / 'device.json', {'abi': 'arm32', 'model': 'x1dii',
                                        'available_models': ['x1dii', '907x50c']})
    assert activate_package(target, 'org.example.demo', '1.0.0')['abi'] == 'arm32'


def test_legacy_x2dii_profile_without_abi_can_install_without_rewriting_it(tmp_path):
    target = device(tmp_path, 'x2dii')
    old_profile = {'name': 'Hasselblad X2D II', 'version': '1.3.16.2',
                   'sha256': '9789d6a9843d3880' + '0' * 48}
    write_json(target / 'device.json', old_profile)
    source = package(tmp_path, 'arm64', 'x2dii')
    assert install_package(target, source)['abi'] == 'arm64'
    assert activate_package(target, 'org.example.demo', '1.0.0')['id'] == 'org.example.demo'
    assert active_package(target)['payload_entry'].endswith('/bin/demo')
    assert json.loads((target / 'device.json').read_text()) == old_profile
