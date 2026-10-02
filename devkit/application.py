"""Native Qt workbench, with Material surfaces from Infotainment Lab."""
from pathlib import Path
import argparse
import json
import locale
import os
import platform
import shutil
import struct
import sys
import time
from PySide6.QtCore import Qt, QTimer, QThread, Signal, QRectF, QUrl
from PySide6.QtGui import QPainter, QColor, QImage, QDesktopServices, QFont, QPixmap, QIcon
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QFrame, QLabel, QPushButton,
    QToolButton, QVBoxLayout, QHBoxLayout, QListWidget, QStackedWidget, QFileDialog,
    QPlainTextEdit, QComboBox, QMessageBox, QProgressBar, QLineEdit, QDialog, QCheckBox,
    QDialogButtonBox, QSplitter)
from .core import ASSETS, Task, Cancelled, data_home, read_json, write_json
from .firmware import import_firmware, TESTED_VERSION
from .runtime import discover, setup
from .development import workspace, build, find_ndk
from .session import Session
from .guest.prepare import network_supported
from .models import MODELS, model_id, available_models
from .theme import apply_theme, current_colors

class Job(QThread):
    message = Signal(str)
    result = Signal(object)
    failed = Signal(str)
    def __init__(self, operation):
        super().__init__()
        self.operation, self.task = operation, Task(self.message.emit)
    def run(self):
        try:
            self.result.emit(self.operation(self.task))
        except Exception as error:
            self.failed.emit(str(error))

class Screen(QWidget):
    touch = Signal(str, int, int)
    def __init__(self):
        super().__init__()
        self.frame = None
        self.message = 'X2D II'
        self.caption = 'Import official firmware to begin'
        self.last_move = 0
        self.dragging = False
        self.setMinimumSize(480, 360)
        self.setSizePolicy(self.sizePolicy().Policy.Expanding, self.sizePolicy().Policy.Expanding)
    def bounds(self):
        fw, fh = (self.frame.width(),self.frame.height()) if self.frame is not None else (1024,768)
        scale = min(self.width()/fw, self.height()/fh)
        w, h = fw*scale, fh*scale
        return QRectF((self.width()-w)/2, (self.height()-h)/2, w, h)
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor('#0f0e13'))
        if self.frame is not None:
            painter.drawImage(self.bounds(), self.frame)
        else:
            painter.setPen(QColor('#d0bcff'))
            painter.setFont(QFont('Segoe UI', 38, QFont.Weight.Light))
            painter.drawText(self.rect().adjusted(0, -50, 0, -50), Qt.AlignCenter, self.message)
            painter.setPen(QColor('#938f99'))
            painter.setFont(QFont('Segoe UI', 12))
            painter.drawText(self.rect().adjusted(20, 65, -20, 65), Qt.AlignCenter | Qt.TextWordWrap, self.caption)
        painter.end()
    def send(self, operation, event):
        r = self.bounds(); p = event.position()
        if operation == 'down' and not r.contains(p):
            return
        fw, fh = (self.frame.width(),self.frame.height()) if self.frame is not None else (1024,768)
        x = max(0, min(fw-1, int((p.x()-r.x())*fw/r.width())))
        y = max(0, min(fh-1, int((p.y()-r.y())*fh/r.height())))
        self.touch.emit(operation, x, y)
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.bounds().contains(event.position()):
            self.dragging = True
            self.send('down', event)
    def mouseMoveEvent(self, event):
        if self.dragging and time.monotonic()-self.last_move > .016:
            self.last_move = time.monotonic(); self.send('move', event)
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.dragging:
            self.send('up', event); self.dragging = False
class DropArea(QFrame):
    dropped = Signal(str)
    clicked = Signal()
    def __init__(self, title, caption):
        super().__init__()
        self.setAcceptDrops(True); self.setFocusPolicy(Qt.StrongFocus)
        layout = QVBoxLayout(self); layout.setContentsMargins(24, 22, 24, 22)
        self.title = QLabel(title); self.title.setObjectName('subtitle')
        self.caption = QLabel(caption); self.caption.setWordWrap(True); self.caption.setObjectName('muted')
        layout.addWidget(self.title); layout.addWidget(self.caption)
    def dragEnterEvent(self, event):
        urls = event.mimeData().urls()
        if len(urls) == 1 and urls[0].isLocalFile() and urls[0].toLocalFile().lower().endswith('.cim'):
            event.acceptProposedAction()
    def dropEvent(self, event):
        self.dropped.emit(event.mimeData().urls()[0].toLocalFile())
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton: self.clicked.emit()
    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Space): self.clicked.emit()

class Window(QMainWindow):
    def __init__(self, home):
        super().__init__()
        self.home = home
        home.mkdir(parents=True, exist_ok=True)
        self.preferences = read_json(home / 'preferences.json')
        self.lang = self.preferences.get('language', 'zh' if (locale.getlocale()[0] or '').lower().startswith('zh') else 'en')
        self.bindings = []
        self.job = self.session = None
        self.runtime = discover(home)
        self.devices = []; self.device = None
        self.last_frame = None
        self.closing = False
        self.setWindowTitle('Hasselblad X System QEMU DevKit')
        cat_logo = QPixmap(str(ASSETS / 'assets' / 'cat-logo.jpg'))
        if not cat_logo.isNull():
            self.setWindowIcon(QIcon(cat_logo))
        self.resize(1400, 940); self.setMinimumSize(1120, 780)
        self.setAcceptDrops(True)
        app = QApplication.instance()
        apply_theme(app, self.preferences.get('theme', 'system'), self.preferences.get('accent', 'violet'))
        app.styleHints().colorSchemeChanged.connect(lambda *_: self.appearance())
        body = QWidget(); self.setCentralWidget(body)
        row = QHBoxLayout(body); row.setContentsMargins(18, 18, 18, 18); row.setSpacing(22)
        sidebar = QFrame(); sidebar.setObjectName('sidebar'); sidebar.setFixedWidth(224)
        side = QVBoxLayout(sidebar); side.setContentsMargins(18, 24, 18, 20); side.setSpacing(12)
        brand = QLabel()
        brand.setAccessibleName('Cat logo')
        brand.setPixmap(cat_logo.scaled(160, 117, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        side.addWidget(brand)
        side.addSpacing(25)
        self.pages = QStackedWidget(); self.nav = []
        for i, (en, zh) in enumerate([('Firmware library', '固件库'), ('Development', '开发工作区'), ('Console and logs', '控制台与日志'), ('Settings', '设置')]):
            b = QToolButton(); b.setObjectName('nav'); b.setCheckable(True); b.setToolButtonStyle(Qt.ToolButtonTextOnly)
            self.bind(b.setText, en, zh); b.clicked.connect(lambda _=False, n=i: self.navigate(n))
            side.addWidget(b); self.nav.append(b)
        side.addStretch()
        side.addWidget(self.label('LOCAL WORKBENCH', '本地开发环境', 'eyebrow'))
        host_label = 'macOS ARM64' if sys.platform == 'darwin' and platform.machine() == 'arm64' else ('macOS' if sys.platform == 'darwin' else 'Windows x64')
        side.addWidget(self.label(f'ARM32 / ARM64 · Software rendering\n{host_label} · v0.2.0', f'ARM32 / ARM64 · 软件渲染\n{host_label} · v0.2.0', 'muted'))
        self.official = self.button('Get official firmware ↗', '下载官方固件 ↗', lambda: QDesktopServices.openUrl(QUrl('https://www.hasselblad.com/x-system/firmware/')))
        side.addWidget(self.official)
        row.addWidget(sidebar); row.addWidget(self.pages, 1)
        self.make_library(); self.make_development(); self.make_console(); self.make_settings()
        self.navigate(0)
        self.progress = QProgressBar(); self.progress.setMaximumWidth(170); self.progress.setRange(0, 0); self.progress.hide()
        self.cancel = self.button('Cancel', '取消', self.cancel_job); self.cancel.hide()
        self.statusBar().addPermanentWidget(self.progress); self.statusBar().addPermanentWidget(self.cancel)
        self.refresh_library(); self.update_controls()
        self.timer = QTimer(self); self.timer.timeout.connect(self.tick); self.timer.start(16)

    def tr(self, en, zh): return zh if self.lang == 'zh' else en
    def bind(self, setter, en, zh):
        self.bindings.append((setter, en, zh)); setter(self.tr(en, zh))
    def label(self, en, zh, style=None):
        label = QLabel(); label.setWordWrap(True)
        if style: label.setObjectName(style)
        self.bind(label.setText, en, zh); return label
    def button(self, en, zh, action, primary=False):
        b = QPushButton(); self.bind(b.setText, en, zh); b.clicked.connect(action)
        if primary: b.setObjectName('primary')
        return b
    def card(self, layout):
        card = QFrame(); card.setObjectName('card'); inner = QVBoxLayout(card); inner.setContentsMargins(22, 20, 22, 20); inner.setSpacing(12)
        layout.addWidget(card); return inner
    def page(self, en, zh, sub_en, sub_zh):
        p = QWidget(); layout = QVBoxLayout(p); layout.setContentsMargins(0, 8, 0, 0); layout.setSpacing(16)
        layout.addWidget(self.label(en, zh, 'title')); layout.addWidget(self.label(sub_en, sub_zh, 'muted'))
        self.pages.addWidget(p); return layout

    def make_library(self):
        layout = self.page('Hasselblad X System QEMU DevKit', 'Hasselblad X System QEMU DevKit',
            'Bring your own firmware. Explore the original interface in a local QEMU guest.', '导入官方固件，在本地 QEMU 虚拟机中探索原厂界面。')
        self.drop = DropArea('', '')
        self.bind(self.drop.title.setText, '↓  Drop official firmware here', '↓  将官方固件拖到这里')
        self.bind(self.drop.caption.setText, '.cim · X1D / X1D II / X2D / X2D II / 907X 50C', '.cim · X1D / X1D II / X2D / X2D II / 907X 50C')
        self.drop.clicked.connect(self.browse); self.drop.dropped.connect(self.import_file); layout.addWidget(self.drop)
        content = QHBoxLayout(); content.setSpacing(16); layout.addLayout(content, 1)
        list_card = QFrame(); list_card.setObjectName('card'); list_card.setFixedWidth(242)
        left = QVBoxLayout(list_card); left.setContentsMargins(18, 20, 18, 20)
        left.addWidget(self.label('FIRMWARE LIBRARY', '固件库', 'eyebrow'))
        self.library = QListWidget(); self.library.currentRowChanged.connect(self.select_device); left.addWidget(self.library, 1)
        self.details = QLabel(); self.details.setWordWrap(True); self.details.setObjectName('muted'); left.addWidget(self.details)
        self.model_choice = QComboBox(); self.model_choice.currentIndexChanged.connect(self.select_model); left.addWidget(self.model_choice)
        self.folder = self.button('Open files', '打开文件目录', self.open_device); left.addWidget(self.folder)
        content.addWidget(list_card)
        preview = QFrame(); preview.setObjectName('card'); right = QVBoxLayout(preview); right.setContentsMargins(16, 14, 16, 16)
        header = QHBoxLayout(); header.addWidget(self.label('LIVE PREVIEW', '实时预览', 'eyebrow')); header.addStretch()
        self.badge = QLabel(); self.badge.setObjectName('badge'); header.addWidget(self.badge); right.addLayout(header)
        self.screen = Screen(); self.screen.touch.connect(self.send_touch); right.addWidget(self.screen, 1)
        right.addWidget(self.label('Click to tap · Drag to swipe · Camera data is simulated', '鼠标点击 = 触控 · 拖动 = 滑动 · 相机数据为模拟值', 'muted'))
        key_row = QHBoxLayout(); self.camera_keys = []
        for i in range(1,6):
            key = QPushButton(f'F{i}')
            key.pressed.connect(lambda i=i:self.send_touch('key',58+i,1))
            key.released.connect(lambda i=i:self.send_touch('key',58+i,0))
            self.camera_keys.append(key); key_row.addWidget(key)
        key_row.addStretch(); right.addLayout(key_row)
        buttons = QHBoxLayout()
        self.start = self.button('Start original UI', '启动原厂 UI', self.launch, True)
        self.stop = self.button('Stop', '停止', self.stop_session)
        self.shot = self.button('Screenshot', '截图', self.screenshot)
        buttons.addWidget(self.start); buttons.addWidget(self.stop); buttons.addStretch(); buttons.addWidget(self.shot); right.addLayout(buttons)
        content.addWidget(preview, 1)

    def make_development(self):
        layout = self.page('Develop for your camera.', '为选中的机型开发应用。',
            'Build and run a Wayland example for the selected firmware.', '按所选固件的架构编译 Wayland 示例，在虚拟机中运行。')
        card = self.card(layout)
        card.addWidget(self.label('01  Create your workspace', '01  创建开发工作区', 'subtitle'))
        card.addWidget(self.label('Create hello.c and a guide for the selected firmware. Existing edits are preserved.', '为选中的固件创建 hello.c 和开发说明，保留已有修改。', 'muted'))
        card.addWidget(self.button('Open development workspace', '打开开发工作区', self.open_workspace))
        card = self.card(layout)
        card.addWidget(self.label('02  Build and run', '02  编译并运行', 'subtitle'))
        card.addWidget(self.label('Use NDK r27 clang. The build selects Android ARM32, ARM64, or Linux ARMhf automatically.', '使用 NDK r27 的 clang，自动选择 Android ARM32、ARM64 或 Linux ARMhf；仅运行 UI 不需要 NDK。', 'muted'))
        ndk_row = QHBoxLayout(); self.ndk = QLineEdit(str(find_ndk() or self.preferences.get('ndk', '')))
        self.ndk.setPlaceholderText('Android NDK folder'); ndk_row.addWidget(self.ndk, 1)
        ndk_row.addWidget(self.button('Browse…', '选择…', self.choose_ndk)); card.addLayout(ndk_row)
        buttons = QHBoxLayout(); self.build_button = self.button('Build app', '编译应用', self.build_app, True)
        self.app_button = self.button('Run app', '运行应用', lambda: self.launch(mode='app'))
        buttons.addWidget(self.build_button); buttons.addWidget(self.app_button); buttons.addStretch(); card.addLayout(buttons)
        card.addWidget(self.button('Download Android NDK ↗', '下载 Android NDK ↗', lambda: QDesktopServices.openUrl(QUrl('https://developer.android.com/ndk/downloads'))))
        card = self.card(layout)
        card.addWidget(self.label('03  Test a third-party guest app', '03  测试第三方虚拟机应用', 'subtitle'))
        card.addWidget(self.label('Import a validated .xdevapp package for this firmware. Apps run only in the local QEMU guest; original UI and apps use separate sessions.', '导入适用于当前固件的 .xdevapp 包。应用只在本地 QEMU 虚拟机运行，与原厂 UI 使用独立会话。', 'muted'))
        self.app_choice = QComboBox(); self.app_choice.currentIndexChanged.connect(lambda _: self.update_controls()); card.addWidget(self.app_choice)
        app_actions = QHBoxLayout()
        self.import_app_button = self.button('Import app package', '导入应用包', self.import_app_package)
        self.remove_app_button = self.button('Remove selected package', '移除所选应用包', self.remove_app_package)
        app_actions.addWidget(self.import_app_button); app_actions.addWidget(self.remove_app_button); app_actions.addStretch(); card.addLayout(app_actions)
        self.app_network = QCheckBox()
        self.bind(self.app_network.setText, 'Enable QEMU network for this app session', '为此次应用会话启用 QEMU 网络')
        self.app_network.setChecked(False)
        card.addWidget(self.app_network)
        card.addWidget(self.label('Off by default. Verified only for X2D II ARM64 apps in QEMU; the original camera UI stays offline.', '默认关闭。仅 X2D II ARM64 虚拟机应用已验证；原厂相机 UI 保持离线。', 'muted'))
        card = self.card(layout)
        card.addWidget(self.label('What this environment provides', '开发环境能力', 'subtitle'))
        card.addWidget(self.label('Original Qt UI + a minimal Wayland compositor + mocked camera services. The included C app uses shared memory. Custom Qt apps need a toolchain matching the selected firmware’s ABI.', '原厂 Qt UI、精简 Wayland 合成器和模拟相机服务。附带的 C 示例使用共享内存绘制；自定义 Qt 应用另需与所选固件 ABI 匹配的工具链。', 'muted'))
        layout.addStretch()

    def make_console(self):
        layout = self.page('See what is happening.', '查看运行状态。', 'Commands run only inside the local development guest.', '命令只在本地开发虚拟机中执行。')
        self.logs = QPlainTextEdit(); self.logs.setReadOnly(True); self.logs.setMaximumBlockCount(2500); self.logs.setFont(QFont('Cascadia Mono', 10)); layout.addWidget(self.logs, 1)
        row = QHBoxLayout(); self.command = QLineEdit(); self.bind(self.command.setPlaceholderText, 'Guest shell command, e.g. uname -a', '虚拟机 Shell 命令，例如 uname -a')
        self.command.returnPressed.connect(self.send_command); row.addWidget(self.command, 1)
        self.send_button = self.button('Run in guest', '在虚拟机执行', self.send_command); row.addWidget(self.send_button); layout.addLayout(row)
        row = QHBoxLayout(); row.addWidget(self.button('Open logs folder', '打开日志目录', self.open_device)); row.addWidget(self.button('Clear view', '清空显示', self.logs.clear)); row.addStretch(); layout.addLayout(row)

    def make_settings(self):
        layout = self.page('Make it yours.', '设置你的工作环境。', 'Native Qt on your desktop. No WSL or administrator privileges required.', '桌面原生 Qt，无需 WSL 或管理员权限。')
        card = self.card(layout); card.addWidget(self.label('Appearance', '外观', 'subtitle'))
        row = QHBoxLayout(); self.language = QComboBox(); self.language.addItems(['English', '简体中文']); self.language.setCurrentIndex(int(self.lang == 'zh'))
        self.language.currentIndexChanged.connect(self.change_language); row.addWidget(self.language)
        self.theme = QComboBox(); self.theme.addItems(['System / 跟随系统', 'Light / 浅色', 'Dark / 深色']); self.theme.setCurrentIndex(['system','light','dark'].index(self.preferences.get('theme','system')))
        self.theme.currentIndexChanged.connect(self.appearance); row.addWidget(self.theme)
        self.accent = QComboBox(); self.accent.addItems(['Iris / 鸢尾紫', 'Blue / 蓝色', 'Leaf / 叶绿']); self.accent.setCurrentIndex(['violet','blue','green'].index(self.preferences.get('accent','violet')))
        self.accent.currentIndexChanged.connect(self.appearance); row.addWidget(self.accent); card.addLayout(row)
        card = self.card(layout); card.addWidget(self.label('Runtime', '运行环境', 'subtitle'))
        self.runtime_label = QLabel(); self.runtime_label.setWordWrap(True); self.runtime_label.setObjectName('muted'); card.addWidget(self.runtime_label)
        self.setup_button = self.button('Set up runtime', '安装运行环境', self.install_runtime, True); card.addWidget(self.setup_button)
        card.addWidget(self.label('Base setup downloads about 615 MB; X1D adds about 78 MB of Linux libraries. Reserve 8 GB, or 12 GB for X1D, plus space for each firmware. CPU emulation and Qt software rendering are used; GPU acceleration is unavailable in this ARM64 guest.', '基础环境下载约 615 MB，X1D 另需约 78 MB Linux 运行库。请预留 8 GB，X1D 建议 12 GB，多份固件需额外空间。当前使用 CPU 模拟与 Qt 软件渲染，此 ARM64 环境尚未提供 GPU 加速。', 'muted'))
        card.addWidget(self.button('Open DevKit data folder', '打开 DevKit 数据目录', lambda: self.open_path(self.home)))
        card = self.card(layout); card.addWidget(self.label('Credits & scope', '致谢与范围', 'subtitle'))
        card.addWidget(self.label('Material theme adapted from Derrick Yao’s tsla-infotainment-lab (MIT). Powered by QEMU, Android, Qt for Python and 7-Zip. Firmware is supplied by you and remains local. Unaffiliated with Hasselblad.', 'Material 主题改编自 Derrick Yao 的 tsla-infotainment-lab（MIT）。基于 QEMU、Android、Qt for Python 和 7-Zip。固件由你提供并保留在本地。本项目与哈苏无隶属关系。', 'muted'))
        card.addWidget(self.button('View source & documentation ↗', '查看源码与文档 ↗', lambda: QDesktopServices.openUrl(QUrl('https://github.com/derrickyau9/Hasselblad-X-System-QEMU-DevKit'))))
        layout.addStretch()

    def navigate(self, n):
        self.pages.setCurrentIndex(n)
        for i, b in enumerate(self.nav): b.setChecked(i == n)
    def change_language(self, index):
        self.lang = 'zh' if index else 'en'; self.preferences['language'] = self.lang
        for setter, en, zh in self.bindings: setter(self.tr(en, zh))
        self.save_preferences(); self.update_controls()
    def appearance(self, *_):
        if not hasattr(self, 'accent'): return
        self.preferences.update(theme=['system','light','dark'][self.theme.currentIndex()], accent=['violet','blue','green'][self.accent.currentIndex()])
        apply_theme(QApplication.instance(), self.preferences['theme'], self.preferences['accent']); self.save_preferences()
    def save_preferences(self): write_json(self.home / 'preferences.json', self.preferences)
    def open_path(self, path): QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
    def open_device(self):
        if self.device: self.open_path(self.device)
    def open_workspace(self):
        if self.device: self.open_path(workspace(self.device))
        else: self.error(self.tr('Import and select a firmware first.', '请先导入并选择固件。'))
    def choose_ndk(self):
        path = QFileDialog.getExistingDirectory(self, 'Android NDK', self.ndk.text())
        if path:
            self.ndk.setText(path); self.preferences['ndk'] = path; self.save_preferences()
    def browse(self):
        path, _ = QFileDialog.getOpenFileName(self, self.tr('Import official firmware', '导入官方固件'), '', 'Hasselblad firmware (*.cim)')
        if path: self.import_file(path)
    def dragEnterEvent(self, event):
        urls = event.mimeData().urls()
        if len(urls) == 1 and urls[0].isLocalFile() and urls[0].toLocalFile().lower().endswith('.cim'): event.acceptProposedAction()
    def dropEvent(self, event): self.import_file(event.mimeData().urls()[0].toLocalFile())
    def busy(self): return bool((self.job and self.job.isRunning()) or (self.session and self.session.isRunning()))
    def import_file(self, path):
        if self.busy(): return self.error(self.tr('Stop the current operation before importing.', '请先停止当前任务再导入。'))
        def done(device):
            self.refresh_library(device)
            self.log(self.tr('Ready. Click Start original UI.', '已就绪，点击「启动原厂 UI」。'))
        self.run_job(lambda task: import_firmware(path, self.home / 'library', task), done)
    def run_job(self, operation, done):
        if self.busy(): return
        self.job = Job(operation); self.job.message.connect(self.log); self.job.failed.connect(self.error); self.job.result.connect(done)
        self.job.finished.connect(self.update_controls); self.job.start(); self.update_controls()
    def cancel_job(self):
        if self.job: self.job.task.cancelled.set()
    def install_runtime(self, *_ , then=None):
        if self.busy(): return
        dialog = QDialog(self); dialog.setWindowTitle(self.tr('Runtime setup', '安装运行环境')); box = QVBoxLayout(dialog)
        box.addWidget(self.label('Download QEMU, 7-Zip and the Android SDK system image from their official sources. They stay in your DevKit data folder.', '从官方来源下载 QEMU、7-Zip 与 Android SDK 系统镜像，保存在 DevKit 数据目录。'))
        license_link = QLabel('<a href="https://developer.android.com/studio/terms">Android SDK License Agreement / Android SDK 许可协议</a>'); license_link.setOpenExternalLinks(True); box.addWidget(license_link)
        accepted = QCheckBox(self.tr('I have read and accept the Android SDK license terms.', '我已阅读并接受 Android SDK 许可条款。')); box.addWidget(accepted)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel); buttons.button(QDialogButtonBox.Ok).setEnabled(False)
        accepted.toggled.connect(buttons.button(QDialogButtonBox.Ok).setEnabled); buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject); box.addWidget(buttons)
        if dialog.exec() != QDialog.Accepted: return
        def done(config):
            self.runtime = config
            if then: QTimer.singleShot(100, then)
        self.run_job(lambda task: setup(self.home, task), done)
    def refresh_library(self, select=None):
        self.devices = sorted((self.home / 'library').glob('*/device.json'))
        self.library.blockSignals(True); self.library.clear()
        selected = 0
        for i, path in enumerate(self.devices):
            data = read_json(path); self.library.addItem(f"{data['name']}\n{data['version']}")
            if select and path.parent == select: selected = i
        self.library.blockSignals(False)
        self.library.setCurrentRow(selected if self.devices else -1)
        if not self.devices: self.select_device(-1)
    def select_device(self, index):
        self.device = self.devices[index].parent if 0 <= index < len(self.devices) else None
        self.screen.frame = None; self.screen.update(); self.last_frame = None
        self.model_choice.blockSignals(True); self.model_choice.clear()
        if self.device:
            profile = read_json(self.device / 'device.json')
            for model in available_models(profile): self.model_choice.addItem(MODELS[model]['label'],model)
            self.model_choice.setCurrentIndex(self.model_choice.findData(model_id(profile)))
        self.model_choice.blockSignals(False)
        self.refresh_apps()
        self.update_controls()
    def select_model(self,index):
        if not self.device or self.busy(): return
        profile = read_json(self.device / 'device.json')
        selected = self.model_choice.itemData(index)
        if selected not in available_models(profile): return
        profile['model'] = selected
        write_json(self.device / 'device.json',profile)
        self.refresh_apps()
        self.update_controls()
    def refresh_apps(self, select=None):
        self.app_choice.clear()
        self.app_choice.addItem(self.tr('Built-in Hello example', '内置 Hello 示例'), None)
        if self.device:
            from .packages import list_packages
            profile = read_json(self.device / 'device.json')
            abi = profile.get('abi') or MODELS[model_id(profile)]['abi']
            for package in list_packages(self.device):
                if package['abi'] == abi and model_id(profile) in package['models']:
                    key = (package['id'], package['version'])
                    self.app_choice.addItem(f"{package['id']} · {package['version']}", key)
                    if key == select: self.app_choice.setCurrentIndex(self.app_choice.count()-1)
    def import_app_package(self):
        if self.busy() or not self.device: return
        path, _ = QFileDialog.getOpenFileName(self, self.tr('Import QEMU guest app', '导入 QEMU 虚拟机应用'), '', 'DevKit guest app (*.xdevapp)')
        if not path: return
        from .packages import install_package
        def done(package):
            self.refresh_apps((package['id'], package['version']))
            self.log(self.tr('Package imported. Select Run app to test in QEMU.', '应用包已导入，点击「运行应用」在 QEMU 中测试。'))
        self.run_job(lambda task: install_package(self.device, path, task), done)
    def remove_app_package(self):
        if self.busy() or not self.device: return
        key = self.app_choice.currentData()
        if key is None: return
        from .packages import remove_package
        self.run_job(lambda task: remove_package(self.device, *key), lambda _: self.refresh_apps())
    def launch(self, checked=False, mode='live'):
        if self.busy() or not self.device: return
        if not self.runtime:
            return self.install_runtime(then=lambda: self.launch(mode=mode))
        network = mode == 'app' and self.app_network.isChecked()
        if network and not network_supported(read_json(self.device / 'device.json'), mode):
            return self.error(self.tr('QEMU networking is verified only for X2D II ARM64 app sessions.', 'QEMU 网络目前只在 X2D II ARM64 应用会话中验证。'))
        app_entry = None
        if mode == 'app':
            key = self.app_choice.currentData()
            if key is None:
                if not (self.device / 'payload-stage/app/hello').exists():
                    return self.error(self.tr('Build the app first.', '请先编译应用。'))
            else:
                from .packages import activate_package, active_package
                try:
                    activate_package(self.device, *key)
                    package = active_package(self.device)
                    app_entry = f"apps/{package['id']}/{package['version']}/{package['entry']}"
                except (OSError, ValueError, RuntimeError, KeyError) as error:
                    return self.error(str(error))
        self.screen.frame = None; self.last_frame = None
        # The network choice applies to one launch only; a later app run starts offline.
        if network: self.app_network.setChecked(False)
        self.session = Session(self.device, self.runtime, mode, app_entry=app_entry, network=network); self.session.message.connect(self.log)
        self.session.console.connect(self.logs.appendPlainText)
        self.session.phase.connect(self.on_phase); self.session.failed.connect(self.error); self.session.finished.connect(self.update_controls)
        self.session.start(); self.navigate(0); self.update_controls()
    def on_phase(self, phase):
        self.current_phase = phase; self.update_controls()
        self.statusBar().showMessage(self.badge.text())
    def stop_session(self):
        if self.session: self.session.stop()
    def build_app(self):
        if self.device and not self.busy(): self.run_job(lambda task: build(self.device, self.ndk.text(), task), lambda result: self.log(str(result)))
    def send_touch(self, op, x, y):
        if self.session: self.session.touch(op, x, y)
    def send_command(self):
        if self.session and self.session.ready and self.command.text().strip():
            self.session.commands.put(self.command.text()); self.command.clear()
    def screenshot(self):
        if self.screen.frame is None: return
        path, _ = QFileDialog.getSaveFileName(self, self.tr('Save screenshot', '保存截图'), 'x2dii-preview.png', 'PNG (*.png)')
        if path and not self.screen.frame.save(path): self.error('Could not save screenshot')
    def tick(self):
        if self.closing:
            if not self.busy(): self.close()
            return
        if self.session and self.session.isRunning() and self.session.frames:
            latest = self.session.frames.latest
            if latest and latest is not self.last_frame:
                head, pixels = latest
                _, w, h, stride, fmt, seq = struct.unpack_from('<6I', head)
                self.screen.frame = QImage(pixels, w, h, stride, QImage.Format_RGB32).copy()
                self.last_frame = latest; self.screen.update(); self.shot.setEnabled(True)
    def update_controls(self):
        busy = self.busy(); live = bool(self.session and self.session.isRunning()); ready = bool(live and self.session.ready)
        self.start.setEnabled(bool(self.device) and not busy); self.stop.setEnabled(live)
        self.library.setEnabled(not busy); self.drop.setEnabled(not busy); self.folder.setEnabled(bool(self.device))
        self.model_choice.setEnabled(not busy and self.model_choice.count()>1)
        for key in self.camera_keys: key.setEnabled(ready)
        self.build_button.setEnabled(bool(self.device) and not busy); self.app_button.setEnabled(bool(self.device) and not busy)
        self.app_choice.setEnabled(bool(self.device) and not busy)
        self.import_app_button.setEnabled(bool(self.device) and not busy)
        self.remove_app_button.setEnabled(bool(self.device) and not busy and self.app_choice.currentData() is not None)
        supports_network = bool(self.device and network_supported(read_json(self.device / 'device.json'), 'app'))
        if not supports_network and self.app_network.isChecked(): self.app_network.setChecked(False)
        self.app_network.setEnabled(supports_network and not busy)
        self.setup_button.setEnabled(not busy); self.send_button.setEnabled(ready); self.command.setEnabled(ready)
        self.shot.setEnabled(self.screen.frame is not None)
        self.progress.setVisible(busy and not ready); self.cancel.setVisible(bool(self.job and self.job.isRunning()))
        phase = getattr(self, 'current_phase', 'stopped') if live else 'stopped'
        statuses = {'starting': ('Starting…', '启动中…'), 'running': ('Running', '运行中'), 'stopping': ('Stopping…', '停止中…'), 'stopped': ('Stopped', '已停止')}
        self.badge.setText(self.tr(*statuses[phase])); self.badge.setProperty('phase', phase)
        self.badge.style().unpolish(self.badge); self.badge.style().polish(self.badge)
        self.screen.caption = self.tr('Click Start original UI', '点击「启动原厂 UI」') if self.device else self.tr('Import official firmware to begin', '导入官方固件，开始开发')
        if live and not ready: self.screen.caption = self.tr('Starting the ARM64 guest…', '正在启动 ARM64 虚拟机…')
        self.screen.update()
        self.runtime_label.setText(self.tr('Runtime ready · QEMU + Android ARM64', '运行环境已就绪 · QEMU + Android ARM64') if self.runtime else self.tr('Runtime not installed. Setup runs once, then works offline.', '尚未安装运行环境，安装一次后可离线使用。'))
        if self.device:
            profile = read_json(self.device / 'device.json'); model = model_id(profile)
            status = self.tr('UI verified','UI 已验证') if profile.get('validated') and model == 'x2dii' else self.tr('UI development preview','UI 开发预览')
            self.details.setText(f"{status}\n{MODELS[model]['abi']} · {profile['version']}")
            self.screen.message = MODELS[model]['label'].removeprefix('Hasselblad ')
        else: self.details.setText(self.tr('Your imported firmware will appear here.', '导入的固件会显示在这里。'))
    def log(self, message):
        if message.strip():
            self.logs.appendPlainText(message); self.statusBar().showMessage(message.splitlines()[-1][:180])
    def error(self, message):
        self.log('ERROR: ' + message)
        QMessageBox.warning(self, self.tr('DevKit needs attention', 'DevKit 提示'), message)
    def closeEvent(self, event):
        if self.busy():
            self.closing = True; self.cancel_job(); self.stop_session()
            self.statusBar().showMessage(self.tr('Stopping the guest before closing…', '正在关闭虚拟机…')); event.ignore()
        else:
            self.save_preferences(); event.accept()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('firmware', nargs='?')
    parser.add_argument('--home', type=Path)
    parser.add_argument('--smoke-test', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    app = QApplication(sys.argv[:1]); app.setApplicationName('X System QEMU DevKit'); app.setOrganizationName('X2DII-DevKit')
    window = Window((args.home or data_home()).resolve()); window.show()
    if args.smoke_test:
        # Packaged-executable verification without requiring UI automation software.
        output = args.smoke_test.resolve(); output.mkdir(parents=True, exist_ok=True)
        def fail(message):
            write_json(output / 'result.json', {'ok': False, 'error': message})
            window.close()
        window.error = fail
        def begin_check():
            if not window.device or not window.runtime:
                return fail('Import firmware and prepare runtime before this check')
            window.launch()
            def phase(value):
                if value == 'running': QTimer.singleShot(5000, capture_check)
            window.session.phase.connect(phase)
        def capture_check():
            window.tick()
            if window.screen.frame is None: return fail('No frame')
            window.screen.frame.save(str(output / 'guest.png'))
            window.grab().save(str(output / 'workbench.png'))
            write_json(output / 'result.json', {'ok': True, 'frozen': bool(getattr(sys, 'frozen', False)), 'firmware': read_json(window.device / 'device.json')['version']})
            window.close()
        if args.firmware:
            def import_check():
                window.import_file(args.firmware)
                window.job.finished.connect(lambda: QTimer.singleShot(100, begin_check) if not window.closing else None)
            QTimer.singleShot(200, import_check)
        else:
            QTimer.singleShot(500, begin_check)
        QTimer.singleShot(240000, lambda: fail('Timed out') if not window.closing else None)
    elif args.firmware: QTimer.singleShot(200, lambda: window.import_file(args.firmware))
    sys.exit(app.exec())
