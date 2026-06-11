"""M8.14.b.6 -- tests pinning the origin-conduit topology discriminator.

Locks the drawn-containment law: footprints are union bboxes of cluster
members; a chain must be continuous (bounded dash gaps); the origin binds iff
conduit dash endpoints land inside EXACTLY ONE candidate footprint -- zero ->
not found, two -> ambiguous; never a nearest-distance comparison."""
from __future__ import annotations

from truelinev2.proof.run_origin_conduit_topology_probe import (
    BRENHAM_CONDUIT_LAYERS,
    ORIGIN_AMBIGUOUS,
    ORIGIN_BOUND,
    ORIGIN_NOT_FOUND,
    chain_continuity,
    dash_endpoints,
    discriminate_origin,
    symbol_footprint,
)


def _seg(x0, y0, x1, y1, layer="BORE - VACANT PIPE"):
    return {"layer": layer, "x0": x0, "y0": y0, "x1": x1, "y1": y1,
            "xc": (x0 + x1) / 2, "yc": (y0 + y1) / 2,
            "lines": [(x0, y0, x1, y1)]}


def test_symbol_footprint_unions_cluster_members():
    drawings = [_seg(576.4, 351.7, 578.0, 356.8, layer="NEXTLINK"),
                _seg(577.0, 352.0, 579.6, 355.0, layer="NEXTLINK"),
                _seg(900.0, 900.0, 905.0, 905.0, layer="NEXTLINK")]
    bb = symbol_footprint(drawings, "NEXTLINK", (577.6, 354.2))
    assert bb == (576.4, 351.7, 579.6, 356.8)  # far member excluded
    assert symbol_footprint(drawings, "NEXTLINK", (10.0, 10.0)) is None


def test_chain_continuity_bounds_dash_gaps():
    segs = [_seg(150, 343, 184, 345), _seg(216, 344, 250, 346),
            _seg(282, 345, 316, 348)]
    ok = chain_continuity(segs)
    assert ok["continuous"] and ok["segments"] == 3 and ok["gaps"] == [32.0, 32.0]
    broken = chain_continuity([_seg(150, 343, 184, 345), _seg(300, 345, 330, 348)])
    assert not broken["continuous"]  # 116-pt hole is not a dash gap


def test_discriminator_exactly_one_law():
    pts = dash_endpoints([_seg(570, 354, 578, 354)])
    hh = (576.4, 351.7, 579.6, 356.8)
    pot = (572.7, 352.1, 576.7, 356.4)
    far = (700.0, 700.0, 710.0, 710.0)
    one = discriminate_origin(pts, {"hh": hh, "far": far})
    assert one["result"] == ORIGIN_BOUND and one["winner"] == "hh"
    # endpoint at 570,354 is inside pot's x-range? 570 < 572.7 -> no; 578 in hh only
    both = discriminate_origin([(577.0, 354.0), (574.0, 354.0)],
                               {"hh": hh, "pot": pot})
    assert both["result"] == ORIGIN_AMBIGUOUS and both["winner"] is None
    none = discriminate_origin([(10.0, 10.0)], {"hh": hh, "pot": pot})
    assert none["result"] == ORIGIN_NOT_FOUND
    assert none["hit_counts"] == {"hh": 0, "pot": 0}


def test_dialect_conduit_map_is_v2_local():
    assert BRENHAM_CONDUIT_LAYERS["VACANT HDPE"] == "BORE - VACANT PIPE"
