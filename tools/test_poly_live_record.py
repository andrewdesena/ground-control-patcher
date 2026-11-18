#!/usr/bin/env python3
"""Exercise the stock event bus and playback clock consumer with live chord recording."""

import argparse
import struct
from pathlib import Path

from test_poly_v119 import BANK, OWNER, SIZE, TMP, TRACKS, install_fatfs, neutralize, run
from fw_sandbox import Sandbox
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2

RECORDERS = (0x2000C848, 0x2000C754, 0x2000C660)
HOOKS = (0x08021898, 0x080218FA, 0x08021954, 0x08021AAC)
EVENT = TMP + 16
SETTINGS = 0x2001BB38
LETTER = 4
LENGTH = 4


def word(n):
    return struct.pack('<I', n)


def bench(bundle, restore=()):
    sb = Sandbox(bundle)
    if restore:
        stock = Sandbox()
        for address in restore:
            sb.w(address, stock.r(address, 4))
    # Initialize flash-backed SRAM and construct the actual track/recorder objects.
    run(sb, 0x08030C1C, stop=0x08030C32)
    neutralize(sb, 0x080190A6, 0x08023514)
    sb.w(TRACKS[0] + 0x2D, b'\1')
    for slot, recorder in enumerate(RECORDERS, 1):
        track = TRACKS[slot]
        run(sb, 0x08023234, {UC_ARM_REG_R0: track, UC_ARM_REG_R1: slot})
        run(sb, 0x08021F78, {UC_ARM_REG_R0: recorder})
        sb.w(track + 0x2E, bytes([LETTER]))
        sb.w(SETTINGS + 0xB9 + slot, bytes([slot]))
        block = track + 0x34 + 0x194 * LETTER
        sb.w(block + 6, b'\1\1')
        sb.w(block + 8, bytes([128, 0, 0]) * 128)
        sb.w(block + 0x188, struct.pack('<HH', LENGTH, LENGTH))
        sb.w(OWNER + 4 * slot, word(LETTER + 1))
        sb.w(recorder + 0x48, b'\1')
    run(sb, 0x08021FC4)
    sb.w(0x200030DE, b'\1')
    sb.w(0x20003129, b'\1')
    sb.w(0x2000CAD0, b'\2')
    sb.w(TMP, struct.pack('<II', 8, 0))
    return sb


def event(sb, slot, note, velocity=0):
    # Six-byte transformed event as queued by the stock MIDI input path.
    sb.w(EVENT, bytes([0x90 if velocity else 0x80, slot, 1, 0, note, velocity]))
    run(sb, 0x08019D40, {UC_ARM_REG_R0: EVENT})
    run(sb, 0x08019CF0)


def advance(sb, slot, step):
    recorder = RECORDERS[slot - 1]
    for _ in range(300):
        run(sb, 0x08022054, {UC_ARM_REG_R0: TMP})
        if sb.r(recorder + 0x3C, 1) == bytes([step]):
            return
    raise AssertionError(f'track {slot}: clock dispatch never landed on step {step}')


def assert_step(sb, slot, step, primary, pairs):
    block = TRACKS[slot] + 0x34 + 0x194 * LETTER
    bank = BANK + SIZE * slot
    record = sb.r(bank + 17 * step, 17)
    expected = bytes([len(pairs)] + [value for pair in pairs for value in pair]).ljust(17, b'\0')
    assert record == expected, (slot, step, record.hex(), expected.hex())
    native = sb.r(block + 8 + 3 * step, 2)
    assert native == bytes(primary), (slot, step, native.hex(), bytes(primary).hex())


def record(bundle):
    for slot in (1, 2, 3):
        sb = bench(bundle)
        advance(sb, slot, 1)
        for pitch, velocity in [(60, 77), (64, 88), (67, 99)]:
            event(sb, slot, pitch, velocity)
        chord = [(67, 99), (60, 77), (64, 88)]
        assert_step(sb, slot, 1, chord[0], chord)
        advance(sb, slot, 2)
        assert_step(sb, slot, 2, chord[0], chord)
        # A rolled addition lands on the new step. Releasing it restores the
        # remaining held set here because the stock note-off path commits.
        event(sb, slot, 71, 55)
        assert_step(sb, slot, 2, (71, 55), [(71, 55), (60, 77), (64, 88), (67, 99)])
        event(sb, slot, 71)
        assert_step(sb, slot, 2, chord[0], chord)
        event(sb, slot, 71, 42)
        assert_step(sb, slot, 2, (71, 42), [(71, 42), (60, 77), (64, 88), (67, 99)])
        for pitch in (60, 64, 67, 71):
            event(sb, slot, pitch)
        advance(sb, slot, 3)
        assert_step(sb, slot, 3, (128, 0), [])
        advance(sb, slot, 0)
        assert_step(sb, slot, 0, (128, 0), [])
        advance(sb, slot, 1)
        event(sb, slot, 50, 53)
        assert_step(sb, slot, 1, (50, 53), [(50, 53)])
        for pitch in range(51, 61):
            event(sb, slot, pitch, pitch + 1)
        assert_step(sb, slot, 1, (60, 61), [(60, 61)] + [(n, n + 1) for n in range(51, 58)])
        for other in set(range(4)) - {slot}:
            assert sb.r(BANK + SIZE * other, SIZE) == bytes(SIZE)
    print('PASS transform-bus input and clock dispatch record, carry, release, wrap and overdub on tracks 1–3')


def transport_and_arm(bundle):
    sb = bench(bundle)
    advance(sb, 1, 1)
    sb.w(0x2000CAD0, b'\0')
    event(sb, 1, 55, 80)
    assert_step(sb, 1, 1, (128, 0), [])
    sb.w(0x2000CAD0, b'\2')
    sb.w(0x200030DE, b'\0')
    event(sb, 1, 55, 80)
    assert_step(sb, 1, 1, (128, 0), [])
    sb.w(0x200030DE, b'\1')
    # Let the stock write window close before receiving the next chord.
    for _ in range(96):
        if sb.r(RECORDERS[0] + 0x68, 1) == b'\0':
            break
        run(sb, 0x08022054, {UC_ARM_REG_R0: TMP})
    else:
        raise AssertionError('track 1 write window stayed open')
    event(sb, 1, 55, 80)
    event(sb, 1, 58, 90)
    assert_step(sb, 1, 1, (128, 0), [])
    advance(sb, 1, 2)
    assert_step(sb, 1, 2, (58, 90), [(58, 90), (55, 80)])
    print('PASS stock arm and transport gates, with pending notes assigned to the next write window')


def mutations(bundle):
    for hook in HOOKS:
        sb = bench(bundle, restore=(hook,))
        advance(sb, 1, 1)
        if hook == 0x08021898:
            # Stock takes the other note-on branch in this per-track mode.
            held_manager = int.from_bytes(sb.r(0x20000454, 4), 'little')
            sb.w(held_manager + 0x2DB, b'\1')
        event(sb, 1, 60, 79)
        event(sb, 1, 64, 91)
        if hook == 0x08021954:
            event(sb, 1, 64)
            native, stale = (60, 79), [(64, 91), (60, 79)]
        elif hook == 0x08021AAC:
            advance(sb, 1, 2)
            assert_step(sb, 1, 2, (64, 91), [])
            continue
        else:
            native, stale = (64, 91), []
        assert_step(sb, 1, 1, native, stale)
    print('PASS restoring each of the four installed calls independently removes its capture')


def clock_ingress(bundle):
    for external in (False, True):
        sb = bench(bundle)
        if external:
            sb.w(0x20003128, bytes([2, 2]))
            sb.w(EVENT, bytes([0xF8, 0, 3, 0xFF, 0, 0]))
            # Feed an initial DIN clock message to the stock realtime subscriber.
            run(sb, 0x080197A0, {UC_ARM_REG_R1: EVENT})
        for target in (1, 2):
            for timer_interrupt in range(2500):
                if external and timer_interrupt % 208 == 0:
                    run(sb, 0x080197A0, {UC_ARM_REG_R1: EVENT})
                run(sb, 0x08011258)
                run(sb, 0x08019580, {UC_ARM_REG_R0: TMP})
                if sb.reg(UC_ARM_REG_R0):
                    run(sb, 0x08022054, {UC_ARM_REG_R0: TMP})
                if sb.r(RECORDERS[0] + 0x3C, 1) == bytes([target]):
                    break
            else:
                raise AssertionError(f'clock ingress failed on step {target}, external={external}')
            if target == 1:
                # The stock DIN note decoder calls the transformed input path.
                for pitch, velocity in ((60, 77), (67, 99)):
                    sb.w(EVENT + 8, bytes([3, 0, pitch, velocity]))
                    run(sb, 0x200015EC, {UC_ARM_REG_R0: EVENT + 8, UC_ARM_REG_R1: 0x91})
                    run(sb, 0x08019CF0)
            assert_step(sb, 1, target, (67, 99), [(67, 99), (60, 77)])
    print('PASS internal timer and external DIN F8 ingress drive live chord recording')


def roundtrip(bundle):
    sb = bench(bundle)
    advance(sb, 1, 1)
    event(sb, 1, 60, 77)
    event(sb, 1, 67, 99)
    block = TRACKS[1] + 0x34 + 0x194 * LETTER
    files = {}
    neutralize(sb, 0x080232A0, 0x080232B0, 0x0801EDD4)
    opened = install_fatfs(sb, files)
    run(sb, 0x0801C450, {UC_ARM_REG_R1: block, UC_ARM_REG_R2: LETTER})
    assert opened == [b'patternE.txt']
    reloaded = bench(bundle)
    neutralize(reloaded, 0x080232A0, 0x080232B0)
    install_fatfs(reloaded, files)
    run(reloaded, 0x0801CCC4, {UC_ARM_REG_R0: block, UC_ARM_REG_R1: LETTER, UC_ARM_REG_R2: 0})
    assert_step(reloaded, 1, 1, (67, 99), [(67, 99), (60, 77)])
    print('PASS recorded chord persists through the native single-file save and reload')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle', type=Path)
    arguments = parser.parse_args()
    record(arguments.bundle)
    transport_and_arm(arguments.bundle)
    mutations(arguments.bundle)
    clock_ingress(arguments.bundle)
    roundtrip(arguments.bundle)
