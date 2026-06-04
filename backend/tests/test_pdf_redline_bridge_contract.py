"""Contract tests for the read-only PDF↔KMZ bridge candidate schema.

PDF-FREE / no main import / no rendering: exercises app.core.pdf_redline_bridge in isolation.
Proves the schema validates a well-formed candidate, rejects malformed / draw-carrying /
coordinate-carrying ones, enforces abstain-first safety, and that a candidate assembled from
the REAL MRQ pdf_first_evidence vocabulary (AP-# -> KMZ feature, geo_anchors -> structures)
carries the right join keys WITHOUT drawing anything.

COMMAND (from repo root):
    python -m pytest backend/tests/test_pdf_redline_bridge_contract.py -v
"""
from __future__ import annotations

from app.core import pdf_redline_bridge as B


def _candidate(**over):
    base = dict(
        session_id="sess-1", log_id="bore_log12", pdf_plan_id="plan-A",
        sheet=3, page=2, station_start="5+50", station_end="10+92",
        structure_start="AP-120", structure_end="AP-121",
        evidence_refs=["bore_log12_pathtrace_s3.png"],
        map_candidate_route_id="route-77", kmz_candidate_feature_id="120",
        confidence=0.0, created_from_flags=["TRUELINE_MATCHLINE_FRAME_RESOLVER"],
    )
    base.update(over)
    return B.make_bridge_candidate(**base)


def test_valid_candidate_validates():
    ok, errors = B.validate_bridge_candidate(_candidate())
    assert ok, errors


def test_all_required_fields_present():
    cand = _candidate()
    for f in B.REQUIRED_FIELDS:
        assert f in cand, f
    assert cand["schema_version"] == B.BRIDGE_SCHEMA_VERSION


def test_missing_required_field_fails():
    cand = _candidate()
    del cand["station_start"]
    ok, errors = B.validate_bridge_candidate(cand)
    assert not ok
    assert any("station_start" in e for e in errors)


def test_status_derivation():
    # No plan identity -> blocked.
    assert B.make_bridge_candidate(session_id="s", log_id="l", pdf_plan_id=None)["status"] == "blocked"
    # Identity + a world target -> candidate.
    c = B.make_bridge_candidate(session_id="s", log_id="l", pdf_plan_id="p",
                                kmz_candidate_feature_id="120")
    assert c["status"] == "candidate"
    # Identity but no world target -> abstain with a reason (no silent dangling join).
    a = B.make_bridge_candidate(session_id="s", log_id="l", pdf_plan_id="p")
    assert a["status"] == "abstain" and a["abstain_reason"]


def test_abstain_requires_reason_and_no_path():
    # Abstain WITHOUT a reason is invalid.
    bad = _candidate(status="abstain", abstain_reason=None, map_candidate_route_id=None,
                     kmz_candidate_feature_id=None)
    ok, errors = B.validate_bridge_candidate(bad)
    assert not ok and any("abstain_reason" in e for e in errors)

    # Abstain that still carries a drawn path is invalid (no fake diagonal at the bridge layer).
    faked = _candidate(status="abstain", abstain_reason="multiple_candidate_paths",
                       pdf_path_xy=[[1.0, 2.0], [3.0, 4.0]],
                       map_candidate_route_id=None, kmz_candidate_feature_id=None)
    ok2, errors2 = B.validate_bridge_candidate(faked)
    assert not ok2 and any("no fake path" in e for e in errors2)

    # A clean abstain (reason, empty path) validates.
    clean = _candidate(status="abstain", abstain_reason="named_matchline_not_bound",
                       pdf_path_xy=None, map_candidate_route_id=None,
                       kmz_candidate_feature_id=None)
    ok3, errors3 = B.validate_bridge_candidate(clean)
    assert ok3, errors3


def test_candidate_requires_a_world_target():
    bad = _candidate(status="candidate", map_candidate_route_id=None,
                     kmz_candidate_feature_id=None)
    ok, errors = B.validate_bridge_candidate(bad)
    assert not ok and any("requires map_candidate_route_id" in e for e in errors)


def test_world_coordinate_keys_are_forbidden():
    # Identity-join invariant (sidesteps the kmz_xref [lon,lat] vs render [lat,lon] inversion).
    for k in ("lat", "lonlat", "coords", "geometry", "segments"):
        cand = _candidate()
        cand[k] = [1, 2]
        ok, errors = B.validate_bridge_candidate(cand)
        assert not ok and any(k in e for e in errors), k


def test_confidence_range_enforced():
    ok, _ = B.validate_bridge_candidate(_candidate(confidence=0.5))
    assert ok
    bad, errors = B.validate_bridge_candidate(_candidate(confidence=1.5))
    assert not bad and any("confidence" in e for e in errors)


def test_built_from_real_mrq_vocabulary_maps_join_keys():
    """A pdf_first_evidence card (canonical field names) -> bridge candidate without drawing."""
    card = {
        "log_ids": ["bore_log12"], "print": "print3", "sheets": [3, 23],
        "station_range": {"start": "5+50", "end": "10+92"},
        "geo": {"geo_anchors": [
            {"kind": "AP", "id": "AP-120", "sta": "5+50", "chainage_ft": 550.0},
            {"kind": "AP", "id": "AP-121", "sta": "10+92", "chainage_ft": 1092.0},
        ]},
        "render_artifact_ref": ["bore_log12_card_s3.png"],
    }
    anchors = card["geo"]["geo_anchors"]
    cand = B.make_bridge_candidate(
        session_id="sess-1",
        log_id=card["log_ids"][0],
        pdf_plan_id="plan-A",
        sheet=card["sheets"][0],
        page=card["sheets"][0],
        station_start=card["station_range"]["start"],
        station_end=card["station_range"]["end"],
        structure_start=anchors[0]["id"],
        structure_end=anchors[-1]["id"],
        evidence_refs=card["render_artifact_ref"],
        # D5 identity join: PDF AP-120 -> KMZ TermPortHH feature "120" (normalize TYPE:number).
        kmz_candidate_feature_id=anchors[0]["id"].split("-")[-1],
        map_candidate_route_id="route-77",
        confidence=0.0,
        created_from_flags=["TRUELINE_PDF_FIRST_ENGINE", "TRUELINE_MATCHLINE_FRAME_RESOLVER"],
    )
    ok, errors = B.validate_bridge_candidate(cand)
    assert ok, errors
    assert cand["status"] == "candidate"
    assert cand["kmz_candidate_feature_id"] == "120"
    assert cand["structure_start"] == "AP-120" and cand["structure_end"] == "AP-121"
    assert cand["pdf_path_xy"] == []          # evidence-only; nothing drawn
