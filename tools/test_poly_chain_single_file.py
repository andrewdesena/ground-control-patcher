#!/usr/bin/env python3
"""Replay real stock letter selection, the SD wait hook and bank publication."""

import struct

from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_R0, UC_ARM_REG_R4

from fw_sandbox import Sandbox
from test_poly_v119 import BUNDLE, TRACKS, BANK, OWNER, SIZE, install_fatfs, neutralize, pattern_file, run, sidecar

REQUEST = 0x1000D734
PROJECT = 0x2000B499
SWITCH = 0x2000C5D8
SELECT = 0x08023158
SD_RECEIVE = 0x08020706
QUEUE = 0x08033256


def setup(bundle=BUNDLE):
    sb = Sandbox(bundle)
    for i, track in enumerate(TRACKS):
        sb.w(track + 0x1f, bytes([i]))
        sb.w(track + 0x2d, bytes([i == 0]))
        sb.w(OWNER + 4 * i, struct.pack('<I', 1))
        sb.w(BANK + i * SIZE, sidecar(60, 64))
    neutralize(sb, 0x080232A0, 0x080232B0)
    ins = sb.dis(0x0802315C, 2)[0]
    literal = ((ins.address + 4) & ~3) + int(ins.op_str.split('#')[1][:-1], 16)
    selector = int.from_bytes(sb.r(literal, 4), 'little')
    return sb, selector


def request(sb, selector, slot, letter):
    # Stock pending selector uses these two fields before its regular chain scan.
    sb.w(selector + slot + 0x35, b'\1')
    sb.w(selector + slot + 0x39, bytes([letter]))
    run(sb, SELECT, {UC_ARM_REG_R0: TRACKS[slot]})


def service(sb):
    calls = []

    def receive(uc, addr, size, user_data):
        calls.append(addr)
        uc.reg_write(UC_ARM_REG_R0, int(len(calls) == 2))
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    hook = sb.uc.hook_add(UC_HOOK_CODE, receive, begin=QUEUE, end=QUEUE)
    run(sb, SD_RECEIVE, stop=SD_RECEIVE + 4)
    sb.uc.hook_del(hook)
    assert len(calls) == 2, 'an empty receive dispatched a stale stock event'


def main():
    payload = sidecar(62, 65, 69)
    path = b'/projectA/track3/patternE.txt'
    for mode in ('fixed', 'stock', 'missing', 'superseded', 'project_changed', 'same_letter', 'switching'):
        sb, selector = setup()
        bank = BANK + 3 * SIZE
        owner = OWNER + 12
        mailbox = REQUEST + 4
        opens = install_fatfs(sb, {} if mode == 'missing' else {path: pattern_file(b'{}', payload)})
        if mode == 'stock':
            sb.w(0x0802316E, Sandbox().r(0x0802316E, 4))
        request(sb, selector, 3, 0 if mode == 'same_letter' else 4)
        assert not opens, 'timing callback entered FatFS'
        if mode == 'stock':
            assert sb.r(TRACKS[3] + 0x2e, 1) == b'\4'
            assert sb.r(owner, 4) == struct.pack('<I', 1)
            continue
        assert sb.r(TRACKS[3] + 0x2e, 1) == b'\0'
        assert sb.r(mailbox, 2) == struct.pack('<H', 1 if mode == 'same_letter' else 5)
        if mode in ('superseded', 'project_changed'):
            def interrupt(uc, addr, size, user_data):
                if mode == 'superseded':
                    sb.w(mailbox, b'\6\0')
                else:
                    sb.w(PROJECT, b'\1')
            # Interleave a new selector or project change with the trailer reader.
            sb.uc.hook_add(UC_HOOK_CODE, interrupt, begin=0x08014B30, end=0x08014B30)
            run(sb, 0x0804C000)
            assert opens == [path]
            assert sb.r(TRACKS[3] + 0x2e, 1) == b'\0'
            assert sb.r(bank, SIZE) == sidecar(60, 64)
            assert sb.r(mailbox, 2) == (b'\6\0' if mode == 'superseded' else b'\0\0')
            continue
        if mode == 'switching':
            sb.w(SWITCH, b'\1')
        service(sb)
        if mode in ('same_letter', 'switching'):
            assert opens == []
            assert sb.r(bank, SIZE) == sidecar(60, 64)
            assert sb.r(TRACKS[3] + 0x2e, 1) == b'\0'
        else:
            assert opens == [path], opens
            assert sb.r(TRACKS[3] + 0x2e, 1) == b'\4'
            assert sb.r(owner, 4) == struct.pack('<I', 5)
            assert sb.r(bank, SIZE) == (bytes(SIZE) if mode == 'missing' else payload)
            assert sb.r(mailbox, 2) == b'\0\0'
            assert sb.r(BANK + SIZE, SIZE) == sidecar(60, 64)

    sb, selector = setup()
    opens = install_fatfs(sb, {path: pattern_file(b'{}', payload)})
    request(sb, selector, 3, 5)
    sb.w(selector + 3 + 0x39, b'\4')
    run(sb, 0x08021528, {UC_ARM_REG_R0: TRACKS[3], UC_ARM_REG_R4: TRACKS[3]}, stop=0x0802152C)
    assert opens == [path]
    assert sb.r(TRACKS[3] + 0x2e, 1) == b'\4'
    assert sb.r(REQUEST + 4, 2) == bytes(2)
    assert sb.r(BANK + 3 * SIZE, SIZE) == payload

    sb, selector = setup()
    request(sb, selector, 0, 4)
    assert sb.r(TRACKS[0] + 0x2e, 1) == b'\4'
    assert sb.r(REQUEST, 6) == bytes(6)
    print('PASS stock chain hooks and SD worker, deferred notes and bank, stale results, drum isolation, stock mutation')


if __name__ == '__main__':
    main()
