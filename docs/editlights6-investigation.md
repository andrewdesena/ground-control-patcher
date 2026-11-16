# EDIT keyboard LEDs: image findings and experimental v6

Stock input: `testdata/gc326.hex`, SHA-256
`c16f25740bdae0f3ca793d3747ad0e578a83dd5d2d4000923471c8716f317fa4`.
Evidence below comes from Capstone disassembly and controlled Unicorn replay of
that image. Hardware behavior of v6 is unverified. The supplied hardware result
for v5 is consistent with the reproduced failure.

## The selected-step renderer

The stock UI task dispatches the active page at `0x080207B4..0x080207BA`, then
calls the compositor at `0x080207BC`:

```
[0x2001C380] -> active page object (page 6: 0x20000590)
  page vtable 0x08039688, slot +8 -> 0x0802AE20
    [0x2001C388 + 8] -> selected inner editor (melodic: 0x2001C230)
    inner vtable 0x08038A28, slot +0x14 -> 0x08027D24
      0x08027D98..0x08027DC2 -> selected primary note -> 0x0801ECFC
      0x0801227C(bit, mode) -> 0x08011F50 -> LED state planes
  0x08012128 -> composes seven bytes at 0x20001E7B
scheduler tick -> 0x08012C12 -> 0x08012008 -> hook 0x08012068
  -> 0x080322C4(r0=0x20002B2C, r1=0x20001E74, r2=7)
```

The scheduler has calls at `0x08033AB2` and `0x08033B52`. They are not
unconditional in all scheduler states: the first checks `0x2001CE28`.
The point relevant here is that the transmit path does not select the EDIT UI.

The edited note is cached by `0x080273B4` at `0x2001CDFC`. Its source is
`[editor+8] + 3*[editor+7] + 8`. The editor fields are:

| Field | Meaning established by stock code |
|---|---|
| `+4` | 1 selects the step EDIT branch, rather than record entry |
| `+7` | 0-based selected step; cursor writes at `0x08027A04/0x08027A3C` |
| `+8` | selected pattern pointer, track + letter*0x194 + 0x34 |
| `+0xC` | selected track pointer |

`0x080274CC` opens this editor. `0x08027506..16` constructs its pattern pointer;
`0x0802752E..3A` selects cached-note display mode 2 and calls `0x080273B4`.
`0x0802D4B4(6)` reaches this opener through `0x0802C01C -> 0x0802BF64`
and the inner editor's vtable slot +8.

The twin sender `0x08011FB8` has no composition loop. It transmits the existing
seven-byte frame. Its single direct caller, `0x08012B34`, is in initialization
before task creation. The two senders are not two EDIT keyboard views.

## Why v5 declines

The test replays the stock `.data` copy at `0x08030C1C` and global constructors
at `0x0803530C`, then initializes managers via `0x0801F7E8`. It does not invent
track types or manager IDs. The resulting track table is:

| Table index | Track pointer | Byte +0x2D | Stock role |
|---:|---|---:|---|
| 0 | 0x20013DEC | 1 | drum |
| 1 | 0x200117C8 | 0 | melodic |
| 2 | 0x2000F1A4 | 0 | melodic |
| 3 | 0x2000CB80 | 0 | melodic |

Stock's discriminator at `0x080213D8` takes type 1 into the `0x51C` drum
pattern path. Its other branch uses `0x194`. `0x0801F544` likewise uses the
melodic `0x194` path when type is **not** 1. The brief and previous test reverse
this condition. V5's `cmp #1 / bne pick` cannot accept a real melodic track.

The manager flag is also unrelated to the displayed step editor. Manager
`+0x2DC` is the latch flag: setter `0x0801F364`, toggle `0x0801F394`.
`+0x2DB` enables that input-manager mode. Opening the selected-step editor
calls `0x0801F3DC(manager, 0)` at `0x080274EE` to disable it. This leaves a
previous latch flag intact, so the flag can be either 0 or stale 1 in EDIT.
It is not a reliable EDIT gate. Manager `+0x2DF` is that manager's input cursor,
not the `editor+7` cursor moved by `0x0802796C`.

The cited `0x0802DD3A/5A` writes target the separate object at `0x2001C3CC`.
The reset at `0x0802B430` targets that object too. These addresses do not prove
anything about the CCM managers merely by sharing the offset `+0x2DC`.

In the reproduced C60 step, the first three transmit bytes are `00 00 10`:
the singleton guard passes, every manager latch is 0, and v5 returns without
expansion. With the selected manager latched through stock UI code, v5 still
returns without expansion because the selected melodic track's type is 0.
This proves two independent defects; it does not establish which gate Drew's
physical unit reaches first in every UI state.

## Frame and mapping corrections

The transmitted frame is **seven bytes**, not three. Aligned literal scans over
the complete HEX address map find E74 at `0x08011FE0/0x08012088`, and 2B2C at
`0x08011FE4/0x0801209C/0x08012784/0x08030BD8`.

`0x08012128` produces E7B from E82 XOR the blinking/temporary plane.
`0x08012008` rebuilds E74 from E7B, masking E90 during five of six PWM phases,
and separately modulating bit 15. These first three bytes are not an exclusive
24-key plane: bit 15 is absent from the stock keyboard map, while keyboard bit
31 lives in byte 3. Thus the singleton guard can also fail on a non-key bit.

`0x0801ECFC` subtracts 12 times the signed octave at `0x2001CDE8`, then maps
notes 53..76 using the 24-byte table at `0x08038690`. C60 maps to bit 20,
E64 to bit 9, G67 to bit 0, and F#54 to bit 31. The supplied artificial
C-based key-index map instead maps G67 to bit 18 and substitutes bit 15 for
the missing key. Its two halves are mutual inverses, but that property does
not establish compatibility with stock's octave window. V6 uses the stock
mapping directly. Its data writes stay inside the seven-byte E74 frame;
bit 31 requires byte 3. It never writes E7B, E82, E89, E90, patterns or banks.
If a separate policy requires exactly the first three bytes, F#54 cannot be
supported under that policy.

The v5 compiled cave is 288 bytes including its literal pool, rather than the
280 claimed in the brief.

## Contribution and limits

`mods/poly-editlights6.source.json` uses a new 300-byte cave at `0x08048000`.
It replaces both hooks and preserves the old cave and tables as unused bytes.
It checks active page 6, open melodic inner editor, EDIT choice, display mode,
actual track identity, active pattern pointer, cursor, cached primary, chord
count and visible primary. It ORs in-range notes using stock's signed octave
and mapping. Counts outside 1..8 are rejected. r4-r11 are preserved; its stack
save is 24 bytes. Both displaced literals are restored at both hook sites.
It calls no other routines and performs no SD I/O.

**Existing bank limitation:** v1's fan-out only resolves table indices 0..2.
Slot 0 is the drum; the third melodic track is slot 3 and has no bank address
supported by that fan-out. V6 intentionally follows the installed bank
identity and skips slot 3. It does not change playback or repair that separate
bank-coverage issue. The existing commit-reload source also has the reversed
type-1 discriminator; this contribution leaves that baseline unchanged.

The test in `tools/test_poly_editlights6.py` enters through the actual page
switch, stock UI task call site, renderer, compositor and tick thunk. Only
UART logging and SPI transport are stubbed. It reproduces v5's failure and
checks both new hooks, A/X, signed octaves, adjacent steps advanced through
stock input code, mono/empty/8-note chords, out-of-window notes, key bit 31,
all six PWM phases, boot sender silence, rejection paths, set-only writes,
bank immutability and the register/stack contract. The original
`tools/test_poly_editlights4.py` also passes, demonstrating why its invented
track types and pre-seeded LED source failed to catch this bug.

Both standalone bundles and both merged bundles pass `tools/verify.py`.
The browser engine also serializes images matching the Python builds at every
address: 254540 bytes for the fix, 254576 bytes for the diagnostic. The style
linter reports clean.
Merged builds retain every v5 site byte-for-byte except the two intended
hooks, and add a disjoint cave. Neither `index.html` nor existing images were
changed. No commit, deployment or hardware flash was performed.

## One-flash diagnostic alternative

`mods/poly-editlights6-diag.source.json` uses a separate 336-byte cave at
`0x08048400`. Use it **instead of v6**. It checks the old v5 gates before ORing
markers, only while page 6 is active. It does not perform chord expansion.
Use the reported C-E-G step so the status keys do not overlap its primary C.
Labels below use the supplied hardware bit-to-key observations.

Sender marker: **high C** means sender B (`0x08012068`) ran. **High D** means
sender A (`0x08011FC6`) ran. B is the expected runtime marker. No marker is
added during boot or outside page 6.

| Additional key | Bit | First relevant v5 failure/status |
|---|---:|---|
| low C# | 14 | first three bytes empty |
| low D | 19 | more than one bit in first three bytes |
| low D# | 13 | no manager has a nonzero +0x2DC latch flag |
| low F | 17 | flagged managers have invalid IDs above 3 |
| low G | 18 | valid flagged IDs exist, but none passes v5's type == 1 test |
| low G# | 16 | v5-computed chord count is zero |
| low A | 22 | v5-computed count exceeds 8 (v5 clamps it; v6 rejects it) |
| low A# | 23 | manager cursor exceeds 127 |
| high F# | 12 | count valid, but every chord delta misses v5's 0..23 window |
| low B | 21 | count valid and at least one old-map delta is in range |

A one-flash result of high C + low D# confirms the default replay's first
failure. High C + low G confirms the independently proven reversed type
gate on a latched melodic manager. If several status keys alternate, the
frame/state is changing between tick samples; the diagnostic stores no
history. Both sender markers and every status path are exercised by the test.

Build the fix:

```sh
./.venv/bin/python tools/asm.py mods/poly-editlights6.source.json mods/poly-editlights6.json
./.venv/bin/python tools/test_poly_editlights6.py
GC_VERSION=1.6 ./.venv/bin/python tools/build_v1.py mods/v1-poly-edit6.json /tmp/gc-v3.26_poly-v1.6.hex mods/poly-editlights5.source.json mods/poly-editlights6.source.json
```

Build the diagnostic alternative:

```sh
./.venv/bin/python tools/asm.py mods/poly-editlights6-diag.source.json mods/poly-editlights6-diag.json
GC_VERSION=1.6-diag ./.venv/bin/python tools/build_v1.py mods/v1-poly-edit6-diag.json /tmp/gc-v3.26_poly-v1.6-diag.hex mods/poly-editlights5.source.json mods/poly-editlights6-diag.source.json
```

Fix HEX SHA-256:
`a182d6f8d4e01a2990cbc9085da7581f53416c2bf59199a07ceb162fd628e2ef`.
Diagnostic HEX SHA-256:
`e500bcb62e145987d90dcfc438becde1818070a4187f29e48e0dae1fc092c51e`.
