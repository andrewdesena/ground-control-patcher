# Ground Control — Polyphony patcher

Unofficial customization of **Endorphin.es Ground Control** firmware **v3.26**, applied **locally in
your browser**. Firmware is never uploaded. This repo contains only the static site, patch
definitions, emulator/test tooling, and docs — **not** the vendor firmware; you bring your own stock
`gc-*.hex`.

> **Status: v1.1 is emulator-proven; hardware validation pending.** v1.1 = clock fix + live chord
> capture with real velocity + stock-gate playback + **hardware chord entry** + **poly sidecar
> load/save** (`trackN/poly<letter>`). Every layer passes Unicorn tests and `verify.py` shows zero
> collateral. See [`docs/poly-persistence.md`](docs/poly-persistence.md).

Open the patcher: **https://andrewdesena.github.io/ground-control-patcher/**
Requires **Chrome or Edge over https** (the SD-card step uses the File System Access API).

The **Pattern Editor** is built into the same page — switch to the **Editor** tab: full MIDI 0–127
piano roll, left track bar for Tracks 1/2/3/D, polyphonic note entry, **per-note velocity with
multi-select and velocity-shaded notes**, **stacked CC automation lanes** (draggable points), and
**copy/paste** of note patterns. It also **opens the whole SD card**: browse/create/delete `projectA/B/…`
folders, switch **patterns A/B/C/…** within a project, edit **`GlobalSettings.txt`** and the native
project/track files, and **save back in the GC's own format** (originals are backed up as `.bak`).
Our own JSON export/import remains available too.

Printable docs: [reference guide (Letter)](docs/reference/guide-letter.pdf) ·
[reference guide (A4)](docs/reference/guide-a4.pdf) ·
[quick card (Letter)](docs/reference/quick-card-letter.pdf) ·
[quick card (A4)](docs/reference/quick-card-a4.pdf)

## Use

1. **Back up your whole microSD card.**
2. Download the official Ground Control firmware (`gc-*.hex`) from endorphin.es.
3. Open the patcher → select that `.hex` → tick **Polyphony v1** → **Build modded firmware**.
4. Hold **PROJ ~5 s** on the module to mount the SD over USB → **Connect GC SD card** → **Install to
   GC**. It writes the patched file to the **card ROOT** as **`<stock-name>-poly1.hex`** — a
   `gc-*.hex` name that still satisfies the updater but is clearly marked as patched (keep only one
   firmware `.hex` there).
5. **PROJ ~5 s** again: the module reboots and flashes. Power-cycle when done.

The patcher **creates a file; it does not flash the module itself** — the module's own bootloader
flashes a `gc-*.hex` found at the card root.

## What Polyphony v1.1 changes

- **Clock priority** — `0xF8`/`0xFA`/`0xFB`/`0xFC` go to the front of the MIDI event queue instead of
  waiting behind notes.
- **Polyphonic note capture** for melodic tracks 1–3 — every held note is stored per step with its
  **real velocity** (not just the last note).
- **Stock-gate chord playback** — each chord note replays through the real note emitter with the
  **same timing and gate as the primary note**, so chords hold exactly like stock.
- **Hardware chord entry** — a note-on while editing a step appends to that step's poly record
  (deduped, max 8 notes), so step-edit mode accepts chords instead of overwriting one note.
- **SD persistence** — each save also writes `trackN/poly<letter>` (2,176 bytes = 128 × [count,
  note/vel pairs]); loading a pattern reads it straight into the poly array. Chords survive power
  cycles, and browser-authored chords play on the module.

## Limits (v1.1)

- Melodic tracks 1–3 only; assumes default channels 1/2/3.
- Stock projects still load as mono until a chord is recorded or authored and saved by v1.1/editor.
- Captured velocity falls back to 100 if a note-on velocity wasn't seen.
- Up to 8 notes per step.

## Hardware validation checklist (v1.1)

1. Flash the `-poly1.hex` from the card root (PROJ ~5 s → `BURN` → 10–15 s → reboot).
2. Play a stock project: tracks and clock behave as before.
3. In the editor, save a chord pattern to the card; load it on the module and play — all chord notes sound.
4. Enter a chord in step-edit mode on the module and play.
5. Save the pattern on the module, power-cycle, reload — the chord persists.
6. If anything fails: return to stock (original `gc-*.hex` at root, PROJ ~5 s) and keep the pattern/SD state for diagnosis.

## Verify / return to stock

- Supported base: firmware **v3.26**, canonical image SHA-256
  `e1db4815f8cf2983f832493aa8b2085586cb5ea10446e133774bdfc91bca9f52`.
- `tools/verify.py` proves a bundle moves **0** untouched bytes; the tool re-parses its output before
  writing.
- To return to stock: put the original vendor `gc-*.hex` back at the card root, **PROJ ~5 s**.

---

# Technical / development

Status: **Polyphony v1.1 builds and is emulator-verified** (clock fix, capture w/ real velocity,
stock-gate chord playback, hardware entry append, poly sidecar load/save); **EXPERIMENTAL /
PENDING HARDWARE VALIDATION.** The **Unicorn emulator harness**
(`tools/fw_sandbox.py`) runs real firmware functions including the player's **FPU/VFP** path
(set a Cortex-M7/M4 core *before* mapping memory, or VFP won't decode). Playback step cursor is
solved (`docs/polyphony-capture.md`). Toolchain: `tools/thumbfix.py` encodes far branches as
`addend - instr_off`; `tools/verify.py` proves zero collateral; `tools/apply.py` writes the new-flash
cave records the stock file omits, then re-checks content identity.

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

## Dynamic analysis tooling (emulator)

No hardware needed to run firmware functions. All tools use `.venv/bin/python` (Unicorn + capstone).

```
tools/fw_sandbox.py   reusable Unicorn sandbox: loads the full image, maps FLASH/SRAM/CCM/wide
                      peripherals, calls any function with set registers/memory, steps + traces.
tools/trace_emit.py   runs the note-on / note-off / pair primitives, captures the real MIDI bytes.
tools/boot_trace.py   boots from reset with a small RCC model; reports init progress + stalls.
```

Run: `.venv/bin/python tools/trace_emit.py` (prints captured messages, e.g. `90 3C 64`).

**Critical gotcha (do not remove):** the sandbox sets a **Cortex-M7/M4 CPU model before mapping any
memory** and enables CPACR. The audio player uses hardware FPU/VFP instructions; on Unicorn's default
core they fail to decode (`UC_ERR_INSN_INVALID`) and the player cannot run at all. Setting the model
after `mem_map` does not work. This is the key that makes emulator-testing the playback path possible.

**Pick up here:** the playback step cursor is solved (`docs/polyphony-capture.md`). To finish the
chord fan-out, construct a real track/voice object in the sandbox and drive `0x8021A14` to observe
its per-step emits (`0x8021748` -> `0x8019A92`), then splice the fan-out cave and prove it with
`verify.py` before flashing. Boots past reset still need an RCC/PLL peripheral model (clock init
returns error -> fatal loop `0x0801245A`); a full boot is optional if the track object can be faked.

## Open risk

The bootloader at `0x08000000–0x0800FFFF` is **not in the hex**, so whether it validates the app image is
unverified. Nothing in the app uses the hardware CRC unit or a CRC32 table, which is encouraging, but the
first modded image should be flashed on a unit with a recovery path (SD-card boot from v2.x procedure)
before this is published. If the bootloader does verify, the whole approach changes to "reflash via the
bootloader's own recovery path".
