"""Evidence-FUSION authored-path selector — log56 sheet-17 ONLY, default-OFF, abstain-FIRST.

The topology tracer (``cross_sheet_seam_tracer.trace_seam_path``) proves graph CONNECTIVITY, not
that a connected vector path IS the authored bore_log56 duct. This selector adds the authored
discriminators an office/field operator reads, and DRAWS only when ALL of them agree on exactly
ONE path; otherwise it ABSTAINS with a precise, machine-readable reason. Graph connectivity is used
ONLY as candidate geometry AFTER the authored discriminators are applied — never as proof.

Discriminators (ALL must pass, in order):
  1. NAMED MATCHLINE     — the seam is the authored 'MATCHLINE STA <home>/<neighbor>' edge bound by
                           its callout text, NOT any MATCHLINE line.
  2. RUN COLOR           — authored duct identity (ledger: log56 = the magenta run). The run color
                           is read from the BORE-* strokes incident to the PROVEN start HH structure;
                           candidate geometry is then restricted to that color.
  3. CANDIDATE PATH      — a UNIQUE simple path on the color-isolated graph from the start structure
                           node to the named seam node (connectivity used as candidate ONLY).
  4. STATION ORDER       — authored 'STA N+NN' callouts bound to the path increase MONOTONICALLY
                           from the start equation (0+00) toward the named seam (home_sta).
  5. BOC/OFFSET CORRIDOR — an authored '<boc>'' offset callout (log56 = 11') co-locates with the
                           path corridor (the side/offset the duct runs at).

Abstain reasons (machine-readable): named_matchline_not_bound, color_did_not_isolate_single_run,
endpoint_structure_not_bound, multiple_candidate_paths_after_evidence_fusion,
station_callouts_insufficient_to_orient, path_not_station_monotonic, boc_corridor_ambiguous.

PURE core: ``select_authored_s17_path`` takes already-extracted geometry + callouts (the caller does
the PDF text extraction), so the whole pipeline is unit-testable WITHOUT fitz. Never raises.
Scope: bore_log56 sheet-17. NOT a generic all-logs feature.
"""
from __future__ import annotations

import math
import re
from collections import deque
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .cross_sheet_seam_tracer import BORE_LAYERS, _build_graph, seam_edges

# Tolerances (px, DISPLAY space). Conservative on purpose — bias toward ABSTAIN.
GAP_TOL = 10.0           # chain consecutive authored strokes (~dash pitch); matches the tracer
START_TOL = 28.0         # max dist from the proven start HH to the run's first node
EDGE_TOL = 6.0           # max dist from a node to the named matchline edge to count as the seam
COLOR_TOL = 0.06         # per-channel color equality (0..1 floats)
STA_NEAR_TOL = 60.0      # max dist from a 'STA N+NN' callout to the path to bind it
OFFSET_NEAR_TOL = 130.0  # max dist from a '<boc>'' offset callout to the path corridor

_STA_RE = re.compile(r"\bSTA\.?\s*(\d+)\+(\d+)\b", re.I)
_OFF_RE = re.compile(r"^(\d{1,2})'$")
_FT_RE = re.compile(r"(\d+)\+(\d+)")
_SEE_SHEET_RE = re.compile(r"SEE\s+SHEET\s+(\d+)", re.I)


def _abstain(reason: str, disc: Dict[str, Any]) -> Dict[str, Any]:
    return {"resolved": False, "path_xy": None, "reason": reason, "discriminators": disc}


def _sta_ft(major: str, minor: str) -> int:
    return int(major) * 100 + int(minor)


# ── pure callout parsers (take text-extractor output; no fitz) ───────────────────────────────
def parse_station_callouts(words: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Authored 'STA N+NN' callouts -> [{ft, sta, xy}]. ``words`` = [{text, bbox_display}]."""
    out: List[Dict[str, Any]] = []
    for w in words or []:
        m = _STA_RE.search(str(w.get("text") or ""))
        b = w.get("bbox_display")
        if not m or not (isinstance(b, (list, tuple)) and len(b) == 4):
            continue
        out.append({"ft": _sta_ft(m.group(1), m.group(2)), "sta": f"{int(m.group(1))}+{m.group(2)}",
                    "xy": [(b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0]})
    return out


def parse_offset_callouts(words: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Authored small '<n>'' offset callouts -> [{ft, xy}]."""
    out: List[Dict[str, Any]] = []
    for w in words or []:
        m = _OFF_RE.match(str(w.get("text") or "").strip())
        b = w.get("bbox_display")
        if not m or not (isinstance(b, (list, tuple)) and len(b) == 4):
            continue
        out.append({"ft": int(m.group(1)), "xy": [(b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0]})
    return out


def parse_matchline_callouts(blocks: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Authored 'MATCHLINE STA ...' text blocks -> [{text, xy}]."""
    out: List[Dict[str, Any]] = []
    for bl in blocks or []:
        t = " ".join(str(bl.get("text") or "").split())
        b = bl.get("bbox_display")
        if "MATCHLINE" not in t.upper() or not (isinstance(b, (list, tuple)) and len(b) == 4):
            continue
        out.append({"text": t, "xy": [(b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0]})
    return out


# ── discriminator helpers ────────────────────────────────────────────────────────────────────
def _color_eq(c1, c2, tol: float = COLOR_TOL) -> bool:
    if not c1 or not c2 or len(c1) != len(c2):
        return False
    return all(abs(float(a) - float(b)) <= tol for a, b in zip(c1, c2))


def isolate_run_color(segments, start_xy, *, start_tol: float = START_TOL
                      ) -> Tuple[Optional[List[float]], Optional[str]]:
    """Run color = the SINGLE color shared by authored BORE-* strokes incident to the proven start
    HH structure. Abstains (None + reason) if there is no single such color (mixed / none)."""
    near: List[Tuple[float, ...]] = []
    for s in segments or []:
        if str(s.get("layer")) not in BORE_LAYERS or not s.get("color"):
            continue
        for pt in (s.get("p0"), s.get("p1")):
            if pt and math.hypot(pt[0] - start_xy[0], pt[1] - start_xy[1]) <= start_tol:
                near.append(tuple(s["color"]))
                break
    if not near:
        return None, "color_did_not_isolate_single_run"
    base = near[0]
    if all(_color_eq(base, c) for c in near):
        return list(base), None
    return None, "color_did_not_isolate_single_run"


def _on_edge(n, e, edge_tol: float) -> bool:
    if e["vert"]:
        return abs(n[0] - e["x"]) <= edge_tol and e["bbox"][1] - edge_tol <= n[1] <= e["bbox"][3] + edge_tol
    return abs(n[1] - e["y"]) <= edge_tol and e["bbox"][0] - edge_tol <= n[0] <= e["bbox"][2] + edge_tol


def _parse_see_sheet(text: Any) -> Optional[int]:
    """Parse the 'SEE SHEET N' target sheet from a matchline callout, or None if absent/unparseable."""
    m = _SEE_SHEET_RE.search(str(text or ""))
    return int(m.group(1)) if m else None


def bind_named_matchline(matchline_paths, matchline_callouts, home_sta, neighbor_sta=None,
                         expected_neighbor_sheet=None
                         ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Bind the seam to the authored matchline named by its callout (home or neighbor STA), then
    pick the seam EDGE nearest that callout. Abstains if no named callout or no seam edge.

    SEE-SHEET target validation (item 2, FAIL-OPEN): when ``expected_neighbor_sheet`` is given, a
    STA-matching callout that carries a PARSEABLE 'SEE SHEET N' target which CONTRADICTS the
    expected sheet is rejected (it names a matchline to the WRONG sheet). If every STA-matching
    callout is rejected for that reason, abstain ``named_matchline_wrong_target_sheet``. Fail-open:
    ``expected_neighbor_sheet`` None, OR a callout with no parseable SEE-SHEET, leaves behavior
    EXACTLY as before — never broadens matching, never creates a new draw."""
    edges = seam_edges(matchline_paths)
    if not edges:
        return None, "named_matchline_not_bound"
    target = None
    rejected_wrong_sheet = False
    for c in matchline_callouts or []:
        u = str(c.get("text") or "").upper()
        if not ((home_sta and str(home_sta) in u) or (neighbor_sta and str(neighbor_sta) in u)):
            continue
        # SEE-SHEET target check (fail-open): reject ONLY on a PROVEN wrong target sheet.
        if expected_neighbor_sheet is not None:
            see_sheet = _parse_see_sheet(c.get("text"))
            if see_sheet is not None and see_sheet != int(expected_neighbor_sheet):
                rejected_wrong_sheet = True
                continue
        target = c
        break
    if target is None:
        if rejected_wrong_sheet:
            return None, "named_matchline_wrong_target_sheet"
        return None, "named_matchline_not_bound"
    cx, cy = target["xy"]
    edge = min(edges, key=lambda e: math.hypot(e["x"] - cx, e["y"] - cy))
    return edge, None


def _nearest_node(nodes, xy, tol: float) -> Optional[int]:
    best, bd = None, tol
    for i, n in enumerate(nodes):
        d = math.hypot(n[0] - xy[0], n[1] - xy[1])
        if d < bd:
            bd, best = d, i
    return best


def _seam_node(nodes, named_edge, *, edge_tol: float = EDGE_TOL) -> Optional[int]:
    cand = [i for i, n in enumerate(nodes) if _on_edge(n, named_edge, edge_tol)]
    if not cand:
        return None
    return min(cand, key=lambda i: math.hypot(nodes[i][0] - named_edge["x"], nodes[i][1] - named_edge["y"]))


def unique_shortest_path(nodes, adj, start: int, target: int
                         ) -> Tuple[Optional[List[int]], Optional[str]]:
    """UNIQUE shortest authored path start->target via parent-tracked BFS, or abstain. >1 equal
    route -> multiple_candidate_paths_after_evidence_fusion; unreachable -> endpoint_structure_not_bound."""
    if start == target:
        return None, "endpoint_structure_not_bound"
    dist = {start: 0}
    npaths = {start: 1}
    parent = {start: -1}
    q = deque([start])
    while q:
        u = q.popleft()
        for v in adj[u]:
            if v not in dist:
                dist[v] = dist[u] + 1
                npaths[v] = npaths[u]
                parent[v] = u
                q.append(v)
            elif dist[v] == dist[u] + 1:
                npaths[v] = npaths[v] + npaths[u]
    if target not in dist:
        return None, "endpoint_structure_not_bound"
    if npaths[target] != 1:
        return None, "multiple_candidate_paths_after_evidence_fusion"
    chain: List[int] = []
    u = target
    while u != -1:
        chain.append(u)
        u = parent[u]
    chain.reverse()
    return chain, None


def _path_arclen(path_xy) -> List[float]:
    cum = [0.0]
    for i in range(1, len(path_xy)):
        cum.append(cum[-1] + math.hypot(path_xy[i][0] - path_xy[i - 1][0], path_xy[i][1] - path_xy[i - 1][1]))
    return cum


def _project_t(path_xy, cum, pt) -> Tuple[float, float]:
    """Nearest point on the polyline to ``pt`` -> (arc-length at that point, distance)."""
    best_t, best_d = 0.0, float("inf")
    for i in range(len(path_xy) - 1):
        ax, ay = path_xy[i]
        bx, by = path_xy[i + 1]
        dx, dy = bx - ax, by - ay
        seglen = math.hypot(dx, dy)
        if seglen <= 1e-9:
            t, px, py = 0.0, ax, ay
        else:
            t = max(0.0, min(1.0, ((pt[0] - ax) * dx + (pt[1] - ay) * dy) / (seglen * seglen)))
            px, py = ax + t * dx, ay + t * dy
        d = math.hypot(pt[0] - px, pt[1] - py)
        if d < best_d:
            best_d, best_t = d, cum[i] + t * seglen
    return best_t, best_d


def station_monotonic(path_xy, station_callouts, *, near_tol: float = STA_NEAR_TOL
                      ) -> Tuple[bool, Optional[str]]:
    """Authored STA callouts bound to the path (within ``near_tol``) must increase monotonically
    with arc-length from the start end. The path is oriented start->seam, so increasing arc-length
    == increasing station; a decrease means the run reads the wrong direction."""
    if len(path_xy) < 2:
        return False, "endpoint_structure_not_bound"
    cum = _path_arclen(path_xy)
    binds: List[Tuple[float, int]] = []
    for c in station_callouts or []:
        t, d = _project_t(path_xy, cum, c["xy"])
        if d <= near_tol:
            binds.append((t, int(c["ft"])))
    if len(binds) < 2:
        return False, "station_callouts_insufficient_to_orient"
    binds.sort(key=lambda b: b[0])
    fts = [b[1] for b in binds]
    if all(fts[i] < fts[i + 1] for i in range(len(fts) - 1)):
        return True, None
    return False, "path_not_station_monotonic"


def boc_corridor_ok(path_xy, offset_callouts, boc_ft, *, near_tol: float = OFFSET_NEAR_TOL
                    ) -> Tuple[bool, Optional[str]]:
    """An authored '<boc>'' offset callout must co-locate with the path corridor (the side/offset
    the duct runs at). Abstains if none corroborates the path."""
    if boc_ft is None:
        return False, "boc_corridor_ambiguous"
    cum = _path_arclen(path_xy)
    for o in offset_callouts or []:
        if int(o.get("ft", -1)) == int(boc_ft) and _project_t(path_xy, cum, o["xy"])[1] <= near_tol:
            return True, None
    return False, "boc_corridor_ambiguous"


# ── orchestrator (pure: takes extracted geometry + parsed callouts) ──────────────────────────
def select_authored_s17_path(*, segments, matchline_paths, start_xy, home_sta, neighbor_sta,
                             station_callouts, matchline_callouts, offset_callouts, boc_ft,
                             expected_neighbor_sheet=None,
                             gap_tol: float = GAP_TOL, start_tol: float = START_TOL,
                             edge_tol: float = EDGE_TOL) -> Dict[str, Any]:
    """Fuse the authored discriminators and return ``{resolved, path_xy, reason, discriminators,
    evidence}``. Draws (resolved True) ONLY when color + named matchline + a unique candidate path
    + station monotonicity + BOC corridor ALL agree; else abstains with a precise reason. Never raises."""
    disc: Dict[str, Any] = {}
    try:
        # 1. NAMED MATCHLINE — bind the seam to the authored callout, not any MATCHLINE line.
        named_edge, why = bind_named_matchline(matchline_paths, matchline_callouts, home_sta, neighbor_sta,
                                               expected_neighbor_sheet=expected_neighbor_sheet)
        if named_edge is None:
            return _abstain(why, disc)
        disc["named_matchline_bound"] = True

        # 2. RUN COLOR — authored duct identity at the proven start structure.
        run_color, why = isolate_run_color(segments, start_xy, start_tol=start_tol)
        if run_color is None:
            return _abstain(why, disc)
        disc["run_color"] = run_color

        # 3. CANDIDATE PATH — connectivity AFTER identity: unique path on the color-isolated run.
        csegs = [s for s in segments
                 if str(s.get("layer")) in BORE_LAYERS and _color_eq(s.get("color"), run_color)]
        nodes, adj = _build_graph(csegs, gap_tol)
        if not nodes:
            return _abstain("color_did_not_isolate_single_run", disc)
        start_idx = _nearest_node(nodes, start_xy, start_tol)
        seam_idx = _seam_node(nodes, named_edge, edge_tol=edge_tol)
        if start_idx is None or seam_idx is None:
            return _abstain("endpoint_structure_not_bound", disc)
        chain, why = unique_shortest_path(nodes, adj, start_idx, seam_idx)
        if chain is None:
            return _abstain(why, disc)
        path_xy = [[round(nodes[i][0], 1), round(nodes[i][1], 1)] for i in chain]
        if len(path_xy) < 2:
            return _abstain("endpoint_structure_not_bound", disc)
        disc["candidate_vertices"] = len(path_xy)

        # 4. STATION ORDER — authored stationing must progress 0+00 -> named seam along the path.
        ok, why = station_monotonic(path_xy, station_callouts, near_tol=STA_NEAR_TOL)
        if not ok:
            return _abstain(why, disc)
        disc["station_monotonic"] = True

        # 5. BOC/OFFSET CORRIDOR — the '<boc>'' offset must corroborate the path's side/corridor.
        ok, why = boc_corridor_ok(path_xy, offset_callouts, boc_ft, near_tol=OFFSET_NEAR_TOL)
        if not ok:
            return _abstain(why, disc)
        disc["boc_corridor_ft"] = boc_ft

        return {"resolved": True, "path_xy": path_xy, "reason": "authored_path_evidence_fused",
                "discriminators": disc,
                "evidence": {"run_color": run_color, "named_seam_sta": home_sta,
                             "path_vertices": len(path_xy), "boc_ft": boc_ft}}
    except Exception as exc:  # pure: never raise into the draw path
        return _abstain("selector_error:%s" % type(exc).__name__, disc)
