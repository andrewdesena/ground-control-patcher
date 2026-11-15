#!/usr/bin/env python3
"""Execute installed module lifecycle hooks and real v3.26 stock callers.

FatFS is modeled at its public API boundary. The native text tokenizer and UI /
RTOS services are stubbed; native writer/loader/directory/delete/switch/transpose
and real MIDI emitter code are executed. This certifies emulator behavior, not
physical SD timing or hardware. --require-ready is an assertion gate.
"""
import argparse
import contextlib
from functools import lru_cache
import io
import json
import os
import tempfile
from pathlib import Path
import struct
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
# Keep Python assembly files and clang scratch files in the same writable root.
# clang does not share tempfile's fallback when inherited TMPDIR is unavailable.
os.environ['TMPDIR'] = os.path.realpath('/tmp')
tempfile.tempdir = os.environ['TMPDIR']
import asm
import verify
from fw_sandbox import Sandbox, SENTINEL
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import *

TABLE, POLY, SIZE, META = 0x08038370, 0x1000B530, 2176, 0x1000CF00
PROJECT = 0x2001BB38
LOAD, WRITE = 0x0801CCC4, 0x0801C450
F_OPEN, F_READ, F_WRITE, F_CLOSE = 0x0801496C, 0x08014B30, 0x08014C92, 0x08014F18
MODULES = ['poly-record', 'poly-velhook', 'poly-load', 'poly-save', 'poly-fanout',
           'poly-clear', 'poly-init', 'poly-entry', 'poly-transpose', 'poly-chord', 'poly-lifecycle']


@lru_cache(maxsize=None)
def source(name):
    with contextlib.redirect_stdout(io.StringIO()):
        return asm.build(json.loads((ROOT / 'mods' / f'{name}.source.json').read_text()))


def install(sb, name):
    for p in source(name)['patches']:
        sb.w(int(p['addr'], 0), bytes.fromhex(p['bytes']))


def stub(sb, addr, value=0):
    sb.w(addr, bytes.fromhex('7047'))
    def hook(u, a, size, _):
        u.reg_write(UC_ARM_REG_R0, value)
    sb.uc.hook_add(UC_HOOK_CODE, hook, begin=addr, end=addr)


def cache_setup(uc, parents=None, letters=(0, 0, 0), project=0):
    """Install the real shared cache helper for isolated legacy cave fixtures."""
    parents = parents or (0x20013DEC, 0x200117C8, 0x2000F1A4, 0x2000CB80)
    # Only injected helper bytes; standalone fixtures retain control of their callers.
    for patch in source('poly-lifecycle')['patches'][:1]:
        uc.mem_write(int(patch['addr'], 0), bytes.fromhex(patch['bytes']))
    uc.mem_write(TABLE, struct.pack('<4I', *parents))
    uc.mem_write(META, struct.pack('<I', 0x504f4c59) + bytes([255])*4 +
                 bytes(letters) + b'\0' + bytes([project])*3 + b'\0' +
                 bytes([1])*3 + bytes(45))
    uc.mem_write(PROJECT+0x8c, bytes([project]))
    for parent, letter in zip(parents[1:], letters):
        uc.mem_write(parent+0x2e, bytes([letter]))


def chord(*notes):
    return bytes([len(notes)] + [v for n in notes for v in (n, 90)] + [0] * (16 - 2 * len(notes))) + bytes(SIZE - 17)


class Module:
    def __init__(self):
        self.sb = Sandbox(str(ROOT / 'mods/v1-poly-full.json'))
        self.parents = struct.unpack('<4I', self.sb.r(TABLE, 16))
        self.sb.w(0x20000450, struct.pack('<4I', *self.parents))
        self.files, self.handles, self.events = {}, {}, []
        self.dirs = {'/', '/projectA', '/projectB'} | {f'/project{p}/track{t}' for p in 'AB' for t in 'D123'}
        self.cwd = '/projectA/track1'
        self.open_error, self.read_error, self.write_error, self.close_error = {}, 0, 0, 0
        self.short_write = False
        self.interrupt = None
        self.locked = False
        self.wait_on_contention = False
        self.mutex_waits = []
        self.native_present = True
        for a in [F_OPEN, F_READ, F_WRITE, F_CLOSE, 0x080150B6, 0x08014F32,
                  0x08014F92, 0x08014FF8, 0x08015214, 0x08015172, 0x080232A0, 0x080232B0]:
            self.sb.w(a, bytes.fromhex('7047'))
            self.sb.uc.hook_add(UC_HOOK_CODE, self.fatfs, begin=a, end=a)
        for a in [0x0801536C, 0x08015336, 0x0801EF68, 0x0801EDD4,
                  0x0801AC18, 0x0801C194, 0x0801EC0C, 0x0801ECE8, 0x0801227C]:
            stub(self.sb, a)
        self.sb.w(0x0801A6F8, bytes.fromhex('7047'))
        def parse(u, *_):
            # Boundary: tokenizer returns a parsed, single-step melodic pattern.
            self.sb.w(0x200037A4 + 4, bytes([int(self.native_present), 0]))
            self.sb.w(0x200037A4 + 8, bytes([60, 90, 0]))
            u.reg_write(UC_ARM_REG_R0, 0)
        self.sb.uc.hook_add(UC_HOOK_CODE, parse, begin=0x0801A6F8, end=0x0801A6F8)
        self.call(0x0804A140)
        for t in range(1, 4):
            self.sb.w(self.parents[t] + 0x1F, bytes([t]))
            for letter in range(24):
                p = self.pattern(t, letter)
                self.sb.w(p, struct.pack('<I',0x08038280))
                self.sb.w(p + 4, b'\x01')
                self.sb.w(p + 0x188, b'\x01\x00')
        self.sb.w(PROJECT + 0x8C, b'\x00')

    def call(self, addr, regs=None, **kw):
        self.sb.call(addr, regs=regs, max_steps=kw.pop('max_steps', 2000000), **kw)
        assert self.sb.reg(UC_ARM_REG_PC) == SENTINEL, hex(self.sb.reg(UC_ARM_REG_PC))

    def pattern(self, t, letter=0):
        return self.parents[t] + 0x34 + letter * 0x194

    def path(self, t, letter=0, project=0):
        return f'/project{chr(65+project)}/track{t}/poly{chr(65+letter)}'

    def cstr(self, p):
        return self.sb.r(p, 256).split(b'\0')[0].decode()

    def absolute(self, p):
        return p if p.startswith('/') else self.cwd.rstrip('/') + '/' + p

    def fatfs(self, u, a, size, _):
        regs = [u.reg_read(r) for r in [UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3]]
        r0, r1, r2, r3 = regs
        result = 0
        if a in (0x080232A0, 0x080232B0):
            assert u.reg_read(UC_ARM_REG_SP) % 8 == 0, f'mutex ABI alignment at {a:08x}'
        if a == 0x080232A0:
            if self.locked and self.wait_on_contention:
                self.mutex_waits.append(u.reg_read(UC_ARM_REG_SP))
                u.emu_stop()
                return
            assert not self.locked, 'nested sequencer mutex'
            self.locked = True
        elif a == 0x080232B0:
            assert self.locked, 'unbalanced sequencer mutex'
            self.locked = False
        elif a == F_OPEN:
            path = self.absolute(self.cstr(r1))
            self.events.append(('open', path, r2))
            result = self.open_error.get(path, 0)
            if not result and path.rsplit('/', 1)[0] not in self.dirs:
                result = 5
            if not result and r2 == 1 and path not in self.files:
                result = 4
            if not result and r2 == 6 and path in self.files:
                result = 8
            if not result:
                if r2 & 2:
                    self.files[path] = b''
                self.handles[r0] = path
        elif a == F_READ:
            path = self.handles[r0]
            data = self.files[path][:r2]
            self.sb.w(r1, data)
            self.sb.w(r3, struct.pack('<I', len(data)))
            self.events.append(('read', path, r2))
            result = self.read_error if '/poly' in path else 0
        elif a == F_WRITE:
            path = self.handles[r0]
            n = r2 - int(self.short_write)
            self.files[path] = self.sb.r(r1, n)
            self.sb.w(r3, struct.pack('<I', n))
            self.events.append(('write', path, r1, r2))
            result = self.write_error
        elif a == F_CLOSE:
            self.handles.pop(r0, None)
            result = self.close_error
        elif a == 0x080150B6:
            path = self.absolute(self.cstr(r0))
            self.events.append(('unlink', path))
            result = 0 if path in self.files else 4
            self.files.pop(path, None)
        elif a == 0x08014F32:
            path = self.absolute(self.cstr(r0))
            if path == self.cwd + '/..':
                path = self.cwd.rsplit('/', 1)[0] or '/'
            result = 0 if path in self.dirs else 5
            if not result:
                self.cwd = path
        elif a == 0x08015172:
            data = self.cwd.encode() + b'\0'
            assert len(data) <= r1
            self.sb.w(r0, data)
        elif a == 0x08014F92:
            result = 0 if self.absolute(self.cstr(r1)) in self.dirs else 5
        elif a == 0x08015214:
            self.dirs.add(self.absolute(self.cstr(r0)))
        if a in [F_OPEN, F_READ, F_WRITE, F_CLOSE] and '/poly' in (self.events[-1][1] if self.events else ''):
            assert u.reg_read(UC_ARM_REG_SP) % 8 == 0, 'FatFS alignment'
        if self.interrupt:
            self.interrupt(a, regs)
        u.reg_write(UC_ARM_REG_R0, result)

    def worker(self):
        self.call(0x0804A600)
        assert not self.locked

    def seed(self, t, data, letter=0, project=0):
        self.files[self.path(t, letter, project)] = data

    def bank(self, t):
        return self.sb.r(POLY + (t-1)*SIZE, SIZE)

    def touch(self, t):
        self.call(0x0804AF00, {UC_ARM_REG_R0: t})
        assert self.sb.reg(UC_ARM_REG_R0) == POLY + (t-1)*SIZE

    def switch(self, t, letter):
        # Execute the real stopped module selection caller, including its installed hook.
        self.sb.w(self.parents[t] + 4, bytes([letter]))
        stub(self.sb, 0x08019100, 0)
        self.call(0x08029C78, {UC_ARM_REG_R0: t})

    def save(self, t, letter, dest=None, present=True):
        self.cwd = f'/projectA/track{t if t else "D"}'
        self.sb.w(self.pattern(t, letter) + 4, bytes([int(present)]))
        self.sb.w(self.pattern(t, letter) + 0x188, b'\x01\x00')
        self.call(WRITE, {UC_ARM_REG_R0: 0x2000B250,
                         UC_ARM_REG_R1: self.pattern(t, letter),
                         UC_ARM_REG_R2: letter if dest is None else dest})


def test_sources():
    bundle = json.loads((ROOT / 'mods/v1-poly-full.json').read_text())
    actual = {int(p['addr'], 0): p['bytes'] for p in bundle['patches']}
    stock = verify.index(verify.parse((ROOT / 'testdata/gc326.hex').read_text()))
    seen = set()
    for name in MODULES:
        for p in source(name)['patches']:
            a, data = int(p['addr'], 0), bytes.fromhex(p['bytes'])
            assert actual[a] == p['bytes'], name
            region = set(range(a, a+len(data)))
            assert not seen & region, 'overlap'
            seen |= region
            if a >= 0x08046810:
                assert all(stock.get(b, 255) == 255 for b in region)
    html = (ROOT / 'index.html').read_text()
    embedded = json.loads(html.split('  var V1 = ', 1)[1].split(';\n  var mods', 1)[0])
    assert embedded['patches'] == bundle['patches']
    assert 0x08028224 in actual and 0x0801FD52 in actual


def test_read_buffer_reservation():
    bundle = json.loads((ROOT / 'mods/v1-poly-full.json').read_text())
    reserved = bundle['requires']['ram']
    assert any(int(r['addr'],0) == 0x1000E500 and r['size'] == SIZE+1 for r in reserved)
    assert source('poly-lifecycle')['requires']['ram'] == reserved
    m = Module(); m.seed(3, chord(60,64)+b'X')
    m.sb.w(0x1000ED81, b'canary')
    m.worker()
    assert m.bank(3) == bytes(SIZE), '2177-byte file was accepted'
    assert m.sb.r(0x1000ED80,1) == b'X', 'oversize detection byte was not read'
    assert m.sb.r(0x1000ED81,6) == b'canary'
    assert all(e[2] == SIZE+1 for e in m.events if e[0] == 'read')


def test_boot():
    m = Module()
    m.sb.w(POLY, b'\xaa' * (3*SIZE))
    m.sb.w(META, b'\xaa' * 64)
    m.call(0x080215E8)
    assert m.bank(1) == m.bank(2) == m.bank(3) == bytes(SIZE)
    assert m.sb.r(META, 7) == struct.pack('<I', 0x504f4c59) + b'\xff'*3
    assert m.sb.r(META+16, 3) == bytes(3)


def test_banks_save():
    m = Module()
    for t in (1, 2, 3): m.seed(t, chord(50+t, 60+t))
    m.worker()
    for letter in (0, 1, 2, 3, 23):
        for t in (1, 2, 3):
            m.switch(t, letter)
            m.worker()
            m.touch(t)
            m.sb.w(POLY+(t-1)*SIZE, chord(40+t, 70+t))
            m.save(t, letter)
            assert m.files[m.path(t, letter)] == chord(40+t, 70+t)
    before = {p: d for p, d in m.files.items() if '/poly' in p}
    m.save(0, 0)
    assert before == {p: d for p, d in m.files.items() if '/poly' in p}
    assert not any('trackD/poly' in p for p in m.files)


def test_load_validation():
    for data, read_error, close_error in [(None,0,0), (b'',0,0), (chord(60)[:-1],0,0),
        (chord(60)+b'x',0,0), (b'\xff'*SIZE,0,0),
        (bytes([1, 128, 90])+bytes(SIZE-3),0,0),
        (bytes([1, 60, 0])+bytes(SIZE-3),0,0),
        (bytes([1, 60, 128])+bytes(SIZE-3),0,0), (chord(60),1,0), (chord(60),0,1),
        (chord(60,64),0,0)]:
        m = Module()
        m.sb.w(POLY, b'\xaa' * (SIZE*3))
        if data is not None: m.seed(3, data)
        m.read_error, m.close_error = read_error, close_error
        m.worker()
        good = data == chord(60,64) and not (read_error or close_error)
        assert m.bank(3) == (data if good else bytes(SIZE))
        assert m.bank(1) == m.bank(2) == bytes(SIZE)


def test_switch_dirty_and_failure():
    m = Module()
    m.seed(1, chord(60,64)); m.seed(1, chord(60,67), 1)
    m.seed(2, chord(60,72))
    m.worker()
    m.touch(1); m.sb.w(POLY, chord(60,65))
    m.switch(1, 1)
    assert m.sb.r(m.parents[1]+0x2e, 1) == b'\0', 'switch committed before cache ready'
    assert m.bank(1) == chord(60,65)
    m.write_error = 1
    m.worker()
    assert m.bank(1) == chord(60,65) and m.sb.r(META+20,1) == b'\1'
    assert m.sb.r(m.parents[1]+0x2e,1) == b'\0'
    m.write_error = 0
    m.worker()
    assert m.files[m.path(1)] == chord(60,65)
    assert m.bank(1) == chord(60,67)
    assert m.bank(2) == chord(60,72)
    assert m.sb.r(m.parents[1]+0x2e,1) == b'\1'
    m.switch(1,0); m.worker()
    assert m.bank(1) == chord(60,65)
    # Rapid requests coalesce before committing; no dirty snapshot is discarded.
    m.switch(1,2);m.switch(1,1);m.worker()
    assert m.bank(1) == chord(60,67)


def test_clear_delete_copy():
    m=Module();m.seed(1,chord(60,64));m.worker()
    # Real native clear virtual method.
    m.call(0x0801A4D0,{UC_ARM_REG_R0:m.pattern(1)})
    assert m.bank(1)==bytes(SIZE)
    m.save(1,0,present=False)
    assert m.files[m.path(1)]==bytes(SIZE)
    # Editing after clear removes virtual zero and persists the new snapshot.
    m.touch(1);m.sb.w(POLY,chord(60,67));m.save(1,0)
    assert m.files[m.path(1)]==chord(60,67)
    m.save(1,0,dest=1)
    assert m.files[m.path(1,1)]==chord(60,67)
    m.touch(1);m.sb.w(POLY,chord(60,72));m.save(1,0)
    assert m.files[m.path(1,1)]==chord(60,67)
    # Real delete function builds project, track, pattern paths and checks chdir.
    m.cwd='/'
    m.files['/projectA/track1/patternA.txt']=b'native'
    m.call(0x0801C0D4,{UC_ARM_REG_R0:0x2000b250,UC_ARM_REG_R1:0,UC_ARM_REG_R2:1,UC_ARM_REG_R3:0})
    assert m.path(1) not in m.files
    assert m.bank(1)==bytes(SIZE)
    m.worker();m.switch(1,1);m.worker()
    assert m.path(1) not in m.files, 'delete resurrected by dirty flush'
    assert m.bank(1)==chord(60,67)


def test_native_load():
    for present in (False, True):
        m=Module();m.seed(1,chord(60,64));m.worker()
        # Actual native load, including missing-native bypass of old CD96 hook.
        if present:m.files['/projectA/track1/patternA.txt']=b'{}'
        m.call(LOAD,{UC_ARM_REG_R0:m.pattern(1),UC_ARM_REG_R1:0,UC_ARM_REG_R2:0})
        assert m.bank(1)==(chord(60,64) if present else bytes(SIZE))
        assert m.sb.r(META+16,1)==b'\1'
        m.worker()
        assert m.bank(1)==(chord(60,64) if present else bytes(SIZE))
    # Real 24-letter preload must never publish the last sidecar as the active bank.
    m=Module()
    for letter in range(24):m.seed(1,chord(40+letter),letter)
    for letter in range(24):
        m.cwd='/projectA/track1'
        m.files[f'/projectA/track1/pattern{chr(65+letter)}.txt']=b'{}'
        m.call(LOAD,{UC_ARM_REG_R0:m.pattern(1,letter),UC_ARM_REG_R1:letter,UC_ARM_REG_R2:0})
    m.worker()
    assert m.bank(1)==chord(40)



def test_import_source_identity():
    # Native cwd is source identity; the active project and pointer are destination.
    for source_project, source_track, source_letter, dest_track, dest_letter in [
        (0, 1, 1, 1, 0), (0, 2, 2, 3, 1), (1, 3, 2, 1, 0), (1, 2, 1, 3, 2)]:
        m=Module()
        source_data=chord(60,65+source_track)
        stale_data=chord(60,80+dest_track)
        m.seed(source_track,source_data,source_letter,source_project)
        m.seed(dest_track,stale_data,dest_letter)
        m.worker()
        m.switch(dest_track,dest_letter);m.worker()
        m.cwd=f'/project{chr(65+source_project)}/track{source_track}'
        m.files[m.cwd+f'/pattern{chr(65+source_letter)}.txt']=b'{}'
        if source_project == 1:
            # Real stock import caller establishes source track cwd and picks a
            # destination pattern from independent stack track/letter arguments.
            from fw_sandbox import STACKTOP
            m.cwd='/projectB'
            m.sb.w(STACKTOP,struct.pack('<II',dest_track,dest_letter))
            m.call(0x0801D064,{UC_ARM_REG_R0:0x2000b250,
                             UC_ARM_REG_R1:source_track,UC_ARM_REG_R2:source_letter,
                             UC_ARM_REG_R3:0})
        else:
            m.call(LOAD,{UC_ARM_REG_R0:m.pattern(dest_track,dest_letter),
                         UC_ARM_REG_R1:source_letter,UC_ARM_REG_R2:0})
        m.worker()
        assert m.bank(dest_track)==source_data, (source_project,source_track,source_letter,dest_track,dest_letter)
        assert m.files[m.path(dest_track,dest_letter)]==source_data
        # Source file and later source edits cannot alias destination bytes.
        m.seed(source_track,chord(60,99),source_letter,source_project)
        assert m.bank(dest_track)==source_data
        assert m.files[m.path(dest_track,dest_letter)]==source_data
    # Unsaved source bytes are captured independently before native invalidation.
    m=Module();m.seed(2,chord(60,64));m.worker();m.touch(2)
    m.sb.w(POLY+SIZE,chord(60,72))
    m.cwd='/projectA/track2';m.files[m.cwd+'/patternA.txt']=b'{}'
    m.call(LOAD,{UC_ARM_REG_R0:m.pattern(1),UC_ARM_REG_R1:0,UC_ARM_REG_R2:0})
    m.worker();assert m.bank(1)==chord(60,72)
    m.touch(2);m.sb.w(POLY+SIZE,chord(60,77))
    assert m.bank(1)==chord(60,72)


    # A failed destination write retains active imported data as an owned dirty
    # snapshot instead of letting the worker revive the old destination file.
    m=Module();m.seed(1,chord(60,80));m.seed(2,chord(60,67),1,1);m.worker()
    m.cwd='/projectB/track2';m.files[m.cwd+'/patternB.txt']=b'{}'
    m.open_error[m.path(1)]=1
    m.call(LOAD,{UC_ARM_REG_R0:m.pattern(1),UC_ARM_REG_R1:1,UC_ARM_REG_R2:0})
    assert m.bank(1)==chord(60,67)
    assert m.sb.r(META+20,1)==b'\1'
    m.worker();assert m.bank(1)==chord(60,67)
    m.open_error.clear();m.switch(1,1);m.worker()
    assert m.files[m.path(1)]==chord(60,67)


    # An inactive unsaved clear is also an authoritative source snapshot.
    m=Module();m.seed(1,chord(60,64));m.seed(1,chord(60,67),1);m.worker()
    m.call(0x0801A4D0,{UC_ARM_REG_R0:m.pattern(1,1)})
    m.cwd='/projectA/track1';m.files[m.cwd+'/patternB.txt']=b'{}'
    m.call(LOAD,{UC_ARM_REG_R0:m.pattern(3),UC_ARM_REG_R1:1,UC_ARM_REG_R2:0})
    m.worker();assert m.bank(3)==bytes(SIZE)


def test_foreign_project_delete():
    m=Module();m.seed(1,chord(60,64));m.seed(1,chord(60,72),project=1);m.worker()
    m.touch(1)
    before_bank=m.bank(1);before_meta=m.sb.r(META,64)
    m.files['/projectB/track1/patternA.txt']=b'native'
    m.cwd='/'
    m.call(0x0801C0D4,{UC_ARM_REG_R0:0x2000b250,UC_ARM_REG_R1:1,
                       UC_ARM_REG_R2:1,UC_ARM_REG_R3:0})
    assert m.path(1,project=1) not in m.files
    assert m.bank(1)==before_bank
    assert m.sb.r(META,64)==before_meta
    m.worker();assert m.bank(1)==before_bank

def test_creation():
    m=Module();m.files.clear();m.dirs={'/','/projectA'}
    for t in (1,2,3):
        m.cwd='/projectA'
        # Stock track-directory creator includes its loop of 24 native pattern saves.
        m.call(0x0801C5A8,{UC_ARM_REG_R0:0x2000b250,UC_ARM_REG_R1:t,UC_ARM_REG_R2:1})
        assert all(m.files[m.path(t,l)]==bytes(SIZE) for l in range(24))
    assert not any('trackD/poly' in p for p in m.files)
    m.worker()
    assert m.bank(1)==m.bank(2)==m.bank(3)==bytes(SIZE)


def test_transpose():
    for delta in (12,-12):
        m=Module();m.seed(3,chord(60,64));m.worker()
        # Real success path and real table selection.
        p=m.pattern(3)
        # RAM held managers are distinct objects from flash native parents on hardware.
        m.sb.w(0x20000450+12,struct.pack('<I',0x20006000))
        m.sb.w(0x20006000+0x2db,b'\0')
        m.sb.w(p+8,bytes([60,90,0])*128)
        m.call(0x08028194,{UC_ARM_REG_R0:0,UC_ARM_REG_R1:3,UC_ARM_REG_R2:delta & 0xffffffff})
        assert m.bank(3)[:5]==bytes([2,60+delta,90,64+delta,90])
        assert m.bank(1)==m.bank(2)==bytes(SIZE)
        assert m.sb.r(META+22,1)==b'\1'


def test_copy_stock_caller():
    from fw_sandbox import STACKTOP
    for source_track, dest_track in [(1,1),(1,3),(3,2)]:
        m=Module();m.seed(source_track,chord(60,64));m.worker()
        m.files[f'/projectA/track{source_track}/patternA.txt']=b'{}'
        m.touch(source_track)
        m.sb.w(POLY+(source_track-1)*SIZE,chord(60,67))
        m.sb.w(STACKTOP,struct.pack('<II',dest_track,2))
        m.call(0x0801D200,{UC_ARM_REG_R0:0x2000B250,UC_ARM_REG_R1:0,
                          UC_ARM_REG_R2:source_track,UC_ARM_REG_R3:0})
        assert m.files[m.path(dest_track,2)]==chord(60,67)
        assert m.sb.r(META+48,1)==b'\0'
        m.touch(source_track);m.sb.w(POLY+(source_track-1)*SIZE,chord(60,72))
        assert m.files[m.path(dest_track,2)]==chord(60,67)
        m.switch(dest_track,2);m.worker()
        assert m.bank(dest_track)==chord(60,67)


def test_requests_during_io():
    m=Module();m.seed(1,chord(60,64));m.seed(1,chord(60,67),1);m.seed(1,chord(60,72),2)
    m.worker();m.switch(1,1)
    injected=[]
    def interrupt(addr, regs):
        if addr==F_READ and not injected:
            assert not m.locked
            # Timing caller may queue another byte request, with no filesystem reentry.
            m.sb.w(META+4,b'\2');injected.append(True)
    m.interrupt=interrupt;m.worker();m.interrupt=None
    assert injected and m.sb.r(META+4,1)==b'\2'
    assert m.bank(1)==chord(60,64)
    m.worker();assert m.bank(1)==chord(60,72)


def test_project_switch():
    m=Module();m.seed(1,chord(60,64));m.seed(1,chord(60,67),project=1);m.worker()
    m.touch(1);m.sb.w(POLY,chord(60,65))
    # Execute the installed project entry hook, stop at the original stock body.
    m.sb.call(0x0801DB60,regs={UC_ARM_REG_R0:0x2000b250,UC_ARM_REG_R1:1},stop_at=0x0801DB64)
    assert m.sb.reg(UC_ARM_REG_PC)==0x0801DB64
    assert m.files[m.path(1)]==chord(60,65)
    assert m.bank(1)==m.bank(2)==m.bank(3)==bytes(SIZE)
    assert m.sb.r(META+16,3)==bytes(3)
    m.sb.w(PROJECT+0x8c,b'\1');m.worker()
    assert m.bank(1)==chord(60,67)
    assert m.bank(2)==m.bank(3)==bytes(SIZE)
    # Failed flush keeps old project and dirty cache, rather than discarding it.
    m.touch(1);m.write_error=1
    m.call(0x0801DB60,{UC_ARM_REG_R0:0x2000b250,UC_ARM_REG_R1:0})
    assert m.bank(1)==chord(60,67) and m.sb.r(META+20,1)==b'\1'
    assert m.sb.r(PROJECT+0x8c,1)==b'\1'


def test_playback_switch():
    from fw_sandbox import STACKTOP
    m=Module();m.seed(1,chord(60,64));m.seed(1,chord(60,67),1);m.seed(2,chord(60,72));m.worker()
    voice=0x20008000
    m.sb.w(voice+8,struct.pack('<I',m.parents[1]));m.sb.w(voice+0x3c,b'\0')
    messages=[]
    m.sb.w(0x08019840,bytes.fromhex('7047'))
    def queue(u,a,size,_):
        messages.append(m.sb.r(u.reg_read(UC_ARM_REG_R1),6))
        u.reg_write(UC_ARM_REG_R0,0)
    m.sb.uc.hook_add(UC_HOOK_CODE,queue,begin=0x08019840,end=0x08019840)
    def play():
        messages.clear();m.sb.w(STACKTOP,struct.pack('<III',60,90,1))
        m.sb.call(0x080217F4,regs={UC_ARM_REG_R0:0,UC_ARM_REG_R1:1000,UC_ARM_REG_R2:50,
                  UC_ARM_REG_R3:7,UC_ARM_REG_R5:voice},stop_at=0x080217F8)
        assert m.sb.reg(UC_ARM_REG_PC)==0x080217F8
        return [msg[4] for msg in messages if msg[0]==0x90]
    assert play()==[64,60]
    # Real running chain caller: override branch requests B and returns to the sequencer.
    # Override table comes from the stock PC-relative literal at 0x0802315c.
    ins=m.sb.dis(0x0802315C,2)[0]
    off=int(ins.op_str.split('#')[1].split(']')[0],0)
    table=int.from_bytes(m.sb.r(((ins.address+4)&~3)+off,4),'little')
    m.sb.w(table+0x35+1,b'\1');m.sb.w(table+0x39+1,b'\1')
    m.call(0x08023158,{UC_ARM_REG_R0:m.parents[1]})
    assert play()==[64,60], 'old pattern remains paired with old cache until commit'
    m.worker();assert play()==[67,60]
    # An unexpected direct parent letter change suppresses old extras even with the SAME primary.
    m.sb.w(m.parents[1]+0x2e,b'\0')
    assert play()==[60]
    m.worker();assert play()==[64,60]
    m.sb.w(PROJECT+0x8c,b'\1')
    assert play()==[60]
    m.worker();assert play()==[60]


def test_inline_clear_and_entry():
    m=Module();m.seed(2,chord(60,64));m.worker()
    p=m.pattern(2)
    # The inline module clear ends with movs/strh, then native length lookup.
    m.sb.call(0x0802BEFC,regs={UC_ARM_REG_R8:p},stop_at=0x0802BF02)
    assert m.sb.reg(UC_ARM_REG_PC)==0x0802BF02
    assert m.bank(2)==bytes(SIZE)
    m.save(2,0);assert m.files[m.path(2)]==bytes(SIZE)
    manager,event=0x20006000,0x20006400
    m.sb.w(manager+0x2e1,b'\2');m.sb.w(manager+0x2df,b'\4')
    m.sb.w(manager+0x120,b'\3')
    m.sb.w(event,b'\x90')
    stub(m.sb,0x080190A6)
    for note,vel in [(60,100),(64,90),(60,80)]:
        m.sb.w(event+4,bytes([note,vel]))
        m.sb.call(0x0801FD30,regs={UC_ARM_REG_R0:manager,UC_ARM_REG_R1:event},stop_at=0x0801FD56)
        assert m.sb.reg(UC_ARM_REG_PC)==0x0801FD56
    addr=POLY+SIZE+4*17
    assert m.sb.r(addr,5)==bytes([2,60,80,64,90])
    assert m.sb.reg(UC_ARM_REG_R6)==3
    # Real rest commit follows BGE using the flags restored by the installed hook.
    m.call(0x0801F32C,{UC_ARM_REG_R0:manager,UC_ARM_REG_R1:0xffffffff})
    assert m.sb.r(addr,17)==bytes(17)
    assert m.sb.r(manager+0x2f7,1)==b'\0'


def test_held_octave():
    m=Module();m.seed(3,chord(60,64));m.worker()
    manager=0x20006000
    m.sb.w(0x20000450+3*4,struct.pack('<I',manager))
    m.sb.w(manager+0x2db,b'\1');m.sb.w(manager+0x2e1,b'\3')
    m.sb.w(manager+0x2df,b'\0');m.sb.w(manager+0x120,b'\2')
    m.sb.w(manager+8,b'\x3c');m.sb.w(manager+20,b'\x40')
    m.call(0x08028194,{UC_ARM_REG_R0:0,UC_ARM_REG_R1:3,UC_ARM_REG_R2:12})
    assert m.bank(3)[:5]==bytes([2,72,90,76,90])
    assert m.sb.r(manager+8,1)==b'\x48' and m.sb.r(manager+20,1)==b'\x4c'
    # Bounds failure in stock held transpose must not touch the poly snapshot.
    before=m.bank(3)
    m.call(0x08028194,{UC_ARM_REG_R0:0,UC_ARM_REG_R1:3,UC_ARM_REG_R2:100})
    assert m.bank(3)==before


def test_project_save_destination():
    m=Module();m.seed(1,chord(60,64));m.worker();m.touch(1)
    m.sb.w(0x2000b250+0x249,b'\1')
    m.cwd='/projectB'
    m.call(0x0801C5A8,{UC_ARM_REG_R0:0x2000b250,UC_ARM_REG_R1:1,UC_ARM_REG_R2:1})
    assert m.files[m.path(1,0,project=1)]==chord(60,64)
    assert m.sb.r(META+49,1)==b'\0'
    assert m.sb.r(PROJECT+0x8c,1)==b'\0'
    assert m.sb.r(META+20,1)==b'\1', 'copying to another project did not save source'


def test_sd_task_receive():
    from fw_sandbox import STACKTOP
    m=Module();m.seed(1,chord(60,64));m.seed(1,chord(60,67),1)
    m.worker();m.switch(1,1)
    receives=[]
    m.sb.w(0x08033256,bytes.fromhex('7047'))
    def receive(u,a,n,_):
        assert u.reg_read(UC_ARM_REG_R2)==1
        assert not m.locked
        receives.append(True)
        u.reg_write(UC_ARM_REG_R0,int(len(receives)==3))
    m.sb.uc.hook_add(UC_HOOK_CODE,receive,begin=0x08033256,end=0x08033256)
    m.sb.call(0x08020706,regs={UC_ARM_REG_R0:0x1234,UC_ARM_REG_R1:STACKTOP-100},stop_at=0x0802070A)
    assert m.sb.reg(UC_ARM_REG_PC)==0x0802070A and len(receives)==3
    assert m.bank(1)==chord(60,67)


def test_new_project_unsaved_switch():
    m=Module();m.files.clear();m.dirs={'/'};m.worker()
    assert m.bank(1)==bytes(SIZE)
    m.touch(1);m.sb.w(POLY,chord(60,64));m.switch(1,1)
    cwd=m.cwd;m.worker()
    assert m.cwd==cwd, 'absolute write mkdir must not alter stock cwd'
    assert m.files[m.path(1)]==chord(60,64)
    assert m.bank(1)==bytes(SIZE)
    assert '/projectA/track1' in m.dirs
    m.switch(1,0);m.worker();assert m.bank(1)==chord(60,64)
    assert not any('trackD/poly' in p for p in m.files)


def test_clear_track_stock_caller():
    m=Module();m.seed(1,chord(60,64));m.seed(1,chord(60,67),23);m.worker()
    # Stock track reset walks all 24 real native virtual clear methods.
    m.call(0x080231E8,{UC_ARM_REG_R0:m.parents[1]})
    assert m.bank(1)==bytes(SIZE)
    assert struct.unpack('<I',m.sb.r(META+24,4))[0]==0xffffff
    m.save(1,23,present=False)
    assert m.files[m.path(1,23)]==bytes(SIZE)
    m.switch(1,23);m.worker();assert m.bank(1)==bytes(SIZE)


# Readiness is an emulator release gate. Physical-card timing remains a separate
# hardware qualification; no JSON status string can substitute for these checks.
REQUIRED_READINESS_HOOKS = frozenset({
    0x0801A4D0, 0x0801C16E, 0x0801C542, 0x0801CCC4, 0x0801D300,
    0x0801DB60, 0x0801F32E, 0x0801FD52, 0x08020706, 0x080215E8,
    0x080217F4, 0x0802178C, 0x0801F328, 0x0802BEFC, 0x08028224, 0x08029C8E, 0x08019A92, 0x08019840,
})
REQUIRED_READINESS_TESTS = frozenset({
    'test_sources', 'test_boot', 'test_native_load', 'test_copy_stock_caller',
    'test_project_switch', 'test_import_source_identity',
    'test_foreign_project_delete', 'test_delayed_io_competing_task',
    'test_real_queue_capacity', 'test_readiness_gate',
    'test_stale_read_generation', 'test_edit_during_flush_generation',
    'test_clear_during_read_generation', 'test_project_clear_during_read_generation',
    'test_stock_save_concurrent_edit', 'test_stock_save_disk_read_changed',
    'test_stock_copy_destination_changed',
    'test_project_flush_concurrent_edit', 'test_installed_mutation_publication',
    'test_real_tie_capacity', 'test_read_buffer_reservation',
})


def readiness_errors(bundle, expected, completed):
    """Return concrete reasons a candidate has not earned emulator readiness."""
    actual = {int(p['addr'], 0): p['bytes'] for p in bundle['patches']}
    errors = [f'missing installed hook 0x{a:08X}'
              for a in sorted(REQUIRED_READINESS_HOOKS - actual.keys())]
    errors += [f'installed/source bytes differ at 0x{a:08X}'
               for a, data in expected.items() if actual.get(a) != data]
    errors += [f'unexpected installed patch 0x{a:08X}'
               for a in sorted(actual.keys() - expected.keys())]
    if len(actual) != len(bundle['patches']):
        errors.append('duplicate installed patch address')
    errors += [f'required regression did not pass: {name}'
               for name in sorted(REQUIRED_READINESS_TESTS - set(completed))]
    return errors


def assert_ready(completed, bundle=None):
    if bundle is None:
        bundle = json.loads((ROOT / 'mods/v1-poly-full.json').read_text())
    expected = {int(p['addr'], 0): p['bytes'] for name in MODULES
                for p in source(name)['patches']}
    errors = readiness_errors(bundle, expected, completed)
    if errors:
        raise AssertionError('module-only readiness refused:\n' + '\n'.join(errors))


def test_readiness_gate():
    # Negative checks prove the CLI gate refuses stale/missing hooks and skipped
    # QA regressions, even when the candidate claims a successful status.
    bundle = json.loads((ROOT / 'mods/v1-poly-full.json').read_text())
    expected = {int(p['addr'], 0): p['bytes'] for p in bundle['patches']}
    completed = REQUIRED_READINESS_TESTS
    assert not readiness_errors(bundle, expected, completed)
    missing = {**bundle, 'patches': [p for p in bundle['patches']
               if int(p['addr'], 0) != LOAD], 'status': 'ready'}
    assert any('missing installed hook' in e
               for e in readiness_errors(missing, expected, completed))
    corrupt = json.loads(json.dumps(bundle))
    patch = next(p for p in corrupt['patches'] if int(p['addr'], 0) == LOAD)
    patch['bytes'] = ('00' if patch['bytes'][:2] != '00' else 'ff') + patch['bytes'][2:]
    assert any('bytes differ' in e
               for e in readiness_errors(corrupt, expected, completed))
    unexpected = {**bundle, 'patches': bundle['patches'] +
                  [{'addr': '0x08010000', 'bytes': '0000'}]}
    assert any('unexpected installed patch' in e
               for e in readiness_errors(unexpected, expected, completed))
    errors = readiness_errors(bundle, expected, completed - {'test_real_queue_capacity'})
    assert errors == ['required regression did not pass: test_real_queue_capacity']


def main():
    from test_poly_sd_concurrency import (test_delayed_io_competing_task,
        test_stale_read_generation, test_edit_during_flush_generation,
        test_clear_during_read_generation, test_project_clear_during_read_generation,
        test_stock_save_concurrent_edit, test_stock_save_disk_read_changed,
        test_stock_copy_destination_changed,
        test_project_flush_concurrent_edit, test_installed_mutation_publication)
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--require-ready',action='store_true')
    parser.add_argument('--export')
    args=parser.parse_args()
    tests=[test_sources,test_read_buffer_reservation,test_boot,test_banks_save,test_load_validation,test_switch_dirty_and_failure,
           test_clear_delete_copy,test_native_load,test_creation,test_transpose,
           test_copy_stock_caller,test_requests_during_io,test_project_switch,test_playback_switch,
           test_inline_clear_and_entry,test_held_octave,test_project_save_destination,test_sd_task_receive,
           test_new_project_unsaved_switch,test_clear_track_stock_caller,
           test_import_source_identity,test_foreign_project_delete,
           test_delayed_io_competing_task,test_stale_read_generation,
           test_edit_during_flush_generation,test_clear_during_read_generation,
           test_project_clear_during_read_generation,test_stock_save_concurrent_edit,
           test_stock_save_disk_read_changed,test_stock_copy_destination_changed,test_project_flush_concurrent_edit,
           test_installed_mutation_publication,test_readiness_gate]
    completed = set()
    for test in tests:
        test();completed.add(test.__name__);print('PASS',test.__name__)
    if args.require_ready:
        from test_fanout_real import test_real_queue_capacity, test_real_tie_capacity
        test_real_queue_capacity()
        completed.add('test_real_queue_capacity')
        test_real_tie_capacity()
        completed.add('test_real_tie_capacity')
        assert_ready(completed)
        print('PASS module-only readiness: installed bytes and all required QA regressions')
    if args.export:
        out=Path(args.export);out.mkdir(parents=True,exist_ok=True)
        (out/'candidate.json').write_text((ROOT/'mods/v1-poly-full.json').read_text())
    print('PASS module-only lifecycle suites')
    return 0


if __name__=='__main__':sys.exit(main())
