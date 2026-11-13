#!/usr/bin/env python3
"""
test_fanout.py — unit-test the poly-fanout cave in the emulator (no hardware).

Assembles mods/poly-fanout.source.json, loads the cave at 0x08047600, builds a synthetic
voice object + a CCM poly[track][step] array, runs the cave, and checks that it emits a note
pair (0x8019A92) for every chord note EXCEPT the primary (sl), on the right channel/velocity.

  ./.venv/bin/python tools/test_fanout.py
"""
import os, sys, json
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import asm
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_HOOK_CODE, UcError
from unicorn.arm_const import *

CAVE = 0x08047600
BACK = 0x08021A72
PAIR = 0x08019A92
POLY = 0x1000B530
OBJ, PAR = 0x20010000, 0x20011000
BASE = ((CAVE // 0x1000) * 0x1000)
SENT = 0x2001FFF1


def build():
    src = json.load(open(os.path.join(HERE, '..', 'mods', 'poly-fanout.source.json')))
    return asm.assemble(src['cave']['asm'], int(src['cave']['addr'], 0))


def run_case(code, notes, primary, channel, step, label):
    uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
    # FPU core BEFORE mapping (same gotcha as fw_sandbox)
    import unicorn.arm_const as A
    try: uc.ctl_set_cpu_model(A.UC_CPU_ARM_CORTEX_M7)
    except Exception: pass
    uc.mem_map(0x08000000, 0x100000)       # flash (covers cave + pair)
    uc.mem_map(0x20000000, 0x20000)        # sram
    uc.mem_map(0x10000000, 0x10000)        # ccm poly area
    uc.mem_write(CAVE, code)
    uc.mem_write(PAIR, bytes([0x70, 0x47]))  # stub 0x8019A92 = bx lr (we capture args at entry)
    # object graph
    uc.mem_write(OBJ, b'\x00' * 0x40)
    uc.mem_write(PAR, b'\x00' * 0x40)
    uc.mem_write(OBJ + 8, PAR.to_bytes(4, 'little'))
    uc.mem_write(PAR + 0x1f, bytes([channel]))
    # poly[track][step]
    track = channel - 1
    addr = POLY + track * 0x880 + step * 17
    buf = bytes([len(notes)])
    for n, v in notes:
        buf += bytes([n, v])
    uc.mem_write(addr, buf)
    calls = []
    def hc(u, a, s, _):
        if a == PAIR:
            sp = u.reg_read(UC_ARM_REG_SP)
            note = u.mem_read(sp, 1)[0]
            vel = u.mem_read(sp + 4, 1)[0]
            ch = u.mem_read(sp + 8, 1)[0]
            calls.append((note, vel, ch))
        if a == BACK:
            u.emu_stop()
    uc.hook_add(UC_HOOK_CODE, hc)
    uc.reg_write(UC_ARM_REG_R0, step)
    uc.reg_write(UC_ARM_REG_R4, OBJ)
    uc.reg_write(UC_ARM_REG_R8, PAR)
    uc.reg_write(UC_ARM_REG_R10, primary)   # sl = primary note
    uc.reg_write(UC_ARM_REG_SP, 0x2001F000)
    uc.reg_write(UC_ARM_REG_LR, SENT)
    try:
        uc.emu_start(CAVE | 1, SENT, count=20000)
    except UcError as e:
        print("   stopped:", e)
    exp = [(n, v, channel) for (n, v) in notes if n != primary]
    ok = calls == exp
    print(f"  {label:24} notes={notes} primary={primary} ch={channel} -> emitted={calls} "
          f"{'OK' if ok else 'FAIL exp '+str(exp)}")
    return ok


def main():
    code = build()
    print(f"fan-out cave: {len(code)} bytes @ 0x{CAVE:08X}")
    from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB
    for i in Cs(CS_ARCH_ARM, CS_MODE_THUMB).disasm(code, CAVE):
        print(f"    {i.address:08x}  {i.mnemonic:<8} {i.op_str}")
    fails = 0
    fails += not run_case(code, [(60, 100)], 60, 1, 0, "mono (no extras)")
    fails += not run_case(code, [(60, 100), (64, 90), (67, 80)], 60, 1, 0, "C-major triad")
    fails += not run_case(code, [(48, 70), (52, 71), (55, 72), (59, 73)], 48, 2, 5, "7th chord ch2 step5")
    fails += not run_case(code, [(36 + i, 40 + i) for i in range(8)], 36, 3, 127, "8-note cluster ch3")
    print('PASS' if not fails else f'FAIL ({fails})')
    return 0 if not fails else 1


if __name__ == '__main__':
    sys.exit(main())
