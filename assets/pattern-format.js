/* Binary-safe Ground Control pattern codec. Usable in a browser or Node. */
(function (root) {
  "use strict";
  const MAX_CC = 4,
    CC_SIZE = 540,
    STEPS = 128,
    NOTES = 8,
    RECORD = 17,
    POLY = 2176,
    TRAILER = 2188;
  const LETTERS = "ABCDEFGHIJKLMNOPQRSTVWYZ".split("");
  const NAMES = [
    "C",
    "C#",
    "D",
    "D#",
    "E",
    "F",
    "F#",
    "G",
    "G#",
    "A",
    "A#",
    "B",
  ];
  const enc = new TextEncoder(),
    dec = new TextDecoder("utf-8", { fatal: true });
  const clone = (value) => JSON.parse(JSON.stringify(value));
  const empty = () => ({ notes: [], cc: [], modifier: 0, ratchet: 0 });
  function crc32(bytes) {
    let c = 0xffffffff;
    for (const byte of bytes) {
      c ^= byte;
      for (let b = 0; b < 8; b++) c = (c >>> 1) ^ (c & 1 ? 0xedb88320 : 0);
    }
    return (c ^ 0xffffffff) >>> 0;
  }
  function noteToMidi(value) {
    const m = /^([A-G])(#?)(-?\d+)(#?)$/.exec(String(value));
    if (!m) return null;
    const n =
      (Number(m[3]) + 2) * 12 + NAMES.indexOf(m[1]) + (m[2] || m[4] ? 1 : 0);
    return n >= 0 && n <= 127 ? n : null;
  }
  function nativeNote(n) {
    const name = NAMES[n % 12],
      oct = Math.floor(n / 12) - 2;
    return name.length > 1 ? name[0] + oct + "#" : name + oct;
  }
  const displayNote = (n) => NAMES[n % 12] + (Math.floor(n / 12) - 1);
  function integer(n, min, max, label) {
    if (!Number.isInteger(n) || n < min || n > max)
      throw new Error(label + " must be " + min + " to " + max);
  }
  function validate(pattern) {
    integer(pattern.length, 1, 128, "Pattern length");
    if (pattern.base?.duration !== undefined)
      integer(pattern.base.duration, 0, 7, "Step duration");
    for (const [i, step] of pattern.steps.entries()) {
      if (i >= 128) throw new Error("A pattern can contain at most 128 steps");
      if (step.notes.length > NOTES)
        throw new Error("Step " + (i + 1) + " exceeds eight notes");
      const pitches = new Set();
      for (const [n, v] of step.notes) {
        integer(n, 0, 127, "Pitch");
        integer(v, 1, 127, "Velocity");
        if (pitches.has(n))
          throw new Error("Duplicate pitch in step " + (i + 1));
        pitches.add(n);
      }
      const controllers = new Set();
      for (const [n, v] of step.cc) {
        integer(n, 0, 127, "CC number");
        integer(v, 0, 127, "CC value");
        if (controllers.has(n))
          throw new Error("Duplicate CC in step " + (i + 1));
        controllers.add(n);
      }
    }
    const controllers = new Set(
      pattern.steps
        .flatMap((s) => s.cc.map((c) => c[0]))
        .concat(
          Object.keys(pattern.ccSources || {}).map(Number),
          pattern.ccLanes || [],
        ),
    );
    for (const n of pattern.ccLanes || []) integer(n, 0, 127, "CC number");
    if (controllers.size > MAX_CC)
      throw new Error("A track supports at most four CC lanes");
    for (const [n, src] of Object.entries(pattern.ccSources || {})) {
      integer(+n, 0, 127, "CC number");
      integer(src.input, 0, 3, "CV input");
      integer(src.min, 0, 127, "CV minimum");
      integer(src.max, 0, 127, "CV maximum");
    }
    return pattern;
  }
  function blank(drum = false) {
    return {
      drum,
      length: 16,
      base: { duration: 2, Polyrhythm: { From: 4, To: 4 } },
      steps: Array.from({ length: STEPS }, empty),
      ccSources: {},
      ccLanes: [],
      warnings: [],
      source: "new",
    };
  }
  function parseText(text) {
    try {
      return JSON.parse(text.replace(/^\uFEFF/, ""));
    } catch {}
    return JSON.parse(
      text
        .replace(/^\uFEFF/, "")
        .replace(/,\s*([}\]])/g, "$1")
        .replace(/([}\]"])\s*\n\s*"/g, '$1,\n"')
        .replace(/(\d)\s*\n\s*"/g, '$1,\n"'),
    );
  }
  function decode(input, drum = false) {
    const bytes = input instanceof Uint8Array ? input : new Uint8Array(input);
    const nul = bytes.indexOf(0),
      text = dec.decode(nul < 0 ? bytes : bytes.subarray(0, nul));
    const base = parseText(text),
      p = blank(drum);
    p.base = base;
    p.source = "stock";
    const limit = drum
      ? base.step_limit?.[1] || base.count || 16
      : base.step_limit || 16;
    p.length = Math.max(1, Math.min(128, Number(limit) || 16));
    if (drum) {
      for (let lane = 0; lane < 8; lane++)
        for (let s = 0; s < 128; s++) {
          const v = base.steps?.[lane]?.[s];
          if (Number.isInteger(v) && v > 0 && v < 128)
            p.steps[s].notes.push([lane, v]);
        }
      return p;
    }
    (base.steps || []).slice(0, 128).forEach((st, i) => {
      const note = noteToMidi(st.note);
      p.steps[i] = {
        notes: note !== null && st.velocity > 0 ? [[note, st.velocity]] : [],
        cc: [],
        modifier: st.modifier || 0,
        ratchet: st.ratchet || 0,
      };
    });
    if (nul >= 0) {
      const tail = bytes.subarray(bytes.length - TRAILER),
        header = [0, 71, 67, 80, 49, 0, 0, 0];
      if (
        tail.length !== TRAILER ||
        !header.every((v, i) => tail[i] === v) ||
        crc32(tail.subarray(8, 2184)) !==
          new DataView(tail.buffer, tail.byteOffset).getUint32(2184, true)
      ) {
        p.warnings.push(
          "Chord trailer is missing, damaged or unsupported. Native notes were loaded; saving will replace the damaged trailer.",
        );
        p.source = "damaged";
      } else {
        let valid = true;
        for (let s = 0; s < 128; s++) {
          const off = 8 + s * RECORD,
            count = tail[off],
            notes = [],
            seen = new Set();
          if (count > NOTES) {
            valid = false;
            break;
          }
          for (let k = 0; k < count; k++) {
            const n = tail[off + 1 + k * 2],
              v = tail[off + 2 + k * 2];
            if (n > 127 || v < 1 || v > 127 || seen.has(n)) {
              valid = false;
              break;
            }
            seen.add(n);
            notes.push([n, v]);
          }
          if (!valid) break;
          // Match firmware playback: an empty record leaves the native mono note.
          if (count) p.steps[s].notes = notes;
        }
        if (!valid) {
          const fallback = decode(enc.encode(text));
          fallback.warnings.push(
            "Chord records are invalid. Native notes were loaded.",
          );
          fallback.source = "damaged";
          return fallback;
        }
        p.source = "GCP1";
        if (nul !== bytes.length - TRAILER) {
          const cc = bytes.subarray(nul, bytes.length - TRAILER);
          const ok =
            cc.length === CC_SIZE &&
            [0, 71, 67, 67, 49, 0, 0, 0].every((v, i) => cc[i] === v) &&
            crc32(cc.subarray(8, 536)) ===
              new DataView(cc.buffer, cc.byteOffset).getUint32(536, true);
          let validCC = ok;
          const seen = new Set();
          if (ok)
            for (let l = 0; l < 4; l++) {
              const off = 8 + l * 132,
                code = cc[off],
                src = cc[off + 1];
              if (
                code > 128 ||
                src > 4 ||
                cc[off + 2] > 127 ||
                cc[off + 3] > 127 ||
                (code && seen.has(code))
              ) {
                validCC = false;
                break;
              }
              if (!code) continue;
              seen.add(code);
              const num = code - 1;
              p.ccLanes.push(num);
              if (src)
                p.ccSources[num] = {
                  input: src - 1,
                  min: cc[off + 2],
                  max: cc[off + 3],
                };
              for (let s = 0; s < 128; s++) {
                const v = cc[off + 4 + s];
                if (v > 128) {
                  validCC = false;
                  break;
                }
                if (v) p.steps[s].cc.push([num, v - 1]);
              }
            }
          if (validCC) p.source = "GCP1+GCC1";
          else {
            p.steps.forEach((s) => {
              s.cc = [];
            });
            p.ccSources = {};
            p.ccLanes = [];
            p.warnings.push(
              "This pattern contains a damaged or unsupported extension. Save is blocked to preserve its data.",
            );
          }
        }
      }
    }
    return p;
  }
  function encode(p) {
    validate(p);
    if (p.warnings.some((w) => w.includes("unsupported extension")))
      throw new Error("Cannot overwrite an unsupported pattern extension");
    const controllers = [
      ...new Set(
        p.steps
          .flatMap((s) => s.cc.map((c) => c[0]))
          .concat(Object.keys(p.ccSources || {}).map(Number), p.ccLanes || []),
      ),
    ].sort((a, b) => a - b);
    if (p.drum && controllers.length)
      throw new Error("CC lanes belong to melodic tracks 1–3");
    const base = clone(p.base || {}),
      used =
        p.steps.slice(0, p.length).some((s) => s.notes.length || s.cc.length) ||
        controllers.length > 0;
    if (p.drum) {
      base.step_limit = Array.isArray(base.step_limit)
        ? base.step_limit
        : Array(9).fill(p.length);
      for (let lane = 1; lane <= 8; lane++) base.step_limit[lane] = p.length;
      base.steps = Array.from({ length: 8 }, (_, pad) =>
        Array.from(
          { length: p.length },
          (_, s) => p.steps[s].notes.find((n) => n[0] === pad)?.[1] ?? 128,
        ),
      );
      base.ratchets = Array.from({ length: 8 }, (_, pad) =>
        Array.from(
          { length: p.length },
          (_, s) => base.ratchets?.[pad]?.[s] || 0,
        ),
      );
    } else {
      base.step_limit = p.length;
      base.steps = p.steps.slice(0, p.length).map((st) => {
        const primary = st.notes.length
          ? st.notes.reduce((a, b) => (a[0] < b[0] ? a : b))
          : null;
        return {
          note: primary ? nativeNote(primary[0]) : "G8#",
          velocity: primary?.[1] || 0,
          modifier: st.modifier || 0,
          ratchet: st.ratchet || 0,
        };
      });
    }
    base.count = used ? p.length : 0;
    delete base.steps2;
    const text = enc.encode(JSON.stringify(base) + "\n");
    if (text.length + (controllers.length ? CC_SIZE : 0) > 10200)
      throw new Error(
        "Native pattern text exceeds the 10,200-byte firmware loader limit",
      );
    if (p.drum) return text;
    const prefix = text.length + (controllers.length ? CC_SIZE : 0),
      out = new Uint8Array(prefix + TRAILER);
    out.set(text);
    if (controllers.length) {
      const cc = out.subarray(text.length, prefix);
      cc.set([0, 71, 67, 67, 49, 0, 0, 0]);
      controllers.forEach((num, l) => {
        const off = 8 + l * 132,
          src = p.ccSources?.[num];
        cc[off] = num + 1;
        if (src) {
          cc[off + 1] = src.input + 1;
          cc[off + 2] = src.min;
          cc[off + 3] = src.max;
        }
        for (let s = 0; s < p.length; s++) {
          const pair = p.steps[s].cc.find((c) => c[0] === num);
          if (pair) cc[off + 4 + s] = pair[1] + 1;
        }
      });
      new DataView(cc.buffer, cc.byteOffset).setUint32(
        536,
        crc32(cc.subarray(8, 536)),
        true,
      );
    }
    out.set([0, 71, 67, 80, 49, 0, 0, 0], prefix);
    for (let s = 0; s < 128; s++) {
      const ns = s < p.length ? p.steps[s].notes : [],
        off = prefix + 8 + s * RECORD;
      out[off] = ns.length;
      ns.forEach(([n, v], k) => {
        out[off + 1 + k * 2] = n;
        out[off + 2 + k * 2] = v;
      });
    }
    new DataView(out.buffer).setUint32(
      prefix + 2184,
      crc32(out.subarray(prefix + 8, prefix + 2184)),
      true,
    );
    return out;
  }
  const api = {
    MAX_CC,
    CC_SIZE,
    STEPS,
    NOTES,
    POLY,
    TRAILER,
    LETTERS,
    blank,
    clone,
    crc32,
    decode,
    encode,
    validate,
    parseText,
    noteToMidi,
    nativeNote,
    displayNote,
  };
  if (typeof module !== "undefined") module.exports = api;
  root.GCFormat = api;
})(typeof window === "undefined" ? globalThis : window);
