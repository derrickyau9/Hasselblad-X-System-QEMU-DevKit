# Third-party notices

The DevKit application is AGPL-3.0-or-later. Copyright © 2026 Derrick Yao.
The MIT theme and existing small MIT example retain their original notices.
This repository's license does not relicense any third-party component.

| Component | License / source |
| --- | --- |
| Material theme, adapted `devkit/theme.py` and chevrons | MIT; Derrick Yao, [tsla-infotainment-lab](https://github.com/derrickyau9/tsla-infotainment-lab/tree/f590d8fd9a053ab072df94b994c0a58ee7b976ed) |
| PySide6 / Qt / Shiboken 6.9.3 | LGPL-3.0 option and component-specific licenses; [Qt source](https://download.qt.io/archive/qt/6.9/6.9.3/) and [PySide source](https://code.qt.io/cgit/pyside/pyside-setup.git/tag/?h=v6.9.3) |
| Dissect extfs 3.15 | AGPL-3.0-or-later; [source](https://github.com/fox-it/dissect.extfs) |
| Dissect cstruct, util | Apache-2.0; [cstruct](https://github.com/fox-it/dissect.cstruct), [util](https://github.com/fox-it/dissect.util) |
| pyfdt 0.3 | Apache-2.0; Copyright 2014 Neil Armstrong; [source](https://github.com/superna9999/pyfdt) |
| pyelftools 0.33 | Public domain; [source](https://github.com/eliben/pyelftools) |
| Brotli 1.2.0 | MIT; [source](https://github.com/google/brotli) |
| cryptography 46.0.3 | Apache-2.0 OR BSD-3-Clause; [source](https://github.com/pyca/cryptography) |
| cffi | MIT; [source](https://foss.heptapod.net/pypy/cffi) |
| Python | PSF license; [source](https://www.python.org/downloads/source/) |
| PyInstaller bootloader | GPL with distribution exception; [source and license](https://pyinstaller.org/en/stable/license.html) |

The portable distribution uses separate Qt DLLs in `_internal/PySide6`. Users may
replace compatible libraries and rebuild the application; no restriction is
imposed on reverse engineering for debugging modifications to LGPL components.
The release also includes the project's corresponding source and build scripts.
Installed wheel license texts are retained under `third-party-licenses`.

## Research references / 研究参考

**Radium Wang / radium-wang** — [Hasselblad X-System CIM Firmware Research & Feature Extensions](https://github.com/radium-wang/Hasselblad-X-System-CIM-Firmware-Research-Feature-Extensions).
This MIT-licensed upstream project (Copyright © 2026 Radium Wang) provided reference
and background for offline CIM firmware analysis and original UI/menu extension
research. This acknowledgement credits that research; it does not imply upstream
authorship or validation of the DevKit's QEMU implementation.

感谢 **Radium Wang / radium-wang** 公开分享哈苏 X 系列 CIM 固件研究及功能扩展项目，
为固件离线分析、原厂 UI 与菜单扩展研究提供参考。上游项目使用 MIT 许可证，
版权归 Radium Wang 所有；此致谢不表示上游作者开发或验证了本 DevKit 的 QEMU 实现。

## Downloaded separately, not bundled in the portable app

- **QEMU**, GPL-2.0 and other included licenses, downloaded from [Stefan Weil](https://qemu.weilnetz.de/w64/). The extracted download includes its license and source information. [QEMU source](https://gitlab.com/qemu-project/qemu).
- **7-Zip / 7zr**, LGPL/BSD/unRAR restrictions or public domain as applicable, downloaded from [official release 26.03](https://github.com/ip7z/7zip/releases/tag/26.03). Its extracted license files remain with the runtime.
- **Android SDK system image and Platform Tools**, downloaded from Google's official repository after the user accepts the [Android SDK license](https://developer.android.com/studio/terms). [AOSP source](https://source.android.com/).
- **Android NDK**, optional and installed by the developer from [Google](https://developer.android.com/ndk/downloads).

## User-supplied firmware

Hasselblad/DJI firmware binaries, Qt assets embedded in them, proprietary libraries,
fonts and artwork are not included in the repository or release. Their respective
licenses and ownership remain with their owners. Import processes only a local
user-supplied package. Screenshots illustrating compatibility are not a firmware
distribution. Hasselblad and X2D II names identify the compatible product and do
not imply affiliation or endorsement.
