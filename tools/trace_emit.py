#!/usr/bin/env python3
"""
trace_emit.py — dynamic trace of the note-emit primitives via fw_sandbox.

Executes 0x8019A2A (note-on), 0x8019A5E (note-off), 0x8019A92 (note pair) with synthetic
arguments and captures, at the instant they call the queue push 0x08019840, the MIDI bytes they
built. This pins the register contract (which arg is note / velocity / channel) that fan-out
must preserve.

  ./.venv/bin/python tools/trace_emit.py
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from fw_sandbox import Sandbox, STACKTOP
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3

PUSH = 0x08019840


def run(sb, addr, r0, r1, r2, r3, stackargs, label):
    # seed caller stack args at STACKTOP (function reads [sp,#0x10],[sp,#0x14] after push)
    sb.w(STACKTOP, b''.join(int(x).to_bytes(4, 'little') for x in stackargs))
    # stop at the queue push and capture the message it was handed
    log = sb.call(addr, regs={UC_ARM_REG_R0: r0, UC_ARM_REG_R1: r1,
                              UC_ARM_REG_R2: r2, UC_ARM_REG_R3: r3},
                  stop_at=PUSH)
    if log and log[-1][0] == 'STOP':
        # at 0x8019840, r1 = msg ptr (from 0x8019A2A's `mov r1,sp`)
        msgp = sb.reg(UC_ARM_REG_R1)
        msg = sb.r(msgp, 6)
        print(f"  {label:14} -> queue push, msg ptr=0x{msgp:08X} bytes={msg.hex()} "
              f"[{msg[0]:#04x} {msg[1]} {msg[2]}]")
    else:
        print(f"  {label:14} -> did NOT reach queue push (ran to return); last={log[-1] if log else None}")


def main():
    sb = Sandbox()
    print("note-on 0x8019A2A (try r0=vel, r2=note):")
    run(sb, 0x08019A2A, r0=100, r1=0x20010000, r2=60, r3=0, stackargs=[0x11, 0, 0, 0, 0, 0, 0, 0], label="A2A note-on")
    print("\nnote-off 0x8019A5E (try r0=vel, r2=note):")
    run(sb, 0x08019A5E, r0=0, r1=0x20010000, r2=60, r3=0, stackargs=[0x11, 0, 0, 0, 0, 0, 0, 0], label="A5E note-off")
    print("\npair 0x8019A92 (r0=?, r1=note, r2=?, r3=?):")
    run(sb, 0x08019A92, r0=0, r1=60, r2=100, r3=0, stackargs=[0x11, 0, 0, 0, 0x11, 0, 0, 0], label="A92 pair")


if __name__ == '__main__':
    main()
