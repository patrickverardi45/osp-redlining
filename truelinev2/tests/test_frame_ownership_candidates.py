"""M8.9 -- tests for frame-ownership classification (no PDF).

Locks the product-doctrine lanes and every zero-false gate: READY needs a unique
supported frame AND a unique in-frame route AND positive end evidence AND no
contesting rival AND no matchline-boundary end AND no banked human tie; frames
are never collapsed; suggestions are always labeled SUGGESTION_NOT_PLACEMENT;
source inconsistencies go to review; nothing here is wired into the engine."""
from __future__ import annotations

from truelinev2.match.frames import parse_frame_equations
from truelinev2.proof.frame_ownership_candidates import (
    ADJUSTABLE,
    PICK_CARD,
    READY,
    SOURCE_REVIEW,
    UNSAFE,
    VERDICTS,
    classify_frame_ownership,
)
from truelinev2.proof.station_equation_ownership import extract_reset_origins
from truelinev2.schema.models import Callout
from truelinev2.stations import feet_to_station


def _c(sheet, f0, f1):
    return Callout(sheet=sheet, page=sheet, from_sta=feet_to_station(f0),
                   to_sta=feet_to_station(f1), from_ft=f0, to_ft=f1,
                   footage=round(f1 - f0, 2), text=f"s{sheet} {f0}->{f1}", dialect="test")


def _classify(start, end, span, ticks, callouts, refs, origins=(), hh=None, eqs=None):
    return classify_frame_ownership(
        bore_id="logT", bore_start_ft=start, bore_end_ft=end, span_ft=span,
        ticks_by_sheet=ticks, callouts=callouts, origins=list(origins),
        hh_notes_by_sheet=hh or {}, sheet_refs=list(refs),
        equations_by_sheet=eqs)


# one clean local frame on sheet 10: ticks 0..450 incl. an end tick at 4+15,
# two contiguous intervals covering 0..450.
T10 = {10: [0, 100, 200, 300, 400, 415, 450]}
C10 = [_c(10, 0, 200), _c(10, 200, 450)]


def test_unique_frame_with_end_tick_is_ready():
    p = _classify(0, 415, 415, T10, C10, refs=[10])
    assert p["result"] == READY
    assert any("end_evidence" in e for e in p["evidence"])
    assert p["never_auto"] is True and p["review_gated_only"] is True


def test_origin_seeding_recorded_as_evidence():
    origins = extract_reset_origins(["STA 2+72=0+00", "INSTALLER HH"], sheet=10)
    p = _classify(0, 415, 415, T10, C10, refs=[10], origins=origins)
    assert p["result"] == READY
    assert "seeded_by_structure_origin" in p["evidence"]
    assert p["owned_frame"]["origin"]["origin_id"] == "sheet:10/reset@2+72"


def test_banked_human_tie_is_never_overridden():
    p = classify_frame_ownership(
        bore_id="log48", bore_start_ft=0, bore_end_ft=415, span_ft=415,
        ticks_by_sheet=T10, callouts=C10, origins=[], hh_notes_by_sheet={},
        sheet_refs=[10])
    assert p["result"] == PICK_CARD
    assert "banked_human_grade" in p
    assert p["label"] == "SUGGESTION_NOT_PLACEMENT"


def test_containment_only_end_is_suggestion_grade():
    # no tick and no callout end near the bore end (390): containment only.
    ticks = {10: [0, 100, 200, 300, 450]}
    p = _classify(0, 390, 390, ticks, C10, refs=[10])
    assert p["result"] == PICK_CARD
    assert "containment only" in p["named_missing_relationship"]


def test_rival_frame_with_end_evidence_contests():
    # sheet 11's frame holds a callout END 1 ft from the bore end but its
    # coverage is incomplete (the log71 lesson) -> contested pick-card.
    ticks = {10: [0, 100, 200, 300, 400, 415, 450], 11: [0, 100, 300, 416]}
    callouts = C10 + [_c(11, 300, 416)]
    p = _classify(0, 415, 415, ticks, callouts, refs=[10, 11])
    assert p["result"] == PICK_CARD
    assert "CONTESTED" in p["named_missing_relationship"]
    assert len(p["suggestions"]) >= 2


def test_matchline_boundary_end_is_suggestion_grade():
    eqs = {10: tuple(parse_frame_equations("MATCH LINE STA 4+15 / 0+10 - SEE SHEET 11"))}
    p = _classify(0, 415, 415, T10, C10, refs=[10], eqs=eqs)
    assert p["result"] == PICK_CARD
    assert "matchline/drive-boundary" in p["named_missing_relationship"]


def test_two_supported_frames_pick_card():
    ticks = {10: [0, 100, 200, 300, 400, 415, 450],
             12: [0, 100, 200, 300, 400, 415, 450]}
    callouts = C10 + [_c(12, 0, 200), _c(12, 200, 450)]
    p = _classify(0, 415, 415, ticks, callouts, refs=[10, 12])
    assert p["result"] == PICK_CARD
    assert len(p["suggestions"]) == 2
    assert all(s["label"] == "SUGGESTION_NOT_PLACEMENT" for s in p["suggestions"])


def test_multi_holding_route_in_one_frame_pick_cards():
    # two parallel intervals both hold the end (the log5 lesson).
    callouts = [_c(10, 0, 200), _c(10, 200, 450), _c(10, 205, 452)]
    p = _classify(0, 450, 450, T10, callouts, refs=[10])
    assert p["result"] == PICK_CARD


def test_uncovered_frames_yield_adjustable_redline():
    # candidate frames exist but none completes coverage: footage is still
    # certain -> human-adjustable length redline with the right footage.
    callouts = [_c(10, 300, 450)]  # nothing covers 0..300
    p = _classify(0, 415, 415, T10, callouts, refs=[10])
    assert p["result"] == ADJUSTABLE
    assert p["redline_object"]["footage_ft"] == 415
    assert p["label"] == "SUGGESTION_NOT_PLACEMENT"


def test_span_inconsistency_routes_to_source_review():
    p = _classify(100, 415, 200, T10, C10, refs=[10])
    assert p["result"] == SOURCE_REVIEW
    assert p["suspect_values"]["span_ft"] == 200


def test_no_candidates_is_unsafe_with_named_relationship():
    p = _classify(0, 9999, 9999, {10: [0, 100]}, [_c(10, 0, 100)], refs=[10])
    assert p["result"] == UNSAFE
    assert "never a guess" in p["named_missing_relationship"]


def test_verdicts_confined():
    cases = [
        _classify(0, 415, 415, T10, C10, refs=[10]),
        _classify(100, 415, 200, T10, C10, refs=[10]),
        _classify(0, 9999, 9999, {10: [0, 100]}, [_c(10, 0, 100)], refs=[10]),
    ]
    for p in cases:
        assert p["result"] in VERDICTS
        assert p["never_auto"] is True


def test_no_engine_wiring():
    import truelinev2.match.engine as eng
    assert not [m for m in dir(eng) if "ownership" in m.lower() or "frame_owner" in m.lower()]
