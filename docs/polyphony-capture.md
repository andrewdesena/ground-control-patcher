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

## Layer 2: per-step note array (built + tested)

`mods/poly-steps.source.json` holds the step-array primitives (all position-independent, capped at
**CAP = 16** notes per step):

| routine | contract |
|---------|----------|
| `poly_merge(dst, note, vel)` | add note, or update its velocity if already present (dedupe by note); drops silently at cap. Used per note-on. |
| `poly_remove(dst, note)` | remove a note on note-off (swap-with-last, decrement). |
| `poly_count(dst)` | return current count. |

Step layout: `byte 0 = count`, then entries `[note, vel]` at `dst + 1 + 2*i`.

`tools/test_polysteps.py` assembles these and **executes** them in Unicorn: chord C-E-G, velocity
update, 20-note→16 clamp, remove-middle (swap), remove-absent, count, plus a **5-CC controller
bank** (add, sweep-update, release-remove). 14/14 pass. The merge/remove primitives are generic
(key, value) accumulators, so the exact same code drives a per-step CC bank — no separate routine.

```
./.venv/bin/python tools/test_polysteps.py     # PASS (14/14)
```

## Layer 3: steps2 writer / reader (built + tested)

New project key `steps2` (ours): each step is
`{ "modifier": m, "notes": [[midi,vel],...], "cc": [[ccnum,val],...] }`. Notes are integer MIDI
numbers; **CC is a list**, so one step stores a whole controller bank (mod bus, breath, cutoffs,
etc.), capped at 16 each. This is what lets an external controller's CCs be stored per step and
later passed to MIDI out per track.

`tools/project_format.py` is the reference codec:
- `project_with_steps2(base, steps)` writes `steps2` **and** the legacy `steps` (single-note,
  note-name strings) + `ratchets`, so old firmware still loads the project.
- `decode(project)` prefers `steps2`, falls back to legacy `steps` for old projects.

Legacy schema grounded from firmware strings (`"step_limit"`, `"steps"`, `"ratchets"`,
`"note"`/`"velocity"`/`"modifier"`, note names as `%s`).

`tools/test_project_format.py`: note-name roundtrip (12..107), steps2 roundtrip, multi-CC
preservation, empty steps, legacy emit + fallback, steps2 precedence, capacity caps. 20/20 pass.

```
python3 tools/test_project_format.py    # PASS (20/20)
```

## Record-path wiring (built + tested, experimental)

`mods/poly-record.source.json` hooks the record site **additively**. It replaces the 4 bytes at
`0x08025814` (`strb r1,[r3,#0x1d]` + `b 0x80257f8`) with `b.w 0x08047400`; the cave:

1. does the **original** step store verbatim (playback data unchanged → device-safe), then
2. computes `dst = 0x1000B530 + track*0x880 + step*17` (track from `0x080232F0`, step from
   `[r4+5]` — confirmed by the writer at `0x08026760` that uses stride 10), and
3. calls an embedded `poly_merge(dst, note, 100)` (CAP 8; clips a stale count>8 to 0, so no boot
   init is needed).

Layout: `byte0 = count (<=8)`, entries `[note,vel]` at `+1+2*i`, per-track stride `0x880` (128*17),
3 melodic tracks from `0x1000B530`.

`tools/test_polyrecord.py` loads the **whole firmware** into Unicorn, seeds the pattern-manager +
active-track globals, and calls the hook at the exact register state: **9/9 pass** (original store,
r4/r5 preserved, return to continuation, capture, chord, dedupe, stale-count clip).

Combined image `gc-modded-exp.hex` = clock patch + poly-record hook (222 bytes changed,
zero collateral): `python3 tools/apply.py mods/combined-exp.json gc-modded-exp.hex`.

**Not yet wired (next layers):** playback fan-out (so chords actually sound), `steps2` serializer
on SD save, per-step CC capture, and real velocity (currently stored as 100). Until playback is
wired the captured poly data is inert — the hook changes nothing you can hear, so flashing is low
risk for testing the store path.

## Playback map (for the fan-out layer)

- MIDI-out send queue push: `0x08019840`.
- Primitives: note-on `0x8019A2A` (status 0x90), note-off `0x8019A5E` (0x80), note-pair
  `0x8019A92` (builds on then off), CC `0x8019ACE` (0xB0) — all push to the queue above.
- Playback is **not** a simple step loop. A step feeds a per-track **arp/ratchet player**
  `0x80208F6` (loops `0x8019A92` calls stepping the note) and a **gate/trigger player**
  `0x8021748`. Channel/scale come from `[track+0x178]` / `[track+0x1f]`.
- Step processor that reads the step note and calls the arp player: `0x8020A84` calls
  `0x80208F6` at `0x8020C72`.
- **Fan-out hook point** = inject extra `0x8019A92` sends per poly note at the step→player bridge,
  with matching channel + gate + scheduled note-offs. BLOCKED until the player argument contract
  (which register is note/track/gate at `0x8020C72`) is pinned, or confirmed by a 60 s MIDI capture.
  Do not guess this — a wrong guess = stuck notes / wrong channel on real hardware.

### Resolved: live-input vs sequencer are DIFFERENT paths

- `0x8019580` → `0x802063C` → `0x8022054` is **live MIDI INPUT** (reads hardware receive queue
  `0x200030E4/0x20003120/...`). Do NOT patch here — it's MIDI-thru, not sequencer playback.
- The **sequencer** plays each track via a **vtable-dispatched per-track tick `0x8020CE4(track,
  note)`** (no `bl` callers — invoked through a function-pointer/vtable), which calls
  `0x8020A84(track, note)` → arp player `0x80208F6(track, note, …)`. Play position/timing live in
  the track object: pattern base `[track+0x17c]`, timing `[+0x184]`, counters `[+0x6c]`/`[+0x68]`,
  flags `[+0x18d]`/`[+0x18e]`.
- Players emit via `0x8019A92` (note-pair) with per-track channel from `[track+0x1f]`.

### Status: fan-out needs dynamic tracing (static RE exhausted)

- `0x802B548` = pattern/chain advancer: indexes a 24-entry table, wraps patterns, writes
  `[track+5]`. Steps within a pattern advance elsewhere by timing.
- Melodic player `0x8021A14` and x0x player `0x8020A84` are dispatched as per-track **vtable ticks**
  (`0x8021D04` at vtable slot `0x08038790`; `0x8020CE4` at `0x080386FC`) with the **note already
  computed in `r1`**.
- The step→note→voice computation is inside the RTOS task scheduler (object/vtable dispatch). There
  is no single `bl` site to splice fan-out safely, and the per-track step cursor field is not
  statically evident. Guessing it risks stuck notes / wrong channels on hardware.
- **Recommended next technique:** a dynamic trace — run the firmware under an emulator (or the
  REA debugger) with clock/timer emulation, hook `0x8019A92` (note emit), and observe which caller /
  registers / track-object field drive each step's note. That pins the cursor without guessing.
  Hardware MIDI capture is the other route.

Backlog (Drew's asks, later layers)

- **CC values per step**: DONE in the `steps2` format + emulator-proven bank. Remaining work is the
  firmware wiring: capture live `0xB0` into the per-step CC array on the record path, and fan CC out
  on playback / MIDI out per track.
- **External CV inputs**: improve response / mapping (separate workstream).
- **Pattern generators (added in official v3)**: revisit musicality; current output is very
  EDM/wacky. Separate from polyphony.
