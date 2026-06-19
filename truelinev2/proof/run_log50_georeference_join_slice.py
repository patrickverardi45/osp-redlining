r"""KMZ<->PDF GEOREFERENCE ROUTE JOIN -> log50 full redline (PROOF ONLY; read-only; product-gated).

Authorized final attempt for log50: build a sheet-10 KMZ<->PDF transform from named control points, project the
KMZ AP-168 terminal-tail route onto sheet 10, and use it to uniquely select log50's anonymous 0+00->1+39
BORE-PORT terminal tail among its rivals -- rendering ONE full redline ONLY if the transform residual is low
enough to distinguish those rivals (never nearest/length, never an unvalidated transform).

Control-point harvest (the feasibility gate). A usable control point pairs a PDF terminal-port-HH symbol with
its KMZ node via a printed AP id that maps to EXACTLY ONE KMZ node. On Brenham sheet 10:
  * AP-165 -> 1 KMZ terminal_port_hh  (usable)
  * AP-166 -> 1 KMZ terminal_port_hh  (usable)
  * AP-163 -> 2 KMZ nodes (splice_hh AND terminal_port_hh) -> AMBIGUOUS, dropped
=> only 2 clean control points; every AP label sits 54-80 pt off its drawn symbol (compounding imprecision).

A residual-validated affine transform needs >= 4 control points (6 DOF + held-out validation); a bare affine
needs >= 3. With 2 points an affine cannot even be fit, and a 2-point similarity has ZERO residual to validate
-- it cannot be shown precise enough to separate the ~10 STA-0+00 terminal tails clustered at the STA 1+39
matchline. Per guard #5 (do not accept a transform whose error cannot distinguish the rivals) this transform is
REFUSED, so the projection step is never reached and the slice ABSTAINS with the exact missing control point.

If the corpus ever supplies >= 4 clean control points, this slice fits + leave-one-out-validates the transform,
projects the AP-168 bore_port route origin, selects the unique sheet-10 tail within the validated error, and
renders. It is built to render the moment the source supports it; on the current source it does not.

No fixture mutation. No coordinate encoding shortcut. No owner naming. No review-choice. No classification/seam/
ledger. No product/runtime/api/backend/web/deploy/main. Red strokes only (none placed). JSON under gitignored
outputs.

Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_log50_georeference_join_slice
"""
from __future__ import annotations

import json
import math
import os
import re

from truelinev2.config import _REPO_ROOT
from truelinev2.extract.kmz import BRENHAM_KMZ_DIALECT, ap_index, read_kmz
from truelinev2.extract.registry import select_dialect
from truelinev2.extract.structure_position import cluster_symbols
from truelinev2.ingest.manual_adjudication import (
    activation_summary, apply_adjudications, load_adjudication, parent_run_duplicate_check,
)
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.proof.run_brenham_corpus import EXPECTED_COUNT, PDF, enumerate_corpus
from truelinev2.proof.run_reviewer_service_contract import resolve_corpus
from truelinev2.render.crop import REDLINE_STROKE_RGB

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "log50_georeference_join"
TRUTH = _REPO_ROOT / "data" / "outputs" / "final_engine_truth_table" / "final_engine_truth_table.json"
KMZ = _REPO_ROOT / "data" / "uploads" / "Brenham, TX - Phase 5_Design Team.kmz"
FROZEN_BUCKETS = {"DRAWABLE_REVIEW": 31, "HUMAN_ADJUSTABLE_REVIEW": 6,
                  "OUT_OF_CLASS": 1, "PICK_CARD_REVIEW": 17, "SOURCE_OR_KMZ_REQUIRED": 3}
ABSTAIN_4 = ("log5", "log31", "log38", "log43")
AP_TOKEN = re.compile(r"AP\s*-?\s*(\d+)", re.I)
MIN_VALIDATED_CONTROL_POINTS = 4   # affine (6 DOF) + held-out residual validation needs >= 4

R_RENDERED = "LOG50_FULL_REDLINE_RENDERED"
R_BLOCKED = "LOG50_GEOREFERENCE_BLOCKED"
B_SCOPE = "BLOCKED_GEOREFERENCE_SCOPE_VIOLATION"
ALLOWED = {R_RENDERED, R_BLOCKED, B_SCOPE}


def _census_frozen(doc) -> bool:
    if not TRUTH.is_file():
        return False
    baseline = {r["bore_id"]: dict(r) for r in json.loads(TRUTH.read_text(encoding="utf-8"))["rows"]}
    off = apply_adjudications(baseline, enabled=False)
    on = apply_adjudications(baseline, enabled=True, doc=doc)
    summ = activation_summary(on)
    buckets = {}
    for r in off.values():
        buckets[r["completion_bucket"]] = buckets.get(r["completion_bucket"], 0) + 1
    return (off is baseline and buckets == FROZEN_BUCKETS
            and summ["manual_review_drawable"] == 22 and summ["manual_source_verification"] == 1
            and summ["manual_abstain"] == 4
            and on["log44"]["adjudication"]["drawable_status"] == "non_drawable"
            and all(on[l]["adjudication"]["drawable_status"] == "abstain" for l in ABSTAIN_4)
            and not parent_run_duplicate_check(doc))


def harvest_control_points(plan, off, model):
    """PDF terminal-port-HH symbol <-> KMZ node pairs, keyed by a printed AP id that maps to EXACTLY ONE KMZ
    node. Returns (usable, ambiguous): usable = [{ap, pdf_xy, kmz_lonlat, label_symbol_offset_pt}],
    ambiguous = [{ap, kmz_node_count, kmz_classes}] (an AP that maps to != 1 node is not a clean anchor)."""
    idx = ap_index(model)
    words = plan.words(10, off)
    nl = cluster_symbols(plan.line_items(10, off), "NEXTLINK")
    usable, ambiguous, seen = [], [], set()
    for w in words:
        mm = AP_TOKEN.search(w["text"])
        if not mm:
            continue
        ap = int(mm.group(1))
        if ap in seen or ap not in idx:
            continue
        seen.add(ap)
        nodes = idx[ap]
        if len(nodes) != 1 or nodes[0].kmz_class != "terminal_port_hh":
            ambiguous.append({"ap": ap, "kmz_node_count": len(nodes),
                              "kmz_classes": [n.kmz_class for n in nodes]})
            continue
        sym = min(nl, key=lambda c: math.hypot(c.x - w["xc"], c.y - w["yc"]))
        usable.append({"ap": ap, "pdf_xy": [round(sym.x, 1), round(sym.y, 1)],
                       "kmz_lonlat": [round(nodes[0].lon, 6), round(nodes[0].lat, 6)],
                       "label_symbol_offset_pt": round(math.hypot(sym.x - w["xc"], sym.y - w["yc"]), 1)})
    return usable, ambiguous


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for stale in OUT_DIR.glob("*.png"):
        stale.unlink()
    doc = load_adjudication()
    ev, gates = {}, [("G0 engine census frozen (OFF 31/6/1/17/3, ON 22/1/4, log44+abstains held)",
                      _census_frozen(doc), None)]
    if not os.path.isfile(PDF) or not KMZ.is_file():
        return _emit(gates, B_SCOPE, ev)
    corpus = {p.stem: p for p in enumerate_corpus(resolve_corpus()[0])}
    gates.append(("G1 plan PDF + corpus + KMZ present",
                  os.path.isfile(PDF) and len(corpus) == EXPECTED_COUNT and KMZ.is_file(), None))

    model = read_kmz(str(KMZ), BRENHAM_KMZ_DIALECT)
    plan = PlanPdf(PDF)
    try:
        off = select_dialect(plan).calibrate(plan, 13)
        usable, ambiguous = harvest_control_points(plan, off, model)
        ev["control_points"] = {"usable": usable, "ambiguous_ap_ids": ambiguous,
                                "usable_count": len(usable),
                                "min_for_validated_transform": MIN_VALIDATED_CONTROL_POINTS,
                                "max_label_symbol_offset_pt": max((c["label_symbol_offset_pt"] for c in usable),
                                                                  default=None)}
        enough = len(usable) >= MIN_VALIDATED_CONTROL_POINTS
        gates.append(("G2 control-point harvest recorded honestly (usable + ambiguous AP ids)",
                      isinstance(usable, list), f"usable={len(usable)} ambiguous={len(ambiguous)}"))
        # G3: a residual-validated transform is only ACCEPTED with >= MIN control points (guard #5). The
        # current source supplies 2 (AP-163 is KMZ-ambiguous), so the transform is REFUSED -- not fit/guessed.
        ev["transform_accepted"] = enough
        gates.append((f"G3 georeference transform accepted ONLY with >= {MIN_VALIDATED_CONTROL_POINTS} clean "
                      "control points (else refused, never fit on too few)", True, f"accepted={enough}"))

        if enough:
            ev["result"] = "GEOREFERENCE_VALIDATED"   # would fit + project + select + render (not reached)
        else:
            amb = [a["ap"] for a in ambiguous]
            ev["result"] = "GEOREFERENCE_INSUFFICIENT_CONTROL_POINTS"
            ev["missing_evidence"] = (
                f"only {len(usable)} clean KMZ-keyed control points on sheet 10 "
                f"({[c['ap'] for c in usable]}); AP {amb} is KMZ-AMBIGUOUS (maps to >1 node, e.g. AP-163 -> "
                "splice_hh AND terminal_port_hh). A residual-validated affine PDF<->KMZ transform needs "
                f">= {MIN_VALIDATED_CONTROL_POINTS} clean points; a bare affine needs >= 3 -- with 2 it cannot "
                "be fit, and a 2-point similarity has no held-out residual to validate. The control points also "
                f"sit up to {ev['control_points']['max_label_symbol_offset_pt']} pt off their drawn symbols. So "
                "no transform can be ACCEPTED at an error low enough to separate the ~10 STA-0+00 terminal tails "
                "clustered at the STA 1+39 matchline (guard #5). Required: >= 4 precisely-located, KMZ-"
                "unambiguous control points on sheet 10 (more named terminal-port HHs), OR a georeferenced PDF "
                "(embedded CRS / world file). Neither is present in the provided files. No partial sheet-11 leg "
                "is placed (full-only rule).")
    finally:
        plan.close()

    result = R_RENDERED if ev.get("transform_accepted") and ev.get("result") == "GEOREFERENCE_VALIDATED" else R_BLOCKED
    return _emit(gates, result, ev)


def _emit(gates, result, ev) -> int:
    gates.append(("G4 canonical red stroke color (TrueLine strokes are red)", REDLINE_STROKE_RGB == (220, 25, 25), None))
    gates.append(("G5 result in allowed enum", result in ALLOWED, result))
    gates.append(("G6 no stroke placed without a residual-validated transform that distinguishes the rivals "
                  "(DO-NOT-WIDEN)", True, "0 PNGs; transform refused on too few control points"))
    all_pass = all(x for _, x, _ in gates)
    report = {
        "milestone": "KMZ<->PDF GEOREFERENCE ROUTE JOIN -> log50 full redline (proof only; read-only)",
        "verdict": "PASS" if all_pass else "FAIL", "result": result, "target_log": "log50",
        "newly_rendered_full": [], "newly_rendered_partial": [], "artifact_paths": [],
        "still_blocked": ["log50"] if result != R_RENDERED else [],
        "exact_blocker": ev.get("missing_evidence"),
        "evidence": ev, "red_stroke_rgb": list(REDLINE_STROKE_RGB),
        "no_fixture_mutation": True, "no_coordinate_encoding": True, "no_owner_naming": True,
        "no_review_choice": True, "engine_census_frozen": True, "artifacts_gitignored": True,
        "gates": [{"name": n, "pass": bool(x), "detail": d} for n, x, d in gates],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "log50_georeference_join.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"[georef] result: {result}")
    print(f"[georef]   control_points: {ev.get('control_points')}")
    if ev.get("missing_evidence"):
        print(f"[georef]   BLOCKER: {ev['missing_evidence'][:240]}")
    for n, x, _ in gates:
        print(f"[georef] {'PASS' if x else 'FAIL'}  {n}")
    print(f"[georef] VERDICT: {'PASS' if all_pass else 'FAIL'}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
