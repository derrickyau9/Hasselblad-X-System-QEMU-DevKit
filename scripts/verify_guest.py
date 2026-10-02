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
p.add_argument('--network', action='store_true', help='Enable guest networking for X2D II ARM64 app sessions only')
p.add_argument('--package', help='Installed guest package as ID@version; requires --app')
p.add_argument('--key', type=int, choices=range(1,6), help='Press virtual F1–F5 before capture')
p.add_argument('--model', choices=['x1d','x1dii','907x50c','x2d','x2dii'])
p.add_argument('--tap',type=int,nargs=2,metavar=('X','Y'),help='Tap a specific menu control after the optional key')
p.add_argument('--device', help='Imported firmware SHA256 prefix')
p.add_argument('--output', type=Path, help='Directory for screenshots (defaults to --home)')
args = p.parse_args()
app = QApplication([])
font_root = Path(os.environ['WINDIR']) / 'Fonts' if os.environ.get('WINDIR') else None
if font_root:
    for font in ('segoeui.ttf', 'segoeuil.ttf', 'msyh.ttc'):
        QFontDatabase.addApplicationFont(str(font_root / font))
w = Window(args.home.resolve())
if args.device:
    w.refresh_library(args.home.resolve() / 'library' / args.device)
if args.model:
    index=w.model_choice.findData(args.model)
    if index<0: raise SystemExit('Selected firmware cannot run this model')
    w.model_choice.setCurrentIndex(index)
if args.package:
    if not args.app or '@' not in args.package:
        raise SystemExit('--package requires --app and ID@version')
    package_key=tuple(args.package.rsplit('@',1))
    for index in range(w.app_choice.count()):
        if w.app_choice.itemData(index)==package_key:
            w.app_choice.setCurrentIndex(index)
            break
    else:
        raise SystemExit('Package is not installed for this firmware model and ABI')
if args.network:
    if not args.app:
        raise SystemExit('--network requires --app')
    if not w.app_network.isEnabled():
        raise SystemExit('--network is verified only for X2D II ARM64 app sessions')
    w.app_network.setChecked(True)
w.error = lambda message: (print('FAILED:', message, flush=True), QTimer.singleShot(0,lambda:app.exit(1)))
w.show()
result = {'running': False}
def capture():
    w.tick()
    if w.screen.frame is None:
        print('FAILED: No frame', flush=True); app.exit(1); return
    suffix = 'app' if args.app else 'original'
    output = args.output or args.home
    output.mkdir(parents=True, exist_ok=True)
    w.screen.frame.save(str(output / f'verified-{suffix}.png'))
    w.grab().save(str(output / f'verified-workbench-{suffix}.png'))
    # Transport success alone does not establish usable UI support.
    image=w.screen.frame
    colors={image.pixelColor(x,y).rgb() for x in range(0,image.width(),8) for y in range(0,image.height(),8)}
    if len(colors)<3:
        print('FAILED: blank frame; capture retained for diagnosis',flush=True)
        w.stop_session();return
    print('CAPTURED: nonblank guest frame; inspect screenshot to verify UI and interaction', flush=True)
    w.stop_session()
    result['running'] = True
def phase(value):
    print('PHASE:', value, flush=True)
    if value == 'running':
        if args.key:
            QTimer.singleShot(2000, lambda: w.session.touch('key', 58+args.key, 1))
            QTimer.singleShot(2200, lambda: w.session.touch('key', 58+args.key, 0))
        elif not args.app:
            QTimer.singleShot(3000, lambda: w.session.touch('down', 393, 390))
            QTimer.singleShot(3200, lambda: w.session.touch('up', 393, 390))
        if args.tap:
            QTimer.singleShot(5000,lambda:w.session.touch('down',*args.tap))
            QTimer.singleShot(5200,lambda:w.session.touch('up',*args.tap))
        QTimer.singleShot(12000, capture)
    elif value == 'stopped':
        QTimer.singleShot(1000, lambda: app.exit(0 if result['running'] else 1))
w.launch(mode='app' if args.app else 'live')
if w.session:
    w.session.phase.connect(phase)
    w.session.message.connect(lambda s: print(s, flush=True))
QTimer.singleShot(600000, lambda: (print('FAILED: timeout', flush=True), w.stop_session()))
code = app.exec()
if w.session:
    w.session.stop(); w.session.wait(30000)
sys.exit(code)
