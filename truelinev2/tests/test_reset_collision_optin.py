"""M8.2l -- tests for the default-OFF reset-collision gate wiring (no PDF needed).

Locks: flag defaults OFF everywhere; OFF (no gate) leaves the engine byte-identical;
ON demotes ONLY a runtime-detected on-crossing collision per the banked human grade
(log42-style -> REVIEW, log65-style -> ABSTAIN, log57-style precision -> REVIEW);
non-collision chains and sub-AUTO statuses are untouched; nothing is ever promoted.
"""
from __future__ import annotations

import dataclasses

from truelinev2.config import Settings
from truelinev2.match.collision_gate import CollisionGate, load_human_grades
from truelinev2.match.engine import run_match
from truelinev2.match.frames import parse_frame_equations
from truelinev2.schema.models import Bore, Callout, Placement, PlacementStatus
from truelinev2.stations import feet_to_station


def _c(sheet: int, f0: float, f1: float) -> Callout:
    return Callout(sheet=sheet, page=sheet, from_sta=feet_to_station(f0), to_sta=feet_to_station(f1),
                   from_ft=f0, to_ft=f1, footage=round(f1 - f0, 2), text="x", dialect="test")


def _placed(chain, status=PlacementStatus.AUTO_SELECT) -> Placement:
    return Placement(bore_id="log42", status=status, tier="AUTO_SELECT",
                     reason="EXACT_BOX_FOOTAGE_AND_ENDPOINTS",
                     sheets=sorted({c.sheet for c in chain}),
                     footage=sum(c.footage for c in chain), footage_delta=0.0,
                     start_delta=0.0, end_delta=0.0, matched_callouts=list(chain))


# A log42-shaped collision: chain s2[0+00->2+70] -> s1[2+70->2+87]; the matchline
# equation STA 2+70/5+16 (SEE SHEET 1) references the crossing 2+70; the far-side
# continuation s1[5+16->7+40] exists among the extracted callouts.
_CHAIN = [_c(2, 0, 270), _c(1, 270, 287)]
_FAR = _c(1, 516, 740)
_EQS = {2: tuple(parse_frame_equations("MATCH LINE STA 2+70/5+16 - SEE SHEET 1")), 1: ()}


def _gate(grades=None, eqs=None) -> CollisionGate:
    return CollisionGate(equations_by_sheet=(eqs or _EQS), human_grades=grades or {})


# --- flag defaults ------------------------------------------------------------

def test_flag_defaults_off():
    assert Settings.for_proof().reset_collision_optin is False
    on = dataclasses.replace(Settings.for_proof(), reset_collision_optin=True)
    assert on.reset_collision_optin is True


def test_ledger_loader_missing_file_is_empty():
    assert load_human_grades(Settings.for_proof().db_path / "nope.json") == {}


# --- gate behavior --------------------------------------------------------------

def test_graded_reset_demotes_auto_to_review():
    pl = _gate({"log42": "reset_equation_confirmed"}).apply(_placed(_CHAIN), _CHAIN + [_FAR])
    assert pl.status is PlacementStatus.REVIEW
    assert "RESET_COLLISION_GATE" in pl.caveats


def test_graded_abstain_demotes_auto_to_abstain():
    pl = _gate({"log42": "abstain_required"}).apply(_placed(_CHAIN), _CHAIN + [_FAR])
    assert pl.status is PlacementStatus.ABSTAIN
    assert pl.abstain_reason


def test_ungraded_collision_demotes_to_review_only():
    # R4: continuous never silently wins, but without human evidence the demotion
    # floor is REVIEW, never ABSTAIN/AUTO.
    pl = _gate({}).apply(_placed(_CHAIN), _CHAIN + [_FAR])
    assert pl.status is PlacementStatus.REVIEW


def test_human_continuous_confirmed_leaves_placement_unchanged():
    before = _placed(_CHAIN)
    after = _gate({"log42": "continuous_station_confirmed"}).apply(before, _CHAIN + [_FAR])
    assert after == before


def test_no_on_crossing_equation_means_untouched():
    # equation references OTHER stations -> not this crossing -> no collision
    eqs = {2: tuple(parse_frame_equations("MATCH LINE STA 9+99/5+16 - SEE SHEET 1")), 1: ()}
    before = _placed(_CHAIN)
    assert _gate({"log42": "abstain_required"}, eqs).apply(before, _CHAIN) == before


def test_same_sheet_chain_untouched():
    chain = [_c(3, 0, 100), _c(3, 100, 200)]
    before = _placed(chain)
    assert _gate({"log42": "abstain_required"}).apply(before, chain) == before


def test_precision_conflict_detected_at_runtime():
    # log57-shaped: two readings of one matchline sharing the 3+08 side, 5 ft apart
    text = ("MATCHLINE STA 3+98/3+08 - SEE SHEET 13 ........................ "
            "MATCHLINE STA 3+93/3+08 - SEE SHEET 13")
    eqs = {8: tuple(parse_frame_equations(text)), 13: ()}
    chain = [_c(13, 162, 398), _c(8, 398, 413)]
    pl = _gate({}, eqs).apply(_placed(chain), chain)
    assert pl.status is PlacementStatus.REVIEW
    assert "PRECISION_CONFLICT_MANUAL_REVIEW" in pl.caveats


# --- never promote ----------------------------------------------------------------

def test_abstain_and_review_never_promoted():
    abstain = Placement(bore_id="log42", status=PlacementStatus.ABSTAIN, tier="FAIL_SAFE",
                        reason="X", matched_callouts=list(_CHAIN))
    assert _gate({"log42": "reset_equation_confirmed"}).apply(abstain, _CHAIN).status \
        is PlacementStatus.ABSTAIN
    review = _placed(_CHAIN, status=PlacementStatus.REVIEW)
    out = _gate({"log42": "reset_equation_confirmed"}).apply(review, _CHAIN + [_FAR])
    assert out.status is PlacementStatus.REVIEW  # stays REVIEW, never AUTO


# --- engine wiring ------------------------------------------------------------------

class _StubDialect:
    name = "test"
    match_mode = "footage"

    def __init__(self, callouts):
        self._c = callouts

    def extract_callouts(self, plan, sheet, offset):
        return [c for c in self._c if c.sheet == sheet]


def _bore(start_ft, end_ft, sheets) -> Bore:
    return Bore(bore_id="logT", source_file="logT.xlsx", sheet_refs=list(sheets),
                station_start=feet_to_station(start_ft), station_end=feet_to_station(end_ft),
                station_start_ft=start_ft, station_end_ft=end_ft,
                span_ft=round(end_ft - start_ft, 2))


def test_engine_without_gate_unchanged_auto():
    pl = run_match(_bore(0, 287, [2, 1]), None, _StubDialect(_CHAIN + [_FAR]), 0)
    assert pl.status is PlacementStatus.AUTO_SELECT  # default path: byte-identical


def test_engine_with_gate_demotes_collision_only():
    bore = _bore(0, 287, [2, 1])
    bore = bore.model_copy(update={"bore_id": "log42"})
    pl = run_match(bore, None, _StubDialect(_CHAIN + [_FAR]), 0,
                   collision_gate=_gate({"log42": "reset_equation_confirmed"}))
    assert pl.status is PlacementStatus.REVIEW
    assert "RESET_COLLISION_GATE" in pl.caveats
