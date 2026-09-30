import struct
import zlib
from pathlib import Path
SECTOR = 512

def patched_chunks(source: Path, new_name: str):
    with source.open("rb") as stream:
        stream.seek(SECTOR)
        primary = stream.read(SECTOR)
        if primary[:8] != b"EFI PART":
            raise ValueError(f"{source} is not a GPT disk image")
        backup_lba = struct.unpack_from("<Q", primary, 32)[0]
        locations = [1, backup_lba]
        for header_lba in locations:
            stream.seek(header_lba * SECTOR)
            header = bytearray(stream.read(SECTOR))
            entry_lba = struct.unpack_from("<Q", header, 72)[0]
            entry_count = struct.unpack_from("<I", header, 80)[0]
            entry_size = struct.unpack_from("<I", header, 84)[0]
            length = entry_count * entry_size
            stream.seek(entry_lba * SECTOR)
            entries = bytearray(stream.read(length))
            if not any(entries[:16]):
                raise ValueError("first GPT partition entry is empty")
            label = new_name.encode("utf-16le")
            if len(label) > 70:
                raise ValueError("GPT name is too long")
            entries[56:128] = label.ljust(72, b"\0")
            struct.pack_into("<I", header, 88, zlib.crc32(entries) & 0xffffffff)
            header_size = struct.unpack_from("<I", header, 12)[0]
            struct.pack_into("<I", header, 16, 0)
            struct.pack_into("<I", header, 16, zlib.crc32(header[:header_size]) & 0xffffffff)
            yield entry_lba * SECTOR, bytes(entries)
            yield header_lba * SECTOR, bytes(header)

