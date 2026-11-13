# GC Pattern Editor

A static, no-build visual pattern editor for Endorphin.es Ground Control projects. Place notes on a
piano roll (chords allowed per step), draw a CC bank, and export `steps2` JSON. It mirrors the
`tools/project_format.py` format, and exports the legacy single-note `steps` alongside for old
firmware.

## Run locally

```
python3 -m http.server 8931 --bind 127.0.0.1
# open http://127.0.0.1:8931/docs/editor/index.html
```

(Opening via `file://` works in a normal browser; a server is only needed if a browser blocks
`file://`.)

## Publish (GitHub Pages)

Repo settings -> Pages -> Source: "Deploy from a branch" -> branch `main`, folder `/docs`.
The editor is then at `https://<user>.github.io/gc-modder/editor/`.

## Features (v2)

- **4 tracks**: 1-3 melodic (piano roll) + **Track D = 8 drum lanes** (X0X triggers).
- **Steps 1-128** (device supports up to 128 since v3.14).
- Piano roll: click to place/remove notes at current velocity; each step holds a full chord.
- CC lane per melodic track: pick CC# + value, click a step (right-click clears). Many CCs per step.
- **Settings drawer**: Global/project (BPM, clock src/div, reset mode, LEDs, MIDI routing incl.
  4-channel TX/RX/omni, forwarding, snap algo, buzzer), per-track (scale/root, direction, shuffle,
  humanize, ratchet, gate, slide, arp, modulation, polyrhythm), and Ext CV 1-4 (type/param).
- Export a **complete project JSON**: global + cv[4] + tracks (scale/settings/arp/polyrhythm +
  `steps2` + legacy `steps` + ratchets) + drum (8 lanes/map/triggers).
- Import reads `steps2` or legacy `steps`.

Schema source: `docs/project-schema.md` (reconstructed from firmware JSON strings + v3 manual).

## Roadmap

- Drag-paint notes/velocity; per-note velocity lane.
- Multi-lane CC view (all CC numbers at once).
- Song/pattern chaining; tempo.
- Direct exporters for `/projectX` and `/projectX/trackD` file shapes once their exact schema is
  confirmed from the firmware.
