#!/usr/bin/env python3
"""
test_poly_commit_reload.py — chord banks are republished from the committed playback letter.

The bug: a live project switch (C -> A -> B -> C) comes back monophonic until a
power cycle.  Stock, during a playing switch, stages the incoming project's
patterns at 0x2000BC00 + (sel-1)*0x194 and installs them at the deferred commit
(0x08021338); the per-track playback letter is then selected by 0x08023158 inside
the loop at 0x08021518.  Nothing reloads the chord bank there, so the bank keeps
whatever the earlier pattern preload left behind.

The fix hooks 0x08021528 (that per-track select): call 0x08023158 first, then
load /project<P>/track<N>/poly<L> into bank 0x1000B530 + N*0x880 using the letter
the player itself will use, and the track index from the fan-out's own table
(0x08038370: 0 drum, 1/2/3 melodic).

  python3 tools/test_poly_commit_reload.py [bundle.json]

Executes the installed hook address, never the cave directly.
"""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from fw_sandbox import Sandbox, STACKTOP  # noqa: E402
from unicorn import UC_HOOK_CODE  # noqa: E402
from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2,  # noqa: E402
                               UC_ARM_REG_R3, UC_ARM_REG_R4, UC_ARM_REG_R5,
                               UC_ARM_REG_R6, UC_ARM_REG_R7, UC_ARM_REG_R8,
                               UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11,
                               UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC)

ROOT = os.path.dirname(HERE)
BUNDLE = os.path.join(ROOT, 'mods', 'v1-poly-commit.json')

HOOK = 0x08021528          # installed hook: per-track letter select
AFTER_HOOK = 0x0802152C    # first stock instruction after the hook returns
CAVE = 0x08047A00
SELECT = 0x08023158        # stock: install the playing letter for a track
TABLE = 0x08038370         # fan-out's track table: 0 drum, 1..3 melodic
PROJECT = 0x2000B250       # project object; +0x249 = project index
SWITCH_FLAG = 0x2000C5D8   # nonzero while a project load/switch is in flight
POLY, SIZE = 0x1000B530, 2176
PATHBUF = 0x1000E420
F_OPEN, F_READ, F_CLOSE = 0x0801496C, 0x08014B30, 0x08014F18
FR_OK, FR_NO_FILE, FR_NO_PATH = 0, 4, 3
# Table order in 0x08038370: tracks 1..3 then the drum, i.e. bank n == selector n
# for the three melodic tracks and index 3 is the drum slot (excluded by both the
# type byte at +0x2d and the bank bound).
MEL1, MEL2, MEL3, DRUM = 0x20013DEC, 0x200117C8, 0x2000F1A4, 0x2000CB80


def sidecar(*notes):
    body = bytes([len(notes)]) + b''.join(bytes([n, 90]) for n in notes)
    return body + bytes(SIZE - len(body))


class Bench:
    def __init__(self, bundle=BUNDLE, stub_selector=True):
        self.sb = Sandbox(bundle)
        self.sb.w(TABLE, struct.pack('<4I', MEL1, MEL2, MEL3, DRUM))
        for p in (DRUM, MEL1, MEL2, MEL3):
            self.sb.w(p, b'\0')
            self.sb.w(p + 0x2e, b'\0')
            self.sb.w(p + 0x2d, b'\0' if p == DRUM else b'\1')
        self.sb.w(SWITCH_FLAG, b'\0')
        self.sb.w(PROJECT + 0x249, b'\0')
        self.files = {}
        self.opens = []
        self.open_result = {}      # path -> FRESULT override
        self.current = ''
        u = self.sb.uc
        # By default the stock selector is replaced by a no-op so a test can own the
        # letters. stub_selector=False keeps the real 0x08023158 in place.
        self.real_selector = not stub_selector
        if stub_selector:
            self.sb.w(SELECT, bytes.fromhex('7047'))
        u.hook_add(UC_HOOK_CODE, self._stop, begin=AFTER_HOOK, end=AFTER_HOOK)
        u.hook_add(UC_HOOK_CODE, self._open, begin=F_OPEN, end=F_OPEN)
        u.hook_add(UC_HOOK_CODE, self._read, begin=F_READ, end=F_READ)
        u.hook_add(UC_HOOK_CODE, self._close, begin=F_CLOSE, end=F_CLOSE)

    # --- FatFS model ---------------------------------------------------
    def _name(self, u, reg):
        try:
            return bytes(u.mem_read(u.reg_read(reg), 80)).split(b'\0')[0].decode('latin1')
        except Exception:
            return ''

    def _open(self, u, addr, size, _):
        self.current = self._name(u, UC_ARM_REG_R1)
        self.opens.append(self.current)
        res = self.open_result.get(self.current)
        if res is None:
            res = FR_OK if self.current in self.files else FR_NO_FILE
        u.reg_write(UC_ARM_REG_R0, res)
        u.reg_write(UC_ARM_REG_PC, u.reg_read(UC_ARM_REG_LR))

    def _read(self, u, addr, size, _):
        data = self.files.get(self.current, b'')
        n = u.reg_read(UC_ARM_REG_R2)
        take = min(n, len(data))
        if take:
            u.mem_write(u.reg_read(UC_ARM_REG_R1), data[:take])
        u.mem_write(u.reg_read(UC_ARM_REG_R3), struct.pack('<I', take))
        u.reg_write(UC_ARM_REG_R0, FR_OK)
        u.reg_write(UC_ARM_REG_PC, u.reg_read(UC_ARM_REG_LR))

    def _stop(self, u, addr, size, _):
        u.emu_stop()

    def _close(self, u, addr, size, _):
        u.reg_write(UC_ARM_REG_R0, FR_OK)
        u.reg_write(UC_ARM_REG_PC, u.reg_read(UC_ARM_REG_LR))

    # --- driving -------------------------------------------------------
    def install_letter(self, letter):
        """Make the stock selector stub install `letter`, as 0x08023158 would."""
        self.sb.w(SELECT, bytes([0x2e, 0x30, 0x01, 0x21, letter & 0xFF, 0x70, 0x70, 0x47]))

    def set_project(self, index):
        self.sb.w(PROJECT + 0x249, bytes([index]))

    def set_letter(self, track, letter):
        self.sb.w(track + 0x2e, bytes([letter]))

    def set_path_buf_marker(self):
        self.sb.w(PATHBUF, b'!' * 32)

    def run(self, track, prev_letter=None):
        """Call the installed hook exactly as the playback-start loop does."""
        if prev_letter is not None:
            self.sb.w(track + 0x2e, bytes([prev_letter]))
        u = self.sb.uc
        # The installed site is a `bl`, so "returned" means the next stock
        # instruction (0x0802152C) was reached - not a synthetic LR sentinel.
        guard = (UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7, UC_ARM_REG_R8,
                 UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11)

        # match the stock caller: 0x08021526 does `mov r0, r4` before the bl
        u.reg_write(UC_ARM_REG_R4, track)
        u.reg_write(UC_ARM_REG_R0, track)
        keep = {r: u.reg_read(r) for r in guard}
        u.reg_write(UC_ARM_REG_SP, STACKTOP)
        u.emu_start(HOOK | 1, 0xFFFFFFF0, count=400000)
        assert u.reg_read(UC_ARM_REG_PC) == AFTER_HOOK, \
            f'hook did not return to stock: pc=0x{u.reg_read(UC_ARM_REG_PC):08X}'
        assert u.reg_read(UC_ARM_REG_R4) == track, 'hook must preserve r4 (the track)'
        after = {r: u.reg_read(r) for r in guard}
        assert after == keep, f'hook must preserve r5-r11: {keep} -> {after}'
        return list(self.opens)

    def bank(self, sel):
        return self.sb.r(POLY + sel * SIZE, SIZE)

    def seed_bank(self, sel, data):
        self.sb.w(POLY + sel * SIZE, data + bytes(SIZE - len(data)))


def test_installed_hook():
    b = Bench()
    ins = b.sb.dis(HOOK, 4)[0]
    assert ins.mnemonic in ('bl', 'bl.w'), ins.mnemonic
    assert int(ins.op_str.split('#')[1], 0) | 0x08000000 == CAVE, ins.op_str
    print('PASS installed hook at 0x08021528 branches to the cave')


def test_paths_and_banks():
    b = Bench()
    b.set_project(2)                                  # project C
    b.files = {'/projectC/track1/polyC': sidecar(60, 64, 67),
               '/projectC/track2/polyC': sidecar(48, 55, 59),
               '/projectC/track3/polyC': sidecar(36, 43, 50)}
    b.sb.w(SWITCH_FLAG, b'\1')
    # Bank index == the track's index in 0x08038370, which is the space the fan-out
    # resolves (its loop covers 0..2), so bank n is exactly what playback will read.
    want_notes = {MEL1: (60, 64, 67), MEL2: (48, 55, 59), MEL3: (36, 43, 50)}
    for sel, track in enumerate((MEL1, MEL2, MEL3)):
        b.opens.clear()
        b.set_letter(track, 2)
        b.set_path_buf_marker()
        opens = b.run(track)
        want = f'/projectC/track{sel + 1}/polyC'
        assert want in opens, (sel, opens)
        assert b.bank(sel) == sidecar(*want_notes[track]), \
            f'bank {sel} mismatch: {b.bank(sel)[:8].hex()}'
    print('PASS project C publishes /projectC/track1..3/polyC into banks 1..3')

    # The drum track is recognised by its own type byte, not by table position.
    b.opens.clear()
    for sel in range(3):
        b.seed_bank(sel, b'\x07' * 8)
    b.set_letter(DRUM, 2)
    b.run(DRUM)
    assert not b.opens, b.opens
    assert all(b.bank(sel)[:8] == b'\x07' * 8 for sel in range(3))
    print('PASS drum track (type byte != 1) publishes nothing')


def test_letters_beyond_c():
    b = Bench()
    b.set_project(0)
    b.sb.w(SWITCH_FLAG, b'\1')
    b.files = {'/projectA/track1/polyE': sidecar(64, 68, 71)}
    b.opens.clear()
    b.set_letter(MEL1, 4)                              # letter E
    opens = b.run(MEL1)
    assert opens == ['/projectA/track1/polyE'], opens
    assert b.bank(0) == sidecar(64, 68, 71)
    print('PASS letter E (index 4) publishes polyE — the 0x4F0 bound is gone from this path')


def test_cost_gate():
    b = Bench()
    b.set_project(1)
    b.files = {'/projectB/track1/polyA': sidecar(60, 64)}
    # Same letter, no switch in flight: an ordinary play press must not hit the card.
    b.set_letter(MEL1, 0)
    b.opens.clear()
    b.run(MEL1, prev_letter=0)
    assert not b.opens, b.opens
    print('PASS repeat play press with an unchanged letter does no SD I/O')

    # Same letter, but the switch flag is up (C -> A -> B -> C all on pattern A):
    # this is the reported case, so it must publish.
    b.sb.w(SWITCH_FLAG, b'\1')
    b.opens.clear()
    b.run(MEL1, prev_letter=0)
    assert b.opens == ['/projectB/track1/polyA'], b.opens
    assert b.bank(0) == sidecar(60, 64)
    print('PASS same-letter project switch republishes the chord')


def test_letter_change_publishes():
    # Fresh bench: the selector stub has to be in place before this address is
    # first executed (unicorn caches translated blocks), so build it up front.
    b = Bench()
    b.set_project(1)
    b.files = {'/projectB/track1/polyA': sidecar(60, 64),
               '/projectB/track1/polyB': sidecar(62, 65)}
    b.set_letter(MEL1, 0)
    b.install_letter(1)
    b.sb.w(SWITCH_FLAG, b'\0')
    b.opens.clear()
    b.run(MEL1)
    assert b.opens == ['/projectB/track1/polyB'], b.opens
    assert b.bank(0) == sidecar(62, 65)
    print('PASS a committed letter change republishes even without the switch flag')


def test_real_selector_installs_the_letter():
    """Do not stub the selector: prove [track+0x2e] is final before the cave reads it."""
    b = Bench(stub_selector=False)
    b.set_project(2)
    b.files = {'/projectC/track1/polyC': sidecar(60, 64, 67)}
    b.sb.w(SWITCH_FLAG, b'\1')
    # stock 0x08023158: base = 0x2000B594 + [track+0x1f]; if [base+0x35] then
    # [track+0x2e] = [base+0x39].
    slot = 4
    b.sb.w(MEL1 + 0x1f, bytes([slot]))
    b.sb.w(0x2000B594 + slot + 0x35, b'\1')
    b.sb.w(0x2000B594 + slot + 0x39, b'\2')
    b.set_letter(MEL1, 0)
    b.opens.clear()
    opens = b.run(MEL1)
    assert b.sb.r(MEL1 + 0x2e, 1) == b'\x02', 'the real selector must install the letter'
    assert opens == ['/projectC/track1/polyC'], opens
    assert b.bank(0) == sidecar(60, 64, 67)
    print('PASS real selector 0x08023158 installs the letter before the hook reads it')


def test_missing_and_error_paths():
    b = Bench()
    b.set_project(2)
    b.sb.w(SWITCH_FLAG, b'\1')
    b.set_letter(MEL1, 0)
    b.seed_bank(0, sidecar(60, 64, 67))
    b.files = {}
    b.opens.clear()
    b.run(MEL1)
    assert b.bank(0) == bytes(SIZE), 'missing sidecar (FR_NO_FILE) must zero the bank'
    print('PASS missing sidecar zeroes the bank')

    b.seed_bank(0, sidecar(60, 64, 67))
    b.open_result = {'/projectC/track1/polyA': FR_NO_PATH}
    b.run(MEL1)
    assert b.bank(0) == sidecar(60, 64, 67), 'FR_NO_PATH must leave the bank untouched'
    print('PASS FR_NO_PATH leaves the bank untouched (a wrong path cannot silence a track)')

    b.open_result = {}
    b.seed_bank(0, sidecar(60, 64, 67))
    b.set_project(0x40)
    b.opens.clear()
    b.run(MEL1)
    assert not b.opens and b.bank(0) == sidecar(60, 64, 67), 'bad project index must be inert'
    print('PASS out-of-range project index is inert')

    b.set_project(2)
    b.seed_bank(0, sidecar(60, 64, 67))
    b.opens.clear()
    b.run(MEL1, prev_letter=0x40)
    assert not b.opens and b.bank(0) == sidecar(60, 64, 67), 'bad letter must be inert'
    print('PASS out-of-range letter is inert')


def test_truncated_sidecar():
    b = Bench()
    b.set_project(2)
    b.sb.w(SWITCH_FLAG, b'\1')
    b.set_letter(MEL1, 2)
    b.files = {'/projectC/track1/polyC': sidecar(60, 64, 67)[:1000]}
    b.seed_bank(1, sidecar(48, 52))
    b.run(MEL1)
    assert b.bank(0) == bytes(SIZE), 'short read must zero the bank'
    print('PASS truncated sidecar zeroes the bank')


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('-')]
    if args:
        BUNDLE = args[0]
    test_installed_hook()
    test_paths_and_banks()
    test_letters_beyond_c()
    test_cost_gate()
    test_letter_change_publishes()
    test_real_selector_installs_the_letter()
    test_missing_and_error_paths()
    test_truncated_sidecar()
    print('\nOK commit-time sidecar reload')
