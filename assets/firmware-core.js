/* Local Intel HEX patching engine. */
(function (root) {
  "use strict";
  /* ---------------- Intel HEX: read, change, write back ---------------- */
  var REC = {
    DATA: 0,
    EOF: 1,
    EXT_SEG: 2,
    START_SEG: 3,
    EXT_LIN: 4,
    START_LIN: 5,
  };

  function checksum(bytes) {
    var s = 0;
    for (var i = 0; i < bytes.length; i++) s += bytes[i];
    return -s & 0xff;
  }

  function HexFile(text) {
    this.eol = text.indexOf("\r\n") >= 0 ? "\r\n" : "\n";
    this.records = [];
    var lines = text.split(/\r?\n/);
    for (var i = 0; i < lines.length; i++) {
      var s = lines[i].trim();
      if (!s) continue;
      if (s.charAt(0) !== ":")
        throw new Error("line " + (i + 1) + " is not a hex record");
      var bin = new Uint8Array((s.length - 1) / 2);
      for (var j = 0; j < bin.length; j++)
        bin[j] = parseInt(s.substr(1 + j * 2, 2), 16);
      var len = bin[0],
        off = (bin[1] << 8) | bin[2],
        type = bin[3];
      var data = bin.slice(4, 4 + len);
      if ((checksum(bin.slice(0, 4 + len)) & 0xff) !== bin[4 + len])
        throw new Error("line " + (i + 1) + " fails its checksum");
      this.records.push({
        type: type,
        offset: off,
        data: data,
        raw: s,
        dirty: false,
      });
    }
    var last = this.records[this.records.length - 1];
    if (!last || last.type !== REC.EOF)
      throw new Error("file is missing its end marker (EOF record)");
    this.reindex();
  }

  HexFile.prototype.reindex = function () {
    var base = 0;
    this.index = new Map();
    for (var i = 0; i < this.records.length; i++) {
      var r = this.records[i];
      if (r.type === REC.EXT_SEG)
        base = (((r.data[0] << 8) | r.data[1]) << 4) >>> 0;
      else if (r.type === REC.EXT_LIN)
        base = (((r.data[0] << 8) | r.data[1]) << 16) >>> 0;
      else if (r.type === REC.DATA) {
        var a = (base + r.offset) >>> 0;
        for (var p = 0; p < r.data.length; p++)
          this.index.set(a + p, { rec: i, pos: p });
      }
    }
  };

  HexFile.prototype.readByte = function (addr) {
    var hit = this.index.get(addr >>> 0);
    return hit ? this.records[hit.rec].data[hit.pos] : null;
  };
  HexFile.prototype.read = function (addr, len) {
    var out = new Uint8Array(len);
    for (var i = 0; i < len; i++) {
      var b = this.readByte(addr + i);
      if (b === null)
        throw new Error(
          "address 0x" + (addr + i).toString(16) + " is not in this file",
        );
      out[i] = b;
    }
    return out;
  };
  HexFile.prototype.segments = function () {
    var addrs = Array.from(this.index.keys()).sort(function (a, b) {
      return a - b;
    });
    if (!addrs.length) return [];
    var segs = [],
      start = addrs[0],
      prev = addrs[0];
    for (var i = 1; i < addrs.length; i++) {
      var a = addrs[i];
      if (a !== prev + 1) {
        segs.push({ start: start, end: prev, length: prev - start + 1 });
        start = a;
      }
      prev = a;
    }
    segs.push({ start: start, end: prev, length: prev - start + 1 });
    return segs;
  };
  HexFile.prototype.isBlank = function (start, length) {
    for (var i = 0; i < length; i++) {
      var b = this.readByte(start + i);
      if (b !== null && b !== 0xff) return false;
    }
    return true;
  };
  HexFile.prototype.makeRecord = function (type, offset, data) {
    var buf = new Uint8Array(5 + data.length);
    buf[0] = data.length;
    buf[1] = (offset >> 8) & 0xff;
    buf[2] = offset & 0xff;
    buf[3] = type;
    buf.set(data, 4);
    buf[4 + data.length] = checksum(buf.slice(0, 4 + data.length));
    return buf;
  };
  HexFile.prototype.patch = function (addr, bytes) {
    var inPlace = 0,
      pending = [];
    for (var i = 0; i < bytes.length; i++) {
      var a = (addr + i) >>> 0,
        hit = this.index.get(a);
      if (hit) {
        this.records[hit.rec].data[hit.pos] = bytes[i];
        this.records[hit.rec].dirty = true;
        inPlace++;
      } else pending.push([a, bytes[i]]);
    }
    if (pending.length) this.appendBytes(pending);
    return { inPlace: inPlace, appended: pending.length };
  };
  HexFile.prototype.appendBytes = function (pairs) {
    var eof = this.records.pop(),
      curPage = null,
      run = [],
      self = this;
    function flush() {
      for (var i = 0; i < run.length; i += 16) {
        var chunk = run.slice(i, i + 16);
        var data = Uint8Array.from(
          chunk.map(function (p) {
            return p[1];
          }),
        );
        self.records.push({
          type: REC.DATA,
          offset: chunk[0][0] & 0xffff,
          data: data,
          raw: null,
          dirty: true,
        });
      }
      run = [];
    }
    for (var k = 0; k < pairs.length; k++) {
      var a = pairs[k][0],
        page = (a >>> 16) & 0xffff;
      if (page !== curPage) {
        flush();
        this.records.push({
          type: REC.EXT_LIN,
          offset: 0,
          data: Uint8Array.from([(page >> 8) & 0xff, page & 0xff]),
          raw: null,
          dirty: true,
        });
        curPage = page;
      }
      if (run.length && a !== run[run.length - 1][0] + 1) flush();
      run.push(pairs[k]);
    }
    flush();
    this.records.push(eof);
    this.reindex();
  };
  HexFile.prototype.serialize = function (r) {
    if (r.raw && !r.dirty) return r.raw;
    var buf = this.makeRecord(r.type, r.offset, r.data),
      s = ":";
    for (var i = 0; i < buf.length; i++)
      s += ("0" + buf[i].toString(16).toUpperCase()).slice(-2);
    return s;
  };
  HexFile.prototype.toString = function () {
    var out = [];
    for (var i = 0; i < this.records.length; i++)
      out.push(this.serialize(this.records[i]));
    return out.join(this.eol) + this.eol;
  };
  HexFile.prototype.freeRuns = function (min) {
    var segs = this.segments(),
      runs = [];
    for (var i = 0; i < segs.length - 1; i++) {
      var gap = segs[i + 1].start - segs[i].end - 1;
      if (gap >= min)
        runs.push({
          start: segs[i].end + 1,
          end: segs[i + 1].start - 1,
          length: gap,
        });
    }
    return runs;
  };

  /* ---------------- mod bundles ---------------- */
  var APP_BASE = 0x08010000;

  function toNum(v) {
    return typeof v === "number" ? v : parseInt(v, 16);
  }
  function toBytes(v) {
    var s = String(v).replace(/[^0-9a-fA-F]/g, "");
    if (s.length % 2) throw new Error("patch has an odd number of hex digits");
    var out = new Uint8Array(s.length / 2);
    for (var i = 0; i < out.length; i++)
      out[i] = parseInt(s.substr(i * 2, 2), 16);
    return out;
  }
  function identify(hex) {
    var b = hex.read(APP_BASE, 8);
    var sp = (b[0] | (b[1] << 8) | (b[2] << 16) | (b[3] << 24)) >>> 0;
    var reset = (b[4] | (b[5] << 8) | (b[6] << 16) | (b[7] << 24)) >>> 0;
    if (sp !== 0x20020000)
      throw new Error(
        "this does not look like a Ground Control firmware (unexpected start of file)",
      );
    if (!(reset & 1))
      throw new Error(
        "this does not look like a Ground Control firmware (wrong entry point)",
      );
    return { sp: sp, reset: reset };
  }
  function applyBundle(hex, bundle) {
    var id = identify(hex);
    var blankReq = (bundle.requires && bundle.requires.blank) || [];
    if (blankReq.length && typeof blankReq[0] === "string")
      blankReq = [blankReq];
    for (var i = 0; i < blankReq.length; i++) {
      var s = toNum(blankReq[i][0]),
        e = toNum(blankReq[i][1]);
      if (!hex.isBlank(s, e - s + 1))
        throw new Error(
          "expected empty space at 0x" +
            s.toString(16) +
            " but it is not empty",
        );
    }
    var report = [];
    for (var j = 0; j < bundle.patches.length; j++) {
      var p = bundle.patches[j],
        addr = toNum(p.addr),
        bytes = toBytes(p.bytes);
      if (addr < APP_BASE)
        throw new Error(
          "patch address 0x" +
            addr.toString(16) +
            " is inside the protected bootloader area",
        );
      var res = hex.patch(addr, bytes);
      report.push({
        addr: addr,
        length: bytes.length,
        inPlace: res.inPlace,
        appended: res.appended,
        note: p.note || "",
      });
    }
    return { id: id, report: report };
  }

  async function canonicalHash(hf) {
    if (!crypto || !crypto.subtle) return null;
    var keys = Array.from(hf.index.keys()).sort(function (a, b) {
      return a - b;
    });
    var buf = new Uint8Array(keys.length * 5);
    for (var i = 0; i < keys.length; i++) {
      var a = keys[i],
        o = i * 5;
      buf[o] = a & 255;
      buf[o + 1] = (a >>> 8) & 255;
      buf[o + 2] = (a >>> 16) & 255;
      buf[o + 3] = (a >>> 24) & 255;
      buf[o + 4] = hf.readByte(a);
    }
    var h = await crypto.subtle.digest("SHA-256", buf);
    return Array.from(new Uint8Array(h))
      .map(function (b) {
        return b.toString(16).padStart(2, "0");
      })
      .join("");
  }

  root.GCFirmware = { HexFile, identify, applyBundle, canonicalHash };
})(typeof window === "undefined" ? globalThis : window);
