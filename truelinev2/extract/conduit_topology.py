r"""Conduit-topology laws (GENERAL; no plan-set knowledge).

The drawn-containment discriminator proven by M8.14.b.6 and generalized for
the b.8 drop-lane sweep. Everything here is core law: callers inject layer
names, footprints, and segments -- this module never names a CAD layer, a
company, or a structure type.

Laws:
  * A symbol FOOTPRINT is the union bbox of a symbol cluster's drawings --
    a containment target, never a distance tolerance.
  * A conduit CHAIN is the set of conduit segments graph-connected to a seed
    footprint by bounded inter-bbox gaps (dashed-line convention). Connectivity
    is orientation-free (frontier expansion), so north-south corridors chain
    exactly like east-west ones.
  * The ORIGIN binds iff conduit dash endpoints land inside EXACTLY ONE
    candidate footprint: 0 -> not found, >= 2 -> ambiguous. Never nearest.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

ORIGIN_BOUND = "CONDUIT_ORIGIN_BOUND"
ORIGIN_AMBIGUOUS = "CONDUIT_ORIGIN_AMBIGUOUS"
ORIGIN_NOT_FOUND = "CONDUIT_ORIGIN_NOT_FOUND"
MAX_DASH_GAP = 35.0   # drawn dash spacing (b.6 observed 31.3-31.7 pt)
FOOTPRINT_RADIUS = 8.0

BBox = Tuple[float, float, float, float]


def symbol_footprint(drawings: Sequence[dict], layer: str,
                     center: Tuple[float, float],
                     radius: float = FOOTPRINT_RADIUS) -> Optional[BBox]:
    """Union bbox of the symbol-cluster member drawings around ``center``."""
    mem = [d for d in drawings if d.get("layer") == layer
           and math.hypot(d["xc"] - center[0], d["yc"] - center[1]) <= radius]
    if not mem:
        return None
    return (min(d["x0"] for d in mem), min(d["y0"] for d in mem),
            max(d["x1"] for d in mem), max(d["y1"] for d in mem))


def dash_endpoints(segments: Sequence[dict]) -> List[Tuple[float, float]]:
    return [p for d in segments for ln in (d.get("lines") or ())
            for p in ((ln[0], ln[1]), (ln[2], ln[3]))]


def bbox_gap(a: dict, b: dict) -> float:
    """Smallest gap between two drawing bboxes (0 when they touch/overlap)."""
    dx = max(0.0, max(a["x0"], b["x0"]) - min(a["x1"], b["x1"]))
    dy = max(0.0, max(a["y0"], b["y0"]) - min(a["y1"], b["y1"]))
    return math.hypot(dx, dy)


def connected_chain(segments: Sequence[dict], seed_bbox: BBox,
                    max_gap: float = MAX_DASH_GAP) -> List[dict]:
    """All segments graph-connected to the seed footprint by gaps <= max_gap.
    Orientation-free frontier expansion -- no axis sort, no direction prior."""
    seed = {"x0": seed_bbox[0], "y0": seed_bbox[1],
            "x1": seed_bbox[2], "y1": seed_bbox[3]}
    chain: List[dict] = []
    rest = list(segments)
    frontier: List[dict] = [seed]
    while frontier:
        nxt = [s for s in rest if any(bbox_gap(s, f) <= max_gap for f in frontier)]
        if not nxt:
            break
        chain.extend(nxt)
        rest = [s for s in rest if s not in nxt]
        frontier = nxt
    return chain


def chain_continuity(segments: Sequence[dict],
                     max_gap: float = MAX_DASH_GAP) -> dict:
    """Legacy b.6 single-axis continuity report (x-sorted gaps). Superseded by
    ``connected_chain`` for assembly; retained because the b.6 gates pin the
    exact drawn dash gaps of the proof specimen."""
    segs = sorted(segments, key=lambda d: d["x0"])
    gaps = [round(b["x0"] - a["x1"], 1) for a, b in zip(segs, segs[1:])]
    return {"segments": len(segs), "gaps": gaps,
            "continuous": all(g <= max_gap for g in gaps)}


def ladder_band_scales(ticks, y_lo: float, y_hi: float) -> List[float]:
    """Consecutive-station pts/ft hop scales among clean ladder ticks in a
    y-band. The RAW evidence behind ``ladder_scale_for_band`` -- exposed
    (M8.16) because a band holding ticks from MORE THAN ONE drawn ladder
    yields multi-modal hop scales whose median is a cross-ladder artifact:
    callers needing a corroboration BASIS must see the spread, not just the
    median."""
    band = sorted({(t.station_ft, t.x, t.y) for t in ticks if y_lo < t.y < y_hi})
    return [math.hypot(b[1] - a[1], b[2] - a[2]) / (b[0] - a[0])
            for a, b in zip(band, band[1:]) if b[0] > a[0]]


def ladder_scale_for_band(ticks, y_lo: float, y_hi: float) -> Optional[float]:
    """Median consecutive-station pts/ft among clean ladder ticks in a y-band;
    None when fewer than two distinct stations exist (no corroboration basis).
    Re-homed from the b.8 sweep for the M8.14.c lane (general law)."""
    scales = ladder_band_scales(ticks, y_lo, y_hi)
    return sorted(scales)[len(scales) // 2] if scales else None


def _inside(p: Tuple[float, float], bb: BBox) -> bool:
    return bb[0] <= p[0] <= bb[2] and bb[1] <= p[1] <= bb[3]


def discriminate_origin(endpoints: Sequence[Tuple[float, float]],
                        footprints: Dict[str, BBox]) -> dict:
    """The exactly-one law on drawn containment."""
    hits = {label: [p for p in endpoints if _inside(p, bb)]
            for label, bb in sorted(footprints.items())}
    winners = [label for label, ps in hits.items() if ps]
    result = (ORIGIN_BOUND if len(winners) == 1
              else ORIGIN_NOT_FOUND if not winners else ORIGIN_AMBIGUOUS)
    return {"result": result,
            "winner": winners[0] if len(winners) == 1 else None,
            "hit_counts": {label: len(ps) for label, ps in hits.items()}}
