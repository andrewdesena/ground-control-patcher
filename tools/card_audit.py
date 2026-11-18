#!/usr/bin/env python3
"""Audit and repair Endorphin.es Ground Control SD card project data.

Read-only unless --repair is given. Exit codes: 0 clean, 1 errors, 2 warnings only.
Layout: project<L>/track{1,2,3}/pattern<L>.txt plus poly<L>, and project<L>/trackD/pattern<L>.txt.
poly<L> is 128 records of 17 bytes: a count byte then up to 8 (note, velocity) pairs.
Note byte 0x80 is the empty step sentinel, written in JSON as "G8#". Firmware before v1.9
could save a foreign chord bank here, leaving random count and note bytes.
"""

import argparse
import json
import os
import re
import shutil
import sys

POLY_SIZE, REC_SIZE, MAX_NOTES, EMPTY_NOTE = 2176, 17, 8, 128
TRACKS = ("track1", "track2", "track3", "trackD")
NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
FLATS = {"Db": 1, "Eb": 3, "Gb": 6, "Ab": 8, "Bb": 10}
POLY_RE = re.compile(r"^poly([A-Z])$")
PAT_RE = re.compile(r"^pattern([A-Z])\.txt$")
PROJ_RE = re.compile(r"^project[A-Z]$")
SEV = {"error": "errors", "warning": "warnings", "info": "infos"}


def new_entry(rel):
    return {"file": rel, "errors": [], "warnings": [], "infos": []}


def add(entry, sev, check, msg):
    entry[SEV[sev]].append((check, msg))


def note_to_midi(name):
    """Name to MIDI with the firmware convention oct = midi // 12 - 2."""
    s = str(name).strip()
    if s in ("G8#", "G#8"):
        return EMPTY_NOTE
    if not s:
        return None
    acc = s[-1] if s[-1] in "#b" else ""
    m = re.match(r"^([A-G])(-?\d+)$", s[:-1] if acc else s)
    if not m:
        raise ValueError("bad note name %r" % name)
    letter, octave = m.group(1), int(m.group(2))
    if acc == "b" and letter + "b" in FLATS:
        pc = FLATS[letter + "b"]
    elif acc == "b":
        raise ValueError("bad note name %r" % name)
    else:
        pc = NAMES.index(letter + acc)
    midi = (octave + 2) * 12 + pc
    if not 0 <= midi <= 127:
        raise ValueError("note %r is outside MIDI 0..127" % name)
    return midi


def check_poly(data, rel, entry):
    """Validate one poly sidecar and return its 128 records, or None."""
    if len(data) != POLY_SIZE:
        add(entry, "error", "poly-size", "size %d, expected %d" % (len(data), POLY_SIZE))
        return None
    records = []
    for k in range(128):
        off, count = k * REC_SIZE, data[k * REC_SIZE]
        if count > MAX_NOTES:
            add(entry, "error", "poly-count", "record %d count %d, valid range 0..8 (garbage chord data)" % (k, count))
            records.append(None)
            continue
        notes = [(data[off + 1 + 2 * i], data[off + 2 + 2 * i]) for i in range(count)]
        for i, (note, vel) in enumerate(notes):
            if note > 127:
                add(entry, "error", "poly-note", "record %d note %d byte %d is invalid" % (k, i, note))
            if vel > 127:
                add(entry, "error", "poly-vel", "record %d velocity %d is out of range 0..127" % (k, vel))
        if count and notes[0][1] == 0:
            add(entry, "warning", "poly-zero-vel", "record %d has count %d but its first velocity is 0" % (k, count))
        records.append(notes)
    return records


def read_json(path, rel, entry):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError) as exc:
        add(entry, "error", "json", "cannot parse as JSON: %s" % exc)
        return None


def check_melodic(path, rel, entry, strict_count=False):
    """Validate one melodic pattern. Returns [(midi, velocity)] or None."""
    doc = read_json(path, rel, entry)
    if doc is None:
        return None
    steps, limit, count = doc.get("steps"), doc.get("step_limit"), doc.get("count")
    if not isinstance(steps, list):
        add(entry, "error", "pattern-steps", "missing or non-list steps")
        return None
    if not isinstance(limit, int) or not 1 <= limit <= 128:
        add(entry, "error", "pattern-limit", "step_limit %r is not an int in 1..128" % (limit,))
    elif len(steps) != limit:
        add(entry, "error", "pattern-limit", "steps length %d does not equal step_limit %d" % (len(steps), limit))
    if count != len(steps):
        if strict_count:
            add(entry, "error", "pattern-count", "steps length %d does not equal count %r" % (len(steps), count))
        else:
            add(entry, "info", "pattern-count",
                "count %r differs from steps length %d (play counter, not array length)" % (count, len(steps)))
    out = []
    for i, st in enumerate(steps):
        if not isinstance(st, dict):
            add(entry, "error", "pattern-step", "step %d is not an object" % i)
            out.append(None)
            continue
        try:
            midi = note_to_midi(st.get("note", ""))
        except ValueError as exc:
            add(entry, "error", "pattern-note", "step %d: %s" % (i, exc))
            out.append(None)
            continue
        vel = st.get("velocity", 0)
        if not isinstance(vel, int) or not 0 <= vel <= 127:
            add(entry, "error", "pattern-vel", "step %d velocity %r is out of range 0..127" % (i, vel))
            vel = 0
        if midi is None and vel > 0:
            add(entry, "error", "pattern-note", "step %d has an empty note but velocity %d" % (i, vel))
        out.append(None if midi is None else (midi, vel))
    return out


def cross_check(steps, records, entry):
    """Compare each pattern step with the sidecar record at the same index."""
    for i, step in enumerate(steps):
        if step is None or records[i] is None:
            continue
        midi, vel, notes = step[0], step[1], records[i]
        if vel > 0 and midi != EMPTY_NOTE:
            if not notes:
                add(entry, "warning", "pattern-mono",
                    "step %d note midi %d but sidecar record %d is empty, plays mono" % (i, midi, i))
                continue
            values = [n for n, _ in notes]
            lowest = min(values)
            # Cards mix firmware names (MIDI 60 = C3) with editor names (MIDI 60 = C4);
            # accept the same note one octave either side.
            if lowest in (midi, midi - 12, midi + 12):
                continue
            if midi in values or midi - 12 in values or midi + 12 in values:
                add(entry, "warning", "pattern-root",
                    "step %d pattern midi %d is not the lowest sidecar note (lowest %d)" % (i, midi, lowest))
            else:
                add(entry, "warning", "pattern-chord", "step %d pattern midi %d missing from sidecar record %d (%s), wrong chord"
                    % (i, midi, i, ",".join(str(v) for v in values)))
        elif notes:
            add(entry, "warning", "pattern-ghost",
                "step %d is empty but sidecar record %d holds %d notes" % (i, i, len(notes)))
    for i in range(len(steps), 128):
        if records[i]:
            add(entry, "warning", "pattern-orphan",
                "sidecar record %d is populated beyond pattern length %d" % (i, len(steps)))


def check_drum(path, rel, entry):
    doc = read_json(path, rel, entry)
    if doc is None:
        return
    limit = doc.get("step_limit")
    if not (isinstance(limit, list) and len(limit) == 9 and all(isinstance(v, int) for v in limit)):
        add(entry, "error", "drum-limit", "step_limit must be a list of 9 ints")
    else:
        for i, v in enumerate(limit):
            if not 1 <= v <= 128:
                add(entry, "error", "drum-limit", "step_limit[%d] = %d out of range 1..128" % (i, v))
    rows = doc.get("steps")
    if not (isinstance(rows, list) and len(rows) == 8):
        add(entry, "error", "drum-rows", "steps must be 8 rows")
        return
    widths = set()
    for r, row in enumerate(rows):
        if not isinstance(row, list):
            add(entry, "error", "drum-rows", "row %d is not a list" % r)
            continue
        widths.add(len(row))
        for i, v in enumerate(row):
            if not isinstance(v, int) or not (v == 128 or 0 <= v <= 127):
                add(entry, "error", "drum-value", "row %d step %d value %r is neither 128 nor 0..127" % (r, i, v))
    if len(widths) > 1:
        add(entry, "error", "drum-width", "rows differ in length: %s" % sorted(widths))
    elif widths and max(widths) > 128:
        add(entry, "error", "drum-width", "rows hold %d steps, maximum is 128" % max(widths))
    ratchets = doc.get("ratchets")
    if ratchets is not None and (not isinstance(ratchets, list) or len(ratchets) != 8):
        add(entry, "error", "drum-ratchets", "ratchets must be 8 rows")
    count = doc.get("count")
    if not isinstance(count, int) or not 0 <= count <= 128:
        add(entry, "error", "drum-count", "count %r is not an int in 0..128" % (count,))


def audit_card(root, strict_count=False):
    """Walk project*/track* and return per-file entries sorted by path."""
    entries = {}
    for proj in sorted(os.listdir(root)):
        if not PROJ_RE.match(proj):
            continue
        for track in TRACKS:
            tdir = os.path.join(root, proj, track)
            if not os.path.isdir(tdir):
                continue
            steps = {}
            for name in sorted(os.listdir(tdir)):
                path = os.path.join(tdir, name)
                if not os.path.isfile(path) or name.startswith("."):
                    continue
                rel, pm, po = os.path.relpath(path, root), PAT_RE.match(name), POLY_RE.match(name)
                if not (pm or (po and track != "trackD")):
                    continue
                entry = entries[rel] = new_entry(rel)
                if pm and track == "trackD":
                    check_drum(path, rel, entry)
                elif pm:
                    steps[pm.group(1)] = check_melodic(path, rel, entry, strict_count)
                elif po:
                    with open(path, "rb") as fh:
                        records = check_poly(fh.read(), rel, entry)
                    pair = steps.get(po.group(1))
                    if records is not None and None not in records and pair is not None:
                        cross_check(pair, records, entry)
    return [entries[k] for k in sorted(entries)]


def summarize(entries):
    errors = sum(len(e["errors"]) for e in entries)
    warnings = sum(len(e["warnings"]) for e in entries)
    return {"files": len(entries), "errors": errors, "warnings": warnings,
            "exit_code": 1 if errors else (2 if warnings else 0)}


def print_report(root, entries, stream=sys.stdout):
    print("CARD %s" % root, file=stream)
    for e in entries:
        nerr, nwarn = len(e["errors"]), len(e["warnings"])
        state = "ERROR" if nerr else ("WARN" if nwarn else "OK")
        print("%-54s %-5s errors=%d warnings=%d" % (e["file"], state, nerr, nwarn), file=stream)
        for check, msg in e["errors"]:
            print("    ERROR %s: %s" % (check, msg), file=stream)
        for check, msg in e["warnings"]:
            print("    WARN  %s: %s" % (check, msg), file=stream)
    s = summarize(entries)
    print("TOTAL %d files, %d errors, %d warnings -> exit %d"
          % (s["files"], s["errors"], s["warnings"], s["exit_code"]), file=stream)


def audit_backup(rel, src, strict_count):
    """Structural audit of a single backup file, with no card context."""
    entry = new_entry(rel)
    if os.path.basename(os.path.dirname(rel)) == "trackD":
        check_drum(src, rel, entry)
    elif os.path.basename(rel).startswith("poly"):
        with open(src, "rb") as fh:
            check_poly(fh.read(), rel, entry)
    else:
        check_melodic(src, rel, entry, strict_count)
    return entry


def plan_repairs(card_root, backup_root, entries, strict_count):
    plan = []
    for e in entries:
        if not e["errors"]:
            continue
        rel = e["file"]
        src = os.path.join(backup_root, rel)
        dirty = audit_backup(rel, src, strict_count)["errors"] if os.path.isfile(src) else None
        if dirty is None:
            action, reason = "skip", "no backup copy"
        elif dirty:
            action, reason = "skip", "backup copy is dirty too (%s)" % dirty[0][0]
        elif os.path.realpath(src) == os.path.realpath(os.path.join(card_root, rel)):
            action, reason = "skip", "same file as card copy"
        else:
            action, reason = "restore", "backup copy passes structural checks"
        plan.append({"file": rel, "action": action, "source": src, "reason": reason})
    return plan


def apply_repairs(card_root, plan):
    for item in plan:
        if item["action"] != "restore":
            continue
        dst = os.path.join(card_root, item["file"])
        saved = os.path.join(card_root, ".audit-repair-backup", item["file"])
        os.makedirs(os.path.dirname(saved), exist_ok=True)
        shutil.copy2(dst, saved)
        shutil.copy2(item["source"], dst)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Audit and repair a Ground Control SD card.")
    ap.add_argument("card_root", help="mounted card or copied card image directory")
    ap.add_argument("--repair", metavar="BACKUP_ROOT", help="restore files with errors from a backup card")
    ap.add_argument("--dry-run", action="store_true", help="with --repair, print the plan only")
    ap.add_argument("--json", action="store_true", dest="as_json", help="machine-readable output")
    ap.add_argument("--strict-count", action="store_true", help="also treat pattern count != steps length as an error")
    args = ap.parse_args(argv)

    card_root = os.path.abspath(args.card_root)
    if not os.path.isdir(card_root):
        print("error: %s is not a directory" % card_root, file=sys.stderr)
        return 1
    before = audit_card(card_root, args.strict_count)
    report = {"card_root": card_root, "files": [dict(e, clean=not e["errors"]) for e in before],
              "summary": summarize(before)}
    plan, after = None, None
    if args.repair:
        backup_root = os.path.abspath(args.repair)
        if not os.path.isdir(backup_root):
            print("error: backup root %s is not a directory" % backup_root, file=sys.stderr)
            return 1
        plan = plan_repairs(card_root, backup_root, before, args.strict_count)
        if not args.dry_run:
            apply_repairs(card_root, plan)
            after = audit_card(card_root, args.strict_count)

    final = after if after is not None else before
    code = summarize(final)["exit_code"]
    report["exit_code"] = code
    if args.as_json:
        if plan is not None:
            report["repair_plan"] = plan
        if after is not None:
            report["summary_after"] = summarize(after)
            report["files_after"] = [dict(e, clean=not e["errors"]) for e in after]
        print(json.dumps(report, indent=2))
        return code

    print_report(card_root, before)
    if plan is not None:
        print("\nREPAIR PLAN from %s%s" % (args.repair, " (dry run, nothing changed)" if args.dry_run else ""))
        if not plan:
            print("  no files need repair")
        for item in plan:
            print("  %-8s %s: %s" % (item["action"].upper(), item["file"], item["reason"]))
        if after is not None:
            print("")
            print_report(card_root, after)
    return code


if __name__ == "__main__":
    sys.exit(main())
