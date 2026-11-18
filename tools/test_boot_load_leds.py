#!/usr/bin/env python3
"""Compare pattern-load key pulses and transmitted frames with stock v3.26."""

import argparse
import json
from pathlib import Path

from unicorn import UC_HOOK_CODE
from unicorn.arm_const import (
    UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_SP,
)

from fw_sandbox import STACKTOP
from test_poly_v119 import (
    BUNDLE, SENTINEL, TRACKS, Sandbox, install, install_fatfs, neutralize, pattern_file, run, sidecar,
)

LETTERS = 'ABCDEFGHIJKLMNOPQRSTVWYZ'
ORDER = 0x080382F8
PULSES = 0x20001D9C
TRANSFER = 0x080322C4
GET_TICK = 0x08033A38
SHOW_LETTER = 0x0801EDD4
KEY_LED = 0x0801227C
LOCKED = BUNDLE.with_name('v1-poly-v120-lock1.json')
QUIET_BOOT = BUNDLE.with_name('v1-poly-v120-boot1.json')
DRUM_FIXTURE = {b'patternA.txt': b'{"count":1,"duration":2}'}


def restore(bundle, tracks, *, boot):
    """Run the stock project dispatcher with SD I/O and settings stubbed."""
    sb = Sandbox(bundle)
    run(sb, 0x08030C1C, stop=0x08030C32)  # Initialize flash-backed SRAM as reset does.
    for slot, track in enumerate(TRACKS):
        sb.w(track + 0x2D, bytes([slot == 0]))
    neutralize(sb, 0x080232A0, 0x080232B0, 0x080190A6, 0x08014F32,
               0x0801C01C, 0x0801D52C, 0x0801B80C, 0x0801AB3E,
               0x080246B8, 0x0801B664, 0x08025208, 0x08011C00,
               0x08011BC8, 0x08020FE4)
    install(sb, GET_TICK, 'movs r0, #1', 'bx lr')
    for i in range(18):
        sb.w(PULSES + i * 12, b'\xff')

    files = {}
    opened = install_fatfs(sb, files)
    slot = None
    reads, flashes = [], []

    def select_track(uc, addr, size, userdata):
        nonlocal slot
        slot = uc.reg_read(UC_ARM_REG_R1)
        files.clear()
        files.update(tracks[slot])

    def record_letter(uc, addr, size, userdata):
        flashes.append((slot, LETTERS[uc.reg_read(UC_ARM_REG_R0)]))

    def record_pattern(uc, addr, size, userdata):
        reads.append((slot, uc.reg_read(UC_ARM_REG_R0), uc.reg_read(UC_ARM_REG_R1)))

    for addr, callback in ((0x0801D064, select_track), (SHOW_LETTER, record_letter),
                           (0x0801C8B8, record_pattern), (0x0801CCC4, record_pattern)):
        sb.uc.hook_add(UC_HOOK_CODE, callback, begin=addr, end=addr)
    # Boot restore and the panel share the full-project loader. Boot initializes
    # its mode in 0x0801DCCA, while the panel supplies zero to 0x0801DCB0.
    for reg, value in ((UC_ARM_REG_R0, 0x2000B250), (UC_ARM_REG_R1, 0),
                       (UC_ARM_REG_SP, STACKTOP), (UC_ARM_REG_LR, SENTINEL | 1)):
        sb.uc.reg_write(reg, value)
    sb.uc.emu_start(0x0801DCCB if boot else 0x0801DCB1, SENTINEL, count=80_000_000)
    assert sb.reg(UC_ARM_REG_PC) == SENTINEL, (hex(sb.reg(UC_ARM_REG_PC)), reads[-1:])
    blocks = [sb.r(block, 0x51C if track == 0 else 0x194)
              for track, block, _ in reads]
    bank_state = sb.r(0x1000B530, 4 * 0x880) + sb.r(0x1000D740, 16)
    return (opened, reads, blocks, bank_state), flashes


def test_quiet_boot(tracks, label):
    baseline, flashes = restore(LOCKED, tracks, boot=True)
    fixed, quiet = restore(QUIET_BOOT, tracks, boot=True)
    assert {slot for slot, _, _ in baseline[1]} == {0, 1, 2, 3}, label
    for slot in range(4):
        expected = {name[7:8].decode() for name in tracks[slot]}
        assert expected and {letter for s, letter in flashes if s == slot} == expected, label
    assert not quiet, (label, quiet)
    assert baseline == fixed, f'{label}: startup changed pattern files read or loaded data'
    assert restore(LOCKED, tracks, boot=False) == restore(QUIET_BOOT, tracks, boot=False), label
    print(f'PASS {label}: startup pattern flashes {flashes} suppressed, with identical pattern data and panel load')


def trace(bundle, slot, files, spacing):
    sb = Sandbox(bundle)
    for i, track in enumerate(TRACKS):
        sb.w(track + 0x2D, bytes([i == 0]))
    neutralize(sb, 0x080232A0, 0x080232B0, 0x080190A6)
    for i in range(18):
        sb.w(PULSES + i * 12, b'\xff')

    tick = 1
    frames, letters, keys = [], [], []

    def read_tick(uc, addr, size, userdata):
        uc.reg_write(UC_ARM_REG_R0, tick)
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    def record_letter(uc, addr, size, userdata):
        letters.append(LETTERS[uc.reg_read(UC_ARM_REG_R0)])

    def record_key(uc, addr, size, userdata):
        if uc.reg_read(UC_ARM_REG_R1) == 6:
            keys.append(uc.reg_read(UC_ARM_REG_R0))

    def send(uc, addr, size, userdata):
        frames.append(sb.r(uc.reg_read(UC_ARM_REG_R1), uc.reg_read(UC_ARM_REG_R2)))
        uc.reg_write(UC_ARM_REG_R0, 0)
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    for addr, callback in ((GET_TICK, read_tick), (SHOW_LETTER, record_letter),
                           (KEY_LED, record_key), (TRANSFER, send)):
        sb.uc.hook_add(UC_HOOK_CODE, callback, begin=addr, end=addr)
    install_fatfs(sb, files)
    run(sb, 0x08011FB8)  # Initial stock SPI send.
    for letter in sb.r(ORDER, 24):
        block = TRACKS[slot] + 0x34 + letter * 0x194
        run(sb, 0x0801CCC4, {UC_ARM_REG_R0: block, UC_ARM_REG_R1: letter, UC_ARM_REG_R2: 1})
        run(sb, 0x08012128)  # Stock compositor.
        run(sb, 0x08012008)  # Stock PWM and SPI sender.
        tick += spacing
    return ''.join(letters), keys, frames


def fixtures(letters):
    native = json.dumps({
        'step_limit': 1, 'count': 1, 'duration': 2, 'Polyrhythm': {'From': 4, 'To': 4},
        'steps': [{'note': 'C3', 'velocity': 90, 'modifier': 0, 'ratchet': 0}],
    }).encode()
    return {f'pattern{letter}.txt'.encode(): pattern_file(native, sidecar(60, 64, 67))
            for letter in letters}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, action='append', default=[])
    args = parser.parse_args()
    stock_sparse = trace(None, 1, fixtures('A'), spacing=2)
    stock_dense = trace(None, 1, fixtures('ABCD'), spacing=2)
    stock_gap = trace(None, 1, fixtures('ABCD'), spacing=20)
    assert stock_sparse[0] == 'A' and stock_dense[0] == stock_gap[0] == 'ABCD'
    assert stock_dense[2] != stock_gap[2], 'fixture did not exercise time-dependent display'
    for name in ('v1-poly-v120.json', 'v1-poly-v120-lock1.json'):
        bundle = BUNDLE.with_name(name)
        assert trace(bundle, 1, fixtures('A'), spacing=2) == stock_sparse
        assert trace(bundle, 1, fixtures('ABCD'), spacing=2) == stock_dense
        assert trace(bundle, 1, fixtures('ABCD'), spacing=20) == stock_gap
    print(f'PASS stock and both v1.20 builds match at the same timing. A={stock_sparse[1]}, A–D={stock_dense[1]}.')
    test_quiet_boot([DRUM_FIXTURE, fixtures('ABCD'), fixtures('ABC'), fixtures('A')], 'fixtures')
    for project in args.project:
        tracks = [{f.name.encode(): f.read_bytes()
                   for f in (project / track).glob('pattern*.txt')}
                  for track in ('trackD', 'track1', 'track2', 'track3')]
        for slot in (1, 2, 3):
            files = tracks[slot]
            stock = trace(None, slot, files, spacing=2)
            assert trace(LOCKED, slot, files, spacing=2) == stock
            print(f'{project.name} track {slot}: pulses {stock[0]} on LED bits {stock[1]} (stock == lock1)')
        test_quiet_boot(tracks, project.name)


if __name__ == '__main__':
    main()
