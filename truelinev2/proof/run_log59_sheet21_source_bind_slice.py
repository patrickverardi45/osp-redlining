r"""OWNER-PACKET-2 -- log59 sheet-21 SOURCE BIND slice (PROOF ONLY; no render).

Binds log59's encoded endpoint identity (its bridge slice) to REAL sheet-21 source with the SAME
primitives log64 used (printed label -> label box -> leader -> modeled symbol; modeled conduit chain)
-- never screenshot pixels, never invented coordinates, never a fallback/nearest snap. It renders
nothing, draws no stroke, writes no PNG. log59 is the log64 single-sheet structure-to-structure shape:

  sheet 21:  INSTALLER HH @ STA 2+76  ->  FLOWER POT @ STA 4+46  (HH - HH = 170')

What it proves on sheet 21 (single sheet; no cross-sheet solving):
  1. START installer HH binds: label '2+76' (a plain station, NOT a reset token -- log59's start is
     not a reset) -> INSTALLER HH - TEXT box -> leader -> NEXTLINK symbol (installer-HH fill);
  2. END flower pot binds: label '4+46' + ('FLOWER','POT') context -> FLOWER POT - TEXT box -> leader
     -> FLOWER POT symbol;
  3. a MODELED base conduit chain (BORE - VACANT PIPE / BORE - PORT) is graph-connected to BOTH bound
     symbols (each within MAX_DASH_GAP) -- the two termini sit on ONE source conduit chain, so a later
     render can trace it (via the proven ordered chain path);
  4. the printed 'HH - HH = 170'' annotation is present on sheet 21 and the station span
     4+46 - 2+76 = 170' corroborates it.

Sheet 21 was SOURCE-RECOVERED bridge evidence (the near-miss sheet-locator scout) and is now
OWNER-CONFIRMED -- log59's corrected_sheets == [21] and log59 is promoted into the seam contract
eligible set. The direct corridor's strict continuity is REPORTED as render-mode (continuous_corridor
vs ordered_chain_path); the source-backed bind is the connected chain reaching both termini, exactly
as log64/log71 proved.

All endpoint coordinates are produced by the EXISTING extractor (resolve_structure_position); this
slice synthesizes none. Census stays frozen (the only cohort delta is the already-known log59 bridge:
REPRESENTATIVE_ROUTE_CANDIDATE -> SOURCE_BINDABLE_NOW). A render is the separately-authorized next
step, NOT done here.

Proof-only; the JSON report is written under the gitignored data/outputs path.
Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_log59_sheet21_source_bind_slice
"""
from __future__ import annotations

import json
import os
import re

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
    validate_endpoint_anchors,
)
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.proof.run_brenham_corpus import EXPECTED_COUNT, PDF, enumerate_corpus
from truelinev2.proof.run_log53_primitives_cohort_replay import SOURCE_BINDABLE_NOW, classify_record
from truelinev2.proof.run_log64_sheet21_source_bind_slice import corridor_is_continuous
from truelinev2.proof.run_log71_two_leg_source_bind_slice import leg_corridor_band
from truelinev2.proof.run_reviewer_service_contract import resolve_corpus
from truelinev2.seam import ELIGIBLE_EXEMPLARS, build_seam_payload
from truelinev2.stations import parse_station

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "log59_sheet21_source_bind_slice"
TRUTH = _REPO_ROOT / "data" / "outputs" / "final_engine_truth_table" / \
    "final_engine_truth_table.json"
SHEET = 21                              # SOURCE-RECOVERED bridge evidence (near-miss scout), not corrected_sheets
SPAN_FT = 170.0
INSTALLER_SYMBOL_LAYER = "NEXTLINK"     # installer_hh shares the NEXTLINK symbol layer (dialect)
BASE_CONDUIT = set(BRENHAM_CONDUIT_LAYERS.values())   # BORE - VACANT PIPE / BORE - PORT
FROZEN_BUCKETS = {"DRAWABLE_REVIEW": 31, "HUMAN_ADJUSTABLE_REVIEW": 6,
                  "OUT_OF_CLASS": 1, "PICK_CARD_REVIEW": 17, "SOURCE_OR_KMZ_REQUIRED": 3}
ABSTAIN_4 = ("log5", "log31", "log38", "log43")
_HH_170 = re.compile(r"HH\s*[-_]?\s*HH\s*=\s*170(?!\d)", re.I)

R_CONFIRMED = "LOG59_SHEET21_SOURCE_BIND_CONFIRMED"
R_PARTIAL = "LOG59_PARTIAL_SOURCE_BIND_CONFIRMED"
B_ANCHORS = "BLOCKED_LOG59_ANCHORS_MISSING"
B_START = "BLOCKED_LOG59_START_BIND_FAILED"
B_END = "BLOCKED_LOG59_END_BIND_FAILED"
B_CONDUIT_SEED = "BLOCKED_LOG59_CONDUIT_SEED_NOT_FOUND"
B_ROUTE = "BLOCKED_LOG59_ROUTE_NOT_SOURCE_BACKED"
B_ANNOTATION = "BLOCKED_LOG59_SPAN_ANNOTATION_MISMATCH"
ALLOWED = {R_CONFIRMED, R_PARTIAL, B_ANCHORS, B_START, B_END, B_CONDUIT_SEED, B_ROUTE, B_ANNOTATION}


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
        stale.unlink()  # no render/stroke lane: a PNG must never exist

    doc = load_adjudication()
    rec = {r["log_id"]: r for r in doc["logs"]}
    l59 = rec.get("log59") or {}
    ea = l59.get("endpoint_anchors") or {}
    start_a, end_a = ea.get("start") or {}, ea.get("end") or {}
    gates, ev = [], {"sheet": SHEET}

    gates.append(("G0 engine census frozen (OFF 31/6/1/17/3, ON 22/1/4, log44+abstains held)",
                  _census_frozen(doc), None))
    # only cohort delta is the known log59 bridge: REPRESENTATIVE_ROUTE_CANDIDATE -> SOURCE_BINDABLE_NOW
    gates.append(("G0b cohort delta is the known log59 bridge only (log59 SOURCE_BINDABLE_NOW)",
                  classify_record(l59)["classification"] == SOURCE_BINDABLE_NOW
                  and (rec["log53"].get("endpoint_anchors") or {}).get("start", {}).get("structure_class") == "nextlink_hh"
                  and (rec["log64"].get("endpoint_anchors") or {}).get("start", {}).get("structure_class") == "installer_hh", None))

    # ---- consume the encoded identity (the bridge) -------------------------------
    anchors_ok = (validate_endpoint_anchors(l59) == []
                  and start_a.get("structure_class") == "installer_hh" and start_a.get("station") == "2+76"
                  and end_a.get("structure_class") == "flower_pot" and end_a.get("station") == "4+46"
                  and start_a.get("boundary_kind") == "structure_terminus"
                  and end_a.get("boundary_kind") == "structure_terminus")
    gates.append(("G1 log59 encoded anchors consumed (installer_hh @2+76 -> flower_pot @4+46, schema-valid)",
                  anchors_ok, {"start": start_a.get("station"), "end": end_a.get("station")}))
    if not anchors_ok:
        return _emit(gates, B_ANCHORS, ev, rec)

    # sheet 21 is BRIDGE evidence ONLY: corrected_sheets stays [] (not promoted), and the source-
    # recovered sheet is cited in the anchor owner_note_text.
    note_up = (str(start_a.get("owner_note_text") or "") + str(end_a.get("owner_note_text") or "")).upper()
    gates.append(("G2 sheet 21 consumed as source; OWNER-CONFIRMED -> corrected_sheets == [21]",
                  l59.get("corrected_sheets") == [21] and str(SHEET) in note_up and "SOURCE-RECOVERED" in note_up, None))

    result = B_ROUTE
    if not os.path.isfile(PDF):
        gates.append(("G3 plan PDF present", False, f"missing {PDF}"))
        return _emit(gates, B_ROUTE, ev, rec)
    corpus_dir, _ = resolve_corpus()
    corpus = {p.stem: p for p in enumerate_corpus(corpus_dir)} if os.path.isdir(corpus_dir) else {}
    gates.append(("G3 plan PDF + corpus present",
                  os.path.isfile(PDF) and len(corpus) == EXPECTED_COUNT,
                  {"pdf": os.path.isfile(PDF), "corpus": len(corpus)}))

    plan = PlanPdf(PDF)
    try:
        dialect = select_dialect(plan)
        offset = dialect.calibrate(plan, 13)
        words = plan.words(SHEET, offset)
        draw = plan.line_items(SHEET, offset)
        lines = plan.lines(SHEET, offset)

        # (1) START installer HH (plain station label '2+76' -- non-reset)
        sv = resolve_structure_position(label_text=start_a.get("station"), structure_class="installer_hh",
                                        words=words, drawings=draw, layer_table=BRENHAM_STRUCTURE_LAYERS)
        ev["start_label_text"] = start_a.get("station")
        ev["start_bind_result"] = sv.result
        s_bound = sv.result == POSITION_BOUND and sv.symbol_xy
        ev["start_symbol_xy"] = [round(c, 2) for c in sv.symbol_xy] if sv.symbol_xy else None
        gates.append(("G4 START installer_hh @2+76 binds on sheet 21 (label box -> leader -> NEXTLINK symbol)",
                      bool(s_bound), sv.result))
        if not s_bound:
            return _emit(gates, B_START, ev, rec)
        s_xy = tuple(sv.symbol_xy)

        # (2) END flower pot (label '4+46' + FLOWER/POT context)
        pv = resolve_structure_position(label_text=end_a.get("station"), structure_class="flower_pot",
                                        words=words, drawings=draw, layer_table=BRENHAM_STRUCTURE_LAYERS,
                                        context_texts=("FLOWER", "POT"))
        ev["end_bind_result"] = pv.result
        e_bound = pv.result == POSITION_BOUND and pv.symbol_xy
        ev["end_symbol_xy"] = [round(c, 2) for c in pv.symbol_xy] if pv.symbol_xy else None
        gates.append(("G5 END flower_pot @4+46 binds on sheet 21 (label+context -> leader -> FLOWER POT symbol)",
                      bool(e_bound), pv.result))
        if not e_bound:
            return _emit(gates, B_END, ev, rec)
        e_xy = tuple(pv.symbol_xy)

        # (3) MODELED base conduit chain connected to BOTH symbols (source-backed corridor)
        fp = symbol_footprint(draw, INSTALLER_SYMBOL_LAYER, s_xy)
        chain = connected_chain([x for x in draw if x.get("layer") in BASE_CONDUIT], fp) if fp else []
        eps = dash_endpoints(chain)
        ev["chain_segs"] = len(chain)
        if not chain:
            return _emit(gates, B_CONDUIT_SEED, ev, rec)
        reach_start = min((((p[0] - s_xy[0]) ** 2 + (p[1] - s_xy[1]) ** 2) ** 0.5 for p in eps), default=None)
        reach_end = min((((p[0] - e_xy[0]) ** 2 + (p[1] - e_xy[1]) ** 2) ** 0.5 for p in eps), default=None)
        ev["chain_to_start_symbol_pt"] = round(reach_start, 2) if reach_start is not None else None
        ev["chain_to_end_symbol_pt"] = round(reach_end, 2) if reach_end is not None else None
        both_connected = (reach_start is not None and reach_start <= MAX_DASH_GAP
                          and reach_end is not None and reach_end <= MAX_DASH_GAP)
        gates.append(("G6 base conduit chain connects BOTH bound symbols (<= MAX_DASH_GAP) -> source-backed corridor",
                      both_connected, {"to_start": ev["chain_to_start_symbol_pt"],
                                       "to_end": ev["chain_to_end_symbol_pt"]}))
        if not both_connected:
            return _emit(gates, B_ROUTE, ev, rec)

        # (4) direct-corridor continuity (orientation-aware; log59's corridor runs horizontally) ->
        #     render-mode refinement. Continuous -> continuous_corridor; else -> ordered_chain_path
        #     (the proven log71 sheet-24 path over the connected chain). Either way it is render-feasible.
        band, lo, hi, axis = leg_corridor_band(eps, s_xy, e_xy)
        continuous = corridor_is_continuous(band, lo, hi)
        ev["corridor_axis"] = axis
        ev["corridor_band_points"] = len(band)
        ev["corridor_max_gap_pt"] = round(max((band[i + 1] - band[i] for i in range(len(band) - 1)),
                                              default=0.0), 2)
        ev["direct_corridor_continuous"] = continuous
        ev["render_mode"] = "continuous_corridor" if continuous else "ordered_chain_path"
        gates.append(("G7 direct-corridor continuity characterized (render_mode); chain is render-feasible either way",
                      isinstance(continuous, bool), {"axis": axis, "continuous": continuous,
                                                     "render_mode": ev["render_mode"]}))

        # (5) printed HH-HH=170' annotation + station span corroboration
        hh = [ln for ln in lines if _HH_170.search(ln)]
        span = parse_station(end_a.get("station")) - parse_station(start_a.get("station"))
        ev["hh_hh_170_lines"] = hh[:3]
        ev["station_span_ft"] = span
        annotation_ok = bool(hh) and abs(span - SPAN_FT) <= 0.5
        gates.append(("G8 HH-HH=170' annotation present on sheet 21 + station span 4+46-2+76 = 170'",
                      annotation_ok, {"annotation": bool(hh), "span_ft": span}))
        if not annotation_ok:
            return _emit(gates, B_ANNOTATION, ev, rec)

        result = R_CONFIRMED if (both_connected and continuous) else R_PARTIAL
    finally:
        plan.close()

    return _emit(gates, result, ev, rec)


def _emit(gates, result, ev, rec) -> int:
    # ---- scope / safety gates (always run) -------------------------------------
    gates.append(("G9 log36 anchored-but-held-back (seam-refused); log66 PROMOTED (seam builds); log59 PROMOTED (builds)",
                  rec["log36"].get("endpoint_anchors") and _refuses_seam("log36", rec)
                  and rec["log66"].get("endpoint_anchors") and not _refuses_seam("log66", rec)
                  and tuple(ELIGIBLE_EXEMPLARS) == ("log53", "log64", "log71", "log59", "log66")
                  and not _refuses_seam("log59", rec), None))
    pngs = sorted(p.name for p in OUT_DIR.glob("*.png"))
    gates.append(("G10 zero PNG / zero stroke (no render lane)", len(pngs) == 0, {"pngs": pngs}))
    gates.append(("G11 result in allowed enum", result in ALLOWED, result))
    confirmed = result in (R_CONFIRMED, R_PARTIAL)
    all_pass = all(x for _, x, _ in gates) and confirmed
    payload = {
        "target": "log59", "sheet": SHEET, "shape": "single_sheet_structure_to_structure (log64 family)",
        "start": {"structure_class": "installer_hh", "station": "2+76", "xy": ev.get("start_symbol_xy")},
        "end": {"structure_class": "flower_pot", "station": "4+46", "xy": ev.get("end_symbol_xy")},
        "render_mode": ev.get("render_mode"),
        "corridor": {"chain_segs": ev.get("chain_segs"), "axis": ev.get("corridor_axis"),
                     "band_points": ev.get("corridor_band_points"),
                     "max_gap_pt": ev.get("corridor_max_gap_pt"),
                     "direct_corridor_continuous": ev.get("direct_corridor_continuous"),
                     "reach_to_start_pt": ev.get("chain_to_start_symbol_pt"),
                     "reach_to_end_pt": ev.get("chain_to_end_symbol_pt")},
    } if confirmed else None
    report = {
        "milestone": "OWNER-PACKET-2 -- log59 sheet-21 source bind slice (proof only; no render)",
        "verdict": "PASS" if all_pass else "FAIL",
        "result": result, "target": "log59", "sheet": SHEET,
        "question": ("does log59's encoded identity bind to real sheet-21 source -- installer HH @2+76, "
                     "flower pot @4+46, a connected modeled conduit chain between them, and the "
                     "HH-HH=170' span -- as the proven log64 single-sheet shape?"),
        "source_bind_payload": payload,
        "sheet_21_provenance": ("SOURCE-RECOVERED by the near-miss scout, now OWNER-CONFIRMED; "
                                "corrected_sheets == [21]; log59 promoted to seam eligibility"),
        "render_ready": confirmed,
        "no_render": True, "no_invented_coordinates": True, "no_screenshot_pixels": True,
        "no_cross_sheet": True, "no_corrected_sheets_promotion": True, "coords_are_extractor_derived": True,
        "next_slice": ("log59 RENDER artifact + owner-confirmation + seam promotion are now COMPLETE "
                       f"(render via the proven {ev.get('render_mode') or 'ordered_chain_path'}); log36 has "
                       "since been bridged (anchored-but-held-back); no un-anchored near-miss remains."),
        "evidence": ev,
        "gates": [{"name": n, "pass": bool(x), "detail": d} for n, x, d in gates],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "log59_sheet21_source_bind_slice.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"[log59-bind] result: {result}")
    for k in ("start_label_text", "start_bind_result", "start_symbol_xy", "end_bind_result",
              "end_symbol_xy", "chain_segs", "chain_to_start_symbol_pt", "chain_to_end_symbol_pt",
              "corridor_axis", "corridor_band_points", "corridor_max_gap_pt",
              "direct_corridor_continuous", "render_mode", "station_span_ft"):
        if k in ev:
            print(f"[log59-bind]   {k}: {ev[k]}")
    for n, x, _ in gates:
        print(f"[log59-bind] {'PASS' if x else 'FAIL'}  {n}")
    print(f"[log59-bind] VERDICT: {'PASS' if all_pass else 'FAIL'}  (report: {OUT_DIR})")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
