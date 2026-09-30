# macOS Apple Silicon / macOS 安装说明

This is a source-run path for Apple Silicon Macs. The Windows portable package and
Windows download manifest are not used. The guest remains an isolated QEMU guest;
it does not connect to or flash a physical camera.

## 1. Install host tools

```sh
brew install python@3.13 qemu
```

The project needs `qemu-system-aarch64`, `qemu-img`, `qemu-io`, and `mke2fs`.
Homebrew's Android platform-tools package also provides `mke2fs`; if it is not
already installed, install it with:

```sh
brew install android-platform-tools
```

## 2. Install the Android ARM64 API 28 image

The image is downloaded from Google's official Android repository. The archive is
about 427 MB and expands to about 2.8 GB.

```sh
SDK="$HOME/Library/Android/sdk"
mkdir -p "$SDK/system-images/android-28/default"
curl -L --fail --output /tmp/android-arm64-v8a-28_r02.zip \
  https://dl.google.com/android/repository/sys-img/android/arm64-v8a-28_r02.zip
echo 'e209114dd0dfc2f4e0d328f5fd7367fec39ee1bd  /tmp/android-arm64-v8a-28_r02.zip' | shasum -a 1 -c -
unzip -q /tmp/android-arm64-v8a-28_r02.zip -d "$SDK/system-images/android-28/default"
```

The archive contains an `arm64-v8a` directory, which is the location expected by
the DevKit. Set `ANDROID_SDK_ROOT` if you keep the SDK somewhere else:

```sh
export ANDROID_SDK_ROOT="$HOME/Library/Android/sdk"
```

## 3. Install Python dependencies and launch

From the repository directory:

```sh
./Launch.sh --home "$HOME/Library/Application Support/X2DII-DevKit"
```

Import your own official X2D II `.cim` in the workbench. Only the validated
X2D II versions listed in `devkit/firmware.py` are accepted. The original `.cim`
file is read without modification.

## Limits

- This runs the original camera UI inside an Android ARM64 QEMU guest with mocked
  camera services; it does not emulate capture, ISP, AF, lens control, or real
  camera storage.
- QEMU uses software CPU emulation and software rendering for the guest UI.
- The source macOS path has been smoke-tested on Apple Silicon with X2D II
  1.3.16.2: the UI booted and a real guest frame was captured.
