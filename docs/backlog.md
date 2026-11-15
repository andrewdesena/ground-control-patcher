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

## Editor UX pass (v1.1)
Shipped: drag-select rectangle + Delete/Backspace, auto-load project/pattern on dropdown change, unsaved-change prompt with browser draft, save/load toasts, Clear Track moved into the track toolbar, backup pruning.

Still open:
- Left sidebar as a real file navigator (projects > tracks > patterns) instead of dropdowns.
- Per-note ties: the stock pattern format stores TIE as a step-level modifier, so one chord note cannot tie independently of others. Doing this needs a new per-note field and firmware support.
