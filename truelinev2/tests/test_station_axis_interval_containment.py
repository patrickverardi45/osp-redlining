"""M8.7 -- tests for station-axis interval containment / path-walk (no PDF).

Locks: ticks cluster into per-frame ladders (never merged); sheet joins require a
shared NON-ROUND tick (round ticks repeat in every local frame -- coincidence);
rival frames containing the end value abstain; the end may be an axis tick or
interior to an authored interval; backward walk uses existing tolerances only;
off-print claims never READY; verdicts confined to the six; proof-only (no
engine import of this module)."""
from __future__ import annotations

from truelinev2.proof.station_axis_interval_containment import (
    DISCONTINUITY,
    FRAME_CONFLICT,
    READY,
    TICK_NOT_FOUND,
    VERDICTS,
    build_ladder,
    prove_interval_path,
    tick_clusters,
)
from truelinev2.schema.models import Callout
from truelinev2.stations import feet_to_station


def _c(sheet, f0, f1):
    return Callout(sheet=sheet, page=sheet, from_sta=feet_to_station(f0),
                   to_sta=feet_to_station(f1), from_ft=f0, to_ft=f1,
                   footage=round(f1 - f0, 2), text=f"s{sheet} {f0}->{f1}", dialect="test")


# the log15 shape: trunk ladder s6->s7->s8 with non-round shared boundary ticks,
# local clusters alongside, end 3100 as an s8 tick interior to 3064->3393.
TICKS = {
    6: [0, 100, 200, 2411, 2500, 2600, 2671],
    7: [0, 100, 200, 2671, 2700, 2800, 2900, 3000, 3064],
    8: [0, 100, 200, 3064, 3100, 3200, 3300, 3393],
}
INTERVALS = [_c(6, 2411, 2671), _c(7, 2671, 3064), _c(8, 3064, 3393),
             _c(6, 0, 200), _c(7, 0, 150)]


def _prove(start, end, span, ticks=None, callouts=None, refs=(6, 7, 8)):
    return prove_interval_path(
        bore_id="logT", bore_start_ft=start, bore_end_ft=end, span_ft=span,
        ticks_by_sheet=ticks or TICKS, callouts=callouts or INTERVALS,
        sheet_refs=list(refs))


def test_clusters_split_trunk_from_local_frames():
    cs = tick_clusters(TICKS[8], sheet=8)
    assert len(cs) == 2
    assert (cs[0].lo, cs[0].hi) == (0.0, 200.0)
    assert (cs[1].lo, cs[1].hi) == (3064.0, 3393.0)


def test_ladder_joins_only_on_shared_nonround_ticks():
    clusters = {s: tick_clusters(v, s) for s, v in TICKS.items()}
    ladder, joins = build_ladder(clusters, 3100.0, 2407.0)
    assert [c.sheet for c in ladder] == [6, 7, 8]
    assert all(j["shared_nonround_ticks"] for j in joins)
    # local clusters share ROUND ticks (0/100/200) across sheets -> never joined
    local_ladder, _ = build_ladder(clusters, 150.0, -500.0)
    assert len(local_ladder) == 1


def test_log15_shape_ready_with_containment_and_path_walk():
    p = _prove(2407, 3100, 693)
    assert p["result"] == READY
    assert p["end_axis_ticks"] == [(8, "31+00")]
    assert p["sheets_crossed"] == [6, 7, 8]
    assert p["computed_start_sta"] == "24+07"
    assert p["start_delta_vs_borelog_ft"] == 0.0
    assert p["never_auto"] is True and p["review_gated_only"] is True
    assert "STATION_AXIS_INTERVAL_PATH" in p["caveats"]


def test_rival_frame_containing_end_abstains():
    # a second sheet's LOCAL cluster spans the end value -> frame-ambiguous.
    ticks = dict(TICKS)
    ticks[9] = [3000, 3100, 3200]  # an unjoined rival ladder containing 3100
    p = _prove(2407, 3100, 693, ticks=ticks, refs=(6, 7, 8, 9))
    assert p["result"] == FRAME_CONFLICT
    assert p["rival_frames_containing_end"]
    assert "cannot pick a frame" in p["named_missing_relationship"]


def test_tick_not_found_names_relationship():
    p = _prove(0, 9990, 500, ticks={1: [0, 100, 200]}, callouts=[_c(1, 0, 200)], refs=(1,))
    assert p["result"] == TICK_NOT_FOUND
    assert "vision/crop" in p["named_missing_relationship"]


def test_discontinuity_when_no_nonround_join_exists():
    # the ladder cannot reach the computed start: sheets share only round ticks.
    ticks = {6: [0, 100, 2411, 2500], 8: [0, 100, 3064, 3100, 3393]}
    p = _prove(2407, 3100, 693, ticks=ticks, callouts=[_c(8, 3064, 3393)], refs=(6, 8))
    assert p["result"] == DISCONTINUITY
    assert "shares a boundary tick" in p["named_missing_relationship"]


def test_footage_gap_named():
    # ladder fine but a missing authored interval leaves a coverage hole.
    holes = [_c(8, 3064, 3393), _c(6, 2411, 2671)]  # s7 interval missing
    p = _prove(2407, 3100, 693, callouts=holes)
    assert p["result"] == "FOOTAGE_MISMATCH"
    assert "no authored interval behind it" in p["named_missing_relationship"]


def test_off_print_claim_never_ready():
    # whole path on sheet 21 while the print references 19/20 (the log69 shape).
    ticks = {21: [0, 161, 200, 300, 400, 446, 491]}
    p = prove_interval_path(bore_id="logT", bore_start_ft=0, bore_end_ft=446,
                            span_ft=446, ticks_by_sheet=ticks,
                            callouts=[_c(21, 0, 161), _c(21, 161, 491)],
                            sheet_refs=[19, 20])
    assert p["result"] == FRAME_CONFLICT
    assert "off-print" in p["named_missing_relationship"]


def test_round_end_value_in_single_frame_ok_interior_to_interval():
    # the log72 shape: round end 10+00 interior to 6+94->10+03, single frame.
    ticks = {24: [0, 100, 694, 700, 800, 900, 1000, 1003]}
    p = prove_interval_path(bore_id="logT", bore_start_ft=750, bore_end_ft=1000,
                            span_ft=250, ticks_by_sheet=ticks,
                            callouts=[_c(24, 694, 1003)], sheet_refs=[24])
    assert p["result"] == READY


def test_verdicts_confined_and_named():
    cases = [
        _prove(2407, 3100, 693),
        _prove(0, 9990, 500, ticks={1: [0, 100]}, callouts=[_c(1, 0, 200)], refs=(1,)),
        _prove(2407, 3100, 693, callouts=[_c(8, 3064, 3393), _c(6, 2411, 2671)]),
    ]
    for p in cases:
        assert p["result"] in VERDICTS
        if p["result"] != READY:
            assert p["named_missing_relationship"].strip()


def test_no_engine_wiring():
    import truelinev2.match.engine as eng
    assert not [m for m in dir(eng) if "interval" in m.lower() or "axis" in m.lower()]
