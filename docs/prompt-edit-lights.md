# New-session prompt: EDIT chord key lights (gc-modder)

Copy everything below into a fresh session.

---

Project: `/Users/andrewdesena/gc-modder` (Endorphin.es Ground Control v3.26 polyphony patcher + editor, STM32F4).

Read first, in this order: `docs/known-good.md`, `docs/next-session.md`, `docs/project-switch-preload.md`.
Then `git show 0ac0aad` and `git show f9431f2` (the pulled editlights work).

## State you are inheriting

- Hardware baseline `tag known-good-poly` = `71957a3`, 10-site bundle, `gc-v3.26_poly-v1.1.hex`,
  sha256 `226f824b…dad0454`. Confirmed on hardware: Project C / track 1 / pattern A plays C-E-G,
  save + power-cycle + reload keeps it, clear + save + power-cycle is silent.
- v1.3 (`mods/v1-poly-commit.json`, 12 sites, `gc-v3.26_poly-v1.3.hex`, sha256 `bfbc5327…6cc1a`)
  fixes live project switching. Two independent adversarial reviews returned SAFE TO FLASH; it is
  awaiting a hardware gate and is NOT yet in `index.html`. Do not disturb it. Build your work as a
  separate source file so it can be stacked on whichever base wins.
- `index.html` still serves v1.1. Never deploy an ungated bundle.

## Task

In STEP EDIT mode, when the current step holds a chord, light every key of that chord. Today only
the primary note lights, because stock lights exactly one key bit.

## VERIFIED FINDINGS (do not skip; a whole session was wasted contradicting these)

Verified against stock `testdata/gc326.hex` by decoding from real entry points (a linear capstone
sweep drifts on the interleaved literal pools and produces false "no reference" results):

- The edit state is NOT absolute. It lives in **per-track manager objects in CCM**:
  `0x10007A18 + idx*0x2FC` for idx 0..3 (also pointed to from `.data` at `0x20000450+4i`; init loop
  `0x0802001C`). `+0x2E1` = the object's track id and it is **0-based** (written by `0x0801F26C`
  from `0x0801F7F4/F7FC/F804/F80C` with 0..3); `+0x2DF` = that object's step cursor
  (`0x0801FE5C` ++, `0x0801FDB2/0x0801FE1E` --, `0x0801F354` reset). Track pointer from the id:
  table `0x080386D0` (`0x0801F2EC`).
- `0x20006000..0x20006400` is BSS (zeroed by the startup loop at `0x08030C50`). Anything that reads
  a field there gets 0 forever; a guard like `ldrb; subs #1; cmp #3; bhs` then bails every time and
  the cave becomes dead code. That is exactly what `mods/poly-editlights2.source.json` does.
- `0x08012008` is the **LED frame transmitter**, not an edit redraw: sole caller is the thunk
  `0x08012C12` (`bl 0x08015DAC` -> `b.w 0x08012008`), called unconditionally from the scheduler at
  `0x08033AB2` and `0x08033B52` every pass in every UI state. Its counters
  (`0x0801201C-0x0801203A`) are a 6-phase PWM index and a ~100 ms toggle.
- `0x20001E74` is a **transient masked frame**, recomputed each pass as
  `0x20001E7B[i] & ~0x20001E90[i]`, with `0x20001E7B = 0x20001E82 XOR render(...)`. The real key
  plane is **`0x20001E82`**; light keys through the stock LED API `0x0801227C(key, mode)` (which
  lands at `0x08011F50(buf, bit, 1)`), never by OR-ing the transmit copy.
- CONFIRMED good: a step's stored primary note is at `track + 0x194*[track+0x2E] + 3*N + 0x3C`
  (player `0x08021A5E-0x08021A6A`, parser `0x0802A12E-0x0802A152`), and 0x194 is the per-letter
  stride. The chord bank read (`0x1000B530 + i*0x880 + step*17`, count at +0, note at +1+2k) is also
  correct, bank index 0..2.

## What already exists (pulled, do not just revive)

`mods/poly-editlights.source.json` (cave `0x08048A00`), `mods/poly-editlights.json`,
`tools/test_poly_editlights.py`. It compiles and `tools/verify.py` passes, but it was pulled for two
real defects:

1. It reads the edited step index from `[track+0x2DF]`, which is stored pattern data (inside stored
   pattern B), not the input-manager's edit cursor. `tools/test_poly_editlights.py:31` writes that
   byte itself, so the test is self-fulfilling and proves nothing.
2. It ignores `active_letter * 0x194`, so even with a correct step index it would read the wrong
   letter's stored pattern.

Also suspect `0x08038374` (= table `0x08038370` + 4, i.e. entries 1..3) combined with the
`subs r5,#1; cmp r5,#3` guard: that maps the edited track onto the wrong track pointer. Verify the
whole index chain, do not assume.

## Addresses known from the earlier attempt (verify each yourself)

- LED bitfield buffer `0x20001E74`, 3 bytes, one bit per key; the cave must stay set-only (OR) so it
  can never clear a key stock lit.
- Note -> key-bit table `0x08048B00`; chord-note -> key-bit table `0x08048B18`.
- Track pointer table `0x08038370` (track1 `0x20013DEC`, track2 `0x200117C8`, track3 `0x2000F1A4`,
  drum `0x2000CB80`); melodic test is `[track+0x2D] == 1`; active letter at `[track+0x2E]`.
- Chord bank `0x1000B530 + trackIndex*0x880`, 17 bytes per step (count byte + up to 8 (note, offset)
  pairs), step count taken from the stored pattern.
- Stored pattern stride per letter: `0x194`.
- `0x2000CADA` is read by the cave and treated as a 1-based track selector. Confirm what actually
  writes it and whether that is the edited track.

## Required approach

1. Find the real edit-cursor source with capstone/REA: which code sets the step currently being
   edited in EDIT mode, and how the edited track is identified. Trace it from the input manager, not
   from the LED routine. Do not guess an offset.
2. Hook the real LED refresh caller that runs when a step's keys are drawn in EDIT mode, not the boot
   or playback path. Justify the hook site with the caller chain.
3. Set-only OR into `0x20001E74`; no SD I/O; no writes to anything outside that buffer; preserve
   r4-r11; keep the stack balanced and 8-byte aligned.
4. Build as `mods/poly-editlights2.source.json` and merge it onto the baseline with
   `./.venv/bin/python tools/build_v1.py <bundle> <out.hex>` so the shipped bundle stays provably
   the tested one.

## Tests (they must fail if the fix is broken)

Replace the self-fulfilling test. Required cases, driving the installed hook with the real caller
chain:

- Letter A and letter X, with the same step index, produce different chords (proves `0x194`
  scaling).
- Non-zero step indices, and two adjacent steps holding different chords.
- A single-note step still lights exactly that one key.
- Chords longer than 8 notes, and a step with no chord, must not overflow or light anything.
- Drum track lights nothing.
- Nothing outside `0x20001E74` changes.
- Re-run `./.venv/bin/python tools/verify.py <bundle>` and the node browser-engine check so the
  bundle matches what the patcher would build byte for byte.

## Gates

- Codex (`codex exec --model gpt-6.1-sol -c model_reasoning_effort="high" --sandbox read-only`) is
  the QA gate, but its quota has been blocking runs; if it fails with a usage limit, run an
  adversarial review as a delegated subagent against the same checklist and say so explicitly
  rather than calling it approved.
- Hardware gate: flash, then in STEP EDIT confirm every chord key lights for letters A and X, that
  non-chord keys stay dark, that a mono step still shows one key, and that playback is unchanged.
- Never commit or deploy a bundle that has not passed the hardware gate.

## Workflow rules

- Card protocol: back up `projectC` (pattern + sidecar) to `~/Downloads/gc-card-backups/`, `fsck`
  if filenames look wrong, 8.3-safe name (`GCV326P.HEX`), `sync`, then `diskutil unmount`.
- Never patch the shared string at `0x08036E50` (only the private newline at `0x08036E53`).
- Python with capstone + unicorn: `./.venv/bin/python`. Stock image `testdata/gc326.hex`.
- Report hardware results per step; on any regression, fall back to the known-good image and say
  which step failed.

---

## Review of the v2 attempt (poly-editlights2), 2026-11-15

`mods/poly-editlights2.source.json` + `tools/test_poly_editlights2.py` were built in another
session. 9/9 of their tests pass and `tools/verify.py mods/poly-editlights2.json` is clean, but the
work was NOT folded in. Reasons, with evidence:

**Correct and reusable (keep this part):**

- Hook site `0x08012068` is real and surgical. Stock bytes there are
  `ldr r1,=0x20001E74` / `ldr r0,=0x20002B2C` / `movs r2,#7` / `bl 0x080322C4` (the LED
  shift-out). The 4-byte `bl` displaces exactly those two LDRs, and the cave restores
  `r1 = 0x20001E74`, `r0 = 0x20002B2C` — the exact literals at `0x08012088` and `0x0801209C`.
- Cave math checks out: primary note at `track + letter*0x194 + step*3 + 0x3C`, table base
  `0x08038370`, bank `0x1000B530 + trackIdx*0x880 + step*17`, count capped at 8, set-only OR into
  `0x20001E74`, `push {r4-r7,lr}` / `pop` balanced, nothing written outside the LED buffer.

**Blocker 1 — the edit cursor is still a guess.** The cave reads track/step from
`0x20006000 + 0x2E1` / `+ 0x2DF`. The literal `0x20006000` has ZERO references anywhere in
`testdata/gc326.hex`. `tools/test_poly_editlights2.py` writes those two bytes itself (lines 82-87)
and calls the cave directly with `sb.call(CAVE)` (line 113) instead of entering through the
installed hook, so it reproduces the v1 self-fulfilling pattern and proves nothing about the source.

**Blocker 2 — no EDIT-mode gate.** The hook is in the generic LED shift-out, which also runs during
playback. Its only guard is "exactly one key bit lit". During playback with a mono note lit and a
valid manager track/step, it would OR the edited step's chord onto the playing note: stray keys
flashing while playing. Gate on the actual EDIT-mode flag, not just on the buffer contents.

**Blocker 3 — the hook installation is untested.** Every case calls the cave address directly, so
the 4-byte patch at `0x08012068` and the r0/r1 restoration are only verified by hand disassembly.

**What to do next:**

1. Trace the real edit cursor and the EDIT-mode flag from the input manager. The LED buffer has only
   two literals in the whole image (`0x08011FE0`, `0x08012088`), so the painter is reached obliquely
   — do not stop at the first plausible offset.
2. Add a test that enters through `0x08012068` and asserts playback-mode silence (single note lit,
   valid-looking manager state, no chord bits added).
3. Build on `mods/v1-poly-commit.json` (the v1.3 bundle, 12 sites) so the two fixes stack, and emit
   v1.4 rather than a standalone bundle.
