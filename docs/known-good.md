# Known-good poly build

Last hardware-confirmed build: **`71957a3`** (10-site bundle). This is what
`index.html` still embeds and what users get today.

- Output file: `gc-v3.26_poly-v1.1.hex`
- SHA-256: `226f824becd040e315e0bed269fe77571dc31d62584f954098bbd4b32dad0454`
- Size: 713,490 bytes
- Site commit currently serving it: `f9cd51f`
- Source copy of the bundle: `mods/v1-poly-known-good.json`

Hardware-confirmed behavior:

- Project C / Pattern A plays the saved C-E-G chord (60/64/67).
- Tracks 2/3 stay quiet when cleared.
- Module save, power-cycle, reload, and replay keep the chord.

Known defect (unfixed): switching projects (C -> A -> B -> C) comes back
monophonic until a power cycle. Stock map and the reason the first fix attempt
missed it: `docs/project-switch-preload.md`.

Not in this build:

- EDIT-mode chord key lights.
- Module-only lifecycle cache/async loader (regressed playback; parked).
- Save-gating and ProjectSettings JSON fixes.

## v1.3 commit-handoff reload — HARDWARE CONFIRMED

`mods/poly-commit-reload.source.json` (cave `0x08047A00` + hook at `0x08021528`),
merged onto the byte-exact v1.1 base by `tools/build_v1.py`.

- Bundle: `mods/v1-poly-commit.json` (12 sites: the 10 v1.1 sites unchanged, plus
  the cave and the hook)
- Image: `gc-v3.26_poly-v1.3.hex`, sha256
  `bfbc532780dc68b402212dbbc822dd9e906fb9fb41ea3542223dee0537c6cc1a`, 714,263 bytes
- Only behavior change: at playback start, after the switch commit has installed
  the incoming project's patterns and letters, each melodic track republishes its
  own `poly<letter>` sidecar into the chord bank. Details in
  `docs/project-switch-preload.md`.
- Independent adversarial review: `VERDICT: SAFE TO FLASH`, no must-fix items; a second, narrower
  review returned the same verdict independently.
  Confirmed by disassembly: `0x08021338` has one caller (`0x0802150E`), so a playing
  switch cannot skip the hook; `0x08023158` writes `[track+0x2E]`; the project index
  at `[0x2000B250+0x249]` is what stock uses for `/project<letter>`; the cave's bank
  index, directory digit (`index+1`) and `cmp #3` bound match the fan-out; r4-r11
  preserved, stack balanced, 8-byte aligned, returns to `0x0802152C`; the cave only
  writes `0x1000B530..0x1000CEB0` and `0x1000E420`.
- Tests: `tools/test_poly_commit_reload.py`, 13 assertions, including one that runs
  the **real** `0x08023158` to prove the letter is final before the cave reads it.
- Residual risk flagged by the review: up to 3 x 2176-byte SD reads inside the UI
  event path each time the commit fires (flag `0x2000C5D8` can be seen more than
  once), and the bank being rewritten while transport already runs. That is exactly
  what the "no stuck notes" criterion measures on hardware.

Hardware gate, 2026-11-15: **all four tests passed** on the module with `GCV326P.HEX`
(sha256 `bfbc5327...6cc1a`) copied to the card root.
1. Cold boot: Project C / track 1 / pattern A plays C-E-G.
2. C -> A -> B -> C while playing returns with the chord; no stuck notes, no track 2/3 blinks.
3. Save + power-cycle + reload keeps the chord.
4. Explicit clear + save + power-cycle is silent.

This is now the shipped build: `index.html` embeds these 12 sites as v1.3 and downloads
`gc-v3.26_poly-v1.3.hex`.


## v1.2 sidecar gate — REJECTED, do not flash

`mods/poly-load-sidecar.source.json` + `mods/v1-poly-full-gated.json` publish
`poly<[track+0x2E]>` from the loader hook. Codex QA returned `VERDICT: NOT SAFE`:

1. During a playing project switch the loader writes to a temporary destination
   (`0x2000BC00 + (sel-1)*0x194`), which the cave's range match rejects, so the
   outgoing bank survives. A project with only pattern A never publishes at all.
2. The active letter is installed later, at the deferred commit
   (`0x0802150E` -> `0x08021338`, letter write at `0x0802144E`), so the hook can
   publish the outgoing letter's chord.
3. Inherited claims it does not hold for: letters D..Z never reach the publish
   (`0x4F0` bound), melodic track 3 is excluded (`r5 < 3` includes the drum slot
   instead), and the save cave at `0x08047E00` indexes banks by pattern letter.
4. The tests drive single loader calls and model the decisive path away; they
   would pass with a broken cave.

State left behind: `index.html` is back on the v1.1 bytes (version 1.1,
`gc-v3.26_poly-v1.1.hex`), and the generated v1.2 hex plus `GCV326P.HEX` were
deleted so nothing unvalidated can be copied to a card. `tools/build_v1.py` and
the unicorn loader harness (`tools/test_poly_activegate.py`) are kept for reuse.

Rules for the next attempt:

1. Start from the v1.1 bundle. Do not replace the loader/fan-out architecture wholesale.
2. Change one behavior at a time behind a diagnostic flash.
3. Publish from the committed playback identity, not from the loader hook.
4. Hardware acceptance for every flash: chord plays, save survives power-cycle, no extra-track blinks.
5. Keep a card backup under `~/Downloads/gc-card-backups/` before any save test.

## v1.4 EDIT chord key lights — built, unit-gated, awaiting review + hardware

Stacked on v1.3: `mods/poly-editlights4.source.json` merged by `tools/build_v1.py` on top of
`mods/poly-commit-reload.source.json`.

- Bundle: `mods/v1-poly-edit.json` (15 sites: the 12 v1.3 sites unchanged, plus the lights cave
  `0x08048C00`, the hook at `0x08012068`, and the 48-byte key tables at `0x08048B00`)
- Image: `gc-v3.26_poly-v1.4.hex` / `GCV326Q.HEX`, sha256
  `aba41b1b6f107a092d60127f3aa1be067e50b4d1e1feaa90079eb4bd52f64842`, 715,208 bytes
- Behavior: in EDIT mode only, OR the edited step's stored chord notes into `0x20001E74` next to the
  primary key stock lit. Set-only, no SD I/O, no writes outside that buffer.
- Track source: the manager table at `0x20000450` (4 slots; stock's `0x0801F26C` initialises each
  with its own 0-based id at `+0x2E1`, and site `0x0801FF26` does `[0x20000450 + idx*4]` then reads
  `+0x2DB`, which is the access pattern the cave reproduces). EDIT flag `+0x2DC`, step cursor
  `+0x2DF`. A manager is skipped unless its flag is set and its track is melodic (`[track+0x2D]==1`).
- Why v3 was not shipped: it derived the track from `0x2000CADA` minus 1, and stock bounds that byte
  with `cmp r0,#3; bls` at `0x08023432`, i.e. it is already 0-based; the subtraction would have
  shifted every track by one. v4 reads the id from the manager itself and consults no global.
- Tests: `tools/test_poly_editlights4.py`, 6 cases, all entering through the real hook at
  `0x08012068` via `0x08012008` (no direct cave calls), asserting exact key sets, playback silence,
  drum silence, letter scaling, and that nothing outside `0x20001E74` changed.
- `tools/verify.py` clean; browser engine == python image (15 sites, 254,240 addressed bytes, 0
  mismatches).

### Review of v1.4 (2026-11-15): one negative verdict, overruled with evidence

A delegated review returned `VERDICT: NOT SAFE` claiming that table `0x08038370` is ordered
`[drum, track1, track2, track3]` and that the bank index must therefore be `[mgr+0x2E1] - 1`.
That is refuted by the hardware-confirmed v1.1 cave itself: `0x08049000` matches the track pointer
against `0x08038370` with `cmp r5,#3; bhs` and publishes into `bank = 0x1000B530 + r5*0x880`, i.e.
**bank index == table index**, and chords play on hardware with that build. The fan-out at
`0x08047600` uses the same identity (`r7 = fp<<11 + fp<<7`). Stock also treats `+0x2E1` as a direct
index into the table (`0x0801FCD6`: `ldrb r2,[r4,#0x2e1]` -> `ldr r3,[0x080386D0 + r2*4]` ->
`ldrb r3,[r3,#0x2d]`), so `bank = +0x2E1` is consistent with both the loader and the fan-out.
The review's experiment seeded `+0x2D = 1` on indices 1..3 while placing track 1's chord in bank 0,
which is the very mismatch it reported. `0x08038370` and `0x080386D0` both hold
`[0x20013DEC, 0x200117C8, 0x2000F1A4, 0x2000CB80]`.

Two review points were valid and are now covered by tests: the cave must return `r0=0x20002B2C`,
`r1=0x20001E74` to stock at `0x0801206E` (asserted through a code hook on every case), and a
neighbouring bank holding a different chord must not leak (added as a case).

Known cosmetic caveat: `+0x2DC` is the step-editor-open flag and `+0x2DB` selects the sub-page, so
the cave can also light chord keys on the editor's non-step sub-pages. It never writes outside
`0x20001E74` and stock rebuilds that buffer every frame.

## Correction: v1.3 was a no-op, and track 3 had no polyphony (2026-11-15)

Two facts established by executing the stock constructors in the sandbox, then corrected:

1. **Track type byte `+0x2D` is 1 for the drum and 0 for melodic tracks.** Every cave in
   v1.3/v1.4/v1.5 tested `== 1` for "melodic", so they matched the drum and skipped every real
   track. v1.3's hardware pass was therefore not caused by its patch; the same-letter project
   switch it tested never disturbed the chord bank. `index.html` is rolled back to v1.1 until a
   corrected build passes hardware.
2. **Table `0x08038370` is ordered `[drum, track1, track2, track3]`** and the chord bank index
   equals the table index, so the drum owns bank 0 and tracks 1-3 own banks 1-3. The v1.1 fan-out
   and sidecar loader both stopped at index 3 (`cmp ... #3`), so **track 3 never received chord
   fan-out or a sidecar load**. `0x20013DEC` is the drum: its constructor builds 9 lanes.

### v1.7 (unproven)

- `mods/v1-poly-base4.json` — v1.1 base with the fan-out bound (`0x08047634`) and the loader bound
  (`0x08049010`) widened to 4, so bank 3 is reachable. The 4th-bank region
  `0x1000CEB0..0x1000D730` has zero references in stock, so it is free.
- `mods/poly-commit-reload.source.json` — corrected: melodic is type 0, indices 1-3, directory
  digit == track number, bank == index.
- `mods/poly-editlights6.source.json` — contributed by Codex after a full trace of the display
  path (`0x080207B4 -> 0x0802AE20 -> 0x08027D24 -> 0x0801ECFC -> 0x0801227C`); reads the real
  editor state at `0x2001C230` (`+7` cursor, `+0xC` track pointer), handles the 7-byte frame, and
  skips the drum via `+0x2D == 1`.
- `mods/v1-poly-track3.json` / `gc-v3.26_poly-v1.7.hex` / `GCV326U.HEX`, sha256
  `c7e3c450ad1526947c464151580931a7ae58fad540100fbcf2c95a53bc95088f`, 15 sites.
- `tools/test_poly_track3.py` proves it with stock-accurate seeds: track1 -> bank 1, track2 ->
  bank 2, track3 -> bank 3, drum untouched, no SD I/O on an ordinary play press.
- Hardware gate still required, and the switch test must use projects holding **different** chords.

## v1.9 — HARDWARE CONFIRMED (2026-11-16)

All four tests passed on hardware, with the dub techno project C loaded:

1. Playback: three melodic tracks with chords plus drums.
2. **Save + power cycle + reload: chords survive on all three tracks** (the save cave now
   writes the saving track's own bank).
3. Step edit on a track 3 chord step shows the full chord.
4. Project switch while playing returns with the chords.

Bundle `mods/v1-poly-dub.json` (15 sites), image `gc-v3.26_poly-v1.9.hex` / `GCV326W.HEX`,
sha256 `38a87fb6d9c43ec6de47dd40d964aba19de86cc7cc4ddae5c8de404c3906f661`, 715,290 bytes.
Composition of the bundle:

- `mods/v1-poly-base4.json` — v1.1 base with the fan-out and loader bounds widened to 4, so
  bank 3 (track 3) is reachable.
- `mods/poly-commit-reload.source.json` — post-switch republish at `0x08021528`; melodic type 0,
  indices 1-3, directory digit == track number, bank == table index.
- `mods/poly-editlights6.source.json` — EDIT-mode chord lights from the real editor state
  (`0x2001C230`, `+7` cursor, `+0xC` track), 7-byte frame, drum skipped by type, track loop to 4.
- `mods/poly-save-track.source.json` — save-time sidecar writer picks the bank from the track,
  not the pattern letter; drum only closes.

This supersedes the earlier "v1.3 hardware confirmed" claim, which was a no-op (its type test
matched only the drum).

Still open: chord records are capped at 8 notes per step; the patcher still offers Write to SD;
cards written by older builds can hold garbage sidecars (restore from a card backup).
