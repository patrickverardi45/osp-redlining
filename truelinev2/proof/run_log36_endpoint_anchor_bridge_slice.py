r"""OWNER-PACKET-2 -- log36 endpoint-anchor bridge slice (PROOF ONLY; identity encoding).

Encodes + validates log36's endpoint identity bridge now that the near-miss sheet-locator scout
SOURCE-RECOVERED its sheet: installer_hh @ STA 0+56 = 0+00 and installer_hh @ STA 1+45 = 0+00 bind
uniquely on sheet 17, and sheet 17 prints the 'HH - HH = 89'' annotation. It places no bore, draws no
stroke, renders no PNG, parses no PDF here, and solves no cross-sheet frame. Identity + boundary
semantics ONLY, never coordinates.

log36 is a SINGLE-sheet structure-to-structure run (the log64 family, installer-to-INSTALLER variant):
start STA 0+56 INSTALLER HH (structure_terminus, installer_hh), end STA 1+45 INSTALLER HH
(structure_terminus, installer_hh), both on sheet 17. NO matchline (both ends are true structure
termini; there is no interior route context). Both ends are STATION RESET points (each "= 0+00"), in
DIFFERENT reset frames, so there is NO same-frame station-span arithmetic for the run length -- the 89'
run is corroborated by the printed 'HH - HH = 89'' annotation + the owner span_ft, not by subtracting
plan stations.

The 0+56=0+00 start reset collides in station-NUMBER with the log6/log63 shared-print resets, which is
why log36 was ranked BEHIND log66 when log66 was the competing pick. That collision is a cross-sheet
RANKING concern, NOT a sheet-17 anchoring hazard: on sheet 17 the glued reset-equation tokens
'0+56=0+00' and '1+45=0+00' each occur exactly once and bind a unique installer_hh symbol (the scout's
both_bound=[17] uniqueness result), so the identity bind on sheet 17 is unambiguous.

Sheet 17 is SOURCE-RECOVERED bridge evidence, NOT owner-recorded production truth: it is kept OUT of
corrected_sheets and lives in the anchor owner_note_text; an owner confirmation of sheet 17 is required
before any product use, and log36 is NOT added to the seam contract eligible set in this slice (the
log59/log66-bridge precedent: bridge first, then owner-confirm + source-bind + render, then promote).

Proves: anchors present + schema-valid + owner/source-backed + modeled + machine-consumable; the cohort
classifier moves log36 REPRESENTATIVE_ROUTE_CANDIDATE (NO_RECORDED_SHEET) -> SOURCE_BINDABLE_NOW (the
explicit, deterministic, log36-LIMITED cohort delta); the frozen ENGINE census is unchanged (identity-
only addition; flag-OFF 31/6/1/17/3, flag-ON 22/1/4); the five prior bridges stay intact; the seam
ELIGIBLE_EXEMPLARS stays log53/log64/log71/log59/log66 (log36 refused by build_seam_payload); no renderer.

Proof-only; the JSON report is written under the gitignored data/outputs path.
Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_log36_endpoint_anchor_bridge_slice
"""
from __future__ import annotations

import json
import re

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

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "log36_endpoint_anchor_bridge_slice"
TRUTH = _REPO_ROOT / "data" / "outputs" / "final_engine_truth_table" / \
    "final_engine_truth_table.json"
FROZEN_BUCKETS = {"DRAWABLE_REVIEW": 31, "HUMAN_ADJUSTABLE_REVIEW": 6,
                  "OUT_OF_CLASS": 1, "PICK_CARD_REVIEW": 17, "SOURCE_OR_KMZ_REQUIRED": 3}
ABSTAIN_4 = ("log5", "log31", "log38", "log43")
# the 6 logs carrying an endpoint-anchor bridge after this slice (log36 is the new one); log59/log66
# were promoted in their own slices, log36 is bridged-but-held-back here
EXPECTED_ANCHOR_LOGS = ("log36", "log53", "log59", "log64", "log66", "log71")
NOT_ANCHORED_NEAR_MISSES = ()   # log36 was the last un-anchored near-miss; none remain after this slice
SHEET = 17
SPAN_FT = 89.0
SEAM_ELIGIBLE = ("log53", "log64", "log71", "log59", "log66")   # log36 NOT promoted into the seam this slice
_HH_89 = re.compile(r"HH\s*[-_]?\s*HH\s*=\s*89(?!\d)", re.I)
_COORD_KEYS = {"x", "y", "z", "xc", "yc", "x0", "y0", "x1", "y1", "cx", "cy", "xy",
               "lat", "lon", "lng", "coord", "coords", "coordinate", "coordinates",
               "px", "py", "pixel", "pixels", "point", "points", "symbol_xy", "anchor_xy",
               "stroke", "stroke_points", "geometry", "geom"}

R_ENCODED = "LOG36_ENDPOINT_ANCHORS_ENCODED"
B_SCHEMA = "BLOCKED_LOG36_SCHEMA_GAP"
B_IDENTITY = "BLOCKED_LOG36_IDENTITY_NOT_REPRESENTABLE"
B_SHEET = "BLOCKED_LOG36_SHEET_EVIDENCE_MISSING"
B_PROMOTED = "BLOCKED_LOG36_SILENTLY_PROMOTED"
B_VALIDATION = "BLOCKED_LOG36_ENDPOINT_ANCHOR_VALIDATION_FAILED"
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
    l36 = rec.get("log36", {})
    ea = l36.get("endpoint_anchors") or {}
    start, end = ea.get("start") or {}, ea.get("end") or {}
    start_note_up = str(start.get("owner_note_text") or "").upper()
    end_note_up = str(end.get("owner_note_text") or "").upper()
    notes_up = str(l36.get("evidence_notes") or "").upper()
    gates = []
    result = B_SCHEMA

    gates.append(("G1 whole artifact still validates clean (additive)",
                  validate_adjudication(doc) == [], None))
    gates.append(("G2 log36 endpoint_anchors present + schema-valid",
                  bool(ea) and validate_endpoint_anchors(l36) == [], None))
    gates.append(("G3 start = structure_terminus installer_hh 'INSTALLER HH' @ STA 0+56 (owner-backed)",
                  start.get("boundary_kind") == "structure_terminus"
                  and start.get("structure_class") == "installer_hh"
                  and start.get("structure_label") == "INSTALLER HH"
                  and start.get("station") == "0+56"
                  and "0+56" in notes_up and "INSTALLER HH" in notes_up, start))
    gates.append(("G4 end = structure_terminus installer_hh 'INSTALLER HH' @ STA 1+45 (owner-backed)",
                  end.get("boundary_kind") == "structure_terminus"
                  and end.get("structure_class") == "installer_hh"
                  and end.get("structure_label") == "INSTALLER HH"
                  and end.get("station") == "1+45"
                  and "1+45" in notes_up and "INSTALLER HH" in notes_up, end))
    gates.append(("G5 both termini classes are modeled (installer_hh + installer_hh)",
                  start.get("structure_class") in MODELED_TERMINUS_CLASSES
                  and end.get("structure_class") in MODELED_TERMINUS_CLASSES, None))
    gates.append(("G6 anchors carry NO coordinate/stroke/geometry field",
                  not _has_coord_keys(start) and not _has_coord_keys(end), None))
    gates.append(("G7 both anchors structure_terminus single-sheet S2S (no matchline; log64 family)",
                  start.get("boundary_kind") == "structure_terminus"
                  and end.get("boundary_kind") == "structure_terminus"
                  and set(ea) <= {"start", "end"}, sorted(ea)))
    # sheet 17 = SOURCE-RECOVERED bridge evidence cited in BOTH anchor notes, explicitly NOT promoted
    gates.append(("G8 sheet 17 cited as SOURCE-RECOVERED bridge evidence in both anchor notes (not promoted)",
                  str(SHEET) in start_note_up and str(SHEET) in end_note_up
                  and "SOURCE-RECOVERED" in start_note_up and "SOURCE-RECOVERED" in end_note_up
                  and "NOT PRODUCT PROMOTION" in start_note_up
                  and l36.get("corrected_sheets") == [], l36.get("corrected_sheets")))
    # both ends reset to 0+00 in DIFFERENT frames -> NO same-frame station arithmetic; the 89' run is
    # corroborated by the printed HH-HH=89' annotation + the owner span_ft (never by subtracting stations)
    gates.append(("G9 HH-HH=89' annotation present (owner-recorded) + span_ft == 89 (no cross-frame station math)",
                  bool(_HH_89.search(str(l36.get("evidence_notes") or "")))
                  and abs(float(l36.get("span_ft") or 0.0) - SPAN_FT) <= 0.5, {"span_ft": l36.get("span_ft")}))

    disp = resolve(doc).get("log36")
    flag_on = flag_on_disposition(l36)
    gates.append(("G10 bridge consumed by resolve()+overlay; drawable stays review_drawable; NEEDS_GEOMETRY",
                  disp is not None and disp.endpoint_anchors is not None
                  and flag_on.get("endpoint_anchors") is not None
                  and flag_on.get("drawable_status") == "review_drawable"
                  and placement_geometry_readiness(l36)["status"] == PLACE_NEEDS_GEOMETRY, None))

    cls = classify_record(l36)["classification"]
    gates.append(("G11 cohort classifier moves log36 -> SOURCE_BINDABLE_NOW (was REPRESENTATIVE_ROUTE_CANDIDATE)",
                  cls == SOURCE_BINDABLE_NOW, {"now": cls, "was": REPRESENTATIVE_ROUTE_CANDIDATE}))

    with_anchors = {r["log_id"] for r in doc["logs"] if r.get("endpoint_anchors")}
    l53e = (rec["log53"].get("endpoint_anchors") or {}).get("end") or {}
    l64s = (rec["log64"].get("endpoint_anchors") or {}).get("start") or {}
    l71s = (rec["log71"].get("endpoint_anchors") or {}).get("start") or {}
    l59s = (rec["log59"].get("endpoint_anchors") or {}).get("start") or {}
    l66s = (rec["log66"].get("endpoint_anchors") or {}).get("start") or {}
    no_other_anchors = all(not rec[l].get("endpoint_anchors") for l in NOT_ANCHORED_NEAR_MISSES)
    gates.append(("G12 prior bridges intact (log53/log59/log64/log66/log71 + new log36); no remaining un-anchored near-miss",
                  set(EXPECTED_ANCHOR_LOGS) == with_anchors
                  and l53e.get("boundary_kind") == "matchline_continuation"
                  and l64s.get("structure_class") == "installer_hh"
                  and l71s.get("structure_class") == "nextlink_hh"
                  and l59s.get("structure_class") == "installer_hh"
                  and l66s.get("structure_class") == "installer_hh" and no_other_anchors,
                  sorted(with_anchors)))

    # NOT silently promoted: log36 stays OUT of the seam contract eligible set; build_seam_payload refuses it
    gates.append(("G13 log36 NOT promoted to seam eligibility (ELIGIBLE_EXEMPLARS == log53/64/71/59/66; seam refuses log36)",
                  tuple(ELIGIBLE_EXEMPLARS) == SEAM_ELIGIBLE
                  and _refuses_seam("log36", rec)
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
    return _emit(gates, result, l36, cls)


def _emit(gates, result, l36, cls) -> int:
    pngs = sorted(p.name for p in OUT_DIR.glob("*.png"))
    gates.append(("G15 zero PNG / zero stroke (no render lane)", len(pngs) == 0, {"pngs": pngs}))
    gates.append(("G16 result in allowed enum", result in ALLOWED, result))
    all_pass = all(x for _, x, _ in gates)
    ea = l36.get("endpoint_anchors") or {}
    report = {
        "milestone": "OWNER-PACKET-2 -- log36 endpoint-anchor bridge slice (proof only; identity encoding)",
        "verdict": "PASS" if all_pass else "FAIL",
        "result": result if all_pass else "BLOCKED",
        "target": "log36", "sheet": SHEET,
        "shape": "single_sheet_structure_to_structure (log64 family; installer-to-installer variant)",
        "anchor_bridge": {"start": ea.get("start"), "end": ea.get("end")},
        "sheet_17_provenance": ("SOURCE-RECOVERED by the near-miss sheet-locator scout (footage_sheets=[17], "
                                "both_bound=[17], uniquely_recovered=True); BRIDGE evidence in anchor notes, "
                                "kept OUT of corrected_sheets; owner confirmation required before product "
                                "use; log36 NOT promoted to seam eligibility"),
        "span_evidence": ("HH-HH=89' annotation + owner span_ft=89; both ends reset to 0+00 in DIFFERENT "
                          "frames, so the run length used NO same-frame station-span arithmetic"),
        "reset_collision_resolved": ("the 0+56=0+00 start reset number-collides with log6/log63 shared-print "
                                     "resets (cross-sheet ranking concern), but on sheet 17 the glued tokens "
                                     "'0+56=0+00' and '1+45=0+00' each occur once and bind a unique installer_hh"),
        "cohort_delta": {"log36": {"from": REPRESENTATIVE_ROUTE_CANDIDATE, "to": cls},
                         "explicit": True, "deterministic": True, "limited_to": "log36"},
        "seam_eligible_unchanged": list(ELIGIBLE_EXEMPLARS),
        "log36_anchored_not_promoted": True,
        "no_pdf_parse": True, "no_render": True, "no_invented_coordinates": True,
        "no_source_bind": True, "no_seam_promotion": True, "engine_census_frozen": True,
        "next_slice": ("log36 source-bind: PRESENT recovered sheet 17 for OWNER confirmation, then a "
                       "log64-style single-sheet source-bind (installer HH 0+56 -> installer HH 1+45 on "
                       "sheet 17); render + seam promotion follow only after that is green. No remaining "
                       "un-anchored near-miss -- the near-miss sheet-locator scout now returns "
                       "NO_SAFE_SHEET_LOCATOR_CANDIDATE; further eligibility growth needs a new source."),
        "gates": [{"name": n, "pass": bool(x), "detail": d} for n, x, d in gates],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "log36_endpoint_anchor_bridge_slice.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"[log36-bridge] result: {result if all_pass else 'BLOCKED'}")
    print(f"[log36-bridge] start: {ea.get('start')}")
    print(f"[log36-bridge] end:   {ea.get('end')}")
    print(f"[log36-bridge] cohort delta: log36 {REPRESENTATIVE_ROUTE_CANDIDATE} -> {cls}")
    for n, x, _ in gates:
        print(f"[log36-bridge] {'PASS' if x else 'FAIL'}  {n}")
    print(f"[log36-bridge] VERDICT: {'PASS' if all_pass else 'FAIL'}  (report: {OUT_DIR})")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
