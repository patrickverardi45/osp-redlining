# TrueLine v2 — Redline Manifest Contract (Phase 1)

> **CONTRACT-ONLY.** This is the first engine→website contract: a schema-pinned
> `redline_manifest.json` plus a representative example for the current 50/58 state.
> **No website wiring, no backend wiring, no engine run, no render, no deploy** was done
> to produce it. The example is **hand-authored from the committed accountability ledger**,
> not engine-generated. Created 2026-06-19 (`TRUELINE_V2_REDLINEMANIFEST_SCHEMA_AND_RUNNER_CONTRACT` Phase 1).

## Why this exists

The website/backend must consume a **stable, machine-readable** description of what the
engine has drawn — so UI work never scrapes proof scripts, PNG filenames, stale model
fields (`parent_source_model.json placement_status`), or gitignored on-demand artifacts.
This contract defines exactly that surface. See the readiness audit for the full gap
analysis: [`trueline_v2_engine_website_readiness_audit.md`](trueline_v2_engine_website_readiness_audit.md).

## Files (in the repo)

| File | Role |
|---|---|
| `truelinev2/contracts/redline_manifest.schema.json` | JSON Schema (Draft 2020-12) — the pinned contract. |
| `truelinev2/contracts/examples/brenham_50_of_58_redline_manifest.example.json` | Representative example for the current Brenham 50/58 state (`mock_example: true`). |
| `truelinev2/tests/test_redline_manifest_contract.py` | Validation + reconciliation test (dependency-free; also uses `jsonschema` when installed). |

Run the test (repo-root venv):

```
venv/Scripts/python.exe -m pytest truelinev2/tests/test_redline_manifest_contract.py -v
```

## Shape

Top level: `schema_version` · `mock_example` · `disclaimer` · `project_id` ·
`project_name` · `engine{branch, engine_head, render_commit, generated_from}` ·
`summary{total_logs, drawn_count, covered_count, blocked_count, frontier}` ·
`status_counts` · `provenance_counts` · `consumption_rules` · `logs[]`.

Per log: `log_id` · `parent_id` · `entry_role` · `status` · `provenance` · `drawn` ·
`covered` · `blocked` · `drawn_lane` · `source_sheets` · `span` · `closure` · `coverage` ·
`blocker` · `artifacts[]` · `evidence[]` · `warnings[]`.

### Status enum (5)
`DRAWN_REDLINE` · `COVERED_BY_EXISTING_REDLINE` · `OWNER_LOCKED_ABSTAIN` ·
`SOURCE_GAP_BLOCKED` · `MISSING_SOURCE_SHEET_BLOCKED`

### Provenance enum (6)
`DETERMINISTIC_AUTO` · `OWNER_CONFIRMED_HUMAN_ADJUSTABLE` (← **log3 only**) ·
`COVERED_BY_EXISTING_REDLINE` · `BLOCKED_OWNER_LOCKED` · `BLOCKED_SOURCE_GAP` ·
`BLOCKED_MISSING_SOURCE`

Exactly one of `drawn` / `covered` / `blocked` is true per log, consistent with `status`.
A `blocker` object is present **iff** `blocked` is true and carries an `unlock_requirement`.

## Current truth encoded by the example

- **58 logs · 50 drawn · 1 covered · 7 blocked** (`frontier: "50/58"`, `render_commit: c19b565`).
- **log3** → `DRAWN_REDLINE` / `OWNER_CONFIRMED_HUMAN_ADJUSTABLE` (the only owner-geometry,
  human-adjustable render — **never** `DETERMINISTIC_AUTO`); upstream `12+63→15+13` drawn,
  downstream `15+13→21+63` `coverage.downstream_covered_by: ["log4"]`.
- **log14** → `COVERED_BY_EXISTING_REDLINE`, `coverage.covered_by: "log10"`, `drawn: false`,
  no artifacts (no duplicate stroke; not a missing redline).
- **Blocked 7** → log5/31/38/43 owner-locked, log15/16 source-gap, log57 missing `.FS` sheet;
  each carries a `blocker.unlock_requirement` (a call-to-action, never a green check).

## How the website MUST consume it (consumption rules)

1. Treat **this manifest** as the only source of drawn/covered/blocked truth.
2. **Never** read `parent_source_model.json` for status or geometry — especially
   `placement_status` (stale) or `adj_corrected_span` (corrupted for log48/log70).
3. **Never** infer status from PNG filenames or a file's presence/absence on disk
   (absence ≠ blocked; presence ≠ drawn).
4. Render only artifacts with `kind == FINAL_REDLINE_PNG`; ignore `PROOF_HELPER` /
   `EVIDENCE_SCREENSHOT`. Resolve each by `path` + `sha256` once published.
5. **Never display 58/58.** Always show the denominator (“50 drawn of 58 accounted”).
6. Surface per-log `warnings` (e.g. stored-anchor debt `B-DATA-LOG48-ADJ-1`,
   owner-corrected sheets) to consumers.

## Not yet built (explicit Phase boundary)

This task delivered the **contract and example only**. It did **not** build:

- a clean parameterized **runner** that emits a real manifest (still Brenham-hardcoded
  proof/sweep scripts);
- **live artifact publishing** with real `sha256` (example artifacts are
  `example_placeholder: true`, `sha256: null`);
- any **website/backend wiring** or deploy.

Safe next work against this contract: a **contract-first mock UI** that consumes the
example manifest (status/provenance chips, blocked-log CTAs, the “50 of 58 accounted”
honesty header, artifact rendering by manifest reference) — with **no live engine wiring**.
