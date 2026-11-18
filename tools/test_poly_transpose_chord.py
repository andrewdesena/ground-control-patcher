#!/usr/bin/env python3
"""Chord-aware transpose: the step's chord record must move with its note.

Stock 0x08028194 rewrites only the note byte of every step, so transposing a
chord desyncs the record at 0x1000B530 + index*0x880. The cave at 0x08048C00
wraps that routine: it validates the whole pattern and every record first, then
lets stock move the notes and moves the record by the same delta.

Cases: semitone up, octave down, an out-of-range octave that must change
nothing, the drum, and a step whose recorded chord would leave range while the
pattern note would not.
"""
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from fw_sandbox import Sandbox, SENTINEL, SRAM
from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2,
                               UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC)

HOOK = 0x08048C00
TABLE = 0x08038370
BANK = 0x1000B530
DRUM, T1, T2, T3 = 0x20013DEC, 0x200117C8, 0x2000F1A4, 0x2000CB80
STACK = SRAM + 0x9000


def build(index, letter, steps, records, kind=0, transpose_mode=0):
    sb = Sandbox()
    # the stock image stops short of the cave page; extend flash so the cave can execute
    for page in (0x08048000, 0x08049000):
        try:
            sb.r(page, 4)
        except Exception:
            try:
                sb.uc.mem_map(page, 0x1000)
            except Exception:
                pass
    import json
    for p in json.load(open(ROOT / 'mods/poly-transpose-rec.json'))['patches']:
        sb.w(int(p['addr'], 0), bytes.fromhex(p['bytes']))
    # stock takes an RTOS lock around the edit; stub lock and unlock so the call returns
    sb.w(0x080232A0, bytes.fromhex('00207047'))
    sb.w(0x080232B0, bytes.fromhex('00207047'))
    sb.w(TABLE, struct.pack('<4I', DRUM, T1, T2, T3))
    track = (DRUM, T1, T2, T3)[index]
    sb.w(track + 0x2D, bytes([kind]))
    sb.w(track + 0x2E, bytes([letter]))
    # stock resolves track state through the wrapper table at 0x20000450
    for i in range(4):
        ptr = 0x20015000 + i * 0x300
        sb.w(0x20000450 + i * 4, struct.pack('<I', ptr))
        sb.w(ptr + 0x2DB, bytes([transpose_mode]))
    base = track + 0x3C + letter * 0x194
    for i in range(128):
        note = steps.get(i, 0x80)
        sb.w(base + i * 3, bytes([note, 100 if note != 0x80 else 0, 0]))
    for step, notes in records.items():
        rec = bytearray(17)
        rec[0] = len(notes)
        for k, n in enumerate(notes[:8]):
            rec[1 + 2 * k] = n
            rec[2 + 2 * k] = 90
        sb.w(BANK + index * 0x880 + step * 17, bytes(rec))
    return sb, base, track


def run(sb, index, delta):
    u = sb.uc
    u.reg_write(UC_ARM_REG_SP, STACK)
    u.reg_write(UC_ARM_REG_LR, SENTINEL | 1)
    u.reg_write(UC_ARM_REG_R0, 0)
    u.reg_write(UC_ARM_REG_R1, index)
    u.reg_write(UC_ARM_REG_R2, delta & 0xFF)
    u.emu_start(HOOK | 1, SENTINEL, count=300000)
    assert u.reg_read(UC_ARM_REG_PC) == SENTINEL, 'did not return'
    return u.reg_read(UC_ARM_REG_R0)


def notes_of(sb, base, step):
    return sb.r(base + step * 3, 1)[0]


def record_of(sb, index, step):
    rec = sb.r(BANK + index * 0x880 + step * 17, 17)
    return [rec[1 + 2 * k] for k in range(rec[0])]


def main():
    fails = []

    def check(label, cond, detail=''):
        if cond:
            print(f'  PASS {label}')
        else:
            fails.append(label)
            print(f'  FAIL {label} {detail}')

    # 1. semitone up: both the note byte and the record move
    sb, base, track = build(1, 0, {0: 50, 4: 46}, {0: [50, 53, 57], 4: [46, 50, 53]})
    ok = run(sb, 1, 1)
    check('semitone up returns success', ok == 1, f'r0={ok}')
    check('note byte +1', notes_of(sb, base, 0) == 51, notes_of(sb, base, 0))
    check('record +1', record_of(sb, 1, 0) == [51, 54, 58], record_of(sb, 1, 0))
    check('second step +1', (notes_of(sb, base, 4), record_of(sb, 1, 4)) == (47, [47, 51, 54]))

    # 2. octave down: still in range, everything moves by -12
    sb, base, track = build(1, 0, {0: 50}, {0: [50, 53, 57]})
    run(sb, 1, -12)
    check('octave down note', notes_of(sb, base, 0) == 38, notes_of(sb, base, 0))
    check('octave down record', record_of(sb, 1, 0) == [38, 41, 45], record_of(sb, 1, 0))

    # 3. octave down out of range: nothing may change anywhere
    sb, base, track = build(1, 0, {0: 5}, {0: [5, 8, 12]})
    ok = run(sb, 1, -12)
    check('out of range returns 0', ok == 0, f'r0={ok}')
    check('out of range note untouched', notes_of(sb, base, 0) == 5, notes_of(sb, base, 0))
    check('out of range record untouched', record_of(sb, 1, 0) == [5, 8, 12], record_of(sb, 1, 0))

    # 4. a record note below range while the pattern note is fine: validate must fail
    sb, base, track = build(1, 0, {0: 20}, {0: [20, 4, 27]})
    ok = run(sb, 1, -12)
    check('record range failure returns 0', ok == 0, f'r0={ok}')
    check('record range failure leaves note', notes_of(sb, base, 0) == 20, notes_of(sb, base, 0))
    check('record range failure leaves record', record_of(sb, 1, 0) == [20, 4, 27], record_of(sb, 1, 0))

    # 5. drum: pattern may move, the record is not touched
    sb, base, track = build(0, 0, {0: 38}, {0: [38, 41]}, kind=1)
    run(sb, 0, 1)
    check('drum record untouched', record_of(sb, 0, 0) == [38, 41], record_of(sb, 0, 0))

    # 6. stock's offset mode (+0x2DB set) must not shift the record
    sb, base, track = build(1, 0, {0: 50}, {0: [50, 53]}, transpose_mode=1)
    run(sb, 1, 1)
    check('offset-mode record untouched', record_of(sb, 1, 0) == [50, 53], record_of(sb, 1, 0))

    if fails:
        print(f'\nFAIL {len(fails)}: {fails}')
        return 1
    print('\nPASS transpose moves the chord record with the note')
    return 0


if __name__ == '__main__':
    sys.exit(main())
