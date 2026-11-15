#!/usr/bin/env python3
"""Cooperatively schedule real firmware tasks while SD I/O is suspended.

Only FatFS/RTOS and final MIDI delivery are modeled. Each task uses its own ARM
register context and stack. The scheduler ring enqueue and due drain execute
stock firmware, and the competing task takes the same sequencing mutex.
"""
import struct
import sys
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import *
from test_poly_module_only import Module, META, POLY, SIZE, PROJECT, F_OPEN, F_READ, F_WRITE, F_CLOSE, chord
from fw_sandbox import SENTINEL, STACKTOP


def task(m, address, regs=None):
    """Run a different RTOS task, with a disjoint stack, to completion."""
    for reg, value in (regs or {}).items():
        m.sb.uc.reg_write(reg, value)
    m.sb.uc.reg_write(UC_ARM_REG_SP, STACKTOP - 0x3000)
    m.sb.uc.reg_write(UC_ARM_REG_LR, SENTINEL | 1)
    m.sb.uc.emu_start(address | 1, SENTINEL, count=200000)
    assert m.sb.reg(UC_ARM_REG_PC) == SENTINEL


def suspend_io(m, boundary):
    """Stop the SD task inside FatFS, leaving I/O incomplete until resumed."""
    stopped = []
    def interrupt(address, regs):
        if address in (F_OPEN, F_READ, F_WRITE, F_CLOSE, 0x08015214):
            assert not m.locked, f'filesystem under sequencer mutex at {address:08x}'
        if address == boundary and not stopped:
            stopped.append(True)
            m.sb.uc.emu_stop()
    m.interrupt = interrupt
    m.sb.call(0x0804A600, max_steps=2000000)
    assert stopped and m.sb.reg(UC_ARM_REG_PC) == boundary
    return m.sb.uc.context_save()


def resume_io(m, context):
    m.sb.uc.context_restore(context)
    # The modeled API has produced its result; complete its bx lr only now.
    m.sb.uc.emu_start(m.sb.reg(UC_ARM_REG_LR) | 1, SENTINEL, count=2000000)
    assert m.sb.reg(UC_ARM_REG_PC) == SENTINEL
    assert not m.locked
    m.interrupt = None


def due_off(m):
    """Install an outstanding off in the real scheduler, then return its drain."""
    m.call(0x08019BF0)
    message = bytes([0x80, 7, 0, 0xff, 45, 1])
    pointer = 0x20017000
    m.sb.w(pointer, message)
    m.call(0x08019840, {UC_ARM_REG_R0: 25, UC_ARM_REG_R1: pointer, UC_ARM_REG_R2: 0})
    delivered = []
    m.sb.w(0x08019D98, bytes.fromhex('7047'))
    def dispatch(u, address, size, _):
        delivered.append(m.sb.r(u.reg_read(UC_ARM_REG_R0), 6))
    m.sb.uc.hook_add(UC_HOOK_CODE, dispatch, begin=0x08019D98, end=0x08019D98)
    def drain():
        task(m, 0x080232A0, {UC_ARM_REG_R0: 0xffffffff})
        task(m, 0x08019BBC, {UC_ARM_REG_R0: 25})
        task(m, 0x080232B0)
        assert delivered == [message], 'due off could not run while SD task was blocked'
    return drain


def test_delayed_io_competing_task():
    for boundary in (F_READ, F_WRITE):
        m = Module()
        m.seed(1, chord(60, 64))
        m.seed(1, chord(60, 67), 1)
        m.worker()
        if boundary == F_WRITE:
            m.touch(1)
            m.sb.w(POLY, chord(60, 65))
        drain = due_off(m)
        m.switch(1, 1)
        context = suspend_io(m, boundary)
        # SD task stays blocked. Sequencer independently takes the mutex and
        # dispatches the due off from the real ring before I/O can complete.
        drain()
        resume_io(m, context)
        assert m.bank(1) == chord(60, 67)
        if boundary == F_WRITE:
            assert m.files[m.path(1)] == chord(60, 65)


def request(m, letter):
    task(m, 0x0804A280, {UC_ARM_REG_R0: m.parents[1], UC_ARM_REG_R1: letter})


def test_stale_read_generation():
    m = Module()
    m.seed(1, chord(60, 64)); m.seed(1, chord(60, 67), 1)
    m.worker(); m.switch(1, 1)
    before = m.sb.r(META+64, 4)
    context = suspend_io(m, F_READ)
    task(m, 0x080232A0, {UC_ARM_REG_R0: 0xffffffff})
    request(m, 2); request(m, 1)  # Same final target, different request generation.
    task(m, 0x080232B0)
    assert m.sb.r(META+64, 4) != before
    resume_io(m, context)
    assert m.bank(1) == chord(60, 64), 'obsolete read published after an ABA request'
    assert m.sb.r(m.parents[1]+0x2e, 1) == b'\0'
    assert m.sb.r(META+4, 1) == b'\1'
    m.worker(); assert m.bank(1) == chord(60, 67)


def test_edit_during_flush_generation():
    m = Module()
    m.seed(1, chord(60, 64)); m.seed(1, chord(60, 67), 1)
    m.worker(); m.touch(1); m.sb.w(POLY, chord(60, 65)); m.switch(1, 1)
    context = suspend_io(m, F_WRITE)
    task(m, 0x080232A0, {UC_ARM_REG_R0: 0xffffffff})
    task(m, 0x0804AF00, {UC_ARM_REG_R0: 1})
    m.sb.w(POLY, chord(60, 72))
    task(m, 0x080232B0)
    resume_io(m, context)
    assert m.bank(1) == chord(60, 72)
    assert m.sb.r(META+20, 1) == b'\1', 'new edit falsely marked flushed'
    m.worker()
    assert m.files[m.path(1)] == chord(60, 72)
    assert m.bank(1) == chord(60, 67)


def test_clear_during_read_generation():
    m = Module()
    m.seed(1, chord(60, 64)); m.seed(1, chord(60, 67), 1)
    m.worker(); m.switch(1, 1)
    context = suspend_io(m, F_READ)
    task(m, 0x080232A0, {UC_ARM_REG_R0: 0xffffffff})
    task(m, 0x0804A840, {UC_ARM_REG_R0: m.pattern(1, 1)})
    task(m, 0x080232B0)
    resume_io(m, context)
    assert m.bank(1) == chord(60, 64)
    m.worker(); assert m.bank(1) == bytes(SIZE)


def test_project_clear_during_read_generation():
    m = Module()
    m.seed(1, chord(60, 64)); m.seed(1, chord(60, 67), project=1)
    m.worker()
    # Project-load reset invalidates old work before the stock project ID changes.
    m.call(0x0804A140)
    m.sb.w(PROJECT+0x8c, b'\1')
    context = suspend_io(m, F_READ)
    task(m, 0x080232A0, {UC_ARM_REG_R0: 0xffffffff})
    task(m, 0x0804A840, {UC_ARM_REG_R0: m.pattern(1)})
    task(m, 0x080232B0)
    resume_io(m, context)
    assert m.bank(1) == bytes(SIZE)
    m.worker()
    assert m.bank(1) == bytes(SIZE), 'new-project clear lost after superseded read'
    assert struct.unpack('<I', m.sb.r(META+24, 4))[0] & 1


def main():
    for test in (test_delayed_io_competing_task, test_stale_read_generation,
                 test_edit_during_flush_generation, test_clear_during_read_generation,
                 test_project_clear_during_read_generation):
        test(); print('PASS', test.__name__)
    return 0


if __name__ == '__main__':
    sys.exit(main())
