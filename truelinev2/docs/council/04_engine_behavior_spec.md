# Engine Behavior Spec — Redline Placement Confidence & Honesty (v2)

> **Role of this document.** The behavior contract for how the v2 placement engine *should* decide
> where a redline goes, how confident it is allowed to claim to be, and when it must abstain. It is
> grounded in (a) the engine-correctness audit of the live code on HEAD `9ee706a`, and (b) the public
> HDD/fiber plan-set research corpus (`02_public_web_research_corpus.md`).
>
> **What this is NOT.** It is not a redesign of the deterministic recognizer and it does not invent
> customer geometry. The public corpus supplies *patterns and tests*, never placement truth. The
> deterministic **50/58 drawn-redline frontier MUST NOT change**; the renderer, fixtures, anchors,
> coordinates, the backend truth path, `origin/main`, and deploy are out of scope for any "do-now"
> recommendation here.
>
> **The honesty north star.** Confidence must be *earned*, never *displayed*. A band is a claim about
> evidence the engine actually has — not a polish layer on a guess. "HTTP 200 is not proof," and a HIGH
> band is not proof either: HIGH must be unreachable on linework the engine cannot disambiguate.

---

## 0. The two lanes (what exists today, restated honestly)

The engine has two structurally separate placement lanes. This spec governs both, but holds them to
*different* ceilings because they rest on *different* evidence.

| Lane | Fires when | Evidence basis | Max honest band | Source of truth |
|---|---|---|---|---|
| **A. Named-dialect recognizer** (`run_match` → `decide_by_extent` / `decide_by_containment` / footage chains) | A registered dialect (Brenham footage, ODOT containment+extent) recognizes the plan | The bore route is **already drawn** in a parseable convention; the bore log carries footage/span | `AUTO_SELECT` only on a tight, unique drawn extent; else `REVIEW`; else honest `ABSTAIN` | This is the **deterministic 50/58 frontier**. UNTOUCHED. |
| **B. Generic name-free fallback** (`GenericGeometryDialect` + `_place_generic` / `_score_bore_run` / `_confidence`) | NO named dialect recognizes the plan AND the named path placed nothing drawable | Reconstructed run from generic vector geometry + a fitted station-label axis; the bore is **inferred**, not annotated | `REVIEW` only, confidence capped `< 0.86`; **never** `AUTO` | A job-local `1/1` bundle. NEVER summed into the 50/58 frontier. |

The hard separation is verified in the audit: the generic dialect is never in `_DIALECTS`
(`extract/registry.py:16`) and only constructed in `_run_engine` after the named path declines
(`uploaded_corpus_engine_handoff.py:440-449`). **This separation is a strength to preserve, not a gap.**

---

## 1. Confidence bands — required evidence per band

Bands map onto the existing buckets in `GENERAL_PLACEMENT_DESIGN_WIP.md` and the research corpus
Section 3 checklist. The **band names mean the same thing in both lanes**; what differs is the maximum
band each lane may *reach*. The unifying rule:

> A band is a statement about **endpoint location + corroboration + uniqueness**, in that priority
> order. Coverage of the bore span dominates; a beautifully linear axis or a red stroke can never lift
> a band on its own.

### 1.1 HIGH — both endpoints independently located, geometry corroborated, no rival
A HIGH placement asserts: *"I know which drawn feature is this bore, and independent evidence agrees."*
HIGH requires **all** of:

- **Both endpoints are named, located features** (entry/exit pit, bore/receiving pit, Begin/End Station
  rows) — research P2; OR a tight unique drawn extent whose endpoints match the bore-log start/end
  within tolerance (named-dialect `decide_by_extent` AUTO case).
- **Span coverage near-full**: the selected drawn run covers `≥ 0.90` of the bore span
  (`_GENERIC_HIGH_COVER`), AND extent fit `≥ 0.80`.
- **Uniqueness**: zero plausible rival runs (`fragments == 0`) and zero near-tied competitors
  (`competition == 0`); not placed on a full-sheet alignment baseline.
- **Independent corroboration**: length agrees with stated footage / pay-item LF within tolerance
  (research P10/P16), and where present, KMZ total route length agrees (WIP confidence input). KMZ
  corroborates length **only** — it never sets PDF coordinates (WIP invariant).
- Plan + profile both present and consistent (P1); install method explicit (P5); diameter consistent
  with the method's range and the cover-by-diameter table (P7/P8).

**Lane ceiling.** In **Lane A** (named), a tight unique drawn extent is the *only* legitimate `AUTO`
case and it is the frontier. In **Lane B** (generic), HIGH is reserved for a near-full, tight,
rival-free, non-baseline run — the clean single-bore case. **Per finding §3.2 below, Lane B HIGH on a
real plan is structurally unreachable (always 5–13 rival fragments) and is therefore a demo-only band
that must be additionally gated or relabeled.**

### 1.2 MEDIUM (0.50–0.75) — endpoints located, corroboration partial
A MEDIUM placement asserts: *"I'm fairly sure where this is, but one corroboration leg is missing."*
MEDIUM requires:

- Endpoints named/located, but **only one stationing dialect** present, OR length check within a looser
  band, OR profile present without plan (or vice versa) (corpus §3 MEDIUM).
- Station anchors present but sparse near one endpoint (one endpoint interpolated).
- Install method inferred from linetype/legend rather than stated; diameter/cover not independently
  confirmed.
- A *single* corroboration source (length OR KMZ OR scope tally) agrees, not all.
- Coverage `≥ ~0.70` AND `fragments == 0` AND `competition == 0` AND extent fit `≥ 0.60` (the
  "decent-but-partial" cap of `0.55` in `_confidence:383`).

### 1.3 LOW (< 0.50) — produce a candidate, but require/recommend correction
A LOW placement asserts: *"Here is my best honest guess; a human must verify or correct it."* The
engine **still emits a reviewable candidate** (this is the product value over a bare abstain), but
flags `CORRECTION_RECOMMENDED`. LOW is required when **any** of:

- One endpoint requires **extrapolation** beyond the station-anchor set (flag + cap).
- Axis residual high (`> 6.0 ft`, → `NOISY_STATION_AXIS`) or sparse anchors (`< 5 ticks`,
  → `SPARSE_STATION_LABELS`).
- `fragments ≥ 2` (3+ plausible co-linear runs over the span): cannot single out the bore from geometry
  alone → hard ceiling `0.45`.
- Partial coverage `< 0.85` (`_GENERIC_CONFIDENT_COVER`) without the decent-but-partial conditions.
- Method ambiguous; length disagrees with stated/pay-item beyond tolerance (possible wrong leg /
  parallel-run mix-up — corpus P14 + the v2 parallel-run discriminator doctrine).
- Multi-pull/multi-leg run where a joining pit/matchline is unmodeled (P11/P17): show the best
  continuous candidate, flag the unresolved joint.

### 1.4 ABSTAIN — insufficient evidence; emit a *specific* missing-evidence target
Per the v2 evidence-seeking doctrine, **ABSTAIN = unmodeled relationship, not impossible**. The engine
must name which checklist element is missing AND the next artifact that would resolve it — never a
silent or generic abstain. ABSTAIN is required when:

- No drawn run covers `≥ _GENERIC_MIN_COVER` (0.5) of the span on any single sheet
  (`NO_DRAWN_RUN_OVER_SPAN`) — better to abstain than to draw a line through < half the bore.
- No station anchors and no named endpoints on the relevant sheet → *"need plan-view station labels or
  a named entry/exit/pit token."*
- No bore-log span (`[start_ft, end_ft]`) to interpolate → *"need a reviewed bore-log row."*
- Endpoint named but unanchorable (no station, no offset-to-permanent-feature, no KMZ tie) → *"need a
  position reference for endpoint X (station / offset-to-feature / intersection name)."*
- Named-dialect coverage `< cover_min` (0.6) → `INSUFFICIENT_DRAWN_COVERAGE`; no overlapping drawn
  geometry → `NO_DRAWN_BORE_OVER_SPAN` (`decide_by_extent:65,70`).

**Required band-decision order (both lanes, normative):**
1. Is there enough evidence to place at all? No → **ABSTAIN** with a named missing element.
2. Compute coverage / extent / endpoint fit; apply ambiguity & axis penalties.
3. Apply hard ceilings (ambiguity ≥2 → 0.45; partial coverage cap; full-sheet baseline → 0.35).
4. Clamp to lane ceiling (Lane B: `< 0.86`, never AUTO).
5. Re-derive band from the clamped score; **demote HIGH→MEDIUM unless the strict HIGH predicate holds**
   (`_confidence:395-397`).
6. Set `correction_recommended` if band==LOW OR full_sheet OR fragments≥2 OR coverage partial.

---

## 2. How to use each evidence source

### 2.1 Station labels (the 1-D coordinate)
- Station labels printed along the route corridor are the **primary anchor**. Order anchors by
  `station_ft`; the station-ordered centers trace the route's bends dialect-free (WIP step 2). Fit a
  Theil-Sen axis (`extract/station_axis.fit_axis`); the residual is a linearity/monotonicity confidence
  signal — reject a fit noisier than `_AXIS_MAX_RESIDUAL_FT` (12 ft).
- Support the multi-dialect resolver (research H2/P3): engineering `NN+NN`; **station distance**
  (exit − entry = length, P3b); milepost+feet (`MP n + ffff ft`); station + perpendicular offset
  (`<dist>' <dir>/O CL`); offset-from-a-named-permanent-feature; and **named-structure endpoints**
  (intersection/facility) as first-class (Concord). Normalize all to the internal
  `(begin, end, side/offset, method, length)` tuple (Iowa schema, H2).
- **Length is a corroborating check, never a free input** (H1/P2). Prefer parsing explicit Entry/Exit
  + length over inferring endpoints from a drawn line.
- Cluster ticks to the **densest horizontal row** so stray title-block/general-note station references
  don't corrupt the axis (`generic_geometry._densest_tick_row`).

### 2.2 Bore-log spans
- The reviewed bore-log row `[start_ft, end_ft]` is the **authority for footage/span**; the plan
  confirms *where*, the log says *how long* (`overlap.py` header; `match/engine.py:84`).
- Clip the drawn stroke to the bore-log span projected onto the run via the axis
  (`clip_centerline_to_x`) so the redline spans **exactly** the bore, not the full run or a sheet-long
  baseline. This is why a near-tied fragment pick stays *locationally* correct even when LOW.
- The bore log gates engine-readiness: the engine never runs on un-reviewed raw rows
  (`_first_ready_rbl`, the product review gate).

### 2.3 Plan / profile notes
- Treat a bore as a **plan view + profile view pair** (research P1). The plan locates horizontally; the
  profile carries depth-of-cover, entry/exit angles, and the sag low point.
- **Parametric profile prior** (H5/P6): where a profile exists, model the bore as two endpoints +
  entry tangent (~12–14°) + sag (min radius) + exit tangent (~6–12°) + cover, in a vertical plane
  through the endpoints. Use it to **sanity-check, not set**, a plan-view candidate. A candidate
  violating the bend/approach-angle budget (P15, ≤180° total, ±30° vertical pull-box entry) is flagged.
- **Method + diameter sanity gate** (H4/P5/P8): carry install method per segment; validate diameter ∈
  method range (HDD 2–48", jack&bore 8–60", …) and depth-of-cover ≈ the cover-by-diameter table
  (2–6"→4ft; 8–15"→6ft; 16–24"→10ft; >24"→15ft). `≥30"` reclassifies toward tunnel/large-bore. A
  mismatch **lowers confidence; it never auto-corrects geometry.**
- A printed `BORE` / `DIRECTIONAL BORE` note within tolerance is **weak, name-free corroboration only**
  (`_nearest_bore_note`, `_GENERIC_BORE_NOTE_PT` 220pt). It is a *reason*, capped at `+0.05`; it can
  never lift a band past a hard ceiling.

### 2.4 KMZ route context
- KMZ/KML supplies route **context** on the Map page and a **length-corroboration** signal: compare KMZ
  total route length to the bore-log total span to nudge confidence (H11/P16).
- **KMZ never sets PDF pixel coordinates** — there is no PDF georeference (WIP §32). The Map redline
  overlay stays honestly BLOCKED until a real WGS84 redline exists. Length agreement raises confidence;
  disagreement beyond tolerance is a correction signal.

---

## 3. Avoiding ROW / utility / edge-of-pavement false positives

A real sheet fragments into ~150 thin co-linear runs — road centerline, ROW, pavement edge, utilities,
alignment — so the bore is one of many near-ties (audit, verified live). The defenses below are present
and **must be kept**; the spec adds two honest disclosures.

### 3.1 Defenses that exist and must stay
- **Alignment-band gate** (`_ALIGN_BAND` 260pt): only segments near the station-tick row are eligible.
- **Vertical-dominant rejection** (`dy > dx` → skip): tick marks and leaders never weld into a run.
- **Legend-block suppression** (`detect_legend_block` + `point_in_bbox`): keys/title blocks excluded.
- **Elongation + thickness gates** (`_MIN_ELONGATION` 4.0, `_MAX_RUN_THICKNESS_PT` 34pt): a bore is a
  thin line, not a box/blob/fill.
- **Full-sheet baseline penalty**: a run spanning `≥ 0.8` of the sheet station range is an alignment
  baseline, scored `× 0.35` and ceilinged to `0.35` with `PLACED_ON_FULL_SHEET_ALIGNMENT_LINE`.
- **Red is a weak tie-breaker only** (`+0.05`), never a promoter: 15/150 runs on the real ODOT sheet
  are red (verified), so red is not bore-exclusive (corpus: proposed construction is *often* but not
  *always* red).
- **Crossing-vs-longitudinal classifier** (H9/P14): a crossing sits near 90° at the crossed centerline;
  a longitudinal run holds a consistent centerline offset. Apply the matching geometry prior.

### 3.2 Required honest disclosures (the false-positive risk that remains)
- **Disclose near-tie selection.** On the real 71' bore the top-5 runs score 0.614/0.590/0.590/0.575/
  0.565 — within 0.05 — and the winner wins *only* on the red tie-breaker. This is acceptable **because
  the band is LOW + CORRECTION_RECOMMENDED and the stroke is clipped to the bore-log stations**, so the
  x-location is right even when the specific fragment is near-arbitrary. The spec **requires** surfacing
  the competition count (already computed) in the candidate warnings so the human knows the pick was one
  of N near-ties. Red must **never** exceed a pure tie-breaker.
- **Disclose the demo-HIGH gap.** HIGH is reachable on a contrived single-dominant-run plan (the
  rigged-demo scenario, audit §finding 2: synthesized signals yield `band=HIGH score=0.85
  correction_recommended=False`). Because Lane B is an *inference* with no annotation/CAD-layer evidence
  that the run **is** the bore, the spec requires one of: (a) cap Lane B at MEDIUM regardless of signals,
  OR (b) require independent corroboration beyond geometry (e.g. a directional-bore note within
  tolerance) before HIGH, OR (c) never render a Lane B HIGH without explicit "inferred — human must
  verify" framing. See gap G2.

---

## 4. Ambiguity, runner-ups, and human correction

### 4.1 Detecting ambiguity (must count over ALL overlapping runs)
- `fragments` = distinct non-baseline runs that *also* plausibly cover the span (`cover ≥
  _GENERIC_FRAG_COVER` 0.25). `competition` = placements scoring within `0.08` of the winner. Both are
  counted over **all overlapping runs**, not the cover-prefiltered set — fixing the prior bug that hid
  competition (`_place_generic:278-280`). **This is correct and must be kept.**
- `fragments ≥ 1` → `MULTIPLE_PLAUSIBLE_RUNS`, penalty `−0.12 × min(fragments,4)`.
  `fragments ≥ 2` → hard ceiling `0.45` (LOW). `competition ≥ 1` → `COMPETING_RUNS_NEAR_SCORE`,
  `−0.10 × min(competition,3)`.

### 4.2 Surfacing runner-up alternatives
- The engine emits up to `_GENERIC_MAX_ALTERNATIVES` (4) runner-up runs, best score first, each with
  `{from_sta, to_sta, sheet, score, cover, is_red}` (`_place_generic:293-295`). These feed the guided
  "Correct redline placement" step so a human can pick the intended line instead of trusting the
  geometry guess. **Requirement:** alternatives are *always* surfaced when `fragments ≥ 1` or
  `competition ≥ 1`, and the warnings must state the rival count.

### 4.3 Human correction supersedes the engine candidate
The correction lane is correct and must be preserved exactly:
- A human source-anchor correction calls `supersede_review_candidate_for_reviewed_bore_log`
  (`review_acceptance.py:324-359`): the engine candidate becomes `REVIEW_SUPERSEDED` and the
  human-confirmed render fills the job's redline slot. **A SUPERSEDED record is itself proof that a
  human correction — not the engine — is the placed redline.** It can supersede from CANDIDATE /
  REJECTED / ACCEPTED (clears the reject-first trap).
- The **export gate** (`product_workflow.export_gate` + `_review_gate:201-221`) blocks downloading a
  still-pending `REVIEW_CANDIDATE` or a `REVIEW_REJECTED` candidate; ACCEPTED, SUPERSEDED, and stale
  ABSTAINED all pass. This is the unified gate every export path shares. **A banked human grade is never
  overridden by the engine** (product-lanes doctrine).

---

## 5. Gap analysis — where today's engine diverges from this spec

Ordered by honesty severity. Each gap names the **smallest honest change** and confirms **zero frontier
risk** (Lane B / adapter / docs only; no engine/renderer/fixture/coordinate/`origin/main` change).

### G1 — Stale committed proof artifact shows HIGH 0.73 on a real plan (CONTRADICTS current code) — HIGH
**Spec divergence.** `data/outputs/.../generic_adapter_probe/report.json` (commit `96c0e10`) records
`placement confidence HIGH (0.73)` for the 71' ODOT bore and `MEDIUM (0.48)` for 88'. Re-running the
identical path on HEAD `9ee706a` yields **LOW 0.05 (71'), LOW 0.14 (118'), and NO candidate for 88'**.
The committed artifact tells a reader the generic lane earns HIGH on a real plan — exactly the
overstated-confidence dishonesty this spec forbids.
**Smallest honest change.** Regenerate or delete the stale gitignored `report.json` (and the
`seed_general_upload_local_smoke` / `general_upload_e2e` artifacts) so checked-in proof reflects current
honest LOW output. Update any START_HERE/doc that asserts the old HIGH/MEDIUM bands.
**Risk.** Gitignored data/output artifacts only — **not engine code, no frontier impact.**

### G2 — HIGH reachable on a clean/contrived single-bore plan (demo dishonesty) — HIGH
**Spec divergence.** `_confidence:391-397` awards HIGH when `cover≥0.90 ∧ extent_fit≥0.80 ∧
fragments==0 ∧ competition==0 ∧ ¬full_sheet`. On a polished single-dominant-run demo plan these all
hold and the customer sees HIGH for a placement no human verified — violating §3.2. Real plans never
reach it (always 5–13 fragments, verified), but a demo plan can.
**Smallest honest change.** Adopt §3.2 option (a) or (b): cap Lane B at MEDIUM regardless of signals,
OR require an independent non-geometry corroboration (directional-bore note within tolerance, or KMZ
length agreement) before HIGH. At minimum, never display a Lane B HIGH without the "inferred — human
must verify" framing. **Gate behind a regression test asserting no real-plan bore reaches HIGH (G7).**
**Risk.** Lane B `_confidence` (adapter), not the 50/58 deterministic path — **medium, test-gated.**

### G3 — Named-dialect REVIEW emits NO confidence band — asymmetry vs the generic lane — MEDIUM
**Spec divergence.** `evaluate_uploaded_corpus_engine_handoff:634-635` attaches confidence only when
`signals` is non-empty, and only the generic dialect populates `signals`. All three ODOT bores through
the **named** dialect return REVIEW with `signals_empty=True` → no band shown, while a *generic* upload
shows a band. The named REVIEW rests on a **real drawn extent** (stronger evidence) yet displays *less*,
so a generic LOW can read as "more analyzed" than a named drawn-extent REVIEW — backwards.
**Smallest honest change.** Either suppress the generic band in the UI when it would invite a misleading
comparison, OR emit an honest **qualitative** band for named REVIEW too (e.g. `LOCATION CONFIRMED,
EXTENT NOT TIGHT` derived from the existing `DRAWN_EXTENT_COVERS_SPAN_NOT_TIGHT` / `LOCATION_ONLY`
caveats). Document the asymmetry so the UI never presents generic-LOW as more measured than a named
REVIEW.
**Risk.** Adapter/UI — **no deterministic-path change.**

### G4 — Cross-matchline bore silently produces NO candidate (`NO_DRAWN_RUN_OVER_SPAN`) — MEDIUM
**Spec divergence.** The 88' ODOT bore (span 23+33→24+21, sheets [11,12]) returns
`_place_generic → (None, NO_DRAWN_RUN_OVER_SPAN)`: sheet 11 (b=1452.6) and sheet 12 (b=2275.5) have
separate station axes and the span straddles the matchline, so per-sheet coverage never reaches the 0.5
minimum. The product reports `ENGINE_ABSTAINED` rather than a LOW reviewable candidate. This is **honest
and correct per the abstain doctrine** (better to abstain than guess), but a legitimate cross-matchline
bore yields nothing for the user to act on.
**Smallest honest change (optional, deliberate product decision only).** Compute per-sheet *partial*
coverage and place the best partial leg with `PARTIAL_CROSS_SHEET_REVIEW` + LOW confidence, surfacing
alternatives. Otherwise, **keep as a known coverage gap** and let the ABSTAIN name the missing element
("cross-matchline span; need a per-sheet leg or a printed boundary station"). Aligns with research
P11/P17 multi-leg-joined-at-matchline.
**Risk.** Adapter-level — **no frontier impact.**

### G5 — Docstrings overstate the generic lane's mechanism; `_cap_review` is dead code — LOW
**Spec divergence.** `generic_geometry.py:12-16` and `uploaded_corpus_engine_handoff.py:416-418/438-439`
state the generic dialect "runs through the EXISTING, tested `run_match` + `decide_by_extent`
unchanged, inheriting their span-coverage + uniqueness gates and REVIEW-capping." The live path actually
calls `_place_generic` (the bore-aware path), constructs the `Placement` directly as REVIEW
(`:320-324`), and **never** calls `run_match`/`decide_by_extent` for the generic case. `_cap_review`
(`:168-178`) is referenced only by tests, not the live flow. The AUTO-impossibility is *real* (generic
builds REVIEW directly + caps `< 0.86`) but the stated mechanism is inaccurate — a "dev plumbing
exposed" honesty smell.
**Smallest honest change.** Correct the docstrings to describe the actual `_place_generic` path (own
coverage/ambiguity gates, REVIEW constructed directly, confidence capped `< 0.86`), and either wire
`_cap_review` in as a belt-and-suspenders guard or remove it as dead code.
**Risk.** Documentation/cleanup — **no behavior change, no frontier risk.**

### G6 — Confidence thresholds are unvalidated magic constants from one corpus — LOW
**Spec divergence.** The whole lane's honesty rests on hand-tuned constants validated against a single
3-bore ODOT corpus: `_GENERIC_MIN_COVER` 0.5, `_GENERIC_CONFIDENT_COVER` 0.85, `_GENERIC_HIGH_COVER`
0.90, `_GENERIC_FRAG_COVER` 0.25, `_GENERIC_FULL_SHEET_FRAC` 0.8, the score weights 0.40/0.30/0.25/0.05,
and the `_confidence` weights/penalties/ceilings. A denser/sparser firm's plan could shift fragment
counts and let a partial pick slip into MEDIUM, or suppress a legitimate placement.
**Smallest honest change.** Treat them as **provisional**; gather a second real general-upload corpus
before trusting the bands. Add the regression test (G7). Mark the constants `# PROVISIONAL — validated
on one corpus` in code.
**Risk.** Adapter-level — **no deterministic-frontier impact.**

### G7 — No regression test locks the honest LOW output (re-inflation risk) — MEDIUM
**Spec divergence.** Nothing prevents a future weight change from silently re-inflating confidence back
to the banked-dishonesty HIGH. The honest behavior verified in the audit is unprotected.
**Smallest honest change.** Add a regression test asserting that on the ODOT corpus **all three bores
stay LOW + CORRECTION_RECOMMENDED** and that **no real-plan bore ever reaches HIGH** (also closes G2's
test gate). Build the synthetic generator from corpus §4 (R1–R10, name-free guards wired in) so HIGH/
MEDIUM/LOW/ABSTAIN fixtures exercise the band logic in both directions — but synthetic fixtures may feed
**only** the REVIEW/test lane (R10), never AUTO/FINAL, never the 50/58 fixtures.
**Risk.** Test-only — **no production behavior change.**

---

## 6. Invariants this spec must never break

- **No fake AUTO / FINAL / confidence / map geometry / street names / billing / coordinates / hidden
  uncertainty.** Every drawn vertex derives from a real run endpoint or an axis projection between real
  run points; extrapolation is flagged and capped; ABSTAIN names its missing evidence.
- **The deterministic 50/58 drawn-redline frontier is UNTOUCHED.** Lane A routes through the tested
  `run_match` gates; the generic lane is never registered and only fires after the named path declines,
  so the recognized render stays byte-identical.
- **Provenance stays `OWNER_CONFIRMED_HUMAN_ADJUSTABLE`** for generic REVIEW — never
  `DETERMINISTIC_AUTO`. The generic lane caps confidence `< 0.86` and builds REVIEW directly.
- **A banked human grade is never overridden** by the engine; SUPERSEDED proves a human correction is
  the placed redline; the export gate blocks a pending/rejected REVIEW.
- **Public HDD guidance is patterns and tests, not customer placement truth.** It informs priors,
  confidence checklists, and synthetic fixtures — never auto-placement and never customer geometry.
- **Must not regress:** the recognized-deterministic path, a clean uploaded project, the ambiguous
  correction flow, and the ZIP/PDF exports.
