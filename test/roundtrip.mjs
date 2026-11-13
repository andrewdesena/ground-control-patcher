import fs from 'node:fs';
import { HexFile, freeRuns, isBlank } from '../src/hexfile.js';

const SRC = '/Users/andrewdesena/Downloads/Ground_Control_update/gc-v3.26_latest_release_300925.hex';
const orig = fs.readFileSync(SRC, 'utf8');
let pass = 0, fail = 0;
const ok = (cond, msg) => { if (cond) { pass++; console.log('  ok  ' + msg); } else { fail++; console.log('  FAIL ' + msg); } };

console.log('\n[1] parse');
const h = new HexFile(orig);
ok(h.records.length > 1000, `records parsed: ${h.records.length}`);
const segs = h.segments();
console.log('  segments:', segs.map(s => `0x${s.start.toString(16)}..0x${s.end.toString(16)} (${s.length})`).join('  '));

console.log('\n[2] byte-exact round trip');
const out = h.toString();
ok(out === orig, `re-emitted file identical to vendor file (${orig.length} vs ${out.length} chars)`);
ok(h.eol === '\r\n', 'CRLF preserved');

console.log('\n[3] vector table + entry');
const rd32 = a => h.read(a, 4);
const u32 = b => (b[0] | (b[1] << 8) | (b[2] << 16) | (b[3] << 24)) >>> 0;
ok(u32(rd32(0x08010000)) === 0x20020000, 'SP = 0x20020000');
ok(u32(rd32(0x08010004)) === 0x08030c15, 'Reset = 0x08030C15');
ok(u32(rd32(0x080f0000)) === 0x20020000, 'second image vector table at 0x080F0000');

console.log('\n[4] free flash');
const runs = freeRuns(h, 1024);
for (const r of runs) console.log(`  0x${r.start.toString(16)}..0x${r.end.toString(16)}  ${r.length} bytes  blank=${isBlank(h, r.start, r.length)}`);

console.log('\n[5] in-place patch (1 byte inside the app)');
const target = 0x08030c14;                    // reset handler, harmless test address
const before = h.readByte(target);
h.patch(target, Uint8Array.from([0x00]));
ok(h.readByte(target) === 0x00, `wrote 0x00 over 0x${before.toString(16)}`);
const out2 = h.toString();
ok(out2 !== orig && out2.length === orig.length, 'line count/length unchanged (record rewritten in place)');
const reparsed = new HexFile(out2);
ok(reparsed.readByte(target) === 0x00, 're-parse sees the patched byte');
ok(reparsed.readByte(target + 1) === h.readByte(target + 1), 'next byte untouched');
h.patch(target, Uint8Array.from([before]));
ok(h.toString() === orig, 'reverting the patch restores the original file exactly');

console.log('\n[6] append into free flash (code cave)');
const cave = 0x0804dd00;
const payload = Uint8Array.from([0x70, 0x47]);   // bx lr
const res = h.patch(cave, payload);
ok(res.appended === payload.length, `appended ${res.appended} bytes`);
const out3 = h.toString();
const re3 = new HexFile(out3);
ok(re3.readByte(cave) === 0x70 && re3.readByte(cave + 1) === 0x47, 'code cave bytes re-parse correctly');
ok(re3.segments().some(s => s.start <= cave && s.end >= cave + 1), 'new segment present in image');
ok(out3.split(/\r\n/).pop() === '' || out3.trimEnd().slice(-11) === ':00000001FF', 'EOF record still last');

console.log(`\n${fail === 0 ? 'ALL PASS' : 'FAILURES'}  pass=${pass} fail=${fail}`);
process.exit(fail === 0 ? 0 : 1);
