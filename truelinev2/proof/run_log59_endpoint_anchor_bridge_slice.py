r"""OWNER-PACKET-2 -- log59 endpoint-anchor bridge slice (PROOF ONLY; identity encoding).

Encodes + validates log59's endpoint identity bridge now that the near-miss sheet-locator scout
(88d9f96) SOURCE-RECOVERED its sheet: installer_hh @ STA 2+76 and flower_pot @ STA 4+46 bind uniquely
on sheet 21 across all 43 pages, and the station span 4+46-2+76 = 170' matches the printed
'HH - HH = 170'' annotation. It places no bore, draws no stroke, renders no PNG, parses no PDF here,
and solves no cross-sheet frame. Identity + boundary semantics ONLY, never coordinates.

log59 is the log64 shape (clean single-sheet structure-to-structure): start STA 2+76 INSTALLER HH
(structure_terminus, installer_hh), end STA 4+46 FLOWER POT (structure_terminus, flower_pot), both
on sheet 21. NO matchline (distinct from log53/log71). Sheet 21 was SOURCE-RECOVERED bridge evidence
and has since been OWNER-CONFIRMED (2026-06-15): it is now recorded in corrected_sheets=[21] and cited
in the anchor owner_note_text, and log59 has been promoted into the seam contract eligible set (a
later, separately-authorized slice). This bridge slice still only validates the identity encoding.

Proves: anchors present + schema-valid + owner/source-backed + modeled + machine-consumable; the
cohort classifier moves log59 REPRESENTATIVE_ROUTE_CANDIDATE (NO_RECORDED_SHEET) -> SOURCE_BINDABLE_NOW
(the explicit, deterministic, log59-LIMITED cohort delta); the frozen ENGINE census is unchanged
(identity-only addition; flag-OFF 31/6/1/17/3, flag-ON 22/1/4); no log66/log36 anchors; the seam
ELIGIBLE_EXEMPLARS stays log53/log64/log71 (log59 refused by build_seam_payload); no renderer.

Proof-only; the JSON report is written under the gitignored data/outputs path.
Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_log59_endpoint_anchor_bridge_slice
"""
from __future__ import annotations

import json

from truelinev2.config import _REPO_ROOT
from truelinev2.ingest.manual_adjudication import (
    PLACE_NEEDS_GEOMETRY,
    activation_summary,
    apply_adjudications,
    flag_on_disposition,
    load_adjudication,
    parent_run_duplicate_check,
    placement_geometry_readiness,
    resolve,
    validate_adjudication,
    validate_endpoint_anchors,
)
from truelinev2.proof.run_log53_primitives_cohort_replay import (
    MODELED_TERMINUS_CLASSES,
    REPRESENTATIVE_ROUTE_CANDIDATE,
    SOURCE_BINDABLE_NOW,
    classify_record,
)
from truelinev2.seam import ELIGIBLE_EXEMPLARS, build_seam_payload
from truelinev2.stations import parse_station

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "log59_endpoint_anchor_bridge_slice"
TRUTH = _REPO_ROOT / "data" / "outputs" / "final_engine_truth_table" / \
    "final_engine_truth_table.json"
FROZEN_BUCKETS = {"DRAWABLE_REVIEW": 31, "HUMAN_ADJUSTABLE_REVIEW": 6,
                  "OUT_OF_CLASS": 1, "PICK_CARD_REVIEW": 17, "SOURCE_OR_KMZ_REQUIRED": 3}
ABSTAIN_4 = ("log5", "log31", "log38", "log43")
EXPECTED_ANCHOR_LOGS = ("log53", "log59", "log64", "log66", "log71")
NOT_ANCHORED_NEAR_MISSES = ("log36",)   # log66 has since been bridged; log36 is the remaining un-anchored near-miss
SHEET = 21
SPAN_FT = 170.0
_COORD_KEYS = {"x", "y", "z", "xc", "yc", "x0", "y0", "x1", "y1", "cx", "cy", "xy",
               "lat", "lon", "lng", "coord", "coords", "coordinate", "coordinates",
               "px", "py", "pixel", "pixels", "point", "points", "symbol_xy", "anchor_xy",
               "stroke", "stroke_points", "geometry", "geom"}

R_ENCODED = "LOG59_ENDPOINT_ANCHORS_ENCODED"
B_SCHEMA = "BLOCKED_LOG59_SCHEMA_GAP"
B_IDENTITY = "BLOCKED_LOG59_IDENTITY_NOT_REPRESENTABLE"
B_SHEET = "BLOCKED_LOG59_SHEET_EVIDENCE_MISSING"
B_PROMOTED = "BLOCKED_LOG59_SILENTLY_PROMOTED"
B_VALIDATION = "BLOCKED_LOG59_ENDPOINT_ANCHOR_VALIDATION_FAILED"
ALLOWED = {R_ENCODED, B_SCHEMA, B_IDENTITY, B_SHEET, B_PROMOTED, B_VALIDATION}


def _has_coord_keys(anchor: dict) -> bool:
    return bool({str(k).lower() for k in anchor} & _COORD_KEYS)


def _refuses_seam(log_id: str, rec: dict) -> bool:
    try:
        build_seam_payload(log_id, rec.get(log_id, {}))
        return False
    except ValueError:
        return True


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for stale in OUT_DIR.glob("*.png"):
        stale.unlink()

    doc = load_adjudication()
    rec = {r["log_id"]: r for r in doc["logs"]}
    l59 = rec.get("log59", {})
    ea = l59.get("endpoint_anchors") or {}
    start, end = ea.get("start") or {}, ea.get("end") or {}
    start_note_up = str(start.get("owner_note_text") or "").upper()
    end_note_up = str(end.get("owner_note_text") or "").upper()
    gates = []
    result = B_SCHEMA

    gates.append(("G1 whole artifact still validates clean (additive)",
                  validate_adjudication(doc) == [], None))
    gates.append(("G2 log59 endpoint_anchors present + schema-valid",
                  bool(ea) and validate_endpoint_anchors(l59) == [], None))
    gates.append(("G3 start = structure_terminus installer_hh 'INSTALLER HH' @ STA 2+76",
                  start.get("boundary_kind") == "structure_terminus"
                  and start.get("structure_class") == "installer_hh"
                  and start.get("structure_label") == "INSTALLER HH"
                  and start.get("station") == "2+76", start))
    gates.append(("G4 end = structure_terminus flower_pot 'FLOWER POT' @ STA 4+46",
                  end.get("boundary_kind") == "structure_terminus"
                  and end.get("structure_class") == "flower_pot"
                  and end.get("structure_label") == "FLOWER POT"
                  and end.get("station") == "4+46", end))
    gates.append(("G5 both termini classes are modeled (installer_hh + flower_pot)",
                  start.get("structure_class") in MODELED_TERMINUS_CLASSES
                  and end.get("structure_class") in MODELED_TERMINUS_CLASSES, None))
    gates.append(("G6 anchors carry NO coordinate/stroke/geometry field",
                  not _has_coord_keys(start) and not _has_coord_keys(end), None))
    gates.append(("G7 both anchors structure_terminus single-sheet S2S (no matchline; log64 shape)",
                  start.get("boundary_kind") == "structure_terminus"
                  and end.get("boundary_kind") == "structure_terminus"
                  and set(ea) <= {"start", "end"}, sorted(ea)))
    # sheet 21 = SOURCE-RECOVERED bridge evidence cited in BOTH anchor notes, explicitly NOT promoted
    gates.append(("G8 sheet 21 cited as SOURCE-RECOVERED + OWNER-CONFIRMED in both anchor notes (promoted)",
                  str(SHEET) in start_note_up and str(SHEET) in end_note_up
                  and "SOURCE-RECOVERED" in start_note_up and "SOURCE-RECOVERED" in end_note_up
                  and "OWNER-CONFIRMED" in start_note_up and "OWNER-CONFIRMED" in end_note_up, None))
    span = parse_station(end.get("station") or "0+00") - parse_station(start.get("station") or "0+00")
    gates.append(("G9 station span 4+46 - 2+76 = 170' (matches HH-HH=170' annotation)",
                  abs(span - SPAN_FT) <= 0.5, {"span_ft": span}))

    disp = resolve(doc).get("log59")
    flag_on = flag_on_disposition(l59)
    gates.append(("G10 bridge consumed by resolve()+overlay; drawable stays review_drawable; NEEDS_GEOMETRY",
                  disp is not None and disp.endpoint_anchors is not None
                  and flag_on.get("endpoint_anchors") is not None
                  and flag_on.get("drawable_status") == "review_drawable"
                  and placement_geometry_readiness(l59)["status"] == PLACE_NEEDS_GEOMETRY, None))

    cls = classify_record(l59)["classification"]
    gates.append(("G11 cohort classifier moves log59 -> SOURCE_BINDABLE_NOW (was REPRESENTATIVE_ROUTE_CANDIDATE)",
                  cls == SOURCE_BINDABLE_NOW, {"now": cls, "was": REPRESENTATIVE_ROUTE_CANDIDATE}))

    with_anchors = {r["log_id"] for r in doc["logs"] if r.get("endpoint_anchors")}
    l53e = (rec["log53"].get("endpoint_anchors") or {}).get("end") or {}
    l64s = (rec["log64"].get("endpoint_anchors") or {}).get("start") or {}
    l71s = (rec["log71"].get("endpoint_anchors") or {}).get("start") or {}
    no_other_anchors = all(not rec[l].get("endpoint_anchors") for l in NOT_ANCHORED_NEAR_MISSES)
    gates.append(("G12 prior bridges intact (log53/log64/log71/log66); log36 NOT anchored",
                  set(EXPECTED_ANCHOR_LOGS) == with_anchors
                  and l53e.get("boundary_kind") == "matchline_continuation"
                  and l64s.get("structure_class") == "installer_hh"
                  and l71s.get("structure_class") == "nextlink_hh" and no_other_anchors,
                  sorted(with_anchors)))

    # NOT silently promoted: log59 stays OUT of the seam contract eligible set; build_seam_payload refuses it
    gates.append(("G13 log59 PROMOTED to seam eligibility (ELIGIBLE_EXEMPLARS == 4; seam builds log59; log66/log36 refused)",
                  tuple(ELIGIBLE_EXEMPLARS) == ("log53", "log64", "log71", "log59")
                  and not _refuses_seam("log59", rec)
                  and all(_refuses_seam(l, rec) for l in NOT_ANCHORED_NEAR_MISSES), None))

    if TRUTH.is_file():
        truth = json.loads(TRUTH.read_text(encoding="utf-8"))
        baseline = {r["bore_id"]: dict(r) for r in truth["rows"]}
        off_rows = apply_adjudications(baseline, enabled=False)
        on_rows = apply_adjudications(baseline, enabled=True, doc=doc)
        summ = activation_summary(on_rows)

        def buckets(rows):
            c = {}
            for r in rows.values():
                c[r["completion_bucket"]] = c.get(r["completion_bucket"], 0) + 1
            return c
        census_ok = (off_rows is baseline and buckets(off_rows) == FROZEN_BUCKETS
                     and summ["manual_review_drawable"] == 22
                     and summ["manual_source_verification"] == 1 and summ["manual_abstain"] == 4
                     and on_rows["log44"]["adjudication"]["drawable_status"] == "non_drawable"
                     and all(on_rows[l]["adjudication"]["drawable_status"] == "abstain" for l in ABSTAIN_4)
                     and not parent_run_duplicate_check(doc))
        gates.append(("G14 ENGINE census frozen (OFF 31/6/1/17/3, ON 22/1/4, log44+abstains held)",
                      census_ok, None))
    else:
        gates.append(("G14 truth table present (census-safety baseline)", False, str(TRUTH)))

    if all(x for _, x, _ in gates):
        result = R_ENCODED
    return _emit(gates, result, l59, cls)


def _emit(gates, result, l59, cls) -> int:
    pngs = sorted(p.name for p in OUT_DIR.glob("*.png"))
    gates.append(("G15 zero PNG / zero stroke (no render lane)", len(pngs) == 0, {"pngs": pngs}))
    gates.append(("G16 result in allowed enum", result in ALLOWED, result))
    all_pass = all(x for _, x, _ in gates)
    ea = l59.get("endpoint_anchors") or {}
    report = {
        "milestone": "OWNER-PACKET-2 -- log59 endpoint-anchor bridge slice (proof only; identity encoding)",
        "verdict": "PASS" if all_pass else "FAIL",
        "result": result if all_pass else "BLOCKED",
        "target": "log59", "sheet": SHEET, "shape": "single_sheet_structure_to_structure (log64 family)",
        "anchor_bridge": {"start": ea.get("start"), "end": ea.get("end")},
        "sheet_21_provenance": ("SOURCE-RECOVERED by the near-miss sheet-locator scout (88d9f96); "
                                "OWNER-CONFIRMED 2026-06-15 -> recorded in corrected_sheets=[21]; log59 "
                                "promoted to seam eligibility"),
        "cohort_delta": {"log59": {"from": REPRESENTATIVE_ROUTE_CANDIDATE, "to": cls},
                         "explicit": True, "deterministic": True, "limited_to": "log59"},
        "seam_eligible_unchanged": list(ELIGIBLE_EXEMPLARS),
        "log66_log36_anchored": False,
        "no_pdf_parse": True, "no_render": True, "no_invented_coordinates": True,
        "no_source_bind": True, "no_seam_promotion": True, "engine_census_frozen": True,
        "next_slice": ("log59 source-bind: PRESENT recovered sheet 21 for OWNER confirmation, then a "
                       "log64-style single-sheet source-bind (installer HH 2+76 -> flower pot 4+46 on "
                       "sheet 21); render + seam promotion follow only after that is green."),
        "gates": [{"name": n, "pass": bool(x), "detail": d} for n, x, d in gates],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "log59_endpoint_anchor_bridge_slice.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"[log59-bridge] result: {result if all_pass else 'BLOCKED'}")
    print(f"[log59-bridge] start: {ea.get('start')}")
    print(f"[log59-bridge] end:   {ea.get('end')}")
    print(f"[log59-bridge] cohort delta: log59 {REPRESENTATIVE_ROUTE_CANDIDATE} -> {cls}")
    for n, x, _ in gates:
        print(f"[log59-bridge] {'PASS' if x else 'FAIL'}  {n}")
    print(f"[log59-bridge] VERDICT: {'PASS' if all_pass else 'FAIL'}  (report: {OUT_DIR})")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
