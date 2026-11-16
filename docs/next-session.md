# Next session prompt

Use this at the start of a new session.

---

Project: `/Users/andrewdesena/gc-modder` (Endorphin.es Ground Control v3.26 polyphony patcher + editor).

Hardware baseline (what users get today):
- Tag `known-good-poly` = commit `71957a3`, 10-site bundle; `index.html` embeds exactly these bytes (v1.1).
- Output `gc-v3.26_poly-v1.1.hex`, SHA-256 `226f824becd040e315e0bed269fe77571dc31d62584f954098bbd4b32dad0454`.
- Confirmed: Project C / track 1 / pattern A plays C-E-G; save + power-cycle + reload keeps the chord; explicit clear + save + power-cycle is silent.
- Do NOT ship the main-branch 38-site lifecycle bundle (regressed playback, parked).

Where the project-switch fix stands:
- `docs/project-switch-preload.md` holds the full stock map. Read it first.
- v1.2 (publish from the pattern-loader hook `0x0801CD96`) was rejected by Codex QA and reverted.
- v1.3 candidate: `mods/poly-commit-reload.source.json` -> `mods/v1-poly-commit.json` (12 sites)
  -> `gc-v3.26_poly-v1.3.hex` and `GCV326P.HEX`, sha256
  `bfbc532780dc68b402212dbbc822dd9e906fb9fb41ea3542223dee0537c6cc1a`, 714,263 bytes.
  Hooks `0x08021528`, the per-track call to the stock letter select `0x08023158` inside the
  playback-start routine `0x080214F8`, i.e. after the deferred commit `0x08021338` has staged
  the incoming project. It then republishes `/project<L>/track<n>/poly<L>` into bank
  `0x1000B530 + n*0x880` for melodic tracks (`[track+0x2D] == 1`). Cost-gated on the switch flag
  `0x2000C5D8` or a letter change; `FR_NO_FILE` zeroes the bank, any other FRESULT leaves it alone.
- Status: independent adversarial review returned `VERDICT: SAFE TO FLASH` with no must-fix items
  (Codex itself was quota-blocked, so the gate ran as a delegated reviewer against the same
  checklist). `tools/test_poly_commit_reload.py` green (13 assertions, including one that runs the
  real `0x08023158`), `tools/verify.py` clean, browser engine == python image byte for byte.
  `index.html` is untouched and still serves v1.1.

Next steps, in order:
1. DONE 2026-11-15: v1.3 passed all four hardware tests (cold-boot chord, C->A->B->C while
   playing, save + power-cycle, clear + power-cycle) and is embedded in `index.html`.
2. Next: hardware-test v1.4 (`GCV326Q.HEX`, sha256 `aba41b1b...`) for the EDIT chord key lights.
   v1.4 = the confirmed v1.3 sites plus the lights cave, so only the lights need testing.
3. Re-run a Codex gate when its quota resets, for the record.
4. If the switch still stutters: the review flagged up to 3 x 2176-byte reads in the UI event path
   per commit while `0x2000C5D8` stays up. Tighten the gate before touching anything else.

Still open (do not claim these as working):
- EDIT chord key lights: a v2 attempt (`mods/poly-editlights2.source.json`) exists but was rejected
  on review - its edit-cursor address `0x20006000` is referenced nowhere in the image, its test
  writes that state itself and never enters through the hook, and it lacks an EDIT-mode gate so it
  would light stray keys during playback. See the review section at the end of
  `docs/prompt-edit-lights.md`.
- Save cave `0x08047E00` indexes banks by pattern **letter** (`r7*0x880`, lookup at `0x0801C45A`, skip at `0x08047E08`), not by track: letter 0 == bank 0 only coincides for track 1 / pattern A. Fix before claiming persistence for other tracks or letters.
- Loader cave `0x08049000` still publishes whatever letter it loads and is bounded at pattern offset `0x4F0`, so letters D..Z never reach it. Now a cold-boot-only path.
- Fan-out `0x08047600` only checks primary-note membership (`0x08047672`), so a stale chord sharing the new pattern's primary note still emits extras.
- Product cleanup: remove **Write to SD** from the public patcher, make **Download** primary, document copy-to-card + eject (browser-written long LFN names caused invalid entries and stale flashes).
- EDIT chord key lights: source/test exists (`poly-editlights`) but pulled; it read `parent+0x2DF` instead of the input-manager edit cursor and omitted `active_letter*0x194`.
- ProjectSettings JSON: never patch the shared string at `0x08036E50`; only the private newline at `0x08036E53`.
- `tools/test_poly_module_only.py` (parked lifecycle suite) already fails on main at its index.html JSON parse; repair it to parse the JS literal and compare against the shipped bundle.

Tooling:
- `tools/build_v1.py` rebuilds the shipped bundle from `mods/v1-poly-known-good.json` + EXTRA source files; `--check-html` proves `index.html` matches.
- `tools/test_poly_commit_reload.py` and `tools/test_poly_activegate.py`: unicorn harnesses that execute installed hook addresses with a FatFS model.
- Node engine check: apply a bundle through `src/hexfile.js` + `src/mods.js` and diff against `tools/apply.py` output.

Workflow rules:
- Codex (gpt-6.1-sol) is consultant during planning/building and QA before any flash; loop until SAFE TO FLASH. Tell it not to trust the brief. It rate-limits: a long review can die with "usage limit" and no verdict, so keep the prompt tight or split the review.
- Back up `projectC` (pattern + sidecar) before save tests; backups live in `~/Downloads/gc-card-backups/`.
- Card protocol: fsck if filenames look wrong, 8.3-safe name (`GCV326P.HEX`) for test flashes, `sync`, then `diskutil unmount`.
- Do not commit or deploy a bundle that has not passed the hardware gate.
