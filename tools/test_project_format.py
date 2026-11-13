#!/usr/bin/env python3
"""
test_project_format.py — steps2 codec tests (pure Python, no emulator).

Covers: note-name round-trip, steps2 round-trip with notes AND a multi-CC bank,
legacy "steps" fallback, and steps2 precedence over legacy.

  python3 tools/test_project_format.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import project_format as pf


def main():
    fails = 0
    def check(label, got, exp):
        nonlocal fails
        ok = got == exp
        fails += 0 if ok else 1
        print(f"  {label:34} {'OK' if ok else 'FAIL got='+str(got)+' exp='+str(exp)}")

    # 1. note-name helpers
    check("C4 -> 60", pf.name_to_midi("C4"), 60)
    check("A4 -> 69", pf.name_to_midi("A4"), 69)
    check("C#4 -> 61", pf.name_to_midi("C#4"), 61)
    check("60 -> C4", pf.midi_to_name(60), "C4")
    rt_ok = all(pf.name_to_midi(pf.midi_to_name(n)) == n for n in range(12, 108))
    check("name<->midi roundtrip 12..107", rt_ok, True)

    # 2. model with a chord + multi-CC bank on one step
    steps = [
        {"modifier": 0, "notes": [[60, 100], [64, 90], [67, 80]],
         "cc": [[1, 64], [2, 10], [11, 100], [74, 20], [71, 90]]},
        {"modifier": 2, "notes": [[48, 70]], "cc": [[74, 55]]},
        {"modifier": 0, "notes": [], "cc": []},
    ]

    # 3. steps2 round-trip
    proj = pf.project_with_steps2({"step_limit": [32]}, steps)
    back, src = pf.decode(proj)
    check("encode uses steps2", src, "steps2")
    check("chord preserved", back[0]["notes"], [[60, 100], [64, 90], [67, 80]])
    check("multi-CC preserved", back[0]["cc"], [[1, 64], [2, 10], [11, 100], [74, 20], [71, 90]])
    check("modifier preserved", [s["modifier"] for s in back], [0, 2, 0])
    check("empty step preserved", back[2]["notes"], [])

    # 4. legacy emitted alongside (for old firmware)
    check("legacy steps present", "steps" in proj, True)
    check("legacy note is name", proj["steps"][0]["note"], "C4")   # lowest = 60
    check("legacy ratchets present", "ratchets" in proj, True)

    # 5. legacy-only project falls back to 'steps'
    legacy = {"steps": [
        {"note": "C4", "velocity": 100, "modifier": 0},
        {"note": "E4", "velocity": 90, "modifier": 1},
    ], "ratchets": [0, 2]}
    back2, src2 = pf.decode(legacy)
    check("legacy source", src2, "steps")
    check("legacy note->midi", [s["notes"] for s in back2], [[[60, 100]], [[64, 90]]])
    check("legacy modifier", [s["modifier"] for s in back2], [0, 1])
    check("legacy cc empty", all(s["cc"] == [] for s in back2), True)

    # 6. steps2 wins when both present
    both = dict(legacy)
    both["steps2"] = pf.encode_steps2([{"modifier": 5, "notes": [[72, 1]], "cc": [[7, 7]]}])
    _, src3 = pf.decode(both)
    check("steps2 precedence", src3, "steps2")

    # 7. capacity caps
    big = [{"modifier": 0, "notes": [[40 + i, 1] for i in range(30)],
            "cc": [[i, i] for i in range(30)]}]
    nb, _ = pf.decode({"steps2": pf.encode_steps2(big)})
    check("note cap", len(nb[0]["notes"]), pf.MAX_NOTES)
    check("cc cap", len(nb[0]["cc"]), pf.MAX_CC)

    print('PASS' if not fails else f'FAIL ({fails})')
    return 0 if not fails else 1


if __name__ == '__main__':
    sys.exit(main())
