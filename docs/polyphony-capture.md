# Polyphony, layer 1: capture

Goal: record all simultaneously-held notes per step for tracks 1-3 instead of collapsing to
the last note. Built in layers (capture -> new step array -> `steps2` writer -> reader
fallback -> playback fan-out), each with its own test.

## Confirmed data structures (stock v3.26, from disassembly)

The per-track state struct pointer is passed as `r0` throughout the `0x0801F4xx-0x0801FExx`
cluster. Fields used by the note path:

| offset       | meaning |
|--------------|---------|
| `+0x000`     | held-note list: 24 slots x 12 bytes = 0x120 |
| `+0x008+12*i`| slot i note byte (within slot: `+0` counter dword, `+4` msg dword, `+8` note, `+9` velocity) |
| `+0x120`     | held-note **count** (byte, 0..24) |
| `+0x124`     | running dword counter for slots |
| `+0x128`     | snapshot copy of the whole 0x120 list (memcpy at commit) |
| `+0x2f4`     | current track index |
| `+0x2f5`     | **last** recorded note (signed byte) |
| `+0x2f6`     | note-pending/vel staging (byte) |
| `+0x2f7`     | note-on flag |
| `+0x2df`     | secondary count used by the `0x0801FD34` handler |

Held-note list helpers:

| addr         | role |
|--------------|------|
| `0x0801F14C` | add held note (writes slot at `track+12*count`, note at `+8`, vel at `+9`, count++) |
| `0x0801F1E8` | remove held note |
| `0x0801F050` | lookup note in list, returns match index |
| `0x0801F118` | clear list (count and dword reset) |
| `0x0801FC0C` | insertion-sort the held list over 12-byte slots (by timestamp) |
| `0x0801FC70` | per-track dispatch into the sort above |

## Where chords are lost

The recorder stages a single note in `+0x2f5/+0x2f6` (`0x0801F32C` does `strb [r0,#0x2f5]` /
`strb [r0,#0x2f6]`). Even though the held-note **list** correctly holds every pressed key, the
step commit only ever reads that one byte. Steps themselves are a 10-byte stride at
`pattern+0x1D` and the serializer (`0x0801C194`) emits single-byte note arrays, so a step has
room for exactly one note today.

## Layer 1 deliverable: the capture routine

`mods/poly-capture.source.json` builds a 48-byte, position-independent routine:

```
capture(track_ptr, dest_ptr) -> count
```

It reads `count = [track+0x120]` (clamped to 24), walks each 12-byte slot, and writes
`[note, velocity]` pairs to `dest`. It does not touch the firmware yet; it is the primitive the
commit-path patch (next layer) will call instead of the single-note store.

### Test (real execution, no hardware)

`tools/test_capture.py` assembles the routine, loads it into the Unicorn CPU emulator, builds a
synthetic track struct, **calls the routine**, and asserts the destination holds every held
note. Cases: empty, single note, 3-note chord, 5-note cluster, full 24-note cluster, and a
corrupt count of 200 (must clamp to 24).

```
./.venv/bin/python tools/test_capture.py    # PASS (6/6)
```

The `.venv` is created by `python3 -m venv .venv && ./.venv/bin/pip install unicorn pyelftools capstone`.
It is gitignored.

## Step-store site (PINNED)

The single-note store into the step array is `0x080257D8`. Register/field map at that site:

```
r4 = [pc]          ; pattern-manager struct
r5 = [pc]          ; another global
r3 = [r4, #0xc]    ; pattern/step base pointer
r6 = [r5, #0x5c]   ; record-armed flag
r2 = [r4, #0x10]   ; current step offset
r0 = [r4, #0x5]    ; track/row index
stride = 0xa (10)
r3 = r3 + 10*r0
if (!armed) strb note, [r3, #0x1c]   ; idle: staging byte
else        strb note, [r3 + step + 0x1d]   ; armed: committed step note
```

Entered with `r0` = the note to write. It is installed as a callback by the MIDI handler
`0x080263B8` (the handler stages the incoming note at `step+0x1c`).

**Why chords collapse:** the step note is a single byte at `+0x1d`. Each note-on in a chord
re-enters and overwrites that same byte, so only the last note survives. The fix is to
accumulate every held note for the step instead of overwriting one byte (this is layer 2: the new
step array).

## Open nuance for wiring (layer 2)

At `0x080257D8` the context does **not** carry the track struct pointer directly (it uses a
separate pattern-manager global; `r0` on entry is only the note). The held-note list lives at the
*track* struct `+0x120`. Resolve it like the MIDI handler does:

```
idx         = active track index  via 0x080232F0   (byte global)
track_ptr   = *(uint32_t *)(0x20000450 + idx*4)     (track-struct pointer table in RAM)
```

So a layer-2 patch at the store site can fetch `track_ptr`, call `capture(track_ptr, dest)`, and
accumulate the whole chord. Confirm the RAM table `0x20000450` holds the same track structs the
`0x0801F4xx` note helpers operate on before shipping.
