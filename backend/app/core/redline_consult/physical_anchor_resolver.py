"""Deterministic PHYSICAL structure-anchor resolver — single-sheet, default-OFF.

The callout / info box PROVES identity (verified upstream by ``frame_resolver``). It
is NOT the draw anchor. This module resolves the *physical* structure node a connector
should attach to, using ONLY the authored CAD vector layers (via
``redline_pdf_first.pdf.vector_extract``) — never nearest-box guessing, which the
page-22 probes showed can grab ``TEL-HH`` / ``FLOWER POT`` / ``HOUSES`` / unrelated
geometry.

Determinism contract (no scoring, no nearest-of-many, no snapping):
  * restrict to an explicit allow-list of authored STRUCTURE layers — e.g. the fiber
    installer's ``NEXTLINK`` layer. This layer filter is what excludes TEL-HH / houses /
    road / bore lines so they can NEVER be chosen.
  * cluster that layer's paths into discrete symbol blobs (union-find on bbox touch);
  * accept ONLY if EXACTLY ONE blob lies within ``radius`` of the verified callout
    (the uniqueness gate). 0 blobs or >1 blob -> UNRESOLVED, and the caller falls back
    to today's text-box anchor (never a guessed physical point).

Scope: single-sheet HH-HH crossings, seeded for ``bore_log66`` (sheet 10). Cross-sheet
(log56) seam stitching is explicitly OUT of scope. Pure; never raises.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Sequence, Tuple

# Authored installer-structure layer(s). For the NextLink plan set the placed handholes
# (NEXTLINK HH / INSTALLER HH) are authored on the ``NEXTLINK`` CAD layer; TEL-HH,
# FLOWER POT, HOUSES, ROAD and BORE-* are deliberately NOT listed, so they are never
# candidates. A different plan vendor would extend this allow-list — it is the ONLY
# plan-specific knob, and it is authored data, not a guess.
DEFAULT_STRUCTURE_LAYERS: Tuple[str, ...] = ("NEXTLINK",)
# px; tuned to the single-sheet HH-HH street-crossing scale (sheet 10 / page 22). Large
# enough to reach the structure marker beside a vertical callout, small enough that the
# OTHER crossing endpoint's marker (~79px away here) never falls inside both radii.
DEFAULT_RADIUS = 95.0


def _centroid(bbox: Sequence[float]) -> Tuple[float, float]:
    return ((bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0)


def _bbox_touch(a: Sequence[float], b: Sequence[float], margin: float = 5.0) -> bool:
    """True when two display-space bboxes overlap (expanded by ``margin``) — the union
    rule that stitches a symbol drawn as several short strokes into one blob."""
    return not (a[2] + margin < b[0] or b[2] + margin < a[0]
                or a[3] + margin < b[1] or b[3] + margin < a[1])


def _cluster_layer_blobs(paths: List[Dict[str, Any]], layer: str) -> List[Dict[str, Any]]:
    """Union-find the paths on ONE authored layer into connected symbol blobs."""
    items = [p for p in paths
             if str(p.get("layer")) == layer
             and isinstance(p.get("bbox_display"), (list, tuple)) and len(p["bbox_display"]) == 4]
    parent = list(range(len(items)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if _bbox_touch(items[i]["bbox_display"], items[j]["bbox_display"]):
                parent[find(i)] = find(j)
    groups: Dict[int, List[Dict[str, Any]]] = {}
    for i, p in enumerate(items):
        groups.setdefault(find(i), []).append(p)
    blobs: List[Dict[str, Any]] = []
    for ps in groups.values():
        xs = [c for p in ps for c in (p["bbox_display"][0], p["bbox_display"][2])]
        ys = [c for p in ps for c in (p["bbox_display"][1], p["bbox_display"][3])]
        bb = [min(xs), min(ys), max(xs), max(ys)]
        blobs.append({"bbox": bb, "centroid": list(_centroid(bb)),
                      "layer": layer, "n_paths": len(ps)})
    return blobs


def resolve_physical_anchor(callout_bbox: Sequence[float], paths: List[Dict[str, Any]], *,
                            structure_layers: Sequence[str] = DEFAULT_STRUCTURE_LAYERS,
                            radius: float = DEFAULT_RADIUS) -> Dict[str, Any]:
    """Resolve ONE physical structure anchor for a verified callout, or signal fallback.

    ``callout_bbox`` — the PROVEN callout's display-space bbox (proof, NOT the anchor).
    ``paths``        — ``vector_extract.extract_paths(page)`` for the SAME sheet.
    Returns ``{resolved, anchor:[x,y]|None, bbox|None, reason, evidence:[...]}``.
    Never raises (any failure -> resolved False, caller falls back)."""
    try:
        cpt = _centroid(callout_bbox)
        hits: List[Dict[str, Any]] = []
        for layer in structure_layers:
            for b in _cluster_layer_blobs(paths, layer):
                d = math.hypot(b["centroid"][0] - cpt[0], b["centroid"][1] - cpt[1])
                if d <= radius:
                    b = dict(b)
                    b["dist"] = round(d, 2)
                    hits.append(b)
        hits.sort(key=lambda b: b["dist"])
        evidence = [{"layer": b["layer"], "centroid": [round(x, 1) for x in b["centroid"]],
                     "dist_px": b["dist"], "n_paths": b["n_paths"]} for b in hits[:5]]
        if not hits:
            return {"resolved": False, "anchor": None, "bbox": None, "evidence": evidence,
                    "reason": "no_structure_blob_on_allowed_layer_within_radius",
                    "structure_layers": list(structure_layers)}
        if len(hits) > 1:
            return {"resolved": False, "anchor": None, "bbox": None, "evidence": evidence,
                    "reason": "ambiguous_multiple_structure_blobs",
                    "structure_layers": list(structure_layers)}
        b = hits[0]
        return {"resolved": True,
                "anchor": [round(b["centroid"][0], 2), round(b["centroid"][1], 2)],
                "bbox": [round(x, 2) for x in b["bbox"]],
                "reason": "unique_structure_blob", "evidence": evidence,
                "structure_layers": list(structure_layers)}
    except Exception as exc:  # pure: never raise into the connector path
        return {"resolved": False, "anchor": None, "bbox": None, "evidence": [],
                "reason": "resolver_error:%s" % type(exc).__name__}


def resolve_connector_anchors(start_bbox: Sequence[float], end_bbox: Sequence[float],
                              paths: List[Dict[str, Any]], *,
                              structure_layers: Sequence[str] = DEFAULT_STRUCTURE_LAYERS,
                              radius: float = DEFAULT_RADIUS) -> Dict[str, Any]:
    """Resolve BOTH connector endpoints. Accept the physical pair ONLY if BOTH ends
    resolve uniquely; otherwise signal fallback for the WHOLE connector (never mix one
    physical + one text-box end). Records a light corroboration note (resolved span vs
    text-box span) — informational, not a gate."""
    s = resolve_physical_anchor(start_bbox, paths, structure_layers=structure_layers, radius=radius)
    e = resolve_physical_anchor(end_bbox, paths, structure_layers=structure_layers, radius=radius)
    out: Dict[str, Any] = {"start": s, "end": e}
    if s.get("resolved") and e.get("resolved"):
        sp = math.hypot(s["anchor"][0] - e["anchor"][0], s["anchor"][1] - e["anchor"][1])
        tx = math.hypot(_centroid(start_bbox)[0] - _centroid(end_bbox)[0],
                        _centroid(start_bbox)[1] - _centroid(end_bbox)[1])
        out.update({"resolved": True, "start_anchor": s["anchor"], "end_anchor": e["anchor"],
                    "corroboration": {"resolved_span_px": round(sp, 1),
                                      "textbox_span_px": round(tx, 1),
                                      "tighter_than_textbox": bool(sp < tx)}})
    else:
        out.update({"resolved": False,
                    "reason": "fallback_to_text_anchor:start=%s;end=%s"
                              % (s.get("reason"), e.get("reason"))})
    return out
