# NetSurf browser prototype / NetSurf 浏览器原型

NetSurf 3.10 runs as a third-party Wayland app inside the disposable QEMU guest.
The build scripts download exact Debian Bullseye packages, check their pinned
sizes and SHA-256 hashes, and create a `.xdevapp` package. The packages contain
an offline HTML page, browser resources, fonts, required guest libraries, and
their Debian copyright notices. They do not contain camera firmware. Building
or importing a package does not install anything on a physical camera.

NetSurf 3.10 可以作为第三方 Wayland 应用在独立的 QEMU 虚拟机中运行。构建脚本下载
固定版本的 Debian Bullseye 包，核对大小与 SHA-256 后生成 `.xdevapp`。包内含离线
HTML 页面、浏览器资源、字体、所需的虚拟机动态库及 Debian 版权说明，不包含相机固件。
构建或导入应用包不会安装到实机。

## Build and run / 构建和运行

Install the DevKit runtime, import official firmware, and prepare the matching
guest before running the following commands from the repository root. An Android
NDK r27 toolchain is required to build the small launchers.

先安装 DevKit 运行环境并导入官方固件，再在仓库根目录执行下列命令。构建启动器还需要
Android NDK r27。

### X1D Linux ARMhf

```powershell
.\.venv\Scripts\python.exe scripts\prepare_netsurf.py --home .local
.\.venv\Scripts\python.exe scripts\app_packages.py install --device .local\library\e6bea3675dec9fb2 .local\netsurf\netsurf-armhf-offline.xdevapp
.\.venv\Scripts\python.exe scripts\app_packages.py activate --device .local\library\e6bea3675dec9fb2 org.hasselblad.devkit.netsurf 3.10.1
.\.venv\Scripts\python.exe scripts\verify_guest.py --home .local --device e6bea3675dec9fb2 --model x1d --app --package org.hasselblad.devkit.netsurf@3.10.1 --output .local\netsurf\qa
```

The example library prefix is the locally verified X1D 1.21.0 import. Replace
it with your imported X1D library directory. The launcher and libraries use
the Linux ARMhf guest ABI; they cannot be used on an Android ABI model.

上例的固件前缀对应本地验证过的 X1D 1.21.0；使用时请替换为自己的导入目录。

### X2D II Android ARM64

```powershell
.\.venv\Scripts\python.exe scripts\prepare_netsurf_arm64.py --home .local
.\.venv\Scripts\python.exe scripts\app_packages.py install --device .local\library\68aa9bce63c303a7 .local\netsurf-arm64\netsurf-arm64-offline.xdevapp
.\.venv\Scripts\python.exe scripts\app_packages.py activate --device .local\library\68aa9bce63c303a7 org.hasselblad.devkit.netsurf 3.10.1
.\.venv\Scripts\python.exe scripts\verify_guest.py --home .local --device 68aa9bce63c303a7 --model x2dii --app --package org.hasselblad.devkit.netsurf@3.10.1 --output .local\netsurf-arm64\qa
```

The example prefix is the locally verified X2D II 1.2.7.16 import. Replace
it with your imported X2D II library directory. This package starts with a
small Android Bionic launcher, which invokes a private ARM64 glibc loader and
private Debian libraries inside the app directory. It does not replace the
guest's `/system` libraries.

上例的固件前缀对应本地验证过的 X2D II 1.2.7.16。ARM64 包使用一个 Android
Bionic 启动器，在应用目录内启动私有 glibc 加载器及 Debian 动态库，不替换虚拟机
`/system` 中的库。

The graphical workbench can also import the generated `.xdevapp` from its
Development page, then run it with **Run app**. The browser opens a packaged
local page and starts offline. For an X2D II ARM64 app session only, select
**Enable QEMU network for this app session** before launching to allow public
web requests. This choice resets after that launch; the original firmware UI
runs in a separate offline session.

图形界面也可以在“开发”页导入生成的 `.xdevapp`，再点击“运行应用”。点击页面中的
“查看本地说明”可验证鼠标点击。浏览器默认打开包内的本地页面且不联网。仅 X2D II
ARM64 应用会话可在启动前勾选“为此次应用会话启用 QEMU 网络”，让浏览器访问公网；
勾选在本次启动后复位。原厂界面在独立的离线会话中运行。

For a scripted network run, add `--network` to the X2D II `verify_guest.py`
command above. This flag is not available for other models or the original UI.
脚本验证网络时，可在上述 X2D II 的 `verify_guest.py` 命令后加 `--network`；其他
机型和原厂 UI 不支持该参数。

Optional networking is an experimental QEMU development feature. NetSurf 3.10
and the pinned Debian Bullseye CA trust list are older components; successful
loading of one HTTPS page does not establish compatibility or security for
current websites. Keep networking off unless a test needs it.

可选联网用于 QEMU 开发实验。NetSurf 3.10 与固定的 Debian Bullseye CA 信任名单
版本较旧；成功打开一个 HTTPS 页面不代表能兼容或安全浏览现代网站。不需要联网测试时
保持关闭即可。

## Touch keyboard / 触摸键盘

NetSurf's **own** on-screen keyboard is enabled in both packages. Tap a text
field or the address bar, then tap the small keyboard icon at the bottom right
to open it. Tap characters and press its Enter key to submit. On the X2D II
1.2.7.16 QEMU guest, `ab1` entered into the packaged form and reached
`submitted.html?typed=ab1`; entering `#details` in the address bar and pressing
Enter navigated to the local details section. Replacing `index.html` with
`submitted.html` using the touch keyboard opened that page too. This is the NetSurf keyboard,
not a Hasselblad firmware keyboard.

两个包均启用了 **NetSurf 自带**屏幕键盘。先点网页输入框或地址栏，再点右下角的小键盘
图标，点选字符，最后按键盘上的 Enter。X2D II 1.2.7.16 QEMU 中已实测：在包内
表单输入 `ab1` 后，提交地址变为 `submitted.html?typed=ab1`；在地址栏输入
`#details` 并按 Enter 后，页面跳至本地说明区；用触摸键盘把地址栏的 `index.html`
改成 `submitted.html` 后，也成功打开该页面。这是 NetSurf 键盘，**不是哈苏固件原厂
键盘**。

## Verified scope / 已验证范围

- X1D 1.21.0 QEMU: page, Chinese font, and a clicked anchor rendered correctly.
- X1D 1.21.0 QEMU: NetSurf keyboard opened; `ab1` entered a local form and
  submitting the form displayed the result page.
- X2D II 1.2.7.16 QEMU: page, Chinese font, and browser toolbar rendered correctly.
- Wayland compositor: the browser's `wl_shell`, `wl_shm`, and `wl_pointer`
  paths work in both verified guests; touch input to the original UI still works.
- X2D II 1.2.7.16 QEMU: NetSurf keyboard opened, entered text in a form and
  address bar, submitted the form, and navigated to a local anchor.
- X2D II 1.3.16.2 QEMU with optional networking: the final generated ARM64
  package rendered the public IANA page over HTTPS with the requested URL in
  the browser address bar. Guest DNS, UTC time, and the package's pinned CA
  bundle were active in that session.

These results establish the QEMU development path. A physical X2D II uses its
own SELinux policy and Weston socket; neither package has been installed or
run on a camera. NetSurf 3.10 is a limited, older browser. This prototype
tests local HTML/CSS, touch input, and one public HTTPS page. Modern websites,
physical host keyboard input, and Firefox compatibility are not validated.

这些结果仅证明 QEMU 开发路径。实机 X2D II 使用自己的 SELinux 策略和 Weston
套接字；上述应用包尚未在相机上安装或运行。NetSurf 3.10 功能有限且版本较旧，
目前验证了本地 HTML/CSS、触摸输入和一个公网 HTTPS 页面；现代网站、电脑实体
键盘输入和 Firefox 兼容性尚未验证。
