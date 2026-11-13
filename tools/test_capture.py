#!/usr/bin/env python3
"""
test_capture.py — Layer 1 (polyphony capture) test.

Assembles the capture routine from mods/poly-capture.source.json, loads it into the
Unicorn CPU emulator, and CALLS it against a synthetic track struct. Proves it copies
every held note (not just the last) into the destination, for 0, 1, a 3-note chord, a
full 24-note cluster, and a corrupt over-range count (must clamp to 24).

  ./.venv/bin/python tools/test_capture.py
"""
import os, sys, json
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import asm
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_SP, UC_ARM_REG_LR
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB

CAVE_ADDR = 0x08047000
CODE_BASE = CAVE_ADDR
CODE_SIZE = 0x1000
MEM_BASE = 0x20000000
MEM_SIZE = 0x4000
TRACK = MEM_BASE
DEST = MEM_BASE + 0x1000
SENTINEL = MEM_BASE + 0x3000
STRIDE = 12
NOTE_OFF = 8
VEL_OFF = 9


def build():
    src = json.load(open(os.path.join(HERE, '..', 'mods', 'poly-capture.source.json')))
    return asm.assemble(src['cave']['asm'], int(src['cave']['addr'], 0))


def make_track(uc, notes):
    """notes: list of (note,vel). Write struct: count at +0x120, elements at +12*i."""
    uc.mem_write(TRACK, b'\x00' * 0x200)
    for i, (n, v) in enumerate(notes):
        base = TRACK + STRIDE * i
        uc.mem_write(base + NOTE_OFF, bytes([n]))
        uc.mem_write(base + VEL_OFF, bytes([v]))
    uc.mem_write(TRACK + 0x120, bytes([len(notes) & 0xFF]))


def run_case(uc, code, raw_count, notes, label):
    make_track(uc, notes)
    # overwrite count with raw_count to test clamping
    uc.mem_write(TRACK + 0x120, bytes([raw_count & 0xFF]))
    uc.mem_write(DEST, b'\x00' * 0x100)
    uc.reg_write(UC_ARM_REG_R0, TRACK)
    uc.reg_write(UC_ARM_REG_R1, DEST)
    uc.reg_write(UC_ARM_REG_SP, MEM_BASE + 0x3F00)
    uc.reg_write(UC_ARM_REG_LR, SENTINEL | 1)   # thumb return, bit0 set

    stop = {'hit': False}
    def hook(uc_, address, size, user):
        if address in (SENTINEL, SENTINEL | 1):
            stop['hit'] = True
            uc_.emu_stop()
    h = uc.hook_add(UC_HOOK_CODE, hook)
    uc.emu_start(CODE_BASE | 1, 0xFFFFFFF0, count=10000)
    uc.hook_del(h)
    if not stop['hit']:
        raise RuntimeError("routine did not return to sentinel")
    n = uc.reg_read(UC_ARM_REG_R0)
    out = uc.mem_read(DEST, max(n, 0) * 2)
    # expected: first min(raw_count,24) notes actually present
    exp_n = min(raw_count, len(notes), 24)
    ok = (n == exp_n)
    got = [(out[2 * i], out[2 * i + 1]) for i in range(n)]
    exp = notes[:exp_n]
    ok = ok and got == exp
    print(f"  {label:22} raw={raw_count:3} -> n={n:2} dest={got}  {'OK' if ok else 'FAIL exp '+str(exp)}")
    return ok


def main():
    code = build()
    print(f"capture routine: {len(code)} bytes @ 0x{CAVE_ADDR:08X}")
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
    for ins in md.disasm(code, CAVE_ADDR):
        print(f"    {ins.address:08x}  {ins.mnemonic:<8} {ins.op_str}")

    uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
    uc.mem_map(CODE_BASE, CODE_SIZE)
    uc.mem_map(MEM_BASE, MEM_SIZE)
    uc.mem_write(CODE_BASE, code)

    cases = [
        (0, [], "empty"),
        (1, [(60, 100)], "single note"),
        (3, [(60, 100), (64, 90), (67, 80)], "C-major chord"),
        (5, [(48, 70), (52, 71), (55, 72), (59, 73), (62, 74)], "five-finger"),
        (24, [(36 + i, 40 + i) for i in range(24)], "full 24-note cluster"),
        (200, [(50 + i, 60 + i) for i in range(24)], "corrupt count 200 -> clamp"),
    ]
    fails = sum(0 if run_case(uc, code, rc, notes, lbl) else 1 for rc, notes, lbl in cases)
    print('PASS' if not fails else f'FAIL ({fails})')
    return 0 if not fails else 1


if __name__ == '__main__':
    sys.exit(main())
