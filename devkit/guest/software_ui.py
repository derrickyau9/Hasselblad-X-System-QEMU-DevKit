"""Apply a bounded QML rendering adaptation to a disposable development copy.

The original executable and executable instructions are preserved. The two
equal-length substitutions expose the Image and hide its GPU ShaderEffect.
QML_DISABLE_DISK_CACHE=1 is required to load the adapted embedded source.
"""
from pathlib import Path
import hashlib
import json

def build(source: Path, destination: Path):
    data = source.read_bytes()
    start = data.index(b'    objectName: "hblimage_root"')
    end = data.index(b'    objectName: "hblimage_shader"', start)
    changes = [
        (b'        visible: false', b'        visible: true ', start, end),
        (b'        visible: root.ready', b'        visible: false     ', end, end + 400),
    ]
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
