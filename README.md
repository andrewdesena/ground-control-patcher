# gc-modder

Browser tool that takes a stock Endorphin.es **Ground Control** firmware `.hex`, bakes in mods, and
hands back a flashable `.hex`. Static site, no server, no upload: the file never leaves the tab.

Status: **build toolchain fixed; clock-priority patch builds, verifies, and emits a flashable
`.hex` — but it is EXPERIMENTAL and UNFLASHED.** Toolchain note: `tools/thumbfix.py` now encodes
far branches as `addend - instr_off` (gas emits `target-base-4`); `tools/test_thumbfix.py` is the
regression. `tools/verify.py` proves zero collateral, and `tools/apply.py` writes the new-flash cave
records the stock file omits, then re-checks content identity.

```
index.html          THE TOOL. Single self-contained file: double-click it, it works. UI + engine inside.
src/hexfile.js      Intel HEX parse / in-place patch / emit   (reference copy for the Node tests)
src/mods.js         mod bundle format, preconditions, applier (reference copy for the Node tests)
mods/index.json     list of shipped bundles ([] today)
test/roundtrip.mjs  parse -> emit byte-identical to the vendor file, patch, revert
test/mods.mjs       bundle apply, precondition abort, code-cave append, re-parse
testdata/           a stock v3.26 image for local testing
```

`index.html` must run from `file://` with no server, because that is how a normal person opens a
downloaded HTML file. That is why the engine is inlined instead of imported as an ES module: Chrome
blocks module imports on `file://`, and the page then renders but every button is dead. Keep
`src/*.js` in sync with the inlined copy when either changes; `src/` is what the tests exercise.

Run the tests: `node test/roundtrip.mjs && node test/mods.mjs`
Run the page: double-click `index.html`. Optional override for automated checks:
`python3 -m http.server 8899` then `http://127.0.0.1:8899/?sample=testdata/gc326.hex`

## Why it is shaped like this

The image has **694,256 blank bytes** of flash at `0x08046810–0x080EFFFF`, and the running app keeps its
hot MIDI path in SRAM, copied from flash at boot. So most real mods are not byte edits, they are
*small routines injected into the cave plus a 2 or 4 byte hop at the call site*. A patcher therefore has
to do three things and nothing else:

1. rewrite bytes **in place** inside the vendor's existing record grid (never re-lay-out the image),
2. **append** new data records for the cave, with the `EXT_LIN` records the target address needs,
3. recompute each touched record's checksum and re-parse the result before offering it for download.

That is what `hexfile.js` does. Round-trip on stock v3.26 is byte-identical, which is the property that
makes diffs of two builds readable and keeps any change scrolling in a `.hex` viewer as a small hunk.

## Bundle format

```json
{
  "name": "clock-priority",
  "status": "experimental",
  "description": "0xF8/0xFA/0xFC bypass the event queue; clock only waits on the byte in flight.",
  "requires": { "blank": ["0x08046810", "0x080EFFFF"] },
  "patches": [
    { "addr": "0x08019620", "bytes": "...", "note": "clock builder -> cave stub" },
    { "addr": "0x08046810", "bytes": "...", "note": "injected routine" }
  ]
}
```

Rules the applier enforces:

* any patch below `0x08010000` throws (bootloader territory, not ours),
* `requires.blank` ranges are verified before a byte is written; failure means no download at all,
* the patched result is re-parsed before the download starts, so a broken emit can't reach a card.

## Roadmap

| mod | difficulty | needs |
|---|---|---|
| clock priority bypass | small: one hop + ~40 bytes of cave code | a spare RAM byte for the pending-realtime flag |
| CC number remap for external inputs | small: table patch | the exact CV -> CC mapper (one more RE pass) |
| polyphonic record for tracks 1-3 | large: capture, storage and playback | new step array + `steps2` JSON key + parser fallback |

The polyphony mod is the one that decides the project's shape: it is a real feature port, not a patch,
so the bundle needs a code-cave routine that is big enough to have its own tests. Design sketch lives
in `../GC_RE_v3.26_findings.md` §2.

## Open risk

The bootloader at `0x08000000–0x0800FFFF` is **not in the hex**, so whether it validates the app image is
unverified. Nothing in the app uses the hardware CRC unit or a CRC32 table, which is encouraging, but the
first modded image should be flashed on a unit with a recovery path (SD-card boot from v2.x procedure)
before this is published. If the bootloader does verify, the whole approach changes to "reflash via the
bootloader's own recovery path".
