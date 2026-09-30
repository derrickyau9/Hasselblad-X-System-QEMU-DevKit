# Verification record / 验证记录

Host: Windows x64 on AMD x86-64. Python 3.12, PySide6 6.9.3, QEMU Windows build
20260811, Android API 28 ARM64 image revision 2, Android NDK r27.
Recorded: 2026-09-29. These checks use local virtual machines only.

## Firmware profiles

| Firmware | SHA-256 of official input | Verified |
| --- | --- | --- |
| 1.2.7.16 | `68aa9bce63c303a7d13ca4c14aae76be935925d596094bdcb92549cff42e1bc1` | Import, original UI, main menu, mouse tap to Display submenu, frame capture, shutdown |
| 1.3.16.2 | `9789d6a9843d388034bc12341ad9a97585c25cb98cf11a0da8b768399b4842f6` | Import, original UI, main menu, mouse tap to Display submenu, frame capture, shutdown; compiled Hello app |

Both packages were imported from `.cim` using the new pipeline, without reusing
the older experiment's extracted system directories. QEMU, SDK image and platform
tools were downloaded, checksum-verified and extracted by the new runtime setup.
No preinstalled QEMU/Android runtime was required for those checks.

The portable PyInstaller EXE also started the original 1.2.7.16 UI and captured
a valid guest frame with `frozen: true`; Python was provided by the distribution.
A second portable EXE check imported the original `.cim` into a fresh data
directory, prepared new guest disks, displayed a valid frame and exited cleanly.

The original and adapted ELF `.text` and `.plt` sections compare byte for byte
identical for both versions. Only the two intended embedded QML strings differ.
The original `.cim` files remain unchanged.

## Automated checks

23 unit tests cover Windows path traversal/device names/ADS, archive collisions,
full OTA block reconstruction and malformed/truncated input, cancellation,
loopback-only QEMU transport, guest disk locking, and fragmented/invalid frame
streams. Unit tests do not require or download proprietary firmware.

The real guest integration script checks that a valid frame arrives and captures
it for visual inspection. The captured original UI showed the Display submenu;
the guest app showed the expected `HELLO X2D` drawing. Guest shutdown completed.

## Limits of this evidence

No claims are made about physical camera operation, real capture/AF/ISP, GPU
acceleration, other firmware revisions, or correctness of every original menu.
Menu startup and navigation success do not imply all underlying services work.
No input-to-display latency or FPS guarantee is made.

中文摘要：两个官方固件版本均从 `.cim` 导入并实际启动过原厂界面，点击进入
Display 子菜单；1.3.16.2 还验证了 NDK 编译示例并在虚拟机显示。23 项自动测试
通过。相机实机功能、硬件加速和其他固件版本未验证。

## Multi-model preview — 2026-09-30

The Windows source build imports 14 distinct known package hashes (the X1D II and CFV II 1.5.2 downloads share one hash). Each input is supplied by the user. This adds no physical-camera control.

| Profile | Versions | Checks |
| --- | --- | --- |
| X1D 50C | 1.20.0, 1.21.0, 1.25.0 | Legacy CIM/rootfs import, original UI in Linux ARMhf/Qt 5.15, 640×480 main menu, virtual F1; General Settings navigation on 1.21.0 and 1.25.0 |
| X1D II 50C | 1.0.1, 1.0.2, 1.1.0, 1.2.0, 1.3.0, 1.4.0, 1.5.2 | Raw Android OTA import, ARM32 UI, upward swipe to main menu, mouse tap to camera settings |
| X2D 100C | 1.0.5, 4.2.0 | Original UI with X2D identity `4.1.0`, Power / Display submenu navigation |
| 907X / CFV II 50C | 1.5.2 | Shared-package model selection, CFV identity `14.1.0`, main menu and Focus settings page |
| X2D II 100C | 1.3.16.2 | Regression check after adding multi-model support; prior 1.2.7.16 evidence remains above |

Three separately compiled Hello clients were run and visually checked: Android ARM32 with 1.5.2, Android ARM64 with X2D 4.2.0, and Linux ARMhf with X1D 1.25.0. The demonstration still draws `HELLO X2D`; it is not a device identity test.

38 host unit tests pass. Added cases cover legacy versus Android CIM IV derivation, shared-package model selection, kernel identity and isolated Linux disk selection, bounded legacy QML adaptation and Linux archive path validation. Linux runtime reconstruction from the pinned cached Debian packages was also exercised.

During verification, earlier Eagle buffers required a byte-stride adapter. Later image review also exposed partial repaint loss: the compositor now retains unchanged pixels, applies Wayland damage regions, and presents committed buffers before releasing them and completing frame callbacks on a 16 ms display tick. Delaying callbacks alone was insufficient. Pending releases follow Wayland resource destruction so a destroyed buffer is not used later, and repeated commits of a pending buffer accumulate their damage. X1D 1.21.0 and X1D II 1.0.2 / 1.4.0 were additionally observed through repeated captures for 34 seconds after readiness, including settings-page interactions. Blank-frame rejection alone is insufficient; retained screenshots were reviewed for complete menus. The original X1D QML root-window adaptation changes a compressed data resource, without altering ELF instructions. `.text` and `.plt` compare byte for byte for all 14 imported profiles.

The Windows portable EXE was also checked: a fresh data directory imported CFV II 1.5.2 and displayed the 907X main menu; the Linux path displayed the X1D 1.25.0 main menu. Both recorded `frozen: true`.

The launcher allows the opening menu transition and asynchronous loaders to settle before readiness. Menu filtering also needs a synthetic body type: firmware Qt metadata defines Xsystem as `1024` and Cfv907x as `1048576`, rather than sequential enum values. The mock supplies these masks to `Seq`, with the GUI exposure capability, while hardware methods remain unsupported. X1D II 1.3.0 Quality and 907X Focus pages were checked after this change.

The firmware/UI ABI paths were tested on Windows. The additional models have not been verified on macOS. No 907X / CFV 100C image was supplied; that model is unsupported. Hardware operations, all menu values, settings persistence, and physical camera behavior remain outside these checks. There is no GPU acceleration claim.
