#!/usr/bin/env python3
"""
test_poly_activegate.py — the sidecar loader must publish the ACTIVE pattern letter.

Why
---
The stock project loader (0x0801DB60 -> 0x0801D1EE -> 0x0801D064 -> 0x0801CCC4)
preloads pattern files for all 24 letters of every track through the loader that
hooks 0x0801CD96.  v1.1 copied the sidecar of whatever letter was being loaded
into the shared chord bank (0x1000B530 + track*0x880), so after a project switch
the bank held some other letter's chord.  The fan-out only emits extras when the
step's primary note appears in the bank, so a mismatched bank sounds like mono:
the reported "project C -> A -> B -> C comes back playing a single note".

The fixed cave resolves the track from the destination pattern pointer, reads the
track's active pattern letter at [track+0x2e] (the byte the player itself loads at
0x0801F54C), and always publishes `poly<that letter>`.  A missing or short sidecar
zeroes the bank, so a previous project's chord can never leak through.

  python3 tools/test_poly_activegate.py            # fixed bundle (default)
  python3 tools/test_poly_activegate.py --repro    # v1.1: the wrong letter wins
"""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from fw_sandbox import Sandbox, STACKTOP  # noqa: E402
from unicorn import UC_HOOK_CODE  # noqa: E402
from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2,  # noqa: E402
                               UC_ARM_REG_R3, UC_ARM_REG_SP, UC_ARM_REG_LR,
                               UC_ARM_REG_PC)

ROOT = os.path.dirname(HERE)
GATED = os.path.join(ROOT, 'mods', 'v1-poly-full-gated.json')
KNOWN = os.path.join(ROOT, 'mods', 'v1-poly-known-good.json')

LOADER = 0x0801CCC4
HOOK = 0x0801CD96
CAVE = 0x08049000
TABLE = 0x08038370          # track pointer table in flash
ORDER = 0x080382F8          # 24-byte order walked by the project preload
POLY, SIZE = 0x1000B530, 2176
F_OPEN, F_READ, F_CLOSE = 0x0801496C, 0x08014B30, 0x08014F18
FR_OK, FR_NO_FILE = 0, 4
STEP = 0x194
LETTERS = 'ABCDEFGHIJKLMNOPQRSTVWYZ'


def sidecar(*notes):
    body = bytes([len(notes)]) + b''.join(bytes([n, 90]) for n in notes)
    return body + bytes(SIZE - len(body))


class Bench:
    """Real stock loader + real installed cave, FatFS served from a dict."""

    def __init__(self, bundle):
        self.sb = Sandbox(bundle)
        self.parents = [0x20013DEC, 0x200117C8, 0x2000F1A4, 0x2000CB80]
        self.sb.w(TABLE, struct.pack('<4I', *self.parents))
        for i, p in enumerate(self.parents):
            self.sb.w(p, bytes([0x41 + i]))       # letter byte in the track object
            self.sb.w(p + 0x2e, b'\0')            # active pattern letter index
        self.files = {}
        self.current = ''
        self.opens = []
        self.loads = 0
        u = self.sb.uc
        u.hook_add(UC_HOOK_CODE, self._open, begin=F_OPEN, end=F_OPEN)
        u.hook_add(UC_HOOK_CODE, self._read, begin=F_READ, end=F_READ)
        u.hook_add(UC_HOOK_CODE, self._close, begin=F_CLOSE, end=F_CLOSE)
        u.hook_add(UC_HOOK_CODE, self._count, begin=LOADER, end=LOADER)

    # --- FatFS model ---------------------------------------------------
    def _name(self, u, reg):
        try:
            return bytes(u.mem_read(u.reg_read(reg), 64)).split(b'\0')[0].decode('latin1')
        except Exception:
            return ''

    def _open(self, u, addr, size, _):
        self.current = self._name(u, UC_ARM_REG_R1)
        ok = self.current in self.files
        self.opens.append(self.current)
        u.reg_write(UC_ARM_REG_R0, FR_OK if ok else FR_NO_FILE)
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

    def _close(self, u, addr, size, _):
        u.reg_write(UC_ARM_REG_R0, FR_OK)
        u.reg_write(UC_ARM_REG_PC, u.reg_read(UC_ARM_REG_LR))

    def _count(self, u, addr, size, _):
        self.loads += 1

    # --- card ----------------------------------------------------------
    def card(self, patterns=(), poly=None):
        """patterns: letter indexes with a pattern file. poly: {index: notes}."""
        poly = poly or {}
        self.files = {'pattern%s.txt' % LETTERS[i]: b'{}' for i in patterns}
        for idx, notes in poly.items():
            self.files['poly' + LETTERS[idx]] = sidecar(*notes)

    # --- driving -------------------------------------------------------
    def load(self, track, letter):
        u = self.sb.uc
        u.reg_write(UC_ARM_REG_R0, self.parents[track] + 0x34 + letter * STEP)
        u.reg_write(UC_ARM_REG_R1, letter)
        u.reg_write(UC_ARM_REG_R2, 0)
        u.reg_write(UC_ARM_REG_SP, STACKTOP)
        u.reg_write(UC_ARM_REG_LR, 0x2001FFFF | 1)
        u.emu_start(LOADER | 1, 0xFFFFFFF0, count=400000)

    def preload(self, track):
        """Walk the 24-letter order exactly like the stock project preload."""
        for letter in self.sb.r(ORDER, 24):
            self.load(track, letter)

    def set_active(self, track, letter):
        self.sb.w(self.parents[track] + 0x2e, bytes([letter]))

    def clear_bank(self):
        self.sb.w(POLY, bytes(3 * SIZE))

    def bank(self, track):
        return self.sb.r(POLY + track * SIZE, SIZE)

    def poly_opens(self):
        return [n for n in self.opens if n.startswith('poly')]


def test_installed_hook():
    b = Bench(GATED)
    ins = b.sb.dis(HOOK, 4)[0]
    assert ins.mnemonic in ('bl', 'bl.w'), ins.mnemonic
    assert int(ins.op_str.split('#')[1], 0) | 0x08000000 == CAVE, ins.op_str
    print('PASS installed hook at 0x0801CD96 branches to the cave')


def test_active_letter_wins_the_preload():
    b = Bench(GATED)
    # Project with pattern files A..C and sidecars for A and C; player sits on A.
    b.card(patterns=(0, 1, 2), poly={0: (60, 64, 67), 2: (48, 52, 55)})
    b.set_active(0, 0)
    b.clear_bank()
    b.opens.clear()
    b.preload(0)
    assert b.loads == 24, f'stock preload must hit the loader 24x, saw {b.loads}'
    assert set(b.poly_opens()) == {'polyA'}, b.poly_opens()
    assert b.bank(0) == sidecar(60, 64, 67), 'bank must hold the active letter A chord'
    print('PASS 24-letter preload publishes only polyA (active), never polyC')

    # Same card, player moved to C: the same preload must publish polyC.
    b.set_active(0, 2)
    b.opens.clear()
    b.preload(0)
    assert set(b.poly_opens()) == {'polyC'}, b.poly_opens()
    assert b.bank(0) == sidecar(48, 52, 55), 'bank must hold the active letter C chord'
    print('PASS active letter C publishes polyC through the same preload')


def test_single_load_is_active_letter():
    b = Bench(GATED)
    b.card(patterns=tuple(range(24)), poly={0: (60, 64, 67), 1: (62, 65, 69)})
    b.set_active(0, 0)
    b.clear_bank()
    b.opens.clear()
    b.load(0, 1)                      # loading pattern B while the player is on A
    assert b.poly_opens() == ['polyA'], b.poly_opens()
    assert b.bank(0) == sidecar(60, 64, 67)
    print("PASS loading pattern B never publishes B's chord while A is active")


def test_missing_and_short_active_sidecar_clear_the_bank():
    b = Bench(GATED)
    b.set_active(0, 2)
    b.sb.w(POLY, sidecar(60, 64, 67))
    b.card(patterns=(2,), poly={})              # active sidecar absent
    b.load(0, 2)
    assert b.bank(0) == bytes(SIZE), 'missing active sidecar must zero the bank'
    print('PASS missing active sidecar zeroes the bank (no stale chord)')

    b.sb.w(POLY, sidecar(60, 64, 67))
    b.card(patterns=(2,))
    b.files['polyC'] = sidecar(60, 64, 67)[:1000]   # truncated file
    b.load(0, 2)
    assert b.bank(0) == bytes(SIZE), 'short active sidecar must zero the bank'
    print('PASS short active sidecar zeroes the bank')


def test_track_scoping():
    b = Bench(GATED)
    b.card(patterns=tuple(range(24)), poly={0: (48, 52), 1: (55, 59), 3: (70, 74)})
    for t, letter in ((0, 0), (1, 1), (2, 3)):
        b.set_active(t, letter)
    b.clear_bank()
    b.preload(1)
    assert b.bank(1) == sidecar(55, 59), b.bank(1)[:8].hex()
    assert b.bank(0) == bytes(SIZE) and b.bank(2) == bytes(SIZE), 'neighbour tracks untouched'
    print("PASS preload on track 2 writes only track 2's bank")


def test_invalid_active_letter_falls_back():
    b = Bench(GATED)
    b.card(patterns=(2,), poly={2: (70, 74)})
    b.set_active(0, 0x40)              # unset / out of range active letter
    b.clear_bank()
    b.load(0, 2)
    assert b.bank(0) == sidecar(70, 74), 'out-of-range active letter must fall back'
    print('PASS out-of-range active letter falls back to the letter being loaded')


def repro_known_good():
    """v1.1: the bank ends holding whichever letter loaded last, not the active one."""
    b = Bench(KNOWN)
    b.card(patterns=(0, 1, 2), poly={0: (60, 64, 67), 2: (48, 52, 55)})
    b.set_active(0, 0)                 # player is on pattern A
    b.clear_bank()
    b.opens.clear()
    b.preload(0)
    assert set(b.poly_opens()) == {'polyA', 'polyB', 'polyC'}, b.poly_opens()
    assert b.bank(0) == sidecar(48, 52, 55), "v1.1 leaves C's chord in the bank"
    print("PASS repro: v1.1 preload ends on polyC while the player is on pattern A")


if __name__ == '__main__':
    if '--repro' in sys.argv:
        repro_known_good()
    else:
        if len(sys.argv) == 1:
            test_installed_hook()
        test_active_letter_wins_the_preload()
        test_single_load_is_active_letter()
        test_missing_and_short_active_sidecar_clear_the_bank()
        test_track_scoping()
        test_invalid_active_letter_falls_back()
        print('\nOK active-letter sidecar publish')
