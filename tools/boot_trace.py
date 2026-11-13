#!/usr/bin/env python3
"""
boot_trace.py — boot the firmware from reset in the sandbox with a small peripheral model and
report how far it gets + which key functions are reached. Used to find the sequencer scheduler.

Peripheral model: RCC CR/CFGR report "clocks ready / PLL selected" so init proceeds. Everything
else reads 0 (mapped). Extend FAKE as new stalls are found.

  ./.venv/bin/python tools/boot_trace.py [steps]
"""
import sys, os
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from fw_sandbox import Sandbox
from unicorn import UcError, UC_HOOK_CODE, UC_HOOK_MEM_READ
from unicorn.arm_const import UC_ARM_REG_SP

RESET = 0x08030C15
INTEREST = {0x08019A92: 'emit-pair', 0x08019A2A: 'note-on', 0x08020A84: 'x0x-player',
            0x08021A14: 'melodic-player', 0x08020CE4: 'x0x-tick', 0x08021D04: 'melodic-tick',
            0x0802B548: 'chain-adv', 0x0802063C: 'live-input', 0x08022054: 'dispatcher'}
# peripheral read fakes: RCC_CR (0x40023800) clocks ready, RCC_CFGR (0x40023808) PLL = sysclk
FAKE = {0x40023800: 0x03030003, 0x40023808: 0x0000000A,  # CR: HSI/HSE/PLL all ON+READY; CFGR: SWS=PLL, PLLSRC=HSE
        0x40023C00: 0x00000301}  # FLASH_ACR: 1 WS, prefetch/cache on


def main():
    steps = int(sys.argv[1]) if len(sys.argv) > 1 else 1_500_000
    sb = Sandbox(); uc = sb.uc
    def mr(u, acc, addr, size, val, _):
        v = FAKE.get(addr)
        if v is not None:
            u.mem_write(addr, v.to_bytes(4, 'little')); return True
    uc.hook_add(UC_HOOK_MEM_READ, mr)
    hit = {}; last = [0]; n = [0]; hist = {}
    def h(u, a, s, _):
        n[0] += 1; last[0] = a
        if a in INTEREST and a not in hit:
            hit[a] = n[0]
    uc.hook_add(UC_HOOK_CODE, h)
    uc.reg_write(UC_ARM_REG_SP, 0x20020000)
    err = None
    try:
        uc.emu_start(RESET, 0xFFFFFFF0, count=steps)
    except UcError as e:
        err = str(e)
    print(f"steps={n[0]}  last_pc=0x{last[0]:08X}  err={err}")
    print("reached:", {INTEREST[a]: c for a, c in hit.items()} or "none of interest")


if __name__ == '__main__':
    main()
