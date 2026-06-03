"""Bounded bore-run seam tracer — single-sheet, log56-seeded, default-OFF.

Deterministically traces ONE bore run from a resolved physical HH anchor by chaining
connected authored bore/path vector segments (via ``vector_extract``), to find where
the run crosses a matchline SEAM edge. The seam anchor is accepted ONLY if the HH's
connected bore-run component reaches EXACTLY ONE seam-edge crossing point.

Determinism / anti-guess contract (mirrors physical_anchor_resolver):
  * chain authored bore/path segments within a STRICT gap tolerance (the authored dash
    pitch) — connectivity is the only relationship used;
  * record branch nodes (degree >= 3) explicitly;
  * a seam crossing is a component node lying on a thin, long, axis-aligned MATCHLINE
    line (the title-block frame is excluded);
  * resolve ONLY when the component reaches exactly ONE seam crossing. 0 -> the run does
    not reach a seam; >1 -> ambiguous which crossing. Either case ABSTAINS with a
    machine-readable ``reason`` + the evidence a human / owner-seam-anchor would need.
NO nearest-crossing, NO perpendicular projection, NO single-layer guess, NO snapping.
Pure; never raises. Scope: log56 single-sheet seam; NOT a generic all-logs feature.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Sequence, Tuple

# Authored bore/path layers the run is chained over (the duct line itself, by type).
BORE_LAYERS: Tuple[str, ...] = ("BORE - PORT", "BORE - LATERAL", "BORE - VACANT PIPE", "BORE - PATH")
DEFAULT_GAP_TOL = 10.0     # px; max gap between consecutive authored bore strokes to chain (~dash pitch)
DEFAULT_START_TOL = 28.0   # px; max distance from the resolved HH anchor to the run's first node
DEFAULT_EDGE_TOL = 6.0     # px; max distance from a node to a matchline line to count as a crossing


def seam_edges(matchline_paths: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Thin, long, axis-aligned MATCHLINE lines (sheet-content seam edges). Excludes the
    title-block frame, which is wide AND tall on the MATCHLINE layer."""
    out: List[Dict[str, Any]] = []
    for p in matchline_paths or []:
        b = p.get("bbox_display")
        if not (isinstance(b, (list, tuple)) and len(b) == 4):
            continue
        w, h = b[2] - b[0], b[3] - b[1]
        if float(p.get("length") or 0.0) > 400.0 and (w < 6.0 or h < 6.0):
            out.append({"vert": w < h, "x": (b[0] + b[2]) / 2.0, "y": (b[1] + b[3]) / 2.0, "bbox": list(b)})
    return out


def _build_graph(bore_segments: Sequence[Dict[str, Any]], gap_tol: float):
    """Union segment endpoints within ``gap_tol`` into nodes; adjacency = the segments."""
    nodes: List[List[float]] = []
    adj: List[set] = []

    def nid(pt) -> int:
        for i, n in enumerate(nodes):
            if abs(n[0] - pt[0]) <= gap_tol and abs(n[1] - pt[1]) <= gap_tol \
                    and math.hypot(n[0] - pt[0], n[1] - pt[1]) <= gap_tol:
                return i
        nodes.append([float(pt[0]), float(pt[1])])
        adj.append(set())
        return len(nodes) - 1

    for s in bore_segments:
        try:
            a = nid(tuple(s["p0"]))
            b = nid(tuple(s["p1"]))
        except Exception:
            continue
        if a != b:
            adj[a].add(b)
            adj[b].add(a)
    return nodes, adj


def trace_seam_anchor(bore_segments: Sequence[Dict[str, Any]],
                      matchline_paths: Sequence[Dict[str, Any]],
                      hh_anchor: Sequence[float], *,
                      gap_tol: float = DEFAULT_GAP_TOL,
                      start_tol: float = DEFAULT_START_TOL,
                      edge_tol: float = DEFAULT_EDGE_TOL) -> Dict[str, Any]:
    """Trace the run from ``hh_anchor`` to a unique seam crossing, or ABSTAIN.

    Returns ``{resolved, seam_anchor:[x,y]|None, reason, evidence:{...}}``. Never raises.
    """
    try:
        bore = [s for s in (bore_segments or []) if str(s.get("layer")) in BORE_LAYERS]
        nodes, adj = _build_graph(bore, gap_tol)
        if not nodes:
            return {"resolved": False, "seam_anchor": None, "reason": "no_bore_segments_on_sheet",
                    "evidence": {"gap_tol": gap_tol}}
        start, bd = None, start_tol
        for i, n in enumerate(nodes):
            d = math.hypot(n[0] - hh_anchor[0], n[1] - hh_anchor[1])
            if d < bd:
                bd, start = d, i
        if start is None:
            nearest = min((math.hypot(n[0] - hh_anchor[0], n[1] - hh_anchor[1]) for n in nodes), default=-1.0)
            return {"resolved": False, "seam_anchor": None, "reason": "no_bore_run_node_within_start_tol",
                    "evidence": {"start_tol": start_tol, "nearest_bore_node_dist": round(nearest, 1)}}
        seen = {start}
        stack = [start]
        while stack:
            u = stack.pop()
            for v in adj[u]:
                if v not in seen:
                    seen.add(v)
                    stack.append(v)
        branch_nodes = [[round(nodes[i][0], 1), round(nodes[i][1], 1)] for i in seen if len(adj[i]) >= 3]
        edges = seam_edges(matchline_paths)
        crossings: List[List[float]] = []
        for i in seen:
            n = nodes[i]
            for e in edges:
                on = ((abs(n[0] - e["x"]) < edge_tol and e["bbox"][1] - edge_tol <= n[1] <= e["bbox"][3] + edge_tol)
                      if e["vert"] else
                      (abs(n[1] - e["y"]) < edge_tol and e["bbox"][0] - edge_tol <= n[0] <= e["bbox"][2] + edge_tol))
                if on:
                    crossings.append([round(n[0], 1), round(n[1], 1)])
        uniq: List[List[float]] = []
        for c in crossings:
            if not any(math.hypot(c[0] - u[0], c[1] - u[1]) < gap_tol * 2 for u in uniq):
                uniq.append(c)
        ev = {"start_node": [round(nodes[start][0], 1), round(nodes[start][1], 1)],
              "start_dist": round(bd, 1), "component_size": len(seen),
              "branch_node_count": len(branch_nodes), "branch_nodes": branch_nodes[:10],
              "seam_edges": len(edges), "seam_crossings": uniq, "gap_tol": gap_tol}
        if len(uniq) == 1:
            return {"resolved": True, "seam_anchor": uniq[0], "reason": "unique_seam_crossing", "evidence": ev}
        if not uniq:
            return {"resolved": False, "seam_anchor": None,
                    "reason": "seam_unreachable_from_hh_component", "evidence": ev}
        return {"resolved": False, "seam_anchor": None, "reason": "multiple_seam_crossings", "evidence": ev}
    except Exception as exc:  # pure: never raise into the connector path
        return {"resolved": False, "seam_anchor": None, "reason": "tracer_error:%s" % type(exc).__name__,
                "evidence": {}}


def verify_owner_seam_anchor(proposed_xy: Sequence[float],
                             matchline_paths: Sequence[Dict[str, Any]],
                             bore_segments: Sequence[Dict[str, Any]], *,
                             sheet: int, expected_sheet: int,
                             edge_tol: float = 8.0, port_tol: float = 14.0) -> Dict[str, Any]:
    """Machine-VERIFY an owner-proposed seam anchor before any use (used only because the
    delivered sheet-21 vectors are disconnected). The owner coordinate is NEVER blind truth:

      (1) it must lie within ``edge_tol`` of a thin authored MATCHLINE seam edge,
      (2) it must lie within ``port_tol`` of an authored ``BORE - PORT`` vector point
          (the observed seam entry), and
      (3) it must be on ``expected_sheet``.

    On success the anchor is SNAPPED to the verified BORE-PORT point projected onto the
    seam edge (so the draw point is authored geometry, not the approximate owner xy).
    Returns ``{verified, snapped_xy, reason, checks:{...}}``. Never raises; verified=False
    -> caller ABSTAINS."""
    try:
        if int(sheet) != int(expected_sheet):
            return {"verified": False, "snapped_xy": None,
                    "reason": "wrong_sheet:%s!=%s" % (sheet, expected_sheet), "checks": {}}
        px, py = float(proposed_xy[0]), float(proposed_xy[1])
        # (1) on an authored matchline seam edge?
        on_edge = None
        ed = None
        for e in seam_edges(matchline_paths):
            d = abs(px - e["x"]) if e["vert"] else abs(py - e["y"])
            within = ((e["bbox"][1] - edge_tol <= py <= e["bbox"][3] + edge_tol) if e["vert"]
                      else (e["bbox"][0] - edge_tol <= px <= e["bbox"][2] + edge_tol))
            if d <= edge_tol and within and (ed is None or d < ed):
                on_edge, ed = e, d
        # (2) near an authored BORE-PORT vector point (the observed seam entry)?
        best, bestd = None, port_tol
        for s in bore_segments or []:
            if str(s.get("layer")) != "BORE - PORT":
                continue
            for pt in (s.get("p0"), s.get("p1")):
                if not pt:
                    continue
                dd = math.hypot(float(pt[0]) - px, float(pt[1]) - py)
                if dd < bestd:
                    bestd, best = dd, [round(float(pt[0]), 2), round(float(pt[1]), 2)]
        on_matchline = on_edge is not None
        near_port = best is not None
        verified = bool(on_matchline and near_port)
        snapped = None
        if verified:
            sx, sy = best[0], best[1]
            if on_edge["vert"]:
                sx = round(on_edge["x"], 2)
            else:
                sy = round(on_edge["y"], 2)
            snapped = [sx, sy]
        reason = ("verified_owner_seam_anchor" if verified
                  else ("not_on_authored_matchline_edge" if not on_matchline else "not_near_authored_bore_port_entry"))
        return {"verified": verified, "snapped_xy": snapped, "reason": reason,
                "checks": {"sheet": int(sheet), "on_matchline_edge": on_matchline,
                           "edge_dist_px": (round(ed, 2) if ed is not None else None),
                           "near_bore_port": near_port, "bore_port_pt": best,
                           "bore_port_dist_px": (round(bestd, 2) if best is not None else None),
                           "proposed_xy": [round(px, 1), round(py, 1)]}}
    except Exception as exc:
        return {"verified": False, "snapped_xy": None, "reason": "verify_error:%s" % type(exc).__name__,
                "checks": {}}


def trace_cross_sheet_run(start_bore_segments, start_matchlines, start_hh,
                          end_bore_segments, end_matchlines, end_hh, *,
                          gap_tol: float = DEFAULT_GAP_TOL, start_tol: float = DEFAULT_START_TOL,
                          edge_tol: float = DEFAULT_EDGE_TOL) -> Dict[str, Any]:
    """Trace BOTH page sides. Draw only if BOTH resolve uniquely (rule 7). Returns the two
    per-sheet segments [HH->seam (start sheet)] / [seam->HH (end sheet)] + evidence, or an
    ABSTAIN with each side's reason. Never raises."""
    s = trace_seam_anchor(start_bore_segments, start_matchlines, start_hh,
                          gap_tol=gap_tol, start_tol=start_tol, edge_tol=edge_tol)
    e = trace_seam_anchor(end_bore_segments, end_matchlines, end_hh,
                          gap_tol=gap_tol, start_tol=start_tol, edge_tol=edge_tol)
    if s.get("resolved") and e.get("resolved"):
        return {"resolved": True,
                "start_segment": {"from_hh": [round(x, 1) for x in start_hh], "to_seam": s["seam_anchor"]},
                "end_segment": {"from_seam": e["seam_anchor"], "to_hh": [round(x, 1) for x in end_hh]},
                "start_trace": s, "end_trace": e,
                "run_id": "bore_log56", "note": "two per-sheet overlays = ONE cross-sheet run"}
    return {"resolved": False, "reason": "fallback_abstain:start=%s;end=%s" % (s.get("reason"), e.get("reason")),
            "start_trace": s, "end_trace": e, "run_id": "bore_log56"}
