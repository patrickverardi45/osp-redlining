"""Phase 1I-C-Tests — match-shadow-disagreements-1 taxonomy lock-down suite.

17 tests for ``_compute_match_shadow_disagreements`` (pure helper) and
``get_match_shadow_disagreements`` (endpoint), added in Phase 1I-A.

ISOLATION STRATEGY
------------------
``_compute_match_shadow_disagreements`` is a pure function — most tests call
it directly with synthetic dicts, no monkeypatching required.

Endpoint tests (test_16, test_17) monkeypatch ``main.MATCH_SHADOW_COMPARE_PATH``
via a ``tempfile.TemporaryDirectory`` in setUp/tearDown so the real
``uploads/match_shadow_compare.jsonl`` is never touched.

IF A TEST FAILS after a legitimate Phase 1I-A change:
  1. Confirm the change is intentional.
  2. Update the relevant constant or assertion below.
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
# Exact entry key set produced by _compute_match_shadow_disagreements.
# Any change here means the entry schema changed — update with a comment.
# ---------------------------------------------------------------------------
EXPECTED_ENTRY_KEYS: frozenset = frozenset(
    {
        "decided_at",
        "match_pass_id",
        "input_sha256",
        "group_id",
        "operational_winner_route_id",
        "operational_winner_route_name",
        "semantic_winner_route_id",
        "semantic_winner_route_name",
        "anchors_near_operational_winner",
        "anchors_near_semantic_winner",
        "contributing_anchor_count",
        "shadow_explanation",
        "disagreement_kind",
        "review_priority",
        "review_priority_reasons",
    }
)

# Endpoint returns 8 top-level keys:
#   schema_version, computed_at, window, filters, taxonomy,
#   entries, guards, stability_note.
EXPECTED_ENDPOINT_TOP_KEYS: frozenset = frozenset(
    {
        "schema_version",
        "computed_at",
        "window",
        "filters",
        "taxonomy",
        "entries",
        "guards",
        "stability_note",
    }
)

# All five approved label strings (sorted as the backend emits them).
APPROVED_LABELS: List[str] = sorted(
    [
        "COMPETING_SUPPORT",
        "DOMINANT_SHADOW_SUPPORT",
        "MODEST_SHADOW_SUPPORT",
        "NO_CONTRIBUTORS_LISTED",
        "THIN_EVIDENCE",
    ]
)

# Exact prefix that must appear in the stability_note.
# Only the prefix is locked so minor wording tweaks don't force a test change,
# but the critical meaning ("EVIDENCE STRENGTH ONLY") is anchored.
STABILITY_NOTE_PREFIX = (
    "match-shadow-disagreements-1 labels describe disagreement EVIDENCE "
    "STRENGTH ONLY."
)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _dis_row(
    *,
    had_shadow_payload: bool = True,
    agreement: Optional[bool] = False,
    op_id: str = "R1",
    sem_id: str = "R2",
    op_name: str = "Route R1",
    sem_name: str = "Route R2",
    anch_op: int = 0,
    anch_sem: int = 4,
    contrib_ids: Optional[List[str]] = None,
    explanation: str = "Shadow prefers R2.",
    match_pass_id: str = "pass-001",
    group_id: str = "G1",
    input_sha256: str = "a" * 64,
    decided_at: str = "2026-05-10T00:00:00+00:00",
) -> Dict[str, Any]:
    """Build a minimal synthetic match-shadow-1 row dict.

    Defaults produce a valid *disagreement* row (agreement=False,
    had_shadow_payload=True, distinct route IDs, 4 semantic anchors, 1
    contributor).  Override individual kwargs to test specific branches.
    """
    return {
        "schema_version": "match-shadow-1",
        "decided_at": decided_at,
        "match_pass_id": match_pass_id,
        "input_sha256": input_sha256,
        "had_shadow_payload": had_shadow_payload,
        "agreement": agreement,
        "group_id": group_id,
        "group_index": 0,
        "operational_winner_route_id": op_id,
        "operational_winner_route_name": op_name,
        "semantic_winner_route_id": sem_id,
        "semantic_winner_route_name": sem_name,
        "anchors_near_operational_winner": anch_op,
        "anchors_near_semantic_winner": anch_sem,
        "contributing_anchor_ids": (
            contrib_ids if contrib_ids is not None else ["anchor_1"]
        ),
        "shadow_explanation": explanation,
        "session_id_hint": "test-session",
        "shadow_version": "shadow-1",
        "operational_confidence": 0.85,
        "semantic_winner_score": 1.5,
    }


def _call(
    rows: List[Dict[str, Any]],
    min_review_priority: str = "low",
) -> Dict[str, Any]:
    """Convenience wrapper: call helper with min_priority 'low' by default
    so tests see all entries unless they want to test filtering."""
    return main._compute_match_shadow_disagreements(rows, min_review_priority)


# ---------------------------------------------------------------------------
# Test suite
# ---------------------------------------------------------------------------


class TestMatchShadowDisagreements(unittest.TestCase):
    """Lock-down suite for Phase 1I-A disagreement taxonomy."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._orig_path = main.MATCH_SHADOW_COMPARE_PATH
        # Point path at temp file so endpoint tests never touch production JSONL.
        main.MATCH_SHADOW_COMPARE_PATH = (
            Path(self._tmpdir.name) / "match_shadow_compare.jsonl"
        )

    def tearDown(self) -> None:
        main.MATCH_SHADOW_COMPARE_PATH = self._orig_path
        self._tmpdir.cleanup()

    # ------------------------------------------------------------------
    # 01 — entry schema exact 15 keys
    # ------------------------------------------------------------------

    def test_01_entry_schema_exact_keys(self) -> None:
        """Every disagreement entry must carry exactly the 15 expected keys.

        Failure means the entry schema changed.  Update EXPECTED_ENTRY_KEYS
        with a comment explaining why.
        """
        row = _dis_row(anch_op=0, anch_sem=4, contrib_ids=["a1"])
        result = _call([row])

        self.assertEqual(len(result["entries"]), 1)
        actual = frozenset(result["entries"][0].keys())
        extra = actual - EXPECTED_ENTRY_KEYS
        missing = EXPECTED_ENTRY_KEYS - actual
        self.assertEqual(extra, frozenset(), f"Unexpected entry keys: {extra}")
        self.assertEqual(missing, frozenset(), f"Missing entry keys: {missing}")

    # ------------------------------------------------------------------
    # 02 — endpoint top-level 8 keys
    # ------------------------------------------------------------------

    def test_02_endpoint_top_level_keys(self) -> None:
        """Endpoint must return exactly 8 top-level keys."""
        response = main.get_match_shadow_disagreements(limit=10)
        data: Dict[str, Any] = json.loads(response.body)
        actual = frozenset(data.keys())
        extra = actual - EXPECTED_ENDPOINT_TOP_KEYS
        missing = EXPECTED_ENDPOINT_TOP_KEYS - actual
        self.assertEqual(extra, frozenset(), f"Unexpected endpoint keys: {extra}")
        self.assertEqual(missing, frozenset(), f"Missing endpoint keys: {missing}")

    # ------------------------------------------------------------------
    # 03 — hard filter excludes non-disagreements
    # ------------------------------------------------------------------

    def test_03_hard_filter_excludes_non_disagreements(self) -> None:
        """Rows with agreement=True, agreement=None, or had_shadow_payload=False
        must all be excluded from entries.

        Only the genuine disagreement row (agreement=False, had_shadow=True)
        should survive.
        """
        rows = [
            _dis_row(agreement=True,  group_id="agree"),
            _dis_row(agreement=None,  group_id="none"),
            _dis_row(had_shadow_payload=False, agreement=False, group_id="no-shadow"),
            _dis_row(agreement=False, group_id="genuine"),  # only this survives
        ]
        result = _call(rows)

        self.assertEqual(len(result["entries"]), 1)
        self.assertEqual(result["entries"][0]["group_id"], "genuine")

    # ------------------------------------------------------------------
    # 04 — hard filter excludes same-route-id rows
    # ------------------------------------------------------------------

    def test_04_hard_filter_excludes_same_route_ids(self) -> None:
        """Defensive: row where op_id == sem_id but agreement=False is excluded."""
        rows = [
            _dis_row(op_id="R1", sem_id="R1", group_id="same-id"),
            _dis_row(op_id="R1", sem_id="R2", group_id="diff-id"),  # survives
        ]
        result = _call(rows)

        self.assertEqual(len(result["entries"]), 1)
        self.assertEqual(result["entries"][0]["group_id"], "diff-id")

    # ------------------------------------------------------------------
    # 05 — DOMINANT_SHADOW_SUPPORT label
    # ------------------------------------------------------------------

    def test_05_label_dominant_shadow_support(self) -> None:
        """anch_op=0, anch_sem=3 → DOMINANT_SHADOW_SUPPORT in labels."""
        row = _dis_row(anch_op=0, anch_sem=3, contrib_ids=["a1"])
        result = _call([row])

        self.assertEqual(len(result["entries"]), 1)
        kinds = result["entries"][0]["disagreement_kind"]
        self.assertIn("DOMINANT_SHADOW_SUPPORT", kinds)
        self.assertNotIn("MODEST_SHADOW_SUPPORT", kinds,
                         "anch_sem=3 must not also trigger MODEST (anch_sem <= 2)")

    # ------------------------------------------------------------------
    # 06 — dominant threshold boundary: anch_sem=2 is MODEST not DOMINANT
    # ------------------------------------------------------------------

    def test_06_dominant_threshold_boundary_at_2_vs_3(self) -> None:
        """Boundary: anch_sem=2 must NOT trigger DOMINANT; anch_sem=3 MUST.

        The threshold constant is _DOMINANT_THRESHOLD = 3 (>= 3 triggers).
        """
        row_below = _dis_row(anch_op=0, anch_sem=2, contrib_ids=["a1"])
        row_at    = _dis_row(anch_op=0, anch_sem=3, contrib_ids=["a1"],
                             group_id="G2", decided_at="2026-05-10T00:00:01+00:00")

        result_below = _call([row_below])
        result_at    = _call([row_at])

        kinds_below = result_below["entries"][0]["disagreement_kind"]
        kinds_at    = result_at["entries"][0]["disagreement_kind"]

        self.assertNotIn("DOMINANT_SHADOW_SUPPORT", kinds_below,
                         "anch_sem=2 is below threshold; must not be DOMINANT")
        self.assertIn("MODEST_SHADOW_SUPPORT", kinds_below,
                      "anch_sem=2 with anch_op=0 must be MODEST")

        self.assertIn("DOMINANT_SHADOW_SUPPORT", kinds_at,
                      "anch_sem=3 meets threshold; must be DOMINANT")
        self.assertNotIn("MODEST_SHADOW_SUPPORT", kinds_at,
                         "anch_sem=3 is above MODEST range (1..2)")

    # ------------------------------------------------------------------
    # 07 — MODEST_SHADOW_SUPPORT label
    # ------------------------------------------------------------------

    def test_07_label_modest_shadow_support(self) -> None:
        """anch_op=0, anch_sem=1 and anch_op=0, anch_sem=2 both trigger MODEST."""
        for anch_sem in (1, 2):
            with self.subTest(anch_sem=anch_sem):
                row = _dis_row(anch_op=0, anch_sem=anch_sem, contrib_ids=["a1"])
                result = _call([row])
                self.assertEqual(len(result["entries"]), 1)
                kinds = result["entries"][0]["disagreement_kind"]
                self.assertIn("MODEST_SHADOW_SUPPORT", kinds)
                self.assertNotIn("DOMINANT_SHADOW_SUPPORT", kinds)

    # ------------------------------------------------------------------
    # 08 — COMPETING_SUPPORT label
    # ------------------------------------------------------------------

    def test_08_label_competing_support(self) -> None:
        """anch_op >= 1 AND anch_sem >= 1 → COMPETING_SUPPORT in labels."""
        row = _dis_row(anch_op=2, anch_sem=3, contrib_ids=["a1"])
        result = _call([row])

        self.assertEqual(len(result["entries"]), 1)
        kinds = result["entries"][0]["disagreement_kind"]
        self.assertIn("COMPETING_SUPPORT", kinds)
        self.assertNotIn("DOMINANT_SHADOW_SUPPORT", kinds,
                         "anch_op > 0 prevents DOMINANT")
        self.assertNotIn("MODEST_SHADOW_SUPPORT", kinds,
                         "anch_op > 0 prevents MODEST")

    # ------------------------------------------------------------------
    # 09 — THIN_EVIDENCE and NO_CONTRIBUTORS_LISTED labels
    # ------------------------------------------------------------------

    def test_09_label_thin_evidence_and_no_contributors(self) -> None:
        """anch_op + anch_sem <= 2 triggers THIN_EVIDENCE.
        contrib_count == 0 with anch_sem > 0 triggers NO_CONTRIBUTORS_LISTED.
        """
        # Thin evidence (total = 1+1 = 2).
        row_thin = _dis_row(anch_op=1, anch_sem=1, contrib_ids=["a1"])
        result = _call([row_thin])
        kinds = result["entries"][0]["disagreement_kind"]
        self.assertIn("THIN_EVIDENCE", kinds,
                      "anch_op+anch_sem=2 must be THIN_EVIDENCE")

        # No contributors listed: anch_sem=4 but contrib_ids=[].
        row_no_contrib = _dis_row(anch_op=0, anch_sem=4, contrib_ids=[])
        result2 = _call([row_no_contrib])
        kinds2 = result2["entries"][0]["disagreement_kind"]
        self.assertIn("NO_CONTRIBUTORS_LISTED", kinds2)

    # ------------------------------------------------------------------
    # 10 — priority elevated
    # ------------------------------------------------------------------

    def test_10_priority_elevated(self) -> None:
        """DOMINANT + NOT THIN + contributors present → priority = elevated.

        Reasons must include dominant_shadow_support, non_thin_evidence,
        contributors_listed.
        """
        row = _dis_row(anch_op=0, anch_sem=4, contrib_ids=["a1", "a2"])
        result = _call([row])

        entry = result["entries"][0]
        self.assertEqual(entry["review_priority"], "elevated")
        self.assertIn("dominant_shadow_support", entry["review_priority_reasons"])
        self.assertIn("non_thin_evidence", entry["review_priority_reasons"])
        self.assertIn("contributors_listed", entry["review_priority_reasons"])

    # ------------------------------------------------------------------
    # 11 — priority standard (competing support, not thin)
    # ------------------------------------------------------------------

    def test_11_priority_standard(self) -> None:
        """COMPETING_SUPPORT and NOT THIN_EVIDENCE → priority = standard.

        anch_op=2, anch_sem=3: total=5 > 2 (not thin); both routes have anchors.
        Reasons must include competing_or_modest_support and non_thin_evidence.
        """
        row = _dis_row(anch_op=2, anch_sem=3, contrib_ids=["a1"])
        result = _call([row])

        entry = result["entries"][0]
        self.assertEqual(entry["review_priority"], "standard")
        self.assertIn("competing_or_modest_support",
                      entry["review_priority_reasons"])
        self.assertIn("non_thin_evidence", entry["review_priority_reasons"])

    # ------------------------------------------------------------------
    # 12 — priority low: thin-evidence-only path
    # ------------------------------------------------------------------

    def test_12_priority_low_thin_only(self) -> None:
        """THIN_EVIDENCE as sole label → priority = low, reason = thin_evidence_only.

        anch_op=0, anch_sem=1: MODEST + THIN (anch_op=0 so MODEST, total=1 so THIN).
        len(labels) == 2 (MODEST + THIN), so NOT thin_evidence_only; default_low.

        For THIN as sole label: anch_op=0, anch_sem=0 → no anchor signals at all.
        No other labels apply. len(labels)==1 → thin_evidence_only reason.
        Wait: anch_sem=0 means NOT MODEST (needs anch_sem in [1,2]), NOT DOMINANT.
        NOT COMPETING (anch_op < 1). anch_op+anch_sem=0 <= 2 → THIN.
        NO_CONTRIBUTORS: contrib_count=0 but anch_sem=0, so NOT triggered.
        Result: only THIN → thin_evidence_only reason.
        """
        row = _dis_row(anch_op=0, anch_sem=0, contrib_ids=[])
        result = _call([row])

        entry = result["entries"][0]
        self.assertEqual(entry["review_priority"], "low")
        self.assertIn("thin_evidence_only", entry["review_priority_reasons"])
        self.assertIn("THIN_EVIDENCE", entry["disagreement_kind"])
        self.assertEqual(len(entry["disagreement_kind"]), 1,
                         "Only THIN_EVIDENCE should appear with anch_op=0, anch_sem=0")

    # ------------------------------------------------------------------
    # 13 — taxonomy totals counted before min_review_priority filter
    # ------------------------------------------------------------------

    def test_13_taxonomy_totals_before_filter(self) -> None:
        """taxonomy.totals_by_priority reflects ALL disagreements in the window.

        Even when min_review_priority='elevated' filters entries to only
        elevated rows, the taxonomy totals must still include standard and
        low counts.

        Setup: 1 elevated row + 1 standard row + 1 low row.
        With filter='elevated': entries has 1 item but totals has 1+1+1.
        """
        row_elevated = _dis_row(
            anch_op=0, anch_sem=5, contrib_ids=["a1"],
            group_id="elev", decided_at="2026-05-10T00:00:00+00:00",
        )
        # standard: competing, not thin (anch_op=2, anch_sem=3, total=5 > 2)
        row_standard = _dis_row(
            anch_op=2, anch_sem=3, contrib_ids=["a1"],
            group_id="std", decided_at="2026-05-10T00:00:01+00:00",
            op_id="R1", sem_id="R3",
        )
        # low: thin-evidence-only (anch_op=0, anch_sem=0)
        row_low = _dis_row(
            anch_op=0, anch_sem=0, contrib_ids=[],
            group_id="low", decided_at="2026-05-10T00:00:02+00:00",
            op_id="R1", sem_id="R4",
        )

        result = _call(
            [row_elevated, row_standard, row_low],
            min_review_priority="elevated",
        )

        # Only elevated rows should appear in entries.
        self.assertEqual(len(result["entries"]), 1)
        self.assertEqual(result["entries"][0]["group_id"], "elev")

        # But taxonomy totals reflect all three rows.
        by_priority = result["taxonomy"]["totals_by_priority"]
        self.assertEqual(by_priority["elevated"], 1,
                         "elevated count must include the elevated row")
        self.assertEqual(by_priority["standard"], 1,
                         "standard count must include the standard row even when filtered")
        self.assertEqual(by_priority["low"], 1,
                         "low count must include the low row even when filtered")

    # ------------------------------------------------------------------
    # 14 — min_review_priority filter: elevated removes standard + low
    # ------------------------------------------------------------------

    def test_14_min_priority_filter_elevated(self) -> None:
        """min_review_priority='elevated' must exclude standard and low entries."""
        rows = [
            _dis_row(anch_op=0, anch_sem=5, contrib_ids=["a1"],
                     group_id="elev", op_id="R1", sem_id="R2"),
            _dis_row(anch_op=2, anch_sem=3, contrib_ids=["a1"],
                     group_id="std", op_id="R1", sem_id="R3"),
        ]

        result_elev = _call(rows, min_review_priority="elevated")
        result_std  = _call(rows, min_review_priority="standard")
        result_low  = _call(rows, min_review_priority="low")

        # elevated filter: only elevated row visible
        self.assertEqual(len(result_elev["entries"]), 1)
        self.assertEqual(result_elev["entries"][0]["group_id"], "elev")

        # standard filter: elevated + standard visible
        self.assertEqual(len(result_std["entries"]), 2)

        # low filter: all visible
        self.assertEqual(len(result_low["entries"]), 2)

    # ------------------------------------------------------------------
    # 15 — invalid priority coerced to standard
    # ------------------------------------------------------------------

    def test_15_invalid_priority_coerced_to_standard(self) -> None:
        """Any unrecognized min_review_priority must be treated as 'standard'.

        The helper normalizes invalid inputs via:
          _mrp = min_review_priority if min_review_priority in _PRIORITY_ORDER else 'standard'
        so the filters dict must reflect 'standard' and behavior must match it.
        """
        row_elevated = _dis_row(anch_op=0, anch_sem=5, contrib_ids=["a1"],
                                group_id="elev", op_id="R1", sem_id="R2")
        row_low = _dis_row(anch_op=0, anch_sem=0, contrib_ids=[],
                           group_id="low", op_id="R1", sem_id="R3")

        for bad_input in ("ELEVATED", "banana", "", "null", "0"):
            with self.subTest(bad_input=bad_input):
                result = _call([row_elevated, row_low],
                               min_review_priority=bad_input)
                self.assertEqual(
                    result["filters"]["min_review_priority"],
                    "standard",
                    f"'{bad_input}' must coerce to 'standard'",
                )
                # standard filter: elevated visible, low NOT visible
                entry_ids = {e["group_id"] for e in result["entries"]}
                self.assertIn("elev", entry_ids)
                self.assertNotIn("low", entry_ids)

    # ------------------------------------------------------------------
    # 16 — helper never raises on malformed / unexpected input
    # ------------------------------------------------------------------

    def test_16_helper_never_raises(self) -> None:
        """Helper must absorb every exception and return a valid skeleton.

        Tests: non-dict rows, None rows, missing required fields, bad types
        for anchor counts.
        """
        bad_rows: List[Any] = [
            None,
            "not a dict",
            42,
            {},                                          # empty dict
            {"had_shadow_payload": True, "agreement": False},  # missing route IDs
            _dis_row(anch_op="bad", anch_sem="also bad"),       # wrong types
        ]

        try:
            result = _call(bad_rows)  # type: ignore[arg-type]
        except Exception as exc:
            self.fail(
                f"_compute_match_shadow_disagreements raised "
                f"{type(exc).__name__}: {exc}"
            )

        # Must return a valid skeleton even if all rows are garbage.
        self.assertIn("entries", result)
        self.assertIn("taxonomy", result)
        self.assertIn("stability_note", result)
        # The stability note must still be present (not an empty string).
        self.assertTrue(result["stability_note"])

    # ------------------------------------------------------------------
    # 17 — endpoint returns empty skeleton when file is missing
    # ------------------------------------------------------------------

    def test_17_endpoint_missing_file_returns_empty_skeleton(self) -> None:
        """When MATCH_SHADOW_COMPARE_PATH does not exist the endpoint must
        return HTTP 200 with an empty skeleton (entries=[]).

        The setUp already points MATCH_SHADOW_COMPARE_PATH at a non-existent
        temp path, so no file creation is needed here.
        """
        self.assertFalse(
            main.MATCH_SHADOW_COMPARE_PATH.exists(),
            "Precondition: temp path must not exist for this test",
        )

        response = main.get_match_shadow_disagreements(limit=10)
        data: Dict[str, Any] = json.loads(response.body)

        self.assertEqual(data.get("entries"), [],
                         "Missing file must yield entries=[]")
        self.assertEqual(data.get("window", {}).get("rows_read"), 0,
                         "Missing file must yield window.rows_read=0")
        self.assertIn("stability_note", data)
        self.assertTrue(data["stability_note"])
        # Skeleton must still have approved_labels populated.
        approved = data.get("taxonomy", {}).get("approved_labels")
        self.assertEqual(approved, APPROVED_LABELS,
                         "approved_labels must be present even in empty skeleton")


if __name__ == "__main__":
    unittest.main(verbosity=2)
