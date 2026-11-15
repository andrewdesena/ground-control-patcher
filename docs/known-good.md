# Known-good poly build

Last hardware-confirmed build: **`71957a3`** (10-site bundle).

- Output file: `gc-v3.26_poly-v1.1.hex`
- SHA-256: `226f824becd040e315e0bed269fe77571dc31d62584f954098bbd4b32dad0454`
- Size: 713,490 bytes
- Site commit currently serving it: `f9cd51f`

Hardware-confirmed behavior:

- Project C / Pattern A plays the saved C-E-G chord (60/64/67).
- Tracks 2/3 stay quiet when cleared.
- Module save, power-cycle, reload, and replay keep the chord.

Not in this build:

- EDIT-mode chord key lights.
- Module-only lifecycle cache/async loader (regressed playback; parked).
- Save-gating and ProjectSettings JSON fixes.

Rules for the next attempt:

1. Start from this exact bundle. Do not replace the loader/fan-out architecture wholesale.
2. Change one behavior at a time behind a diagnostic flash.
3. Hardware acceptance for every flash: chord plays, save survives power-cycle, no extra-track blinks.
4. Keep a card backup under `~/Downloads/gc-card-backups/` before any save test.
