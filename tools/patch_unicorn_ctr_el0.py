#!/usr/bin/env python3
"""Patch unicorn's Apple-Silicon CTR_EL0 trap.

On Apple Silicon (macOS 26/27) an EL0 read of CTR_EL0 raises SIGILL. Unicorn
2.1.4's cache-info init reads `hw.cachelinesize` via sysctlbyname first and only
falls back to `mrs x8, ctr_el0` when that sysctl fails. Under a sandbox that
denies the sysctl, the fallback runs and the whole process dies with
EXC_BAD_INSTRUCTION / SIGILL at uc_mem_map time.

This replaces the single CTR_EL0 read with `mov w8, #8`, which is the same
I-min-line value (8 << 4 = 128 bytes) the working sysctl path produces.

Re-run after any `pip install --force-reinstall unicorn`.
    python3 tools/patch_unicorn_ctr_el0.py            # apply
    python3 tools/patch_unicorn_ctr_el0.py --revert   # restore .orig
"""
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LIB = HERE.parent / '.venv/lib/python3.9/site-packages/unicorn/lib/libunicorn.2.dylib'
ORIG = LIB.with_suffix('.dylib.orig')

MRS_CTR_EL0 = bytes.fromhex('28003bd5')  # mrs x8, ctr_el0
MOV_W8_8 = bytes.fromhex('08018052')     # mov w8, #8  -> 128-byte I-cache line


def find_sites(data):
    return [i for i in range(len(data) - 4) if data[i:i + 4] == MRS_CTR_EL0]


def main():
    if not LIB.exists():
        sys.exit(f'missing {LIB}')

    if '--revert' in sys.argv:
        if not ORIG.exists():
            sys.exit('no .orig backup to restore')
        shutil.copy2(ORIG, LIB)
        subprocess.run(['codesign', '--force', '--sign', '-', str(LIB)], check=True,
                       capture_output=True)
        print(f'reverted {LIB}')
        return

    data = bytearray(LIB.read_bytes())
    sites = find_sites(data)
    if not sites:
        if MOV_W8_8 in bytes(data):
            print('already patched, nothing to do')
            return
        sys.exit('could not find the CTR_EL0 read')
    if len(sites) != 1:
        sys.exit(f'expected 1 CTR_EL0 site, found {len(sites)} at '
                 f'{[hex(s) for s in sites]}')

    if not ORIG.exists():
        shutil.copy2(LIB, ORIG)
    off = sites[0]
    data[off:off + 4] = MOV_W8_8
    LIB.write_bytes(data)
    subprocess.run(['codesign', '--force', '--sign', '-', str(LIB)], check=True,
                   capture_output=True)
    print(f'patched CTR_EL0 read at 0x{off:x} -> mov w8, #8 (128-byte line)')


if __name__ == '__main__':
    main()
