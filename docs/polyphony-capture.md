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

### Stock-accurate gate — poly-gate (supersedes the fixed-duration fan-out)

- `mods/poly-gate.source.json` wraps the real emitter `0x8021748`: at entry it has
  `r0=obj, r1=time, r2=step_ptr, r3=gate`, reads `poly[track][step]` (step=[obj+0x3c]), and replays
  every non-primary note by calling `0x8021748` again with the SAME `r1`/`r3` and a temp step-record.
  Result: extras get identical stock time/gate (no fixed 100). Reentrancy guard 0x1000FE00.
- `tools/test_gate.py` PASS: mono, triad(gate50), 7th(gate80), 8-note(gate33) all call the emitter
  for exactly the non-primary notes with the passed-through gate. Use poly-gate INSTEAD of
  poly-fanout (both would double-emit).

### Web tool + SD over USB

- `index.html` now: pick stock .hex -> choose "Polyphony v1" -> build in-browser -> **Install to GC**
  writes the patched firmware onto the mounted SD card via the File System Access API (hold PROJ 5s
  for USB mass-storage, then power-cycle to flash). Download .hex is fallback only.
- Same panel connects the GC SD card to **read/open/save project .json files** directly (editor).
- Requires Chrome/Edge over https or localhost (File System Access API; not available on file://).

- Hook `0x08021A6E` (inside player `0x8021A14`, r0=step, r4=obj, r8=parent) -> cave `0x08047600`.
- Cave reproduces the original `strb.w r0,[r4,#0x3c]`, then reads `poly[track][step]` from CCM
  `0x1000B530` (track=channel-1; `track*0x880 + step*17`; byte0=count, then `[note,vel]`), and
  emits every note EXCEPT the primary (`sl`) through the self-contained pair `0x8019A92`.
- `tools/test_fanout.py`: PASS for mono (no extras), C-major triad, 7th chord ch2 step5, and an
  8-note cluster at step 127 (correct note/vel/channel, primary skipped).
- **Real velocity:** `mods/poly-velhook.source.json` hooks the note-on add-to-held-list `0x801F1E8`
  (event note@+4, vel@+5) and stashes `vel_by_note[note]` at CCM `0x1000FD00`. The capture cave
  reads it (fallback 100). `tools/test_velhook.py` and `tools/test_polyrecord.py` PASS.
- `gc-poly-vel.hex` = clock + capture(real vel) + velhook + fan-out, 392 bytes / 8 sites,
  `verify.py` zero collateral, on-disk disassembly verified. **EXPERIMENTAL / UNFLASHED.**
- v1 caveats: assumed default melodic channels 1..3 (track=channel-1); extra-note duration fixed at
  100 ticks (tune on hardware). Only projects RECORDED on this firmware have poly data; stock
  projects stay mono.

Backlog (Drew's asks, later layers)

### B RESULT — the step cursor is FOUND (dynamically confirmed)

The melodic player `0x8021A14(voice_obj, note)` **reads the step note from the pattern itself**:
- `step = 0x80216C8(voice_obj+0xc)` — and `0x80216C8` reads a position counter at
  `RAM 0x2000B594 + channel + 0xa` and returns `counter MOD patternLength` (length from a vtable
  call). Dynamically confirmed: counter 0/5/21/32 -> step 0/5/5/0 with length 16.
- It stores `step` at `[voice_obj+0x3c]`, then `[voice_obj+0x38] = pattern + 0x3c + 3*step`
  (pointer to that step's note byte), and reads `note = *[voice_obj+0x38]`.
- `pattern` = `[voice_obj+8]`; channel = `[[voice_obj+8]+0x1f]`; voice idx = `[[voice_obj+8]+0x2e]`.

**Fan-out hook (now unblocked):** at `0x8021A66` (just after `[obj+0x38]` is set, `r0`=step),
we have `track`/`channel` from `[obj+8]` and `step` in hand. Read `poly[track][step]` and, for each
extra note, emit through the pair `0x8019A92` (note is in **r3**, velocity r0) — reusing the exact
player path so gate/note-off/channel stay correct. This is the final piece to build.

### Emitter contract (learned the hard way — matters for the splice)

The per-note emitter `0x8021748(obj, time, ?, vel)` is the **arp/voice handler**, not a plain note
sender. Primitives put **channel, note, velocity, and time on the STACK**, not in plain registers:
- note-on `0x8019A2A`: note=`r2`, vel=`r0`, channel via stack/port.
- pair `0x8019A92`: `r1`=time, `r2`=duration, note/vel/channel from stack (`[sp]`,`[sp+4]`,`[sp+8]`).
- note-off `0x8019A5E`: `r1`=time, note from stack, channel `[sp+4]`.
- channel per track = `[[obj+8]+0x1f]`; gate is scaled (`udiv`) from track params `[..+0x2a]`.
It is a **single monophonic voice per track** (one active-note slot). So emitting extra notes by
calling the emitter N times will fight that one slot -> stuck notes or voice-steal. A correct
chord fan-out must either (a) emit raw note-ons at step start + matched note-offs at the track's
gate-off time (needs the gate-timer hook + per-track pending list), or (b) add real multi-voice
allocation. Both require **executing** the player to validate time/channel/gate — which the current
Unicorn build cannot (it fails to decode the player's VFP/FPU instructions; `ctl_set_cpu_model`
rejects Cortex-M4/M7 here).

### Dynamic trace harness — BUILT & PROVEN (tools/fw_sandbox.py)

- **FPU/FPU-VFP unlocked:** the sandbox sets a Cortex-M7/M4 CPU model *before* mapping memory and
  enables CPACR, so the player's VFP math now executes. Without this, `vpush` fails to decode
  (`UC_ERR_INSN_INVALID`) and the sequencer/player cannot be run at all. This is the key to
  emulator-testing the playback path.
- `tools/fw_sandbox.py`: Unicorn sandbox that loads the full image, maps FLASH/SRAM/CCM/wide
  peripheral space, calls any function with controlled regs/memory, and steps/stops/traces.
- `tools/trace_emit.py`: executes the real emit primitives and captures the MIDI bytes at the
  queue push. **Confirmed contracts (dynamic):**
  - note-on `0x8019A2A`: note = `r2`, velocity = `r0`  -> e.g. `90 3C 64`
  - note-off `0x8019A5E`: note = `r2`
  - note-pair `0x8019A92`: note = `r3` (not a pointer); velocity = `r0`; calls A2A then A5E
- `tools/boot_trace.py`: boots from reset with a minimal peripheral model (RCC CR/CFGR ready) and
  reports how far init gets + which functions are reached.
- `tools/drive_player.py`: drives the real per-note emitter `0x8021748` with a synthetic track
  object and captures its MIDI. Confirms the emitter runs (FPU/VFP included) and that the note is
  carried in `r3` to note-on/off; `0x8019A92` (pair) is **self-contained note-on + note-off**, so
  extra chord notes emitted through it can't leave stuck notes. Call-site arg layout (from
  `0x80217f4`): `r0=0, r1=time, r2=duration, r3=[obj+4]`, stack `[sp]=note, [sp+4]=vel,
  [sp+8]=channel`; channel = `[[obj+8]+0x1f]`.
  - Boot advances through clock init; then clock-setup `0x80319BC` returns failure -> fatal
    self-loop `0x0801245A` (`cpsid i; b .`). Full sequencer boot needs a real RCC/PLL model.
- **Remaining wall to the step cursor:** boot the scheduler (needs RCC + timer/peripheral model) so
  it generates step notes and calls the ticks; hook the tick to read the live (track, step). Or,
  next tractable experiment: call the melodic player `0x8021A14` with a synthetic track object and
  trace its memory reads to see whether it reads the step note from `[track]->pattern` (if so, the
  cursor is in the track object and fan-out hooks the player, which already has the track).

- **CC values per step**: DONE in the `steps2` format + emulator-proven bank. Remaining work is the
  firmware wiring: capture live `0xB0` into the per-step CC array on the record path, and fan CC out
  on playback / MIDI out per track.
- **External CV inputs**: improve response / mapping (separate workstream).
- **Pattern generators (added in official v3)**: revisit musicality; current output is very
  EDM/wacky. Separate from polyphony.

## Open firmware work: hardware step entry and polyphony

Playback is patched, but **programming chords on the module itself** is not yet poly-capable:

1. **Step-entry mode (clock off)** advances one step each time a note or rest button is pressed and
   commits that single note. A chord cannot be entered because each press commits and moves the
   cursor.
2. **Direct step-edit mode** (clock running or not) edits a step in place, but the commit path still
   stores one note per step (the single-note choke point at `0x0801F32C`).

Both need the same change: make the step commit **append** notes into the CCM poly array
(`0x1000B530`, `track*0x880 + step*17`) instead of replacing the single-note slot, and advance the
cursor only on an explicit "next step" action. Playback fan-out and velocity capture already read
that array, so hardware-entered chords will play once entry writes it. Browser-authored patterns
saved to the card already carry multiple notes and are unaffected.
