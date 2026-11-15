#!/usr/bin/env python3
"""Test the checked post-directory-creation sidecar initializer, not SD hardware."""
import json
import os
import struct
import sys
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_HOOK_CODE
from unicorn.arm_const import *

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
# Keep Python assembly files and clang scratch files in the same writable root.
# clang does not share tempfile's fallback when inherited TMPDIR is unavailable.
import tempfile
os.environ['TMPDIR'] = os.path.realpath('/tmp')
tempfile.tempdir = os.environ['TMPDIR']
import asm
import verify

OPEN, WRITE, CLOSE = 0x0801496C, 0x08014C92, 0x08014F18
ACCESSOR, HOOK, RET = 0x08024034, 0x0801C5F4, 0x2001FFF0
SP, POLY = 0x2001F000, 0x1000B530
ROOT = os.path.join(HERE, '..')


def run(track, created=1, open_error=None, write_error=False):
    src = json.load(open(os.path.join(ROOT, 'mods/poly-init.source.json')))
    cave = int(src['cave']['addr'], 0)
    code = asm.assemble(src['cave']['asm'], cave)
    assert len(code) <= 256
    stock = verify.index(verify.parse(open(os.path.join(ROOT, 'testdata/gc326.hex')).read()))
    # Replace exactly one stock BL, and replay the original accessor.
    assert bytes(stock[a] for a in range(HOOK, HOOK + 4)) == asm.assemble(['bl 0x08024034'], HOOK)
    u = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
    u.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_M7)
    for a, n in [(0x08000000, 0x80000), (0x10000000, 0x10000), (0x20000000, 0x20000)]:
        u.mem_map(a, n)
    u.mem_write(cave, code)
    u.mem_write(HOOK, asm.assemble(src['patches'][0]['asm'], HOOK))
    # A branch at the original return address allows the test to retain the
    # BL contract while returning through a sentinel.
    u.mem_write(HOOK + 4, asm.assemble(['bx r9'], HOOK + 4))
    u.mem_write(ACCESSOR, bytes(stock[a] for a in range(ACCESSOR, ACCESSOR + 8)))
    for a in [OPEN, WRITE, CLOSE]:
        u.mem_write(a, bytes.fromhex('7047'))
    u.mem_write(POLY, b'\xaa' * (3 * 2176))
    u.mem_write(0x1000ED80, b'\x55' * 16)
    events = []
    current = None
    def fatfs(uc, a, size, _):
        nonlocal current
        assert uc.reg_read(UC_ARM_REG_SP) % 8 == 0
        assert uc.reg_read(UC_ARM_REG_R0) == 0x1000E000
        if a == OPEN:
            p = uc.reg_read(UC_ARM_REG_R1)
            current = bytes(uc.mem_read(p, 6)).rstrip(b'\0')
            assert uc.reg_read(UC_ARM_REG_R2) == 6  # WRITE | CREATE_NEW
            events.append(('open', current))
            uc.reg_write(UC_ARM_REG_R0, 8 if current == open_error else 0)
        elif a == WRITE:
            p, n, count = (uc.reg_read(r) for r in [UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3])
            assert p == 0x1000E500 and n == 2176 and count == 0x1000E300
            assert bytes(uc.mem_read(p, n)) == bytes(n)
            events.append(('write', current))
            uc.mem_write(count, struct.pack('<I', 0 if write_error else n))
            uc.reg_write(UC_ARM_REG_R0, int(write_error))
        else:
            events.append(('close', current))
            uc.reg_write(UC_ARM_REG_R0, 0)
    for a in [OPEN, WRITE, CLOSE]:
        u.hook_add(UC_HOOK_CODE, fatfs, begin=a, end=a)
    saved = {r: 0x12340000 + r for r in [UC_ARM_REG_R4, UC_ARM_REG_R5,
             UC_ARM_REG_R6, UC_ARM_REG_R7, UC_ARM_REG_R8]}
    saved[UC_ARM_REG_R4] = track
    for r, value in saved.items():
        u.reg_write(r, value)
    u.reg_write(UC_ARM_REG_R9, RET | 1)
    u.reg_write(UC_ARM_REG_R0, created & 0xffffffff)
    u.reg_write(UC_ARM_REG_SP, SP)
    u.emu_start(HOOK | 1, RET, count=100000)
    assert u.reg_read(UC_ARM_REG_PC) == RET
    assert u.reg_read(UC_ARM_REG_SP) == SP
    assert all(u.reg_read(r) == value for r, value in saved.items())
    assert u.reg_read(UC_ARM_REG_R0) == 0x2001BB38  # original accessor result
    assert bytes(u.mem_read(POLY, 3 * 2176)) == b'\xaa' * (3 * 2176)
    assert bytes(u.mem_read(0x1000ED80, 16)) == b'\x55' * 16
    expected = []
    if created == 1 and track in [1, 2, 3]:
        for letter in range(ord('A'), ord('X') + 1):
            path = b'poly' + bytes([letter])
            expected.append(('open', path))
            if path != open_error:
                expected.extend([('write', path), ('close', path)])
    assert events == expected, events


def main():
    cases = [(f'melodic {t}, A..X zero sidecars', dict(track=t)) for t in [1, 2, 3]]
    cases += [
        ('drum never opens a sidecar', dict(track=0)),
        ('existing directory leaves files alone', dict(track=1, created=0)),
        ('failed directory leaves cwd alone', dict(track=1, created=-1)),
        ('invalid selector skipped', dict(track=4)),
        ('existing sidecar/open failure skipped', dict(track=2, open_error=b'polyC')),
        ('write failure still closes FIL', dict(track=2, write_error=True)),
    ]
    for name, args in cases:
        run(**args)
        print(f'PASS {name}')
    print('PASS initializer boundaries; full lifecycle is covered by test_poly_module_only.py')


if __name__ == '__main__':
    main()
