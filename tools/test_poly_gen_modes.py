#!/usr/bin/env python3
"""Generator modes 1 and 3 must keep chord records in step with notes.

Mode 3 (0x0802F520) raises a note by 0xc inside the pattern generator. Mode 1
(0x0802F3D0) empties a step. Neither touched the chord record in stock, so mode
3 collapsed a chorded step to mono and mode 1 left a record on an empty step.

Both hooks resolve the track by scanning the block pointer against the four
tracks and 24 letters, so the test also proves the resolver rejects the drum.
"""
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from fw_sandbox import Sandbox, SENTINEL, STACKTOP
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import *

TRACKS = (0x20013DEC, 0x200117C8, 0x2000F1A4, 0x2000CB80)
BANK = 0x1000B530
SIZE = 2176
MODE3 = 0x0802F520
MODE1 = 0x0802F3D0


def bench(slot=1, letter=0):
    sb = Sandbox(ROOT / 'mods/v1-poly-v113.json')
    for p in json.load(open(ROOT / 'mods/poly-gen-modes.json'))['patches']:
        sb.w(int(p['addr'], 0), bytes.fromhex(p['bytes']))
    for n, t in enumerate(TRACKS):
        sb.w(t + 0x2D, bytes([int(n == 0)]))
        sb.w(t + 0x2E, bytes([letter]))
    block = TRACKS[slot] + 0x34 + letter * 0x194
    return sb, block, BANK + slot * SIZE


def call(sb, addr, regs, stop=None):
    u = sb.uc
    u.reg_write(UC_ARM_REG_SP, STACKTOP)
    u.reg_write(UC_ARM_REG_LR, SENTINEL | 1)
    for r, v in regs.items():
        u.reg_write(r, v)
    if stop:
        u.hook_add(UC_HOOK_CODE, lambda uc, a, s, d: uc.emu_stop(), begin=stop, end=stop)
        u.emu_start(addr | 1, 0xFFFFFFF0, count=200000)
    else:
        u.emu_start(addr | 1, SENTINEL, count=200000)


def rec(sb, bank, step):
    r = sb.r(bank + 17 * step, 17)
    return r[0], [r[1 + 2 * i] for i in range(min(r[0], 8))]


def main():
    fails = []

    def check(label, cond, detail=None):
        if cond:
            print(f'  PASS {label}')
        else:
            fails.append(label)
            print(f'  FAIL {label} {detail}')

    # mode 3: a three-note chord moves up an octave with its note
    sb, block, bank = bench()
    step = 3
    sb.w(block + 8 + 3 * step, bytes([60, 100, 0]))
    sb.w(bank + 17 * step, bytes([3, 60, 90, 64, 90, 67, 90]) + bytes(10))
    call(sb, MODE3, {UC_ARM_REG_R4: block,
                     UC_ARM_REG_R5: block + 3 * step,
                     UC_ARM_REG_R7: 60}, stop=0x0802F524)
    check('mode3: note raised by 0xC', sb.r(block + 8 + 3 * step, 1)[0] == 72,
          sb.r(block + 8 + 3 * step, 1)[0])
    got = rec(sb, bank, step)
    check('mode3: record raised by 0xC', got == (3, [72, 76, 79]), got)

    # mode 3: a voice that would leave range is dropped and its tail zeroed
    sb, block, bank = bench()
    sb.w(block + 8 + 3 * step, bytes([112, 100, 0]))
    sb.w(bank + 17 * step, bytes([3, 112, 90, 120, 90, 126, 90]) + bytes(10))
    call(sb, MODE3, {UC_ARM_REG_R4: block,
                     UC_ARM_REG_R5: block + 3 * step,
                     UC_ARM_REG_R7: 112}, stop=0x0802F524)
    got = rec(sb, bank, step)
    check('mode3: only the in-range voice survives', got == (1, [124]), got)
    tail = sb.r(bank + 17 * step + 1 + 2 * got[0], 17 - 1 - 2 * got[0])
    check('mode3: tail zeroed', tail == bytes(len(tail)), tail)

    # a stale voice past the declared count must not be resurrected
    sb, block, bank = bench()
    sb.w(block + 8 + 3 * step, bytes([70, 100, 0]))
    sb.w(bank + 17 * step, bytes([1, 70, 90, 64, 90, 67, 90]) + bytes(10))
    call(sb, MODE3, {UC_ARM_REG_R4: block,
                     UC_ARM_REG_R5: block + 3 * step,
                     UC_ARM_REG_R7: 70}, stop=0x0802F524)
    got = rec(sb, bank, step)
    check('mode3: stale voices not revived', got == (1, [82]), got)

    # mode 1: emptying a step clears its record
    sb, block, bank = bench()
    sb.w(block + 8 + 3 * step, bytes([60, 100, 0]))
    sb.w(bank + 17 * step, bytes([3, 60, 90, 64, 90, 67, 90]) + bytes(10))
    call(sb, MODE1, {UC_ARM_REG_R4: block,
                     UC_ARM_REG_R7: block + 3 * step,
                     UC_ARM_REG_R11: step,
                     UC_ARM_REG_R9: 0x80}, stop=0x0802F3D4)
    check('mode1: step emptied', sb.r(block + 8 + 3 * step, 1)[0] == 0x80,
          sb.r(block + 8 + 3 * step, 1)[0])
    check('mode1: record cleared', rec(sb, bank, step) == (0, []), rec(sb, bank, step))

    # mutation control: with stock bytes restored the record must not move
    sb, block, bank = bench()
    sb.w(MODE3, Sandbox().r(MODE3, 4))
    sb.w(block + 8 + 3 * step, bytes([60, 100, 0]))
    sb.w(bank + 17 * step, bytes([3, 60, 90, 64, 90, 67, 90]) + bytes(10))
    call(sb, MODE3, {UC_ARM_REG_R4: block,
                     UC_ARM_REG_R5: block + 3 * step,
                     UC_ARM_REG_R7: 60}, stop=0x0802F524)
    check('mode3 mutation control: note still raised by stock',
          sb.r(block + 8 + 3 * step, 1)[0] == 72, sb.r(block + 8 + 3 * step, 1)[0])
    check('mode3 mutation control: record left stale',
          rec(sb, bank, step) == (3, [60, 64, 67]), rec(sb, bank, step))

    # drum is excluded by the resolver
    sb, block, bank = bench(slot=0)
    sb.w(block + 8 + 3 * step, bytes([60, 100, 0]))
    sb.w(bank + 17 * step, bytes([3, 60, 90, 64, 90, 67, 90]) + bytes(10))
    call(sb, MODE1, {UC_ARM_REG_R4: block,
                     UC_ARM_REG_R7: block + 3 * step,
                     UC_ARM_REG_R11: step,
                     UC_ARM_REG_R9: 0x80}, stop=0x0802F3D4)
    check('drum: record untouched', rec(sb, bank, step) == (3, [60, 64, 67]),
          rec(sb, bank, step))

    if fails:
        print(f'\nFAIL {len(fails)}: {fails}')
        return 1
    print('\nPASS generator modes keep chord records with their notes')
    return 0


if __name__ == '__main__':
    sys.exit(main())
