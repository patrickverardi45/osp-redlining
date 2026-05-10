# TrueLine — KMZ Semantic Ingestion Regression Tests

Phase 1E · Lock-down suite for `_build_kmz_semantic`.

---

## What these tests do

14 `unittest` tests that lock down the current behaviour of the KMZ
semantic parser (`_build_kmz_semantic` in `backend/main.py`).  
No production files are modified. No external services are required.  
Zero new dependencies — stdlib `unittest`, `zipfile`, and `io` only.

---

## Run all tests (PowerShell)

```powershell
cd c:\Nova\projects\TrueLine\TrueLine_Beta\backend
python -m unittest discover -s tests -t . -v
```

Expected output (abridged):

```
test_01_parser_runs_without_exception ... ok
test_02_parser_version_present ... ok
...
test_14_no_unexpected_top_level_keys ... ok
----------------------------------------------------------------------
Ran 14 tests in X.XXXs

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
| `tests/test_semantic_ingestion.py` | 14 lock-down assertions |

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
