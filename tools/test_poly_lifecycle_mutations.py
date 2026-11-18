#!/usr/bin/env python3
"""Run installed clear/rotation hooks against stock firmware in Unicorn.

Optional argument is a complete candidate bundle; otherwise overlay the mutation
bundle on v1.12. Includes a rotation mutation control that restores stock code.
"""
import json
import struct
import sys
from pathlib import Path
from fw_sandbox import Sandbox, SENTINEL, STACKTOP
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import *

ROOT = Path(__file__).resolve().parent.parent
TRACKS = (0x20013DEC, 0x200117C8, 0x2000F1A4, 0x2000CB80)
BANK = 0x1000B530
OWNER = 0x1000D740
SIZE = 2176
GUARDS = (UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6,
          UC_ARM_REG_R7, UC_ARM_REG_R8, UC_ARM_REG_R9,
          UC_ARM_REG_R10, UC_ARM_REG_R11)


def bench(slot=1, letter=23, owner=True):
    sb = Sandbox(sys.argv[1] if len(sys.argv) > 1 else ROOT / 'mods/v1-poly-v112.json')
    if len(sys.argv) == 1:
        for p in json.load(open(ROOT / 'mods/poly-lifecycle-mutations.json'))['patches']:
            sb.w(int(p['addr'], 0), bytes.fromhex(p['bytes']))
    sb.w(0x08038370, struct.pack('<4I', *TRACKS))
    for n, t in enumerate(TRACKS):
        sb.w(t + 0x2d, bytes([int(n == 0)]))
        sb.w(t + 0x2e, bytes([letter]))
        sb.w(OWNER + n * 4, struct.pack('<I', letter + 1 if owner else letter))
        sb.w(BANK + n * SIZE, bytes([0x91 + n]) * SIZE)
    pattern = TRACKS[slot] + 0x34 + letter * 0x194
    return sb, pattern, BANK + slot * SIZE


def records(n):
    return [bytes([3, (60, 72)[i] if n == 2 else 40 + i, 90,
                   (64, 76)[i] if n == 2 else 44 + i, 80,
                   (67, 79)[i] if n == 2 else 47 + i, 70]) + bytes([i + 1]) * 10
            for i in range(n)]


def stop_at(sb, addr):
    def stop(u, a, size, data):
        u.emu_stop()
    return sb.uc.hook_add(UC_HOOK_CODE, stop, begin=addr, end=addr)


def test_clear():
    for letter in (0, 20, 21, 22, 23):
        for owner in (True, False):
            sb, p, b = bench(letter=letter, owner=owner)
            before = sb.r(BANK, 4 * SIZE)
            sb.w(p + 8, bytes([60, 100, 7]) * 128)
            sb.call(0x0801A4D0, {UC_ARM_REG_R0: p})
            assert sb.reg(UC_ARM_REG_PC) == SENTINEL
            assert sb.r(p + 8, 384) == bytes([128, 0, 0]) * 128
            assert sb.r(b, SIZE) == (bytes(SIZE) if owner else bytes([0x92]) * SIZE)
            assert sb.r(BANK, SIZE) == before[:SIZE]
            assert sb.r(BANK + 2 * SIZE, 2 * SIZE) == before[2 * SIZE:]
    # Drum is slot 0 per table 0x08038370 and owns no melodic bank.
    for slot in (0,):
        sb, p, b = bench(slot=slot)
        before = sb.r(BANK, 4 * SIZE)
        sb.call(0x0801A4D0, {UC_ARM_REG_R0: p})
        assert sb.r(BANK, 4 * SIZE) == before
    # Mutation control: with stock bytes restored the bank must survive the clear.
    sb, p, b = bench(letter=0)
    sb.w(0x0801A4E6, Sandbox().r(0x0801A4E6, 4))
    sb.w(p + 8, bytes([60, 100, 7]) * 128)
    sb.call(0x0801A4D0, {UC_ARM_REG_R0: p})
    assert sb.r(p + 8, 384) == bytes([128, 0, 0]) * 128, 'stock clear no longer runs'
    assert sb.r(b, SIZE) != bytes(SIZE), 'clear mutation control was not detected'
    print('PASS whole-pattern clear, every late letter, ownership, drum isolation, mutation control')


def test_fill_clear():
    for step in (0, 1, 127):
        for owner in (True, False):
            sb, p, b = bench(owner=owner)
            sb.w(p + 8 + 3 * step, bytes([60, 99, 7]))
            u = sb.uc
            u.reg_write(UC_ARM_REG_R4, p)
            u.reg_write(UC_ARM_REG_R7, step)
            u.reg_write(UC_ARM_REG_R3, p + 3 * step)
            u.reg_write(UC_ARM_REG_R2, 0xffffff80)
            u.reg_write(UC_ARM_REG_SP, STACKTOP)
            keep = {r: u.reg_read(r) for r in GUARDS}
            stop_at(sb, 0x0802F440)
            u.emu_start(0x0802F43B, 0xFFFFFFF0, count=200000)
            assert u.reg_read(UC_ARM_REG_PC) == 0x0802F440
            assert sb.r(p + 8 + 3 * step, 1) == b'\x80'
            assert u.reg_read(UC_ARM_REG_R2) == 0
            assert sb.r(b + 17 * step, 1) == (b'\0' if owner else b'\x92')
            assert sb.r(b + 17 * step + 1, 16) == b'\x92' * 16
            assert {r: u.reg_read(r) for r in GUARDS} == keep
            assert u.reg_read(UC_ARM_REG_SP) == STACKTOP
    # Mutation control: without the hook the step record must survive.
    sb, p, b = bench()
    sb.w(0x0802F43A, Sandbox().r(0x0802F43A, 6))
    sb.w(p + 8, bytes([60, 99, 7]))
    u = sb.uc
    u.reg_write(UC_ARM_REG_R4, p)
    u.reg_write(UC_ARM_REG_R7, 0)
    u.reg_write(UC_ARM_REG_R3, p)
    u.reg_write(UC_ARM_REG_R2, 0xffffff80)
    u.reg_write(UC_ARM_REG_SP, STACKTOP)
    stop_at(sb, 0x0802F440)
    u.emu_start(0x0802F43B, 0xFFFFFFF0, count=200000)
    assert sb.r(p + 8, 1) == b'\x80', 'stock fill loop no longer runs'
    assert sb.r(b, 1) == b'\x92', 'fill mutation control was not detected'
    print('PASS fill clear count, boundary steps, ownership guard, mutation control')


def run_rotation(direction, length, owner=True, mutant=False):
    sb, p, b = bench(owner=owner)
    notes = [60, 72] if length == 2 else [40 + i for i in range(length)]
    native = [bytes([n, 90 + i % 20, i & 7]) for i, n in enumerate(notes)]
    recs = records(length)
    sb.w(p + 8, b''.join(native))
    sb.w(p + 0x188, struct.pack('<HH', length, length))
    sb.w(b, b''.join(recs))
    sb.w(b + length * 17, b'\xDA' * (SIZE - length * 17))
    if mutant:
        sb.w(0x0802A126, Sandbox().r(0x0802A126, 6))
    # Stock rotation acquires once and releases once. No new lock or I/O allowed.
    calls = []
    def external(u, a, size, data):
        assert u.reg_read(UC_ARM_REG_SP) % 8 == 0, hex(a)
        calls.append(a)
        if a == 0x08023320:
            u.reg_write(UC_ARM_REG_R0, TRACKS[1])
        u.reg_write(UC_ARM_REG_PC, u.reg_read(UC_ARM_REG_LR))
    for a in (0x080232A0, 0x080232B0, 0x08023320):
        sb.uc.hook_add(UC_HOOK_CODE, external, begin=a, end=a)
    for r in GUARDS:
        sb.uc.reg_write(r, 0x72000000 + r)
    keep = {r: sb.reg(r) for r in GUARDS}
    sb.call(0x0802A0C8, {UC_ARM_REG_R0: direction})
    assert sb.reg(UC_ARM_REG_PC) == SENTINEL
    assert {r: sb.reg(r) for r in GUARDS} == keep
    assert sb.reg(UC_ARM_REG_SP) == STACKTOP
    assert calls == [0x080232A0, 0x08023320, 0x08023320, 0x080232B0]
    shift = -1 if direction else 1
    want_native = native[shift:] + native[:shift]
    want_recs = recs[shift:] + recs[:shift]
    assert sb.r(p + 8, length * 3) == b''.join(want_native)
    assert sb.r(b + length * 17, SIZE - length * 17) == b'\xDA' * (SIZE - length * 17)
    if not owner:
        assert sb.r(b, length * 17) == b''.join(recs)
    else:
        assert sb.r(b, length * 17) == b''.join(want_recs), 'rotation left stale chord records'


def test_rotation():
    for direction in (0, 1):
        for length in (1, 2, 16, 128):
            run_rotation(direction, length)
        run_rotation(direction, 2, owner=False)
    try:
        run_rotation(0, 2, mutant=True)
    except AssertionError as e:
        assert str(e) == 'rotation left stale chord records', str(e)
    else:
        raise AssertionError('rotation mutation control was not detected')
    print('PASS both rotations, lengths 1/2/16/128, complete records and mutation control')


def test_cave_space():
    patches = json.load(open(ROOT / 'mods/poly-lifecycle-mutations.json'))['patches']
    old = json.load(open(ROOT / 'mods/v1-poly-dub.json'))['patches']
    old += json.load(open(ROOT / 'mods/v1-poly-v112.json'))['patches']
    for p in patches:
        a = int(p['addr'], 0)
        z = a + len(bytes.fromhex(p['bytes']))
        if a < 0x0804B000:
            continue
        assert z <= 0x0804C000
        for q in old:
            b = int(q['addr'], 0)
            y = b + len(bytes.fromhex(q['bytes']))
            assert z <= b or a >= y, (p['addr'], q['addr'])
    print('PASS new mutation caves have no v1.9 or candidate overlaps')


if __name__ == '__main__':
    test_cave_space()
    test_clear()
    test_fill_clear()
    test_rotation()
    print('OK chord mutation lifecycle')
