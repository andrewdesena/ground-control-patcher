#!/usr/bin/env python3
"""Installed live-record hook with real stock numbering and shared cache helper."""
from test_poly_module_only import Module, POLY, SIZE, META
from unicorn.arm_const import *

def main():
    m = Module(); m.worker()
    sb=m.sb; manager=0x2001C0E4; native=0x20010000
    sb.w(manager+5, b'\x03')
    sb.w(0x2000CADA, b'\x02')  # real stock melodic track 2 -> bank 1
    sb.w(0x1000FD00+67, b'\x4d')
    def record(note, selector=2, step=3):
        sb.w(manager+5, bytes([step]));sb.w(0x2000CADA, bytes([selector]))
        sb.call(0x08025814, regs={UC_ARM_REG_R1:note,UC_ARM_REG_R5:note,
             UC_ARM_REG_R3:native+step*10,UC_ARM_REG_R4:manager}, stop_at=0x080257F8)
        assert sb.reg(UC_ARM_REG_PC)==0x080257F8
        assert sb.reg(UC_ARM_REG_R4)==manager and sb.reg(UC_ARM_REG_R5)==note
        assert sb.r(native+step*10+0x1d,1)==bytes([note])
    record(67)
    dst=POLY+SIZE+3*17
    assert sb.r(dst,3)==bytes([1,67,77])
    record(72);record(72)
    assert sb.r(dst,5)==bytes([2,67,77,72,100])
    sb.w(POLY+5*17, b'\xc8');record(60,1,5)
    assert sb.r(POLY+5*17,3)==bytes([1,60,100])
    before=sb.r(POLY,3*SIZE);record(60,0)
    assert sb.r(POLY,3*SIZE)==before
    assert sb.r(META+20,2)==b'\1\1'
    print('PASS native store, register/continuation preservation, normalized bank, chord/dedupe/cap/fallback and drums')
    return 0

if __name__=='__main__':raise SystemExit(main())
