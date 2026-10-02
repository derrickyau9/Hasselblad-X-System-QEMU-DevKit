"""Build and manage guest-only .xdevapp packages; never connects to a camera."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from devkit.packages import (inspect_package, install_package, activate_package,
                             remove_package, list_packages, active_package,
                             rollback_package)

parser = argparse.ArgumentParser(description=__doc__)
commands = parser.add_subparsers(dest='command', required=True)
pack = commands.add_parser('pack', help='Package an already cross-compiled guest ELF')
pack.add_argument('--binary', type=Path, required=True)
pack.add_argument('--id', required=True)
pack.add_argument('--version', required=True)
pack.add_argument('--abi', choices=['arm32', 'arm64', 'linux-arm32'], required=True)
pack.add_argument('--model', action='append', required=True)
pack.add_argument('--output', type=Path, required=True)
inspect = commands.add_parser('inspect')
inspect.add_argument('archive', type=Path)
for name in ('install', 'list', 'activate', 'remove', 'active', 'rollback'):
    cmd = commands.add_parser(name)
    cmd.add_argument('--device', type=Path, required=True, help='Imported firmware library directory')
    if name == 'install': cmd.add_argument('archive', type=Path)
    if name in ('activate', 'remove'):
        cmd.add_argument('id'); cmd.add_argument('version')
args = parser.parse_args()

if args.command == 'pack':
    payload = args.binary.read_bytes()
    manifest = {
        'schema': 1, 'id': args.id, 'version': args.version, 'abi': args.abi,
        'models': args.model, 'entry': 'bin/app',
        'files': [{'path': 'bin/app', 'size': len(payload),
                   'sha256': hashlib.sha256(payload).hexdigest()}],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.output, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False))
        archive.writestr('bin/app', payload)
    try:
        print(json.dumps(inspect_package(args.output), ensure_ascii=False, indent=2))
    except Exception:
        args.output.unlink(missing_ok=True)
        raise
elif args.command == 'inspect':
    print(json.dumps(inspect_package(args.archive), ensure_ascii=False, indent=2))
else:
    device = args.device.resolve()
    if not (device / 'device.json').is_file():
        parser.error('--device must name an imported firmware library directory')
    if args.command == 'install': value = install_package(device, args.archive)
    elif args.command == 'activate': value = activate_package(device, args.id, args.version)
    elif args.command == 'remove': value = remove_package(device, args.id, args.version)
    elif args.command == 'rollback': value = rollback_package(device)
    elif args.command == 'active': value = active_package(device)
    else: value = list_packages(device)
    print(json.dumps(value, ensure_ascii=False, indent=2))
