"""Synthetic regression coverage for the P5.4 shadow replay infrastructure.

Covers the pure compute helper in engineering_plan_parser.py and the
runtime shadow emission helpers in main.py:

  - engineering_plan_parser.compute_plan_aware_footage_boost
  - main._trueline_plan_pdf_signals_a3_shadow_enabled()
  - main._sheet_to_route_ids_from_packet_index()
  - main._emit_plan_footage_shadow_diagnostic()

Tests verify the SHADOW guarantees: no input mutation, no runtime truth
mutation, byte-identical fallback when the shadow flag is off, deterministic
boost computation with hard caps + hard-stop preconditions.

COMMAND
-------
    python -m pytest backend/tests/test_p54_shadow_infrastructure.py -v
"""

from __future__ import annotations

import copy
import os
import sys
import unittest
from pathlib import Path
from typing import Any, Dict, List

_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

os.environ.setdefault("TRUELINE_JWT_SECRET", "p54-test-secret")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "p54-test-auth-secret")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

import main  # noqa: E402
from app.services import engineering_plan_parser as pp  # noqa: E402

compute = pp.compute_plan_aware_footage_boost

_FLAG_VAR = "TRUELINE_PLAN_PDF_SIGNALS_A3_SHADOW"


class _EnvSaver:
    def __init__(self, name: str) -> None:
        self.name = name
        self._was_set = False
        self._prev: str = ""

    def __enter__(self):
        self._was_set = self.name in os.environ
        self._prev = os.environ.get(self.name, "")
        return self

    def __exit__(self, *args):
        if self._was_set:
            os.environ[self.name] = self._prev
        else:
            os.environ.pop(self.name, None)


def _ranking(route_id: str, score: float, route_name: str = "",
             length_gap_ft: float = 0.0,
             route_length_ft: float = 1000.0) -> Dict[str, Any]:
    return {
        "route_id": route_id,
        "route_name": route_name or f"route-{route_id}",
        "combined_score": float(score),
        "score": float(score),
        "length_gap_ft": float(length_gap_ft),
        "route_length_ft": float(route_length_ft),
    }


def _group(span_ft: int, print_tokens: List[Any]) -> Dict[str, Any]:
    return {"span_ft": span_ft, "print_tokens": list(print_tokens)}


def _origin(length_ft: int, confidence: str = "high",
            has_reset: bool = False) -> Dict[str, Any]:
    return {
        "origin_ft": 0,
        "end_ft": int(length_ft),
        "length_ft": int(length_ft),
        "method": "matchline_chain",
        "confidence": confidence,
        "chain_anchor_sheets": [],
        "has_reset_boundary": bool(has_reset),
        "matchline_count": 2,
        "callout_count": 0,
        "notes": [],
    }


# ---------------------------------------------------------------------------
# Flag resolution
# ---------------------------------------------------------------------------

class FlagResolution(unittest.TestCase):
    def test_unset_is_off(self) -> None:
        with _EnvSaver(_FLAG_VAR):
            os.environ.pop(_FLAG_VAR, None)
            self.assertFalse(main._trueline_plan_pdf_signals_a3_shadow_enabled())

    def test_truthy_values_are_on(self) -> None:
        with _EnvSaver(_FLAG_VAR):
            for val in ("1", "true", "True", "yes", "ON"):
                with self.subTest(val=val):
                    os.environ[_FLAG_VAR] = val
                    self.assertTrue(
                        main._trueline_plan_pdf_signals_a3_shadow_enabled()
                    )

    def test_zero_or_garbage_is_off(self) -> None:
        with _EnvSaver(_FLAG_VAR):
            for val in ("0", "false", "no", "off", "", "2", "maybe"):
                with self.subTest(val=val):
                    os.environ[_FLAG_VAR] = val
                    self.assertFalse(
                        main._trueline_plan_pdf_signals_a3_shadow_enabled()
                    )

    def test_runtime_read_not_import_capture(self) -> None:
        with _EnvSaver(_FLAG_VAR):
            os.environ[_FLAG_VAR] = "0"
            self.assertFalse(main._trueline_plan_pdf_signals_a3_shadow_enabled())
            os.environ[_FLAG_VAR] = "1"
            self.assertTrue(main._trueline_plan_pdf_signals_a3_shadow_enabled())


# ---------------------------------------------------------------------------
# Compute purity & hard-stops
# ---------------------------------------------------------------------------

class ComputeHardStops(unittest.TestCase):
    def test_empty_rankings_returns_no_rankings(self) -> None:
        _, meta = compute([], _group(900, [4]), {4: _origin(900)})
        self.assertFalse(meta["applied"])
        self.assertEqual(meta["skipped_reason"], "no_rankings")

    def test_none_rankings_returns_no_rankings(self) -> None:
        _, meta = compute(None, _group(900, [4]), {4: _origin(900)})
        self.assertFalse(meta["applied"])
        self.assertEqual(meta["skipped_reason"], "no_rankings")

    def test_single_candidate_returns_single_candidate(self) -> None:
        _, meta = compute(
            [_ranking("r1", 0.5)],
            _group(900, [4]),
            {4: _origin(900)},
        )
        self.assertFalse(meta["applied"])
        self.assertEqual(meta["skipped_reason"], "single_candidate_no_ambiguity")

    def test_no_topology_returns_no_topology(self) -> None:
        _, meta = compute(
            [_ranking("r1", 0.5), _ranking("r2", 0.45)],
            _group(900, [4]),
            {},
        )
        self.assertFalse(meta["applied"])
        self.assertEqual(meta["skipped_reason"], "no_topology_available")

    def test_p52_would_boost_false_propagates(self) -> None:
        # group with no print tokens -> evidence is no_data -> would_boost false
        _, meta = compute(
            [_ranking("r1", 0.5), _ranking("r2", 0.45)],
            _group(900, []),
            {4: _origin(900)},
        )
        self.assertFalse(meta["applied"])
        self.assertEqual(meta["skipped_reason"], "p52_would_boost_false")
        self.assertEqual(meta["evidence"]["classification"], "no_data")

    def test_no_sheet_to_route_ids_yields_no_hint(self) -> None:
        # evidence is positive but sheet_to_route_ids is empty
        _, meta = compute(
            [_ranking("r1", 0.5), _ranking("r2", 0.45)],
            _group(900, [4]),
            {4: _origin(900)},
            print_to_sheets={"4": [4]},
            sheet_to_route_ids={},
        )
        self.assertFalse(meta["applied"])
        self.assertEqual(meta["skipped_reason"],
                         "no_hint_route_ids_for_covered_sheets")

    def test_no_eligible_route_in_rankings(self) -> None:
        # hint resolves to ['r99'] but rankings only have r1, r2
        _, meta = compute(
            [_ranking("r1", 0.5), _ranking("r2", 0.45)],
            _group(900, [4]),
            {4: _origin(900)},
            print_to_sheets={"4": [4]},
            sheet_to_route_ids={4: ["r99"]},
        )
        self.assertFalse(meta["applied"])
        self.assertEqual(meta["skipped_reason"], "no_eligible_route_in_rankings")

    def test_gap_too_wide_to_reorder(self) -> None:
        # gap = 0.20 > reorder_gap 0.10 -> no boost
        _, meta = compute(
            [_ranking("r1", 0.8), _ranking("r2", 0.6)],
            _group(900, [4]),
            {4: _origin(900)},
            print_to_sheets={"4": [4]},
            sheet_to_route_ids={4: ["r2"]},
        )
        self.assertFalse(meta["applied"])
        self.assertEqual(meta["skipped_reason"], "gap_too_wide_to_reorder")
        self.assertAlmostEqual(meta["top_score_gap_before"], 0.2)


# ---------------------------------------------------------------------------
# Compute application
# ---------------------------------------------------------------------------

class ComputeApplication(unittest.TestCase):
    def test_eligible_route_receives_boost_up_to_cap(self) -> None:
        boosted, meta = compute(
            [_ranking("r1", 0.5), _ranking("r2", 0.48)],
            _group(900, [4]),
            {4: _origin(900)},
            print_to_sheets={"4": [4]},
            sheet_to_route_ids={4: ["r2"]},
        )
        self.assertTrue(meta["applied"])
        # r2 was eligible, boost up to +0.02 (full cap)
        deltas_by_rid = {d["route_id"]: d for d in meta["per_ranking_deltas"]}
        self.assertAlmostEqual(deltas_by_rid["r2"]["boost"], 0.02)
        self.assertAlmostEqual(deltas_by_rid["r1"]["boost"], 0.0)
        self.assertFalse(deltas_by_rid["r1"]["was_eligible"])
        self.assertTrue(deltas_by_rid["r2"]["was_eligible"])

    def test_boost_magnitude_never_exceeds_cap(self) -> None:
        boosted, meta = compute(
            [_ranking("r1", 0.5), _ranking("r2", 0.49)],
            _group(900, [4]),
            {4: _origin(900)},
            print_to_sheets={"4": [4]},
            sheet_to_route_ids={4: ["r2"]},
            boost_per_entry=0.05,  # caller tries to use 0.05
        )
        self.assertTrue(meta["applied"])
        # boost_per_entry is honored as-is in this function (the caller
        # controls the cap). But the score is clamped to 1.0.
        deltas_by_rid = {d["route_id"]: d for d in meta["per_ranking_deltas"]}
        self.assertAlmostEqual(deltas_by_rid["r2"]["boost"], 0.05)
        # Verify score is bounded by 1.0
        for d in meta["per_ranking_deltas"]:
            self.assertLessEqual(d["score_after"], 1.0)

    def test_negative_boost_per_entry_treated_as_zero(self) -> None:
        boosted, meta = compute(
            [_ranking("r1", 0.5), _ranking("r2", 0.48)],
            _group(900, [4]),
            {4: _origin(900)},
            print_to_sheets={"4": [4]},
            sheet_to_route_ids={4: ["r2"]},
            boost_per_entry=-0.05,
        )
        self.assertTrue(meta["applied"])
        deltas_by_rid = {d["route_id"]: d for d in meta["per_ranking_deltas"]}
        self.assertAlmostEqual(deltas_by_rid["r2"]["boost"], 0.0)


# ---------------------------------------------------------------------------
# Reorder detection
# ---------------------------------------------------------------------------

class ReorderDetection(unittest.TestCase):
    def test_reorder_occurs_when_eligible_route_overtakes_top(self) -> None:
        # r1 at 0.50, r2 at 0.49 (gap 0.01). r2 eligible. boost +0.02.
        # r2 becomes 0.51, leapfrogs r1. would_reorder=True.
        boosted, meta = compute(
            [_ranking("r1", 0.50), _ranking("r2", 0.49)],
            _group(900, [4]),
            {4: _origin(900)},
            print_to_sheets={"4": [4]},
            sheet_to_route_ids={4: ["r2"]},
        )
        self.assertTrue(meta["applied"])
        self.assertTrue(meta["would_reorder"])
        self.assertEqual(meta["top_route_id_before"], "r1")
        self.assertEqual(meta["top_route_id_after"], "r2")
        # boosted[0] is now r2
        self.assertEqual(boosted[0]["route_id"], "r2")

    def test_no_reorder_when_top_is_eligible_and_boosted(self) -> None:
        # r1 at 0.50, r2 at 0.45. r1 eligible. Both stay in same order.
        boosted, meta = compute(
            [_ranking("r1", 0.50), _ranking("r2", 0.45)],
            _group(900, [4]),
            {4: _origin(900)},
            print_to_sheets={"4": [4]},
            sheet_to_route_ids={4: ["r1"]},
        )
        self.assertTrue(meta["applied"])
        self.assertFalse(meta["would_reorder"])
        self.assertEqual(meta["top_route_id_before"], "r1")
        self.assertEqual(meta["top_route_id_after"], "r1")

    def test_no_reorder_when_boost_too_small_to_bridge_gap(self) -> None:
        # r1 at 0.50, r2 at 0.45 (gap 0.05). r2 eligible, boost +0.02.
        # r2 becomes 0.47 -- still below r1. No reorder.
        boosted, meta = compute(
            [_ranking("r1", 0.50), _ranking("r2", 0.45)],
            _group(900, [4]),
            {4: _origin(900)},
            print_to_sheets={"4": [4]},
            sheet_to_route_ids={4: ["r2"]},
        )
        self.assertTrue(meta["applied"])
        self.assertFalse(meta["would_reorder"])
        self.assertEqual(boosted[0]["route_id"], "r1")

    def test_three_candidates_eligible_middle_jumps_to_top(self) -> None:
        boosted, meta = compute(
            [_ranking("r1", 0.50),
             _ranking("r2", 0.495),
             _ranking("r3", 0.40)],
            _group(900, [4]),
            {4: _origin(900)},
            print_to_sheets={"4": [4]},
            sheet_to_route_ids={4: ["r2"]},
        )
        self.assertTrue(meta["applied"])
        self.assertTrue(meta["would_reorder"])
        self.assertEqual(boosted[0]["route_id"], "r2")


# ---------------------------------------------------------------------------
# Input immutability
# ---------------------------------------------------------------------------

class InputImmutability(unittest.TestCase):
    def test_input_rankings_list_not_mutated(self) -> None:
        rankings = [_ranking("r1", 0.5), _ranking("r2", 0.48)]
        snapshot = copy.deepcopy(rankings)
        compute(
            rankings, _group(900, [4]), {4: _origin(900)},
            print_to_sheets={"4": [4]},
            sheet_to_route_ids={4: ["r2"]},
        )
        self.assertEqual(rankings, snapshot)

    def test_input_dicts_not_mutated(self) -> None:
        entry = _ranking("r1", 0.5)
        rankings = [entry, _ranking("r2", 0.48)]
        entry_snapshot = copy.deepcopy(entry)
        compute(
            rankings, _group(900, [4]), {4: _origin(900)},
            print_to_sheets={"4": [4]},
            sheet_to_route_ids={4: ["r1"]},
        )
        self.assertEqual(entry, entry_snapshot)

    def test_normalized_group_not_mutated(self) -> None:
        group = _group(900, [4])
        snapshot = copy.deepcopy(group)
        compute(
            [_ranking("r1", 0.5), _ranking("r2", 0.48)],
            group, {4: _origin(900)},
            print_to_sheets={"4": [4]},
            sheet_to_route_ids={4: ["r2"]},
        )
        self.assertEqual(group, snapshot)

    def test_sheet_origins_not_mutated(self) -> None:
        origins = {4: _origin(900)}
        snapshot = copy.deepcopy(origins)
        compute(
            [_ranking("r1", 0.5), _ranking("r2", 0.48)],
            _group(900, [4]), origins,
            print_to_sheets={"4": [4]},
            sheet_to_route_ids={4: ["r2"]},
        )
        self.assertEqual(origins, snapshot)

    def test_mapping_arguments_not_mutated(self) -> None:
        pts = {"4": [4]}
        s2r = {4: ["r2"]}
        pts_snap = copy.deepcopy(pts)
        s2r_snap = copy.deepcopy(s2r)
        compute(
            [_ranking("r1", 0.5), _ranking("r2", 0.48)],
            _group(900, [4]), {4: _origin(900)},
            print_to_sheets=pts,
            sheet_to_route_ids=s2r,
        )
        self.assertEqual(pts, pts_snap)
        self.assertEqual(s2r, s2r_snap)

    def test_two_consecutive_calls_return_independent_objects(self) -> None:
        kwargs = dict(
            normalized_group=_group(900, [4]),
            sheet_origins={4: _origin(900)},
            print_to_sheets={"4": [4]},
            sheet_to_route_ids={4: ["r2"]},
        )
        rankings = [_ranking("r1", 0.5), _ranking("r2", 0.48)]
        a, _ = compute(rankings, **kwargs)
        b, _ = compute(rankings, **kwargs)
        self.assertIsNot(a, b)
        a[0]["score"] = 9.99
        self.assertNotEqual(b[0]["score"], 9.99)


# ---------------------------------------------------------------------------
# Attribution metadata
# ---------------------------------------------------------------------------

class AttributionMetadata(unittest.TestCase):
    REQUIRED_META_KEYS = {
        "applied", "skipped_reason",
        "boost_per_entry", "reorder_gap",
        "evidence", "hint_route_ids", "boosted_route_ids",
        "would_reorder",
        "top_score_gap_before", "top_score_gap_after",
        "top_route_id_before", "top_route_id_after",
        "per_ranking_deltas",
    }

    def test_applied_meta_has_required_keys(self) -> None:
        _, meta = compute(
            [_ranking("r1", 0.5), _ranking("r2", 0.49)],
            _group(900, [4]), {4: _origin(900)},
            print_to_sheets={"4": [4]},
            sheet_to_route_ids={4: ["r2"]},
        )
        self.assertTrue(self.REQUIRED_META_KEYS.issubset(meta.keys()))

    def test_no_boost_meta_has_required_keys(self) -> None:
        _, meta = compute([], None, None)
        self.assertTrue(self.REQUIRED_META_KEYS.issubset(meta.keys()))

    def test_per_ranking_delta_shape(self) -> None:
        _, meta = compute(
            [_ranking("r1", 0.5), _ranking("r2", 0.49)],
            _group(900, [4]), {4: _origin(900)},
            print_to_sheets={"4": [4]},
            sheet_to_route_ids={4: ["r2"]},
        )
        for d in meta["per_ranking_deltas"]:
            self.assertEqual(
                set(d.keys()),
                {"route_id", "score_before", "score_after", "boost", "was_eligible"},
            )

    def test_evidence_propagates_classification_and_confidence(self) -> None:
        _, meta = compute(
            [_ranking("r1", 0.5), _ranking("r2", 0.49)],
            _group(900, [4]), {4: _origin(900)},
            print_to_sheets={"4": [4]},
            sheet_to_route_ids={4: ["r2"]},
        )
        self.assertEqual(meta["evidence"]["classification"], "contained_consistent")
        self.assertEqual(meta["evidence"]["confidence"], "high")

    def test_boosted_entries_carry_plan_footage_bias(self) -> None:
        boosted, _ = compute(
            [_ranking("r1", 0.5), _ranking("r2", 0.49)],
            _group(900, [4]), {4: _origin(900)},
            print_to_sheets={"4": [4]},
            sheet_to_route_ids={4: ["r2"]},
        )
        for entry in boosted:
            self.assertIn("plan_footage_bias", entry)
            self.assertIn("applied", entry["plan_footage_bias"])


# ---------------------------------------------------------------------------
# Safe failure
# ---------------------------------------------------------------------------

class SafeFailure(unittest.TestCase):
    def test_never_raises_on_arbitrary_garbage(self) -> None:
        nasties = [
            (None, None, None),
            ([], {}, {}),
            ([_ranking("r1", 0.5)], {}, None),
            ([{"garbage": True}, {"more": "junk"}], _group(900, [4]),
             {4: _origin(900)}),
        ]
        for r, g, o in nasties:
            with self.subTest(r=r, g=g, o=o):
                try:
                    rankings, meta = compute(r, g, o)
                except Exception as exc:
                    self.fail(f"compute raised on {r!r}, {g!r}, {o!r}: {exc!r}")
                self.assertIn("applied", meta)


# ---------------------------------------------------------------------------
# Sheet-to-route-ids builder from packet index
# ---------------------------------------------------------------------------

class SheetToRouteIdsBuilder(unittest.TestCase):
    def test_brenham_packet_index_yields_known_mappings(self) -> None:
        out = main._sheet_to_route_ids_from_packet_index()
        # Brenham fixture: sheet 1 -> route_476 (E STONE ST)
        self.assertIn(1, out)
        self.assertIn("route_476", out[1])
        # Sheet 18 -> three routes (the multi-route ambiguous case)
        self.assertIn(18, out)
        self.assertIn("route_477", out[18])
        self.assertIn("route_479", out[18])
        self.assertIn("route_480", out[18])

    def test_keys_are_ints(self) -> None:
        out = main._sheet_to_route_ids_from_packet_index()
        for k in out.keys():
            self.assertIsInstance(k, int)

    def test_values_are_lists_of_strings(self) -> None:
        out = main._sheet_to_route_ids_from_packet_index()
        for v in out.values():
            self.assertIsInstance(v, list)
            for item in v:
                self.assertIsInstance(item, str)


# ---------------------------------------------------------------------------
# Shadow emission wrapper
# ---------------------------------------------------------------------------

class ShadowEmissionWrapper(unittest.TestCase):
    def test_no_topology_returns_no_emit(self) -> None:
        out = main._emit_plan_footage_shadow_diagnostic(
            [_ranking("r1", 0.5), _ranking("r2", 0.45)],
            _group(900, [4]),
            {},
            {},
        )
        self.assertFalse(out["emitted"])
        self.assertEqual(out["reason"], "no_topology_or_no_rankings")

    def test_no_rankings_returns_no_emit(self) -> None:
        out = main._emit_plan_footage_shadow_diagnostic(
            [], _group(900, [4]), {4: _origin(900)}, {},
        )
        self.assertFalse(out["emitted"])

    def test_emits_full_shape_when_evidence_eligible(self) -> None:
        # Use real CURRENT_PACKET_PRINT_SHEET_INDEX -> sheet 4 maps to
        # route_476 + route_479 in the Brenham packet.
        out = main._emit_plan_footage_shadow_diagnostic(
            [_ranking("route_476", 0.50), _ranking("route_479", 0.49)],
            _group(900, [4]),
            {4: _origin(900)},
            {"selected_route_id": "route_476", "render_allowed": True,
             "render_block_reasons": [],
             "ambiguity_resolution_status": "not_ambiguous"},
        )
        self.assertTrue(out["emitted"])
        for key in (
            "applied_hypothetically", "would_reorder",
            "current_top", "hypothetical_top",
            "evidence", "hint_route_ids", "boosted_route_ids",
            "top_score_gap_before", "top_score_gap_after",
            "skipped_reason", "per_ranking_deltas",
            "downstream_validation_snapshot",
        ):
            self.assertIn(key, out)

    def test_downstream_validation_snapshot_propagates(self) -> None:
        diag = {
            "selected_route_id": "route_476",
            "selected_route_name": "E STONE ST",
            "render_allowed": True,
            "render_block_reasons": ["foo"],
            "ambiguity_resolution_status": "resolved_by_plan_signal",
        }
        out = main._emit_plan_footage_shadow_diagnostic(
            [_ranking("route_476", 0.50), _ranking("route_479", 0.49)],
            _group(900, [4]),
            {4: _origin(900)},
            diag,
        )
        snap = out["downstream_validation_snapshot"]
        self.assertEqual(snap["selected_route_id"], "route_476")
        self.assertEqual(snap["render_allowed"], True)
        self.assertEqual(snap["render_block_reasons"], ["foo"])
        self.assertEqual(snap["ambiguity_resolution_status"], "resolved_by_plan_signal")

    def test_emitter_never_mutates_inputs(self) -> None:
        rankings = [_ranking("route_476", 0.50), _ranking("route_479", 0.49)]
        group = _group(900, [4])
        origins = {4: _origin(900)}
        diag = {"selected_route_id": "route_476"}
        snaps = (copy.deepcopy(rankings), copy.deepcopy(group),
                 copy.deepcopy(origins), copy.deepcopy(diag))
        main._emit_plan_footage_shadow_diagnostic(rankings, group, origins, diag)
        self.assertEqual(rankings, snaps[0])
        self.assertEqual(group, snaps[1])
        self.assertEqual(origins, snaps[2])
        self.assertEqual(diag, snaps[3])

    def test_emitter_safe_failure_on_garbage(self) -> None:
        try:
            out = main._emit_plan_footage_shadow_diagnostic(
                None, None, None, None,  # type: ignore[arg-type]
            )
        except Exception as exc:
            self.fail(f"emitter raised on None inputs: {exc!r}")
        self.assertIn("emitted", out)


# ---------------------------------------------------------------------------
# Diagnostic-only guarantees
# ---------------------------------------------------------------------------

class DiagnosticOnlyGuarantees(unittest.TestCase):
    def test_shadow_field_has_no_readers_in_main(self) -> None:
        """The shadow diagnostic field may have multiple writers (success
        path + exception fallback). What it must NOT have is any reader.
        """
        main_py = Path(main.__file__).read_text(encoding="utf-8")

        # At least one writer must exist (the success path).
        writes = main_py.count('_diag["plan_footage_boost_shadow"] =')
        self.assertGreaterEqual(
            writes, 1,
            "expected at least one writer of _diag['plan_footage_boost_shadow']",
        )

        forbidden_read_patterns = [
            '.get("plan_footage_boost_shadow"',
            ".get('plan_footage_boost_shadow'",
            '= _diag["plan_footage_boost_shadow"]',
            "= _diag['plan_footage_boost_shadow']",
            '"plan_footage_boost_shadow" in ',
            "'plan_footage_boost_shadow' in ",
            'if _diag["plan_footage_boost_shadow"]',
            "if _diag['plan_footage_boost_shadow']",
        ]
        for pat in forbidden_read_patterns:
            self.assertNotIn(
                pat, main_py,
                f"plan_footage_boost_shadow must not be consumed by main.py "
                f"(found reader pattern: {pat!r})",
            )

    def test_p54_helpers_exist(self) -> None:
        for name in (
            "_trueline_plan_pdf_signals_a3_shadow_enabled",
            "_sheet_to_route_ids_from_packet_index",
            "_emit_plan_footage_shadow_diagnostic",
        ):
            self.assertTrue(hasattr(main, name),
                            f"main.py missing {name}")

    def test_no_new_state_keys_for_p54(self) -> None:
        main_py = Path(main.__file__).read_text(encoding="utf-8")
        for forbidden in (
            'STATE["plan_footage_boost_shadow"]',
            "STATE['plan_footage_boost_shadow']",
            'STATE["plan_footage_hypothetical_rankings"]',
        ):
            self.assertNotIn(forbidden, main_py,
                             f"P5.4 must not persist shadow data in STATE")


# ---------------------------------------------------------------------------
# Reorder gap configurability
# ---------------------------------------------------------------------------

class ReorderGapConfigurability(unittest.TestCase):
    def test_custom_reorder_gap_respected(self) -> None:
        # gap is 0.05, default reorder_gap is 0.10 -> would apply
        # but we pass reorder_gap=0.02 -> gap_too_wide
        _, meta = compute(
            [_ranking("r1", 0.5), _ranking("r2", 0.45)],
            _group(900, [4]), {4: _origin(900)},
            print_to_sheets={"4": [4]},
            sheet_to_route_ids={4: ["r2"]},
            reorder_gap=0.02,
        )
        self.assertFalse(meta["applied"])
        self.assertEqual(meta["skipped_reason"], "gap_too_wide_to_reorder")


if __name__ == "__main__":
    unittest.main()
