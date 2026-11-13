/**
 * hexfile.js — Intel HEX parse / in-place patch / emit.
 * No dependencies. Works in the browser (ESM) and in Node.
 *
 * Design rule: never re-lay-out the vendor's records. A patch rewrites bytes
 * inside the existing record grid, or appends new records for free flash.
 * That keeps the output as close to stock as possible, which matters when an
 * unknown bootloader is on the other end.
 */

const REC = {
  DATA: 0x00,
  EOF: 0x01,
  EXT_SEG: 0x02,
  START_SEG: 0x03,
  EXT_LIN: 0x04,
  START_LIN: 0x05,
};

export class HexFile {
  constructor(text) {
    this.eol = text.includes('\r\n') ? '\r\n' : '\n';
    this.records = [];   // {type, offset, data:Uint8Array, raw:string}
    this.parse(text);
    this.buildIndex();
  }

  static checksum(bytes) {
    let sum = 0;
    for (const b of bytes) sum += b;
    return (-sum) & 0xff;
  }

  parse(text) {
    const lines = text.split(/\r?\n/);
    this.records = [];
    for (const line of lines) {
      const s = line.trim();
      if (!s) continue;
      if (s[0] !== ':') throw new Error(`not an Intel HEX record: ${s.slice(0, 20)}`);
      const bin = new Uint8Array((s.length - 1) / 2);
      for (let i = 0; i < bin.length; i++) bin[i] = parseInt(s.substr(1 + i * 2, 2), 16);
      const len = bin[0];
      const offset = (bin[1] << 8) | bin[2];
      const type = bin[3];
      const data = bin.slice(4, 4 + len);
      const want = HexFile.checksum(bin.slice(0, 4 + len)) & 0xff;
      const got = bin[4 + len];
      if (want !== got) throw new Error(`bad checksum on record at offset 0x${offset.toString(16)}`);
      this.records.push({ type, offset, data, raw: s });
    }
    const last = this.records[this.records.length - 1];
    if (!last || last.type !== REC.EOF) throw new Error('missing EOF record');
  }

  /** absolute address per record, resolving 02/04 base records in order */
  buildIndex() {
    let base = 0;
    this.abs = new Array(this.records.length);
    this.index = new Map(); // absolute addr -> {rec, pos}
    for (let i = 0; i < this.records.length; i++) {
      const r = this.records[i];
      switch (r.type) {
        case REC.EXT_SEG:
          base = (((r.data[0] << 8) | r.data[1]) << 4) >>> 0;
          this.abs[i] = null;
          break;
        case REC.EXT_LIN:
          base = (((r.data[0] << 8) | r.data[1]) << 16) >>> 0;
          this.abs[i] = null;
          break;
        case REC.DATA: {
          const a = (base + r.offset) >>> 0;
          this.abs[i] = a;
          for (let p = 0; p < r.data.length; p++) this.index.set(a + p, { rec: i, pos: p });
          break;
        }
        default:
          this.abs[i] = null;
      }
    }
  }

  /** byte at absolute address, or null if not present in the image */
  readByte(addr) {
    const hit = this.index.get(addr >>> 0);
    return hit ? this.records[hit.rec].data[hit.pos] : null;
  }

  read(addr, len) {
    const out = new Uint8Array(len);
    for (let i = 0; i < len; i++) {
      const b = this.readByte(addr + i);
      if (b === null) throw new Error(`address 0x${(addr + i).toString(16)} not in image`);
      out[i] = b;
    }
    return out;
  }

  /** contiguous extents of mapped data, for free-space and layout checks */
  segments() {
    const addrs = [...this.index.keys()].sort((a, b) => a - b);
    const segs = [];
    let start = addrs[0], prev = addrs[0];
    for (let i = 1; i < addrs.length; i++) {
      const a = addrs[i];
      if (a !== prev + 1) { segs.push([start, prev]); start = a; }
      prev = a;
    }
    if (addrs.length) segs.push([start, prev]);
    return segs.map(([s, e]) => ({ start: s, end: e, length: e - s + 1 }));
  }

  /**
   * Patch bytes at an absolute address.
   * Bytes inside existing records are rewritten in place. Anything else is
   * queued for appending as new data records (free flash / code cave).
   * Returns {inPlace: n, appended: n}
   */
  patch(addr, bytes) {
    let inPlace = 0;
    const pending = [];
    for (let i = 0; i < bytes.length; i++) {
      const a = (addr + i) >>> 0;
      const hit = this.index.get(a);
      if (hit) { this.records[hit.rec].data[hit.pos] = bytes[i]; inPlace++; }
      else pending.push([a, bytes[i]]);
    }
    if (pending.length) this.appendBytes(pending);
    return { inPlace, appended: pending.length };
  }

  appendBytes(pairs) {
    // group consecutive addresses, emit 16-byte data records, with an EXT_LIN
    // record whenever the 64K page changes
    const EOF = this.records.pop();
    let curPage = null;
    let run = [];
    const flush = () => {
      for (let i = 0; i < run.length; i += 16) {
        const chunk = run.slice(i, i + 16);
        const off = chunk[0][0] & 0xffff;
        const data = Uint8Array.from(chunk.map((p) => p[1]));
        this.records.push(this.makeDataRecord(off, data));
      }
      run = [];
    };
    for (const [a, b] of pairs) {
      const page = (a >>> 16) & 0xffff;
      if (page !== curPage) {
        flush();
        const d = Uint8Array.from([(page >> 8) & 0xff, page & 0xff]);
        this.records.push(this.makeRecord(REC.EXT_LIN, 0, d));
        curPage = page;
      }
      if (run.length && a !== run[run.length - 1][0] + 1) flush();
      run.push([a, b]);
    }
    flush();
    this.records.push(EOF);
    this.buildIndex();
  }

  makeDataRecord(offset, data) {
    if (offset + data.length > 0x10000) throw new Error('record crosses a 64K page');
    return this.makeRecord(REC.DATA, offset, data);
  }

  makeRecord(type, offset, data) {
    const len = data.length;
    const buf = new Uint8Array(5 + len);
    buf[0] = len; buf[1] = (offset >> 8) & 0xff; buf[2] = offset & 0xff; buf[3] = type;
    buf.set(data, 4);
    buf[4 + len] = HexFile.checksum(buf.slice(0, 4 + len));
    return { type, offset, data, raw: null };
  }

  /** serialize. Uses the vendor's own raw line for untouched records. */
  toString(dirtyOnly = false) {
    const out = [];
    for (const r of this.records) {
      if (r.raw && !r.dirty) out.push(r.raw);
      else out.push(this.serializeRecord(r));
    }
    return out.join(this.eol) + this.eol;
  }

  serializeRecord(r) {
    const len = r.data.length;
    const buf = new Uint8Array(5 + len);
    buf[0] = len; buf[1] = (r.offset >> 8) & 0xff; buf[2] = r.offset & 0xff; buf[3] = r.type;
    buf.set(r.data, 4);
    buf[4 + len] = HexFile.checksum(buf.slice(0, 4 + len));
    let s = ':';
    for (const b of buf) s += b.toString(16).padStart(2, '0').toUpperCase();
    return s;
  }
}

/* mark rewritten records dirty so toString() re-serializes them */
const _patch = HexFile.prototype.patch;
HexFile.prototype.patch = function (addr, bytes) {
  const touched = new Set();
  for (let i = 0; i < bytes.length; i++) {
    const hit = this.index.get((addr + i) >>> 0);
    if (hit) touched.add(hit.rec);
  }
  const res = _patch.call(this, addr, bytes);
  for (const r of touched) this.records[r].dirty = true;
  return res;
};

export function freeRuns(hex, min = 256) {
  const segs = hex.segments();
  const runs = [];
  for (let i = 0; i < segs.length - 1; i++) {
    const gap = segs[i + 1].start - segs[i].end - 1;
    if (gap >= min) runs.push({ start: segs[i].end + 1, end: segs[i + 1].start - 1, length: gap });
  }
  return runs;
}

export function isBlank(hex, start, length) {
  for (let i = 0; i < length; i++) {
    const b = hex.readByte(start + i);
    if (b !== null && b !== 0xff) return false;
  }
  return true;
}
