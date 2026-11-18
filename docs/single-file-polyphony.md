# Ground Control v1.19 pattern files

> Historical research for engineering build IDs. Current public versions and user instructions are in [the documentation index](README.md). Sidecar workflows are abandoned.

Melodic tracks use one `pattern<L>.txt` per letter. A step can hold zero to eight notes. Zero notes means a rest and one note plays mono. The drum tracks keep their stock format.

The file begins with the original text written by the v3.26 pattern writer. It ends with a 2,188-byte trailer.

| Offset from trailer start | Size | Contents |
| --- | ---: | --- |
| 0 | 8 | NUL, `GCP1`, three reserved zero bytes |
| 8 | 2,176 | 128 records. Each record contains a count and eight note/velocity pairs. |
| 2,184 | 4 | Little-endian IEEE CRC32 of the records |

The stock tokenizer stops at the NUL delimiter. In the emulator, the original firmware parsed a 128-step stock file identically before and after appending the trailer. Stock firmware plays the mono notes and drops the trailer if it rewrites the file. Tools that read the file as text should read only the bytes before the first NUL.

A native file with no valid trailer loads with no chord expansion. The candidate neither reads nor writes separate polyphony files. Save As serializes the selected source pattern to the destination letter, with its chord data in the same file. Saving all patterns preserves an inactive letter's embedded records by reading the file before opening it for overwrite. Empty native saves use the existing unlink operation.

The writer snapshots the active bank while holding the stock pattern mutex. The active native loader installs the decoded bank before releasing the mutex that also protects the stock steps. A failed checksum discards the trailer and leaves the stock notes playable. The native overwrite still uses the stock FatFS operation, so it can lose the file if power fails during a write.

There is one live bank per melodic track. During a chain change, the stock SD task loads the requested file and installs the matching bank and letter together. The current letter remains active during the read. A slow card can delay a chain transition, and a request can supersede an earlier one. Chord edits should be saved before leaving a letter. The current implementation cannot retain unsaved chords for every inactive letter.

## Build and verify

```sh
GC_BASE=mods/v1-poly-dub.json GC_VERSION=1.19 .venv/bin/python tools/build_v1.py \
  mods/v1-poly-v119.json gc-v3.26_poly-v1.19.hex \
  mods/poly-lifecycle-ownership.source.json \
  mods/poly-lifecycle-commit.source.json mods/poly-lifecycle-load.source.json \
  mods/poly-lifecycle-mutations.source.json mods/poly-gen-modes.source.json \
  mods/poly-single-file.source.json mods/poly-edit-entry-held.source.json \
  mods/poly-transpose-inlock.source.json mods/poly-harddelete.source.json \
  mods/poly-editlights6.source.json mods/poly-entry-toggle.source.json \
  mods/poly-owned-playback.source.json \
  mods/poly-chain-select.source.json mods/clock-din-realtime.source.json
.venv/bin/python tools/verify.py mods/v1-poly-v119.json
.venv/bin/python tools/test_poly_v119.py
.venv/bin/python tools/test_poly_chain_single_file.py
.venv/bin/python tools/test_clock_din_realtime.py
```

Hardware validation is pending. The browser patcher still uses its existing format. The DIN clock patch can emit an eligible `F8` at the next byte boundary while a note message is in progress. It keeps the note byte cursor intact and respects older transport messages. USB MIDI uses the stock path. The emulator verifies byte order and duplication. Physical timing still needs a bench measurement.


## Hardware acceptance

Use a copy of the card data. Save test patterns on each melodic track with distinct three-note chords on steps 1 and 16. Include a mono step and a rest. Confirm the following on the module.

1. Enter each chord one note at a time, move the editor cursor, and remove the primary. Check key LEDs, pitch, velocity and rest behavior.
2. Save, power off, and reload. Confirm the chords return from the same pattern files. Save As to a different letter and check both letters after reload.
3. Run a chain such as A, E, A. Check that the first played E step has the E chord and listen for a late transition. Repeat on three tracks and while changing projects.
4. Clear steps and hard-delete a pattern, enter a fresh chord, and save and reload. Check for old voices and confirm the drum track is unaffected.
5. Compare stock and patched DIN recordings with the Ground Control as clock master at the same tempo. Capture 60 seconds with all three tracks playing dense chords. Compare clock count and median, 95th percentile and maximum inter-clock intervals. Include start, stop, continue and external-clock passthrough. Check for dropped notes and stuck notes.
