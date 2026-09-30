import io
from pathlib import Path
import struct
import zipfile
import pytest
from devkit.core import checked_child, Task, Cancelled
from devkit.firmware import reconstruct, ranges, import_firmware
from devkit.runtime import unzip

@pytest.mark.parametrize('name', ['../escape', '/root', 'a/../../b', 'C:/x', 'a:stream', 'CON.txt', 'a/NUL', 'x. ', 'a\\..\\b', 'a//b'])
def test_archive_cannot_escape_or_alias_windows_paths(tmp_path, name):
    with pytest.raises(ValueError): checked_child(tmp_path, name)

def test_only_imported_components_are_written(tmp_path):
    bad = tmp_path/'bad.zip'
    with zipfile.ZipFile(bad, 'w') as z: z.writestr('../outside', b'x')
    with pytest.raises(ValueError): unzip(bad, tmp_path/'out', Task())
    assert not (tmp_path/'outside').exists()

def test_zip_case_collisions_rejected(tmp_path):
    bad = tmp_path/'bad.zip'
    with zipfile.ZipFile(bad, 'w') as z:
        z.writestr('file', b'x'); z.writestr('FILE', b'y')
    with pytest.raises(ValueError): unzip(bad, tmp_path/'out', Task())

def test_reconstruct_full_ota_preserves_holes(tmp_path):
    output = tmp_path/'system.img'
    reconstruct('4\n2\n0\n0\nerase 2,0,4\nnew 4,0,1,3,4', io.BytesIO(b'A'*4096+b'B'*4096), output, Task())
    assert output.read_bytes() == b'A'*4096 + b'\0'*8192 + b'B'*4096

@pytest.mark.parametrize('command', ['move 2,0,1', 'new 3,0,1,2', 'new 2,0,99999999'])
def test_ota_rejects_delta_and_invalid_ranges(tmp_path, command):
    with pytest.raises(ValueError): reconstruct('4\n1\n0\n0\n'+command, io.BytesIO(b''), tmp_path/'s', Task())

def test_ota_rejects_truncation(tmp_path):
    with pytest.raises(ValueError): reconstruct('4\n1\n0\n0\nnew 2,0,1', io.BytesIO(b'x'), tmp_path/'s', Task())

def test_invalid_firmware_does_not_change_input(tmp_path):
    source = tmp_path/'bad.cim'; original = b'not a firmware'*400
    source.write_bytes(original)
    with pytest.raises(ValueError): import_firmware(source, tmp_path/'library')
    assert source.read_bytes() == original
    assert not (tmp_path/'library').exists()

def test_cancellation_is_observed():
    task = Task(); task.cancelled.set()
    with pytest.raises(Cancelled): task.check()
