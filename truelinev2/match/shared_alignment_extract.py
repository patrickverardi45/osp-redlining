r"""M8.20 shipped engine seam: extract SHARED_ALIGNMENT_MULTI_DROP claims.

Promotes the M8.18 design-path-LENGTH survivor discriminator + the M8.19 path-
length cross-sheet join out of the proof layer into convention-agnostic engine
code, so a corpus consumer (e.g. the reviewer service) can produce Law-1
``BoreClaim``s WITHOUT importing proof. ``resolve_bore`` is consulted READ-ONLY
for the per-bore cross-sheet classification (far sheet + bound end structure);
this module adds the length narrowing the per-bore lane deliberately does not
do, then re-proves the M8.19 join.

No proof imports. No per-bore lane behavior change (``resolve_bore`` is consumed,
never modified). No tolerance introduced or widened (``DESIGN_LENGTH_REL_TOL`` /
``JOIN_SCALE_REL_TOL`` imported verbatim). Nothing is rendered: the claims carry
the proven walk geometry as Law-1 evidence; no stroke/segment/PNG is produced.
All plan conventions (layers, materials, multi-port classes) come from the
injected ``dialect``; this module holds zero convention strings.
"""
from __future__ import annotations

import math
from typing import List, Optional, Tuple

from truelinev2.extract.conduit_topology import connected_chain, symbol_footprint
from truelinev2.extract.design_path import (
    DESIGN_LENGTH_REL_TOL,
    TRACED,
    conduit_pieces,
    path_length,
    walk_design_path,
)
from truelinev2.extract.ladder_cluster import cluster_ladders, coherent_ladder_scale
from truelinev2.extract.matchline_join import (
    CHAIN_UNIQUE,
    PROVEN,
    assemble_callout_chain,
    chain_conduit_evidence,
    cross_sheet_join_verdict,
    extend_dash_to_boundary,
    matchline_bboxes,
    nearest_gap,
    run_callouts_ending_at,
)
from truelinev2.extract.structure_position import cluster_symbols
from truelinev2.extract.tick_path import route_ladder_ticks
from truelinev2.match.shared_alignment import BoreClaim
from truelinev2.match.symbol_conduit_lane import (
    S_STRUCTURE_REQUIRED,
    _sheet_no,
    resolve_bore,
)
from truelinev2.stations import feet_to_station

_ANCHOR_MATCH_TOL = 1.0   # recover the bound end structure's layer at its xy


def _materials(dialect) -> Tuple[str, ...]:
    """Conduit material vocabulary, dialect-sourced (the material token of the
    conduit key, e.g. ``VACANT HDPE`` -> ``HDPE``)."""
    parts = dialect.conduit_key.split()
    return (parts[-1],) if parts else ()


def _multiport_keywords(dialect) -> Tuple[str, ...]:
    """Printed multi-port origin-class keywords, dialect-sourced: the keyword
    sets of the dialect's declared multi-port origin classes."""
    classes = set(getattr(dialect, "multiport_origin_classes", ()) or ())
    return tuple(kw for cls, kws in dialect.class_keywords if cls in classes
                 for kw in kws)


def _structure_layers(dialect) -> List[str]:
    return sorted({v[1] for v in dialect.structure_layers.values()})


def _matchline_for(plan, off, graph, dialect, far, end, boundary_raw, drawings):
    """The drawn matchline bbox for the printed frame equation between the two
    sheets at ``boundary_raw``; None if the printed lookup is not unique."""
    edges = [e for e in graph.edges
             if {_sheet_no(e.from_frame), _sheet_no(e.to_frame)} == {far, end}
             and boundary_raw in (e.a_raw, e.b_raw)]
    if len(edges) != 1:
        return None
    eqt = edges[0].source.split(None, 1)[-1]
    eqxy = next(((w["xc"], w["yc"]) for w in plan.words(far, off)
                 if w["text"] == eqt), None)
    mls = matchline_bboxes(drawings, dialect.matchline_layer)
    if eqxy is None or not mls:
        return None
    return min(mls, key=lambda bb: nearest_gap([eqxy], bb))


def _boundary_and_chain(plan, off, far, end, start_raw, end_raw):
    """(boundary_raw, seg_far, seg_end, chain) via the M8.17 uniqueness-
    mandatory printed chain; None when any printed lookup is not unique -- the
    engine abstains softly (no claim), never crashes, never guesses."""
    ec = [(r, f) for r, f, _ in run_callouts_ending_at(plan.lines(end, off), end_raw)
          if f is not None and r != start_raw]
    if len(ec) != 1:
        return None
    boundary_raw, seg_end = ec[0]
    chain = assemble_callout_chain(plan.lines(far, off), start_raw, boundary_raw)
    if chain["result"] != CHAIN_UNIQUE:
        return None
    return boundary_raw, chain["footage"], seg_end, chain


def _far_survivor(plan, off, dialect, far, ml, seg_far, scale):
    """M8.18 design-path-length survivor: the UNIQUE far-sheet structure whose
    drawn route length corroborates ``seg_far * scale`` within
    ``DESIGN_LENGTH_REL_TOL``. (id, footprint_mid_xy, boundary_xy,
    stroke_points, path_len) or None when 0 or >= 2 survive (never a guess)."""
    drawings = plan.line_items(far, off)
    conduit = [x for x in drawings if x["layer"] in dialect.path_layers]
    pieces = conduit_pieces(drawings, dialect.path_layers)
    exp = seg_far * scale
    survivors = []
    for lay in _structure_layers(dialect):
        for c in cluster_symbols(drawings, lay):
            bb = symbol_footprint(drawings, lay, (c.x, c.y))
            if not bb:
                continue
            chain = connected_chain(conduit, bb)
            bnd = extend_dash_to_boundary(chain, ml) if chain else None
            if bnd is None:
                continue
            xy = ((bb[0] + bb[2]) / 2.0, (bb[1] + bb[3]) / 2.0)
            walk = walk_design_path(pieces, xy, bnd)
            if walk["result"] != TRACED:
                continue
            plen = path_length(walk["stroke_points"])
            if exp > 0 and abs(plen - exp) / exp <= DESIGN_LENGTH_REL_TOL:
                survivors.append((f"{lay}@{c.x:.0f},{c.y:.0f}", xy, bnd,
                                  tuple(walk["stroke_points"]), plen))
    return survivors[0] if len(survivors) == 1 else None


def _end_structure_layer(plan, off, dialect, end_sheet, end_anchor):
    """The structure layer of the bore's bound end anchor, recovered at its xy;
    None if no structure cluster sits at that point."""
    best = None
    dr = plan.line_items(end_sheet, off)
    for lay in _structure_layers(dialect):
        for c in cluster_symbols(dr, lay):
            d = math.hypot(c.x - end_anchor[0], c.y - end_anchor[1])
            if d <= _ANCHOR_MATCH_TOL and (best is None or d < best[1]):
                best = (lay, d)
    return best[0] if best else None


def _end_path_scale(plan, off, graph, dialect, far, end, boundary_raw,
                    end_layer, end_anchor, seg_end):
    """M8.19 implied scale (drawn path_len / footage) for the END structure's
    span to the shared matchline; None if it does not uniquely trace."""
    if not seg_end:
        return None
    dr = plan.line_items(end, off)
    ml = _matchline_for(plan, off, graph, dialect, far, end, boundary_raw, dr)
    clusters = cluster_symbols(dr, end_layer)
    if ml is None or not clusters:
        return None
    c = min(clusters, key=lambda c: math.hypot(c.x - end_anchor[0],
                                               c.y - end_anchor[1]))
    fp = symbol_footprint(dr, end_layer, (c.x, c.y))
    chain = connected_chain([x for x in dr if x["layer"] in dialect.path_layers],
                            fp) if fp else []
    bnd = extend_dash_to_boundary(chain, ml) if chain else None
    if bnd is None:
        return None
    walk = walk_design_path(conduit_pieces(dr, dialect.path_layers), (c.x, c.y), bnd)
    if walk["result"] != TRACED:
        return None
    return path_length(walk["stroke_points"]) / seg_end


def _claim_for_bore(plan, off, graph, dialect, bore, out) -> Optional[BoreClaim]:
    far = out.detail.get("far_sheet")
    end_anchor = out.detail.get("end_anchor")
    if far is None or end_anchor is None:
        return None
    others = [s for s in sorted(set(bore.sheet_refs)) if s != far]
    if len(others) != 1:        # ambiguous end sheet -> no claim (safe)
        return None
    end = others[0]
    bc = _boundary_and_chain(plan, off, far, end,
                             feet_to_station(bore.station_start_ft),
                             feet_to_station(bore.station_end_ft))
    if bc is None:
        return None
    boundary_raw, seg_far, seg_end, chain = bc
    ticks, _ = route_ladder_ticks(plan, far, off)
    scale = coherent_ladder_scale(cluster_ladders(ticks))
    if scale is None:           # no coherent ladder scale -> no claim (no guess)
        return None
    drawings = plan.line_items(far, off)
    ml = _matchline_for(plan, off, graph, dialect, far, end, boundary_raw, drawings)
    if ml is None:
        return None
    surv = _far_survivor(plan, off, dialect, far, ml, seg_far, scale)
    if surv is None:            # M8.18: 0 or >= 2 survivors -> no claim (log42)
        return None
    survivor_id, _far_xy, far_bnd, far_walk, far_plen = surv

    # M8.19 path-length join: far survivor scale vs end structure scale.
    far_scale = far_plen / seg_far if seg_far else None
    end_layer = _end_structure_layer(plan, off, dialect, end, end_anchor)
    end_scale = (_end_path_scale(plan, off, graph, dialect, far, end,
                                 boundary_raw, end_layer, end_anchor, seg_end)
                 if end_layer is not None else None)
    span = bore.station_end_ft - bore.station_start_ft
    join_proven = bool(
        far_scale is not None and end_scale is not None
        and cross_sheet_join_verdict(
            equation_edge=True, eq_at_matchline_a=True, eq_at_matchline_b=True,
            chain_a_reaches=True, chain_b_reaches=True,
            seg_a_ft=seg_far, seg_b_ft=seg_end, span_ft=span,
            scale_a=far_scale, scale_b=end_scale)["verdict"] == PROVEN)

    notes = chain.get("notes", [])
    first_note = (notes[0] if notes else "").upper()
    return BoreClaim(
        bore_id=bore.bore_id, survivor_id=survivor_id, boundary_raw=boundary_raw,
        chain_unique=True, join_proven=join_proven,
        chain_hops=tuple((a, b, f) for a, b, f, _ in chain["hops"]),
        walk_points=far_walk, boundary_xy=tuple(far_bnd),
        conduit_count=len(chain_conduit_evidence(notes, _materials(dialect))),
        origin_multiport=any(k in first_note for k in _multiport_keywords(dialect)))


def extract_group_claims(plan, offset, graph, dialect, bores) -> List[BoreClaim]:
    """Shipped engine entry point: per-bore Law-1 ``BoreClaim``s for cross-sheet
    shared-origin candidates. ``resolve_bore`` is consulted READ-ONLY for the
    cross-sheet classification; the M8.18 length discriminator + M8.19 path-
    length join (proof-only until now) run here. A bore that is not a cross-
    sheet structure-required candidate, or whose far survivor is not unique
    (e.g. log42 -- 0 survivors), yields NO claim. Pure read; nothing rendered.
    """
    claims: List[BoreClaim] = []
    for bore in bores:
        out = resolve_bore(plan, bore, offset, dialect, frame_graph=graph)
        if out.status != S_STRUCTURE_REQUIRED:
            continue
        claim = _claim_for_bore(plan, offset, graph, dialect, bore, out)
        if claim is not None:
            claims.append(claim)
    return claims


def _matchline_boundary_stations(graph, far, end):
    out = set()
    for e in graph.edges:
        if {_sheet_no(e.from_frame), _sheet_no(e.to_frame)} == {far, end}:
            out.add(e.a_raw)
            out.add(e.b_raw)
    return out


def origin_chain_boundaries(plan, offset, graph, dialect, far_sheet, end_sheet,
                            start_raw) -> frozenset:
    """The Law-1 gate-5 bijection universe: boundary stations of EVERY
    uniqueness-mandatory printed chain from the shared origin's start station to
    a boundary on the shared matchline."""
    far_lines = plan.lines(far_sheet, offset)
    out = set()
    for b in _matchline_boundary_stations(graph, far_sheet, end_sheet):
        if assemble_callout_chain(far_lines, start_raw, b)["result"] == CHAIN_UNIQUE:
            out.add(b)
    return frozenset(out)
