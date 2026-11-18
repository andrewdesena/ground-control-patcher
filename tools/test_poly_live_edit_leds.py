#!/usr/bin/env python3
"""Exercise live chord entry with stock preview suppression and the installed LED hook."""

from test_poly_edit_entry_held import bench, chord, key
from test_poly_editlights6 import CACHE, LED, apply, frame, render, run, stock_bits

KEYS = set(range(24)) | {31}
MASK = 0x20001E90
PWM = 0x20001D93


def check_frames(bundle, *, fixed):
    for track in (1, 2, 3):
        sb = bench(track=track, letter=2)
        apply(sb, bundle)
        for key_id in (4, 6, 8):
            key(sb, 1, key_id)
            key(sb, 2, key_id)
        assert {note for note, _ in chord(sb)} == {60, 64, 67}
        render(sb)
        bits = stock_bits(sb, (60, 64, 67))
        primary = next(iter(stock_bits(sb, (60,))))
        # Test the display-mode and PWM gates independently.
        sb.w(CACHE + 17, b'\1')
        run(sb, 0x08012C12)
        assert (bits <= frame(sb) & KEYS) == fixed, (track, 'preview mode')
        sb.w(CACHE + 17, b'\2')
        for i in range(6):
            sb.w(MASK + primary // 8, bytes([1 << (primary % 8)]))
            sb.w(PWM, bytes([i]))
            run(sb, 0x08012C12)
            assert (bits <= frame(sb) & KEYS) == (fixed or i == 5), (track, i, sb.r(LED, 7).hex())

        if fixed:
            # A valid-looking foreign record must not light without the native primary.
            sb.w(sb.record, bytes([2, 55, 90, 57, 90]))
            sb.w(MASK + primary // 8, b'\0')
            run(sb, 0x08012C12)
            assert not (stock_bits(sb, (55, 57)) & frame(sb))


if __name__ == '__main__':
    check_frames('v1-poly-v119', fixed=False)
    check_frames('v1-poly-v119-led1', fixed=True)
    check_frames('v1-poly-v120', fixed=True)
    print('PASS live STEP EDIT entry, preview suppression and all PWM phases on tracks 1–3')
