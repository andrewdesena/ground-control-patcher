#!/usr/bin/env python3
"""
test_poly_transpose.py — chord notes follow a track transpose.

Simulates the success path of FUN_08028194: r12 = pattern sub-struct (track + idx*0x194),
r4 = 1, r5 = signed delta. The cave must store the success flag and shift every chord note
in that track's poly record, clamped to 0..127.

  ./.venv/bin/python tools/test_poly_transpose.py
"""
import os, sys, json
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import asm
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UcError
from unicorn.arm_const import *

CAVE = 0x08048600
TABLE = 0x20010000
TRACK = 0x20011000
POLY = 0x1000B530
RESUME = 0x08028228
IDX = 1


def build():
    src = json.load(open(os.path.join(HERE, '..', 'mods', 'poly-transpose.source.json')))
    return asm.assemble(src['cave']['asm'], int(src['cave']['addr'], 0))


def run_case(cave, delta):
    uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
    uc.mem_map(0x08000000, 0x100000)
    uc.mem_map(0x20000000, 0x20000)
    uc.mem_map(0x10000000, 0x10000)
    uc.mem_write(CAVE, cave)
    uc.mem_write(0x08028230, TABLE.to_bytes(4, 'little'))
    uc.mem_write(TRACK, b'\x00' * 0x1200)
    for i in range(4):
        base = TRACK + i * 0x400
        uc.mem_write(TABLE + i * 4, base.to_bytes(4, 'little'))
        uc.mem_write(base + 0x2e, bytes([i]))
    ip = TRACK + IDX * 0x400 + IDX * 0x194
    addr = POLY + IDX * 0x880
    uc.mem_write(addr + 0 * 17, bytes([2, 60, 64]))
    uc.mem_write(addr + 1 * 17, bytes([1, 120]))
    uc.reg_write(UC_ARM_REG_R12, ip)
    uc.reg_write(UC_ARM_REG_R4, 1)
    uc.reg_write(UC_ARM_REG_R5, delta & 0xffffffff)
    uc.reg_write(UC_ARM_REG_SP, 0x2001F000)
    uc.reg_write(UC_ARM_REG_LR, RESUME | 1)
    try:
        uc.emu_start(CAVE | 1, RESUME, count=20000)
    except UcError as e:
        print("   UCERR", e, "pc=0x%08X" % uc.reg_read(UC_ARM_REG_PC))
    n0 = list(uc.mem_read(addr, 3))
    n1 = list(uc.mem_read(addr + 17, 2))
    flag = uc.mem_read(ip + 0x38, 2)
    ok = (n0 == [2, max(0, min(127, 60 + delta)), 64] and n1 == [1, max(0, min(127, 120 + delta))]
          and flag == b'\x01\x00' and uc.reg_read(UC_ARM_REG_PC) == RESUME)
    print(f"  delta={delta:+3} -> {n0} {n1} flag={flag.hex()} {'OK' if ok else 'FAIL'}")
    return ok


def main():
    cave = build()
    print(f"poly-transpose cave {len(cave)}B @ 0x{CAVE:08X}")
    fails = 0
    fails += not run_case(cave, 2)
    fails += not run_case(cave, -1)
    fails += not run_case(cave, 12)   # 120+12 clamps to 127
    print('PASS' if not fails else f'FAIL ({fails})')
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
