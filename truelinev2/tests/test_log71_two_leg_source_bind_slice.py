"""OWNER-PACKET-2 log71 two sheet-local-leg source bind -- offline tests.

Locks the proof's pure laws: the result/blocker enum, the owner-reset START label derivation, the
ORIENTATION-AWARE corridor band (the END leg runs vertically, the START leg horizontally) and that
it feeds the reused log64 ``corridor_is_continuous`` law, that the 5+45 matchline stays ROUTE CONTEXT
(never a third endpoint), and that the slice consumes log71's encoded nextlink_hh -> flower_pot
identity. No PDF parse here (the proof runs the real sheet 24 + 23 binds at verification).
"""
from pathlib import Path

from truelinev2.ingest.manual_adjudication import load_adjudication
from truelinev2.proof.run_log64_sheet21_source_bind_slice import corridor_is_continuous
from truelinev2.proof.run_log71_two_leg_source_bind_slice import (
    ALLOWED,
    R_CONFIRMED,
    leg_corridor_band,
    start_label_text,
)


def test_result_enum_exact():
    assert ALLOWED == {
        "LOG71_TWO_LEG_SOURCE_BIND_CONFIRMED",
        "BLOCKED_LOG71_ENCODED_ANCHORS_MISSING",
        "BLOCKED_LOG71_END_FLOWER_POT_BIND_FAILED",
        "BLOCKED_LOG71_END_LEG_MATCHLINE_NOT_LOCATED",
        "BLOCKED_LOG71_START_NEXTLINK_HH_BIND_FAILED",
        "BLOCKED_LOG71_START_LEG_MATCHLINE_NOT_LOCATED",
        "BLOCKED_LOG71_ROUTE_NOT_SOURCE_BACKED",
    }
    assert R_CONFIRMED in ALLOWED


def test_start_label_is_owner_reset_token():
    # the bindable START label is the owner reset token '<station>=0+00' (Lawndale reset), not a bare
    # station -- the same shape log64 used for its installer-HH start.
    assert start_label_text({"station": "7+50"}) == "7+50=0+00"
    assert start_label_text({"station": "21+63"}) == "21+63=0+00"


def test_leg_corridor_band_vertical_axis():
    # the END leg runs vertically (flower pot below the 5+45 matchline): band by y, x off-corridor out
    term, ml = (200.0, 400.0), (203.0, 600.0)
    eps = [(201.0, 400.0), (201.0, 480.0), (260.0, 500.0), (202.0, 600.0)]
    band, lo, hi, axis = leg_corridor_band(eps, term, ml, half=40.0)
    assert axis == "y"
    assert (lo, hi) == (400.0, 600.0)
    assert band == [400.0, 480.0, 600.0]   # the off-centerline (260, 500) is excluded


def test_leg_corridor_band_horizontal_axis():
    # the START leg runs horizontally (nextlink HH far in x from the 5+45 matchline): band by x
    term, ml = (800.0, 300.0), (200.0, 320.0)
    eps = [(800.0, 310.0), (600.0, 312.0), (400.0, 380.0), (200.0, 308.0)]
    band, lo, hi, axis = leg_corridor_band(eps, term, ml, half=40.0)
    assert axis == "x"
    assert (lo, hi) == (200.0, 800.0)
    assert band == [200.0, 600.0, 800.0]   # the off-centerline (400, 380) is excluded


def test_leg_band_feeds_reused_log64_continuity_law():
    # leg_corridor_band produces a 1-D sorted band that the (axis-agnostic) log64 law judges directly
    good = [400.0, 430.0, 460.0, 490.0, 520.0]
    assert corridor_is_continuous(good, 400.0, 520.0) is True
    assert corridor_is_continuous([400.0, 470.0, 520.0], 400.0, 520.0) is False   # 70 > MAX_DASH_GAP
    assert corridor_is_continuous([400.0, 430.0, 460.0], 400.0, 520.0) is False   # never reaches hi


def test_matchline_5_45_is_route_context_not_endpoint():
    # log71 has exactly TWO true termini; 5+45 is the between-leg crossing, never a third anchor.
    doc = load_adjudication()
    l71 = next(r for r in doc["logs"] if r["log_id"] == "log71")
    ea = l71["endpoint_anchors"]
    assert set(ea) == {"start", "end"}                                  # no third anchor slot
    assert ea["start"]["station"] != "5+45" and ea["end"]["station"] != "5+45"
    assert "5+45" in ea["end"]["owner_note_text"].upper()               # preserved as route context


def test_slice_consumes_log71_encoded_identity():
    doc = load_adjudication()
    l71 = next(r for r in doc["logs"] if r["log_id"] == "log71")
    s = l71["endpoint_anchors"]["start"]
    e = l71["endpoint_anchors"]["end"]
    assert (s["structure_class"], s["station"]) == ("nextlink_hh", "7+50")
    assert (e["structure_class"], e["station"]) == ("flower_pot", "6+95")
    assert list(l71["corrected_sheets"]) == [23, 24]


def test_proof_has_no_render_lane():
    src = Path(__file__).resolve().parent.parent / "proof" / "run_log71_two_leg_source_bind_slice.py"
    text = src.read_text(encoding="utf-8")
    assert "from truelinev2.render" not in text
    assert "import truelinev2.render" not in text
    assert "render_redline_stroke" not in text
