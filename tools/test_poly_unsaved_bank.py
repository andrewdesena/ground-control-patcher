#!/usr/bin/env python3
"""Verify RAM retention and explicit save of inactive notes after real selector calls."""

import struct

from unicorn.arm_const import UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R4

from test_poly_chain_single_file import setup, request, service
from test_poly_v119 import BANK, BUNDLE, SIZE, TRACKS, install_fatfs, neutralize, run, sidecar


def check_switch(bundle, fixed):
    for slot in (1, 2, 3):
        sb, selector = setup(bundle)
        track = TRACKS[slot]
        bank = BANK + slot * SIZE
        a = track + 0x34
        c = a + 2 * 0x194
        chord_a = sidecar(60, 64, 67)
        chord_c = sidecar(62, 65, 69)
        sb.w(a + 4, b'\1\0')
        sb.w(a + 8, bytes([60, 90, 0]))
        sb.w(a + 0x188, struct.pack('<HH', 1, 1))
        sb.w(bank, chord_a)
        files = {}
        install_fatfs(sb, files)

        request(sb, selector, slot, 2)
        service(sb)
        assert sb.r(track + 0x2e, 1) == b'\2'
        assert sb.r(bank, SIZE) == bytes(SIZE)
        assert files == {}, "letter selection wrote to SD"

        # Explicitly save inactive A before going back to it.
        sb.call(0x08030C1C, stop_at=0x08030C32)
        neutralize(sb, 0x0801EDD4)
        run(sb, 0x0801C450, {UC_ARM_REG_R1: a, UC_ARM_REG_R2: 0})
        trailer = files[b'patternA.txt'][-2188:]
        assert (trailer[8:-4] == chord_a) == fixed

        sb.w(c + 4, b'\1\0')
        sb.w(c + 8, bytes([62, 90, 0]))
        sb.w(bank, chord_c)
        request(sb, selector, slot, 0)
        service(sb)
        assert sb.r(track + 0x2e, 1) == b'\0'
        assert sb.r(a + 8, 1) == bytes([60])
        assert sb.r(bank, SIZE) == (chord_a if fixed else bytes(SIZE))

        # A Play press uses the synchronous publisher instead of the chain worker.
        request(sb, selector, slot, 2)
        run(sb, 0x08021528, {UC_ARM_REG_R4: track}, stop=0x0802152C)
        assert sb.r(track + 0x2e, 1) == b'\2'
        assert sb.r(bank, SIZE) == (chord_c if fixed else bytes(SIZE))


if __name__ == '__main__':
    check_switch(BUNDLE.with_name('v1-poly-v120-record.json'), False)
    check_switch(BUNDLE.with_name('v1-poly-v120.json'), True)
    print('PASS unsaved A → C → A, inactive save, and playback-start restore on tracks 1–3')
