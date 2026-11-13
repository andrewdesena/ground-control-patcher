#!/usr/bin/env python3
"""
test_velhook.py — unit-test the velocity-stash hook (poly-velhook) in the emulator.

Assembles mods/poly-velhook.source.json, loads the cave at 0x08047800, feeds a synthetic note-on
event (note@+4, vel@+5 in r1), and checks it writes vel_by_note[note] at CCM 0x1000FD00 and
reproduces the original two ldrb (+ returns to 0x0801F1EC with r3=note, r2=vel).

  ./.venv/bin/python tools/test_velhook.py
"""
import os, sys, json
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import asm
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_HOOK_CODE, UcError
from unicorn.arm_const import *

CAVE = 0x08047800
BACK = 0x0801F1EC
VELTAB = 0x1000FD00
EVENT = 0x20010000


def build():
    src = json.load(open(os.path.join(HERE, '..', 'mods', 'poly-velhook.source.json')))
    return asm.assemble(src['cave']['asm'], int(src['cave']['addr'], 0))


def run_case(code, note, vel, label):
    uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
    import unicorn.arm_const as A
    try: uc.ctl_set_cpu_model(A.UC_CPU_ARM_CORTEX_M7)
    except Exception: pass
    uc.mem_map(0x08000000, 0x100000)
    uc.mem_map(0x20000000, 0x20000)
    uc.mem_map(0x10000000, 0x10000)
    uc.mem_write(CAVE, code)
    uc.mem_write(VELTAB, b'\x00' * 0x80)
    uc.mem_write(EVENT, b'\x00' * 0x10)
    uc.mem_write(EVENT + 4, bytes([note]))
    uc.mem_write(EVENT + 5, bytes([vel]))
    stopped = {'hit': False}
    def hc(u, a, s, _):
        if a == BACK: stopped['hit'] = True; u.emu_stop()
    uc.hook_add(UC_HOOK_CODE, hc)
    uc.reg_write(UC_ARM_REG_R1, EVENT)
    uc.reg_write(UC_ARM_REG_SP, 0x2001F000)
    uc.reg_write(UC_ARM_REG_LR, 0x2001FFF1)
    try:
        uc.emu_start(CAVE | 1, 0x2001FFF1, count=20000)
    except UcError:
        pass
    got = uc.mem_read(VELTAB + note, 1)[0]
    r3 = uc.reg_read(UC_ARM_REG_R3) & 0xFF
    r2 = uc.reg_read(UC_ARM_REG_R2) & 0xFF
    r1 = uc.reg_read(UC_ARM_REG_R1)
    ok = (got == vel) and (r3 == note) and (r2 == vel) and (r1 == EVENT) and stopped['hit']
    print(f"  {label:26} tbl[note]={got} r3={r3} r2={r2} r1_preserved={r1==EVENT} "
          f"ret={stopped['hit']}  {'OK' if ok else 'FAIL'}")
    return ok


def main():
    code = build()
    print(f"velhook cave: {len(code)} bytes @ 0x{CAVE:08X}")
    from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB
    for i in Cs(CS_ARCH_ARM, CS_MODE_THUMB).disasm(code, CAVE):
        print(f"    {i.address:08x}  {i.mnemonic:<8} {i.op_str}")
    fails = 0
    fails += not run_case(code, 60, 100, "note 60 vel 100")
    fails += not run_case(code, 67, 77, "note 67 vel 77")
    fails += not run_case(code, 43, 5, "note 43 vel 5")
    print('PASS' if not fails else f'FAIL ({fails})')
    return 0 if not fails else 1


if __name__ == '__main__':
    sys.exit(main())
