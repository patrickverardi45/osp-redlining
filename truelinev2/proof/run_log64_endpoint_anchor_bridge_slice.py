r"""OWNER-PACKET-2 -- log64 endpoint-anchor bridge slice (PROOF ONLY; identity encoding).

Encodes + validates the MINIMUM owner-reviewed endpoint identity bridge for log64 -- the safest
first conversion candidate from the cohort replay (single sheet, two MODELED termini, no
cross-sheet gap, no renderer). It places no bore, draws no stroke, renders no PNG, parses no PDF,
and computes no geometry. The bridge holds owner IDENTITY + BOUNDARY semantics ONLY (the schema
law from log53), never coordinates, and authorizes no drawing.

Every encoded field traces to owner-AUTHORITATIVE fields already in the adjudication artifact
(log64.evidence_notes / corrected_start / corrected_end / corrected_sheets), NOT to proximity or
inference:
  start: STA 3+69 = 0+00 at INSTALLER HH (structure_terminus, installer_hh)  -- reset/column-3 start
  end:   STA 1+00 FLOWER POT            (structure_terminus, flower_pot)      -- end of the 100' bore
both on print/sheet 21; direct callout 'STA 0+00 TO STA 1+00 DIR. BORE (100')'.

This proves the bridge is present, schema-valid, owner-backed, modeled, machine-consumable, and
that it moves log64 PARTIAL_SOURCE_BINDABLE -> SOURCE_BINDABLE_NOW in the cohort census -- WITHOUT
changing the frozen engine census (identity-only addition; flag-OFF 31/6/1/17/3, flag-ON 22/1/4),
without touching any other log, and without a renderer. A real PDF source bind is NOT forced here;
the exact remaining blocker for a rendered redline is reported.

Proof-only; the JSON report is written under the gitignored data/outputs path.
Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_log64_endpoint_anchor_bridge_slice
"""
from __future__ import annotations

import json

from truelinev2.config import _REPO_ROOT
from truelinev2.extract.structure_position import BRENHAM_STRUCTURE_LAYERS
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
    PARTIAL_SOURCE_BINDABLE,
    SOURCE_BINDABLE_NOW,
    classify_record,
)

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "log64_endpoint_anchor_bridge_slice"
TRUTH = _REPO_ROOT / "data" / "outputs" / "final_engine_truth_table" / \
    "final_engine_truth_table.json"
FROZEN_BUCKETS = {"DRAWABLE_REVIEW": 31, "HUMAN_ADJUSTABLE_REVIEW": 6,
                  "OUT_OF_CLASS": 1, "PICK_CARD_REVIEW": 17, "SOURCE_OR_KMZ_REQUIRED": 3}
ABSTAIN_4 = ("log5", "log31", "log38", "log43")
EXPECTED_ANCHOR_LOGS = ("log53", "log64")  # the only two carrying the bridge after this slice
_COORD_KEYS = {"x", "y", "z", "xc", "yc", "x0", "y0", "x1", "y1", "cx", "cy", "xy",
               "lat", "lon", "lng", "coord", "coords", "coordinate", "coordinates",
               "px", "py", "pixel", "pixels", "point", "points", "symbol_xy", "anchor_xy",
               "stroke", "stroke_points", "geometry", "geom"}

R_ENCODED = "LOG64_ENDPOINT_ANCHORS_ENCODED"
R_BINDABLE = "LOG64_SOURCE_BINDABLE_NOW"
R_EVIDENCE = "BLOCKED_LOG64_OWNER_EVIDENCE_INSUFFICIENT"
R_AMBIGUOUS = "BLOCKED_LOG64_ANCHOR_IDENTITY_AMBIGUOUS"
R_SCHEMA = "BLOCKED_LOG64_SCHEMA_GAP"
R_BIND_MISSING = "BLOCKED_LOG64_SOURCE_BINDING_STILL_MISSING"
ALLOWED = {R_ENCODED, R_BINDABLE, R_EVIDENCE, R_AMBIGUOUS, R_SCHEMA, R_BIND_MISSING}

# the source bind that would lift log64 to a rendered redline (NOT forced this slice): the
# plan-station label for the sheet-21 endpoints is not pinned in owner evidence (the artifact
# gives bore-local 0+00 -> 1+00 + the reset plan-station 3+69, but not the end pot's plan
# station), exactly as log53 first needed 21+63 / 26+38 pinned before its binds.
NEXT_BLOCKER = ("source bind not forced: the printed plan-station label for the sheet-21 "
                "flower-pot END (and confirmation of the installer-HH START label) is not yet "
                "in owner evidence -- the same owner-evidence/PDF-probe step log53 resolved as "
                "21+63 / 26+38. A separately-authorized sheet-21 bind slice is the next step.")


def _has_coord_keys(anchor: dict) -> bool:
    return bool({str(k).lower() for k in anchor} & _COORD_KEYS)


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for stale in OUT_DIR.glob("*.png"):
        stale.unlink()  # no render/stroke lane: a PNG must never exist

    doc = load_adjudication()
    rec = {r["log_id"]: r for r in doc["logs"]}
    l64 = rec.get("log64", {})
    ea = l64.get("endpoint_anchors") or {}
    start = ea.get("start") or {}
    end = ea.get("end") or {}
    notes_up = str(l64.get("evidence_notes") or "").upper()
    gates = []
    result = R_SCHEMA

    # --- schema validity ----------------------------------------------------------
    gates.append(("G1 whole artifact still validates clean (additive)",
                  validate_adjudication(doc) == [], None))
    gates.append(("G2 log64 endpoint_anchors present + schema-valid",
                  bool(ea) and validate_endpoint_anchors(l64) == [], None))

    # --- start/end identity, modeled + owner-backed (no invention) ----------------
    modeled = set(BRENHAM_STRUCTURE_LAYERS)  # installer_hh / terminal_port_hh / flower_pot
    gates.append(("G3 start = structure_terminus installer_hh 'INSTALLER HH' @3+69 (owner-backed)",
                  start.get("boundary_kind") == "structure_terminus"
                  and start.get("structure_class") == "installer_hh"
                  and start.get("structure_class") in modeled
                  and start.get("structure_label") == "INSTALLER HH"
                  and start.get("station") == "3+69"
                  and "3+69" in notes_up and "INSTALLER HH" in notes_up, start))
    gates.append(("G4 end = structure_terminus flower_pot 'FLOWER POT' @1+00 (owner-backed)",
                  end.get("boundary_kind") == "structure_terminus"
                  and end.get("structure_class") == "flower_pot"
                  and end.get("structure_class") in modeled
                  and end.get("structure_label") == "FLOWER POT"
                  and end.get("station") == "1+00"
                  and "FLOWER POT" in notes_up and "1+00" in notes_up, end))
    gates.append(("G5 end station consistent with corrected_end; single sheet 21",
                  end.get("station") == l64.get("corrected_end")
                  and list(l64.get("corrected_sheets") or []) == [21], l64.get("corrected_sheets")))
    gates.append(("G6 anchors carry NO coordinate/stroke/geometry field",
                  not _has_coord_keys(start) and not _has_coord_keys(end), None))

    # --- machine-consumable downstream (identity only; never auto-placed) ---------
    disp = resolve(doc).get("log64")
    flag_on = flag_on_disposition(l64)
    gates.append(("G7 bridge consumed by resolve()+overlay; drawable stays review_drawable",
                  disp is not None and disp.endpoint_anchors is not None
                  and flag_on.get("endpoint_anchors") is not None
                  and flag_on.get("drawable_status") == "review_drawable", None))
    gates.append(("G8 log64 still NEEDS_GEOMETRY (bridge adds identity, not a positioned path)",
                  placement_geometry_readiness(l64)["status"] == PLACE_NEEDS_GEOMETRY, None))

    # --- cohort move: PARTIAL -> SOURCE_BINDABLE_NOW (the intended conversion) -----
    cls = classify_record(l64)["classification"]
    gates.append(("G9 cohort classifier now buckets log64 SOURCE_BINDABLE_NOW (was PARTIAL)",
                  cls == SOURCE_BINDABLE_NOW, {"now": cls, "was": PARTIAL_SOURCE_BINDABLE}))

    # --- no broad cohort change: only log53 + log64 carry the bridge --------------
    with_anchors = tuple(sorted(r["log_id"] for r in doc["logs"] if r.get("endpoint_anchors")))
    l53s = (rec["log53"].get("endpoint_anchors") or {}).get("start") or {}
    l53e = (rec["log53"].get("endpoint_anchors") or {}).get("end") or {}
    gates.append(("G10 exactly log53 + log64 carry anchors; log53 bridge untouched",
                  with_anchors == EXPECTED_ANCHOR_LOGS
                  and l53s.get("structure_class") == "nextlink_hh"
                  and l53e.get("boundary_kind") == "matchline_continuation", with_anchors))

    # --- frozen ENGINE census (identity-only addition changes no bucket) ----------
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
        gates.append(("G11 engine census frozen (OFF 31/6/1/17/3, ON 22/1/4, log44+abstains held)",
                      census_ok, None))
    else:
        gates.append(("G11 truth table present (census-safety baseline)", False, str(TRUTH)))

    if all(x for _, x, _ in gates):
        result = R_ENCODED
    return _emit(gates, result, l64)


def _emit(gates, result, l64) -> int:
    pngs = sorted(p.name for p in OUT_DIR.glob("*.png"))
    gates.append(("G12 zero PNG / zero stroke (no render lane)", len(pngs) == 0, {"pngs": pngs}))
    gates.append(("G13 result in allowed enum", result in ALLOWED, result))
    all_pass = all(x for _, x, _ in gates)
    ea = l64.get("endpoint_anchors") or {}
    report = {
        "milestone": "OWNER-PACKET-2 -- log64 endpoint-anchor bridge slice (proof only; identity encoding)",
        "verdict": "PASS" if all_pass else "FAIL",
        "result": result if all_pass else "BLOCKED",
        "target": "log64", "sheet": 21,
        "anchor_bridge": {"start": ea.get("start"), "end": ea.get("end")},
        "cohort_move": {"from": PARTIAL_SOURCE_BINDABLE, "to": SOURCE_BINDABLE_NOW},
        "source_bind_next_blocker": NEXT_BLOCKER,
        "no_pdf_parse": True, "no_render": True, "no_invented_coordinates": True,
        "no_forced_placement": True, "no_broad_cohort_encoding": True,
        "engine_census_frozen": True,
        "gates": [{"name": n, "pass": bool(x), "detail": d} for n, x, d in gates],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "log64_endpoint_anchor_bridge_slice.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"[log64-bridge] result: {result if all_pass else 'BLOCKED'}")
    print(f"[log64-bridge] start: {ea.get('start')}")
    print(f"[log64-bridge] end:   {ea.get('end')}")
    print(f"[log64-bridge] source-bind next blocker: {NEXT_BLOCKER[:160]}")
    for n, x, _ in gates:
        print(f"[log64-bridge] {'PASS' if x else 'FAIL'}  {n}")
    print(f"[log64-bridge] VERDICT: {'PASS' if all_pass else 'FAIL'}  (report: {OUT_DIR})")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
