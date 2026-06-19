# TrueLine v2 — Engine Completion / Website-Readiness Audit

> **READ-ONLY AUDIT.** Engine-to-website *contract* audit — not website work, not backend wiring.
> No engine/renderer/backend/web/runtime/fixture/anchor/corpus/census/parent-model mutation; no
> render; no production flag; no deploy. Generated 2026-06-19 (continued-34 arc).

## Provenance / state at time of audit

| Field | Value |
|---|---|
| Branch | `feat/truelinev2` |
| HEAD | `b083b76` (accountability-ledger docs commit) |
| Latest render commit | `c19b565` (log3 wired + drawn) |
| `origin/feat/truelinev2` | `b083b76` (in sync) |
| `origin/main` | `068a279` (untouched) |
| Deploy / production wiring | none |
| Drawn frontier | **50 / 58** |
| Companion ledger | [`wiki/trueline_v2_50_of_58_accountability_table.md`](trueline_v2_50_of_58_accountability_table.md) |

## Audit conclusion (preserved verbatim)

- **The engine is accountability-complete for the current source package.** Every one of the 58 bore
  logs is classified into exactly one bucket (50 drawn / 1 covered / 4 owner-locked / 2 source-gap /
  1 missing-sheet). There are zero unaccounted logs.
- **The engine is NOT 58/58 drawn-complete.** It is **50/58 drawn**. The remaining 8 are accounted but
  not drawn (1 covered-by-existing + 7 named blockers).
- **The engine is NOT website-ready yet.** The gating gap is a *contract boundary*, not more redlines.
- **Honest current claim: `50 drawn / 1 covered (log14) / 7 named blockers`** (4 owner-locked abstain,
  2 source-gap, 1 missing-source-sheet). Accountability-complete, **not** placement-complete. Never
  present as "58/58."

## Two truth axes — do not conflate

v2 carries **two orthogonal truth surfaces**. The website must consume the first; the second is a
separate review-readiness view.

1. **Drawn-redline accountability (this audit's axis).** What the engine actually strokes: **50/58
   drawn**, captured by the sweep constants + live sweep result + the committed accountability ledger.
2. **Reviewer-lane completion census** (`final_engine_truth_table.json`, frozen buckets OFF
   31/6/1/17/3 = 58, ON 22/1/4). This is *product review readiness* (DRAWABLE_REVIEW, PICK_CARD_REVIEW,
   …), **not** drawn status. The truth-table header itself notes the axes are orthogonal (a bore can be
   stroke-eligible yet a product PICK_CARD, or product-placed yet stroke STRUCTURE_IDENTITY).

> **Do not consume the reviewer-lane census as drawn status, and do not consume drawn status as review
> readiness.** They answer different questions.

## Key blockers to website wiring

1. **No stable machine-readable redline manifest.** The richest per-log render data is the sweep report
   `data/outputs/callout_route_assembly_sweep/callout_route_assembly_sweep.json` (`verdicts`,
   `artifacts`, `closure`, `bound_labels`, `parent_source_gate`, `leg_summary`) — but it is
   **gitignored, generated only under `TL2_TRY_DRAW_E2E=1`, and Brenham-hardcoded**. There is no
   tracked, schema-pinned, drawn-redline manifest.
2. **No clean parameterized project runner.** v2 is proof/sweep-script driven. The render path is
   `python -m truelinev2.proof.run_callout_route_assembly_sweep` (`main() -> int`), hardcoded to the
   Brenham plan PDF + corpus + frozen census + adjudication doc. The typed seam (`truelinev2/seam/`)
   drives only **3 exemplars** (log53/64/71); the API (`truelinev2/api/app.py`, default-OFF
   `run_assembly_api_optin`) is a **review-card transport**, not a redline/manifest runner.
3. **Final artifacts are gitignored / on-demand / not stable published outputs.** Render PNGs land in
   `data/outputs/callout_route_assembly_sweep/{log_id}_{n}.png`; `.gitignore` ignores all of `data/`
   (0 tracked), and **stale PNGs are deleted at the start of every run**. Paths are not durable or
   versioned.
4. **Runtime / performance not benchmarked.** The heavy render e2e is deliberately excluded from the
   fast suite (gated behind `TL2_TRY_DRAW_E2E=1` + PDF presence); the exemplar driver uses a 600 s
   per-proof timeout. A full multi-sheet solve+render across ~50 bores has no measured wall-clock /
   memory profile.
5. **Raw `parent_source_model.json placement_status` is stale and unsafe for website consumption.**
   log3/log42/log44/log30 read `BLOCKED_OR_UNATTEMPTED`/`HELD` in that file yet are drawn (renders come
   from gated overrides applied at solve time; the field is never written back). The field must not be
   used to derive drawn status.
6. **Proof / helper artifacts must not be treated as final redline output.** `data/manual_adjudications/
   evidence/**` are owner-review **screenshots**; the many `*_proof` / `*_slice` / `*_probe` scripts
   emit helper crops. The website must consume **only** the final route-stroke PNGs listed in a
   manifest's `artifacts`, and must **never infer status from a filename** or from a PNG's presence on
   disk (absence ≠ blocked; presence ≠ drawn).

## Source-of-truth (today vs future)

| Concern | Today (authoritative) | Future canonical (website) |
|---|---|---|
| Drawn set (50) | `ALREADY_DRAWN ∪ NEW_TARGETS` in `run_callout_route_assembly_sweep.py`, asserted by its test | generated **`redline_manifest.json`** (override-resolved, SHA-pinned) |
| Per-log render detail | live sweep report JSON `verdicts` / `rendered_full` (on-demand, gitignored) | the manifest |
| Accountability rollup | committed accountability ledger (human-readable) | the manifest + a machine accountability report |
| Review readiness | `final_engine_truth_table.json` (separate axis) | unchanged, kept separate |
| **Never consume** | `placement_status`; `adj_corrected_span` for log48 (`5+14`) / log70 (`1+45`); raw fixture coordinates; filenames | — |

## Status / provenance contract

**Status enum (required floor — 5):**

- `DRAWN_REDLINE`
- `COVERED_BY_EXISTING_REDLINE`
- `OWNER_LOCKED_ABSTAIN`
- `SOURCE_GAP_BLOCKED`
- `MISSING_SOURCE_SHEET_BLOCKED`

**Provenance enum (required floor — 6):**

- `DETERMINISTIC_AUTO`
- `OWNER_CONFIRMED_HUMAN_ADJUSTABLE`  ← **log3** (preserved; **NOT** `DETERMINISTIC_AUTO`)
- `COVERED_BY_EXISTING_REDLINE`
- `BLOCKED_OWNER_LOCKED`
- `BLOCKED_SOURCE_GAP`
- `BLOCKED_MISSING_SOURCE`

| status | provenance | logs |
|---|---|---|
| `DRAWN_REDLINE` | `OWNER_CONFIRMED_HUMAN_ADJUSTABLE` | **log3** (owner geometry; human-adjustable lane) |
| `DRAWN_REDLINE` | `DETERMINISTIC_AUTO` | the other 49 drawn |
| `COVERED_BY_EXISTING_REDLINE` | `COVERED_BY_EXISTING_REDLINE` | log14 (covered by drawn log10) |
| `OWNER_LOCKED_ABSTAIN` | `BLOCKED_OWNER_LOCKED` | log5, log31, log38, log43 |
| `SOURCE_GAP_BLOCKED` | `BLOCKED_SOURCE_GAP` | log15, log16 |
| `MISSING_SOURCE_SHEET_BLOCKED` | `BLOCKED_MISSING_SOURCE` | log57 |

> **log3 is explicitly preserved as `OWNER_CONFIRMED_HUMAN_ADJUSTABLE`, never `DETERMINISTIC_AUTO`.**
>
> **Honesty note (Patrick decision):** the "49 AUTO" actually mixes *pure-deterministic* renders with
> *owner-confirmed plan-route / endpoint-identity* renders (e.g. log48/70/61/62/2/8/27/32/44/42/19/49/
> 30/9/23 + the owner-reviewed span promotions). Per doctrine these remain in the deterministic/AUTO
> census (log3 is the *first* owner-**geometry** render to enter the production path), so collapsing
> them to `DETERMINISTIC_AUTO` is defensible. A **7th label `OWNER_CONFIRMED_PLAN_ROUTE`** would be more
> honest for the website; the floor of 6 is met either way.

## Proposed `redline_manifest.json` schema (contract-first target)

A versioned, SHA-pinned manifest emitted by the clean runner to a **tracked published** location
(separate from the gitignored working dir). The website consumes **only** this.

```jsonc
{
  "schema_version": "1.0",
  "project_id": "<project>",
  "generated_from": {
    "engine_commit": "<git sha>",
    "corpus_sha": "<hash of plan PDF + bore-log source>",
    "generated_at": "<ISO-8601>"          // stamped by the runner, not the consumer
  },
  "accountability": {                       // machine rollup; must reconcile to total
    "total": 58, "drawn": 50, "covered": 1,
    "owner_locked_abstain": 4, "source_gap_blocked": 2, "missing_source_sheet_blocked": 1
  },
  "logs": [
    {
      "log_id": "log3",
      "parent_id": "bore_log3",
      "entry_role": "standalone_bore",
      "span": "12+63->21+63",
      "source_sheets": [3, 4, 5],
      "status": "DRAWN_REDLINE",
      "provenance": "OWNER_CONFIRMED_HUMAN_ADJUSTABLE",
      "drawn": true,
      "owner_confirmed_geometry": true,
      "closure": { "span_ft": 250, "drawn_ft": 247.0, "closes": true },
      "coverage": { "downstream_covered_by": ["log4"] },   // when applicable
      "artifacts": [
        { "sheet": 2, "leg_kind": "start_leg", "path": "<published>/log3_0.png", "sha256": "<hash>" },
        { "sheet": 3, "leg_kind": "owner_confirmed_segment", "path": "<published>/log3_1.png", "sha256": "<hash>" }
      ],
      "blocker": null
    },
    {
      "log_id": "log14",
      "status": "COVERED_BY_EXISTING_REDLINE",
      "provenance": "COVERED_BY_EXISTING_REDLINE",
      "drawn": false,
      "coverage": { "covered_by": "log10" },
      "artifacts": [], "blocker": null
    },
    {
      "log_id": "log57",
      "status": "MISSING_SOURCE_SHEET_BLOCKED",
      "provenance": "BLOCKED_MISSING_SOURCE",
      "drawn": false, "artifacts": [],
      "blocker": { "name": "missing .FS drive-decomposition sheet",
                   "unlock_requirement": "the absent .FS drive sheet that decomposes this drive" }
    }
    // ... all 58 logs
  ]
}
```

**Field-safety rules baked into the schema:** `drawn` comes from the manifest only (never a filename);
artifacts carry per-file `sha256` + `(sheet, leg_kind)`; blocked logs carry a `blocker.unlock_requirement`;
the manifest is pinned to `engine_commit` + `corpus_sha` so stale fixtures cannot leak.

## Required pre-website tasks

1. **Clean parameterized runner.** Project-parameterized (not Brenham-hardcoded), idempotent,
   deterministic. **Inputs:** plan PDF · bore-log source / reviewed structured data · project config.
   **Outputs:** manifest · redline artifacts · accountability report · blocker report ·
   evidence/provenance report.
2. **Schema-pinned `redline_manifest.json`** (the contract above) — versioned, with `schema_version`
   and `generated_from` SHAs; override-resolved (gated overrides applied), so it never exposes stale
   fixture fields.
3. **Stable artifact publishing path with SHA hashes.** A durable, versioned location (not the
   gitignored on-demand `data/outputs/` working dir); every artifact referenced by relative path +
   `sha256` + sheet/leg metadata.
4. **Status / provenance contract** (the 5 + 6 enums above), with log3 preserved as
   `OWNER_CONFIRMED_HUMAN_ADJUSTABLE`; optional 7th `OWNER_CONFIRMED_PLAN_ROUTE` for finer honesty.
5. **Full solve / render benchmark.** Measured end-to-end wall-clock (cold + warm), peak memory, and
   per-bore worst case on a representative project — to decide background-job vs synchronous. (Heavy;
   a named future task — do not run inside a web request path.)
6. **Repo hygiene cleanup / ignore policy.** ~50 untracked non-ignored scratch files today (proof
   probes under `truelinev2/`, `gac/` packets, root loose files like `probe_err.txt`/`skills-lock.json`,
   `.agents/`, `backend/tl_core/`) — the `git add -A` landmine. Triage keepers vs scratch; add ignore
   rules or a dedicated scratch dir; always use **path-scoped adds**, never `git add -A`.
7. **Default-OFF flag + rollback plan.** v2 stays behind a default-OFF flag; manifest+artifacts shipped
   as a versioned, regenerable build artifact (never hand-edited); one-flag-flip rollback; no merge to
   `main` without a tested manifest **and** the benchmark; monolith/Render/Vercel untouched until
   runner + manifest + benchmark exist.

## Performance / runtime stance

- The heavy render path is **deliberately excluded** from the default suite (`TL2_TRY_DRAW_E2E=1`
  gate); 600 s per-proof timeouts; multi-sheet PDF parse + per-bore solve + stroke render.
- **Unsafe to assume it is a viable synchronous web request.** Recommend a **background job** that
  produces the manifest + artifacts; the website consumes the published manifest/artifacts and never
  invokes the solver inline. Benchmark (task 5) before any Render/Vercel sizing.

## Blocked-log product messaging

| group | logs | unlock input |
|---|---|---|
| `OWNER_LOCKED_ABSTAIN` | log5, log31, log38, log43 | owner lifts the abstain + supplies a safe, source-backed endpoint identity (`must_remain_abstained`) |
| `SOURCE_GAP_BLOCKED` | log15, log16 | the sheet-5+ head-end source where the unprinted ruler-cut start is printed |
| `MISSING_SOURCE_SHEET_BLOCKED` | log57 | the absent `.FS` drive-decomposition sheet |

- Headline metric: **"50 drawn of 58 accounted"** — denominator always shown.
- The 1 covered + 7 blocked are visible and labeled; blockers carry a **call-to-action** (owner input /
  source upload), never a green check.
- Never roll covered/blocked into "drawn"; never display 58/58. log14 = "already on the plan as log10,"
  not a separate stroke.

## Safe website work that can start now

- **Build the website contract-first against the proposed `redline_manifest.json` schema using mock
  data** — status/provenance enums, blocked-log CTAs, the "50 of 58 accounted" honesty UI, artifact
  rendering by manifest reference. This is fully decoupled and zero-coupling to the engine.
- **No live engine wiring yet.** Do not invoke the solver, do not read `parent_source_model.json` raw
  fields, do not read filenames for status.

## Stored-anchor debt — `B-DATA-LOG48-ADJ-1`

- **Summary:** `log48` (`adj_corrected_span "0+00->5+14"`) and `log70` (prior start `1+45`) carry
  stale/corrupted fixture values in `parent_source_model.json`. log48's `5+14` is sibling **log50's**
  route (the original mixup); log70's `1+45` is superseded. Both render **correctly** today via gated
  `OWNER_CONFIRMED_PLAN_ROUTES` overrides (log48 → `5+07`, sheets 10+12; log70 → start re-anchored
  `4+54`), but the stored fields still disagree with reality. Repair only under a **census re-baseline**.
- **Does it block website work? No** — the renders are correct. **But it is a source-of-truth hazard:**
  any consumer reading the raw fixture fields gets wrong values for log48/log70 (and stale drawn-status
  for every override/gated log).
- **Prevention:** consume **only** the override-resolved, commit-SHA-pinned manifest — never the raw
  `parent_source_model.json` fields. Repair the fixtures later under a re-baseline so the model
  eventually agrees; until then, fixtures are **not** a consumption surface.

## Forbidden until explicit authorization

Engine code · renderer (`truelinev2/render/`, `render/crop.py`) · fixtures/anchors/coordinates
(`parent_source_model.json`, `brenham_known_answers.json`) · census (`final_engine_truth_table.json` +
frozen buckets) · backend · web · runtime · production flags · `origin/main` · deploy ·
`START_HERE_TRUELINE_V2.md` bump · solving the 7 blockers. All changes surgical, reversible,
minimal-blast-radius.

---
*Sources: `truelinev2/proof/run_callout_route_assembly_sweep.py` (main, OUT_DIR, TRUTH, ALREADY_DRAWN/
NEW_TARGETS, gated overrides) · `truelinev2/tests/test_callout_route_assembly_sweep.py` ·
`truelinev2/proof/run_final_engine_truth_table.py` · `truelinev2/proof/run_exemplar_pipeline_end_to_end_driver.py`
(+ `truelinev2/seam/`) · `truelinev2/proof/run_run_assembly_api_contract.py` (+ `truelinev2/api/app.py`,
`Settings`) · `truelinev2/ingest/parent_source/parent_source_model.json` · `.gitignore` · git
status/ls-files/check-ignore. Read-only; no engine/render/census/backend/web touched.*
