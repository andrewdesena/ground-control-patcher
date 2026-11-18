#!/usr/bin/env python3
"""Save path end to end: the sidecar must be named for the pattern letter.

Drives the real stock pattern writer 0x0801C450 with FatFS and helpers stubbed,
then asserts on the names actually passed to f_open. This is the test the old
fixture could not be: it used to write the very frame byte the cave reads, so a
wrong-letter save was invisible.

Call convention, verified in the disassembly: r1 is the pattern block pointer,
r2 is the letter index (it indexes the 24 entry table at 0x08038310), and the
function returns through 0x0801C4A2 to LR.
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

TRACKS = (0x20013DEC, 0x200117C8, 0x2000F1A4, 0x2000CB80)
BANK = 0x1000B530
SIZE = 2176
WRITER = 0x0801C450
F_OPEN = 0x0801496C
RET = 0x0801C4A2

# helpers the writer calls that are irrelevant here; stub each to return 0
STUBS = (0x080351FC, 0x080150B6, 0x08014F18, 0x080232A0, 0x080232B0,
         0x0801536C, 0x0801B560, 0x0801EF68, 0x08015336, 0x0801EDD4,
         0x08014C92, 0x08014B30, 0x080147E0)


def run(track_slot, letter, bundle, owner_letter=None):
    sb = Sandbox(ROOT / bundle)
    # always test the current save cave, not whatever the bundle happens to hold
    for p in json.load(open(ROOT / 'mods/poly-save-sanitize.json'))['patches']:
        sb.w(int(p['addr'], 0), bytes.fromhex(p['bytes']))
    for n, t in enumerate(TRACKS):
        sb.w(t + 0x2D, bytes([int(n == 0)]))
        sb.w(t + 0x2E, bytes([letter if owner_letter is None else owner_letter]))
    block = TRACKS[track_slot] + 0x34 + letter * 0x194
    sb.w(block + 4, bytes([1]))            # non-zero so the writer reaches f_open
    sb.w(block + 8, bytes([60, 100, 0]))   # one real step
    sb.w(block + 0x188, struct.pack('<HH', 1, 1))
    bank = BANK + track_slot * SIZE
    sb.w(bank, bytes([1, 60, 90]) + bytes(14))
    held = letter if owner_letter is None else owner_letter
    sb.w(0x1000D740 + track_slot * 4, struct.pack('<I', held + 1))

    seen = []
    u = sb.uc

    def on_open(uc, addr, size, data):
        name = bytes(uc.mem_read(uc.reg_read(UC_ARM_REG_R1), 20)).split(b'\0')[0].decode('latin1')
        seen.append(name)
        uc.reg_write(UC_ARM_REG_R0, 0)
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    def on_stub(uc, addr, size, data):
        assert uc.reg_read(UC_ARM_REG_SP) % 8 == 0, f'stack misaligned at {addr:#x}'
        uc.reg_write(UC_ARM_REG_R0, 0)
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    u.hook_add(UC_HOOK_CODE, on_open, begin=F_OPEN, end=F_OPEN)
    for a in STUBS:
        u.hook_add(UC_HOOK_CODE, on_stub, begin=a, end=a)
    u.hook_add(UC_HOOK_CODE, lambda uc, a, s, d: uc.emu_stop(), begin=RET, end=RET)

    u.reg_write(UC_ARM_REG_SP, STACKTOP)
    u.reg_write(UC_ARM_REG_LR, SENTINEL | 1)
    u.reg_write(UC_ARM_REG_R1, block)
    u.reg_write(UC_ARM_REG_R2, letter)
    u.emu_start(WRITER | 1, 0xFFFFFFF0, count=400000)
    return seen


def main():
    fails = []
    bundle = sys.argv[1] if len(sys.argv) > 1 else 'mods/v1-poly-v117.json'

    def check(label, cond, detail=None):
        if cond:
            print(f'  PASS {label}')
        else:
            fails.append(label)
            print(f'  FAIL {label} {detail}')

    # letters that break ASCII arithmetic, on more than one track
    for slot, letter, name in ((1, 0, 'A'), (1, 4, 'E'), (2, 20, 'V'),
                               (3, 21, 'W'), (1, 23, 'Z')):
        seen = run(slot, letter, bundle)
        want = [f'pattern{name}.txt', f'poly{name}']
        check(f'track{slot} letter {name}: names {want}', seen == want, seen)

    # saving to a chosen letter is how a pattern is copied, so the chord bank
    # must be written to the destination even when it belongs to another letter
    seen = run(1, 4, bundle, owner_letter=0)
    check('save-to-letter copies the chords too',
          seen == ['patternE.txt', 'polyE'], seen)

    if fails:
        print(f'\nFAIL {len(fails)}: {fails}')
        return 1
    print('\nPASS save names the sidecar for the pattern letter, end to end')
    return 0


if __name__ == '__main__':
    sys.exit(main())
