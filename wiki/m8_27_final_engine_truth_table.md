# M8.27: Final all-58 Engine Truth Table + Completion Map

Status: **SHIPPED (proof-only); adversarially audited FAITHFUL.** One
authoritative completion map for the full Brenham corpus. Joins the three
shipped truth surfaces per bore without altering any of them. Census frozen
`25/13/5/5/4/3/1/2 = 58`; no placement/stroke/PNG/segment/AUTO change.

Proof: `truelinev2/proof/run_final_engine_truth_table.py` (G1–G15 PASS)
Tests: `truelinev2/tests/test_final_engine_truth_table.py` (8, offline)
Artifact (gitignored): `data/outputs/final_engine_truth_table/` (`.json` + `.md`
hold the full 58-row table + the group card)
Audit: M8.27 faithfulness workflow — 6/6 bucket audits + invariants FAITHFUL;
one blocking finding (log11) fixed; two cosmetic nits + two sound-challenge
tweaks deliberately NOT gold-plated.

## Three orthogonal axes (the table carries all three)

1. **PRODUCT axis (authoritative):** M8.11 reviewer service, `fullest_safe_review`
   mode (M8.5 + M8.8 opt-ins) → exactly one M8.10 `ReviewerLane` per bore. This
   is product truth (what the reviewer does). Transcribed verbatim.
2. **ROUTE-STROKE axis (proof-only):** the M8.14.c symbol_conduit lane status —
   can a route-FOLLOWING red stroke be drawn? The lane is **default-OFF and
   UNWIRED**; `STROKE_ELIGIBLE_REVIEW` is a graded proof artifact, **never** a
   product placement. The axes are independent (log59 is stroke-eligible yet a
   product PICK_CARD; log8/32/42 are product PLACED yet stroke STRUCTURE_IDENTITY).
3. **GROUP axis (separate surface):** the M8.20 shared-alignment card (log8 +
   log32). It is the **59th review item** — members keep their unchanged per-bore
   lane; the card is never folded in.

`completion_bucket` is a derived UI-readiness VIEW over the contract lane (a
pure function; it never rewrites the M8.10 lane).

## 58 vs 59 — resolved

Exactly **58 production bore logs** (files `log2..log72`, 13 numbering gaps —
log1/13/17/18/20/21/22/24/26/28/33/34/35/40 — no duplicates, none missing within
the present set). The **59th** is the M8.20 group-review card. `58 per-bore + 1
group card = 59 review items`.

## Counts

| product lane (M8.10/M8.11) | n | → completion bucket | n |
|---|--:|---|--:|
| PLACED_REVIEW | 30 | DRAWABLE_REVIEW | 30 |
| PICK_CARD_ROUTE_SUGGESTION | 16 | PICK_CARD_REVIEW | 17 |
| HUMAN_ADJUSTABLE_LENGTH_REDLINE | 6 | HUMAN_ADJUSTABLE_REVIEW | 6 |
| OUT_OF_CLASS | 4 | SOURCE_OR_KMZ_REQUIRED | 3 |
| SOURCE_REVIEW_REQUIRED | 2 | SOURCE_REVIEW_REQUIRED | 2 |
| — | — | (GROUP_REVIEW, separate) | 1 |

PICK_CARD_REVIEW = 17 = 16 product pick-cards + log11 (an OUT_OF_CLASS bore whose
M8.7 verdict is `MULTIPLE_PATHS_PICK_CARD` — a routing-order pick-card, see
below). OUT_OF_CLASS (4) refines to 3 SOURCE_OR_KMZ (log43/log44/log68) + 1
pick-card (log11).

**Headline (UI readiness):**
- drawable now (product placement): **30**
- review-ready (placed / pick / adjustable): **53**
- source/KMZ/owner review: **5** (log37/log38 unparseable; log43/log44 source
  re-read; log68 no matchline equation → geo/KMZ)
- engine-law/doctrine required: **4** — and **ZERO** at the product level. The 4
  (log7/log8/log32/log42) place a redline NOW; only their proof-only
  route-FOLLOWING stroke needs new doctrine (a strand discriminator for log7; an
  origin/structure-identity binder for log8/32/42).
- proof-only route strokes (graded PASS, NOT product placements): **4**
  (log25/log51/log59/log65).

## Key reconciliations (gated)

- **log8/log32/log42:** product **PLACED_REVIEW** (exact box footage) + stroke
  **STRUCTURE_IDENTITY_BINDING_REQUIRED**; log8/log32 are group-card members,
  log42 correctly excluded.
- **log43/log44:** product OUT_OF_CLASS + stroke END_IDENTITY_UNPRINTED →
  **SOURCE_OR_KMZ_REQUIRED** (M8.25 source-quality / source-vs-plan).
- **END_IDENTITY_UNPRINTED (25):** the M8.26 honest-negative — none drew a route
  stroke; their product disposition spans DRAWABLE (placed) / PICK / ADJUSTABLE /
  SOURCE per the orthogonal product axis.
- **default_baseline** unchanged (24 placed); **stroke census** unchanged
  (25/13/5/5/4/3/1/2); M8.10/M8.11/M8.14.c/M8.20 contracts untouched.

## The one audit fix (log11)

The audit caught log11 mis-bucketed `ENGINE_LAW_REQUIRED` (a false "wait for a new
solver" signal). Verified at source: log11's M8.7 verdict is
`MULTIPLE_PATHS_PICK_CARD` (two genuinely PRINTED parallel intervals, zero rival
frames); it lands in OUT_OF_CLASS only because M8.7 runs before the M8.9
pick-card classifier (routing order), not because it is hard — the identical
situation ships as a product PICK_CARD for log36/log59/log66. Re-bucketed to
**PICK_CARD_REVIEW** (review-eligible NOW); an engine auto-pick discriminator is
an optional later enhancement, not a precondition. Gated by G15.

## Next completion step before UI

The table makes UI readiness unambiguous: **53 bores are review-ready today**
(30 drawable placements + 23 pick/adjustable interactions) and the group card is
a 59th surface. No engine doctrine blocks any PRODUCT disposition. The single
remaining engine lever is the proof-only route-FOLLOWING stroke for 4 placed
bores (log7 strand discriminator; log8/32/42 origin-identity binder) — an
enhancement, not a UI precondition. The recommended next step before UI is to
wire the M8.11 reviewer bundle + the M8.20 group card into the consumer
(authorized API/route), not more engine doctrine.

## Boundary

Proof-only; reads M8.10/M8.11/M8.14.c/M8.20 + the symbol_conduit lane, changes
none of them. No UI/web/mobile/production/deploy; no placement-logic change; no
geometry/strokes; no tolerance widening; no AUTO; no family relation as placement
proof; census + all contracts frozen.
