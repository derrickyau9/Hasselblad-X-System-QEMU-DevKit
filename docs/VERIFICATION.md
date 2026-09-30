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
