# Target #30 — Positioned AP-Glyph Reconstruction (default-OFF, read-only)

**Mission:** recover positioned AP-number glyph clusters so scrambled AP labels (esp. AP-166)
become geometry targets for Primitive B/C — without guessing.

**VERDICT: PRIMARY GOAL ACHIEVED — AP-166 IS safely localizable.** The Target #29 "glyph floor"
is broken: the problem was never that AP-166's glyphs are scrambled — its `1`,`6`,`6` chars are
present and correctly ordered (forensic: clean `166` char triples on sheet 10). The failure was
Primitive A's greedy clustering **over-merging** dense AutoCAD callout digits. Valid-AP-subsequence
extraction with structure anchoring recovers AP-166 at centroid **[793.8, 161.4]** with zero false
clusters and all regression APs preserved.

**Endpoint 136→166 still NOT auto-recovered** — but for a precise, advanced reason (see §4):
AP-166 is now a valid target, but it sits 45 px from STA 1+36 in a SEPARATE vector component, so
binding it over the local AP-125 would be guessing. Honest abstain.

> Read-only. Pure helpers; isolated in `scripts/`; no engine import-as-production, no flag, no
> STATE, no placement. Helper `scripts/pdf_ap_glyph_reconstruct.py` → `.json`/`.out`.

---

## 1. Root cause (why Target #29 saw no `166` cluster)

Forensic on sheet 10: `166` appears as clean, correctly-ordered char triples (e.g. @ (790,161),
(862,554)). Primitive A's clusterer merges all x-adjacent same-line digits, so in dense callout
text `166` gets swallowed into a longer run (`…21660…`) and never emerges as the exact token. The
glyphs were **localizable all along** — the extraction method was wrong, not the data.

## 2. Method (valid-AP-subsequence + structure anchoring, deterministic)

`reconstruct_positioned_aps(chars, words, valid_ap_ids)`:
1. Build digit runs (same y-band, x-adjacent chars), keeping per-char positions.
2. In each run, every contiguous **3-char substring equal to a valid AP id (105–168)** → candidate
   with centroid + bbox. (3-digit only — 2-digit dimensions like `11`/`12` ignored.)
3. **Structure anchor:** keep a candidate only if a `TERMINAL`/`PORT`/`HH`/`AP` token is within
   34 px — rejects station/dimension/matchline/sheet numbers that aren't near AP structures.
4. **Station exclusion:** drop a candidate whose centroid coincides (≤8 px) with a `STA n+nn`
   callout center.
5. A run with ≥2 distinct anchored valid-AP substrings → **abstain** (`ambiguous_multiple_valid_ap_in_run`).

Output: `{ap_id, centroid, bbox, confidence, reason, anchor}` positioned AP targets.

## 3. Grade (deliverable 3) — primary + regressions

| AP | role | result | centroid | anchor |
|---|---|---|---|---|
| **166** | **PRIMARY** | **LOCALIZED** | [793.8, 161.4] | structure-anchored |
| 163 | regression | LOCALIZED (kept) | [327.6, 305.1] | — |
| 157 | regression | LOCALIZED (kept) | [1055.5, 350.1] | — |
| 165 | regression | LOCALIZED (kept) | [663.4, 187.7] | — |

**No false AP clusters** from station numbers, matchlines, dimensions, or sheet labels (anchor +
station-exclusion gates; ambiguous runs abstain). Self-test confirms dimension rejection and
ambiguous-abstain.

## 4. Primitive C re-grade with the reconstructed AP-166 target (deliverable 4)

```
STA 1+36 <-> AP-166 centroid [793.8,161.4]: straight=45px  shared_vector_component=False
=> STILL ABSTAIN (endpoint 136->166 NOT auto-recovered)
```

The blocker has **advanced**, not vanished: AP-166 is now a real geometry target, but STA 1+36 and
AP-166 are in **different vector components** 45 px apart, and the LOCAL structure at STA 1+36 is
AP-125 (Target #28). Choosing AP-166 over the adjacent AP-125 without a connecting run polyline
would be guessing — so the pipeline abstains on the endpoint while **trusting neither 125 nor 166**
(both are review-only). This fully honors "do not trust AP-125 for STA 136 if AP-166 is the actual
far-end label."

## 5. Machine-readable reasons (deliverable 5)

Per target: `valid_ap_subsequence_structure_anchored` (localized),
`ambiguous_multiple_valid_ap_in_run` (abstain). Endpoint re-grade: explicit
`shared_vector_component=False` + straight-line distance. All in `pdf_ap_glyph_reconstruct.json`.

## 6. Safety posture

- **No degradation:** Target #27/#28/#29 endpoint TRUST set is untouched (this helper only adds
  positioned AP targets; it does not alter endpoint trust). Gate APs 163/157/165 still localized.
- **No guessing / no false clusters:** anchor + station + 3-digit-only gates; ambiguous runs abstain.
- **Placement-free / read-only:** lives in `scripts/`, no engine import, no flag, no STATE.
- Self-test `python scripts/pdf_ap_glyph_reconstruct.py selftest` → `SELFTEST_OK`.

## 7. Verdict + next target

The glyph-localizability floor is cleared — **AP numbers are now positionable as geometry
targets**, including the previously-unreachable AP-166. The remaining 136→166 gap is now a pure
**run-component bridging** problem: STA 1+36 and AP-166 are 45 px apart in separate components.
Next:
1. **Component-bridge / run-polyline span** — connect a STA callout to a localized AP target that
   is *close but in a separate component* ONLY when a single bored-run polyline (not hatch) spans
   the gap; abstain on branch/hatch. This is the precise, final unlock for the 136→166 class.
2. Feed the reconstructed positioned AP targets into Primitive B/C as the canonical AP universe
   (replacing the looser digit-cluster scan), then extend sheets 8/10 → 8–14.
Still placement-free; DO-NOT-WIDEN intact.

## 8. Files read
- `Brenham - Phase 5_07-15-25.pdf` sheets 8 & 10 (`page.chars`/words/`lines`/`curves`; read-only).
- `scripts/pdf_run_endpoint_extractor.py` (Prim A), `scripts/pdf_leader_run_following.py` (Prim B) — reused pure.
- Target #27/#28/#29 reports. Helper: `scripts/pdf_ap_glyph_reconstruct.py` → `.json`/`.out`.
