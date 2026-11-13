#!/usr/bin/env python3
"""
apply.py — apply a bytes bundle to the stock hex and emit a flashable modded hex.

  python3 tools/apply.py mods/clock.json out.hex

Unlike verify.py (which only proves collateral), this WRITES the new flash region
(e.g. the cave) as fresh Intel-HEX records, because the stock file omits blank
flash. Then it re-parses the result and asserts:
  * every patched byte is present with the intended value
  * every stock byte outside the patch is byte-identical (zero collateral)
  * no stock address was dropped
"""
import json, sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from verify import parse, index, emit, build_records

STOCK = os.path.join(HERE, '..', 'testdata', 'gc326.hex')


def main(bundle_path, out_path):
    bundle = json.load(open(bundle_path))
    stock_text = open(STOCK, newline='').read()
    mem_before = index(parse(stock_text))

    mem = dict(mem_before)
    written = {}
    for p in bundle['patches']:
        addr = int(p['addr'], 16)
        data = bytes.fromhex(p['bytes'])
        for i, b in enumerate(data):
            mem[addr + i] = b
            written[addr + i] = b

    out_text = emit(build_records(mem))
    open(out_path, 'w', newline='').write(out_text)

    # --- independent re-verification against the file we just wrote ---
    reparse = index(parse(out_text))
    bad_written = [a for a, v in written.items() if reparse.get(a) != v]
    dropped = [a for a in mem_before if a not in reparse]
    moved = [a for a in mem_before if a not in written and reparse.get(a) != mem_before[a]]

    print(f"bundle      : {bundle['name']}")
    print(f"output      : {out_path}  ({len(out_text.splitlines())} lines)")
    print(f"patched     : {len(written)} bytes ({len(bundle['patches'])} site(s))")
    print(f"stock bytes : {len(mem_before)}")
    print(f"written mismatches      : {len(bad_written)}  {[hex(x) for x in bad_written[:4]]}")
    print(f"dropped stock addresses : {len(dropped)}  {[hex(x) for x in dropped[:4]]}")
    print(f"untouched bytes that moved: {len(moved)}  {[hex(x) for x in moved[:4]]}")
    ok = not bad_written and not dropped and not moved
    print('OK' if ok else 'FAIL')
    return 0 if ok else 1


if __name__ == '__main__':
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    sys.exit(main(sys.argv[1], sys.argv[2]))
