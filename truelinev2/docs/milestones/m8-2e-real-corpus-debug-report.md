# M8.2e — v2 real-corpus debug report (for Patrick review)

**Status:** read-only debug artifact for human inspection. Default behavior unchanged
(23/58); the M8.2d **NOT_SAFE** result is re-confirmed. No engine / `decide.py` /
default-`run_match` change; no product claim; outputs under gitignored `data/outputs/`.

## What it is

`truelinev2/proof/run_real_corpus_debug_report.py` runs the v2 matcher over the real Brenham
corpus TWICE per bore — DEFAULT (`frame_graph=None`, the shipped engine) and OPT-IN (the real
PDF-derived `FrameGraph`) — and writes a human-readable report
(`data/outputs/real_corpus_debug_report.{json,md}`) explaining, per selected log: what the
engine did, why it placed/abstained, the default chain's callout spans, each cross-sheet
transition **classified** as `continuous_station` / `reset_equation` /
`reset_equation_offset_mismatch` / `ambiguous_*`, the frame evidence found, the missing
evidence, and a link to the existing m5 grading-crop PNG to check visually.

## Key finding (visible per-log in the report)

- DEFAULT `AUTO_SELECT=14 REVIEW=9 ABSTAIN=33 ERROR=2 PLACED=23`; OPT-IN `AUTO_SELECT=6
  REVIEW=9 ABSTAIN=41 ERROR=2 PLACED=15` → **8 regressions, 0 improvements**.
- **All 8 regressed logs' cross-sheet transitions classify as `continuous_station`
  (raw_gap ≈ 0 ft, no frame edge).** The M8.2c Step-2 opt-in rule wrongly *required* a frame
  edge for these continuous multi-sheet runs and therefore broke them — the report shows it
  line-by-line (e.g. `log2 s18->s19: continuous_station (raw_gap=0.0ft, safe_edge=False)`).
- **log11 [5,17]:** safe frame edge present, translated link possible, **but still ABSTAIN**
  (`NO_AUTHORED_BOX_MATCH_FOR_BORE_SPAN`) — the edge resolves the cross-frame LINK, but the
  anchor/box/footage evidence is still missing. No AUTO promotion.

## What Patrick should review visually

- Open the `grading crop` PNGs the report links for the regressed AUTO placements
  (`data/outputs/truelinev2/m5_brenham/*.png`) and confirm they are correct continuous
  multi-sheet runs that the frame rule must NOT break.
- Confirm log11's two sheets are a genuine matchline reset (sheet 5 STA 3+23 ≡ sheet 17 STA
  0+69, offset 254 ft) and that no single authored box matches its span.

## Recommended next implementation step

Replace the binary same-sheet/cross-sheet rule with a TRANSITION CLASSIFIER:
`continuous_station` → keep the raw link (do NOT require an edge); `reset_equation` →
translate through the safe edge; `ambiguous_*` → abstain. Re-run M8.2d and require ALL 23
current placements preserved before any default activation. log11 separately needs
anchor/box/footage evidence beyond the frame edge.

## NOT proven by this report

Not product readiness, not zero false placements, not frame-activation safety. Frame
translation remains **INACTIVE** in the default/real path. Placements are not visually graded
here — the crops must be opened to verify. No customer-facing claim.
