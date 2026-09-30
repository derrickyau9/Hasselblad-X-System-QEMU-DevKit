"""One owned QEMU process, loopback transports and a guest-only console."""
import os
import shutil
import queue
import select
import socket
import subprocess
import time
from PySide6.QtCore import QThread, Signal
from .core import ASSETS, Task, Cancelled, GuestLock
from .guest.prepare import prepare, command
from .guest.frame_stream import FrameStream

class Session(QThread):
    message = Signal(str)
    phase = Signal(str)
    failed = Signal(str)

    def __init__(self, device, runtime, mode='live'):
        super().__init__()
        self.device, self.runtime = device, runtime
        self.mode = mode
        self.task = Task(self.message.emit)
        self.frames = None
        self.commands, self.touches = queue.Queue(), queue.Queue(maxsize=512)
        self.ready = False
        self.process = None

    def stop(self):
        self.task.cancelled.set()

    def touch(self, operation, x, y):
        if self.ready:
            try:
                self.touches.put_nowait(f'{operation} {int(x)} {int(y)}\n'.encode())
            except queue.Full:
                pass

    def run(self):
        connection = fast = frames = process = None
        lock = None
        errors = log = None
        try:
            self.phase.emit('starting')
            lock = GuestLock(self.device)
            (self.device / 'payload-stage/camera/run.sh').write_bytes((ASSETS / 'guest/camera_run.sh').read_bytes().replace(b'\r\n', b'\n'))
            for name in ('mini_compositor', 'mock_services', 'dbus_launcher'):
                shutil.copy2(ASSETS / 'helpers' / name, self.device / 'payload-stage' / name)
            prepare(self.device, self.runtime, self.task)
            with (self.device / 'framebuffer.raw').open('wb') as f:
                f.truncate(32*1024**2)
            reservations = [socket.socket() for _ in range(3)]
            try:
                for reservation in reservations:
                    reservation.bind(('127.0.0.1', 0))
                ports = [s.getsockname()[1] for s in reservations]
            finally:
                for reservation in reservations:
                    reservation.close()
            errors = (self.device / 'qemu.log').open('wb')
            log = (self.device / 'console.log').open('wb')
            process = self.process = subprocess.Popen(command(self.device, self.runtime, *ports), stdout=errors,
                        stderr=errors, creationflags=subprocess.CREATE_NO_WINDOW)
            for attempt in range(100):
                self.task.check()
                try:
                    connection = socket.create_connection(('127.0.0.1', ports[0]), timeout=.5)
                    break
                except OSError:
                    if process.poll() is not None:
                        raise RuntimeError('QEMU exited; see qemu.log in the selected firmware folder')
                    time.sleep(.1)
            if connection is None:
                raise TimeoutError('QEMU console did not become available')
            connection.settimeout(.1)
            fast = socket.create_connection(('127.0.0.1', ports[1]), timeout=3)
            fast.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            fast.settimeout(.05)
            stream = socket.create_connection(('127.0.0.1', ports[2]), timeout=3)
            stream.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4*1024**2)
            stream.settimeout(.5)
            frames = self.frames = FrameStream(stream)

            def received():
                try:
                    data = connection.recv(65536)
                except socket.timeout:
                    return b''
                if not data:
                    raise ConnectionError('Guest console disconnected')
                log.write(data); log.flush()
                return data

            def until(marker, seconds):
                buffer = bytearray()
                end = time.monotonic() + seconds
                while time.monotonic() < end:
                    self.task.check()
                    if process.poll() is not None:
                        raise RuntimeError('QEMU exited during startup')
                    buffer.extend(received())
                    if b'X2DII_UI_FAILED' in buffer:
                        raise RuntimeError('Guest application failed to start; see console.log')
                    if marker in buffer:
                        return
                    if len(buffer) > 262144:
                        del buffer[:131072]
                raise TimeoutError(f'Guest startup timed out waiting for {marker.decode()}; see console.log')

            def send(text, cancellable=True):
                wire = (text + '\n').encode()
                for offset in range(0, len(wire), 8):
                    if cancellable:
                        self.task.check()
                    connection.sendall(wire[offset:offset+8])
                    time.sleep(.08)

            self.message.emit('Booting Android ARM64 guest / 启动 ARM64 虚拟机…')
            until(b'console:/ $', 90)
            send('su 0'); until(b'console:/ #', 15)
            for line in ['dmesg -n 1', 'stop surfaceflinger', 'stop vendor.hwcomposer-2-1',
                         'mkdir -p /mnt/x2dii', 'mount -t vfat /dev/block/vde1 /mnt/x2dii']:
                send(line); until(b'console:/ #', 15)
            self.message.emit('Starting original camera UI / 启动原厂界面…')
            send(f'sh /mnt/x2dii/camera/run.sh {self.mode} &')
            until(b'X2DII_UI_SESSION_READY', 150)
            deadline = time.monotonic() + 30
            while frames.latest is None and time.monotonic() < deadline:
                self.task.check(); received()
            if frames.latest is None:
                raise RuntimeError('Guest started but no valid UI frame arrived')
            self.ready = True
            self.phase.emit('running')
            self.message.emit('Original UI is ready / 原厂界面已就绪')
            while not self.task.cancelled.is_set():
                if process.poll() is not None:
                    raise RuntimeError('QEMU stopped unexpectedly')
                if frames.error:
                    raise RuntimeError(frames.error)
                while not self.touches.empty():
                    fast.sendall(self.touches.get_nowait())
                readable, _, _ = select.select([fast, connection], [], [], .008)
                if fast in readable:
                    if not fast.recv(4096):
                        raise ConnectionError('Input disconnected')
                if not self.commands.empty():
                    send(self.commands.get_nowait())
                output = received() if connection in readable else b''
                if output:
                    self.message.emit(output.decode(errors='replace').strip())
            self.phase.emit('stopping')
            send('reboot -p', cancellable=False)
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                pass
        except Cancelled:
            pass
        except Exception as error:
            self.failed.emit(str(error))
        finally:
            self.ready = False
            if process and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait()
            if frames:
                frames.close(self.device / 'framebuffer.raw')
            for resource in (fast, connection, errors, log, lock):
                if resource:
                    resource.close()
            self.phase.emit('stopped')
