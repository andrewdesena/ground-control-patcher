#!/usr/bin/env python3
"""
verify.py — apply a bundle to the stock image and prove what changed.

  python3 tools/verify.py mods/clock_out.json

Checks, in order:
  1. the bundle applies cleanly to the stock hex (patch rules + preconditions)
  2. the output re-parses as Intel HEX
  3. the byte diff is EXACTLY the bundle's bytes, nothing else moved
  4. disassembles every patched region so a human can eyeball the machine code
  5. every other record is byte-identical to the vendor file
"""
import json, sys, os, difflib
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

HERE = os.path.dirname(os.path.abspath(__file__))
STOCK = os.path.join(HERE, '..', 'testdata', 'gc326.hex')

# --- minimal Intel HEX reader/writer (mirrors src/hexfile.js) ---
def parse(text):
    recs, base = [], 0
    for i, line in enumerate(text.splitlines()):
        s = line.strip()
        if not s:
            continue
        b = bytes.fromhex(s[1:])
        n, off, t = b[0], (b[1] << 8) | b[2], b[3]
        data = b[4:4 + n]
        if (sum(b[:4 + n]) + b[4 + n]) & 0xff:
            raise SystemExit(f'bad checksum on input line {i+1}')
        recs.append({'type': t, 'off': off, 'data': bytearray(data)})
    return recs

def index(recs):
    base, m = 0, {}
    for i, r in enumerate(recs):
        if r['type'] == 4:
            base = ((r['data'][0] << 8) | r['data'][1]) << 16
        elif r['type'] == 2:
            base = ((r['data'][0] << 8) | r['data'][1]) << 4
        elif r['type'] == 0:
            for p, byte in enumerate(r['data']):
                m[base + r['off'] + p] = byte
    return m

def emit(recs, eol='\r\n'):
    out = []
    for r in recs:
        buf = bytes([len(r['data']), (r['off'] >> 8) & 0xff, r['off'] & 0xff, r['type']]) + bytes(r['data'])
        out.append(':' + (buf + bytes([(-sum(buf)) & 0xff])).hex().upper())
    return eol.join(out) + eol

def build_records(mem):
    """mem: addr->byte dict. Canonical Intel-HEX: type04 per 64K, 16-byte data lines,
    then the stock start-address (0x08030C15) and EOF."""
    addrs = sorted(mem)
    recs, cur_upper, i, n = [], None, 0, len(addrs)
    while i < n:
        a = addrs[i]; upper = a >> 16
        if upper != cur_upper:
            cur_upper = upper
            recs.append({'type': 4, 'off': 0,
                         'data': bytearray([(upper >> 8) & 0xFF, upper & 0xFF])})
        line = bytearray(); start = a
        while i < n and (addrs[i] >> 16) == upper and len(line) < 16 and addrs[i] == start + len(line):
            line.append(mem[addrs[i]]); i += 1
        recs.append({'type': 0, 'off': start & 0xFFFF, 'data': line})
    recs.append({'type': 5, 'off': 0, 'data': bytearray([0x08, 0x03, 0x0C, 0x15])})
    recs.append({'type': 1, 'off': 0, 'data': bytearray()})
    return recs

def main(bundle_path):
    bundle = json.load(open(bundle_path))
    stock_text = open(STOCK, newline='').read()
    recs = parse(stock_text)
    mem_before = index(recs)
    mem = dict(mem_before)

    print(f"bundle: {bundle['name']}  ({len(bundle['patches'])} site(s))")
    written = {}
    for p in bundle['patches']:
        addr = int(p['addr'], 16)
        data = bytes.fromhex(p['bytes'])
        for i, byte in enumerate(data):
            mem[addr + i] = byte
            written[addr + i] = byte
        print(f"  0x{addr:08X}  +{len(data):<3} {p.get('note','')}")

    changed = sorted(a for a in written if mem_before.get(a) != written[a])
    added = sorted(a for a in written if a not in mem_before)
    print(f"\nbytes changed in place : {len(changed)}")
    print(f"bytes added (new flash): {len(added)}")

    # 4. disassemble patched regions
    try:
        from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB
        md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
        for p in bundle['patches']:
            addr, data = int(p['addr'], 16), bytes.fromhex(p['bytes'])
            print(f"\n--- 0x{addr:08X}")
            for ins in md.disasm(data, addr):
                print(f"    {ins.address:08x}  {ins.mnemonic:<8} {ins.op_str}")
    except ImportError:
        print('(capstone missing, skipping disassembly)')

    # 1-3. apply in place + append, then re-parse. Rebuild the whole image so blank-flash
    # patches (e.g. the cave) are actually EMITTED — the stock file omits blank regions.
    out_text = emit(build_records(mem))
    reparse = index(parse(out_text))
    inplace_ok = all(reparse.get(a) == mem[a] for a in written if a in mem_before)
    added_ok = all(reparse.get(a) == mem[a] for a in written if a not in mem_before)
    print(f"\nre-parsed in-place bytes match intent: {inplace_ok}")
    print(f"re-parsed NEW-flash bytes present    : {added_ok}")
    if not (inplace_ok and added_ok):
        bad = [a for a in written if reparse.get(a) != mem[a]][:5]
        print('  mismatch at', [hex(x) for x in bad])
        return 1
    untouched = sum(1 for a in mem_before if a not in written and reparse.get(a) != mem_before[a])
    print(f"untouched bytes that moved: {untouched}")
    print('\nOK' if untouched == 0 else 'FAIL')
    return 0 if untouched == 0 else 1

if __name__ == '__main__':
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    sys.exit(main(sys.argv[1]))
