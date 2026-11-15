# Next session prompt

Use this at the start of a new session.

---

Project: `/Users/andrewdesena/gc-modder` (Endorphin.es Ground Control v3.26 polyphony patcher + editor).

Current hardware baseline:
- Tag `known-good-poly` = commit `71957a3`, 10-site bundle. This exact build is flashed and confirmed.
- Output `gc-v3.26_poly-v1.1.hex`, SHA-256 `226f824becd040e315e0bed269fe77571dc31d62584f954098bbd4b32dad0454`.
- Confirmed: Project C / track 1 / pattern A plays C-E-G; module save + power-cycle + reload keeps the chord; explicit clear + save + power-cycle is silent; pattern A/B switching keeps the chord.
- Do NOT ship the current main-branch 38-site lifecycle bundle. It regressed playback and is parked. The public index is the known-good 10-site build.

Primary task: fix live project switching.
- Bug: switch Project C -> A -> B -> C while playing. On return to C, track 1 plays only C (mono) until a power-cycle.
- Pattern switching inside a project is fine.
- Likely cause: project switch reuses cached pattern RAM and never re-runs the `poly<letter>` sidecar loader hook at `0x0801CD96` (cave `0x08047C00`, known-good source in git tag `known-good-poly`).
- Required: hook the project-select path (find the real stock caller with REA/Capstone, do not guess) and reload the destination project/track/letter sidecar for all three melodic tracks after the switch, without touching the boot playback path or running SD I/O inside the audio callback.
- Acceptance: C -> A -> B -> C returns with the chord intact, no stuck notes, no track 2/3 blinks, then save + power-cycle still works.

Related open items:
1. Product cleanup: remove **Write to SD** from the public patcher. Make **Download** primary. Keep the descriptive filename `gc-v3.26_poly-v1.1.hex`. Document copy-to-card + eject. The browser writing a long name directly into FAT created invalid LFN entries and stale flashes; downloading then copying avoids it.
2. EDIT chord key lights: source/test exists (`poly-editlights`) but is pulled. The first attempt read `parent+0x2DF` (inside stored pattern B) instead of the input-manager edit cursor and omitted `active_letter*0x194`. Fix the source read, add real-caller tests for letters A/X and non-zero steps, then hardware-test.
3. ProjectSettings JSON: the shared string at `0x08036E50` must NOT be patched (`"]"` is expected by suffix callers and drum serialization breaks). If revisited, patch only the private leading newline at `0x08036E53` and add an emitted-ProjectSettings JSON parse test.
4. Lifecycle/async cache: parked. On hardware the async worker never populated the chord bank, causing mono. Do not revive it wholesale. If needed later, add one behavior at a time with a hardware diagnostic build.
5. Test harness: lifecycle tests model FatFS; they are not proof of boot/worker behavior. Every firmware claim needs a hardware acceptance step.

Workflow rules:
- Codex (gpt-6.1-sol) is code consultant during planning/building and QA before any flash. Loop until it returns SAFE TO FLASH.
- Back up `projectC` (pattern + sidecar) before save tests; backups live in `~/Downloads/gc-card-backups/`.
- Card protocol: fsck if filenames look wrong, use an 8.3-safe name (`GCV326P.HEX`) for test flashes, `sync`, then `diskutil unmount` before exiting storage.
- Verify: `python3 tools/verify.py mods/v1-poly-full.json`; run all relevant `tools/test_*.py`; browser build sanity check.
- Do not commit or deploy a bundle that has not passed the hardware gate.
