"""PDF-first review-reason normalizer (Monday hardening — item 6).

PDF-free unit tests for ``match_review_queue.build_review_reason``. The helper is
additive + read-only: it summarizes an already-emitted PDF-first ``geo`` block
into an operator-facing review reason and NEVER changes any draw / abstain /
placement decision. These tests lock:
  - a cross-sheet ABSTAIN card yields a structured review_reason (code/missing/discriminators)
  - a DRAWN matchline card yields the evidence summary (station/matchline/BOC/physical anchor)
  - missing / partial / malformed geo never crashes
  - the helper never mutates its input (purity)
  - the existing legacy projection (assemble_match_review_queue) still works + carries no review_reason
"""
from __future__ import annotations

import copy

from backend.app.core.match_review_queue import (
    assemble_match_review_queue,
    build_review_reason,
)


def test_none_and_empty_geo_return_none():
    assert build_review_reason(None) is None
    assert build_review_reason("not a mapping") is None  # type: ignore[arg-type]
    assert build_review_reason(123) is None  # type: ignore[arg-type]
    assert build_review_reason({}) is None  # nothing informative -> key omitted


def test_cross_sheet_abstain_yields_structured_reason():
    geo = {
        "geometry_status": "FRAME_ONLY",
        "cross_sheet_seam_stitch": {
            "resolved": False,
            "reason": "authored_path_selector_required",
            "discriminators": [
                {"name": "run_color", "ok": True, "detail": "magenta duct isolated"},
                {"name": "named_matchline", "ok": False, "reason": "named_matchline_not_bound"},
            ],
            "segments": [
                {"sheet": 17, "status": "abstained_pending_evidence_fusion",
                 "reason": "multiple_candidate_paths_after_evidence_fusion"},
                {"sheet": 21, "status": "abstained_requires_path_evidence",
                 "reason": "s21_vectors_disconnected_no_authored_path"},
            ],
        },
    }
    rr = build_review_reason(geo)
    assert rr is not None
    assert rr["schema_version"] == "pdf-first-review-reason-1"
    assert rr["code"] == "abstained"
    assert "Missing" in rr["message"]
    joined = " ".join(rr["missing"])
    assert "multiple_candidate_paths_after_evidence_fusion" in joined
    assert "s21_vectors_disconnected_no_authored_path" in joined
    assert "authored_path_selector_required" in rr["missing"]
    names = {d["name"]: d["ok"] for d in rr["discriminators"]}
    assert names.get("run_color") is True
    assert names.get("named_matchline") is False


def test_drawn_matchline_card_yields_evidence_summary():
    geo = {
        "geometry_status": "MATCHLINE_FRAME_RESOLVED",
        "frame": {
            "chainage_start_ft": 0.0, "chainage_end_ft": 276.0, "axis": "x",
            "eqs_used": ["STA 4+57=0+00"], "multi_sheet": True,
        },
        "matchline_resolution": {
            "status": "MATCHLINE_FRAME_RESOLVED", "class": "matchline_pair",
            "sheets": [17, 21], "boc_ft": 11.0, "hh_hh_ft": 276.0,
        },
        "physical_anchor": {"resolved": True},
        "pdf_path_trace": {"artifact_name": "bore_log56_s17_seam_stitch.png"},
    }
    rr = build_review_reason(geo)
    assert rr is not None
    assert rr["code"] == "matchline_frame_resolved"
    assert "proven" in rr["message"].lower()
    assert rr["missing"] == []
    ev = rr["evidence"]
    assert ev["matchline"]["sheets"] == [17, 21]
    assert ev["boc_ft"] == 11.0
    assert ev["station_frame"]["eqs_used"] == ["STA 4+57=0+00"]
    assert ev["station_frame"]["chainage_end_ft"] == 276.0
    assert any(d["name"] == "physical_handhole_anchor" and d["ok"] for d in rr["discriminators"])
    assert any(d["name"] == "named_matchline" and d["ok"] for d in rr["discriminators"])


def test_physical_anchor_text_fallback_is_flagged():
    geo = {
        "geometry_status": "STATION_FRAME_RESOLVED",
        "physical_anchor": {"resolved": False, "reason": "ambiguous_multiple_structure_blobs"},
    }
    rr = build_review_reason(geo)
    assert rr is not None
    assert any(d["name"] == "physical_handhole_anchor" and d["ok"] is False
               for d in rr["discriminators"])
    assert "ambiguous_multiple_structure_blobs" in rr["missing"]


def test_partial_and_malformed_geo_never_crashes():
    weird = {
        "geometry_status": 12345,
        "frame": "nope",
        "matchline_resolution": ["nope"],
        "physical_anchor": None,
        "cross_sheet_seam_stitch": {"segments": ["x", 3, None], "discriminators": "nope"},
    }
    rr = build_review_reason(weird)  # must not raise
    assert rr is None or isinstance(rr, dict)


def test_helper_does_not_mutate_input():
    geo = {
        "geometry_status": "MATCHLINE_FRAME_RESOLVED",
        "matchline_resolution": {"status": "MATCHLINE_FRAME_RESOLVED", "sheets": [17, 21]},
        "physical_anchor": {"resolved": True},
    }
    before = copy.deepcopy(geo)
    build_review_reason(geo)
    assert geo == before  # pure: caller's geo is untouched


def test_legacy_assemble_unchanged_and_no_review_reason_on_rows():
    out = assemble_match_review_queue([
        {"source_file": "bore_log56.xlsx", "group_id": "g1", "stopped_at": "abstained_x",
         "render_allowed": False, "selected_route_id": ""},
    ])
    assert out["schema_version"] == "match-review-queue-1"
    assert out["row_count"] == 1
    row = out["rows"][0]
    assert row["status"] == "abstained"
    assert row["abstain_reason"] == "abstained_x"
    # review_reason is a pdf_first card field, NOT a matcher queue-row field.
    assert "review_reason" not in row
