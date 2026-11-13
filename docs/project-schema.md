# Ground Control project file schema (grounded)

Reconstructed from the v3.26 firmware JSON-format strings (addresses under `0x08036xxx`) plus the v3
manual. This is what the device reads/writes to SD. `/projectX` holds the project + melodic track
data; `/projectX/trackD` holds the drum track.

## Project / global settings

```
Cv1..Cv4        : { "Type": u, "Param": u }          external CV input matrix
Track1..3Scale  : { "Scale": u, "Root": u }          per melodic track
direction       : u      pattern direction (fwd/rev/pendulum/random)
slide           : u
shuffle         : u
humanize        : u
ratchet         : u
humanize[9]     : u[9]
ratchet[9]      : u[9]
triggerlength[9]: u[9]
gatelength      : u
ArpEngaged      : u
ArpMode         : u
ArpLatch        : u
ArpSuperLatch   : u
ArpNotes        : [ { "Note": [ "<name>", <vel> ] }, ... ]
patternChain    : [ "A", ... ]                       pattern queue letters
BPM             : u
Muted[12]       : u[12]                              mute flags
modulationTrack : u
modulationSubtrack : u
modulationPolarity : "<str>"
modulationSource   : "<str>"
modulationSlideMode: "<str>"
Polyrhythm      : { "From": u, "To": u }
```

## Global device settings

```
LastLoadedProject, TracksLocked, BuzzerTrack, BuzzerEnabled,
MasterClockSource, ResetOutputMode, ClockDividers, OutputClockDivider,
channelRx[4], enableChannelGlobalRx, channelGlobalRx, RxSameAsTx[4],
channelTx[4], enableRx[4], enableTx[4], OmniChannel[4],
MidiHostLoopback, MidiHostToDeviceForward, MidiDeviceToHostForward,
ClockOnStop, KeyLed, RxTransport, TxTransport, GateLed,
MenuTimeout, TapTempo, StartPattern, SnapAlgo
calibrationData : [ { "channel":u, "low_mv":d, "zero_mv":d, "high_mv":d }, ... ]
```

## Step data (per track, melodic)

```
{
  "step_limit": [ u, ... ],      active steps (1..128)
  "count": u,
  "duration": u,
  "modulations": ...,
  "steps": [ { "note":"<name>", "velocity":u, "modifier":u, "ratchet":u }, ... ],
  "ratchets": [ u, ... ]
}
```

## Drum track (`/projectX/trackD`)

8 trigger lanes 1..8 (one MIDI note each). Steps carry `{ "note","velocity","modifier","ratchet" }`.

## Notes for the editor

- **Steps 1..128** (device supports up to 128 since v3.14; the manual's "64" is stale).
- Polyphony extension: our `steps2` adds `notes:[[midi,vel]]` and `cc:[[num,val]]` per step; the
  editor exports it alongside the legacy single-note `steps` for backward load.
- The editor models the drum track as 8 lanes per step and exports a drum section; exact device
  lane-vs-flat layout still needs a real SD `trackD` sample to pin.
