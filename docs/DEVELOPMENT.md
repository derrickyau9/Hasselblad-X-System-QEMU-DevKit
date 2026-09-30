# Development / 开发

## Desktop application

Python 3.11+ and PySide6. The native Material theme is adapted from
`derrickyau9/tsla-infotainment-lab`; its notice is retained in
`third-party-licenses/tsla-infotainment-lab.txt`.

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
.\.venv\Scripts\python run_app.py --home .local
.\.venv\Scripts\python -m pytest -q
```

`--home .local` isolates development data inside an ignored directory. Firmware
import, runtime setup and app builds use worker threads; QEMU owns separate
loopback console/input/frame channels. Cancellation stops only owned processes.

## Guest app

The Development page creates a source workspace without overwriting edits.
`hello.c` draws a 1024×768 surface using Wayland shared memory. Modify its pixel
loop, build with Android NDK r27 and run in the guest. The firmware's dynamically
linked Wayland library stays in the local imported payload.

The NDK is optional, separately downloaded by the developer. Set
`ANDROID_NDK_HOME`, or select its folder in the app. The DevKit detects normal
Android SDK `ndk/*` installs. Running the original UI does not require an NDK.

`Build app` and import are disabled during a running guest: the virtual FAT disk
is read-only, and its source directory must not change while attached.

A Qt toolchain matching Android ARM32, Android ARM64, or Linux ARMhf is needed for custom Qt guest apps; the
desktop's PySide6/Windows Qt libraries cannot be cross-used. The example avoids
this extra dependency so the initial edit/build/run loop remains small.

## Rebuild the three guest helpers

The repository includes only **our own** small compiled ARM32, ARM64 and Linux ARMhf helpers and their
complete C sources. It does not contain firmware libraries or Android SDK images.

```powershell
.\scripts\build_helpers.ps1 `
  -NdkRoot '<your Android NDK r27 folder>' `
  -FirmwareLibraries '<import folder>\payload-stage\camera\lib'
```

The compositor links to the firmware's exported Wayland server ABI. Mock services
link to its D-Bus ABI. These library files are supplied locally by firmware import.
Linking is dynamic; their contents are not embedded in the helper binaries.

## Integration verification

After importing a supported firmware and installing the runtime:

```powershell
.\.venv\Scripts\python scripts/verify_guest.py --home .local
.\.venv\Scripts\python scripts/verify_guest.py --home .local --app
```

The app test requires a successful `Build app` first. The script starts only the
local virtual machine, verifies a valid frame, captures a screenshot and stops
QEMU. The original UI test also taps the Display menu location; inspect the saved
screenshot to verify menu semantics. These are manual integration checks and do
not fetch firmware in CI.

## Release

`scripts/build.py` creates a PyInstaller **onedir** portable distribution with
replaceable Qt DLLs, notices and project source. GitHub Actions runs tests and
builds that folder; pushing a version tag publishes the ZIP and SHA-256 file.
The source ZIP is drawn from `git ls-files`, never from the entire workspace.
Review staged files before releasing. Do not commit firmware, user workspaces,
downloaded runtimes or logs.

## Multi-model builds

The workbench chooses the C app target from `device.json`. For X1D, NDK clang uses the pinned Linux sysroot and GNU dynamic loader; it does not link Android Bionic. The base VM still boots the Android SDK kernel, then enters the isolated Linux userspace.

Rebuild Android ARM32 helpers with `scripts/build_helpers.ps1 -Architecture arm32`, using an imported X1D II `camera/lib` directory. This also builds the ION adapter. Rebuild Linux helpers with:

```powershell
.\scripts\build_linux_helpers.ps1 -NdkRoot '<NDK r27>' -Sysroot '<DevKit data>\runtime\linux-armhf\sysroot'
```

Use `scripts/verify_guest.py --home .local --device <hash-prefix> --model 907x50c --output .local/check` to test the shared package's 907X profile. `--key 1` sends F1, and `--tap 560 360` tests the X1D General Settings entry. The verifier rejects blank frames but every screenshot must still be reviewed for completeness and the intended menu.

For a local portable preview without replacing the previous build:

```powershell
.\.venv\Scripts\python scripts/build.py --name X2DII-DevKit-preview
```
