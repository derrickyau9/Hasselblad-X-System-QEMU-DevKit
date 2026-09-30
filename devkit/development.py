"""Create a small, editable guest app workspace and compile it with the NDK."""
from pathlib import Path
import os
import shutil
import sys
from .core import ASSETS, Task, GuestLock, read_json

def workspace(device):
    root = device / 'workspace'
    root.mkdir(exist_ok=True)
    for src in (ASSETS / 'templates').iterdir():
        target = root / src.name
        if not target.exists():
            shutil.copy2(src, target)
    return root

def find_ndk():
    configured = os.environ.get('ANDROID_NDK_HOME') or os.environ.get('ANDROID_NDK_ROOT')
    if configured:
        return Path(configured)
    if os.name == 'nt':
        default_sdk = Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'Android/Sdk'
    elif sys.platform == 'darwin':
        default_sdk = Path.home() / 'Library/Android/sdk'
    else:
        default_sdk = Path.home() / 'Android/Sdk'
    sdk = Path(os.environ.get('ANDROID_SDK_ROOT', str(default_sdk)))
    candidates = sorted((sdk / 'ndk').glob('*'), reverse=True)
    hosts = ('windows-x86_64',) if os.name == 'nt' else (('darwin-arm64', 'darwin-x86_64') if sys.platform == 'darwin' else ('linux-x86_64',))
    compiler = 'clang.exe' if os.name == 'nt' else 'clang'
    return next((p for p in candidates if any((p / f'toolchains/llvm/prebuilt/{host}/bin/{compiler}').exists() for host in hosts)), None)

def build(device, ndk, task=None):
    task = task or Task()
    root = workspace(device)
    hosts = ('windows-x86_64',) if os.name == 'nt' else (('darwin-arm64', 'darwin-x86_64') if sys.platform == 'darwin' else ('linux-x86_64',))
    compiler_name = 'clang.exe' if os.name == 'nt' else 'clang'
    compiler = next((Path(ndk) / f'toolchains/llvm/prebuilt/{host}/bin/{compiler_name}' for host in hosts if (Path(ndk) / f'toolchains/llvm/prebuilt/{host}/bin/{compiler_name}').exists()), None)
    if compiler is None:
        raise FileNotFoundError('Select an Android NDK folder containing toolchains/llvm (r27 validated)')
    output = device / 'payload-stage/app'
    output.mkdir(exist_ok=True)
    abi=read_json(device/'device.json').get('abi','arm64')
    task.report(f'Compiling / 编译: {abi}')
    # clang.exe avoids cmd.exe string interpolation for paths supplied by users.
    with GuestLock(device):
        if abi=='linux-arm32':
            from .linux_runtime import setup_linux
            sysroot=setup_linux(device,task);libs=sysroot/'usr/lib/arm-linux-gnueabihf'
            task.run([compiler,'--target=arm-linux-gnueabihf',f'--sysroot={sysroot}',
                      '-isystem',sysroot/'usr/include/arm-linux-gnueabihf','-O2','-fPIE','-pie','-fuse-ld=lld','-nostdlib',
                      libs/'Scrt1.o',libs/'crti.o',root/'hello.c','-L'+str(libs),'-L'+str(sysroot/'lib/arm-linux-gnueabihf'),
                      '-Wl,-dynamic-linker,/lib/ld-linux-armhf.so.3','-Wl,--allow-shlib-undefined',
                      '-l:libwayland-client.so.0','-l:libc.so.6','-l:libgcc_s.so.1','-l:libc_nonshared.a',libs/'crtn.o',
                      '-o',output/'hello.new'])
        else:
            target='armv7a-linux-androideabi23' if abi=='arm32' else 'aarch64-linux-android28'
            task.run([compiler, '--target='+target, '-O2', '-fPIE', '-pie', root / 'hello.c',
                      '-o', output / 'hello.new', '-L' + str(device / 'payload-stage/camera/lib'), '-lwayland-client'])
        (output / 'hello.new').replace(output / 'hello')
    task.report('Build successful / 编译成功')
    return output / 'hello'
