# `STA ` Station-Label Normalization — ACTIVATION (PARENT-CHILD-RECON-2A)

**Branch:** `feat/truelinev2` · **Engine HEAD:** `eb5740c` → this commit · **Date:** 2026-06-13
**Type:** narrow engine/data activation — flips the RECON-2 `normalize_station_label`
opt-in from default-OFF to default-ON, then updates only the baselines that
intentionally change. No UI · no web · no deploy · no cleanup.

---

## What this does

PARENT-CHILD-RECON-2 proved (default-OFF) that the `STA ` station-label
normalization is isolated to log37/log38 and that activating it moves exactly
those two. RECON-2A makes that the **active Brenham ingest behavior**:

- `read_brenham_borelog(..., normalize_station_label=True)` and
  `load_borelog(..., normalize_station_label=True)` are now the **defaults**.
- `parse_station` is **unchanged** (the normalization is still a reader-level strip
  of a leading `STA`/`STA.`/`STA:` label before parsing; bare stations and
  non-station text are untouched; no fuzzy OCR).
- Pass `normalize_station_label=False` to recover the pre-activation byte-identical
  load (the OFF-leg proof `run_station_label_optin_sweep` still does exactly this).

## Exact movement — only log37/log38

A full 58-row truth-table per-bore diff (pre vs post activation) confirms **exactly
two rows change; the other 56 are byte-identical**:

| bore | before | after | why |
|---|---|---|---|
| **log37** | `SOURCE_REVIEW_REQUIRED` / `BORE_SOURCE_UNPARSEABLE` | **`PLACED_REVIEW`** (DRAWABLE), `3+50→4+08`, sheet 23 | stations were present (`STA 3+50`/`STA 4+08`); existing engine law places it — **not forced** |
| **log38** | `SOURCE_REVIEW_REQUIRED` / `BORE_SOURCE_UNPARSEABLE` | **`OUT_OF_CLASS`** (`END_POSITION_UNRESOLVED`), `0+62→16+21`, sheets 25,27 | stations present (`STA 0+62`…`STA 16+21`); the endpoint/path is **not deterministically locatable**, so the engine abstains — **not promoted to placed** |

**log38 is deliberately NOT over-promoted.** The operator manually checked the
plan and could locate the **HH at 16+21** but **could not safely locate 0+62**, so
log38 must stay non-placed exactly as the engine's own law decides (`OUT_OF_CLASS`,
endpoint unresolved). RECON-2A does not add any endpoint/path inference for it.

## Census before → after (intentional, documented)

The only changes are the two bores above:

| surface | before | after |
|---|---|---|
| M8.11 default baseline | `AUTO 14 / REVIEW 10 / ABSTAIN 32 / ERROR 2 / PLACED 24` | `AUTO 14 / REVIEW 11 / ABSTAIN 33 / ERROR 0 / PLACED 25` |
| M8.11 fullest-safe lanes | `PLACED 30 / PICK 16 / ADJUST 6 / OUT_OF_CLASS 4 / SOURCE_REVIEW 2` | `PLACED 31 / PICK 16 / ADJUST 6 / OUT_OF_CLASS 5` (SOURCE_REVIEW → 0) |
| completion buckets | `DRAWABLE 30 / … / SOURCE_REVIEW_REQUIRED 2` | `DRAWABLE 31 / … / OUT_OF_CLASS 1` (SOURCE_REVIEW_REQUIRED → 0) |
| route-stroke census | `25/13/5/5/4/3/1/2` (incl. `BORE_SOURCE_UNPARSEABLE 2`) | `26/13/5/6/4/3/1` (`END_IDENTITY 26`, `END_POSITION 6`; `BORE_SOURCE_UNPARSEABLE → 0`) |
| headline | drawable 30 / review-ready 53 / source-owner 5 | drawable 31 / review-ready 54 / source-owner 3 |

`ERROR 2 → 0`, `PLACED +1`, `OUT_OF_CLASS +1`, `SOURCE_REVIEW_REQUIRED 2 → 0` — all
attributable solely to log37 (+1 placed) and log38 (+1 out-of-class).

## Baselines updated (intentional)

The corrected-source baseline that ~20 proofs froze (`…ERROR 2 / 24 placed` and the
`30/.../2` fullest lanes / `25/13/5/5/4/3/1/2` stroke census) is updated **only**
where the change is the log37/log38 movement:

- `run_final_engine_truth_table` (M8.27) — `BANKED_STROKE_CENSUS`,
  `BANKED_FULLEST_LANES`, `BANKED_DEFAULT_STATUS`, G10/G11/G12 + the M8.27 test.
- corpus sweeps: `run_station_axis_interval_containment` / `…_optin_sweep`
  (combined-ceiling 30→31), `run_reverse_endpoint_anchor_proof` / `…_optin_sweep`,
  `run_reset_collision_optin_sweep` (OFF + ON legs) / `run_reset_collision_rule_proof`,
  `run_frame_aware_continuation_optin`, `run_frame_optin_validation`,
  `run_frame_ownership_candidates`.
- reviewer/group/run-assembly contracts: `run_reviewer_service_contract`,
  `run_reviewer_payload_contract`, `run_group_review_service_proof`,
  `run_group_review_transport_proof`, `run_run_assembly_review_service_proof`.
- banked boundary proofs: `run_run_assembly_phase0` / `…_extract`,
  `run_terminus_attribution_phase0` / `…_extract`,
  `run_kmz_matchline_substitute_phase0` (`BANKED_FULLEST_LANES`).
- the RECON-2 test `test_station_label_normalization` (the default is now ON).

Every other proof / the `STA `-prefix scan / the RECON-1 + RECON-2 Part B proofs are
**unchanged** (they don't assert the changed counts, or they explicitly pass the
OFF flag).

## Verification

- `parse_station` unchanged; the normalization still strips ONLY a leading
  `STA`/`STA.`/`STA:` followed by a valid station (targeted tests).
- **M8.27 truth-table proof PASS** with the new intentional census.
- All affected baseline proofs updated to the measured new values and re-run PASS.
- **PARENT-CHILD-RECON-1 proof PASS** (family map unchanged).
- **RECON-2 Part B proof PASS** (the 13 families' children are unaffected — log37/38
  are standalone, not split children).
- **Full v2 suite PASS**; import-isolation / convention / global-state / red-stroke
  guards green.
- M9.8 not contradicted (unchanged).

## Adversarial audit

- **No broad parser blast radius** — `parse_station` untouched; the strip is
  reader-confined; only `STA `-prefixed cells (log37/log38, proven isolated) differ.
- **Only log37/log38 moved** — full 58-row per-bore diff.
- **log38 not over-promoted** — stays `OUT_OF_CLASS` (endpoint unresolved); no
  endpoint inference added; matches the operator's manual finding (0+62 not
  safely locatable).
- **log37 not hardcoded** — its placement is produced by the shipped engine law on
  the now-parseable stations (run via the reviewer pipeline), not a literal.
- **No unrelated baseline drift** — every updated baseline changes by exactly the
  log37/log38 delta (`ERROR 2→0`, `PLACED +1`, `OUT_OF_CLASS +1`).
- **No UI/web/deploy/main/v1.**

## Posture

Narrow activation: the only behavior change is the `normalize_station_label`
default; `parse_station` unchanged; shared core (`match`/`schema`) untouched; no
proximity/nearest/length; no OCR correction invented; no AUTO wording forced; no
geometry/strokes/PNG; no UI/API/web/deploy/main/v1; no cleanup. Pre-activation
behavior remains reproducible via `normalize_station_label=False`.
