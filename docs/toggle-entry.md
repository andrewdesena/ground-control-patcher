# One-at-a-time chord entry (toggle)

> Historical research for engineering build IDs. Current public versions and user instructions are in [the documentation index](README.md). Sidecar workflows are abandoned.

Built 2026-11-16, in v1.17. Overlay `mods/poly-entry-toggle.source.json`, wrapper
cave at 0x0804B500, hook replaces the direct call at 0x080275C0. Eleven checks in
`tools/test_poly_entry_toggle.py`, including a control that calls the entry cave
directly and shows it does not remove a note, so removal is provably the
wrapper's doing. Not yet on hardware.

## Why

Today the entry cave at `0x08049C00` builds a step's chord from the keys held at
the moment of the press. A chord therefore has to be pressed all at once, and
every note has to be reachable on the current two octaves. Drew wants to add
notes one press at a time, including notes an octave away from the ones already
recorded.

## Design: wrap, do not rewrite

The existing cave is 420 bytes plus a 248 byte helper block and it is hardware
proven. Do not modify its internals. Put a wrapper in front of it at the same
hook site, `0x080275C0`, and let the wrapper decide whether this press is an
addition or a removal.

Call convention at that site, established by disassembly: `r0` is the pattern
block pointer, `r1` is the step index, `r2` points at a three byte record
`{note, velocity, modifier}` that stock has already built for this press.

Wrapper logic:

1. Resolve the bank with `0x0804A000` (block pointer in, bank and slot and
   letter index out). If it returns zero the track is the drum or unknown: fall
   straight through to the existing cave.
2. Read the record for this step: `bank + step*17`, count byte then pairs at
   `1+2i` and `2+2i`.
3. If the count is zero or greater than 8, fall through: nothing to toggle.
4. Search the declared pairs for the pressed note.
   - **Not found**: fall through to the existing cave. It already appends and
     deduplicates, so addition needs no new code.
   - **Found**: this press removes the note. Compact the pairs, skipping the
     matched one, zero the tail, and write the new count.
5. After a removal, the step's note byte must be the lowest remaining note, or
   `0x80` when the record is now empty. The fan-out only fires when the played
   note appears in the record, so leaving the old primary behind would silence
   the step.
6. Return without calling the existing cave, so the note is not re-added.

## The eight note cap

The record is 17 bytes: a count byte plus eight note/velocity pairs. The stock
append helper at `0x08049DCA` does `cmp r2,#8` and `bhs`, so a ninth note is
silently dropped. The dangerous part is that the step's own note could still move
to the pressed key, leaving the played note absent from the record; the fan-out
then cannot match it and the step collapses to a single note. The sanitiser
would later drop the dead record on save, so a ninth note destroyed the chord
rather than extending it.

The wrapper now refuses the press when the record is full: nothing is written,
the chord and its primary note stay exactly as they were. If a swap policy is
preferred later (newest replaces the highest) that is a three line change here.

## Test plan

Drive the wrapper with a prepared record and a synthetic press record:

- press a note already present in a three note chord: count drops to two, the
  removed note is gone, the step note becomes the new lowest
- press the only remaining note: count zero, step note `0x80`, record silent
- press a note not present: the existing cave runs and the chord grows
- press on a step with no record: the existing cave creates a single note
- drum: nothing happens
- mutation control: with the wrapper's hook restored to stock bytes, pressing an
  existing note must add a duplicate rather than remove it

## Why this is its own build

It changes what a key press means, on the one code path that every edit goes
through. Getting it wrong breaks entry entirely, which is worse than entry
requiring a simultaneous press. It needs its own tests and its own hardware run,
so it should not ride along with the save sanitiser that fixes data corruption.
