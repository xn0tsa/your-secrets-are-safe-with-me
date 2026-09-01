#!/usr/bin/env python3
"""
EK-33: Extraction of the universal AES-256 key hardcoded in FirmwareUpdater.

The binary (distributed in cleartext via bin.zip on the public CDN) keeps its
symbols: the `(anonymous namespace)::kEmbeddedAesKey` symbol points at file
offset 113720 (.rodata section). The same key is the passphrase of the AI
Station OTA image (AES-256-CBC, PBKDF2-HMAC-SHA512, 500,000 iterations).

Verified on a CDN-downloaded binary on 2026-09-01: MATCH.

Usage: python3 extract_aes_key.py [path/to/FirmwareUpdater]
"""
import struct
import sys

EXPECTED = "79e610de213d8966a1e0dde84136ac6072996a828053032e34773951fd080a5e"


def find_symbol_offset(data, name=b"kEmbeddedAesKeyE"):
    """Parse a little-endian ELF64 .symtab to locate the symbol."""
    if data[:4] != b"\x7fELF" or data[4] != 2 or data[5] != 1:
        raise ValueError("not an ELF64 LE")
    e_shoff, = struct.unpack_from("<Q", data, 0x28)
    e_shentsize, e_shnum, e_shstrndx = struct.unpack_from("<HHH", data, 0x3A)
    sections = []
    for i in range(e_shnum):
        off = e_shoff + i * e_shentsize
        sh_name, sh_type, sh_flags, sh_addr, sh_offset, sh_size, sh_link, sh_info, sh_align, sh_entsize = \
            struct.unpack_from("<IIQQQQIIQQ", data, off)
        sections.append(dict(addr=sh_addr, offset=sh_offset, size=sh_size,
                             type=sh_type, link=sh_link, entsize=sh_entsize))
    for s in sections:
        if s["type"] != 2:  # SHT_SYMTAB
            continue
        strtab = sections[s["link"]]
        n = s["size"] // s["entsize"]
        for i in range(n):
            off = s["offset"] + i * s["entsize"]
            st_name, st_info, st_other, st_shndx, st_value, st_size = \
                struct.unpack_from("<IBBHQQ", data, off)
            nm = data[strtab["offset"] + st_name:
                     strtab["offset"] + st_name + 64].split(b"\0")[0]
            if name in nm and st_size == 32:
                # convert virtual addr → file offset
                for sec in sections:
                    if sec["addr"] <= st_value < sec["addr"] + sec["size"] and sec["type"] != 8:
                        return sec["offset"] + (st_value - sec["addr"])
    return None


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "../firmware/104000/extracted/bin/FirmwareUpdater"
    data = open(path, "rb").read()
    off = find_symbol_offset(data) or 113720  # documented fallback offset
    key = data[off:off + 32].hex()
    print(f"kEmbeddedAesKey symbol → file offset {off}")
    print(f"AES-256 key: {key}")
    print("MATCH with the report (P26-C-02/P42-C-02)" if key == EXPECTED else "different key (new version?)")


if __name__ == "__main__":
    main()
