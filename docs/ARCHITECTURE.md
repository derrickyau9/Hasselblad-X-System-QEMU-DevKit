# Architecture / 架构

```mermaid
flowchart LR
  CIM[User-supplied official .cim] --> Import[Local verified import]
  Import --> Payload[Read-only UI payload]
  SDK[Official Android ARM64 SDK image] --> QEMU[QEMU virt / TCG]
  Payload --> QEMU
  QEMU --> Compositor[Minimal Wayland compositor]
  Compositor -->|Virtio frame stream, loopback TCP| Qt[Native Windows Qt workbench]
  Qt -->|Virtio touch, loopback TCP| Compositor
  Workspace[Editable hello.c] --> NDK[Android NDK]
  NDK --> Payload
```

## Data ownership

The original `.cim` is read only. Import identifies a known package by SHA-256,
reads its full OTA component, expands the Android block transfer data and reads
the ext4 filesystem locally. Only the original UI's dependency closure, fonts,
XKB files and product configuration enter its local payload. Intermediate files
are discarded when import completes or fails.

No camera or host disk is passed through. QEMU networking is disabled. The
console, input and display transports bind to `127.0.0.1` on ephemeral ports.
These local development endpoints are not authenticated; other processes on the
same computer may access them. They must never be rebound to public interfaces.
The guest console is the SDK image's built-in development console.

SDK system/vendor images remain read-only backing files. Qcow2 overlays rename
their GPT labels for the SDK kernel's virtio layout. QEMU discards system writes
on exit. Userdata and the encryption-key disk belong exclusively to the selected
import. A file lock prevents two sessions from writing the same guest disks.

The frame disk is disposable and uses `cache=unsafe` only for fallback frame
storage; userdata does not use that setting. Normal frames stream over virtio.

## Original UI rendering adaptation

`software_ui.py` creates a separate copy of `camera-gui`. Two equal-length
embedded QML source substitutions make `HblImage` use its ordinary Image rather
than a GPU ShaderEffect. The guest sets `QT_QUICK_BACKEND=software` and
`QML_DISABLE_DISK_CACHE=1`. Source and output hashes and byte offsets are recorded
next to the development copy. Executable instructions remain unchanged.

This is only a rendering adaptation in the disposable guest. The tool does not
modify bootloaders, original kernels, SELinux policy or a connected camera.

## Services and development

`mock_services.c` provides initial D-Bus properties for UI startup. Methods which
have no simulation return NotSupported. Battery, hardware and storage values are
not physical camera measurements. A working menu does not imply working capture,
AF, media management, upgrade or network functionality.

The minimal compositor supports the protocols required by this UI and the
included `wl_shm` example. It is not a complete general-purpose Wayland desktop.
The app example and original UI run in separate sessions; they are not injected
into a live camera interface.

## Paths

```text
%LOCALAPPDATA%/X2DII-DevKit/
  preferences.json             language, theme, optional NDK path
  runtime.json                 selected runtime paths
  downloads/                   checksum-verified official archives
  runtime/                     extracted QEMU, Android SDK, 7-Zip
  library/<firmware-sha-prefix>/
    device.json                version + package digest
    payload-stage/             read-only virtual FAT contents
    workspace/                 user-owned source edits
    userdata-qemu.img          private data disk
    system-name.qcow2          disposable system backing overlay
    vendor-name.qcow2          vendor backing overlay
    console.log / qemu.log     local diagnostic output
```

Runtime paths are kept stable because qcow2 overlays reference their backing
files. If moving the runtime, use a fresh DevKit data directory and re-import.
Keep your development workspace backed up separately.
