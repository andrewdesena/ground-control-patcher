# Chord lifecycle: verified state and open work

> Historical research for engineering build IDs. Current public versions and user instructions are in [the documentation index](README.md). Sidecar workflows are abandoned.

2026-11-16. Everything below was verified against `testdata/gc326.hex` by
disassembly or by executing the installed hooks. Claims that are inherited
from a reviewer are labelled as such.

## Ground truth settled today

**Pattern letters are `A..T,V,W,Y,Z`.** 24 slots, no U, no X. Table
`0x08038310` is 24 pointers to one-character strings; dereferencing them yields
`ABCDEFGHIJKLMNOPQRSTVWYZ`. Verified by reading the table directly.

**`track+0x2E` is a 0-based letter index, not ASCII.** Every consumer multiplies
it by the `0x194` block stride (`0x080281C4`, `0x0801F54C`, `0x08020814`).
`0x194 * 0x41` would land inside the next track object, so ASCII is impossible.

**The save path's caller frame byte at `sp+0xF` is the pattern letter as ASCII**
(table lookup, not from `+0x2E`). The old v1.9 cave recovered the track with
`pattern - 0x34 - (ascii - 0x41) * 0x194`, which is only correct for letter A.
Every other letter shifted the pointer into the wrong track, and the save then
bailed. Chords silently did not save except on letter A. The hardware tests
passed because they used letter A.

**Correct recovery is a scan, not arithmetic.** Given the block pointer, test
`track + 0x34 + 0x194*i` for `i` in 0..23 across all four tracks and accept only
an exact match. Implemented by the resolver at `0x0804A000`.

## Ownership model

- Four words at `0x1000D740`, one per bank index, holding `letter_index + 1`.
  Zero means unknown. There is no letter whose value plus one is zero, so the
  unknown state cannot collide with a real letter.
- Reset clears the words because the CCM clear bound at flash `0x08030C9C` was
  extended from `0x1000B52C` to `0x1000D750`. That runs in the reset handler
  before any hook, so nothing depends on initialization order.
- The owner is written only after all 2176 bank bytes are in place
  (`0x0804A100`, owner store after the copy loop). A race therefore produces a
  stale-but-true owner, and the worst case is a skipped save, never a wrong one.
- Save writes only when `owner[bank] == letter + 1`, and the filename letter
  comes from the table rather than from ASCII arithmetic.

## Memory map, checked

Cave and buffer placement in the v1.13 candidate, all checked against each
other and against the v1.9 caves:

| use | range | status |
|---|---|---|
| v1.9 caves | 0x08047400, 0x08047600, 0x08047800, 0x08047A00, 0x08047E00, 0x08048000, 0x08049000 | untouched extents |
| transpose cave | 0x08048C00 to 0x08048CE8 | clear |
| edit entry cave | 0x08049C00 to 0x08049EA8 | clear |
| resolver | 0x0804A000 | clear |
| reader and publisher | 0x0804A100 | clear |
| empty-save clear | 0x0804A300 | clear |
| mutation caves | 0x0804B000, 0x0804B100, 0x0804B180, 0x0804B200 | clear |
| chord banks | 0x1000B530 to 0x1000D730 | stock |
| owners | 0x1000D740 to 0x1000D750 | free, no literal reference in stock above 0x1000B52C |
| name and staging buffers | 0x1000E000, 0x1000E300, 0x1000E400, 0x1000E500 to 0x1000ED80 | free by the same scan |

Method note: an earlier scan that treated every 4-byte word as a possible
literal produced a false collision at `0x1000E9D0`. Only words actually reached
by a PC-relative load count. Redone properly, stock has no literal anywhere
above `0x1000B52C`.

## Nudge

The nudge control is the whole-pattern shift at `0x0802A0C8` (no direct BL
callers, so it is reached through a page vtable). It locks at `0x080232A0`, takes
the current track at `0x08023320`, and rejects the drum by type at `0x0802A0DE`.
The rotate store at `0x0802A126` is hooked, so records rotate with the steps in
both directions. Covered by `tools/test_poly_lifecycle_mutations.py` for lengths
1, 2, 16 and 128 with a mutation control.

## Open work, in priority order

1. **Generator modes 1 and 3: FIXED 2026-11-16** (`mods/poly-gen-modes.source.json`,
   caves at 0x0804B300 and 0x0804B400, hooks at 0x0802F520 and 0x0802F3D0).
   Mode 3 now moves the record by 0xc with the note, drops voices that would
   leave range and zeroes the tail; mode 1 zeroes the step's record count. Both
   resolve the track by scanning the block pointer, and both leave the drum
   alone. Nine checks in `tools/test_poly_gen_modes.py` including a mutation
   control that leaves the record stale. Original note follows.

   **Was:** The routine at `0x0802F264` takes
   a mode at `[r1]` and dispatches four ways at `0x0802F284`. Only the mode-0
   step loop is hooked. Mode 1 at `0x0802F3D0` writes `strb.w sb,[r7,#8]` and
   `strb.w sl,[r7,#9]`, emptying a step, and mode 3 at `0x0802F520` does
   `adds r7,#0xc` then `strb r7,[r5,#8]`, moving a note up an octave. Neither
   touches the chord record, so mode 3 collapses a chorded step to mono and
   mode 1 leaves a record on an empty step. Reachability from the UI is not
   proven yet. Both need hooks that adjust the record the same way the step
   moved.
2. **Test fixtures.** DONE on 2026-11-16: added
   `tools/test_poly_save_letter.py`, which drives the real writer `0x0801C450`
   with FatFS stubbed and asserts on the names passed to `f_open`. It proves the
   sidecar is named for the pattern letter on A, E, V, W and Z, and that a save
   for a letter the bank does not hold writes the pattern file but skips the
   sidecar. The call convention it depends on, verified in the disassembly:
   `r1` is the block pointer and `r2` is the letter index into the 24 entry
   table at `0x08038310`, not a track index. Earlier audit work that assumed a
   track index there was wrong.

   Fixed earlier the same day: the drum-isolation case marked slot 3
   as the drum; it now uses slot 0, which is what table `0x08038370` holds.
   Mutation controls were added for the whole-pattern clear and the step-fill
   clear, matching the one rotation already had. Still open: the save test
   writes the very frame byte the code is supposed to read, so it cannot detect
   a wrong-letter save. It has to drive `0x0801C450` with stubs for the FatFS
   and helper calls and assert on the name passed to `f_open`.
3. **Publication cost.** DONE on 2026-11-16. The publisher at `0x0804A100` used
   to read into a 2176 byte staging buffer at `0x1000E500` and then copy it into
   the bank word by word: 544 word moves per publish, plus 2176 bytes of CCM
   held forever. It now zeroes the bank and reads straight into it, the way the
   hardware confirmed v1.9 cave did. A short read, read error or close error
   falls through to the zero fill and then records ownership, so an empty bank
   is always the honest empty representation of that letter. Only a failed open
   leaves bank and owner untouched. `tools/test_poly_ownership_direct.py` covers
   all six outcomes. Original note follows.

   **Was:** The reader stages into `0x1000E500` and
   then copies to the bank. Reading straight into the bank after zeroing, as
   v1.9 did and hardware confirmed, removes a buffer and one full read.
4. **Untested: two tracks switching letters at once, and save racing a publish
   between the owner read and `f_write`.** The second is the reason a staging
   copy exists; if item 3 removes it, that race has to be closed another way,
   such as copying under the lock the cave already takes.

## Current candidate

v1.17, 38 sites, `mods/v1-poly-v117.json`, `gc-v3.26_poly-v1.17.hex`,
sha256 `7dfbdb9b39680589154a5ecf00e5eb6571aab0cc94fdb775fc2e4fa8be2bc423`.
Adds toggle chord entry on top of v1.16's save sanitiser. Twelve suites green.

Root cause of the hardware resurrection, found from the card on 2026-11-16:
`polyA` held records exactly 12 semitones above their pattern notes at two steps,
and `polyE` had never been written. The fan-out only fires when the played note
appears in the record, so those steps could not sound; the step looked chorded in
edit mode and played as one note. The save sanitiser now refuses to persist a
record that cannot play.

## Previous candidate

v1.15, 37 sites, `mods/v1-poly-v115.json`, `gc-v3.26_poly-v1.15.hex`,
sha256 `45791d2d321d42c278166bed3087cfdd171fc33ad3a0f684223dca315f2b0b3f`.
All 15 v1.9 patches byte identical except the three caves deliberately rewritten
for the ownership model (0x08047A00, 0x08047E00, 0x08049000). No patch spans
overlap. Every suite green: save letter, ownership direct, generator modes,
lifecycle mutations, save track, edit entry, transpose, track 3, commit reload,
edit lights.

## Not verified by anyone yet

A full-boot hardware run, and an independent audit of v1.15. No candidate has
been flashed since v1.9.
