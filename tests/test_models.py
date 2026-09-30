import hashlib
import io
import struct
import zlib
from pathlib import Path
import pytest
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from devkit import cim
from devkit.core import write_json
from devkit.firmware import profile_metadata
from devkit.models import model_id, available_models, MODELS
from devkit.guest.prepare import command
from devkit.guest.software_ui import legacy_window, build
from devkit.linux_runtime import deb_data, guest_path

@pytest.mark.parametrize('product,known',[
    ('1601254_PVF',b'#!/bin/sh\n\nKERNE'),('1700000_PVF',b'#!/system/bin/sh')])
def test_legacy_and_android_iv_derivation(product,known):
    iv=bytes(range(16)); plaintext=known.ljust(16,b'\0')
    raw=bytearray(256);header=f'VHABCIM\r\n{product}\r\n1\r\n2026\r\n00:00:00'.encode()
    raw[:len(header)]=header
    encryptor=Cipher(algorithms.AES(cim.CIM_AES128_KEY),modes.CBC(iv)).encryptor()
    raw[128:144]=encryptor.update(plaintext)+encryptor.finalize()
    assert cim.derive_iv_from_items(bytes(raw),[{'name':'hbl-upgrade','offset_in_cim':128}])==iv[:len(known)]

def test_shared_firmware_offers_two_real_model_identities():
    p=profile_metadata('Hasselblad X1D II / 907X 50C','1.5.2','1bb69d26627d3af6'+'0'*48,'CFV_II_50C_v1_5_2.cim','arm32')
    assert model_id(p)=='907x50c'
    assert available_models(p)==['x1dii','907x50c']
    assert not p['validated']

@pytest.mark.parametrize('model',list(MODELS))
def test_guest_uses_selected_hardware_identity(tmp_path,model):
    write_json(tmp_path/'device.json',{'model':model,'abi':MODELS[model]['abi']})
    args=command(tmp_path,{'image':'runtime/image','qemu':'runtime/qemu'},10001,10002,10003)
    assert f'hw_version={MODELS[model]["hardware"]}' in args[args.index('-append')+1]
    assert args[args.index('-nic')+1]=='none'
    assert any('id=linuxroot' in a for a in args)==(model=='x1d')

def test_no_shader_resource_is_copied_without_instruction_changes(tmp_path):
    original=tmp_path/'gui';original.write_bytes(b'ELF stand-in without embedded QML')
    report=build(original,tmp_path/'adapted')
    assert (tmp_path/'adapted').read_bytes()==original.read_bytes()
    assert report['qml_source_offsets']==[]

def test_legacy_window_adapts_only_compressed_resource(tmp_path):
    qml=b'import QtQuick 2.2\nItem {\n    objectName: "mainRoot"\n// Control state:\n}\n'
    compressed=zlib.compress(qml);capacity=len(compressed)+128
    resource=struct.pack('>II',capacity+4,len(qml))+compressed.ljust(capacity,b'\0')
    before=b'ELF-CODE-UNCHANGED';after=b'OTHER-RESOURCES'
    source=tmp_path/'gui';source.write_bytes(before+resource+after)
    target=tmp_path/'adapted';legacy_window(source,target);out=target.read_bytes()
    assert source.read_bytes()==before+resource+after
    assert out[:len(before)]==before and out[-len(after):]==after
    assert len(out)==source.stat().st_size
    assert b'Window {' in zlib.decompress(out[len(before)+8:])

@pytest.mark.parametrize('name',['../../x','/etc/passwd','usr/../escape','lib\\bad'])
def test_linux_runtime_paths_stay_in_guest(name):
    with pytest.raises(ValueError):guest_path(name)

def test_malformed_debian_archive_is_rejected():
    with pytest.raises(ValueError):deb_data(b'!<arch>\n')
