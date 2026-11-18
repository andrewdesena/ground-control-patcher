# CC automation candidate

**v0.10.0-alpha.1 is experimental. Hardware validation is pending.** Keep v0.9.0 and a verified off-card backup for rollback. [Firmware tool](../index.html) · [Editor guide](reference/editor.html) · [Support](https://github.com/andrewdesena/ground-control-patcher/issues)

## What it does

Each melodic track has four CC lanes. A lane uses one controller number, 0–127, and stores up to 128 step values. A missing value sends nothing; zero is a valid value. The native GCP1 chord trailer is retained, with a checksummed GCC1 block immediately before it. See the [file specification](project-schema.md).

In the editor, add a CC lane and choose its recording source:

- **MIDI / editor:** draw values in the browser or record matching incoming MIDI CCs on the module.
- **CV input 1–4:** sample that external input at each native step boundary while live recording is enabled. Map the normalized input to a chosen minimum/maximum CC range. Reversing the range inverts it.

To record, load the pattern on the CC candidate, start playback, and enable the module’s native live-record mode. Incoming MIDI CCs follow the project’s melodic receive-channel/omni configuration. The last received value for each controller wins within a step. MIDI can allocate unused lanes until all four are occupied; additional controller numbers are ignored until a lane is freed. CV sources are assigned explicitly in the editor and are not overwritten by MIDI recording of the same controller.

Disarming or stopping prevents further recording. Playback sends programmed values once per step, including steps without notes. Notes and other controllers are preserved when overdubbing one lane. Step changes, ties and ratchets do not turn the CC lane into a per-note stream.

Save on the module before leaving an edited letter. There is one active automation bank per melodic track, matching the firmware’s existing chord-bank limitation. The editor retains multiple independent documents in browser memory.

## Memory and timing

The old drum chord-bank slot is unused by melodic ownership resolution; the native drum path remains stock. The candidate partitions that existing allocation instead of taking memory from the stack or the deferred-chain scratch area.

| Region | Purpose |
| --- | --- |
| `0x1000B530` through `0x1000BB5F` | Three 528-byte CC banks |
| `0x1000BB60` through `0x1000BD7B` | 540-byte SD snapshot / read staging |
| `0x1000BD80` through `0x1000BD8B` | Three automation ownership words |
| `0x1000BD8C` through `0x1000BD8F` | Validated snapshot flag |
| `0x1000BD90` through `0x1000BD92` | Per-track recording-overflow flags |
| `0x1000BDB0` onward | Existing melodic chord banks, unchanged |

No heap allocation or peripheral configuration is added. The input callback and step hook perform bounded work with no SD calls. Loading and saving run in the existing serial storage path. Snapshots and publication share the native pattern locking boundaries. The writer appends CC before the existing GCP1 tail.

External CV uses the same four 12-bit ADC samples and 4095 full-scale normalization found in the stock CV input dispatch. It does not rewrite the hardware calibration or change existing live CV mappings. Physical input order, voltage response, noise behavior and simultaneous native CV assignments must still be checked on the module.

CC output goes through the stock MIDI message builder and queue, retaining the baseline DIN realtime-priority patch. Four extra controllers per track can increase wire traffic substantially; high tempo and dense chords still require a physical timing test. The candidate does not promise unlimited DIN bandwidth.

## Build and emulator verification

```sh
.venv/bin/python tools/build_cc.py
.venv/bin/python tools/test_cc_automation.py
.venv/bin/python tools/test_poly_live_record.py mods/poly-0.10.0-alpha.1.json
.venv/bin/python tools/verify.py mods/poly-0.10.0-alpha.1.json
python3 tools/web_release.py
python3 tools/web_release.py --check
node --test test/web/*.test.cjs
```

The CC tests enter the installed transformed-input, step-playback, native writer and native loader hooks. They cover zero values, overdub, track routing, CV endpoints, ownership, CRC failures, legacy files and mutation controls. A firmware-written pattern is also decoded by the independent JavaScript codec. Build verification checks every patched byte and confirms zero collateral changes to stock addresses.

## Hardware acceptance

Use a copy of the SD card and retain the confirmed baseline firmware.

1. Check ordinary stock and polyphonic patterns, all three melodic tracks, drum playback and startup restore before using automation.
2. Record CC 74 and CC 1 from a MIDI controller on each track’s configured receive channel. Include value 0, repeated changes within a step, rests and loop wrap. Confirm wrong channels and disarmed transport do not record.
3. Assign each external CV input in the editor, one at a time. Verify the physical input order, low/mid/high values, minimum/maximum ranges and inversion. Check sustained values, noise near boundaries and simultaneous assignments.
4. Save on the module, power-cycle, and reload. Open the same files in the browser, edit the recorded values, save and reload on the module again.
5. Test Save As, A/E/A chains, project switches, clear, fill-clear, rotation and hard delete. Confirm no old automation returns, and test same-letter changes across projects.
6. Fill four lanes, then send a fifth controller. Confirm the pattern’s four lanes remain intact. Confirm the editor prevents creating a fifth lane.
7. Record DIN and USB output under dense chords and four controllers per track at several tempos. Compare clock intervals, note counts, CC counts and start/stop behavior with v0.9.0. Listen for dropped or stuck notes.
8. Test read-only/full cards and failed writes. Preserve the test data and revert to the confirmed baseline if behavior is unexpected.

## Responsibility and support

Unofficial software, provided as-is without warranty and used at your own risk. To the fullest extent permitted by law, the authors and contributors accept no responsibility for problems. This project has no affiliation with Endorphin.es. Do not contact Endorphin.es for patch support; use [this repository’s issue tracker](https://github.com/andrewdesena/ground-control-patcher/issues).
