#!/usr/bin/env python3
"""Direct bank publication at 0x0804A100.

The publisher opens the sidecar, and must end with the bank fully replaced and
the ownership word set to letter+1. Cases that matter:

  full read          -> bank equals the file, owner = letter+1
  file missing       -> bank zeroed, owner = letter+1 (empty is the truth)
  short read         -> bank zeroed, owner = letter+1
  read error         -> bank zeroed, owner = letter+1
  open error (other) -> bank and owner untouched

The old staging version left the bank untouched on a short read instead of
zeroing it, which mixed old chords with a new letter.
"""
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from fw_sandbox import Sandbox, SENTINEL, STACKTOP
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import *

PUB = 0x0804A100
F_OPEN, F_READ, F_CLOSE = 0x0801496C, 0x08014B30, 0x08014F18
OWNER = 0x1000D740
BANK = 0x1000B530
SIZE = 2176
SLOT = 1
LETTER = 4                      # 'E'
NAME = 0x1000E400


def bench(open_rc=0, read_rc=0, close_rc=0, short=0, prior_owner=LETTER, prior_bank=b'\xAA'):
    sb = Sandbox(ROOT / 'mods/v1-poly-v114.json')
    for p in json.load(open(ROOT / 'mods/poly-ownership-direct.json'))['patches']:
        sb.w(int(p['addr'], 0), bytes.fromhex(p['bytes']))
    payload = bytes((i * 7) & 0xFF for i in range(SIZE - short))
    sb.w(NAME, b'polyE\0')
    sb.w(BANK + SLOT * SIZE, bytes([prior_bank[0]]) * SIZE)
    sb.w(OWNER + SLOT * 4, struct.pack('<I', prior_owner + 1))
    u = sb.uc

    def on_open(uc, a, s, d):
        uc.reg_write(UC_ARM_REG_R0, open_rc)
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    def on_read(uc, a, s, d):
        dst = uc.reg_read(UC_ARM_REG_R1)
        if read_rc == 0:
            uc.mem_write(dst, payload)
        uc.mem_write(0x1000E300, struct.pack('<I', len(payload) if read_rc == 0 else 0))
        uc.reg_write(UC_ARM_REG_R0, read_rc)
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    def on_close(uc, a, s, d):
        uc.reg_write(UC_ARM_REG_R0, close_rc)
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    u.hook_add(UC_HOOK_CODE, on_open, begin=F_OPEN, end=F_OPEN)
    u.hook_add(UC_HOOK_CODE, on_read, begin=F_READ, end=F_READ)
    u.hook_add(UC_HOOK_CODE, on_close, begin=F_CLOSE, end=F_CLOSE)

    u.reg_write(UC_ARM_REG_SP, STACKTOP)
    u.reg_write(UC_ARM_REG_LR, SENTINEL | 1)
    u.reg_write(UC_ARM_REG_R0, BANK + SLOT * SIZE)
    u.reg_write(UC_ARM_REG_R1, SLOT)
    u.reg_write(UC_ARM_REG_R2, LETTER)
    u.reg_write(UC_ARM_REG_R3, NAME)
    u.emu_start(PUB | 1, SENTINEL, count=200000)
    assert u.reg_read(UC_ARM_REG_PC) == SENTINEL
    bank = sb.r(BANK + SLOT * SIZE, SIZE)
    owner = struct.unpack('<I', sb.r(OWNER + SLOT * 4, 4))[0]
    return sb, bank, owner, payload


def main():
    fails = []

    def check(label, cond, detail=None):
        if cond:
            print(f'  PASS {label}')
        else:
            fails.append(label)
            print(f'  FAIL {label} {detail}')

    _, bank, owner, payload = bench()
    check('full read: bank equals the file', bank == payload)
    check('full read: owner set', owner == LETTER + 1, owner)

    _, bank, owner, _ = bench(open_rc=4)
    check('missing file: bank zeroed', bank == bytes(SIZE), bank[:8])
    check('missing file: owner set', owner == LETTER + 1, owner)

    _, bank, owner, payload = bench(short=100)
    check('short read: bank zeroed', bank == bytes(SIZE), bank[:8])
    check('short read: owner set', owner == LETTER + 1, owner)

    _, bank, owner, _ = bench(read_rc=1)
    check('read error: bank zeroed', bank == bytes(SIZE))
    check('read error: owner set', owner == LETTER + 1, owner)

    _, bank, owner, _ = bench(close_rc=1)
    check('close error: bank zeroed', bank == bytes(SIZE))
    check('close error: owner set', owner == LETTER + 1, owner)

    _, bank, owner, _ = bench(open_rc=3)
    check('other open error: bank untouched', bank == b'\xAA' * SIZE)
    check('other open error: owner untouched', owner == LETTER + 1, owner)

    # staging buffer is no longer used by this path
    asm = json.load(open(ROOT / 'mods/poly-ownership-direct.source.json'))['patches'][0]['asm']
    check('staging buffer dropped',
          not any('e500' in line.lower() for line in asm), [l for l in asm if 'e500' in l.lower()])

    if fails:
        print(f'\nFAIL {len(fails)}: {fails}')
        return 1
    print('\nPASS direct publication owns the bank on every path')
    return 0


if __name__ == '__main__':
    sys.exit(main())
