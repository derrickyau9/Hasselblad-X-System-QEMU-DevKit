# Adapted from tsla-infotainment-lab, Copyright (c) 2026 Derrick Yao.
# MIT license: see third-party-licenses/tsla-infotainment-lab.txt.
"""Material 3 inspired native Qt surfaces and semantic color roles.

Curated palettes keep contrast predictable; no wallpaper or firmware asset access
is needed. Appearance changes update widgets in place, preserving live controls.
"""
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QWidget


ACCENTS = {
    'violet': ('#6750a4', '#ffffff', '#eaddff', '#21005d', '#d0bcff', '#381e72', '#4f378b', '#eaddff'),
    'blue': ('#415f91', '#ffffff', '#d6e3ff', '#001b3e', '#aac7ff', '#0a305f', '#284777', '#d6e3ff'),
    'green': ('#386a20', '#ffffff', '#b8f397', '#072100', '#9dd67d', '#113800', '#205107', '#b8f397'),
}


def colors(mode='light', accent='violet'):
    dark = mode == 'dark'
    tones = ACCENTS.get(accent, ACCENTS['violet'])
    roles = dict(zip(('primary', 'on_primary', 'primary_container', 'on_primary_container'), tones[4:] if dark else tones[:4]))
    roles.update(dict(zip(
        ('surface', 'container', 'high', 'on_surface', 'muted', 'outline', 'outline_variant', 'secondary_container',
         'on_secondary_container', 'error_container', 'on_error_container', 'error', 'disabled', 'preview'),
        ('#141218', '#211f26', '#2b2930', '#e6e0e9', '#cac4d0', '#938f99', '#49454f', '#4a4458',
         '#e8def8', '#8c1d18', '#ffdad6', '#ffb4ab', '#8e8994', '#0f0e13') if dark else
        ('#fef7ff', '#f3edf7', '#ece6f0', '#1d1b20', '#49454f', '#79747e', '#cac4d0', '#e8def8',
         '#1d192b', '#f9dedc', '#410e0b', '#b3261e', '#716c76', '#e6e0e9'))))
    return roles


def current_colors():
    app = QApplication.instance()
    return getattr(app, 'material_colors', colors())


def state(widget, name, value):
    if widget.property(name) != value:
        widget.setProperty(name, value)
        widget.style().unpolish(widget)
        widget.style().polish(widget)
        QWidget.update(widget)


def stylesheet(c):
    template = '''
QWidget { background: transparent; color: @on_surface; font-family: 'Segoe UI', 'Microsoft YaHei UI', 'Noto Sans CJK SC', sans-serif; font-size: 14px; }
QMainWindow, QDialog, QMessageBox, QMenu { background: @surface; }
QFrame#sidebar { background: @container; border-radius: 24px; }
QFrame#card, QFrame#panel { background: @container; border: 0; border-radius: 24px; }
QLabel#muted { color: @muted; }
QLabel#eyebrow { color: @primary; font-size: 12px; font-weight: 600; }
QLabel#title { font-size: 30px; font-weight: 500; }
QLabel#subtitle { font-size: 20px; font-weight: 500; }
QLabel#metric { font-size: 32px; font-weight: 500; }
QLabel#notice { padding: 14px 18px; background: @secondary_container; border-radius: 16px; color: @on_secondary_container; }
QLabel#notice[error="true"] { background: @error_container; color: @on_error_container; }
QLabel#muted[active="true"] { color: @primary; }
QLabel#badge { color: @on_secondary_container; background: @secondary_container; border-radius: 12px; padding: 6px 12px; font-size: 12px; }
QLabel#badge[phase="running"] { background: @primary_container; color: @on_primary_container; }
QLabel#badge[phase="failed"], QLabel#badge[phase="degraded"] { background: @error_container; color: @on_error_container; }
QPushButton { background: @secondary_container; color: @on_secondary_container; border: 2px solid transparent; border-radius: 20px; padding: 9px 16px; font-weight: 600; min-height: 18px; }
QPushButton:hover { background: @high; border-color: @outline; }
QPushButton:pressed, QPushButton:checked { background: @primary_container; color: @on_primary_container; border-color: @primary; }
QPushButton#primary { background: @primary; color: @on_primary; }
QPushButton#primary:hover { border-color: @on_primary_container; }
QPushButton#danger { background: transparent; color: @error; border-color: @outline_variant; }
QPushButton:disabled, QPushButton#primary:disabled, QPushButton#danger:disabled { background: @high; color: @disabled; border-color: transparent; }
QPushButton:focus, QToolButton:focus { border: 2px solid @primary; }
QToolButton#nav { text-align: left; background: transparent; color: @muted; padding: 10px 14px; border: 2px solid transparent; border-radius: 22px; min-height: 22px; font-size: 14px; }
QToolButton#nav:checked { background: @secondary_container; color: @on_secondary_container; }
QToolButton#nav:hover { background: @high; }
QToolButton#nav:focus { border-color: @primary; }
QToolButton { background: transparent; border: 2px solid transparent; border-radius: 16px; padding: 6px; color: @muted; }
QToolButton:hover { background: @secondary_container; }
QToolButton:disabled { color: @disabled; }
QComboBox, QDoubleSpinBox, QLineEdit { background: @surface; border: 1px solid @outline; border-radius: 10px; padding: 10px 12px; min-height: 18px; selection-background-color: @primary_container; selection-color: @on_primary_container; }
QComboBox { padding-right: 28px; }
QComboBox:focus, QDoubleSpinBox:focus, QLineEdit:focus { border: 2px solid @primary; padding: 9px 11px; }
QComboBox:disabled, QDoubleSpinBox:disabled, QLineEdit:disabled { color: @disabled; border-color: @outline_variant; }
QComboBox::drop-down { border: 0; width: 26px; }
QComboBox::down-arrow { image: url("@arrow_down"); width: 16px; height: 16px; }
QDoubleSpinBox { padding-right: 30px; }
QDoubleSpinBox::up-button { subcontrol-origin: border; subcontrol-position: top right; width: 28px; border: 0; }
QDoubleSpinBox::down-button { subcontrol-origin: border; subcontrol-position: bottom right; width: 28px; border: 0; }
QDoubleSpinBox::up-arrow { image: url("@arrow_up"); width: 16px; height: 16px; }
QDoubleSpinBox::down-arrow { image: url("@arrow_down"); width: 16px; height: 16px; }
QMenu::item { padding: 10px 20px; }
QMenu::item:selected { background: @primary_container; color: @on_primary_container; border-radius: 8px; }
QComboBox QAbstractItemView { background: @container; color: @on_surface; selection-background-color: @primary_container; selection-color: @on_primary_container; padding: 6px; }
QGroupBox { border: 1px solid @outline_variant; border-radius: 16px; margin-top: 14px; padding: 18px 12px 12px; color: @muted; }
QGroupBox::title { subcontrol-origin: margin; left: 16px; padding: 0 6px; }
QTabWidget::pane { border: 0; background: @container; border-radius: 16px; padding: 8px; }
QTabBar::tab { padding: 12px 14px; color: @muted; border-bottom: 3px solid transparent; }
QTabBar::tab:selected { color: @primary; border-bottom-color: @primary; }
QTabBar::tab:hover { background: @high; }
QListWidget { background: transparent; border: 0; padding: 0; outline: 0; }
QListWidget::item { padding: 14px 10px; border: 2px solid transparent; border-radius: 16px; }
QListWidget::item:selected { background: @primary_container; color: @on_primary_container; }
QListWidget::item:hover { border-color: @outline_variant; }
QListWidget::item:focus { border-color: @primary; }
QTextEdit { background: @surface; border: 1px solid @outline_variant; border-radius: 16px; padding: 16px; font-family: 'Cascadia Code', 'DejaVu Sans Mono', monospace; font-size: 12px; selection-background-color: @primary_container; selection-color: @on_primary_container; }
QProgressBar { border: 0; background: @secondary_container; border-radius: 2px; max-height: 4px; }
QProgressBar::chunk { background: @primary; border-radius: 2px; }
QSlider { min-height: 30px; }
QSlider::groove:horizontal { height: 8px; background: @secondary_container; border-radius: 4px; }
QSlider::sub-page:horizontal { background: @primary; border-radius: 4px; }
QSlider::handle:horizontal { background: @primary; border: 2px solid @surface; width: 20px; margin: -8px 0; border-radius: 12px; }
QSlider::handle:horizontal:focus { border-color: @on_primary_container; }
QSlider::sub-page:horizontal:disabled, QSlider::handle:horizontal:disabled { background: @disabled; }
QCheckBox { spacing: 10px; padding: 4px 0; }
QCheckBox::indicator { width: 20px; height: 20px; }
QCheckBox:disabled { color: @disabled; }
QScrollArea { border: 0; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 0; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 0; }
QScrollBar::handle { background: @outline_variant; border-radius: 5px; min-height: 32px; min-width: 32px; }
QScrollBar::handle:hover { background: @outline; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QToolTip { color: @surface; background: @on_surface; border: 0; padding: 8px; }
DropArea { border: 1px dashed @primary; border-radius: 20px; background: @primary_container; }
DropArea QLabel, DropArea QLabel#muted { color: @on_primary_container; }
DropArea:focus { border: 2px solid @primary; }
'''
    appearance = 'dark' if c['surface'] == colors('dark')['surface'] else 'light'
    for direction in ('up', 'down'):
        path = Path(__file__).parent / 'assets' / f'chevron-{direction}-{appearance}.svg'
        template = template.replace('@arrow_' + direction, path.as_posix())
    for name in sorted(c, key=len, reverse=True):
        template = template.replace('@' + name, c[name])
    return template


def apply_theme(app, mode='system', accent='violet'):
    if mode == 'system':
        mode = 'dark' if app.styleHints().colorScheme() == Qt.ColorScheme.Dark else 'light'
    c = colors(mode, accent)
    if getattr(app, 'material_colors', None) == c:
        return c
    app.material_colors = c
    palette = QPalette()
    for role, key in ((QPalette.Window, 'surface'), (QPalette.WindowText, 'on_surface'),
                      (QPalette.Base, 'surface'), (QPalette.AlternateBase, 'container'),
                      (QPalette.Text, 'on_surface'), (QPalette.Button, 'secondary_container'),
                      (QPalette.ButtonText, 'on_secondary_container'), (QPalette.Highlight, 'primary'),
                      (QPalette.HighlightedText, 'on_primary'), (QPalette.ToolTipBase, 'on_surface'),
                      (QPalette.ToolTipText, 'surface'), (QPalette.PlaceholderText, 'muted')):
        palette.setColor(role, QColor(c[key]))
    for role in (QPalette.Text, QPalette.ButtonText, QPalette.WindowText):
        palette.setColor(QPalette.Disabled, role, QColor(c['disabled']))
    app.setPalette(palette)
    app.setStyleSheet(stylesheet(c))
    for widget in app.allWidgets():
        QWidget.update(widget)
    return c
