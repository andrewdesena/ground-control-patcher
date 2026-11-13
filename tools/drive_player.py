#!/usr/bin/env python3
"""
drive_player.py — drive the real per-note emitter (0x8021748) with a synthetic track object and
capture the MIDI it emits. Demonstrates that the emulator runs the actual playback emitter (FPU/VFP
included) without hardware, and pins the emit contract used by the polyphony fan-out.

  ./.venv/bin/python tools/drive_player.py
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from fw_sandbox import Sandbox
from unicorn import UcError, UC_HOOK_CODE
from unicorn.arm_const import *

EMITTER = 0x08021748
PRIMS = {0x08019A2A: 'note-on', 0x08019A5E: 'note-off', 0x08019A92: 'pair'}


def run(note=60, vel=100, channel=0, gate=100):
    sb = Sandbox(); uc = sb.uc
    OBJ, PAR, HAND, STEP = 0x20010000, 0x20011000, 0x20012000, 0x20013000
    sb.w(OBJ, b'\x00' * 0x100); sb.w(PAR, b'\x00' * 0x100)
    sb.w(OBJ + 8, PAR.to_bytes(4, 'little'))     # [obj+8]   = track/parent
    sb.w(OBJ + 0x40, HAND.to_bytes(4, 'little'))  # [obj+0x40]= voice handle slot
    sb.w(PAR + 0x1f, bytes([channel & 0xFF]))     # per-track channel
    sb.w(0x2000B59B + channel, b'\x00' * 0x40)    # per-channel flags/gate table
    sb.w(0x2000B59B + channel + 0x2a, bytes([100]))
    sb.w(STEP, bytes([note & 0xFF, vel & 0xFF, 0]))  # step record: note, vel, modifier
    emits = []
    def hc(u, a, s, _):
        if a in PRIMS:
            emits.append((PRIMS[a], u.reg_read(UC_ARM_REG_R1), u.reg_read(UC_ARM_REG_R2),
                          u.reg_read(UC_ARM_REG_R3)))
    uc.hook_add(UC_HOOK_CODE, hc)
    uc.reg_write(UC_ARM_REG_R0, OBJ); uc.reg_write(UC_ARM_REG_R1, 0)
    uc.reg_write(UC_ARM_REG_R2, STEP); uc.reg_write(UC_ARM_REG_R3, gate)
    uc.reg_write(UC_ARM_REG_SP, 0x2001F000); uc.reg_write(UC_ARM_REG_LR, 0x2001FFF1)
    sb.w(0x2001F000, (vel).to_bytes(4, 'little'))
    try:
        uc.emu_start(EMITTER | 1, 0x2001FFF1, count=20000)
    except UcError:
        pass  # sentinel-return fetch artifact is benign
    return emits


def main():
    print("driving 0x8021748 (per-note emitter) with synthetic object:")
    for label, kw in [("note 60 vel 100", dict(note=60, vel=100)),
                      ("note 64 vel 90 ch 0", dict(note=64, vel=90)),
                      ("chord member note 67", dict(note=67, vel=80))]:
        emits = run(**kw)
        seq = [f"{n}(r3=0x{r3:02X})" for n, r1, r2, r3 in emits]
        print(f"  {label:22} -> {seq}")


if __name__ == '__main__':
    main()
