"""Apply a bounded QML rendering adaptation to a disposable development copy.

The original executable and executable instructions are preserved. Image
adaptations use equal-length substitutions; legacy root-window changes are
recompressed within the original resource capacity. QML_DISABLE_DISK_CACHE=1
is required to load adapted embedded source on the Android profiles.
"""
from pathlib import Path
import hashlib
import json
import re
import struct
import zlib

def legacy_window(source: Path, destination: Path):
    """Give Qt 5.5's root Item a window when loaded by the Linux Qt 5.15 runtime."""
    data = source.read_bytes(); result = bytearray(data); changed = []
    for match in re.finditer(b'\x78[\x01\x9c\xda]', data):
        offset = match.start()
        if offset < 8: continue
        size, original_size = struct.unpack_from('>II',data,offset-8)
        if not 4 < size < 1024*1024 or offset+size-4 > len(data): continue
        try: qml = zlib.decompress(data[offset:offset+size-4])
        except zlib.error: continue
        marker = b'Item {\n    objectName: "mainRoot"'
        if marker not in qml or b'Control state:' not in qml: continue
        if len(qml) != original_size: raise ValueError('Unexpected legacy QML resource size')
        qml = qml.replace(b'import QtQuick 2.2',b'import QtQuick 2.2\nimport QtQuick.Window 2.1',1)
        qml = qml.replace(marker,b'Window {\n    visible: true\n    width: 1024; height: 768\n    objectName: "mainRoot"',1)
        compressed = zlib.compress(qml,9)
        if len(compressed)>size-4: raise ValueError('Legacy QML adaptation exceeds resource capacity')
        struct.pack_into('>I',result,offset-4,len(qml))
        result[offset:offset+size-4]=compressed.ljust(size-4,b'\0')
        changed.append(offset)
    if len(changed)!=1: raise ValueError('Unsupported legacy root-window resource')
    destination.write_bytes(result)
    report={'purpose':'QEMU-only root window for Linux Qt 5.15','qml_resource_offsets':changed,
            'original_sha256':hashlib.sha256(data).hexdigest(),'development_sha256':hashlib.sha256(result).hexdigest()}
    destination.with_suffix('.json').write_text(json.dumps(report,indent=2))
    return report

def build(source: Path, destination: Path):
    data = source.read_bytes()
    if b'    objectName: "hblimage_root"' in data:
        start = data.index(b'    objectName: "hblimage_root"')
        end = data.index(b'    objectName: "hblimage_shader"', start)
        changes = [
            (b'        visible: false', b'        visible: true ', start, end),
            (b'        visible: root.ready', b'        visible: false     ', end, end + 400),
        ]
    elif b'    objectName: "uiimage_root"' in data:
        start = data.index(b'    objectName: "uiimage_root"')
        end = data.index(b'    objectName: "uiimage_shader"', start)
        shader_visibility = b'        visible: image.status === Image.Ready && (!lut.used || lut.status === Image.Ready)'
        changes = [
            (b'        visible: false', b'        visible: true ', start, end),
            (shader_visibility, b'        visible: false'.ljust(len(shader_visibility), b' '), end, end + 600),
        ]
    else:
        changes = []
    result = bytearray(data)
    offsets = []
    for old, new, low, high in changes:
        if len(old) != len(new):
            raise ValueError("Adaptation changes embedded resource size")
        offset = data.index(old, low, high)
        result[offset:offset + len(old)] = new
        offsets.append(offset)
    destination.write_bytes(result)
    report = {"purpose": "QEMU-only software rendering of original QML images",
              "original_sha256": hashlib.sha256(data).hexdigest(),
              "development_sha256": hashlib.sha256(result).hexdigest(),
              "qml_source_offsets": offsets,
              "executable_size_unchanged": len(data) == len(result)}
    destination.with_suffix(".json").write_text(json.dumps(report, indent=2))
    return report
