#!/usr/bin/env python3
"""Save-time sidecar writer must use the saving track's own bank.

The cave at 0x08047E00 runs from inside the pattern writer, where r4 is the
pattern block pointer and the pattern letter sits at caller sp+0xf. It must:
  * recover track = pattern - 0x34 - letter*0x194
  * find that track in 0x08038370 (drum = index 0, tracks 1..3 = 1..3)
  * write bank 0x1000B530 + index*0x880 into poly<letter>
  * do nothing but close for the drum
The old version wrote bank letter*0x880, which is why saving letter A on track 2
dumped bank 0 (the drum's unused buffer) over that track's chords.
"""
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from fw_sandbox import Sandbox, SENTINEL, SRAM
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2,
                               UC_ARM_REG_R3, UC_ARM_REG_R4, UC_ARM_REG_SP,
                               UC_ARM_REG_LR, UC_ARM_REG_PC)

CAVE = 0x08047E00
F_OPEN, F_WRITE, F_CLOSE = 0x0801496C, 0x08014C92, 0x08014F18
TABLE = 0x08038370
BANK = 0x1000B530
DRUM, T1, T2, T3 = 0x20013DEC, 0x200117C8, 0x2000F1A4, 0x2000CB80
TRACKS = (DRUM, T1, T2, T3)
STACK = SRAM + 0x8000


def main():
    fails = []

    def run_case(label, track, letter, expect_bank, expect_open=True, active=None):
        active = letter if active is None else active
        sb = Sandbox()
        import json
        for p in json.load(open(ROOT / 'mods/poly-save-letter.json'))['patches']:
            sb.w(int(p['addr'], 0), bytes.fromhex(p['bytes']))
        sb.w(TABLE, struct.pack('<4I', *TRACKS))
        for i, p in enumerate(TRACKS):
            sb.w(p + 0x2D, bytes([1 if p == DRUM else 0]))
        sb.w(track + 0x2E, bytes([active]))   # the letter the bank currently holds
        # caller frame as the pattern writer leaves it
        sb.w(STACK, bytes(0x60))
        sb.w(STACK + 0x0F, bytes([0x41 + letter]))   # frame holds the ASCII letter
        sb.w(STACK + 0x18, b'\xEE' * 8)          # caller's own file handle

        seen = {'open': [], 'write': [], 'close': 0}

        def stop(u, addr, size, _):
            u.emu_stop()

        def do_open(u, addr, size, _):
            name = bytes(u.mem_read(u.reg_read(UC_ARM_REG_R1), 24)).split(b'\0')[0].decode('latin1')
            seen['open'].append(name)
            u.reg_write(UC_ARM_REG_R0, 0)
            u.reg_write(UC_ARM_REG_PC, u.reg_read(UC_ARM_REG_LR))

        def do_write(u, addr, size, _):
            seen['write'].append((u.reg_read(UC_ARM_REG_R1), u.reg_read(UC_ARM_REG_R2)))
            u.mem_write(u.reg_read(UC_ARM_REG_R3), struct.pack('<I', u.reg_read(UC_ARM_REG_R2)))
            u.reg_write(UC_ARM_REG_R0, 0)
            u.reg_write(UC_ARM_REG_PC, u.reg_read(UC_ARM_REG_LR))

        def do_close(u, addr, size, _):
            seen['close'] += 1
            u.reg_write(UC_ARM_REG_R0, 0)
            u.reg_write(UC_ARM_REG_PC, u.reg_read(UC_ARM_REG_LR))

        u = sb.uc
        u.hook_add(UC_HOOK_CODE, do_open, begin=F_OPEN, end=F_OPEN)
        u.hook_add(UC_HOOK_CODE, do_write, begin=F_WRITE, end=F_WRITE)
        u.hook_add(UC_HOOK_CODE, do_close, begin=F_CLOSE, end=F_CLOSE)
        u.hook_add(UC_HOOK_CODE, stop, begin=SENTINEL, end=SENTINEL)

        pattern = track + 0x34 + letter * 0x194
        u.reg_write(UC_ARM_REG_R4, pattern)      # pattern pointer, as the writer has it
        u.reg_write(UC_ARM_REG_SP, STACK)
        u.reg_write(UC_ARM_REG_LR, SENTINEL | 1)
        u.emu_start(CAVE | 1, 0xFFFFFFF0, count=200000)
        assert u.reg_read(UC_ARM_REG_PC) == SENTINEL, f'{label}: did not return'

        ok = True
        if expect_open:
            name = f'poly{chr(ord("A") + letter)}'
            if seen['open'] != [name]:
                fails.append(label + ' name'); ok = False
                print(f'  FAIL {label}: opened {seen["open"]} want [{name}]')
            if len(seen['write']) != 1 or seen['write'][0] != (BANK + expect_bank * 0x880, 0x880):
                fails.append(label + ' bank'); ok = False
                got = [(hex(b), n) for b, n in seen['write']]
                print(f'  FAIL {label}: wrote {got} want [{hex(BANK + expect_bank * 0x880)}, 0x880]')
        else:
            if seen['open'] or seen['write']:
                fails.append(label + ' drum'); ok = False
                print(f'  FAIL {label}: drum opened {seen["open"]} wrote {seen["write"]}')
        want_close = 2 if expect_open else 1   # sidecar handle + the caller's own
        if seen['close'] != want_close:
            fails.append(label + ' close'); ok = False
            print(f'  FAIL {label}: closed {seen["close"]} time(s), want {want_close}')
        if ok:
            print(f'  PASS {label}')

    print('save writer: bank comes from the track, not the pattern letter')
    run_case('track1 letter A -> bank 1', T1, 0, 1)
    run_case('track2 letter A -> bank 2', T2, 0, 2)
    run_case('track3 letter A -> bank 3', T3, 0, 3)
    run_case('track2 letter E, E active -> bank 2', T2, 4, 2)
    run_case('track2 letter E while A active -> no sidecar write', T2, 4, 2, expect_open=False, active=0)
    run_case('track1 letter B while B active -> bank 1', T1, 1, 1, active=1)
    run_case('drum only closes', DRUM, 0, 0, expect_open=False)

    if fails:
        print(f'\nFAIL {len(fails)}: {fails}')
        return 1
    print('\nPASS save writer uses the track bank only for the active letter')
    return 0


if __name__ == '__main__':
    sys.exit(main())
