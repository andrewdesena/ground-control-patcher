#!/usr/bin/env python3
"""Focused v0.9.0 reset/DIN smoke test, not a 30-minute hardware reproduction.

Execute the native storage-exit reset-request fragment, application RAM init,
and patched DIN byte interrupt. UART registers are memory-backed and output
routing is stubbed; USB, external receivers and a full boot are not simulated.
"""
import struct
from pathlib import Path
from unicorn.arm_const import UC_ARM_REG_PC
from fw_sandbox import Sandbox, SENTINEL
import test_clock_din_realtime as din

ROOT = Path(__file__).resolve().parent.parent
BASELINE = ROOT / 'mods/poly-0.9.0.json'
AIRCR = 0xE000ED0C


def main():
    sb = Sandbox(BASELINE)
    sb.w(AIRCR, struct.pack('<I', 0x500))
    sb.call(0x080F107C, stop_at=0x080F1092)
    request, = struct.unpack('<I', sb.r(AIRCR, 4))
    assert request == 0x05FA0504, hex(request)

    # Unicorn does not apply SYSRESETREQ. Execute the real reset RAM setup
    # explicitly, with dirty pre-reset RAM, stopping before peripheral init.
    sb.w(0x20000000, b'\xa5' * 0x1E000)
    sb.w(0x10000000, b'\xa5' * 0x10000)
    sb.call(0x08030C1C, stop_at=0x08030C68, max_steps=400000)
    assert sb.r(din.PENDING, 32) == bytes(32)
    assert sb.r(din.STREAM, 8) == bytes(8)
    assert sb.r(din.PRIORITY, 3) == bytes(3)
    assert sb.r(0x20001CCD, 3) == bytes(3), 'ordinary note FIFO not cleared'

    # Deliberately stub only output routing, as in the existing DIN regression.
    sb.w(0x080192AC, bytes.fromhex('02207047'))
    sb.w(din.UART, struct.pack('<I', 0x80))
    sb.w(din.UART + 0xC, struct.pack('<I', 0x80))
    sb.w(din.DATA, bytes([0x90, 60, 100]))
    sb.w(din.STREAM, struct.pack('<I4B', din.DATA, 3, 3, 0, 0))
    din.enqueue(sb, 0xF8)
    assert [din.irq(sb) for _ in range(4)] == [0xF8, 0x90, 60, 100]
    assert sb.reg(UC_ARM_REG_PC) == SENTINEL
    assert sb.r(din.PENDING, 1) == b'\0'
    print('PASS native storage reset request, dirty-RAM MIDI state clearing, and clock plus note bytes after RAM init')
    print('LIMIT: no full boot, 30-minute storage session, USB peripheral or physical receiver is simulated; hardware fault remains unresolved')


if __name__ == '__main__':
    main()
