#!/usr/bin/env python3
"""EDIT-mode chord key lights: OR stored chord notes into the stock LED buffer."""
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from test_poly_module_only import Module, POLY, SIZE  # noqa: E402

FB = 0x20001E74
CAVE = 0x08048A00
BIT_FOR_KEY = [20, 14, 19, 13, 9, 17, 15, 18, 16, 22, 23, 21, 3, 6, 4, 7, 5, 8, 12, 0, 11, 1, 10, 2]


def set_bit(fb, bit):
    fb[bit // 8] |= 1 << (bit % 8)


def has_bit(fb, bit):
    return bool(fb[bit // 8] & (1 << (bit % 8)))


def main():
    m = Module()
    track, letter, step = 1, 0, 0
    m.sb.w(0x2000CADA, bytes([track]))
    parent = m.parents[track]
    m.sb.w(parent + 0x2DF, bytes([step]))
    p = m.pattern(track, letter)
    m.sb.w(p + 8 + step * 3, bytes([60, 90, 0]))
    m.sb.w(POLY + (track - 1) * SIZE + step * 17,
           bytes([3, 60, 90, 64, 90, 67, 90] + [0] * 10))
    fb = bytearray(7)
    set_bit(fb, BIT_FOR_KEY[0])          # stock lights C
    m.sb.w(FB, bytes(fb))
    m.call(CAVE)
    out = m.sb.r(FB, 7)
    for key in (0, 4, 7):                # C, E, G
        assert has_bit(out, BIT_FOR_KEY[key]), (key, out.hex())
    print('PASS edit-mode chord lights C/E/G')
    return 0


if __name__ == '__main__':
    sys.exit(main())
