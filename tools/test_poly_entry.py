#!/usr/bin/env python3
"""
test_poly_entry.py — unit-test the hardware-entry chord append cave.

Calls the cave with a synthetic track struct (track index at +0x2E1, current step at +0x2DF,
held-note count at +0x120) and a note-on event (note at +4, velocity at +5). Verifies:
  * a new note is appended to 0x1000B530 + track*0x880 + step*17
  * an existing note updates velocity without duplicating
  * the per-step cap (8) is enforced
  * the track offset is correct for track 2
  * r6 is restored to the original ldrb (track+0x120)

  ./.venv/bin/python tools/test_poly_entry.py
"""
import os, sys, json
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import asm
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UcError
from unicorn.arm_const import *

CAVE = 0x08048000
POLY = 0x1000B530
TRACK, EVENT, SP = 0x20010000, 0x20011000, 0x2001F000
RET = 0x2001FFF1


def build():
    src = json.load(open(os.path.join(HERE, '..', 'mods', 'poly-entry.source.json')))
    return asm.assemble(src['cave']['asm'], int(src['cave']['addr'], 0))


def run_case(cave, track, step, note, vel, seeded, label, held=3):
    uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
    uc.mem_map(0x08000000, 0x100000)
    uc.mem_map(0x20000000, 0x20000)
    uc.mem_map(0x10000000, 0x10000)
    uc.mem_write(CAVE, cave)
    uc.mem_write(TRACK, b'\x00' * 0x400)
    uc.mem_write(TRACK + 0x2e1, bytes([track]))
    uc.mem_write(TRACK + 0x2df, bytes([step]))
    uc.mem_write(TRACK + 0x120, bytes([held]))
    uc.mem_write(EVENT, bytes([0x90, 0, 0, 0, note & 0x7f, vel & 0x7f]))
    addr = POLY + track * 0x880 + step * 17
    uc.mem_write(addr, bytes([len(seeded)]))
    for i, (n, v) in enumerate(seeded):
        uc.mem_write(addr + 1 + i * 2, bytes([n, v]))
    uc.reg_write(UC_ARM_REG_R4, TRACK)
    uc.reg_write(UC_ARM_REG_R5, EVENT)
    uc.reg_write(UC_ARM_REG_SP, SP)
    uc.reg_write(UC_ARM_REG_LR, RET | 1)
    try:
        uc.emu_start(CAVE | 1, RET & ~1, count=5000)
    except UcError as e:
        print("   UCERR", e, "pc=0x%08X" % uc.reg_read(UC_ARM_REG_PC))
    c = uc.mem_read(addr, 1)[0]
    got = [(uc.mem_read(addr + 1 + i * 2, 1)[0], uc.mem_read(addr + 2 + i * 2, 1)[0]) for i in range(c)]
    r6 = uc.reg_read(UC_ARM_REG_R6)
    exp = list(seeded)
    if any(n == note for n, _ in exp):
        exp = [(n, vel if n == note else v) for n, v in exp]
    elif len(exp) < 8:
        exp = exp + [(note, vel)]
    ok = (got == exp and r6 == held)
    print(f"  {label:26} seeded={seeded} note={note},{vel} -> {got} r6={r6} {'OK' if ok else 'FAIL exp '+str(exp)}")
    return ok


def main():
    cave = build()
    print(f"poly-entry cave {len(cave)}B @ 0x{CAVE:08X}")
    fails = 0
    fails += not run_case(cave, 0, 0, 60, 100, [], "empty -> add")
    fails += not run_case(cave, 0, 0, 60, 80, [(60, 100)], "duplicate -> velocity")
    fails += not run_case(cave, 0, 0, 64, 90, [(60, 100)], "second note -> chord")
    fails += not run_case(cave, 0, 3, 67, 70, [(i + 40, 10) for i in range(8)], "cap 8 -> no add")
    fails += not run_case(cave, 2, 5, 72, 120, [], "track2 step5 offset")
    print('PASS' if not fails else f'FAIL ({fails})')
    return 0 if not fails else 1


if __name__ == '__main__':
    sys.exit(main())
