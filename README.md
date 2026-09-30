# Hasselblad X2D II QEMU DevKit

**A Windows workbench, with a source-run macOS ARM64 path, for exploring the original Hasselblad X System interfaces and developing guest apps.**

[简体中文](README.zh-CN.md) · [Download Windows app](https://github.com/derrickyau9/Hasselblad-X2D-II-QEMU-DevKit/releases/latest)

![DevKit workbench](docs/workbench.png)

## From firmware to a running UI

1. Download **X2DII-DevKit-Windows-x64.zip** from Releases, extract it, and double-click **X2DII-DevKit.exe**. Python, Qt and WSL are not required on your computer.
2. Download a supported **camera `.cim`** from Hasselblad. Drop it into the workbench or click the import area.
3. Click **Start original UI**. On first use, review the Android SDK license and approve runtime setup. The app downloads and verifies its runtime, then boots the guest.
4. Click to tap, drag to swipe. **Stop** shuts down the owned QEMU process. The next launch uses your cached firmware and runtime, offline.

Initial runtime download: approximately **615 MB**. Allow **8 GB free disk space**, a Windows x64 computer, and preferably at least 8 GB RAM. Runtime files are extracted into your user profile; no administrator privileges or system-wide installation is needed.

## What you get

- Drag-and-drop firmware import, SHA-256 validation and a local firmware library.
- Original firmware UI, streamed directly from a minimal Wayland compositor in QEMU.
- Start/stop controls, correctly scaled mouse touch input and PNG screenshots.
- English / Simplified Chinese; system / light / dark themes; Iris / Blue / Leaf accents.
- A guest console, persistent logs and an editable **hello.c** development workspace.
- **Build app → Run app** using an installed Android NDK; no NDK is needed to run the original UI.
- Disposable system writes and a separate data disk per imported firmware.

## Compatibility and limits

| Item | Status |
| --- | --- |
| Windows x64 host | Supported; portable Qt application |
| macOS Apple Silicon | Supported from source after the macOS setup in [docs/MACOS.md](docs/MACOS.md); no portable package yet |
| X2D II 1.2.7.16 | Original UI, menu navigation and Display submenu verified |
| X2D II 1.3.16.2 | See [verification record](docs/VERIFICATION.md) |
| Additional profiles | X1D, X1D II, X2D and 907X 50C; see the preview matrix below |
| Unknown packages | Exact hashes not listed by the importer are rejected |
| Rendering | QEMU TCG + Qt Quick software backend |
| Hardware acceleration | Not implemented for this ARM64 guest on x86-64 Windows |
| Capture, ISP, AF, lens, USB camera, real storage | Not emulated |
| Physical camera installation / firmware flashing | Not provided |

This runs the **original camera user interface in a development guest**, with Android ARM32, Android ARM64 or Linux ARMhf libraries selected for the firmware and simulated camera services. It does not boot the camera's original kernel or reproduce the complete camera hardware. UI responsiveness varies with the host CPU. Camera values are mocked and some actions are intentionally unsupported.

Depending on the firmware, a local development copy adapts embedded QML image visibility or the legacy root window for software rendering. The original executable is retained, executable instructions are not patched, and no modified firmware is written back to the `.cim` file. See [architecture](docs/ARCHITECTURE.md).

## Develop an app

1. Import and select firmware.
2. Open **Development → Open development workspace**.
3. Edit `hello.c` in your editor.
4. Select your [Android NDK](https://developer.android.com/ndk/downloads) folder (**r27 tested**).
5. Stop any running guest, click **Build app**, then **Run app**.

The example is a `wl_shm` client compiled for the selected firmware ABI. It runs in its own guest session; stop it and start Original UI to return. The firmware payload is read-only while QEMU runs, so stop before rebuilding. Custom Qt guest applications require a Qt toolchain matching the selected guest ABI, which is not included. A Windows Qt executable cannot run inside this guest.

[Development guide](docs/DEVELOPMENT.md) · [Troubleshooting](docs/TROUBLESHOOTING.md)

## Run from source

Install Python **3.11+**, clone the repository, and double-click `Launch.cmd`. It creates a local virtual environment and installs dependencies on the first run.

```powershell
git clone https://github.com/derrickyau9/Hasselblad-X2D-II-QEMU-DevKit.git
cd Hasselblad-X2D-II-QEMU-DevKit
.\Launch.cmd
```

For contributors:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
.\.venv\Scripts\python -m pytest -q
.\.venv\Scripts\python run_app.py
.\.venv\Scripts\python scripts/build.py
```

Data lives in `%LOCALAPPDATA%\X2DII-DevKit`. Set `X2DII_DEVKIT_HOME` or pass `--home <directory>` for a different location. Avoid commas in runtime/data paths. Firmware files, extracted assets, runtime downloads, logs and user workspaces are excluded from Git.

On macOS Apple Silicon, use the source launcher after completing the [macOS setup](docs/MACOS.md):

```sh
./Launch.sh --home "$HOME/Library/Application Support/X2DII-DevKit"
```

## Additional camera profiles (v0.2.0)

| Camera | Firmware inputs | UI checks |
| --- | --- | --- |
| X1D 50C | 1.20.0, 1.21.0, 1.25.0 | Linux ARMhf; see the verification matrix |
| X1D II 50C | 1.0.1, 1.0.2, 1.1.0, 1.2.0, 1.3.0, 1.4.0, 1.5.2 | Android ARM32; main menu and settings navigation |
| X2D 100C | 1.0.5, 4.2.0 | Android ARM64; original UI and settings navigation |
| 907X / CFV II 50C | 1.5.2 | Shared package with X1D II; choose the camera in the library |

These additions are available in v0.2.0 as UI development previews. **907X / CFV 100C is not covered.** The X1D II and CFV II 1.5.2 input files supplied for testing are byte-identical, so importing both creates one library entry with two camera choices.

X1D downloads about 78 MB of pinned Debian ARMhf libraries on first launch, then works offline. Allow about 12 GB free for initial X1D setup, plus space for additional firmware. It runs the original Linux UI with a Qt 5.15 compatibility runtime inside the guest; the camera kernel and hardware are not emulated. X1D displays at 640×480. F1–F5 buttons send the UI's virtual camera keys. The launcher opens the main menu for development.

The app compiler now selects Android ARM32, Android ARM64 or Linux ARMhf from the selected firmware. NDK r27 clang is used for all three; Linux builds also use the downloaded sysroot. Windows/macOS binaries cannot run as guest apps. Original UI and custom apps run in separate sessions.

See [verification details](docs/VERIFICATION.md). Menu controls backed by unimplemented hardware services can remain unavailable; displayed camera data is synthetic.

## Credits and licensing

- **[Radium Wang / radium-wang — Hasselblad X-System CIM Firmware Research & Feature Extensions](https://github.com/radium-wang/Hasselblad-X-System-CIM-Firmware-Research-Feature-Extensions)** — reference and background for offline CIM firmware analysis and original UI/menu extension research. Thank you for making this research available.
- **[Derrick Yao / tsla-infotainment-lab](https://github.com/derrickyau9/tsla-infotainment-lab)** — Material theme and native Qt workbench design; adapted with its MIT notice preserved. Reference commit: `f590d8fd9a053ab072df94b994c0a58ee7b976ed`.
- Existing local X2D II QEMU/UI research and CIM container tools by Derrick Yao form the basis of the guest adapters and import pipeline.
- [QEMU](https://www.qemu.org/), [Stefan Weil's Windows builds](https://qemu.weilnetz.de/), Android/AOSP, Qt for Python, 7-Zip, Dissect, pyfdt, pyelftools, Brotli and cryptography.

DevKit is **AGPL-3.0-or-later**, including the requirements of its Dissect filesystem dependency. The adapted theme retains its MIT notice. The portable package includes project source and third-party license notices; Qt libraries remain separately replaceable in the distribution. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

Hasselblad firmware, fonts, artwork, libraries and trademarks belong to their respective owners. They are **not distributed in this repository or release**. Users supply their own official firmware. This project is not affiliated with or endorsed by Hasselblad.

## Disclaimer

Provided **as is**, without warranty. You use it at your own risk. You are solely responsible for consequences including any loss of warranty, camera damage, data loss or other loss arising from your use or modifications. This DevKit operates locally and does not provide camera flashing or installation functions.
