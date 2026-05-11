# TrueLine — KMZ Semantic Ingestion Regression Tests

Phase 1E/1F-B/1G-B/1H-B-II/1I-C-Tests/1K/1L/1M/1O/1P/1Q/1S/1T · Lock-down suites for semantic ingestion, MatchAudit, disagreement taxonomy, review labels, analytics, fidelity audit, topology sidecar, redline continuity advisors, endpoint validator, and snap recommendations.

---

## What these tests do

212 `unittest` tests across fourteen suites:

| Suite | File | Tests | Covers |
|---|---|---|---|
| Phase 1E | `test_semantic_ingestion.py` | 14 | `_build_kmz_semantic` parser lock-down |
| Phase 1F-B | `test_match_audit.py` | 7 | `_append_match_audit_entry` + `get_match_audit` |
| Phase 1G-B | `test_match_audit_v2.py` | 12 | `_append_match_audit_v2_entries` + `get_match_audit_groups` |
| Phase 1H-B-II (A) | `test_match_shadow_compare.py` | 11 | `_append_match_shadow_compare_entries` + `get_match_shadow_compare` |
| Phase 1H-B-II (B) | `test_match_shadow_summary.py` | 13 | `_compute_match_shadow_summary` + `get_match_shadow_summary` |
| Phase 1I-C-Tests | `test_match_shadow_disagreements.py` | 17 | `_compute_match_shadow_disagreements` + `get_match_shadow_disagreements` |
| Phase 1K | `test_review_labels.py` | 16 | `_append_review_label` + 3 endpoints + isolation regression |
| Phase 1L | `test_review_label_summary.py` | 15 | `_compute_review_label_summary` + `get_review_label_summary` |
| Phase 1M | `test_kmz_fidelity_audit.py` | 14 | `_compute_kmz_fidelity_audit` + `get_kmz_fidelity_audit` |
| Phase 1O | `test_kmz_topology_sidecar.py` | 14 | `_build_kmz_topology_sidecar` + `get_kmz_topology_sidecar` + policy regression |
| Phase 1P | `test_redline_topology_continuity.py` | 14 | `_build_redline_topology_continuity` + `get_redline_topology_continuity` + AST regression |
| Phase 1Q | `test_redline_node_continuity.py` | 17 | `_build_redline_node_continuity` + `get_redline_node_continuity` + AST regression |
| Phase 1S | `test_redline_endpoint_validation.py` | 24 | `_build_redline_endpoint_validation` + schema/classification/summary/AST regression + Brenham smoke (skipped when STATE empty) |
| Phase 1T | `test_endpoint_snap_recommendations.py` | 24 | `_build_endpoint_snap_recommendations` + schema/coordinate/delta/AST regression + Brenham smoke (skipped when STATE empty) |

No production files are modified. No external services are required.  
Zero new dependencies — stdlib `unittest`, `tempfile`, `zipfile`, and `io` only.

---

## Run all tests (PowerShell)

```powershell
cd c:\Nova\projects\TrueLine\TrueLine_Beta\backend
python -m unittest discover -s tests -t . -v
```

Expected output (abridged):

```
test_01_append_creates_row_with_correct_schema ... ok
...
test_07_helper_never_raises ... ok
test_01_append_match_audit_v2_creates_rows ... ok
...
test_12_match_audit_v2_helper_never_raises ... ok
test_01_shadow_compare_creates_rows ... ok
...
test_11_shadow_compare_helper_never_raises ... ok
test_01_summary_empty_rows_returns_valid_skeleton ... ok
...
test_13_summary_stability_note_exact ... ok
test_01_parser_runs_without_exception ... ok
...
test_14_no_unexpected_top_level_keys ... ok
----------------------------------------------------------------------
Ran 57 tests in X.XXXs

OK
```

---

## Run a single test

```powershell
cd c:\Nova\projects\TrueLine\TrueLine_Beta\backend
python -m unittest tests.test_semantic_ingestion.TestSemanticIngestion.test_13_replay_determinism -v
```

---

## File map

| File | Purpose |
|---|---|
| `tests/__init__.py` | Makes `tests/` a package (empty) |
| `tests/fixtures/__init__.py` | Makes `fixtures/` a package (empty) |
| `tests/fixtures/synthetic_kmz.py` | Builds a deterministic in-memory KMZ from inline KML |
| `tests/test_semantic_ingestion.py` | 14 lock-down assertions (Phase 1E) |
| `tests/test_match_audit.py` | 7 lock-down assertions (Phase 1F-B) |
| `tests/test_match_audit_v2.py` | 12 lock-down assertions (Phase 1G-B) |
| `tests/test_match_shadow_compare.py` | 11 lock-down assertions (Phase 1H-B-II A) |
| `tests/test_match_shadow_summary.py` | 13 lock-down assertions (Phase 1H-B-II B) |
| `tests/test_match_shadow_disagreements.py` | 17 lock-down assertions (Phase 1I-C-Tests) |
| `tests/test_review_labels.py` | 16 lock-down assertions (Phase 1K) |
| `tests/test_review_label_summary.py` | 15 lock-down assertions (Phase 1L) |
| `tests/test_kmz_fidelity_audit.py` | 14 lock-down assertions (Phase 1M) |
| `tests/test_kmz_topology_sidecar.py` | 14 lock-down assertions (Phase 1O) |
| `tests/test_redline_topology_continuity.py` | 14 lock-down assertions (Phase 1P) |
| `tests/test_redline_node_continuity.py` | 17 lock-down assertions (Phase 1Q) |
| `tests/test_redline_endpoint_validation.py` | 24 lock-down assertions + Brenham smoke (Phase 1S) |
| `tests/test_endpoint_snap_recommendations.py` | 24 lock-down assertions + Brenham smoke (Phase 1T) |

---

## Fixture design

The fixture builds a KMZ in memory (no binary committed to git).  
Each expected count is derivable by reading the inline KML + the
`_kmz_semantic_classify` heuristics in `main.py`.

| Placemark | Classification | Confidence | In anchor catalog? |
|---|---|---|---|
| HH-001 | handhole | high | Yes |
| VAULT-A | structure_marker | medium | Yes |
| MAIN-LINE | route_segment | low | No (low confidence) |
| RESOLVED-PT | annotation | low | No (annotation not an anchor kind) |
| UNRESOLVED-PT | annotation | low | No |

Style counts: 1 declared Style, 1 StyleMap, 2 referenced styleUrls,  
1 unresolved reference (`missingStyle`).

---

## When a test fails

These are **lock-down tests**, not aspirational tests.  A failure after a
*legitimate* parser improvement is expected.

1. Confirm the change is intentional.  
2. Update the relevant `EXPECTED_*` constant in `test_semantic_ingestion.py`.  
3. Add a code comment explaining why (e.g. `# updated in parser-v2: …`).  

**Do not "fix to green" by tweaking constants without understanding why.**

---

## Phase roadmap

| Phase | Description |
|---|---|
| 1E (now) | Synthetic fixture + lock-down tests — baseline |
| 1F | Opt-in real KMZ fixture (env-gated, file outside git) |
| 1G | Ledger-write determinism test (writes to tempdir) |
| 1H | Semantic-assisted matching shadow — safe because 1E provides a regression net |
