# RAM budget (stock v3.26)

From the C startup (reset handler at `0x08030C14`), which copies `.data` and zeroes `.bss`.

| region | range | size |
|--------|-------|------|
| `.data` (SRAM) | `0x20000000`–`0x20001A40` | 6,720 B |
| `.bss` (SRAM)      | `0x20001A40`–`0x2001D074` | 112,180 B |
| SRAM slack (stack) | `0x2001D074`–`0x20020000` | 12,172 B (stack, grows down from top) |
| CCM `.data`        | none (copy length 0) | 0 |
| CCM `.bss`         | `0x10000000`–`0x1000B52C` | 46,380 B |
| **CCM free**       | `0x1000B52C`–`0x10010000` | **~18.7 KB** |

- Init SP = `0x20020000` => **128 KB main SRAM** (STM32F405/407-class), plus **64 KB CCM** at `0x10000000`.
- Main SRAM is effectively full; the only slack is the 12 KB stack gap (shared with heap).
- The one real pocket is **~18.7 KB of CCM**. A `malloc` exists in the build ("REENT malloc
  succeeded"), so confirm heap placement before planting arrays there.

## Footprint of the polyphonic arrays

Per step: notes `1 + 2*CAPN` bytes, CC `1 + 2*CAPC` bytes.

| CAP (notes/cc) | bytes/step | 128 steps x 3 tracks |
|----------------|-----------|----------------------|
| 8 / 8          | 34        | ~12.8 KB |
| 10 / 8         | 38        | ~14.3 KB |
| 16 / 16        | 66        | ~24.8 KB |

**Decision:** CAP = 8 notes + 8 CC per step (~12.8 KB) fits the CCM pocket; 16/16 does not.
8 simultaneous notes is ample for chords; 8 distinct CCs covers a controller bank. Could raise CC
cap independently if needed.

## Next check before wiring

Confirm the CCM heap region (`_sbrk` limit / linker `end`) so the poly arrays do not collide with
the allocator. If CCM is contested, fall back to overlaying the legacy single-note step arrays
(delta = (CAPN-1) bytes/step) plus a sparse CC store.
