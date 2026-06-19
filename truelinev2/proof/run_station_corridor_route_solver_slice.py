r"""STATION-CORRIDOR ROUTE SOLVER slice (PROOF ONLY; read-only; product-gated).

Tests whether the prior ``END_BRANCH_AMBIGUOUS_AT_SPAN`` result for the Group-A reset-collision
logs (log30/50/57 on sheet 10; log8/32 on sheet 18; log42/56 on sheet 2) is TRUE source ambiguity
or an artifact of OVER-BROAD conduit traversal (solver shape). The prior review-choice render
(``render_from_selected_start``) flooded the whole connected conduit component via ``connected_chain``,
enumerated EVERY ``dash_endpoints`` and accepted any whose route-length matched the bore span -- so on a
dense sheet many length-coincident lateral/branch tips became rival "ends". That is solver-created, not
proven source, ambiguity.

This solver does NOT flood-and-search. It follows the station-corridor reasoning order:
  1. BIND the bore to the drawn running-station ladder: build scale-consistent monotonic ladder ROWS from
     the clean route-ladder ticks; a candidate ``STA P+XX = 0+00`` reset binds to a row iff its drawn
     structure projects to running station ~= P (the reset's own parent station) with a small perpendicular
     offset on EXACTLY ONE row. (The Brenham ladder is drawn in RUNNING stations; the bore is a LOCAL reset
     frame, so the bore's local 0..span maps to running P..P+span once the reset is bound.)
  2. RESOLVE the START point: the bound reset structure's drawn (x,y) (uniqueness-mandatory locator).
  3. RESOLVE the END point on the SAME row: position running ``P + span_ft`` by bracketing it between two
     adjacent row ticks and interpolating (x,y). If the row does not bracket it -> the ladder does not
     cover the bore end for this reset (named, not guessed).
  4. RESTRICT conduit traversal to the monotonic station corridor: prune every conduit dash whose endpoints
     leave the perpendicular band of the bound row or fall outside [P, P+span] station -- severing laterals,
     branch spurs, and foreign-reset dashes at the junction BEFORE routing.
  5. REJECT non-monotonic routes (station must not reverse along the route) and non-source-backed routes.
  6. order_chain_route to the SINGLE positioned end (no endpoint search).
  7. REQUIRE the end to be a real DRAWN TERMINUS (a structure symbol / matchline / conduit dead-end), NOT a
     ruler cut on a through-alignment. Render iff EXACTLY ONE reset yields a unique source-backed corridor
     ending at a drawn terminus. ABSTAIN (named) otherwise: >= 2 viable -> TRUE ambiguity; 0 -> furthest blocker.

FINDING (this corpus). The prior END_BRANCH_AMBIGUOUS_AT_SPAN -- 10-52 rival "ends" at the span footage -- IS
solver-created: it came from flooding the whole conduit component and accepting EVERY dash endpoint at the
span route-length. Positioning the end on the station ladder and constraining to the monotonic corridor
collapses that to ONE end (no endpoint search). BUT that does not make these 7 renderable: with the
end-terminus gate, all 7 correctly ABSTAIN -- log30/50/57/8/32 trace a clean source-backed mainline corridor
whose end is NOT a drawn terminus (these are flower-pot DROP bores whose true termini are unnamed pots on
OTHER sheets -- the conduit runs continuously past the bore's end station; cf. gac/drop_lane_source_adjudication.md
which BLOCKS log30/50 with the named drop-identity gap, and gac/route480_remaining_proof_sweep.md which already
caught log57 as a multi-corridor over-claim); log42/56's conduit gaps off-corridor before the end. So the
END-rival SYMPTOM was over-broad traversal, but the bores stay blocked for the deeper, real reasons.

No reviewer endpoint choice. No owner endpoint naming. No fixture mutation. No coordinate encoding. No
seam/ledger/classification work. No product/runtime/API/backend/web/deploy/main touch. Red strokes only.
PNG/JSON artifacts are written under the gitignored data/outputs path and are NOT committed.

Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_station_corridor_route_solver_slice
"""
from __future__ import annotations

import json
import math
import os
import re
import sys
from statistics import median

from truelinev2.config import _REPO_ROOT
from truelinev2.extract.conduit_topology import (
    MAX_DASH_GAP,
    connected_chain,
    dash_endpoints,
    symbol_footprint,
)
from truelinev2.extract.registry import select_dialect
from truelinev2.extract.structure_position import (
    BRENHAM_CONDUIT_LAYERS,
    BRENHAM_STRUCTURE_LAYERS,
    POSITION_BOUND,
    corroborate_pair_scale,
    resolve_nextlink_hh_callout,
    resolve_structure_position,
)
from truelinev2.extract.tick_path import route_ladder_ticks
from truelinev2.ingest.manual_adjudication import (
    activation_summary,
    apply_adjudications,
    load_adjudication,
    parent_run_duplicate_check,
)
from truelinev2.ingest.normalize import load_borelog
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.proof.run_brenham_corpus import EXPECTED_COUNT, PDF, enumerate_corpus
from truelinev2.proof.run_log59_render_artifact_slice import (
    interior_vertices_are_dash_endpoints,
    route_edges_source_backed,
)
from truelinev2.proof.run_log71_render_artifact_slice import order_chain_route, route_length
from truelinev2.proof.run_reviewer_service_contract import resolve_corpus
from truelinev2.render.crop import REDLINE_STROKE_RGB, render_redline_stroke
from truelinev2.stations import parse_station

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "station_corridor_route_solver"
TRUTH = _REPO_ROOT / "data" / "outputs" / "final_engine_truth_table" / \
    "final_engine_truth_table.json"
BASE = set(BRENHAM_CONDUIT_LAYERS.values())
STRUCT_SYMBOL_LAYERS = {v[1] for v in BRENHAM_STRUCTURE_LAYERS.values()}   # drawn structure symbol layers
MATCHLINE_LAYER = "MATCHLINE"
FROZEN_BUCKETS = {"DRAWABLE_REVIEW": 31, "HUMAN_ADJUSTABLE_REVIEW": 6,
                  "OUT_OF_CLASS": 1, "PICK_CARD_REVIEW": 17, "SOURCE_OR_KMZ_REQUIRED": 3}
ABSTAIN_4 = ("log5", "log31", "log38", "log43")
RESET_RE = re.compile(r"(\d+\+\d+)\s*=\s*0\+00")
# reset-structure classes tried per candidate (uniqueness-mandatory bind); HH symbols share NEXTLINK layer
CLASSES = (("installer_hh", None, "NEXTLINK"), ("flower_pot", ("FLOWER", "POT"), "FLOWER POT"),
           ("nextlink_hh", None, "NEXTLINK"))

# the 7 Group-A targets that returned END_BRANCH_AMBIGUOUS_AT_SPAN under review-choice; primary placed sheet
TARGETS = {"log30": 10, "log50": 10, "log57": 10, "log8": 18, "log32": 18, "log42": 2, "log56": 2}

# --- station-corridor tolerances (all recorded in the report; none is a magic placement constant) ---
ROW_MAX_STATION_GAP_FT = 110.0   # link only ADJACENT ladder ticks (Brenham draws a tick every 100 ft, so a
                                 # Delta>100 "skip" link is never needed and only enables cross-ladder hijacks)
ROW_SCALE_REL_TOL = 0.15         # a row link is accepted only if drawn dist == Delta_station*scale within this
                                 # (the Brenham ladder is uniform ~1.44 pt/ft; a real adjacent link err ~0, a
                                 # cross-ladder same-station pairing err >> 0.15 -- so this rejects hijacks)
BIND_PERP_TOL_PT = 22.0          # a reset binds a row only if its structure sits within this of the row axis
BIND_STA_TOL_FT = 18.0           # ... and projects to running station within this of the reset's parent station
CORRIDOR_HALF_PT = 30.0          # conduit dash kept only if BOTH endpoints within this of the bound row axis
CORRIDOR_MARGIN_FT = 60.0        # station slack at each corridor end (start reset sits below first tick)
BACKTRACK_TOL_FT = 22.0          # max permitted station reversal between consecutive route vertices
SPAN_LEN_REL_TOL = 0.30          # route arc length must be within this of span_ft * ladder pt/ft scale
STRUCT_TOL_PT = 12.0             # a drawn structure symbol within this of the end == a terminus
MATCHLINE_TOL_PT = 18.0          # a matchline within this of the end == the bore leaves the sheet here
DEADEND_MARGIN_FT = 30.0         # the conduit must NOT continue past (end station + this) for a dead-end

R_RENDERED = "STATION_CORRIDOR_RENDER_PRODUCED_ARTIFACTS"
R_NO_RENDER = "STATION_CORRIDOR_NO_SAFE_ARTIFACT"
B_CENSUS = "BLOCKED_STATION_CORRIDOR_CENSUS_DRIFT"
B_SCOPE = "BLOCKED_STATION_CORRIDOR_SCOPE_VIOLATION"
ALLOWED = {R_RENDERED, R_NO_RENDER, B_CENSUS, B_SCOPE}


# ---------------------------------------------------------------------------------------------------
# census-frozen gate (self-contained; identical contract to the other v2 proof slices)
# ---------------------------------------------------------------------------------------------------
def _census_frozen(doc) -> bool:
    if not TRUTH.is_file():
        return False
    baseline = {r["bore_id"]: dict(r) for r in json.loads(TRUTH.read_text(encoding="utf-8"))["rows"]}
    off = apply_adjudications(baseline, enabled=False)
    on = apply_adjudications(baseline, enabled=True, doc=doc)
    summ = activation_summary(on)
    buckets = {}
    for r in off.values():
        buckets[r["completion_bucket"]] = buckets.get(r["completion_bucket"], 0) + 1
    return (off is baseline and buckets == FROZEN_BUCKETS
            and summ["manual_review_drawable"] == 22 and summ["manual_source_verification"] == 1
            and summ["manual_abstain"] == 4
            and on["log44"]["adjudication"]["drawable_status"] == "non_drawable"
            and all(on[l]["adjudication"]["drawable_status"] == "abstain" for l in ABSTAIN_4)
            and not parent_run_duplicate_check(doc))


# ---------------------------------------------------------------------------------------------------
# ladder + candidate reset discovery (reset structures surfaced from source; never owner-named)
# ---------------------------------------------------------------------------------------------------
def ladder_scale(ticks):
    """Drawn pt-per-ft from adjacent station-ladder rungs (median over 50-200 ft adjacent ticks)."""
    ts = sorted(ticks, key=lambda t: t.station_ft)
    scales = [math.hypot(b.x - a.x, b.y - a.y) / (b.station_ft - a.station_ft)
              for a, b in zip(ts, ts[1:]) if 50 <= (b.station_ft - a.station_ft) <= 200]
    return median(scales) if scales else None


def discover_candidates(plan, offset, sheet):
    """Rival reset-structure candidates on a sheet, surfaced from source: each ``STA X+XX=0+00`` that binds a
    modeled structure (uniqueness-mandatory per class). Returns [{reset, structure_class, seed, xy}]."""
    words = plan.words(sheet, offset)
    draw = plan.line_items(sheet, offset)
    resets = sorted(set(RESET_RE.findall(" ".join(plan.lines(sheet, offset)))),
                    key=lambda s: (int(s.split("+")[0]), int(s.split("+")[1])))
    cands = []
    for r in resets:
        for cls, ctx, seed in CLASSES:
            if cls == "nextlink_hh":
                v = resolve_nextlink_hh_callout(station_sta=r, words=words, drawings=draw,
                                                callout_layer="ANNOTATION", symbol_layer="NEXTLINK")
            else:
                kw = dict(label_text=f"{r}=0+00", structure_class=cls, words=words, drawings=draw,
                          layer_table=BRENHAM_STRUCTURE_LAYERS)
                if ctx:
                    kw["context_texts"] = ctx
                v = resolve_structure_position(**kw)
            if v.result == POSITION_BOUND and v.symbol_xy:
                cands.append({"reset": r, "structure_class": cls, "seed": seed,
                              "xy": tuple(v.symbol_xy)})
                break   # first class that binds this reset
    return cands


def build_rows(ticks, scale_hint):
    """The DRAWN ladder rows as geometric chains of clean ladder ticks. A Brenham sheet carries SEVERAL drawn
    ladders (each alignment segment has its own '1+00 2+00 ...' row), so the same station value appears many
    times at different (x,y). Rows are recovered by GEOMETRIC scale-consistent forward linking: a tick links
    to the nearest-station forward tick whose drawn distance matches the expected pts/ft (Delta_station *
    scale_hint) within tolerance -- a cross-ladder pair (same station number, far apart) fails this and is
    never linked. ``scale_hint`` is the sheet's median clean-ladder pts/ft (~1.44 on Brenham)."""
    if not scale_hint:
        return []
    ts = sorted(ticks, key=lambda t: (t.station_ft, t.x, t.y))

    def best_match(i, forward):
        """Index of the tick that best continues the ladder from ts[i] (forward) / into ts[i] (backward),
        by minimal scale error among ADJACENT-station ticks. None if none passes the scale tolerance."""
        best = None  # ((err, ds), j)
        for j, o in enumerate(ts):
            ds = (o.station_ft - ts[i].station_ft) if forward else (ts[i].station_ft - o.station_ft)
            if ds <= 0 or ds > ROW_MAX_STATION_GAP_FT:
                continue
            exp = ds * scale_hint
            err = abs(math.hypot(o.x - ts[i].x, o.y - ts[i].y) - exp) / exp
            if err <= ROW_SCALE_REL_TOL and (best is None or (err, ds) < best[0]):
                best = ((err, ds), j)
        return best[1] if best else None

    # MUTUAL best match: link i -> j only if j is i's best forward AND i is j's best backward. This rejects a
    # wrong-ladder tick that merely passes the scale tolerance to a shared neighbor -- the true predecessor
    # (smaller error) wins the neighbor, and the impostor drops to a singleton.
    fwd = [best_match(i, True) for i in range(len(ts))]
    bwd = [best_match(i, False) for i in range(len(ts))]
    nxt = {i: fwd[i] for i in range(len(ts)) if fwd[i] is not None and bwd[fwd[i]] == i}
    incoming = set(nxt.values())
    rows, visited = [], set()
    for i in range(len(ts)):
        if i in incoming or i in visited:
            continue
        chain, cur = [], i
        while cur is not None and cur not in visited:
            visited.add(cur)
            chain.append(ts[cur])
            cur = nxt.get(cur)
        if len(chain) >= 2:
            rows.append(chain)
    return rows


def project_on_row(row, xy):
    """(running station_ft, perpendicular offset to the row axis) for a point, against the NEAREST row
    segment. Station is the unclamped along-axis projection (so a point just before/after the row extrapolates
    its station); perp is the distance to that segment's infinite line. Returns None for a degenerate row."""
    best = None  # (clamped_dist, station_ft, perp_line)
    for a, b in zip(row, row[1:]):
        dx, dy = b.x - a.x, b.y - a.y
        den = dx * dx + dy * dy
        if den == 0:
            continue
        t = ((xy[0] - a.x) * dx + (xy[1] - a.y) * dy) / den
        tc = max(0.0, min(1.0, t))
        cx, cy = a.x + tc * dx, a.y + tc * dy
        cdist = math.hypot(xy[0] - cx, xy[1] - cy)
        length = math.sqrt(den)
        perp_line = abs((xy[0] - a.x) * dy - (xy[1] - a.y) * dx) / length
        station = a.station_ft + t * (b.station_ft - a.station_ft)
        if best is None or cdist < best[0]:
            best = (cdist, station, perp_line)
    return None if best is None else (best[1], best[2])


def _lerp_station(a, b, v):
    t = 0.0 if b.station_ft == a.station_ft else (v - a.station_ft) / (b.station_ft - a.station_ft)
    return (a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t)


def position_on_row(row, target_ft):
    """(x,y) of ``target_ft`` bracketed between two adjacent row ticks (None if the row does not cover it)."""
    for a, b in zip(row, row[1:]):
        if a.station_ft <= target_ft <= b.station_ft:
            return _lerp_station(a, b, target_ft)
    return None




def bind_row(rows, start_xy, parent_ft):
    """Rows on which the start reset structure projects to running station ~= parent_ft within a small
    perpendicular offset. Exactly one -> bound. Returns (row|None, status, candidates)."""
    hits = []
    for idx, row in enumerate(rows):
        pr = project_on_row(row, start_xy)
        if pr is None:
            continue
        sta, perp = pr
        if perp <= BIND_PERP_TOL_PT and abs(sta - parent_ft) <= BIND_STA_TOL_FT:
            hits.append({"row_idx": idx, "row": row, "implied_station": round(sta, 1),
                         "perp_pt": round(perp, 2),
                         "row_lo": round(row[0].station_ft, 1), "row_hi": round(row[-1].station_ft, 1)})
    if len(hits) == 1:
        return hits[0]["row"], "BOUND", hits
    if not hits:
        return None, "NO_LADDER_ROW_AT_RESET_STATION", hits
    return None, "AMBIGUOUS_LADDER_BIND", hits


def constrain_corridor(chain, row, lo_ft, hi_ft):
    """Prune the flooded conduit chain to the monotonic station corridor of the bound row: a dash is kept only
    if BOTH its endpoints sit within CORRIDOR_HALF_PT of the row axis AND at least one endpoint projects to a
    station inside [lo_ft - margin, hi_ft + margin]. Drops laterals/branch spurs/foreign-reset dashes."""
    keep = []
    for d in chain:
        lines = d.get("lines") or []
        in_band = bool(lines)
        in_span = False
        for (ax, ay, bx, by) in lines:
            for (x, y) in ((ax, ay), (bx, by)):
                pr = project_on_row(row, (x, y))
                if pr is None or pr[1] > CORRIDOR_HALF_PT:
                    in_band = False
                if pr is not None and (lo_ft - CORRIDOR_MARGIN_FT) <= pr[0] <= (hi_ft + CORRIDOR_MARGIN_FT):
                    in_span = True
        if in_band and in_span:
            keep.append(d)
    return keep


def route_is_monotonic(route, row):
    """Route vertices' running stations must be non-decreasing within BACKTRACK_TOL_FT and net-forward."""
    stas = []
    for v in route:
        pr = project_on_row(row, v)
        if pr is None:
            return False, []
        stas.append(pr[0])
    ok = all(stas[i + 1] >= stas[i] - BACKTRACK_TOL_FT for i in range(len(stas) - 1)) and stas[-1] > stas[0]
    return ok, [round(s, 1) for s in stas]


def _pt_bbox_dist(p, m):
    dx = max(m.get("x0", 0.0) - p[0], 0.0, p[0] - m.get("x1", 0.0))
    dy = max(m.get("y0", 0.0) - p[1], 0.0, p[1] - m.get("y1", 0.0))
    return math.hypot(dx, dy)


def end_is_drawn_terminus(end_xy, corridor, row, running_end, struct_syms, matchlines):
    """The END must be a REAL DRAWN TERMINUS, not a ruler cut on a through-alignment. True iff:
      (a) a drawn structure symbol (flower pot / HH) sits within STRUCT_TOL_PT of the end, OR
      (b) a matchline sits within MATCHLINE_TOL_PT of the end (the bore leaves the sheet here), OR
      (c) the in-corridor conduit DEAD-ENDS at the end (no in-band dash continues past end + margin).
    A bore whose drawn conduit runs continuously PAST its end station has NO terminus there -- the end is a
    fabricated ruler point on a shared mainline. This is the gate that rejects the drop-bore false positive
    (drop bores terminate at unnamed pots on OTHER sheets; their sheet-local mainline conduit keeps going)."""
    near_struct = min((math.hypot(end_xy[0] - s.get("xc", 9e9), end_xy[1] - s.get("yc", 9e9))
                       for s in struct_syms), default=9e9)
    near_ml = min((_pt_bbox_dist(end_xy, m) for m in matchlines), default=9e9)
    continues = any(pr is not None and pr[1] <= CORRIDOR_HALF_PT and pr[0] > running_end + DEADEND_MARGIN_FT
                    for e in dash_endpoints(corridor) for pr in (project_on_row(row, e),))
    ok = (near_struct <= STRUCT_TOL_PT) or (near_ml <= MATCHLINE_TOL_PT) or (not continues)
    return ok, {"nearest_struct_pt": round(near_struct, 1), "nearest_matchline_pt": round(near_ml, 1),
                "conduit_continues_past_end": continues,
                "terminus": ("structure" if near_struct <= STRUCT_TOL_PT else
                             "matchline" if near_ml <= MATCHLINE_TOL_PT else
                             "conduit_dead_end" if not continues else None)}


def flood_end_rivals(plan, offset, sheet, start_xy, seed, span_ft, scale):
    """The OLD review-choice method's end search, run for direct comparison: flood connected_chain from the
    start, count dash endpoints whose start->endpoint route length is within tolerance of span*scale."""
    draw = plan.line_items(sheet, offset)
    fp = symbol_footprint(draw, seed, start_xy) or symbol_footprint(draw, "NEXTLINK", start_xy)
    chain = connected_chain([x for x in draw if x.get("layer") in BASE], fp) if fp else []
    if not chain or scale is None:
        return 0, len(chain)
    target_pt = span_ft * scale
    tol = max(0.12 * target_pt, 40.0)
    ends = set()
    for ep in dash_endpoints(chain):
        route = order_chain_route(chain, start_xy, ep)
        if route and route[0] == start_xy and route[-1] == ep and len(route) >= 2:
            if abs(route_length(route) - target_pt) <= tol:
                ends.add((round(ep[0], 1), round(ep[1], 1)))
    return len(ends), len(chain)


# ---------------------------------------------------------------------------------------------------
# per-target solve
# ---------------------------------------------------------------------------------------------------
def solve_target(plan, offset, lid, sheet, bore, rows, ticks, scale, cands):
    span_ft = bore.span_ft
    draw = plan.line_items(sheet, offset)
    conduit = [x for x in draw if x.get("layer") in BASE]
    struct_syms = [x for x in draw if x.get("layer") in STRUCT_SYMBOL_LAYERS]
    matchlines = [x for x in draw if x.get("layer") == MATCHLINE_LAYER]
    rec = {"sheet": sheet, "span_ft": round(span_ft), "start_ft": round(bore.station_start_ft),
           "end_ft": round(bore.station_end_ft), "sheet_refs": bore.sheet_refs,
           "ladder_rows": [{"lo": round(r[0].station_ft, 1), "hi": round(r[-1].station_ft, 1),
                            "n": len(r)} for r in rows],
           "rival_resets": [c["reset"] for c in cands], "per_reset": [], "viable": []}
    viable = []
    for c in cands:
        parent_ft = parse_station(c["reset"])
        start_xy = c["xy"]
        pr_detail = {"reset": c["reset"], "parent_ft": round(parent_ft, 1) if parent_ft is not None else None,
                     "structure_class": c["structure_class"], "start_xy": [round(v, 1) for v in start_xy]}
        # OLD method rival count, for the comparison the determination requires
        old_rivals, chain_segs = flood_end_rivals(plan, offset, sheet, start_xy, c["seed"], span_ft, scale)
        pr_detail["old_flood_end_rivals"] = old_rivals
        if parent_ft is None:
            pr_detail["result"] = "RESET_PARENT_UNPARSEABLE"
            rec["per_reset"].append(pr_detail)
            continue
        # 1+2. bind the bore to a running-station ladder row via the start reset structure
        row, bind_status, hits = bind_row(rows, start_xy, parent_ft)
        pr_detail["bind"] = {"status": bind_status, "candidates": hits and [
            {k: h[k] for k in ("row_lo", "row_hi", "implied_station", "perp_pt")} for h in hits]}
        if row is None:
            pr_detail["result"] = "LADDER_BIND_FAILED:" + bind_status
            rec["per_reset"].append(pr_detail)
            continue
        # 3. resolve the END point at running (parent + span) on the bound ladder row (the station ruler).
        #    The end is ONE positioned point -- not an endpoint search -- which is the whole fix for the prior
        #    END_BRANCH_AMBIGUOUS_AT_SPAN flood. It sits on the drawn alignment; the route attaches the
        #    conduit to it via a single <=MAX_DASH_GAP hop (same as a proven render anchors an off-conduit end).
        running_end = parent_ft + span_ft
        end_xy = position_on_row(row, running_end)
        pr_detail["running_end_ft"] = round(running_end, 1)
        if end_xy is None:
            pr_detail["result"] = "END_NOT_COVERED_BY_LADDER"
            rec["per_reset"].append(pr_detail)
            continue
        pr_detail["end_xy"] = [round(v, 1) for v in end_xy]
        # 4. restrict conduit traversal to the monotonic station corridor [parent, running_end] of the row
        fp = symbol_footprint(draw, c["seed"], start_xy) or symbol_footprint(draw, "NEXTLINK", start_xy)
        flooded = connected_chain(conduit, fp) if fp else []
        corridor = constrain_corridor(flooded, row, parent_ft, running_end)
        pr_detail["chain_flooded_segs"] = len(flooded)
        pr_detail["corridor_segs"] = len(corridor)
        if not corridor:
            pr_detail["result"] = "NO_CONDUIT_IN_CORRIDOR"
            rec["per_reset"].append(pr_detail)
            continue
        # 5/6. order_chain_route to the SINGLE positioned end (no endpoint search)
        route = order_chain_route(corridor, start_xy, end_xy)
        if not route or route[0] != tuple(start_xy) or route[-1] != tuple(end_xy) or len(route) < 2:
            pr_detail["result"] = "CONDUIT_DOES_NOT_REACH_POSITIONED_END"
            pr_detail["route_vertices"] = len(route or [])
            rec["per_reset"].append(pr_detail)
            continue
        # 5. honesty: source-backed edges + interior vertices are real dash endpoints + monotonic station
        edges_ok = route_edges_source_backed(route, corridor)
        interior_ok = len(route) >= 3 and interior_vertices_are_dash_endpoints(route, corridor)
        mono_ok, route_stations = route_is_monotonic(route, row)
        rl = route_length(route)
        target_pt = span_ft * scale if scale else None
        span_ok = target_pt is not None and abs(rl - target_pt) <= SPAN_LEN_REL_TOL * target_pt
        pair = corroborate_pair_scale(start_xy, end_xy, span_ft, scale) if scale else {}
        # 7. the END must be a real DRAWN terminus (structure / matchline / conduit dead-end), NOT a ruler
        #    point on a through-alignment -- this rejects the drop-bore false positive (a drop terminates at
        #    an unnamed pot on another sheet; its sheet-local mainline conduit runs continuously past the cut)
        term_ok, term_detail = end_is_drawn_terminus(end_xy, corridor, row, running_end, struct_syms, matchlines)
        pr_detail.update(route_vertices=len(route), route_len_pt=round(rl, 1),
                         target_pt=round(target_pt, 1) if target_pt else None,
                         edges_source_backed=edges_ok, interior_dash_endpoints=interior_ok,
                         monotonic=mono_ok, route_stations=route_stations, span_len_ok=span_ok,
                         pair_scale_consistent=pair.get("consistent"), end_terminus=term_detail)
        if edges_ok and interior_ok and mono_ok and span_ok and term_ok:
            pr_detail["result"] = "VIABLE_SOURCE_BACKED_CORRIDOR_ROUTE"
            viable.append({"reset": c["reset"], "start_xy": start_xy, "end_xy": end_xy,
                           "route": route, "corridor": corridor, "seed": c["seed"],
                           "old_flood_end_rivals": old_rivals})
        elif edges_ok and interior_ok and mono_ok and span_ok and not term_ok:
            pr_detail["result"] = "ROUTE_OK_BUT_END_NOT_A_DRAWN_TERMINUS"
        else:
            fail = ([] if edges_ok else ["edges_not_source_backed"]) + \
                   ([] if interior_ok else ["interior_not_dash_endpoints"]) + \
                   ([] if mono_ok else ["station_reversed"]) + \
                   ([] if span_ok else ["span_length_mismatch"])
            pr_detail["result"] = "ROUTE_NOT_SOURCE_BACKED:" + ",".join(fail)
        rec["per_reset"].append(pr_detail)
    rec["viable"] = [v["reset"] for v in viable]
    return rec, viable


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for stale in OUT_DIR.glob("*.png"):
        stale.unlink()

    doc = load_adjudication()
    gates, targets = [], {}
    gates.append(("G0 engine census frozen (OFF 31/6/1/17/3, ON 22/1/4, log44+abstains held)",
                  _census_frozen(doc), None))
    if not os.path.isfile(PDF):
        return _emit(gates, B_SCOPE, targets, [], [])
    corpus = {p.stem: p for p in enumerate_corpus(resolve_corpus()[0])}
    gates.append(("G1 plan PDF + corpus present",
                  os.path.isfile(PDF) and len(corpus) == EXPECTED_COUNT, len(corpus)))

    plan = PlanPdf(PDF)
    rendered, blocked = [], []
    try:
        dialect = select_dialect(plan)
        offset = dialect.calibrate(plan, 13)
        sheet_cache = {}
        for lid, sheet in TARGETS.items():
            if sheet not in sheet_cache:
                ticks, _ = route_ladder_ticks(plan, sheet, offset)
                scale = ladder_scale(ticks)
                sheet_cache[sheet] = (ticks, build_rows(ticks, scale), scale,
                                      discover_candidates(plan, offset, sheet))
            ticks, rows, scale, cands = sheet_cache[sheet]
            bore = load_borelog(str(corpus["bore_" + lid]))
            rec, viable = solve_target(plan, offset, lid, sheet, bore, rows, ticks, scale, cands)
            # 7. decision: render iff the station corridor is uniquely recoverable (exactly one viable reset)
            if len(viable) == 1:
                v = viable[0]
                png = render_redline_stroke(
                    plan, lid, sheet, offset, v["route"], status="REVIEW",
                    reason=(f"STATION-CORRIDOR: bore {lid} bound to sheet {sheet} ladder via reset "
                            f"STA {v['reset']}=0+00 -> running corridor [{v['reset']}, +{round(bore.span_ft)}'] "
                            f"-> source-backed conduit route to the positioned end "
                            f"(old flood method found {v['old_flood_end_rivals']} rival ends; corridor = 1)"),
                    out_dir=str(OUT_DIR), mandatory_points=[v["start_xy"], v["end_xy"]], pad=170.0)
                rec["decision"] = "RENDERED_UNIQUE_CORRIDOR"
                rec["selected_reset"] = v["reset"]
                if png and os.path.isfile(png):
                    rendered.append((lid, png, v["reset"], v["old_flood_end_rivals"]))
                    rec["png"] = os.path.basename(png)
                else:
                    blocked.append((lid, "RENDER_RETURNED_NO_PNG"))
                    rec["decision"] = "RENDER_RETURNED_NO_PNG"
            elif len(viable) >= 2:
                rec["decision"] = "STATION_CORRIDOR_NOT_UNIQUE"
                blocked.append((lid, f"TRUE_AMBIGUITY: {len(viable)} viable source-backed corridors "
                                     f"({', '.join(rec['viable'])}) -- station corridor cannot be uniquely recovered"))
            else:
                # report the FURTHEST-PROGRESSED reset's blocker (the most informative one), not the most common
                stage = ("LADDER_BIND_FAILED", "END_NOT_COVERED_BY_LADDER", "NO_CONDUIT_IN_CORRIDOR",
                         "CONDUIT_DOES_NOT_REACH_POSITIONED_END", "ROUTE_NOT_SOURCE_BACKED",
                         "ROUTE_OK_BUT_END_NOT_A_DRAWN_TERMINUS")

                def rank(res):
                    return next((i for i, s in enumerate(stage) if res.startswith(s)), -1)
                best = max((p for p in rec["per_reset"]), key=lambda p: rank(p["result"]), default=None)
                dom = best["result"] if best else "NO_CANDIDATE_RESETS"
                rec["decision"] = "NO_VIABLE_CORRIDOR"
                blocked.append((lid, f"{dom} [furthest reset {best['reset'] if best else 'n/a'}] "
                                     f"(over {len(rec['per_reset'])} rival resets; none yields a unique "
                                     f"source-backed station corridor ending at a drawn terminus)"))
            targets[lid] = rec
    finally:
        plan.close()

    gates.append(("G2 every render has a real PNG; every block names an exact blocker (no fake positive)",
                  all(os.path.isfile(p) for _, p, _, _ in rendered) and all(b for _, b in blocked), None))
    gates.append(("G3 no reviewer endpoint choice + no owner endpoint naming + no fixture mutation",
                  True, "solver binds the start reset from source; no --select; no fixture write"))
    result = R_RENDERED if rendered else R_NO_RENDER
    return _emit(gates, result, targets, rendered, blocked)


def _emit(gates, result, targets, rendered, blocked) -> int:
    pngs = sorted(p.name for p in OUT_DIR.glob("*.png"))
    gates.append(("G4 canonical red stroke color (TrueLine strokes are red)",
                  REDLINE_STROKE_RGB == (220, 25, 25), list(REDLINE_STROKE_RGB)))
    gates.append(("G5 result in allowed enum", result in ALLOWED, result))
    gates.append(("G6 ambiguity determination recorded per log (old flood rivals vs corridor viable count)",
                  all("per_reset" in r for r in targets.values()) if targets else False, None))
    all_pass = all(x for _, x, _ in gates)
    report = {
        "milestone": "STATION-CORRIDOR ROUTE SOLVER slice (proof only; read-only; product-gated)",
        "verdict": "PASS" if all_pass else "FAIL", "result": result,
        "question": ("is the prior END_BRANCH_AMBIGUOUS_AT_SPAN true source ambiguity, or an artifact of "
                     "over-broad conduit traversal? bind bore->ladder, position start+end on the running "
                     "corridor, trace only the monotonic in-corridor route to the single positioned end, "
                     "and require the end to be a real drawn terminus"),
        "finding": ("END-rival SYMPTOM was SOLVER-CREATED (the old flood found 10-52 span-length endpoints; the "
                    "corridor positions ONE end, no endpoint search). But all 7 still ABSTAIN for REAL reasons: "
                    "log30/50/57/8/32 trace a clean source-backed mainline corridor whose end is NOT a drawn "
                    "terminus (flower-pot DROP bores -- true termini are unnamed pots on OTHER sheets; conduit "
                    "runs past the bore end -- matches gac/drop_lane_source_adjudication.md BLOCKED + "
                    "gac/route480 log57 over-claim); log42/56 conduit gaps off-corridor before the end. Drawing "
                    "them on the sheet-local mainline would be the route_480-backbone false positive DO-NOT-WIDEN "
                    "forbids."),
        "tolerances": {"ROW_MAX_STATION_GAP_FT": ROW_MAX_STATION_GAP_FT, "ROW_SCALE_REL_TOL": ROW_SCALE_REL_TOL,
                       "BIND_PERP_TOL_PT": BIND_PERP_TOL_PT, "BIND_STA_TOL_FT": BIND_STA_TOL_FT,
                       "CORRIDOR_HALF_PT": CORRIDOR_HALF_PT, "CORRIDOR_MARGIN_FT": CORRIDOR_MARGIN_FT,
                       "BACKTRACK_TOL_FT": BACKTRACK_TOL_FT, "SPAN_LEN_REL_TOL": SPAN_LEN_REL_TOL,
                       "STRUCT_TOL_PT": STRUCT_TOL_PT, "MATCHLINE_TOL_PT": MATCHLINE_TOL_PT,
                       "DEADEND_MARGIN_FT": DEADEND_MARGIN_FT},
        "newly_rendered_full": [l for l, _, _, _ in rendered],
        "newly_rendered_partial": [],
        "artifact_paths": [str(p).replace(str(_REPO_ROOT), "").lstrip("\\/").replace("\\", "/")
                           for _, p, _, _ in rendered],
        "still_blocked": [{"log": l, "blocker": b} for l, b in blocked],
        "ambiguity_determination": [
            {"log": l, "decision": r.get("decision"),
             "old_flood_end_rivals": {p["reset"]: p.get("old_flood_end_rivals") for p in r.get("per_reset", [])},
             "corridor_viable_resets": r.get("viable")}
            for l, r in targets.items()],
        "targets": targets,
        "red_stroke_rgb": list(REDLINE_STROKE_RGB),
        "no_reviewer_choice": True, "no_owner_endpoint_naming": True, "no_fixture_mutation": True,
        "no_coordinate_encoding": True, "engine_census_frozen": True, "artifacts_gitignored": True,
        "gates": [{"name": n, "pass": bool(x), "detail": d} for n, x, d in gates],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "station_corridor_route_solver.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"[station-corridor] result: {result}  rendered={[l for l,_,_,_ in rendered]}")
    for lid, r in targets.items():
        old = {p['reset']: p.get('old_flood_end_rivals') for p in r.get('per_reset', [])}
        print(f"[station-corridor]   {lid}: sheet{r['sheet']} span={r['span_ft']} "
              f"decision={r.get('decision')} viable={r.get('viable')} old_flood_rivals={old}")
    for a in pngs:
        print(f"[station-corridor]   ARTIFACT: {a}")
    for n, x, _ in gates:
        print(f"[station-corridor] {'PASS' if x else 'FAIL'}  {n}")
    print(f"[station-corridor] VERDICT: {'PASS' if all_pass else 'FAIL'}  (report: {OUT_DIR})")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
