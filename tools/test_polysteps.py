#!/usr/bin/env python3
"""
test_polysteps.py — Layer 2 (per-step note array) test.

Assembles poly_merge / poly_remove / poly_count from mods/poly-steps.source.json and
EXECUTES them in Unicorn against synthetic step buffers. Proves a step can hold a chord
(add/dedupe/velocity-update), drop a note on note-off, and clamp at capacity.

  ./.venv/bin/python tools/test_polysteps.py
"""
import os, sys, json
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import asm
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_SP, UC_ARM_REG_LR
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB

CODE_BASE = 0x08047000
CODE_SIZE = 0x1000
MEM_BASE = 0x20000000
MEM_SIZE = 0x4000
DST = MEM_BASE + 0x1000
SENTINEL = MEM_BASE + 0x3000
CAP = 16

BASES = {'merge': 0x08047100, 'remove': 0x08047180, 'count': 0x08047200}


def load_routines():
    src = json.load(open(os.path.join(HERE, '..', 'mods', 'poly-steps.source.json')))
    out = {'merge': src['cave']['asm']}
    tr = src['test_routines']
    out['remove'] = tr['poly_remove']
    out['count'] = tr['poly_count']
    return out


class Emu:
    def __init__(self, routines):
        self.uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
        self.uc.mem_map(CODE_BASE, CODE_SIZE)
        self.uc.mem_map(MEM_BASE, MEM_SIZE)
        self.addr = {}
        for name, lines in routines.items():
            base = BASES[name]
            code = asm.assemble(lines, base)
            self.uc.mem_write(base, code)
            self.addr[name] = base

    def call(self, name, r0=0, r1=0, r2=0):
        uc = self.uc
        uc.mem_write(DST + 0x200, b'\x00' * 0x10)
        uc.reg_write(UC_ARM_REG_R0, r0)
        uc.reg_write(UC_ARM_REG_R1, r1)
        uc.reg_write(UC_ARM_REG_R2, r2)
        uc.reg_write(UC_ARM_REG_SP, MEM_BASE + 0x3F00)
        uc.reg_write(UC_ARM_REG_LR, SENTINEL | 1)
        stop = {'hit': False}
        def hook(u, address, size, user):
            if address in (SENTINEL, SENTINEL | 1):
                stop['hit'] = True
                u.emu_stop()
        h = uc.hook_add(UC_HOOK_CODE, hook)
        uc.emu_start(self.addr[name] | 1, 0xFFFFFFF0, count=20000)
        uc.hook_del(h)
        assert stop['hit'], f"{name} did not return"
        return uc.reg_read(UC_ARM_REG_R0)


def read_step(uc):
    n = uc.mem_read(DST, 1)[0]
    pairs = []
    for i in range(n):
        b = uc.mem_read(DST + 1 + 2 * i, 2)
        pairs.append((b[0], b[1]))
    return n, pairs


def fresh(uc):
    uc.mem_write(DST, b'\x00' * 0x100)


def main():
    routines = load_routines()
    for name, lines in routines.items():
        code = asm.assemble(lines, BASES[name])
        md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
        print(f"{name}: {len(code)} bytes @ 0x{BASES[name]:08X}")
    e = Emu(routines)
    uc = e.uc
    fails = 0

    def check(label, got, exp):
        nonlocal fails
        ok = got == exp
        fails += 0 if ok else 1
        print(f"  {label:32} got={got}  {'OK' if ok else 'FAIL exp '+str(exp)}")

    # 1. build a chord
    fresh(uc)
    for n, v in [(60, 100), (64, 90), (67, 80)]:
        e.call('merge', DST, n, v)
    check("chord C-E-G count", read_step(uc)[0], 3)
    check("chord C-E-G notes", read_step(uc)[1], [(60, 100), (64, 90), (67, 80)])

    # 2. velocity update (same note twice)
    fresh(uc)
    e.call('merge', DST, 60, 20)
    e.call('merge', DST, 60, 99)
    check("velocity update count", read_step(uc)[0], 1)
    check("velocity update value", read_step(uc)[1], [(60, 99)])

    # 3. capacity clamp
    fresh(uc)
    for i in range(20):
        e.call('merge', DST, 40 + i, 50)
    n, pairs = read_step(uc)
    check("capacity clamp count", n, CAP)
    check("capacity first/last", (pairs[0], pairs[-1]), ((40, 50), (40 + CAP - 1, 50)))

    # 4. remove middle of chord
    fresh(uc)
    for nm, v in [(60, 100), (64, 90), (67, 80)]:
        e.call('merge', DST, nm, v)
    e.call('remove', DST, 64)
    n, pairs = read_step(uc)
    check("remove count", n, 2)
    check("remove set", sorted(x[0] for x in pairs), [60, 67])

    # 5. remove absent note -> unchanged
    fresh(uc)
    for nm in (60, 64, 67):
        e.call('merge', DST, nm, 100)
    e.call('remove', DST, 99)
    check("remove-absent count", read_step(uc)[0], 3)

    # 6. count routine
    check("poly_count", e.call('count', DST, 0, 0), 3)

    print('PASS' if not fails else f'FAIL ({fails})')
    return 0 if not fails else 1


if __name__ == '__main__':
    sys.exit(main())
