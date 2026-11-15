#!/usr/bin/env python3
"""Fan-out cave test at the real pair call site 0x080217F4.

Executes the cave, stubs 0x08019A92, and verifies:
  - extras emitted first, primary last (tail branch),
  - stock time/duration/routing forwarded to every call,
  - no extras when count==1, selector==3 (drums), or primary absent,
  - track/step indexing and count cap.
"""
import json, os, struct, sys
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_HOOK_CODE, UcError
from unicorn.arm_const import *

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from asm import build

CAVE = 0x08047600
PAIR = 0x08019A92
BASE = 0x1000B530


def run(count, notes, selector, step=0, primary=60):
    src = json.load(open(os.path.join(HERE, '..', 'mods', 'poly-fanout.source.json')))
    bundle = build(src)
    code = bytes.fromhex([p for p in bundle['patches'] if int(p['addr'], 16) == CAVE][0]['bytes'])
    u = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
    u.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_M7)
    for a, s in ((0x08000000, 0x80000), (0x10000000, 0x20000), (0x20000000, 0x20000)):
        u.mem_map(a, s)
    u.mem_write(CAVE, code)
    u.mem_write(PAIR, b'\x70\x47')  # bx lr
    rec = bytes([count])
    for n, v in notes:
        rec += bytes([n, v])
    u.mem_write(BASE + selector * 0x880 + step * 17, rec)
    voice = 0x20008000
    u.mem_write(voice + 0x3c, bytes([step]))
    sp = 0x20010000
    u.mem_write(sp, struct.pack('<III', primary, 100, selector))
    for r, v in ((UC_ARM_REG_SP, sp), (UC_ARM_REG_R0, 0), (UC_ARM_REG_R1, 1000),
                 (UC_ARM_REG_R2, 50), (UC_ARM_REG_R3, 7), (UC_ARM_REG_R5, voice),
                 (UC_ARM_REG_LR, 0x2001FFF1)):
        u.reg_write(r, v)
    calls = []

    def hook(uc, addr, size, _):
        if addr == PAIR:
            p = uc.reg_read(UC_ARM_REG_SP)
            note, vel, sel = struct.unpack('<III', uc.mem_read(p, 12))
            calls.append((note, vel, sel, uc.reg_read(UC_ARM_REG_R1),
                          uc.reg_read(UC_ARM_REG_R2), uc.reg_read(UC_ARM_REG_R3)))
    u.hook_add(UC_HOOK_CODE, hook)
    try:
        u.emu_start(CAVE | 1, 0x2001FFF0, count=3000)
    except UcError as e:
        return calls, f'UCERR {e}'
    return calls, None


def check(name, got, want, err):
    ok = not err and got == want
    print(f'  {name:26} {"OK" if ok else "FAIL"}  {got}' + (f' err={err}' if err else ''))
    return ok


def main():
    ok = 0
    total = 0

    calls, err = run(3, [(60, 100), (64, 90), (67, 80)], 0)
    total += 1; ok += check('triad extras first', calls,
                            [(64, 90, 0, 1000, 50, 7), (67, 80, 0, 1000, 50, 7),
                             (60, 100, 0, 1000, 50, 7)], err)

    calls, err = run(1, [(60, 100)], 0)
    total += 1; ok += check('single note no extras', calls, [(60, 100, 0, 1000, 50, 7)], err)

    calls, err = run(3, [(60, 100), (64, 90), (67, 80)], 3)
    total += 1; ok += check('drums selector skip', calls, [(60, 100, 3, 1000, 50, 7)], err)

    calls, err = run(3, [(62, 100), (64, 90), (67, 80)], 0)
    total += 1; ok += check('primary absent skip', calls, [(60, 100, 0, 1000, 50, 7)], err)

    calls, err = run(3, [(60, 100), (64, 90), (67, 80)], 2, step=127)
    total += 1; ok += check('track2 step127', calls,
                            [(64, 90, 2, 1000, 50, 7), (67, 80, 2, 1000, 50, 7),
                             (60, 100, 2, 1000, 50, 7)], err)

    calls, err = run(9, [(60, 100), (64, 90)], 0)
    total += 1; ok += check('count>8 rejected', calls, [(60, 100, 0, 1000, 50, 7)], err)

    print(f'{"PASS" if ok == total else "FAIL"} ({ok}/{total})')
    return 0 if ok == total else 1


if __name__ == '__main__':
    raise SystemExit(main())
