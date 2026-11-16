#!/usr/bin/env python3
"""Test poly-editlights3: enters through the real hook at 0x08012068.

Drives the LED commit function which reaches the hook's BL to the cave.
Demonstrates playback-mode silence: with manager+0x2DC=0, extra bits
are NOT ORed even when all other state looks like an edit session.

manager structure:
  CCM managers at 0x10007A18 + idx*0x2FC, pointed to from 0x20000450+4i
  +0x2DC = EDIT flag, +0x2DF = step cursor, +0x2E1 = track id
"""
import sys, struct
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from fw_sandbox import Sandbox, SENTINEL
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import *

CAVE = 0x08048B30
FB = 0x20001E74
MANAGER_TABLE = 0x20000450  # 4 manager pointers
TRACK_TABLE = 0x08038370    # 4 track pointers
TRACK_SEL = 0x2000CADA      # 1-based track selector

# Manager CCM addresses (verified from init loop 0x0802001C)
MGMT_BASE = 0x10007A18
MGMT_STRIDE = 0x2FC

# key -> bit map (same as note->bit table at 0x08048B18)
KEY_TO_BIT = [20,14,19,13,9,17,15,18,16,22,23,21,
              3,6,4,7,5,8,12,0,11,1,10,2]


def set_bit(buf, k):
    b = KEY_TO_BIT[k]
    buf[b//8] |= 1 << (b%8)


def has_bit(buf, k):
    b = KEY_TO_BIT[k]
    return bool(buf[b//8] & (1 << (b%8)))


def install_source(sb, name):
    from test_poly_module_only import source
    for p in source(name)['patches']:
        sb.w(int(p['addr'],0), bytes.fromhex(p['bytes']))


def setup_managers(sb, parents):
    """Set up 4 CCM managers. parents = (track1, track2, track3, drum) pointers."""
    for idx in range(4):
        mgr = MGMT_BASE + idx * MGMT_STRIDE
        sb.w(mgr + 0x2DC, bytes([0]))    # EDIT flag = 0
        sb.w(mgr + 0x2DF, bytes([0]))    # step cursor
        sb.w(mgr + 0x2E1, bytes([idx]))  # track id (0-based, drum=0...track3=3)
        sb.w(mgr + 0x2DB, bytes([1]))    # active flag = 1

    # Write manager pointers into RAM table
    for idx in range(4):
        mgr = MGMT_BASE + idx * MGMT_STRIDE
        sb.w(MANAGER_TABLE + idx*4, struct.pack('<I', mgr))


def setup_track(sb, track_idx, letter, step, primary_note, notes, parent):
    """Set up pattern and chord bank for a track."""
    # Active letter
    sb.w(parent + 0x2E, bytes([letter]))

    # Pattern data
    pat = parent + 0x34 + letter * 0x194 + 8 + step * 3
    sb.w(pat, bytes([primary_note, 90, 0]))

    # Chord bank: 0x1000B530 + track_idx*0x880 + step*17
    addr = 0x1000B530 + track_idx * 0x880 + step * 17
    if notes:
        from test_poly_module_only import chord
        sb.w(addr, chord(*notes))
    else:
        sb.w(addr, bytes(17))


def main():
    sb = Sandbox()
    install_source(sb, 'poly-editlights3')

    # Track pointer table
    parents = (0x20013DEC, 0x200117C8, 0x2000F1A4, 0x2000CB80)
    sb.w(TRACK_TABLE, struct.pack('<4I', *parents))
    # Also set up 0x20000450 as track table copy (used by some)
    sb.w(0x20000450, struct.pack('<4I', *parents))

    # Set up managers in CCM
    setup_managers(sb, parents)

    # Initialize track parent fields (melodic flag, pattern headers)
    for t_idx, parent in enumerate(parents):
        sb.w(parent + 0x1F, bytes([t_idx+1]))
        sb.w(parent + 0x2D, bytes([1 if t_idx < 3 else 0]))  # melodic for 0-2
        for letter in range(24):
            p = parent + 0x34 + letter * 0x194
            sb.w(p, struct.pack('<I', 0x08038280))
            sb.w(p + 4, b'\x01')
            sb.w(p + 0x188, b'\x01\x00')

    # SPI shift-out stub: return 0 (movs r0,#0; bx lr)
    sb.w(0x080322C4, bytes.fromhex('00207047'))

    fails = 0

    def run_through_hook(track_1based, edit_flag, step, letter, primary, notes,
                          prelit_keys, expect_keys):
        """Set state, call the LED commit function, check result."""
        nonlocal fails
        track_idx = track_1based - 1

        # Reset LED buffer and source buffer (stock copies 0x20001E7B->0x20001E74)
        sb.w(FB, bytes(3))
        sb.w(0x20001E7B, bytes(3))     # source buffer (stock LED refresh reads from here)
        sb.w(0x20001E90, bytes(7))     # mask buffer (0 = no masking)

        # Set track selector
        sb.w(TRACK_SEL, bytes([track_1based]))

        # Set manager state
        mgr = MGMT_BASE + track_idx * MGMT_STRIDE
        sb.w(mgr + 0x2DC, bytes([edit_flag]))
        sb.w(mgr + 0x2DF, bytes([step]))

        # Set track data
        if track_idx < 3:
            setup_track(sb, track_idx, letter, step, primary, notes,
                        parents[track_idx])

        # Pre-light stock key(s) in the SOURCE buffer (0x20001E7B).
        # The LED commit copies 0x20001E7B → 0x20001E74, then our hook
        # runs and ORs additional bits into 0x20001E74.
        fb = bytearray(3)
        for k in prelit_keys:
            set_bit(fb, k)
        sb.w(0x20001E7B, bytes(fb))
        # Also set the destination buffer directly for completeness
        sb.w(FB, bytes(fb))

        # Call LED commit function (0x08012008) — reaches hook -> cave -> SPI stub
        # r0 = 0x40020000 (from instruction at +0x0A literal pool)
        sb.call(0x08012008, regs={UC_ARM_REG_R0: 0x40020000},
                max_steps=50000)
        assert sb.reg(UC_ARM_REG_PC) == SENTINEL, \
            f"pc=0x{sb.reg(UC_ARM_REG_PC):08X}"

        out = sb.r(FB, 3)
        ok = all(has_bit(out, k) for k in expect_keys)
        no_extra = not any(has_bit(out, k) for k in range(24)
                           if k not in expect_keys)

        label = f"trk{track_1based} edit={edit_flag} step={step}"
        if ok and no_extra:
            print(f"  PASS {label}")
            return True
        else:
            bits = [k for k in range(24) if has_bit(out, k)]
            missing = [k for k in expect_keys if not has_bit(out, k)]
            print(f"  FAIL {label}: set={bits} missing={missing} extra={not no_extra}")
            return False

    def run_direct_call(track_1based, edit_flag, step, letter, primary, notes,
                         prelit_keys, expect_keys):
        """Call the cave directly (for isolated chord-add testing)."""
        nonlocal fails
        track_idx = track_1based - 1

        sb.w(FB, bytes(3))
        sb.w(TRACK_SEL, bytes([track_1based]))

        mgr = MGMT_BASE + track_idx * MGMT_STRIDE
        sb.w(mgr + 0x2DC, bytes([edit_flag]))
        sb.w(mgr + 0x2DF, bytes([step]))

        if track_idx < 3:
            setup_track(sb, track_idx, letter, step, primary, notes,
                        parents[track_idx])

        fb = bytearray(3)
        for k in prelit_keys:
            set_bit(fb, k)
        sb.w(FB, bytes(fb))

        sb.call(CAVE, max_steps=50000)
        assert sb.reg(UC_ARM_REG_PC) == SENTINEL

        out = sb.r(FB, 3)
        ok = all(has_bit(out, k) for k in expect_keys)
        no_extra = not any(has_bit(out, k) for k in range(24)
                           if k not in expect_keys)

        label = f"DIRECT trk{track_1based} edit={edit_flag} step={step}"
        if ok and no_extra:
            print(f"  PASS {label}")
            return True
        else:
            bits = [k for k in range(24) if has_bit(out, k)]
            missing = [k for k in expect_keys if not has_bit(out, k)]
            print(f"  FAIL {label}: set={bits} missing={missing}")
            return False

    def check(label, ok):
        nonlocal fails
        if ok:
            print(f"  PASS {label}")
        else:
            fails += 1
            print(f"  FAIL {label}")

    print("poly-editlights3 tests")

    # === A. End-to-end through real hook (0x08012068) ===

    # A1: EDIT mode (flag=1), C-E-G chord → expect keys 0,4,7
    ok = run_through_hook(1, 1, 0, 0, 60, (60,64,67), (0,), (0,4,7))
    check("hook: C4-E4-G4 edit=1 step=0", ok)

    # A2: EDIT mode with different letter → letter X (idx 23)
    ok = run_through_hook(1, 1, 2, 23, 60, (60,64,67), (0,), (0,4,7))
    check("hook: C4-E4-G4 letter X edit=1 step=2", ok)

    # A3: PLAYBACK mode (flag=0) → must NOT add chord keys
    ok = run_through_hook(1, 0, 0, 0, 60, (60,64,67), (0,), (0,))
    check("hook: PLAYBACK silence — only key 0 lit", ok)

    # A4: PLAYBACK mode with different step/letter → still silent
    ok = run_through_hook(1, 0, 5, 3, 64, (64,67,71), (4,), (4,))
    check("hook: PLAYBACK silence — only key 4 lit step 5", ok)

    # A5: Drum track → no chord keys
    ok = run_through_hook(4, 1, 0, 0, 60, (60,64,67), (0,), (0,))
    check("hook: drum track silence", ok)

    # === B. Direct cave call (isolated chord-add tests) ===

    # B1: Basic chord
    ok = run_direct_call(1, 1, 0, 0, 60, (60,64,67), (0,), (0,4,7))
    check("direct: C4-E4-G4", ok)

    # B2: Letter B (idx 1), step 1
    ok = run_direct_call(1, 1, 1, 1, 72, (72,76,79), (0,), (0,4,7))
    check("direct: C5-E5-G5 letter B step 1", ok)

    # B3: Single note = only stock key
    ok = run_direct_call(1, 1, 5, 0, 60, (60,), (0,), (0,))
    check("direct: single note C4", ok)

    # B4: Empty chord
    ok = run_direct_call(1, 1, 3, 0, 67, (), (7,), (7,))
    check("direct: empty chord G4", ok)

    # B5: 8+ notes — cap at 8
    ok = run_direct_call(1, 1, 6, 0, 60, (60,62,64,65,67,69,71,72,74,76),
                          (0,), (0,2,4,5,7,9,11,12))
    check("direct: 8-note cap step6", ok)

    # B6: PLAY mode = no chord keys added
    ok = run_direct_call(1, 0, 0, 0, 60, (60,64,67), (0,), (0,))
    check("direct: PLAY mode silence", ok)

    # B7: Drum track silence
    ok = run_direct_call(4, 1, 0, 0, 60, (60,64,67), (0,), (0,))
    check("direct: drum track", ok)

    # B8: Verify no writes outside buffer
    snap = sb.r(0x20001E70, 16)
    check("no writes outside LED buffer", snap[3] == 0 and snap[7] == 0)

    print()
    if fails:
        print(f"FAIL ({fails})")
        return 1
    print("PASS")
    return 0


if __name__ == '__main__':
    sys.exit(main())