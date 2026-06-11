"""M8.14.b.7 -- tests pinning the log51 symbol-anchored stroke contract.

Locks: an anchor at station 0 seeds the unchanged solver and the stroke
starts EXACTLY on the anchor symbol; endpoint fidelity (tol 0.1) structurally
distinguishes the 3-pt co-located rival pot from the HH anchor -- the rival
can never silently become the start; interior stays the clean ladder."""
from __future__ import annotations

import math

from truelinev2.extract.tick_path import READY, Tick, solve_tick_path
from truelinev2.proof.run_symbol_anchored_stroke_proof import (
    stroke_endpoint_fidelity,
)

HH = (577.6, 354.2)
RIVAL_POT = (574.6, 354.3)
END_POT = (149.9, 343.3)
LADDER = [Tick(100.0, 436.0, 359.5), Tick(200.0, 292.0, 351.7)]


def _solve(start_anchor):
    anchors = [Tick(0.0, start_anchor[0], start_anchor[1]),
               Tick(299.0, END_POT[0], END_POT[1])]
    return solve_tick_path(bore_id="log51", sheet=8, start_ft=0.0, end_ft=299.0,
                           ticks=LADDER + anchors)


def test_zero_station_anchor_starts_stroke_on_symbol():
    v = _solve(HH)
    assert v.result == READY and v.strokes_found == 1
    assert v.stroke_points[0] == HH
    assert [p for p in v.stroke_points[1:-1]] == [(436.0, 359.5), (292.0, 351.7)]
    assert v.stroke_points[-1] == END_POT


def test_endpoint_fidelity_distinguishes_the_three_point_rival():
    v = _solve(HH)
    assert stroke_endpoint_fidelity(v, HH, END_POT)
    # the 3-pt-away rival pot is OUTSIDE the 0.1 fidelity tolerance: a stroke
    # anchored on the HH can never be claimed as pot-anchored, and vice versa
    assert not stroke_endpoint_fidelity(v, RIVAL_POT, END_POT)
    assert math.hypot(HH[0] - RIVAL_POT[0], HH[1] - RIVAL_POT[1]) > 0.1


def test_rival_anchored_solve_is_a_distinct_stroke():
    # anchoring on the rival pot yields a DIFFERENT stroke start -- the solver
    # never merges the co-located candidates into one answer
    v_pot = _solve(RIVAL_POT)
    assert v_pot.result == READY
    assert v_pot.stroke_points[0] == RIVAL_POT != HH
