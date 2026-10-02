"""Build an X2D II QEMU-only ARM64 NetSurf package with a private glibc loader.

Debian Bullseye arm64 NetSurf 3.10-1+b1 and its exact dependency closure are
locked in ``netsurf-bullseye-arm64-lock.json``. The .xdevapp entrypoint is a
small Android Bionic ELF; it explicitly executes the bundled Debian glibc
loader, which loads NetSurf and private libraries from the same package.
Nothing is written to a camera, Android system partition or host system.

Usage: python scripts/prepare_netsurf_arm64.py --home .local
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import io
import json
from pathlib import Path
import posixpath
import re
import struct
import subprocess
import tarfile
import tempfile

from prepare_netsurf import (APP_ID, APP_VERSION, ar_member, collect_debian_files,
                             compiler_tools, create_package, elf_needed,
                             fetch_one, find_ndk, offline_page, submitted_page, resolve_file,
                             verify_debian_packages)
from devkit.linux_runtime import deb_data


ROOT = Path(__file__).resolve().parents[1]
LOCK = Path(__file__).with_name('netsurf-bullseye-arm64-lock.json')
GUEST_ROOT = f'/mnt/x2dii/apps/{APP_ID}/{APP_VERSION}'


def certificate_bundle(package: Path) -> tuple[bytes, int]:
    """Bundle Bullseye's enabled Mozilla roots from its pinned package.

    The Debian post-install hooks that normally create /etc/ssl/certs are not
    run in the isolated guest app. Debian's control/config declares the
    initial enabled certificate list (CERTS_LIST), which we use to exclude
    any bundled but disabled roots. No host trust store is read or modified.
    """
    raw = package.read_bytes()
    with tarfile.open(fileobj=io.BytesIO(ar_member(raw, b'control.tar'))) as archive:
        config = archive.extractfile('./config').read()
    match = re.search(rb'^CERTS_LIST="([^"]*)"$', config, re.MULTILINE)
    if match is None:
        raise ValueError('Bullseye default CA trust list is absent')
    enabled = [name.strip().decode('utf-8') for name in match.group(1).split(b',')]
    if len(enabled) != len(set(enabled)) or len(enabled) < 100:
        raise ValueError('Bullseye default CA trust list is invalid')
    certificates: dict[str, bytes] = {}
    with tarfile.open(fileobj=io.BytesIO(deb_data(raw))) as archive:
        for member in archive:
            name = member.name.removeprefix('./')
            if not (name.startswith('usr/share/ca-certificates/mozilla/') and
                    name.endswith('.crt')):
                continue
            if not member.isfile() or '/' in name.removeprefix('usr/share/ca-certificates/mozilla/'):
                raise ValueError(f'Unexpected CA certificate path: {name}')
            data = archive.extractfile(member).read().strip()
            if not (data.startswith(b'-----BEGIN CERTIFICATE-----') and
                    data.endswith(b'-----END CERTIFICATE-----')):
                raise ValueError(f'Invalid PEM certificate: {name}')
            certificates[name.removeprefix('usr/share/ca-certificates/')] = data
    missing = set(enabled) - set(certificates)
    if missing:
        raise ValueError(f'Enabled Bullseye CA roots are missing: {sorted(missing)}')
    bundle = b'\n'.join(certificates[name] for name in sorted(enabled)) + b'\n'
    return bundle, len(enabled)


def remove_elf_interpreter(data: bytes, *, required: bool = True) -> bytes:
    """Set the program's PT_INTERP header to PT_NULL for explicit loader use.

    The bytes are a copy in the .xdevapp, leaving the Debian .deb untouched.
    Shared libraries and the loader already have no PT_INTERP. The package
    validator accepts this secondary ELF because no guest linker is requested.
    """
    result = bytearray(data)
    if result[:6] != b'\x7fELF\x02\x01' or struct.unpack_from('<H', result, 18)[0] != 183:
        raise ValueError('Expected little-endian AArch64 ELF64')
    offset = struct.unpack_from('<Q', result, 32)[0]
    entry_size, count = struct.unpack_from('<HH', result, 54)
    if not (56 <= entry_size <= 128 and 1 <= count <= 128 and
            offset + entry_size * count <= len(result)):
        raise ValueError('Invalid AArch64 ELF program header table')
    found = 0
    for index in range(count):
        entry = offset + index * entry_size
        if struct.unpack_from('<I', result, entry)[0] == 3:  # PT_INTERP
            struct.pack_into('<I', result, entry, 0)  # PT_NULL
            found += 1
    if found > 1 or (required and found != 1):
        raise ValueError(f'Expected exactly one NetSurf PT_INTERP; got {found}')
    return bytes(result)


def build_bionic_launcher(clang: Path, destination: Path) -> bytes:
    loader = f'{GUEST_ROOT}/lib/ld-linux-aarch64.so.1'
    libs = f'{GUEST_ROOT}/lib'
    browser = f'{GUEST_ROOT}/bin/netsurf-fb'
    resources = f'{GUEST_ROOT}/share/netsurf'
    certificates = f'{GUEST_ROOT}/share/ca-bundle.pem'
    page = f'file://{GUEST_ROOT}/web/index.html'
    code = f'''#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
int main(void) {{
    static const char *loader = "{loader}";
    char *const args[] = {{
        (char *)loader, "--library-path", "{libs}", "{browser}",
        "-f", "wld", "-b", "32", "-w", "1024", "-h", "768",
        "{page}", NULL
    }};
    setenv("NETSURFRES", "{resources}", 1);
    setenv("HOME", "/dev/x2dii-cache", 1);
    setenv("CURL_CA_BUNDLE", "{certificates}", 1);
    setenv("SSL_CERT_FILE", "{certificates}", 1);
    unsetenv("LD_LIBRARY_PATH");
    unsetenv("LD_PRELOAD");
    execv(loader, args);
    perror("NetSurf private loader");
    return 127;
}}
'''
    source = destination.with_suffix('.c')
    source.write_text(code, encoding='ascii')
    command = [str(clang), '--target=aarch64-linux-android28', '-O2',
               '-fPIE', '-pie', str(source), '-o', str(destination)]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f'Android ARM64 launcher build failed:\n{result.stderr}')
    return destination.read_bytes()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home', type=Path, default=ROOT / '.local')
    parser.add_argument('--output', type=Path,
                        help='Package path (default: HOME/netsurf-arm64/netsurf-arm64-offline.xdevapp)')
    parser.add_argument('--ndk', type=Path, help='Android NDK r27 path')
    args = parser.parse_args()
    home = args.home.resolve()
    output = (args.output or home / 'netsurf-arm64/netsurf-arm64-offline.xdevapp').resolve()
    cache = home / 'netsurf-arm64/cache'
    cache.mkdir(parents=True, exist_ok=True)
    ndk = args.ndk or find_ndk()
    if ndk is None:
        raise SystemExit('Android NDK r27 is required to build the Bionic launcher')
    clang, readelf = compiler_tools(ndk)
    lock = json.loads(LOCK.read_text(encoding='utf-8'))
    print(f"{lock['suite']} ARM64 lock: {len(lock['packages'])} packages")
    paths = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        jobs = {pool.submit(fetch_one, name, spec, cache): name
                for name, spec in lock['packages'].items()}
        for job in as_completed(jobs):
            name = jobs[job]
            paths[name] = job.result()
            print(f'  verified {name} {lock["packages"][name]["version"]}', flush=True)
    verify_debian_packages(lock, paths, base=set(), arch='arm64')
    print('Debian package controls and dependency closure verified')
    files, links = collect_debian_files(paths)
    loader_data = resolve_file('lib/ld-linux-aarch64.so.1', files, links)
    browser_data = remove_elf_interpreter(files['usr/bin/netsurf-fb'])
    payload = {
        'bin/netsurf-fb': browser_data,
        'lib/ld-linux-aarch64.so.1': loader_data,
        'web/index.html': offline_page().replace(b'X1D', b'X2D II').replace(b'ARMhf', b'ARM64'),
        'web/submitted.html': submitted_page(),
        'share/fonts/wqy-microhei.ttc': files['usr/share/fonts/truetype/wqy/wqy-microhei.ttc'],
    }
    payload['share/ca-bundle.pem'], roots = certificate_bundle(paths['ca-certificates'])
    for name, data in files.items():
        if name.startswith('usr/share/netsurf/'):
            payload[name.removeprefix('usr/')] = data
        elif name.endswith('/copyright') and name.startswith('usr/share/doc/'):
            payload['licenses/' + name.split('/')[3] + '.txt'] = data
    # Debian's libncursesw6 documentation directory is a symlink to libtinfo6.
    ncurses_notice = files.get('usr/share/doc/libtinfo6/copyright')
    if ncurses_notice is None:
        raise ValueError('Missing ncurses copyright notice from libtinfo6')
    payload['licenses/libncursesw6.txt'] = ncurses_notice
    font = f'{GUEST_ROOT}/share/fonts/wqy-microhei.ttc'
    payload['share/netsurf/Choices'] = ('\n'.join(
        f'{option}:{font}' for option in (
            'fb_face_sans_serif', 'fb_face_sans_serif_bold',
            'fb_face_sans_serif_italic', 'fb_face_sans_serif_italic_bold',
            'fb_face_serif', 'fb_face_serif_bold',
            'fb_face_monospace', 'fb_face_monospace_bold')) +
        f'\nfb_osk:1\nca_bundle:{GUEST_ROOT}/share/ca-bundle.pem\n').encode('ascii')
    candidates = {posixpath.basename(name): name for name in sorted(set(files) | set(links))
                  if name.startswith(('lib/', 'usr/lib/')) and '.so' in name}
    included = {'ld-linux-aarch64.so.1'}
    with tempfile.TemporaryDirectory(prefix='netsurf-elf-', dir=cache) as scratch:
        temporary = Path(scratch) / 'inspect.elf'
        payload['bin/launch'] = build_bionic_launcher(clang, Path(scratch) / 'launch')
        pending = [browser_data, loader_data]
        # glibc loads NSS backends with dlopen during DNS resolution, so these
        # are absent from the executable's DT_NEEDED graph. Keep them private.
        for soname in ('libnss_dns.so.2', 'libnss_files.so.2'):
            data = remove_elf_interpreter(resolve_file(candidates[soname], files, links),
                                          required=False)
            payload[f'lib/{soname}'] = data
            included.add(soname)
            pending.append(data)
        while pending:
            binary = pending.pop()
            for soname in sorted(elf_needed(binary, readelf, temporary)):
                if soname in included:
                    continue
                name = candidates.get(soname)
                if name is None:
                    raise ValueError(f'Missing Debian ARM64 shared library: {soname}')
                data = resolve_file(name, files, links)
                if not data.startswith(b'\x7fELF'):
                    raise ValueError(f'Non-ELF shared library: {name}')
                data = remove_elf_interpreter(data, required=False)
                payload[f'lib/{soname}'] = data
                included.add(soname)
                pending.append(data)
    manifest = create_package(payload, output, abi='arm64', models=['x2dii'])
    print(f'Built {output} ({output.stat().st_size:,} bytes; '
          f'{len(manifest["files"])} files; {len(included) - 1} private libraries; '
          f'{roots} pinned CA roots)')
    print('Use only with an imported X2D II QEMU guest; no camera is accessed.')


if __name__ == '__main__':
    main()
