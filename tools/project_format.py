#!/usr/bin/env python3
"""
project_format.py — reference codec for the polyphonic step key `steps2`.

New key (ours): each step is
    { "modifier": m, "notes": [[midi, vel], ...], "cc": [[ccnum, val], ...] }
Notes are integer MIDI numbers; CC is an arbitrary list of (cc#, value) pairs, so a step
can hold a whole controller bank (capped at MAX).

Backward compat: when writing we ALSO emit the legacy single-note "steps" array
([{ "note": "C4", "velocity": v, "modifier": m }, ...]) and "ratchets", so old firmware
still loads the project. The reader prefers "steps2" and falls back to legacy "steps".

Note-name convention for legacy emit/parse: middle C = MIDI 60 = "C4".
"""
MAX_NOTES = 16
MAX_CC = 16
NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def midi_to_name(n):
    n = int(n)
    return f"{NOTE_NAMES[n % 12]}{n // 12 - 1}"


def name_to_midi(s):
    s = s.strip()
    pc = NOTE_NAMES.index(s[:-1]) if s[:-1] in NOTE_NAMES else NOTE_NAMES.index(s[:-2])
    octave = int(s[-1])
    return (octave + 1) * 12 + pc


def _norm_step(st):
    return {
        "modifier": int(st.get("modifier", 0)),
        "notes": [[int(n), int(v)] for n, v in st.get("notes", [])][:MAX_NOTES],
        "cc": [[int(c), int(v)] for c, v in st.get("cc", [])][:MAX_CC],
    }


def encode_steps2(steps):
    """Model -> steps2 array (integer notes + cc lists)."""
    return [_norm_step(st) for st in steps]


def encode_legacy(steps):
    """Model -> (legacy steps array of single-note objects, ratchets array)."""
    legacy_steps, ratchets = [], []
    for st in steps:
        notes = st.get("notes", [])
        # representative single note: the lowest held note (deterministic)
        note = min((int(n) for n, _ in notes), default=None)
        vel = next((int(v) for n, v in notes if int(n) == note), 0) if note is not None else 0
        legacy_steps.append({
            "note": midi_to_name(note) if note is not None else "",
            "velocity": vel,
            "modifier": int(st.get("modifier", 0)),
        })
        ratchets.append(int(st.get("ratchet", 0)))
    return legacy_steps, ratchets


def project_with_steps2(base, steps):
    """Return base project dict updated with BOTH steps2 and legacy steps/ratchets."""
    out = dict(base) if base else {}
    out["steps2"] = encode_steps2(steps)
    legacy_steps, ratchets = encode_legacy(steps)
    out["steps"] = legacy_steps
    out["ratchets"] = ratchets
    return out


def decode(project):
    """Project dict -> (model steps, source_key). Prefers steps2; falls back to legacy."""
    if project.get("steps2"):
        return [_norm_step(s) for s in project["steps2"]], "steps2"
    steps = []
    ratchets = project.get("ratchets", [])
    for i, s in enumerate(project.get("steps", [])):
        raw = s.get("note")
        if isinstance(raw, str):
            note = name_to_midi(raw) if raw else None
        else:
            note = raw
        notes = [[int(note), int(s.get("velocity", 0))]] if note is not None else []
        steps.append({
            "modifier": int(s.get("modifier", 0)),
            "notes": notes,
            "cc": [],
            "ratchet": int(ratchets[i]) if i < len(ratchets) else 0,
        })
    return steps, "steps"
