# M5 scope packet — Brenham coverage sweep (v2 only)

**Status:** SCOPE — decisions approved (`663728a`); framing-corrected (Brenham = Adapter #1; measurement-first). **No code written.** Implementation gated on a separate go-ahead.
**Date:** 2026-06-09
**Branch:** `feat/truelinev2` (isolated; not merged to main)

## Goal
Measure how far the standalone `truelinev2/` engine gets across the **full known
Brenham bore-log corpus** — its AUTO_SELECT / REVIEW / ABSTAIN distribution and,
above all, **zero false placements** — using v2's shipped pipeline only. This
quantifies "replacement-level coverage" on the reference convention and de-risks
the later redline-geometry milestone.

## Framing — Brenham is Adapter #1, not the product (core-purity rule)

**Brenham is not the product.** Brenham is **Adapter #1** — a worked example of the
kind of contractor project package TrueLine will receive. ODOT is **Adapter #2**.
Future customers bring different conventions. The product is the **generic core +
pluggable adapters**, not a Brenham engine.

So M5 is **measurement, not hardcoding**. It measures four things:
- how well the **generic core** performs when driven by the **Brenham adapter**;
- where the **Brenham adapter** is incomplete;
- which failures are **adapter-specific**;
- which failures expose **missing generic-engine capabilities**.

**Hard rule — no Brenham assumptions in the shared core.** Brenham-specific logic may
live ONLY in `ingest/borelog_brenham.py`, `extract/brenham.py`, and Brenham
proof/tests/docs. It may **not** appear in `match/`, `schema/`, `render/`, `store/`,
`api/`, or shared `service.py`. This is already **structurally enforced** by the shipped
drift guard `tests/test_no_convention_leakage.py` (it fails the build if
`brenham`/`odot`/… appears in core); M5 keeping that guard green *is* the mechanical
proof that v2 stays multi-convention.

**Measurement-first.** Do **not** patch to raise the Brenham placed-count during M5. Any
fix is a **separate, explicitly-approved implementation milestone** (M5 hands it a
prioritized, classified gap list). M5's job is to produce that list, not to close it.

### Required miss taxonomy (every non-correct outcome gets exactly ONE class)
Classified by **where the gap lives** — which is what keeps v2 a multi-convention engine:

1. **adapter_parser_gap** — the Brenham adapter (`borelog_brenham.py` / `extract/brenham.py`)
   failed to extract/normalize something the source actually contains. Fix → the adapter.
2. **generic_match_scoring_gap** — a correctly-extracted case the convention-agnostic
   `match/` core couldn't resolve. Fix → core, and it MUST stay convention-agnostic.
3. **missing_redline_geometry** — located fine, but the gap is v2's inability to draw/
   represent the needed geometry. Fix → the M6 geometry milestone.
4. **bad_or_ambiguous_source** — the bore log / plan genuinely lacks or contradicts the
   info (e.g. a missing source packet). Not a v2 defect.
5. **honest_abstain** — v2 correctly abstained given the evidence. A pass.

## Hard separation (carried from the session rules)
Work only in `truelinev2/`. Do **not** touch `backend/`, `main.py`, `web/`,
Render/Vercel; do not deploy or merge to main; do not **import** old-app code.
Reading old **outputs / known answers** as a static reference is allowed;
importing old **modules** is not. If anything forces a touch of old production
code → **stop and ask**.

---

## 1. Exact corpus path(s) to enumerate
- **Root:** `C:\Users\Patrick\OneDrive\Attachments\Desktop\excel bore logs\`
- **Enumerate:** top-level `bore_log*.xlsx` only, **non-recursive**.
- **EXCLUDE:** the subfolder `…\excel bore logs\combined_originals_DO_NOT_IMPORT\`
  (13 pre-split "combined originals", flagged DO_NOT_IMPORT — not canonical logs).
- Make the corpus root an env override (`TL2_BRENHAM_CORPUS`) defaulting to the path above.

## 2. How many bore logs are expected
**58** canonical logs (bore_log2–72, minus the 13 archived originals; bore_log1 is
absent). This matches the documented "Brenham 58-log corpus." **Stop condition:**
if the enumerated count ≠ 58, pause and report before running (corpus drift).

## 3. Canonical engineering PDF for Brenham
`<repo>/data/uploads/Brenham_Tx/NEXTLINK - Brenham - Phase 5_07-15-25.pdf`
— the exact plan M1 proved on. (A second older plan
`NXL -BRENHAM PH5 - 18-02-2026.pdf` exists in the same folder but is **not** used;
single canonical PDF keeps the sweep deterministic.) Env override `TL2_PROOF_PDF`.

## 4. How v2 will run each bore
Reuse the shipped service unchanged — for each of the 58 logs:
1. `ctx = require_context("proof-tenant", "brenham-<bore_id>")` (per-log session).
2. `payload = RedlineService.run(ctx, bore_path, PDF)` →
   `load_borelog` → `PlanPdf` → `select_dialect` (Brenham) → `calibrate` (offset 13)
   → `run_match` (footage mode: chains → score → decide) → `render_evidence_crop`
   → tenant-scoped artifact store → review payload.
3. Read `payload.items[0].placement` (status / tier / reason / sheets / station_span
   / footage + deltas / caveats / artifacts).
- **No HTTP server in the sweep** (M1 already proved serving + tenant isolation).
  Optional `--serve-sample` to spot-check one artifact over `/v2/artifact/...`.
- Engine code is **untouched** → coverage is measured on the shipped M1/M2/M3 engine.

## 5. Report schema
`m5_brenham_coverage.json`:
```
{
  "milestone": "truelinev2 M5 — Brenham coverage sweep",
  "pdf": "<canonical pdf path>",
  "corpus_root": "<path>", "enumerated": 58, "excluded_subdir": "combined_originals_DO_NOT_IMPORT",
  "generated_note": "statuses are deterministic; zero-false verified by VISUAL grading, not by this file",
  "rows": [
    {
      "bore_id": "bore_log51", "source_file": "bore_log51.xlsx",
      "station_span": "0+00->2+99", "span_ft": 299.0, "sheet_refs": [8],
      "status": "AUTO_SELECT", "tier": "...", "reason": "...",
      "placed_sheets": [8], "footage": 299.0,
      "footage_delta": .., "start_delta": .., "end_delta": .., "caveats": [..],
      "artifact": "log51_s8_0p00-2p99.png", "artifact_path": "<grading copy path>",
      "old_engine": {"status": "AUTO_SELECT", "sheets": [8], "span": "0+00->2+99", "source": "M1 known answer"},
      "agreement": "agree | v2_only_place | old_only_place | both_abstain | differ",
      "grade": "pending | correct | false | abstain_ok",   // filled during grading
      "miss_class": "n/a | adapter_parser_gap | generic_match_scoring_gap | missing_redline_geometry | bad_or_ambiguous_source | honest_abstain",
      "grade_notes": ""
    }
  ],
  "summary": {
    "auto_select": N, "review": N, "abstain": N, "errored": 0,
    "placed": N, "false_placements": 0,
    "miss_breakdown": {"adapter_parser_gap": N, "generic_match_scoring_gap": N,
                       "missing_redline_geometry": N, "bad_or_ambiguous_source": N, "honest_abstain": N},
    "vs_baseline": {"old_placed_documented": "~34-36", "v2_placed": N,
                    "v2_only": [..], "old_only": [..], "both_abstain": [..], "differ": [..]}
  }
}
```

## 6. Artifact naming / location (runtime outputs — NOT committed)
- v2 renders crops to its configured `cards_dir` then copies into the tenant-scoped
  `artifact_root` (`data/outputs/truelinev2/...`), exactly as M1/M2 do.
- The sweep also writes a **flat grading set** to
  `<repo>/data/outputs/truelinev2/m5_brenham/` :
  - `m5_brenham_coverage.json` (the report)
  - one crop per placed log named `\<bore_id\>__\<STATUS\>__s\<sheet\>.png` for fast human grading.
- These are **generated outputs**: untracked, gitignored, **never staged/committed**.
  Only the harness code under `truelinev2/proof/` is committed.

## 7. Grading checklist (human, per PLACED log — the zero-false gate)
For each AUTO_SELECT / REVIEW row:
1. Open the grading crop and locate the bore's `station_span` on the named sheet.
2. Confirm the highlighted/located run is the bore's **actual** drilled run on that sheet.
3. Cross-check the static old-engine answer (item 11) where documented.
4. Mark `correct` / `false` (+ notes). A crop that does **not** contain the bore's
   true location = `false`.
For each ABSTAIN row: confirm the reason is honest and that no obvious deterministic
placement was missed → `abstain_ok`; if a real placement was clearly missed, note it
as a **coverage gap** (named target), not a pass/fail of correctness.

## 8. What counts as correct
- **Correct AUTO_SELECT:** right sheet + station span matching ground truth (old
  answer where known, else visually-verified plan callout), footage from the log,
  crop shows the true run.
- **Correct REVIEW:** located on the right sheet/region and flagged for human
  approval (location confirmed, not auto-committed). Pointing at the right place = correct.

## 9. What counts as a false placement
Any AUTO_SELECT **or** REVIEW whose crop/located run is on the **wrong**
sheet/station/run, or contradicts a documented old answer without a verified reason.
- A false **AUTO_SELECT** = **milestone failure** (hard zero-false breach).
- A false **REVIEW** is a defect too (a human would catch it, but it still breaches
  zero-false intent) → must be investigated and counted; it blocks acceptance.

## 10. What counts as an honest abstain
`status = ABSTAIN` with a populated reason, where abstaining is the safe correct call
given v2's current evidence. An abstain on a log the **old engine placed** is a
**coverage gap** (named target for a future milestone), **not** a false placement and
**not** an M5 failure. Honest abstain is a pass.

## 11. Baseline comparison without importing the monolith
- Author a **static** reference fixture `truelinev2/proof/fixtures/brenham_known_answers.json`,
  keyed by `bore_id`, transcribed by hand from **documented old-engine outputs**
  (trust_ledger_replay ~34 placed; Sprint 2.5 grader 36/58; the route_480-bucket
  abstainers; bore_log71/72 validated; M1's log51 answer). Each entry carries a
  `source` provenance string; undocumented logs → `"old": "unknown"` (graded visually only).
- The sweep **reads this JSON file** (a file read, not a module import) and annotates
  `old_engine` + `agreement` per row. **No old-app module is imported.**
- Comparison is informational: `old_only_place` = coverage gap (expected, v2 is younger);
  `v2_only_place` = requires extra grading scrutiny (v2 must be provably right or it's a false placement).

## 12. Acceptance gates
1. **Zero false placements** (0 false AUTO, 0 false REVIEW) — the hard bar; one false = fail.
2. All **58** logs run to a terminal status, **0 errored**; every non-placed log has an honest abstain reason.
3. Every AUTO/REVIEW has a rendered crop and is **graded** (no `pending` left).
4. Coverage reported: counts + `vs_baseline` (v2_placed, v2_only, old_only, differ).
5. **No engine drift / core purity:** existing **43 tests green**, all 3 drift guards green —
   in particular `test_no_convention_leakage.py` proves **zero Brenham logic leaked into the
   core**; statuses **deterministic** on re-run.
6. **Every non-correct outcome carries exactly one `miss_class`** (the required taxonomy); the
   report ships a `miss_breakdown`.
7. **Measurement-only:** no patch raised the Brenham count (no core/adapter edit during M5
   beyond the proof harness). Any fix is deferred to a separate, approved milestone.
8. Packet results recorded as a follow-up doc/checkpoint update (separate, gated commit).

## 13. Stop conditions
- Any need to **import or modify** `backend/` / `main.py` / old-app modules → **stop, ask**.
- Enumerated corpus count ≠ 58, or the canonical PDF missing/unparseable, or the
  Brenham dialect fails to detect → **stop, report, confirm** before running.
- A **false placement** is found → stop the "success" path; document it as a finding
  (M4-style); **do not widen tolerances** to hide it.
- A miss "wants" a Brenham special-case in `match/`/`schema/`/`render/`/`store/`/`api/`/
  `service.py` → **stop** (core-purity breach). Record it as `generic_match_scoring_gap`
  (fix stays convention-agnostic) or `adapter_parser_gap` (fix goes in the Brenham adapter)
  — never a convention branch in the core.
- Tempted to patch to raise the Brenham count → **stop**; M5 is measurement. Defer to a
  separate, explicitly-approved implementation milestone.
- A bore log fails to ingest/route → record as an ingest finding (not a false placement); do not force.
- Render/Vercel/deploy/merge-to-main → never.

## 14. Files created / modified
**Created (committed, `truelinev2/` only):**
- `truelinev2/proof/run_brenham_corpus.py` — the sweep harness (reuses shipped service).
- `truelinev2/proof/fixtures/brenham_known_answers.json` — static baseline reference.
- `truelinev2/tests/test_brenham_corpus_harness.py` — tiny test: enumeration excludes the
  DO_NOT_IMPORT subfolder + expects 58 (keeps drift guards meaningful; no engine touch).

**Modified:** none in core/extract/ingest/match/render/store/api/schema. (If the sweep
surfaces a bug, fixing it is a **separate, gated** change — not part of M5.)

**Runtime outputs (NOT committed):** `data/outputs/truelinev2/m5_brenham/**`.

## 15. Code changes needed, or proof-harness-only?
**Proof-harness-only.** No changes to the engine (schema/match/render/extract/ingest/
api/store). New code lives solely under `truelinev2/proof/` (+ one fixture + one tiny
test). The engine stays byte-identical, so coverage is measured on exactly the shipped
M1/M2/M3 build — which is the point.

## 16. Estimated effort
- Harness + fixture + tiny test: **S** (~1 focused session, a couple hours).
- Sweep runtime: **minutes** (58 logs × a few seconds each; no server).
- **Long pole = human visual grading** of every placed crop (operator time, roughly
  proportional to placed count; ~30 placed → ~1–2 hrs). Zero-false cannot be rushed.

## 17. How results inform the later redline-geometry milestone
- Produces the **coverage map**: which logs v2 AUTO-places correctly (safe first
  candidates for geometry — lowest zero-false risk), which it REVIEWs (need a human gate
  before geometry), which it abstains on (geometry N/A until located — named targets).
- Footage-mode deltas (start/end/footage) across the corpus are the raw material for a
  **plan-space overlay** geometry option, and reveal whether located runs are precise
  enough to draw.
- The `v2_placed` vs `~34–36` baseline quantifies the remaining "replacement-level
  coverage" gap and tells us whether geometry should target plan-space overlay first
  or requires the larger **geo / KMZ** subsystem (a separate, bigger separation decision).
- Net: M6 (geometry) gets scoped to the **AUTO-correct set first**, with the coverage
  numbers and located-run evidence already in hand.
```

---

## Open decisions for you (before implementation)
1. **Corpus = the 58 top-level logs, excluding `combined_originals_DO_NOT_IMPORT/`** — confirm.
2. **Single canonical PDF** (`NEXTLINK - Brenham - Phase 5_07-15-25.pdf`) — confirm vs. also trying the second plan.
3. **Baseline fixture authored from documented records** (unknowns graded visually) — confirm this is the separation-safe baseline you want.
