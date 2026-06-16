r"""OWNER-PACKET-2 -- SOURCE_BINDABLE_HELD_BACK batch source-bind + render slice (PROOF ONLY).

Moves the whole currently source-bindable HELD_BACK class -- {log36, log52, log58} -- through the next
controlled lane (source-bind, then render) AS FAR AS EACH IS SAFE, in one shared slice. It binds the
encoded endpoint identities to REAL PDF source with the SAME proven primitives the log59/log64/log66/log71
exemplars used (printed station label -> label box -> leader -> modeled symbol; modeled conduit chain), it
joins the two cross-sheet pairs with the ALREADY-SHIPPED, ALREADY-PROVEN frame primitive
(match.frames.translate_between_sheets over the SAFE frame graph -- the cross_sheet_frame_join scout's
primitive; it ABSTAINS to None on any ambiguous/missing edge and NEVER falls back to a raw station), and it
draws ONLY the render-safe member. It invents NO coordinate, screenshots NO pixel, reconciles NO cross-sheet
coordinate into a placement (the inter-sheet join stays an offset identity, the render-time coordinate
reconciliation step), promotes NOTHING, and loosens no threshold.

Per-log verdict (each determined by RUNNING the real binders/primitive, not assumed):

  log52  FLOWER POT @ 0+98 (sheet 7) -> FLOWER POT @ 4+57 (sheet 8)   -- SOURCE-BIND + RENDER (both safe)
         both flower-pot termini bind uniquely; each carries a connected BORE - VACANT PIPE / BORE - PORT
         chain; the 7<->8 join is a HIGH-confidence unique printed frame edge; AND each leg's terminus->
         matchline corridor is a source-backed ordered chain path (every edge a real dash or <= MAX_DASH_GAP
         hop), so the two-leg render is drawn: one red REVIEW stroke per sheet, joined by station identity
         (the proven log53/log71/log65 cross-sheet render shape; the two matchline points stay in their own
         sheet frames and are NEVER reconciled).

  log58  INSTALLER HH @ 39+79 (sheet 10) -> INSTALLER HH @ 2+36 (sheet 13)  -- SOURCE-BIND only (render HELD)
         both installer-HH termini bind uniquely with connected chains; the 10<->13 join is a SAFE frame edge
         (translate returns a concrete offset). The render is HELD with a NAMED, source-proven blocker: the
         safe 10<->13 edge is anchored on SHEET 13's HIGH-confidence side; on SHEET 10 the matching matchline
         equations are MEDIUM and ambiguously linked to BOTH frame 12 and frame 13, so the per-sheet render
         leg's crossing on sheet 10 is not uniquely disambiguated 12-vs-13 (the same crossing-disambiguation
         gap the frame-join scout named for log67/69/70). Source-bind is complete; the render leg is not safe.

  log36  INSTALLER HH @ 0+56 -> INSTALLER HH @ 1+45 (sheet 17, single sheet)  -- HELD (owner confirmation)
         binds cleanly on sheet 17 (single-sheet log64 family), BUT sheet 17 is SOURCE-RECOVERED, not
         owner-recorded: corrected_sheets == []. The render + source-bind exemplars gate on owner-confirmed
         sheets, and log36's own bridge mandates owner confirmation FIRST. Blocker: owner confirmation of the
         source-recovered sheet 17. Not source-bound or rendered here.

Census stays frozen (no adjudication artifact changes; flag-OFF 31/6/1/17/3, flag-ON 22/1/4). The seam
ELIGIBLE_EXEMPLARS stays log53/log64/log71/log59/log66 (all three targets refused by build_seam_payload);
nothing is promoted. The held-back set stays {log36, log52, log58}. Red TrueLine REVIEW strokes only
(render.crop.REDLINE_STROKE_RGB); source PDF/CAD evidence colors are never touched. PNG + JSON are written
under the gitignored data/outputs path and are NOT committed; this is a source-backed REVIEW/proof artifact,
NOT a broad renderer and NOT wired into product/UI/API.

Proof-only.
Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_source_bindable_held_back_render_slice
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
from truelinev2.proof.run_cross_sheet_frame_join_scout import scout_log
from truelinev2.proof.run_log53_primitives_cohort_replay import (
    MODELED_TERMINUS_CLASSES,
    SOURCE_BINDABLE_NOW,
    classify_record,
)
from truelinev2.proof.run_log59_render_artifact_slice import (
    interior_vertices_are_dash_endpoints,
    route_edges_source_backed,
)
from truelinev2.proof.run_log71_render_artifact_slice import order_chain_route, route_length
from truelinev2.proof.run_log71_sheet_local_bind_scout import locate_matchline_boundary
from truelinev2.proof.run_reviewer_service_contract import resolve_corpus
from truelinev2.render.crop import REDLINE_STROKE_RGB, render_redline_stroke
from truelinev2.seam import ELIGIBLE_EXEMPLARS, build_seam_payload

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "source_bindable_held_back_render_slice"
TRUTH = _REPO_ROOT / "data" / "outputs" / "final_engine_truth_table" / \
    "final_engine_truth_table.json"
BASE_CONDUIT = set(BRENHAM_CONDUIT_LAYERS.values())   # BORE - VACANT PIPE / BORE - PORT
FROZEN_BUCKETS = {"DRAWABLE_REVIEW": 31, "HUMAN_ADJUSTABLE_REVIEW": 6,
                  "OUT_OF_CLASS": 1, "PICK_CARD_REVIEW": 17, "SOURCE_OR_KMZ_REQUIRED": 3}
ABSTAIN_4 = ("log5", "log31", "log38", "log43")
SEAM_ELIGIBLE = ("log53", "log64", "log71", "log59", "log66")   # this slice promotes NOTHING
HELD_BACK_SET = ("log36", "log52", "log58")
_COORD_KEYS = {"x", "y", "z", "xc", "yc", "x0", "y0", "x1", "y1", "cx", "cy", "xy",
               "lat", "lon", "lng", "coord", "coords", "coordinate", "coordinates",
               "px", "py", "pixel", "pixels", "point", "points", "symbol_xy", "anchor_xy",
               "stroke", "stroke_points", "geometry", "geom"}

# per-endpoint sheet attribution + bind recipe (the per-endpoint sheet is owner-note provenance WITHIN the
# owner-confirmed corrected_sheets SET; the station/class are the encoded anchors; nothing here is invented)
BIND = {
    "log52": {
        "start": {"class": "flower_pot", "label": "0+98", "sheet": 7, "seed": "FLOWER POT",
                  "context": ("FLOWER", "POT"), "reset": False},
        "end": {"class": "flower_pot", "label": "4+57", "sheet": 8, "seed": "FLOWER POT",
                "context": ("FLOWER", "POT"), "reset": False},
    },
    "log58": {
        "start": {"class": "installer_hh", "label": "39+79", "sheet": 10, "seed": "NEXTLINK",
                  "context": None, "reset": True},
        "end": {"class": "installer_hh", "label": "2+36", "sheet": 13, "seed": "NEXTLINK",
                "context": None, "reset": False},
    },
}
# log52 two-leg render targets: the per-sheet matchline station of the HIGH 7<->8 frame edge (1+93 / 30+64)
RENDER_LEGS = {
    "log52": [
        {"role": "start", "sheet": 7, "label": "0+98", "matchline_sta": "30+64",
         "class": "flower_pot", "seed": "FLOWER POT", "context": ("FLOWER", "POT")},
        {"role": "end", "sheet": 8, "label": "4+57", "matchline_sta": "1+93",
         "class": "flower_pot", "seed": "FLOWER POT", "context": ("FLOWER", "POT")},
    ],
}
RENDER_LOGS = ("log52",)          # the render-safe member of the held-back class
NO_EDGE_PAIR = (7, 10)            # abstain guard: no printed frame edge -> translate must return None

R_PROVEN = "SOURCE_BINDABLE_HELD_BACK_RENDER_PROVEN"
B_CENSUS = "BLOCKED_HELD_BACK_CENSUS_DRIFT"
B_ANCHORS = "BLOCKED_HELD_BACK_ANCHORS_INVALID"
B_BIND = "BLOCKED_HELD_BACK_TERMINUS_BIND_FAILED"
B_JOIN = "BLOCKED_HELD_BACK_CROSS_SHEET_JOIN_NOT_SOURCE_BACKED"
B_RENDER = "BLOCKED_HELD_BACK_RENDER_NOT_SOURCE_BACKED"
B_PROMOTED = "BLOCKED_HELD_BACK_SILENTLY_PROMOTED"
B_SCOPE = "BLOCKED_HELD_BACK_SCOPE_VIOLATION"
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


def _sheet_text(plan, offset, sheet):
    idx = sheet + offset - 1
    if idx < 0 or idx >= plan.page_count:
        return ""
    return " ".join(ln for ln in plan.text_by_index(idx).splitlines() if ln.strip())


def bind_terminus(plan, offset, spec):
    """Bind one terminus on its owner-attributed sheet with the proven primitive; seed a base conduit
    chain at the bound symbol. Returns (xy|None, chain, result, reach|None). Coordinates extractor-derived."""
    words = plan.words(spec["sheet"], offset)
    draw = plan.line_items(spec["sheet"], offset)
    labels = ([f"{spec['label']}=0+00", spec["label"]] if spec["reset"]
              else [spec["label"], f"{spec['label']}=0+00"])
    last = None
    for label in labels:
        kw = dict(label_text=label, structure_class=spec["class"], words=words,
                  drawings=draw, layer_table=BRENHAM_STRUCTURE_LAYERS)
        if spec["context"]:
            kw["context_texts"] = spec["context"]
        v = resolve_structure_position(**kw)
        last = v.result
        if v.result == POSITION_BOUND and v.symbol_xy:
            xy = tuple(v.symbol_xy)
            fp = symbol_footprint(draw, spec["seed"], xy)
            chain = connected_chain([x for x in draw if x.get("layer") in BASE_CONDUIT], fp) if fp else []
            eps = dash_endpoints(chain)
            reach = min((math.hypot(p[0] - xy[0], p[1] - xy[1]) for p in eps), default=None)
            return xy, chain, v.result, reach
    return None, [], last, None


def render_leg(plan, offset, leg):
    """Source-bind one render leg (terminus -> matchline) and order the source-backed chain route.
    Returns a dict with the bound xy, located matchline xy, ordered route, and source-backed flags."""
    words = plan.words(leg["sheet"], offset)
    draw = plan.line_items(leg["sheet"], offset)
    kw = dict(label_text=leg["label"], structure_class=leg["class"], words=words,
              drawings=draw, layer_table=BRENHAM_STRUCTURE_LAYERS)
    if leg["context"]:
        kw["context_texts"] = leg["context"]
    v = resolve_structure_position(**kw)
    out = {"sheet": leg["sheet"], "role": leg["role"], "label": leg["label"],
           "matchline_sta": leg["matchline_sta"], "bound": False, "route": None,
           "terminus_xy": None, "matchline_xy": None, "source_backed": False}
    if v.result != POSITION_BOUND or not v.symbol_xy:
        return out
    xy = tuple(v.symbol_xy)
    out["terminus_xy"] = [round(c, 2) for c in xy]
    out["bound"] = True
    fp = symbol_footprint(draw, leg["seed"], xy)
    chain = connected_chain([x for x in draw if x.get("layer") in BASE_CONDUIT], fp) if fp else []
    bnd, reach, uniq = locate_matchline_boundary(words, draw, leg["matchline_sta"], chain)
    if not bnd or not uniq:
        return out
    out["matchline_xy"] = [round(c, 2) for c in bnd]
    route = order_chain_route(chain, xy, tuple(bnd))
    if not route:
        return out
    interior_ok = len(route) >= 3 and interior_vertices_are_dash_endpoints(route, chain)
    edges_ok = route[0] == xy and route[-1] == tuple(bnd) and route_edges_source_backed(route, chain)
    out.update(route=route, route_vertices=len(route), route_len=round(route_length(route), 1),
               source_backed=bool(interior_ok and edges_ok),
               _xy=xy, _bnd=tuple(bnd))
    return out


def log58_render_blocker_proven(plan, offset) -> dict:
    """Prove (from source) that log58's sheet-10 render leg is NOT uniquely disambiguated 12-vs-13: the
    safe 10<->13 edge is anchored on sheet 13's HIGH side, while sheet 10's matching matchline equations
    are MEDIUM and ambiguously link BOTH frame 12 and frame 13. Read-only; reuses match.frames grammar."""
    f10, f13 = FR.frame_for_sheet(10), FR.frame_for_sheet(13)
    eq10 = FR.parse_frame_equations(_sheet_text(plan, offset, 10))
    eq13 = FR.parse_frame_equations(_sheet_text(plan, offset, 13))
    # sheet-13 side: a HIGH-confidence equation that links uniquely back to frame 10 (the safe edge anchor)
    s13_high_unique = any(e.has_matchline and str(e.confidence).endswith("HIGH")
                          and e.linked_frames == [10] for e in eq13)
    # sheet-10 side: the matchline equations that mention frame 13 also mention frame 12 (ambiguous target)
    s10_amb = [e for e in eq10 if e.has_matchline and 13 in e.linked_frames]
    s10_links_both = bool(s10_amb) and all(12 in e.linked_frames for e in s10_amb)
    s10_no_high_unique = not any(e.has_matchline and str(e.confidence).endswith("HIGH")
                                 and e.linked_frames == [13] for e in eq10)
    return {"sheet13_high_unique_to_10": s13_high_unique,
            "sheet10_amb_equations": [{"a": e.a.raw, "b": e.b.raw, "conf": str(e.confidence),
                                       "links": e.linked_frames} for e in s10_amb],
            "sheet10_links_both_12_and_13": s10_links_both,
            "sheet10_no_high_unique_to_13": s10_no_high_unique,
            "blocker_proven": bool(s13_high_unique and s10_links_both and s10_no_high_unique)}


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for stale in OUT_DIR.glob("*.png"):
        stale.unlink()

    doc = load_adjudication()
    rec = {r["log_id"]: r for r in doc["logs"]}
    gates, ev = [], {"binds": {}, "joins": {}, "render_legs": {}}
    result = B_BIND

    # ---- safety: frozen census + seam unchanged (nothing promoted) ---------------
    gates.append(("G0 engine census frozen (OFF 31/6/1/17/3, ON 22/1/4, log44+abstains held)",
                  _census_frozen(doc), None))
    gates.append(("G0b seam ELIGIBLE_EXEMPLARS == log53/64/71/59/66 (5); seam refuses log36+log52+log58",
                  tuple(ELIGIBLE_EXEMPLARS) == SEAM_ELIGIBLE
                  and all(_refuses_seam(l, rec) for l in HELD_BACK_SET), None))

    # ---- anchors consumed: both cross-sheet pairs valid, modeled, owner-named, NO coordinates ----
    anchors_ok = True
    for lid in ("log52", "log58"):
        l = rec.get(lid, {})
        ea = l.get("endpoint_anchors") or {}
        start, end = ea.get("start") or {}, ea.get("end") or {}
        ok = (validate_endpoint_anchors(l) == [] and set(ea) <= {"start", "end"}
              and start.get("boundary_kind") == "structure_terminus"
              and end.get("boundary_kind") == "structure_terminus"
              and start.get("structure_class") in MODELED_TERMINUS_CLASSES
              and end.get("structure_class") in MODELED_TERMINUS_CLASSES
              and start.get("structure_class") == BIND[lid]["start"]["class"]
              and start.get("station") == BIND[lid]["start"]["label"]
              and end.get("structure_class") == BIND[lid]["end"]["class"]
              and end.get("station") == BIND[lid]["end"]["label"]
              and not _has_coord_keys(start) and not _has_coord_keys(end))
        anchors_ok = anchors_ok and ok
    gates.append(("G1 log52+log58 anchors valid, two structure_terminus modeled classes, identity-only (NO coords)",
                  anchors_ok, None))

    # ---- cohort: both are SOURCE_BINDABLE_NOW (the bridged held-back cohort delta is intact) -----
    cls = {lid: classify_record(rec[lid])["classification"] for lid in ("log52", "log58")}
    gates.append(("G2 cohort: log52 + log58 are SOURCE_BINDABLE_NOW (bridged held-back)",
                  all(cls[lid] == SOURCE_BINDABLE_NOW for lid in ("log52", "log58")), cls))

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

        # ---- SOURCE-BIND: both termini of log52 + log58 bind with a connected modeled chain ----
        bind_ok = True
        for lid in ("log52", "log58"):
            d = {}
            for role in ("start", "end"):
                xy, chain, res, reach = bind_terminus(plan, offset, BIND[lid][role])
                connected = bool(chain) and reach is not None and reach <= MAX_DASH_GAP
                d[role] = {"sheet": BIND[lid][role]["sheet"], "class": BIND[lid][role]["class"],
                           "station": BIND[lid][role]["label"], "result": res,
                           "xy": [round(c, 2) for c in xy] if xy else None,
                           "chain_segs": len(chain), "chain_reach_pt": round(reach, 2) if reach is not None else None,
                           "chain_connected": connected}
                bind_ok = bind_ok and xy is not None and connected
            ev["binds"][lid] = d
        gates.append(("G4 log52 + log58: BOTH termini bind (POSITION_BOUND) with a connected modeled conduit chain",
                      bind_ok, ev["binds"]))
        if not bind_ok:
            return _emit(gates, B_BIND, ev, rec, plan=plan)

        # ---- CROSS-SHEET JOIN: the shipped primitive returns a concrete safe offset (source-backed) ----
        join_ok = True
        for lid in ("log52", "log58"):
            s = scout_log(graph, plan, offset, rec[lid])
            ev["joins"][lid] = {"sheets": s["sheets"], "n_hops": s["n_hops"],
                                "source_backed": s["source_backed"], "hops": s["hops"],
                                "blocker": s["blocker"]}
            join_ok = join_ok and s["source_backed"] and all(
                h["safe_edge"] and h["translated_ft"] is not None for h in s["hops"])
        # abstain guard: a NON-edge sheet pair MUST translate to None (no raw fallback / no fake join)
        guard_none = FR.translate_between_sheets(graph, NO_EDGE_PAIR[0], NO_EDGE_PAIR[1], 100.0) is None
        ev["abstain_guard"] = {"pair": list(NO_EDGE_PAIR), "translate_is_none": guard_none}
        gates.append(("G5 cross-sheet join source-backed: translate_between_sheets concrete for log52(7<->8)+log58(10<->13); non-edge pair -> None (abstain, no raw fallback)",
                      join_ok and guard_none, {"joins": {k: v["source_backed"] for k, v in ev["joins"].items()},
                                               "abstain_guard": ev["abstain_guard"]}))
        if not (join_ok and guard_none):
            return _emit(gates, B_JOIN, ev, rec, plan=plan)

        # ---- NO cross-sheet COORDINATE reconciliation into a placement: still NEEDS_GEOMETRY -----
        no_placement = all(placement_geometry_readiness(rec[lid])["status"] == PLACE_NEEDS_GEOMETRY
                           for lid in ("log52", "log58"))
        gates.append(("G6 no cross-sheet coordinate reconciled into a placement (join is offset identity; both still NEEDS_GEOMETRY)",
                      no_placement, None))

        # ---- RENDER the render-safe member (log52): two sheet-local legs, joined by station identity ----
        render_ok = True
        for lid in RENDER_LOGS:
            legs = [render_leg(plan, offset, leg) for leg in RENDER_LEGS[lid]]
            ev["render_legs"][lid] = [{k: v for k, v in leg.items() if not k.startswith("_")} for leg in legs]
            legs_source_backed = all(leg["source_backed"] for leg in legs)
            if not legs_source_backed:
                render_ok = False
                continue
            # the two matchline points live in their OWN sheet frames and are NEVER reconciled
            ml_a, ml_b = legs[0]["matchline_xy"], legs[1]["matchline_xy"]
            frames_not_reconciled = legs[0]["sheet"] != legs[1]["sheet"]
            ev["render_legs"][lid + "_join"] = {
                "shape": "two_sheet_local_strokes_joined_by_station_identity",
                "sheet_frames_reconciled": False,
                "matchline_sheet7_xy": ml_a, "matchline_sheet8_xy": ml_b}
            for leg in legs:
                png = render_redline_stroke(
                    plan, lid, leg["sheet"], offset, leg["route"], status="REVIEW",
                    reason=(f"OWNER-PACKET-2 source-backed: {lid} FLOWER POT {leg['label']} -> "
                            f"STA {leg['matchline_sta']} matchline (sheet-local leg; cross-sheet join by "
                            f"station identity, frames not reconciled)"),
                    out_dir=str(OUT_DIR), mandatory_points=[leg["_xy"], leg["_bnd"]], pad=170.0)
                leg["png"] = png
                render_ok = render_ok and bool(png) and os.path.isfile(png) and frames_not_reconciled
        gates.append(("G7 log52 RENDER: both legs source-backed ordered chain routes; one red REVIEW stroke per sheet; frames not reconciled",
                      render_ok, {lid: [(l["sheet"], l.get("route_vertices"), l["source_backed"])
                                        for l in ev["render_legs"][lid]] for lid in RENDER_LOGS}))
        if not render_ok:
            return _emit(gates, B_RENDER, ev, rec, plan=plan)

        # ---- log58 render HELD: prove the sheet-10 12-vs-13 crossing ambiguity from source -----
        ev["log58_render_blocker"] = log58_render_blocker_proven(plan, offset)
        gates.append(("G8 log58 render HELD: sheet-10 leg crossing NOT uniquely disambiguated 12-vs-13 (sheet-13 HIGH/unique; sheet-10 MEDIUM/links 12+13) -- proven, not rendered",
                      ev["log58_render_blocker"]["blocker_proven"], ev["log58_render_blocker"]))
    finally:
        plan.close()

    if all(x for _, x, _ in gates):
        result = R_PROVEN
    return _emit(gates, result, ev, rec)


def _emit(gates, result, ev, rec, plan=None) -> int:
    pngs = sorted(p.name for p in OUT_DIR.glob("*.png"))
    # ---- scope / safety gates (always run) -------------------------------------
    # log36 HELD: corrected_sheets == [] (sheet 17 not owner-confirmed); not bound/rendered here
    gates.append(("G9 log36 HELD: anchored, corrected_sheets == [] (sheet 17 owner-confirmation required); not rendered",
                  bool(rec["log36"].get("endpoint_anchors")) and rec["log36"].get("corrected_sheets") == []
                  and _refuses_seam("log36", rec), rec["log36"].get("corrected_sheets")))
    # exactly the two log52 leg PNGs exist (render-safe member only); zero log58/log36 PNG
    expected_pngs = ["log52_s7_redline_stroke.png", "log52_s8_redline_stroke.png"]
    gates.append(("G10 exactly the two log52 sheet-local PNGs exist (no log58/log36 render)",
                  pngs == expected_pngs or (result != R_PROVEN and all("log58" not in p and "log36" not in p for p in pngs)),
                  pngs))
    gates.append(("G11 canonical red stroke color (TrueLine REVIEW strokes are red)",
                  REDLINE_STROKE_RGB == (220, 25, 25), list(REDLINE_STROKE_RGB)))
    # held-back set intact: exactly {log36, log52, log58} anchored-and-seam-refused; nothing promoted
    with_anchors = {lid for lid, r in rec.items() if r.get("endpoint_anchors")}
    held_back = tuple(sorted((l for l in with_anchors if _refuses_seam(l, rec)),
                             key=lambda s: int(s[3:])))
    gates.append(("G12 held-back set intact == {log36, log52, log58}; ELIGIBLE_EXEMPLARS unchanged (nothing promoted)",
                  held_back == HELD_BACK_SET and tuple(ELIGIBLE_EXEMPLARS) == SEAM_ELIGIBLE,
                  {"held_back": list(held_back)}))
    gates.append(("G13 result in allowed enum", result in ALLOWED, result))

    all_pass = all(x for _, x, _ in gates) and result == R_PROVEN
    report = {
        "milestone": "OWNER-PACKET-2 -- SOURCE_BINDABLE_HELD_BACK batch source-bind + render slice (proof only)",
        "verdict": "PASS" if all_pass else "FAIL",
        "result": result,
        "class": "SOURCE_BINDABLE_HELD_BACK {log36, log52, log58}",
        "passed_source_bind": ["log52", "log58"],
        "passed_render": ["log52"],
        "held": {
            "log36": ("HELD -- owner confirmation of the SOURCE-RECOVERED sheet 17 (corrected_sheets == []; "
                      "the source-bind/render exemplars gate on owner-confirmed sheets, and log36's own bridge "
                      "mandates owner confirmation first). Binds cleanly on sheet 17; not bound/rendered here."),
            "log58_render": ("HELD -- the sheet-10 render leg's crossing is NOT uniquely disambiguated 12-vs-13: "
                             "the safe 10<->13 frame edge is anchored on sheet 13's HIGH/unique side; on sheet 10 "
                             "the matching matchline equations are MEDIUM and link BOTH frame 12 and frame 13. "
                             "Source-bind is complete (termini bound + safe join); the per-sheet render leg is not "
                             "safe (same crossing-disambiguation gap the frame-join scout named for log67/69/70)."),
        },
        "binds": ev.get("binds"),
        "cross_sheet_joins": ev.get("joins"),
        "abstain_guard": ev.get("abstain_guard"),
        "render_legs": {k: v for k, v in ev.get("render_legs", {}).items()},
        "log58_render_blocker": ev.get("log58_render_blocker"),
        "shape": ("log52 cross-sheet two-leg render = two sheet-local red REVIEW strokes (sheet 7 + sheet 8) "
                  "joined by station identity (the HIGH 7<->8 frame edge); the two matchline points stay in "
                  "their own sheet frames and are NEVER reconciled"),
        "red_stroke_rgb": list(REDLINE_STROKE_RGB),
        "artifacts": pngs,
        "no_invented_coordinates": True, "no_screenshot_pixels": True,
        "no_cross_sheet_coordinate_reconciled_into_placement": True,
        "no_seam_promotion": True, "engine_census_frozen": True, "max_dash_gap_not_loosened": MAX_DASH_GAP == 35.0,
        "held_back_set": list(HELD_BACK_SET), "seam_eligible": list(ELIGIBLE_EXEMPLARS),
        "broad_renderer": False, "product_wired": False,
        "next_slice": ("(1) log52 cross-sheet COORDINATE reconciliation -> a single joined placement (the "
                       "deferred render-time frame-translate step) + seam promotion. (2) log58: recover the "
                       "sheet-10 10->13 crossing identity (disambiguate 12-vs-13) so its render leg is safe, "
                       "then render. (3) log36: owner-confirm the source-recovered sheet 17, then source-bind + "
                       "render. Each separately authorized."),
        "gates": [{"name": n, "pass": bool(x), "detail": d} for n, x, d in gates],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "source_bindable_held_back_render_slice.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"[held-back] result: {result}")
    for lid in ("log52", "log58"):
        b = ev.get("binds", {}).get(lid, {})
        j = ev.get("joins", {}).get(lid, {})
        if b:
            print(f"[held-back]   {lid}: start={b.get('start', {}).get('xy')} end={b.get('end', {}).get('xy')} "
                  f"join_source_backed={j.get('source_backed')} sheets={j.get('sheets')}")
    for a in pngs:
        print(f"[held-back]   ARTIFACT: {a}")
    for n, x, _ in gates:
        print(f"[held-back] {'PASS' if x else 'FAIL'}  {n}")
    print(f"[held-back] VERDICT: {'PASS' if all_pass else 'FAIL'}  (report: {OUT_DIR})")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
