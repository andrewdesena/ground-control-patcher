#!/usr/bin/env python3
"""Generate projectC / pattern A with chords on all three melodic tracks.

Writes only the files a chord needs (patternA.txt + polyA per track) into
./card-staging/projectC/, ready to copy onto the SD card in storage mode.

Drum left alone. Note names follow the firmware: oct = midi//12 - 2, so
MIDI 60 is "C3" and MIDI 45 is "A2". Empty steps carry the "G8#" sentinel with
velocity 0, and `count` is the real pattern length (never 0 when notes exist).

Music: i - VI - III - VII in A minor, one chord per beat over a 16-step bar.
  bar 1: Am    bar 2: F     bar 3: Dm    bar 4: E7
Track 1 plays low triads on beats 1 and 3, track 2 mid voicings on the offbeats,
track 3 answers up high on beats 2 and 4. Nothing lands on the same step twice,
so each track reads clearly on its own.
"""
import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'card-staging' / 'projectC'
SIZE = 2176
STEPS = 16

NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']


def note_name(midi):
    n = NAMES[midi % 12]
    octave = midi // 12 - 2
    return f'{n[0]}{octave}#' if n.endswith('#') else f'{n}{octave}'


# i - VI - III - VII, voiced per track
LOW = [[45, 48, 52],      # Am: A2 C3 E3
       [41, 45, 48],      # F : F2 A2 C3
       [38, 41, 45],      # Dm: D2 F2 A2
       [40, 44, 47]]      # E : E2 G#2 B2
MID = [[57, 60, 64, 67],  # Am7 : A3 C4 E4 G4
       [53, 57, 60, 64],  # Fmaj7: F3 A3 C4 E4
       [50, 53, 57, 60],  # Dm7 : D3 F3 A3 C4
       [52, 56, 59, 62]]  # E7  : E3 G#3 B3 D4
HIGH = [[69, 72, 76],     # Am: A4 C5 E5
        [65, 69, 72],     # F : F4 A4 C5
        [62, 65, 69],     # Dm: D4 F4 A4
        [64, 68, 71]]     # E : E4 G#4 B4

# step -> chord index, per track
TRACKS = [
    ('track1', LOW,  {0: 0, 4: 1, 8: 2, 12: 3}, 100),
    ('track2', MID,  {2: 0, 6: 1, 10: 2, 14: 3}, 92),
    ('track3', HIGH, {3: 0, 7: 1, 11: 2, 15: 3}, 84),
]


def pattern(chords, hits):
    steps = []
    for i in range(STEPS):
        if i in hits:
            chord = chords[hits[i]]
            steps.append({'note': note_name(chord[0]), 'velocity': 100,
                          'modifier': 0, 'ratchet': 0})
        else:
            steps.append({'note': 'G8#', 'velocity': 0, 'modifier': 0, 'ratchet': 0})
    return {'step_limit': STEPS, 'count': STEPS, 'duration': 2,
            'Polyrhythm': {'From': 4, 'To': 4}, 'steps': steps}


def sidecar(chords, hits, velocity):
    buf = bytearray(SIZE)
    for step, which in hits.items():
        chord = sorted(chords[which])
        buf[step * 17] = len(chord)
        for k, midi in enumerate(chord[:8]):
            buf[step * 17 + 1 + k * 2] = midi & 0x7F
            buf[step * 17 + 2 + k * 2] = velocity & 0x7F
    return bytes(buf)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name, chords, hits, vel in TRACKS:
        d = OUT / name
        d.mkdir(exist_ok=True)
        pat = pattern(chords, hits)
        (d / 'patternA.txt').write_text(json.dumps(pat, indent=1) + '\n')
        (d / 'polyA').write_bytes(sidecar(chords, hits, vel))
        print(f'{name}: steps {sorted(hits)} -> ' +
              ', '.join(f'{s}:{"-".join(note_name(m) for m in sorted(chords[w]))}'
                        for s, w in sorted(hits.items())))
        # cross-check: the pattern's note must be the record's first note
        for step, which in hits.items():
            want = sorted(chords[which])[0]
            first = sidecar(chords, hits, vel)[step * 17 + 1]
            assert first == want, (name, step, first, want)
            assert pat['steps'][step]['note'] == note_name(want), (name, step)
    print(f'wrote {OUT}')


if __name__ == '__main__':
    main()
