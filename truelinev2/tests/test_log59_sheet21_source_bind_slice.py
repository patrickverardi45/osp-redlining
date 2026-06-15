"""OWNER-PACKET-2 log59 sheet-21 source bind -- offline tests.

Locks the proof's pure laws + committed-data facts: the result/blocker enum (R_PARTIAL is a passing
confirm, like log64); the slice consumes log59's encoded installer_hh @2+76 -> flower_pot @4+46
identity; the start label is a PLAIN station '2+76' (non-reset, unlike log64's '3+69=0+00'); sheet 21
was SOURCE-RECOVERED and is now OWNER-CONFIRMED -> corrected_sheets == [21]; the
span is 170'; log36 stays un-anchored, log66 is now seam-promoted, log59 is now seam-promoted; and the proof reuses the
proven corridor laws (orientation-aware leg_corridor_band + axis-agnostic corridor_is_continuous) and
has no render lane. No PDF parse here (the proof runs the real sheet-21 bind at verification).
"""
from pathlib import Path

from truelinev2.ingest.manual_adjudication import load_adjudication
from truelinev2.proof.run_log59_sheet21_source_bind_slice import (
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
L59 = REC["log59"]


def test_result_enum_exact():
    assert ALLOWED == {
        "LOG59_SHEET21_SOURCE_BIND_CONFIRMED", "LOG59_PARTIAL_SOURCE_BIND_CONFIRMED",
        "BLOCKED_LOG59_ANCHORS_MISSING", "BLOCKED_LOG59_START_BIND_FAILED",
        "BLOCKED_LOG59_END_BIND_FAILED", "BLOCKED_LOG59_CONDUIT_SEED_NOT_FOUND",
        "BLOCKED_LOG59_ROUTE_NOT_SOURCE_BACKED", "BLOCKED_LOG59_SPAN_ANNOTATION_MISMATCH",
    }
    assert {R_CONFIRMED, R_PARTIAL} <= ALLOWED          # both are passing confirms (log64 precedent)
    assert SHEET == 21 and SPAN_FT == 170.0


def test_slice_consumes_log59_encoded_identity():
    s = L59["endpoint_anchors"]["start"]
    e = L59["endpoint_anchors"]["end"]
    assert (s["structure_class"], s["station"], s["boundary_kind"]) == ("installer_hh", "2+76", "structure_terminus")
    assert (e["structure_class"], e["station"], e["boundary_kind"]) == ("flower_pot", "4+46", "structure_terminus")


def test_start_label_is_a_plain_station_not_a_reset_token():
    # log59's start is NOT a reset (no STATION_RESET_SEGMENT_BOUNDARY) -> the bind label is the bare
    # station '2+76', not log64's reset token '<station>=0+00'
    assert "STATION_RESET_SEGMENT_BOUNDARY" not in (L59.get("correction_types") or [])
    assert L59["endpoint_anchors"]["start"]["station"] == "2+76"


def test_sheet21_source_recovered_then_owner_confirmed():
    assert L59["corrected_sheets"] == [21]               # owner-confirmed -> recorded
    for side in ("start", "end"):
        note = L59["endpoint_anchors"][side]["owner_note_text"].upper()
        assert "21" in note and "SOURCE-RECOVERED" in note and "OWNER-CONFIRMED" in note


def test_station_span_is_170():
    s, e = L59["endpoint_anchors"]["start"]["station"], L59["endpoint_anchors"]["end"]["station"]
    assert abs((parse_station(e) - parse_station(s)) - 170.0) <= 0.5


def test_log36_un_anchored_log66_promoted_log59_promoted():
    assert not REC["log36"].get("endpoint_anchors")
    assert REC["log66"].get("endpoint_anchors")        # log66 promoted into the seam (owner-confirmed sheet 10)
    assert tuple(ELIGIBLE_EXEMPLARS) == ("log53", "log64", "log71", "log59", "log66")
    build_seam_payload("log59", L59)                   # promoted -> builds
    build_seam_payload("log66", REC["log66"])          # promoted -> builds
    with pytest.raises(ValueError):
        build_seam_payload("log36", REC["log36"])      # log36 still un-anchored -> refused


def test_proof_reuses_proven_corridor_laws_and_has_no_render_lane():
    src = (Path(__file__).resolve().parent.parent / "proof" / "run_log59_sheet21_source_bind_slice.py").read_text(encoding="utf-8")
    # reuse, not reinvent: orientation-aware band (log71) + axis-agnostic continuity (log64)
    assert "from truelinev2.proof.run_log71_two_leg_source_bind_slice import leg_corridor_band" in src
    assert "corridor_is_continuous" in src
    # no render lane
    assert "from truelinev2.render" not in src
    assert "import truelinev2.render" not in src
    assert "render_redline_stroke" not in src
