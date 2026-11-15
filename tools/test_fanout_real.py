#!/usr/bin/env python3
"""Execute the fan-out cave through stock pair and note-on/off routines.

Legacy contract cases stub the queue; saturation regressions execute the real
queue insertion, sorting, and due-event drain. Its six-byte message layout is status, routing,
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
from test_poly_module_only import cache_setup

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
    stock_code = bytearray(stock_code)
    for patch in bundle['patches']:
        addr = int(patch['addr'], 16)
        if NOTE_ON <= addr < STOCK_END:
            data = bytes.fromhex(patch['bytes'])
            stock_code[addr-NOTE_ON:addr-NOTE_ON+len(data)] = data
    return bytes(stock_code), cave


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
    cache_setup(u, (TRACKBASE-STRIDE, *(TRACKBASE + i*STRIDE for i in range(3))))

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
                or 0x0804A1C0 <= addr < 0x0804A280 or addr == QUEUE), f'unexpected execution at 0x{addr:08x}'
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



class RealQueue:
    """Real firmware ring, stock pair and fanout; only final MIDI delivery is stubbed."""
    BASE = 0x10007010

    def __init__(self, guarded=True, head=0):
        from fw_sandbox import Sandbox
        from test_poly_module_only import install
        self.sb = Sandbox()
        self.original_pair = self.sb.r(PAIR, 4)
        self.original_queue = self.sb.r(QUEUE, 4)
        install(self.sb, 'poly-fanout')
        cache_setup(self.sb.uc)
        if not guarded:
            self.sb.w(PAIR, self.original_pair)
            self.sb.w(QUEUE, self.original_queue)
        self.parents = struct.unpack('<4I', self.sb.r(0x08038370, 16))
        self.sb.call(0x08019BF0)
        self.sb.w(self.BASE+0xA00, struct.pack('<II', head, head))
        self.delivered = []
        self.sb.w(0x08019D98, bytes.fromhex('7047'))
        def delivery(u, a, n, _):
            ptr = u.reg_read(UC_ARM_REG_R0)
            self.delivered.append((self.sb.r(ptr, 6), int.from_bytes(self.sb.r(ptr+8, 4), 'little')))
        self.sb.uc.hook_add(UC_HOOK_CODE, delivery, begin=0x08019D98, end=0x08019D98)

    def enqueue(self, message, tick=50, selector=0):
        self.sb.w(0x20007000, message)
        self.sb.call(QUEUE, regs={UC_ARM_REG_R0:tick, UC_ARM_REG_R1:0x20007000, UC_ARM_REG_R2:selector})
        assert self.sb.reg(UC_ARM_REG_PC) == 0x2001F000

    def play(self, track=1, tick=1000, notes=tuple(range(60, 68))):
        from fw_sandbox import STACKTOP
        voice = 0x20008000
        self.sb.w(voice+8, struct.pack('<I', self.parents[track]))
        self.sb.w(voice+0x3C, b'\0')
        self.sb.w(POLY+(track-1)*2176, bytes([len(notes)]+[v for note in notes for v in (note,90)]))
        self.sb.w(STACKTOP, struct.pack('<III', notes[0], 90, track))
        self.sb.call(CAVE, regs={UC_ARM_REG_R0:0, UC_ARM_REG_R1:tick, UC_ARM_REG_R2:50,
                               UC_ARM_REG_R3:7, UC_ARM_REG_R5:voice}, max_steps=2000000)
        assert self.sb.reg(UC_ARM_REG_PC) == 0x2001F000

    def entries(self):
        head, tail = struct.unpack('<II', self.sb.r(self.BASE+0xA00, 8))
        return [self.sb.r(self.BASE+((head+i)&127)*20, 20) for i in range((tail-head)&127)]

    def drain(self, tick=100000):
        self.sb.call(0x08019BBC, regs={UC_ARM_REG_R0:tick}, max_steps=2000000)
        assert self.sb.reg(UC_ARM_REG_PC) == 0x2001F000
        assert not self.entries()
        return self.delivered


def test_real_queue_capacity():
    off = bytes([0x80,7,0,255,99,3])
    # First demonstrate the original 8 notes x 8 ratchets x 2 messages failure.
    original = RealQueue(guarded=False)
    for ratchet in range(8): original.play(tick=1000+ratchet*100)
    assert original.entries() == [], 'unprotected ring must reproduce head==tail wrap'
    original = RealQueue(guarded=False)
    original.enqueue(off)
    for ratchet in range(8): original.play(tick=1000+ratchet*100)
    assert off not in [e[:6] for e in original.entries()], 'original bug lost pending unrelated off'

    # Repeat with real queue sorting and insertion, arbitrary wrap positions,
    # unrelated existing events, every ratchet and all three melodic tracks.
    for occupied in (0, 1, 124, 125, 126, 127):
        q = RealQueue(head=113)
        previous = []
        for i in range(occupied):
            message = off if i == 0 else bytes([0x80,7,0,255,20+i%30,2])
            q.enqueue(message, tick=50+i)
            previous.append(message)
        before = q.entries()
        for track in (1, 2, 3):
            for ratchet in range(8):
                q.play(track, tick=1000+ratchet*100)
                assert len(q.entries()) <= 127
        entries = q.entries()
        if len(entries) == 127:
            q.enqueue(bytes([0xF8,7,0,255,0,0]), tick=2000)
            assert q.entries() == entries, 'non-pair insertion overwrote a pending event'
        assert len(entries) == occupied + 2*((127-occupied)//2)
        # Every pre-existing event remains byte-for-byte, including its sequence id.
        assert entries[:occupied] == before
        scheduled = entries[occupied:]
        pairs = Counter((e[4], e[1], e[5] if e[0] == 0x80 else e[13], int.from_bytes(e[8:12], 'little')-(50 if e[0] == 0x80 else 0))
                        for e in scheduled)
        assert all(count == 2 for count in pairs.values()), 'partial on/off pair admitted'
        assert Counter(e[0] for e in scheduled)[0x90] == len(scheduled)//2
        drained = q.drain()
        assert [m for m,t in drained[:occupied]] == previous
        assert len(drained) == len(entries)
        if occupied: assert (off,50) in drained
    print('  real queue saturation: OK (original wrap reproduced; complete pairs and pending offs preserved)')


def main():
    triad = [(60, 100), (64, 90), (67, 80)]
    emitted = [(64, 90), (67, 80), (60, 100)]
    check('triad extras before primary', 3, triad, 1, emitted)
    check('single note', 1, [(60, 100)], 1, [(60, 100)])
    check('track 2 step 7', 3, triad, 2, emitted, step=7,
          start=2345, dur=137, routing=11)
    check('empty poly', 0, [], 1, [(60, 100)])
    check('corrupt count 9 falls back to mono', 9, triad, 1, [(60, 100)])
    check('corrupt count 255 falls back to mono', 255, triad, 1, [(60, 100)])
    check('stale primary does not fan out', 3, triad, 1, [(62, 100)], primary=62)
    test_real_queue_capacity()
    print('PASS (8/8)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
