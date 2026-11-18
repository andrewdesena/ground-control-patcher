# Stock step paths: copy, clear, undo

> Historical research for engineering build IDs. Current public versions and user instructions are in [the documentation index](README.md). Sidecar workflows are abandoned.

Traced 2026-11-16 against `testdata/gc326.hex` by disassembly. Every claim below
is address backed. Poly-aware notes say what a patch would have to add for the
chord record at `0x1000B530 + slot*0x880 + step*17`.

## Pattern block layout

Block base = `track + 0x34 + 0x194*letter`.

| offset | meaning |
|---|---|
| `+0` | header pointer, deliberately not copied by the commit clone |
| `+4`, `+5` | header bytes |
| `+6..7` | header halfword |
| `+8` | first step record; 3 bytes each, note / velocity / modifier; 128 steps to `+0x187` |
| `+0x188` | pattern length (halfword) |
| `+0x18A` | extent / loop (halfword) |
| `+0x18C` | 8-byte tail |

So the note for step `n` is at `track + 0x34 + 0x194*letter + 8 + 3*n`. Earlier
notes in this repo said `+0x34 + 3*n`, which is off by eight and cost a day.

The canonical single-step writer is `0x0802705C` (`strh r3,[r1,#8]`,
`strb r3,[r1,#0xA]`, dirty `strh r3,[r0,#4]`).

## Copy: there is no pattern copier in stock

What looks like copy is the deferred commit at `0x08021338` into `0x08021480`:

```
080214A6  ldrh.w r1,[sl,#6]      / strh r1,[r2,#6]      header
080214B0  mov.w  r2,#0x180                             384 = 128*3
080214B8  bl     0x08035428                            memcpy(dst+8, src+8, 0x180)
080214BC  ldrh.w r2,[sl,#0x188] / strh.w r2,[fp,#0x1bc] length
```

It copies note, velocity and modifier for all 128 steps, plus the length and
extent. It never reads the chord bank: `0x1000B52C` has exactly one literal
reference in the whole image (`0x08030C5A`, the BSS clear).

Consequence: copying a chorded pattern between letters gives you the notes and
silently drops the chords.

Poly-aware copy needs the 128 chord records cloned from source to destination
bank after the `0x080214B8` memcpy. The complication is that each track owns
one bank, not one per letter, so the clone has to be reconciled with the loader
that repopulates a bank when the active letter changes.

## Clear: two paths, only one clears the record today

- **Edit-page path**, hooked in v1.10 at `0x080275C0`: clears the step and now
  clears the chord record too.
- **Step-fill path** `0x0802F264`, store body at `0x0802F430`:

```
0802F436  mvn  r2,#0x7f
0802F43A  strb r2,[r3,#8]     note = 0x80
0802F440  strb r2,[r3,#9]     velocity = 0
0802F446  bic  r2,r2,#7   / strb r2,[r3,#0xA]   modifier low 3 bits cleared
```

This one clears note, velocity and modifier bits only. It does not touch the
record, does not set the dirty flag, and does not write the length. Only caller
is `0x0802F6EE`.

Consequence: a step cleared through the fill path keeps a stale record. Playback
is silent because the note byte is empty, but re-entering a note on that step
can resurrect the old chord.

Whole-pattern clear is `0x0802BEDE`. It is not just a step loop: it sets length
to 16 (`0x0802BEBE`), zeroes the extent, sets dirty, and calls through
`block+0` to an object method at `0x0802BEB8`.

## Undo: does not exist in stock

No undo entry, no snapshot buffer, no restore path.

- The only 0x180 or 0x194 copy in the image is the forward commit memcpy above.
  There is no reverse or paired copy.
- `0x2000BC00 + 0x194*(trackIndex-1)` is a forward staging area written by the
  SD loader, not a save/restore pair.
- Pattern length has four writers: commit `0x080214C0`, UI setter `0x08026112`,
  whole-pattern clear `0x0802BEBE`, reset `0x0802D900`.

The 16 to 18 step symptom is most likely `0x08027758` to `0x0802777C`, an
append path that writes step 127 and then, if the length is at most 0x7F, forces
length and extent to 128 (`strhls.w r2,[r3,#0x188]`, `strh.w r2,[r3,#0x18a]`).
Writing a step past the current length pulls the length up. This is a plausible
mechanism, not a proven chain: the call site that an undo would use was not
found, because there is no undo to find.

## Hook addresses

| addr | role | poly-aware work |
|---|---|---|
| `0x080214B8` | commit clone memcpy, the only block copy | clone 128 chord records source bank to destination bank |
| `0x0802F430` | per-step clear in the fill routine | zero the step's record count |
| `0x0802BEDE` | whole-pattern clear | zero 128 record counts for the block's bank |
| `0x0802F2EE` | inlined second whole-pattern clear | same |
| `0x0802705C` | canonical step writer | set record `{count, note, vel}` |
| `0x08028194` | transpose, note only | done in v1.10, record moves by the same delta |
| `0x0802A10E` | step rotate, copies note/vel/mod in place | rotate records with it |
| `0x08027758` | append that can force length 128 | audit before any undo work |
