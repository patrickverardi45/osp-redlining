"""GAC Sprint 1 — per-log redline PLACEMENT PROOF tests (core-only).

Locks the additive, read-only contract for `classify_placement` +
`assemble_placement_proof` in `app.core.match_review_queue`:

- `classify_placement` reads ONLY existing pipeline_diag `_diag` fields and
  resolves the evidence_source with the precedence
  pdf_ap_authoritative > abstained > print_index > geometry_fallback.
- `assemble_placement_proof` produces ONE row per source_file (no double-count
  when a log spans multiple print-groups), tallies counts_by_evidence_source,
  and — when given the rendered-geometry counts map — reconciles `totals` to the
  map (the GAC success condition: bore_log71/72 placed on route_477 via
  pdf_ap_authoritative, bore_log39 abstained, totals = 21 pts / 19 segs).
- Never mutates the input; never raises on bad input.

Pure projection — no env flag, no main.py, no real resolver mappings. The
`_diag` shapes below mirror the live write sites in main.py (checkpoint E/J).
"""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path
from typing import Any, Dict, List

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "backend"))

from backend.app.core.match_review_queue import (
    PLACEMENT_PROOF_SCHEMA_VERSION,
    assemble_placement_proof,
    classify_placement,
)


def _diag(
    source_file: str,
    *,
    selected_route_id: Any = None,
    render_allowed: Any = None,
    stopped_at: Any = None,
    strict_allowed: Any = None,
    pdf_ap_applied: bool = False,
    shadow_dist_ft: Any = None,
    abstain_reason: Any = None,
) -> Dict[str, Any]:
    """Build a minimal pipeline_diag entry with only the fields the classifier
    reads (mirrors the live `_diag` write sites)."""
    entry: Dict[str, Any] = {"source_file": source_file, "group_id": source_file + ":g"}
    if selected_route_id is not None:
        entry["selected_route_id"] = selected_route_id
    if render_allowed is not None:
        entry["render_allowed"] = render_allowed
    if stopped_at is not None:
        entry["stopped_at"] = stopped_at
    if strict_allowed is not None:
        entry["strict_allowed_route_ids"] = strict_allowed
    if abstain_reason is not None:
        entry["abstain_reason"] = abstain_reason
    if pdf_ap_applied:
        entry["pdf_ap_route_authoritative"] = {
            "applied": True,
            "selected_route_id": selected_route_id,
            "pdf_allowed_route_ids": [selected_route_id] if selected_route_id else [],
        }
    if shadow_dist_ft is not None:
        entry["pdf_ap_route_shadow"] = {
            "reason": "resolved_via_print_token_sheets",
            "nearest_routes": [{"route_id": selected_route_id, "dist_ft": shadow_dist_ft}],
        }
    return entry


class TestClassifyPlacement(unittest.TestCase):

    def test_pdf_ap_authoritative_with_dist(self):
        e = _diag("bore_log71.xlsx", selected_route_id="route_477", render_allowed=True,
                  strict_allowed=["route_477"], pdf_ap_applied=True, shadow_dist_ft=94.0)
        r = classify_placement(e)
        self.assertEqual(r["evidence_source"], "pdf_ap_authoritative")
        self.assertEqual(r["selected_route_id"], "route_477")
        self.assertEqual(r["dist_ft"], 94.0)
        self.assertIsNone(r["abstain_reason"])

    def test_pdf_ap_authoritative_wins_over_print_index_and_abstain(self):
        # Even if a stale abstain marker AND a strict allow-set are present, an
        # applied PDF-AP override is the highest-precedence signal.
        e = _diag("bore_log72.xlsx", selected_route_id="route_477", render_allowed=True,
                  stopped_at="abstained_location_evidence_mismatch",
                  strict_allowed=["route_478"], pdf_ap_applied=True)
        self.assertEqual(classify_placement(e)["evidence_source"], "pdf_ap_authoritative")

    def test_abstained_via_stopped_at(self):
        e = _diag("bore_log39.xlsx", render_allowed=False,
                  stopped_at="abstained_location_evidence_mismatch")
        r = classify_placement(e)
        self.assertEqual(r["evidence_source"], "abstained")
        self.assertIsNone(r["selected_route_id"])
        self.assertEqual(r["abstain_reason"], "abstained_location_evidence_mismatch")

    def test_abstained_via_no_rankings(self):
        e = _diag("x.xlsx", render_allowed=False, stopped_at="no_rankings_after_all_passes")
        self.assertEqual(classify_placement(e)["evidence_source"], "abstained")

    def test_abstained_render_blocked_no_route(self):
        e = _diag("x.xlsx", render_allowed=False)
        self.assertEqual(classify_placement(e)["evidence_source"], "abstained")

    def test_render_gate_blocked_is_not_abstain(self):
        # placed-but-not-rendered: a route was selected; classify by the index.
        e = _diag("x.xlsx", selected_route_id="route_1", render_allowed=False,
                  stopped_at="render_gate_blocked", strict_allowed=["route_1"])
        r = classify_placement(e)
        self.assertEqual(r["evidence_source"], "print_index")
        self.assertEqual(r["selected_route_id"], "route_1")

    def test_print_index(self):
        e = _diag("x.xlsx", selected_route_id="route_5", render_allowed=True,
                  strict_allowed=["route_5", "route_6"])
        self.assertEqual(classify_placement(e)["evidence_source"], "print_index")

    def test_geometry_fallback(self):
        e = _diag("x.xlsx", selected_route_id="route_9", render_allowed=True, strict_allowed=[])
        self.assertEqual(classify_placement(e)["evidence_source"], "geometry_fallback")

    def test_does_not_mutate_input(self):
        e = _diag("x.xlsx", selected_route_id="route_5", render_allowed=True,
                  strict_allowed=["route_5"])
        snap = copy.deepcopy(e)
        classify_placement(e)
        self.assertEqual(e, snap)


class TestAssemblePlacementProof(unittest.TestCase):

    def _ph5_diag(self) -> List[Dict[str, Any]]:
        return [
            _diag("bore_log71.xlsx", selected_route_id="route_477", render_allowed=True,
                  strict_allowed=["route_477"], pdf_ap_applied=True, shadow_dist_ft=94.0),
            _diag("bore_log72.xlsx", selected_route_id="route_477", render_allowed=True,
                  strict_allowed=["route_477"], pdf_ap_applied=True, shadow_dist_ft=94.0),
            _diag("bore_log39.xlsx", render_allowed=False,
                  stopped_at="abstained_location_evidence_mismatch"),
        ]

    def test_71_72_39_attribution_and_totals_reconcile(self):
        # The GAC success condition, proven at the projection level.
        counts = {
            "bore_log71.xlsx": {"station_pts": 10, "segs": 9},
            "bore_log72.xlsx": {"station_pts": 11, "segs": 10},
            "bore_log39.xlsx": {"station_pts": 0, "segs": 0},
        }
        out = assemble_placement_proof(self._ph5_diag(), counts_by_source=counts)
        self.assertEqual(out["schema_version"], PLACEMENT_PROOF_SCHEMA_VERSION)
        rows = {r["source_file"]: r for r in out["rows"]}

        self.assertEqual(rows["bore_log71.xlsx"]["evidence_source"], "pdf_ap_authoritative")
        self.assertEqual(rows["bore_log71.xlsx"]["selected_route_id"], "route_477")
        self.assertEqual(rows["bore_log72.xlsx"]["evidence_source"], "pdf_ap_authoritative")
        self.assertEqual(rows["bore_log72.xlsx"]["selected_route_id"], "route_477")
        self.assertEqual(rows["bore_log39.xlsx"]["evidence_source"], "abstained")
        self.assertIsNone(rows["bore_log39.xlsx"]["selected_route_id"])

        # 10+11 = 21 pts, 9+10 = 19 segs.
        self.assertEqual(out["totals"]["station_pts"], 21)
        self.assertEqual(out["totals"]["segs"], 19)
        self.assertEqual(out["totals"]["placed_logs"], 2)
        self.assertEqual(out["totals"]["abstained_logs"], 1)
        self.assertEqual(out["counts_by_evidence_source"]["pdf_ap_authoritative"], 2)
        self.assertEqual(out["counts_by_evidence_source"]["abstained"], 1)
        self.assertEqual(out["log_count"], 3)

    def test_multi_group_log_is_not_double_counted(self):
        # bore_log72 appears as TWO pipeline_diag groups; counts must apply once.
        diag = [
            _diag("bore_log72.xlsx", selected_route_id="route_477", render_allowed=True,
                  strict_allowed=["route_477"], pdf_ap_applied=True),
            _diag("bore_log72.xlsx", selected_route_id="route_477", render_allowed=True,
                  strict_allowed=["route_477"], pdf_ap_applied=True),
        ]
        counts = {"bore_log72.xlsx": {"station_pts": 11, "segs": 10}}
        out = assemble_placement_proof(diag, counts_by_source=counts)
        self.assertEqual(out["log_count"], 1)
        self.assertEqual(out["totals"]["station_pts"], 11)
        self.assertEqual(out["totals"]["segs"], 10)

    def test_multi_group_keeps_most_authoritative_classification(self):
        # one abstained group + one placed group for the same log -> placed wins.
        diag = [
            _diag("m.xlsx", render_allowed=False, stopped_at="no_anchored_hypotheses"),
            _diag("m.xlsx", selected_route_id="route_3", render_allowed=True,
                  strict_allowed=["route_3"]),
        ]
        out = assemble_placement_proof(diag, counts_by_source={"m.xlsx": {"station_pts": 4, "segs": 3}})
        self.assertEqual(out["log_count"], 1)
        self.assertEqual(out["rows"][0]["evidence_source"], "print_index")
        self.assertEqual(out["totals"]["placed_logs"], 1)
        self.assertEqual(out["totals"]["abstained_logs"], 0)

    def test_counts_none_yields_none_counts(self):
        out = assemble_placement_proof(self._ph5_diag())
        for r in out["rows"]:
            self.assertIsNone(r["station_pts"])
            self.assertIsNone(r["segs"])
        self.assertEqual(out["totals"]["station_pts"], 0)
        self.assertEqual(out["totals"]["segs"], 0)
        self.assertEqual(out["totals"]["placed_logs"], 2)
        self.assertEqual(out["totals"]["abstained_logs"], 1)

    def test_deterministic_sort_by_source_file(self):
        diag = [_diag("c.xlsx", selected_route_id="r", render_allowed=True, strict_allowed=["r"]),
                _diag("a.xlsx", selected_route_id="r", render_allowed=True, strict_allowed=["r"]),
                _diag("b.xlsx", selected_route_id="r", render_allowed=True, strict_allowed=["r"])]
        out = assemble_placement_proof(diag)
        self.assertEqual([r["source_file"] for r in out["rows"]], ["a.xlsx", "b.xlsx", "c.xlsx"])

    def test_bad_input_returns_empty(self):
        for bad in (None, 42, "x", {"not": "a list"}):
            out = assemble_placement_proof(bad)
            self.assertEqual(out["log_count"], 0)
            self.assertEqual(out["rows"], [])
            self.assertEqual(out["totals"]["station_pts"], 0)

    def test_does_not_mutate_input(self):
        diag = self._ph5_diag()
        snap = copy.deepcopy(diag)
        assemble_placement_proof(diag, counts_by_source={"bore_log71.xlsx": {"station_pts": 1, "segs": 1}})
        self.assertEqual(diag, snap)


if __name__ == "__main__":
    unittest.main()
