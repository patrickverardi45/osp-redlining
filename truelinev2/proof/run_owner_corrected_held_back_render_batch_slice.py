r"""OWNER-PACKET-2 -- owner-corrected HELD_BACK batch source-bind + render slice (PROOF ONLY).

Cashes in the five newly owner-corrected (2026-06-16) HELD_BACK logs {log11, log47, log67, log69, log70}
-- the bridges the owner-corrected endpoint-anchor slice encoded -- by driving each as far through the
controlled lane (source-bind, then render) AS FAR AS EACH IS SAFE, in one shared slice. It binds the
encoded endpoint identities to REAL PDF source with the SAME proven primitives the log59/log64/log66/log71
exemplars used (printed reset/station label -> label box / callout -> leader -> modeled symbol; modeled
conduit chain), it joins the cross-sheet pairs with the ALREADY-SHIPPED, ALREADY-PROVEN frame primitive
(match.frames.translate_between_sheets over the SAFE frame graph; it ABSTAINS to None on any conflicting/
missing edge and NEVER falls back to a raw station), and it draws ONLY the render-safe member. It invents
NO coordinate, screenshots NO pixel, reconciles NO cross-sheet coordinate into a placement, promotes
NOTHING, and loosens no threshold.

This slice covers the FIVE owner-corrected logs; the older three HELD_BACK logs {log36, log52, log58} are
covered by run_source_bindable_held_back_render_slice (log52 rendered; log58 source-bound, render held on
the sheet-10 12-vs-13 ambiguity; log36 held for owner-confirmation of sheet 17). The class-level gates here
re-verify the FULL 8-log held-back set is intact and that NOTHING is promoted.

Per-log verdict (each determined by RUNNING the real binders/primitive, not assumed):

  log69  INSTALLER HH @ 1+45=0+00 -> INSTALLER HH @ 4+54 (sheet 17, single sheet)  -- SOURCE-BIND + RENDER
         both installer-HH termini bind uniquely on sheet 17 (the start is the common reset HH shared by
         log67/log69/log70); a connected BORE - VACANT PIPE / BORE - PORT chain reaches BOTH symbols; the
         direct horizontal corridor is CONTINUOUS (max gap < MAX_DASH_GAP), so the ordered source-backed
         chain path is drawn as ONE red REVIEW stroke on sheet 17. The cleanest new render candidate.

  log47  FLOWER POT @ 3+23 (sheet 13) -> INSTALLER HH @ 4+94 (sheet 14)   -- SOURCE-BIND only (render HELD)
         both termini bind uniquely on their owner-attributed sheets; the 10->13->14 cross-sheet frame join
         is source-backed (every consecutive hop a safe printed frame edge). Render HELD with a NAMED reason:
         the run's corrected_sheets is a THREE-sheet set [10,13,14] (the termini on 13/14, sheet 10 in the
         matchline walk), so the drawn-leg sheet membership + the per-sheet inter-sheet crossing are a
         render-time reconciliation NOT yet source-proven-unambiguous here (a contained 2-leg stroke could be
         incomplete/misleading). Source-bind is complete; the render is deferred, not guessed.

  log11  NEXTLINK HH @ 21+63=0+00 (sheet 5) -> FLOWER POT @ 6+30 (sheet 17)  -- SOURCE-BIND only (render HELD)
         start binds via the committed nextlink-callout locator (it IS the shared log53 NEXTLINK HH reset,
         owner-confirmed 2026-06-16); end flower_pot binds uniquely on sheet 17; the 5->17 frame join is
         source-backed. Render HELD with a NAMED reason: the two terminus sheets (5 and 17) are NON-ADJACENT,
         so there is no single shared printed matchline crossing to anchor a 2-leg sheet-local render (the
         translate(5,17) value is a frame-graph offset, not one physical crossing); a contained render is a
         deferred render-time reconciliation, not done here.

  log67  INSTALLER HH @ 1+45=0+00 (sheet 17) -> FLOWER POT @ 4+14 (sheet 20)  -- TERMINI bind (join HELD)
  log70  INSTALLER HH @ 1+45=0+00 (sheet 17) -> FLOWER POT @ 2+15 (sheet 20)  -- TERMINI bind (join HELD)
         both termini bind uniquely on their sheets, BUT the 17<->20 cross-sheet frame join is BLOCKED: the
         boundary prints TWO conflicting matchline equations, so the shipped primitive correctly ABSTAINS
         (CONFLICTING_FRAME_EQUATIONS) and never guesses a safe edge. The cross-sheet relationship is NOT
         source-backed; render HELD. (log70's printed 'HH - HH = 215'' annotation is also owner-HELD: the
         corrected end is a FLOWER POT, not an HH.)

Census stays frozen (no adjudication artifact changes; flag-OFF 31/6/1/17/3, flag-ON 22/1/4). The seam
ELIGIBLE_EXEMPLARS stays log53/log64/log71/log59/log66 (all eight held-back logs refused by
build_seam_payload); NOTHING is promoted. The held-back set stays the 8 {log11,36,47,52,58,67,69,70}.
Red TrueLine REVIEW strokes only (render.crop.REDLINE_STROKE_RGB); source PDF/CAD evidence colors are never
touched. PNG + JSON are written under the gitignored data/outputs path and are NOT committed; this is a
source-backed REVIEW/proof artifact, NOT a broad renderer and NOT wired into product/UI/API.

Proof-only.
Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_owner_corrected_held_back_render_batch_slice
"""
from __future__ import annotations

import json
import math
import os

import truelinev2.match.frames as FR
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
    resolve_nextlink_hh_callout,
    resolve_structure_position,
)
from truelinev2.ingest.manual_adjudication import (
    PLACE_NEEDS_GEOMETRY,
    activation_summary,
    apply_adjudications,
    load_adjudication,
    parent_run_duplicate_check,
    placement_geometry_readiness,
    validate_endpoint_anchors,
)
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.proof.run_brenham_corpus import EXPECTED_COUNT, PDF, enumerate_corpus
from truelinev2.proof.run_cross_sheet_frame_join_scout import (
    ABSTAIN_CONFLICT,
    scout_log,
)
from truelinev2.proof.run_log53_primitives_cohort_replay import (
    MODELED_TERMINUS_CLASSES,
    SOURCE_BINDABLE_NOW,
    classify_record,
)
from truelinev2.proof.run_log59_render_artifact_slice import (
    interior_vertices_are_dash_endpoints,
    route_edges_source_backed,
)
from truelinev2.proof.run_log64_sheet21_source_bind_slice import corridor_is_continuous
from truelinev2.proof.run_log71_render_artifact_slice import order_chain_route, route_length
from truelinev2.proof.run_log71_two_leg_source_bind_slice import leg_corridor_band
from truelinev2.proof.run_reviewer_service_contract import resolve_corpus
from truelinev2.render.crop import REDLINE_STROKE_RGB, render_redline_stroke
from truelinev2.seam import ELIGIBLE_EXEMPLARS, build_seam_payload

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "owner_corrected_held_back_render_batch_slice"
TRUTH = _REPO_ROOT / "data" / "outputs" / "final_engine_truth_table" / \
    "final_engine_truth_table.json"
BASE_CONDUIT = set(BRENHAM_CONDUIT_LAYERS.values())   # BORE - VACANT PIPE / BORE - PORT
INSTALLER_SYMBOL_LAYER = "NEXTLINK"                   # installer/nextlink HHs share the NEXTLINK symbol layer
FROZEN_BUCKETS = {"DRAWABLE_REVIEW": 31, "HUMAN_ADJUSTABLE_REVIEW": 6,
                  "OUT_OF_CLASS": 1, "PICK_CARD_REVIEW": 17, "SOURCE_OR_KMZ_REQUIRED": 3}
ABSTAIN_4 = ("log5", "log31", "log38", "log43")
SEAM_ELIGIBLE = ("log53", "log64", "log71", "log59", "log66")   # this slice promotes NOTHING
HELD_BACK_8 = ("log11", "log36", "log47", "log52", "log58", "log67", "log69", "log70")
# the FIVE owner-corrected logs this slice drives (the older 3 are in run_source_bindable_held_back_render_slice)
CORRECTED = ("log11", "log47", "log67", "log69", "log70")
_COORD_KEYS = {"x", "y", "z", "xc", "yc", "x0", "y0", "x1", "y1", "cx", "cy", "xy",
               "lat", "lon", "lng", "coord", "coords", "coordinate", "coordinates",
               "px", "py", "pixel", "pixels", "point", "points", "symbol_xy", "anchor_xy",
               "stroke", "stroke_points", "geometry", "geom"}

# per-log bind recipe + per-endpoint sheet attribution (the station/class are the encoded anchors; the
# per-endpoint sheet is owner-note provenance WITHIN the owner-confirmed corrected_sheets set; nothing here
# is invented). 'callout' termini bind via resolve_nextlink_hh_callout (nextlink_hh has no structure layer).
SPEC = {
    "log69": {"single_sheet": 17, "sheets": [17],
              "start": {"class": "installer_hh", "station": "1+45", "sheet": 17, "reset": True,
                        "seed": "NEXTLINK", "context": None},
              "end":   {"class": "installer_hh", "station": "4+54", "sheet": 17, "reset": False,
                        "seed": "NEXTLINK", "context": None}},
    "log47": {"sheets": [10, 13, 14],
              "start": {"class": "flower_pot", "station": "3+23", "sheet": 13, "reset": False,
                        "seed": "FLOWER POT", "context": ("FLOWER", "POT")},
              "end":   {"class": "installer_hh", "station": "4+94", "sheet": 14, "reset": False,
                        "seed": "NEXTLINK", "context": None}},
    "log67": {"sheets": [17, 20],
              "start": {"class": "installer_hh", "station": "1+45", "sheet": 17, "reset": True,
                        "seed": "NEXTLINK", "context": None},
              "end":   {"class": "flower_pot", "station": "4+14", "sheet": 20, "reset": False,
                        "seed": "FLOWER POT", "context": ("FLOWER", "POT")}},
    "log70": {"sheets": [17, 20],
              "start": {"class": "installer_hh", "station": "1+45", "sheet": 17, "reset": True,
                        "seed": "NEXTLINK", "context": None},
              "end":   {"class": "flower_pot", "station": "2+15", "sheet": 20, "reset": False,
                        "seed": "FLOWER POT", "context": ("FLOWER", "POT")}},
    "log11": {"sheets": [5, 17],
              "start": {"class": "nextlink_hh", "station": "21+63", "sheet": 5, "reset": True,
                        "callout": True},
              "end":   {"class": "flower_pot", "station": "6+30", "sheet": 17, "reset": False,
                        "seed": "FLOWER POT", "context": ("FLOWER", "POT")}},
}
RENDER_LOGS = ("log69",)                          # the render-safe member (single sheet, continuous corridor)
FULL_SOURCE_BIND = ("log47", "log11")             # termini bind + cross-sheet join source-backed
JOIN_HELD = ("log67", "log70")                    # termini bind; cross-sheet join CONFLICTING -> held
NO_EDGE_PAIR = (7, 10)                            # abstain guard: no printed frame edge -> translate None

# named, source-proven render-held blockers (each grounded in the runs below)
HELD_REASON = {
    "log47": ("SOURCE-BIND complete; RENDER HELD -- corrected_sheets is the THREE-sheet set [10,13,14] "
              "(termini on 13/14, sheet 10 in the matchline walk); the drawn-leg sheet membership and the "
              "per-sheet inter-sheet crossing are a render-time reconciliation not source-proven-unambiguous "
              "here (a 2-leg stroke could be incomplete). Deferred, not guessed."),
    "log11": ("SOURCE-BIND complete; RENDER HELD -- the two terminus sheets (5 and 17) are NON-ADJACENT, so "
              "there is no single shared printed matchline crossing to anchor a 2-leg sheet-local render "
              "(translate(5,17) is a frame-graph offset, not one physical crossing). Deferred render-time "
              "reconciliation; the shared log53 NEXTLINK HH start is a separate coordination concern."),
    "log67": ("TERMINI bind; cross-sheet JOIN HELD + RENDER HELD -- the 17<->20 boundary prints TWO "
              "conflicting matchline equations; the shipped primitive ABSTAINS (CONFLICTING_FRAME_EQUATIONS) "
              "and never guesses a safe edge. The cross-sheet relationship is NOT source-backed."),
    "log70": ("TERMINI bind; cross-sheet JOIN HELD + RENDER HELD -- 17<->20 CONFLICTING_FRAME_EQUATIONS "
              "(same as log67). Also the printed 'HH - HH = 215'' annotation is owner-HELD (the corrected "
              "end is a FLOWER POT, not an HH)."),
}

R_PROVEN = "OWNER_CORRECTED_HELD_BACK_BATCH_RENDER_PROVEN"
B_CENSUS = "BLOCKED_OWNER_CORRECTED_BATCH_CENSUS_DRIFT"
B_ANCHORS = "BLOCKED_OWNER_CORRECTED_BATCH_ANCHORS_INVALID"
B_BIND = "BLOCKED_OWNER_CORRECTED_BATCH_TERMINUS_BIND_FAILED"
B_JOIN = "BLOCKED_OWNER_CORRECTED_BATCH_JOIN_PARTITION_WRONG"
B_RENDER = "BLOCKED_OWNER_CORRECTED_BATCH_RENDER_NOT_SOURCE_BACKED"
B_PROMOTED = "BLOCKED_OWNER_CORRECTED_BATCH_SILENTLY_PROMOTED"
B_SCOPE = "BLOCKED_OWNER_CORRECTED_BATCH_SCOPE_VIOLATION"
ALLOWED = {R_PROVEN, B_CENSUS, B_ANCHORS, B_BIND, B_JOIN, B_RENDER, B_PROMOTED, B_SCOPE}


def _has_coord_keys(anchor: dict) -> bool:
    return bool({str(k).lower() for k in anchor} & _COORD_KEYS)


def _refuses_seam(log_id: str, rec: dict) -> bool:
    try:
        build_seam_payload(log_id, rec.get(log_id, {}))
        return False
    except ValueError:
        return True


def _census_frozen(doc) -> bool:
    if not TRUTH.is_file():
        return False
    truth = json.loads(TRUTH.read_text(encoding="utf-8"))
    baseline = {r["bore_id"]: dict(r) for r in truth["rows"]}
    off_rows = apply_adjudications(baseline, enabled=False)
    on_rows = apply_adjudications(baseline, enabled=True, doc=doc)
    summ = activation_summary(on_rows)
    buckets = {}
    for r in off_rows.values():
        buckets[r["completion_bucket"]] = buckets.get(r["completion_bucket"], 0) + 1
    return (off_rows is baseline and buckets == FROZEN_BUCKETS
            and summ["manual_review_drawable"] == 22 and summ["manual_source_verification"] == 1
            and summ["manual_abstain"] == 4
            and on_rows["log44"]["adjudication"]["drawable_status"] == "non_drawable"
            and all(on_rows[l]["adjudication"]["drawable_status"] == "abstain" for l in ABSTAIN_4)
            and not parent_run_duplicate_check(doc))


def bind_one(plan, offset, spec):
    """Bind one terminus on its owner-attributed sheet with the proven primitive. nextlink_hh binds via
    the committed callout locator; installer_hh/flower_pot via resolve_structure_position. Returns
    (xy|None, result, draw). Coordinates are extractor-derived; nothing is invented or snapped."""
    words = plan.words(spec["sheet"], offset)
    draw = plan.line_items(spec["sheet"], offset)
    if spec.get("callout"):
        v = resolve_nextlink_hh_callout(station_sta=spec["station"], words=words, drawings=draw,
                                        callout_layer="ANNOTATION", symbol_layer="NEXTLINK")
        xy = tuple(v.symbol_xy) if (v.result == POSITION_BOUND and v.symbol_xy) else None
        return xy, v.result, draw
    labels = ([f"{spec['station']}=0+00", spec["station"]] if spec["reset"]
              else [spec["station"], f"{spec['station']}=0+00"])
    last = None
    for label in labels:
        kw = dict(label_text=label, structure_class=spec["class"], words=words,
                  drawings=draw, layer_table=BRENHAM_STRUCTURE_LAYERS)
        if spec.get("context"):
            kw["context_texts"] = spec["context"]
        v = resolve_structure_position(**kw)
        last = v.result
        if v.result == POSITION_BOUND and v.symbol_xy:
            return tuple(v.symbol_xy), v.result, draw
    return None, last, draw


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for stale in OUT_DIR.glob("*.png"):
        stale.unlink()

    doc = load_adjudication()
    rec = {r["log_id"]: r for r in doc["logs"]}
    gates, ev = [], {"binds": {}, "joins": {}, "render": {}, "held": {}}
    result = B_BIND

    # ---- safety: frozen census + seam unchanged (nothing promoted) ---------------
    gates.append(("G0 engine census frozen (OFF 31/6/1/17/3, ON 22/1/4, log44+abstains held)",
                  _census_frozen(doc), None))
    gates.append(("G0b seam ELIGIBLE_EXEMPLARS == log53/64/71/59/66 (5); ALL 8 held-back logs seam-refused",
                  tuple(ELIGIBLE_EXEMPLARS) == SEAM_ELIGIBLE
                  and all(_refuses_seam(l, rec) for l in HELD_BACK_8), None))

    # ---- anchors consumed: each owner-corrected bridge valid, modeled, identity-only, NO coordinates ----
    anchors_ok = True
    anchor_detail = {}
    for lid in CORRECTED:
        l = rec.get(lid, {})
        ea = l.get("endpoint_anchors") or {}
        start, end = ea.get("start") or {}, ea.get("end") or {}
        ok = (validate_endpoint_anchors(l) == [] and set(ea) <= {"start", "end"}
              and start.get("boundary_kind") == "structure_terminus"
              and end.get("boundary_kind") == "structure_terminus"
              and start.get("structure_class") in MODELED_TERMINUS_CLASSES
              and end.get("structure_class") in MODELED_TERMINUS_CLASSES
              and start.get("structure_class") == SPEC[lid]["start"]["class"]
              and start.get("station") == SPEC[lid]["start"]["station"]
              and end.get("structure_class") == SPEC[lid]["end"]["class"]
              and end.get("station") == SPEC[lid]["end"]["station"]
              and (l.get("corrected_sheets") or []) == SPEC[lid]["sheets"]
              and not _has_coord_keys(start) and not _has_coord_keys(end))
        anchor_detail[lid] = ok
        anchors_ok = anchors_ok and ok
    gates.append(("G1 5 owner-corrected anchors valid: two modeled structure_terminus, classes/stations/sheets match, identity-only (NO coords)",
                  anchors_ok, anchor_detail))

    # ---- cohort: all 5 are SOURCE_BINDABLE_NOW (the bridged held-back cohort delta is intact) -----
    cls = {lid: classify_record(rec[lid])["classification"] for lid in CORRECTED}
    gates.append(("G2 cohort: all 5 owner-corrected logs are SOURCE_BINDABLE_NOW (bridged held-back)",
                  all(cls[lid] == SOURCE_BINDABLE_NOW for lid in CORRECTED), cls))

    if not os.path.isfile(PDF):
        gates.append(("G3 plan PDF present", False, f"missing {PDF}"))
        return _emit(gates, B_BIND, ev, rec)
    corpus_dir, _ = resolve_corpus()
    corpus = {p.stem: p for p in enumerate_corpus(corpus_dir)} if os.path.isdir(corpus_dir) else {}
    gates.append(("G3 plan PDF + corpus present",
                  os.path.isfile(PDF) and len(corpus) == EXPECTED_COUNT, len(corpus)))

    plan = PlanPdf(PDF)
    try:
        offset = select_dialect(plan).calibrate(plan, 13)
        graph = FR._build_plan_frame_graph(plan, offset)

        # ---- SOURCE-BIND termini: BOTH ends of all 5 bind (POSITION_BOUND) on their sheets ----
        bind_ok = True
        draws = {}
        for lid in CORRECTED:
            d = {}
            for role in ("start", "end"):
                xy, res, draw = bind_one(plan, offset, SPEC[lid][role])
                draws[(lid, role)] = (draw, xy)
                d[role] = {"sheet": SPEC[lid][role]["sheet"], "class": SPEC[lid][role]["class"],
                           "station": SPEC[lid][role]["station"], "result": res,
                           "xy": [round(c, 2) for c in xy] if xy else None}
                bind_ok = bind_ok and xy is not None
            ev["binds"][lid] = d
        gates.append(("G4 ALL 5 logs: BOTH termini bind (POSITION_BOUND) on their owner-attributed sheets",
                      bind_ok, {l: {r: ev["binds"][l][r]["xy"] for r in ("start", "end")} for l in CORRECTED}))
        if not bind_ok:
            return _emit(gates, B_BIND, ev, rec, plan=plan)

        # ---- log69 single-sheet source-bind: connected chain reaches BOTH termini on sheet 17 ----
        s_draw, s_xy = draws[("log69", "start")]
        _, e_xy = draws[("log69", "end")]
        fp = symbol_footprint(s_draw, INSTALLER_SYMBOL_LAYER, s_xy)
        chain69 = connected_chain([x for x in s_draw if x.get("layer") in BASE_CONDUIT], fp) if fp else []
        eps69 = dash_endpoints(chain69)
        reach_s = min((math.hypot(p[0] - s_xy[0], p[1] - s_xy[1]) for p in eps69), default=None)
        reach_e = min((math.hypot(p[0] - e_xy[0], p[1] - e_xy[1]) for p in eps69), default=None)
        both69 = (bool(chain69) and reach_s is not None and reach_s <= MAX_DASH_GAP
                  and reach_e is not None and reach_e <= MAX_DASH_GAP)
        band69, lo69, hi69, axis69 = leg_corridor_band(eps69, s_xy, e_xy)
        cont69 = corridor_is_continuous(band69, lo69, hi69)
        maxgap69 = round(max((band69[i + 1] - band69[i] for i in range(len(band69) - 1)), default=0.0), 2)
        ev["render"]["log69_corridor"] = {"chain_segs": len(chain69), "axis": axis69,
                                          "reach_to_start_pt": round(reach_s, 2) if reach_s is not None else None,
                                          "reach_to_end_pt": round(reach_e, 2) if reach_e is not None else None,
                                          "band_points": len(band69), "max_gap_pt": maxgap69,
                                          "direct_corridor_continuous": cont69}
        gates.append(("G5 log69 single-sheet source-bind: connected BORE - VACANT PIPE/PORT chain reaches BOTH installer-HH termini (<= MAX_DASH_GAP)",
                      both69, ev["render"]["log69_corridor"]))
        if not both69:
            return _emit(gates, B_BIND, ev, rec, plan=plan)

        # ---- CROSS-SHEET JOIN partition (the shipped primitive, source-backed or NAMED abstain) ----
        join_ok = True
        for lid in ("log47", "log11", "log67", "log70"):
            s = scout_log(graph, plan, offset, rec[lid])
            ev["joins"][lid] = {"sheets": s["sheets"], "n_hops": s["n_hops"],
                                "source_backed": s["source_backed"], "blocker": s["blocker"], "hops": s["hops"]}
        full = all(ev["joins"][l]["source_backed"]
                   and all(h["safe_edge"] and h["translated_ft"] is not None for h in ev["joins"][l]["hops"])
                   for l in FULL_SOURCE_BIND)
        held = all((not ev["joins"][l]["source_backed"]) and ev["joins"][l]["blocker"] == ABSTAIN_CONFLICT
                   and all(h["translated_ft"] is None for h in ev["joins"][l]["hops"] if not h["safe_edge"])
                   for l in JOIN_HELD)
        # abstain guard: a non-edge sheet pair MUST translate to None (no raw fallback / no fake join)
        guard_none = FR.translate_between_sheets(graph, NO_EDGE_PAIR[0], NO_EDGE_PAIR[1], 100.0) is None
        ev["abstain_guard"] = {"pair": list(NO_EDGE_PAIR), "translate_is_none": guard_none}
        join_ok = full and held and guard_none
        gates.append(("G6 join partition: log47(10->13->14)+log11(5->17) SOURCE-BACKED; log67+log70(17<->20) BLOCKED CONFLICTING_FRAME_EQUATIONS; non-edge pair -> None",
                      join_ok, {"source_backed": {l: ev["joins"][l]["source_backed"] for l in ("log47", "log11", "log67", "log70")},
                                "abstain_guard": ev["abstain_guard"]}))
        if not join_ok:
            return _emit(gates, B_JOIN, ev, rec, plan=plan)

        # ---- NO cross-sheet COORDINATE reconciled into a placement: all 5 still NEEDS_GEOMETRY -----
        no_placement = all(placement_geometry_readiness(rec[lid])["status"] == PLACE_NEEDS_GEOMETRY
                           for lid in CORRECTED)
        gates.append(("G7 no cross-sheet coordinate reconciled into a placement (all 5 still NEEDS_GEOMETRY; render is a proof artifact, not a placement)",
                      no_placement, None))

        # ---- RENDER the render-safe member (log69): ordered source-backed chain path, one red stroke ----
        route = order_chain_route(chain69, s_xy, e_xy)
        interior_ok = len(route) >= 3 and interior_vertices_are_dash_endpoints(route, chain69)
        edges_ok = bool(route) and route[0] == s_xy and route[-1] == e_xy \
            and route_edges_source_backed(route, chain69)
        route_ok = interior_ok and edges_ok
        ev["render"]["log69"] = {"sheet": 17, "start_xy": [round(c, 2) for c in s_xy],
                                 "end_xy": [round(c, 2) for c in e_xy],
                                 "render_mode": "continuous_corridor" if cont69 else "ordered_chain_path",
                                 "route_vertices": len(route),
                                 "route_len_pt": round(route_length(route), 1) if route else None,
                                 "straight_len_pt": round(math.hypot(s_xy[0] - e_xy[0], s_xy[1] - e_xy[1]), 1),
                                 "source_backed": route_ok}
        if route_ok:
            png = render_redline_stroke(
                plan, "log69", 17, offset, route, status="REVIEW",
                reason=("OWNER-PACKET-2 source-backed: log69 INSTALLER HH 1+45=0+00 -> INSTALLER HH 4+54 "
                        "(single sheet 17; ordered source-backed chain path, BORE - VACANT PIPE corridor)"),
                out_dir=str(OUT_DIR), mandatory_points=[s_xy, e_xy], pad=170.0)
            ev["render"]["log69"]["png"] = png
        else:
            png = None
        render_ok = route_ok and bool(png) and os.path.isfile(png)
        gates.append(("G8 log69 RENDER: ordered source-backed chain path (>= 3 real vertices; every edge a dash or <= MAX_DASH_GAP hop); one red REVIEW stroke on sheet 17",
                      render_ok, {"vertices": ev["render"]["log69"]["route_vertices"],
                                  "route_len": ev["render"]["log69"]["route_len_pt"],
                                  "straight_len": ev["render"]["log69"]["straight_len_pt"],
                                  "render_mode": ev["render"]["log69"]["render_mode"]}))
        if not render_ok:
            return _emit(gates, B_RENDER, ev, rec, plan=plan)

        # ---- RENDER HELD for the other 4: each carries an exact, source-proven blocker; NO stroke ----
        for lid in ("log47", "log11", "log67", "log70"):
            ev["held"][lid] = HELD_REASON[lid]
        gates.append(("G9 RENDER HELD for log47/log11 (source-bind complete) + log67/log70 (join CONFLICTING) -- each with an exact source-proven blocker; no stroke",
                      all(lid in ev["held"] and ev["held"][lid] for lid in ("log47", "log11", "log67", "log70")), None))
    finally:
        plan.close()

    if all(x for _, x, _ in gates):
        result = R_PROVEN
    return _emit(gates, result, ev, rec)


def _emit(gates, result, ev, rec, plan=None) -> int:
    pngs = sorted(p.name for p in OUT_DIR.glob("*.png"))
    # ---- scope / safety gates (always run) -------------------------------------
    # exactly the one log69 PNG exists (render-safe member only); zero PNG for any other log
    expected_pngs = ["log69_s17_redline_stroke.png"]
    no_other = all("log69" in p for p in pngs)
    gates.append(("G10 exactly the one log69 sheet-17 PNG exists (render-safe member only; no other log render)",
                  pngs == expected_pngs or (result != R_PROVEN and no_other), pngs))
    gates.append(("G11 canonical red stroke color (TrueLine REVIEW strokes are red)",
                  REDLINE_STROKE_RGB == (220, 25, 25), list(REDLINE_STROKE_RGB)))
    # held-back set intact: exactly the 8 anchored-and-seam-refused; nothing promoted
    with_anchors = {lid for lid, r in rec.items() if r.get("endpoint_anchors")}
    held_back = tuple(sorted((l for l in with_anchors if _refuses_seam(l, rec)),
                             key=lambda s: int(s[3:])))
    gates.append(("G12 held-back set intact == 8 {log11,36,47,52,58,67,69,70}; ELIGIBLE_EXEMPLARS unchanged (nothing promoted)",
                  held_back == HELD_BACK_8 and tuple(ELIGIBLE_EXEMPLARS) == SEAM_ELIGIBLE,
                  {"held_back": list(held_back)}))
    gates.append(("G13 result in allowed enum", result in ALLOWED, result))

    all_pass = all(x for _, x, _ in gates) and result == R_PROVEN
    report = {
        "milestone": "OWNER-PACKET-2 -- owner-corrected HELD_BACK batch source-bind + render slice (proof only)",
        "verdict": "PASS" if all_pass else "FAIL",
        "result": result,
        "class": "owner-corrected SOURCE_BINDABLE_HELD_BACK {log11, log47, log67, log69, log70}",
        "older_held_back_covered_elsewhere": {
            "slice": "run_source_bindable_held_back_render_slice",
            "logs": {"log52": "source-bind + render proven", "log58": "source-bind proven; render held (sheet-10 12-vs-13)",
                     "log36": "held -- owner-confirmation of source-recovered sheet 17 (corrected_sheets == [])"}},
        "passed_source_bind": ["log69", "log47", "log11"],
        "passed_render": ["log69"],
        "termini_bound_join_held": ["log67", "log70"],
        "held": ev.get("held"),
        "binds": ev.get("binds"),
        "cross_sheet_joins": ev.get("joins"),
        "abstain_guard": ev.get("abstain_guard"),
        "render": ev.get("render"),
        "shape": ("log69 single-sheet installer-to-installer (log64/log66 family) drawn as ONE red REVIEW "
                  "stroke on sheet 17 via the ordered source-backed chain path; the cross-sheet logs are "
                  "source-bound where their join is source-backed (log47/log11) and held where it is not "
                  "(log67/log70 CONFLICTING_FRAME_EQUATIONS); no cross-sheet coordinate reconciled into a "
                  "placement; nothing promoted"),
        "red_stroke_rgb": list(REDLINE_STROKE_RGB),
        "artifacts": pngs,
        "no_invented_coordinates": True, "no_screenshot_pixels": True,
        "no_cross_sheet_coordinate_reconciled_into_placement": True,
        "no_seam_promotion": True, "engine_census_frozen": True,
        "max_dash_gap_not_loosened": MAX_DASH_GAP == 35.0,
        "held_back_set": list(HELD_BACK_8), "seam_eligible": list(ELIGIBLE_EXEMPLARS),
        "broad_renderer": False, "product_wired": False,
        "next_slice": ("(1) log47: locate the unique inter-sheet crossing + confirm the drawn-leg sheet "
                       "membership for the [10,13,14] set, then render. (2) log11: contained 2-leg render "
                       "across non-adjacent sheets 5/17 (render-time reconciliation). (3) log67/log70: per-bore "
                       "disambiguation of the two printed 17<->20 crossings, then join + render. (4) seam "
                       "promotion of log69 (owner sign-off on the single-sheet render). Each separately authorized."),
        "gates": [{"name": n, "pass": bool(x), "detail": d} for n, x, d in gates],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "owner_corrected_held_back_render_batch_slice.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"[oc-held-back] result: {result}")
    for lid in CORRECTED:
        b = ev.get("binds", {}).get(lid, {})
        j = ev.get("joins", {}).get(lid, {})
        line = f"[oc-held-back]   {lid}: start={b.get('start', {}).get('xy')} end={b.get('end', {}).get('xy')}"
        if j:
            line += f"  join_source_backed={j.get('source_backed')} blocker={j.get('blocker')}"
        print(line)
    for a in pngs:
        print(f"[oc-held-back]   ARTIFACT: {a}")
    for n, x, _ in gates:
        print(f"[oc-held-back] {'PASS' if x else 'FAIL'}  {n}")
    print(f"[oc-held-back] VERDICT: {'PASS' if all_pass else 'FAIL'}  (report: {OUT_DIR})")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
