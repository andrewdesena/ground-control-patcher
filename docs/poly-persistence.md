# Polyphony persistence — what is still missing (status: NOT ready to flash)

## Bottom line

The shipped v1 patch (clock + poly-record + velocity hook + playback gate) makes chords play when
they are captured live into RAM. It does **not** make the module read or write polyphonic note data
on the SD card. Until that exists, a browser-authored chord cannot play from a saved pattern, and a
chord recorded on the module does not survive a power cycle. **Do not flash for the polyphony MVP
until this document's work is implemented and emulator-tested.**

## What already exists

| piece | location | status |
|---|---|---|
| CCM poly array | `0x1000B530`, `track*0x880 + step*17`, byte0 = count, then `[note, vel]` pairs | populated live, read by the gate fan-out |
| velocity table | `0x1000FD00` (`vel_by_note[note]`) | live capture works |
| playback fan-out | cave `0x08047A00`, hook `0x08021A6E`, re-calls emitter `0x08021748` | works (emulator-tested) |
| single-note commit choke | `0x0801F32C` (`strb [r0,#0x2f5]` / `+0x2f6`) | overwrites one note per step |
| editor `steps2` writer/reader | `assets/editor.js` | writes/reads full chords in pattern files |

## Native pattern format (decoded)

Pattern files are JSON stored as `.txt`:

- melodic: `{ step_limit, count, duration, Polyrhythm{From,To}, steps:[{note,velocity,modifier,ratchet}] }`
- drum: `{ step_limit:[9], count, duration, Polyrhythm, modulations:[128], steps:[8][N], ratchets:[8][N] }`

`note` uses letter+octave+sharp order, e.g. `G8#` (= MIDI 116). The parser tolerates trailing
commas **and** missing commas between properties (the editor's `lenientJSON()` mirrors this).

The editor currently adds a `steps2` array of `{modifier,ratchet,notes:[[midi,vel],...],cc:[[n,v],...]}`.
The stock firmware ignores it.

## Firmware map (static, from `testdata/gc326.hex`)

- key strings: `0x08037160+` (`From`, `To`, `step_limit`, `count`, `duration`, `modulations`,
  `steps`, `ratchets`, `note`, `velocity`, `modifier`, `ArpNotes`, `Type`, `Param`, ...)
- writer format strings: `0x0803703d` (`"step_limit" : [ %u`), `0x08037097` (`"steps" :`),
  `0x080370db` (melodic `step_limit/count/duration`), `0x0803710e` (`"velocity"`, `"modifier"`, `"ratchet"`)
- writer code (literal-pool cluster): `0x0801a660` / `0x0801b4c8`
- parser key-reference literal pools: `0x0801c7a8`, `0x0801cb80`, `0x0801cf50`, `0x0801d04c`
- project/track loader function start: `0x0801ccc4` (`push.w {r4..lr}`, calls tokenizer `0x0801496c`,
  `memset` `0x080351fc`, `memcpy` `0x08035428`, helpers `0x0801b10c` / `0x0801b134`)
- pattern load function start: `0x0801d064`
- Strings for paths: `0x08037005` (`project?`), `0x0803700e` (`pattern?.txt`), `0x08037021`
  (`/projectX/trackD`), `0x0803702c` (`patternX.txt`)

These are static addresses in v3.26; the patcher must verify the base image hash before applying.

## Work items

1. **Load `steps2` (browser-authored chords play from the card).**
   After a pattern file is read and parsed, scan its text for `"steps2"` and decode the numeric
   triples into the poly array for each step. Needs the text-buffer pointer at the load call site
   (open question) and a bounded scanner in a cave. Alternative: teach the structured parser a new
   key, but raw-text scanning avoids touching its tokenizer.

2. **Write `steps2` (hardware-saved chords persist).**
   Hook the pattern writer after the `steps` array is emitted and append a `steps2` array built from
   the poly array, using a new format string in the cave. Must respect the output buffer size.

3. **Hardware entry appends notes.**
   Replace the single-note commit at `0x0801F32C` with a call that merges `(note,velocity)` into the
   poly array for the current step and advances the cursor only on an explicit next-step action.
   This covers both step-entry (clock off) and direct step-edit modes.

4. **Tests.** Extend `tools/test_*` in Unicorn: load a pattern with `steps2` and assert the poly
   array; run the writer and re-parse the emitted text; drive the entry hook with two note-ons and
   assert both notes survive one commit.

## Definition of done

- Browser-authored chord saved to card → module loads and plays all notes.
- Chord recorded on the module → saves as `steps2` → reloads and plays after power cycle.
- `verify.py` zero collateral, disassembly of every cave eyeballed, stock image untouched elsewhere.

## Progress

- **Loader sidecar read: implemented and emulator-tested.**
  `mods/poly-load.source.json` (cave `0x08047C00`, hook `0x0801CD96` after `f_close`) rewrites the
  path buffer to `poly<letter>`, opens it in the same project/track directory, reads 2,176 bytes into
  `0x1000B530 + track*0x880`, and skips the drum track.
  `tools/test_poly_load.py` PASS: track1/A and track3/C destinations, 2,176-byte copy, f_close, and
  `r3 = 0xFFFFFFFF` for the caller.
- **Writer sidecar save: implemented and emulator-tested.**
  `mods/poly-save.source.json` (cave `0x08047E00`, hook `0x0801C542`) opens `poly<letter>` with mode
  `0x0A`, writes 2,176 bytes from `0x1000B530 + track*0x880`, closes it, then closes the pattern FIL.
  `tools/test_poly_save.py` PASS (polyA/polyC, destination, 2,176 bytes, drum skip, close counts).
- **Combined bundle:** `mods/v1-poly-full.json` = v1 + load + save (12 sites), `verify.py` zero
  collateral; embedded in `index.html` as the patcher's v1.1 bundle.
- **Editor sidecar:** `poly<letter>` encode/decode (2,176 bytes) written on Save to SD and read on
  open; verified chord round-trip.
- **Hardware entry append: implemented and emulator-tested.**
  `mods/poly-entry.source.json` (cave `0x08048000`, hook `0x0801FD52`) merges each note-on into
  `0x1000B530 + track*0x880 + step*17` using `track+0x2E1` (track index) and `track+0x2DF` (edit
  step); dedupes by note, caps at 8. `tools/test_poly_entry.py` PASS (add, velocity update, chord,
  cap, track offset, r6 restore).
- **Combined bundle:** 14 sites (`v1-poly-full.json`), `verify.py` zero collateral, embedded in the
  patcher as v1.1.
- Remaining: hardware validation (flash, play browser chords, record+save chords, reload).
