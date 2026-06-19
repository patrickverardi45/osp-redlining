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

## Phase 2B — unified-50 render + real publish: STOPPED at the precondition

Authorized to render the 50 drawn logs into one authoritative directory and publish a real
manifest — but **stopped at the feasibility gate** (no render run, no manifest published, no
partial-as-full claim). Determined by `truelinev2/proof/run_redline_manifest_unified50_render_publish.py`
(read-only gate that renders/publishes nothing unless ALL 50 have one authoritative path):

- **37 `NEW_TARGETS`** render authoritatively via the callout route-assembly sweep — one dir,
  1:1 with the sweep report `verdicts[*].artifacts` (Phase 2A.5). **Ready.**
- **13 `ALREADY_DRAWN`** (log7/25/45/50/51/52/53/59/64/65/66/69/71) are **excluded from that
  sweep by design** (the `ALREADY_DRAWN` skip in `_is_target`) and render only through
  scattered, heterogeneous per-log proofs with **multiple candidate PNGs each** (log65=9,
  log51=5, log59=4, log25=3), log7 only a PARTIAL/representative stroke, and **log50 wired into
  no unified registry**. There is no single authoritative all-50 path.
- Bringing the 13 into one path requires either an **authorized unified solver pass** (changes
  the engine — forbidden in this task) or **owner-confirmed canonical-artifact selection** per
  log (non-source — forbidden). Each needs separate authorization.

The Phase-2A publisher + Phase-2A.5 checksum dry-run already prove the pipe works on the 37's
real render bytes; the missing piece is a **unified render that covers all 50** — that is the
real Phase 2B/2C, and it is engine/solver work, not a contract step.

## Phase 2C — ALREADY_DRAWN canonical render registry (DONE)

`truelinev2/proof/run_already_drawn13_canonical_render_registry.py` pins **one** canonical
existing render entrypoint per ALREADY_DRAWN log (12 from the proven try-draw-all drivers +
**log50** added explicitly — Phase 2B found it standalone) and **re-renders all 13 into one
clean dir** (re-running the proven lanes, *not* selecting old PNGs by filename). Result:
**13/13 rendered, exit 0, no blocker** — 17 final stroke PNGs (~12.5 MB) under the gitignored
`data/outputs/redline_manifest_publish/already_drawn13_canonical/<log>/`. Every collected
artifact is a redline **stroke** (helper crops filtered out; `other_png=0`); log7 flagged
`PARTIAL` (representative interior route); log50 rendered its splice-46 cross-sheet two legs.
No geometry/solver/fixture/census change — each lane is an existing proof driven out-of-process;
drawn-truth from the manifest, never filenames. Static integrity locked by
`truelinev2/tests/test_already_drawn13_render_registry.py`.

**All 50 drawn logs now have authoritative artifacts** (37 NEW_TARGETS in the sweep dir + 13
ALREADY_DRAWN in the canonical dir) — the Phase-2B unified-render precondition is satisfied
**without** an engine/solver change, by re-rendering the 13's existing canonical lanes.

## Phase 2D — all-50 real manifest published (DONE)

`truelinev2/proof/run_redline_manifest_all50_publish.py` assembled the first **real** all-50
redline manifest: it merges the two authoritative artifact sources — 37 NEW_TARGETS from the
sweep report `verdicts[*].artifacts` + 13 ALREADY_DRAWN from the Phase-2C canonical report —
into one publisher input, then runs the Phase-2A publisher. Result (gitignored, **NOT committed**)
under `data/outputs/redline_manifest_publish/brenham_c19b565_all50_real_manifest/`:
**`mock_example:false`, counts 58/50/1/7, 83 final stroke artifacts (~50.5 MB), all 50 drawn logs
with ≥1 published `FINAL_REDLINE_PNG`** (real `sha256` + `bytes`, `published:true`,
`example_placeholder:false`). All 83 published files re-verified on disk (0 checksum/flag
mismatches). Semantics preserved: log3 `OWNER_CONFIRMED_HUMAN_ADJUSTABLE`; log7 carries a
PARTIAL/representative warning; log14 covered-by-log10 with **no** artifact; the 7 blocked keep
their unlock requirements with **no** artifacts; log48/log70 stored-anchor debt stays
warning-only. Benchmark: assemble ~4 ms · publish ~97 ms · validate ~2 ms. No render, no solver,
no geometry/fixture change. Assembler logic locked by
`truelinev2/tests/test_redline_manifest_all50_assembler.py` (synthetic inputs; no real artifacts).

**The engine→website contract chain is now end-to-end real for the 50/58 frontier:** schema →
example → mock UI → publisher → unified render registry → **real published all-50 manifest**.

## Phase 2E — published bundle contract (DONE)

`truelinev2/contracts/published_bundle.py` formalizes the **published run bundle** — the durable
static-serving boundary the website will consume: `<bundle_root>/redline_manifest.json` +
`artifacts/<log_id>/<file>.png` + `_published_bundle_index.json`. `validate_bundle()` proves the
manifest is schema-valid and every artifact reference is a **safe in-root relative path** (no
absolute/drive-letter, no `..` traversal, no backslash, no `data/outputs` leakage) that **exists**,
matches its `sha256` + `bytes`, and is `published:true` / `example_placeholder:false`; it also
enforces drawn-has-artifact / covered-blocked-have-none, and reports **static-serving safe** + the
manifest sha256. `build_bundle_index()` emits `_published_bundle_index.json` (bundle format · run
label · project · schema version · engine head/render commit · manifest filename + sha256 ·
artifact count · total bytes · validation summary · generated_at).

Proof against the real Phase-2D bundle (`truelinev2/proof/run_redline_manifest_published_bundle_validation.py`):
**valid YES · 83 artifacts · 50,499,989 bytes · 0 checksum-mismatch / 0 missing / 0 unsafe / 0
schema / 0 structure errors · static-serving safe YES**, manifest sha256 `ddfffff7…3e50689f`.
Contract code + 11 tests run on **tiny temp fixtures** (no 50 MB artifacts moved into the repo).
No render, no engine, no web/backend wiring.

## Phase 2F — one-command local pipeline runner (DONE)

`truelinev2/proof/run_redline_manifest_local_pipeline.py` chains the proven pipeline in one
command: verify the 37 NEW_TARGET sweep artifacts → verify (or, behind `--render-already-drawn13`,
re-render) the 13 ALREADY_DRAWN canonical artifacts → assemble the all-50 input (Phase 2D) →
publish (Phase 2A) → validate the bundle (Phase 2E) → emit one report. Three modes:
**`--validate-existing`** (DEFAULT; no render, no republish), **`--publish-existing-artifacts`**
(fresh bundle from existing artifacts, no render), and the explicit **`--render-already-drawn13`**
(announces render authorization; never re-runs the 37 sweep, never renders blocked/covered logs).
Both no-render modes proven: validate-existing → the Phase-2D/2E bundle VALID (sha256 `ddfffff7…`);
publish-existing → a fresh `…/brenham_c19b565_all50_pipeline/` bundle VALID (83 artifacts · 50.5 MB
· `mock_example:false` · all semantics preserved). Per-phase benchmarks recorded. Locked by
`truelinev2/tests/test_redline_manifest_local_pipeline.py` (synthetic fixtures; no real artifacts).

This phase also fixed a **latent reconciliation bug** surfaced by the pipeline's tiny fixtures:
`redline_manifest_publisher.reconciliation_errors` now compares status/provenance counts per key
with a 0 default, so a manifest with an empty bucket (e.g. a project with 0 covered logs) is no
longer falsely rejected (regression-locked in the publisher test). The real 58-log example —
every bucket non-empty — is unaffected.

## Phase 2G — render-phase benchmark (DONE)

`truelinev2/proof/run_redline_manifest_render_benchmark.py` drove the pipeline in explicit
`--render-already-drawn13` mode (re-rendered ONLY the 13 ALREADY_DRAWN; the 37 NEW_TARGET sweep was
NOT re-run; log14 + the 7 blocked never rendered) → publish → bundle-validate, recording the full
breakdown. Result: **13/13 re-rendered, 0 failures, 17 stroke artifacts**; the final all-50 bundle
**VALID** (83 artifacts · 50.5 MB · schema PASS · static-serving safe · all semantics preserved).
Local timing (Windows, repo venv):

| phase | seconds |
|---|---|
| inspect / verify | 0.002 |
| **render (13 ALREADY_DRAWN)** | **52.16** |
| assemble | 0.001 |
| publish | 0.094 |
| bundle validate | 0.038 |
| **total** | **52.30** |

**Takeaway:** render dominates wall-clock by ~370× over assemble + publish + validate (~0.13 s
combined). The render cost is mostly per-subprocess startup (each of the 13 lanes re-loads the
engine + parses the plan PDF; ~4 s/log), not per-log geometry — so a single-process or warm-engine
runner would cut it sharply. Even so, the whole 13-log re-render-and-publish is **under a minute**;
a background-job model is comfortable and the publish→serve path is effectively instant once
artifacts exist. Benchmark artifact: gitignored
`…/brenham_c19b565_pipeline_render13_benchmark/_phase2g_render_benchmark.json`.

## Phase 2H — NEW_TARGET sweep benchmark (DONE) · full render-cost picture

`truelinev2/proof/run_redline_manifest_newtargets_sweep_benchmark.py` timed the callout-route-
assembly sweep (the 37 NEW_TARGETS, single process), then re-validated the full all-50 bundle
(publish + validate, **no render**). Result: sweep exit 0, **37/37 NEW_TARGETS rendered · 66
stroke-only artifacts (no crops) · 0 blocked/skipped**; ALREADY_DRAWN / covered / blocked correctly
**excluded** by the sweep's own `_is_target`; post-sweep all-50 bundle **VALID** (83 artifacts, all
semantics preserved). Full render-cost picture (local, repo venv):

| phase | seconds | note |
|---|---|---|
| 37 NEW_TARGET sweep (1 process) | **299.6** | ~8.1 s/log — dominated by the route-assembly **solve**, not engine reload |
| 13 ALREADY_DRAWN render (Phase 2G) | 52.2 | ~4 s/log — mostly per-subprocess engine reload |
| downstream publish + bundle-validate | ~0.13 | negligible |
| **estimated full-frontier refresh (all 50)** | **~351.9 (~5.9 min)** | entirely render-bound |

**Takeaway:** a full 50-log refresh is **~6 minutes and entirely render-bound**; assemble + publish
+ validate is ~0.13 s. This confirms the offline/background-job architecture (render offline →
publish a bundle → serve statically) with **no synchronous-web-render risk**. A warm-engine /
single-process unified runner could cut the ~6 min sharply if refresh latency ever matters.
Benchmark artifact: gitignored
`…/brenham_c19b565_newtargets_sweep_benchmark/_phase2h_newtargets_sweep_benchmark.json`.

## Not yet built (explicit Phase boundary)

Phases 1–2H delivered the **contract, example, mock UI, artifact publisher, unified render
registry, a real published all-50 manifest, a validated published-bundle contract, a one-command
local pipeline runner, and a complete render-cost benchmark (13 + 37)**. Still **not** built:

- a **durable published store** with retention/versioning (today the validated bundle lives only in
  gitignored `data/outputs/`);
- **website/backend wiring** to serve the bundle (the Phase-1 mock UI could now consume a real
  bundle as the first integration test) — still no live wiring;
- any deploy.
- *(optional)* a **warm-engine / single-process unified runner** to collapse the ~6 min full refresh.

Safe next work against this contract: a **contract-first mock UI** that consumes the
example manifest (status/provenance chips, blocked-log CTAs, the “50 of 58 accounted”
honesty header, artifact rendering by manifest reference) — with **no live engine wiring**.
