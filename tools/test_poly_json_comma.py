#!/usr/bin/env python3
"""Test the pulled comma source in isolation; enforce bundle exclusion."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ADDR = 0x08036E50


def main():
    bundle = json.loads((ROOT / 'mods/v1-poly-full.json').read_text())
    assert all(int(p['addr'],0) != ADDR for p in bundle['patches'])
    source = json.loads((ROOT / 'mods/poly-json-comma.source.json').read_text())
    patch = next(p for p in source['patches'] if int(p['addr'],0) == ADDR)
    assert patch['bytes'] == '5d2c00', patch
    blob = bytes.fromhex(patch['bytes'])
    assert blob == b'],\x00'
    print('PASS isolated comma source; excluded from flash bundle')
    return 0


if __name__ == '__main__':
    sys.exit(main())
