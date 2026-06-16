r"""OWNER-CORRECTED endpoint-anchor bridge slice -- log67/69/70/47/11 (PROOF ONLY; identity encoding).

Locks the consequences of applying the owner-confirmed/source-verified corrections (2026-06-16) for the
five source-verified logs from the owner-correction recon scout. Each now carries an IDENTITY-ONLY
endpoint_anchors bridge in the reviewed fixture; this slice proves the bridge is well-formed and that its
cohort/ledger/seam-refusal consequences are exactly as intended -- it changes no fixture (the corrections
are already applied), parses no coordinate into a placement, draws nothing, promotes nothing.

The five owner-corrected bridges (start -> end; every class source-verified as the UNIQUE resolver bind):
  log67  installer_hh @ 1+45=0+00 (s17) -> flower_pot @ 4+14 (s20)    [cross-sheet 17->20]
  log69  installer_hh @ 1+45=0+00 (s17) -> installer_hh @ 4+54 (s17)  [SINGLE-SHEET -- both on s17]
  log70  installer_hh @ 1+45=0+00 (s17) -> flower_pot @ 2+15 (s20)    [cross-sheet 17->20]
  log47  flower_pot   @ 3+23     (s13) -> installer_hh @ 4+94 (s14)   [cross-sheet; join 10->13->14 backed]
  log11  nextlink_hh  @ 21+63=0+00 (s5)-> flower_pot @ 6+30 (s17)     [cross-sheet 5->17; join backed]

Proves: each carries a schema-valid, identity-only (NO coordinate), two-structure-terminus bridge with the
owner-corrected classes; each cohort-classifies SOURCE_BINDABLE_NOW (the cohort delta PARTIAL/REPRESENTATIVE
-> SOURCE_BINDABLE_NOW); log69 is single-sheet (corrected_sheets [17]) while log67/70/47/11 stay cross-sheet;
the engine census is FROZEN (additive; flag-OFF 31/6/1/17/3, flag-ON 22/1/4); all five are HELD BACK (anchored
but seam-REFUSED -- ELIGIBLE_EXEMPLARS unchanged at 5, nothing promoted); the held-back set becomes the 8
{log11,36,47,52,58,67,69,70}; the anchored set becomes 13; the closure ledger moves CROSS_SHEET 6->1 (only
log48 parent/child remains) and SOURCE_BINDABLE_HELD_BACK 3->8; no renderer.

Proof-only; the JSON report is written under the gitignored data/outputs path.
Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_owner_corrected_endpoint_anchor_bridge_slice
"""
from __future__ import annotations

import json

from truelinev2.config import _REPO_ROOT
from truelinev2.ingest.manual_adjudication import (
    activation_summary,
    apply_adjudications,
    load_adjudication,
    parent_run_duplicate_check,
    validate_adjudication,
    validate_endpoint_anchors,
)
from truelinev2.proof.run_all_redlines_closure_ledger import (
    CROSS_SHEET,
    HELD_BACK,
    UNMODELED_TERMINUS,
    build_ledger,
)
from truelinev2.proof.run_log53_primitives_cohort_replay import (
    MODELED_TERMINUS_CLASSES,
    SOURCE_BINDABLE_NOW,
    classify_record,
)
from truelinev2.seam import ELIGIBLE_EXEMPLARS, build_seam_payload

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "owner_corrected_endpoint_anchor_bridge_slice"
TRUTH = _REPO_ROOT / "data" / "outputs" / "final_engine_truth_table" / \
    "final_engine_truth_table.json"
FROZEN_BUCKETS = {"DRAWABLE_REVIEW": 31, "HUMAN_ADJUSTABLE_REVIEW": 6,
                  "OUT_OF_CLASS": 1, "PICK_CARD_REVIEW": 17, "SOURCE_OR_KMZ_REQUIRED": 3}
ABSTAIN_4 = ("log5", "log31", "log38", "log43")
SEAM_ELIGIBLE = ("log53", "log64", "log71", "log59", "log66")

# the owner-corrected bridges (start/end as (structure_class, station)); the per-endpoint sheet is in the
# anchor owner_note_text. Source-verified by run_owner_correction_recon_scout.
CORRECTED = {
    "log67": {"start": ("installer_hh", "1+45"), "end": ("flower_pot", "4+14"), "sheets": [17, 20]},
    "log69": {"start": ("installer_hh", "1+45"), "end": ("installer_hh", "4+54"), "sheets": [17]},
    "log70": {"start": ("installer_hh", "1+45"), "end": ("flower_pot", "2+15"), "sheets": [17, 20]},
    "log47": {"start": ("flower_pot", "3+23"), "end": ("installer_hh", "4+94"), "sheets": [10, 13, 14]},
    "log11": {"start": ("nextlink_hh", "21+63"), "end": ("flower_pot", "6+30"), "sheets": [5, 17]},
}
SINGLE_SHEET = ("log69",)
HELD_BACK_8 = ("log11", "log36", "log47", "log52", "log58", "log67", "log69", "log70")
ANCHORED_13 = ("log11", "log36", "log47", "log52", "log53", "log58", "log59",
               "log64", "log66", "log67", "log69", "log70", "log71")
_COORD_KEYS = {"x", "y", "z", "xc", "yc", "x0", "y0", "x1", "y1", "cx", "cy", "xy",
               "lat", "lon", "lng", "coord", "coords", "coordinate", "coordinates",
               "px", "py", "pixel", "pixels", "point", "points", "symbol_xy", "anchor_xy",
               "stroke", "stroke_points", "geometry", "geom"}

R_ENCODED = "OWNER_CORRECTED_ENDPOINT_ANCHORS_ENCODED"
B_SCHEMA = "BLOCKED_OWNER_CORRECTED_SCHEMA_GAP"
B_COHORT = "BLOCKED_OWNER_CORRECTED_COHORT_DRIFT"
B_PROMOTED = "BLOCKED_OWNER_CORRECTED_SILENTLY_PROMOTED"
B_CENSUS = "BLOCKED_OWNER_CORRECTED_CENSUS_DRIFT"
ALLOWED = {R_ENCODED, B_SCHEMA, B_COHORT, B_PROMOTED, B_CENSUS}


def _has_coord_keys(a: dict) -> bool:
    return bool({str(k).lower() for k in a} & _COORD_KEYS)


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
    gates = []
    result = B_SCHEMA

    gates.append(("G0 whole artifact still validates clean (additive corrections)",
                  validate_adjudication(doc) == [], None))

    # G1 each of the 5 carries a schema-valid, identity-only, two-structure-terminus bridge with the
    #    owner-corrected classes/stations (NO coordinate field)
    schema_ok = True
    for lid, exp in CORRECTED.items():
        l = rec.get(lid, {})
        ea = l.get("endpoint_anchors") or {}
        start, end = ea.get("start") or {}, ea.get("end") or {}
        ok = (validate_endpoint_anchors(l) == [] and set(ea) <= {"start", "end"}
              and start.get("boundary_kind") == "structure_terminus"
              and end.get("boundary_kind") == "structure_terminus"
              and (start.get("structure_class"), start.get("station")) == exp["start"]
              and (end.get("structure_class"), end.get("station")) == exp["end"]
              and start.get("structure_class") in MODELED_TERMINUS_CLASSES
              and end.get("structure_class") in MODELED_TERMINUS_CLASSES
              and not _has_coord_keys(start) and not _has_coord_keys(end)
              and l.get("corrected_sheets") == exp["sheets"])
        schema_ok = schema_ok and ok
    gates.append(("G1 log67/69/70/47/11 carry schema-valid identity-only two-terminus bridges (owner-corrected classes; NO coords)",
                  schema_ok, None))

    # G2 cohort: all 5 now classify SOURCE_BINDABLE_NOW
    cls = {lid: classify_record(rec[lid])["classification"] for lid in CORRECTED}
    gates.append(("G2 cohort: all 5 owner-corrected logs classify SOURCE_BINDABLE_NOW",
                  all(c == SOURCE_BINDABLE_NOW for c in cls.values()), cls))

    # G3 log69 single-sheet [17]; log67/70/47/11 stay multi-sheet (cross-sheet)
    g3 = (rec["log69"].get("corrected_sheets") == [17]
          and all(len(rec[l].get("corrected_sheets") or []) >= 2 for l in ("log67", "log70", "log47", "log11")))
    gates.append(("G3 log69 single-sheet [17]; log67/70/47/11 stay cross-sheet (multi-sheet)", g3, None))

    # G4 NOT promoted: all 5 are seam-REFUSED (held back); ELIGIBLE_EXEMPLARS unchanged (5)
    gates.append(("G4 NOT promoted: all 5 seam-REFUSED (held back); ELIGIBLE_EXEMPLARS == log53/64/71/59/66 (5)",
                  tuple(ELIGIBLE_EXEMPLARS) == SEAM_ELIGIBLE
                  and all(_refuses_seam(l, rec) for l in CORRECTED), None))

    # G5 held-back set == 8; anchored set == 13
    with_anchors = tuple(sorted((l for l in rec if rec[l].get("endpoint_anchors")), key=lambda s: int(s[3:])))
    held_back = tuple(sorted((l for l in rec if rec[l].get("endpoint_anchors") and _refuses_seam(l, rec)),
                             key=lambda s: int(s[3:])))
    gates.append(("G5 held-back set == 8 {log11,36,47,52,58,67,69,70}; anchored set == 13",
                  held_back == HELD_BACK_8 and with_anchors == ANCHORED_13,
                  {"held_back": list(held_back), "anchored": list(with_anchors)}))

    # G6 closure ledger: CROSS_SHEET == 1 (only log48 parent/child); SOURCE_BINDABLE_HELD_BACK == 8
    led_ok = False
    if TRUTH.is_file():
        rows = json.loads(TRUTH.read_text(encoding="utf-8"))["rows"]
        ledger = build_ledger(rows, doc)
        from collections import Counter
        c = Counter(v["category"] for v in ledger.values())
        cross = sorted((b for b, v in ledger.items() if v["category"] == CROSS_SHEET), key=lambda s: int(s[3:]))
        led_ok = (c[CROSS_SHEET] == 1 and cross == ["log48"] and c[HELD_BACK] == 8
                  and c[UNMODELED_TERMINUS] == 6)
        gates.append(("G6 ledger: CROSS_SHEET == 1 (log48 only); HELD_BACK == 8; UNMODELED == 6",
                      led_ok, {"cross_sheet": cross, "held_back": c[HELD_BACK]}))
    else:
        gates.append(("G6 truth table present (ledger baseline)", False, str(TRUTH)))

    # G7 engine census FROZEN (additive; OFF byte-identical, ON 22/1/4)
    census_ok = False
    if TRUTH.is_file():
        rows = json.loads(TRUTH.read_text(encoding="utf-8"))["rows"]
        baseline = {r["bore_id"]: dict(r) for r in rows}
        off = apply_adjudications(baseline, enabled=False)
        on = apply_adjudications(baseline, enabled=True, doc=doc)
        summ = activation_summary(on)
        buckets = {}
        for r in off.values():
            buckets[r["completion_bucket"]] = buckets.get(r["completion_bucket"], 0) + 1
        census_ok = (off is baseline and buckets == FROZEN_BUCKETS
                     and summ["manual_review_drawable"] == 22 and summ["manual_source_verification"] == 1
                     and summ["manual_abstain"] == 4
                     and on["log44"]["adjudication"]["drawable_status"] == "non_drawable"
                     and all(on[l]["adjudication"]["drawable_status"] == "abstain" for l in ABSTAIN_4)
                     and not parent_run_duplicate_check(doc))
    gates.append(("G7 engine census FROZEN (additive: OFF 31/6/1/17/3, ON 22/1/4, log44+abstains held)",
                  census_ok, None))

    if all(x for _, x, _ in gates):
        result = R_ENCODED
    elif not census_ok:
        result = B_CENSUS
    elif not (gates[3][1] if len(gates) > 3 else True):
        result = B_COHORT
    return _emit(gates, result, rec, cls, held_back, with_anchors)


def _emit(gates, result, rec, cls, held_back, with_anchors) -> int:
    pngs = sorted(p.name for p in OUT_DIR.glob("*.png"))
    gates.append(("G8 zero PNG / zero stroke (no render lane)", len(pngs) == 0, {"pngs": pngs}))
    gates.append(("G9 result in allowed enum", result in ALLOWED, result))
    all_pass = all(x for _, x, _ in gates)
    report = {
        "milestone": "OWNER-CORRECTED endpoint-anchor bridge slice (proof only; identity encoding) -- log67/69/70/47/11",
        "verdict": "PASS" if all_pass else "FAIL",
        "result": result if all_pass else "BLOCKED",
        "bridged": {lid: {"start": rec[lid]["endpoint_anchors"]["start"],
                          "end": rec[lid]["endpoint_anchors"]["end"],
                          "corrected_sheets": rec[lid]["corrected_sheets"]} for lid in CORRECTED},
        "single_sheet": list(SINGLE_SHEET),
        "cohort_now": cls,
        "held_back_set": list(held_back),
        "anchored_set": list(with_anchors),
        "seam_eligible_unchanged": list(ELIGIBLE_EXEMPLARS),
        "ledger_delta": "CROSS_SHEET 6->1 (only log48 parent/child remains); SOURCE_BINDABLE_HELD_BACK 3->8",
        "no_coordinates": True, "no_render": True, "no_seam_promotion": True, "engine_census_frozen": True,
        "next_slice": ("source-bind + render the owner-corrected held-back logs (each separately authorized): "
                       "log69 single-sheet (installer->installer on s17); log67/70/47/11 cross-sheet two-leg "
                       "(crossing reconciliation deferred; for log67/70 the 17<->20 conflicting crossing is a "
                       "render-time concern). log48 stays parent/child reconstruction pending owner segmentation."),
        "gates": [{"name": n, "pass": bool(x), "detail": d} for n, x, d in gates],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "owner_corrected_endpoint_anchor_bridge_slice.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"[owner-bridge] result: {result if all_pass else 'BLOCKED'}")
    for lid in CORRECTED:
        ea = rec[lid]["endpoint_anchors"]
        print(f"[owner-bridge]   {lid}: {ea['start']['structure_class']} {ea['start']['station']} -> "
              f"{ea['end']['structure_class']} {ea['end']['station']}  sheets={rec[lid]['corrected_sheets']}")
    for n, x, _ in gates:
        print(f"[owner-bridge] {'PASS' if x else 'FAIL'}  {n}")
    print(f"[owner-bridge] VERDICT: {'PASS' if all_pass else 'FAIL'}  (report: {OUT_DIR})")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
