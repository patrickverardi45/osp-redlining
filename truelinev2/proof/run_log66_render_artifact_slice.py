r"""OWNER-PACKET-2 -- log66 RENDER ARTIFACT slice (contained proof artifact; log66-only).

Draws log66's redline on the real sheet-10 PDF so Patrick can VISUALLY inspect it, mirroring the
controlled log59 render-artifact style (log66-only, single-sheet) with the log71 ORDERED-CHAIN route
mode -- because log66's direct corridor is NOT continuous:

  sheet 10:  INSTALLER HH start (STA 0+55 = 0+00)  ->  NEXTLINK HH end (STA 45+33 = 0+00), HH - HH = 55'

Every endpoint is RE-DERIVED from source here via the SAME proven primitives the log66 source-bind
slice used -- the START installer HH via resolve_structure_position with the owner reset token
'0+55=0+00' (the log64 reset-start), the END nextlink HH via resolve_nextlink_hh_callout (nextlink_hh
has NO BRENHAM_STRUCTURE_LAYERS entry; it binds ONLY through the committed callout locator, the
log53/log71 precedent) -- no hardcoded/invented coordinate -- and gated against the proven bind values.
The stroke FOLLOWS THE DRAWN ROUTE via the ordered source-backed CHAIN PATH (order_chain_route, reused
from the log71 render slice): the shortest path through the bound BORE - VACANT PIPE / BORE - PORT
conduit chain's drawn dashes from the installer HH to the nextlink HH.

log66's direct horizontal corridor has a 36.36 pt gap -- just ABOVE MAX_DASH_GAP (35.0) -- so a naive
continuous/straight corridor is NOT source-backed and is REFUSED here (render_mode is FORCED to
ordered_chain_path; the discontinuity is re-proven from source, not assumed). The ordered chain path
instead threads the real drawn dashes (each within MAX_DASH_GAP), so every drawn edge is a real source
dash or a <= MAX_DASH_GAP gap hop -- never a fabricated straight jump bridging the 36.36 gap. MAX_DASH_GAP
is NOT loosened.

Span corroboration is the printed 'HH - HH = 55'' annotation + the owner span_ft = 55' -- NOT a station
subtraction: both ends reset to 0+00 in DIFFERENT frames (0+55 and 45+33 are not in one frame), so no
same-frame station arithmetic is performed (distinct from log59's same-frame span).

Red TrueLine stroke only (render.crop.REDLINE_STROKE_RGB), REVIEW-style (dashed). Source PDF/CAD
evidence colors are never touched; only TrueLine's own drawn REVIEW stroke is governed -- and it is
red. Source-backed REVIEW/proof artifact, NOT a broad renderer and NOT wired into product/UI/API. PNG
+ JSON are written under the gitignored data/outputs path and are NOT committed.

Sheet 10 is OWNER-CONFIRMED (2026-06-15): log66's corrected_sheets == [10]. log66 is source-bound,
rendered, and PROMOTED into the seam contract eligible set (log53/log64/log71/log59/log66;
build_seam_payload builds it; the contract/adapter/end-to-end driver all carry log66). Census stays
frozen (no artifact change).

Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_log66_render_artifact_slice
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
    resolve_nextlink_hh_callout,
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
from truelinev2.proof.run_log59_render_artifact_slice import (
    EDGE_EPS,
    interior_vertices_are_dash_endpoints,
    route_edges_source_backed,
)
from truelinev2.proof.run_log64_sheet21_source_bind_slice import corridor_is_continuous, start_label_text
from truelinev2.proof.run_log66_sheet10_source_bind_slice import (
    INSTALLER_SYMBOL_LAYER,
    SHEET,
    SPAN_FT,
    _HH_55,
)
from truelinev2.proof.run_log71_render_artifact_slice import order_chain_route, route_length
from truelinev2.proof.run_log71_two_leg_source_bind_slice import leg_corridor_band
from truelinev2.proof.run_reviewer_service_contract import resolve_corpus
from truelinev2.render.crop import REDLINE_STROKE_RGB, render_redline_stroke
from truelinev2.seam import ELIGIBLE_EXEMPLARS, build_seam_payload

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "log66_render_artifact"
TRUTH = _REPO_ROOT / "data" / "outputs" / "final_engine_truth_table" / \
    "final_engine_truth_table.json"
BASE_CONDUIT = set(BRENHAM_CONDUIT_LAYERS.values())   # BORE - VACANT PIPE / BORE - PORT
FROZEN_BUCKETS = {"DRAWABLE_REVIEW": 31, "HUMAN_ADJUSTABLE_REVIEW": 6,
                  "OUT_OF_CLASS": 1, "PICK_CARD_REVIEW": 17, "SOURCE_OR_KMZ_REQUIRED": 3}
ABSTAIN_4 = ("log5", "log31", "log38", "log43")
SEAM_ELIGIBLE = ("log53", "log64", "log71", "log59", "log66")   # log66 since promoted into the seam
# proven sheet-10 binds (extractor-derived in the source-bind slice; the render is gated to match these)
PROVEN = {"start": (861.3, 354.19), "end": (941.04, 353.28)}
MATCH_TOL = 4.0

R_CREATED = "LOG66_RENDER_ARTIFACT_CREATED"
B_ENDPOINT = "BLOCKED_LOG66_RENDER_ENDPOINT_MISMATCH"
B_NO_CHAIN = "BLOCKED_LOG66_RENDER_CHAIN_NOT_CONNECTED"
B_DIRECT_CONTINUOUS = "BLOCKED_LOG66_RENDER_DIRECT_CORRIDOR_CONTINUOUS"
B_ROUTE = "BLOCKED_LOG66_RENDER_ROUTE_NOT_SOURCE_BACKED"
B_SPAN = "BLOCKED_LOG66_RENDER_SPAN_ANNOTATION_MISMATCH"
B_FAILED = "BLOCKED_LOG66_RENDER_ARTIFACT_FAILED"
ALLOWED = {R_CREATED, B_ENDPOINT, B_NO_CHAIN, B_DIRECT_CONTINUOUS, B_ROUTE, B_SPAN, B_FAILED}


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
    l66 = rec.get("log66") or {}
    ea = l66.get("endpoint_anchors") or {}
    start_a, end_a = ea.get("start") or {}, ea.get("end") or {}
    gates, ev = [], {"sheet": SHEET}

    gates.append(("G0 engine census frozen (OFF 31/6/1/17/3, ON 22/1/4, log44+abstains held)",
                  _census_frozen(doc), None))
    # preserve behavior: log53/log64/log71/log59 encoded anchors untouched; log66 anchors as encoded
    l53s = (rec["log53"].get("endpoint_anchors") or {}).get("start") or {}
    l64s = (rec["log64"].get("endpoint_anchors") or {}).get("start") or {}
    l71s = (rec["log71"].get("endpoint_anchors") or {}).get("start") or {}
    l59s = (rec["log59"].get("endpoint_anchors") or {}).get("start") or {}
    gates.append(("G0b log53/log64/log71/log59 anchors unchanged; log66 installer_hh @0+55 -> nextlink_hh @45+33",
                  l53s.get("structure_class") == "nextlink_hh"
                  and l64s.get("structure_class") == "installer_hh" and l64s.get("station") == "3+69"
                  and l71s.get("structure_class") == "nextlink_hh"
                  and l59s.get("structure_class") == "installer_hh"
                  and start_a.get("structure_class") == "installer_hh" and start_a.get("station") == "0+55"
                  and end_a.get("structure_class") == "nextlink_hh" and end_a.get("station") == "45+33", None))
    gates.append(("G0c sheet 10 OWNER-CONFIRMED; corrected_sheets == [10]",
                  l66.get("corrected_sheets") == [10], {"corrected_sheets": l66.get("corrected_sheets")}))

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
        # START installer HH is a RESET token '0+55=0+00' (the log64 reset-start, not log59's plain station)
        sv = resolve_structure_position(label_text=start_label_text(start_a),
                                        structure_class="installer_hh", words=words, drawings=draw,
                                        layer_table=BRENHAM_STRUCTURE_LAYERS)
        # END nextlink HH binds ONLY via the callout locator (no BRENHAM_STRUCTURE_LAYERS entry)
        nv = resolve_nextlink_hh_callout(station_sta=end_a.get("station"), words=words, drawings=draw,
                                         callout_layer="ANNOTATION", symbol_layer="NEXTLINK")
        s_xy = tuple(sv.symbol_xy) if (sv.result == POSITION_BOUND and sv.symbol_xy) else None
        e_xy = tuple(nv.symbol_xy) if (nv.result == POSITION_BOUND and nv.symbol_xy) else None
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

        # ---- render-mode FORCED to ordered_chain_path: re-prove the direct corridor is DISCONTINUOUS
        #      from source (36.36 > MAX_DASH_GAP) -- a continuous/straight corridor is NOT source-backed
        #      and is refused (no fake straight corridor). ------------------------------------------
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
        interior_ok = len(route) >= 3 and interior_vertices_are_dash_endpoints(route, chain)
        edges_ok = bool(route) and route[0] == s_xy and route[-1] == e_xy \
            and route_edges_source_backed(route, chain)
        route_ok = interior_ok and edges_ok
        gates.append(("G5 stroke is the ordered source-backed chain path (>= 3 real vertices; every edge a dash or <= MAX_DASH_GAP hop)",
                      route_ok, {"vertices": len(route), "route_len": ev["route_len_pt"],
                                 "straight_len": ev["straight_len_pt"]}))
        if not route_ok:
            return _emit(gates, B_ROUTE, ev, artifacts, rec)

        # ---- HH-HH=55' annotation + owner span_ft corroboration (NO cross-frame station math) -----
        hh = [ln for ln in lines if _HH_55.search(ln)]
        span_ft = float(l66.get("span_ft") or 0.0)
        ev["hh_hh_55_lines"] = hh[:3]
        ev["owner_span_ft"] = span_ft
        ev["station_span_arithmetic_used"] = False
        span_ok = bool(hh) and abs(span_ft - SPAN_FT) <= 0.5
        gates.append(("G6 HH-HH=55' annotation present on sheet 10 + owner span_ft == 55' (no cross-frame station math)",
                      span_ok, {"annotation": bool(hh), "owner_span_ft": span_ft}))
        if not span_ok:
            return _emit(gates, B_SPAN, ev, artifacts, rec)

        # ---- render the single sheet-local red REVIEW stroke ---------------------
        png = render_redline_stroke(
            plan, "log66", SHEET, offset, route, status="REVIEW",
            reason="OWNER-PACKET-2 source-backed: INSTALLER HH 0+55=0+00 -> 45+33=0+00 NEXTLINK HH (55'; ordered chain path, BORE - VACANT PIPE corridor)",
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
    gates.append(("G8 exactly one log66 sheet-10 PNG (log66-only, sheet-local)",
                  pngs == ["log66_s10_redline_stroke.png"], pngs))
    gates.append(("G9 canonical red stroke color", REDLINE_STROKE_RGB == (220, 25, 25),
                  list(REDLINE_STROKE_RGB)))
    # scope / safety gates (always run): no promotion, no eligibility expansion, near-misses untouched
    l66 = rec.get("log66") or {}
    gates.append(("G10 log66 corrected_sheets == [10]; source-bound + rendered + seam-PROMOTED (ELIGIBLE_EXEMPLARS == 5; seam builds log66)",
                  l66.get("corrected_sheets") == [10]
                  and tuple(ELIGIBLE_EXEMPLARS) == SEAM_ELIGIBLE
                  and not _refuses_seam("log66", rec), None))
    gates.append(("G11 log36 un-anchored + blank; log59 seam-promoted (builds); log53/log64/log71 bridges intact",
                  not rec["log36"].get("endpoint_anchors") and rec["log36"].get("corrected_sheets") == []
                  and not _refuses_seam("log59", rec)
                  and (rec["log53"].get("endpoint_anchors") or {}).get("end", {}).get("boundary_kind") == "matchline_continuation"
                  and (rec["log64"].get("endpoint_anchors") or {}).get("start", {}).get("structure_class") == "installer_hh"
                  and (rec["log71"].get("endpoint_anchors") or {}).get("start", {}).get("structure_class") == "nextlink_hh", None))
    gates.append(("G12 result in allowed enum", result in ALLOWED, result))
    created = result == R_CREATED
    all_pass = all(x for _, x, _ in gates) and created
    report = {
        "milestone": "OWNER-PACKET-2 -- log66 render artifact (contained proof; visual inspection)",
        "verdict": "PASS" if all_pass else "FAIL",
        "result": result, "target": "log66 ONLY", "sheet": SHEET,
        "shape": ("single_sheet_structure_to_structure (log64 family; installer-to-nextlink variant); "
                  "ordered_chain_path route (log71 mode)"),
        "endpoints": {"start": {"structure_class": "installer_hh", "station": "0+55", "xy": ev.get("start_symbol_xy")},
                      "end": {"structure_class": "nextlink_hh", "station": "45+33", "xy": ev.get("end_symbol_xy")}},
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
        "span_evidence": ("HH-HH=55' annotation + owner span_ft=55; both ends reset to 0+00 in DIFFERENT "
                          "frames, so NO same-frame station-span arithmetic was performed"),
        "sheet_10_provenance": ("SOURCE-RECOVERED by the near-miss scout, now OWNER-CONFIRMED 2026-06-15; "
                                "corrected_sheets == [10]; log66 source-bound + rendered + PROMOTED "
                                "into the seam (5th exemplar)"),
        "sheet_local_only": True, "log66_only": True, "single_sheet": True,
        "source_corridor_layers": sorted(BASE_CONDUIT),
        "max_dash_gap_not_loosened": MAX_DASH_GAP == 35.0,
        "coords_are_extractor_derived": True, "no_invented_coordinates": True,
        "no_screenshot_pixels": True, "no_cross_sheet": True, "no_fake_straight_corridor": True,
        "no_station_subtraction": True,
        "corrected_sheets_owner_confirmed": True, "seam_promoted": True,
        "seam_eligible": list(ELIGIBLE_EXEMPLARS),
        "broad_renderer": False, "product_wired": False,
        "next_slice": ("log66 seam promotion is COMPLETE (log66 is the 5th seam exemplar in the "
                       "contract/adapter/end-to-end driver, the controlled path log59 walked); next growth "
                       "is the next endpoint-anchor bridge (log36, the remaining un-anchored near-miss)."),
        "evidence": ev,
        "gates": [{"name": n, "pass": bool(x), "detail": d} for n, x, d in gates],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "log66_render_artifact.json").write_text(json.dumps(report, indent=2, default=str),
                                                        encoding="utf-8")
    print(f"[log66-render] result: {result}")
    for k in ("start_symbol_xy", "end_symbol_xy", "chain_segs", "chain_to_start_symbol_pt",
              "chain_to_end_symbol_pt", "corridor_axis", "corridor_band_points", "corridor_max_gap_pt",
              "direct_corridor_continuous", "render_mode", "route_vertices", "route_len_pt",
              "straight_len_pt", "owner_span_ft"):
        if k in ev:
            print(f"[log66-render]   {k}: {ev[k]}")
    for a in artifacts:
        print(f"[log66-render]   ARTIFACT: {a}")
    for n, x, _ in gates:
        print(f"[log66-render] {'PASS' if x else 'FAIL'}  {n}")
    print(f"[log66-render] VERDICT: {'PASS' if all_pass else 'FAIL'}  (report: {OUT_DIR})")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
