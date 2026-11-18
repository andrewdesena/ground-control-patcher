# Documentation

[Open firmware tool](../index.html) · [Open editor](../index.html#editor) · [Repository](https://github.com/andrewdesena/ground-control-patcher) · [Support](https://github.com/andrewdesena/ground-control-patcher/issues)

## Current user documentation

- [Installation, warnings and rollback](reference/guide.html)
- [Editor controls, file workflow and CC recording](reference/editor.html)
- [Quick installation card](reference/quick-card.html)
- [Features, improvements and release status](releases.md)
- [Pattern format and firmware compatibility](project-schema.md)
- [CC candidate implementation and hardware acceptance](cc-automation.md)

Printable guides are generated from the current HTML pages. The confirmed firmware baseline is v0.9.0. The CC candidate is v0.10.0-alpha.1 and still needs physical testing. No affiliation with Endorphin.es; support belongs in this repository.

## Historical research

The remaining technical notes record investigations and previous builds. Their version-specific statements, proposed features and sidecar references are historical evidence, not current product instructions. In particular, `poly-persistence.md`, `polyphony-capture.md`, `project-switch-preload.md`, `known-good.md`, `clock-analysis.md`, `ram-budget.md` and `led-bitmap.md` should be read with their original version context.

The original RAM-budget document predates the current chain scratch areas and CC allocation. The current allocation is in [CC implementation](cc-automation.md#memory-and-timing). Older audit/generator scripts that expect separate sidecars are development tools for legacy card data and are not used by the web editor.
