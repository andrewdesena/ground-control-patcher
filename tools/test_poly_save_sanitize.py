#!/usr/bin/env python3
"""Save drops chord records that cannot play.

A record only sounds when the step's note appears among its notes, because the
fan-out matches the played note against the record. A record that does not
contain it is dead weight: the step looks chorded in edit mode, plays as a
single note, and the desync gets written to the card.

Drives the real pattern writer 0x0801C450 with FatFS stubbed, then inspects the
bank that was handed to f_write.
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
WRITER = 0x0801C450
F_OPEN, F_CLOSE = 0x0801496C, 0x08014F18
RET = 0x0801C4A2
SLOT, LETTER = 1, 0
STUBS = (0x080351FC, 0x080150B6, 0x0801536C, 0x0801B560, 0x0801EF68,
         0x08015336, 0x0801EDD4, 0x08014C92, 0x08014B30, 0x080147E0,
         0x080232A0, 0x080232B0)


def run(records, steps, sanitize=True, tail=None):
    """records/steps: {step: ...} maps for the bank and the pattern."""
    sb = Sandbox(ROOT / ('mods/v1-poly-v119.json' if sanitize else 'mods/v1-poly-v115.json'))
    for n, t in enumerate(TRACKS):
        sb.w(t + 0x2D, bytes([int(n == 0)]))
        sb.w(t + 0x2E, bytes([LETTER]))
    block = TRACKS[SLOT] + 0x34 + LETTER * 0x194
    sb.w(block + 4, bytes([1]))
    sb.w(block + 0x188, struct.pack('<HH', 16, 16))
    for step, note in steps.items():
        sb.w(block + 8 + 3 * step, bytes([note, 100 if note != 0x80 else 0, 0]))
    bank = BANK + SLOT * SIZE
    for step, notes in records.items():
        rec = bytearray(17)
        rec[0] = len(notes)
        for k, n in enumerate(notes[:8]):
            rec[1 + 2 * k] = n
            rec[2 + 2 * k] = 90
        sb.w(bank + step * 17, bytes(rec))
    for step, (off, note) in (tail or {}).items():
        sb.w(bank + step * 17 + off, bytes([note]))
    sb.w(0x1000D740 + SLOT * 4, struct.pack('<I', LETTER + 1))

    u = sb.uc

    def on_open(uc, a, s, d):
        uc.reg_write(UC_ARM_REG_R0, 0)
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    def on_stub(uc, a, s, d):
        uc.reg_write(UC_ARM_REG_R0, 0)
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    u.hook_add(UC_HOOK_CODE, on_open, begin=F_OPEN, end=F_OPEN)
    for a in STUBS:
        u.hook_add(UC_HOOK_CODE, on_stub, begin=a, end=a)
    u.hook_add(UC_HOOK_CODE, lambda uc, a, s, d: uc.emu_stop(), begin=RET, end=RET)
    u.reg_write(UC_ARM_REG_SP, STACKTOP)
    u.reg_write(UC_ARM_REG_LR, SENTINEL | 1)
    u.reg_write(UC_ARM_REG_R1, block)
    u.reg_write(UC_ARM_REG_R2, LETTER)
    u.emu_start(WRITER | 1, 0xFFFFFFF0, count=400000)

    # The save cave now writes from a snapshot at 0x1000E500, not the live bank.
    # The live bank is untouched. Read the snapshot buffer when sanitize=True.
    snapshot_addr = 0x1000E500 if sanitize else bank

    def count(step):
        return sb.r(snapshot_addr + step * 17, 1)[0]

    return {s: count(s) for s in range(16)}


def main():
    fails = []

    def check(label, cond, detail=None):
        if cond:
            print(f'  PASS {label}')
        else:
            fails.append(label)
            print(f'  FAIL {label} {detail}')

    steps = {0: 60, 1: 0x80, 2: 38, 3: 0x80}
    records = {0: [60, 64, 67], 1: [50, 53], 2: [50, 53], 3: [38, 41]}
    got = run(records, steps, sanitize=True)
    check('record containing the step note kept', got[0] == 3, got[0])
    check('record on an empty step dropped', got[1] == 0, got[1])
    check('record an octave above the step note dropped', got[2] == 0, got[2])
    check('record on an empty step dropped (2)', got[3] == 0, got[3])

    # a stale byte past the declared count must not rescue an unplayable record
    sb = None
    steps2 = {0: 72}
    got2 = run({0: [60]}, steps2, sanitize=True, tail={0: (3, 72)})
    check('undeclared tail note does not save the record', got2[0] == 0, got2[0])

    # the same inputs without the sanitiser must keep all four, proving the
    # test detects the difference rather than passing by construction
    raw = run(records, steps, sanitize=False)
    check('unsanitised build keeps the dead records', raw[1] != 0 and raw[2] != 0, raw)

    if fails:
        print(f'\nFAIL {len(fails)}: {fails}')
        return 1
    print('\nPASS save writes only records that can play')
    return 0


if __name__ == '__main__':
    sys.exit(main())
