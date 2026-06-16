"""OWNER-PACKET-2 log36 endpoint-anchor bridge -- offline tests.

Locks the bridge's pure facts: log36's endpoint_anchors are schema-valid and identity-only
(installer_hh @ 0+56 -> installer_hh @ 1+45, both structure_terminus, no matchline = the log64 family,
installer-to-installer variant); the HH-HH=89' annotation + owner span_ft corroborate (both ends reset
to 0+00 in different frames, so NO cross-frame station arithmetic); sheet 17 is cited as SOURCE-RECOVERED
bridge evidence (NOT product promotion) and is kept OUT of corrected_sheets; the cohort classifier moves
log36 to SOURCE_BINDABLE_NOW (the explicit log36-limited delta); and log36 is NOT promoted to the seam
contract eligible set (it stays log53/log64/log71/log59/log66). No PDF parse here.
"""
from pathlib import Path

import pytest

from truelinev2.ingest.manual_adjudication import load_adjudication, validate_endpoint_anchors
from truelinev2.proof.run_log53_primitives_cohort_replay import SOURCE_BINDABLE_NOW, classify_record
from truelinev2.proof.run_log36_endpoint_anchor_bridge_slice import (
    ALLOWED,
    EXPECTED_ANCHOR_LOGS,
    R_ENCODED,
)
from truelinev2.seam import ELIGIBLE_EXEMPLARS, build_seam_payload

DOC = load_adjudication()
REC = {r["log_id"]: r for r in DOC["logs"]}
L36 = REC["log36"]


def test_result_enum():
    assert R_ENCODED == "LOG36_ENDPOINT_ANCHORS_ENCODED"
    assert R_ENCODED in ALLOWED


def test_log36_anchors_present_and_schema_valid():
    assert L36.get("endpoint_anchors")
    assert validate_endpoint_anchors(L36) == []
    assert set(L36["endpoint_anchors"]) == {"start", "end"}


def test_start_installer_hh_0_56():
    s = L36["endpoint_anchors"]["start"]
    assert (s["structure_class"], s["station"], s["boundary_kind"]) == ("installer_hh", "0+56", "structure_terminus")
    assert s["structure_label"] == "INSTALLER HH"


def test_end_installer_hh_1_45():
    e = L36["endpoint_anchors"]["end"]
    assert (e["structure_class"], e["station"], e["boundary_kind"]) == ("installer_hh", "1+45", "structure_terminus")
    assert e["structure_label"] == "INSTALLER HH"


def test_single_sheet_structure_to_structure_no_matchline():
    ea = L36["endpoint_anchors"]
    assert ea["start"]["boundary_kind"] == "structure_terminus"
    assert ea["end"]["boundary_kind"] == "structure_terminus"   # no matchline_continuation (log64 family)


def test_hh_hh_89_annotation_and_span_no_cross_frame_math():
    # both ends reset to 0+00 in DIFFERENT frames -> the 89' run is the owner annotation + span_ft,
    # NOT a station subtraction across frames
    assert "HH - HH = 89" in L36["evidence_notes"]
    assert abs(float(L36["span_ft"]) - 89.0) <= 0.5


def test_sheet_17_is_source_recovered_bridge_evidence_not_promoted():
    ea = L36["endpoint_anchors"]
    for side in ("start", "end"):
        note = ea[side]["owner_note_text"].upper()
        assert "17" in note and "SOURCE-RECOVERED" in note
    assert "NOT PRODUCT PROMOTION" in ea["start"]["owner_note_text"].upper()
    # sheet 17 is kept OUT of the owner-confirmed production field (bridge evidence only)
    assert L36["corrected_sheets"] == []


def test_anchors_carry_no_coordinate_fields():
    coord_keys = {"x", "y", "xy", "symbol_xy", "coord", "coords", "point", "points", "geometry"}
    for side in ("start", "end"):
        assert not (set(L36["endpoint_anchors"][side]) & coord_keys)


def test_cohort_delta_log36_source_bindable_now_limited():
    assert classify_record(L36)["classification"] == SOURCE_BINDABLE_NOW
    # the delta is limited to log36: exactly the six expected logs carry endpoint_anchors
    with_anchors = {r["log_id"] for r in DOC["logs"] if r.get("endpoint_anchors")}
    assert with_anchors == set(EXPECTED_ANCHOR_LOGS) == {
        "log36", "log52", "log53", "log58", "log59", "log64", "log66", "log71"}


def test_log36_not_promoted_to_seam_eligibility():
    # seam set unchanged at 5 (log66 already promoted in its own slice; log36 is bridged-but-held-back)
    assert tuple(ELIGIBLE_EXEMPLARS) == ("log53", "log64", "log71", "log59", "log66")
    with pytest.raises(ValueError):
        build_seam_payload("log36", L36)             # log36 anchored but NOT promoted -> refused


def test_bridge_proof_has_no_render_lane():
    src = Path(__file__).resolve().parent.parent / "proof" / "run_log36_endpoint_anchor_bridge_slice.py"
    text = src.read_text(encoding="utf-8")
    assert "from truelinev2.render" not in text
    assert "render_redline_stroke" not in text
