"""M8.8 -- tests for the default-OFF station-axis interval opt-in wiring (no PDF).

Locks: flag defaults OFF; OFF/None byte-identical; ON places REVIEW only (never
AUTO) with reason STATION_AXIS_INTERVAL_PATH; ambiguity never overridden; placed
logs untouched; collision gate composes demote-only; footage-ambiguity rivals
never tiebroken; print-scope guard survives wiring; the solver re-home keeps the
M8.7 proof path importable."""
from __future__ import annotations

import dataclasses

from truelinev2.config import Settings
from truelinev2.match.engine import run_match
from truelinev2.match.frames import parse_frame_equations
from truelinev2.match.station_axis_interval import StationAxisContext
from truelinev2.schema.models import Bore, Callout, PlacementStatus
from truelinev2.stations import feet_to_station


def _c(sheet, f0, f1):
    return Callout(sheet=sheet, page=sheet, from_sta=feet_to_station(f0),
                   to_sta=feet_to_station(f1), from_ft=f0, to_ft=f1,
                   footage=round(f1 - f0, 2), text=f"s{sheet} {f0}->{f1}", dialect="test")


def _bore(s, e, sheets, span=None):
    return Bore(bore_id="logT", source_file="logT.xlsx", sheet_refs=list(sheets),
                station_start=feet_to_station(s), station_end=feet_to_station(e),
                station_start_ft=s, station_end_ft=e,
                span_ft=round((e - s) if span is None else span, 2))


class _StubDialect:
    name = "test"
    match_mode = "footage"

    def __init__(self, callouts):
        self._c = callouts

    def extract_callouts(self, plan, sheet, offset):
        return [c for c in self._c if c.sheet == sheet]


# the log15 shape: bore end is a tick interior to a larger interval; the start
# anchor never binds (no callout from_ft within 8 of 2407).
TICKS = {
    6: (2411.0, 2500.0, 2600.0, 2671.0),
    7: (2671.0, 2700.0, 2800.0, 2900.0, 3000.0, 3064.0),
    8: (3064.0, 3100.0, 3200.0, 3300.0, 3393.0),
}
INTERVALS = (_c(6, 2411, 2671), _c(7, 2671, 3064), _c(8, 3064, 3393))


def _ctx(ticks=TICKS, callouts=INTERVALS):
    return StationAxisContext(ticks_by_sheet=dict(ticks), callouts=tuple(callouts))


def test_flag_defaults_off_and_env_parsing(monkeypatch):
    assert Settings.for_proof().station_axis_interval_optin is False
    on = dataclasses.replace(Settings.for_proof(), station_axis_interval_optin=True)
    assert on.station_axis_interval_optin is True
    monkeypatch.setenv("TL2_STATION_AXIS_INTERVAL_OPTIN", "1")
    assert Settings.from_env().station_axis_interval_optin is True
    monkeypatch.delenv("TL2_STATION_AXIS_INTERVAL_OPTIN")
    assert Settings.from_env().station_axis_interval_optin is False


def test_engine_off_none_is_byte_identical_abstain():
    off = run_match(_bore(2407, 3100, [6, 7, 8]), None, _StubDialect(INTERVALS), 0)
    explicit = run_match(_bore(2407, 3100, [6, 7, 8]), None, _StubDialect(INTERVALS), 0,
                         station_axis=None)
    assert off.status is PlacementStatus.ABSTAIN
    assert off == explicit


def test_engine_axis_places_review_never_auto():
    pl = run_match(_bore(2407, 3100, [6, 7, 8]), None, _StubDialect(INTERVALS), 0,
                   station_axis=_ctx())
    assert pl.status is PlacementStatus.REVIEW
    assert pl.reason == "STATION_AXIS_INTERVAL_PATH"
    assert "STATION_AXIS_INTERVAL_PATH" in pl.caveats
    assert "NEVER_AUTO_BY_CONSTRUCTION" in pl.caveats
    assert pl.start_delta == 0.0 and pl.end_delta == 0.0
    assert pl.sheets == [6, 7, 8]


def test_engine_ambiguity_is_never_overridden():
    tie = [_c(1, 2407, 3100), _c(3, 2409, 3102)]
    pl = run_match(_bore(2407, 3100, [1, 3, 6, 7, 8]), None,
                   _StubDialect(list(INTERVALS) + tie), 0, station_axis=_ctx())
    assert pl.status is PlacementStatus.ABSTAIN
    assert pl.reason == "GE_2_COEQUAL_CANDIDATES_NO_TIEBREAKER"


def test_engine_existing_placements_untouched():
    raw = [_c(1, 0, 300), _c(2, 300, 500)]
    off = run_match(_bore(0, 500, [1, 2]), None, _StubDialect(raw), 0)
    on = run_match(_bore(0, 500, [1, 2]), None, _StubDialect(raw), 0, station_axis=_ctx())
    assert off.status is PlacementStatus.AUTO_SELECT
    assert on == off


def test_engine_print_scope_guard_survives_wiring():
    # whole proven path on sheet 21; print references 19/20 -> abstain.
    ticks = {21: (0.0, 161.0, 200.0, 300.0, 400.0, 446.0, 491.0)}
    cos = (_c(21, 0, 161), _c(21, 161, 491))
    pl = run_match(_bore(0, 446, [19, 20]), None, _StubDialect(cos), 0,
                   station_axis=_ctx(ticks, cos))
    assert pl.status is PlacementStatus.ABSTAIN


def test_engine_footage_ambiguity_not_tiebroken_by_axis():
    # fb declares two footage-coequal rivals; the axis winner IS one of them ->
    # abstain (span 693 -> review_foot 41.58; both decoys footage 700).
    decoys = [_c(8, 3064, 3393).model_copy(update={"footage": 700.0}),
              _c(9, 5000, 5700)]
    cos = (INTERVALS[0], INTERVALS[1], decoys[0], decoys[1])
    pl = run_match(_bore(2407, 3100, [6, 7, 8, 9], span=693), None,
                   _StubDialect(list(cos)), 0, station_axis=_ctx(TICKS, cos))
    assert pl.status is PlacementStatus.ABSTAIN


def test_engine_axis_passes_through_collision_gate():
    from truelinev2.match.collision_gate import CollisionGate
    gate_eqs = {7: tuple(parse_frame_equations(
        "MATCHLINE STA 30+64/1+00 - SEE SHEET 8 ................ "
        "MATCHLINE STA 30+64/1+05 - SEE SHEET 8")), 8: ()}
    gate = CollisionGate(equations_by_sheet=gate_eqs,
                         human_grades={"logT": "abstain_required"})
    pl = run_match(_bore(2407, 3100, [6, 7, 8]), None, _StubDialect(INTERVALS), 0,
                   station_axis=_ctx(), collision_gate=gate)
    assert pl.status is PlacementStatus.ABSTAIN
    assert "RESET_COLLISION_GATE" in pl.caveats


def test_m87_proof_import_path_still_works():
    from truelinev2.proof.station_axis_interval_containment import (
        READY, prove_interval_path)
    p = prove_interval_path(
        bore_id="logT", bore_start_ft=2407, bore_end_ft=3100, span_ft=693,
        ticks_by_sheet={k: list(v) for k, v in TICKS.items()},
        callouts=list(INTERVALS), sheet_refs=[6, 7, 8])
    assert p["result"] == READY
