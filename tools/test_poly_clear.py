#!/usr/bin/env python3
"""
test_poly_clear.py — rest/clear must zero the step's poly record; note commits must not.

  ./.venv/bin/python tools/test_poly_clear.py
"""
import os, sys, json
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import asm
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UcError
from unicorn.arm_const import *

CAVE = 0x08048400
POLY = 0x1000B530
TRACK = 0x20010000
RESUME = 0x0801F332


def build():
    src = json.load(open(os.path.join(HERE, '..', 'mods', 'poly-clear.source.json')))
    return asm.assemble(src['cave']['asm'], int(src['cave']['addr'], 0))


def run_case(cave, note, label):
    uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
    uc.mem_map(0x08000000, 0x100000)
    uc.mem_map(0x20000000, 0x20000)
    uc.mem_map(0x10000000, 0x10000)
    uc.mem_write(CAVE, cave)
    uc.mem_write(TRACK, b'\x00' * 0x400)
    uc.mem_write(TRACK + 0x2e1, bytes([1]))
    uc.mem_write(TRACK + 0x2df, bytes([4]))
    addr = POLY + 1 * 0x880 + 4 * 17
    uc.mem_write(addr, bytes([2, 60, 90, 64, 80]))
    uc.reg_write(UC_ARM_REG_R0, TRACK)
    uc.reg_write(UC_ARM_REG_R1, note & 0xffffffff)
    uc.reg_write(UC_ARM_REG_LR, RESUME | 1)
    try:
        uc.emu_start(CAVE | 1, RESUME, count=2000)
    except UcError as e:
        print("   UCERR", e, "pc=0x%08X" % uc.reg_read(UC_ARM_REG_PC))
    cnt = uc.mem_read(addr, 1)[0]
    stored = uc.mem_read(TRACK + 0x2f5, 1)[0]
    exp = 0 if note < 0 else 2
    ok = (cnt == exp and stored == (note & 0xff) and uc.reg_read(UC_ARM_REG_PC) == RESUME)
    print(f"  {label:20} note={note:3} count={cnt} stored={stored} {'OK' if ok else 'FAIL exp '+str(exp)}")
    return ok


def main():
    cave = build()
    print(f"poly-clear cave {len(cave)}B @ 0x{CAVE:08X}")
    fails = 0
    fails += not run_case(cave, -1, "rest/clear -> 0")
    fails += not run_case(cave, 60, "note commit -> keep")
    print('PASS' if not fails else f'FAIL ({fails})')
    return 0 if not fails else 1


if __name__ == '__main__':
    sys.exit(main())
