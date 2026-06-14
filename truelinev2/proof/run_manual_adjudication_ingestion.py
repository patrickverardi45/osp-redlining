r"""OWNER-PACKET-2 -- manual adjudication ingestion proof (read-only).

Verifies the owner-reviewed source-correction artifact + screenshot evidence index:
the prior RECON-3 ``ZERO_YIELD_OWNER_SOURCE_REQUIRED`` / "11 of 11 owner-source-
required" conclusion was materially wrong for this dataset. Manual source review
(OCR/print corrections, station resets, matchline chains, HH-HH annotations, leader
lines, direct bore callouts, original parent/child columns) reclassifies 23 of the
27 problem logs as recoverable/correct-as-drawn and keeps exactly 4 genuinely
abstained.

This proves the ADJUDICATION-LAYER reclassification (structured corrected evidence
the engine can consume + re-run). It does NOT re-run the geometry engine or move the
frozen M8.27 product census -- wiring the corrections into ``read_brenham_borelog``
is a separately-authorized ACTIVATION step. Read-only; writes one gitignored JSON.
No PDF parse, no corpus read.
"""
from __future__ import annotations

import json
from pathlib import Path

from truelinev2.config import _REPO_ROOT
from truelinev2.ingest.manual_adjudication import (
    DEFAULT_ARTIFACT,
    DEFAULT_EVIDENCE_INDEX,
    RECOVERABLE_STATUS,
    load_adjudication,
    load_evidence_index,
    parent_run_duplicate_check,
    resolve,
    summarize,
    validate_adjudication,
)

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "manual_adjudication_ingestion"
RECON2B = _REPO_ROOT / "data" / "outputs" / "parent_child_print_assignment_phase0" / \
    "parent_child_print_assignment_phase0.json"
TRUTH = _REPO_ROOT / "data" / "outputs" / "final_engine_truth_table" / \
    "final_engine_truth_table.json"

EXPECTED_27 = {
    "log6", "log63", "log64", "log46", "log47", "log52", "log53", "log58", "log67",
    "log70", "log71", "log11", "log12", "log29", "log36", "log41", "log44", "log48",
    "log54", "log59", "log66", "log68", "log69",          # 23 recoverable
    "log5", "log31", "log38", "log43",                     # 4 abstain
}
SHARED_PRINT_11 = {
    "log6", "log46", "log47", "log52", "log53", "log58", "log63", "log64", "log67",
    "log70", "log71",
}
ABSTAIN_4 = {"log5", "log31", "log38", "log43"}
PRINT_OCR_1720 = ("log67", "log68", "log69", "log70")


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    doc = load_adjudication(DEFAULT_ARTIFACT)
    disp = resolve(doc)
    summary = summarize(doc)
    idx = load_evidence_index(DEFAULT_EVIDENCE_INDEX)

    gates = []

    # G1 -- artifact parses + validates (fail-closed structural validation)
    errs = validate_adjudication(doc)
    gates.append(("G1 artifact parses and validates", not errs, errs[:8]))

    # G2 -- all 27 logs represented exactly once, exactly the expected set
    ids = [r["log_id"] for r in doc["logs"]]
    g2 = len(ids) == 27 and set(ids) == EXPECTED_27 and len(set(ids)) == len(ids)
    gates.append(("G2 all 27 logs present exactly once", g2,
                  {"n": len(ids), "missing": sorted(EXPECTED_27 - set(ids)),
                   "extra": sorted(set(ids) - EXPECTED_27)}))

    # G3 -- the 23 recoverable/correct-as-drawn are no longer owner-source-required
    recoverable = [r for r in doc["logs"] if r["status"] in RECOVERABLE_STATUS]
    g3 = (len(recoverable) == 23
          and all(not r["must_remain_abstained"] for r in recoverable)
          and all(r.get("original_recon3_classification")
                  != "OWNER_SOURCE_REQUIRED_SHARED_PRINT_AMBIGUITY" for r in recoverable))
    gates.append(("G3 23 recoverable, none owner-source-required", g3,
                  {"recoverable": len(recoverable)}))

    # G4 -- the 4 no-good logs stay abstained
    g4 = all(
        d.status == "ABSTAIN_NO_SAFE_SOURCE" and d.must_remain_abstained
        and not d.allowed_to_draw and not d.correction_types
        for lid in ABSTAIN_4 for d in [disp[lid]]
    ) and {r["log_id"] for r in doc["logs"]
           if r["status"] == "ABSTAIN_NO_SAFE_SOURCE"} == ABSTAIN_4
    gates.append(("G4 the 4 no-good logs stay abstained", g4, sorted(ABSTAIN_4)))

    # G5 -- the 11 shared-print children accounted for, all recoverable, none owner-source
    shared = {r["log_id"] for r in doc["logs"] if r.get("shared_print_child")}
    g5 = (shared == SHARED_PRINT_11
          and all(disp[l].status in RECOVERABLE_STATUS for l in SHARED_PRINT_11)
          and summary["shared_print_owner_source_required_after_review"] == 0)
    gates.append(("G5 11 shared-print children all recovered (0 owner-source)", g5,
                  {"shared": sorted(shared),
                   "still_owner_source": summary["shared_print_owner_source_required_after_review"]}))

    # G6 -- log68 uses corrected STA 5+03 -> 6+79, NOT the 4+54 (log69/log70) segment
    l68 = disp["log68"]
    g6 = (l68.corrected_start == "5+03" and l68.corrected_end == "6+79"
          and "4+54" not in (l68.corrected_start, l68.corrected_end))
    gates.append(("G6 log68 = STA 5+03->6+79 (never 4+54)", g6,
                  {"start": l68.corrected_start, "end": l68.corrected_end}))

    # G7 -- log67/68/69/70 corrected print is 17,20 (not OCR 19,20)
    g7 = all(disp[l].corrected_prints == (17, 20) for l in PRINT_OCR_1720)
    gates.append(("G7 log67/68/69/70 corrected print = 17,20", g7,
                  {l: disp[l].corrected_prints for l in PRINT_OCR_1720}))

    # G8 -- log41 is correct-as-drawn / review-approved
    g8 = disp["log41"].status == "CORRECT_AS_DRAWN"
    gates.append(("G8 log41 = CORRECT_AS_DRAWN", g8, disp["log41"].status))

    # G9 -- no parent/child duplicate overlapping redline
    dup = parent_run_duplicate_check(doc)
    gates.append(("G9 no parent/child duplicate overlapping redline", not dup, dup))

    # G10 -- screenshot evidence index present, tied to real logs, covers 47
    if idx is None:
        g10, d10 = False, "evidence index missing"
    else:
        shots = idx.get("screenshots", [])
        cand = {s.get("candidate_log") for s in shots} - {None}
        bylog = set(idx.get("by_log", {}).keys())
        clear = set(idx.get("coverage", {}).get("logs_with_clear_support", []))
        g10 = (len(shots) == 27 + 20  # 47 screenshots
               and cand <= EXPECTED_27
               and bylog <= EXPECTED_27
               and clear <= {r["log_id"] for r in recoverable})
        d10 = {"screenshots": len(shots), "candidate_logs_valid": cand <= EXPECTED_27,
               "by_log_valid": bylog <= EXPECTED_27,
               "clear_all_recoverable": clear <= {r["log_id"] for r in recoverable}}
    gates.append(("G10 evidence index covers 47, tied to real logs", g10, d10))

    # G11 -- computed summary matches the banked expected_summary
    exp = doc.get("expected_summary", {})
    g11 = (summary["original_problem_logs"] == exp.get("original_problem_logs") == 27
           and summary["recoverable_or_correct_as_drawn"]
           == exp.get("recoverable_or_correct_as_drawn") == 23
           and summary["valid_abstain_no_good"] == exp.get("valid_abstain_no_good") == 4
           and summary["active_unknowns"] == exp.get("active_unknowns") == 0
           and summary["shared_print_owner_source_required_after_review"]
           == exp.get("shared_print_owner_source_required_after_review") == 0)
    gates.append(("G11 summary == banked 27/23/4/0/0", g11, summary))

    # G12 -- cross-check the MOVEMENT against the prior RECON-2 Part B + M8.27 truth table
    #        (proves these were genuinely in the false owner-source / non-drawable buckets)
    cross = {"recon2b_present": RECON2B.is_file(), "truth_present": TRUTH.is_file()}
    g12 = True
    if RECON2B.is_file():
        r2 = {c["child"]: c for c in json.loads(RECON2B.read_text(encoding="utf-8"))["children"]}
        # every shared-print-11 child WAS UNASSIGNABLE_SHARED_PRINT_AMBIGUITY in RECON-2 Part B
        was_ambig = {l for l in SHARED_PRINT_11
                     if r2.get(l, {}).get("classification") == "UNASSIGNABLE_SHARED_PRINT_AMBIGUITY"}
        cross["recon2b_shared_print_ambiguous"] = sorted(was_ambig)
        g12 = g12 and (was_ambig == SHARED_PRINT_11)
    if TRUTH.is_file():
        rows = {r["bore_id"]: r for r in json.loads(TRUTH.read_text(encoding="utf-8"))["rows"]}
        # all 27 were NON-DRAWABLE in the frozen M8.27 census (i.e., truly "problem" logs)
        non_drawable = {l for l in EXPECTED_27
                        if rows.get(l, {}).get("completion_bucket") != "DRAWABLE_REVIEW"}
        cross["m827_non_drawable_of_27"] = len(non_drawable)
        g12 = g12 and (len(non_drawable) == 27)
    gates.append(("G12 movement cross-check vs RECON-2B + M8.27", g12, cross))

    all_pass = all(g for _, g, _ in gates)
    report = {
        "milestone": "OWNER-PACKET-2 -- manual adjudication ingestion proof",
        "verdict": "PASS" if all_pass else "FAIL",
        "engine_head": doc.get("engine_head"),
        "artifact": str(DEFAULT_ARTIFACT),
        "evidence_index": str(DEFAULT_EVIDENCE_INDEX),
        "summary": summary,
        "supersedes": "RECON-3 ZERO_YIELD_OWNER_SOURCE_REQUIRED / OWNER-PACKET-2 '11 of 11'",
        "frozen_census_untouched": True,
        "activation_followon": "wire corrected stations/prints into read_brenham_borelog (separately authorized; not done here)",
        "gates": [{"name": n, "pass": bool(g), "detail": d} for n, g, d in gates],
    }
    (OUT_DIR / "manual_adjudication_ingestion.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8")

    print("[owner-packet-2] summary:", summary)
    for n, g, d in gates:
        print(f"[owner-packet-2] {'PASS' if g else 'FAIL'}  {n}")
    print(f"[owner-packet-2] VERDICT: {'PASS' if all_pass else 'FAIL'}  (report: {OUT_DIR})")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
