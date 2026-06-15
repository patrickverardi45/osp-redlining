"""OWNER-PACKET-2 log66 endpoint-anchor bridge -- offline tests.

Locks the bridge's pure facts: log66's endpoint_anchors are schema-valid and identity-only
(installer_hh @ 0+55 -> nextlink_hh @ 45+33, both structure_terminus, no matchline = the log64 family,
installer-to-nextlink variant); the HH-HH=55' annotation + owner span_ft corroborate (both ends reset
to 0+00 in different frames, so NO cross-frame station arithmetic); sheet 10 was SOURCE-RECOVERED and is
now OWNER-CONFIRMED (recorded in corrected_sheets=[10]); the cohort classifier moves log66 to
SOURCE_BINDABLE_NOW (the explicit log66-limited delta); log36 stays un-anchored; and log66 is still
NOT promoted to the seam contract eligible set (it stays log53/log64/log71/log59). No PDF parse here.
"""
from pathlib import Path

import pytest

from truelinev2.ingest.manual_adjudication import load_adjudication, validate_endpoint_anchors
from truelinev2.proof.run_log53_primitives_cohort_replay import SOURCE_BINDABLE_NOW, classify_record
from truelinev2.proof.run_log66_endpoint_anchor_bridge_slice import ALLOWED, R_ENCODED
from truelinev2.seam import ELIGIBLE_EXEMPLARS, build_seam_payload

DOC = load_adjudication()
REC = {r["log_id"]: r for r in DOC["logs"]}
L66 = REC["log66"]


def test_result_enum():
    assert R_ENCODED == "LOG66_ENDPOINT_ANCHORS_ENCODED"
    assert R_ENCODED in ALLOWED


def test_log66_anchors_present_and_schema_valid():
    assert L66.get("endpoint_anchors")
    assert validate_endpoint_anchors(L66) == []
    assert set(L66["endpoint_anchors"]) == {"start", "end"}


def test_start_installer_hh_0_55():
    s = L66["endpoint_anchors"]["start"]
    assert (s["structure_class"], s["station"], s["boundary_kind"]) == ("installer_hh", "0+55", "structure_terminus")
    assert s["structure_label"] == "INSTALLER HH"


def test_end_nextlink_hh_45_33():
    e = L66["endpoint_anchors"]["end"]
    assert (e["structure_class"], e["station"], e["boundary_kind"]) == ("nextlink_hh", "45+33", "structure_terminus")
    assert e["structure_label"] == "NEXTLINK HH"


def test_single_sheet_structure_to_structure_no_matchline():
    ea = L66["endpoint_anchors"]
    assert ea["start"]["boundary_kind"] == "structure_terminus"
    assert ea["end"]["boundary_kind"] == "structure_terminus"   # no matchline_continuation (log64 family)


def test_hh_hh_55_annotation_and_span_no_cross_frame_math():
    # both ends reset to 0+00 in DIFFERENT frames -> the 55' run is the owner annotation + span_ft,
    # NOT a station subtraction (0+55 and 45+33 are not in one frame)
    assert "HH - HH = 55" in L66["evidence_notes"]
    assert abs(float(L66["span_ft"]) - 55.0) <= 0.5


def test_sheet_10_source_recovered_then_owner_confirmed_held_back_from_seam():
    ea = L66["endpoint_anchors"]
    for side in ("start", "end"):
        note = ea[side]["owner_note_text"].upper()
        assert "10" in note and "SOURCE-RECOVERED" in note and "OWNER-CONFIRMED" in note
    # sheet 10 is now owner-confirmed -> recorded in corrected_sheets (still NOT seam-promoted)
    assert L66["corrected_sheets"] == [10]


def test_anchors_carry_no_coordinate_fields():
    coord_keys = {"x", "y", "xy", "symbol_xy", "coord", "coords", "point", "points", "geometry"}
    for side in ("start", "end"):
        assert not (set(L66["endpoint_anchors"][side]) & coord_keys)


def test_cohort_delta_log66_source_bindable_now_only():
    assert classify_record(L66)["classification"] == SOURCE_BINDABLE_NOW
    # the delta is limited to log66: log36 stays un-anchored (the remaining near-miss)
    assert not REC["log36"].get("endpoint_anchors")


def test_log66_not_promoted_to_seam_eligibility():
    assert tuple(ELIGIBLE_EXEMPLARS) == ("log53", "log64", "log71", "log59")   # seam set unchanged
    for lid in ("log66", "log36"):
        with pytest.raises(ValueError):
            build_seam_payload(lid, REC[lid])


def test_bridge_proof_has_no_render_lane():
    src = Path(__file__).resolve().parent.parent / "proof" / "run_log66_endpoint_anchor_bridge_slice.py"
    text = src.read_text(encoding="utf-8")
    assert "from truelinev2.render" not in text
    assert "render_redline_stroke" not in text
