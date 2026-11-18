# EDIT chord entry investigation and contribution

> Historical research for engineering build IDs. Current public versions and user instructions are in [the documentation index](README.md). Sidecar workflows are abandoned.

2026-11-16. Evidence is local Capstone disassembly of `testdata/gc326.hex`
and controlled Unicorn execution of that image. Stock file SHA-256:
`c16f25740bdae0f3ca793d3747ad0e578a83dd5d2d4000923471c8716f317fa4`. This is not a hardware test.
Read `docs/known-good.md` for the shipped v1.9 state; its earlier corrected
claims are not assumptions for this investigation.

## Result

- Source overlay: `mods/poly-edit-entry-held.source.json`.
- Assembled overlay: `mods/poly-edit-entry-held.json`.
- Candidate combined bundle: `mods/v1-poly-entry-held.json`, v1.9 plus this overlay.
- Test: `tools/test_poly_edit_entry_held.py`.
- Hook: `0x080275C0`, replacing only the EDIT note/clear writer call.
- Cave: `0x08049C00..0x08049DA4` exclusive, 420 bytes.
- No change to `index.html`, shipped HEX files, or the current hardware-confirmed build.

The candidate bundle's generic description comes from `build_v1.py`; this document
and the overlay source describe its additional entry behavior. Hardware acceptance
is still required before shipping this candidate.

## Actual input chain

`0x0801227C` is an LED command API, not the input dispatcher. Its arguments
are a panel LED index and a display mode. Its branches call bit setter
`0x08011F50` over the LED state planes at `0x20001E82`, `0x20001E89`,
and `0x20001E90`.

Physical EDIT input travels through:

```text
UI task physical-event branch 0x080207D0
  0x080207D4 -> 0x0802D4A0 -> 0x08011424 (update held bitmap)
  0x080207E0 -> current page vtable slot 0 -> 0x0802E3FC
    0x0802E42A -> inner editor vtable +0x10 -> 0x08027B94
      EDIT branch -> 0x0802796C -> 0x080271AC
        0x080271BC -> 0x0801EC0C (key ID -> base MIDI note)
        0x08027288 -> 0x08026EAC (octave and note-on producer)
          0x08026EE2 -> 0x08019E10 -> 0x08019D98
            0x0802031C (input transpose and note-off mapping)
            0x080201D4 (per-track scale/root quantization)
            0x08019D40 (six-byte event ring)
0x08019CF0 drains ring -> 0x08019C84 (registered subscribers)
  wrapper 0x0802917C -> 0x080288F8 -> editor 0x08027564
    0x080275C0 -> 0x0802705C (three-byte pattern writer)
```

The test registers the EDIT wrapper through the real open command
`0x0802D4E8`. It runs the UI task branch and event-ring drain rather than
calling the cave directly. Constructors, page callbacks, input transforms,
quantizer, event bus, writer, and display-cache refresh all execute stock code.
The existing bench stubs debug UART and SPI transfer.

### Key to note instructions

`0x0801EC0C` copies the table at `0x08037364` and returns its signed byte for
key IDs 0..23. The decisive indexed load is `0x0801EC36`:

```asm
ldrsbls r0, [r3, #-0x18]
```

The table, in physical/event ID order, is:

```text
53 55 57 59 60 62 64 65 67 69 71 72 74 76
54 56 58 61 63 66 68 70 73 75
```

C60, E64, and G67 are key IDs 4, 6, and 8.

At `0x08026EB0`, stock loads signed octave from `0x2001CDE8`.
`0x08026EB6` computes `baseNote + 12*octave` with `smlabb`;
`0x08026EBA` saturates it to 0..127 with `usat #7`. The octave is latched
at `0x2001C117 + baseNote` by `0x08026ED2` and reused for note-off.

At the destination, `0x0802758C` loads the already processed event note from
`[r5+4]`, `0x0802758E` places it at `[sp+0xC]`, and
`0x080275BC` places event velocity `[r5+5]` at `[sp+0xD]`.
`[sp+0xE]` retains the old modifier byte. `r2=sp+0xC` is passed to
`0x080275C0`. No scale lookup happens inside the three-byte writer.

### Scale, root, and input transpose

Scale and root apply on **input**, before storing the step. Thus on-module
chord entry can respect the selected track's key, including the stock
track-1-follow scale setting. The verified setting source is per track in
ProjectSettings, not a separate per-pattern Scale/Root field on this path.

- Settings object: `0x2001BB38`, returned by `0x08024034`.
- Track scale/root: `+0x196/+0x197 + (trackIndex-1)*14`.
- SnapAlgo: 32-bit value at `+0xE0`.
- `0x080202C8 -> 0x08022E74(trackIndex, &scalePointer, &root)`.
- `0x080202D6 -> 0x08022DA0(note, scalePointer, SnapAlgo, root)`.
- A result of 255 rejects the note. Snap-up/down can merge different keys.

Before quantization, `0x0802031C` maps input transposition. Ten
`{raw,transposed}` pairs per track live at
`0x2000B614 + (trackIndex-1)*20`. New raw notes use signed delta
`[0x2000B5A9+trackIndex]` and saturate to 0..127 at `0x08020374`.
Existing raw notes retain their tracked mapping for consistent note-off.

The cave reconstructs held notes using the same key map, each key's latched
octave, the tracked input mapping (or current signed delta when absent), then
the real `0x08022E74` and `0x08022DA0`. It does not reprocess the entered
note, which has already gone through this chain.

Dynamic examples from the real input chain:

- Physical key0: 53 -> input delta +1 -> 54 -> C-major snap-up -> 55.
- D-major/root2: C60 snaps to C#61; E64 remains E64.
- Quantizer collisions produce one stored note; rejected held notes are skipped.

## Held keys

`0x20001C84` is the panel-button bitmap. The first three bytes cover the 24
keyboard keys. It is distinct from LED frame data.

`0x08011424(event*)` maintains it using `{eventType, keyID}`:

```asm
0801142C lsr.w r2, r3, #3       ; keyID / 8
08011430 and   r3, r3, #7       ; keyID % 8
; type 1, press:
08011438 ldrb  r4, [r5, r2]     ; r5 = 0x20001C84
0801143A lsls  r1, r3           ; type1 supplies the value 1
0801143C orrs  r1, r4
0801143E strb  r1, [r5, r2]
; type 2, release:
0801144C ldrb  r3, [r0, r2]     ; r0 = 0x20001C84
0801144E bic.w r3, r3, r1       ; r1 = 1 << bit
08011452 strb  r3, [r0, r2]
```

Type3 leaves the bitmap unchanged. `0x0801145C(keyID)` reads one bit.
The UI task updates it before dispatching the same physical event to the page,
so it already contains the new key when EDIT handles the press.

## Writer and other edit actions

The eight direct BL sites to `0x0802705C` have different meanings:

| Call site | Verified action |
| --- | --- |
| `0x080270FE` | Velocity edit: replaces stack record byte1 only |
| `0x08027492` | Modifier low-two-bit mode toggle |
| `0x080275C0` | EDIT note-on entry, including sentinel-note clear |
| `0x080276E2` | Record-mode previous-step low-two-bit update |
| `0x0802773A` | Event type1/subtype0 changes low-two-bit modifier |
| `0x080277D4` | Event type1/subtype1 adds signed delta to a step note |
| `0x08027A82` | Physical key0x27 toggles modifier low-two-bit value1 |
| `0x08027ABA` | Physical key0x26 toggles modifier bit2; another branch also rejoins this call |

The writer stores note/velocity with `strh` at `0x0802706A`, modifier with
`strb` at `0x0802706E`, and dirty=1 at `[pattern+4]` at `0x08027072`.
Correction to the brief: an index **greater than** 128 loops forever at
`0x08027060`; it does not return. Stock accepts index128, which is outside
the 128-step sidecar. The new sidecar code guards `step < 128`.

Record-mode entry also has inline stores at `0x08027672` and
`0x08027758`; this contribution deliberately targets EDIT note entry only.
The separate event-delta site `0x080277D4` is unchanged and can still leave
sidecars stale. It is not the pattern transpose routine discussed below.

## Chord behavior and limits

The cave validates melodic table identity, type0, active letter0..23, matching
pattern pointer, EDIT mode, and step0..127. Bank index equals table index1..3.
It stages a complete 17-byte record on the stack, then publishes its data and
count. It preserves r0-r12/lr around its work and tail-calls the original
writer with the original arguments, changing only the incoming note byte
to the minimum retained note. Stack use is 104 bytes before stock helpers;
SP remains aligned to eight bytes at every helper call from the cave.

The entered note is retained first with its event velocity. Other currently
held physical notes use the keyboard's stock velocity127. Rebuilding from the
held set removes duplicates, including snapping collisions, and caps at eight.
At capacity the entered note has priority, followed by held keys in physical
ID order. Pattern velocity and modifier remain stock values. There is no SD I/O.

Releases do not erase the stored chord. After all keys are released, a new
entry gesture replaces the chord. This is held-key entry, not an indefinite
append of unrelated taps or a timed accumulation window. The held bitmap is
sampled when the processed note event reaches the writer; queued inputs do
not carry a historical bitmap snapshot.

### Clear

`0x080271DC..0x080271E6` compares a pressed key's raw octave-adjusted note
against the displayed primary. A match calls `0x08026E34`, which emits
note-on with note128, velocity127. `0x08019C66` classifies this as a special
event, bypassing transpose/scale. It reaches `0x080275C0` as usual.
The cave zeros all 17 sidecar bytes, then lets stock store the sentinel and
set dirty. This preserves stock's primary-key re-press clear gesture.

That clear comparison occurs before input transpose/scale. Its dependence
on an unprocessed key note is stock behavior; this contribution does not
change it. It also does not add sidecar clearing to whole-pattern clear or
other edit operations.

## Pattern transpose recommendation

Correction: `0x08028194` takes `r1=trackIndex`, `r2=signedDelta`; r0 is not
the track selector. It saves delta in r5. Octave callers are
`0x0802DF2A` (-12) and `0x0802DF50` (+12). `0x0802DF4E` is the +12 MOV.

The clean success hook is **`0x08028224`**, replacing and replaying:

```asm
strh.w r4, [r12, #0x38]
```

At that point r4=1, r5=delta, and r12 is
`track + letter*0x194`, without the pattern's +0x34. The mono loop has
succeeded; the cave can resolve the same track/bank and shift the 128 records
without relying on caller-specific arguments or recomputing the delta.
Hooking after the function returns loses this useful internal state.

A success-only hook is insufficient for correct bounds handling. Stock's
preflight at `0x080281DA..0x080281F6` scans only pattern note bytes, and
`0x080281F8..0x08028202` permits final notes1..126. The primary is now the
lowest chord note, so upper extras can overflow while the mono check passes.
Extend the preflight with chord extrema before any mono writes, then apply
the delta to all retained notes at the success hook. Reject the whole operation
on an invalid chord result. Clamping extras independently changes intervals
and can create duplicate notes.

Also cover the held-manager branch:
`0x080281B2 -> 0x0801F328 -> 0x0801F20C`; it bypasses `0x08028224`.
The older experimental `mods/poly-transpose.source.json` references a cache
helper absent from v1.9 and is not a drop-in solution. No transpose patch is
included in this contribution.

## Validation

```sh
./.venv/bin/python tools/asm.py mods/poly-edit-entry-held.source.json mods/poly-edit-entry-held.json
./.venv/bin/python tools/test_poly_edit_entry_held.py
./.venv/bin/python tools/verify.py mods/poly-edit-entry-held.json
GC_BASE=mods/v1-poly-dub.json GC_VERSION=1.10 ./.venv/bin/python tools/build_v1.py mods/v1-poly-entry-held.json mods/poly-edit-entry-held.source.json
./.venv/bin/python tools/verify.py mods/v1-poly-entry-held.json
```

The caller-chain test includes a stock negative control, tracks1..3, lettersA/X,
step127, nonzero modifiers, held/released/repeated keys, cap8, scale/root,
input transpose, octave latching, clear, register/stack preservation, writes
restricted to the selected record/pattern/stack, and real v1.9 fan-out into
the actual scheduler ring. A deliberate no-op cave mutation is detected by the chord assertion. The same
tests also confirm the existing EDIT lights display the newly entered chord.

Hardware has not been exercised. Before shipping, test held chord entry and
clear on all three tracks, playback/lights, save and cold reload, and project
switching. The active bank still follows the existing v1.9 architecture.
