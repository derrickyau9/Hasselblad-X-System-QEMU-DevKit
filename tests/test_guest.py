import socket
import struct
import time
from pathlib import Path
from devkit.guest.prepare import command
from devkit.guest.frame_stream import FrameStream

def test_session_lock_prevents_concurrent_disk_writers(tmp_path):
    import pytest
    from devkit.core import GuestLock
    with GuestLock(tmp_path):
        with pytest.raises(RuntimeError): GuestLock(tmp_path)
    with GuestLock(tmp_path): pass

def test_guest_has_no_external_network_or_host_device_access(tmp_path):
    args = command(tmp_path, {'qemu':'C:/runtime/qemu', 'image':'C:/runtime/image'}, 41001, 41002, 41003)
    assert args[args.index('-nic')+1] == 'none'
    assert 'snapshot=on' in ' '.join(args)
    assert not any('usb-host' in arg or 'hostfwd' in arg or 'PhysicalDrive' in arg for arg in args)
    channels = [args[n+1] for n,a in enumerate(args) if a in ('-chardev','-serial')]
    assert all('127.0.0.1' in channel for channel in channels)

def test_invalid_frame_fails_without_allocating_pixels(tmp_path):
    a,b = socket.socketpair(); b.settimeout(.1)
    stream = FrameStream(b)
    a.sendall(struct.pack('<6I', 0x58463244, 900000, 768, 4000000, 1, 1).ljust(512,b'\0'))
    stream.thread.join(2)
    assert stream.latest is None
    assert stream.error == 'invalid frame stream header'
    stream.close(tmp_path/'unused');a.close()

def test_complete_frame_survives_fragmented_transport(tmp_path):
    import threading
    a,b = socket.socketpair(); b.settimeout(.1)
    stream=FrameStream(b)
    header=struct.pack('<6I',0x58463244,1024,768,4096,1,7).ljust(512,b'\0')
    pixels=b'\x44\x33\x22\xff'*(1024*768)
    def send():
        a.sendall(header[:39]);a.sendall(header[39:]);a.sendall(pixels)
    worker=threading.Thread(target=send);worker.start()
    deadline=time.monotonic()+3
    while stream.latest is None and time.monotonic()<deadline:time.sleep(.01)
    assert stream.latest == (header,pixels)
    worker.join();target=tmp_path/'snapshot';target.touch()
    stream.close(target);a.close()
    assert target.read_bytes()==header+pixels
