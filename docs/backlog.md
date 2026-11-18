# Backlog

Current status: [features and releases](releases.md). Historical implementation discussions are indexed in [documentation](README.md).

## Before promoting the CC candidate

- Complete physical CV input-order, range, noise and inverted-mapping checks.
- Measure DIN and USB output with dense chords plus four controllers per melodic track.
- Complete save, power-cycle, Save As, chain, project-switch and clear/rotation checks on a copied card.
- Test card-full/read-only errors and recovery. Retain v0.9.0 as the confirmed baseline.

## Future improvements

- Independent per-note lengths and ties require additional firmware representation.
- Continuous automation and interpolation require a separate timing/traffic design.
- Browser MIDI-device preview/output and MIDI file import/export are not part of this release.
- Chord-mode generators and improvements to the stock generators remain separate work.
- A visible on-module indication for CC-lane capacity overflow would improve recording feedback.
