#!/usr/bin/env python3
"""
asm.py — build a patch bundle from Thumb assembly + a patch list.

  python3 tools/asm.py mods/clock.source.json mods/clock.json

Uses clang (no keystone, no linker): assemble to an object, then read .text out of
it. Absolute branch targets resolve at assembly time, so `bl 0x08019620` and
`.set name,0x...` both work. Any unresolved relocation is an error, not a guess.

Source bundle (JSON):
{
  "name": "clock-priority",
  "cave":    { "addr": "0x08046810", "asm": ["push {r4, lr}", "..."] },
  "patches": [ { "addr": "0x08019620", "asm": ["bl 0x08046810"], "note": "hop" } ],
  "requires": { "blank": ["0x08046810", "0x080EFFFF"] }
}
Output is a bytes-only bundle that index.html can apply. No assembler ships to users.
"""
import json, sys, os, subprocess, tempfile
from elftools.elf.elffile import ELFFile

CLANG = 'clang'
TARGET = ['--target=thumbv7m-none-eabi', '-mthumb', '-c', '-x', 'assembler-with-cpp',
          '-march=armv7-m', '-O2', '-fno-pic']

def assemble(lines, addr):
    import re
    src = ['.syntax unified', '.thumb', '.text', '.global _start', f'.set __base, 0x{addr:08X}', '_start:']
    for line in lines:
        line = line.split('@')[0].split('//')[0].rstrip()
        if not line.strip():
            continue
        # absolute branch targets must become section-relative: the assembler does not
        # know we will live at `addr`, so `bl 0x08046810` would encode the wrong offset.
        line = re.sub(r'\b(blx|bl|b\.w|b|bne|beq|bhi|bls|bcc|bcs|bmi|bpl|bge|blt|bgt|ble)\s+#?(0x[0-9A-Fa-f]+)',
                      lambda m: f'{m.group(1)} _start+({m.group(2)}-__base)', line)
        src.append('  ' + line.strip())
    with tempfile.TemporaryDirectory() as td:
        s = os.path.join(td, 'a.s'); o = os.path.join(td, 'a.o')
        open(s, 'w').write('\n'.join(src) + '\n')
        r = subprocess.run([CLANG] + TARGET + [s, '-o', o], capture_output=True, text=True)
        if r.returncode:
            raise SystemExit('clang:\n' + r.stderr)
        with open(o, 'rb') as f:
            elf = ELFFile(f)
            text = elf.get_section_by_name('.text').data()
            relocs = []
            for sec in elf.iter_sections():
                if sec.header['sh_type'] in ('SHT_REL', 'SHT_RELA'):
                    symtab = elf.get_section(sec.header['sh_link'])
                    for rel in sec.iter_relocations():
                        relocs.append((rel['r_offset'], symtab.get_symbol(rel['r_info_sym']).name))
            if relocs:
                import thumbfix
                text = bytearray(text)
                text = thumbfix.fix(text, relocs)
            return bytes(text)

def build(src):
    patches = []
    if src.get('cave'):
        addr = int(src['cave']['addr'], 0)
        code = assemble(src['cave']['asm'], addr)
        patches.append({'addr': hex(addr), 'bytes': code.hex(), 'note': 'cave routine'})
        print(f"cave   0x{addr:08X}  {len(code):>3} bytes")
    for p in src['patches']:
        addr = int(p['addr'], 0)
        data = assemble(p['asm'], addr) if 'asm' in p else bytes.fromhex(p['bytes'])
        patches.append({'addr': hex(addr), 'bytes': data.hex(), 'note': p.get('note', '')})
        print(f"patch  0x{addr:08X}  {len(data):>3} bytes  {p.get('note','')}")
    return {'name': src['name'], 'status': src.get('status', 'experimental'),
            'description': src.get('description', ''), 'requires': src.get('requires', {}),
            'patches': patches}

if __name__ == '__main__':
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    out = build(json.load(open(sys.argv[1])))
    json.dump(out, open(sys.argv[2], 'w'), indent=2)
    print(f"wrote {sys.argv[2]}")
