"""Explicit local integration check; requires an already imported firmware/runtime."""
import argparse
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from PySide6.QtGui import QFontDatabase
from devkit.application import Window

p = argparse.ArgumentParser()
p.add_argument('--home', type=Path, required=True)
p.add_argument('--app', action='store_true')
p.add_argument('--device', help='Imported firmware SHA256 prefix')
args = p.parse_args()
app = QApplication([])
font_root = Path(os.environ['WINDIR']) / 'Fonts' if os.environ.get('WINDIR') else None
if font_root:
    for font in ('segoeui.ttf', 'segoeuil.ttf', 'msyh.ttc'):
        QFontDatabase.addApplicationFont(str(font_root / font))
w = Window(args.home.resolve())
if args.device:
    w.refresh_library(args.home.resolve() / 'library' / args.device)
w.error = lambda message: (print('FAILED:', message, flush=True), app.exit(1))
w.show()
result = {'running': False}
def capture():
    w.tick()
    if w.screen.frame is None:
        print('FAILED: No frame', flush=True); app.exit(1); return
    suffix = 'app' if args.app else 'original'
    w.screen.frame.save(str(args.home / f'verified-{suffix}.png'))
    w.grab().save(str(args.home / f'verified-workbench-{suffix}.png'))
    print('PASS: running guest and captured real frame', flush=True)
    w.stop_session()
    result['running'] = True
def phase(value):
    print('PHASE:', value, flush=True)
    if value == 'running':
        if not args.app:
            QTimer.singleShot(3000, lambda: w.session.touch('down', 393, 390))
            QTimer.singleShot(3200, lambda: w.session.touch('up', 393, 390))
        QTimer.singleShot(12000, capture)
    elif value == 'stopped':
        QTimer.singleShot(1000, lambda: app.exit(0 if result['running'] else 1))
w.launch(mode='app' if args.app else 'live')
if w.session:
    w.session.phase.connect(phase)
    w.session.message.connect(lambda s: print(s, flush=True))
QTimer.singleShot(240000, lambda: (print('FAILED: timeout', flush=True), w.stop_session()))
code = app.exec()
if w.session:
    w.session.stop(); w.session.wait(30000)
sys.exit(code)
