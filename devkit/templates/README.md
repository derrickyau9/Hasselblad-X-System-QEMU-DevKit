# Your guest app / 你的虚拟机应用

Edit `hello.c`, stop the guest, click **Build app**, then **Run app**.
The workbench compiles an Android/Bionic ARM64 Wayland shared-memory client using
your installed Android NDK (r27 tested). No camera connection is involved.

编辑 `hello.c`，停止虚拟机，点击「编译应用」再点击「运行应用」。
需要安装 Android NDK；此示例运行在独立 QEMU 会话中，不访问实机。

`hello.c` intentionally has no Qt cross-build dependency. It draws a 1024×768
software surface using the firmware's Wayland client library. Replace the
pixel drawing loop to prototype an app. Close/stop the session to return to the
workbench, then start Original UI again.

The original Qt UI uses software rendering and mocked camera services. A custom
Qt guest app additionally needs a compatible Android ARM64 Qt build; a Windows
Qt executable cannot run in this guest. This DevKit does not supply that SDK.
