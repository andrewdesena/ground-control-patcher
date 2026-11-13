#!/usr/bin/env python3
"""
fw_sandbox.py — reusable Unicorn sandbox for the Ground Control firmware.

Loads the full image, maps FLASH/SRAM/CCM/peripheral space, and can call any firmware
function with controlled registers + memory, with instruction/memory tracing. This is the
base for dynamic analysis (no hardware): trace the note-emit path, confirm register contracts,
and later boot the scheduler.

  from fw_sandbox import Sandbox
  sb = Sandbox()                 # loads testdata/gc326.hex (+ optional bundle)
  sb.call(0x08019A2A, r0=..., r1=...)   # run until it returns to a sentinel
"""
import os, sys, json, struct
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from verify import parse, index
from unicorn import (Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_HOOK_CODE,
                     UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE)
from unicorn.arm_const import *
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB

IMG = os.path.join(HERE, '..', 'testdata', 'gc326.hex')
FLASH = 0x08010000
SRAM, SRAMSZ = 0x20000000, 0x20000
CCM, CCMSZ = 0x10000000, 0x10000
PERIPH, PERIPHSZ = 0x40000000, 0x00100000
SCB, SCBSZ = 0xE0000000, 0x00100000
SENTINEL = SRAM + 0x1F000
STACKTOP = SRAM + 0x1FF00


class Sandbox:
    def __init__(self, bundle=None):
        mem = index(parse(open(IMG, newline='').read()))
        lo, hi = min(mem), max(mem)
        size = ((hi - lo) // 0x1000 + 2) * 0x1000
        img = bytearray([0xFF]) * size
        for a, b in mem.items():
            img[a - lo] = b
        if bundle:
            b = json.load(open(bundle))
            for p in b['patches']:
                addr = int(p['addr'], 16); data = bytes.fromhex(p['bytes'])
                for i, byte in enumerate(data):
                    img[addr - lo + i] = byte
        self.lo = lo
        self.uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
        # map flash from its real base (0x08000000) so low-flash writes/reads don't fault
        fbase = 0x08000000
        fsize = ((lo + len(img) - fbase) // 0x1000 + 2) * 0x1000
        self.uc.mem_map(fbase, fsize)
        self.uc.mem_write(lo, bytes(img))
        for base, sz in [(SRAM, SRAMSZ), (CCM, CCMSZ),
                         (0x40000000, 0x08000000),   # AHB1/AHB2/APB peripherals (wide)
                         (0x50000000, 0x01000000),   # USB OTG etc.
                         (SCB, SCBSZ)]:
            self.uc.mem_map(base, sz)
        self.md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)

    def w(self, addr, data): self.uc.mem_write(addr, bytes(data))
    def r(self, addr, n): return bytes(self.uc.mem_read(addr, n))
    def reg(self, name): return self.uc.reg_read(name)

    def call(self, addr, regs=None, trace=None, stop_at=None, max_steps=200000):
        """Run from addr until it returns to SENTINEL. If stop_at is set, stop when PC hits it
        (and return there) — used to capture a callee's inputs. trace=set of addrs to log."""
        uc = self.uc
        for k, v in (regs or {}).items():
            uc.reg_write(k, v)
        uc.reg_write(UC_ARM_REG_SP, STACKTOP)
        uc.reg_write(UC_ARM_REG_LR, SENTINEL | 1)
        log = []
        def hcode(u, a, s, _):
            if trace and a in trace:
                log.append((a, {n: u.reg_read(n) for n in
                                (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2,
                                 UC_ARM_REG_R3, UC_ARM_REG_R4, UC_ARM_REG_R5)}))
            if stop_at is not None and a == stop_at:
                log.append(('STOP', a)); u.emu_stop()
            if a == SENTINEL:
                u.emu_stop()
        h = uc.hook_add(UC_HOOK_CODE, hcode)
        uc.emu_start(addr | 1, 0xFFFFFFF0, count=max_steps)
        uc.hook_del(h)
        return log

    def dis(self, addr, n):
        return list(self.md.disasm(self.r(addr, n), addr))
