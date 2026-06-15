"""OWNER-PACKET-2 log66 sheet-10 source bind -- offline tests.

Locks the proof's pure laws + committed-data facts: the result/blocker enum (R_PARTIAL is a passing
confirm, like log59/log64); the slice consumes log66's encoded installer_hh @0+55 -> nextlink_hh @45+33
identity; the start label is a RESET token '0+55=0+00' (the log64 reset-start, unlike log59's plain
'2+76'); the end is a nextlink_hh that has NO BRENHAM_STRUCTURE_LAYERS entry (it binds ONLY via the
callout locator); sheet 10 was SOURCE-RECOVERED and is now OWNER-CONFIRMED -> corrected_sheets == [10];
the span is 55' from the owner annotation + span_ft (both ends reset to 0+00 in DIFFERENT frames, so a
station subtraction is WRONG); log36 is now anchored-but-held-back, log66 is PROMOTED into the seam (build_seam_payload
builds it), log59 stays seam-promoted; and the proof reuses the proven corridor laws and
has no render lane. No PDF parse here (the proof runs the real sheet-10 bind at verification).
"""
from pathlib import Path

from truelinev2.extract.structure_position import BRENHAM_STRUCTURE_LAYERS
from truelinev2.ingest.manual_adjudication import load_adjudication
from truelinev2.proof.run_log64_sheet21_source_bind_slice import start_label_text
from truelinev2.proof.run_log66_sheet10_source_bind_slice import (
    ALLOWED,
    R_CONFIRMED,
    R_PARTIAL,
    SHEET,
    SPAN_FT,
)
from truelinev2.seam import ELIGIBLE_EXEMPLARS, build_seam_payload
from truelinev2.stations import parse_station
import pytest

DOC = load_adjudication()
REC = {r["log_id"]: r for r in DOC["logs"]}
L66 = REC["log66"]


def test_result_enum_exact():
    assert ALLOWED == {
        "LOG66_SHEET10_SOURCE_BIND_CONFIRMED", "LOG66_PARTIAL_SOURCE_BIND_CONFIRMED",
        "BLOCKED_LOG66_ANCHORS_MISSING", "BLOCKED_LOG66_START_BIND_FAILED",
        "BLOCKED_LOG66_END_BIND_FAILED", "BLOCKED_LOG66_CONDUIT_SEED_NOT_FOUND",
        "BLOCKED_LOG66_ROUTE_NOT_SOURCE_BACKED", "BLOCKED_LOG66_SPAN_ANNOTATION_MISMATCH",
    }
    assert {R_CONFIRMED, R_PARTIAL} <= ALLOWED          # both are passing confirms (log59/log64 precedent)
    assert SHEET == 10 and SPAN_FT == 55.0


def test_slice_consumes_log66_encoded_identity():
    s = L66["endpoint_anchors"]["start"]
    e = L66["endpoint_anchors"]["end"]
    assert (s["structure_class"], s["station"], s["boundary_kind"]) == ("installer_hh", "0+55", "structure_terminus")
    assert (e["structure_class"], e["station"], e["boundary_kind"]) == ("nextlink_hh", "45+33", "structure_terminus")


def test_start_label_is_a_reset_token():
    # log66's start IS a reset (STATION_RESET_SEGMENT_BOUNDARY) -> the bind label is the reset token
    # '0+55=0+00' (the log64 reset-start shape), NOT log59's bare station
    assert "STATION_RESET_SEGMENT_BOUNDARY" in (L66.get("correction_types") or [])
    assert start_label_text(L66["endpoint_anchors"]["start"]) == "0+55=0+00"


def test_end_nextlink_hh_binds_only_via_callout_locator():
    # nextlink_hh has NO structure-layer entry -> resolve_structure_position cannot bind it; the END
    # must use the committed resolve_nextlink_hh_callout locator (log53/log71 precedent)
    assert L66["endpoint_anchors"]["end"]["structure_class"] == "nextlink_hh"
    assert "nextlink_hh" not in BRENHAM_STRUCTURE_LAYERS


def test_sheet10_source_recovered_then_owner_confirmed():
    assert L66["corrected_sheets"] == [10]               # owner-confirmed -> recorded
    for side in ("start", "end"):
        note = L66["endpoint_anchors"][side]["owner_note_text"].upper()
        assert "10" in note and "SOURCE-RECOVERED" in note and "OWNER-CONFIRMED" in note


def test_span_is_55_from_owner_evidence_not_cross_frame_math():
    # both ends reset to 0+00 in DIFFERENT frames -> the 55' run is the owner annotation + span_ft,
    # NOT a station subtraction (0+55 and 45+33 are not in one frame)
    assert abs(float(L66["span_ft"]) - 55.0) <= 0.5
    s, e = L66["endpoint_anchors"]["start"]["station"], L66["endpoint_anchors"]["end"]["station"]
    assert abs(parse_station(e) - parse_station(s)) != 55.0   # the naive cross-frame subtraction is WRONG


def test_log36_anchored_held_back_log66_promoted_log59_promoted():
    # log36 has since been bridged: anchored but held back (corrected_sheets [], NOT owner-confirmed)
    assert REC["log36"].get("endpoint_anchors") and REC["log36"]["corrected_sheets"] == []
    assert REC["log66"].get("endpoint_anchors") and REC["log66"]["corrected_sheets"] == [10]
    assert tuple(ELIGIBLE_EXEMPLARS) == ("log53", "log64", "log71", "log59", "log66")
    build_seam_payload("log59", REC["log59"])            # promoted -> builds
    build_seam_payload("log66", L66)                     # owner-confirmed + source-bound + rendered + promoted -> builds
    with pytest.raises(ValueError):
        build_seam_payload("log36", REC["log36"])        # log36 anchored-but-held-back -> refused


def test_proof_reuses_proven_corridor_laws_and_has_no_render_lane():
    src = (Path(__file__).resolve().parent.parent / "proof" / "run_log66_sheet10_source_bind_slice.py").read_text(encoding="utf-8")
    # reuse, not reinvent: orientation-aware band (log71) + axis-agnostic continuity (log64) + reset label (log64)
    assert "from truelinev2.proof.run_log71_two_leg_source_bind_slice import leg_corridor_band" in src
    assert "corridor_is_continuous" in src
    assert "start_label_text" in src
    # nextlink-callout locator for the END (nextlink_hh has no structure-layer entry)
    assert "resolve_nextlink_hh_callout" in src
    # no render lane
    assert "from truelinev2.render" not in src
    assert "import truelinev2.render" not in src
    assert "render_redline_stroke" not in src
