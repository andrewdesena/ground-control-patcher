# Current pattern file formats

This document supersedes the older `steps2` and separate `poly<letter>` proposals. [Editor guide](reference/editor.html) · [CC specification](cc-automation.md) · [Historical research](README.md#historical-research)

## Card layout

`project<name>/track{1,2,3,D}/pattern<letter>.txt`, with project/track settings in `ProjectSettings.txt` and `TrackSettings.txt`. Supported pattern letters are A–T, V, W, Y and Z; U and X are not available.

Melodic tracks support up to 128 steps and eight note/velocity pairs per step. Native note names use octave `floor(midi / 12) - 2`, with sharps after the octave, such as `C3#`. The editor displays conventional MIDI names, with MIDI 60 shown as C4. A native rest is `G8#` with velocity zero. Tie, slide and ratchet are shared step attributes; independent note lengths are not stored.

## GCP1 chords

The file starts with native v3.26 pattern text. At the end is a 2,188-byte trailer:

| Offset | Bytes | Meaning |
| --- | ---: | --- |
| 0 | 8 | `00 47 43 50 31 00 00 00` (NUL, GCP1, reserved zeros) |
| 8 | 2176 | 128 records, each count + eight note/velocity pairs |
| 2184 | 4 | Little-endian IEEE CRC32 of the 2,176 record bytes |

A zero-count chord record falls back to the native mono note. The native text always includes a representative note for each chord, so stock firmware can play a mono version. The editor emits the lowest chord note as that representative.

## GCC1 automation extension

The experimental v0.10.0-alpha.1 layout is **native text + optional GCC1 block + GCP1 trailer**. Files without automation keep the GCP1-only layout. The optional block is 540 bytes:

| Offset | Bytes | Meaning |
| --- | ---: | --- |
| 0 | 8 | `00 47 43 43 31 00 00 00` (NUL, GCC1, reserved zeros) |
| 8 | 528 | Four lanes of 132 bytes |
| 536 | 4 | Little-endian IEEE CRC32 of the 528 lane bytes |

Each lane starts with controller number + 1 (zero means unused), source (0 = editor/MIDI, 1–4 = external CV input), CV minimum, and CV maximum. The next 128 bytes are per-step value + 1. Zero means no event; byte 1 represents CC value zero; byte 128 represents CC value 127. Inverted CV ranges are supported.

The existing final GCP1 trailer remains intact. v0.9.0 can read the chords from editor-generated CC files but does not play or record their automation. Saving from older firmware removes the CC block. Stock firmware stops at the first NUL and plays native notes; rewriting the file removes extensions. Keep an off-card backup before downgrading.

The editor bounds native text plus GCC1 to 10,200 bytes to retain the baseline loader’s prefix bound. The candidate’s chord reader accepts up to 10,740 prefix bytes so the native firmware writer can also append GCC1. The native text parser’s buffer is unchanged. Very large candidate-written files can therefore lose chord expansion when opened on older patched firmware; use the editor’s notes-only export for downgrade.

## Drums and settings

The drum track remains native text with its lane arrays and no GCP1/GCC1 trailer. Unknown pattern and settings keys are preserved. Editor project JSON is a separate workspace backup, not a module pattern file.

All reads, copies and backups of melodic pattern files must operate on bytes. Parse only the native text before the first NUL. Validate extension headers, bounds and CRCs before decoding their payloads. Separate legacy sidecars are ignored and never created or migrated.
