# Backlog

## Chord mode: one key triggers a MIDI chord

Idea from Drew, 2026-11-13. Not started.

- Polyphony can only leave the module over MIDI: CV/gate are one pitch + one gate per track.
  CV and gate follow the chord root; the extra notes go out as MIDI note-ons on the track channel.
- Preferred UX: a dedicated CHORD mode, not replacing the generators.
  - Enter/leave with a long-press of `GEN` (or `TRACK` + a key), so generator behavior is unchanged
    when the mode is off.
  - In CHORD mode, each piano key triggers a stored chord shape; generator controls (or PAGE/knobs)
    select quality (maj/min/7/sus) and inversion.
  - 8 chord slots per track, stored in the same format as the existing per-step chord record
    (count + note/velocity pairs), so no new file format.
- Implementation sketch: hook the key-press path used by step entry; when CHORD mode is on, emit each
  interval through the existing MIDI out path instead of a single note. Gate stays on the root.
- Open questions: per-track vs global chord memory; how chord mode interacts with step recording and
  live record; whether the 7-segment display shows the chord quality.

## Pattern generators

Drew finds the stock generators not very musically useful and is open to tuning them. Deferred until
after chord mode; capture concrete examples of what is wrong before changing behavior.

## Next up (after module-only lifecycle)

- **EDIT-mode chord key lights:** pulled from the flash bundle. The first integration used `parent+0x2DF`
  (inside stored pattern B) instead of the input-manager cursor and omitted `active_letter*0x194`, so it
  lit the wrong keys on non-A patterns. Source and tests remain for a correct integration.
- **ProjectSettings JSON:** the shared-format-string comma patch was reverted; suffix callers expect
  `"]"`, and it corrupted drum-scale JSON. Needs private punctuation or caller-specific strings plus an
  emitted-output parsing test.
- **Concurrency hardening:** save/flush generation validation, publication serialization against inline
  clear/held transpose, queue-capacity-before-cancel, and 8-byte mutex stack alignment are integrated and
  QA-passed. Per-ratchet chord retriggers are intentional and retained.
- **Hardware bench pass:** read-only/full card, missing sidecar, project switch while playing, pattern
  copy/delete, clear then save then power-cycle.
- **Editor transport limits:** compact JSON serialization is still pending; `patternA.txt` sits close to
  the 10,200-byte loader cap when pretty-printed.
- **Chord mode:** one key triggers a stored chord shape over MIDI, entered with a long-press of `GEN`.
  Not started; design notes above.
- **Per-note ties:** stock format stores TIE at the step level, so independent chord-note ties need a
  new per-note field and firmware support.

## Editor UX pass (v1.1)
Shipped: drag-select rectangle + Delete/Backspace, auto-load project/pattern, unsaved-change prompt with browser draft, save/load toasts, Clear Track in the track toolbar, backup pruning, Project → Track → Pattern collapsible navigator, drag-copy between tracks/projects, note-clear, CC lanes, velocity shading.

Still open:
- Per-note ties: the stock pattern format stores TIE as a step-level modifier, so one chord note cannot tie independently of others. Doing this needs a new per-note field and firmware support.
