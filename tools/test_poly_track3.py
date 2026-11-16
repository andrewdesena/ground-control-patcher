#!/usr/bin/env python3
"""Track 1-3 polyphony with the real track numbering.

Table 0x08038370 is ordered [drum, track1, track2, track3]: the drum object
(0x20013DEC) is initialised with 9 lanes and carries type byte +0x2D = 1, while
the three melodic tracks carry +0x2D = 0 and their own track number at +0x1F.
The chord bank index equals the table index, so the drum owns bank 0 and tracks
1-3 own banks 1-3.

These checks drive the installed hooks with that numbering, which the older
test_poly_commit_reload.py does not (it assumed melodic tracks at 0..2).
"""
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from test_poly_commit_reload import (Bench, sidecar, TABLE, SWITCH_FLAG, HOOK,
                                     CAVE, PROJECT)
from unicorn.arm_const import UC_ARM_REG_R4

BUNDLE = str(ROOT / 'mods' / 'v1-poly-track3.json')
DRUM, T1, T2, T3 = 0x20013DEC, 0x200117C8, 0x2000F1A4, 0x2000CB80
TRACKS = (DRUM, T1, T2, T3)


def bench():
    b = Bench(bundle=BUNDLE)
    b.sb.w(TABLE, struct.pack('<4I', *TRACKS))
    for i, p in enumerate(TRACKS):
        b.sb.w(p + 0x1F, bytes([i]))                 # own track number
        b.sb.w(p + 0x2D, bytes([1 if p == DRUM else 0]))
        b.sb.w(p + 0x2E, bytes([0]))
    b.sb.w(SWITCH_FLAG, b'\0')
    b.set_project(2)                                  # project C
    return b


def main():
    fails = []
    print('track numbering: table = [drum, track1, track2, track3]')

    # installed hooks point at the expected caves
    b = bench()
    ins = b.sb.dis(HOOK, 4)[0]
    if not (ins.mnemonic.startswith('bl') and int(ins.op_str.split('#')[1], 0) | 0x08000000 == CAVE):
        fails.append('hook at 0x08021528')
        print(f'  FAIL hook at 0x08021528 -> {ins.mnemonic} {ins.op_str}')
    else:
        print('  PASS hook at 0x08021528 branches to the cave')

    # fan-out and loader must cover the 4th bank now
    from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
    sb = bench().sb
    fan = [i for i in md.disasm(bytes(sb.r(0x08047632, 4)), 0x08047632)][0]
    load = [i for i in md.disasm(bytes(sb.r(0x08049010, 2)), 0x08049010)][0]
    if fan.op_str.endswith('#4') and load.op_str.endswith('#4'):
        print(f'  PASS bounds widened: fan-out `{fan.mnemonic} {fan.op_str}`, loader `{load.mnemonic} {load.op_str}`')
    else:
        fails.append('bounds')
        print(f'  FAIL bounds: fan-out {fan.op_str}, loader {load.op_str}')

    # each melodic track publishes its own sidecar into its own bank
    for idx, track in ((1, T1), (2, T2), (3, T3)):
        b = bench()
        b.set_letter(track, 0)
        path = f'/projectC/track{idx}/polyA'
        b.files = {path: sidecar(60 + idx, 64 + idx, 67 + idx)}
        for other in (0, 1, 2, 3):
            b.seed_bank(other, b'\x07' * 8)
        b.sb.w(SWITCH_FLAG, b'\1')
        opens = b.run(track)
        want = sidecar(60 + idx, 64 + idx, 67 + idx)
        ok = (opens == [path] and b.bank(idx) == want)
        others = all(b.bank(o)[:8] == b'\x07' * 8 for o in (0, 1, 2, 3) if o != idx)
        if ok and others:
            print(f'  PASS track{idx} -> bank {idx} via {path}')
        else:
            fails.append(f'track{idx}')
            print(f'  FAIL track{idx}: opens={opens} bank{idx} ok={b.bank(idx) == want} others clean={others}')

    # the drum owns bank 0 and must never be published into
    b = bench()
    b.files = {'/projectC/track0/polyA': sidecar(36, 40)}   # decoy
    for o in range(4):
        b.seed_bank(o, b'\x07' * 8)
    b.sb.w(SWITCH_FLAG, b'\1')
    opens = b.run(DRUM)
    if opens == [] and all(b.bank(o)[:8] == b'\x07' * 8 for o in range(4)):
        print('  PASS drum (type 1) publishes nothing and opens nothing')
    else:
        fails.append('drum')
        print(f'  FAIL drum: opens={opens}')

    # an ordinary play press does no SD I/O
    b = bench()
    b.set_letter(T1, 0)
    b.files = {'/projectC/track1/polyA': sidecar(60, 64, 67)}
    opens = b.run(T1, prev_letter=0)
    if opens == []:
        print('  PASS play press with unchanged letter does no SD I/O')
    else:
        fails.append('no-io')
        print(f'  FAIL play press opened {opens}')

    if fails:
        print(f'\nFAIL {len(fails)}: {fails}')
        return 1
    print('\nPASS track 1-3 polyphony, drum untouched')
    return 0


if __name__ == '__main__':
    sys.exit(main())
