#!/usr/bin/env python3
"""Physical keys -> real UI page -> input transforms -> queue -> EDIT writer.

Boots stock constructors and opens the real editor, then installs the v1.9 base
and the contributed overlay. Only existing UART/SPI stubs from the lights bench
are used. No note producer, quantizer, queue, editor callback or writer is stubbed.
"""
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
import asm
from fw_sandbox import STACKTOP, Sandbox
from test_poly_editlights6 import setup, apply, run, u32, EDITOR, PAGE, BANK, PARENTS, REGS, render, commit, frame, stock_bits
from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn.arm_const import *

SOURCE = ROOT / 'mods/poly-edit-entry-held.source.json'
SETTINGS = 0x2001BB38
CAVE = 0x08049C00
DELTA = 0x08049DE0


def bench(track=1, letter=0, octave=0, scale=0, root=0, snap=0, delta=0, patched=True):
    sb = setup(track=track, letter=letter, primary=128, octave=octave)
    apply(sb, 'v1-poly-dub')
    if patched:
        apply(sb, 'v1-poly-v111')
    # Distinct input channels avoid the stock default channel-0 broadcast.
    sb.w(SETTINGS + 0xB9, bytes(range(4)))
    sb.w(SETTINGS + 0xE0, struct.pack('<I', snap))
    off = (track - 1) * 14
    sb.w(SETTINGS + 0x196 + off, bytes([scale, root]))
    sb.w(0x2000B5A9 + track, bytes([delta & 255]))
    sb.w(0x2000B614, b'\xff' * 60)  # initially empty raw/transposed held pairs
    sb.w(0x2000B650, b'\xff' * 30)  # initially empty quantized held lists
    # Real user EDIT-open command registers the wrapper in the event bus.
    run(sb, 0x0802D4E8, {UC_ARM_REG_R0: 0x2001C388, UC_ARM_REG_R1: 1})
    run(sb, 0x08019CF0)
    sb.track, sb.letter, sb.step = track, letter, 0
    sb.pattern = u32(sb, EDITOR + 8)
    sb.record = BANK + track * 0x880
    sb.hits = []
    sb.active = False
    sb.cave_writes = []
    sb.writer_calls = 0

    def code(uc, addr, size, _):
        if addr in (CAVE, DELTA):
            sb.active = True
            sb.saved_regs = [uc.reg_read(r) for r in REGS]
            sb.saved_sp = uc.reg_read(UC_ARM_REG_SP)
            assert sb.saved_sp % 8 == 0
            sb.hits.append(addr)
            sb.resume = 0x080275C4 if addr == CAVE else 0x080277D8
        if patched and sb.active and addr == sb.resume:
            assert sb.active, 'real EDIT write skipped cave'
            assert [uc.reg_read(r) for r in REGS] == sb.saved_regs
            assert uc.reg_read(UC_ARM_REG_SP) == sb.saved_sp
            sb.active = False
        if sb.active and addr == 0x0802705C:
            sb.writer_calls += 1
        if sb.active and (CAVE <= addr < 0x08049DA4 or 0x08049DB0 <= addr < 0x0804A000):
            ins = sb.dis(addr, size)[0]
            if ins.mnemonic in ('bl', 'blx'):
                assert uc.reg_read(UC_ARM_REG_SP) % 8 == 0, hex(addr)
        if sb.active and addr == 0x0802705C:
            assert uc.reg_read(UC_ARM_REG_SP) % 8 == 0
        # FatFS open/read/write/close must never be used by the cave.
        if sb.active:
            assert addr not in (0x0801496C, 0x08014C92, 0x08014F18)

    def write(uc, access, addr, size, value, _):
        if not sb.active:
            return
        # Stack includes the incoming three-byte record; the final stock writer
        # is included in this observation window.
        allowed = ((STACKTOP - 768 <= addr and addr + size <= STACKTOP)
                   or (sb.record <= addr and addr + size <= sb.record + 17)
                   or (sb.pattern + 4 <= addr and addr + size <= sb.pattern + 6)
                   or (sb.pattern + 8 + 3*sb.step <= addr and addr + size <= sb.pattern + 11 + 3*sb.step))
        assert allowed, (hex(addr), hex(uc.reg_read(UC_ARM_REG_PC)))
        sb.cave_writes.append(addr)

    sb.uc.hook_add(UC_HOOK_CODE, code)
    sb.uc.hook_add(UC_HOOK_MEM_WRITE, write)
    return sb


def key(sb, kind, ident):
    # Execute the actual UI task's physical-event branch. Its loop frame has
    # event bytes at sp+4 and r4 points at the current page holder.
    sb.w(STACKTOP + 4, bytes([kind, ident]))
    run(sb, 0x080207D0, {UC_ARM_REG_R4: PAGE}, stop=0x08020786)
    run(sb, 0x08019CF0)  # real event ring and registered EDIT callback
    assert not sb.active


def chord(sb):
    data = sb.r(sb.record, 17)
    assert data[0] <= 8
    pairs = [(data[1 + 2*i], data[2 + 2*i]) for i in range(data[0])]
    assert all(1 <= n <= 127 and 1 <= v <= 127 for n, v in pairs), pairs
    return pairs


def check(sb, notes, modifier=0):
    got = chord(sb)
    assert set(n for n, v in got) == set(notes), (got, notes)
    assert len(got) == len(set(n for n, v in got)), got
    assert all(v == 127 for n, v in got), got
    primary = min(notes) if notes else 128
    assert sb.r(sb.pattern + 8 + 3*sb.step, 3) == bytes([primary, 127, modifier])
    assert sb.r(sb.pattern + 4, 2) == b'\x01\x00'
    assert sb.r(0x2001CDFC, 1) == bytes([primary]), 'stock display cache stale'
    assert sb.hits, 'cave was never reached'


def playback(sb, notes):
    # Stock sequencer argument setup and installed fan-out call. Queue insertion
    # and sorting execute normally; inspect the resulting real scheduler ring.
    run(sb, 0x08019BF0)
    voice = 0x2001E100
    sb.w(voice + 8, struct.pack('<I', PARENTS[sb.track]))
    sb.w(voice + 4, b'\x07')
    sb.w(voice + 0x3C, bytes([sb.step]))
    run(sb, 0x080217DE, {UC_ARM_REG_R5: voice,
                          UC_ARM_REG_R7: sb.pattern + 8 + 3*sb.step,
                          UC_ARM_REG_R6: 1000, UC_ARM_REG_R4: 50},
        stop=0x080217F8)
    head, tail = struct.unpack('<II', sb.r(0x10007A10, 8))
    entries = [sb.r(0x10007010 + ((head+i) & 127) * 20, 20)
               for i in range((tail-head) & 127)]
    assert len(entries) == 2 * len(notes), [e[:6].hex() for e in entries]
    for status, tick in ((0x90, 1000), (0x80, 1050)):
        messages = [e for e in entries if e[0] == status]
        assert {e[4] for e in messages} == set(notes)
        assert all(int.from_bytes(e[8:12], 'little') == tick for e in messages)


def delta_edit(sb, delta):
    # Real event-type1/subtype1 callback, including stock uxtab and stack record.
    # Stock dispatches this action in record mode; use the same selected step.
    run(sb, 0x08023418)
    selector = sb.reg(UC_ARM_REG_R0)
    event = 0x2001E040
    sb.w(event, bytes([1, selector, 0, 0, 1, delta & 255]))
    mode = sb.r(EDITOR + 4, 1)
    sb.w(EDITOR + 4, b'\0')
    run(sb, 0x08027564, {UC_ARM_REG_R0: EDITOR, UC_ARM_REG_R1: event})
    sb.w(EDITOR + 4, mode)
    assert not sb.active
    assert DELTA in sb.hits, 'real delta action skipped guard'


def unchanged_by_delta(sb, delta):
    pattern, record, calls = sb.r(sb.pattern, 0x194), sb.r(sb.record, 17), sb.writer_calls
    delta_edit(sb, delta)
    assert sb.r(sb.pattern, 0x194) == pattern
    assert sb.r(sb.record, 17) == record
    assert sb.writer_calls == calls, 'refused delta invoked stock writer'


def main():
    built = asm.build(json.loads(SOURCE.read_text()))
    expected = json.loads((ROOT / 'mods/poly-edit-entry-held.json').read_text())
    assert built == expected, 'assembled bundle is stale'
    stock_sites = json.loads((ROOT / 'mods/v1-poly-dub.json').read_text())['patches']
    for p in built['patches']:
        a, n = int(p['addr'], 0), len(bytes.fromhex(p['bytes']))
        for q in stock_sites:
            b, m = int(q['addr'], 0), len(bytes.fromhex(q['bytes']))
            assert max(a, b) >= min(a+n, b+m), 'overlap with v1.9'
    assert len(bytes.fromhex(built['patches'][0]['bytes'])) <= 0x1A4
    for p in built['patches']:
        addr, size = int(p['addr'], 0), len(bytes.fromhex(p['bytes']))
        if addr >= CAVE:
            assert addr == CAVE or addr >= 0x08049DB0
            assert addr + size <= 0x0804A000
    delta_hook = next(p for p in built['patches'] if int(p['addr'], 0) == 0x080277D4)
    original_delta = Sandbox()
    assert original_delta.dis(0x080277D4, 4)[0].op_str == '#0x802705c'
    original_delta.w(0x080277D4, bytes.fromhex(delta_hook['bytes']))
    assert original_delta.dis(0x080277D4, 4)[0].op_str == f'#{DELTA:#x}'
    original = Sandbox()
    cave_bytes = bytes.fromhex(built['patches'][0]['bytes'])
    assert original.r(CAVE, len(cave_bytes)) == b'\xff' * len(cave_bytes)
    for p in built['patches']:
        addr, data = int(p['addr'], 0), bytes.fromhex(p['bytes'])
        if addr >= CAVE:
            assert original.r(addr, len(data)) == b'\xff' * len(data)
    ordered = sorted((int(p['addr'], 0), len(bytes.fromhex(p['bytes'])))
                     for p in json.loads((ROOT / 'mods/v1-poly-v111.json').read_text())['patches'])
    assert all(a+n <= b for (a, n), (b, _) in zip(ordered, ordered[1:]))
    assert original.dis(0x080275C0, 4)[0].op_str == '#0x802705c'
    combined = {int(p['addr'], 0): p['bytes'] for p in json.loads(
        (ROOT / 'mods/v1-poly-v111.json').read_text())['patches']}
    for p in stock_sites + built['patches']:
        assert combined[int(p['addr'], 0)] == p['bytes'], 'candidate bundle diverges'


    # Negative control executes the same chain without the cave. The assertion
    # for a chord must fail; this prevents a harness that models the patch away.
    sb = bench(patched=False)
    key(sb, 1, 4)
    key(sb, 1, 6)
    assert sb.r(sb.pattern + 8, 1) == b'\x40'
    assert chord(sb) != [(60, 127), (64, 127)]
    print('PASS negative control: stock replaces C with E')

    sb = bench()
    sb.w(CAVE, bytes.fromhex('7047'))  # deliberate broken-cave mutation
    key(sb, 1, 4)
    detected = False
    try:
        check(sb, (60,))
    except AssertionError:
        detected = True
    assert detected, 'broken cave escaped the chord assertions'
    print('PASS mutation control: a no-op cave fails the chord assertion')


    for track in (1, 2, 3):
        for letter in (0, 23):
            sb = bench(track=track, letter=letter)
            before = sb.r(BANK, 4 * 0x880)
            sb.w(sb.pattern + 10, b'\xa6')
            key(sb, 1, 8)   # G first, then lower notes
            check(sb, (67,), 0xA6)
            key(sb, 1, 4)
            check(sb, (60, 67), 0xA6)
            key(sb, 1, 6)
            check(sb, (60, 64, 67), 0xA6)
            playback(sb, (60, 64, 67))
            render(sb)
            commit(sb)
            assert frame(sb) & (set(range(24)) | {31}) == stock_bits(sb, (60, 64, 67))
            key(sb, 1, 6)   # repeated E cannot duplicate
            check(sb, (60, 64, 67), 0xA6)
            for k in (4, 6, 8):
                key(sb, 2, k)
            assert sb.r(0x20001C84, 3) == b'\0\0\0'
            check(sb, (60, 64, 67), 0xA6)  # releases leave stored chord
            key(sb, 1, 9)  # a new, separate gesture replaces the old chord
            check(sb, (69,), 0xA6)
            for i in range(4):
                if i != track:
                    assert sb.r(BANK+i*0x880, 0x880) == before[i*0x880:(i+1)*0x880]
            assert sb.r(sb.record+17, 0x880-17) == before[track*0x880+17:(track+1)*0x880]
            print(f'PASS physical EDIT entry, duplicate, release, replace: track{track}, letter{letter}')

    sb = bench(octave=1)
    for k in (4, 6, 8):
        key(sb, 1, k)
    check(sb, (72, 76, 79))
    print('PASS stock octave latch maps held notes')

    sb = bench()
    key(sb, 1, 4)
    sb.w(0x2001CDE8, b'\x01')  # octave changes while C remains held
    key(sb, 1, 6)
    check(sb, (60, 76))
    print('PASS each held key retains its original octave')

    sb = bench()
    key(sb, 1, 4)
    sb.w(0x2000B5AA, b'\x03')  # input transpose changes while C remains held
    key(sb, 1, 6)
    check(sb, (60, 67))
    print('PASS existing raw/transposed mapping survives input-delta changes')

    sb = bench(track=3, letter=23)
    sb.step = 127
    sb.record += 127 * 17
    sb.w(EDITOR + 7, b'\x7f')
    sb.w(sb.pattern + 0x188, struct.pack('<HH', 128, 128))
    sb.w(sb.pattern + 8 + 127*3, b'\x80\0\0')
    run(sb, 0x080273B4, {UC_ARM_REG_R0: EDITOR})
    for k in (4, 6, 8):
        key(sb, 1, k)
    check(sb, (60, 64, 67))
    playback(sb, (60, 64, 67))
    print('PASS track3, letterX, final step127 offset and playback')


    sb = bench(scale=1, snap=1, delta=1)
    key(sb, 1, 0)  # 53 + 1 -> 54, C-major snap up -> 55
    key(sb, 1, 4)  # 60 + 1 -> 61, snap up -> 62
    check(sb, (55, 62))
    print('PASS real input transpose and C-major snapping on entered and held notes')

    sb = bench(scale=1, root=2, snap=1)
    key(sb, 1, 4)  # C -> C# in D major
    key(sb, 1, 6)  # E remains E
    check(sb, (61, 64))
    print('PASS nonzero root D-major snapping')

    sb = bench(scale=1, snap=1)
    key(sb, 1, 0)   # F -> F
    key(sb, 1, 14)  # F# -> G
    key(sb, 1, 1)   # G -> G: quantizer collision
    check(sb, (53, 55))
    print('PASS quantized held-note collisions deduplicate')

    sb = bench(scale=1, snap=0)
    key(sb, 1, 14)  # F# rejected; held bit remains set
    key(sb, 1, 4)
    check(sb, (60,))
    print('PASS rejected out-of-scale held note is omitted')

    # An entered zero must return without calling the original writer, including
    # when other valid keys are held. The rejected event preserves both stores.
    sb = bench(delta=-64)
    before = (sb.r(sb.pattern, 0x194), sb.r(sb.record, 17))
    key(sb, 1, 4)  # physical C -> saturated input zero
    assert sb.hits and sb.writer_calls == 0
    assert (sb.r(sb.pattern, 0x194), sb.r(sb.record, 17)) == before
    print('PASS entered zero rejected without stock writer or stored-state changes')
    key(sb, 1, 8)  # G -> 3, while zero-valued C is still held
    check(sb, (3,))
    playback(sb, (3,))
    print('PASS held zero skipped while a valid entered note builds the chord')
    key(sb, 2, 4)
    before = (sb.r(sb.pattern, 0x194), sb.r(sb.record, 17), sb.writer_calls)
    key(sb, 1, 4)  # reject zero even though G is still held
    assert (sb.r(sb.pattern, 0x194), sb.r(sb.record, 17), sb.writer_calls) == before
    print('PASS entered zero with valid held notes still refuses the entire event')

    # Fault the staged record just before its validation. The real producer,
    # quantizer, append helper and publisher still execute.
    min_addr = next(i.address for i in original_delta.md.disasm(cave_bytes, CAVE)
                    if i.mnemonic == 'ldrb.w' and i.op_str == 'r2, [r8]')
    for label, change, accepted in (
        ('empty staging', lambda b: bytes(17), False),
        ('oversize staging', lambda b: bytes([9]) + b[1:], False),
        ('declared zero note', lambda b: b[:1] + b'\0' + b[2:], False),
        ('declared invalid velocity', lambda b: b[:2] + b'\x80' + b[3:], False),
        ('undeclared garbage ignored', lambda b: b[:3] + b'\xff'*14, True),
    ):
        sb = bench()
        before = (sb.r(sb.pattern, 0x194), sb.r(sb.record, 17))
        def fault(uc, addr, size, _, sb=sb, change=change):
            if addr == min_addr:
                ptr = uc.reg_read(UC_ARM_REG_R8)
                sb.w(ptr, change(sb.r(ptr, 17)))
        h = sb.uc.hook_add(UC_HOOK_CODE, fault)
        key(sb, 1, 4)
        sb.uc.hook_del(h)
        if accepted:
            check(sb, (60,))
        else:
            assert sb.writer_calls == 0
            assert (sb.r(sb.pattern, 0x194), sb.r(sb.record, 17)) == before
        print(f'PASS staging validation: {label}')

    for track, letter, step in ((1, 0, 0), (2, 23, 0), (3, 23, 127)):
        sb = bench(track=track, letter=letter)
        sb.step = step
        sb.record += step * 17
        sb.w(EDITOR + 7, bytes([step]))
        sb.w(sb.pattern + 0x188, struct.pack('<HH', 128, 128))
        for k in (4, 6, 8):
            key(sb, 1, k)
        for d in (1, -1, 12, -12):
            unchanged_by_delta(sb, d)
            check(sb, (60, 64, 67))
        playback(sb, (60, 64, 67))
        print(f'PASS delta refuses C/E/G unchanged: track{track}, letter{letter}, step{step}')

    sb = bench()
    key(sb, 1, 4)
    # Corrupt unused pairs must not invalidate the single declared pair.
    sb.w(sb.record + 3, b'\xff' * 14)
    delta_edit(sb, 1)
    check(sb, (61,))
    delta_edit(sb, -1)
    check(sb, (60,))
    print('PASS delta singleton updates primary and declared record, ignores unused pairs')
    for raw in (bytes([9])+bytes(16), bytes([1, 0, 127])+bytes(14),
                bytes([1, 60, 0])+bytes(14), bytes([1, 60, 128])+bytes(14),
                bytes([1, 64, 127])+bytes(14)):
        sb.w(sb.record, raw)
        unchanged_by_delta(sb, 1)
    print('PASS delta fails closed for invalid count, declared note/velocity or mismatched primary')

    for old, d in ((1, -1), (127, 1), (1, -2), (127, 127)):
        sb = bench()
        sb.w(sb.pattern + 8, bytes([old, 127, 0]))
        sb.w(sb.record, bytes([1, old, 127]) + bytes(14))
        unchanged_by_delta(sb, d)
    print('PASS delta rejects zero, out-of-range and wrapped singleton proposals')
    sb = bench()
    sb.w(sb.pattern + 8, bytes([60, 127, 0]))
    sb.w(sb.record, bytes(17))
    delta_edit(sb, 1)
    assert sb.r(sb.pattern + 8, 3) == bytes([61, 127, 0])
    assert sb.r(sb.record, 17) == bytes(17)
    print('PASS delta preserves stock editing for steps without a chord record')

    sb = bench()
    # Ascending physical white keys keep the minimum stable and exceed cap.
    for k in range(10):
        key(sb, 1, k)
        assert len(chord(sb)) <= 8
    got = chord(sb)
    assert 69 in dict(got), 'newly entered note lost at cap'
    assert len(got) == 8
    assert sb.r(sb.pattern+8, 1)[0] == min(dict(got))
    unchanged_by_delta(sb, 1)
    assert sb.r(sb.pattern+8, 1)[0] == min(dict(chord(sb)))
    print('PASS eight-note cap retains entered note and lowest primary after delta refusal')

    sb = bench()
    for k in (4, 6, 8):
        key(sb, 1, k)
    for k in (4, 6, 8):
        key(sb, 2, k)
    key(sb, 1, 4)  # stock re-press of raw primary invokes note128 clear path
    check(sb, ())
    assert sb.r(sb.record, 17) == bytes(17)
    print('PASS physical stock clear also clears entire sidecar record')
    # Remove the held-zero lower-bound branch. Validation then refuses the
    # entire G event instead of accepting G while omitting held C; detect it.
    sb = bench(delta=-64)
    key(sb, 1, 4)
    held_guard = next(i.address for i in sb.dis(CAVE, len(cave_bytes))
                      if i.mnemonic == 'blo' and i.address < min_addr)
    sb.w(held_guard, bytes.fromhex('00bf'))
    key(sb, 1, 8)
    assert sb.r(sb.pattern + 8, 1) != b'\x03', 'held-zero mutant escaped'
    print('PASS mutation control: removing held-zero skip loses valid entry')

    # Replace just the delta guard with the original writer: the real callback
    # must reproduce primary61 / record-min60, which the refusal checks reject.
    sb = bench()
    for k in (4, 6, 8):
        key(sb, 1, k)
    sb.w(DELTA, asm.assemble(['b.w 0x0802705c'], DELTA))
    caught = False
    try:
        unchanged_by_delta(sb, 1)
    except AssertionError:
        caught = True
    assert caught, 'direct-writer delta mutant escaped'
    assert sb.r(sb.pattern + 8, 1) == b'\x3d'
    assert min(n for n, v in chord(sb)) == 60
    print('PASS mutation control: direct delta writer reproduces primary61 / record-min60')
    print('PASS all EDIT-entry checks')


if __name__ == '__main__':
    main()
