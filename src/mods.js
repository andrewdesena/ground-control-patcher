/**
 * mods.js — mod bundle format + applier (reference implementation for tests).
 * The shipped browser tool has this same logic inlined in index.html.
 */
import { HexFile, isBlank } from './hexfile.js';

export const APP_BASE = 0x08010000;

export function num(v) {
  return typeof v === 'number' ? v : parseInt(v, 16);
}

export function bytesOf(v) {
  if (v instanceof Uint8Array) return v;
  const s = String(v).replace(/[^0-9a-fA-F]/g, '');
  if (s.length % 2) throw new Error('odd hex length');
  const out = new Uint8Array(s.length / 2);
  for (let i = 0; i < out.length; i++) out[i] = parseInt(s.substr(i * 2, 2), 16);
  return out;
}

/** verify the image looks like a Ground Control build we understand */
export function identify(hex) {
  const u32 = (a) => {
    const b = hex.read(a, 4);
    return (b[0] | (b[1] << 8) | (b[2] << 16) | (b[3] << 24)) >>> 0;
  };
  const sp = u32(APP_BASE);
  const reset = u32(APP_BASE + 4);
  if (sp !== 0x20020000) throw new Error(`unexpected stack pointer 0x${sp.toString(16)} — not a Ground Control image?`);
  if ((reset & 0x1) === 0) throw new Error('reset vector is not a Thumb address — wrong load base?');
  return { sp, reset };
}

/**
 * Apply a bundle. Throws on any precondition failure so a user never gets a
 * half-patched firmware. Returns a report.
 */
export function applyBundle(hex, bundle) {
  const id = identify(hex);

  const blankPairs = (bundle.requires?.blank || []);
  const ranges = typeof blankPairs[0] === 'string' ? [blankPairs] : blankPairs;   // accept flat or nested
  for (const [start, end] of ranges.map(([x, y]) => [num(x), num(y)])) {
    if (!isBlank(hex, start, end - start + 1)) {
      throw new Error(`precondition failed: expected blank flash 0x${start.toString(16)}..0x${end.toString(16)}`);
    }
  }

  const report = [];
  for (const p of bundle.patches) {
    const addr = num(p.addr);
    const bytes = bytesOf(p.bytes);
    if (addr < APP_BASE) throw new Error(`patch at 0x${addr.toString(16)} is below the app base (bootloader area)`);
    const { inPlace, appended } = hex.patch(addr, bytes);
    report.push({ addr, length: bytes.length, inPlace, appended, note: p.note || '' });
  }
  return { id, report };
}
