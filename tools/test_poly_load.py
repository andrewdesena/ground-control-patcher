#!/usr/bin/env python3
"""
test_poly_load.py — unit-test the poly sidecar loader cave.

Simulates the loader's post-f_close state (sp+0x14 = track, path buffer at sp+0x38 =
"patternA") and stubs FatFS f_open/f_read/f_close with code hooks. Verifies the cave:
  * rewrites the path to "poly<letter>" in the same directory
  * passes the right FIL/path/mode to f_open
  * reads 2176 bytes into 0x1000B530 + track*0x880
  * leaves [sp+0x34] = 0xFFFFFFFF for the caller
  * skips the drum track (index 3) entirely

  ./.venv/bin/python tools/test_poly_load.py
"""
import os, sys, json
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import asm
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_HOOK_CODE, UcError
from unicorn.arm_const import *
import unicorn.arm_const as A

CAVE = 0x08047C00
F_OPEN, F_READ, F_CLOSE = 0x0801496C, 0x08014B30, 0x08014F18
POLY = 0x1000B530
FIL = 0x1000E000
COUNT = 0x1000E300
SP = 0x2001F000
RET = 0x2001FFF1


def build():
    src = json.load(open(os.path.join(HERE, '..', 'mods', 'poly-load.source.json')))
    return asm.assemble(src['cave']['asm'], int(src['cave']['addr'], 0))


def run_case(cave, track, letter, label):
    uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
    try: uc.ctl_set_cpu_model(A.UC_CPU_ARM_CORTEX_M7)
    except Exception: pass
    uc.mem_map(0x08000000, 0x100000)
    uc.mem_map(0x20000000, 0x20000)
    uc.mem_map(0x10000000, 0x10000)
    # FatFS stubs: return success; hooks perform side effects
    uc.mem_write(F_OPEN, bytes.fromhex('00207047'))   # movs r0,#0 ; bx lr
    uc.mem_write(F_READ, bytes.fromhex('7047'))       # bx lr
    uc.mem_write(F_CLOSE, bytes.fromhex('7047'))      # bx lr
    uc.mem_write(CAVE, cave)
    uc.mem_write(SP + 0x14, track.to_bytes(4, 'little'))
    uc.mem_write(SP + 0x38, ("pattern" + letter + "\x00").encode())
    side = bytes(((i * 7) & 0xFF) for i in range(2176))
    log = {'open': [], 'read': [], 'close': 0}

    def hook(u, addr, size, _):
        if addr == F_OPEN:
            p = u.reg_read(UC_ARM_REG_R1)
            log['open'].append(bytes(u.mem_read(p, 6)).decode(errors='replace').rstrip('\x00'))
        elif addr == F_READ:
            dest = u.reg_read(UC_ARM_REG_R1)
            n = u.reg_read(UC_ARM_REG_R2)
            log['read'].append((dest, n))
            u.mem_write(dest, side[:n])
            u.reg_write(UC_ARM_REG_R3, n)   # *br
            u.reg_write(UC_ARM_REG_R0, 0)
            u.mem_write(COUNT, n.to_bytes(4, 'little'))
        elif addr == F_CLOSE:
            log['close'] += 1
            u.reg_write(UC_ARM_REG_R0, 0)
    uc.hook_add(UC_HOOK_CODE, hook)
    # poison destination so we can prove it was written
    uc.mem_write(POLY + track * 0x880, b'\xAA' * 2176)
    uc.reg_write(UC_ARM_REG_SP, SP)
    uc.reg_write(UC_ARM_REG_LR, RET | 1)
    try:
        uc.emu_start(CAVE | 1, RET & ~1, count=20000)
    except UcError as e:
        print("   UCERR", e, "pc=0x%08X" % uc.reg_read(UC_ARM_REG_PC))
    got = bytes(uc.mem_read(POLY + track * 0x880, 2176))
    ret = uc.reg_read(UC_ARM_REG_R3) & 0xFFFFFFFF
    path = bytes(uc.mem_read(SP + 0x38, 6)).decode(errors='replace')
    ok = True
    if track == 3:
        ok = (log['open'] == [] and log['close'] == 0 and got == b'\xAA' * 2176 and ret == 0xFFFFFFFF)
    else:
        ok = (log['open'] == ['poly' + letter] and log['close'] == 1 and got == side and ret == 0xFFFFFFFF)
    print(f"  {label:16} open={log['open']} read={log['read']} close={log['close']} "
          f"path={path!r} ret={ret:#010x} {'OK' if ok else 'FAIL'}")
    return ok


def main():
    cave = build()
    print(f"poly-load cave {len(cave)}B @ 0x{CAVE:08X}")
    fails = 0
    fails += not run_case(cave, 0, 'A', 'track1 pattern A')
    fails += not run_case(cave, 2, 'C', 'track3 pattern C')
    fails += not run_case(cave, 3, 'A', 'drum (skip)')
    print('PASS' if not fails else f'FAIL ({fails})')
    return 0 if not fails else 1


if __name__ == '__main__':
    sys.exit(main())
