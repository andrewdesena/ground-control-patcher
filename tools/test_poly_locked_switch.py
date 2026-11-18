#!/usr/bin/env python3
"""Exercise the stock all-track boundary, native restart, and SD task handoff."""

from unicorn import UC_HOOK_CODE
from unicorn.arm_const import (
    UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_PRIMASK, UC_ARM_REG_R0,
    UC_ARM_REG_R4, UC_ARM_REG_R6, UC_ARM_REG_R8, UC_ARM_REG_R10, UC_ARM_REG_R11,
)

from test_poly_chain_single_file import setup, service
from test_poly_v119 import BANK, BUNDLE, SIZE, TRACKS, install_fatfs, neutralize, pattern_file, run, sidecar

HANDOFF = 0x080223DC
RESUME = 0x08022304
STATE = 0x1000D731
HOLDS = [0x2000C93C + 0x18E, 0x2000C848 + 0x49, 0x2000C754 + 0x49,
         0x2000C660 + 0x49, 0x2000C65B]
BOUNDARY_REGS = {
    UC_ARM_REG_R4: 0x2000C93C, UC_ARM_REG_R6: 0, UC_ARM_REG_R8: 0x2000C65B,
    UC_ARM_REG_R10: 0x2000C754, UC_ARM_REG_R11: 0x2000C848,
}


def bench(name):
    sb, selector = setup(BUNDLE.with_name(name))
    # Keep stock hardware output and unrelated transport callbacks out of the harness.
    neutralize(sb, 0x080190A6, 0x080212BC, 0x0802267E, 0x080227C0, 0x08021050)
    for addr in (0x08022434, 0x0802243C):
        def voice(uc, addr, size, user_data):
            uc.reg_write(UC_ARM_REG_R0, 0x2001E000)
            uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))
        sb.uc.hook_add(UC_HOOK_CODE, voice, begin=addr, end=addr)
    for slot in range(4):
        sb.w(selector + slot + 0x35, b'\1')
        sb.w(selector + slot + 0x39, b'\1')
    for addr in HOLDS:
        sb.w(addr, b'\1')
    files = {f'/projectA/track{slot}/patternB.txt'.encode():
             pattern_file(b'{}', sidecar(60 + slot, 64 + slot, 67 + slot))
             for slot in (1, 2, 3)}
    opens = install_fatfs(sb, files)
    return sb, files, opens


def main():
    original, _, old_opens = bench('v1-poly-v120.json')
    original.uc.reg_write(UC_ARM_REG_PRIMASK, 1)
    original.call(HANDOFF, BOUNDARY_REGS, stop_at=0x0801496C)
    assert old_opens == [b"/projectA/track1/patternB.txt"]
    assert original.reg(UC_ARM_REG_PRIMASK) == 1, 'baseline did not reach FatFS under mask'

    fixed, files, opens = bench('v1-poly-v120-lock1.json')
    fixed.uc.reg_write(UC_ARM_REG_PRIMASK, 1)
    for _ in range(3):
        run(fixed, HANDOFF, BOUNDARY_REGS, stop=RESUME)
        assert fixed.r(STATE, 1) == b'\1'
        assert all(fixed.r(addr, 1) == b'\1' for addr in HOLDS)
    assert not opens
    assert all(fixed.r(t + 0x2e, 1) == b'\0' for t in TRACKS)

    reads = []
    def check_read(uc, addr, size, user_data):
        assert fixed.reg(UC_ARM_REG_PRIMASK) == 0
        assert fixed.r(STATE, 1) == b'\2'
        assert all(fixed.r(a, 1) == b'\1' for a in HOLDS)
        reads.append(addr)

    fixed.uc.hook_add(UC_HOOK_CODE, check_read, begin=0x08014B30, end=0x08014B30)
    fixed.uc.reg_write(UC_ARM_REG_PRIMASK, 0)
    service(fixed)
    assert opens == list(files) and reads
    assert fixed.r(STATE, 1) == b'\3'
    assert all(fixed.r(t + 0x2e, 1) == b'\1' for t in TRACKS)
    for slot, data in enumerate(files.values(), 1):
        assert fixed.r(BANK + slot * SIZE, SIZE) == data[-2180:-4]
    run(fixed, HANDOFF, BOUNDARY_REGS, stop=RESUME)
    assert fixed.r(STATE, 1) == b'\0'
    assert all(fixed.r(addr, 1) == b'\0' for addr in HOLDS), [fixed.r(a,1) for a in HOLDS]
    print('PASS stock restart reaches FatFS under mask; fixed boundary waits for one SD-task restart and releases all four tracks')


if __name__ == '__main__':
    main()
