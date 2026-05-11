"""Phase 1H-B-II (Part B) — match-shadow-summary-1 analytics lock-down suite.

13 tests for ``_compute_match_shadow_summary`` and ``get_match_shadow_summary``,
added in Phase 1H-B-I.

ISOLATION STRATEGY
------------------
``_compute_match_shadow_summary`` is a pure function — most tests call it
directly with synthetic row lists and require no monkeypatching.

Tests for ``get_match_shadow_summary`` (endpoint) redirect
``main.MATCH_SHADOW_COMPARE_PATH`` to a temp directory so the endpoint reads
from a controlled file, never from ``uploads/match_shadow_compare.jsonl``.

IF A TEST FAILS after a legitimate Phase 1H-B-I change:
  1. Confirm the change is intentional.
  2. Update the relevant assertion or constant below.
  3. Add a comment explaining why.
  DO NOT "fix to green" without understanding the failure.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional

_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

import main  # noqa: E402

# ---------------------------------------------------------------------------
# Exact stability note (lock-down).
# If the note text changes, update here with a comment explaining why.
# ---------------------------------------------------------------------------
EXPECTED_STABILITY_NOTE: str = (
    "match-shadow-summary-1 metrics are PROVISIONAL until at least 2 distinct "
    "input_sha256 values have each contributed at least 100 groups in the "
    "window. Per-classification (handhole / splice / structure / segment) "
    "and per-route-role rates require Phase 1H-C; the absence of those "
    "fields in this response does not indicate missing data."
)

# Expected top-level key set (10 keys, including computed_at added by endpoint).
EXPECTED_SUMMARY_TOP_KEYS: frozenset = frozenset(
    {
        "schema_version",
        "computed_at",
        "window",
        "shadow_availability",
        "agreement",
        "anchor_participation",
        "top_disagreement_passes",
        "by_input_sha256",
        "guards",
        "stability_note",
    }
)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _fake_summary_row(
    had_shadow: bool = True,
    agreement: Optional[bool] = True,
    anchors_op: int = 2,
    anchors_sem: int = 2,
    sha: str = "a" * 64,
    pass_id: str = "P1",
    decided_at: str = "2026-05-10T05:00:00+00:00",
    group_id: str = "G1",
) -> Dict[str, Any]:
    """Minimal match-shadow-1 row for analytics testing."""
    return {
        "schema_version": "match-shadow-1",
        "decided_at": decided_at,
        "match_pass_id": pass_id,
        "session_id_hint": None,
        "input_sha256": sha,
        "shadow_version": "shadow-1" if had_shadow else None,
        "had_shadow_payload": had_shadow,
        "group_id": group_id,
        "group_index": 0,
        "operational_winner_route_id": "R1",
        "operational_winner_route_name": "Route R1",
        "operational_confidence": 0.9,
        "semantic_winner_route_id": "R1" if agreement is True else ("R2" if agreement is False else None),
        "semantic_winner_route_name": "Route R1" if agreement is True else ("Route R2" if agreement is False else None),
        "semantic_winner_score": 1.5 if had_shadow else None,
        "agreement": agreement if had_shadow else None,
        "anchors_near_operational_winner": anchors_op,
        "anchors_near_semantic_winner": anchors_sem,
        "contributing_anchor_ids": ["a1"] if had_shadow else [],
        "shadow_explanation": "Test explanation." if had_shadow else None,
    }


# ---------------------------------------------------------------------------
# Endpoint helpers
# ---------------------------------------------------------------------------

def _call_summary_endpoint(
    limit: int = 500,
    group_by: str = "none",
) -> Dict[str, Any]:
    """Call get_match_shadow_summary directly; return parsed JSON."""
    response = main.get_match_shadow_summary(limit=limit, group_by=group_by)
    return json.loads(response.body)


# ---------------------------------------------------------------------------
# Test suite
# ---------------------------------------------------------------------------

class TestMatchShadowSummary(unittest.TestCase):
    """Lock-down suite for Phase 1H-B-I shadow divergence analytics."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._orig_path = main.MATCH_SHADOW_COMPARE_PATH
        main.MATCH_SHADOW_COMPARE_PATH = (
            Path(self._tmpdir.name) / "match_shadow_compare.jsonl"
        )

    def tearDown(self) -> None:
        main.MATCH_SHADOW_COMPARE_PATH = self._orig_path
        self._tmpdir.cleanup()

    def _write_rows(self, rows: List[Dict[str, Any]]) -> None:
        """Write synthetic rows to the temp shadow-compare file."""
        lines = [json.dumps(r, separators=(",", ":")) + "\n" for r in rows]
        main.MATCH_SHADOW_COMPARE_PATH.write_text("".join(lines), encoding="utf-8")

    # ------------------------------------------------------------------
    # 01 — empty rows → valid skeleton with all 9 helper keys
    # ------------------------------------------------------------------

    def test_01_summary_empty_rows_returns_valid_skeleton(self) -> None:
        """_compute_match_shadow_summary([]) must return all required keys with safe zero values."""
        summary = main._compute_match_shadow_summary([], "none")

        # Endpoint adds computed_at; helper returns 9 keys
        expected_helper_keys = EXPECTED_SUMMARY_TOP_KEYS - {"computed_at"}
        actual_keys = frozenset(summary.keys())

        missing = expected_helper_keys - actual_keys
        extra = actual_keys - expected_helper_keys
        self.assertEqual(missing, frozenset(), f"Missing keys in empty skeleton: {missing}")
        self.assertEqual(extra, frozenset(), f"Unexpected keys in empty skeleton: {extra}")

        self.assertEqual(summary["window"]["rows_read"], 0)
        self.assertEqual(summary["shadow_availability"]["sample_size"], 0)
        self.assertEqual(summary["agreement"]["agree_count"], 0)
        self.assertEqual(summary["anchor_participation"]["groups_with_anchors_near_op"], 0)
        self.assertEqual(summary["top_disagreement_passes"], [])
        self.assertEqual(summary["by_input_sha256"], [])

    # ------------------------------------------------------------------
    # 02 — shadow_availability rates correct
    # ------------------------------------------------------------------

    def test_02_summary_shadow_availability_rates(self) -> None:
        """10 shadow + 5 no-shadow → shadow_availability_rate = 10/15 = 0.6667."""
        rows = (
            [_fake_summary_row(had_shadow=True)] * 10
            + [_fake_summary_row(had_shadow=False)] * 5
        )
        summary = main._compute_match_shadow_summary(rows, "none")

        avail = summary["shadow_availability"]
        self.assertEqual(avail["sample_size"], 15)
        self.assertEqual(avail["rows_with_shadow_payload"], 10)
        self.assertIsNotNone(avail["shadow_availability_rate"])
        self.assertAlmostEqual(avail["shadow_availability_rate"], round(10 / 15, 4), places=4)

    # ------------------------------------------------------------------
    # 03 — agreement rates correct
    # ------------------------------------------------------------------

    def test_03_summary_agreement_rates(self) -> None:
        """6 agree + 3 disagree + 1 inconclusive (all shadow=True) → exact rates."""
        rows = (
            [_fake_summary_row(had_shadow=True, agreement=True)] * 6
            + [_fake_summary_row(had_shadow=True, agreement=False)] * 3
            + [_fake_summary_row(had_shadow=True, agreement=None)] * 1
        )
        summary = main._compute_match_shadow_summary(rows, "none")

        agr = summary["agreement"]
        self.assertEqual(agr["sample_size"], 10)
        self.assertEqual(agr["agree_count"], 6)
        self.assertEqual(agr["disagree_count"], 3)
        self.assertEqual(agr["inconclusive_count"], 1)
        # sample_size == 10 == MIN_RATE → rates must be non-null
        self.assertIsNotNone(agr["agree_rate"])
        self.assertAlmostEqual(agr["agree_rate"], round(6 / 10, 4), places=4)
        self.assertAlmostEqual(agr["disagree_rate"], round(3 / 10, 4), places=4)
        self.assertAlmostEqual(agr["inconclusive_rate"], round(1 / 10, 4), places=4)

    # ------------------------------------------------------------------
    # 04 — anchor participation rates and averages
    # ------------------------------------------------------------------

    def test_04_summary_anchor_rates(self) -> None:
        """10 shadow rows each with anchors_op=3, anchors_sem=2 → avg 3.0 / 2.0."""
        rows = [
            _fake_summary_row(had_shadow=True, anchors_op=3, anchors_sem=2)
            for _ in range(10)
        ]
        summary = main._compute_match_shadow_summary(rows, "none")

        ap = summary["anchor_participation"]
        self.assertEqual(ap["sample_size"], 10)
        self.assertEqual(ap["groups_with_anchors_near_op"], 10)   # all > 0
        self.assertEqual(ap["groups_with_anchors_near_sem"], 10)  # all > 0
        self.assertIsNotNone(ap["avg_anchors_near_op"])
        self.assertAlmostEqual(ap["avg_anchors_near_op"], 3.0, places=2)
        self.assertAlmostEqual(ap["avg_anchors_near_sem"], 2.0, places=2)
        self.assertAlmostEqual(ap["rate_anchors_near_op"], 1.0, places=4)
        self.assertAlmostEqual(ap["rate_anchors_near_sem"], 1.0, places=4)

    # ------------------------------------------------------------------
    # 05 — top_disagreement_passes sort order
    # ------------------------------------------------------------------

    def test_05_summary_top_disagreement_passes_sorted(self) -> None:
        """Passes sorted: disagree_count desc, then group_count desc, then pass_id asc.

        P1: 5 disagrees / 10 total
        P2: 3 disagrees / 20 total
        P3: 5 disagrees /  5 total
        Expected order: P1, P3, P2 (P1 and P3 tie on disagree→group_count breaks tie).
        """
        rows = (
            # P1 — 5 disagrees in 10 groups
            [_fake_summary_row(had_shadow=True, agreement=False, pass_id="P1")] * 5
            + [_fake_summary_row(had_shadow=True, agreement=True, pass_id="P1")] * 5
            # P2 — 3 disagrees in 20 groups
            + [_fake_summary_row(had_shadow=True, agreement=False, pass_id="P2")] * 3
            + [_fake_summary_row(had_shadow=True, agreement=True, pass_id="P2")] * 17
            # P3 — 5 disagrees in 5 groups
            + [_fake_summary_row(had_shadow=True, agreement=False, pass_id="P3")] * 5
        )
        summary = main._compute_match_shadow_summary(rows, "none")

        passes = summary["top_disagreement_passes"]
        self.assertGreaterEqual(len(passes), 3)
        ids = [p["match_pass_id"] for p in passes]
        self.assertEqual(ids[0], "P1", f"P1 must lead (5 dis / 10 grp); got {ids}")
        self.assertEqual(ids[1], "P3", f"P3 must be second (5 dis / 5 grp); got {ids}")
        self.assertEqual(ids[2], "P2", f"P2 must be third (3 dis / 20 grp); got {ids}")

    # ------------------------------------------------------------------
    # 06 — by_input_sha256 auto-appears with ≥ 2 SHAs
    # ------------------------------------------------------------------

    def test_06_summary_by_sha_auto_appears_with_two_shas(self) -> None:
        """by_input_sha256 must be populated when 2 distinct SHAs are in window,
        even with group_by='none'."""
        rows = (
            [_fake_summary_row(sha="a" * 64, had_shadow=True, agreement=True)] * 12
            + [_fake_summary_row(sha="b" * 64, had_shadow=True, agreement=False)] * 10
        )
        summary = main._compute_match_shadow_summary(rows, "none")

        by_sha = summary["by_input_sha256"]
        self.assertGreater(len(by_sha), 0, "by_input_sha256 must be populated with 2 SHAs")
        sha_vals = {e["input_sha256"] for e in by_sha}
        self.assertIn("a" * 64, sha_vals)
        self.assertIn("b" * 64, sha_vals)

    # ------------------------------------------------------------------
    # 07 — by_input_sha256 capped at 50
    # ------------------------------------------------------------------

    def test_07_summary_by_sha_respects_cap(self) -> None:
        """51 distinct SHAs → by_input_sha256 length capped at 50."""
        rows = [
            _fake_summary_row(sha=str(i).zfill(64), had_shadow=True)
            for i in range(51)
        ]
        summary = main._compute_match_shadow_summary(rows, "input_sha256")

        by_sha = summary["by_input_sha256"]
        self.assertLessEqual(
            len(by_sha),
            50,
            f"by_input_sha256 must be capped at 50; got {len(by_sha)}",
        )

    # ------------------------------------------------------------------
    # 08 — small sample size → rates null, counts present
    # ------------------------------------------------------------------

    def test_08_summary_small_sample_rates_null(self) -> None:
        """5 rows (< MIN_RATE=10) → all rate/avg fields must be None; counts still present."""
        rows = [_fake_summary_row(had_shadow=True, agreement=True)] * 5
        summary = main._compute_match_shadow_summary(rows, "none")

        avail = summary["shadow_availability"]
        self.assertIsNone(
            avail["shadow_availability_rate"],
            "shadow_availability_rate must be None for 5 rows",
        )
        self.assertEqual(avail["rows_with_shadow_payload"], 5)  # count still present

        agr = summary["agreement"]
        self.assertIsNone(agr["agree_rate"])
        self.assertEqual(agr["agree_count"], 5)  # count still present

        ap = summary["anchor_participation"]
        self.assertIsNone(ap["avg_anchors_near_op"])
        self.assertIsNone(ap["rate_anchors_near_op"])
        self.assertEqual(ap["groups_with_anchors_near_op"], 5)  # count still present

    # ------------------------------------------------------------------
    # 09 — malformed rows → helper returns valid skeleton, never raises
    # ------------------------------------------------------------------

    def test_09_summary_helper_never_raises(self) -> None:
        """Malformed / non-dict rows must be skipped; helper must not raise."""
        malformed: List[Any] = [
            None,
            "not a dict",
            42,
            {"had_shadow_payload": "bad_type"},
            {},
        ]
        try:
            summary = main._compute_match_shadow_summary(malformed, "none")  # type: ignore[arg-type]
        except Exception as exc:
            self.fail(
                f"_compute_match_shadow_summary raised {type(exc).__name__}: {exc}"
            )

        # Must return a valid skeleton regardless.
        self.assertIn("schema_version", summary)
        self.assertEqual(summary["schema_version"], "match-shadow-summary-1")
        self.assertIsInstance(summary["top_disagreement_passes"], list)

    # ------------------------------------------------------------------
    # 10 — endpoint returns exactly 10 top-level keys
    # ------------------------------------------------------------------

    def test_10_summary_endpoint_returns_10_top_level_keys(self) -> None:
        """get_match_shadow_summary (empty file) must return exactly 10 top-level keys."""
        data = _call_summary_endpoint()
        actual = frozenset(data.keys())

        extra = actual - EXPECTED_SUMMARY_TOP_KEYS
        missing = EXPECTED_SUMMARY_TOP_KEYS - actual
        self.assertEqual(
            extra,
            frozenset(),
            f"Unexpected top-level keys: {extra}",
        )
        self.assertEqual(
            missing,
            frozenset(),
            f"Missing top-level keys: {missing}",
        )

    # ------------------------------------------------------------------
    # 11 — endpoint coerces invalid group_by silently
    # ------------------------------------------------------------------

    def test_11_summary_endpoint_coerces_invalid_group_by(self) -> None:
        """Any unknown group_by value must be coerced to 'none' without raising."""
        rows = [_fake_summary_row(sha="a" * 64)] * 3
        self._write_rows(rows)

        try:
            data = _call_summary_endpoint(group_by="bogus_value_xyz")
        except Exception as exc:
            self.fail(f"Endpoint raised on invalid group_by: {exc}")

        # Must still return a valid summary.
        self.assertIn("window", data)
        # by_input_sha256 should be empty (only 1 SHA, group_by coerced to "none")
        self.assertEqual(data["by_input_sha256"], [])

    # ------------------------------------------------------------------
    # 12 — endpoint safe when file is missing
    # ------------------------------------------------------------------

    def test_12_summary_endpoint_missing_file_safe(self) -> None:
        """Endpoint must return valid empty summary when the compare file does not exist."""
        # Ensure file does not exist.
        if main.MATCH_SHADOW_COMPARE_PATH.exists():
            main.MATCH_SHADOW_COMPARE_PATH.unlink()

        try:
            data = _call_summary_endpoint()
        except Exception as exc:
            self.fail(f"Endpoint raised when file missing: {exc}")

        self.assertEqual(data["window"]["rows_read"], 0)
        self.assertIsNone(data["shadow_availability"]["shadow_availability_rate"])
        self.assertEqual(data["top_disagreement_passes"], [])
        self.assertIn("stability_note", data)

    # ------------------------------------------------------------------
    # 13 — stability_note exact string match
    # ------------------------------------------------------------------

    def test_13_summary_stability_note_exact(self) -> None:
        """stability_note must match the verbatim lock-down string.

        If the note text is intentionally changed, update EXPECTED_STABILITY_NOTE
        above with a comment explaining why.
        """
        summary = main._compute_match_shadow_summary([], "none")
        self.assertEqual(
            summary["stability_note"],
            EXPECTED_STABILITY_NOTE,
            "stability_note text has changed — update EXPECTED_STABILITY_NOTE if intentional",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
