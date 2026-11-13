import fs from 'node:fs';
import { HexFile } from '../src/hexfile.js';
import { applyBundle, identify, APP_BASE } from '../src/mods.js';

const SRC = '/Users/andrewdesena/Downloads/Ground_Control_update/gc-v3.26_latest_release_300925.hex';
const hex = new HexFile(fs.readFileSync(SRC, 'utf8'));

let pass = 0, fail = 0;
const ok = (c, m) => c ? (pass++, console.log('  ok  ' + m)) : (fail++, console.log('  FAIL ' + m));

console.log('\n[1] identify');
const id = identify(hex);
ok(id.sp === 0x20020000 && id.reset === 0x08030c15, `SP 0x${id.sp.toString(16)} reset 0x${id.reset.toString(16)}`);

console.log('\n[2] reject a wrong image');
const fake = new HexFile(fs.readFileSync(SRC, 'utf8'));
fake.patch(APP_BASE, Uint8Array.from([0xff, 0xff, 0xff, 0xff]));
let threw = false;
try { identify(fake); } catch (e) { threw = true; console.log('  threw: ' + e.message); }
ok(threw, 'bad vector table rejected');

console.log('\n[3] apply a bundle (code cave + in-place hop)');
const hex2 = new HexFile(fs.readFileSync(SRC, 'utf8'));
const bundle = {
  name: 'selftest',
  requires: { blank: ['0x08046810', '0x080EFFFF'] },
  patches: [
    { addr: '0x08046810', bytes: '0148 0047 C046 0000', note: 'cave stub' },
    { addr: '0x08019620', bytes: '0000', note: 'in-place nop test' },
  ],
};
const res = applyBundle(hex2, bundle);
ok(res.report[0].appended === 8, 'cave bytes appended');
ok(res.report[1].inPlace === 2, 'in-place bytes overwritten');

console.log('\n[4] precondition failure aborts cleanly');
const hex3 = new HexFile(fs.readFileSync(SRC, 'utf8'));
let threw2 = false;
try {
  applyBundle(hex3, { patches: [], requires: { blank: ['0x08010000', '0x08010010'] } });
} catch (e) { threw2 = true; console.log('  threw: ' + e.message); }
ok(threw2, 'non-blank precondition rejected');

console.log('\n[5] output re-parses and keeps both images');
const out = hex2.toString();
const re = new HexFile(out);
ok(re.readByte(0x08019620) === 0x00, 'in-place patch survived serialization');
ok(re.read(0x08046810, 4).join(',') === '1,72,0,71', 'cave bytes present');
ok(re.segments().length >= 2, 'multi-segment image intact');
ok(re.readByte(0x080f0000) === 0x00 && re.readByte(0x080f0001) === 0x00, 'second image (0x080F0000) preserved');

console.log(`\n${fail === 0 ? 'ALL PASS' : 'FAILURES'}  pass=${pass} fail=${fail}`);
process.exit(fail ? 1 : 0);
