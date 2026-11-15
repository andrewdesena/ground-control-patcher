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


def suspend_io(m, boundary, run=None, select=None):
    """Stop the SD task inside FatFS, leaving I/O incomplete until resumed."""
    stopped = []
    def interrupt(address, regs):
        if address in (F_OPEN, F_READ, F_WRITE, F_CLOSE, 0x08015214):
            assert not m.locked, f'filesystem under sequencer mutex at {address:08x}'
        if (address == boundary and not stopped
                and (select is None or select(address, regs))):
            stopped.append(True)
            m.sb.uc.emu_stop()
    m.interrupt = interrupt
    (run or (lambda: m.sb.call(0x0804A600, max_steps=2000000)))()
    assert stopped and m.sb.reg(UC_ARM_REG_PC) == boundary
    return m.sb.uc.context_save()


def resume_io(m, context, stop_at=None):
    hook = None
    if stop_at is not None:
        def stop(u, address, size, _): u.emu_stop()
        hook = m.sb.uc.hook_add(UC_HOOK_CODE, stop, begin=stop_at, end=stop_at)
    m.sb.uc.context_restore(context)
    # The modeled API has produced its result; complete its bx lr only now.
    m.sb.uc.emu_start(m.sb.reg(UC_ARM_REG_LR) | 1, SENTINEL, count=2000000)
    assert m.sb.reg(UC_ARM_REG_PC) == (stop_at or SENTINEL)
    if hook is not None: m.sb.uc.hook_del(hook)
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


def poly_io(m, track=None):
    """Select the sidecar API, excluding the stock writer's native text I/O."""
    def selected(address, regs):
        path = m.cstr(regs[1]) if address == F_OPEN else m.handles.get(regs[0], m.events[-1][1] if m.events else '')
        return '/poly' in path and (track is None or f'/track{track}/' in path)
    return selected


def edit_task(m, track, data):
    task(m, 0x080232A0, {UC_ARM_REG_R0: 0xffffffff})
    task(m, 0x0804AF00, {UC_ARM_REG_R0: track})
    m.sb.w(POLY+(track-1)*SIZE, data)
    task(m, 0x080232B0)


def test_stock_save_concurrent_edit():
    # Execute the installed real stock native writer, including its close hook.
    # Suspend before or after write consumption, then change source RAM.
    for boundary in (F_OPEN, F_WRITE, F_CLOSE):
        m = Module(); m.seed(1, chord(60, 64)); m.worker()
        m.touch(1); m.sb.w(POLY, chord(60, 65))
        def save():
            m.sb.call(0x0801C450, regs={UC_ARM_REG_R0:0x2000B250,
                      UC_ARM_REG_R1:m.pattern(1), UC_ARM_REG_R2:0}, max_steps=2000000)
        context = suspend_io(m, boundary, save, poly_io(m))
        edit_task(m, 1, chord(60, 72))
        resume_io(m, context)
        assert m.files[m.path(1)] == chord(60, 65), 'writer did not use independent snapshot'
        assert m.bank(1) == chord(60, 72)
        assert m.sb.r(META+20, 1) == b'\1', 'stock save marked a newer edit clean'
        m.save(1, 0)
        assert m.files[m.path(1)] == chord(60, 72)
        assert m.sb.r(META+20, 1) == b'\0'


def test_stock_save_disk_read_changed():
    m = Module(); m.seed(1, chord(60,64)); m.seed(1, chord(60,67), 1); m.worker()
    # Saving a non-active letter with an untagged cache must preserve that file,
    # not read it back and overwrite it with the active bank.
    m.sb.call(0x0801C450, regs={UC_ARM_REG_R0:0x2000B250,
              UC_ARM_REG_R1:m.pattern(1,1), UC_ARM_REG_R2:1}, max_steps=2000000)
    assert m.bank(1) == chord(60,64)
    assert m.sb.r(META+20,1) == b'\0'
    assert m.files[m.path(1,1)] == chord(60,67)
    assert not any(e[0] == 'write' and '/poly' in e[1] for e in m.events)


def test_stock_copy_destination_changed():
    for change in ('edit', 'ownership', 'mask', 'request_aba', 'project'):
        m = Module(); m.seed(1, chord(60, 64)); m.seed(3, chord(60, 80)); m.worker()
        m.touch(1); m.sb.w(POLY, chord(60, 65))
        def copy():
            m.sb.w(STACKTOP, struct.pack('<II', 3, 0))
            m.sb.call(0x0801D200, regs={UC_ARM_REG_R0:0x2000B250, UC_ARM_REG_R1:0,
                                      UC_ARM_REG_R2:1, UC_ARM_REG_R3:0}, max_steps=2000000)
        context = suspend_io(m, F_WRITE, copy, poly_io(m, 3))
        task(m, 0x080232A0, {UC_ARM_REG_R0:0xffffffff})
        if change == 'edit':
            task(m, 0x0804AF00, {UC_ARM_REG_R0:3})
            m.sb.w(POLY+2*SIZE, chord(60, 72))
        elif change == 'ownership':
            m.sb.w(META+10, b'\1')
        elif change == 'mask':
            m.sb.w(META+32, struct.pack('<I', 1))
        elif change == 'request_aba':
            task(m, 0x0804A280, {UC_ARM_REG_R0:m.parents[3], UC_ARM_REG_R1:1})
            task(m, 0x0804A280, {UC_ARM_REG_R0:m.parents[3], UC_ARM_REG_R1:0})
        else:
            m.sb.w(PROJECT+0x8c, b'\1')
        task(m, 0x080232B0)
        before = m.sb.r(META, 84); bank = m.bank(3)
        resume_io(m, context, stop_at=0x0801D304)
        # Save-as wrapper may clear its scoped override, but no cache metadata
        # may be cleared or invalidated by this stale completion.
        after = bytearray(m.sb.r(META, 84)); before = bytearray(before)
        before[48] = after[48] = 0
        assert after == before, (change, [(i,x,y) for i,(x,y) in enumerate(zip(before,after)) if x!=y])
        assert m.bank(3) == bank, change
        assert m.files[m.path(3)] == chord(60, 65)


def test_project_flush_concurrent_edit():
    for boundary, write_track, edit_track in ((F_OPEN, 1, 1), (F_WRITE, 1, 1),
                                               (F_WRITE, 2, 1), (F_WRITE, 2, 3)):
        m = Module()
        for track in (1, 2, 3): m.seed(track, chord(60, 64+track))
        m.worker()
        for track in (1, 2): m.touch(track)
        initial = [m.bank(t) for t in (1, 2, 3)]
        def load():
            m.sb.call(0x0801DB60, regs={UC_ARM_REG_R0:0x2000b250, UC_ARM_REG_R1:1},
                      stop_at=0x0801DB64, max_steps=2000000)
        context = suspend_io(m, boundary, load, poly_io(m, write_track))
        edit_task(m, edit_track, chord(60, 72))
        resume_io(m, context)
        assert m.files[m.path(write_track)] == initial[write_track-1]
        assert m.bank(edit_track) == chord(60, 72), 'project load discarded a newer edit'
        assert m.sb.r(META+20+edit_track-1, 1) == b'\1'
        assert m.sb.r(PROJECT+0x8c, 1) == b'\0'
        assert m.sb.r(META+16, 3) == b'\1'*3
        # Retry the real installed caller. All dirty banks must persist before reset.
        load()
        assert m.sb.reg(UC_ARM_REG_PC) == 0x0801DB64
        assert m.files[m.path(edit_track)] == chord(60, 72)
        assert all(m.bank(t) == bytes(SIZE) for t in (1, 2, 3))


def test_installed_mutation_publication():
    for mutation in ('inline_clear', 'held_transpose'):
        m = Module(); m.seed(1, chord(60, 64)); m.seed(1, chord(60, 67), 1)
        m.worker(); m.switch(1, 1)
        stopped = []
        def during_copy(u, address, size, _):
            # Stop after the new count byte has been copied, before the first note.
            if u.reg_read(UC_ARM_REG_R3) == POLY and not stopped:
                assert m.locked
                stopped.append(True); u.emu_stop()
        hook = m.sb.uc.hook_add(UC_HOOK_CODE, during_copy, begin=0x0803543A, end=0x0803543A)
        m.sb.call(0x0804A600, max_steps=2000000)
        assert stopped
        worker = m.sb.uc.context_save()
        m.sb.uc.hook_del(hook)
        m.wait_on_contention = True
        # A different UI task enters the real installed caller with no mutex.
        if mutation == 'inline_clear':
            start = 0x0802BEFC
            m.sb.uc.reg_write(UC_ARM_REG_R8, m.pattern(1, 1))
            # The installed hook continues into a larger stock UI function.
            # Stop exactly after its complete mutation and metadata update.
            def end(u, address, size, _): u.emu_stop()
            end_hook = m.sb.uc.hook_add(UC_HOOK_CODE, end, begin=0x0802BF02, end=0x0802BF02)
        else:
            manager = 0x20006000
            m.sb.w(0x20000450+4, struct.pack('<I', manager))
            m.sb.w(manager+0x2db, b'\1'); m.sb.w(manager+0x2e1, b'\1')
            m.sb.w(manager+0x2df, b'\0'); m.sb.w(manager+0x120, b'\2')
            m.sb.w(manager+8, b'\x3c'); m.sb.w(manager+20, b'\x40')
            start = 0x08028194
            for reg, value in ((UC_ARM_REG_R0,0),(UC_ARM_REG_R1,1),(UC_ARM_REG_R2,12)):
                m.sb.uc.reg_write(reg, value)
        m.sb.uc.reg_write(UC_ARM_REG_SP, STACKTOP-0x3000)
        m.sb.uc.reg_write(UC_ARM_REG_LR, SENTINEL|1)
        m.sb.uc.emu_start(start|1, SENTINEL, count=200000)
        assert m.mutex_waits and m.sb.reg(UC_ARM_REG_PC) == 0x080232A0
        waiting = m.sb.uc.context_save()
        # Finish publication, then allow the waiting caller to acquire its lock.
        m.sb.uc.context_restore(worker)
        m.sb.uc.emu_start(m.sb.reg(UC_ARM_REG_PC)|1, SENTINEL, count=2000000)
        assert m.sb.reg(UC_ARM_REG_PC) == SENTINEL and not m.locked
        assert m.bank(1) == chord(60, 67)
        m.sb.uc.context_restore(waiting)
        m.sb.uc.emu_start(m.sb.reg(UC_ARM_REG_PC)|1, SENTINEL, count=2000000)
        assert not m.locked
        assert m.bank(1) == (bytes(SIZE) if mutation == 'inline_clear' else chord(72, 79))
        assert m.sb.r(META+20, 1) == b'\1'
        assert m.sb.r(META+8, 1) == b'\1'
        if mutation == 'inline_clear':
            m.sb.uc.hook_del(end_hook)
            assert struct.unpack('<I', m.sb.r(META+24,4))[0] & 2
            assert m.sb.r(m.pattern(1,1)+4,2) == b'\1\0'
        else:
            assert m.sb.r(manager+8,1) == b'\x48'
            assert m.sb.r(manager+20,1) == b'\x4c'


def main():
    for test in (test_delayed_io_competing_task, test_stale_read_generation,
                 test_edit_during_flush_generation, test_clear_during_read_generation,
                 test_project_clear_during_read_generation, test_stock_save_concurrent_edit,
                 test_stock_save_disk_read_changed, test_stock_copy_destination_changed,
                 test_project_flush_concurrent_edit, test_installed_mutation_publication):
        test(); print('PASS', test.__name__)
    return 0


if __name__ == '__main__':
    sys.exit(main())
