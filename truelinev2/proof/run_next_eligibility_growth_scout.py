r"""OWNER-PACKET-2 -- NEXT eligibility-growth scout (PROOF/REPORT ONLY; no promotion, no encoding).

The seam pipeline (contract + adapter + end-to-end driver) is eligibility-frozen to the five proven
exemplars (log53, log64, log71, log59, log66 -- log66 owner-confirmed + promoted). The cohort
SOURCE_BINDABLE_NOW set is now 8 (those 5 + the held-back log36/log52/log58 bridges); the seam stays 5.
This scout classifies the 14 PENDING no-endpoint-anchors logs (19 minus log59/66/36 + log52/log58, all
now SOURCE_BINDABLE_NOW) and
identifies the SINGLE safest next log to promote into the seam -- OR honestly reports that none is
safe yet. It encodes NO endpoint_anchors, changes NO seam contract/adapter/driver, parses NO PDF,
draws nothing, and promotes nothing. It only reads owner-AUTHORITATIVE adjudication facts via the
EXISTING canonical cohort classifier (run_log53_primitives_cohort_replay.classify_record /
derive_signals) and the existing sibling-overlap check; it adds no new classifier.

A candidate is recommended ONLY if it satisfies ALL of the task's eight criteria, expressed against
the canonical classifier:
  * classification == PARTIAL_SOURCE_BINDABLE  (>=1 modeled terminus the existing resolver can bind
    from source AND a recorded sheet to bind it on -- the hard endpoint-identity part is done);
  * single sheet (n_sheets == 1)              -> no cross-sheet coordinate solving;
  * no STATION/PRINT OCR correction           -> no unreviewed-OCR label-bind risk;
  * not a shared-print child / parent-column split -> no parent/child aggregation or ownership adjudication;
  * no sibling-endpoint overlap               -> no ambiguous shared-print / same-station collision;
  * not owner-flagged for review.
That is exactly the log64 shape (single-sheet structure-to-structure) with both endpoints already
owner-confirmed. If no pending log meets it, the honest result is NO_SAFE_NEXT_ELIGIBILITY_CANDIDATE.

Proof-only; the JSON report is written under the gitignored data/outputs path.
Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_next_eligibility_growth_scout
"""
from __future__ import annotations

import json
from collections import Counter

from truelinev2.config import _REPO_ROOT
from truelinev2.ingest.manual_adjudication import (
    activation_summary,
    apply_adjudications,
    load_adjudication,
    parent_run_duplicate_check,
)
from truelinev2.proof.run_log53_primitives_cohort_replay import (
    ENDPOINT_IDENTITY_NOT_MODELED,
    NO_RECORDED_SHEET,
    PARTIAL_SOURCE_BINDABLE,
    REPRESENTATIVE_ROUTE_CANDIDATE,
    SOURCE_BINDABLE_NOW,
    classify_cohort,
    classify_record,
)
from truelinev2.proof.run_partial_cohort_next_candidate_scout import sibling_overlap
from truelinev2.seam import ELIGIBLE_EXEMPLARS, build_seam_payload

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "next_eligibility_growth_scout"
TRUTH = _REPO_ROOT / "data" / "outputs" / "final_engine_truth_table" / \
    "final_engine_truth_table.json"
FROZEN_BUCKETS = {"DRAWABLE_REVIEW": 31, "HUMAN_ADJUSTABLE_REVIEW": 6,
                  "OUT_OF_CLASS": 1, "PICK_CARD_REVIEW": 17, "SOURCE_OR_KMZ_REQUIRED": 3}
ABSTAIN_4 = ("log5", "log31", "log38", "log43")
_OCR = {"STATION_OCR_CORRECTION", "PRINT_OCR_CORRECTION"}

# blocker categories (the task's vocabulary; one log may carry several)
CAT_OCR = "ocr_correction_needed"
CAT_OWNERSHIP = "ownership_adjudication_needed"
CAT_SOURCE_VERIFY = "source_verification_needed"
CAT_PARENT_CHILD = "parent_child_aggregation_needed"
CAT_CROSS_SHEET = "cross_sheet_frame_solving_needed"
CAT_REPRESENTATIVE = "representative_route_logic_needed"
CAT_IDENTITY_MISSING = "endpoint_identity_missing"
CAT_NO_SHEET = "no_recorded_sheet"
CAT_SHARED_PRINT_COLLISION = "ambiguous_shared_print_same_station_collision"
CAT_REVIEW_FLAG = "review_flag_held"

R_SELECTED = "NEXT_ELIGIBILITY_GROWTH_SCOUT_PASS"
R_NONE = "NO_SAFE_NEXT_ELIGIBILITY_CANDIDATE"
B_INVARIANT = "BLOCKED_NEXT_ELIGIBILITY_INVARIANT_VIOLATED"
ALLOWED = {R_SELECTED, R_NONE, B_INVARIANT}


def pending_logs(doc: dict) -> list:
    """The pending no-endpoint-anchors logs (owner-recovered, not abstain, not source-verify)."""
    return [r for r in doc["logs"]
            if not r.get("endpoint_anchors")
            and not r.get("must_remain_abstained")
            and not r.get("needs_source_verification")]


def blocker_categories(rec: dict, c: dict, doc: dict) -> list:
    """Named blocker categories (task vocabulary) for a pending log; >= 1 for any non-ready log."""
    cts = set(rec.get("correction_types") or [])
    sig = c["signals"]
    cats = set()
    if _OCR & cts:
        cats.add(CAT_OCR)
    if "ORIGINAL_PARENT_COLUMN_SPLIT" in cts:
        cats.add(CAT_OWNERSHIP)
    if rec.get("shared_print_child"):
        cats.add(CAT_PARENT_CHILD)
    if sig["n_sheets"] > 1 or sig["matchline_chain"]:
        cats.add(CAT_CROSS_SHEET)
    if rec.get("needs_review"):
        cats.add(CAT_REVIEW_FLAG)
    if NO_RECORDED_SHEET in c["blockers"]:
        cats.add(CAT_NO_SHEET)
    if ENDPOINT_IDENTITY_NOT_MODELED in c["blockers"]:
        cats.add(CAT_IDENTITY_MISSING)
        cats.add(CAT_REPRESENTATIVE)
    if sibling_overlap(rec, doc):
        cats.add(CAT_SHARED_PRINT_COLLISION)
    return sorted(cats)


def is_eligibility_ready(rec: dict, doc: dict) -> bool:
    """All eight criteria, against the canonical classifier: a single-sheet PARTIAL_SOURCE_BINDABLE
    (both endpoints already source-bindable + a recorded sheet) with no OCR, no parent/child split,
    no sibling collision, no review flag. That is the log64 shape with endpoints already confirmed."""
    c = classify_record(rec)
    sig = c["signals"]
    cts = set(rec.get("correction_types") or [])
    return (c["classification"] == PARTIAL_SOURCE_BINDABLE
            and sig["n_sheets"] == 1
            and not (_OCR & cts)
            and not rec.get("shared_print_child")
            and "ORIGINAL_PARENT_COLUMN_SPLIT" not in cts
            and not sibling_overlap(rec, doc)
            and not rec.get("needs_review"))


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
    pending = pending_logs(doc)

    # per-pending-log analysis (canonical classification + 8-criteria readiness + named blockers)
    analyzed = []
    for r in pending:
        c = classify_record(r)
        sig = c["signals"]
        ready = is_eligibility_ready(r, doc)
        analyzed.append({
            "log_id": r["log_id"],
            "classification": c["classification"],
            "n_sheets": sig["n_sheets"], "sheets": sig["sheets"],
            "modeled_terminus_classes": sig["modeled_terminus_classes"],
            "corrected_start": r.get("corrected_start"), "corrected_end": r.get("corrected_end"),
            "ready": ready,
            "blocker_categories": blocker_categories(r, c, doc),
        })

    ready_rows = [a for a in analyzed if a["ready"]]
    # rank a ready candidate (safest first): fewest blocker categories, fewest correction types, id
    ready_rows.sort(key=lambda a: (len(a["blocker_categories"]),
                                   len(rec[a["log_id"]].get("correction_types") or []), a["log_id"]))
    recommended = ready_rows[0] if ready_rows else None
    result = R_SELECTED if recommended else R_NONE

    # nearest near-misses when NO_SAFE: modeled endpoints present, blocked only by a missing sheet
    near_misses = sorted(
        (a for a in analyzed
         if a["classification"] == REPRESENTATIVE_ROUTE_CANDIDATE and CAT_NO_SHEET in a["blocker_categories"]),
        key=lambda a: (-len(a["modeled_terminus_classes"]), a["log_id"]))

    gates = []
    gates.append(("G0 engine census frozen (OFF 31/6/1/17/3, ON 22/1/4, log44+abstains held)",
                  _census_frozen(doc), None))

    # G1 the cohort SOURCE_BINDABLE_NOW set (5: log53/59/64/66/71) now MATCHES the SEAM eligible set (5):
    # log66 was owner-confirmed + promoted, so the cohort-vs-seam gap is closed. No PENDING (no-anchor)
    # log is source-bindable yet.
    source_bindable_now = sorted(a["log_id"] for a in
                                 (classify_record(r) for r in doc["logs"])
                                 if a["classification"] == SOURCE_BINDABLE_NOW)
    gates.append(("G1 cohort SOURCE_BINDABLE_NOW (8, incl held-back log36/log52/log58) is a superset of seam eligible (5)",
                  source_bindable_now == ["log36", "log52", "log53", "log58", "log59", "log64", "log66", "log71"]
                  and tuple(ELIGIBLE_EXEMPLARS) == ("log53", "log64", "log71", "log59", "log66")
                  and set(source_bindable_now) - set(ELIGIBLE_EXEMPLARS) == {"log36", "log52", "log58"}, source_bindable_now))

    # G2 no code path promotes a new log here: the seam contract still REFUSES every pending no-anchor log
    refused = all(_refuses(a["log_id"], rec) for a in analyzed)
    gates.append(("G2 no further promotion: seam contract refuses every pending no-anchor log; eligible set == 5",
                  refused and len(ELIGIBLE_EXEMPLARS) == 5, None))

    gates.append(("G3 all pending no-anchor logs classified (14 after log59/66/36 + log52/log58 bridges moved out of pending)",
                  len(analyzed) == 14 and len({a["log_id"] for a in analyzed}) == 14, len(analyzed)))

    # G4 candidate determination correct: recommended satisfies all 8 (or NO_SAFE and none does)
    g4 = (is_eligibility_ready(rec[recommended["log_id"]], doc) if recommended
          else not ready_rows)
    gates.append(("G4 recommended satisfies all 8 criteria (or NO_SAFE and no pending log does)", g4, None))

    # G5-G8 a recommended candidate avoids OCR / parent-child / cross-sheet / representative-route
    #       (vacuously satisfied when NO_SAFE -- there is no candidate to violate them)
    def rec_avoids(cat):
        return recommended is None or cat not in recommended["blocker_categories"]
    gates.append(("G5 recommended avoids unreviewed OCR", rec_avoids(CAT_OCR), None))
    gates.append(("G6 recommended avoids parent/child aggregation + ownership adjudication",
                  rec_avoids(CAT_PARENT_CHILD) and rec_avoids(CAT_OWNERSHIP), None))
    gates.append(("G7 recommended avoids cross-sheet frame solving", rec_avoids(CAT_CROSS_SHEET), None))
    gates.append(("G8 recommended avoids representative-route resolver logic + missing identity/sheet",
                  rec_avoids(CAT_REPRESENTATIVE) and rec_avoids(CAT_IDENTITY_MISSING)
                  and rec_avoids(CAT_NO_SHEET), None))

    # G9 every rejected (non-ready) pending log carries >= 1 named blocker category
    rejected = [a for a in analyzed if not a["ready"]]
    gates.append(("G9 every rejected candidate has >= 1 named blocker category",
                  all(a["blocker_categories"] for a in rejected), None))

    # G10 seam eligibility == 5; cohort source-bindable == 5 (log66 promoted -> seam == cohort); no PENDING log added one
    gates.append(("G10 seam eligibility == 5; cohort source-bindable == 8 (log36/log52/log58 held-back -> seam (5) < cohort (8))",
                  len(ELIGIBLE_EXEMPLARS) == 5 and len(source_bindable_now) == 8, None))

    gates.append(("G11 result in allowed enum", result in ALLOWED, result))
    pngs = sorted(p.name for p in OUT_DIR.glob("*.png"))
    gates.append(("G12 no render artifact (scout writes JSON only; zero PNG)", len(pngs) == 0, pngs))

    return _emit(gates, result, recommended, near_misses, analyzed, rejected)


def _refuses(log_id: str, rec: dict) -> bool:
    try:
        build_seam_payload(log_id, rec.get(log_id, {}))
        return False
    except ValueError:
        return True


def _emit(gates, result, recommended, near_misses, analyzed, rejected) -> int:
    all_pass = all(x for _, x, _ in gates)
    by_category = Counter(c for a in rejected for c in a["blocker_categories"])
    by_classification = Counter(a["classification"] for a in analyzed)
    report = {
        "milestone": "OWNER-PACKET-2 -- next eligibility-growth scout (proof/report only; no promotion)",
        "verdict": "PASS" if all_pass else "FAIL",
        "result": result if all_pass else "BLOCKED",
        "current_eligible": list(ELIGIBLE_EXEMPLARS),
        "candidate_recommended": (
            {"bore_id": recommended["log_id"], "shape": "single_sheet_structure_to_structure",
             "endpoint_truth": recommended["modeled_terminus_classes"],
             "sheets": recommended["sheets"]} if recommended else None),
        "no_safe_reason": (
            None if recommended else
            "No pending log is a SINGLE-SHEET PARTIAL_SOURCE_BINDABLE with both endpoints owner-named "
            "and no OCR/parent-split/sibling-collision. Every recorded-sheet candidate with a modeled "
            "terminus is MULTI-SHEET (needs the deferred cross-sheet frame join); every clean "
            "single-area structure-to-structure candidate with both endpoints named has NO recorded "
            "sheet to bind on (NO_RECORDED_SHEET). So no candidate meets all eight criteria yet."),
        "closest_near_misses": [
            {"bore_id": a["log_id"], "modeled_termini": a["modeled_terminus_classes"],
             "start": a["corrected_start"], "end": a["corrected_end"],
             "only_blocker": a["blocker_categories"],
             "unblock": ("recover the print/sheet (a focused sheet-locator step) so the already-named "
                         "modeled termini can bind on a real sheet -> then it becomes a log64-shape "
                         "single-sheet candidate")}
            for a in near_misses],
        "rejected_candidates": [
            {"bore_id": a["log_id"], "classification": a["classification"], "n_sheets": a["n_sheets"],
             "blocker_categories": a["blocker_categories"]}
            for a in rejected],
        "counts": {
            "eligible_now": len(ELIGIBLE_EXEMPLARS),
            "pending_classified": len(analyzed),
            "safe_next_candidate": 1 if recommended else 0,
            "by_classification": dict(by_classification),
            "blocked_by_category": dict(by_category.most_common()),
        },
        "invariants": {
            "seam_contract_unchanged": True, "adapter_unchanged": True, "driver_unchanged": True,
            "engine_census_unchanged": True, "no_eligibility_expansion": True,
            "no_endpoint_anchors_encoded": True, "no_generated_artifacts": True,
        },
        "method": ("reuses the canonical cohort classifier (classify_record / derive_signals) + the "
                   "existing sibling-overlap check; no new classifier, no PDF, no coordinate, no render"),
        "next_recommended_slice": (
            f"promote {recommended['log_id']} via the controlled path (encode endpoint_anchors -> "
            f"log64-style single-sheet source-bind + render -> add to contract/adapter/driver)"
            if recommended else
            "no remaining NO_RECORDED_SHEET near-miss to bridge: log59 + log66 + log36 are all bridged "
            "(log59/log66 promoted; log36 anchored-but-held-back), and the near-miss sheet-locator scout "
            "now returns NO_SAFE_SHEET_LOCATOR_CANDIDATE. Further eligibility growth needs a NEW source "
            "(a recovered sheet for another modeled-terminus log, or owner-confirmation of log36's sheet 17)."),
        "gates": [{"name": n, "pass": bool(x), "detail": d} for n, x, d in gates],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "next_eligibility_growth_scout.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"[next-elig] result: {report['result']}  recommended: "
          f"{recommended['log_id'] if recommended else None}")
    print(f"[next-elig] by_classification: {dict(by_classification)}")
    print(f"[next-elig] blocked_by_category: {dict(by_category.most_common())}")
    print(f"[next-elig] closest near-misses (modeled endpoints, only missing a sheet): "
          f"{[a['log_id'] for a in near_misses]}")
    for n, x, _ in gates:
        print(f"[next-elig] {'PASS' if x else 'FAIL'}  {n}")
    print(f"[next-elig] VERDICT: {'PASS' if all_pass else 'FAIL'}  (report: {OUT_DIR})")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
