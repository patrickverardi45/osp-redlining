"""M8.18 -- tests pinning the per-ladder tick-clustering seam (synthetic).

Locks: a single clean ladder is recovered with its scale; two interleaved
ladders are SEPARATED (not mixed into a cross-ladder median); a long station
jump at a short drawn distance is never fused into one ladder; the coherent
sheet scale is the shared scale only when the real ladders AGREE, and is None
(honest abstain) when they disagree or when only orphans exist; clustering is
pure (input never mutated) and deterministic."""
from __future__ import annotations

from truelinev2.extract.ladder_cluster import (
    cluster_ladders,
    coherent_ladder_scale,
)
from truelinev2.extract.tick_path import Tick


def _ladder(x0, y, scale_pt_per_ft, stations, dx=1.0, dy=0.0):
    """A drawn ladder: ticks at the given stations, spaced ``scale`` pt/ft
    along the (dx,dy) direction from (x0, y)."""
    out = []
    for s in stations:
        out.append(Tick(float(s), x0 + dx * scale_pt_per_ft * s,
                        y + dy * scale_pt_per_ft * s))
    return out


def test_single_clean_ladder_recovered_with_scale():
    ticks = _ladder(100.0, 400.0, 1.44, [100, 200, 300, 400, 500])
    lads = cluster_ladders(ticks)
    assert len(lads) == 1
    assert lads[0].length == 5
    assert abs(lads[0].scale - 1.44) < 1e-6
    assert lads[0].station_span == (100.0, 500.0)


def test_two_interleaved_ladders_are_separated():
    # two ladders sharing a y-band but running opposite directions -- the
    # exact log42 shape that made the old y-band median multi-modal
    a = _ladder(100.0, 420.0, 1.44, [100, 200, 300, 400, 500], dx=1.0)
    b = _ladder(900.0, 420.0, 1.44, [100, 200], dx=-1.0)
    lads = cluster_ladders(a + b)
    assert len(lads) == 2
    assert all(abs(l.scale - 1.44) < 1e-6 for l in lads)
    # the coherent scale is clean 1.44, NOT a cross-ladder artifact
    assert abs(coherent_ladder_scale(lads, min_ticks=2) - 1.44) < 1e-6


def test_long_station_jump_is_never_one_ladder():
    # station 100 and station 1100 sitting near each other (the buggy-cluster
    # trap) must NOT fuse into a tiny-scale "ladder"
    ticks = [Tick(100.0, 300.0, 540.0), Tick(1100.0, 101.0, 405.0)]
    lads = cluster_ladders(ticks)   # delta-station 1000 ft > max step -> no hop
    assert lads == []


def test_coherent_scale_abstains_on_disagreement():
    a = _ladder(100.0, 400.0, 1.44, [100, 200, 300])
    b = _ladder(100.0, 600.0, 3.20, [100, 200, 300])   # a genuinely different scale
    lads = cluster_ladders(a + b)
    assert coherent_ladder_scale(lads) is None        # no single drawn scale


def test_coherent_scale_none_when_only_orphans():
    assert coherent_ladder_scale([]) is None
    # two isolated ticks 1000 ft apart never form a ladder -> no voters
    orphans = [Tick(100.0, 10.0, 10.0), Tick(1100.0, 900.0, 900.0)]
    assert coherent_ladder_scale(cluster_ladders(orphans)) is None


def test_clustering_is_pure_and_deterministic():
    ticks = _ladder(100.0, 400.0, 1.44, [100, 200, 300])
    snapshot = [(t.station_ft, t.x, t.y) for t in ticks]
    a = cluster_ladders(ticks)
    b = cluster_ladders(ticks)
    assert [(l.length, l.scale) for l in a] == [(l.length, l.scale) for l in b]
    assert [(t.station_ft, t.x, t.y) for t in ticks] == snapshot  # not mutated
