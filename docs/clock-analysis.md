# MIDI clock: how it actually works, and what a safe fix looks like

Confirmed in v3.26 by disassembly. Addresses are flash; SRAM functions are shown with their
flash alias (`SRAM = flash 0x080398A4 → 0x20000000`, so `flash = sram - 0x17FC675C`).

## 1. The chain

```
TIM2 (0x40000000)  ISR   0x08011258   clear TIM2 SR, then fall through
  └─ clock scheduler     0x08019644   runs every timer tick
       ├─ [thru flag]  → 0x080362D0   external-sync passthrough (v3.17 behaviour)
       ├─ accumulator += 0x64 (100)   [r4]
       ├─ if accumulator >= next[0x?] → send clock, next += period
       └─ 0x080190B0                  read current time
  └─ clock send          SRAM 0x20001408 (flash 0x0803ACAC)
       ├─ 0x0803B224  helper
       ├─ 0x0803B25C  helper
       └─ several 16-bit counters decremented per tick (per-output pacing)
  └─ event build         SRAM 0x200015E8 (flash 0x0803AE8C)
       writes 20-byte event {…, port byte = 0xFF (hardcoded at 0x0803AE9A)}
  └─ queue insert        SRAM 0x200015A8 (flash 0x0803AE4C) → sorted insert
  └─ per-port FIFO       refill 0x080117A4 : 6-byte records, 4 slots, cpsid i
  └─ byte formatter      0x0801901A / 0x0801903A : stream {buf,len,left,idx}
  └─ UART4 TX ISR        0x080118F0 : one byte per TXE interrupt
```

Separate, and unrelated to the tick: `0x08019620` builds an `0xF8` event and inserts it
into the same queue. Nothing branches to it — it is reached through the veneer pool
(`0x0803B278` → `0x08019620`), so its caller is not a plain `BL` in flash. Treat it as *a*
clock path, not necessarily *the* clock path; the live one is the SRAM sender above.

Two facts that matter:

* **One byte leaves per TXE interrupt at 31250 baud = 320 µs/byte.** A 3-byte note = 960 µs.
* Every event, clock included, is placed in **one 128-entry queue** shared with notes and CC,
  sorted by a 32-bit timestamp at entry `+8`, ties broken note-off before note-on.

## 2. "Won't skipping the queue wreck the notes?"

Naive version: **yes, in two specific ways.**

1. **Double send.** The clock event is a *queue entry*, not a byte. If you also write `0xF8`
   straight into the UART, the queued copy still gets formatted and transmitted afterwards.
   Every tick sends two clocks. Instantly audible as double-tempo downstream.
2. **Reordered note-on/note-off.** The queue is what guarantees note-off precedes note-on at
   equal timestamps (that tie-break is real code in the insert sort). Jump the queue and you
   can emit a note-on before the previous note-off of the same pitch. On synths in mono/legato
   mode that is a stuck note, and the module already has a known class of bug there (v3.26
   release note: stuck notes on project change when the last step had a TIE).

The legal argument people reach for — "0xF8 is a System Real-Time byte, receivers must accept
it anywhere, even mid-message" — is true at the *wire* level and does not help here. It
licenses interleaving on the DIN cable. It says nothing about the firmware's own bookkeeping,
and nothing about USB-MIDI, where a realtime byte has to become its own 4-byte packet with
CIN `0x0F`. A blind byte injection breaks the USB path rather than corrupting DIN.

So the rule for this mod: **the clock may overtake a message boundary, never a message.** Any
patch that emits `0xF8` between the bytes of a note is doing something legal but it is also
doing surgery on a stream the formatter still owns.

## 3. The three candidate fixes, ranked by risk

| # | change | effect | risk to notes |
|---|---|---|---|
| A | clock tick emits before the step's notes are queued (reorder one call) | clock always enters the queue with the earliest timestamp of that instant | none — no new bytes, no reordering of existing entries |
| B | dedicate a UART write to `F8` that the queue cannot see, and remove `F8` from the queue | clock never waits | medium — needs the per-port counter logic in the SRAM sender understood first, or the counters drift |
| C | 0xF8 preempts at the byte level, DIN only, queued copy kept for other ports | lowest latency | high — double-send and USB packetization both live here |

**A is the one to build first.** It needs one fact we do not have yet: which call site queues the
step's notes relative to the clock scheduler, i.e. the order inside the step handler. Then it is
a moved `BL`, not new code.

## 7. Queue ordering: what is actually true (corrected)

Read of `push` at `0x08019840`, which every port uses:

```
0x8019846  sub sp,#0x34
0x8019854  bl 0x080351FC        ; memset(entry, 0, 20)  — 20-byte entry template
0x8019868  str.w r8,[sp,#0x10]  ; entry+8 = arg0 (the port/context pointer)
0x801986C  add.w r2,sl,#1
0x8019870  str   r2,[r3]        ; global sequence counter++
0x8019878  str   r0,[sp,#8]     ; entry+0 = status/channel/data from the event
0x8019896  str.w sl,[r6]        ; entry+16 = sequence number
```

Two corrections to earlier notes in this file:

* **`entry+8` IS written** — it receives `arg0`, which for a member call is the port
  object pointer. It is not a timestamp and not zero.
* Since every entry in a given port's queue therefore carries the *same* key, the
  "sorted insert" degenerates to **FIFO order with one tie-break** (note-off before
  note-on, between two notes). There is still **no time-based priority anywhere.**

The practical conclusion stands and is what matters: a real-time byte enqueued after notes
waits behind them, always, for however many bytes are already in that port's queue. The fix
is a front-insert for realtime status (`0xF8`), which cannot reorder the entries behind it.

Caveat on confidence: this file has now been corrected twice as deeper reads came in. Static
reading has been overturning its own conclusions, which is the signal to stop reading and take
the bench measurement (clock master → log 60 s of MIDI → histogram of inter-clock intervals)
before any patch ships.

## 6. The decisive finding: clock and notes share one builder and one insert

`0x0803AFB2` is the tail of the single event dispatcher (`0x0803AE90`). Every real-time and
transport message lands on the *same* three instructions:

```
0x0803AFBE  movs r3, #0xF2      ; song position pointer
0x0803AFC0  mov  r0, sp
0x0803AFC2  strb r3, [sp]       ; status byte
0x0803AFC6  bl   0x0803AE4C     ; -> queue insert
0x0803AFCC  movs r3, #0xF8      ; <- CLOCK, same path
0x0803AFD0  b    0x0803AFC0
0x0803AFD2  movs r3, #0xFA      ; start
0x0803AFD6  movs r3, #0xFB      ; continue
0x0803AFD8  movs r3, #0xFC      ; stop
0x0803AFDC  movs r3, #0xFF      ; reset
```

So the clock is not special-cased anywhere. It is an ordinary queue entry built by the same
function that builds note-on, note-off, CC and pitch-bend, and inserted by the same primitive
(`0x0803AE4C` → copy primitive `0x0803B224` → pacing helper `0x0803B27C`).

Consequence, and this is the whole diagnosis:

* the timestamp is stamped by the insert, so two events created in the same 100 µs tick get the
  **same timestamp**;
* ties are broken by **insertion order** (the note-off-before-note-on rule only applies between
  two notes);
* therefore the clock loses whenever a note happens to be inserted first in that tick. Not always
  — which is exactly why it feels like intermittent drift rather than a constant offset.

The fix is a tie-break, not a bypass: a realtime byte must win the tie. Options, once the stamp
site inside `0x0803B224` is read:

1. stamp realtime events one tick early (`now - 1`) so they always sort first;
2. give the clock's insert its own entry point that writes the head slot directly;
3. raise the TIM2 NVIC priority so the clock ISR always inserts before the step ISR in the same
   window (cheapest, but it can preempt the SD/DMA paths, so it needs care).

All three keep note bytes untouched and keep note-off/note-on order intact, because inserting an
item ahead of everything else cannot reorder the items behind it.

## 4. The tick rate — answered

TIM2 setup at `0x08011160`:

```
mov.w  r3, #0x40000000
str    r2, [r3, #0x24]      ; CNT = 0
movs   r2, #0x53
str    r2, [r3, #0x28]      ; PSC = 83   -> 84 MHz / 84 = 1 MHz
movs   r2, #0x63
str    r2, [r3, #0x2c]      ; ARR = 99   -> 100 counts = 100 us
```

So the clock grid runs at **10 kHz, 100 µs resolution**, and the scheduler's `+= 0x64` per
callback is adding 100 µs. At 120 BPM one 24-ppqn tick is 20 833 µs, so the grid quantises it
to the nearest 100 µs: a **±100 µs floor, about 0.5% of one tick**. Inaudible next to a 1 ms
note-on.

That settles the diagnosis: the jitter is not the timer, it is **the clock waiting in a queue
behind note and CC bytes**. Which makes fix A the right one, and makes fix C (byte-level
preemption) unnecessary surgery.

Also note the scheduler re-targets with `next += period` rather than `next = now + period`, so
the 33 µs left over from 20 833 / 100 does not accumulate. Drift is already handled.
