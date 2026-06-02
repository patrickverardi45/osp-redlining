"""Bounded dash-chain reconstruction (pure, page-space; no fitz).

A plan's bored conduit is drawn as a DASHED linetype that PyMuPDF returns as many
short SOLID segments. This module reconstructs the authored polyline by joining
segments of the SAME AUTHORED STROKE FAMILY ``(layer, color, width)`` that are
COLINEAR and MONOTONIC along a shared axis, with the join gap bounded by the
family's OWN intrinsic dash length (a multiple of its median dash — NEVER a fixed
search radius, NEVER cross-family, NEVER off-axis). Excessive gaps / off-axis /
cross-family transitions terminate a chain and are recorded in
``rejected_candidates``.

This stage performs NO bore binding — it only reconstructs candidate chains from
geometry the PDF already contains. Binding to a bore (layer ∈ BORE-family +
callout corridor + station-tick corroboration) happens in ``path_tracer``.

Hard line vs forbidden behaviour: grouping by ``(layer,color,width)`` is reading
the authored pen, not selecting the bore by colour; the gap bound scales with the
family's own dash length, so it is intrinsic, not a proximity radius.
"""
from __future__ import annotations

import math
import statistics
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_PERP_TOL = 2.5      # max perpendicular offset to stay on one line (display pt)
DEFAULT_ANGLE_TOL = 6.0     # near-horizontal acceptance (deg)
DEFAULT_GAP_K = 1.6         # gap <= K * median_dash_len of THIS family (intrinsic)
DEFAULT_GAP_FLOOR = 4.0     # small absolute floor so tiny-dash families still join
DEFAULT_MIN_DASHES = 4
DEFAULT_MIN_SPAN = 120.0


def _seg_len(s: Dict[str, Any]) -> float:
    return math.hypot(s["p1"][0] - s["p0"][0], s["p1"][1] - s["p0"][1])


def _angle_deg(s: Dict[str, Any]) -> float:
    return math.degrees(math.atan2(s["p1"][1] - s["p0"][1], s["p1"][0] - s["p0"][0]))


def _family_key(s: Dict[str, Any]) -> Tuple:
    col = s.get("color")
    return (s.get("layer"), tuple(col) if isinstance(col, (list, tuple)) else col, s.get("width"))


def _ordered_points(chain: List[Dict[str, Any]]) -> List[List[float]]:
    """Verbatim dash endpoints in x-order; consecutive segments' endpoints connect
    (the gap-bridge is the reconstruction). No interpolation/snapping/smoothing."""
    ordered = sorted(chain, key=lambda s: min(s["p0"][0], s["p1"][0]))
    pts: List[List[float]] = []
    for s in ordered:
        a, b = (s["p0"], s["p1"]) if s["p0"][0] <= s["p1"][0] else (s["p1"], s["p0"])
        for p in (a, b):
            fp = [float(p[0]), float(p[1])]
            if not pts or abs(pts[-1][0] - fp[0]) > 1e-6 or abs(pts[-1][1] - fp[1]) > 1e-6:
                pts.append(fp)
    return pts


def build_chains(segments: List[Dict[str, Any]], *,
                 perp_tol: float = DEFAULT_PERP_TOL,
                 angle_tol: float = DEFAULT_ANGLE_TOL,
                 gap_k: float = DEFAULT_GAP_K,
                 gap_floor: float = DEFAULT_GAP_FLOOR,
                 min_dashes: int = DEFAULT_MIN_DASHES,
                 min_span: float = DEFAULT_MIN_SPAN) -> Dict[str, Any]:
    """Reconstruct near-horizontal dash chains per authored stroke family.

    Returns ``{'chains': [...], 'rejected_candidates': [...]}``. Each chain:
    ``{layer, color, width, points_display, bbox_display, dash_count,
    median_dash_len, gap_bound, span, axis, source_vector_refs}``. Page-space only.
    """
    fams: Dict[Tuple, List[Dict[str, Any]]] = defaultdict(list)
    for s in segments:
        if _seg_len(s) < 0.8:
            continue
        fams[_family_key(s)].append(s)

    chains: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []

    for fam, ss in fams.items():
        # near-horizontal members only (the bored runs on these sheets); off-axis
        # members are not chained into a horizontal run (recorded, not absorbed).
        horiz = [s for s in ss if abs(_angle_deg(s)) < angle_tol or abs(_angle_deg(s)) > 180 - angle_tol]
        if len(horiz) < min_dashes:
            continue
        # cluster into thin y-bands so a family's two parallel runs don't merge
        bands: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
        for s in horiz:
            ym = (s["p0"][1] + s["p1"][1]) / 2.0
            bands[round(ym / (perp_tol * 2.0))].append(s)
        for band in bands.values():
            if len(band) < min_dashes:
                continue
            band.sort(key=lambda s: min(s["p0"][0], s["p1"][0]))
            med_dash = statistics.median([_seg_len(s) for s in band]) or 1.0
            gap_bound = max(gap_floor, gap_k * med_dash)   # INTRINSIC to this family
            # greedy split into colinear runs bounded by gap + perpendicular drift
            runs: List[List[Dict[str, Any]]] = []
            cur: List[Dict[str, Any]] = [band[0]]
            for s in band[1:]:
                prev = cur[-1]
                gap = min(s["p0"][0], s["p1"][0]) - max(prev["p0"][0], prev["p1"][0])
                perp = abs(((s["p0"][1] + s["p1"][1]) / 2.0) - ((prev["p0"][1] + prev["p1"][1]) / 2.0))
                if gap <= gap_bound and perp <= perp_tol:
                    cur.append(s)
                else:
                    reason = "gap_exceeds_period" if gap > gap_bound else "off_axis_perp_drift"
                    rejected.append({"layer": fam[0], "reason": reason,
                                     "gap": round(gap, 1), "gap_bound": round(gap_bound, 1)})
                    runs.append(cur)
                    cur = [s]
            runs.append(cur)
            for ch in runs:
                if len(ch) < min_dashes:
                    continue
                xs = [p for s in ch for p in (s["p0"][0], s["p1"][0])]
                ys = [p for s in ch for p in (s["p0"][1], s["p1"][1])]
                span = max(xs) - min(xs)
                if span < min_span:
                    continue
                chains.append({
                    "layer": fam[0],
                    "color": (list(fam[1]) if isinstance(fam[1], tuple) else fam[1]),
                    "width": fam[2],
                    "points_display": _ordered_points(ch),
                    "bbox_display": [min(xs), min(ys), max(xs), max(ys)],
                    "dash_count": len(ch),
                    "median_dash_len": round(med_dash, 2),
                    "gap_bound": round(gap_bound, 2),
                    "span": round(span, 1),
                    "axis": "horizontal",
                    "source_vector_refs": [s.get("source_ref") for s in ch],
                })
    return {"chains": chains, "rejected_candidates": rejected}
