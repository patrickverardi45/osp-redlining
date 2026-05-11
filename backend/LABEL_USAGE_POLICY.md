# TrueLine — Label Usage Policy

Phase 1K · Review Label Telemetry

---

## What review labels are

`review_labels.jsonl` is an **append-only observability log**.  
Each row records a human reviewer's opinion about a single shadow-disagreement entry:
`useful_catch`, `noise`, `unclear`, or `cleared`.

---

## What review labels are NOT

Labels are **not** any of the following:

| Forbidden use | Why |
|---|---|
| Operational feedback | Labels never alter route selection, matching, or scoring |
| Auto-learning input | Labels are not fed to any model or heuristic |
| Threshold tuning | Labels do not adjust any numeric threshold |
| Route promotion | Labels cannot activate, demote, or weight any route |
| AI/ML training data | No ML or training usage without explicit governance approval |
| Auto-review triggers | No label triggers any automatic re-processing |

---

## Strict isolation rules

1. **Read boundary**: `_append_review_label`, `get_review_labels`, and `get_review_labels_current` are the ONLY functions that read or write `review_labels.jsonl`. No matching, scoring, or rendering code path imports or calls these functions.

2. **No feedback loops**: Labels are written by the UI and read back by the UI diagnostics panel only. They do not flow into `_build_kmz_semantic`, `_build_semantic_match_shadow`, `_compute_match_shadow_disagreements`, route matching, or any pipeline function.

3. **Append-only**: Old rows are never mutated. Latest-write-wins resolution is applied only at read time, for display purposes.

4. **Cap enforcement**: The file is tail-truncated to `REVIEW_LABELS_MAX_ROWS = 5000` after each append to prevent unbounded growth.

---

## Governance requirements for future use

Any use of review labels beyond read-only UI display — including:

- training data export
- threshold calibration
- automated scoring adjustments
- feedback loop construction

**requires explicit written governance approval before implementation.**

---

## Regression protection

`backend/tests/test_review_labels.py` includes a regression assertion that verifies no matching or scoring code path calls `_append_review_label`, `get_review_labels`, or `get_review_labels_current`.

If that test fails after a code change, investigate before proceeding.
