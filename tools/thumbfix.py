"""
thumbfix.py — resolve Thumb-2 32-bit branch relocations without a linker.

clang assembles our cave at address 0, so a branch to an absolute address encodes the
wrong offset. We assemble with the section-relative form `_start+(TARGET-base)`, which
leaves one relocation; the immediate gas emits is `target - base - 4` (it pre-subtracts the
4-byte PC bias). The correct PC-relative offset the CPU needs is `target-(instr+4)`, i.e.
`emitted_addend - k` where k is the branch's byte offset in the section. This module decodes
the emitted addend out of the bytes and re-encodes the branch with the true offset.
Handles BL (T4) and B.W (T4). Conditional 4-byte B (T3) is not supported on purpose.
"""
MASK32 = (1 << 32) - 1


def decode_t4(b):
    """b = 4 bytes at the branch. returns (kind, addend) kind in {'bl','bw'}"""
    h1 = int.from_bytes(b[0:2], 'little')
    h2 = int.from_bytes(b[2:4], 'little')
    if (h1 >> 11) != 0b11110:
        return None
    if (h2 >> 14) == 0b11:
        kind = 'bl'
    elif (h2 >> 14) == 0b10:
        kind = 'bw'
    else:
        return None
    s = (h1 >> 10) & 1
    imm10 = h1 & 0x3FF
    j1 = (h2 >> 13) & 1
    j2 = (h2 >> 11) & 1
    imm11 = h2 & 0x7FF
    i1 = 1 - (j1 ^ s)
    i2 = 1 - (j2 ^ s)
    imm = (s << 24) | (i1 << 23) | (i2 << 22) | (imm10 << 12) | (imm11 << 1)
    if imm & (1 << 24):
        imm -= (1 << 25)
    return kind, imm


def encode_t4(kind, offset):
    """offset is the signed branch distance from the instruction address + 4"""
    if offset % 2 or not (-(1 << 24) <= offset < (1 << 24)):
        raise ValueError(f'branch out of range / unaligned: {offset}')
    s = 1 if offset < 0 else 0
    imm = offset & 0x1FFFFFF
    i1 = (imm >> 23) & 1
    i2 = (imm >> 22) & 1
    j1 = (1 - i1) ^ s
    j2 = (1 - i2) ^ s
    imm10 = (imm >> 12) & 0x3FF
    imm11 = (imm >> 1) & 0x7FF
    h1 = 0xF000 | (s << 10) | imm10
    top = 0xD000 if kind == 'bl' else 0x9000
    h2 = top | (j1 << 13) | (j2 << 11) | imm11
    return h1.to_bytes(2, 'little') + h2.to_bytes(2, 'little')


def fix(data, relocs):
    """data: bytearray of the assembled section, relocs: [(offset, symbol)]"""
    for off, sym in relocs:
        chunk = bytes(data[off:off + 4])
        dec = decode_t4(chunk)
        if not dec:
            raise SystemExit(f'unsupported branch encoding at offset 0x{off:x} ({sym})')
        kind, addend = dec
        # gas emitted `target-base-4`; the CPU needs `target-(instr+4)`, i.e. addend - off
        true_offset = addend - off
        data[off:off + 4] = encode_t4(kind, true_offset)
    return data
