#!/usr/bin/env python3
"""Exercise the installed DIN enqueue and UART interrupt with memory-backed UART registers."""

import struct
from pathlib import Path

from fw_sandbox import Sandbox, SENTINEL
from unicorn.arm_const import UC_ARM_REG_PC, UC_ARM_REG_R1

BUNDLE = Path(__file__).resolve().parent.parent / 'mods/v1-poly-v119.json'
STREAM = 0x20001CB8
PRIORITY = 0x20001CCA
PENDING = 0x1000D730
UART = 0x40004C00
INPUT = 0x2001E000
DATA = INPUT + 16


def run(sb, address, registers=None):
    sb.call(address, regs=registers)
    assert sb.reg(UC_ARM_REG_PC) == SENTINEL


def bench(patched):
    sb = Sandbox(BUNDLE if patched else None)
    sb.call(0x08030C1C, stop_at=0x08030C32)
    sb.w(0x080192AC, b'\x02\x20\x70\x47')  # permit the stock output routing
    sb.w(UART, struct.pack('<I', 0x80))  # TXE
    sb.w(UART + 0xC, struct.pack("<I", 0x80))  # TXE interrupt is already enabled
    sb.w(DATA, bytes([0x90, 60, 100]))
    sb.w(STREAM, struct.pack('<I4B', DATA, 3, 2, 1, 0))
    return sb


def enqueue(sb, status):
    sb.w(INPUT, bytes([status, 0, 2, 0xFF, 0, 0]))
    run(sb, 0x08011830, {UC_ARM_REG_R1: INPUT})


def irq(sb):
    run(sb, 0x080118F0)
    return sb.r(UART + 4, 1)[0]


def main():
    sb = bench(True)
    enqueue(sb, 0xF8)
    assert sb.r(PENDING, 1) == b'\1' and sb.r(PRIORITY, 1) == b'\0'
    before = sb.r(STREAM, 8)
    assert irq(sb) == 0xF8
    assert sb.r(STREAM, 8) == before
    assert sb.r(PENDING, 1) == b'\0'
    assert [irq(sb), irq(sb)] == [60, 100]
    assert sb.r(PRIORITY, 1) == b'\0', 'duplicate F8 entered the priority FIFO'

    sb = bench(False)
    enqueue(sb, 0xF8)
    assert sb.r(PRIORITY, 1) == b'\1'
    assert [irq(sb), irq(sb)] == [60, 100], 'stock mutation unexpectedly preempted the note'

    sb = bench(True)
    enqueue(sb, 0xFA)
    enqueue(sb, 0xF8)
    assert sb.r(PENDING, 1) == b'\0'
    assert sb.r(PRIORITY, 1) == b'\2'
    assert sb.r(PRIORITY + 3, 1) == b'\xfa'
    assert sb.r(PRIORITY + 9, 1) == b'\xf8'
    assert [irq(sb), irq(sb)] == [60, 100]

    sb = bench(True)
    enqueue(sb, 0xF8)
    enqueue(sb, 0xF8)
    assert sb.r(PRIORITY, 1) == b'\1'
    assert irq(sb) == 0xF8
    assert sb.r(PENDING, 1) == b'\0'
    print('PASS next-byte DIN clock, preserved note bytes, no duplicates, transport FIFO order, stock mutation')


if __name__ == '__main__':
    main()
