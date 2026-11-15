#!/usr/bin/env python3
"""EDIT-mode chord key lights: OR stored chord notes into the stock LED buffer."""
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


def run_case(track, primary_note, notes, lit_keys):
    m = Module()
    letter, step = 0, 0
    m.sb.w(0x2000CADA, bytes([track]))
    if track <= 3:
        m.sb.w(m.parents[track] + 0x2DF, bytes([step]))
        p = m.pattern(track, letter)
        m.sb.w(p + 8 + step * 3, bytes([primary_note, 90, 0]))
        m.sb.w(POLY + (track - 1) * SIZE + step * 17,
               bytes([len(notes)] + [v for n in notes for v in (n, 90)] + [0] * (16 - 2 * len(notes))))
    fb = bytearray(7)
    for key in lit_keys:
        set_bit(fb, BIT_FOR_KEY[key])
    m.sb.w(FB, bytes(fb))
    m.call(CAVE)
    return m, m.sb.r(FB, 7)


def main():
    _, out = run_case(1, 60, (60, 64, 67), (0,))
    for key in (0, 4, 7):                # C, E, G
        assert has_bit(out, BIT_FOR_KEY[key]), ('C4', key, out.hex())

    _, out = run_case(1, 72, (72, 76, 79), (0,))
    for key in (0, 4, 7):                # same pitch classes one octave up
        assert has_bit(out, BIT_FOR_KEY[key]), ('C5', key, out.hex())

    _, out = run_case(4, 60, (60, 64, 67), (0,))
    assert out == bytes([0] * 2 + [1 << 4] + [0] * 4), ('drum', out.hex())

    _, out = run_case(1, 60, (60, 64, 67), (0, 4))
    assert out == bytes([0, (1 << 1), (1 << 4)] + [0] * 4), ('multi-lit', out.hex())

    print('PASS edit-mode chord lights: C4, C5, drum skip, multi-lit guard')
    return 0


if __name__ == '__main__':
    sys.exit(main())
