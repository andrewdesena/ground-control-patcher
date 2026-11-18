# Features and release notes

Updated 18 November 2026. [Firmware tool](../index.html) · [Pattern editor](../index.html#editor) · [Repository and support](https://github.com/andrewdesena/ground-control-patcher)

## Status matters

The confirmed baseline is **v0.9.0**, reported working by the maintainer. **v0.10.0-alpha.1** is a separate experimental candidate. Its CC paths have emulator tests; physical hardware validation is pending. The new web interface is local source until published.

## Public version scheme

Use 0.x while the complete v1 experience is being built. Preview **0.9.0** maps to engineering build **1.20-boot1**. Candidate **0.10.0-alpha.1** maps to the work initially labeled **1.21-cc1**. Those old IDs remain for traceability, not as public product versions. Reserve **1.0.0** for completed hardware acceptance. `firmware/releases.json` is the source of truth for public versions and filenames.

## Firmware improvements through v0.9.0

- Eight-note MIDI chords on all three melodic tracks, with individual velocities.
- Live chord recording and hardware step entry/removal with matching key lights.
- Single-file patterns replace the abandoned sidecar workflow.
- Save/load, Save As, clear and transpose retain matching chord state.
- Ownership checks prevent foreign or stale chord banks from leaking across letters.
- Pattern-chain selection uses the SD task; the timing callback does not read the card.
- Locked switching preserves the handoff between transport and the storage task.
- Quiet startup restores projects without the previous startup indicator behavior.
- DIN clock handling can service eligible realtime bytes at the next byte boundary while preserving note-message progress.

## Web and editor improvements

- Download-only firmware installation, supported-image checks, generated release metadata and short 8.3 download names. Browser-to-SD firmware writing was removed because of FAT32 and long-filename issues; transfer the HEX using your file manager.
- Confirmed and experimental firmware are labeled separately.
- Default pointer selection/movement, marquee selection and Option/Alt-drag copying.
- Double-click insertion/removal, B for draw/erase, clipboard and keyboard editing.
- Undo/redo groups a whole gesture into one edit.
- Velocity lane, selection inspector and relative velocity adjustment.
- Zoom, fit controls, timeline scrolling, browser sound preview and loop controls.
- Binary pattern I/O, exact-path navigation, independent document state and browser recovery.
- Card backups, conflict detection, full read-back verification and explicit save failures.
- Contextual instructions, backup/compatibility notices, disclaimer and project-owned support links.

## v0.10.0-alpha.1 experimental candidate

- Four CC lanes per melodic track; arbitrary controller numbers 0–127 and values 0–127.
- Incoming MIDI CC recording follows the native melodic input channel configuration.
- Four external CV inputs can be assigned to lanes on the desired track/pattern.
- CV samples are quantized at native step boundaries and mapped to the configured CC range.
- Values persist in a checksummed block inside the same pattern file.
- CC output runs once per step, including rests, independently of note ratchets.
- Native save/reload and corrupt-extension fallback have emulator coverage.
- Clear and rotation hooks keep automation aligned with pattern lifecycle operations.

See [CC hardware acceptance](cc-automation.md#hardware-acceptance) before treating this candidate as a release. This build does not add continuous automation curves, per-note durations, browser MIDI-device output or drum CC recording.

## Support and responsibility

These are unofficial tools, supplied as-is without warranty and used at your own risk. The authors and contributors accept no responsibility for problems to the fullest extent permitted by law. There is no affiliation with or endorsement by Endorphin.es. Do not contact Endorphin.es for support with the patches or editor; [report problems here](https://github.com/andrewdesena/ground-control-patcher/issues).
