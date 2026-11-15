#!/usr/bin/env python3
"""Execute the fan-out cave through stock pair and note-on/off routines.

Only the queue is stubbed. Its six-byte message layout is status, routing,
port, 0xff, note, velocity. Stock note-off puts the track selector in the last
byte and passes queue selector zero; note-on passes the original selector.
"""
import json
import os
import struct
import sys
from collections import Counter
from functools import lru_cache

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_HOOK_CODE
from unicorn.arm_const import (
    UC_CPU_ARM_CORTEX_M7, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC,
    UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3,
    UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7,
    UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11,
)

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import verify
from asm import build

ROOT = os.path.join(HERE, '..')
CAVE = 0x08047600
NOTE_ON = 0x08019A2A
NOTE_OFF = 0x08019A5E
PAIR = 0x08019A92
STOCK_END = 0x08019ACE  # exclusive: includes pair's final b.w to note-off
QUEUE = 0x08019840
BASEARR = 0x08028230
TRACKBASE = 0x20008000
STRIDE = 0x194
POLY = 0x1000B530
SP = 0x20010000
SENTINEL = 0x2001FFF0
SAVED_REGS = (UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7,
              UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11)


@lru_cache(maxsize=1)
def images():
    with open(os.path.join(ROOT, 'testdata', 'gc326.hex')) as f:
        mem = verify.index(verify.parse(f.read()))
    # Direct indexing deliberately rejects missing stock bytes.
    stock_code = bytes(mem[a] for a in range(NOTE_ON, STOCK_END))
    with open(os.path.join(ROOT, 'mods', 'poly-fanout.source.json')) as f:
        bundle = build(json.load(f))
    cave = bytes.fromhex(next(p['bytes'] for p in bundle['patches']
                             if int(p['addr'], 16) == CAVE))
    return stock_code, cave


def queue_return(status, note):
    """Distinct queue results expose accidental return of an extra's result."""
    return 0xC0000000 | (note << 8) | status


def run(count, notes, track_id, step=0, primary=60, start=1000, dur=50,
        routing=7, velocity=100, entry=CAVE):
    stock_code, cave = images()
    u = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
    u.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_M7)
    for a, size in ((0x08000000, 0x80000), (0x10000000, 0x20000),
                    (0x20000000, 0x20000)):
        u.mem_map(a, size)
    u.mem_write(NOTE_ON, stock_code)
    u.mem_write(CAVE, cave)
    u.mem_write(QUEUE, b'\x70\x47')  # sole stub: bx lr
    u.mem_write(BASEARR, struct.pack('<I', TRACKBASE))
    for i in range(3): u.mem_write(0x20000450 + i*4, struct.pack('<I', TRACKBASE + i*STRIDE))

    voice = TRACKBASE + (track_id - 1) * STRIDE
    parent = voice
    u.mem_write(voice + 0x3C, bytes([step]))
    u.mem_write(voice + 4, bytes([routing]))
    u.mem_write(voice + 8, struct.pack('<I', parent))
    u.mem_write(parent + 0x1F, bytes([track_id]))
    record = bytes([count]) + bytes(b for note in notes for b in note)
    u.mem_write(POLY + (track_id - 1) * 0x880 + step * 17, record)
    u.mem_write(SP, struct.pack('<III', primary, velocity, track_id))

    saved = {r: 0x11220000 + i for i, r in enumerate(SAVED_REGS)}
    saved[UC_ARM_REG_R5] = voice
    regs = {**saved, UC_ARM_REG_SP: SP, UC_ARM_REG_R0: 0,
            UC_ARM_REG_R1: start, UC_ARM_REG_R2: dur,
            UC_ARM_REG_R3: routing, UC_ARM_REG_LR: SENTINEL | 1}
    for reg, value in regs.items():
        u.reg_write(reg, value)

    out = []
    hits = Counter()

    def hook(uc, addr, size, _):
        addr &= ~1
        assert (NOTE_ON <= addr < STOCK_END or CAVE <= addr < CAVE + len(cave)
                or addr == QUEUE), f'unexpected execution at 0x{addr:08x}'
        hits[addr] += 1
        if addr == QUEUE:
            msg = bytes(uc.mem_read(uc.reg_read(UC_ARM_REG_R1), 6))
            out.append((msg, uc.reg_read(UC_ARM_REG_R2),
                        uc.reg_read(UC_ARM_REG_R0)))
            uc.reg_write(UC_ARM_REG_R0, queue_return(msg[0], msg[4]))

    u.hook_add(UC_HOOK_CODE, hook)
    u.emu_start(entry | 1, SENTINEL, count=20000)
    assert u.reg_read(UC_ARM_REG_PC) == SENTINEL, 'instruction cap reached'
    assert u.reg_read(UC_ARM_REG_SP) == SP, 'stack pointer not restored'
    assert {r: u.reg_read(r) for r in saved} == saved, 'callee-saved registers changed'
    # Pair tail-calls note-off after replacing its first two incoming stack args.
    assert bytes(u.mem_read(SP, 12)) == struct.pack('<III', track_id, 0, track_id)
    return out, u.reg_read(UC_ARM_REG_R0), hits


def expected_messages(notes, track, start, duration, routing):
    out = []
    for note, velocity in notes:
        out.append((bytes([0x90, routing, 0, 0xFF, note, velocity]), track, start))
        out.append((bytes([0x80, routing, 0, 0xFF, note, track]), 0, start + duration))
    return out


def check(name, count, notes, track, emitted, **kwargs):
    out, result, hits = run(count, notes, track, **kwargs)
    start = kwargs.get('start', 1000)
    duration = kwargs.get('dur', 50)
    routing = kwargs.get('routing', 7)
    primary = kwargs.get('primary', 60)
    velocity = kwargs.get('velocity', 100)
    want = expected_messages(emitted, track, start, duration, routing)
    assert out == want, f'{name}: messages\n  got {out!r}\n want {want!r}'
    for addr in (PAIR, NOTE_ON, NOTE_OFF):
        assert hits[addr] == len(emitted), f'{name}: missing stock routine {addr:08x}'
    assert hits[QUEUE] == 2 * len(emitted)
    assert result == queue_return(0x80, primary), f'{name}: primary return lost'

    # Compare the primary's full observable result with a direct stock pair call.
    direct_kwargs = {**kwargs, 'entry': PAIR}
    direct, direct_result, _ = run(count, notes, track, **direct_kwargs)
    assert direct == expected_messages([(primary, velocity)], track, start, duration, routing)
    assert out[-2:] == direct and result == direct_result
    print(f'  {name}: OK ({len(out)} messages, primary return 0x{result:08x})')


def main():
    triad = [(60, 100), (64, 90), (67, 80)]
    emitted = [(64, 90), (67, 80), (60, 100)]
    check('triad extras before primary', 3, triad, 1, emitted)
    check('single note', 1, [(60, 100)], 1, [(60, 100)])
    check('track 2 step 7', 3, triad, 2, emitted, step=7,
          start=2345, dur=137, routing=11)
    check('empty poly', 0, [], 1, [(60, 100)])
    print('PASS (4/4)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
