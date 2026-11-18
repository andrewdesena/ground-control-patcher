# Project-switch preload: stock map (v2, QA-corrected)

> Historical research and version-specific observations. Use [current documentation](README.md) for installation, compatibility and release status. Sidecar references describe abandoned formats.

Answers "which stock caller loads patterns on a project switch, and why does the
chord bank end up wrong?". Addresses are Stock v3.26 (`testdata/gc326.hex`).

> **Status: the v1.2 loader-cave fix was rejected by QA (`VERDICT: NOT SAFE`); the
> v1.3 commit-handoff cave in `mods/poly-commit-reload.source.json` is the current
> candidate and is awaiting QA plus the hardware gate. `index.html` still embeds the
> hardware-confirmed v1.1 ten-site bundle, so nothing unvalidated is being served.
> See "The v1.3 design" below.**

## Call chain

```
0x0802DC4C  playing project switch: 0x080210B8(1, newProject)
  0x080210D8  sets the transition flags, including the inhibit byte 0x2000C5D8
0x0801DCCA  activate project: saves the old index, calls 0x0801DCB0, then 0x0801B664
  0x0801DCB0  wrapper: mode bytes 0x63 / 0x62 + stack args
    0x0801DB60  project load entry (r0 project object, r1 index, r2 0x63, r3 0x62)
      0x0801DBD2/DBDC/DBE6/DBF0  call 0x0801D1EE for selectors 0..3
        0x0801D1EE -> 0x0801D1DC -> 0x0801D064   (track dispatch)
```

`0x0801D064` routing:

- selector 0 (drum) -> drum loader `0x0801C8B8`; selectors 1..3 -> `0x0801CCC4`.
- mode `0x62` (project path): `0x0801D0AA` loads `TrackSettings.txt`, then
  `0x0801D0CA` walks the 24-byte order table at `0x080382F8`
  (`00 0e 01 0f 02 10 03 04 11 05 12 06 07 13 08 14 09 15 0a 0b 16 0c 17 0d`)
  and calls the pattern loader once per letter with
  `dest = projectBase + 0x194*letter + 0x34`.

**The inhibit byte `0x2000C5D8` does not skip the loop.** When it is nonzero,
`0x0801D19A–0x0801D1AA` routes the *held active letter's* load through
`0x0802101C` to a temporary destination:

```
0x2000BC00 + (trackSelector - 1) * 0x194
```

That is the normal state during a *playing* project switch.

## Pattern loader `0x0801CCC4`

```
0x0801CCD6  bl 0x0801A4D0    clear the staging buffer (does NOT touch the chord bank)
0x0801CCE6  copy the 20-byte path template from 0x0803702C ("patternX.txt")
0x0801CD08  letter table 0x08038310[letter] -> ASCII letter, stored at [sp+0x3F]
0x0801CD26  f_open(0x1000E000, buffer, 1)
0x0801CD2C  FR_OK -> 0x0801CD80, otherwise -> epilogue at 0x0801CD78
0x0801CD80  f_read(0x20008A78, 0x27D8)
0x0801CD92  f_close
0x0801CD96  sidecar hook site (v1.1/v1.2: bl cave)
0x0801CD9A  parse, copy the staging buffer into dest, epilogue 0x0801CD78
```

Emulator findings: a failed `f_open` never reaches `0x0801CD96` and does not touch
the chord bank; the native clear at `0x0801A4D0` does not touch it either; the
24-letter loop really does enter the loader 24 times per track.

## Tables, letters, bank

| what | address | notes |
|---|---|---|
| track object table | `0x08038370` | 0 track1 `0x20013DEC`, 1 track2 `0x200117C8`, 2 track3 `0x2000F1A4`, 3 drum `0x2000CB80` |
| second track table | `0x08038768` | same four parents |
| pattern letter table | `0x08038310` | 24 pointers; A..T, V, W, Y, Z (no U, no X) |
| pattern order table | `0x080382F8` | 24 indexes walked by the preload |
| active pattern letter | `track + 0x2E` | index 0..23; the player reads it at `0x0801F54C` |
| chord bank | `0x1000B530 + track*0x880` | 2176 bytes per bank; bank 0 is the drum slot |
| sidecar filename | `0x1000E400` | "poly" + letter |
| sidecar count | `0x1000E300` | must be exactly 2176 |
| FATFS FIL | `0x1000E000` | |

Pattern object: `track + 0x34 + 0x194*letter` -> A `0x034`, B `0x1C8`, C `0x35C`,
D `0x4F0`. The v1.1/v1.2 cave tests `offset < 0x4F0`, so **letters D..Z never
reach the publish**, and `r5 < 3` admits the drum slot while **excluding melodic
track 3**.

Related sites with their own inherited defects (v1.1 and v1.2 alike):

- Fan-out (playback): `0x08047600`, hooked at `0x080217F4`. Its primary-note
  membership check at `0x08047672` accepts any stale chord that happens to share
  the new pattern's primary note.
- Save cave: `0x08047E00`. The stock writer puts the **letter** in `r7`
  (`0x0801C45A`) and the cave uses `r7*0x880` as a bank offset (`0x08047E40`)
  while skipping `r7 == 3` (`0x08047E08`). Letter D skips sidecar saving; E..Z
  index past the three melodic banks.

## The v1.3 design: publish at the commit handoff

Hook `0x08021528`, the per-track call to `0x08023158` inside the playback-start
routine at `0x080214F8`. The loop walks four track pointers from the RAM table at
`0x2001CC50` (literal at `0x080215E4`); the flash tables `0x08038768` and
`0x08038370` hold the same four pointers, so any of the three is the same index
space. By then:

- the deferred commit (`0x08021338`, gated on `0x2000C5D8` at `0x0802150C`) has
  already copied the incoming project's staged patterns into the track objects and
  written the incoming settings;
- `0x08023158` installs that track's playing pattern letter at `[track+0x2E]`.

So this is the first point where "the letter the player will use" is knowable, and
it is the point the loader hook could never reach.

`mods/poly-commit-reload.source.json` (cave `0x08047A00`, 312 bytes) does:

1. call the stock `0x08023158`, then read `[track+0x2E]`;
2. cost gate: publish only when the switch flag `0x2000C5D8` is up or the letter
   changed during the call — an ordinary play press with an unchanged letter does
   no SD I/O;
3. skip non-melodic tracks with stock's own discriminator `[track+0x2D] == 1`
   (`0x080213D8`, player `0x0801F544`), so the drum is skipped wherever it sits;
4. resolve the track index from `0x08038370`, require `< 3` (the range the fan-out
   can consume), and build `/project<L>/track<idx+1>/poly<L>` at `0x1000E420` from
   the template at `0x0803701B`; project letter = `letterTable[[0x2000B250+0x249]]`;
5. zero bank `0x1000B530 + idx*0x880`, `f_open`/`f_read` 2176/`f_close`, require
   exactly 2176 bytes. `FR_NO_FILE` zeroes the bank; any other error leaves the
   bank untouched, so a wrong path can never silence a track that plays today.

`tools/test_poly_commit_reload.py` drives the installed hook (not the cave) and
covers: paths and banks for tracks 1..3, drum skip, letter E, the cost gate, the
same-letter switch, a committed letter change, missing/short sidecars, `FR_NO_PATH`,
and out-of-range project/letter bytes.

## Fix order for whatever comes next

1. Hardware gate the current candidate; fall back to v1.1 if anything regresses.
2. Save cave `0x08047E00` indexes banks by pattern letter, not track (letter 0 ==
   bank 0 only coincides for track 1 / pattern A). Fix before claiming persistence
   for other tracks or letters.
3. Loader cave `0x08049000` still publishes whatever letter it loads and is bounded
   at `0x4F0` (letters D..Z never reach it). The commit hook makes the bank correct
   at every play start, so this is now a cold-boot-only path; tidy it separately.
4. Fan-out `0x08047600` only checks primary-note membership (`0x08047672`), so a
   stale chord sharing the new pattern's primary note still emits extras.
5. Test through the real project-switch entry (0x0802DC4C) end to end once the
   hardware build is confirmed.

## What still stands from this work

- `mods/v1-poly-known-good.json` — byte copy of the v1.1 bundle; useful base.
- `tools/build_v1.py` — rebuilds the shipped bundle from a base + one source file,
  and `--check-html` proves `index.html`'s embedded V1 matches. Keep it; point it
  at the next cave.
- `tools/test_poly_activegate.py` — unicorn harness that runs the **real loader**
  with a FatFS model; useful, but its assertions must be rewritten to drive the
  real project-switch entry, not single loader calls.
- `mods/poly-load-sidecar.source.json` and `mods/v1-poly-full-gated.json` — the
  rejected v1.2 cave. Kept as evidence; **do not flash**. `index.html` is back on
  the v1.1 bytes and the generated v1.2 hex/`GCV326P.HEX` were deleted.
