# Ground Control firmware and pattern tools

Local browser tools for unofficial customization of Endorphin.es Ground Control v3.26 and editing its patterns.

[Open firmware tool](https://andrewdesena.github.io/ground-control-patcher/) · [Open pattern editor](https://andrewdesena.github.io/ground-control-patcher/#editor) · [Installation guide](docs/reference/guide.html) · [Editor instructions](docs/reference/editor.html) · [Features and release notes](docs/releases.md) · [Report a problem](https://github.com/andrewdesena/ground-control-patcher/issues)

## Disclaimer and support

**Unofficial firmware. Use at your own risk.** This project is not affiliated with, endorsed by, or supported by Endorphin.es in any way. The tools and patches are provided as-is, without warranty. To the fullest extent permitted by law, the authors and contributors accept no responsibility for device damage, lost data, failed updates, or other problems arising from their use.

**Do not contact Endorphin.es for support with these tools or modified firmware.** Use [this repository’s issue tracker](https://github.com/andrewdesena/ground-control-patcher/issues). Back up the whole SD card and retain the original stock firmware before installing anything. Ground Control is a product of Endorphin.es. The tooling is MIT-licensed; no vendor firmware is distributed here.

## Release status

| Component | Version / status |
| --- | --- |
| Confirmed firmware baseline | **v0.9.0**, reported working on the maintainer’s module |
| CC automation firmware | **v0.10.0-alpha.1**, experimental candidate with emulator tests; physical validation pending |
| Web tools | Source in this checkout; deployed site changes only after publication |

The patcher defaults to the confirmed baseline. Selecting the CC candidate is explicit. Neither a passing emulator test nor a verified SD write proves that a firmware build works on physical hardware.

Public versions are pre-1.0: **1.0.0 is reserved for the complete, hardware-tested experience.** The previous firmware IDs were engineering build counters. Preview 0.9.0 contains the same patch bytes as internal build 1.20-boot1; alpha 0.10.0-alpha.1 continues the CC work previously called 1.21-cc1. Older filenames remain as historical test inputs.

## Features and improvements

### Confirmed firmware baseline

- Up to eight MIDI notes per step on melodic tracks 1–3, with per-note velocity.
- Live polyphonic recording and hardware step editing, including note removal and chord-key LEDs.
- Chord data embedded in `pattern<letter>.txt`; no separate polyphony files.
- Single-file pattern saving, Save As, loading, clearing and chord transposition.
- Pattern ownership and deferred switching keep incoming and outgoing chord banks separate.
- Locked pattern-switch handling and quiet startup project restore.
- DIN MIDI realtime clock priority while retaining the existing byte formatter.
- Stock mono patterns remain readable. The drum track keeps its native file format; CV/gate outputs remain monophonic.

### Web tool and editor improvements

- Guided installation with stock-image verification, a pinned release bundle, output checksums and byte-for-byte card-write verification.
- Clear distinction between writing a firmware file and flashing it on the module.
- Ableton-style note selection and movement, marquee selection, double-click insertion/removal and Alt/Option-drag duplication.
- Draw/erase mode, clipboard operations, keyboard nudging, semitone/octave transposition and undo/redo.
- Per-note velocity lane and inspector, with relative velocity adjustment for selections.
- Horizontal/vertical zoom, fit controls, shared timeline scrolling and a responsive layout.
- Simple browser sound preview with play/stop, looping and a moving playhead.
- Binary-safe single-file pattern imports, exports, backups, copies and verified saves.
- Separate project/track/letter documents, unsaved-change indicators and browser draft recovery.
- Step-level tie, slide and ratchet controls; native pattern and track settings are preserved.
- Explicit limits, compatibility notices, installation instructions and project-owned support links.

### Experimental CC candidate

- Four controller lanes per melodic track, stored in the same pattern file as notes.
- Draw, paint, numerically edit and remove CC values in the browser.
- Record incoming MIDI CC messages while transport and live record are enabled.
- Assign each lane to incoming MIDI/editor data or one of the four external CV inputs.
- Record external CV at step boundaries, with configurable CC minimum/maximum values, including inverted ranges.
- Play automation once per step, including rests; preserve explicit zero values.
- Preserve notes and other controller lanes when overdubbing one controller.
- Checksum validation and bank ownership prevent damaged or foreign automation from being played.

**CC requires v0.10.0-alpha.1.** The default v0.9.0 build does not record or play the new automation. Physical CV input order, voltage mapping, MIDI timing under dense traffic and power-cycle persistence still need the [hardware acceptance pass](docs/cc-automation.md#hardware-acceptance).

## Install

1. Back up your whole microSD card outside the card itself. Keep the original official v3.26 HEX file for rollback.
2. Open the [firmware tool](https://andrewdesena.github.io/ground-control-patcher/) in Chrome or Edge on HTTPS. Choose the confirmed release unless deliberately testing CC.
3. Select your official stock v3.26 HEX. The build button remains disabled until its canonical SHA-256 matches the supported image.
4. Build the firmware. Hold **PROJ for about five seconds** on the module to enter USB storage, then connect the card root in the tool.
5. Choose **Write firmware to SD card**, or download the HEX and copy it yourself. Keep only one firmware HEX at the card root. Conflicting firmware files are never deleted automatically. Direct writes use short 8.3 card names: `GCV326B0.HEX` for 0.9.0 and `GCV326C1.HEX` for the alpha. Downloaded files retain descriptive versioned names; use the corresponding short name when copying manually.
6. After the write verifies, safely disconnect USB storage and follow the module’s firmware-update procedure. Keep power stable during updating.

The browser writes a file; the module’s bootloader performs the update. To return to stock, put only the original vendor HEX at the card root and follow the same module update procedure. Stock firmware plays native mono notes and removes embedded extensions when it rewrites patterns, so keep your backup.

Supported stock canonical SHA-256:

```text
e1db4815f8cf2983f832493aa8b2085586cb5ea10446e133774bdfc91bca9f52
```

## Edit patterns

Open the [pattern editor](https://andrewdesena.github.io/ground-control-patcher/#editor). Use **Open SD card** to browse native projects, or import a pattern file/editor project. Select the exact project, track and pattern letter. Save changes to the card or export a pattern file.

Each melodic pattern is a native text prefix followed by binary data. **Do not edit these files in a plain text editor or parse the whole file as JSON.** Legacy `poly<letter>` files are ignored; this tool neither reads, writes, migrates nor deletes them. A missing letter never silently loads A.

**Export editor project** creates a browser-workspace JSON backup, which the module does not read. Native pattern export uses `pattern<letter>.txt`. Existing card files receive a byte-preserving `.bak` before replacement; a backup failure or conflicting card edit stops the save. These on-card backups do not replace a full off-card backup.

Notes use fixed steps, up to 128. Tie, slide and ratchet apply to a whole step. Independent note lengths are not supported. Preview uses a basic browser instrument; it is not a hardware synthesizer or a complete simulation of the module’s modulation, generators, swing, routing or CV outputs.

## Development and checks

Serve locally with `python3 -m http.server 8765 --bind 127.0.0.1`, then open `http://127.0.0.1:8765`. Direct card access and SHA-256 verification need HTTPS or localhost. No backend or upload service is used.

- `assets/pattern-format.js`: independent binary codec shared by every editor file operation.
- `assets/editor-model.js`: undoable document and settings state.
- `assets/card-store.js`: exact card paths, backups, conflict detection and read-back verification.
- `tools/web_release.py`: generate/check the browser release against pinned firmware bundles.
- `firmware/cc_automation.c` and `tools/build_cc.py`: bounded CC candidate and freestanding Thumb build.
- [Pattern formats and firmware compatibility](docs/project-schema.md), [CC implementation and acceptance](docs/cc-automation.md), [documentation index](docs/README.md).

Install the local emulator dependencies into a virtual environment: `unicorn`, `capstone` and `pyelftools`. A working `clang` targeting Cortex-M4 is needed to rebuild the CC candidate. Put your own official firmware at `testdata/gc326.hex`; it is ignored by Git.

```sh
python3 tools/web_release.py --check
node --test test/web/*.test.cjs
.venv/bin/python tools/build_cc.py
.venv/bin/python tools/test_cc_automation.py
.venv/bin/python tools/test_poly_live_record.py mods/poly-0.10.0-alpha.1.json
.venv/bin/python tools/verify.py mods/poly-0.10.0-alpha.1.json
```

`test_cc_automation.py` regenerates the cross-language pattern fixture consumed by the JavaScript tests. Browser checks use Playwright with a local Chrome installation; see `test/web/browser.cjs`. The standalone older HEX tests use `testdata/gc326.hex` as their local input.

## Repository hygiene

Firmware images, real card data, `.bak` files, local staging folders and session handoffs stay on disk but are ignored. The browser contains patch bytes only. Historical research remains clearly labeled under [the documentation index](docs/README.md); it is not current installation guidance. No changes are published just by editing this checkout.
