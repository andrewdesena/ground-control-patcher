#!/usr/bin/env python3
"""The stock ProjectSettings format tail must close QuantizedMute with a comma."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ADDR = 0x08036E50


def main():
    bundle = json.loads((ROOT / 'mods/v1-poly-full.json').read_text())
    patch = next(p for p in bundle['patches'] if int(p['addr'], 16) == ADDR)
    assert patch['bytes'] == '5d2c00', patch
    blob = bytes.fromhex(patch['bytes'])
    assert blob == b'],\x00'
    print('PASS ProjectSettings format tail closes with a comma')
    return 0


if __name__ == '__main__':
    sys.exit(main())
