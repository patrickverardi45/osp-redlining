"""M8.14 -- tests pinning the clean-ladder tick-path solver (synthetic; no PDF).

Locks the abstain-first stroke contract: ladder ticks come ONLY from all-tick
/ no-alpha text blocks (callout/note station tokens are excluded and counted);
exactly one scale-consistent covering stroke -> READY; two distinct strokes ->
MULTIPLE_ROUTE_TICK_CHAINS with NO path; a span endpoint below the clean
ladder -> STRUCTURE_IDENTITY_BINDING_REQUIRED (structure-owned origins are
never guessed); uncovered spans -> ROUTE_TICK_LADDER_SPAN_NOT_COVERED; a
scale-drift hop is refused (cross-frame jump defense); endpoints interpolate
only between bracketing chain ticks; lead-in differences are ONE answer; the
renderer refuses to draw without a real path."""
from __future__ import annotations

import pytest

from truelinev2.extract.tick_path import (
    MULTIPLE,
    NOT_COVERED,
    READY,
    STRUCTURE_REQUIRED,
    Tick,
    ladder_ticks_from_words,
    solve_tick_path,
)


def _ladder(stations, origin=(100.0, 100.0), scale=1.3, bend=0.3):
    """Synthetic tick ladder along a gently bending path at a uniform pts/ft
    scale (x advances, y drifts by ``bend`` of the step)."""
    out, (x, y) = [], origin
    prev = stations[0]
    for s in stations:
        step = (s - prev) * scale
        x += step * (1 - bend)
        y += step * bend
        out.append(Tick(float(s), x, y))
        prev = s
    return out


def _solve(ticks, start=20.0, end=250.0, **kw):
    return solve_tick_path(bore_id="logT", sheet=9, start_ft=start, end_ft=end,
                           ticks=ticks, **kw)


# --- clean-tick classification ---------------------------------------------------------

def _word(text, block, x=0.0, y=0.0):
    return {"text": text, "xc": x, "yc": y, "block": block}


def test_all_tick_block_accepted_as_ladder():
    words = [_word("1+00", 5, 10, 50), _word("2+00", 5, 20, 50), _word("3+00", 5, 30, 50)]
    ticks, counts = ladder_ticks_from_words(words)
    assert [t.station_ft for t in ticks] == [100, 200, 300]
    assert counts == {"raw_tick_tokens": 3, "excluded_text_tokens": 0,
                      "clean_ladder_ticks": 3}


def test_callout_and_note_station_tokens_excluded():
    words = [
        # a DIR. BORE callout block -- its stations are TEXT, not ticks
        _word("STA", 1), _word("0+00", 1, 99, 99), _word("TO", 1),
        _word("STA", 1), _word("2+99", 1, 99, 99), _word("DIR.", 1), _word("BORE", 1),
        # a structure note block
        _word("STA", 2), _word("4+54", 2), _word("INSTALLER", 2), _word("HH", 2),
        # the drawn ladder
        _word("1+00", 3, 10, 50), _word("2+00", 3, 20, 50),
    ]
    ticks, counts = ladder_ticks_from_words(words)
    assert [t.station_ft for t in ticks] == [100, 200]
    assert counts == {"raw_tick_tokens": 5, "excluded_text_tokens": 3,
                      "clean_ladder_ticks": 2}


# --- the solver ------------------------------------------------------------------------

def test_unique_chain_ready_with_interpolated_endpoints():
    v = _solve(_ladder([0, 100, 200, 300]))
    assert v.result == READY and v.strokes_found == 1
    assert v.endpoint_type == "interpolated_from_tick_ladder"
    assert [t.station_ft for t in v.chain] == [0, 100, 200, 300]
    t0, t1 = v.chain[0], v.chain[1]
    assert min(t0.x, t1.x) < v.start_point[0] < max(t0.x, t1.x)
    t2, t3 = v.chain[2], v.chain[3]
    assert min(t2.x, t3.x) < v.end_point[0] < max(t2.x, t3.x)
    assert len(v.stroke_points) == 2 + 2  # start + interior(100,200) + end


def test_two_consistent_chains_abstain_no_path():
    a = _ladder([0, 100, 200, 300], origin=(100, 100))
    b = _ladder([0, 100, 200, 300], origin=(100, 600))  # parallel rival frame
    v = _solve(a + b)
    assert v.result == MULTIPLE
    assert v.strokes_found >= 2
    assert v.stroke_points is None and v.start_point is None
    assert v.endpoint_type == "abstained"
    assert "never tiebroken" in v.named_missing_relationship


def test_frame_doppelganger_origin_without_ladder_is_rejected():
    a = _ladder([0, 100, 200, 300])
    doppel = [Tick(0.0, 900.0, 900.0)]  # a rival 0+00 with NO following ladder
    v = _solve(a + doppel)
    assert v.result == READY and v.strokes_found == 1
    assert v.chain[0] == a[0]


def test_structure_owned_start_abstains_named():
    # ladder begins at 1+00: the bore's 0+20 start is a structure-owned origin
    v = _solve(_ladder([100, 200, 300, 400]), start=20, end=350)
    assert v.result == STRUCTURE_REQUIRED
    assert v.stroke_points is None
    assert "structure-identity binding" in v.named_missing_relationship
    assert "forbidden" in v.named_missing_relationship


def test_uncovered_span_abstains_named():
    v = _solve(_ladder([0, 100, 200]), start=50, end=450)
    assert v.result == NOT_COVERED
    assert v.stroke_points is None
    assert "does not span the bore" in v.named_missing_relationship


def test_scale_drift_hop_refused():
    a = _ladder([0, 100, 200])
    far = [Tick(300.0, a[-1].x + 520.0, a[-1].y)]  # 5.2 pts/ft vs ~1.3 median
    v = _solve(a + far, start=20, end=280)
    assert v.result == NOT_COVERED  # the cross-frame jump may not be taken


def test_lead_in_difference_is_one_answer():
    a = _ladder([0, 47, 100, 200, 300])
    v = _solve(a, start=55, end=250)
    assert v.result == READY and v.strokes_found == 1


def test_search_budget_exhaustion_abstains():
    v = _solve(_ladder([0, 100, 200, 300]), max_expansions=1)
    assert v.result == "TICK_PATH_SEARCH_EXHAUSTED"
    assert v.stroke_points is None


def test_renderer_refuses_without_real_path():
    from truelinev2.render.crop import render_redline_stroke
    assert render_redline_stroke(None, "logT", 9, 13, [], status="AUTO_SELECT",
                                 reason="X", out_dir="unused") is None
    assert render_redline_stroke(None, "logT", 9, 13, [(1.0, 2.0)],
                                 status="REVIEW", reason="X",
                                 out_dir="unused") is None
