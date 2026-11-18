#!/usr/bin/env python3
"""Toggle chord entry: pressing a note already in the record removes it.

Wrapper in front of the proven entry cave. Removal cases are asserted exactly.
Pass-through cases assert that the existing cave ran (it rewrites the step's
note), because with no input state its record behaviour is a single note.
"""
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from fw_sandbox import Sandbox, SENTINEL, STACKTOP
from unicorn.arm_const import *

TRACKS = (0x20013DEC, 0x200117C8, 0x2000F1A4, 0x2000CB80)
BANK = 0x1000B530
WRAP = 0x0804B500
STEP = 4


def bench(slot=1, letter=0, rec=None, step_note=60):
    sb = Sandbox(ROOT / 'mods/v1-poly-v119.json')
    for n, t in enumerate(TRACKS):
        sb.w(t + 0x2D, bytes([int(n == 0)]))
        sb.w(t + 0x2E, bytes([letter]))
    block = TRACKS[slot] + 0x34 + letter * 0x194
    sb.w(block + 8 + 3 * STEP, bytes([step_note, 100, 0]))
    bank = BANK + slot * 0x880
    if rec is not None:
        b = bytearray(17)
        b[0] = len(rec)
        for i, note in enumerate(rec[:8]):
            b[1 + 2 * i] = note
            b[2 + 2 * i] = 90
        sb.w(bank + STEP * 17, bytes(b))
    sb.w(0x1000D740 + slot * 4, struct.pack("<I", letter + 1))
    sb.w(0x2001C234, b"\1")
    sb.w(0x2001C238, struct.pack("<II", block, TRACKS[slot]))
    sb.w(0x20018000, bytes([0, 0, 0]))
    return sb, block, bank


def press(sb, block, note, velocity=100):
    rec = 0x20018000
    sb.w(rec, bytes([note, velocity, 0]))
    u = sb.uc
    u.reg_write(UC_ARM_REG_SP, STACKTOP)
    u.reg_write(UC_ARM_REG_LR, SENTINEL | 1)
    u.reg_write(UC_ARM_REG_R0, block)
    u.reg_write(UC_ARM_REG_R1, STEP)
    u.reg_write(UC_ARM_REG_R2, rec)
    u.emu_start(0x080275C1, 0x080275C4, count=300000)
    assert u.reg_read(UC_ARM_REG_PC) == 0x080275C4


def state(sb, block, bank):
    r = sb.r(bank + STEP * 17, 17)
    count = r[0]
    notes = [r[1 + 2 * i] for i in range(min(count, 8))]
    return count, notes, sb.r(block + 8 + 3 * STEP, 1)[0]


def main():
    fails = []

    def check(label, cond, detail=None):
        if cond:
            print(f'  PASS {label}')
        else:
            fails.append(label)
            print(f'  FAIL {label} {detail}')

    # remove a middle note
    sb, block, bank = bench(rec=[60, 64, 67])
    press(sb, block, 64)
    got = state(sb, block, bank)
    check('remove middle: two notes left', got[0] == 2 and got[1] == [60, 67], got)
    check('remove middle: primary unchanged', got[2] == 60, got[2])

    # remove the primary: the next lowest takes over
    sb, block, bank = bench(rec=[60, 64, 67])
    press(sb, block, 60)
    got = state(sb, block, bank)
    check('remove primary: notes', got[0] == 2 and got[1] == [64, 67], got)
    check('remove primary: new primary is the lowest', got[2] == 64, got[2])

    # BUG B: 0x80 with velocity=0 clears all (Rest/clear button)
    sb, block, bank = bench(rec=[60, 64, 67])
    press(sb, block, 0x80, velocity=0)
    got = state(sb, block, bank)
    check('0x80 vel=0 clears all', got[0] == 0, got)
    check('0x80 vel=0 step is rest', got[2] == 0x80, got[2])

    # 0x80 with velocity>0 removes just the primary (root note re-press)
    sb, block, bank = bench(rec=[60, 64, 67])
    press(sb, block, 0x80, velocity=100)
    got = state(sb, block, bank)
    check('0x80 vel>0 removes primary', got[0] == 2 and got[1] == [64, 67], got)
    check('0x80 vel>0 new primary', got[2] == 64, got[2])

    # remove the last note: step becomes a rest
    sb, block, bank = bench(rec=[60])
    press(sb, block, 60)
    got = state(sb, block, bank)
    check('remove last: record empty', got[0] == 0, got)
    check('remove last: step is a rest', got[2] == 0x80, got[2])

    # tail is zeroed after a removal
    sb, block, bank = bench(rec=[60, 64, 67])
    press(sb, block, 64)
    tail = sb.r(bank + STEP * 17 + 5, 12)
    check('tail zeroed after removal', tail == bytes(12), tail)

    # BUG A: a new note must preserve the existing chord, not destroy it
    sb, block, bank = bench(rec=[60, 64])
    press(sb, block, 70)
    got = state(sb, block, bank)
    check('new note preserves old notes', got[0] >= 3 and 60 in got[1] and 64 in got[1] and 70 in got[1], got)
    check('new note: primary is lowest', got[2] == min(got[1]), got)

    # a step with no record falls through too
    sb, block, bank = bench(rec=None, step_note=0x80)
    press(sb, block, 55)
    got = state(sb, block, bank)
    check('empty step reaches the existing cave', got[2] == 55, got[2])

    # drum is passed through: the record is untouched
    sb, block, bank = bench(slot=0, rec=[60, 64])
    press(sb, block, 60)
    check('drum: record untouched', state(sb, block, bank)[0] == 2, state(sb, block, bank))

    # a full record must refuse the press, not drop the chord to one note
    sb, block, bank = bench(rec=[60, 62, 64, 65, 67, 69, 71, 72])
    press(sb, block, 73)
    got = state(sb, block, bank)
    check('full record: ninth note not stored', got[0] == 8, got)
    check('full record: chord unchanged', got[1] == [60, 62, 64, 65, 67, 69, 71, 72], got)
    check('full record: primary not moved to the refused note', got[2] != 73, got[2])

    # mutation control: with stock bytes the press adds instead of removing
    sb, block, bank = bench(rec=[60, 64, 67])
    mov = 0x08049C00            # the entry cave itself, bypassing the wrapper
    u = sb.uc
    u.reg_write(UC_ARM_REG_SP, STACKTOP)
    u.reg_write(UC_ARM_REG_LR, SENTINEL | 1)
    u.reg_write(UC_ARM_REG_R0, block)
    u.reg_write(UC_ARM_REG_R1, STEP)
    u.reg_write(UC_ARM_REG_R2, 0x20018000)
    u.emu_start(mov | 1, SENTINEL, count=300000)
    got = state(sb, block, bank)
    check('mutation control: entry cave alone does not remove', got[0] == 3, got)

    if fails:
        print(f'\nFAIL {len(fails)}: {fails}')
        return 1
    print('\nPASS toggle entry removes, falls through, and skips the drum')
    return 0


if __name__ == '__main__':
    sys.exit(main())
