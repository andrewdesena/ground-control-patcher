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

## Features (v1)

- 3 tracks, 16-128 steps, scrollable piano roll with octave shift.
- Click to place/remove a note at the current velocity; each step holds a full chord.
- CC lane: pick a CC number + value, click a step to set it (right-click clears). A step holds many
  distinct CC numbers.
- Export JSON: `{steps2:[{modifier,notes:[[midi,vel]],cc:[[num,val]]}...], steps:[legacy]}`.
- Import: reads `steps2` or legacy `steps`.

## Roadmap

- Drag-paint notes/velocity; per-note velocity lane.
- Multi-lane CC view (all CC numbers at once).
- Song/pattern chaining; tempo.
- Direct exporters for `/projectX` and `/projectX/trackD` file shapes once their exact schema is
  confirmed from the firmware.
