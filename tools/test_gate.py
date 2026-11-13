#!/usr/bin/env python3
"""
test_gate.py — unit-test the stock-gate wrapper (poly-gate).

Stubs the emitter body (0x802174C = bx lr) and checks the wrapper calls 0x8021748 (its `bl`) once
per poly note EXCEPT the primary, passing the SAME gate (r3) and time (r1) as the primary call,
with the correct temp step-record note. That is what "stock-accurate gate" requires: extras go
through the real emitter with the primary's timing/gate rather than a fixed duration.

  ./.venv/bin/python tools/test_gate.py
"""
import os, sys, json
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import asm
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_HOOK_CODE, UcError
from unicorn.arm_const import *

CAVE = 0x08047A00
BL = 0x08047A86            # the wrapper's `bl 0x8021748` inside the cave
BODY_STUB = 0x0802174C
POLY = 0x1000B530
OBJ, PAR, HAND, STEPR = 0x20010000, 0x20011000, 0x20012000, 0x20013000


def build():
    src = json.load(open(os.path.join(HERE, '..', 'mods', 'poly-gate.source.json')))
    return (asm.assemble(src['cave']['asm'], int(src['cave']['addr'], 0)),
            asm.assemble(src['patches'][0]['asm'], int(src['patches'][0]['addr'], 0)),
            int(src['patches'][0]['addr'], 0))


def run_case(cave, patch, pa, notes, primary, channel, step, gate, label):
    uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
    import unicorn.arm_const as A
    try: uc.ctl_set_cpu_model(A.UC_CPU_ARM_CORTEX_M7)
    except Exception: pass
    uc.mem_map(0x08000000, 0x100000)
    uc.mem_map(0x20000000, 0x20000)
    uc.mem_map(0x10000000, 0x10000)
    uc.mem_write(CAVE, cave)
    uc.mem_write(pa, patch)
    uc.mem_write(BODY_STUB, bytes([0x70, 0x47]))     # body -> bx lr (return immediately)
    uc.mem_write(OBJ, b'\x00' * 0x100); uc.mem_write(PAR, b'\x00' * 0x40)
    uc.mem_write(OBJ + 8, PAR.to_bytes(4, 'little'))
    uc.mem_write(OBJ + 0x40, HAND.to_bytes(4, 'little'))
    uc.mem_write(OBJ + 0x3c, bytes([step]))
    uc.mem_write(PAR + 0x1f, bytes([channel]))
    uc.mem_write(0x1000FE00, b'\x00' * 0x40)
    uc.mem_write(STEPR, bytes([primary & 0xFF, 100, 0]))
    track = channel - 1
    addr = POLY + track * 0x880 + step * 17
    buf = bytes([len(notes)])
    for n, v in notes:
        buf += bytes([n, v])
    uc.mem_write(addr, buf)
    calls = []
    def hc(u, a, s, _):
        if a == BL:
            t = u.reg_read(UC_ARM_REG_R2)
            note = u.mem_read(t, 1)[0]
            calls.append((note, u.reg_read(UC_ARM_REG_R3), u.reg_read(UC_ARM_REG_R1)))
    uc.hook_add(UC_HOOK_CODE, hc)
    uc.reg_write(UC_ARM_REG_R0, OBJ); uc.reg_write(UC_ARM_REG_R1, 777)
    uc.reg_write(UC_ARM_REG_R2, STEPR); uc.reg_write(UC_ARM_REG_R3, gate)
    uc.reg_write(UC_ARM_REG_SP, 0x2001F000); uc.reg_write(UC_ARM_REG_LR, 0x2001FFF1)
    uc.mem_write(0x2001F000, (100).to_bytes(4, 'little'))
    try:
        uc.emu_start(CAVE | 1, 0x2001FFF1, count=60000)
    except UcError as e:
        print("   UCERR", e, "pc=0x%08X" % uc.reg_read(UC_ARM_REG_PC))
    exp = [(n, gate, 777) for (n, v) in notes if n != primary]
    ok = calls == exp
    print(f"  {label:22} poly={notes} -> emitter calls={calls} {'OK' if ok else 'FAIL exp '+str(exp)}")
    return ok


def main():
    cave, patch, pa = build()
    print(f"poly-gate cave {len(cave)}B @ 0x{CAVE:08X}")
    fails = 0
    fails += not run_case(cave, patch, pa, [(60, 100)], 60, 1, 0, 50, "mono")
    fails += not run_case(cave, patch, pa, [(60, 100), (64, 90), (67, 80)], 60, 1, 3, 50, "triad gate 50")
    fails += not run_case(cave, patch, pa, [(48, 70), (52, 71), (55, 72), (59, 73)], 48, 2, 5, 80, "7th ch2 gate 80")
    fails += not run_case(cave, patch, pa, [(36 + i, 40 + i) for i in range(8)], 36, 3, 127, 33, "8-notes ch3 step127")
    print('PASS' if not fails else f'FAIL ({fails})')
    return 0 if not fails else 1


if __name__ == '__main__':
    sys.exit(main())
