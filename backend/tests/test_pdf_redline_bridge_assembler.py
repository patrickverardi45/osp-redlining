"""Contract tests for the pure PDF↔KMZ bridge candidate ASSEMBLER.

PDF-FREE / no main import / no rendering. Composes route-index + resolver + identity adapter +
builder; proves the review-only block shape, missing-input blockers, identity-index source
selection, no world-coordinate leakage, and that every emitted candidate validates.

COMMAND (from repo root):
    python -m pytest backend/tests/test_pdf_redline_bridge_assembler.py -v
"""
from __future__ import annotations

from app.core import pdf_redline_bridge as B
from app.core import pdf_redline_bridge_assembler as A

_WORLD_KEYS = ("lat", "lon", "lonlat", "coord", "coords", "geometry", "segments", "polyline")


def _evidence():
    return {
        "schema_version": "pdf-first-evidence-1", "status": "OK",
        "source": {"plan_pdf": "Brenham.pdf"},
        "placements": [], "fail_safe": [],
        "review_items": [{
            "log_ids": ["bore_log56"], "tier": "MATCHLINE_FRAME_RESOLVER", "surface": "review",
            "sheets": [17], "station_range": {"start": "0+00", "end": "2+76"},
            "geo": {"frame": {"page": 17},
                    "geo_anchors": [{"kind": "AP", "id": "AP-120", "coord": [254.0, 424.0]}]},
        }],
    }


def _render_payload():
    return {"points": [{"feature_id": "TX-AP120_pt", "name": "AP-120",
                        "classification": "terminal_port_handhole", "coord": [30.1, -96.3]}],
            "lines": [], "polygons": []}


def _mrq():
    return {"rows": [{"source_file": "bore_log56.xlsx", "selected_route_id": "route_123",
                      "selected_route_name": "Main St", "group_id": "G1"}]}


def _assert_no_world_keys(block):
    for c in block["candidates"]:
        for k in _WORLD_KEYS:
            assert k not in c, (k, c.get("log_id"))


def test_full_inputs_produce_validated_candidate():
    block = A.assemble_bridge_candidates(
        pdf_first_evidence=_evidence(), mrq_payload=_mrq(),
        kmz_render_payload=_render_payload(), kmz_xref=None,
        session_id="s", pdf_plan_id="plan-A")
    assert block["schema_version"] == "pdf-redline-bridge-candidates-1"
    assert block["identity_index"]["source"] == "render_only"
    assert len(block["candidates"]) == 1
    c = block["candidates"][0]
    assert c["status"] == "candidate"
    assert c["kmz_candidate_feature_id"] == "TX-AP120_pt"     # resolver-fed identity
    assert c["map_candidate_route_id"] == "route_123"          # route-index fed
    assert block["counts_by_status"].get("candidate") == 1
    ok, errs = B.validate_bridge_candidate(c)
    assert ok, errs
    _assert_no_world_keys(block)
    assert c["pdf_path_xy"] == []                              # draw-free


def test_missing_evidence_returns_empty_with_blocker():
    block = A.assemble_bridge_candidates(pdf_first_evidence={}, mrq_payload=_mrq(),
                                         kmz_render_payload=_render_payload(), session_id="s")
    assert block["candidates"] == []
    assert "no_pdf_first_evidence_cards" in block["blockers"]


def test_no_kmz_no_route_blockers_listed_no_crash():
    block = A.assemble_bridge_candidates(pdf_first_evidence=_evidence(), mrq_payload=None,
                                         kmz_render_payload=None, session_id="s", pdf_plan_id="p")
    assert block["identity_index"]["source"] == "none"
    for blk in ("no_kmz_render_features", "no_identity_index", "no_route_index"):
        assert blk in block["blockers"]
    assert block["counts_by_status"].get("abstain", 0) >= 1   # card present, no world target -> abstain
    _assert_no_world_keys(block)


def test_route_only_makes_candidate_without_kmz():
    block = A.assemble_bridge_candidates(pdf_first_evidence=_evidence(), mrq_payload=_mrq(),
                                         kmz_render_payload=None, session_id="s", pdf_plan_id="p")
    c = block["candidates"][0]
    assert c["status"] == "candidate"
    assert c["map_candidate_route_id"] == "route_123"
    assert c["kmz_candidate_feature_id"] is None


def test_ap_map_path_uses_kmz_xref_source():
    block = A.assemble_bridge_candidates(
        pdf_first_evidence=_evidence(), mrq_payload=_mrq(),
        kmz_render_payload=_render_payload(),
        kmz_xref={"ap_map": {"120": {"folder": "Terminal Port Handhole"}}},
        session_id="s", pdf_plan_id="p")
    assert block["identity_index"]["source"] == "kmz_xref+render"
    assert block["candidates"][0]["kmz_candidate_feature_id"] == "TX-AP120_pt"


def test_all_none_inputs_safe_empty_block():
    block = A.assemble_bridge_candidates(pdf_first_evidence=None, mrq_payload=None,
                                         kmz_render_payload=None, kmz_xref=None, session_id=None)
    assert block["candidates"] == []
    assert block["schema_version"] == "pdf-redline-bridge-candidates-1"
    assert "no_pdf_first_evidence_cards" in block["blockers"]


def test_inputs_diagnostics_counts():
    inp = A.assemble_bridge_candidates(
        pdf_first_evidence=_evidence(), mrq_payload=_mrq(),
        kmz_render_payload=_render_payload(), session_id="s", pdf_plan_id="p")["inputs"]
    assert inp["pdf_first_cards"] == 1
    assert inp["mrq_rows"] == 1
    assert inp["render_features"] == 1
    assert inp["ap_map_entries"] == 0
