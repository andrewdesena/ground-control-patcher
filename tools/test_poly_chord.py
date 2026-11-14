#!/usr/bin/env python3
"""
test_poly_chord.py — unit-test the step-record "hold-to-chord" cave.

The cave replaces strb.w r3,[r4,#0x2df] at 0x0801FE2A, which stock reaches with
r3 = current step + 1. It must keep the step unchanged, add the held note via
0x0801F14C, and resume at 0x0801FDBE.

  ./.venv/bin/python tools/test_poly_chord.py
"""
import os, sys, json
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import asm
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_HOOK_CODE, UcError
from unicorn.arm_const import *

CAVE = 0x08048200
F_ADD = 0x0801F14C
RESUME = 0x0801FDBE
TRACK, EVENT = 0x20010000, 0x20011000


def build():
    src = json.load(open(os.path.join(HERE, '..', 'mods', 'poly-chord.source.json')))
    return asm.assemble(src['cave']['asm'], int(src['cave']['addr'], 0))


def run_case(cave, step):
    uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
    uc.mem_map(0x08000000, 0x100000)
    uc.mem_map(0x20000000, 0x20000)
    uc.mem_write(CAVE, cave)
    uc.mem_write(F_ADD, bytes.fromhex('7047'))  # bx lr
    uc.mem_write(TRACK, b'\x00' * 0x400)
    uc.mem_write(TRACK + 0x2df, bytes([step]))
    uc.mem_write(EVENT, bytes([0x90, 0, 0, 0, 64, 100]))
    log = {'add': 0, 'resume': False}

    def hook(u, addr, size, _):
        if addr == F_ADD:
            log['add'] += 1
        elif addr == RESUME:
            log['resume'] = True
    uc.hook_add(UC_HOOK_CODE, hook)
    uc.reg_write(UC_ARM_REG_R3, (step + 1) & 0xffffffff)  # stock already incremented
    uc.reg_write(UC_ARM_REG_R4, TRACK)
    uc.reg_write(UC_ARM_REG_R5, EVENT)
    try:
        uc.emu_start(CAVE | 1, RESUME, count=2000)
    except UcError as e:
        print("   UCERR", e, "pc=0x%08X" % uc.reg_read(UC_ARM_REG_PC))
    now = uc.mem_read(TRACK + 0x2df, 1)[0]
    pc = uc.reg_read(UC_ARM_REG_PC)
    ok = (now == step and log['add'] == 1 and pc == RESUME)
    print(f"  step {step}: after={now} add_calls={log['add']} pc=0x{pc:08X} {'OK' if ok else 'FAIL'}")
    return ok


def main():
    cave = build()
    print(f"poly-chord cave {len(cave)}B @ 0x{CAVE:08X}")
    fails = 0
    for step in (0, 5, 15):
        fails += not run_case(cave, step)
    print('PASS' if not fails else f'FAIL ({fails})')
    return 0 if not fails else 1


if __name__ == '__main__':
    sys.exit(main())
