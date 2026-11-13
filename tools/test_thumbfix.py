#!/usr/bin/env python3
"""
test_thumbfix.py — regression for Thumb-2 far-branch encoding (BL / B.W, T4).

Guards the bug where gas emits addend = target-base-4, so thumbfix must encode
offset = addend - instr_off. Assembles real far branches at several section offsets
for both branch kinds, runs them through thumbfix.fix(), and asserts the decoded
branch lands on the exact intended absolute address.

  python3 tools/test_thumbfix.py
"""
import os, sys, subprocess, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from elftools.elf.elffile import ELFFile
import thumbfix
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB

BASE = 0x08046810
CASES = [
    ('bw', 0x3C, 0x08019912),
    ('bw', 0x52, 0x08019890),
    ('bl', 0x00, 0x08046810),
    ('bl', 0x20, 0x08011160),
    ('bw', 0x7A, 0x0803AFC6),
]
md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)


def assemble(ins, off, target):
    src = (".syntax unified\n.thumb\n.text\n.global _start\n"
           ".set __base, 0x%08X\n_start:\n  .space 0x%x\n  %s _start+(0x%08X-__base)\n"
           % (BASE, off, ins, target))
    with tempfile.TemporaryDirectory() as td:
        s = os.path.join(td, 'a.s'); o = os.path.join(td, 'a.o')
        open(s, 'w').write(src)
        r = subprocess.run(['clang', '--target=thumbv7m-none-eabi', '-mthumb', '-c',
                            '-x', 'assembler-with-cpp', '-march=armv7-m', '-O2', '-fno-pic',
                            s, '-o', o], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        with open(o, 'rb') as f:
            elf = ELFFile(f)
            text = bytearray(elf.get_section_by_name('.text').data())
            rel = [(rl['r_offset'], 'x') for sec in elf.iter_sections()
                   if sec.header['sh_type'] in ('SHT_REL', 'SHT_RELA')
                   for rl in sec.iter_relocations()]
    return thumbfix.fix(text, rel)


def target_of(chunk, addr):
    ins = next(md.disasm(bytes(chunk), addr))
    return int(ins.op_str.replace('#', '').strip(), 16)


def main():
    fails = 0
    for kind, off, target in CASES:
        ins = 'b.w' if kind == 'bw' else 'bl'
        fixed = assemble(ins, off, target)
        got = target_of(fixed[off:off + 4], BASE + off)
        ok = got == target
        fails += 0 if ok else 1
        print(f"  {ins:3} off=0x{off:02x}  want 0x{target:08X}  got 0x{got:08X}  {'OK' if ok else 'FAIL'}")
    print('PASS' if not fails else f'FAIL ({fails})')
    return 0 if not fails else 1


if __name__ == '__main__':
    sys.exit(main())
