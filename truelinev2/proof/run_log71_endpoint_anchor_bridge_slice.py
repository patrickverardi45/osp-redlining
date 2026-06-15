r"""OWNER-PACKET-2 -- log71 endpoint-anchor bridge slice (PROOF ONLY; identity encoding).

Encodes + validates log71's owner-reviewed endpoint identity bridge, now that the owner has
CONFIRMED (2026-06-15) the Lawndale reset start is a NEXTLINK HH -- the blocker the sheet-local
bind scout (07aad25) deferred. It places no bore, draws no stroke, renders no PNG, parses no PDF,
and solves no cross-sheet frame. Identity + boundary semantics ONLY, never coordinates.

log71 is the log64 shape (BOTH endpoints are modeled structure termini), cross-sheet variant:
  start: STA 7+50 NEXTLINK HH (structure_terminus, nextlink_hh) on sheet 24 -- OWNER-CONFIRMED
         (the reset 'STA 7+50 = 0+00' is owner-documented; the class is owner-confirmed and
         source-binds via the committed nextlink-callout locator);
  end:   STA 6+95 FLOWER POT (structure_terminus, flower_pot) on sheet 23 -- OWNER-NAMED.
The intermediate 'STA 5+45 - SEE SHEET 24' matchline is NOT a separate anchor: the endpoint_anchors
schema has only start/end TERMINUS slots, and 5+45 is a between-leg crossing (route geometry the
bind/render slice resolves by chain-reach + station identity, already proven by the scout), not an
endpoint identity. It is preserved as route context in the END anchor's owner_note_text.

Proves: anchors present + schema-valid + owner-backed + modeled + machine-consumable; log71 moves
PARTIAL_SOURCE_BINDABLE -> SOURCE_BINDABLE_NOW (intended cohort delta); the frozen ENGINE census is
unchanged (identity-only addition; flag-OFF 31/6/1/17/3, flag-ON 22/1/4); no other log is touched;
no renderer.

Proof-only; the JSON report is written under the gitignored data/outputs path.
Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_log71_endpoint_anchor_bridge_slice
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
    PARTIAL_SOURCE_BINDABLE,
    SOURCE_BINDABLE_NOW,
    classify_record,
)

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "log71_endpoint_anchor_bridge_slice"
TRUTH = _REPO_ROOT / "data" / "outputs" / "final_engine_truth_table" / \
    "final_engine_truth_table.json"
FROZEN_BUCKETS = {"DRAWABLE_REVIEW": 31, "HUMAN_ADJUSTABLE_REVIEW": 6,
                  "OUT_OF_CLASS": 1, "PICK_CARD_REVIEW": 17, "SOURCE_OR_KMZ_REQUIRED": 3}
ABSTAIN_4 = ("log5", "log31", "log38", "log43")
EXPECTED_ANCHOR_LOGS = ("log53", "log64", "log71")  # bridges guaranteed present (subset; later slices add more)
_COORD_KEYS = {"x", "y", "z", "xc", "yc", "x0", "y0", "x1", "y1", "cx", "cy", "xy",
               "lat", "lon", "lng", "coord", "coords", "coordinate", "coordinates",
               "px", "py", "pixel", "pixels", "point", "points", "symbol_xy", "anchor_xy",
               "stroke", "stroke_points", "geometry", "geom"}

R_ENCODED = "LOG71_ENDPOINT_ANCHORS_ENCODED"
B_SCHEMA = "BLOCKED_LOG71_SCHEMA_GAP"
B_OWNER = "BLOCKED_LOG71_OWNER_CONFIRMATION_NOT_REPRESENTABLE"
B_MATCHLINE = "BLOCKED_LOG71_MATCHLINE_ANCHOR_AMBIGUOUS"
B_VALIDATION = "BLOCKED_LOG71_ENDPOINT_ANCHOR_VALIDATION_FAILED"
ALLOWED = {R_ENCODED, B_SCHEMA, B_OWNER, B_MATCHLINE, B_VALIDATION}


def _has_coord_keys(anchor: dict) -> bool:
    return bool({str(k).lower() for k in anchor} & _COORD_KEYS)


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for stale in OUT_DIR.glob("*.png"):
        stale.unlink()

    doc = load_adjudication()
    rec = {r["log_id"]: r for r in doc["logs"]}
    l71 = rec.get("log71", {})
    ea = l71.get("endpoint_anchors") or {}
    start, end = ea.get("start") or {}, ea.get("end") or {}
    notes_up = str(l71.get("evidence_notes") or "").upper()
    start_note_up = str(start.get("owner_note_text") or "").upper()
    end_note_up = str(end.get("owner_note_text") or "").upper()
    gates = []
    result = B_SCHEMA

    gates.append(("G1 whole artifact still validates clean (additive)",
                  validate_adjudication(doc) == [], None))
    gates.append(("G2 log71 endpoint_anchors present + schema-valid",
                  bool(ea) and validate_endpoint_anchors(l71) == [], None))

    # start: owner-CONFIRMED nextlink_hh (reset station owner-documented; class owner-confirmed)
    gates.append(("G3 start = structure_terminus nextlink_hh 'NEXTLINK HH' @7+50 (owner-confirmed)",
                  start.get("boundary_kind") == "structure_terminus"
                  and start.get("structure_class") == "nextlink_hh"
                  and start.get("structure_label") == "NEXTLINK HH"
                  and start.get("station") == "7+50"
                  and "7+50" in notes_up                       # reset is owner-documented
                  and "NEXTLINK HH" in start_note_up and "OWNER-CONFIRMED" in start_note_up, start))
    # end: owner-NAMED flower_pot (both station + class in the reviewed evidence_notes)
    gates.append(("G4 end = structure_terminus flower_pot 'FLOWER POT' @6+95 (owner-named)",
                  end.get("boundary_kind") == "structure_terminus"
                  and end.get("structure_class") == "flower_pot"
                  and end.get("structure_label") == "FLOWER POT"
                  and end.get("station") == "6+95"
                  and "6+95" in notes_up and "FLOWER POT" in notes_up, end))
    gates.append(("G5 both termini classes are modeled (nextlink_hh + flower_pot)",
                  start.get("structure_class") in MODELED_TERMINUS_CLASSES
                  and end.get("structure_class") in MODELED_TERMINUS_CLASSES, None))
    gates.append(("G6 anchors carry NO coordinate/stroke/geometry field",
                  not _has_coord_keys(start) and not _has_coord_keys(end), None))
    # the 5+45 matchline is route context in the END anchor, NOT a separate anchor (schema is
    # start/end termini only; the crossing is a bind-time join, not an endpoint identity)
    gates.append(("G7 5+45 matchline preserved as route context in end anchor (not a 3rd anchor)",
                  "5+45" in end_note_up and set(ea) <= {"start", "end"}, sorted(ea)))

    disp = resolve(doc).get("log71")
    flag_on = flag_on_disposition(l71)
    gates.append(("G8 bridge consumed by resolve()+overlay; drawable stays review_drawable",
                  disp is not None and disp.endpoint_anchors is not None
                  and flag_on.get("endpoint_anchors") is not None
                  and flag_on.get("drawable_status") == "review_drawable", None))
    gates.append(("G9 log71 still NEEDS_GEOMETRY (bridge adds identity, not a positioned path)",
                  placement_geometry_readiness(l71)["status"] == PLACE_NEEDS_GEOMETRY, None))

    cls = classify_record(l71)["classification"]
    gates.append(("G10 cohort classifier now buckets log71 SOURCE_BINDABLE_NOW (was PARTIAL)",
                  cls == SOURCE_BINDABLE_NOW, {"now": cls, "was": PARTIAL_SOURCE_BINDABLE}))

    # subset check, not exact: later slices legitimately add more bridges -- this must not break
    # as the cohort grows; the exact count is locked by the cohort replay SOURCE_BINDABLE_NOW count.
    with_anchors = {r["log_id"] for r in doc["logs"] if r.get("endpoint_anchors")}
    l53e = (rec["log53"].get("endpoint_anchors") or {}).get("end") or {}
    l64s = (rec["log64"].get("endpoint_anchors") or {}).get("start") or {}
    gates.append(("G11 log53+log64+log71 bridges present + intact (log53/log64 untouched)",
                  set(EXPECTED_ANCHOR_LOGS) <= with_anchors
                  and l53e.get("boundary_kind") == "matchline_continuation"
                  and l64s.get("structure_class") == "installer_hh", sorted(with_anchors)))

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
        gates.append(("G12 engine census frozen (OFF 31/6/1/17/3, ON 22/1/4, log44+abstains held)",
                      census_ok, None))
    else:
        gates.append(("G12 truth table present (census-safety baseline)", False, str(TRUTH)))

    if all(x for _, x, _ in gates):
        result = R_ENCODED
    return _emit(gates, result, l71)


def _emit(gates, result, l71) -> int:
    pngs = sorted(p.name for p in OUT_DIR.glob("*.png"))
    gates.append(("G13 zero PNG / zero stroke (no render lane)", len(pngs) == 0, {"pngs": pngs}))
    gates.append(("G14 result in allowed enum", result in ALLOWED, result))
    all_pass = all(x for _, x, _ in gates)
    ea = l71.get("endpoint_anchors") or {}
    report = {
        "milestone": "OWNER-PACKET-2 -- log71 endpoint-anchor bridge slice (proof only; identity encoding)",
        "verdict": "PASS" if all_pass else "FAIL",
        "result": result if all_pass else "BLOCKED",
        "target": "log71", "sheets": [24, 23],
        "anchor_bridge": {"start": ea.get("start"), "end": ea.get("end")},
        "matchline_5_45": "route context in end anchor (between-leg crossing; not an endpoint identity)",
        "cohort_move": {"from": PARTIAL_SOURCE_BINDABLE, "to": SOURCE_BINDABLE_NOW},
        "start_owner_confirmed_not_originally_named": True,
        "no_pdf_parse": True, "no_render": True, "no_invented_coordinates": True,
        "no_broad_cohort_encoding": True, "engine_census_frozen": True,
        "next_slice": ("log53-style TWO sheet-local-leg source-bind proof for log71 (start leg s24 "
                       "nextlink HH -> 5+45 matchline; end leg s23 5+45 matchline -> flower pot), "
                       "chain-reach 5+45 disambiguation, cross-sheet translation deferred; then a "
                       "contained render."),
        "gates": [{"name": n, "pass": bool(x), "detail": d} for n, x, d in gates],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "log71_endpoint_anchor_bridge_slice.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"[log71-bridge] result: {result if all_pass else 'BLOCKED'}")
    print(f"[log71-bridge] start: {ea.get('start')}")
    print(f"[log71-bridge] end:   {ea.get('end')}")
    for n, x, _ in gates:
        print(f"[log71-bridge] {'PASS' if x else 'FAIL'}  {n}")
    print(f"[log71-bridge] VERDICT: {'PASS' if all_pass else 'FAIL'}  (report: {OUT_DIR})")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
