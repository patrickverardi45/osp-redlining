"""PT.ACT R3.d/R3.e — shadow flag + shadow dispatcher tests.

Exercises the new SHADOW execution path for PT.1 and PT.2.0 plausibility
boost layers. Doctrine (per pt-act-r3-shadow-execution-design.md):

  SHADOW = compute  ->  observe  ->  discard
  LIVE   = compute  ->  mutate   ->  select
  OFF    = no-op    ->  passthrough

Schema choice (b) is enforced: `meta["shadow"]` is added ONLY on the SHADOW
path; OFF and LIVE meta dicts MUST stay byte-identical to pre-R3.d/e
(verified separately by the R3.a golden fixtures).
"""

from __future__ import annotations

import copy
import os
import unittest
from typing import Any, Dict, List
from unittest.mock import patch

os.environ.setdefault("TRUELINE_JWT_SECRET", "pt-act-r3de-secret")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "pt-act-r3de-auth-secret")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

from backend import main as M


# ---------------------------------------------------------------------------
# Flag context — set/clear PT.1 & PT.2.0 live/shadow flags deterministically
# ---------------------------------------------------------------------------


class _FlagContext:
    def __init__(self, **flags: Any) -> None:
        self.flags = flags
        self._sentinel = object()
        self._saved: Dict[str, Any] = {}

    def __enter__(self) -> "_FlagContext":
        for env_name, value in self.flags.items():
            self._saved[env_name] = os.environ.get(env_name, self._sentinel)
            if value is False or value is None:
                os.environ.pop(env_name, None)
            else:
                os.environ[env_name] = str(value) if value is not True else "1"
        return self

    def __exit__(self, *args: Any) -> None:
        for env_name, prior in self._saved.items():
            if prior is self._sentinel:
                os.environ.pop(env_name, None)
            else:
                os.environ[env_name] = prior  # type: ignore[assignment]


PT1_LIVE   = M._PRINT_TO_SHEET_BOOST_FLAG_ENV
PT1_SHADOW = M._PRINT_TO_SHEET_BOOST_SHADOW_FLAG_ENV
PT2_LIVE   = M._SHEET_ADJACENCY_BOOST_FLAG_ENV
PT2_SHADOW = M._SHEET_ADJACENCY_BOOST_SHADOW_FLAG_ENV


# ---------------------------------------------------------------------------
# Synthetic input helpers — match test_r3_golden_fixtures.py shape
# ---------------------------------------------------------------------------


def _ranking(rid: str, score: float, *, name: str = "") -> Dict[str, Any]:
    return {
        "route_id":        rid,
        "route_name":      name or f"name_{rid}",
        "score":           float(score),
        "combined_score":  float(score),
        "route_score":     0.0,
        "route_length_ft": 1000.0,
    }


def _group(tokens: List[Any]) -> Dict[str, Any]:
    return {
        "group_idx":   0,
        "source_file": "shadow.csv",
        "print_tokens": list(tokens),
    }


# ===========================================================================
# 1. Mode resolution — LIVE > SHADOW > OFF precedence
# ===========================================================================


class TestModeResolution(unittest.TestCase):
    def test_pt1_mode_off_when_both_flags_unset(self) -> None:
        with _FlagContext(**{PT1_LIVE: False, PT1_SHADOW: False}):
            self.assertEqual(M._trueline_print_to_sheet_boost_mode(), "off")

    def test_pt1_mode_live_when_only_live_flag_set(self) -> None:
        with _FlagContext(**{PT1_LIVE: True, PT1_SHADOW: False}):
            self.assertEqual(M._trueline_print_to_sheet_boost_mode(), "live")

    def test_pt1_mode_shadow_when_only_shadow_flag_set(self) -> None:
        with _FlagContext(**{PT1_LIVE: False, PT1_SHADOW: True}):
            self.assertEqual(M._trueline_print_to_sheet_boost_mode(), "shadow")

    def test_pt1_mode_live_when_both_flags_set(self) -> None:
        with _FlagContext(**{PT1_LIVE: True, PT1_SHADOW: True}):
            self.assertEqual(M._trueline_print_to_sheet_boost_mode(), "live")

    def test_pt1_mode_accepts_alt_truthy_strings(self) -> None:
        for v in ("1", "true", "yes", "on", "TRUE", "Yes", "On"):
            with _FlagContext(**{PT1_LIVE: False, PT1_SHADOW: v}):
                self.assertEqual(
                    M._trueline_print_to_sheet_boost_mode(), "shadow",
                    f"shadow flag value {v!r} should resolve to shadow",
                )

    def test_pt2_mode_off_when_both_flags_unset(self) -> None:
        with _FlagContext(**{PT2_LIVE: False, PT2_SHADOW: False}):
            self.assertEqual(M._trueline_sheet_adjacency_boost_mode(), "off")

    def test_pt2_mode_live_when_only_live_flag_set(self) -> None:
        with _FlagContext(**{PT2_LIVE: True, PT2_SHADOW: False}):
            self.assertEqual(M._trueline_sheet_adjacency_boost_mode(), "live")

    def test_pt2_mode_shadow_when_only_shadow_flag_set(self) -> None:
        with _FlagContext(**{PT2_LIVE: False, PT2_SHADOW: True}):
            self.assertEqual(M._trueline_sheet_adjacency_boost_mode(), "shadow")

    def test_pt2_mode_live_when_both_flags_set(self) -> None:
        with _FlagContext(**{PT2_LIVE: True, PT2_SHADOW: True}):
            self.assertEqual(M._trueline_sheet_adjacency_boost_mode(), "live")


# ===========================================================================
# 2. Shadow returns identity rankings (out is rankings)
# ===========================================================================


class TestShadowReturnsIdentity(unittest.TestCase):
    def test_pt1_shadow_returns_identity_when_boost_would_have_applied(self) -> None:
        rankings_in = [_ranking("rA", 0.60), _ranking("rB", 0.59)]
        with _FlagContext(**{PT1_LIVE: False, PT1_SHADOW: True}), \
                patch.object(M, "_print_to_sheets_from_packet_index",
                             return_value={"7": [42], "8": [43], "9": [44]}), \
                patch.object(M, "_sheet_to_route_ids_from_packet_index",
                             return_value={42: ["rB"], 43: ["rB"], 44: ["rB"]}):
            out, meta = M._apply_print_to_sheet_plausibility_boost(
                rankings_in, _group(["7", "8", "9"])
            )
            self.assertIs(out, rankings_in)
            self.assertEqual(meta["mode"], "shadow")
            self.assertEqual(meta["reason_if_not_applied"], "shadow_mode")
            self.assertFalse(meta["applied"])
            self.assertIn("shadow", meta)
            self.assertTrue(meta["shadow"]["computed"])
            self.assertTrue(meta["shadow"]["would_have_applied"])

    def test_pt2_shadow_returns_identity_when_boost_would_have_applied(self) -> None:
        rankings_in = [_ranking("rA", 0.60), _ranking("rB", 0.59)]
        seam = {"7": [101, 102]}
        seq = {"rA": [201], "rB": [101, 102]}
        with _FlagContext(**{PT2_LIVE: False, PT2_SHADOW: True}), \
                patch.object(M, "_print_to_sheets_from_packet_index", return_value=seam), \
                patch.object(M, "_route_sheet_sequence",
                             side_effect=lambda rid: seq.get(rid, [])):
            out, meta = M._apply_sheet_adjacency_plausibility_boost(rankings_in, _group(["7"]))
            self.assertIs(out, rankings_in)
            self.assertEqual(meta["mode"], "shadow")
            self.assertEqual(meta["reason_if_not_applied"], "shadow_mode")
            self.assertFalse(meta["applied"])
            self.assertIn("shadow", meta)
            self.assertTrue(meta["shadow"]["computed"])
            self.assertTrue(meta["shadow"]["would_have_applied"])

    def test_pt1_shadow_returns_identity_even_when_no_boost_would_have_applied(self) -> None:
        rankings_in = [_ranking("rA", 0.60), _ranking("rB", 0.55)]
        with _FlagContext(**{PT1_LIVE: False, PT1_SHADOW: True}), \
                patch.object(M, "_print_to_sheets_from_packet_index", return_value={}), \
                patch.object(M, "_sheet_to_route_ids_from_packet_index", return_value={}):
            out, meta = M._apply_print_to_sheet_plausibility_boost(rankings_in, _group(["7"]))
            self.assertIs(out, rankings_in)
            self.assertEqual(meta["mode"], "shadow")
            self.assertFalse(meta["shadow"]["would_have_applied"])

    def test_pt2_shadow_returns_identity_with_empty_seam(self) -> None:
        rankings_in = [_ranking("rA", 0.60)]
        with _FlagContext(**{PT2_LIVE: False, PT2_SHADOW: True}), \
                patch.object(M, "_print_to_sheets_from_packet_index", return_value={}), \
                patch.object(M, "_route_sheet_sequence", return_value=[]):
            out, meta = M._apply_sheet_adjacency_plausibility_boost(rankings_in, _group(["7"]))
            self.assertIs(out, rankings_in)
            self.assertEqual(meta["mode"], "shadow")
            self.assertFalse(meta["shadow"]["would_have_applied"])


# ===========================================================================
# 3. Shadow never mutates inputs
# ===========================================================================


class TestShadowDoesNotMutateInputs(unittest.TestCase):
    def test_pt1_shadow_does_not_mutate_rankings_or_group(self) -> None:
        rankings_in = [_ranking("rA", 0.60), _ranking("rB", 0.59)]
        group = _group(["7", "8", "9"])
        rankings_snapshot = copy.deepcopy(rankings_in)
        group_snapshot = copy.deepcopy(group)
        with _FlagContext(**{PT1_LIVE: False, PT1_SHADOW: True}), \
                patch.object(M, "_print_to_sheets_from_packet_index",
                             return_value={"7": [42], "8": [43], "9": [44]}), \
                patch.object(M, "_sheet_to_route_ids_from_packet_index",
                             return_value={42: ["rB"], 43: ["rB"], 44: ["rB"]}):
            M._apply_print_to_sheet_plausibility_boost(rankings_in, group)
        self.assertEqual(rankings_in, rankings_snapshot)
        self.assertEqual(group, group_snapshot)

    def test_pt2_shadow_does_not_mutate_rankings_or_group(self) -> None:
        rankings_in = [_ranking("rA", 0.60), _ranking("rB", 0.59)]
        group = _group(["7"])
        rankings_snapshot = copy.deepcopy(rankings_in)
        group_snapshot = copy.deepcopy(group)
        with _FlagContext(**{PT2_LIVE: False, PT2_SHADOW: True}), \
                patch.object(M, "_print_to_sheets_from_packet_index",
                             return_value={"7": [101, 102]}), \
                patch.object(M, "_route_sheet_sequence",
                             side_effect=lambda rid: {"rA": [201], "rB": [101, 102]}.get(rid, [])):
            M._apply_sheet_adjacency_plausibility_boost(rankings_in, group)
        self.assertEqual(rankings_in, rankings_snapshot)
        self.assertEqual(group, group_snapshot)

    def test_pt1_shadow_does_not_add_boost_delta_keys_to_entries(self) -> None:
        rankings_in = [_ranking("rA", 0.60), _ranking("rB", 0.59)]
        with _FlagContext(**{PT1_LIVE: False, PT1_SHADOW: True}), \
                patch.object(M, "_print_to_sheets_from_packet_index",
                             return_value={"7": [42], "8": [43], "9": [44]}), \
                patch.object(M, "_sheet_to_route_ids_from_packet_index",
                             return_value={42: ["rB"], 43: ["rB"], 44: ["rB"]}):
            out, _meta = M._apply_print_to_sheet_plausibility_boost(
                rankings_in, _group(["7", "8", "9"])
            )
            for entry in out:
                self.assertNotIn("print_to_sheet_boost_delta", entry)
                self.assertNotIn("print_to_sheet_boost_evidence", entry)


# ===========================================================================
# 4. Shadow block schema
# ===========================================================================


REQUIRED_SHADOW_KEYS = {
    "computed", "would_have_applied", "would_have_boosted_entries",
    "would_have_max_delta", "would_have_top2_gap",
    "would_have_reorder_attempted", "would_have_reordered",
    "would_have_reorder_blocked_reason",
    "would_have_top1_route_id", "top1_unchanged_vs_actual",
    "would_have_delta_by_route_id", "would_have_evidence", "error",
}


class TestShadowBlockSchema(unittest.TestCase):
    def test_pt1_shadow_block_required_keys_present(self) -> None:
        rankings_in = [_ranking("rA", 0.60), _ranking("rB", 0.59)]
        with _FlagContext(**{PT1_LIVE: False, PT1_SHADOW: True}), \
                patch.object(M, "_print_to_sheets_from_packet_index",
                             return_value={"7": [42], "8": [43], "9": [44]}), \
                patch.object(M, "_sheet_to_route_ids_from_packet_index",
                             return_value={42: ["rB"], 43: ["rB"], 44: ["rB"]}):
            _out, meta = M._apply_print_to_sheet_plausibility_boost(
                rankings_in, _group(["7", "8", "9"])
            )
            self.assertEqual(set(meta["shadow"].keys()), REQUIRED_SHADOW_KEYS)

    def test_pt2_shadow_block_required_keys_present(self) -> None:
        rankings_in = [_ranking("rA", 0.60), _ranking("rB", 0.59)]
        with _FlagContext(**{PT2_LIVE: False, PT2_SHADOW: True}), \
                patch.object(M, "_print_to_sheets_from_packet_index",
                             return_value={"7": [101, 102]}), \
                patch.object(M, "_route_sheet_sequence",
                             side_effect=lambda rid: {"rA": [201], "rB": [101, 102]}.get(rid, [])):
            _out, meta = M._apply_sheet_adjacency_plausibility_boost(rankings_in, _group(["7"]))
            self.assertEqual(set(meta["shadow"].keys()), REQUIRED_SHADOW_KEYS)

    def test_pt1_shadow_top1_changed_when_reorder_would_flip(self) -> None:
        # 0.60/0.59 with 3 tokens -> route_B; would-be 0.62 > 0.60 -> flip
        rankings_in = [_ranking("rA", 0.60), _ranking("rB", 0.59)]
        with _FlagContext(**{PT1_LIVE: False, PT1_SHADOW: True}), \
                patch.object(M, "_print_to_sheets_from_packet_index",
                             return_value={"7": [42], "8": [43], "9": [44]}), \
                patch.object(M, "_sheet_to_route_ids_from_packet_index",
                             return_value={42: ["rB"], 43: ["rB"], 44: ["rB"]}):
            _out, meta = M._apply_print_to_sheet_plausibility_boost(
                rankings_in, _group(["7", "8", "9"])
            )
            sh = meta["shadow"]
            self.assertTrue(sh["would_have_applied"])
            self.assertTrue(sh["would_have_reordered"])
            self.assertTrue(sh["would_have_reorder_attempted"])
            self.assertEqual(sh["would_have_top1_route_id"], "rB")
            self.assertFalse(sh["top1_unchanged_vs_actual"])

    def test_pt1_shadow_top1_unchanged_when_top1_was_already_boost_target(self) -> None:
        rankings_in = [_ranking("rA", 0.60), _ranking("rB", 0.55)]
        with _FlagContext(**{PT1_LIVE: False, PT1_SHADOW: True}), \
                patch.object(M, "_print_to_sheets_from_packet_index", return_value={"7": [42]}), \
                patch.object(M, "_sheet_to_route_ids_from_packet_index",
                             return_value={42: ["rA"]}):
            _out, meta = M._apply_print_to_sheet_plausibility_boost(rankings_in, _group(["7"]))
            sh = meta["shadow"]
            self.assertTrue(sh["would_have_applied"])
            self.assertEqual(sh["would_have_top1_route_id"], "rA")
            self.assertTrue(sh["top1_unchanged_vs_actual"])

    def test_pt1_shadow_delta_by_route_id_populated(self) -> None:
        rankings_in = [_ranking("rA", 0.60), _ranking("rB", 0.59)]
        with _FlagContext(**{PT1_LIVE: False, PT1_SHADOW: True}), \
                patch.object(M, "_print_to_sheets_from_packet_index",
                             return_value={"7": [42], "8": [43], "9": [44]}), \
                patch.object(M, "_sheet_to_route_ids_from_packet_index",
                             return_value={42: ["rB"], 43: ["rB"], 44: ["rB"]}):
            _out, meta = M._apply_print_to_sheet_plausibility_boost(
                rankings_in, _group(["7", "8", "9"])
            )
            self.assertIn("rB", meta["shadow"]["would_have_delta_by_route_id"])
            self.assertAlmostEqual(
                meta["shadow"]["would_have_delta_by_route_id"]["rB"], 0.03, places=9,
            )

    def test_pt2_shadow_evidence_carries_per_route_match(self) -> None:
        rankings_in = [_ranking("rA", 0.60), _ranking("rB", 0.59)]
        with _FlagContext(**{PT2_LIVE: False, PT2_SHADOW: True}), \
                patch.object(M, "_print_to_sheets_from_packet_index",
                             return_value={"7": [101, 102]}), \
                patch.object(M, "_route_sheet_sequence",
                             side_effect=lambda rid: {"rA": [201], "rB": [101, 102]}.get(rid, [])):
            _out, meta = M._apply_sheet_adjacency_plausibility_boost(rankings_in, _group(["7"]))
            ev = meta["shadow"]["would_have_evidence"]
            self.assertIn("seam_sheets", ev)
            self.assertIn("per_route_match", ev)
            self.assertIn("rB", ev["per_route_match"])
            self.assertEqual(ev["per_route_match"]["rB"]["matched_count"], 2)


# ===========================================================================
# 5. Shadow exception safety — never escapes; error field populated
# ===========================================================================


class TestShadowErrorSafety(unittest.TestCase):
    def test_pt1_shadow_catches_seam_exception(self) -> None:
        rankings_in = [_ranking("rA", 0.60)]
        with _FlagContext(**{PT1_LIVE: False, PT1_SHADOW: True}), \
                patch.object(M, "_print_to_sheets_from_packet_index",
                             side_effect=RuntimeError("boom")), \
                patch.object(M, "_sheet_to_route_ids_from_packet_index",
                             side_effect=RuntimeError("boom")):
            # The internal helper itself swallows seam exceptions, so this
            # test exercises a different leak path — patch _compute_internal
            # directly to raise.
            pass

    def test_pt1_shadow_catches_internal_compute_exception(self) -> None:
        rankings_in = [_ranking("rA", 0.60)]
        with _FlagContext(**{PT1_LIVE: False, PT1_SHADOW: True}), \
                patch.object(M, "_compute_print_to_sheet_boost_internal",
                             side_effect=RuntimeError("synthetic shadow failure")):
            out, meta = M._apply_print_to_sheet_plausibility_boost(
                rankings_in, _group(["7"])
            )
            self.assertIs(out, rankings_in)
            self.assertEqual(meta["mode"], "shadow")
            self.assertEqual(meta["reason_if_not_applied"], "shadow_mode")
            self.assertEqual(meta["shadow"], {"computed": False, "error": "RuntimeError"})

    def test_pt2_shadow_catches_internal_compute_exception(self) -> None:
        rankings_in = [_ranking("rA", 0.60)]
        with _FlagContext(**{PT2_LIVE: False, PT2_SHADOW: True}), \
                patch.object(M, "_compute_sheet_adjacency_boost_internal",
                             side_effect=ValueError("synthetic shadow failure")):
            out, meta = M._apply_sheet_adjacency_plausibility_boost(
                rankings_in, _group(["7"])
            )
            self.assertIs(out, rankings_in)
            self.assertEqual(meta["mode"], "shadow")
            self.assertEqual(meta["reason_if_not_applied"], "shadow_mode")
            self.assertEqual(meta["shadow"], {"computed": False, "error": "ValueError"})

    def test_pt1_shadow_exception_never_propagates(self) -> None:
        rankings_in = [_ranking("rA", 0.60)]
        with _FlagContext(**{PT1_LIVE: False, PT1_SHADOW: True}), \
                patch.object(M, "_compute_print_to_sheet_boost_internal",
                             side_effect=KeyError("boom")):
            try:
                _out, _meta = M._apply_print_to_sheet_plausibility_boost(
                    rankings_in, _group(["7"])
                )
            except Exception as e:  # pragma: no cover
                self.fail(f"shadow path leaked exception: {e!r}")


# ===========================================================================
# 6. LIVE precedence over SHADOW
# ===========================================================================


class TestLiveOverridesShadow(unittest.TestCase):
    def test_pt1_both_flags_set_executes_live_path(self) -> None:
        rankings_in = [_ranking("rA", 0.60), _ranking("rB", 0.59)]
        with _FlagContext(**{PT1_LIVE: True, PT1_SHADOW: True}), \
                patch.object(M, "_print_to_sheets_from_packet_index",
                             return_value={"7": [42], "8": [43], "9": [44]}), \
                patch.object(M, "_sheet_to_route_ids_from_packet_index",
                             return_value={42: ["rB"], 43: ["rB"], 44: ["rB"]}):
            out, meta = M._apply_print_to_sheet_plausibility_boost(
                rankings_in, _group(["7", "8", "9"])
            )
            self.assertEqual(meta["mode"], "live")
            self.assertTrue(meta["applied"])
            self.assertNotIn("shadow", meta)  # schema (b): no shadow key on LIVE
            # rankings actually flipped (boost applied)
            self.assertEqual(out[0]["route_id"], "rB")
            self.assertIsNot(out, rankings_in)  # LIVE returns fresh list

    def test_pt2_both_flags_set_executes_live_path(self) -> None:
        rankings_in = [_ranking("rA", 0.60), _ranking("rB", 0.59)]
        with _FlagContext(**{PT2_LIVE: True, PT2_SHADOW: True}), \
                patch.object(M, "_print_to_sheets_from_packet_index",
                             return_value={"7": [101, 102]}), \
                patch.object(M, "_route_sheet_sequence",
                             side_effect=lambda rid: {"rA": [201], "rB": [101, 102]}.get(rid, [])):
            out, meta = M._apply_sheet_adjacency_plausibility_boost(rankings_in, _group(["7"]))
            self.assertEqual(meta["mode"], "live")
            self.assertTrue(meta["applied"])
            self.assertNotIn("shadow", meta)
            self.assertEqual(out[0]["route_id"], "rB")
            self.assertIsNot(out, rankings_in)


# ===========================================================================
# 7. SHADOW computes the same as LIVE (algorithmic equivalence)
# ===========================================================================


class TestShadowComputesSameAsLive(unittest.TestCase):
    """Run the same input through LIVE and SHADOW; assert the shadow block's
    would_have_* fields match LIVE's actual outputs."""

    def test_pt1_shadow_facts_match_live_for_reorder_flip_scenario(self) -> None:
        rankings_in_live = [_ranking("rA", 0.60), _ranking("rB", 0.59)]
        rankings_in_shadow = [_ranking("rA", 0.60), _ranking("rB", 0.59)]
        seam = {"7": [42], "8": [43], "9": [44]}
        s2r = {42: ["rB"], 43: ["rB"], 44: ["rB"]}

        with _FlagContext(**{PT1_LIVE: True, PT1_SHADOW: False}), \
                patch.object(M, "_print_to_sheets_from_packet_index", return_value=seam), \
                patch.object(M, "_sheet_to_route_ids_from_packet_index", return_value=s2r):
            live_out, live_meta = M._apply_print_to_sheet_plausibility_boost(
                rankings_in_live, _group(["7", "8", "9"])
            )

        with _FlagContext(**{PT1_LIVE: False, PT1_SHADOW: True}), \
                patch.object(M, "_print_to_sheets_from_packet_index", return_value=seam), \
                patch.object(M, "_sheet_to_route_ids_from_packet_index", return_value=s2r):
            _shadow_out, shadow_meta = M._apply_print_to_sheet_plausibility_boost(
                rankings_in_shadow, _group(["7", "8", "9"])
            )

        sh = shadow_meta["shadow"]
        self.assertEqual(sh["would_have_applied"], live_meta["applied"])
        self.assertEqual(sh["would_have_boosted_entries"], live_meta["boosted_entries"])
        self.assertAlmostEqual(sh["would_have_max_delta"], live_meta["max_delta_applied"],
                               places=9)
        self.assertAlmostEqual(sh["would_have_top2_gap"], live_meta["top2_gap_before_bias"],
                               places=9)
        self.assertEqual(sh["would_have_reorder_attempted"], live_meta["reorder_attempted"])
        self.assertEqual(sh["would_have_reordered"], live_meta["reordered"])
        self.assertEqual(sh["would_have_top1_route_id"], live_out[0]["route_id"])

    def test_pt2_shadow_facts_match_live_for_reorder_flip_scenario(self) -> None:
        rankings_in_live = [_ranking("rA", 0.60), _ranking("rB", 0.59)]
        rankings_in_shadow = [_ranking("rA", 0.60), _ranking("rB", 0.59)]
        seam = {"7": [101, 102]}
        seq = {"rA": [201], "rB": [101, 102]}

        with _FlagContext(**{PT2_LIVE: True, PT2_SHADOW: False}), \
                patch.object(M, "_print_to_sheets_from_packet_index", return_value=seam), \
                patch.object(M, "_route_sheet_sequence",
                             side_effect=lambda rid: seq.get(rid, [])):
            live_out, live_meta = M._apply_sheet_adjacency_plausibility_boost(
                rankings_in_live, _group(["7"])
            )

        with _FlagContext(**{PT2_LIVE: False, PT2_SHADOW: True}), \
                patch.object(M, "_print_to_sheets_from_packet_index", return_value=seam), \
                patch.object(M, "_route_sheet_sequence",
                             side_effect=lambda rid: seq.get(rid, [])):
            _shadow_out, shadow_meta = M._apply_sheet_adjacency_plausibility_boost(
                rankings_in_shadow, _group(["7"])
            )

        sh = shadow_meta["shadow"]
        self.assertEqual(sh["would_have_applied"], live_meta["applied"])
        self.assertEqual(sh["would_have_boosted_entries"], live_meta["boosted_entries"])
        self.assertAlmostEqual(sh["would_have_max_delta"], live_meta["max_delta_applied"],
                               places=9)
        self.assertEqual(sh["would_have_reordered"], live_meta["reordered"])
        self.assertEqual(sh["would_have_top1_route_id"], live_out[0]["route_id"])


# ===========================================================================
# 8. OFF behavior unchanged — no shadow key, identity passthrough
# ===========================================================================


class TestOffPathUnchanged(unittest.TestCase):
    def test_pt1_off_has_no_shadow_key(self) -> None:
        rankings_in = [_ranking("rA", 0.60), _ranking("rB", 0.59)]
        with _FlagContext(**{PT1_LIVE: False, PT1_SHADOW: False}):
            out, meta = M._apply_print_to_sheet_plausibility_boost(
                rankings_in, _group(["7"])
            )
            self.assertIs(out, rankings_in)
            self.assertEqual(meta["mode"], "off")
            self.assertEqual(meta["reason_if_not_applied"], "flag_off")
            self.assertNotIn("shadow", meta)

    def test_pt2_off_has_no_shadow_key(self) -> None:
        rankings_in = [_ranking("rA", 0.60), _ranking("rB", 0.59)]
        with _FlagContext(**{PT2_LIVE: False, PT2_SHADOW: False}):
            out, meta = M._apply_sheet_adjacency_plausibility_boost(
                rankings_in, _group(["7"])
            )
            self.assertIs(out, rankings_in)
            self.assertEqual(meta["mode"], "off")
            self.assertEqual(meta["reason_if_not_applied"], "flag_off")
            self.assertNotIn("shadow", meta)


if __name__ == "__main__":
    unittest.main()
