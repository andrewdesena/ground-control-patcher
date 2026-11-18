#!/usr/bin/env python3
"""Exercise the installed v1.19 hooks and restore faulty behavior as controls."""

import json
import struct
import zlib
from pathlib import Path

from unicorn import UC_HOOK_CODE
from unicorn.arm_const import *

from asm import assemble
from fw_sandbox import Sandbox, SENTINEL
from test_poly_editlights6 import EDITOR, PARENTS, CACHE, setup, render, frame, stock_bits
from test_poly_entry_toggle import bench, press, STEP, state
from test_poly_save_letter import STUBS
from test_poly_track3 import TRACKS
from test_poly_commit_reload import sidecar, SWITCH_FLAG

BUNDLE = Path(__file__).resolve().parent.parent / 'mods/v1-poly-v119.json'
OWNER = 0x1000D740
BANK = 0x1000B530
SIZE = 0x880
TMP = 0x20018000


def install(sb, address, *instructions):
    sb.w(address, assemble(list(instructions), address))


def run(sb, address, registers=None, stop=SENTINEL):
    sb.call(address, regs=registers, stop_at=stop, max_steps=2000000)
    assert sb.reg(UC_ARM_REG_PC) == stop


def neutralize(sb, *addresses):
    for address in addresses:
        install(sb, address, 'movs r0, #0', 'bx lr')


def test_hard_delete():
    stock = Sandbox()
    for inline in (False, True):
        entry, hook, finish = ((0x0802F2DE, 0x0802F2EE, 0x0802F306) if inline
                               else (0x0802BEC2, 0x0802BEDE, 0x0802BEFC))
        for owner, mode in ((5, 'fixed'), (0, 'fixed'), (1, 'fixed'), (5, 'old')):
            sb, block, bank = bench(letter=4)
            sb.w(OWNER + 4, struct.pack('<I', owner))
            sb.w(block + 8, bytes([60, 90, 7]) * 128)
            payload = sidecar(60, 64, 67)
            sb.w(bank, payload)
            if mode == 'old':
                # Both old hooks jumped to the continuation, skipping the note store.
                install(sb, hook, f'b.w {hook + 4:#x}')
            registers = ({UC_ARM_REG_R4: block} if inline else
                         {UC_ARM_REG_R4: block - 0x34, UC_ARM_REG_R7: TRACKS[1],
                          UC_ARM_REG_R8: block, UC_ARM_REG_R10: 4, UC_ARM_REG_R11: 0x194})
            run(sb, entry, registers, stop=finish)
            expected_note = 60 if mode == 'old' else 128
            assert sb.r(block + 8, 384) == bytes([expected_note, 0, 0]) * 128
            assert sb.r(bank, SIZE) == (bytes(SIZE) if owner == 5 and mode == 'fixed' else payload)
            assert sb.r(hook, 4) != stock.r(hook, 4)
    print('PASS both hard-delete loops clear native notes and the owned bank')


def test_entry():
    for mode in ('fixed', 'old'):
        sb, block, bank = bench(rec=[60, 64, 67], step_note=128)
        if mode == 'old':
            # The old wrapper treated any plausible count as a live chord.
            ops = sb.dis(0x0804B500, 0x100)
            start = next(op.address for op in ops if op.op_str == 'r0, [r7]')
            valid = next(op.address for op in ops if op.op_str == 'r0, [r5]')
            sb.w(start, struct.pack("<H", 0xE000 | ((valid - start - 4) // 2)))
        press(sb, block, 59)
        got = state(sb, block, bank)
        assert got == ((1, [59], 59) if mode == 'fixed' else (4, [60, 64, 67, 59], 59)), got

    sb, block, bank = bench(rec=[60, 64])
    sb.w(block, bytes([0, 3, 0, 0]))
    sb.w(TMP, bytes(3))
    sb.w(0x1000E500, b'\xa5' * SIZE)
    press(sb, block, 55, velocity=89)
    record = sb.r(bank + STEP * 17, 17)
    assert record[5:7] == bytes([55, 89]) and sb.r(block + 8 + 3 * STEP, 2) == bytes([55, 89])
    assert sb.r(block + 4, 2) == b'\1\0'
    assert sb.r(0x1000E500, SIZE) == b'\xa5' * SIZE
    sb.w(block + 4, b'\0\0')
    press(sb, block, 60)
    assert sb.r(block + 4, 2) == b'\1\0'
    sb.w(OWNER + 4, struct.pack('<I', 2))
    press(sb, block, 63)
    assert state(sb, block, bank) == (1, [63], 63)
    assert sb.r(OWNER + 4, 4) == struct.pack('<I', 1)
    print('PASS edit rejects stale records, preserves snapshot bytes and writes velocity and dirty state')


def test_save():
    for candidate in (True, False):
        sb, block, bank = bench(letter=0, rec=[60, 64])
        if not candidate:
            # Without the new writer the file contains only stock pattern text.
            sb.w(0x0801C542, Sandbox().r(0x0801C542, 6))
        press(sb, block, 55, velocity=89)
        sb.w(block + 0x188, struct.pack('<HH', STEP + 1, STEP + 1))
        results = {'names': [], 'notes': []}

        def capture(uc, addr, size, _):
            r0 = uc.reg_read(UC_ARM_REG_R0)
            r1 = uc.reg_read(UC_ARM_REG_R1)
            if addr == 0x0801496C:
                results['names'].append(sb.r(r1, 20).split(b'\0')[0])
            elif addr == 0x0801EF68:
                results['notes'].append(r0)
            elif addr == 0x08014C92:
                results['sidecar'] = sb.r(r1, uc.reg_read(UC_ARM_REG_R2))
            uc.reg_write(UC_ARM_REG_R0, 0)
            uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

        for addr in set(STUBS) | {0x0801496C}:
            sb.uc.hook_add(UC_HOOK_CODE, capture, begin=addr, end=addr)
        run(sb, 0x0801C450, {UC_ARM_REG_R1: block, UC_ARM_REG_R2: 4})
        assert results['notes'][STEP] == 55
        assert results['names'] == [b'patternE.txt']
        if candidate:
            trailer = results['sidecar']
            payload = trailer[8:-4]
            assert trailer[:8] == b'\0GCP1\0\0\0'
            assert trailer[-4:] == struct.pack('<I', zlib.crc32(payload))
            assert payload[STEP * 17:STEP * 17 + 7] == bytes([3, 60, 90, 64, 90, 55, 89])
            assert sb.r(OWNER + 4, 4) == struct.pack('<I', 1)
        else:
            assert 'sidecar' not in results
    print('PASS Save As writes the edited native note and chord trailer to a single FIL')


def test_editor_lights():
    patches = json.loads(BUNDLE.read_text())['patches']
    for track in (1, 2, 3):
        sb = setup(track=track, letter=4)
        for patch in patches:
            addr = int(patch['addr'], 0)
            if addr in (0x08011FC6, 0x08012068, 0x08048000):
                sb.w(addr, bytes.fromhex(patch['bytes']))
        sb.w(OWNER + track * 4, struct.pack('<I', 5))
        render(sb)
        sb.w(CACHE + 1, b'\x3e')
        run(sb, 0x08012C12)
        keys = set(range(24)) | {31}
        assert frame(sb) & keys == stock_bits(sb, (60, 64, 67))
        sb.w(OWNER + track * 4, struct.pack('<I', 1))
        run(sb, 0x08012C12)
        assert frame(sb) & keys == stock_bits(sb, (60,))
        # The old cave accepts the same bank even while its owner is another letter.
        from test_poly_editlights6 import apply
        apply(sb, 'poly-editlights6')
        sb.uc.ctl_remove_cache(0x08048000, 0x08048200)
        sb.w(CACHE + 1, b'\x3c')
        run(sb, 0x08012C12)
        assert frame(sb) & keys == stock_bits(sb, (60, 64, 67))
    print('PASS page 6 renders tracks 1–3 with the right owner and tolerates a stale cache')


def install_fatfs(sb, files):
    opened, handle = [], {}

    def io(uc, addr, size, _):
        fil = uc.reg_read(UC_ARM_REG_R0)
        r1 = uc.reg_read(UC_ARM_REG_R1)
        r2 = uc.reg_read(UC_ARM_REG_R2)
        r3 = uc.reg_read(UC_ARM_REG_R3)
        result = 0
        if addr == 0x0801496C:
            name = sb.r(r1, 40).split(b'\0')[0]
            opened.append(name)
            if r2 & 8:
                files[name] = b''
                handle[fil] = [name, 0]
            elif name not in files:
                result = 4
            else:
                handle[fil] = [files[name], 0]
                sb.w(fil + 12, struct.pack('<I', len(files[name])))
        elif addr == 0x08014B30:
            data, pos = handle[fil]
            chunk = data[pos:pos + r2]
            sb.w(r1, chunk)
            sb.w(r3, struct.pack('<I', len(chunk)))
            handle[fil][1] += len(chunk)
        elif addr == 0x08014C92:
            name, pos = handle[fil]
            original = files[name]
            files[name] = original[:pos] + sb.r(r1, r2) + original[pos + r2:]
            handle[fil][1] += r2
            sb.w(r3, struct.pack('<I', r2))
        elif addr == 0x08014F18:
            handle.pop(fil, None)
        uc.reg_write(UC_ARM_REG_R0, result)
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    for addr in (0x0801496C, 0x08014B30, 0x08014C92, 0x08014F18):
        sb.uc.hook_add(UC_HOOK_CODE, io, begin=addr, end=addr)
    return opened


def pattern_file(native, payload):
    return native + b'\0GCP1\0\0\0' + payload + struct.pack('<I', zlib.crc32(payload))


def test_commit_owner():
    payload = sidecar(60, 64, 67)
    name = b'/projectA/track3/patternA.txt'
    for mode in ('valid', 'stock', 'corrupt', 'truncated', 'missing', 'old_owner'):
        sb = Sandbox(BUNDLE)
        for slot, track in enumerate(TRACKS):
            sb.w(track + 0x2D, bytes([slot == 0]))
        neutralize(sb, 0x08023158, 0x080232A0, 0x080232B0)
        native = b'{"steps":[]}'.ljust(10200)
        file = pattern_file(native, payload)
        files = {name: {'stock': native, 'corrupt': file[:-1] + bytes([file[-1] ^ 1]),
                        'truncated': file[:-7]}.get(mode, file)} if mode != 'missing' else {}
        opens = install_fatfs(sb, files)
        sb.w(SWITCH_FLAG, b'\1')
        sb.w(BANK + 3 * SIZE, bytes([0xa5]) * SIZE)
        if mode == 'old_owner':
            # The former commit cave filled the bank without publishing an owner.
            op = next(op for op in sb.dis(0x0804BB00, 0x70)
                      if op.op_str == 'r2, [r0, r1, lsl #2]')
            install(sb, op.address, 'nop', 'nop')
        run(sb, 0x08021528, {UC_ARM_REG_R4: TRACKS[3]}, stop=0x0802152C)
        assert opens == [name], opens
        assert sb.r(BANK + 3 * SIZE, SIZE) == (payload if mode in ('valid', 'old_owner') else bytes(SIZE))
        assert sb.r(OWNER + 12, 4) == struct.pack('<I', 0 if mode == 'old_owner' else 1)
        if mode != 'old_owner':
            opens.clear()
            sb.w(SWITCH_FLAG, b'\0')
            run(sb, 0x08021528, {UC_ARM_REG_R4: TRACKS[3]}, stop=0x0802152C)
            assert opens == []
    print('PASS embedded records publish after project commit; missing and corrupt records clear stale banks')


def test_stock_and_modded_readers():
    native = (BUNDLE.parent.parent / 'testdata/sdcard/projectA/track1/patternB.txt').read_bytes()
    payload = sidecar(60, 64, 67)
    file = pattern_file(native, payload)
    assert len(native) < 0x27d8 < len(file)
    results = []
    for candidate, data in ((False, native), (False, file), (True, file)):
        sb = Sandbox(BUNDLE if candidate else None)
        neutralize(sb, 0x080232A0, 0x080232B0, 0x080190A6)
        opens = install_fatfs(sb, {b'patternB.txt': data})
        block = TRACKS[1] + 0x34 + 0x194
        sb.w(TRACKS[1] + 0x2e, b'\1')
        run(sb, 0x0801CCC4, {UC_ARM_REG_R0: block, UC_ARM_REG_R1: 1, UC_ARM_REG_R2: 0})
        assert opens == [b'patternB.txt'] * (2 if candidate else 1), opens
        results.append(sb.r(block + 4, 0x190))
        if candidate:
            assert sb.r(BANK + SIZE, SIZE) == payload
    assert results[0] == results[1] == results[2]
    assert results[0][4:4 + 3] != bytes(3)
    print('PASS real stock and modded parsers read the same 128-step native pattern')


def test_real_entry_and_playback():
    from test_poly_edit_entry_held import bench as editor_bench, key, chord, playback
    from test_poly_editlights6 import apply
    for track in (1, 2, 3):
        sb = editor_bench(track=track, letter=4)
        apply(sb, 'v1-poly-v119')
        for k in (4, 6, 8):
            key(sb, 1, k)
            key(sb, 2, k)
        assert {note for note, _ in chord(sb)} == {60, 64, 67}
        playback(sb, (60, 64, 67))
        sb.w(OWNER + track * 4, struct.pack('<I', 1))
        playback(sb, (60,))
        # Restore the base fan-out, which plays a foreign bank when the root matches.
        base = json.loads((BUNDLE.parent / 'v1-poly-dub.json').read_text())
        cave = next(p for p in base['patches'] if int(p['addr'], 0) == 0x08047600)
        sb.w(0x08047600, bytes.fromhex(cave['bytes']))
        sb.uc.ctl_remove_cache(0x08047600, 0x08047700)
        playback(sb, (60, 64, 67))
    print('PASS real press/release sequences play chords on all three tracks and reject foreign banks')


def test_armed_capture():
    base = json.loads((BUNDLE.parent / 'v1-poly-dub.json').read_text())
    original = next(p for p in base['patches'] if int(p['addr'], 0) == 0x08047400)
    for slot in (0, 1, 2, 3):
        for old in (False, True) if slot == 3 else (False,):
            sb, block, bank = bench(slot=slot)
            if old:
                sb.w(0x08047400, bytes.fromhex(original['bytes']))
            sb.w(TMP + 5, bytes([STEP]))
            sb.w(TMP + 12, struct.pack('<I', block))
            sb.w(0x2000CADA, bytes([slot]))
            sb.w(0x1000FD00 + 67, bytes([89]))
            run(sb, 0x08025814, {UC_ARM_REG_R3: TMP + 0x30, UC_ARM_REG_R4: TMP,
                                  UC_ARM_REG_R1: 67, UC_ARM_REG_R5: 67}, stop=0x080257F8)
            assert sb.r(TMP + 0x4d, 1) == bytes([67])
            expected = bytes([1, 67, 89]) if slot != 0 and not old else bytes(3)
            assert sb.r(bank + STEP * 17, 3) == expected
    print('PASS armed capture uses the live pattern block for tracks 1–3 and isolates drums')


def test_write_and_boot_read():
    for mode in ('active', 'inactive', 'no_preserve'):
        sb, block, bank = bench(rec=[60, 64], letter=4)
        press(sb, block, 55, velocity=89)
        press(sb, block, 72, velocity=77)
        assert sb.r(block + 8 + 3 * STEP, 2) == bytes([55, 89])
        sb.w(block + 0x188, struct.pack('<HH', STEP + 1, STEP + 1))
        data = sb.r(bank, SIZE)
        name = b'patternE.txt'
        files = {}
        if mode != 'active':
            files[name] = pattern_file(b'{"steps":[]}', data)
            sb.w(OWNER + 4, struct.pack('<I', 1))
            sb.w(bank, bytes(SIZE))
        neutralize(sb, 0x080232A0, 0x080232B0, 0x0801EDD4)
        run(sb, 0x08030C1C, stop=0x08030C32)
        if mode == 'no_preserve':
            sb.w(0x0801C4AC, Sandbox().r(0x0801C4AC, 4))
        opens = install_fatfs(sb, files)
        run(sb, 0x0801C450, {UC_ARM_REG_R1: block, UC_ARM_REG_R2: 4})
        assert opens == [name] * (2 if mode == 'inactive' else 1), opens
        if mode == 'no_preserve':
            assert files[name][-2188:][8:-4] != data
            continue
        native, trailer = files[name].split(b'\0', 1)
        assert native.startswith(b'{') and native.rstrip().endswith(b'}'), native[:64]
        assert trailer[:7] == b'GCP1\0\0\0'
        assert trailer[7:-4] == data
        assert trailer[-4:] == struct.pack('<I', zlib.crc32(data))

        reloaded = Sandbox(BUNDLE)
        reloaded.w(TRACKS[1] + 0x2e, b'\4')
        neutralize(reloaded, 0x080232A0, 0x080232B0, 0x080190A6)
        install_fatfs(reloaded, files)
        run(reloaded, 0x0801CCC4,
            {UC_ARM_REG_R0: block, UC_ARM_REG_R1: 4, UC_ARM_REG_R2: 0})
        assert reloaded.r(block + 8 + 3 * STEP, 2) == bytes([55, 89]), (native, reloaded.r(block + 8, 15))
        assert reloaded.r(bank, SIZE) == data
    print('PASS actual formatted save and fresh reload, including overwrite of an inactive letter')


if __name__ == '__main__':
    test_hard_delete()
    test_entry()
    test_save()
    test_editor_lights()
    test_commit_owner()
    test_stock_and_modded_readers()
    test_real_entry_and_playback()
    test_armed_capture()
    test_write_and_boot_read()
