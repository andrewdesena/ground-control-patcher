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

## Open question for layer 2

The exact site that copies a staged note into the step array is not yet pinned from static
reading. `0x0801FCB8` stages `+0x2f4/f5/f6` and calls the sort, but the byte that lands in the
step is written elsewhere. Before wiring capture into the commit path, confirm with a 60-second
MIDI capture (GC as clock master) that the held-note list is populated before commit, or pin the
store site in the disassembly. Do not guess this site.
