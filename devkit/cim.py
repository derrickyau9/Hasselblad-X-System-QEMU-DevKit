"""Local VHABCIM container reader, adapted from the existing CIM research tools."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import struct
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


PUBLIC_HEADER_SIZE = 0x80
PRIVATE_HEADER_SIZE = 0x180
ITEM_HEADER_SIZE = 0x100

MARKER_PLAINTEXT = 0x0EFC59FB
MARKER_ENCRYPTED = 0x41886A34

CIM_AES128_KEY = bytes.fromhex("93f82ca244ab29e0366934d56713eea2")
CIM_AES_CHUNK_SIZE = 0x1000
ZERO_IV = bytes(16)

KNOWN_COMPONENT_FIRST_BLOCKS = {
    "hbl-upgrade": b"#!/system/bin/sh",
    "hbl-post-upgrade": b"#!/system/bin/sh",
    "region-script": b"\n\nset_region() {",
    "hbmanual.img": bytes.fromhex("eb3c906d6b66732e6661740002040100"),
}


def entropy(data: bytes) -> float:
    if not data:
        return 0.0
    counts = [0] * 256
    for value in data:
        counts[value] += 1
    size = len(data)
    return -sum((n / size) * math.log2(n / size) for n in counts if n)


def cstr(raw: bytes) -> str:
    value = raw.split(b"\0", 1)[0].rstrip(b"\r\n")
    return value.decode("ascii", "replace")


def safe_name(name: str, fallback: str) -> str:
    name = name.strip().replace("\\", "_").replace("/", "_")
    name = re.sub(r"[^A-Za-z0-9._+-]+", "_", name)
    return name or fallback


def parse_public_header(raw: bytes) -> dict[str, Any]:
    if len(raw) < PUBLIC_HEADER_SIZE or not raw.startswith(b"VHABCIM\r\n"):
        raise ValueError("not a VHABCIM container")

    header = raw[:PUBLIC_HEADER_SIZE]
    parts = header.split(b"\r\n", 4)
    marker = struct.unpack_from(">I", header, 0x40)[0]
    stored_size = struct.unpack_from(">I", header, 0x44)[0]
    return {
        "magic": parts[0].decode("ascii", "replace"),
        "product": parts[1].decode("ascii", "replace") if len(parts) > 1 else "",
        "format_version": parts[2].rstrip(b"\0").decode("ascii", "replace") if len(parts) > 2 else "",
        "build_date": parts[3].decode("ascii", "replace") if len(parts) > 3 else "",
        "build_time": parts[4][:8].decode("ascii", "replace") if len(parts) > 4 else "",
        "flags_be": struct.unpack_from(">I", header, 0x3C)[0],
        "encryption_marker_be": marker,
        "encrypted": marker == MARKER_ENCRYPTED,
        "stored_file_size_be": stored_size,
        "actual_file_size": len(raw),
        "size_matches": stored_size == len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def align_up(value: int, alignment: int) -> int:
    return (value + alignment - 1) // alignment * alignment


def decrypt_aes128_cbc_chunked(data: bytes, iv: bytes) -> bytes:
    if len(data) % 16:
        raise ValueError("encrypted data is not AES block aligned")

    out = bytearray()
    for off in range(0, len(data), CIM_AES_CHUNK_SIZE):
        chunk = data[off : off + CIM_AES_CHUNK_SIZE]
        decryptor = Cipher(algorithms.AES(CIM_AES128_KEY), modes.CBC(iv)).decryptor()
        out.extend(decryptor.update(chunk) + decryptor.finalize())
    return bytes(out)


def xor_bytes(a: bytes, b: bytes) -> bytes:
    return bytes(x ^ y for x, y in zip(a, b))


def parse_iv(value: str | None) -> bytes | None:
    if not value:
        return None
    iv = bytes.fromhex(value.replace(":", "").replace(" ", ""))
    if len(iv) != 16:
        raise ValueError("--iv-hex must decode to exactly 16 bytes")
    return iv


def marker_from(raw: bytes) -> int:
    if len(raw) < PUBLIC_HEADER_SIZE:
        raise ValueError("file too small for public header")
    return struct.unpack_from(">I", raw, 0x40)[0]


def is_encrypted(raw: bytes) -> bool:
    marker = marker_from(raw)
    if marker == MARKER_PLAINTEXT:
        return False
    if marker == MARKER_ENCRYPTED:
        return True
    raise ValueError(f"unknown encryption marker 0x{marker:08x}")


def decrypt_private_area(raw: bytes, iv: bytes = ZERO_IV) -> bytes:
    payload = raw[PUBLIC_HEADER_SIZE:]
    marker = struct.unpack_from(">I", raw, 0x40)[0]
    if marker == MARKER_PLAINTEXT:
        return payload
    if marker != MARKER_ENCRYPTED:
        raise ValueError(f"unknown encryption marker 0x{marker:08x}")

    probe_len = min(len(payload), CIM_AES_CHUNK_SIZE)
    probe_len = align_up(probe_len, 16)
    if probe_len > len(payload):
        raise ValueError("encrypted payload too short for private header probe")
    probe = decrypt_aes128_cbc_chunked(payload[:probe_len], iv)
    if len(probe) < PRIVATE_HEADER_SIZE:
        raise ValueError("payload too short for private header")

    item_count = struct.unpack_from(">I", probe, 0x3C)[0]
    private_area_len = PRIVATE_HEADER_SIZE + item_count * ITEM_HEADER_SIZE
    encrypted_len = align_up(private_area_len, 16)
    if encrypted_len > len(payload):
        raise ValueError("private/item-header area points outside payload")
    return decrypt_aes128_cbc_chunked(payload[:encrypted_len], iv)[:private_area_len]


def derive_iv_from_items(raw: bytes, items: list[dict[str, Any]]) -> bytes:
    legacy_linux = parse_public_header(raw)['product'] == '1601254_PVF'
    for item in items:
        known = KNOWN_COMPONENT_FIRST_BLOCKS.get(item["name"])
        if legacy_linux and item['name'] == 'hbl-upgrade':
            known = b'#!/bin/sh\n\nKERNE'
        if not known:
            continue
        start = item["offset_in_cim"]
        if start < PUBLIC_HEADER_SIZE or start + 16 > len(raw):
            continue
        intermediate = decrypt_aes128_cbc_chunked(raw[start : start + 16], ZERO_IV)
        return xor_bytes(intermediate, known)
    raise ValueError(
        "could not auto-derive AES-CBC IV; pass --iv-hex or add a known first block for one component"
    )


def decrypt_component(raw: bytes, item: dict[str, Any], iv: bytes) -> bytes:
    start = item["offset_in_cim"]
    length = item["length"]
    if start < PUBLIC_HEADER_SIZE or start >= len(raw):
        raise ValueError(f"item {item['index']} points outside CIM file: {item}")
    encrypted_len = align_up(length, 16)
    end = start + encrypted_len
    if end > len(raw):
        raise ValueError(f"item {item['index']} encrypted data is truncated: {item}")
    return decrypt_aes128_cbc_chunked(raw[start:end], iv)[:length]


def parse_private_and_items(payload_plain: bytes) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if len(payload_plain) < PRIVATE_HEADER_SIZE:
        raise ValueError("payload too short for private header")

    private = payload_plain[:PRIVATE_HEADER_SIZE]
    item_count = struct.unpack_from(">I", private, 0x3C)[0]
    private_info = {
        "private_header_size": PRIVATE_HEADER_SIZE,
        "item_header_size": ITEM_HEADER_SIZE,
        "item_count": item_count,
        "generated_by": cstr(private[0x2C:0x3C]),
        "generation_epoch_be": struct.unpack_from(">I", private, 0x28)[0],
        "raw_identifier_hex": private[:0x20].hex(),
        "decrypted_private_area_sha256": hashlib.sha256(payload_plain).hexdigest(),
        "decrypted_private_area_entropy_bits_per_byte": round(entropy(payload_plain), 6),
    }

    items: list[dict[str, Any]] = []
    item_table_off = PRIVATE_HEADER_SIZE
    for index in range(item_count):
        off = item_table_off + index * ITEM_HEADER_SIZE
        header = payload_plain[off : off + ITEM_HEADER_SIZE]
        if len(header) != ITEM_HEADER_SIZE:
            raise ValueError(f"truncated item header {index}")
        file_offset = struct.unpack_from(">Q", header, 0x20)[0]
        length = struct.unpack_from(">I", header, 0x28)[0]
        checksum = header[0x2C:0x3C].hex()
        name = cstr(header[0x60:0xA0])
        items.append(
            {
                "index": index,
                "name": name,
                "offset_in_cim": file_offset,
                "offset_in_cim_hex": f"0x{file_offset:x}",
                "offset_in_decrypted_payload": file_offset - PUBLIC_HEADER_SIZE,
                "length": length,
                "length_hex": f"0x{length:x}",
                "checksum_16_hex": checksum,
            }
        )
    return private_info, items


def load_container(raw: bytes, explicit_iv: bytes | None = None) -> tuple[dict[str, Any], bool, bytes | None, dict[str, Any], list[dict[str, Any]]]:
    public = parse_public_header(raw)
    encrypted = is_encrypted(raw)
    iv: bytes | None = None

    if encrypted:
        # The item table is after the first CBC block, so it parses correctly
        # even with a throwaway IV. Use it to locate a known component and
        # recover the real package IV, then re-read the private area cleanly.
        provisional_private_area = decrypt_private_area(raw, ZERO_IV)
        _, provisional_items = parse_private_and_items(provisional_private_area)
        iv = explicit_iv or derive_iv_from_items(raw, provisional_items)
        private_area_plain = decrypt_private_area(raw, iv)
    else:
        private_area_plain = decrypt_private_area(raw, ZERO_IV)

    private, items = parse_private_and_items(private_area_plain)
    return public, encrypted, iv, private, items

