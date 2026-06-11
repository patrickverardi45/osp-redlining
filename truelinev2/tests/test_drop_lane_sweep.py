"""M8.14.b.8 -- tests pinning the drop-lane sweep laws.

Locks: orientation-free chain connectivity (a vertical/north-south conduit
chains exactly like an east-west one -- the portability refusal case for the
old x-sorted assembly); a gap hole stops the chain; the classification
taxonomy never makes a refused candidate a placement (span-refused -> pick
card); end-unprinted dominates everything; ladder-band scale needs two
distinct stations."""
from __future__ import annotations

from truelinev2.extract.conduit_topology import (
    ORIGIN_AMBIGUOUS,
    ORIGIN_BOUND,
    ORIGIN_NOT_FOUND,
    bbox_gap,
    connected_chain,
)
from truelinev2.extract.structure_position import BRENHAM_CONDUIT_LAYERS
from truelinev2.proof.run_drop_lane_evidence_sweep import (
    C_BOUND,
    C_END_ONLY,
    C_PICK,
    C_UNPRINTED,
    classify_drop_bore,
    ladder_scale_for_band,
)
from truelinev2.extract.tick_path import Tick


def _seg(x0, y0, x1, y1):
    return {"layer": "L", "x0": x0, "y0": y0, "x1": x1, "y1": y1,
            "xc": (x0 + x1) / 2, "yc": (y0 + y1) / 2,
            "lines": [(x0, y0, x1, y1)]}


def test_connected_chain_is_orientation_free():
    """A NORTH-SOUTH dashed conduit chains exactly like an east-west one --
    the alternate-style case the x-sorted b.6 continuity could not assemble."""
    vertical = [_seg(100, 200 + i * 60, 102, 230 + i * 60) for i in range(4)]
    chain = connected_chain(vertical, (98.0, 170.0, 104.0, 200.0))
    assert len(chain) == 4
    horizontal = [_seg(200 + i * 60, 100, 230 + i * 60, 102) for i in range(4)]
    chain_h = connected_chain(horizontal, (170.0, 98.0, 200.0, 104.0))
    assert len(chain_h) == 4


def test_connected_chain_stops_at_a_hole():
    segs = [_seg(100, 100, 130, 102), _seg(160, 100, 190, 102),
            _seg(400, 100, 430, 102)]  # 210-pt hole before the third
    chain = connected_chain(segs, (90.0, 98.0, 100.0, 104.0))
    assert len(chain) == 2  # the far segment is NOT part of this conduit


def test_bbox_gap_zero_when_touching():
    assert bbox_gap(_seg(0, 0, 10, 2), _seg(10, 0, 20, 2)) == 0.0
    assert bbox_gap(_seg(0, 0, 10, 2), _seg(13, 6, 20, 8)) == 5.0


def test_classification_taxonomy_never_places_a_refused_candidate():
    assert classify_drop_bore(end_bound=False, origin_result=None,
                              span_consistent=None) == C_UNPRINTED
    assert classify_drop_bore(end_bound=True, origin_result=ORIGIN_NOT_FOUND,
                              span_consistent=None) == C_END_ONLY
    assert classify_drop_bore(end_bound=True, origin_result=ORIGIN_AMBIGUOUS,
                              span_consistent=None) == C_END_ONLY
    # the multi-drive trap: a REAL conduit candidate failing span -> pick card
    assert classify_drop_bore(end_bound=True, origin_result=ORIGIN_BOUND,
                              span_consistent=False) == C_PICK
    assert classify_drop_bore(end_bound=True, origin_result=ORIGIN_BOUND,
                              span_consistent=True) == C_BOUND


def test_ladder_scale_for_band_needs_two_stations():
    ticks = [Tick(200.0, 149.7, 347.7), Tick(300.0, 293.7, 347.3),
             Tick(400.0, 437.7, 347.0), Tick(999.0, 0.0, 900.0)]  # off-band
    s = ladder_scale_for_band(ticks, 320.0, 380.0)
    assert s is not None and abs(s - 1.44) < 0.01
    assert ladder_scale_for_band([Tick(200.0, 149.7, 347.7)], 320.0, 380.0) is None


def test_conduit_dialect_fact_lives_in_the_seam():
    assert BRENHAM_CONDUIT_LAYERS["VACANT HDPE"] == "BORE - VACANT PIPE"
