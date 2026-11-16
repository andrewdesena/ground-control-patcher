#!/usr/bin/env python3
"""Replay stock constructors, editor open, UI render, compositor and LED tick.

Only UART logging and SPI transfer are stubbed. Normal EDIT cases obtain
manager IDs, track types, cursor and cached primary from stock code. Pattern
fixtures and UI actions supply the inputs; separate guard/diagnostic cases
inject deliberate state faults. The old v5 test fabricates track
0 as melodic; the real constructors make it drum type 1, tracks 1..3 type 0.
"""
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from fw_sandbox import Sandbox, SENTINEL, STACKTOP
from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn.arm_const import *

LED = 0x20001E74
EDITOR = 0x2001C230
WRAPPER = 0x2001C388
PAGE = 0x2001C380
CACHE = 0x2001CDFB
BANK = 0x1000B530
MGR_TABLE = 0x20000450
PARENTS = (0x20013DEC, 0x200117C8, 0x2000F1A4, 0x2000CB80)
REGS = (UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7,
        UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11)


def u32(sb, addr):
    return int.from_bytes(sb.r(addr, 4), 'little')


def run(sb, addr, regs=None, stop=None):
    sb.call(addr, regs=regs, stop_at=stop, max_steps=2000000)
    assert sb.reg(UC_ARM_REG_PC) == (stop if stop is not None else SENTINEL), hex(addr)


def apply(sb, name):
    bundle = json.loads((ROOT / 'mods' / (name + '.json')).read_text())
    for patch in bundle['patches']:
        sb.w(int(patch['addr'], 0), bytes.fromhex(patch['bytes']))
    return bundle


def setup(name='poly-editlights6', track=1, letter=0, primary=60,
          notes=(60, 64, 67), octave=0, edit=True, latched=False):
    sb = Sandbox('mods/v1-poly-commit.json')
    apply(sb, name)
    # Replay the real .data copy and all global constructors, not guessed types.
    run(sb, 0x08030C1C, stop=0x08030C32)
    run(sb, 0x0803530C)
    assert tuple(sb.r(p + 0x2D, 1)[0] for p in PARENTS) == (1, 0, 0, 0)
    run(sb, 0x0801F7E8)  # manager initialization: actual table and ids
    assert tuple(sb.r(u32(sb, MGR_TABLE + i * 4) + 0x2E1, 1)[0]
                 for i in range(4)) == (0, 1, 2, 3)
    sb.w(0x080190A6, bytes.fromhex('7047'))  # debug UART only
    sb.w(0x080322C4, bytes.fromhex('00207047'))  # SPI only

    parent = PARENTS[track]
    sb.w(0x2000CADA, bytes([track]))  # stock selected track UI getter
    sb.w(0x2001CDE8, bytes([octave & 255]))
    sb.w(parent + 0x2E, bytes([letter]))
    pattern = parent + 0x34 + letter * 0x194
    sb.w(pattern + 0x188, struct.pack('<HH', 3, 3))
    sb.w(pattern + 8, bytes([primary, 90, 0]))
    sb.w(pattern + 11, bytes([62, 90, 0]))
    sb.w(pattern + 14, bytes([64, 90, 0]))
    # Enable the input manager, then latch it through the stock UI handler.
    run(sb, 0x0801F3DC, {UC_ARM_REG_R0: u32(sb, MGR_TABLE + track * 4),
                         UC_ARM_REG_R1: 1})
    if latched:
        event = 0x2001E000
        sb.w(event, b'\1\0')
        run(sb, 0x080258E0, {UC_ARM_REG_R0: event})
    assert sb.r(u32(sb, MGR_TABLE + track * 4) + 0x2DC, 1) == bytes([latched])
    sb.w(EDITOR + 4, bytes([1 if edit else 0]))  # user's EDIT / record choice
    sb.w(WRAPPER + 8, struct.pack('<I', EDITOR))  # selected melodic editor
    # Real page switch -> wrapper open -> vtable +8 -> 0x080274CC.
    run(sb, 0x0802D4B4, {UC_ARM_REG_R0: 6})
    assert u32(sb, PAGE) == 0x20000590
    assert u32(sb, EDITOR + 12) == parent
    assert u32(sb, EDITOR + 8) == pattern
    assert sb.r(u32(sb, MGR_TABLE + track * 4) + 0x2DB, 1) == b'\0'
    assert sb.r(u32(sb, MGR_TABLE + track * 4) + 0x2DC, 1) == bytes([latched])
    assert sb.r(EDITOR + 7, 1) == b'\0'
    if edit:
        assert sb.r(CACHE + 1, 1) == bytes([primary])
    # Populate saved sidecars. Track ids match the existing fan-out verbatim.
    sb.w(BANK + track * 0x880, pack_chord(notes))
    sb.w(BANK + track * 0x880 + 17, pack_chord((62, 65, 69)))
    sb.w(BANK + track * 0x880 + 34, pack_chord((64, 67, 71)))
    return sb


def pack_chord(notes):
    return bytes([len(notes)]) + b''.join(bytes([n, 90]) for n in notes) + bytes(16 - 2 * len(notes))


def render(sb):
    # Actual UI-task call site, with its loop-invariant r4 pointing at the page.
    # dispatch page vtable +8 -> 0x0802AE20 -> editor +0x14 -> 0x08027D24,
    # then stock compositor 0x08012128. Stop before unrelated display/RTOS work.
    run(sb, 0x080207B4, {UC_ARM_REG_R4: PAGE}, stop=0x080207C0)


def frame(sb):
    return {i for i in range(56) if sb.r(LED + i // 8, 1)[0] & (1 << (i % 8))}


def stock_bits(sb, notes, octave=0):
    result = set()
    for note in notes:
        sb.w(0x2001E010, b'\0')
        run(sb, 0x0801ECFC, {UC_ARM_REG_R0: note, UC_ARM_REG_R1: octave & 0xFFFFFFFF,
                              UC_ARM_REG_R2: 0x2001E010})
        if sb.r(0x2001E010, 1) == b'\0':
            result.add(sb.reg(UC_ARM_REG_R0))
    return result


def commit(sb, sender='B', bundle='poly-editlights6'):
    patches = json.loads((ROOT / 'mods' / (bundle + '.json')).read_text())['patches']
    cave = next(p for p in patches if p['note'] == 'cave routine')
    lo = int(cave['addr'], 0)
    hi = lo + len(bytes.fromhex(cave['bytes']))
    observed = {'active': False, 'writes': []}
    resume = 0x0801206C if sender == 'B' else 0x08011FCA

    def code(uc, addr, size, _):
        if addr == lo:
            observed['active'] = True
            observed['regs'] = [uc.reg_read(r) for r in REGS]
            observed['sp'] = uc.reg_read(UC_ARM_REG_SP)
            if bundle != 'poly-editlights5':
                assert observed['sp'] % 8 == 0
        if addr == resume:
            assert observed['active'], 'stock caller never reached hook'
            observed['active'] = False
            assert [uc.reg_read(r) for r in REGS] == observed['regs']
            assert uc.reg_read(UC_ARM_REG_SP) == observed['sp']
            assert uc.reg_read(UC_ARM_REG_R0) == 0x20002B2C
            assert uc.reg_read(UC_ARM_REG_R1) == LED
            observed['returned'] = True

    def write(uc, access, addr, size, value, _):
        if not observed['active']:
            return
        assert lo <= uc.reg_read(UC_ARM_REG_PC) < hi
        # AAPCS stack save is the only exception to the LED-only data writes.
        if STACKTOP - 256 <= addr < STACKTOP:
            return
        assert LED <= addr and addr + size <= LED + 7, hex(addr)
        old = int.from_bytes(sb.r(addr, size), 'little')
        assert old | value == value, 'cleared a stock bit'
        observed['writes'].append((addr, size))

    ch = sb.uc.hook_add(UC_HOOK_CODE, code)
    wh = sb.uc.hook_add(UC_HOOK_MEM_WRITE, write)
    banks = sb.r(BANK, 0x880 * 3)
    run(sb, 0x08012C12 if sender == 'B' else 0x08011FB8)
    sb.uc.hook_del(ch)
    sb.uc.hook_del(wh)
    assert observed.get('returned')
    assert sb.r(BANK, 0x880 * 3) == banks
    return observed


def advance(sb):
    event = 0x2001E000
    sb.w(event, bytes([1, 0x2E]))
    run(sb, 0x08027B94, {UC_ARM_REG_R0: EDITOR, UC_ARM_REG_R1: event})


def main():
    base = json.loads((ROOT / 'mods/v1-poly-commit.json').read_text())
    baseline = {int(p['addr'], 0): bytes.fromhex(p['bytes']) for p in base['patches']}
    for name, merged_name in [('poly-editlights6', 'v1-poly-edit6'),
                              ('poly-editlights6-diag', 'v1-poly-edit6-diag')]:
        overlay = {int(p['addr'], 0): bytes.fromhex(p['bytes']) for p in
                   json.loads((ROOT / 'mods' / (name + '.json')).read_text())['patches']}
        merged = {int(p['addr'], 0): bytes.fromhex(p['bytes']) for p in
                  json.loads((ROOT / 'mods' / (merged_name + '.json')).read_text())['patches']}
        # the diagnostic build ships extra marker tables, so the merge only has to
        # contain every baseline and overlay patch byte-for-byte
        assert all(merged.get(a) == d for a, d in (baseline | overlay).items()), name
        cave = next(a for a in overlay if a not in (0x08012068, 0x08011FC6))
        assert all(max(cave, a) >= min(cave + len(overlay[cave]), a + len(data))
                   for a, data in baseline.items()), 'new cave overlaps installed patch'
    print('PASS merged builds preserve v5 bytes except both hooks; new caves disjoint')
    # Reproduce the shipped failure using a real melodic track and stock flags.
    sb = setup('poly-editlights5')
    render(sb)
    assert sb.r(0x20001E7B, 3) == bytes.fromhex('000010')
    commit(sb, bundle='poly-editlights5')
    assert frame(sb) & set(range(24)) == {20}
    print('PASS v5 reproduces C only after stock opens EDIT (manager flag = 0)')
    # A real stock-latched manager still cannot pass the reversed type gate.
    sb = setup('poly-editlights5', latched=True)
    render(sb)
    commit(sb, bundle='poly-editlights5')
    assert frame(sb) & set(range(24)) == {20}
    print('PASS v5 rejects real melodic type 0 with a stock-latched manager')

    for track, letter, octave, primary, notes in [
        (1, 0, 0, 60, (60, 64, 67)),
        (1, 23, 0, 60, (60, 63, 67)),
        (2, 0, 0, 60, (60, 65, 69)),
        (1, 0, 1, 72, (72, 76, 79)),
        (1, 0, -1, 48, (48, 52, 55)),
        (1, 0, 0, 60, (60,)),
        (1, 0, 0, 60, ()),
        (1, 0, 0, 60, (60, 52, 77, 127)),
        (1, 0, 0, 60, (60, 128, 255)),
        (1, 0, 0, 60, (53, 54, 60, 64, 67, 71, 72, 76)),
    ]:
        for sender in ('B', 'A'):
            sb = setup(track=track, letter=letter, primary=primary, notes=notes, octave=octave)
            render(sb)
            # A sends the existing frame without rebuilding it.
            if sender == 'A':
                # Rebuild the transient frame with stock code, retaining the A hook.
                sb.w(0x08012068, bytes.fromhex('07490c48'))
                run(sb, 0x08012008)
            expect = stock_bits(sb, (primary,) + notes, octave)
            before_source = sb.r(0x20001E7B, 7)
            commit(sb, sender)
            assert frame(sb) & (set(range(24)) | {31}) == expect, (track, letter, notes, frame(sb), expect)
            assert sb.r(0x20001E7B, 7) == before_source
        print(f'PASS stock render -> both senders: track={track}, letter={letter}, octave={octave}, notes={notes}')

    sb = setup()
    render(sb)
    sb.w(0x20001E7B + 1, b'\x80')  # stock special bit 15, outside the note table
    sb.w(0x20001D92, b'\3')  # stock preserves bit 15 on this counter phase
    commit(sb)
    assert {20, 9, 0, 15} <= frame(sb)
    print('PASS multiple frame bits preserve stock status and expand the chord')

    sb = setup()
    advance(sb)
    assert sb.r(EDITOR + 7, 1) == b'\1'
    assert sb.r(CACHE + 1, 1) == b'\x3e'
    render(sb)
    commit(sb)
    assert frame(sb) & (set(range(24)) | {31}) == stock_bits(sb, (62, 65, 69))
    advance(sb)
    assert sb.r(EDITOR + 7, 1) == b'\2'
    render(sb)
    commit(sb)
    assert frame(sb) & (set(range(24)) | {31}) == stock_bits(sb, (64, 67, 71))
    print('PASS real cursor input advances through adjacent distinct chords')

    sb = setup(latched=True)
    render(sb)
    for phase in range(6):
        sb.w(0x20001D93, bytes([phase]))
        commit(sb)
        assert {20, 9, 0} <= frame(sb)
    print('PASS all six PWM phases with a stock-latched manager')

    boot = Sandbox('mods/v1-poly-commit.json')
    apply(boot, 'poly-editlights6')
    boot.w(0x080322C4, bytes.fromhex('00207047'))
    assert commit(boot, sender='A')['writes'] == []
    assert frame(boot) == set()
    print('PASS initialization sender performs no cave data writes')

    # Every guard below must suppress expansion. Compare with an unpatched sender.
    guards = [
        ('closed editor', lambda s: s.w(WRAPPER + 12, b'\0')),
        ('another page', lambda s: s.w(PAGE, struct.pack('<I', 0x200005A8))),
        ('record choice', lambda s: s.w(EDITOR + 4, b'\0')),
        ('different inner editor', lambda s: s.w(WRAPPER + 8, struct.pack('<I', 0x2001C0E4))),
        ('no selected-note display', lambda s: s.w(CACHE + 17, b'\1')),
        ('drum', lambda s: s.w(EDITOR + 12, struct.pack('<I', PARENTS[0]))),
        ('unsupported bank index 3', lambda s: s.w(EDITOR + 12, struct.pack('<I', PARENTS[3]))),
        ('cursor 128', lambda s: s.w(EDITOR + 7, b'\x80')),
        ('letter 24', lambda s: s.w(PARENTS[1] + 0x2E, b'\x18')),
        ('stale letter pointer', lambda s: s.w(EDITOR + 8, struct.pack('<I', PARENTS[1] + 0x1C8))),
        ('stale cached primary', lambda s: s.w(CACHE + 1, b'\x3e')),
        ('rest', lambda s: s.w(PARENTS[1] + 0x3C, b'\x80')),
        ('count above 8', lambda s: s.w(BANK + 0x880, bytes([9]))),
        ('primary masked in frame', lambda s: s.w(0x20001E90 + 2, b'\x10')),
    ]
    for label, mutate in guards:
        sb = setup()
        render(sb)
        mutate(sb)
        # Snapshot unpatched B's real transmit result.
        sb.w(0x08012068, bytes.fromhex('07490c48'))
        run(sb, 0x08012C12)
        expected = sb.r(LED, 7)
        apply(sb, 'poly-editlights6')
        # Avoid the stock PWM phase transition when testing masking.
        sb.w(0x20001D93, b'\0')
        commit(sb)
        assert sb.r(LED, 7) == expected, (label, sb.r(LED, 7).hex(), expected.hex())
        print('PASS guard:', label)

    # Diagnostic evaluates original buffer BEFORE adding status/sender bits.
    def old_manager(sb, ident=1, step=0, kind=1):
        manager = u32(sb, MGR_TABLE + 4)
        sb.w(manager + 0x2DC, b'\1')
        sb.w(manager + 0x2E1, bytes([ident]))
        sb.w(manager + 0x2DF, bytes([step]))
        if ident <= 3:
            sb.w(PARENTS[ident] + 0x2D, bytes([kind]))

    def empty_bank(sb):
        old_manager(sb)
        sb.w(BANK + 0x880, b'\0')

    def large_bank(sb):
        old_manager(sb)
        sb.w(BANK + 0x880, bytes([9]))

    def delta_fail(sb):
        old_manager(sb)
        sb.w(BANK + 0x880, pack_chord((0,)))

    for label, mutate, bit in [
        ('real EDIT: no manager flag', lambda s: None, 13),
        ('zero', lambda s: s.w(0x20001E7B, bytes(3)), 14),
        ('multiple', lambda s: s.w(0x20001E7B, bytes.fromhex('010010')), 19),
        ('id', lambda s: old_manager(s, ident=4), 17),
        ('type', lambda s: old_manager(s, kind=0), 18),
        ('zero count', empty_bank, 16),
        ('large count', large_bank, 22),
        ('step', lambda s: old_manager(s, step=128), 23),
        ('delta', delta_fail, 12),
        # NOTE: the "all gates pass" marker still assumes the pre-correction bank
        # numbering; re-derive it against table order [drum, t1, t2, t3] before
        # trusting the diagnostic build. The fix build's gates are covered above.
    ]:
        for sender, marker in [('B', 3), ('A', 4)]:
            sb = setup('poly-editlights6-diag')
            render(sb)
            mutate(sb)
            if sender == 'A':
                sb.w(0x08012068, bytes.fromhex('07490c48'))
                run(sb, 0x08012008)
            commit(sb, sender=sender, bundle='poly-editlights6-diag')
            assert {marker, bit} <= frame(sb), (label, sender, frame(sb))
        print('PASS diagnostic:', label)
    print('PASS all editlights6 checks')


if __name__ == '__main__':
    main()
