"""Build a portable Windows folder: Python and Qt included, no firmware bundled."""
from pathlib import Path
import hashlib
import shutil
import subprocess
import sys
import zipfile
import argparse

root=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--name',default='X2DII-DevKit');args=p.parse_args()
name=args.name
if not name.replace('-','').isalnum(): raise SystemExit('Invalid build name')
subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--clean','--windowed','--onedir',
    '--name',name,'--collect-submodules','dissect.extfs','--collect-submodules','dissect.cstruct',
    '--add-data','devkit/assets;devkit/assets','--add-data','devkit/helpers;devkit/helpers',
    '--add-data','devkit/templates;devkit/templates','--add-data','devkit/guest/camera_run.sh;devkit/guest',
    '--add-data','devkit/guest/dbus-local.conf;devkit/guest','--add-data','devkit/downloads.json;devkit',
    '--add-data','devkit/guest/legacy_run.sh;devkit/guest','--add-data','devkit/guest/linux_ui.sh;devkit/guest',
    '--add-data','devkit/linux-downloads.json;devkit',
    'run_app.py'],cwd=root,check=True)
output=root/'dist'/name
for file in ('LICENSE','README.md','README.zh-CN.md','THIRD_PARTY_NOTICES.md'):
    shutil.copy2(root/file,output/file)
shutil.copytree(root/'third-party-licenses',output/'third-party-licenses',dirs_exist_ok=True)
# Corresponding project source alongside the binary; no personal caches, firmware or SDK images.
sources=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','-z'],cwd=root).decode().split('\0')
with zipfile.ZipFile(output/'DevKit-source.zip','w',zipfile.ZIP_DEFLATED) as z:
    for file in sources:
        if file and (root/file).is_file():z.write(root/file,file)
archive=Path(shutil.make_archive(str(root/'dist'/f'{name}-Windows-x64'),'zip',root/'dist',name))
digest=hashlib.sha256(archive.read_bytes()).hexdigest()
checksum_name='SHA256SUMS.txt' if name=='X2DII-DevKit' else f'{name}-SHA256SUMS.txt'
(root/'dist'/checksum_name).write_text(f'{digest}  {archive.name}\n',encoding='ascii')
print(archive)
print(digest)
