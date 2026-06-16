r"""OWNER-PACKET-2 -- PARTIAL cohort NEXT-CANDIDATE scout (PROOF ONLY; ranking census).

After log64 walked the full controlled path (endpoint identity -> source bind -> contained render),
this ranks the remaining PARTIAL_SOURCE_BINDABLE cohort to pick the SAFEST next log for the same
path. Deterministic + artifact-driven (reads only owner-AUTHORITATIVE adjudication facts via the
existing cohort classifier); no PDF parse, no coordinate, no render, no new resolver, no artifact
mutation. It RANKS and RECOMMENDS; it does not encode anchors, bind, or draw.

Transparent risk tiering (straight from the task's prefer/avoid criteria -- no magic weights):
  * HIGH   if any STATION_OCR_CORRECTION (label-bind risk), OR a same-parent sibling shares a
           non-reset endpoint station (segment-ownership / duplicate ambiguity), OR no modeled
           terminus is owner-indicated.
  * MEDIUM if PRINT_OCR_CORRECTION only, OR the run spans >= 3 sheets (longer matchline chain).
  * LOW    otherwise: no OCR, <= 2 sheets, >= 1 modeled terminus, no sibling overlap.
Rank = (risk tier, sheet count, fewer-modeled-termini last). The rank-1 LOW candidate is the
recommendation. A reset origin "X+XX=0+00" is NOT counted as a shared station (it is a generic
reset, not a unique structure).

Proof-only; the JSON report is written under the gitignored data/outputs path.
Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_partial_cohort_next_candidate_scout
"""
from __future__ import annotations

import json

from truelinev2.config import _REPO_ROOT
from truelinev2.ingest.manual_adjudication import (
    activation_summary,
    apply_adjudications,
    load_adjudication,
    parent_run_duplicate_check,
)
from truelinev2.proof.run_log53_primitives_cohort_replay import (
    PARTIAL_SOURCE_BINDABLE,
    classify_cohort,
    derive_signals,
)

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "partial_cohort_next_candidate_scout"
TRUTH = _REPO_ROOT / "data" / "outputs" / "final_engine_truth_table" / \
    "final_engine_truth_table.json"
FROZEN_BUCKETS = {"DRAWABLE_REVIEW": 31, "HUMAN_ADJUSTABLE_REVIEW": 6,
                  "OUT_OF_CLASS": 1, "PICK_CARD_REVIEW": 17, "SOURCE_OR_KMZ_REQUIRED": 3}
ABSTAIN_4 = ("log5", "log31", "log38", "log43")
# the live PARTIAL set shrinks as bridges are encoded: log64/log71, then the cross-sheet two-leg bridges
# log52 + log58 were promoted to SOURCE_BINDABLE_NOW, leaving these 6.
EXPECTED_PARTIAL = ("log11", "log47", "log48", "log67", "log69", "log70")
PROMOTED_OUT = ("log64", "log71", "log52", "log58")   # bridges encoded -> now SOURCE_BINDABLE_NOW, no longer PARTIAL

RISK_LOW, RISK_MEDIUM, RISK_HIGH = "LOW", "MEDIUM", "HIGH"
_RANK = {RISK_LOW: 0, RISK_MEDIUM: 1, RISK_HIGH: 2}

R_SELECTED = "NEXT_CANDIDATE_SELECTED"
R_NONE = "NO_SAFE_CANDIDATE"
ALLOWED = {R_SELECTED, R_NONE}


def _endpoint_stations(rec: dict) -> set:
    """The record's non-reset endpoint stations (a generic '...=0+00' reset is excluded -- it is
    not a unique structure)."""
    out = set()
    for s in (rec.get("corrected_start"), rec.get("corrected_end")):
        if s and s != "0+00":
            out.add(s)
    return out


def sibling_overlap(rec: dict, doc: dict) -> list:
    """Other logs under the SAME parent that share a non-reset endpoint station with ``rec``
    (segment-ownership / duplicate-redline ambiguity). Pure."""
    parent = rec.get("parent")
    if not parent:
        return []
    mine = _endpoint_stations(rec)
    hits = []
    for other in doc.get("logs", []):
        if other.get("log_id") == rec.get("log_id") or other.get("parent") != parent:
            continue
        if mine & _endpoint_stations(other):
            hits.append(other.get("log_id"))
    return sorted(hits)


def scout_record(rec: dict, doc: dict) -> dict:
    """Risk-tier + evidence facts for one PARTIAL candidate. Pure; artifact-only."""
    sig = derive_signals(rec)
    cts = set(rec.get("correction_types") or [])
    station_ocr = "STATION_OCR_CORRECTION" in cts
    print_ocr = "PRINT_OCR_CORRECTION" in cts
    overlap = sibling_overlap(rec, doc)
    n_sheets = sig["n_sheets"]
    modeled = sig["modeled_terminus_classes"]

    if station_ocr or overlap or not modeled:
        risk = RISK_HIGH
    elif print_ocr or n_sheets >= 3:
        risk = RISK_MEDIUM
    else:
        risk = RISK_LOW

    blocker = (
        "STATION_OCR_CORRECTION (label-bind risk)" if station_ocr else
        f"sibling-endpoint overlap with {overlap} (segment-ownership ambiguity)" if overlap else
        "no modeled terminus owner-indicated" if not modeled else
        "PRINT_OCR_CORRECTION (sheet-number correction)" if print_ocr else
        f"spans {n_sheets} sheets (longer matchline chain)" if n_sheets >= 3 else
        "unmodeled-class start (reset boundary) -> only the modeled-terminus leg is clean"
        if len(modeled) < 2 else "none")
    return {
        "log_id": rec.get("log_id"),
        "n_sheets": n_sheets,
        "sheets": sig["sheets"],
        "modeled_termini": modeled,
        "station_ocr": station_ocr,
        "print_ocr": print_ocr,
        "sibling_overlap": overlap,
        "risk": risk,
        "main_blocker": blocker,
    }


def rank_partial_cohort(doc: dict) -> list:
    """Ranked PARTIAL candidates (safest first). Pure; artifact-only."""
    rec = {r["log_id"]: r for r in doc["logs"]}
    partial_ids = [r["log_id"] for r in classify_cohort(doc)
                   if r["classification"] == PARTIAL_SOURCE_BINDABLE]
    rows = [scout_record(rec[i], doc) for i in partial_ids]
    rows.sort(key=lambda r: (_RANK[r["risk"]], r["n_sheets"], -len(r["modeled_termini"]), r["log_id"]))
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return rows


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
    rows = rank_partial_cohort(doc)
    low = [r for r in rows if r["risk"] == RISK_LOW]
    recommended = rows[0] if (rows and rows[0]["risk"] == RISK_LOW) else None
    result = R_SELECTED if recommended else R_NONE

    gates = []
    gates.append(("G1 engine census frozen (OFF 31/6/1/17/3, ON 22/1/4, log44+abstains held)",
                  _census_frozen(doc), None))
    l53s = (rec["log53"].get("endpoint_anchors") or {}).get("start") or {}
    l64s = (rec["log64"].get("endpoint_anchors") or {}).get("start") or {}
    gates.append(("G2 log53 + log64 prior behavior preserved (anchors unchanged)",
                  l53s.get("structure_class") == "nextlink_hh"
                  and l64s.get("structure_class") == "installer_hh", None))
    partial_ids = {r["log_id"] for r in rows}
    safest_remaining = rows[0] if rows else None   # top-ranked even when not LOW (informational)
    gates.append(("G3 PARTIAL cohort is the expected 8 (log64+log71 promoted out)",
                  tuple(sorted(partial_ids)) == EXPECTED_PARTIAL, len(rows)))
    gates.append(("G4 no LOW-risk candidate remains (the two clean wins log64+log71 are encoded)",
                  len(low) == 0 and recommended is None, [r["log_id"] for r in low]))
    gates.append(("G5 result NO_SAFE_CANDIDATE; promoted log64+log71 are no longer PARTIAL",
                  result == R_NONE and not (set(PROMOTED_OUT) & partial_ids), sorted(partial_ids)))
    gates.append(("G6 log69/log70 flagged HIGH for sibling-endpoint overlap (not picked)",
                  all(next(r for r in rows if r["log_id"] == l)["risk"] == RISK_HIGH
                      and next(r for r in rows if r["log_id"] == l)["sibling_overlap"]
                      for l in ("log69", "log70")), None))
    gates.append(("G7 result in allowed enum", result in ALLOWED, result))

    pngs = sorted(p.name for p in OUT_DIR.glob("*.png"))
    gates.append(("G8 zero PNG / zero stroke (no render lane)", len(pngs) == 0, {"pngs": pngs}))
    all_pass = all(x for _, x, _ in gates)

    next_slice = (
        f"NO LOW-risk PARTIAL remains after the log64 + log71 wins. The safest REMAINING is "
        f"{safest_remaining['log_id']} ({safest_remaining['risk']}: {safest_remaining['main_blocker']}), "
        f"but it -- and the rest -- need a MEDIUM+-risk decision (OCR / 3-sheet / sibling-overlap), "
        f"not an automatic safe pick. Re-scope before picking the next candidate."
        if (recommended is None and safest_remaining) else
        (f"Implement {recommended['log_id']} via the controlled path." if recommended else "none"))
    report = {
        "milestone": "OWNER-PACKET-2 -- PARTIAL cohort next-candidate scout (proof only; ranking)",
        "verdict": "PASS" if all_pass else "FAIL",
        "result": result,
        "recommended_candidate": recommended["log_id"] if recommended else None,
        "safest_remaining": (
            {"log_id": safest_remaining["log_id"], "risk": safest_remaining["risk"],
             "main_blocker": safest_remaining["main_blocker"]} if safest_remaining else None),
        "promoted_out_since_first_scout": list(PROMOTED_OUT),
        "recommended_next_slice": next_slice,
        "ranked": rows,
        "risk_tiers": {t: [r["log_id"] for r in rows if r["risk"] == t]
                       for t in (RISK_LOW, RISK_MEDIUM, RISK_HIGH)},
        "no_pdf_parse": True, "no_render": True, "no_invented_coordinates": True,
        "no_anchor_encoding": True, "no_artifact_mutation": True,
        "gates": [{"name": n, "pass": bool(x), "detail": d} for n, x, d in gates],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "partial_cohort_next_candidate_scout.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"[partial-scout] result: {result}  recommended: {report['recommended_candidate']}")
    for r in rows:
        print(f"[partial-scout]   #{r['rank']} {r['log_id']:>6} | {r['risk']:<6} | "
              f"sheets={r['n_sheets']} termini={','.join(r['modeled_termini']) or '-'} | "
              f"{r['main_blocker']}")
    for n, x, _ in gates:
        print(f"[partial-scout] {'PASS' if x else 'FAIL'}  {n}")
    print(f"[partial-scout] VERDICT: {'PASS' if all_pass else 'FAIL'}  (report: {OUT_DIR})")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
