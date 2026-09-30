"""Drain the private QEMU virtio frame stream without blocking the GUI thread."""
import socket
import struct
import threading

class FrameStream:
    def __init__(self, connection):
        self.connection = connection
        self.latest = None
        self.error = None
        self.stopped = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _read(self, size):
        chunks = bytearray()
        while len(chunks) < size and not self.stopped.is_set():
            try:
                data = self.connection.recv(min(size-len(chunks), 262144))
                if not data:
                    raise EOFError("frame stream closed")
                chunks.extend(data)
            except socket.timeout:
                continue
        if len(chunks) != size:
            raise EOFError("frame receiver stopped")
        return bytes(chunks)

    def _run(self):
        try:
            while not self.stopped.is_set():
                header = self._read(512)
                magic, w, h, stride, fmt, number = struct.unpack_from("<6I", header)
                if magic != 0x58463244 or w != 1024 or h != 768 or not w*4 <= stride <= 32768 or fmt > 1:
                    raise ValueError("invalid frame stream header")
                pixels = self._read(stride*h)
                self.latest = (header, pixels)
        except (OSError, EOFError, ValueError) as error:
            if not self.stopped.is_set():
                self.error = str(error)

    def close(self, snapshot):
        self.stopped.set()
        try:
            self.connection.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.connection.close()
        self.thread.join(timeout=2)
        if self.latest:
            header, pixels = self.latest
            with snapshot.open("r+b") as output:
                output.write(header)
                output.write(pixels)
