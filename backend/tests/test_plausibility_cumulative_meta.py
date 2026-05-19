"""PT.ACT R2 — plausibility cumulative diagnostic envelope tests.

Exercises `_build_plausibility_cumulative_meta` purely. The helper is
diagnostic-only — no rankings mutation, no meta mutation, no module-state
side effects, never raises on pathological inputs.

Schema doc: wiki/pt-act-r2-cumulative-envelope-design.md
Schema version under test: "plausibility-cumulative-1"
"""

from __future__ import annotations

import copy
import os
import unittest
from typing import Any, Dict, List, Tuple
from unittest.mock import patch

os.environ.setdefault("TRUELINE_JWT_SECRET", "pt-act-r2-secret")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "pt-act-r2-auth-secret")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

from backend import main as M


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ranking(rid: str, score: float, *, p2s_delta: float = 0.0,
             sa_delta: float = 0.0) -> Dict[str, Any]:
    entry: Dict[str, Any] = {
        "route_id":        rid,
        "route_name":      f"name_{rid}",
        "score":           float(score),
        "combined_score":  float(score),
        "route_score":     0.0,
        "route_length_ft": 1000.0,
    }
    if p2s_delta:
        entry["print_to_sheet_boost_delta"] = float(p2s_delta)
    if sa_delta:
        entry["sheet_adjacency_boost_delta"] = float(sa_delta)
    return entry


def _pt1_meta(*, mode: str = "off", applied: bool = False,
              reorder_attempted: bool = False, reordered: bool = False,
              reason: Any = "flag_off",
              selection_impact: Any = None,
              **extra: Any) -> Dict[str, Any]:
    base: Dict[str, Any] = {
        "applied":                    applied,
        "flag_enabled":               mode == "live",
        "reason_if_not_applied":      reason,
        "tokens_considered":          0,
        "tokens_resolving_to_sheets": 0,
        "routes_with_evidence":       0,
        "boosted_entries":            0,
        "max_delta_applied":          0.0,
        "top2_gap_before_bias":       0.0,
        "reordered":                  reordered,
        "evidence_by_route_id":       {},
        "evidence_by_sheet_int":      {},
        "mode":                       mode,
        "reorder_attempted":          reorder_attempted,
        "reorder_blocked_reason":     "layer_not_applied" if mode == "off" else None,
        "selection_impact":           selection_impact,
    }
    base.update(extra)
    return base


def _pt20_meta(*, mode: str = "off", applied: bool = False,
               reorder_attempted: bool = False, reordered: bool = False,
               reason: Any = "flag_off",
               selection_impact: Any = None,
               **extra: Any) -> Dict[str, Any]:
    base: Dict[str, Any] = {
        "applied":                    applied,
        "flag_enabled":               mode == "live",
        "reason_if_not_applied":      reason,
        "seam_sheets":                [],
        "tokens_considered":          0,
        "tokens_resolving_to_sheets": 0,
        "routes_with_sequence":       0,
        "boosted_entries":            0,
        "max_delta_applied":          0.0,
        "top2_gap_before_bias":       0.0,
        "reordered":                  reordered,
        "per_route_match":            {},
        "mode":                       mode,
        "reorder_attempted":          reorder_attempted,
        "reorder_blocked_reason":     "layer_not_applied" if mode == "off" else None,
        "selection_impact":           selection_impact,
    }
    base.update(extra)
    return base


REQUIRED_ENVELOPE_KEYS = {
    # v1 fields (preserved byte-compatible in v2)
    "schema_version", "generated_at_step",
    "layers_present", "layers_applied", "modes_by_layer",
    "total_boost_delta_by_route_id", "max_total_delta",
    "max_total_delta_ceiling",
    "any_reorder_attempted", "any_reordered",
    "selection_impact_stack", "selection_changed_by_layers",
    "cap_governance",
    # R3.f v2 additions (shadow aggregation)
    "shadow_layers", "selection_impact_shadow_stack",
    "total_shadow_boost_delta_by_route_id", "max_total_shadow_delta",
    "cross_layer_top1_agreement",
    "any_layer_shadow_error", "any_would_have_changed_top1",
    "any_shadow_layer_would_have_applied",
}

REQUIRED_CAP_GOVERNANCE_KEYS = {"violations", "cap_per_layer", "ceiling"}


# ===========================================================================
# 1. Shape — schema invariants
# ===========================================================================


class TestShape(unittest.TestCase):
    def test_off_off_emits_full_schema_with_zero_state(self) -> None:
        env = M._build_plausibility_cumulative_meta(
            [],
            [("PT.1", _pt1_meta()), ("PT.2.0", _pt20_meta())],
        )
        self.assertEqual(set(env.keys()), REQUIRED_ENVELOPE_KEYS)
        self.assertEqual(env["schema_version"], "plausibility-cumulative-2")
        self.assertEqual(env["layers_present"], ["PT.1", "PT.2.0"])
        self.assertEqual(env["layers_applied"], [])
        self.assertEqual(env["modes_by_layer"], {"PT.1": "off", "PT.2.0": "off"})
        self.assertEqual(env["total_boost_delta_by_route_id"], {})
        self.assertEqual(env["max_total_delta"], 0.0)
        self.assertFalse(env["any_reorder_attempted"])
        self.assertFalse(env["any_reordered"])
        self.assertEqual(env["selection_impact_stack"], [])
        self.assertEqual(env["selection_changed_by_layers"], [])
        self.assertEqual(set(env["cap_governance"].keys()), REQUIRED_CAP_GOVERNANCE_KEYS)

    def test_keys_match_required_set_in_every_mode(self) -> None:
        scenarios = [
            ([], [("PT.1", _pt1_meta()), ("PT.2.0", _pt20_meta())]),
            ([_ranking("r1", 0.6)],
             [("PT.1", _pt1_meta(mode="live", applied=True, reason=None,
                                 reorder_attempted=False,
                                 selection_impact={"pre_layer_top1": "r1",
                                                   "post_layer_top1": "r1",
                                                   "changed": False})),
              ("PT.2.0", _pt20_meta())]),
            ([_ranking("r1", 0.6, p2s_delta=0.03)],
             [("PT.1", _pt1_meta(mode="live", applied=True, reason=None,
                                 reorder_attempted=True,
                                 selection_impact={"pre_layer_top1": "r2",
                                                   "post_layer_top1": "r1",
                                                   "changed": True})),
              ("PT.2.0", _pt20_meta(mode="live", applied=True, reason=None))]),
        ]
        for rankings, metas in scenarios:
            env = M._build_plausibility_cumulative_meta(rankings, metas)
            self.assertEqual(set(env.keys()), REQUIRED_ENVELOPE_KEYS)
            self.assertEqual(set(env["cap_governance"].keys()), REQUIRED_CAP_GOVERNANCE_KEYS)

    def test_schema_version_is_v2(self) -> None:
        env = M._build_plausibility_cumulative_meta([], [])
        self.assertEqual(env["schema_version"], "plausibility-cumulative-2")
        self.assertEqual(env["schema_version"],
                         M._PLAUSIBILITY_CUMULATIVE_SCHEMA_VERSION)

    def test_generated_at_step_passthrough(self) -> None:
        env = M._build_plausibility_cumulative_meta([], [], step="custom_step")
        self.assertEqual(env["generated_at_step"], "custom_step")
        env_default = M._build_plausibility_cumulative_meta([], [])
        self.assertEqual(env_default["generated_at_step"], "post_ranking_boosts")


# ===========================================================================
# 2. Layers present / applied / modes
# ===========================================================================


class TestLayersPresentApplied(unittest.TestCase):
    def test_layers_present_lists_registry_order(self) -> None:
        env = M._build_plausibility_cumulative_meta([], [])
        self.assertEqual(env["layers_present"], ["PT.1", "PT.2.0"])
        # Order matches the module-level registry exactly.
        registry_order = [name for name, _ in M._PLAUSIBILITY_LAYER_REGISTRY]
        self.assertEqual(env["layers_present"], registry_order)

    def test_layers_applied_includes_only_applied_metas(self) -> None:
        env = M._build_plausibility_cumulative_meta(
            [],
            [("PT.1", _pt1_meta(mode="live", applied=True, reason=None)),
             ("PT.2.0", _pt20_meta(mode="live", applied=False))],
        )
        self.assertEqual(env["layers_applied"], ["PT.1"])

    def test_layers_applied_both_when_both_applied(self) -> None:
        env = M._build_plausibility_cumulative_meta(
            [],
            [("PT.1", _pt1_meta(mode="live", applied=True, reason=None)),
             ("PT.2.0", _pt20_meta(mode="live", applied=True, reason=None))],
        )
        self.assertEqual(env["layers_applied"], ["PT.1", "PT.2.0"])

    def test_modes_by_layer_reflects_each_meta_mode(self) -> None:
        env = M._build_plausibility_cumulative_meta(
            [],
            [("PT.1", _pt1_meta(mode="off")),
             ("PT.2.0", _pt20_meta(mode="live", applied=True, reason=None))],
        )
        self.assertEqual(env["modes_by_layer"], {"PT.1": "off", "PT.2.0": "live"})


# ===========================================================================
# 3. Total boost deltas
# ===========================================================================


class TestTotalBoostDeltas(unittest.TestCase):
    def test_delta_sum_combines_pt1_and_pt2_annotations(self) -> None:
        rankings = [
            _ranking("r1", 0.62, p2s_delta=0.02, sa_delta=0.03),
            _ranking("r2", 0.55, p2s_delta=0.01),
            _ranking("r3", 0.5),
        ]
        env = M._build_plausibility_cumulative_meta(rankings, [])
        self.assertAlmostEqual(env["total_boost_delta_by_route_id"]["r1"], 0.05, places=9)
        self.assertAlmostEqual(env["total_boost_delta_by_route_id"]["r2"], 0.01, places=9)
        self.assertNotIn("r3", env["total_boost_delta_by_route_id"])

    def test_entries_with_zero_delta_omitted(self) -> None:
        rankings = [_ranking("r1", 0.6), _ranking("r2", 0.5)]
        env = M._build_plausibility_cumulative_meta(rankings, [])
        self.assertEqual(env["total_boost_delta_by_route_id"], {})

    def test_non_dict_entries_skipped(self) -> None:
        rankings: List[Any] = [
            _ranking("r1", 0.6, p2s_delta=0.02),
            "not-a-dict",
            42,
            None,
        ]
        env = M._build_plausibility_cumulative_meta(rankings, [])
        self.assertEqual(set(env["total_boost_delta_by_route_id"].keys()), {"r1"})

    def test_non_numeric_deltas_coerced_to_zero(self) -> None:
        rankings = [
            {
                "route_id":                    "r1",
                "print_to_sheet_boost_delta": "not-a-number",
                "sheet_adjacency_boost_delta": None,
            },
            {
                "route_id":                    "r2",
                "print_to_sheet_boost_delta": True,  # bool is excluded explicitly
                "sheet_adjacency_boost_delta": "0.02",  # numeric-as-str -> coerced
            },
        ]
        env = M._build_plausibility_cumulative_meta(rankings, [])
        # r1: both annotations unusable -> total 0 -> omitted
        self.assertNotIn("r1", env["total_boost_delta_by_route_id"])
        # r2: bool excluded, "0.02" coerced -> total 0.02 -> included
        self.assertAlmostEqual(env["total_boost_delta_by_route_id"]["r2"], 0.02, places=9)

    def test_max_total_delta_reflects_largest(self) -> None:
        rankings = [
            _ranking("r1", 0.6, p2s_delta=0.01, sa_delta=0.01),
            _ranking("r2", 0.6, p2s_delta=0.03, sa_delta=0.02),
            _ranking("r3", 0.6, p2s_delta=0.01),
        ]
        env = M._build_plausibility_cumulative_meta(rankings, [])
        self.assertAlmostEqual(env["max_total_delta"], 0.05, places=9)

    def test_max_total_delta_zero_when_no_deltas(self) -> None:
        env = M._build_plausibility_cumulative_meta(
            [_ranking("r1", 0.6)], [],
        )
        self.assertEqual(env["max_total_delta"], 0.0)

    def test_static_ceiling_is_registry_sum(self) -> None:
        env = M._build_plausibility_cumulative_meta([], [])
        expected_ceiling = sum(cap for _, cap in M._PLAUSIBILITY_LAYER_REGISTRY)
        self.assertAlmostEqual(env["max_total_delta_ceiling"], expected_ceiling, places=9)
        self.assertAlmostEqual(env["cap_governance"]["ceiling"], expected_ceiling, places=9)


# ===========================================================================
# 4. Reorder aggregation
# ===========================================================================


class TestReorderAggregation(unittest.TestCase):
    def test_any_reorder_attempted_true_when_either_layer_attempted(self) -> None:
        # PT.1 attempted, PT.2.0 not
        env = M._build_plausibility_cumulative_meta(
            [],
            [("PT.1", _pt1_meta(mode="live", applied=True, reason=None,
                                reorder_attempted=True)),
             ("PT.2.0", _pt20_meta(mode="live", applied=True, reason=None,
                                   reorder_attempted=False))],
        )
        self.assertTrue(env["any_reorder_attempted"])

        # PT.2.0 attempted, PT.1 not
        env = M._build_plausibility_cumulative_meta(
            [],
            [("PT.1", _pt1_meta()),
             ("PT.2.0", _pt20_meta(mode="live", applied=True, reason=None,
                                   reorder_attempted=True))],
        )
        self.assertTrue(env["any_reorder_attempted"])

    def test_any_reordered_true_when_either_layer_actually_reordered(self) -> None:
        env = M._build_plausibility_cumulative_meta(
            [],
            [("PT.1", _pt1_meta(mode="live", applied=True, reason=None,
                                reorder_attempted=True, reordered=True)),
             ("PT.2.0", _pt20_meta())],
        )
        self.assertTrue(env["any_reordered"])

    def test_both_false_in_off_off(self) -> None:
        env = M._build_plausibility_cumulative_meta(
            [],
            [("PT.1", _pt1_meta()), ("PT.2.0", _pt20_meta())],
        )
        self.assertFalse(env["any_reorder_attempted"])
        self.assertFalse(env["any_reordered"])


# ===========================================================================
# 5. Selection-impact stack
# ===========================================================================


class TestSelectionImpactStack(unittest.TestCase):
    def test_stack_preserves_call_order_pt1_then_pt2(self) -> None:
        si_pt1 = {"pre_layer_top1": "rA", "post_layer_top1": "rB", "changed": True}
        si_pt2 = {"pre_layer_top1": "rB", "post_layer_top1": "rB", "changed": False}
        env = M._build_plausibility_cumulative_meta(
            [],
            [("PT.1", _pt1_meta(mode="live", applied=True, reason=None,
                                selection_impact=si_pt1)),
             ("PT.2.0", _pt20_meta(mode="live", applied=True, reason=None,
                                   selection_impact=si_pt2))],
        )
        self.assertEqual(len(env["selection_impact_stack"]), 2)
        self.assertEqual(env["selection_impact_stack"][0]["layer"], "PT.1")
        self.assertEqual(env["selection_impact_stack"][0]["pre_layer_top1"], "rA")
        self.assertEqual(env["selection_impact_stack"][0]["post_layer_top1"], "rB")
        self.assertTrue(env["selection_impact_stack"][0]["changed"])
        self.assertEqual(env["selection_impact_stack"][1]["layer"], "PT.2.0")
        self.assertEqual(env["selection_impact_stack"][1]["pre_layer_top1"], "rB")
        self.assertFalse(env["selection_impact_stack"][1]["changed"])

    def test_stack_skips_layers_with_none_selection_impact(self) -> None:
        env = M._build_plausibility_cumulative_meta(
            [],
            [("PT.1", _pt1_meta()),  # off-mode: selection_impact=None
             ("PT.2.0", _pt20_meta(mode="live", applied=True, reason=None,
                                   selection_impact={"pre_layer_top1": "rX",
                                                     "post_layer_top1": "rX",
                                                     "changed": False}))],
        )
        self.assertEqual(len(env["selection_impact_stack"]), 1)
        self.assertEqual(env["selection_impact_stack"][0]["layer"], "PT.2.0")

    def test_selection_changed_by_layers_lists_changed_layers_only(self) -> None:
        env = M._build_plausibility_cumulative_meta(
            [],
            [("PT.1", _pt1_meta(mode="live", applied=True, reason=None,
                                selection_impact={"pre_layer_top1": "rA",
                                                  "post_layer_top1": "rB",
                                                  "changed": True})),
             ("PT.2.0", _pt20_meta(mode="live", applied=True, reason=None,
                                   selection_impact={"pre_layer_top1": "rB",
                                                     "post_layer_top1": "rB",
                                                     "changed": False}))],
        )
        self.assertEqual(env["selection_changed_by_layers"], ["PT.1"])

    def test_selection_changed_by_layers_empty_in_off_off(self) -> None:
        env = M._build_plausibility_cumulative_meta(
            [],
            [("PT.1", _pt1_meta()), ("PT.2.0", _pt20_meta())],
        )
        self.assertEqual(env["selection_changed_by_layers"], [])


# ===========================================================================
# 6. Cap governance
# ===========================================================================


class TestCapGovernance(unittest.TestCase):
    def test_violations_empty_when_total_delta_within_ceiling(self) -> None:
        rankings = [_ranking("r1", 0.6, p2s_delta=0.03, sa_delta=0.03)]
        env = M._build_plausibility_cumulative_meta(rankings, [])
        self.assertEqual(env["cap_governance"]["violations"], [])

    def test_violations_detected_when_synthetic_delta_exceeds_ceiling(self) -> None:
        # Synthetic injection: PT.1 delta = 0.10 alone breaches ceiling 0.06.
        rankings = [_ranking("r1", 0.6, p2s_delta=0.10)]
        env = M._build_plausibility_cumulative_meta(rankings, [])
        self.assertEqual(len(env["cap_governance"]["violations"]), 1)
        v = env["cap_governance"]["violations"][0]
        self.assertEqual(v["route_id"], "r1")
        self.assertAlmostEqual(v["observed_delta"], 0.10, places=9)
        self.assertAlmostEqual(v["ceiling"], 0.06, places=9)
        self.assertEqual(v["reason"], "delta_exceeds_registered_layer_caps_sum")

    def test_violations_multiple_route_ids(self) -> None:
        rankings = [
            _ranking("r1", 0.6, p2s_delta=0.08),
            _ranking("r2", 0.6, p2s_delta=0.03),
            _ranking("r3", 0.6, sa_delta=0.09),
        ]
        env = M._build_plausibility_cumulative_meta(rankings, [])
        violation_rids = sorted(v["route_id"] for v in env["cap_governance"]["violations"])
        self.assertEqual(violation_rids, ["r1", "r3"])

    def test_cap_per_layer_matches_registry(self) -> None:
        env = M._build_plausibility_cumulative_meta([], [])
        expected = {name: cap for name, cap in M._PLAUSIBILITY_LAYER_REGISTRY}
        self.assertEqual(env["cap_governance"]["cap_per_layer"], expected)

    def test_ceiling_is_sum_of_caps(self) -> None:
        env = M._build_plausibility_cumulative_meta([], [])
        expected = sum(cap for _, cap in M._PLAUSIBILITY_LAYER_REGISTRY)
        self.assertAlmostEqual(env["cap_governance"]["ceiling"], expected, places=9)


# ===========================================================================
# 7. Diagnostic-only — central proof of non-mutation
# ===========================================================================


class TestDiagnosticOnly(unittest.TestCase):
    def test_helper_does_not_mutate_rankings_list(self) -> None:
        rankings = [
            _ranking("r1", 0.6, p2s_delta=0.02, sa_delta=0.03),
            _ranking("r2", 0.5),
        ]
        snapshot = copy.deepcopy(rankings)
        _ = M._build_plausibility_cumulative_meta(
            rankings,
            [("PT.1", _pt1_meta()), ("PT.2.0", _pt20_meta())],
        )
        self.assertEqual(rankings, snapshot)

    def test_helper_does_not_mutate_meta_dicts(self) -> None:
        pt1 = _pt1_meta(mode="live", applied=True, reason=None,
                        reorder_attempted=True, reordered=True,
                        selection_impact={"pre_layer_top1": "rA",
                                          "post_layer_top1": "rB",
                                          "changed": True})
        pt20 = _pt20_meta(mode="live", applied=True, reason=None,
                          selection_impact={"pre_layer_top1": "rB",
                                            "post_layer_top1": "rB",
                                            "changed": False})
        pt1_snapshot = copy.deepcopy(pt1)
        pt20_snapshot = copy.deepcopy(pt20)
        _ = M._build_plausibility_cumulative_meta(
            [],
            [("PT.1", pt1), ("PT.2.0", pt20)],
        )
        self.assertEqual(pt1, pt1_snapshot)
        self.assertEqual(pt20, pt20_snapshot)

    def test_helper_returns_new_dict_each_call(self) -> None:
        a = M._build_plausibility_cumulative_meta([], [])
        b = M._build_plausibility_cumulative_meta([], [])
        self.assertIsNot(a, b)
        # And same input -> equal output (determinism).
        self.assertEqual(a, b)

    def test_never_raises_on_pathological_inputs(self) -> None:
        for bad_rankings in (None, "not-a-list", 42, [None, "x", 0]):
            for bad_metas in (None, "not-a-list", 42, [None, "x"]):
                try:
                    env = M._build_plausibility_cumulative_meta(
                        bad_rankings,  # type: ignore[arg-type]
                        bad_metas,     # type: ignore[arg-type]
                    )
                except Exception as e:  # pragma: no cover
                    self.fail(f"helper raised on {bad_rankings!r}, {bad_metas!r}: {e!r}")
                self.assertEqual(set(env.keys()), REQUIRED_ENVELOPE_KEYS)

    def test_helper_handles_meta_with_missing_keys(self) -> None:
        env = M._build_plausibility_cumulative_meta(
            [],
            [("PT.1", {}), ("PT.2.0", {})],
        )
        self.assertEqual(set(env.keys()), REQUIRED_ENVELOPE_KEYS)
        self.assertEqual(env["modes_by_layer"], {"PT.1": "off", "PT.2.0": "off"})


# ===========================================================================
# 8. Pipeline integration — call-site wiring matches direct helper output
# ===========================================================================


class TestPipelineIntegration(unittest.TestCase):
    """Confirms the runtime call sites at main.py emit envelopes that match
    what the helper produces given the same `(rankings, layer_metas)`. We do
    not exercise the full pipeline; instead we invoke the two boost layers
    in the same composition order the pipeline uses, then build the envelope
    the way the call site does.
    """

    def test_off_off_pipeline_composition_emits_envelope(self) -> None:
        rankings = [
            {"route_id": "rA", "route_name": "A", "score": 0.60,
             "combined_score": 0.60, "route_score": 0.0, "route_length_ft": 1000.0},
            {"route_id": "rB", "route_name": "B", "score": 0.55,
             "combined_score": 0.55, "route_score": 0.0, "route_length_ft": 1000.0},
        ]
        group = {"group_idx": 0, "source_file": "syn.csv", "print_tokens": ["7"]}

        # Both flags OFF: helpers no-op, metas carry flag_off, identity passthrough.
        r1, pt1_meta = M._apply_print_to_sheet_plausibility_boost(rankings, group)
        r2, pt20_meta = M._apply_sheet_adjacency_plausibility_boost(r1, group)

        env = M._build_plausibility_cumulative_meta(
            r2,
            [("PT.1", pt1_meta), ("PT.2.0", pt20_meta)],
        )

        self.assertEqual(env["layers_applied"], [])
        self.assertEqual(env["modes_by_layer"], {"PT.1": "off", "PT.2.0": "off"})
        self.assertEqual(env["total_boost_delta_by_route_id"], {})
        self.assertEqual(env["max_total_delta"], 0.0)
        self.assertFalse(env["any_reorder_attempted"])
        self.assertFalse(env["any_reordered"])
        self.assertEqual(env["cap_governance"]["violations"], [])
        # Identity preserved through OFF/OFF path.
        self.assertIs(r2, rankings)

    def test_live_live_pipeline_envelope_is_consistent_with_helper(self) -> None:
        rankings = [
            {"route_id": "rA", "route_name": "A", "score": 0.60,
             "combined_score": 0.60, "route_score": 0.0, "route_length_ft": 1000.0},
            {"route_id": "rB", "route_name": "B", "score": 0.59,
             "combined_score": 0.59, "route_score": 0.0, "route_length_ft": 1000.0},
        ]
        group = {"group_idx": 0, "source_file": "syn.csv",
                 "print_tokens": ["7", "8", "9"]}

        # PT.1 boosts route_B with 3 tokens of evidence (3 * 0.01 = cap).
        # PT.2.0 also boosts route_B with full coverage (delta = cap).
        # Combined: route_B's combined_score 0.59 + 0.03 + 0.03 = 0.65 > 0.60.
        seam_pt1 = {"7": [42], "8": [43], "9": [44]}
        s2r_pt1 = {42: ["rB"], 43: ["rB"], 44: ["rB"]}
        seq_pt20 = {"rA": [201], "rB": [101, 102, 103]}
        seam_pt20 = {"7": [101, 102, 103]}

        with patch.dict(os.environ, {
            M._PRINT_TO_SHEET_BOOST_FLAG_ENV: "1",
            M._SHEET_ADJACENCY_BOOST_FLAG_ENV: "1",
        }), patch.object(M, "_print_to_sheets_from_packet_index",
                         side_effect=[seam_pt1, seam_pt20]), \
             patch.object(M, "_sheet_to_route_ids_from_packet_index",
                          return_value=s2r_pt1), \
             patch.object(M, "_route_sheet_sequence",
                          side_effect=lambda rid: seq_pt20.get(rid, [])):
            r1, pt1_meta = M._apply_print_to_sheet_plausibility_boost(rankings, group)
            r2, pt20_meta = M._apply_sheet_adjacency_plausibility_boost(r1, group)

        env = M._build_plausibility_cumulative_meta(
            r2,
            [("PT.1", pt1_meta), ("PT.2.0", pt20_meta)],
        )

        self.assertEqual(env["layers_applied"], ["PT.1", "PT.2.0"])
        self.assertEqual(env["modes_by_layer"], {"PT.1": "live", "PT.2.0": "live"})
        # route_B carries both deltas, summing to ~0.06.
        self.assertIn("rB", env["total_boost_delta_by_route_id"])
        self.assertAlmostEqual(env["total_boost_delta_by_route_id"]["rB"], 0.06, places=9)
        self.assertAlmostEqual(env["max_total_delta"], 0.06, places=9)
        # Reorder happened in at least one layer.
        self.assertTrue(env["any_reorder_attempted"])
        self.assertTrue(env["any_reordered"])
        # Cap governance clean — 0.06 is exactly the ceiling, not above.
        self.assertEqual(env["cap_governance"]["violations"], [])

    def test_envelope_built_from_diag_after_real_pipeline_assignment(self) -> None:
        # Simulates what the runtime call site does: write per-layer metas
        # into _diag, then build the envelope from the same composed inputs.
        rankings = [_ranking("rA", 0.60), _ranking("rB", 0.55)]
        group = {"group_idx": 0, "source_file": "syn.csv", "print_tokens": ["7"]}

        _diag: Dict[str, Any] = {}
        r1, pt1_meta = M._apply_print_to_sheet_plausibility_boost(rankings, group)
        _diag[M._PRINT_TO_SHEET_BOOST_DIAG_KEY] = pt1_meta
        r2, pt20_meta = M._apply_sheet_adjacency_plausibility_boost(r1, group)
        _diag[M._SHEET_ADJACENCY_BOOST_DIAG_KEY] = pt20_meta
        _diag[M._PLAUSIBILITY_CUMULATIVE_DIAG_KEY] = M._build_plausibility_cumulative_meta(
            r2,
            [("PT.1", pt1_meta), ("PT.2.0", pt20_meta)],
            step="post_ranking_boosts",
        )

        self.assertIn(M._PLAUSIBILITY_CUMULATIVE_DIAG_KEY, _diag)
        env = _diag[M._PLAUSIBILITY_CUMULATIVE_DIAG_KEY]
        self.assertEqual(env["generated_at_step"], "post_ranking_boosts")
        self.assertEqual(set(env.keys()), REQUIRED_ENVELOPE_KEYS)


# ===========================================================================
# 9. PT.ACT R3.f — schema v2: shadow aggregation
# ===========================================================================


REQUIRED_SHADOW_STACK_ENTRY_KEYS = {
    "layer", "pre_layer_top1", "post_layer_top1",
    "changed", "would_have_applied", "would_have_reordered",
}


def _shadow_block(
    *,
    computed: bool = True,
    would_have_applied: bool = False,
    would_have_top1: str = "",
    top1_unchanged_vs_actual: bool = True,
    would_have_reordered: bool = False,
    deltas: Dict[str, float] = None,
    error: Any = None,
    **extra: Any,
) -> Dict[str, Any]:
    block: Dict[str, Any] = {
        "computed":                          computed,
        "would_have_applied":                would_have_applied,
        "would_have_boosted_entries":        1 if would_have_applied else 0,
        "would_have_max_delta":              0.0,
        "would_have_top2_gap":               0.0,
        "would_have_reorder_attempted":      would_have_reordered,
        "would_have_reordered":              would_have_reordered,
        "would_have_reorder_blocked_reason": None,
        "would_have_top1_route_id":          would_have_top1,
        "top1_unchanged_vs_actual":          top1_unchanged_vs_actual,
        "would_have_delta_by_route_id":      dict(deltas or {}),
        "would_have_evidence":               {},
        "error":                             error,
    }
    block.update(extra)
    return block


def _meta_with_mode(meta_builder, *, mode: str, shadow: Any = None) -> Dict[str, Any]:
    """Augment a v1-style meta with a `mode` field and optional shadow block."""
    m = meta_builder(mode=mode)
    if shadow is not None:
        m["shadow"] = shadow
    return m


class TestEnvelopeV2Schema(unittest.TestCase):
    """R3.f — schema-v2 shadow aggregation tests. v1 fields stay byte-compat
    (covered by the existing test classes above); these tests focus on the
    8 new fields and the defensive parsing of `meta["shadow"]`.
    """

    def _pt1_off(self) -> Dict[str, Any]:
        return _pt1_meta()

    def _pt2_off(self) -> Dict[str, Any]:
        return _pt20_meta()

    def _pt1_shadow(self, **kwargs: Any) -> Dict[str, Any]:
        m = _pt1_meta(mode="shadow", applied=False, reason="shadow_mode")
        m["shadow"] = _shadow_block(**kwargs)
        return m

    def _pt2_shadow(self, **kwargs: Any) -> Dict[str, Any]:
        m = _pt20_meta(mode="shadow", applied=False, reason="shadow_mode")
        m["shadow"] = _shadow_block(**kwargs)
        return m

    # ── shadow_layers ──────────────────────────────────────────────────────
    def test_shadow_layers_lists_shadow_mode_layers(self) -> None:
        env = M._build_plausibility_cumulative_meta(
            [],
            [("PT.1", self._pt1_shadow()), ("PT.2.0", self._pt2_shadow())],
        )
        self.assertEqual(env["shadow_layers"], ["PT.1", "PT.2.0"])

    def test_shadow_layers_empty_when_no_shadow_mode(self) -> None:
        env = M._build_plausibility_cumulative_meta(
            [], [("PT.1", self._pt1_off()), ("PT.2.0", self._pt2_off())],
        )
        self.assertEqual(env["shadow_layers"], [])

    def test_shadow_layers_excludes_off_and_live_layers(self) -> None:
        live = _pt1_meta(mode="live", applied=True, reason=None)
        env = M._build_plausibility_cumulative_meta(
            [], [("PT.1", live), ("PT.2.0", self._pt2_shadow())],
        )
        self.assertEqual(env["shadow_layers"], ["PT.2.0"])

    # ── selection_impact_shadow_stack ──────────────────────────────────────
    def test_selection_impact_shadow_stack_includes_shadow_layers_only(self) -> None:
        rankings = [_ranking("rA", 0.6)]
        env = M._build_plausibility_cumulative_meta(
            rankings,
            [("PT.1", self._pt1_shadow(would_have_top1="rB",
                                       top1_unchanged_vs_actual=False)),
             ("PT.2.0", self._pt2_off())],
        )
        self.assertEqual(len(env["selection_impact_shadow_stack"]), 1)
        entry = env["selection_impact_shadow_stack"][0]
        self.assertEqual(set(entry.keys()), REQUIRED_SHADOW_STACK_ENTRY_KEYS)
        self.assertEqual(entry["layer"], "PT.1")
        self.assertEqual(entry["pre_layer_top1"], "rA")
        self.assertEqual(entry["post_layer_top1"], "rB")
        self.assertTrue(entry["changed"])

    def test_selection_impact_shadow_stack_preserves_registry_order(self) -> None:
        env = M._build_plausibility_cumulative_meta(
            [_ranking("rA", 0.6)],
            [("PT.1", self._pt1_shadow(would_have_top1="rA")),
             ("PT.2.0", self._pt2_shadow(would_have_top1="rB"))],
        )
        names = [e["layer"] for e in env["selection_impact_shadow_stack"]]
        self.assertEqual(names, ["PT.1", "PT.2.0"])

    # ── total_shadow_boost_delta_by_route_id ───────────────────────────────
    def test_total_shadow_boost_delta_aggregates_sum_across_shadow_layers(self) -> None:
        env = M._build_plausibility_cumulative_meta(
            [],
            [("PT.1", self._pt1_shadow(deltas={"rA": 0.02, "rB": 0.01})),
             ("PT.2.0", self._pt2_shadow(deltas={"rA": 0.03}))],
        )
        self.assertAlmostEqual(env["total_shadow_boost_delta_by_route_id"]["rA"],
                               0.05, places=9)
        self.assertAlmostEqual(env["total_shadow_boost_delta_by_route_id"]["rB"],
                               0.01, places=9)

    def test_total_shadow_boost_delta_empty_when_no_shadow(self) -> None:
        env = M._build_plausibility_cumulative_meta(
            [], [("PT.1", self._pt1_off()), ("PT.2.0", self._pt2_off())],
        )
        self.assertEqual(env["total_shadow_boost_delta_by_route_id"], {})
        self.assertEqual(env["max_total_shadow_delta"], 0.0)

    def test_max_total_shadow_delta_reflects_largest_sum(self) -> None:
        env = M._build_plausibility_cumulative_meta(
            [],
            [("PT.1", self._pt1_shadow(deltas={"rA": 0.02, "rB": 0.01})),
             ("PT.2.0", self._pt2_shadow(deltas={"rA": 0.03}))],
        )
        self.assertAlmostEqual(env["max_total_shadow_delta"], 0.05, places=9)

    # ── cross_layer_top1_agreement ─────────────────────────────────────────
    def test_cross_layer_top1_agreement_true_when_both_shadow_agree(self) -> None:
        env = M._build_plausibility_cumulative_meta(
            [],
            [("PT.1", self._pt1_shadow(would_have_top1="rZ")),
             ("PT.2.0", self._pt2_shadow(would_have_top1="rZ"))],
        )
        self.assertIs(env["cross_layer_top1_agreement"], True)

    def test_cross_layer_top1_agreement_false_when_disagree(self) -> None:
        env = M._build_plausibility_cumulative_meta(
            [],
            [("PT.1", self._pt1_shadow(would_have_top1="rA")),
             ("PT.2.0", self._pt2_shadow(would_have_top1="rB"))],
        )
        self.assertIs(env["cross_layer_top1_agreement"], False)

    def test_cross_layer_top1_agreement_none_with_one_shadow_layer(self) -> None:
        env = M._build_plausibility_cumulative_meta(
            [],
            [("PT.1", self._pt1_shadow(would_have_top1="rA")),
             ("PT.2.0", self._pt2_off())],
        )
        self.assertIsNone(env["cross_layer_top1_agreement"])

    def test_cross_layer_top1_agreement_none_when_one_shadow_errored(self) -> None:
        env = M._build_plausibility_cumulative_meta(
            [],
            [("PT.1", self._pt1_shadow(would_have_top1="rA")),
             ("PT.2.0", self._pt2_shadow(computed=False, error="RuntimeError"))],
        )
        self.assertIsNone(env["cross_layer_top1_agreement"])

    def test_cross_layer_top1_agreement_none_when_top1_empty(self) -> None:
        # both shadow blocks have empty would_have_top1_route_id -> < 2 candidates
        env = M._build_plausibility_cumulative_meta(
            [],
            [("PT.1", self._pt1_shadow(would_have_top1="")),
             ("PT.2.0", self._pt2_shadow(would_have_top1=""))],
        )
        self.assertIsNone(env["cross_layer_top1_agreement"])

    # ── any_* OR aggregations ──────────────────────────────────────────────
    def test_any_layer_shadow_error_true_when_one_layer_errored(self) -> None:
        env = M._build_plausibility_cumulative_meta(
            [],
            [("PT.1", self._pt1_shadow(computed=False, error="RuntimeError")),
             ("PT.2.0", self._pt2_shadow())],
        )
        self.assertTrue(env["any_layer_shadow_error"])

    def test_any_layer_shadow_error_false_when_no_errors(self) -> None:
        env = M._build_plausibility_cumulative_meta(
            [], [("PT.1", self._pt1_shadow()), ("PT.2.0", self._pt2_shadow())],
        )
        self.assertFalse(env["any_layer_shadow_error"])

    def test_any_would_have_changed_top1_oring(self) -> None:
        env = M._build_plausibility_cumulative_meta(
            [_ranking("rA", 0.6)],
            [("PT.1", self._pt1_shadow(would_have_top1="rB",
                                       top1_unchanged_vs_actual=False)),
             ("PT.2.0", self._pt2_shadow(would_have_top1="rA",
                                         top1_unchanged_vs_actual=True))],
        )
        self.assertTrue(env["any_would_have_changed_top1"])

    def test_any_would_have_changed_top1_false_when_all_unchanged(self) -> None:
        env = M._build_plausibility_cumulative_meta(
            [_ranking("rA", 0.6)],
            [("PT.1", self._pt1_shadow(would_have_top1="rA",
                                       top1_unchanged_vs_actual=True)),
             ("PT.2.0", self._pt2_shadow(would_have_top1="rA",
                                         top1_unchanged_vs_actual=True))],
        )
        self.assertFalse(env["any_would_have_changed_top1"])

    def test_any_shadow_layer_would_have_applied_oring(self) -> None:
        env = M._build_plausibility_cumulative_meta(
            [],
            [("PT.1", self._pt1_shadow(would_have_applied=True)),
             ("PT.2.0", self._pt2_shadow(would_have_applied=False))],
        )
        self.assertTrue(env["any_shadow_layer_would_have_applied"])

    def test_any_shadow_layer_would_have_applied_false_when_none_would_apply(self) -> None:
        env = M._build_plausibility_cumulative_meta(
            [],
            [("PT.1", self._pt1_shadow(would_have_applied=False)),
             ("PT.2.0", self._pt2_shadow(would_have_applied=False))],
        )
        self.assertFalse(env["any_shadow_layer_would_have_applied"])

    # ── v1 byte-compat (semantic preservation) ─────────────────────────────
    def test_v2_includes_all_v1_fields_with_unchanged_semantics_off_off(self) -> None:
        env = M._build_plausibility_cumulative_meta(
            [], [("PT.1", self._pt1_off()), ("PT.2.0", self._pt2_off())],
        )
        # v1 fields zero-state
        self.assertEqual(env["layers_present"], ["PT.1", "PT.2.0"])
        self.assertEqual(env["layers_applied"], [])
        self.assertEqual(env["modes_by_layer"], {"PT.1": "off", "PT.2.0": "off"})
        self.assertEqual(env["total_boost_delta_by_route_id"], {})
        self.assertEqual(env["max_total_delta"], 0.0)
        self.assertFalse(env["any_reorder_attempted"])
        self.assertFalse(env["any_reordered"])
        self.assertEqual(env["selection_impact_stack"], [])
        self.assertEqual(env["selection_changed_by_layers"], [])
        self.assertEqual(env["cap_governance"]["violations"], [])

    def test_v2_includes_all_v1_fields_with_unchanged_semantics_live_live(self) -> None:
        rankings = [_ranking("rA", 0.6, p2s_delta=0.02, sa_delta=0.03)]
        pt1_live = _pt1_meta(
            mode="live", applied=True, reason=None,
            selection_impact={"pre_layer_top1": "rA", "post_layer_top1": "rA",
                              "changed": False},
        )
        pt2_live = _pt20_meta(
            mode="live", applied=True, reason=None,
            selection_impact={"pre_layer_top1": "rA", "post_layer_top1": "rA",
                              "changed": False},
        )
        env = M._build_plausibility_cumulative_meta(
            rankings, [("PT.1", pt1_live), ("PT.2.0", pt2_live)],
        )
        self.assertEqual(env["layers_applied"], ["PT.1", "PT.2.0"])
        self.assertEqual(env["modes_by_layer"], {"PT.1": "live", "PT.2.0": "live"})
        self.assertAlmostEqual(env["total_boost_delta_by_route_id"]["rA"],
                               0.05, places=9)
        self.assertEqual(len(env["selection_impact_stack"]), 2)
        # v2-specific: no shadow data when nothing in shadow mode
        self.assertEqual(env["shadow_layers"], [])
        self.assertEqual(env["selection_impact_shadow_stack"], [])
        self.assertEqual(env["total_shadow_boost_delta_by_route_id"], {})
        self.assertIsNone(env["cross_layer_top1_agreement"])

    # ── mixed-mode (live + shadow) ─────────────────────────────────────────
    def test_mixed_live_shadow_separates_real_and_hypothetical(self) -> None:
        rankings = [_ranking("rA", 0.62, p2s_delta=0.02)]
        pt1_live = _pt1_meta(
            mode="live", applied=True, reason=None,
            selection_impact={"pre_layer_top1": "rA", "post_layer_top1": "rA",
                              "changed": False},
        )
        pt2_sh = self._pt2_shadow(would_have_applied=True, would_have_top1="rA",
                                   deltas={"rA": 0.03})
        env = M._build_plausibility_cumulative_meta(
            rankings, [("PT.1", pt1_live), ("PT.2.0", pt2_sh)],
        )
        # live counts in layers_applied, shadow in shadow_layers
        self.assertEqual(env["layers_applied"], ["PT.1"])
        self.assertEqual(env["shadow_layers"], ["PT.2.0"])
        # live stack has 1 entry (PT.1), shadow stack has 1 entry (PT.2.0)
        self.assertEqual(len(env["selection_impact_stack"]), 1)
        self.assertEqual(env["selection_impact_stack"][0]["layer"], "PT.1")
        self.assertEqual(len(env["selection_impact_shadow_stack"]), 1)
        self.assertEqual(env["selection_impact_shadow_stack"][0]["layer"], "PT.2.0")
        # live total + shadow total separate
        self.assertAlmostEqual(env["total_boost_delta_by_route_id"]["rA"],
                               0.02, places=9)
        self.assertAlmostEqual(env["total_shadow_boost_delta_by_route_id"]["rA"],
                               0.03, places=9)

    # ── defensive parsing ──────────────────────────────────────────────────
    def test_layer_with_missing_shadow_block_safely_handled(self) -> None:
        m = _pt1_meta(mode="shadow", reason="shadow_mode")
        # no shadow key
        env = M._build_plausibility_cumulative_meta(
            [], [("PT.1", m), ("PT.2.0", self._pt2_off())],
        )
        # mode is "shadow" so layer joins shadow_layers, but no shadow data
        self.assertEqual(env["shadow_layers"], ["PT.1"])
        self.assertEqual(env["selection_impact_shadow_stack"], [])
        self.assertFalse(env["any_layer_shadow_error"])

    def test_layer_with_non_dict_shadow_block_safely_handled(self) -> None:
        m = _pt1_meta(mode="shadow", reason="shadow_mode")
        m["shadow"] = "not-a-dict"
        env = M._build_plausibility_cumulative_meta(
            [], [("PT.1", m), ("PT.2.0", self._pt2_off())],
        )
        self.assertEqual(env["shadow_layers"], ["PT.1"])
        self.assertEqual(env["selection_impact_shadow_stack"], [])
        self.assertFalse(env["any_layer_shadow_error"])

    def test_shadow_computed_false_excluded_from_aggregation_but_error_counted(self) -> None:
        env = M._build_plausibility_cumulative_meta(
            [],
            [("PT.1", self._pt1_shadow(computed=False, error="RuntimeError",
                                       deltas={"rA": 0.10},
                                       would_have_top1="rZ")),
             ("PT.2.0", self._pt2_off())],
        )
        self.assertTrue(env["any_layer_shadow_error"])
        # computed=False -> no stack entry, no delta contribution
        self.assertEqual(env["selection_impact_shadow_stack"], [])
        self.assertEqual(env["total_shadow_boost_delta_by_route_id"], {})

    def test_non_numeric_shadow_deltas_coerced_to_zero(self) -> None:
        env = M._build_plausibility_cumulative_meta(
            [],
            [("PT.1", self._pt1_shadow(deltas={
                "rA": "0.02",   # str -> coerced
                "rB": True,     # bool -> skipped
                "rC": None,     # None -> skipped
                "rD": "nope",   # bad str -> skipped
            })),
             ("PT.2.0", self._pt2_off())],
        )
        self.assertAlmostEqual(env["total_shadow_boost_delta_by_route_id"]["rA"],
                               0.02, places=9)
        for bad in ("rB", "rC", "rD"):
            self.assertNotIn(bad, env["total_shadow_boost_delta_by_route_id"])

    def test_helper_never_raises_on_pathological_shadow_blocks(self) -> None:
        # totally malformed metas with various pathological shadow shapes
        cases: List[Any] = [
            [("PT.1", {}), ("PT.2.0", {})],
            [("PT.1", {"mode": "shadow", "shadow": None}),
             ("PT.2.0", {"mode": "shadow", "shadow": []})],
            [("PT.1", {"mode": "shadow", "shadow": {"computed": "yes"}}),
             ("PT.2.0", {"mode": "shadow", "shadow": {"computed": True}})],
        ]
        for layer_metas in cases:
            try:
                env = M._build_plausibility_cumulative_meta([], layer_metas)
            except Exception as e:  # pragma: no cover
                self.fail(f"helper raised on {layer_metas!r}: {e!r}")
            self.assertEqual(set(env.keys()), REQUIRED_ENVELOPE_KEYS)

    def test_helper_does_not_mutate_layer_metas_with_shadow(self) -> None:
        pt1 = self._pt1_shadow(would_have_top1="rB",
                                top1_unchanged_vs_actual=False,
                                deltas={"rA": 0.02})
        pt2 = self._pt2_shadow(would_have_top1="rB",
                                top1_unchanged_vs_actual=False,
                                deltas={"rA": 0.03})
        pt1_snap = copy.deepcopy(pt1)
        pt2_snap = copy.deepcopy(pt2)
        _ = M._build_plausibility_cumulative_meta(
            [_ranking("rA", 0.60)],
            [("PT.1", pt1), ("PT.2.0", pt2)],
        )
        self.assertEqual(pt1, pt1_snap)
        self.assertEqual(pt2, pt2_snap)


if __name__ == "__main__":
    unittest.main()
