"""Contract tests for the pure log_id/source_file -> route_id extractor.

PDF-FREE / no main import / no rendering / no file I/O. Proves data-only extraction from the MRQ
payload (matcher's selected_route_id), canonical log_id derivation, ambiguity, empty safety,
coordinate-blindness, and end-to-end feeding of the bridge builder's route_id_by_log WITHOUT
drawing.

COMMAND (from repo root):
    python -m pytest backend/tests/test_pdf_bridge_route_index.py -v
"""
from __future__ import annotations

from app.core import pdf_redline_bridge as B
from app.core import pdf_bridge_route_index as RI
from app.core import pdf_redline_bridge_builder as BB


def _payload(rows):
    return {"success": True, "rows": rows}


# ── extraction + canonical log_id ─────────────────────────────────────────────
def test_maps_both_log_id_and_source_file():
    idx = RI.extract_route_index(_payload([
        {"source_file": "bore_log56.xlsx", "selected_route_id": "route_123",
         "selected_route_name": "Main St", "group_id": "G1"},
    ]))
    assert set(idx) == {"bore_log56", "bore_log56.xlsx"}     # canonical log_id + source_file
    e = idx["bore_log56"]
    assert e["route_id"] == "route_123" and e["route_name"] == "Main St"
    assert e["source"] == "match_review_queue" and e["source_file"] == "bore_log56.xlsx"
    assert e["evidence_refs"] == ["group:G1"]
    assert idx["bore_log56.xlsx"]["route_id"] == "route_123"


def test_log_id_from_source_file_strips_extension_only():
    assert RI.log_id_from_source_file("bore_log56.xlsx") == "bore_log56"
    assert RI.log_id_from_source_file("Bore Log 56.xlsx") == "Bore Log 56"  # exact engine rule
    assert RI.log_id_from_source_file("no_ext") == "no_ext"


# ── duplicates / conflicts ────────────────────────────────────────────────────
def test_duplicate_same_route_is_ok():
    idx = RI.extract_route_index(_payload([
        {"source_file": "bore_log56.xlsx", "selected_route_id": "route_123", "group_id": "G1"},
        {"source_file": "bore_log56.xlsx", "selected_route_id": "route_123", "group_id": "G2"},
    ]))
    assert "ambiguous" not in idx["bore_log56"]
    assert idx["bore_log56"]["route_id"] == "route_123"


def test_conflicting_routes_are_ambiguous():
    idx = RI.extract_route_index(_payload([
        {"source_file": "bore_log56.xlsx", "selected_route_id": "route_123", "group_id": "G1"},
        {"source_file": "bore_log56.xlsx", "selected_route_id": "route_999", "group_id": "G2"},
    ]))
    for key in ("bore_log56", "bore_log56.xlsx"):
        assert idx[key].get("ambiguous") is True
        assert idx[key]["route_id"] is None
        assert key in idx[key]["ambiguous_reason"]


# ── missing / empty safety ────────────────────────────────────────────────────
def test_missing_route_id_yields_no_mapping():
    idx = RI.extract_route_index(_payload([
        {"source_file": "bore_log56.xlsx", "selected_route_id": None, "group_id": "G1"},   # abstained
        {"source_file": "", "selected_route_id": "route_x"},                                # no source
    ]))
    assert idx == {}


def test_empty_or_missing_payload():
    assert RI.extract_route_index(None) == {}
    assert RI.extract_route_index({}) == {}
    assert RI.extract_route_index({"rows": []}) == {}
    assert RI.extract_route_index([]) == {}                  # bare list accepted too


# ── coordinate-blindness ──────────────────────────────────────────────────────
def test_coordinates_do_not_affect_mapping():
    plain = [{"source_file": "bore_log56.xlsx", "selected_route_id": "route_123", "group_id": "G1"}]
    with_coords = [{"source_file": "bore_log56.xlsx", "selected_route_id": "route_123", "group_id": "G1",
                    "selected_route_geometry": [[30.1, -96.3], [30.2, -96.4]], "coord": [30.1, -96.3]}]
    assert RI.extract_route_index(_payload(plain)) == RI.extract_route_index(_payload(with_coords))


# ── projection to route_id_by_log ─────────────────────────────────────────────
def test_to_route_id_by_log_skips_ambiguous():
    idx = {
        "bore_log56": {"route_id": "route_123"},
        "bore_log56.xlsx": {"route_id": "route_123"},
        "bore_log99": {"route_id": None, "ambiguous": True},     # skipped
    }
    assert RI.to_route_id_by_log(idx) == {"bore_log56": "route_123", "bore_log56.xlsx": "route_123"}


# ── end-to-end: feeds the builder, no drawing ─────────────────────────────────
def test_feeds_builder_route_target_no_draw():
    route_by_log = RI.to_route_id_by_log(RI.extract_route_index(_payload([
        {"source_file": "bore_log56.xlsx", "selected_route_id": "route_123",
         "selected_route_name": "Main St", "group_id": "G1"},
    ])))
    evidence = {
        "source": {"plan_pdf": "Brenham.pdf"}, "placements": [], "fail_safe": [],
        "review_items": [{
            "log_ids": ["bore_log56"], "tier": "REVIEW", "surface": "review",
            "sheets": [17], "station_range": {"start": "0+00", "end": "2+76"},
            "geo": {"frame": {"page": 17}},     # NO geo_anchors -> route is the only world target
        }],
    }
    # Empty KMZ identity index -> no feature target; the route id makes it a candidate.
    c = BB.build_candidates_from_evidence(evidence, {}, session_id="s", pdf_plan_id="p",
                                          route_id_by_log=route_by_log)[0]
    assert c["status"] == "candidate"
    assert c["map_candidate_route_id"] == "route_123"
    assert c["kmz_candidate_feature_id"] is None
    ok, errors = B.validate_bridge_candidate(c)
    assert ok, errors
    assert c["pdf_path_xy"] == []               # draw-free
