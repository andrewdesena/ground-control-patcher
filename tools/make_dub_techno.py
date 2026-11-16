#!/usr/bin/env python3
"""Dub techno pass: projectC / pattern A.

D minor, i - VI - iv - V (Dm7 - Bbmaj7 - Gm7 - A7) across 16 steps.

  track 1  poly chords   offbeat skanks on 2, 6, 10, 14 (the "and" of each beat)
  track 2  mono bass     roots on 1 and the "and" of 2, walking D - Bb - G - A
  track 3  poly lead     two sparse high stabs, room left to jam
  track D  drums         four on the floor, snare on 2 and 4, offbeat hats, rim answers

Note names use the firmware convention (oct = midi//12 - 2). Empty steps carry the
G8# sentinel; the pattern's primary note is always the chord's lowest note, which
is what the fan-out's membership test requires.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'card-staging' / 'projectC'
SIZE, STEPS = 2176, 16
NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']


def note_name(midi):
    n = NAMES[midi % 12]
    o = midi // 12 - 2
    return f'{n[0]}{o}#' if n.endswith('#') else f'{n}{o}'


# i - VI - iv - V in D minor
DM7 = [50, 53, 57, 60]      # D3 F3 A3 C4
BBMAJ7 = [46, 50, 53, 57]   # Bb2 D3 F3 A3
GM7 = [43, 46, 50, 53]      # G2 Bb2 D3 F3
A7 = [45, 49, 52, 55]       # A2 C#3 E3 G3

CHORDS = [(DM7, 2), (BBMAJ7, 6), (GM7, 10), (A7, 14)]      # offbeat skanks
# his bass synth is tuned down two octaves, so write in the octave he already validated
BASS = [(50, 0), (50, 3), (58, 4), (58, 7), (55, 8), (55, 11), (57, 12), (57, 15)]
LEAD = [([65, 69, 74], 5), ([64, 67, 73], 13)]             # F A D / E G C#

KICK, SNARE, HAT, RIM = 0, 1, 2, 4                          # pad rows (notes 38,40,41,45)
DRUM = [(KICK, 0, 120), (KICK, 4, 120), (KICK, 8, 120), (KICK, 12, 120),
        (SNARE, 4, 100), (SNARE, 12, 100),
        (HAT, 2, 62), (HAT, 6, 62), (HAT, 10, 62), (HAT, 14, 62),
        (RIM, 7, 78), (RIM, 15, 78)]


def melodic(chords, velocity):
    """chords: list of (notes, step). Returns (pattern dict, sidecar bytes)."""
    steps, buf = [], bytearray(SIZE)
    hits = {s: c for c, s in chords}
    for i in range(STEPS):
        if i in hits:
            chord = sorted(hits[i])
            steps.append({'note': note_name(chord[0]), 'velocity': velocity,
                          'modifier': 0, 'ratchet': 0})
            buf[i * 17] = len(chord)
            for k, midi in enumerate(chord[:8]):
                buf[i * 17 + 1 + k * 2] = midi & 0x7F
                buf[i * 17 + 2 + k * 2] = velocity & 0x7F
        else:
            steps.append({'note': 'G8#', 'velocity': 0, 'modifier': 0, 'ratchet': 0})
    return ({'step_limit': STEPS, 'count': STEPS, 'duration': 2,
             'Polyrhythm': {'From': 4, 'To': 4}, 'steps': steps}, bytes(buf))


def mono(notes, velocity):
    """Single-note line: still a valid one-note chord record, so nothing else fires."""
    return melodic([([n], s) for n, s in notes], velocity)


def drum_pattern():
    rows = [[128] * STEPS for _ in range(8)]
    for pad, step, vel in DRUM:
        rows[pad][step] = vel
    return {'step_limit': [STEPS] * 9, 'count': STEPS, 'steps': rows,
            'ratchets': [[0] * STEPS for _ in range(8)]}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    tracks = [('track1', melodic(CHORDS, 100), 'chords, offbeat skanks'),
              ('track2', mono(BASS, 110), 'mono bass, D-Bb-G-A'),
              ('track3', melodic(LEAD, 88), 'two sparse high stabs')]
    for name, (pat, poly), role in tracks:
        d = OUT / name
        d.mkdir(exist_ok=True)
        (d / 'patternA.txt').write_text(json.dumps(pat, indent=1) + '\n')
        (d / 'polyA').write_bytes(poly)
        hits = [i for i, s in enumerate(pat['steps']) if s['velocity'] > 0]
        print(f'{name}: {role}')
        print('   ' + ', '.join(
            f'{s}:{" ".join(note_name(poly[s*17+1+2*k]) for k in range(poly[s*17]))}'
            for s in hits))

    dd = OUT / 'trackD'
    dd.mkdir(exist_ok=True)
    dpat = drum_pattern()
    (dd / 'patternA.txt').write_text(json.dumps(dpat, indent=1) + '\n')
    names = ['kick', 'snare', 'hat', 'clap', 'rim', 'pad6', 'pad7', 'pad8']
    print('trackD: drums')
    for pad in range(8):
        hits = [i for i, v in enumerate(dpat['steps'][pad]) if v != 128]
        if hits:
            print(f'   {names[pad]:5s} {hits}')
    print(f'wrote {OUT}')


if __name__ == '__main__':
    main()
