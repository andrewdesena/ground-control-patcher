# MIDI note output after USB storage

Status: unresolved hardware report, 18 November 2026. [Release status](releases.md) · [Firmware tool](../index.html) · [Support](https://github.com/andrewdesena/ground-control-patcher/issues)

## Report

The maintainer reported that v0.9.0 stopped sending MIDI notes over the TRS/DIN output after approximately 30 minutes idle in USB storage mode and then returning to normal operation. A subsequent reboot restored output. Connected devices appeared to keep receiving MIDI clock, but that distinction has not been confirmed with a byte capture. CV/gate outputs were not checked.

The CC candidate has not been tested on hardware. This report does not establish its behavior.

## What has been checked

The supported stock v3.26 image was inspected locally, together with the exact v0.9.0 patch bundle. No vendor image is included in this repository.

| Check | Evidence and boundary |
| --- | --- |
| Storage entry shuts down peripherals and transfers to the storage bootloader | Native entry at `0x08030ac8` calls the UART deinitialization path at `0x08032d3e`, changes the vector table to `0x080f0000`, then transfers to `0x080f1300`. REA/Ghidra evidence `ev_ff9ff6ce2aba79eb9f7d66b5908840b914af0b335b0c80c6e22df08d6d61188d`. This is static analysis, not an observed hardware transition. |
| The inspected storage exit path requests a system reset | The native fragment at `0x080f107c` writes the keyed `SYSRESETREQ` value to AIRCR and waits. Instruction decoding and execution of that exact fragment with memory-backed system registers verify the request. The larger bootloader function was not fully recovered by the decompiler. |
| Reset RAM initialization clears the patched DIN-clock state | The baseline RAM initialization at `0x08030c1c` clears the pending-clock area at `0x1000d730`, the DIN stream descriptor and ordinary/priority FIFO counters, even after the test fills RAM with nonzero bytes. This executes the native initialization loops and stops before peripheral initialization. |
| Clock and note bytes can coexist after RAM initialization | The patched DIN interrupt emits `F8 90 3C 64` from a prepared stream after the reset-memory test. Routing is stubbed, and UART registers are memory-backed. This does not test the sequencer generating a new note, the full startup path, or the physical connector. |

The analysis carrier was a temporary ELF reconstructed from the local stock image, SHA-256 `84fd731e9388f0e8ee65c6901659a692ee0a8c486e4390fb394e4ab78b219c36`. It is not a different firmware release. The carrier and vendor bytes are not published.

Run the focused check with the local emulator environment and your own stock image:

```sh
.venv/bin/python tools/test_storage_midi_reset.py
.venv/bin/python tools/test_clock_din_realtime.py
```

## What remains unknown

These checks do not reproduce a 30-minute storage session or identify the cause of the reported failure. They do not simulate the full bootloader, USB host, receiver, hardware reset behavior, restored project settings or live peripheral interrupts. There is no verified firmware fix yet, and the published firmware bytes remain unchanged.

If a capture confirms clock continues on the same output while notes are absent, a complete UART outage would be less likely. Note routing, sequencer dispatch, restored mute/project state and receiver filtering would still need investigation. Those are possible areas to check, not established causes.

## Hardware follow-up

1. Use a copied card and a known short pattern. Capture raw MIDI bytes from the same TRS output before entering storage.
2. Compare short storage sessions with approximately 30 minutes idle. Safely eject storage before exiting it. Keep the connected receiver and routing unchanged.
3. On failure, retain a capture showing clock, start/stop and notes separately. Check manually played notes as well as sequenced notes. Record whether the sequencer and CV/gate outputs still work.
4. Record the selected project, track, pattern, mute state, MIDI channel and output-routing settings. Preserve the card files before changing anything.
5. Save and safely eject, then reboot and capture whether output returns. A stock-firmware comparison on a copied card can help distinguish stock behavior from a patch regression.

Until a fix is demonstrated, the maintainer's observed recovery is a reboot after saving and safely ejecting the card. Do not treat this investigation as proof that the issue is fixed.
