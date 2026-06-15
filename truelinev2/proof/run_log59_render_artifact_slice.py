r"""OWNER-PACKET-2 -- log59 RENDER ARTIFACT slice (contained proof artifact; log59-only).

Draws log59's redline on the real sheet-21 PDF so Patrick can VISUALLY inspect it, mirroring the
controlled log64 render-artifact style (log59-only, single-sheet) but with the log71 ORDERED-CHAIN
route mode -- because log59's direct corridor is NOT continuous:

  sheet 21:  INSTALLER HH start (STA 2+76)  ->  FLOWER POT end (STA 4+46), HH - HH = 170'

Every endpoint is RE-DERIVED from source here via the SAME proven primitives the log59 source-bind
slice used (resolve_structure_position for both termini, plain station labels -- log59's start is a
NON-reset '2+76', not a '=0+00' token) -- no hardcoded/invented coordinate -- and gated against the
proven bind values. The stroke FOLLOWS THE DRAWN ROUTE via the ordered source-backed CHAIN PATH
(order_chain_route, reused from the log71 render slice): the shortest path through the bound
BORE - VACANT PIPE / BORE - PORT conduit chain's drawn dashes from the installer HH to the flower pot.

log59's direct horizontal corridor has a 35.64 pt gap -- just ABOVE MAX_DASH_GAP (35.0) -- so a naive
continuous/straight corridor is NOT source-backed and is REFUSED here (render_mode is FORCED to
ordered_chain_path; the discontinuity is re-proven from source, not assumed). The ordered chain path
instead threads the real drawn dashes (each within MAX_DASH_GAP), so every drawn edge is a real source
dash or a <= MAX_DASH_GAP gap hop -- never a fabricated straight jump bridging the 35.64 gap. MAX_DASH_GAP
is NOT loosened.

Red TrueLine stroke only (render.crop.REDLINE_STROKE_RGB), REVIEW-style (dashed). Source PDF/CAD
evidence colors are never touched; only TrueLine's own drawn REVIEW stroke is governed -- and it is
red. Source-backed REVIEW/proof artifact, NOT a broad renderer and NOT wired into product/UI/API. PNG
+ JSON are written under the gitignored data/outputs path and are NOT committed.

Sheet 21 is OWNER-CONFIRMED (2026-06-15): log59's corrected_sheets == [21] and log59 has been promoted
into the seam contract eligible set (a later, separately-authorized slice). Census stays frozen (the
corrected_sheets confirmation changes only log59's placement-readiness reasons, not any bucket/count).

Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_log59_render_artifact_slice
"""
from __future__ import annotations

import json
import math
import os

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
    activation_summary,
    apply_adjudications,
    load_adjudication,
    parent_run_duplicate_check,
)
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.proof.run_brenham_corpus import EXPECTED_COUNT, PDF, enumerate_corpus
from truelinev2.proof.run_log59_sheet21_source_bind_slice import (
    INSTALLER_SYMBOL_LAYER,
    SHEET,
    SPAN_FT,
    _HH_170,
)
from truelinev2.proof.run_log64_sheet21_source_bind_slice import corridor_is_continuous
from truelinev2.proof.run_log71_render_artifact_slice import order_chain_route, route_length
from truelinev2.proof.run_log71_two_leg_source_bind_slice import leg_corridor_band
from truelinev2.proof.run_reviewer_service_contract import resolve_corpus
from truelinev2.render.crop import REDLINE_STROKE_RGB, render_redline_stroke
from truelinev2.seam import ELIGIBLE_EXEMPLARS, build_seam_payload
from truelinev2.stations import parse_station

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "log59_render_artifact"
TRUTH = _REPO_ROOT / "data" / "outputs" / "final_engine_truth_table" / \
    "final_engine_truth_table.json"
BASE_CONDUIT = set(BRENHAM_CONDUIT_LAYERS.values())   # BORE - VACANT PIPE / BORE - PORT
FROZEN_BUCKETS = {"DRAWABLE_REVIEW": 31, "HUMAN_ADJUSTABLE_REVIEW": 6,
                  "OUT_OF_CLASS": 1, "PICK_CARD_REVIEW": 17, "SOURCE_OR_KMZ_REQUIRED": 3}
ABSTAIN_4 = ("log5", "log31", "log38", "log43")
# proven sheet-21 binds (extractor-derived in 408aa61; the render is gated to match these)
PROVEN = {"start": (250.96, 308.65), "end": (492.55, 311.61)}
MATCH_TOL = 4.0
EDGE_EPS = 0.6   # node-rounding slack for matching a route edge to a real drawn dash / endpoint

R_CREATED = "LOG59_RENDER_ARTIFACT_CREATED"
B_ENDPOINT = "BLOCKED_LOG59_RENDER_ENDPOINT_MISMATCH"
B_NO_CHAIN = "BLOCKED_LOG59_RENDER_CHAIN_NOT_CONNECTED"
B_DIRECT_CONTINUOUS = "BLOCKED_LOG59_RENDER_DIRECT_CORRIDOR_CONTINUOUS"
B_ROUTE = "BLOCKED_LOG59_RENDER_ROUTE_NOT_SOURCE_BACKED"
B_SPAN = "BLOCKED_LOG59_RENDER_SPAN_ANNOTATION_MISMATCH"
B_FAILED = "BLOCKED_LOG59_RENDER_ARTIFACT_FAILED"
ALLOWED = {R_CREATED, B_ENDPOINT, B_NO_CHAIN, B_DIRECT_CONTINUOUS, B_ROUTE, B_SPAN, B_FAILED}


def interior_vertices_are_dash_endpoints(route, chain, eps: float = EDGE_EPS) -> bool:
    """Every INTERIOR route vertex (not the two proven anchors) coincides with a real drawn conduit
    dash endpoint (within ``eps`` of the node rounding). Proves the stroke threads the source dashes
    and invents no interior coordinate. Pure."""
    eps_pts = dash_endpoints(chain)
    return all(any(math.hypot(p[0] - q[0], p[1] - q[1]) <= eps for q in eps_pts)
               for p in route[1:-1])


def route_edges_source_backed(route, chain, max_gap: float = MAX_DASH_GAP,
                              eps: float = EDGE_EPS) -> bool:
    """Every consecutive route EDGE is either a real drawn dash (its two ends are the two ends of one
    drawn line in the chain) OR a dash-gap hop <= ``max_gap``. This is the honesty law for log59's
    ordered chain path: no edge fabricates a straight jump across the 35.64 pt direct-corridor gap;
    a long edge is allowed ONLY when it IS a real drawn dash. Pure."""
    dashes = [((ln[0], ln[1]), (ln[2], ln[3]))
              for seg in chain for ln in (seg.get("lines") or ())]

    def is_drawn_dash(a, b) -> bool:
        for da, db in dashes:
            if ((math.hypot(a[0] - da[0], a[1] - da[1]) <= eps and math.hypot(b[0] - db[0], b[1] - db[1]) <= eps)
                    or (math.hypot(a[0] - db[0], a[1] - db[1]) <= eps and math.hypot(b[0] - da[0], b[1] - da[1]) <= eps)):
                return True
        return False

    for a, b in zip(route, route[1:]):
        if math.hypot(a[0] - b[0], a[1] - b[1]) <= max_gap + eps:
            continue
        if not is_drawn_dash(a, b):
            return False
    return True


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


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for stale in OUT_DIR.glob("*.png"):
        stale.unlink()

    doc = load_adjudication()
    rec = {r["log_id"]: r for r in doc["logs"]}
    l59 = rec.get("log59") or {}
    ea = l59.get("endpoint_anchors") or {}
    start_a, end_a = ea.get("start") or {}, ea.get("end") or {}
    gates, ev = [], {"sheet": SHEET}

    gates.append(("G0 engine census frozen (OFF 31/6/1/17/3, ON 22/1/4, log44+abstains held)",
                  _census_frozen(doc), None))
    # preserve behavior: log53 + log64 + log71 encoded anchors untouched; log59 anchors as encoded
    l53s = (rec["log53"].get("endpoint_anchors") or {}).get("start") or {}
    l64s = (rec["log64"].get("endpoint_anchors") or {}).get("start") or {}
    l71s = (rec["log71"].get("endpoint_anchors") or {}).get("start") or {}
    gates.append(("G0b log53/log64/log71 anchors unchanged; log59 installer_hh @2+76 -> flower_pot @4+46",
                  l53s.get("structure_class") == "nextlink_hh"
                  and l64s.get("structure_class") == "installer_hh" and l64s.get("station") == "3+69"
                  and l71s.get("structure_class") == "nextlink_hh"
                  and start_a.get("structure_class") == "installer_hh" and start_a.get("station") == "2+76"
                  and end_a.get("structure_class") == "flower_pot" and end_a.get("station") == "4+46", None))
    # sheet 21 is SOURCE-RECOVERED bridge evidence ONLY: corrected_sheets stays [] (NOT promoted)
    gates.append(("G0c sheet 21 OWNER-CONFIRMED; corrected_sheets == [21]",
                  l59.get("corrected_sheets") == [21], {"corrected_sheets": l59.get("corrected_sheets")}))

    if not os.path.isfile(PDF):
        gates.append(("G1 plan PDF present", False, f"missing {PDF}"))
        return _emit(gates, B_FAILED, ev, [], rec)
    corpus_dir, _ = resolve_corpus()
    corpus = {p.stem: p for p in enumerate_corpus(corpus_dir)} if os.path.isdir(corpus_dir) else {}
    gates.append(("G1 plan PDF + corpus present",
                  os.path.isfile(PDF) and len(corpus) == EXPECTED_COUNT, len(corpus)))

    plan = PlanPdf(PDF)
    artifacts = []
    result = B_FAILED
    try:
        dialect = select_dialect(plan)
        offset = dialect.calibrate(plan, 13)
        words = plan.words(SHEET, offset)
        draw = plan.line_items(SHEET, offset)
        lines = plan.lines(SHEET, offset)

        # ---- re-derive both endpoints from source (the proven binds) -------------
        # log59's start is a PLAIN station '2+76' (NOT a '=0+00' reset token, distinct from log64/log71)
        sv = resolve_structure_position(label_text=start_a.get("station"),
                                        structure_class="installer_hh", words=words, drawings=draw,
                                        layer_table=BRENHAM_STRUCTURE_LAYERS)
        pv = resolve_structure_position(label_text=end_a.get("station"), structure_class="flower_pot",
                                        words=words, drawings=draw, layer_table=BRENHAM_STRUCTURE_LAYERS,
                                        context_texts=("FLOWER", "POT"))
        s_xy = tuple(sv.symbol_xy) if (sv.result == POSITION_BOUND and sv.symbol_xy) else None
        e_xy = tuple(pv.symbol_xy) if (pv.result == POSITION_BOUND and pv.symbol_xy) else None
        ev["start_symbol_xy"] = [round(c, 2) for c in s_xy] if s_xy else None
        ev["end_symbol_xy"] = [round(c, 2) for c in e_xy] if e_xy else None

        def near(a, key):
            b = PROVEN[key]
            return a is not None and math.hypot(a[0] - b[0], a[1] - b[1]) <= MATCH_TOL
        endpoints_ok = near(s_xy, "start") and near(e_xy, "end")
        gates.append(("G2 both endpoints re-derived from source match the proven bind (<= 4 pt)",
                      endpoints_ok, {"start": ev["start_symbol_xy"], "end": ev["end_symbol_xy"]}))
        if not endpoints_ok:
            return _emit(gates, B_ENDPOINT, ev, artifacts, rec)

        # ---- source conduit chain connected to BOTH bound symbols ----------------
        fp = symbol_footprint(draw, INSTALLER_SYMBOL_LAYER, s_xy)
        chain = connected_chain([x for x in draw if x.get("layer") in BASE_CONDUIT], fp) if fp else []
        eps = dash_endpoints(chain)
        reach_start = min((math.hypot(p[0] - s_xy[0], p[1] - s_xy[1]) for p in eps), default=None)
        reach_end = min((math.hypot(p[0] - e_xy[0], p[1] - e_xy[1]) for p in eps), default=None)
        ev["chain_segs"] = len(chain)
        ev["chain_to_start_symbol_pt"] = round(reach_start, 2) if reach_start is not None else None
        ev["chain_to_end_symbol_pt"] = round(reach_end, 2) if reach_end is not None else None
        both_connected = (bool(chain) and reach_start is not None and reach_start <= MAX_DASH_GAP
                          and reach_end is not None and reach_end <= MAX_DASH_GAP)
        gates.append(("G3 base conduit chain connects BOTH bound symbols (<= MAX_DASH_GAP)",
                      both_connected, {"to_start": ev["chain_to_start_symbol_pt"],
                                       "to_end": ev["chain_to_end_symbol_pt"]}))
        if not both_connected:
            return _emit(gates, B_NO_CHAIN, ev, artifacts, rec)

        # ---- render-mode is FORCED to ordered_chain_path: re-prove the direct corridor is
        #      DISCONTINUOUS from source (35.64 > MAX_DASH_GAP) -- a continuous/straight corridor
        #      is NOT source-backed and is refused (no fake straight corridor). --------------
        band, lo, hi, axis = leg_corridor_band(eps, s_xy, e_xy)
        continuous = corridor_is_continuous(band, lo, hi)
        max_gap = max((band[i + 1] - band[i] for i in range(len(band) - 1)), default=0.0)
        ev["corridor_axis"] = axis
        ev["corridor_band_points"] = len(band)
        ev["corridor_max_gap_pt"] = round(max_gap, 2)
        ev["direct_corridor_continuous"] = continuous
        ev["render_mode"] = "ordered_chain_path"
        forced_chain_mode = (not continuous) and max_gap > MAX_DASH_GAP
        gates.append(("G4 direct corridor DISCONTINUOUS (max gap > MAX_DASH_GAP) -> ordered_chain_path FORCED (no straight corridor)",
                      forced_chain_mode, {"axis": axis, "max_gap": ev["corridor_max_gap_pt"],
                                          "continuous": continuous}))
        if not forced_chain_mode:
            return _emit(gates, B_DIRECT_CONTINUOUS, ev, artifacts, rec)

        # ---- build the ordered source-backed chain path (start -> end) -----------
        route = order_chain_route(chain, s_xy, e_xy)
        ev["route_vertices"] = len(route)
        ev["route_len_pt"] = round(route_length(route), 1) if route else None
        ev["straight_len_pt"] = round(math.hypot(s_xy[0] - e_xy[0], s_xy[1] - e_xy[1]), 1)
        # follows the connected chain (>= 1 interior source vertex), every interior vertex is a real
        # dash endpoint, and every edge is a real drawn dash or a <= MAX_DASH_GAP hop (no fabricated jump)
        interior_ok = len(route) >= 3 and interior_vertices_are_dash_endpoints(route, chain)
        edges_ok = bool(route) and route[0] == s_xy and route[-1] == e_xy \
            and route_edges_source_backed(route, chain)
        route_ok = interior_ok and edges_ok
        gates.append(("G5 stroke is the ordered source-backed chain path (>= 3 real vertices; every edge a dash or <= MAX_DASH_GAP hop)",
                      route_ok, {"vertices": len(route), "route_len": ev["route_len_pt"],
                                 "straight_len": ev["straight_len_pt"]}))
        if not route_ok:
            return _emit(gates, B_ROUTE, ev, artifacts, rec)

        # ---- HH-HH=170' annotation + station span corroboration ------------------
        hh = [ln for ln in lines if _HH_170.search(ln)]
        span = parse_station(end_a.get("station")) - parse_station(start_a.get("station"))
        ev["hh_hh_170_lines"] = hh[:3]
        ev["station_span_ft"] = span
        span_ok = bool(hh) and abs(span - SPAN_FT) <= 0.5
        gates.append(("G6 HH-HH=170' annotation present on sheet 21 + station span 4+46-2+76 = 170'",
                      span_ok, {"annotation": bool(hh), "span_ft": span}))
        if not span_ok:
            return _emit(gates, B_SPAN, ev, artifacts, rec)

        # ---- render the single sheet-local red REVIEW stroke ---------------------
        png = render_redline_stroke(
            plan, "log59", SHEET, offset, route, status="REVIEW",
            reason="OWNER-PACKET-2 source-backed: INSTALLER HH 2+76 -> 4+46 FLOWER POT (170'; ordered chain path, BORE - VACANT PIPE corridor)",
            out_dir=str(OUT_DIR), mandatory_points=[s_xy, e_xy], pad=170.0)
        artifacts = [png] if png else []
        gates.append(("G7 PNG artifact rendered (red REVIEW stroke)",
                      png is not None and os.path.isfile(png), png))
        if not (png and os.path.isfile(png)):
            return _emit(gates, B_FAILED, ev, artifacts, rec)
        result = R_CREATED
    finally:
        plan.close()

    return _emit(gates, result, ev, artifacts, rec)


def _emit(gates, result, ev, artifacts, rec) -> int:
    pngs = sorted(p.name for p in OUT_DIR.glob("*.png"))
    gates.append(("G8 exactly one log59 sheet-21 PNG (log59-only, sheet-local)",
                  pngs == ["log59_s21_redline_stroke.png"], pngs))
    gates.append(("G9 canonical red stroke color", REDLINE_STROKE_RGB == (220, 25, 25),
                  list(REDLINE_STROKE_RGB)))
    # scope / safety gates (always run): no promotion, no eligibility expansion, near-misses untouched
    l59 = rec.get("log59") or {}
    gates.append(("G10 log59 corrected_sheets == [21]; seam-PROMOTED (ELIGIBLE_EXEMPLARS == 4; seam builds log59)",
                  l59.get("corrected_sheets") == [21]
                  and tuple(ELIGIBLE_EXEMPLARS) == ("log53", "log64", "log71", "log59")
                  and not _refuses_seam("log59", rec), None))
    gates.append(("G11 log36 un-anchored + blank; log66 source-bound but NOT seam-promoted (anchors, corrected_sheets [10], seam refuses)",
                  not rec["log36"].get("endpoint_anchors") and rec["log36"].get("corrected_sheets") == []
                  and rec["log66"].get("endpoint_anchors") and rec["log66"].get("corrected_sheets") == [10]
                  and _refuses_seam("log66", rec), None))
    gates.append(("G12 result in allowed enum", result in ALLOWED, result))
    created = result == R_CREATED
    all_pass = all(x for _, x, _ in gates) and created
    report = {
        "milestone": "OWNER-PACKET-2 -- log59 render artifact (contained proof; visual inspection)",
        "verdict": "PASS" if all_pass else "FAIL",
        "result": result, "target": "log59 ONLY", "sheet": SHEET,
        "shape": "single_sheet_structure_to_structure (log64 family); ordered_chain_path route (log71 mode)",
        "endpoints": {"start": {"structure_class": "installer_hh", "station": "2+76", "xy": ev.get("start_symbol_xy")},
                      "end": {"structure_class": "flower_pot", "station": "4+46", "xy": ev.get("end_symbol_xy")}},
        "render_mode": ev.get("render_mode"),
        "route": {"vertices": ev.get("route_vertices"), "route_len_pt": ev.get("route_len_pt"),
                  "straight_len_pt": ev.get("straight_len_pt"),
                  "chain_segs": ev.get("chain_segs"),
                  "direct_corridor_continuous": ev.get("direct_corridor_continuous"),
                  "direct_corridor_max_gap_pt": ev.get("corridor_max_gap_pt"),
                  "reach_to_start_pt": ev.get("chain_to_start_symbol_pt"),
                  "reach_to_end_pt": ev.get("chain_to_end_symbol_pt")},
        "artifacts": artifacts,
        "red_stroke_rgb": list(REDLINE_STROKE_RGB),
        "sheet_21_provenance": ("SOURCE-RECOVERED by the near-miss scout, now OWNER-CONFIRMED 2026-06-15; "
                                "corrected_sheets == [21]; log59 promoted into the seam contract eligible set"),
        "sheet_local_only": True, "log59_only": True, "single_sheet": True,
        "source_corridor_layers": sorted(BASE_CONDUIT),
        "max_dash_gap_not_loosened": MAX_DASH_GAP == 35.0,
        "coords_are_extractor_derived": True, "no_invented_coordinates": True,
        "no_screenshot_pixels": True, "no_cross_sheet": True, "no_fake_straight_corridor": True,
        "corrected_sheets_owner_confirmed": True, "seam_promoted": True,
        "broad_renderer": False, "product_wired": False,
        "next_slice": ("log59 owner-confirmation + seam promotion now COMPLETE; next growth is the next "
                       "endpoint-anchor bridge (log36; log66 since bridged)."),
        "evidence": ev,
        "gates": [{"name": n, "pass": bool(x), "detail": d} for n, x, d in gates],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "log59_render_artifact.json").write_text(json.dumps(report, indent=2, default=str),
                                                        encoding="utf-8")
    print(f"[log59-render] result: {result}")
    for k in ("start_symbol_xy", "end_symbol_xy", "chain_segs", "chain_to_start_symbol_pt",
              "chain_to_end_symbol_pt", "corridor_axis", "corridor_band_points", "corridor_max_gap_pt",
              "direct_corridor_continuous", "render_mode", "route_vertices", "route_len_pt",
              "straight_len_pt", "station_span_ft"):
        if k in ev:
            print(f"[log59-render]   {k}: {ev[k]}")
    for a in artifacts:
        print(f"[log59-render]   ARTIFACT: {a}")
    for n, x, _ in gates:
        print(f"[log59-render] {'PASS' if x else 'FAIL'}  {n}")
    print(f"[log59-render] VERDICT: {'PASS' if all_pass else 'FAIL'}  (report: {OUT_DIR})")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
