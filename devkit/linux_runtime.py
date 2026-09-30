"""Pinned Debian ARMhf userspace for the isolated X1D guest, without installers."""
import hashlib
import io
import posixpath
import shutil
import tarfile
import tempfile
import urllib.request
from pathlib import Path
from .core import ASSETS, Task, checked_child, read_json

def deb_data(data):
    if not data.startswith(b'!<arch>\n'): raise ValueError('Invalid Debian archive')
    offset=8
    while offset+60 <= len(data):
        head=data[offset:offset+60]; size=int(head[48:58]); name=head[:16].decode('ascii').strip().rstrip('/')
        if head[58:60]!=b'`\n' or size<0 or offset+60+size>len(data): raise ValueError('Truncated Debian archive')
        body=data[offset+60:offset+60+size]; offset+=60+size+(size%2)
        if name.startswith('data.tar'): return body
    raise ValueError('Debian archive has no data member')

def guest_path(name):
    name=name.removeprefix('./')
    if not name or name.startswith('/') or '\\' in name or '..' in name.split('/'):
        raise ValueError('Unsafe guest runtime path')
    return name

def unpack_packages(packages, output, task):
    """Keep Unix symlinks only in the guest tar; materialize headers/libs for clang."""
    files={}; metadata={}; total=0
    for package in packages:
        task.check()
        with tarfile.open(fileobj=io.BytesIO(deb_data(package.read_bytes()))) as archive:
            for member in archive:
                task.check()
                if member.isdir(): continue
                name=guest_path(member.name)
                if not name.startswith(('lib/','usr/lib/','usr/include/','usr/share/','etc/','bin/','usr/bin/')): continue
                if member.isfile():
                    total+=member.size
                    if total>2*1024**3: raise ValueError('Linux runtime expansion exceeds limit')
                    files[name]=archive.extractfile(member).read(); metadata[name]=(member.mode,None)
                elif member.issym() or member.islnk():
                    link=member.linkname if member.issym() else '/'+guest_path(member.linkname)
                    target=posixpath.normpath(link.lstrip('/') if link.startswith('/') else posixpath.join(posixpath.dirname(name),link))
                    guest_path(target)
                    files.pop(name,None); metadata[name]=(member.mode,link)
    output.mkdir(parents=True,exist_ok=True)
    with tarfile.open(output/'compat.tar.gz','w:gz') as archive:
        for name,(mode,link) in sorted(metadata.items()):
            task.check()
            if name.startswith('usr/include/'): continue
            entry=tarfile.TarInfo(name); entry.mode=mode & 0o777
            if link is not None: entry.type=tarfile.SYMTYPE; entry.linkname=link; archive.addfile(entry)
            else: entry.size=len(files[name]); archive.addfile(entry,io.BytesIO(files[name]))
    def resolve(name,seen=()):
        if name in seen or len(seen)>32: raise ValueError('Runtime symlink loop')
        if name in files: return files[name]
        if name not in metadata: return None
        link=metadata[name][1]
        if link is None: return None
        target=posixpath.normpath(link.lstrip('/') if link.startswith('/') else posixpath.join(posixpath.dirname(name),link))
        return resolve(target,seen+(name,))
    root=output/'sysroot'
    for name in metadata:
        task.check()
        if not name.startswith(('lib/','usr/lib/','usr/include/')): continue
        data=resolve(name)
        if data is not None:
            path=checked_child(root,name);path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)

def setup_linux(device, task=None):
    task=task or Task(); home=device.parent.parent
    manifest=ASSETS/'linux-downloads.json'; fingerprint=hashlib.sha256(manifest.read_bytes()).hexdigest()
    root=home/'runtime'/'linux-armhf'; marker=root/'manifest.sha256'
    if not marker.exists() or marker.read_text()!=fingerprint:
        cache=home/'downloads'/'linux-armhf';cache.mkdir(parents=True,exist_ok=True)
        packages=[]
        for name,spec in read_json(manifest).items():
            task.check(); path=cache/spec['url'].rsplit('/',1)[1]
            if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest()!=spec['sha256']:
                task.report(f'Linux runtime / Linux 运行库: {name}')
                temporary=path.with_suffix('.part')
                with urllib.request.urlopen(spec['url'],timeout=30) as response,temporary.open('wb') as dest:
                    size=0
                    while chunk:=response.read(1024**2):
                        task.check();size+=len(chunk)
                        if size>spec['size']: raise ValueError('Unexpected Linux package size')
                        dest.write(chunk)
                if hashlib.sha256(temporary.read_bytes()).hexdigest()!=spec['sha256']: raise ValueError('Linux package checksum failed')
                temporary.replace(path)
            packages.append(path)
        root.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='linux-',dir=root.parent) as temp:
            task.report('Preparing Linux compatibility libraries / 准备 Linux 兼容运行库…')
            work=Path(temp)/'ready';unpack_packages(packages,work,task)
            if root.exists(): raise ValueError('Linux runtime manifest changed; use a new data directory')
            (work/'manifest.sha256').write_text(fingerprint);work.rename(root)
    target=device/'payload-stage/compat.tar.gz'
    if not target.exists(): shutil.copy2(root/'compat.tar.gz',target)
    return root/'sysroot'
