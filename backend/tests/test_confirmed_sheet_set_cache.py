"""PI.4B.0 — session-scoped confirmed-sheet catalog cache primitive tests.

Tests for:
  - _resolved_plan_paths_hash
  - _compute_confirmed_sheet_set_uncached
  - _build_confirmed_sheet_set_for_session
  - _invalidate_confirmed_sheet_set_cache

All inputs mocked. No PDF dependencies; no fixture gating. The cache
primitive is inert (no runtime consumer wired by PI.4B.0); these tests
exercise the cache lifecycle directly.

Architectural invariants verified:
  I-1  sheet_labels exposure is evidence exposure only — _compute uses
       the four established surface extractors only, no new derivation.
  I-2  Helpers consume only surfaced deterministic evidence — _compute
       receives extractor outputs as plain dicts/lists; the cache stores
       the resulting Set[int] as a sorted list[int] for STATE survival.
"""

from __future__ import annotations

import os

# Set required env vars before importing backend.main (mirrors the prelude
# in test_p53_diagnostic_emission.py, test_p54_shadow_*, etc.).
os.environ.setdefault("TRUELINE_JWT_SECRET", "pi4b0-test-secret")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "pi4b0-test-auth-secret")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

import unittest
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import patch

from backend import main as M


# ---------------------------------------------------------------------------
# STATE swap helper — snapshot+restore around each test so the global STATE
# never carries test state across the regression run.
# ---------------------------------------------------------------------------


class _StateScope:
    """Context manager: snapshot STATE on enter, restore on exit.

    Avoids touching the real session lifecycle (_session_scope) which
    would require a tenant + session_id round-trip. PI.4B.0 helpers
    operate on STATE directly, so a direct STATE swap is the appropriate
    test fixture.
    """

    def __init__(self, initial: Dict[str, Any] | None = None) -> None:
        self.initial = initial or {}
        self._saved: Dict[str, Any] = {}

    def __enter__(self) -> Dict[str, Any]:
        self._saved = dict(M.STATE)
        M.STATE.clear()
        M.STATE.update(self.initial)
        return M.STATE

    def __exit__(self, *args) -> None:
        M.STATE.clear()
        M.STATE.update(self._saved)


# ---------------------------------------------------------------------------
# _resolved_plan_paths_hash
# ---------------------------------------------------------------------------


class TestResolvedPlanPathsHash(unittest.TestCase):
    def test_none_session_returns_empty_string(self) -> None:
        self.assertEqual(M._resolved_plan_paths_hash(None), "")

    def test_empty_session_returns_empty_string(self) -> None:
        self.assertEqual(M._resolved_plan_paths_hash(""), "")
        self.assertEqual(M._resolved_plan_paths_hash("   "), "")

    def test_no_paths_returns_empty_string(self) -> None:
        with patch.object(M, "_resolve_engineering_plan_pdf_paths", return_value=[]):
            self.assertEqual(M._resolved_plan_paths_hash("s1"), "")

    def test_resolver_raises_returns_empty_string(self) -> None:
        with patch.object(
            M, "_resolve_engineering_plan_pdf_paths",
            side_effect=RuntimeError("boom"),
        ):
            self.assertEqual(M._resolved_plan_paths_hash("s1"), "")

    def test_stable_across_calls_for_same_paths(self) -> None:
        paths = [Path("/x/a.pdf"), Path("/x/b.pdf")]
        with patch.object(M, "_resolve_engineering_plan_pdf_paths", return_value=paths):
            h1 = M._resolved_plan_paths_hash("s1")
            h2 = M._resolved_plan_paths_hash("s1")
        self.assertEqual(h1, h2)
        self.assertNotEqual(h1, "")

    def test_order_independent(self) -> None:
        with patch.object(
            M, "_resolve_engineering_plan_pdf_paths",
            return_value=[Path("/x/a.pdf"), Path("/x/b.pdf")],
        ):
            h_ab = M._resolved_plan_paths_hash("s1")
        with patch.object(
            M, "_resolve_engineering_plan_pdf_paths",
            return_value=[Path("/x/b.pdf"), Path("/x/a.pdf")],
        ):
            h_ba = M._resolved_plan_paths_hash("s1")
        self.assertEqual(h_ab, h_ba)

    def test_changes_when_path_set_grows(self) -> None:
        with patch.object(
            M, "_resolve_engineering_plan_pdf_paths",
            return_value=[Path("/x/a.pdf")],
        ):
            h1 = M._resolved_plan_paths_hash("s1")
        with patch.object(
            M, "_resolve_engineering_plan_pdf_paths",
            return_value=[Path("/x/a.pdf"), Path("/x/b.pdf")],
        ):
            h2 = M._resolved_plan_paths_hash("s1")
        self.assertNotEqual(h1, h2)

    def test_changes_when_path_renamed(self) -> None:
        with patch.object(
            M, "_resolve_engineering_plan_pdf_paths",
            return_value=[Path("/x/a.pdf")],
        ):
            h1 = M._resolved_plan_paths_hash("s1")
        with patch.object(
            M, "_resolve_engineering_plan_pdf_paths",
            return_value=[Path("/x/a_renamed.pdf")],
        ):
            h2 = M._resolved_plan_paths_hash("s1")
        self.assertNotEqual(h1, h2)


# ---------------------------------------------------------------------------
# _compute_confirmed_sheet_set_uncached
# ---------------------------------------------------------------------------


class TestComputeConfirmedSheetSetUncached(unittest.TestCase):
    def test_no_paths_returns_empty_set(self) -> None:
        with patch.object(M, "_resolve_engineering_plan_pdf_paths", return_value=[]):
            self.assertEqual(M._compute_confirmed_sheet_set_uncached("s1"), set())

    def test_resolver_raises_returns_empty_set(self) -> None:
        with patch.object(
            M, "_resolve_engineering_plan_pdf_paths",
            side_effect=RuntimeError("boom"),
        ):
            self.assertEqual(M._compute_confirmed_sheet_set_uncached("s1"), set())

    def test_single_pdf_with_sheet_labels_only(self) -> None:
        with patch.object(
            M, "_resolve_engineering_plan_pdf_paths",
            return_value=[Path("/x/a.pdf")],
        ), patch.object(
            M._engineering_plan_parser, "extract_drawing_index", return_value=[],
        ), patch.object(
            M._engineering_plan_parser, "extract_sheet_labels",
            return_value=[{"page": 1, "sheet_label": 7}],
        ), patch.object(
            M._engineering_plan_parser, "extract_title_block", return_value={},
        ), patch.object(
            M._engineering_plan_parser, "extract_matchlines", return_value=[],
        ):
            result = M._compute_confirmed_sheet_set_uncached("s1")
        self.assertEqual(result, {7})

    def test_single_pdf_with_all_four_channels(self) -> None:
        with patch.object(
            M, "_resolve_engineering_plan_pdf_paths",
            return_value=[Path("/x/a.pdf")],
        ), patch.object(
            M._engineering_plan_parser, "extract_drawing_index",
            return_value=[{"page": 1, "file_name": "T_3.DWG"}],
        ), patch.object(
            M._engineering_plan_parser, "extract_sheet_labels",
            return_value=[{"page": 2, "sheet_label": 4}],
        ), patch.object(
            M._engineering_plan_parser, "extract_title_block",
            return_value={"sheet_number_first_seen": 1},
        ), patch.object(
            M._engineering_plan_parser, "extract_matchlines",
            return_value=[{"page": 3, "references_sheet": 5}],
        ):
            result = M._compute_confirmed_sheet_set_uncached("s1")
        # All four channels contribute; PI.3 _apply_drawing_sheet_number
        # surfaces sheet_number=3 from the filename.
        self.assertEqual(result, {1, 3, 4, 5})

    def test_three_pdfs_union(self) -> None:
        paths = [Path("/x/a.pdf"), Path("/x/b.pdf"), Path("/x/c.pdf")]
        # Use side_effect to return different evidence per PDF.
        sl_seq = iter([
            [{"sheet_label": 1}, {"sheet_label": 2}],
            [{"sheet_label": 3}],
            [{"sheet_label": 4}],
        ])
        with patch.object(
            M, "_resolve_engineering_plan_pdf_paths", return_value=paths,
        ), patch.object(
            M._engineering_plan_parser, "extract_drawing_index", return_value=[],
        ), patch.object(
            M._engineering_plan_parser, "extract_sheet_labels",
            side_effect=lambda p: next(sl_seq),
        ), patch.object(
            M._engineering_plan_parser, "extract_title_block", return_value={},
        ), patch.object(
            M._engineering_plan_parser, "extract_matchlines", return_value=[],
        ):
            result = M._compute_confirmed_sheet_set_uncached("s1")
        self.assertEqual(result, {1, 2, 3, 4})

    def test_one_pdf_raises_others_contribute(self) -> None:
        paths = [Path("/x/bad.pdf"), Path("/x/ok.pdf")]
        # Raise on the first PDF; succeed on the second.
        dl_calls = {"count": 0}

        def _drawing_side(_p):
            dl_calls["count"] += 1
            if dl_calls["count"] == 1:
                raise RuntimeError("boom")
            return []

        with patch.object(
            M, "_resolve_engineering_plan_pdf_paths", return_value=paths,
        ), patch.object(
            M._engineering_plan_parser, "extract_drawing_index",
            side_effect=_drawing_side,
        ), patch.object(
            M._engineering_plan_parser, "extract_sheet_labels",
            return_value=[{"sheet_label": 9}],
        ), patch.object(
            M._engineering_plan_parser, "extract_title_block", return_value={},
        ), patch.object(
            M._engineering_plan_parser, "extract_matchlines", return_value=[],
        ):
            result = M._compute_confirmed_sheet_set_uncached("s1")
        # First PDF skipped; second contributes {9}.
        self.assertEqual(result, {9})


# ---------------------------------------------------------------------------
# _build_confirmed_sheet_set_for_session — cache behavior
# ---------------------------------------------------------------------------


class TestBuildConfirmedSheetSetForSession(unittest.TestCase):
    def test_none_session_returns_empty_without_touching_state(self) -> None:
        with _StateScope() as state:
            result = M._build_confirmed_sheet_set_for_session(None)
            self.assertEqual(result, set())
            self.assertNotIn(M._PI4B_CACHE_STATE_KEY, state)

    def test_empty_session_returns_empty_without_touching_state(self) -> None:
        with _StateScope() as state:
            self.assertEqual(
                M._build_confirmed_sheet_set_for_session(""), set(),
            )
            self.assertNotIn(M._PI4B_CACHE_STATE_KEY, state)

    def test_first_call_builds_and_caches(self) -> None:
        with _StateScope() as state, patch.object(
            M, "_resolved_plan_paths_hash", return_value="HASH_A",
        ), patch.object(
            M, "_compute_confirmed_sheet_set_uncached", return_value={5, 6, 7},
        ) as mock_compute:
            result = M._build_confirmed_sheet_set_for_session("s1")
            self.assertEqual(result, {5, 6, 7})
            self.assertEqual(mock_compute.call_count, 1)
            # Cache populated with sorted list (JSON-friendly).
            self.assertEqual(state.get(M._PI4B_CACHE_STATE_KEY), [5, 6, 7])
            self.assertEqual(state.get(M._PI4B_CACHE_HASH_STATE_KEY), "HASH_A")

    def test_second_call_hits_cache_no_recompute(self) -> None:
        with _StateScope(), patch.object(
            M, "_resolved_plan_paths_hash", return_value="HASH_A",
        ), patch.object(
            M, "_compute_confirmed_sheet_set_uncached", return_value={5, 6, 7},
        ) as mock_compute:
            first = M._build_confirmed_sheet_set_for_session("s1")
            second = M._build_confirmed_sheet_set_for_session("s1")
        self.assertEqual(first, second)
        self.assertEqual(mock_compute.call_count, 1)

    def test_path_change_invalidates_cache(self) -> None:
        with _StateScope(), patch.object(
            M, "_compute_confirmed_sheet_set_uncached",
        ) as mock_compute:
            mock_compute.side_effect = [{5, 6}, {1, 2, 3}]
            with patch.object(M, "_resolved_plan_paths_hash", return_value="HASH_A"):
                first = M._build_confirmed_sheet_set_for_session("s1")
            with patch.object(M, "_resolved_plan_paths_hash", return_value="HASH_B"):
                second = M._build_confirmed_sheet_set_for_session("s1")
        self.assertEqual(first, {5, 6})
        self.assertEqual(second, {1, 2, 3})
        self.assertEqual(mock_compute.call_count, 2)

    def test_returns_fresh_set_each_call(self) -> None:
        with _StateScope(), patch.object(
            M, "_resolved_plan_paths_hash", return_value="HASH_A",
        ), patch.object(
            M, "_compute_confirmed_sheet_set_uncached", return_value={5, 6, 7},
        ):
            first = M._build_confirmed_sheet_set_for_session("s1")
            second = M._build_confirmed_sheet_set_for_session("s1")
        # Mutating the returned set must not pollute the cache.
        first.add(999)
        self.assertNotIn(999, second)

    def test_empty_hash_treated_as_cache_miss(self) -> None:
        # When _resolved_plan_paths_hash returns "" (no paths), the cache
        # validity check must NOT spuriously hit on stored hash=="".
        with _StateScope(), patch.object(
            M, "_resolved_plan_paths_hash", return_value="",
        ), patch.object(
            M, "_compute_confirmed_sheet_set_uncached", return_value=set(),
        ) as mock_compute:
            first = M._build_confirmed_sheet_set_for_session("s1")
            second = M._build_confirmed_sheet_set_for_session("s1")
            # Both calls compute (no caching on empty hash).
            self.assertEqual(first, set())
            self.assertEqual(second, set())
            self.assertEqual(mock_compute.call_count, 2)

    def test_cache_survives_within_state(self) -> None:
        # Simulate STATE save/restore round-trip via dict() copy
        # (mirrors _session_scope.__exit__ at m:621).
        with _StateScope() as state, patch.object(
            M, "_resolved_plan_paths_hash", return_value="HASH_A",
        ), patch.object(
            M, "_compute_confirmed_sheet_set_uncached", return_value={3, 4, 5},
        ):
            M._build_confirmed_sheet_set_for_session("s1")
            snapshot = dict(state)
        # New STATE seeded from the snapshot — second call must NOT recompute.
        with _StateScope(initial=snapshot), patch.object(
            M, "_resolved_plan_paths_hash", return_value="HASH_A",
        ), patch.object(
            M, "_compute_confirmed_sheet_set_uncached",
        ) as mock_compute:
            second = M._build_confirmed_sheet_set_for_session("s1")
            self.assertEqual(second, {3, 4, 5})
            self.assertEqual(mock_compute.call_count, 0)

    def test_cache_isolated_across_state_swaps(self) -> None:
        # Independent STATE snapshots simulate two concurrent sessions
        # (or sequential sessions under _session_scope which calls
        # STATE.clear()). The cache field must not leak between them.
        with _StateScope() as state_a, patch.object(
            M, "_resolved_plan_paths_hash", return_value="HASH_A",
        ), patch.object(
            M, "_compute_confirmed_sheet_set_uncached", return_value={1, 2},
        ):
            M._build_confirmed_sheet_set_for_session("session_a")
            self.assertEqual(state_a.get(M._PI4B_CACHE_STATE_KEY), [1, 2])
        # state_a STATE is restored to the prior snapshot on exit.
        with _StateScope() as state_b:
            self.assertNotIn(M._PI4B_CACHE_STATE_KEY, state_b)

    def test_cache_value_robust_to_corrupt_storage(self) -> None:
        # If something writes a non-list into the cache slot, the helper
        # must treat it as a miss and rebuild rather than crash.
        with _StateScope() as state, patch.object(
            M, "_resolved_plan_paths_hash", return_value="HASH_A",
        ), patch.object(
            M, "_compute_confirmed_sheet_set_uncached", return_value={9},
        ) as mock_compute:
            state[M._PI4B_CACHE_STATE_KEY] = "not a list"
            state[M._PI4B_CACHE_HASH_STATE_KEY] = "HASH_A"
            result = M._build_confirmed_sheet_set_for_session("s1")
            self.assertEqual(result, {9})
            self.assertEqual(mock_compute.call_count, 1)


# ---------------------------------------------------------------------------
# _invalidate_confirmed_sheet_set_cache
# ---------------------------------------------------------------------------


class TestInvalidateConfirmedSheetSetCache(unittest.TestCase):
    def test_clears_cache_fields(self) -> None:
        with _StateScope() as state:
            state[M._PI4B_CACHE_STATE_KEY] = [1, 2, 3]
            state[M._PI4B_CACHE_HASH_STATE_KEY] = "abc"
            M._invalidate_confirmed_sheet_set_cache()
            self.assertNotIn(M._PI4B_CACHE_STATE_KEY, state)
            self.assertNotIn(M._PI4B_CACHE_HASH_STATE_KEY, state)

    def test_idempotent_when_cache_absent(self) -> None:
        with _StateScope() as state:
            M._invalidate_confirmed_sheet_set_cache()
            M._invalidate_confirmed_sheet_set_cache()
            self.assertNotIn(M._PI4B_CACHE_STATE_KEY, state)

    def test_session_id_parameter_accepted_but_informational(self) -> None:
        with _StateScope() as state:
            state[M._PI4B_CACHE_STATE_KEY] = [1, 2]
            state[M._PI4B_CACHE_HASH_STATE_KEY] = "abc"
            # Passing a session_id has the same effect as omitting it —
            # STATE itself is session-scoped at the caller layer.
            M._invalidate_confirmed_sheet_set_cache("some-session-id")
            self.assertNotIn(M._PI4B_CACHE_STATE_KEY, state)


if __name__ == "__main__":
    unittest.main()
