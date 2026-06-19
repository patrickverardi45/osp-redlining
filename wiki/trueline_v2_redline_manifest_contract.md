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

## Contract mock UI (Phase 1 preview)

A static, manifest-driven preview lives under `truelinev2/contracts/mock_ui/`
(`redline_manifest_mock.html` / `.css` / `.js`) — it proves the manifest shape supports
the product UI **before** any runner or live wiring. It **fetches the committed example
manifest** (single source of truth) and renders the header (project · `50/58` · counts ·
render commit), the 5 accountability cards, All/Drawn/Covered/Blocked/Warnings filters,
and the per-log list — including log3 as `OWNER_CONFIRMED_HUMAN_ADJUSTABLE` (not auto),
log14 "covered by log10 / no duplicate artifact", each blocker's exact unlock requirement,
and the stored-anchor-debt warnings as **advisories** (never placement truth). It consumes
**only** the manifest — no engine, backend, parent model, stale status field, or filename
inference. Browsers block `fetch()` on `file://`, so preview via a local static server:

```
cd truelinev2/contracts && python -m http.server 8000
# open http://localhost:8000/mock_ui/redline_manifest_mock.html
```

Locked by `truelinev2/tests/test_redline_manifest_mock_ui_contract.py`. **Still no live
wiring, no runner, no deploy.**

## Artifact publisher (Phase 2A)

`truelinev2/contracts/redline_manifest_publisher.py` is the artifact pipe: given a
manifest-shaped input, a source-artifact root, a publish root, and a run label, it
validates the input against the schema, copies each drawn log's final redline artifacts
into a stable `…/<run-label>/artifacts/<log_id>/` directory, computes `sha256` + `bytes`,
flips each record to `published: true` / `example_placeholder: false`, and emits a real
manifest with `mock_example: false` (re-validated against the schema). It **fails loudly**
if a drawn log is missing a required final artifact, and **refuses** to fake artifacts for
covered/blocked logs. Status / provenance / coverage / blocker / warning fields are carried
through unchanged (publishing is an artifact step, not a placement step). The schema gained
two optional artifact fields (`bytes`, `published`); the placeholder example still validates
(backward-compatible). Locked by `truelinev2/tests/test_redline_manifest_publisher.py`
(temporary fake artifacts; no renderer run).

```
python -m truelinev2.contracts.redline_manifest_publisher \
    --manifest <in.json> --source-root <dir> --publish-root <dir> --run-label <id>
```

## Phase 2A.5 — existing-artifact inspection finding (read-only)

`truelinev2/proof/run_redline_manifest_existing_artifact_inspection.py` answered: *can we
publish a real manifest from the render artifacts already on disk, without re-rendering?*
**Finding: not unambiguously, not yet** (render was NOT run). Against the 50-drawn ledger
truth (status from the manifest, never from filenames), at render commit `c19b565`:

- **37 `NEW_TARGETS`** — clean: authoritative per-sheet stroke PNGs co-located in
  `data/outputs/callout_route_assembly_sweep/`, 1:1 with the sweep report's
  `verdicts[*].artifacts` (66 files, `still_blocked: {}`). A **checksum dry-run** computed
  real `sha256` + `bytes` for all 66 with the publisher's own routine — these are publishable.
- **13 `ALREADY_DRAWN`** (log7/25/45/50/51/52/53/59/64/65/66/69/71) — **ambiguous**: their
  stroke files are scattered across ~10 prior-lane dirs with inconsistent naming
  (`_symbol_anchored_stroke` / `_design_path_` / `_regrade_` / `_redline_stroke`) and
  multiple candidates per log (log65 has 9). **No single authoritative list** → choosing
  "the" final artifact would require filename inference (forbidden) or a unified re-render
  (forbidden).
- **8 non-drawn** — clean: **zero** stroke artifacts (no contamination, nothing faked).
- The Phase-1 example's placeholder artifact records (synthesized, mostly 1/log) do **not**
  match the real **per-sheet** outputs (25 count mismatches), so the example cannot be fed
  to the publisher against real files as-is.

**No real manifest was published and no real-publish claim is made.** A full 50/50 publish
needs Phase 2B: generate the input manifest's artifact records from the sweep report's
`verdicts[*].artifacts` for the 37, plus a unified re-render (or owner-confirmed single-file
selection) to give the 13 `ALREADY_DRAWN` an authoritative artifact list.

## Not yet built (explicit Phase boundary)

Phases 1–2A delivered the **contract, example, mock UI, and artifact publisher**; Phase 2A.5
inspected existing artifacts (above). Still **not** built:

- a clean parameterized **solving runner** that *generates* the manifest + final artifacts
  from a render (the publisher consumes artifacts; it does not produce them — the upstream
  is still Brenham-hardcoded proof/sweep scripts);
- an **actual published run on real render outputs** — Phase 2A.5 found the 37 `NEW_TARGETS`
  ready but the 13 `ALREADY_DRAWN` ambiguous, so no real publish was performed;
- a **full solve/render benchmark**;
- any **website/backend wiring** or deploy.

Safe next work against this contract: a **contract-first mock UI** that consumes the
example manifest (status/provenance chips, blocked-log CTAs, the “50 of 58 accounted”
honesty header, artifact rendering by manifest reference) — with **no live engine wiring**.
