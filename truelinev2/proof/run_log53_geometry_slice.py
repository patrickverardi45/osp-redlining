r"""OWNER-PACKET-2 -- Geometry Resolution Slice 1 (log53 ONLY).

Question: can log53 (manual-adjudicated review-drawable; corrected STA 21+63 -> STA
24+11, 248', sheet 5) be converted from reviewed station/print/sheet TRUTH into safe
positioned plan-coordinate GEOMETRY for the EXISTING v2 redline renderer -- without
inventing geometry, bypassing the structure-identity law, or breaking the red-stroke law?

Method (existing v2 geometry path only):
  1. pull log53 from the ACTUAL flag-on manual-adjudication overlay (not hardcoded);
  2. its corrected stations are ABSOLUTE plan stations (21+63/24+11) on a single sheet,
     so feed start_ft/end_ft (parsed from the reviewed artifact) to the SHIPPED
     ``solve_tick_path`` over sheet-5's clean route-ladder ticks (``route_ladder_ticks``);
  3. map the solver's typed verdict to a geometry-slice classification;
  4. render a RED proof stroke (canonical ``crop.REDLINE_STROKE_RGB``) ONLY if the solver
     is truly READY -- never force a stroke on a non-READY verdict.

No synthesized coordinates, no nearest/proximity/length-only draw, no screenshot
positions, no structure-identity-law bypass. Proof-only; artifacts gitignored.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from truelinev2.config import _REPO_ROOT
from truelinev2.extract.registry import select_dialect
from truelinev2.extract.tick_path import (
    EXHAUSTED,
    MULTIPLE,
    NOT_COVERED,
    READY,
    STRUCTURE_REQUIRED,
    route_ladder_ticks,
    solve_tick_path,
)
from truelinev2.ingest.manual_adjudication import (
    apply_adjudications,
    activation_summary,
    load_adjudication,
    parent_run_duplicate_check,
)
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.proof.run_brenham_corpus import EXPECTED_COUNT, PDF, enumerate_corpus
from truelinev2.proof.run_reviewer_service_contract import resolve_corpus
from truelinev2.render.crop import REDLINE_STROKE_RGB, render_redline_stroke
from truelinev2.stations import parse_station

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "log53_geometry_slice"
TRUTH = _REPO_ROOT / "data" / "outputs" / "final_engine_truth_table" / \
    "final_engine_truth_table.json"

FROZEN_BUCKETS = {"DRAWABLE_REVIEW": 31, "HUMAN_ADJUSTABLE_REVIEW": 6,
                  "OUT_OF_CLASS": 1, "PICK_CARD_REVIEW": 17, "SOURCE_OR_KMZ_REQUIRED": 3}
ABSTAIN_4 = {"log5", "log31", "log38", "log43"}

# solver verdict -> geometry-slice classification (the mission's enum)
_CLASS = {
    READY: "GEOMETRY_READY",
    STRUCTURE_REQUIRED: "BLOCKED_STRUCTURE_IDENTITY_BINDING_REQUIRED",
    NOT_COVERED: "BLOCKED_NO_POSITIONED_TICK_PATH",
    MULTIPLE: "BLOCKED_AMBIGUOUS_SHEET_GEOMETRY",
    EXHAUSTED: "BLOCKED_ENGINE_LAW",
}


def classify_geometry(result: str, clean_ladder_ticks: int) -> str:
    if clean_ladder_ticks == 0:
        return "BLOCKED_NO_ROUTE_LADDER"
    return _CLASS.get(result, "BLOCKED_NO_POSITIONED_TICK_PATH")


def _bucket_counts(rows):
    c = {}
    for r in rows.values():
        c[r["completion_bucket"]] = c.get(r["completion_bucket"], 0) + 1
    return c


def _inside(pt, bbox, m: float = 4.0) -> bool:
    return (bbox and bbox[0] - m <= pt[0] <= bbox[2] + m
            and bbox[1] - m <= pt[1] <= bbox[3] + m)


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for stale in OUT_DIR.glob("*.png"):
        stale.unlink()  # only THIS run's stroke (if any) may exist

    # ---- manual-adjudication overlay context (flag enabled IN-PROOF only) -------
    truth = json.loads(TRUTH.read_text(encoding="utf-8"))
    baseline = {r["bore_id"]: dict(r) for r in truth["rows"]}
    doc = load_adjudication()
    rec = {r["log_id"]: r for r in doc["logs"]}
    off_rows = apply_adjudications(baseline, enabled=False)
    on_rows = apply_adjudications(baseline, enabled=True, doc=doc)
    summ = activation_summary(on_rows)

    # log53 pulled from ACTUAL flag-on output
    l53_row = on_rows["log53"]
    l53 = rec["log53"]
    start_ft = parse_station(l53["corrected_start"])
    end_ft = parse_station(l53["corrected_end"])
    sheet = (l53["corrected_sheets"] or [None])[0]
    span_ft = l53.get("span_ft")

    gates = []

    # G1 flag OFF byte-identical
    g1 = (off_rows is baseline and _bucket_counts(off_rows) == FROZEN_BUCKETS)
    gates.append(("G1 flag OFF byte-identical (31/6/1/17/3)", g1, _bucket_counts(off_rows)))

    # G2 flag ON counts unchanged
    g2 = (summ["manual_review_drawable"] == 22 and summ["manual_source_verification"] == 1
          and summ["manual_abstain"] == 4)
    gates.append(("G2 flag ON 22 review-drawable / 1 source-verify / 4 abstain", g2,
                  {k: summ[k] for k in ("manual_review_drawable", "manual_source_verification",
                                        "manual_abstain")}))

    # G3 log53 selected from flag-on output as review-drawable
    g3 = l53_row.get("adjudication", {}).get("drawable_status") == "review_drawable"
    gates.append(("G3 log53 is review-drawable in flag-on output", g3,
                  l53_row.get("adjudication", {}).get("drawable_status")))

    # G4 log53 corrected facts preserved (21+63->24+11, 248', sheet 5)
    g4 = (l53["corrected_start"] == "21+63" and l53["corrected_end"] == "24+11"
          and sheet == 5 and span_ft == 248.0
          and end_ft - start_ft == 248.0)
    gates.append(("G4 log53 facts preserved (21+63->24+11, 248', sheet 5)", g4,
                  {"start_ft": start_ft, "end_ft": end_ft, "sheet": sheet, "span_ft": span_ft}))

    # G5 other 21 review-drawable untouched controls (still review-drawable, no geometry)
    others = [b for b, r in on_rows.items()
              if r.get("adjudication", {}).get("drawable_status") == "review_drawable"
              and b != "log53"]
    g5 = len(others) == 21
    gates.append(("G5 other 21 review-drawable untouched controls", g5, {"n": len(others)}))

    # G6 log44 blocked / abstains held / log68-69 separated / no dup
    g6 = (on_rows["log44"]["adjudication"]["drawable_status"] == "non_drawable"
          and on_rows["log44"]["can_draw_now"] is False
          and all(on_rows[l]["adjudication"]["drawable_status"] == "abstain" for l in ABSTAIN_4)
          and rec["log68"]["corrected_start"] == "5+03" and rec["log68"]["corrected_end"] == "6+79"
          and "4+54" not in (rec["log68"]["corrected_start"], rec["log68"]["corrected_end"])
          and rec["log69"]["corrected_start"] == "2+15" and rec["log69"]["corrected_end"] == "4+54"
          and not parent_run_duplicate_check(doc))
    gates.append(("G6 log44 blocked / abstains held / log68-69 separated / no dup", g6, None))

    # ---- the geometry-resolution attempt: existing v2 path, sheet 5 -------------
    if not os.path.isfile(PDF):
        gates.append(("G7 plan PDF present", False, f"missing {PDF}"))
        _emit(gates, None, "BLOCKED_NO_ROUTE_LADDER", {}, start_ft, end_ft, sheet, span_ft, None)
        return 2
    corpus_dir, how = resolve_corpus()
    corpus = {p.stem: p for p in enumerate_corpus(corpus_dir)} if os.path.isdir(corpus_dir) else {}
    g7 = os.path.isfile(PDF) and len(corpus) == EXPECTED_COUNT
    gates.append(("G7 plan PDF + corpus present", g7,
                  {"pdf": os.path.isfile(PDF), "corpus": len(corpus)}))

    plan = PlanPdf(PDF)
    classification = None
    png = None
    verdict_dict = None
    counts = {}
    sanity = {}
    try:
        dialect = select_dialect(plan)
        offset = dialect.calibrate(plan, 13)
        ticks, counts = route_ladder_ticks(plan, sheet, offset)
        verdict = solve_tick_path(bore_id="bore_log53", sheet=sheet,
                                  start_ft=start_ft, end_ft=end_ft, ticks=ticks)
        verdict_dict = verdict.to_dict()
        classification = classify_geometry(verdict.result, counts["clean_ladder_ticks"])

        if verdict.result == READY and verdict.stroke_points:
            # belt-and-braces: no stroke point inside a callout bbox
            callout_boxes = [c.bbox for c in dialect.extract_callouts(plan, sheet, offset) if c.bbox]
            polluted = [p for p in verdict.stroke_points
                        if any(_inside(p, b) for b in callout_boxes)]
            # station/length sanity: span matches the reviewed 248'
            sanity = {"station_span_ft": end_ft - start_ft, "reviewed_len_ft": span_ft,
                      "match": (end_ft - start_ft) == span_ft,
                      "stroke_point_count": len(verdict.stroke_points),
                      "callout_polluted_points": len(polluted),
                      "strokes_found": verdict.strokes_found}
            if polluted or verdict.strokes_found != 1 or sanity["match"] is False:
                classification = "BLOCKED_NO_POSITIONED_TICK_PATH"  # not clean -> do NOT draw
            else:
                png = render_redline_stroke(
                    plan, "bore_log53", sheet, offset, verdict.stroke_points,
                    status="REVIEW", reason="MANUAL_ADJUDICATION_GEOMETRY_SLICE",
                    out_dir=str(OUT_DIR), evidence_bboxes=[])
    finally:
        plan.close()

    # ---- gate the geometry outcome (honest either way) --------------------------
    pngs = sorted(p.name for p in OUT_DIR.glob("*.png"))
    if classification == "GEOMETRY_READY":
        r, g, b = REDLINE_STROKE_RGB
        g8 = (png is not None and Path(png).is_file() and len(pngs) == 1
              and r >= 200 and g <= 80 and b <= 80 and sanity.get("match") is True)
        gates.append(("G8 GEOMETRY_READY -> 1 red proof stroke; span sane", g8,
                      {"png": png, "red": list(REDLINE_STROKE_RGB), "sanity": sanity}))
    else:
        g8 = len(pngs) == 0  # BLOCKED -> no stroke, no fake fallback
        gates.append((f"G8 BLOCKED ({classification}) -> no stroke, no fallback", g8,
                      {"named_missing": (verdict_dict or {}).get("named_missing_relationship"),
                       "clean_ladder_ticks": counts.get("clean_ladder_ticks")}))

    _emit(gates, png, classification, counts, start_ft, end_ft, sheet, span_ft, verdict_dict)
    return 0 if all(x for _, x, _ in gates) else 1


def _emit(gates, png, classification, counts, start_ft, end_ft, sheet, span_ft, verdict_dict):
    all_pass = all(x for _, x, _ in gates)
    report = {
        "milestone": "OWNER-PACKET-2 -- Geometry Resolution Slice 1 (log53 only)",
        "verdict": "PASS" if all_pass else "FAIL",
        "target": "log53",
        "corrected_start": "21+63", "corrected_end": "24+11",
        "start_ft": start_ft, "end_ft": end_ft, "sheet": sheet, "reviewed_len_ft": span_ft,
        "geometry_classification": classification,
        "clean_ladder_ticks_on_sheet": counts.get("clean_ladder_ticks"),
        "tick_path_verdict": verdict_dict,
        "proof_stroke_png": png,
        "red_stroke_rgb": list(REDLINE_STROKE_RGB),
        "no_geometry_invented": True,
        "gates": [{"name": n, "pass": bool(x), "detail": d} for n, x, d in gates],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "log53_geometry_slice.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"[log53-geo] classification: {classification}")
    print(f"[log53-geo] clean ladder ticks on sheet {sheet}: {counts.get('clean_ladder_ticks')}")
    if verdict_dict:
        print(f"[log53-geo] tick_path result: {verdict_dict.get('result')}")
        if verdict_dict.get("named_missing_relationship"):
            print(f"[log53-geo]   named: {verdict_dict['named_missing_relationship'][:160]}")
    print(f"[log53-geo] proof stroke png: {png}")
    for n, x, _ in gates:
        print(f"[log53-geo] {'PASS' if x else 'FAIL'}  {n}")
    print(f"[log53-geo] VERDICT: {'PASS' if all_pass else 'FAIL'}  (report: {OUT_DIR})")


if __name__ == "__main__":
    raise SystemExit(main())
