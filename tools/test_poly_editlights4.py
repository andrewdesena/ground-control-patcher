#!/usr/bin/env python3
"""Test poly-editlights4: EDIT chord key lights, entered through the real hook.

The hook replaces the two literals stock loads at 0x08012068 before the LED
shift-out, so every case runs the real caller 0x08012008 and reaches the cave
only by executing the patched BL. Nothing is seeded that stock would not seed:
the manager table at 0x20000450 carries four slots, each manager's own 0-based
id at +0x2E1, its EDIT flag at +0x2DC and its step cursor at +0x2DF.

No track-selector global is used by the cave, so none is provided here.
"""
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from fw_sandbox import Sandbox, SENTINEL
from test_poly_module_only import chord, source
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_PC, UC_ARM_REG_R0, UC_ARM_REG_R1

LED = 0x20001E74
MGR_TABLE = 0x20000450
MGR_BASE = 0x10007A18
MGR_STRIDE = 0x2FC
TRACK_TABLE = 0x08038370
BANK = 0x1000B530
PARENTS = (0x20013DEC, 0x200117C8, 0x2000F1A4, 0x2000CB80)
LED_ENTRY = 0x08012008          # stock LED commit B; reaches the hook at 0x08012068
LED_ENTRY_A = 0x08011FB8        # stock LED commit A; reaches the hook at 0x08011FC6

KEY_TO_BIT = [20, 14, 19, 13, 9, 17, 15, 18, 16, 22, 23, 21,
              3, 6, 4, 7, 5, 8, 12, 0, 11, 1, 10, 2]
NOTE_AT = 0x3C                  # 0x34 + 8: note byte inside a stored step


def has_bit(buf, key_idx):
    bit = KEY_TO_BIT[key_idx]
    return bool(buf[bit // 8] & (1 << (bit % 8)))


def lit(buf):
    return [k for k in range(24) if has_bit(buf, k)]


def main():
    sb = Sandbox()
    for p in source('poly-editlights5')['patches']:
        sb.w(int(p['addr'], 0), bytes.fromhex(p['bytes']))
    sb.w(0x080322C4, bytes.fromhex('00207047'))   # SPI shift-out stub
    sb.w(TRACK_TABLE, struct.pack('<4I', *PARENTS))
    for i, parent in enumerate(PARENTS):
        sb.w(parent + 0x1F, bytes([i + 1]))
        sb.w(parent + 0x2D, bytes([1 if i < 3 else 0]))
        sb.w(parent + 0x2E, bytes([0]))
    for i in range(4):
        sb.w(MGR_TABLE + i * 4, struct.pack('<I', MGR_BASE + i * MGR_STRIDE))
        sb.w(MGR_BASE + i * MGR_STRIDE + 0x2E1, bytes([i]))   # own 0-based id
        sb.w(MGR_BASE + i * MGR_STRIDE + 0x2DC, bytes([0]))   # EDIT off
        sb.w(MGR_BASE + i * MGR_STRIDE + 0x2DF, bytes([0]))   # step cursor

    # the cave must hand stock back exactly the two literals it displaced, at the
    # instruction that consumes them (0x0801206E = bl 0x080322C4)
    seen = {}

    def spy(uc, addr, size, ud):
        seen['r0'] = uc.reg_read(UC_ARM_REG_R0)
        seen['r1'] = uc.reg_read(UC_ARM_REG_R1)

    sb.uc.hook_add(UC_HOOK_CODE, spy, begin=0x0801206E, end=0x0801206E)
    sb.uc.hook_add(UC_HOOK_CODE, spy, begin=0x08011FCA, end=0x08011FCA)

    fails = []

    def case(label, track_idx, letter, step, primary, notes, prelit,
             expect, edit=True, drum=False, entry=LED_ENTRY):
        # reset state
        sb.w(LED, bytes(3))
        sb.w(0x20001E7B, bytes(3))
        for i in range(4):
            m = MGR_BASE + i * MGR_STRIDE
            sb.w(m + 0x2DC, bytes([1 if (edit and i == track_idx) else 0]))
            sb.w(m + 0x2DF, bytes([step]))
        for i in range(3):
            sb.w(BANK + i * 0x880, bytes(0x880))
        parent = PARENTS[track_idx]
        sb.w(parent + 0x2E, bytes([letter]))
        sb.w(parent + 0x34 + letter * 0x194 + step * 3 + 8, bytes([primary, 90, 0]))
        if notes:
            sb.w(BANK + track_idx * 0x880 + step * 17, chord(*notes))
        # prelit/expect arrive as MIDI notes; the keyboard is linear from C4=60
        pk = [k - 60 for k in prelit]
        ek = sorted(k - 60 for k in expect)
        fb = bytearray(3)
        for k in pk:
            bit = KEY_TO_BIT[k]
            fb[bit // 8] |= 1 << (bit % 8)
        sb.w(0x20001E7B, bytes(fb))   # stock's source buffer
        sb.w(LED, bytes(fb))

        seen.clear()
        before = (sb.r(BANK, 0x880 * 3), sb.r(MGR_BASE, MGR_STRIDE * 4),
                  sb.r(TRACK_TABLE, 16))
        sb.call(entry, regs={UC_ARM_REG_R0: 0x40020000}, max_steps=50000)
        assert sb.reg(UC_ARM_REG_PC) == SENTINEL, f"{label}: runaway"
        out = sb.r(LED, 3)
        after = (sb.r(BANK, 0x880 * 3), sb.r(MGR_BASE, MGR_STRIDE * 4),
                 sb.r(TRACK_TABLE, 16))
        ok = lit(out) == ek
        abi = (seen.get('r0'), seen.get('r1')) == (0x20002B2C, 0x20001E74)
        if not abi:
            fails.append(label + ' (r0/r1 not restored)')
            print(f"  FAIL {label}: r0/r1 = {seen}")
        clean = before == after
        if ok and clean and abi:
            print(f"  PASS {label}: keys={[60 + k for k in lit(out)]}")
        else:
            fails.append(label)
            print(f"  FAIL {label}: keys={[60 + k for k in lit(out)]} want={sorted(expect)}"
                  f"{'' if clean else ' (wrote outside the LED buffer)'}")

    print('poly-editlights4 tests (through the installed hook)')
    # chord in EDIT, letter A / step 0 / track 1
    case('track1 letter A step0 C-E-G', 0, 0, 0, 60, (60, 64, 67), [60], [60, 64, 67])
    # the same chord through the twin LED sender (hook at 0x08011FC6)
    case('sender A: track1 letter A step0 C-E-G', 0, 0, 0, 60, (60, 64, 67), [60],
         [60, 64, 67], entry=LED_ENTRY_A)
    case('sender A: playback adds nothing', 0, 0, 0, 60, (60, 64, 67), [60], [60],
         edit=False, entry=LED_ENTRY_A)
    # letter X proves the active_letter*0x194 stride is applied
    case('track2 letter X step2 E-G-B', 1, 23, 2, 64, (64, 67, 71), [64], [64, 67, 71])
    # adjacent step, different chord: cursor must decide which one
    case('track1 letter A step1 E-G-B', 0, 0, 1, 64, (64, 67, 71), [64], [64, 67, 71])
    # a step with no chord keeps stock's single key
    case('mono step keeps one key', 0, 0, 5, 60, (), [60], [60])
    # playback: no manager is in EDIT, so nothing may be added
    case('playback adds nothing', 0, 0, 0, 60, (60, 64, 67), [60], [60], edit=False)
    # the drum slot is index 3 and has no chord bank to publish into
    case('drum slot adds nothing', 3, 0, 0, 60, (60, 64, 67), [60], [60], drum=True)

    # bank indexing: track 2 must read bank 1 even when bank 0 holds a chord
    sb.w(LED, bytes(3))
    sb.w(0x20001E7B, bytes(3))
    for i in range(4):
        m = MGR_BASE + i * MGR_STRIDE
        sb.w(m + 0x2DC, bytes([1 if i == 1 else 0]))
        sb.w(m + 0x2DF, bytes([0]))
    sb.w(BANK + 0 * 0x880, chord(60, 64, 67))     # track 1's chord
    sb.w(BANK + 1 * 0x880, chord(62, 65, 69))     # track 2's chord
    sb.w(BANK + 2 * 0x880, bytes(0x880))
    for i in range(3):
        sb.w(PARENTS[i] + 0x2E, bytes([0]))
    sb.w(PARENTS[1] + 0x34 + 8, bytes([62, 90, 0]))
    fb = bytearray(3)
    bit = KEY_TO_BIT[2]
    fb[bit // 8] |= 1 << (bit % 8)
    sb.w(0x20001E7B, bytes(fb))
    sb.w(LED, bytes(fb))
    sb.call(LED_ENTRY, regs={UC_ARM_REG_R0: 0x40020000}, max_steps=50000)
    out = sb.r(LED, 3)
    want = [2, 5, 9]
    if lit(out) == want:
        print(f"  PASS neighbouring banks: track2 reads its own bank -> {[60 + k for k in lit(out)]}")
    else:
        fails.append('neighbouring banks')
        print(f"  FAIL neighbouring banks: {[60 + k for k in lit(out)]} want {[60 + k for k in want]}")

    if fails:
        print(f"\nFAIL {len(fails)} case(s): {fails}")
        return 1
    print('\nPASS all cases')
    return 0


if __name__ == '__main__':
    sys.exit(main())
