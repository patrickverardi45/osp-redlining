"""OWNER-PACKET-2 log59 endpoint-anchor bridge -- offline tests.

Locks the bridge's pure facts: log59's endpoint_anchors are schema-valid and identity-only
(installer_hh @ 2+76 -> flower_pot @ 4+46, both structure_terminus, no matchline = the log64 shape);
the station span is 170'; sheet 21 is cited as SOURCE-RECOVERED bridge evidence (NOT product
promotion) and is kept OUT of corrected_sheets; the cohort classifier moves log59 to
SOURCE_BINDABLE_NOW (the explicit log59-limited delta); log66/log36 stay un-anchored; and log59 is
NOT promoted to the seam contract eligible set. No PDF parse here.
"""
from pathlib import Path

from truelinev2.ingest.manual_adjudication import load_adjudication, validate_endpoint_anchors
from truelinev2.proof.run_log53_primitives_cohort_replay import SOURCE_BINDABLE_NOW, classify_record
from truelinev2.proof.run_log59_endpoint_anchor_bridge_slice import ALLOWED, R_ENCODED
from truelinev2.seam import ELIGIBLE_EXEMPLARS, build_seam_payload
from truelinev2.stations import parse_station
import pytest

DOC = load_adjudication()
REC = {r["log_id"]: r for r in DOC["logs"]}
L59 = REC["log59"]


def test_result_enum():
    assert R_ENCODED == "LOG59_ENDPOINT_ANCHORS_ENCODED"
    assert R_ENCODED in ALLOWED


def test_log59_anchors_present_and_schema_valid():
    assert L59.get("endpoint_anchors")
    assert validate_endpoint_anchors(L59) == []
    assert set(L59["endpoint_anchors"]) == {"start", "end"}


def test_start_installer_hh_2_76():
    s = L59["endpoint_anchors"]["start"]
    assert (s["structure_class"], s["station"], s["boundary_kind"]) == ("installer_hh", "2+76", "structure_terminus")
    assert s["structure_label"] == "INSTALLER HH"


def test_end_flower_pot_4_46():
    e = L59["endpoint_anchors"]["end"]
    assert (e["structure_class"], e["station"], e["boundary_kind"]) == ("flower_pot", "4+46", "structure_terminus")
    assert e["structure_label"] == "FLOWER POT"


def test_single_sheet_structure_to_structure_no_matchline():
    ea = L59["endpoint_anchors"]
    assert ea["start"]["boundary_kind"] == "structure_terminus"
    assert ea["end"]["boundary_kind"] == "structure_terminus"   # no matchline_continuation (log64 shape)


def test_station_span_is_170():
    ea = L59["endpoint_anchors"]
    span = parse_station(ea["end"]["station"]) - parse_station(ea["start"]["station"])
    assert abs(span - 170.0) <= 0.5


def test_sheet_21_is_source_recovered_bridge_evidence_not_promoted():
    ea = L59["endpoint_anchors"]
    for side in ("start", "end"):
        note = ea[side]["owner_note_text"].upper()
        assert "21" in note and "SOURCE-RECOVERED" in note
    assert "NOT PRODUCT PROMOTION" in ea["start"]["owner_note_text"].upper()
    # sheet 21 is kept OUT of the owner-confirmed production field (bridge evidence only)
    assert L59["corrected_sheets"] == []


def test_anchors_carry_no_coordinate_fields():
    coord_keys = {"x", "y", "xy", "symbol_xy", "coord", "coords", "point", "points", "geometry"}
    for side in ("start", "end"):
        assert not (set(L59["endpoint_anchors"][side]) & coord_keys)


def test_cohort_delta_log59_source_bindable_now_only():
    assert classify_record(L59)["classification"] == SOURCE_BINDABLE_NOW
    # the delta is limited to log59: log66/log36 stay un-anchored (not source-bindable via a bridge)
    assert not REC["log66"].get("endpoint_anchors")
    assert not REC["log36"].get("endpoint_anchors")


def test_log59_not_promoted_to_seam_eligibility():
    assert tuple(ELIGIBLE_EXEMPLARS) == ("log53", "log64", "log71")   # seam set unchanged
    for lid in ("log59", "log66", "log36"):
        with pytest.raises(ValueError):
            build_seam_payload(lid, REC[lid])


def test_bridge_proof_has_no_render_lane():
    src = Path(__file__).resolve().parent.parent / "proof" / "run_log59_endpoint_anchor_bridge_slice.py"
    text = src.read_text(encoding="utf-8")
    assert "from truelinev2.render" not in text
    assert "render_redline_stroke" not in text
