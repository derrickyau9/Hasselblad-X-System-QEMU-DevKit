"""Build a portable Windows folder: Python and Qt included, no firmware bundled."""
from pathlib import Path
import hashlib
import shutil
import subprocess
import sys
import zipfile

root=Path(__file__).resolve().parents[1]
name='X2DII-DevKit'
subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--clean','--windowed','--onedir',
    '--name',name,'--collect-submodules','dissect.extfs','--collect-submodules','dissect.cstruct',
    '--add-data','devkit/assets;devkit/assets','--add-data','devkit/helpers;devkit/helpers',
    '--add-data','devkit/templates;devkit/templates','--add-data','devkit/guest/camera_run.sh;devkit/guest',
    '--add-data','devkit/guest/dbus-local.conf;devkit/guest','--add-data','devkit/downloads.json;devkit',
    'run_app.py'],cwd=root,check=True)
output=root/'dist'/name
for file in ('LICENSE','README.md','README.zh-CN.md','THIRD_PARTY_NOTICES.md'):
    shutil.copy2(root/file,output/file)
shutil.copytree(root/'third-party-licenses',output/'third-party-licenses',dirs_exist_ok=True)
# Corresponding project source alongside the binary; no personal caches, firmware or SDK images.
sources=subprocess.check_output(['git','ls-files','-z'],cwd=root).decode().split('\0')
with zipfile.ZipFile(output/'DevKit-source.zip','w',zipfile.ZIP_DEFLATED) as z:
    for file in sources:
        if file and (root/file).is_file():z.write(root/file,file)
archive=Path(shutil.make_archive(str(root/'dist'/f'{name}-Windows-x64'),'zip',root/'dist',name))
digest=hashlib.sha256(archive.read_bytes()).hexdigest()
(root/'dist'/'SHA256SUMS.txt').write_text(f'{digest}  {archive.name}\n',encoding='ascii')
print(archive)
print(digest)
