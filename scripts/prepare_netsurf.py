"""Build a guest-only, offline NetSurf prototype for X1D Linux ARMhf.

Source: Debian Bullseye main/armhf, NetSurf 3.10-1+b1 and common 3.10-1.
Exact Debian package URLs, versions, sizes and SHA-256 values are locked in
``netsurf-bullseye-lock.json``. Nothing is installed on the host or camera.
The resulting .xdevapp contains an offline HTML page and can run only in the
disposable QEMU X1D guest via the DevKit package installer.

Usage: python scripts/prepare_netsurf.py --home .local
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import io
import json
import os
from pathlib import Path
import posixpath
import re
import subprocess
import sys
import tarfile
import tempfile
from urllib.request import urlopen
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from devkit.development import find_ndk
from devkit.linux_runtime import deb_data
from devkit.packages import inspect_package


APP_ID = 'org.hasselblad.devkit.netsurf'
APP_VERSION = '3.10.1'
APP_ROOT = f'/devkit/apps/{APP_ID}/{APP_VERSION}'
LOCK = Path(__file__).with_name('netsurf-bullseye-lock.json')
REPO = Path(__file__).resolve().parents[1]


def fetch_one(name: str, spec: dict, cache: Path) -> Path:
    target = cache / spec['url'].rsplit('/', 1)[1]
    expected_size = spec['size']
    expected_digest = spec['sha256']
    if target.is_file():
        data = target.read_bytes()
        if len(data) == expected_size and hashlib.sha256(data).hexdigest() == expected_digest:
            return target
        target.unlink()
    temporary = target.with_suffix('.part')
    try:
        with urlopen(spec['url'], timeout=60) as response, temporary.open('wb') as output:
            digest = hashlib.sha256()
            total = 0
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > expected_size:
                    raise ValueError(f'{name}: download exceeds pinned size')
                digest.update(chunk)
                output.write(chunk)
        if total != expected_size or digest.hexdigest() != expected_digest:
            raise ValueError(f'{name}: Debian package SHA-256/size mismatch')
        temporary.replace(target)
        return target
    finally:
        temporary.unlink(missing_ok=True)


def ar_member(data: bytes, prefix: bytes) -> bytes:
    if not data.startswith(b'!<arch>\n'):
        raise ValueError('Invalid Debian ar header')
    offset = 8
    while offset + 60 <= len(data):
        header = data[offset:offset + 60]
        length = int(header[48:58])
        name = header[:16].strip().rstrip(b'/')
        if header[58:60] != b'`\n' or length < 0 or offset + 60 + length > len(data):
            raise ValueError('Invalid Debian ar member')
        body = data[offset + 60:offset + 60 + length]
        offset += 60 + length + (length & 1)
        if name.startswith(prefix):
            return body
    raise ValueError(f'Debian ar member missing: {prefix!r}')


def control_fields(data: bytes) -> dict[str, str]:
    result: dict[str, str] = {}
    control = ar_member(data, b'control.tar')
    with tarfile.open(fileobj=io.BytesIO(control)) as archive:
        member = next((m for m in archive if m.name.lstrip('./') == 'control'), None)
        if member is None:
            raise ValueError('Debian package control file missing')
        raw = archive.extractfile(member).read().decode('utf-8')
    current = None
    for line in raw.splitlines():
        if line.startswith(' ') and current:
            result[current] += ' ' + line.strip()
        elif ': ' in line:
            current, value = line.split(': ', 1)
            result[current] = value
    return result


def first_dependencies(field: str) -> set[str]:
    names = set()
    for requirement in field.split(','):
        first = requirement.split('|', 1)[0].strip()
        if first:
            names.add(re.split(r'[ (]', first, 1)[0])
    return names


def verify_debian_packages(lock: dict, paths: dict[str, Path],
                           base: set[str] | None = None, arch: str = 'armhf') -> None:
    # The lock also includes packaging-only Depends (certificates/font meta
    # packages). Runtime ELF closure below selects just the necessary files.
    if base is None:
        base = set(json.loads((REPO / 'devkit/linux-downloads.json').read_text(encoding='utf-8')))
    available = set(paths) | base
    for name, spec in lock['packages'].items():
        fields = control_fields(paths[name].read_bytes())
        if fields.get('Package') != name or fields.get('Version') != spec['version']:
            raise ValueError(f'{name}: Debian control identity/version mismatch')
        if fields.get('Architecture') not in (arch, 'all'):
            raise ValueError(f'{name}: Debian control architecture mismatch')
        actual = first_dependencies(fields.get('Depends', ''))
        pinned = first_dependencies(spec['depends'])
        if actual != pinned or not actual <= available:
            raise ValueError(f'{name}: dependency closure differs from the lock: {actual - available}')
        if 'pre_depends' in spec:
            actual_pre = first_dependencies(fields.get('Pre-Depends', ''))
            pinned_pre = first_dependencies(spec['pre_depends'])
            if actual_pre != pinned_pre or not actual_pre <= available:
                raise ValueError(f'{name}: pre-dependency closure differs from the lock: {actual_pre - available}')


def collect_debian_files(paths: dict[str, Path]) -> tuple[dict[str, bytes], dict[str, str]]:
    files: dict[str, bytes] = {}
    links: dict[str, str] = {}
    for package, path in sorted(paths.items()):
        with tarfile.open(fileobj=io.BytesIO(deb_data(path.read_bytes()))) as archive:
            for member in archive:
                name = member.name.removeprefix('./')
                if not name or name.startswith('/') or '..' in name.split('/') or '\\' in name:
                    raise ValueError(f'{package}: unsafe data path')
                wanted = (name.startswith(('usr/lib/', 'lib/')) or
                          name == 'usr/bin/netsurf-fb' or
                          name.startswith('usr/share/netsurf/') or
                          name == 'usr/share/fonts/truetype/wqy/wqy-microhei.ttc' or
                          name == f'usr/share/doc/{package}/copyright')
                if not wanted:
                    continue
                if member.isfile():
                    files[name] = archive.extractfile(member).read()
                elif member.issym() or member.islnk():
                    target = member.linkname
                    if member.islnk():
                        target = '/' + target.removeprefix('./')
                    links[name] = target
    return files, links


def resolve_file(name: str, files: dict[str, bytes], links: dict[str, str]) -> bytes:
    visited = set()
    while name in links:
        if name in visited or len(visited) > 32:
            raise ValueError(f'Debian symlink cycle: {name}')
        visited.add(name)
        target = links[name]
        name = posixpath.normpath(target.lstrip('/') if target.startswith('/')
                                else posixpath.join(posixpath.dirname(name), target))
    if name not in files:
        raise ValueError(f'Debian symlink target is absent: {name}')
    return files[name]


def compiler_tools(ndk: Path) -> tuple[Path, Path]:
    hosts = ('windows-x86_64', 'linux-x86_64', 'darwin-arm64', 'darwin-x86_64')
    for host in hosts:
        root = ndk / 'toolchains/llvm/prebuilt' / host / 'bin'
        clang = root / ('clang.exe' if os.name == 'nt' else 'clang')
        readelf = root / ('llvm-readelf.exe' if os.name == 'nt' else 'llvm-readelf')
        if clang.is_file() and readelf.is_file():
            return clang, readelf
    raise FileNotFoundError('NDK clang and llvm-readelf were not found')


def elf_needed(data: bytes, readelf: Path, temporary: Path) -> set[str]:
    temporary.write_bytes(data)
    output = subprocess.run([str(readelf), '-d', str(temporary)], check=True,
                            capture_output=True, text=True).stdout
    return set(re.findall(r'\(NEEDED\).*?\[(.*?)\]', output))


def build_launcher(clang: Path, sysroot: Path, output: Path) -> bytes:
    libs = sysroot / 'usr/lib/arm-linux-gnueabihf'
    code = f'''#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
int main(void) {{
    static const char *binary = "{APP_ROOT}/bin/netsurf-fb";
    setenv("NETSURFRES", "{APP_ROOT}/share/netsurf", 1);
    setenv("HOME", "/dev/x2dii-cache", 1);
    execl(binary, binary, "-f", "wld", "-b", "32", "-w", "640", "-h", "480",
          "file://{APP_ROOT}/web/index.html", (char *)0);
    perror("NetSurf launcher");
    return 127;
}}
'''
    source = output.with_suffix('.c')
    source.write_text(code, encoding='ascii')
    command = [str(clang), '--target=arm-linux-gnueabihf', f'--sysroot={sysroot}',
               '-isystem', str(sysroot / 'usr/include/arm-linux-gnueabihf'),
               '-O2', '-fPIE', '-pie', '-fuse-ld=lld', '-nostdlib',
               str(libs / 'Scrt1.o'), str(libs / 'crti.o'), str(source),
               '-L' + str(libs), '-L' + str(sysroot / 'lib/arm-linux-gnueabihf'),
               '-Wl,-dynamic-linker,/lib/ld-linux-armhf.so.3',
               '-l:libc.so.6', '-l:libgcc_s.so.1', '-l:libc_nonshared.a',
               str(libs / 'crtn.o'), '-o', str(output)]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f'ARMhf launcher compilation failed:\n{result.stderr}')
    return output.read_bytes()


def offline_page() -> bytes:
    return '''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>X1D QEMU Browser</title>
<style>
body { background:#131719; color:#f3f0e9; font:18px sans-serif; margin:0; }
header { background:#272d2e; padding:28px; border-bottom:4px solid #df8d47; }
h1 { font-size:32px; margin:0 0 10px; }
main { padding:30px; }
p { line-height:1.5; max-width:34em; }
.card { background:#303637; border:1px solid #707778; padding:20px; margin:22px 0; }
a { color:#ffbd80; }
</style></head><body>
<header><h1>NetSurf on Hasselblad X1D QEMU</h1>
<div>Offline Wayland browser prototype / 离线 Wayland 浏览器原型</div></header>
<main><div class="card"><strong>Local page rendered successfully.</strong>
<p>This page is packaged with the app; it requests no network content.</p>
<p>页面随应用打包；页面不请求网络内容。</p>
<form action="submitted.html" method="get">
<label for="typed">Touch keyboard test / 触摸键盘测试</label><br>
<input id="typed" name="typed" type="text" size="18">
<button type="submit">Submit / 提交</button>
</form></div>
<p><a href="#details">Open local details / 查看本地说明</a></p>
<div id="details" class="card">NetSurf 3.10 · Debian Bullseye ARMhf · Wayland wl_shell</div>
</main></body></html>
'''.encode('utf-8')


def submitted_page() -> bytes:
    return '''<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>NetSurf form result</title><style>
body{background:#131719;color:#f3f0e9;font:24px sans-serif;padding:36px}
a{color:#ffbd80}</style></head><body>
<h1>Form submitted / 表单已提交</h1>
<p>The typed text is visible in the local URL query.</p>
<p>输入内容显示在本地地址的查询参数中。</p>
<a href="index.html">Back / 返回</a>
</body></html>'''.encode('utf-8')


def create_package(payload: dict[str, bytes], output: Path, *,
                   abi: str = 'linux-arm32', models: list[str] | None = None) -> dict:
    files = [{'path': name, 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
             for name, data in sorted(payload.items())]
    manifest = {'schema': 1, 'id': APP_ID, 'version': APP_VERSION,
                'abi': abi, 'models': models or ['x1d'],
                'entry': 'bin/launch', 'files': files}
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix('.part')
    def write_entry(archive: zipfile.ZipFile, name: str, data: bytes | str) -> None:
        # Stable ZIP metadata keeps rebuilds byte-identical on the same zlib.
        info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
        info.create_system = 3
        info.external_attr = 0o100644 << 16
        archive.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED,
                         compresslevel=9)
    try:
        with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_DEFLATED,
                             compresslevel=9) as archive:
            write_entry(archive, 'manifest.json', json.dumps(
                manifest, ensure_ascii=False, separators=(',', ':')))
            for name, data in sorted(payload.items()):
                write_entry(archive, name, data)
        inspect_package(temporary)
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home', type=Path, default=REPO / '.local',
                        help='Existing DevKit data directory (default: repo/.local)')
    parser.add_argument('--output', type=Path,
                        help='Package path (default: HOME/netsurf/netsurf-armhf-offline.xdevapp)')
    parser.add_argument('--ndk', type=Path, help='Android NDK r27 path for Linux ARMhf clang')
    args = parser.parse_args()
    home = args.home.resolve()
    output = (args.output or home / 'netsurf/netsurf-armhf-offline.xdevapp').resolve()
    cache = home / 'netsurf/cache'
    cache.mkdir(parents=True, exist_ok=True)
    sysroot = home / 'runtime/linux-armhf/sysroot'
    if not (sysroot / 'lib/ld-linux-armhf.so.3').is_file():
        raise SystemExit('First prepare/import an X1D guest to create .local/runtime/linux-armhf/sysroot')
    ndk = args.ndk or find_ndk()
    if ndk is None:
        raise SystemExit('Android NDK r27 is required to compile the ARMhf ELF launcher')
    clang, readelf = compiler_tools(ndk)
    lock = json.loads(LOCK.read_text(encoding='utf-8'))
    print(f"Debian {lock['suite']} package lock: {len(lock['packages'])} packages")
    paths = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        jobs = {pool.submit(fetch_one, name, spec, cache): name
                for name, spec in lock['packages'].items()}
        for job in as_completed(jobs):
            name = jobs[job]
            paths[name] = job.result()
            print(f'  verified {name} {lock["packages"][name]["version"]}', flush=True)
    verify_debian_packages(lock, paths)
    print('Debian package controls and dependency closure verified')
    files, links = collect_debian_files(paths)
    payload = {
        'bin/netsurf-fb': files['usr/bin/netsurf-fb'],
        'web/index.html': offline_page(),
        'web/submitted.html': submitted_page(),
        'share/fonts/wqy-microhei.ttc': files['usr/share/fonts/truetype/wqy/wqy-microhei.ttc'],
    }
    for name, data in files.items():
        if name.startswith('usr/share/netsurf/'):
            payload[name.removeprefix('usr/')] = data
        elif name.endswith('/copyright') and name.startswith('usr/share/doc/'):
            payload['licenses/' + name.split('/')[3] + '.txt'] = data
    # Debian's libncursesw6 documentation directory is a symlink to libtinfo6.
    # The former DSO is bundled, so include its shared source notice by name.
    ncurses_notice = files.get('usr/share/doc/libtinfo6/copyright')
    if ncurses_notice is None:
        raise ValueError('Missing ncurses copyright notice from libtinfo6')
    payload['licenses/libncursesw6.txt'] = ncurses_notice
    font = f'{APP_ROOT}/share/fonts/wqy-microhei.ttc'
    payload['share/netsurf/Choices'] = ('\n'.join(
        f'{option}:{font}' for option in (
            'fb_face_sans_serif', 'fb_face_sans_serif_bold',
            'fb_face_sans_serif_italic', 'fb_face_sans_serif_italic_bold',
            'fb_face_serif', 'fb_face_serif_bold',
            'fb_face_monospace', 'fb_face_monospace_bold')) + '\nfb_osk:1\n').encode('ascii')
    # NetSurf uses a symlink from ca-bundle.txt to /etc/ssl/certs. The guest
    # is deliberately offline, so no external CA resource is bundled.
    base_libs = {p.name for top in ('lib/arm-linux-gnueabihf',
                                   'usr/lib/arm-linux-gnueabihf', 'lib', 'usr/lib')
                 for p in (sysroot / top).glob('*.so*') if p.is_file()}
    candidates = {posixpath.basename(name): name for name in sorted(set(files) | set(links))
                  if name.startswith(('lib/', 'usr/lib/')) and '.so' in name}
    with tempfile.TemporaryDirectory(prefix='netsurf-elf-', dir=cache) as scratch:
        temporary = Path(scratch) / 'inspect.elf'
        payload['bin/launch'] = build_launcher(clang, sysroot, Path(scratch) / 'launch')
        pending = [payload['bin/netsurf-fb'], payload['bin/launch']]
        included = set()
        while pending:
            binary = pending.pop()
            for soname in sorted(elf_needed(binary, readelf, temporary)):
                if soname in base_libs or soname in included:
                    continue
                name = candidates.get(soname)
                if name is None:
                    raise ValueError(f'Missing ARMhf shared library: {soname}')
                data = resolve_file(name, files, links)
                if not data.startswith(b'\x7fELF'):
                    raise ValueError(f'Non-ELF shared library: {name}')
                payload[f'lib/{soname}'] = data
                included.add(soname)
                pending.append(data)
    manifest = create_package(payload, output)
    print(f'Built {output} ({output.stat().st_size:,} bytes; '
          f'{len(manifest["files"])} files; {len(included)} bundled ELF libraries)')
    print('Install/activate this package only on an imported X1D QEMU guest.')


if __name__ == '__main__':
    main()
