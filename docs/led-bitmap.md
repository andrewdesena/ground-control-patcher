# Ground Control key LED bit map (v3.26)

Decoded on hardware 2026-11-13 using five binary-plane probes. Each probe ORed a
mask into the 56-bit phase output buffer `0x20001E74` immediately before SPI
shift-out (`0x08012068`). Keys were reported as note + low/high octave.

## Result: bit index -> key

| bit | key | bit | key |
|----:|-----|----:|-----|
| 0 | G high | 12 | F# high |
| 1 | A high | 13 | D# low |
| 2 | B high | 14 | C# low |
| 3 | C high | 15 | F# low |
| 4 | D high | 16 | G# low |
| 5 | E high | 17 | F low |
| 6 | C# high | 18 | G low |
| 7 | D# high | 19 | D low |
| 8 | F high | 20 | C low |
| 9 | E low | 21 | B low |
| 10 | A# high | 22 | A low |
| 11 | G# high | 23 | A# low |

## Key index -> bit (index 0 = C low, chromatic)

```
key:  C  C#  D  D#  E   F  F#  G  G#  A  A#  B   C  C#  D  D#  E   F  F#  G  G#  A  A#  B
idx:  0   1   2   3   4   5   6   7   8   9  10  11  12  13  14  15  16  17  18  19  20  21  22  23
bit: 20  14  19  13   9  17  15  18  16  22  23  21   3   6   4   7   5   8  12   0  11   1  10   2
```

## Notes

- Bits 0-23 are keyboard keys; bits 24-27 are unused; bits 28-55 are panel
  buttons/digits. Bit 28 = Oct -, 32 = Track 2, 36 = Last Step, 40 = Drum mute 2,
  44 = Drum mute 7, 48 = Track 3 mute.
- Writing bits 0-1 sets keyboard matrix drive lines and makes the LED driver hum.
  Byte 2 (bits 16-23) is quiet. Never clear these bytes; set/OR only. Clearing
  the low bytes kills the module at boot.
- `0x20001E74` is the per-phase output; `0x20001E7B` is the persistent state the
  scan rebuilds from. Writing `E7B` alone does not light keys (scan masks it).
- A single MIDI note held on stock lights exactly one key steadily; use that as
  an oracle when validating any LED patch.
- F# low never appeared in any of the five probe photos (user omission), which
  produced a collision at bit 0. It is bit 15 by elimination: all other indices
  are uniquely assigned.
