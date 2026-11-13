#!/usr/bin/env python3
"""
test_poly_save.py — unit-test the poly sidecar save cave.

Simulates the writer's pre-f_close state (sp+0x8 = "patternA", letter at sp+0xf, r7 = track)
and stubs f_open/f_write/f_close with code hooks. Verifies the cave:
  * opens "poly<letter>" with mode 0x0A in the same directory
  * f_write(FIL, 0x1000B530 + track*0x880, 2176, &count)
  * closes the sidecar and the original pattern FIL
  * skips the sidecar for the drum track (r7 == 3) but still closes the pattern

  ./.venv/bin/python tools/test_poly_save.py
"""
import os, sys, json
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import asm
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_HOOK_CODE, UcError
from unicorn.arm_const import *
import unicorn.arm_const as A

CAVE = 0x08047E00
F_OPEN, F_WRITE, F_CLOSE = 0x0801496C, 0x08014C92, 0x08014F18
POLY = 0x1000B530
SP = 0x2001F000
RET = 0x2001FFF1


def build():
    src = json.load(open(os.path.join(HERE, '..', 'mods', 'poly-save.source.json')))
    return asm.assemble(src['cave']['asm'], int(src['cave']['addr'], 0))


def run_case(cave, track, letter, label):
    uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
    try: uc.ctl_set_cpu_model(A.UC_CPU_ARM_CORTEX_M7)
    except Exception: pass
    uc.mem_map(0x08000000, 0x100000)
    uc.mem_map(0x20000000, 0x20000)
    uc.mem_map(0x10000000, 0x10000)
    uc.mem_write(F_OPEN, bytes.fromhex('00207047'))
    uc.mem_write(F_WRITE, bytes.fromhex('7047'))
    uc.mem_write(F_CLOSE, bytes.fromhex('7047'))
    uc.mem_write(CAVE, cave)
    uc.mem_write(SP + 0x8, ("pattern" + letter + "\x00").encode())
    log = {'open': [], 'write': [], 'close': 0}

    def hook(u, addr, size, _):
        if addr == F_OPEN:
            p = u.reg_read(UC_ARM_REG_R1)
            log['open'].append((bytes(u.mem_read(p, 6)).decode(errors='replace').rstrip('\x00'),
                                u.reg_read(UC_ARM_REG_R2)))
        elif addr == F_WRITE:
            log['write'].append((u.reg_read(UC_ARM_REG_R1), u.reg_read(UC_ARM_REG_R2)))
            u.reg_write(UC_ARM_REG_R3, u.reg_read(UC_ARM_REG_R2))
            u.reg_write(UC_ARM_REG_R0, 0)
        elif addr == F_CLOSE:
            log['close'] += 1
            u.reg_write(UC_ARM_REG_R0, 0)
    uc.hook_add(UC_HOOK_CODE, hook)
    uc.reg_write(UC_ARM_REG_SP, SP)
    uc.reg_write(UC_ARM_REG_R7, track)
    uc.reg_write(UC_ARM_REG_LR, RET | 1)
    try:
        uc.emu_start(CAVE | 1, RET & ~1, count=20000)
    except UcError as e:
        print("   UCERR", e, "pc=0x%08X" % uc.reg_read(UC_ARM_REG_PC))
    path = bytes(uc.mem_read(SP + 0x8, 6)).decode(errors='replace')
    if track == 3:
        ok = (log['open'] == [] and log['write'] == [] and log['close'] == 1 and path == 'patter')
    else:
        ok = (log['open'] == [('poly' + letter, 0x0A)] and
              log['write'] == [(POLY + track * 0x880, 2176)] and
              log['close'] == 2 and path == 'poly' + letter + '\x00')
    print(f"  {label:16} open={log['open']} write={[(hex(d), n) for d, n in log['write']]} "
          f"close={log['close']} path={path!r} {'OK' if ok else 'FAIL'}")
    return ok


def main():
    cave = build()
    print(f"poly-save cave {len(cave)}B @ 0x{CAVE:08X}")
    fails = 0
    fails += not run_case(cave, 0, 'A', 'track1 pattern A')
    fails += not run_case(cave, 2, 'C', 'track3 pattern C')
    fails += not run_case(cave, 3, 'A', 'drum (skip)')
    print('PASS' if not fails else f'FAIL ({fails})')
    return 0 if not fails else 1


if __name__ == '__main__':
    sys.exit(main())
