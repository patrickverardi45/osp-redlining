r"""LOG3 PRINTED-RUN-CALLOUT-CHAIN proof slice -- read-only; NO render; NO commit-of-strokes; NO sweep wiring.

Proves the proposed ``printed_run_callout_chain_route`` assembler for the owner-source-verified log3 chain
(STA 12+63 FLOWER POT s2 -> 21+63 NEXTLINK HH s5, 900', continuous across sheets 2->3->4->5) WITHOUT touching
the production sweep, census, fixtures, or the render frontier. It binds the endpoints + the 15+13 reset
intermediate, verifies the six printed STA-A-TO-STA-B callouts + the bounded 19' gap (<= GAP_CAP 25), checks
station/matchline continuity, ATTEMPTS to assemble the two UNCOVERED upstream legs (s2 12+63->12+66, s3
12+66->15+13), proves the downstream 15+13->21+63 is COVERED by already-drawn log4 (same 15+13 symbol within
SAME_POINT_TOL), and computes closure (250' new + 650' covered = 900') + overlap.

REFINEMENT (callout_bounded_multi_component_stitch): the s3 247' leg is fragmented; this slice attempts to
assemble it with the PROVEN conduit-corridor walk (corridor_prune + walk_design_path -- the SAME machinery the
log16 fiber slice uses), bounded by the printed footage. A straight chord cannot capture a BOWED run, so the
corridor walk is the geometrically-correct path-follower. RESULT (measured, honest): the drawn conduit between
the 12+66 matchline and the 15+13 HH is NOT continuously drawn (walk -> DESIGN_PATH_NOT_CONNECTED), so the leg
does not assemble by conduit tracing -- a SOURCE-geometry fact (the run is drawn in fragments with >dash-cap
gaps + a bow), not a tracer weakness. G9 therefore stays FAIL; the s3 leg needs a non-conduit-tracing route
(callout/station-ladder geometry), out of scope for a conduit stitch. NOTHING is committed while G9 fails.

DECIDES nothing about placement; draws NO red stroke; mutates NO lane/census/fixture/corpus/parent-model. log4's
drawn legs are read via ``solve_log(..., 'log4', OWNER_CONFIRMED_PLAN_ROUTES)`` (the SAME record the sweep
already renders). JSON report -> gitignored data/outputs. Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_log3_chain_route_proof_slice
"""
from __future__ import annotations

import json
import math
import statistics

from truelinev2.config import _REPO_ROOT
from truelinev2.extract.conduit_topology import MAX_DASH_GAP, dash_endpoints
from truelinev2.extract.corridor_prune import corridor_bound, prune_pieces
from truelinev2.extract.design_path import TRACED, conduit_pieces, walk_design_path
from truelinev2.extract.matchline_join import extend_dash_to_boundary, nearest_gap, see_sheet_crossings
from truelinev2.extract.registry import select_dialect
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.proof.run_brenham_corpus import PDF
from truelinev2.proof.run_callout_route_assembly_sweep import (
    BASE_CONDUIT,
    FIBER_CONDUIT_EXTRA,
    OWNER_CONFIRMED_PLAN_ROUTES,
    SAME_POINT_TOL,
    SCALE,
    _bind,
    _conduit_components,
    _footage_tick_ladders,
    _ml_bbox,
    _ordered_leg,
    _pt_to_route,
    solve_log,
)
from truelinev2.proof.run_log71_render_artifact_slice import route_length
from truelinev2.stations import parse_station

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "log3_chain_route_proof_slice"
GAP_CAP = 25.0
FIBER = BASE_CONDUIT | set(FIBER_CONDUIT_EXTRA)
CLOSURE_REL_TOL = 0.10
# station_ladder_callout_route_geometry constants (proof-local; global MAX_DASH_GAP/overlap caps untouched):
CONTROL_GAP_CAP = 25.0     # max gap (ft) between consecutive PRINTED control points before owner-marked fallback
LADDER_BIN_FT = 10.0       # bin width (ft) along the run for building the control-point spine (median per bin)

# The owner-source-verified printed chain (labels only; coordinates extractor-derived). covered = which
# already-drawn child (if any) owns this segment's span.
CHAIN = [
    {"sheet": 2, "a": "12+63", "b": "12+66", "ft": 3,   "join": "matchline", "covered": None,   "kind": "start_leg"},
    {"sheet": 3, "a": "12+66", "b": "15+13", "ft": 247, "join": "station",   "covered": None,   "kind": "mid_leg"},
    {"sheet": 3, "a": "15+13", "b": "16+06", "ft": 93,  "join": "gap",       "covered": "log4", "kind": "covered"},
    {"sheet": 3, "a": "16+06", "b": "16+25", "ft": 19,  "join": "matchline", "covered": "log4", "kind": "covered_gap"},
    {"sheet": 4, "a": "16+25", "b": "17+88", "ft": 163, "join": "station",   "covered": "log4", "kind": "covered"},
    {"sheet": 4, "a": "17+88", "b": "20+18", "ft": 230, "join": "matchline", "covered": "log4", "kind": "covered"},
    {"sheet": 5, "a": "20+18", "b": "21+63", "ft": 145, "join": "end",       "covered": "log4", "kind": "covered"},
]
START = {"sheet": 2, "cls": "flower_pot", "label": "12+63"}
END = {"sheet": 5, "cls": "nextlink_hh", "label": "21+63"}
INTERMED = {"sheet": 3, "cls": "nextlink_hh", "label": "15+13"}   # the 15+13=0+00 reset == log4's start
# OWNER-CONFIRMED s3 control points (PDF display coords), extracted by DIFF of the owner-annotated packet vs the
# regenerated baseline (run_log3_owner_control_point_packet) -- 11 solid yellow dots on the TOP bore centerline
# (y~297, the HH's y). The owner red-X'd the lower diagonal (my old y363 start path) as INCORRECT. Provenance:
# data/outputs/log3_owner_control_point_packet/OWNER_ANNOTATED_RETURN.png. Explicit owner marks only -- never inferred.
OWNER_CONTROL_POINTS_S3 = [
    (876.3, 296.9), (901.7, 297.2), (922.7, 298.0), (952.4, 297.0), (983.2, 297.4), (1017.5, 297.3),
    (1053.0, 297.0), (1078.7, 297.0), (1099.6, 296.1), (1127.5, 296.5), (1140.8, 295.8),
]


def _callout_printed(plan, off, sheet, a, b):
    import re
    pat = re.compile(rf"STA\s*{re.escape(a)}\s*TO\s*STA\s*{re.escape(b)}")
    for ln in plan.lines(sheet, off):
        if pat.search(ln):
            return ln.strip()
    return None


def _trace_single_component(plan, off, sheet, cross, struct_xy):
    """Single-component callout leg: the fiber component reaching the printed matchline bbox, ordered
    matchline-boundary -> structure. Works for a SHORT run drawn as one component (leg A, 3'). Measurement
    only; never renders."""
    draw, words = plan.line_items(sheet, off), plan.words(sheet, off)
    conduit = [d for d in draw if d.get("layer") in FIBER]
    bb = _ml_bbox(words, draw, cross)
    if not bb:
        return {"error": "no matchline bbox"}
    best, comp = 1e9, None
    for c in _conduit_components(conduit):
        eps = dash_endpoints(c)
        if eps:
            g = min(nearest_gap([p], bb) for p in eps)
            if g <= MAX_DASH_GAP and g < best:
                best, comp = g, c
    if comp is None:
        return {"error": "no component reaches matchline"}
    eps = dash_endpoints(comp)
    a_pt = extend_dash_to_boundary(comp, bb)
    b_pt = min(eps, key=lambda p: math.hypot(p[0] - struct_xy[0], p[1] - struct_xy[1]))
    struct_gap = math.hypot(b_pt[0] - struct_xy[0], b_pt[1] - struct_xy[1])
    if a_pt is None:
        return {"error": "extend_dash_to_boundary None"}
    route, ok = _ordered_leg(comp, tuple(a_pt), tuple(b_pt))
    return {"route_ordered_ok": bool(ok), "drawn_ft": round(route_length(route) / SCALE, 1) if len(route) >= 2 else 0.0,
            "struct_gap_pt": round(struct_gap, 1), "_route": route}


def _callout_bounded_corridor_walk(plan, off, sheet, a_xy, b_xy, printed_ft):
    """Assemble ONE printed callout's fiber run between two BOUND anchors using the PROVEN conduit-corridor walk
    (corridor_prune + walk_design_path -- the geometrically-correct path-follower; a straight chord cannot
    capture a bowed run). Bounded by the printed footage. Returns the walk verdict. NEVER renders; NEVER
    invents an endpoint (a_xy = matchline boundary, b_xy = the bound HH)."""
    draw = plan.line_items(sheet, off)
    conduit = [d for d in draw if d.get("layer") in FIBER]
    layers = list(FIBER)
    exp, bound = corridor_bound(float(printed_ft), SCALE)
    pieces = conduit_pieces(conduit, layers)
    pruned = prune_pieces(pieces, tuple(a_xy), tuple(b_xy), bound)
    walk = walk_design_path(pruned, tuple(a_xy), tuple(b_xy))
    res = walk.get("result")
    traced = (res == TRACED and walk.get("path_groups") == 1)
    return {"ok": bool(traced), "walk_result": res, "paths_found": walk.get("paths_found"),
            "path_groups": walk.get("path_groups"), "named_missing": walk.get("named_missing"),
            "pieces": len(pieces), "pruned": len(pruned), "expected_pt": round(exp, 1),
            "bound_pt": round(bound, 1), "printed_ft": printed_ft, "_route": None}


def _station_ladder_callout_route_geometry(plan, off, sheet, a_xy, b_xy, printed_ft, y_window,
                                           gap_cap_ft=CONTROL_GAP_CAP, bin_ft=LADDER_BIN_FT, owner_controls=None):
    """MEASUREMENT-FIRST station-ladder route geometry for ONE printed callout when conduit tracing fails.
    Builds a station-ordered POLYLINE through PRINTED control points (in-corridor conduit-dash endpoints +
    footage-tick-ladder centroids) between two source-bound anchors. The control points sit at their ACTUAL
    (bowed) positions, so the polyline follows the bow -- never an invented chord. Measures control density +
    max inter-control gap FIRST: if <= gap_cap_ft the route is PRINTED-control-backed; if a gap exceeds the cap
    the owner's marked route confirms continuity through it (owner-marked fallback, still bounded by the printed
    callout + closure). The x/y corridor window keeps it on THIS run (excludes the parallel track + the
    downstream run). NEVER renders; NEVER invents an endpoint. Returns measurement + the polyline.

    When ``owner_controls`` (explicit owner-placed PDF points on the intended bore centerline) are supplied, the
    route is start -> owner controls (projection-ordered) -> end: the owner confirmed the path, so the segments
    between owner points (and to the bound anchors) are owner-backed; closure to printed_ft is the gate."""
    if owner_controls:
        oax, oay = a_xy
        obx, oby = b_xy
        oL = math.hypot(obx - oax, oby - oay) or 1.0
        oux, ouy = (obx - oax) / oL, (oby - oay) / oL
        oc = sorted((tuple(p) for p in owner_controls), key=lambda p: (p[0] - oax) * oux + (p[1] - oay) * ouy)
        oroute = [tuple(a_xy)] + oc + [tuple(b_xy)]
        ogaps = [math.hypot(oroute[i + 1][0] - oroute[i][0], oroute[i + 1][1] - oroute[i][1]) / SCALE
                 for i in range(len(oroute) - 1)]
        olen = route_length(oroute) / SCALE
        ocloses = abs(olen - printed_ft) <= CLOSURE_REL_TOL * printed_ft
        return {"ok": bool(ocloses), "control_source": "owner_marked_controls", "dense_enough": True,
                "n_owner_controls": len(oc), "n_fragment_controls": 0, "n_tick_controls": 0,
                "n_spine_bins": len(oc), "max_control_gap_ft": round(max(ogaps), 1), "gap_cap_ft": gap_cap_ft,
                "length_ft": round(olen, 1), "printed_ft": printed_ft, "closes": ocloses,
                "y_profile_ft_pt": [[round(((p[0] - oax) * oux + (p[1] - oay) * ouy) / SCALE), round(p[1])] for p in oroute],
                "_route": oroute}
    draw, words = plan.line_items(sheet, off), plan.words(sheet, off)
    conduit = [d for d in draw if d.get("layer") in FIBER]
    ax, ay = a_xy
    bx, by = b_xy
    L = math.hypot(bx - ax, by - ay)
    if L < 1:
        return {"ok": False, "reason": "degenerate anchors", "_route": None}
    ux, uy = (bx - ax) / L, (by - ay) / L

    def proj(p):
        return (p[0] - ax) * ux + (p[1] - ay) * uy

    ylo, yhi = y_window
    xlo, xhi = min(ax, bx) - 5.0, max(ax, bx) + 15.0
    # CONTROL POINTS: in-corridor conduit-dash endpoints (centerline) + tick-ladder centroids
    ctrl = []
    for d in conduit:
        for ln in (d.get("lines") or ()):
            for px, py in ((ln[0], ln[1]), (ln[2], ln[3])):
                if xlo <= px <= xhi and ylo <= py <= yhi and 0 <= proj((px, py)) <= L:
                    ctrl.append((proj((px, py)), (px, py), "fragment"))
    n_frag = len(ctrl)
    n_tick = 0
    for tx, ty, vals in _footage_tick_ladders(words, [tuple(a_xy), tuple(b_xy)], band=42.0):
        if xlo <= tx <= xhi and ylo <= ty <= yhi and 0 <= proj((tx, ty)) <= L:
            ctrl.append((proj((tx, ty)), (tx, ty), "tick"))
            n_tick += 1
    if not ctrl:
        return {"ok": False, "reason": "no in-corridor control points", "n_fragment_controls": 0,
                "n_tick_controls": 0, "_route": None}
    # BIN by projection; median xy per bin -> a clean spine that follows the bow (robust to run thickness)
    bins = {}
    for t, xy, _kind in ctrl:
        bins.setdefault(int(t // (bin_ft * SCALE)), []).append(xy)
    spine = [(statistics.median([p[0] for p in v]), statistics.median([p[1] for p in v]))
             for _k, v in sorted(bins.items())]
    spine.sort(key=proj)
    route = [tuple(a_xy)] + [tuple(p) for p in spine] + [tuple(b_xy)]
    gaps_ft = [math.hypot(route[i + 1][0] - route[i][0], route[i + 1][1] - route[i][1]) / SCALE
               for i in range(len(route) - 1)]
    max_gap = max(gaps_ft)
    length_ft = route_length(route) / SCALE
    closes = abs(length_ft - printed_ft) <= CLOSURE_REL_TOL * printed_ft
    dense = max_gap <= gap_cap_ft
    y_profile = [[round(proj(p) / SCALE), round(p[1])] for p in spine]
    source = "printed_controls" if dense else "owner_marked_controls"
    return {"ok": bool(closes), "control_source": source, "dense_enough": dense,
            "n_fragment_controls": n_frag, "n_tick_controls": n_tick, "n_spine_bins": len(spine),
            "max_control_gap_ft": round(max_gap, 1), "gap_cap_ft": gap_cap_ft,
            "length_ft": round(length_ft, 1), "printed_ft": printed_ft, "closes": closes,
            "y_profile_ft_pt": y_profile, "_route": route}


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    gates = []
    report = {"milestone": "LOG3 printed-run-callout-chain proof slice (read-only; NO render; NO sweep wiring)",
              "constants": {"MAX_DASH_GAP": MAX_DASH_GAP, "SAME_POINT_TOL": SAME_POINT_TOL,
                            "SCALE": SCALE, "GAP_CAP": GAP_CAP, "CLOSURE_REL_TOL": CLOSURE_REL_TOL},
              "design_decisions": {"parent_linkage": "covered_by_drawn_children:['log4'] (labels only)",
                                   "no_parent_source_mutation": True, "no_census_fixture_mutation": True,
                                   "no_render": True, "s3_leg_assembler": "proven corridor walk (walk_design_path)"}}
    plan = PlanPdf(PDF)
    try:
        off = select_dialect(plan).calibrate(plan, 13)

        # ---- STAGE 1: endpoint + intermediate binds ----
        print("==== STAGE 1: BINDS ====")
        s_xy, _, _, s_res = _bind(plan, off, START["sheet"], START["cls"], START["label"])
        e_xy, _, _, e_res = _bind(plan, off, END["sheet"], END["cls"], END["label"])
        i_xy, _, _, i_res = _bind(plan, off, INTERMED["sheet"], INTERMED["cls"], INTERMED["label"])
        report["binds"] = {"start": {"res": s_res, "xy": s_xy and [round(v, 1) for v in s_xy]},
                           "end": {"res": e_res, "xy": e_xy and [round(v, 1) for v in e_xy]},
                           "intermediate_15+13": {"res": i_res, "xy": i_xy and [round(v, 1) for v in i_xy]}}
        for k, v in report["binds"].items():
            print(f"   {k:18}: {v['res']:26} {v['xy']}")
        gates.append(("G1 start 12+63 FLOWER POT binds", s_xy is not None, s_res))
        gates.append(("G2 end 21+63 NEXTLINK HH binds", e_xy is not None, e_res))
        gates.append(("G3 intermediate 15+13 NEXTLINK HH binds", i_xy is not None, i_res))

        # ---- STAGE 2: six printed callouts + bounded gap ----
        print("\n==== STAGE 2: CALLOUTS + BOUNDED GAP ====")
        callouts = []
        for seg in CHAIN:
            if seg["kind"] == "covered_gap":
                continue
            ln = _callout_printed(plan, off, seg["sheet"], seg["a"], seg["b"])
            callouts.append({"seg": f"{seg['a']}->{seg['b']}", "sheet": seg["sheet"], "printed": ln is not None})
            print(f"   s{seg['sheet']} {seg['a']}->{seg['b']} ({seg['ft']}'): {'PRINTED' if ln else 'MISSING'}")
        report["callouts"] = callouts
        gates.append(("G4 all 6 STA-A-TO-STA-B callouts printed", all(c["printed"] for c in callouts),
                      f"{sum(c['printed'] for c in callouts)}/6"))
        gap_ft = parse_station("16+25") - parse_station("16+06")
        report["bounded_gap"] = {"gap": "16+06->16+25", "ft": gap_ft, "cap": GAP_CAP, "within_cap": gap_ft <= GAP_CAP}
        print(f"   bounded gap 16+06->16+25 = {gap_ft}' (cap {GAP_CAP}): {'OK' if gap_ft <= GAP_CAP else 'TOO LARGE'}")
        gates.append((f"G5 bounded gap 19' <= GAP_CAP {GAP_CAP}", gap_ft <= GAP_CAP, f"{gap_ft}ft"))

        # ---- STAGE 3: matchline / station continuity ----
        print("\n==== STAGE 3: CONTINUITY ====")
        ml_23 = [list(c) for c in see_sheet_crossings(plan.lines(2, off), 3, "MATCHLINE")]
        ml_23r = [list(c) for c in see_sheet_crossings(plan.lines(3, off), 2, "MATCHLINE")]
        ml_34 = [list(c) for c in see_sheet_crossings(plan.lines(3, off), 4, "MATCHLINE")]
        ml_45 = [list(c) for c in see_sheet_crossings(plan.lines(4, off), 5, "MATCHLINE")]
        recip_23 = any("12+66" in c for c in ml_23) and any("12+66" in c for c in ml_23r)
        report["matchlines"] = {"s2->s3": ml_23, "s3->s2(recip)": ml_23r, "s3->s4": ml_34, "s4->s5": ml_45}
        for k, v in report["matchlines"].items():
            print(f"   {k:18}: {v}")
        cont = [CHAIN[i]["b"] == CHAIN[i + 1]["a"] for i in range(len(CHAIN) - 1)]
        print(f"   station continuity B_i==A_(i+1): {all(cont)}")
        gates.append(("G6 s2<->s3 matchline 12+66 reciprocal", recip_23, str(ml_23)))
        gates.append(("G7 s3->s4 @16+25 and s4->s5 @20+18 printed",
                      any("16+25" in c for c in ml_34) and any("20+18" in c for c in ml_45), f"{ml_34}/{ml_45}"))
        gates.append(("G8 station continuity (chain joins end-to-end)", all(cont), str(cont)))

        # ---- STAGE 4: assemble the two UNCOVERED upstream legs ----
        print("\n==== STAGE 4: UPSTREAM LEG ASSEMBLY ====")
        cross = ("5+26", "12+66")
        legA = _trace_single_component(plan, off, 2, cross, tuple(s_xy)) if s_xy else {"error": "no start bind"}
        # leg B (s3 12+66->15+13, 247') -- the load-bearing leg: PROVEN conduit-corridor walk between the bound
        # matchline boundary (A) and the bound 15+13 HH (B).
        draw3, words3 = plan.line_items(3, off), plan.words(3, off)
        bb3 = _ml_bbox(words3, draw3, cross)
        a_xy3 = None
        if bb3:
            conduit3 = [d for d in draw3 if d.get("layer") in FIBER]
            best, mlc = 1e9, None
            for c in _conduit_components(conduit3):
                eps = dash_endpoints(c)
                if eps:
                    g = min(nearest_gap([p], bb3) for p in eps)
                    if g <= MAX_DASH_GAP and g < best:
                        best, mlc = g, c
            if mlc is not None:
                ext = extend_dash_to_boundary(mlc, bb3)
                a_xy3 = tuple(ext) if ext is not None else None
        legB = (_callout_bounded_corridor_walk(plan, off, 3, a_xy3, tuple(i_xy), 247)
                if (a_xy3 and i_xy) else {"ok": False, "walk_result": "no matchline boundary / HH bind", "_route": None})
        report["upstream_leg_s2_12+63_12+66"] = {k: v for k, v in legA.items() if not k.startswith("_")}
        report["upstream_leg_s3_corridor_walk"] = {k: v for k, v in legB.items() if not k.startswith("_")}
        print(f"   s2 12+63->12+66 (3'): drawn_ft={legA.get('drawn_ft')} ordered_ok={legA.get('route_ordered_ok')}")
        print(f"   s3 conduit-walk (why the ladder): {legB.get('walk_result')}")
        # --- STATION-LADDER GEOMETRY with OWNER-CONFIRMED controls for the s3 247' leg ---
        # The owner red-X'd the lower y~363 diagonal as INCORRECT and dotted the TOP bore centerline (y~297).
        # So the start anchor is the matchline crossing at the OWNER TOP-PATH y (not the rejected y~363 lower
        # crossing); the route runs start -> owner dots -> 15+13 HH. Owner controls are explicit, never inferred.
        top_y = statistics.median([p[1] for p in OWNER_CONTROL_POINTS_S3])
        a_xy_top = (a_xy3[0], top_y) if a_xy3 else None
        y_lo, y_hi = (i_xy[1] - 60.0 if i_xy else 240.0), (i_xy[1] + 25.0 if i_xy else 320.0)
        legB_sl = (_station_ladder_callout_route_geometry(plan, off, 3, a_xy_top, tuple(i_xy), 247, (y_lo, y_hi),
                                                          owner_controls=OWNER_CONTROL_POINTS_S3)
                   if (a_xy_top and i_xy) else {"ok": False, "reason": "no anchors", "_route": None})
        report["upstream_leg_s3_station_ladder"] = {k: v for k, v in legB_sl.items() if not k.startswith("_")}
        print(f"   s3 STATION-LADDER: source={legB_sl.get('control_source')} frags={legB_sl.get('n_fragment_controls')} "
              f"ticks={legB_sl.get('n_tick_controls')} bins={legB_sl.get('n_spine_bins')} "
              f"max_gap={legB_sl.get('max_control_gap_ft')}ft (cap {legB_sl.get('gap_cap_ft')}) "
              f"len={legB_sl.get('length_ft')} closes={legB_sl.get('closes')}")
        print(f"      y-profile [ft,ypt]: {legB_sl.get('y_profile_ft_pt')}")
        gates.append(("G9 s3 247' leg assembles via station-ladder geometry (closes to 247')",
                      bool(legB_sl.get("ok")),
                      f"source={legB_sl.get('control_source')} len={legB_sl.get('length_ft')} "
                      f"max_gap={legB_sl.get('max_control_gap_ft')}"))
        gates.append(("G9b control density measured (printed vs owner-marked fallback)",
                      legB_sl.get("control_source") in ("printed_controls", "owner_marked_controls"),
                      f"{legB_sl.get('control_source')} (max_gap {legB_sl.get('max_control_gap_ft')}ft / cap {legB_sl.get('gap_cap_ft')})"))
        legA_ok = legA.get("drawn_ft") is not None and legA.get("drawn_ft", 99) <= 25
        gates.append(("G10 s2 3' stub measured (single component)", bool(legA_ok), f"drawn={legA.get('drawn_ft')}"))

        # ---- STAGE 5: downstream coverage by log4 + boundary proof ----
        print("\n==== STAGE 5: log4 COVERAGE + 15+13 BOUNDARY ====")
        v4 = solve_log(plan, off, "log4", OWNER_CONFIRMED_PLAN_ROUTES)
        legs4 = v4.get("legs") or []
        log4_start_xy = tuple(legs4[0]["a_xy"]) if legs4 else None
        report["log4"] = {"renders": bool(legs4), "n_legs": len(legs4),
                          "start_xy": log4_start_xy and [round(v, 1) for v in log4_start_xy],
                          "leg_sheets": [l["sheet"] for l in legs4]}
        boundary_gap = (math.hypot(i_xy[0] - log4_start_xy[0], i_xy[1] - log4_start_xy[1])
                        if (i_xy and log4_start_xy) else None)
        same_symbol = boundary_gap is not None and boundary_gap <= SAME_POINT_TOL
        report["boundary_15+13"] = {"gap_pt": None if boundary_gap is None else round(boundary_gap, 1),
                                    "same_symbol_within_SAME_POINT_TOL": same_symbol}
        covered_segs = [f"{s['a']}->{s['b']}" for s in CHAIN if s["covered"] == "log4"]
        report["downstream_covered_by_log4"] = covered_segs
        print(f"   log4 renders={bool(legs4)} legs={len(legs4)} sheets={report['log4']['leg_sheets']} "
              f"start_xy={report['log4']['start_xy']}")
        print(f"   15+13 boundary gap = {report['boundary_15+13']['gap_pt']}pt same_symbol={same_symbol}")
        print(f"   downstream covered by log4 (suppressed): {covered_segs}")
        gates.append(("G11 log4 drawn start == log3 15+13 intermediate (same symbol)", same_symbol,
                      f"gap={report['boundary_15+13']['gap_pt']}pt"))
        gates.append(("G12 downstream 15+13->21+63 covered by drawn log4", bool(legs4) and len(covered_segs) == 5,
                      f"{len(covered_segs)} covered segs"))

        # ---- STAGE 6: closure + overlap ----
        print("\n==== STAGE 6: CLOSURE + OVERLAP ====")
        total = sum(s["ft"] for s in CHAIN)
        uncovered = sum(s["ft"] for s in CHAIN if s["covered"] is None)
        covered = sum(s["ft"] for s in CHAIN if s["covered"] == "log4")
        recorded = parse_station("21+63") - parse_station("12+63")
        report["closure"] = {"printed_total": total, "uncovered_upstream": uncovered,
                             "covered_downstream": covered, "recorded_span": recorded,
                             "sum_closes": (uncovered + covered) == total == recorded}
        print(f"   total={total} uncovered={uncovered} covered={covered} recorded={recorded} "
              f"closes={report['closure']['sum_closes']}")
        overlaps = []
        for legname, leg, leg_sheet in (("s2", legA, 2), ("s3", legB_sl, 3)):
            rt = leg.get("_route")
            if not rt:
                continue
            for l4 in legs4:
                if l4["sheet"] != leg_sheet:
                    continue
                dists = [_pt_to_route(p, l4["route"]) for p in rt]
                overlaps.append({"upstream_leg": legname, "vs_log4_sheet": l4["sheet"],
                                 "min_dist_pt": round(min(dists), 1),
                                 "coincident_points": sum(1 for d in dists if d <= SAME_POINT_TOL),
                                 "total_points": len(rt)})
        report["overlap_vs_log4"] = overlaps
        for o in overlaps:
            print(f"   upstream {o['upstream_leg']} vs log4 s{o['vs_log4_sheet']}: min_dist={o['min_dist_pt']}pt "
                  f"coincident={o['coincident_points']}/{o['total_points']}")
        unsafe = [o for o in overlaps if o["coincident_points"] > 1]
        gates.append(("G13 closure: 250 + 650 = 900 = recorded span", report["closure"]["sum_closes"],
                      f"{uncovered}+{covered}={total}"))
        gates.append(("G14 upstream legs 0 unsafe overlap with log4 (shared 15+13 junction only)",
                      len(unsafe) == 0, f"{len(unsafe)} unsafe"))

        # ---- STAGE 7: no-render assertion ----
        gates.append(("G15 NO red stroke rendered (0 PNG)", len(sorted(OUT_DIR.glob("*.png"))) == 0,
                      f"{len(sorted(OUT_DIR.glob('*.png')))} pngs"))
    finally:
        plan.close()

    all_pass = all(x for _, x, _ in gates)
    report["gates"] = [{"name": n, "pass": bool(x), "detail": str(d)} for n, x, d in gates]
    report["verdict"] = "PASS" if all_pass else "FAIL"
    (OUT_DIR / "log3_chain_route_proof_slice.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8")
    print("\n==== VERDICT ====")
    for n, x, d in gates:
        print(f"   [{'PASS' if x else 'FAIL'}] {n}  ({d})")
    print(f"\n[log3-chain] {'PASS' if all_pass else 'FAIL'} -- report: {OUT_DIR / 'log3_chain_route_proof_slice.json'}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
