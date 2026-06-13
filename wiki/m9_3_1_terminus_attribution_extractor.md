# M9.3.1: TERMINUS_ATTRIBUTION — shipped START/END attribution extractor

Status: **SHIPPED (engine; UNWIRED / unconsumed); universal core + injected profile;
adversarially audited (defects fixed pre-commit); zero bores moved.** Promotes the
M9.3 Phase-0 station-note-frame attribution law into convention-agnostic engine code.
The M8.27 census, product lanes, and M9.0/M9.1/M9.2/M9.3 results are untouched.

Core: `truelinev2/match/terminus_attribution.py` (zero plan-set literals — drift-guard-enforced)
Profile: `truelinev2/extract/terminus_profile.py` `BRENHAM_TERMINUS_PROFILE`
Proof: `truelinev2/proof/run_terminus_attribution_extract.py` (G1–G12 PASS)
Tests: `truelinev2/tests/test_terminus_attribution.py` (17; offline; synthetic non-Brenham + alpha-AP profiles prove universality)

## The law (shipped)

`attribute_bore(bore_id, start_station, end_station, lines_by_sheet, profile,
*, kmz_model=None, source_contradiction=False)` → `BoreTerminusResult`.

An AP+splice pair is **ENDPOINT_ATTRIBUTED** to a bore's END iff: the END station
carries exactly one structure note (0 → `NO_ENDPOINT_NOTE`, ≥2 →
`MULTIPLE_COMPETING_CALLOUTS`); the note's class is the profile's terminal class
(else `NON_TERMINAL_ENDPOINT`); exactly one (AP, splice) pair sits **inside** that
note's frame (else `NO_AP_SPLICE_PAIR`); and — when a KMZ model is supplied — the
pair joins its unique terminal via the M9.1 join (a rejection → `PDF_KMZ_CONTRADICTION`).
A corpus check (`check_terminal_uniqueness`) enforces **one terminal → one bore END**.

- **DIRECTION (load-bearing):** a terminal is END-of-feed. A terminal at a bore
  START is the prior feed's terminus → **`JUNCTION_ORIGIN`** (a bore-to-bore
  junction; `resolve_junctions` pairs it to the END bore that owns the terminal),
  never the START bore's identity. Terminal ownership is END-direction only.
- **Not a flat scan:** `owning_pairs` maps every printed AP to the note frame that
  owns it (run-callout / equation lines reset the frame); an AP owned by neither
  endpoint is a **`SHEET_NEIGHBOR_REJECTED`**. Proximity / AP-only / splice-only
  never attribute.
- **`SOURCE_CONTRADICTION`** is an injected caller fact (banked PDF↔source finding),
  not detected by the extractor.

## Result (all-58, through the shipped core — reproduces M9.3)

Bore disposition census: **7 ENDPOINT_ATTRIBUTED / 3 JUNCTION_ORIGIN / 1
PDF_KMZ_CONTRADICTION / 1 SOURCE_CONTRADICTION (log44) / 44 SHEET_NEIGHBOR_REJECTED.**

- **7 clean terminal-END attributions, each KMZ-join BOUND** to a unique terminal:
  log42→105, log72→117, log12→121, log2→148, log10→152, log57→157, log7→163.
- **3 bore-to-bore junctions:** log27→AP-152 (owned by log10), log39→AP-117 (log72),
  log65→AP-163 (log7).
- **1 PDF↔KMZ contradiction:** log46 (PDF `AP-161 SPLICE LOC 35` vs KMZ `Splice Loc 45`).
- log68 AP-148 sheet-neighbour-rejected (owns STA 20+71 = log2's terminal); log44
  source-contradiction (banked M8.25/M9.0).

The bore-disposition census + all named controls are byte-identical to M9.3 Phase 0.
The per-endpoint taxonomy is a strict **refinement**: the former `NO_AP_SPLICE_PAIR`
is split into `NO_AP_SPLICE_PAIR` (partial id at a terminal note) and
`NON_TERMINAL_ENDPOINT` (a bound note whose class is not the terminal class) — no
disposition or control changes.

## Universal core + injected profile

The core holds **zero** plan-set literals (no customer name, no `terminal_port_hh`,
no `FLOWER POT` / `SPLICE LOC`, no coordinate read) and duck-types the profile —
mirroring how the M9.1 `join_terminal` duck-types the KMZ model. Everything
plan-set-specific lives in the `extract/` `TerminusProfile`: the station / AP /
splice / pair grammars, the structure-note keyword set, the class-keyword table, the
terminal-class name, **and the AP id TYPE** (`ap_cast`). Universality is proven on a
synthetic NODE/PORT/WIDGET profile (vocabulary swap), an MH-station profile (station
format swap), and a zone/alpha-AP profile.

### M9.3.1 audit fix — the AP-type coupling

The first draft coerced the AP token to `int` in the core, which **crashed** on a
zone/alpha AP id (e.g. `A12`) and contradicted the M9.1 join (which compares AP by
value-equality and documents discriminating-prefix support). Fixed: the AP id is
cast by the profile's injected `ap_cast` (`int` for digit-AP plan sets — Brenham
byte-identical; `str` for zone/alpha). Regression tests pin that `A12` binds cleanly
and `A12`/`B12` never collapse. (Directly parallels the M9.1 splice-token audit fix.)

## UNWIRED + posture

The extractor is **unconsumed** — no `resolve_bore` / sweep / reviewer service /
`run_match` / engine / service imports it (there is no opt-in flag; it is simply not
wired). It composes the shipped M9.1 `join_terminal` for the cross-check, so two
M9.2/M9.3 phase-0 unwired-guards that over-broadly asserted "no `match/` file imports
the join" were **narrowed to the placement-path modules** (engine / lane / reviewer
service / service) — matching the authoritative `test_kmz_structure_join` unwired
test, not weakening it. No render / PNG / segment / AUTO / placement; zero bores
moved. Full v2 suite **717 passed**; convention/import/global-state/red-stroke guards
green.

## Adversarial audit

4 refutation lenses (universality, faithfulness, unwired/contract/guards, overclaim).
Faithfulness + unwired-contract confirmed sound (exact M9.3 reproduction; legitimate
guard-narrowing; nothing consumes the extractor). The universality + overclaim lenses
caught: the AP-as-int coupling (fixed → `ap_cast`), the "reproduce EXACTLY" overclaim
(reworded → bore-disposition + controls reproduce, per-endpoint taxonomy refined), the
"default-OFF" misnomer (→ "UNWIRED/unconsumed", no flag exists), and the
`source_contradiction` injected-provenance labelling. All applied pre-commit.

## Next step

A **run-assembly lane** (still gated, REVIEW-only) can consume the 7 clean terminal
anchors + the 3 junctions (e.g. log10 END = log27 START at AP-152 = bore-to-bore
continuity). Owner source re-reads remain required for log46 (PDF↔KMZ) and log44
(325′, M8.25). No consumer wiring in this milestone.
