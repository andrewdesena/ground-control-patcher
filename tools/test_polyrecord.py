#!/usr/bin/env python3
"""
test_polyrecord.py — integration test for the poly-record hook.

Loads the stock firmware image into Unicorn, applies the poly-record bundle, seeds the
pattern-manager struct (0x2001C0E4) + active-track global, then CALLS the hook at the exact
register state it sees at 0x08025814. Asserts:
  * original step store still happens (step+0x1d == note),
  * the note is captured into CCM poly[t][step] (count=1, [note,100]),
  * r4/r5 (pattern-mgr, note) preserved for the continuation,
  * control returns to 0x080257f8.

  ./.venv/bin/python tools/test_polyrecord.py
"""
import os, sys, json, struct
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from verify import parse, index
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_HOOK_CODE
from unicorn.arm_const import *

IMG = os.path.join(HERE, '..', 'testdata', 'gc326.hex')
FLASH = 0x08010000
CAVE = 0x08047400
PMGR = 0x2001C0E4
ACT_GETTER = 0x080232F0
CONTINUE = 0x080257F8
POLY = 0x1000B530
VELTAB = 0x1000FD00
TSTRIDE = 0x880
SSTRIDE = 17
SRAM = 0x20000000; SRAMSZ = 0x20000
CCM = 0x10000000; CCMSZ = 0x10000
PATBASE = 0x20010000

def load_image():
    mem = index(parse(open(IMG, newline='').read()))
    lo = min(mem); hi = max(mem)
    size = ((hi - lo) // 0x1000 + 2) * 0x1000
    img = bytearray([0xFF]) * size
    for a, b in mem.items():
        img[a - lo] = b
    return lo, bytes(img)

def apply_bundle(buf, lo, bundle_path):
    b = json.load(open(bundle_path))
    for p in b['patches']:
        addr = int(p['addr'], 16); data = bytes.fromhex(p['bytes'])
        for i, byte in enumerate(data):
            buf[addr - lo + i] = byte

def main():
    lo, img = load_image()
    buf = bytearray(img)
    apply_bundle(buf, lo, os.path.join(HERE, '..', 'mods', 'poly-record.json'))

    uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
    uc.mem_map(lo, len(buf))
    uc.mem_write(lo, bytes(buf))
    uc.mem_map(SRAM, SRAMSZ)
    uc.mem_map(CCM, CCMSZ)

    # active-track global (from getter literal): set to track 2
    lit = struct.unpack_from('<I', bytes(buf), ACT_GETTER + 4 + 4 - lo)[0]
    uc.mem_write(lit, bytes([2]))
    # pattern-manager struct: [5]=step index, [0xc]=pattern base ptr, [0x10]=0
    uc.mem_write(PMGR, b'\x00' * 0x40)
    uc.mem_write(PMGR + 5, bytes([3]))          # step = 3
    uc.mem_write(PMGR + 0xc, struct.pack('<I', PATBASE))
    uc.mem_write(PMGR + 0x10, bytes([0]))
    # zero the CCM poly area (simulate pre-zero; also test stale-clip separately)
    uc.mem_write(POLY, b'\x00' * 0x3300)
    uc.mem_write(VELTAB, b'\x00' * 0x80)
    uc.mem_write(VELTAB + 67, bytes([77]))      # real captured velocity for note 67

    note = 67
    step = 3
    # register state at 0x08025814: r1=note, r5=note, r3=base+10*step+r2, r4=pmgr
    r3 = PATBASE + 10 * step
    uc.reg_write(UC_ARM_REG_R1, note)
    uc.reg_write(UC_ARM_REG_R5, note)
    uc.reg_write(UC_ARM_REG_R3, r3)
    uc.reg_write(UC_ARM_REG_R4, PMGR)
    uc.reg_write(UC_ARM_REG_SP, SRAM + 0x1FF00)
    uc.reg_write(UC_ARM_REG_LR, 0x2001FF00)

    stop = {'hit': False}
    def hook(u, address, size, user):
        if address == CONTINUE:
            stop['hit'] = True; u.emu_stop()
    h = uc.hook_add(UC_HOOK_CODE, hook)
    uc.emu_start(CAVE | 1, 0xFFFFFFF0, count=200000)
    uc.hook_del(h)

    fails = 0
    def check(label, got, exp):
        nonlocal fails
        ok = got == exp; fails += 0 if ok else 1
        print(f"  {label:34} got={got}  {'OK' if ok else 'FAIL exp '+str(exp)}")

    check("returned to continuation", stop['hit'], True)
    check("original step store", uc.mem_read(r3 + 0x1d, 1)[0], note)
    check("r5 (note) preserved", uc.reg_read(UC_ARM_REG_R5), note)
    check("r4 (pmgr) preserved", uc.reg_read(UC_ARM_REG_R4), PMGR)
    dst = POLY + 2 * TSTRIDE + step * SSTRIDE
    cnt = uc.mem_read(dst, 1)[0]
    ent = uc.mem_read(dst + 1, 2)
    check("poly count", cnt, 1)
    check("poly entry (note,vel)", (ent[0], ent[1]), (note, 77))

    # second note same step -> chord (count 2); then a repeat -> velocity update (count stays 2)
    def run_once(n):
        uc.reg_write(UC_ARM_REG_R1, n); uc.reg_write(UC_ARM_REG_R5, n); uc.reg_write(UC_ARM_REG_R3, r3); uc.reg_write(UC_ARM_REG_R4, PMGR)
        st = {'hit': False}
        def hk(u, a, s, uu):
            if a == CONTINUE: st['hit'] = True; u.emu_stop()
        hh = uc.hook_add(UC_HOOK_CODE, hk)
        uc.emu_start(CAVE | 1, 0xFFFFFFF0, count=200000)
        uc.hook_del(hh); return st['hit']
    run_once(72)
    cnt2 = uc.mem_read(dst, 1)[0]
    check("chord count after 2 notes", cnt2, 2)
    run_once(72)   # duplicate -> velocity update, not new entry
    cnt3 = uc.mem_read(dst, 1)[0]
    check("dedupe (count stays)", cnt3, 2)

    # stale-count clip: set count to 200, record one note -> clipped to fresh 1
    uc.mem_write(lit, bytes([0]))               # active track -> 0 for this case
    dst2 = POLY + 0 * TSTRIDE + 5 * SSTRIDE
    uc.mem_write(dst2, bytes([200]))
    uc.mem_write(PMGR + 5, bytes([5]))
    uc.reg_write(UC_ARM_REG_R3, PATBASE + 10 * 5)
    run_once(60)
    check("stale count clipped", uc.mem_read(dst2, 1)[0], 1)
    ent2 = uc.mem_read(dst2 + 1, 2)
    check("fallback vel when unset (100)", (ent2[0], ent2[1]), (60, 100))

    print('PASS' if not fails else f'FAIL ({fails})')
    return 0 if not fails else 1

if __name__ == '__main__':
    sys.exit(main())
