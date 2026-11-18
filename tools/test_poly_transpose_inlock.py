#!/usr/bin/env python3
"""Chord-aware transpose, in-lock design.

Stock 0x08028194 rewrites only the step note bytes. The cave is hooked at
0x08028224, inside the lock interval stock holds while it edits, so nothing can
land between the note move and the record move. It replays the displaced
`strh.w r4,[ip,#0x38]`, shifts each step's chord record by the same delta,
drops record notes that would leave 1..126, and repairs a record whose lowest
note stopped matching the step's note.
"""
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from fw_sandbox import Sandbox, SENTINEL, SRAM
from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2,
                               UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_SP)

STOCK = 0x08028194
BANK = 0x1000B530
WRAP = 0x20000450
SLOT = {0: 'drum', 1: 'track1', 2: 'track2', 3: 'track3'}
TRACKS = {0: 0x20013DEC, 1: 0x200117C8, 2: 0x2000F1A4, 3: 0x2000CB80}
STACK = SRAM + 0x9000


def build(slot, letter, steps, records, offset_mode=0):
    sb = Sandbox()
    for page in (0x08048000, 0x08049000):
        try:
            sb.r(page, 4)
        except Exception:
            try:
                sb.uc.mem_map(page, 0x1000)
            except Exception:
                pass
    for p in json.load(open(ROOT / 'mods/poly-transpose-inlock.json'))['patches']:
        sb.w(int(p['addr'], 0), bytes.fromhex(p['bytes']))
    # stock takes an RTOS lock around the edit; stub lock and unlock
    sb.w(0x080232A0, bytes.fromhex('00207047'))
    sb.w(0x080232B0, bytes.fromhex('00207047'))
    track = TRACKS[slot]
    sb.w(track + 0x2D, bytes([1 if slot == 0 else 0]))
    sb.w(track + 0x2E, bytes([letter]))
    base = track + 0x34 + letter * 0x194 + 8
    for i in range(128):
        note = steps.get(i, 0x80)
        sb.w(base + i * 3, bytes([note, 100 if note != 0x80 else 0, 0]))
    for step, notes in records.items():
        rec = bytearray(17)
        rec[0] = len(notes)
        for k, n in enumerate(notes[:8]):
            rec[1 + 2 * k] = n
            rec[2 + 2 * k] = 90
        sb.w(BANK + slot * 0x880 + step * 17, bytes(rec))
    # stock dereferences the wrapper pointer, so every slot needs a real object
    for i in range(4):
        ptr = 0x20015000 + i * 0x300
        sb.w(WRAP + i * 4, struct.pack('<I', ptr))
        sb.w(ptr + 0x2DB, bytes([1 if (offset_mode and i == slot) else 0]))
    return sb, base


def run(sb, slot, delta):
    u = sb.uc
    u.reg_write(UC_ARM_REG_SP, STACK)
    u.reg_write(UC_ARM_REG_LR, SENTINEL | 1)
    u.reg_write(UC_ARM_REG_R0, 0)
    u.reg_write(UC_ARM_REG_R1, slot)
    u.reg_write(UC_ARM_REG_R2, delta & 0xFFFFFFFF)
    u.emu_start(STOCK | 1, SENTINEL, count=400000)
    assert u.reg_read(UC_ARM_REG_PC) == SENTINEL, 'did not return'
    return u.reg_read(UC_ARM_REG_R0)


def note_at(sb, base, step):
    return sb.r(base + step * 3, 1)[0]


def rec_at(sb, slot, step):
    rec = sb.r(BANK + slot * 0x880 + step * 17, 17)
    return [rec[1 + 2 * k] for k in range(rec[0])]


def main():
    fails = []

    def check(label, cond, detail=None):
        if cond:
            print(f'  PASS {label}')
        else:
            fails.append(label)
            print(f'  FAIL {label} {detail}')

    sb, base = build(1, 0, {0: 50}, {0: [50, 53, 57]})
    ok = run(sb, 1, 1)
    check('semitone: stock reports success', ok == 1, f'r0={ok}')
    check('semitone: note moves', note_at(sb, base, 0) == 51, note_at(sb, base, 0))
    check('semitone: record moves', rec_at(sb, 1, 0) == [51, 54, 58], rec_at(sb, 1, 0))

    sb, base = build(1, 0, {0: 50}, {0: [50, 53, 57]})
    run(sb, 1, -12)
    check('octave down: note', note_at(sb, base, 0) == 38, note_at(sb, base, 0))
    check('octave down: record', rec_at(sb, 1, 0) == [38, 41, 45], rec_at(sb, 1, 0))

    sb, base = build(1, 0, {0: 50}, {0: [50, 53, 57]})
    run(sb, 1, 12)
    check('octave up: note', note_at(sb, base, 0) == 62, note_at(sb, base, 0))
    check('octave up: record', rec_at(sb, 1, 0) == [62, 65, 69], rec_at(sb, 1, 0))

    # a record note that would leave range is dropped, not clamped
    sb, base = build(1, 0, {0: 20}, {0: [20, 24, 4]})
    run(sb, 1, -12)
    check('edge: note still moves', note_at(sb, base, 0) == 8, note_at(sb, base, 0))
    check('edge: bad note dropped', rec_at(sb, 1, 0) == [8, 12], rec_at(sb, 1, 0))

    # stock refuses an out-of-range pattern note; the record must not move
    sb, base = build(1, 0, {0: 5}, {0: [5, 8, 12]})
    ok = run(sb, 1, -12)
    check('refused: returns 0', ok == 0, f'r0={ok}')
    check('refused: note untouched', note_at(sb, base, 0) == 5, note_at(sb, base, 0))
    check('refused: record untouched', rec_at(sb, 1, 0) == [5, 8, 12], rec_at(sb, 1, 0))

    # drum has no record
    sb, base = build(0, 0, {0: 38}, {0: [38, 41]})
    run(sb, 0, 1)
    check('drum: record untouched', rec_at(sb, 0, 0) == [38, 41], rec_at(sb, 0, 0))

    # offset mode means stock stores an offset; the record must not move
    sb, base = build(1, 0, {0: 50}, {0: [50, 53]}, offset_mode=1)
    run(sb, 1, 1)
    check('offset mode: record untouched', rec_at(sb, 1, 0) == [50, 53], rec_at(sb, 1, 0))

    # a record that already disagrees with its step is repaired
    sb, base = build(1, 0, {0: 50}, {0: [57, 60]})
    run(sb, 1, 1)
    check('desync repaired: note', note_at(sb, base, 0) == 51, note_at(sb, base, 0))
    check('desync repaired: record collapses to the note',
          rec_at(sb, 1, 0) == [51], rec_at(sb, 1, 0))

    # an empty step must not keep a chord
    sb, base = build(1, 0, {}, {0: [50, 53]})
    run(sb, 1, 1)
    check('stale record on empty step cleared', rec_at(sb, 1, 0) == [], rec_at(sb, 1, 0))


    # a chord whose first stored note is not its lowest must survive transposition
    sb, base = build(1, 0, {0: 60}, {0: [67, 60, 64]})
    run(sb, 1, 1)
    check('entered chord order: note', note_at(sb, base, 0) == 61, note_at(sb, base, 0))
    check('entered chord order: all voices kept',
          sorted(rec_at(sb, 1, 0)) == [61, 65, 68], rec_at(sb, 1, 0))

    # a voice dropped at the top must not come back on a later transpose
    sb, base = build(1, 0, {0: 110}, {0: [110, 120, 126]})
    run(sb, 1, 1)
    after_up = rec_at(sb, 1, 0)
    run(sb, 1, -1)
    after_down = rec_at(sb, 1, 0)
    check('dropped voice stays dropped', 125 not in after_down, f'{after_up} -> {after_down}')

    # stale pairs beyond the declared count must be ignored, not resurrected
    sb, base = build(1, 0, {0: 60}, {0: [60, 64, 67]})
    sb.w(BANK + 1 * 0x880 + 7, bytes([99, 90]))   # garbage past count 3
    run(sb, 1, 1)
    check('stale tail ignored', sorted(rec_at(sb, 1, 0)) == [61, 65, 68], rec_at(sb, 1, 0))

    if fails:
        print(f'\nFAIL {len(fails)}: {fails}')
        return 1
    print('\nPASS transpose moves records in-lock, drops bad notes, repairs desync')
    return 0


if __name__ == '__main__':
    sys.exit(main())
