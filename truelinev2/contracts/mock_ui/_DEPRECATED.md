# DEPRECATED — superseded contract mock UI

**The old contract mock UI is superseded by the preserved Fable v2 UI bones in
`C:\Nova\projects\trueline-web-experience`. It may remain only as a historical contract fixture if
tests require it; it is not the product UI direction.**

- Lane: `TRUELINE_V2_UI_FABLE_PRESERVE_AND_MOCK_UI_RETIRE` (2026-06-19).
- Authoritative UI base + directive: [`wiki/ui/fable_v2_ui_bones.md`](../../../wiki/ui/fable_v2_ui_bones.md).
- This folder (`redline_manifest_mock.html` / `.css` / `.js`) is a **Phase-1 throwaway preview** that
  proved the manifest shape was renderable. It is **not** the visual/function base for the product.

## Why it still exists (do not treat as active UI)

`truelinev2/tests/test_redline_manifest_mock_ui_contract.py` still uses these files as a **historical
contract fixture** — it cross-checks the example manifest's truth (log3 owner-confirmed, log14
covered-by-log10, the 7 blocked unlock-requirements, advisory warnings, placeholder artifacts). That
guard is worth keeping, so the files are retained here rather than deleted. **Do not** extend, restyle,
or build on this UI. Future web work (Phase 2K+) adapts the **Fable** surfaces in
`trueline-web-experience` to the durable redline-manifest contract via the Phase-2J read-only consumer
(`truelinev2/contracts/published_bundle_consumer.py`).
