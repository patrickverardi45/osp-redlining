# M9.4.1: RUN_ASSEMBLY — shipped convention-agnostic run-assembly extractor + review card

Status: **SHIPPED (engine core + M8.20-style review card; UNWIRED / unconsumed); universal
core + injected drop grammar; adversarially audited (one low-severity overclaim corrected
pre-commit); zero bores moved.** Promotes the M9.4 Phase-0 run-assembly safety law into
convention-agnostic engine code over the M9.3.1 typed terminus facts. The M8.27 census,
product lanes, M8.11 lanes, and M9.0–M9.4 results are untouched.

Core: `truelinev2/match/run_assembly.py` (zero plan-set literals — drift-guard-enforced)
Card: `truelinev2/review/run_assembly_review.py` (schema `truelinev2-run-assembly-review-1`)
Profile field: `truelinev2/extract/terminus_profile.py` `TerminusProfile.drop_markers` (Brenham `("FOR FIBER DROP",)`)
Proof: `truelinev2/proof/run_run_assembly_extract.py` (G1–G11 PASS)
Tests: `truelinev2/tests/test_run_assembly.py` (offline; synthetic non-Brenham profile + posture)

## The law (shipped)

`extract_run_assembly(results, lines_by_id, profile)` → `List[RunAssemblyEvidence]`, one
typed item per bore-to-bore junction (from `terminus_attribution.resolve_junctions`). Each
junction passes a safety law before its departure is classified:

0. bore-to-bore only (`start_bore != end_bore`; a self-junction is refused);
1. END ownership clean + unique (END `ENDPOINT_ATTRIBUTED`; one terminal → one END bore);
2. the START side is `JUNCTION_ORIGIN`, never ownership (the M9.3.1 END-direction law);
3. both sides carry the SAME normalized terminal fact (AP + splice token);
4. the M9.1 two-field join corroborates the terminal (END `kmz_join == BOUND`);
5. neither bore carries a PDF↔KMZ or source contradiction;
6. no competing physical departure at the terminal (see the guard below);
7. EVIDENCE-only — it changes no product disposition.

Then the **departing bore's printed run class** types the evidence item: a non-drop
departure is a **`RUN_ASSEMBLY_REVIEW_CANDIDATE`**; a positively-detected drop departure
(a profile drop marker in the departing run callout) is a **`JUNCTION_DROP_BRANCH`** — a
fiber-drop lateral OFF the terminus, NOT the trunk continuing. Every other case is a typed
blocker (`COMPETING_JUNCTION_CANDIDATES` / `START_JUNCTION_NOT_OWNERSHIP` /
`SELF_JUNCTION_REFUSED` / `PDF_KMZ_CONTRADICTION` / `SOURCE_CONTRADICTION` /
`UNMODELED_RUN_RELATIONSHIP`). A reviewer — never the core — commits a run.

## The competing guard (the named Phase-0 gap, closed for the same-frame case)

Phase-0 counted only `JUNCTION_ORIGIN` departures. The shipped `physical_departure_count`
enumerates the physical run-callout departures printed **within the terminal's own frame**
(the END bore's sheets, where the terminal note sits): every `STA <terminal> … TO STA …`
run callout, plus every `JUNCTION_ORIGIN` start, deduped by callout text so a
`JUNCTION_ORIGIN` bore's own callout is not double-counted. `> 1` distinct physical
departure → `COMPETING_JUNCTION_CANDIDATES`. So a same-frame fiber-drop lateral that lacks
a terminal-class start note can no longer hide (proven: a synthetic unclaimed lateral →
count 2; real Brenham → count 1/terminal). The departure-window mirrors
`detect_endpoint_note`'s frame discipline (it stops at the next STA line, so a neighbour's
drop marker cannot leak in).

**Named limitation (still-open evidence target):** the scan is frame-scoped to the END
bore's sheets, NOT corpus-wide — a station token (e.g. `4+51`) is frame-local and recurs in
every sheet's stationing, so a corpus-wide scan would false-positive (the M9.2 matchline
trap), breaking zero-false. A matchline-adjacent lateral drawn SOLELY on a sheet outside
the END bore's frame is therefore not yet enumerated; associating a far-sheet callout with
this node requires the cross-sheet frame-equation graph (the M9.2 matchline track) — a
separate, justified capability, never a silent widen. Pinned by
`test_physical_departure_count_cross_sheet_lateral_is_named_limitation`.

## Result (all-58, through the shipped core — reproduces M9.4 Phase 0)

3 bore-to-bore junctions → exactly:

- **2 `RUN_ASSEMBLY_REVIEW_CANDIDATE`** — `log10` END → `log27` START @ AP-152;
  `log72` END → `log39` START @ AP-117. (Departure run class undetermined; the reviewer
  classifies — no continuity asserted.)
- **1 `JUNCTION_DROP_BRANCH`** — `log7` END → `log65` START @ AP-163. `log65`'s departing
  run prints `FOR FIBER DROP` (199′ = span, a lateral off `log7`'s end-of-feed terminus),
  so it is positively a drop branch and **cannot** be promoted to a continuation candidate.

The 7 clean END anchors, the M9.3.1 bore census (7/3/1/1/44), the M8.11 fullest lanes
(30/16/6/4/2), and the M8.27 census are re-verified unchanged live.

## Review card (M8.20-style, standalone, unwired)

`build_run_assembly_cards(evidence)` → `RunAssemblyReviewCard[]`: one card per SHARED-
TERMINAL evidence item (a typed blocker yields NO card). REVIEW/evidence-only, label frozen
`SUGGESTION_NOT_PLACEMENT`, no geometry/strokes/AUTO (pydantic fail-closed; a geometry key
anywhere is rejected). A `DROP_BRANCH` card must carry a positively-detected drop; a
`CONTINUATION_CANDIDATE` card may never carry a drop. Mirrors `review/group_review.py`; it
is NOT the reviewer service and is wired into nothing.

## Universal core + injected drop grammar

The core holds **zero** plan-set literals (no customer name, no `FOR FIBER DROP`, no
`SPLICE LOC` / `AP-` / `terminal_port_hh`, no coordinate read) and duck-types the profile.
The drop-marker grammar is the new `TerminusProfile.drop_markers` (empty-tuple default — a
plan set that declares no drop grammar reads every departure as non-drop; the core never
invents a marker). Universality is proven on a synthetic NODE/PORT/WIDGET profile with a
DIFFERENT injected drop marker (`LATERAL TAP`); G8 proves on the real `log65` callout that
`drop_markers=()` flips the same line to a non-drop trunk — the detection is profile-driven.

## UNWIRED + posture

The core composes the M9.3.1 `terminus_attribution` (typed facts + junction resolver) —
exactly as `terminus_attribution` composes the M9.1 join — but nothing consumes it: no
`resolve_bore` / sweep / reviewer service / engine / `run_match` / UI imports `run_assembly`
(no opt-in flag; simply unwired). The M9.3.1 terminus unwired-guard was narrowed to permit
`run_assembly.py` as the legitimate downstream composer, matching the authoritative
`test_kmz_structure_join` placement-path pattern; `run_assembly`'s own unwiredness is
guarded separately (`test_core_unwired_from_placement_path`). No render / PNG / segment /
AUTO / placement / bucket change; zero bores moved. Full v2 suite **751 passed**;
convention / import-isolation / global-state / red-stroke guards green.

## Adversarial audit

8 refutation lenses (core-literal, drop-injection, competing-guard, log65-promotability,
product-movement, wiring, weakened-guards, correctness). 7 confirmed sound with live probes
(zero literals; profile-driven drop; `log65` non-promotable on every route incl. card
validator; no bucket/AUTO/geometry, lanes+census re-verified live; engine/reviewer-service
hold zero `run_assembly` references; surgical guard-narrowing still bites; gate ordering /
KMZ gate / no-crash all verified). One low-severity finding: the competing guard's "enumerate
ALL physical departures" claim was overstated — the cross-sheet lateral (drawn outside the
END bore's frame) is not covered. Corrected pre-commit by scoping the claim accurately and
naming the cross-sheet case as a still-open M9.2-gated target (the disciplined choice; a
corpus-wide widen would reintroduce the M9.2 frame-collision false-positive).

## Next step

A **reviewer-service surface** for the run-assembly cards (a NEW review item, never a
per-bore bucket change; separately justified, authorization-gated). Cross-sheet
competing-lateral enumeration via the M9.2 frame-equation graph (the named limitation).
Owner source re-reads remain required for log46 (PDF↔KMZ) and log44 (325′). No consumer
wiring in this milestone.
