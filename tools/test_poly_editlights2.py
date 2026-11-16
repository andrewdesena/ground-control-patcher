#!/usr/bin/env python3
"""Test poly-editlights2: chord key lights from the real edit cursor.

Drives the installed cave at 0x08048B30 with a live Sandbox, manager state,
pattern data and chord bank. Each case writes a single stock key bit into
the LED buffer, calls the cave, and verifies the extra chord bits appear.
"""
import json
import sys
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from test_poly_module_only import chord
from fw_sandbox import Sandbox, SENTINEL
from unicorn.arm_const import UC_ARM_REG_PC

CAVE = 0x08048B30
FB = 0x20001E74
MANAGER = 0x20006000

# key index -> bit position (from the note→bit table at 0x08048B18)
KEY_TO_BIT = [20, 14, 19, 13, 9, 17, 15, 18, 16, 22, 23, 21,
              3, 6, 4, 7, 5, 8, 12, 0, 11, 1, 10, 2]


def set_bit(buf, key_idx):
    bit = KEY_TO_BIT[key_idx]
    buf[bit // 8] |= 1 << (bit % 8)


def has_bit(buf, key_idx):
    bit = KEY_TO_BIT[key_idx]
    return bool(buf[bit // 8] & (1 << (bit % 8)))


def install_source(sb, name):
    """Install patches from a source file into the sandbox."""
    from test_poly_module_only import source as _src
    for p in _src(name)['patches']:
        addr = int(p['addr'], 0)
        sb.w(addr, bytes.fromhex(p['bytes']))


def main():
    # Build a bare Sandbox
    sb = Sandbox()

    # Install editlights2 patches (cave + tables + hook)
    install_source(sb, 'poly-editlights2')

    # Set up the track pointer table at 0x08038370
    parents = (0x20013DEC, 0x200117C8, 0x2000F1A4, 0x2000CB80)
    sb.w(0x08038370, struct.pack('<4I', *parents))
    sb.w(0x20000450, struct.pack('<4I', *parents))

    # Initialize parent fields and pattern data for tracks 1-3
    for t_idx, parent in enumerate(parents):
        track_num = t_idx + 1  # 1-based track number
        sb.w(parent + 0x1F, bytes([track_num]))
        sb.w(parent + 0x2D, bytes([1]))       # melodic
        sb.w(parent + 0x2E, bytes([0]))       # letter A
        for letter in range(24):
            p = parent + 0x34 + letter * 0x194
            sb.w(p, struct.pack('<I', 0x08038280))
            sb.w(p + 4, b'\x01')
            sb.w(p + 0x188, b'\x01\x00')

    # Initialize drum track (track 4, not melodic)
    sb.w(parents[3] + 0x1F, bytes([4]))
    sb.w(parents[3] + 0x2D, bytes([0]))      # drum

    fails = 0

    def run_case(track, letter, step, primary_note, notes, prelit_keys, expect):
        """Set up manager state, data, LED buffer, call cave, check result."""
        nonlocal fails

        # Reset LED buffer and manager
        sb.w(FB, bytes(3))
        sb.w(MANAGER + 0x2E1, bytes([0]))
        sb.w(MANAGER + 0x2DF, bytes([0]))

        # Set manager state
        sb.w(MANAGER + 0x2E1, bytes([track]))
        sb.w(MANAGER + 0x2DF, bytes([step]))

        if track <= 3:
            parent = parents[track - 1]

            # Active letter
            sb.w(parent + 0x2E, bytes([letter]))

            # Write primary note into pattern[letter].steps[step]
            p = parent + 0x34 + letter * 0x194 + 8 + step * 3
            sb.w(p, bytes([primary_note, 90, 0]))

            # Seed chord bank: 0x1000B530 + (track-1)*0x880 + step*17
            addr = 0x1000B530 + (track - 1) * 0x880 + step * 17
            if notes:
                sb.w(addr, chord(*notes))
            else:
                sb.w(addr, bytes(17))  # empty

        # Pre-light the stock keys
        fb = bytearray(3)
        for k in prelit_keys:
            set_bit(fb, k)
        sb.w(FB, bytes(fb))

        # Call cave
        sb.call(CAVE, max_steps=50000)
        assert sb.reg(UC_ARM_REG_PC) == SENTINEL, \
            f"pc=0x{sb.reg(UC_ARM_REG_PC):08X}"

        out = sb.r(FB, 3)
        ok = all(has_bit(out, k) for k in expect)
        no_extra = not any(has_bit(out, k) for k in range(24) if k not in expect)
        if ok and no_extra:
            return True
        else:
            bits = [k for k in range(24) if has_bit(out, k)]
            missing = [k for k in expect if not has_bit(out, k)]
            return False
        return True

    def check(label, ok):
        nonlocal fails
        if ok:
            print(f"  PASS {label}")
        else:
            fails += 1
            print(f"  FAIL {label}")

    print("poly-editlights2 tests")

    # Case 1: C-E-G on letter A step 0 → keys 0,4,7
    ok = run_case(1, 0, 0, 60, (60, 64, 67), (0,), (0, 4, 7))
    check("C4-E4-G4 letter A step 0", ok)

    # Case 2: Same chord on letter X (index 23), step 2
    ok = run_case(1, 23, 2, 60, (60, 64, 67), (0,), (0, 4, 7))
    check("C4-E4-G4 letter X step 2", ok)

    # Case 3: Different chord on letter A, step 1 → keys 4,7,11 (E4,G4,B4)
    ok = run_case(1, 0, 1, 64, (64, 67, 71), (4,), (4, 7, 11))
    check("E4-G4-B4 letter A step 1", ok)

    # Case 4: Letter A vs Letter B same step → different chords
    # First: letter A step 1 already has E4,G4,B4
    # Now: letter B (idx 1) step 1 with C5,E5,G5
    sb.w(parents[0] + 0x34 + 1 * 0x194 + 8 + 1 * 3, bytes([72, 90, 0]))
    sb.w(0x1000B530 + 0 + 1 * 17, chord(72, 76, 79))  # C5,E5,G5 → keys 0,4,7
    ok = run_case(1, 1, 1, 72, (72, 76, 79), (0,), (0, 4, 7))
    check("C5-E5-G5 letter B step 1", ok)

    # Case 5: Single note step → only stock key should stay
    ok = run_case(1, 0, 5, 60, (60,), (0,), (0,))
    check("single note C4 step 5", ok)

    # Case 6: Chord with >8 notes → cap at 8
    ok = run_case(1, 0, 6, 60, (60, 62, 64, 65, 67, 69, 71, 72, 74, 76), (0,),
                  (0, 2, 4, 5, 7, 9, 11, 12))
    check("chord cap 8 notes step 6", ok)

    # Case 7: Empty chord (no notes)
    ok = run_case(1, 0, 3, 67, (), (7,), (7,))
    check("empty chord G4 step 3", ok)

    # Case 8: Drum track → should not light chord keys
    sb.w(parents[3] + 0x1F, bytes([4]))
    sb.w(MANAGER + 0x2E1, bytes([4]))
    sb.w(MANAGER + 0x2DF, bytes([0]))
    sb.w(FB, bytes([0x10, 0, 0]))  # bit 4 in byte 0 = key? let's use key 0
    sb.w(FB, bytes(3))
    fb = bytearray(3)
    set_bit(fb, 0)
    sb.w(FB, bytes(fb))
    # Set chord bank for drum (should be ignored)
    sb.w(0x1000B530 + 3 * 0x880 + 0, chord(60, 64, 67))
    # Call cave: drum (track 4) should skip
    out = sb.call(CAVE, max_steps=50000)
    out_fb = sb.r(FB, 3)
    drum_ok = has_bit(out_fb, 0) and not has_bit(out_fb, 4) and not has_bit(out_fb, 7)
    check("drum track", drum_ok)

    # Case 9: Verify buffer outside 0x20001E74-0x20001E76 unchanged
    snap = sb.r(0x20001E70, 16)
    # Byte at 0x20001E77 should not be modified by our cave
    # (original is 0x00 since we initialized everything to 0)
    check("no writes outside LED buffer", snap[7] == 0 and snap[8] == 0)

    print()
    if fails:
        print(f"FAIL ({fails})")
        return 1
    print("PASS")
    return 0


if __name__ == '__main__':
    sys.exit(main())