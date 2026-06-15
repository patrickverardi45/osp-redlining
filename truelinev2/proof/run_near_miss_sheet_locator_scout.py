r"""OWNER-PACKET-2 -- near-miss SHEET-LOCATOR scout (PROOF/REPORT ONLY; no encoding, no promotion).

The next-eligibility scout reported NO_SAFE_NEXT_ELIGIBILITY_CANDIDATE with three near-misses blocked
by a missing recorded sheet: log59 (installer_hh -> flower_pot), log66 (installer_hh <-> nextlink_hh),
log36 (installer_hh <-> installer_hh). log59 (sheet 21, owner-confirmed + promoted) and log66 (sheet 10,
source-recovered bridge) have since been bridged -> both SOURCE_BINDABLE_NOW, so this scout inspects the
REMAINING near-miss (log36) and RECOVERS its source sheet from committed/source evidence via a CONTAINED,
read-only PDF probe -- it encodes NO endpoint_anchors, promotes NO log, changes NO seam contract/adapter/
driver, draws nothing, and writes no PNG. (Current recommendation: log36 -> sheet 17.)

Recovery method (source-backed, NOT length-only, NOT a guess): for each log, find the plan sheet(s)
that print its owner-reviewed 'HH - HH = <span>' annotation, then RE-BIND BOTH owner-named modeled
endpoints (resolve_structure_position / resolve_nextlink_hh_callout) on those sheets. The sheet is
recovered iff EXACTLY ONE sheet both prints the footage AND binds both named endpoints; where the two
endpoints share a station frame, their station span must also equal the printed footage (internal
consistency). A footage match alone is never sufficient (length-only is forbidden).

A log is recommended for a later endpoint-anchor bridge slice only when its sheet is uniquely
recovered, both endpoints are owner-named modeled classes, it is single-sheet (no cross-sheet frame
solving), not a shared-print parent/child split, needs no representative-route resolver, and carries
no unreviewed OCR -- i.e. the proven log64 single-sheet shape (or a tiny declared variant). The
recovered sheet is SOURCE-RESOLVED; the later slice still presents it for owner confirmation (the
log71 precedent) before encoding. If none qualifies, the honest result is NO_SAFE_SHEET_LOCATOR_CANDIDATE.

Proof-only; the JSON report is written under the gitignored data/outputs path.
Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_near_miss_sheet_locator_scout
"""
from __future__ import annotations

import json
import os
import re

from truelinev2.config import _REPO_ROOT
from truelinev2.extract.registry import select_dialect
from truelinev2.extract.structure_position import (
    BRENHAM_STRUCTURE_LAYERS,
    POSITION_BOUND,
    resolve_nextlink_hh_callout,
    resolve_structure_position,
)
from truelinev2.ingest.manual_adjudication import (
    activation_summary,
    apply_adjudications,
    load_adjudication,
    parent_run_duplicate_check,
)
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.proof.run_brenham_corpus import EXPECTED_COUNT, PDF, enumerate_corpus
from truelinev2.proof.run_log53_primitives_cohort_replay import (
    NO_RECORDED_SHEET,
    REPRESENTATIVE_ROUTE_CANDIDATE,
    RESET_ORIGIN_FRAME_TRANSLATION,
    classify_record,
)
from truelinev2.proof.run_reviewer_service_contract import resolve_corpus
from truelinev2.seam import ELIGIBLE_EXEMPLARS, build_seam_payload
from truelinev2.stations import parse_station

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "near_miss_sheet_locator_scout"
TRUTH = _REPO_ROOT / "data" / "outputs" / "final_engine_truth_table" / \
    "final_engine_truth_table.json"
FROZEN_BUCKETS = {"DRAWABLE_REVIEW": 31, "HUMAN_ADJUSTABLE_REVIEW": 6,
                  "OUT_OF_CLASS": 1, "PICK_CARD_REVIEW": 17, "SOURCE_OR_KMZ_REQUIRED": 3}
ABSTAIN_4 = ("log5", "log31", "log38", "log43")
# log59 + log66 have been bridged (their slices: log59 sheet 21 owner-confirmed + promoted; log66 sheet
# 10 source-recovered bridge) -> both are SOURCE_BINDABLE_NOW and no longer NO_RECORDED_SHEET near-misses.
# The scout inspects the REMAINING near-miss (log36); the bridged recoveries live in their bridge slices.
BRIDGED_OUT = ("log59", "log66")
NEAR_MISSES = ("log36",)
SPAN_TOL = 0.5

# near-miss endpoint signatures, read from the owner-reviewed evidence_notes (identity-level facts;
# the scout CONFIRMS the tokens appear in owner_review, then probes the PDF to RECOVER the sheet).
# 'struct' endpoints bind via resolve_structure_position; 'nextlink' via resolve_nextlink_hh_callout.
NEAR_MISS_SIG = {
    "log36": {"shape": "single_sheet_structure_to_structure_variant_installer_to_installer",
              "start": {"binder": "struct", "cls": "installer_hh", "label": "0+56=0+00", "ctx": ()},
              "end": {"binder": "struct", "cls": "installer_hh", "label": "1+45=0+00", "ctx": ()},
              "footage": 89, "span": ("0+56", "1+45")},
}

R_PASS = "SHEET_LOCATOR_SCOUT_PASS"
R_NONE = "NO_SAFE_SHEET_LOCATOR_CANDIDATE"
B_INVARIANT = "BLOCKED_SHEET_LOCATOR_INVARIANT_VIOLATED"
ALLOWED = {R_PASS, R_NONE, B_INVARIANT}


def span_consistent(span, footage: int, tol: float = SPAN_TOL) -> bool:
    """The two same-frame endpoint stations are exactly ``footage`` apart (internal source check)."""
    if span is None:
        return True   # different reset frames -> no same-frame span check (footage+bind only)
    a, b = parse_station(span[0]), parse_station(span[1])
    return abs(abs(b - a) - footage) <= tol


def _bind(plan, off, sheet, spec):
    words, draw = plan.words(sheet, off), plan.line_items(sheet, off)
    if spec["binder"] == "nextlink":
        v = resolve_nextlink_hh_callout(station_sta=spec["sta"], words=words, drawings=draw,
                                        callout_layer="ANNOTATION", symbol_layer="NEXTLINK")
    else:
        v = resolve_structure_position(label_text=spec["label"], structure_class=spec["cls"],
                                       words=words, drawings=draw, layer_table=BRENHAM_STRUCTURE_LAYERS,
                                       context_texts=tuple(spec.get("ctx", ())))
    return v.result == POSITION_BOUND and bool(v.symbol_xy)


def footage_sheets(plan, off, footage: int) -> list:
    """Plan sheets that print 'HH - HH = <footage>' (the owner-reviewed annotation). Read-only."""
    pat = re.compile(rf"HH\s*[-_]?\s*HH\s*=\s*{footage}(?!\d)", re.I)
    out = []
    for sheet in range(1, plan.page_count + 1):
        try:
            if any(pat.search(ln) for ln in plan.lines(sheet, off)):
                out.append(sheet)
        except Exception:
            continue
    return out


def recover_sheet(plan, off, sig: dict) -> dict:
    """Recover the source sheet: the UNIQUE sheet that prints the HH-HH footage AND binds BOTH named
    endpoints. Footage alone is never enough (length-only is forbidden). Returns evidence + the
    recovered sheet (or None when zero or >1 such sheets exist -> not safely recoverable)."""
    fsheets = footage_sheets(plan, off, sig["footage"])
    both_bound = []
    detail = {}
    for sheet in fsheets:
        s_ok = _bind(plan, off, sheet, sig["start"])
        e_ok = _bind(plan, off, sheet, sig["end"])
        detail[sheet] = {"start_bound": s_ok, "end_bound": e_ok}
        if s_ok and e_ok:
            both_bound.append(sheet)
    unique = len(both_bound) == 1
    return {
        "footage_sheets": fsheets,
        "bind_detail": detail,
        "both_bound_sheets": both_bound,
        "span_consistent": span_consistent(sig["span"], sig["footage"]),
        "recovered_sheet": (both_bound[0] if unique else None),
        "uniquely_recovered": unique and span_consistent(sig["span"], sig["footage"]),
    }


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


def _refuses(log_id: str, rec: dict) -> bool:
    try:
        build_seam_payload(log_id, rec.get(log_id, {}))
        return False
    except ValueError:
        return True


def _safety_rank(lid: str, rec: dict) -> tuple:
    """Lower is safer: the exact log64 shape (installer->flower_pot) first, then a clean non-reset
    start, then no shared-print station-number collision, then id."""
    sig = NEAR_MISS_SIG[lid]
    exact_log64 = 0 if sig["shape"] == "single_sheet_structure_to_structure" else 1
    reset_start = 1 if str(sig["start"].get("label", "")).endswith("=0+00") else 0
    # a start station whose reset token is shared by another log on the recovered sheet is riskier
    shared_reset = 1 if lid == "log36" else 0   # 0+56=0+00 collides in number with log6/log63 resets
    return (exact_log64, reset_start, shared_reset, lid)


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for stale in OUT_DIR.glob("*.png"):
        stale.unlink()

    doc = load_adjudication()
    rec = {r["log_id"]: r for r in doc["logs"]}
    gates = []

    gates.append(("G0 engine census frozen (OFF 31/6/1/17/3, ON 22/1/4, log44+abstains held)",
                  _census_frozen(doc), None))

    # G1 seam eligible == cohort SOURCE_BINDABLE_NOW (4): log59 owner-confirmed + promoted
    source_bindable_now = sorted(c["log_id"] for c in (classify_record(r) for r in doc["logs"])
                                 if c["classification"] == "SOURCE_BINDABLE_NOW")
    gates.append(("G1 seam eligible == 4 (log53/64/71/59); cohort SOURCE_BINDABLE_NOW == 5 (+log66 bridged, not promoted)",
                  source_bindable_now == ["log53", "log59", "log64", "log66", "log71"]
                  and tuple(ELIGIBLE_EXEMPLARS) == ("log53", "log64", "log71", "log59"), source_bindable_now))

    # G2 inspects the REMAINING NO_RECORDED_SHEET near-miss (log59 + log66 already bridged out)
    canonical_near = sorted(
        r["log_id"] for r in doc["logs"]
        if classify_record(r)["classification"] == REPRESENTATIVE_ROUTE_CANDIDATE
        and NO_RECORDED_SHEET in classify_record(r)["blockers"])
    bridged_ok = all(classify_record(rec[l])["classification"] == "SOURCE_BINDABLE_NOW" for l in BRIDGED_OUT)
    gates.append(("G2 scout inspects the remaining NO_RECORDED_SHEET near-miss (log36; log59+log66 bridged out)",
                  canonical_near == sorted(NEAR_MISSES) == ["log36"] and bridged_ok, canonical_near))

    # G3 no promotion HERE: the seam contract refuses log36 + the bridged-not-promoted log66; log59 is
    # seam-eligible (owner-confirmed + promoted in its own slice -- this scout promotes nothing).
    gates.append(("G3 scout promotes no log (seam refuses log36 + bridged-not-promoted log66; log59 promoted; eligible == 4)",
                  all(_refuses(l, rec) for l in (*NEAR_MISSES, "log66"))
                  and not _refuses("log59", rec)
                  and len(ELIGIBLE_EXEMPLARS) == 4, None))

    # G4 the inspected near-miss (log36) is still un-anchored + blank sheet; the bridged-out logs
    # (log59 owner-confirmed sheet 21; log66 source-recovered sheet 10) carry endpoint_anchors.
    gates.append(("G4 inspected near-miss (log36) still un-anchored + blank sheet; bridged-out logs (log59/log66) anchored",
                  all(not rec[l].get("endpoint_anchors") and not rec[l].get("corrected_sheets")
                      for l in NEAR_MISSES)
                  and all(rec[l].get("endpoint_anchors") for l in BRIDGED_OUT), None))

    # ---- the contained, read-only PDF recovery probe ---------------------------
    recoveries = {}
    if not os.path.isfile(PDF):
        gates.append(("G5 plan PDF + corpus present", False, f"missing {PDF}"))
        return _emit(gates, B_INVARIANT, None, recoveries, rec)
    corpus_dir, _ = resolve_corpus()
    corpus = {p.stem: p for p in enumerate_corpus(corpus_dir)} if os.path.isdir(corpus_dir) else {}
    gates.append(("G5 plan PDF + corpus present",
                  os.path.isfile(PDF) and len(corpus) == EXPECTED_COUNT,
                  {"pdf": os.path.isfile(PDF), "corpus": len(corpus)}))

    plan = PlanPdf(PDF)
    try:
        offset = select_dialect(plan).calibrate(plan, 13)
        for lid in NEAR_MISSES:
            recoveries[lid] = recover_sheet(plan, offset, NEAR_MISS_SIG[lid])
    finally:
        plan.close()

    # A recommendable candidate uniquely recovers its sheet AND its remaining classifier blockers are
    # all SURMOUNTABLE by the proven log64-style single-sheet bind: NO_RECORDED_SHEET (recovered here)
    # and RESET_ORIGIN_FRAME_TRANSLATION (log64's own start was a reset origin '3+69=0+00' and bound
    # via its reset-token label -- single-sheet, not cross-sheet, not a representative-route resolver).
    # Anything else (identity-not-modeled, multiple-reverse-paths, ...) would need machinery we forbid.
    surmountable = {NO_RECORDED_SHEET, RESET_ORIGIN_FRAME_TRANSLATION}
    recoverable = [lid for lid in NEAR_MISSES
                   if recoveries[lid]["uniquely_recovered"]
                   and set(classify_record(rec[lid])["blockers"]) <= surmountable]
    recoverable.sort(key=lambda l: _safety_rank(l, rec))
    recommended = recoverable[0] if recoverable else None
    result = R_PASS if recommended else R_NONE

    gates.append(("G6 recommended (if any) has both endpoint identities known (modeled classes)",
                  recommended is None or (
                      NEAR_MISS_SIG[recommended]["start"].get("cls") in
                      (set(BRENHAM_STRUCTURE_LAYERS) | {"nextlink_hh"})
                      and NEAR_MISS_SIG[recommended]["end"].get("cls") in
                      (set(BRENHAM_STRUCTURE_LAYERS) | {"nextlink_hh"})), None))
    gates.append(("G7 recommended (if any) has a UNIQUE source-recovered sheet (footage + both binds + span)",
                  recommended is None or recoveries[recommended]["uniquely_recovered"],
                  (recoveries.get(recommended) or {}).get("recovered_sheet") if recommended else None))
    gates.append(("G8 recommended (if any) avoids cross-sheet (single recovered sheet)",
                  recommended is None or isinstance(recoveries[recommended]["recovered_sheet"], int), None))
    gates.append(("G9 recommended (if any) avoids parent/child aggregation (not a shared-print child)",
                  recommended is None or not rec[recommended].get("shared_print_child"), None))
    gates.append(("G10 recommended (if any) avoids representative-route logic (blockers surmountable: sheet + reset-origin)",
                  recommended is None
                  or set(classify_record(rec[recommended])["blockers"]) <= surmountable,
                  (classify_record(rec[recommended])["blockers"] if recommended else None)))
    gates.append(("G11 recommended (if any) avoids unreviewed OCR",
                  recommended is None or not ({"STATION_OCR_CORRECTION", "PRINT_OCR_CORRECTION"}
                                              & set(rec[recommended].get("correction_types") or [])), None))

    # G12 every non-recommended near-miss carries a named reason/category
    rejected = {lid: _reject_reason(lid, recoveries[lid], rec[lid]) for lid in NEAR_MISSES if lid != recommended}
    gates.append(("G12 every non-recommended near-miss has a named reason/blocker category",
                  all(v["blocker_category"] for v in rejected.values()), None))

    gates.append(("G13 result in allowed enum", result in ALLOWED, result))
    pngs = sorted(p.name for p in OUT_DIR.glob("*.png"))
    gates.append(("G14 no render artifact (scout writes JSON only; zero PNG)", len(pngs) == 0, pngs))

    return _emit(gates, result, recommended, recoveries, rec, rejected)


def _reject_reason(lid: str, rcv: dict, record: dict) -> dict:
    if not rcv.get("uniquely_recovered"):
        cat = ("sheet_not_uniquely_recoverable"
               if not rcv.get("recovered_sheet") else "span_footage_inconsistent")
        reason = (f"no unique sheet both prints HH-HH={NEAR_MISS_SIG[lid]['footage']}' and binds both "
                  f"endpoints (footage sheets {rcv.get('footage_sheets')}, both-bound "
                  f"{rcv.get('both_bound_sheets')})")
        return {"blocker_category": cat, "reason": reason, "recovered_sheet": rcv.get("recovered_sheet")}
    # recoverable but ranked behind the recommendation (a viable later candidate, not hard-blocked)
    extra = (" + 0+56=0+00 reset-station number collision with log6/log63 (shared-print resets)"
             if lid == "log36" else "")
    return {"blocker_category": "recoverable_but_deferred_lower_priority_variant",
            "reason": (f"sheet {rcv['recovered_sheet']} source-recovered, but a farther variant from "
                       f"the proven log64 installer->flower_pot shape{extra}; defer behind the pick"),
            "recovered_sheet": rcv.get("recovered_sheet")}


def _emit(gates, result, recommended, recoveries, rec, rejected=None) -> int:
    rejected = rejected or {}
    all_pass = all(x for _, x, _ in gates)
    sig = NEAR_MISS_SIG.get(recommended) if recommended else None
    report = {
        "milestone": "OWNER-PACKET-2 -- near-miss sheet-locator scout (proof/report only; no encoding, no promotion)",
        "verdict": "PASS" if all_pass else "FAIL",
        "result": result if all_pass else "BLOCKED",
        "current_eligible": list(ELIGIBLE_EXEMPLARS),
        "near_misses_inspected": list(NEAR_MISSES),
        "recommended_candidate": ({
            "bore_id": recommended,
            "recovered_sheet": recoveries[recommended]["recovered_sheet"],
            "endpoint_identities": {"start": sig["start"].get("cls"), "end": sig["end"].get("cls")},
            "source_evidence": (
                f"sheet {recoveries[recommended]['recovered_sheet']} is the UNIQUE sheet printing "
                f"HH-HH={sig['footage']}' AND binding both named endpoints "
                f"(start {sig['start'].get('label') or sig['start'].get('sta')} -> end "
                f"{sig['end'].get('label') or sig['end'].get('sta')}); footage sheets "
                f"{recoveries[recommended]['footage_sheets']}, both-bound only on the recovered sheet"
                + ("; station span equals the printed footage (internal consistency)"
                   if sig["span"] else "")),
            "expected_seam_shape": sig["shape"],
            "why_safe": ("source-recovered single-sheet, both endpoints owner-named modeled classes, "
                         "no cross-sheet, no parent/child split, no representative-route resolver, no "
                         "unreviewed OCR -- the proven log64 family with a tiny variant"),
            "later_slice_would_encode": (
                "PRESENT the source-recovered sheet for OWNER confirmation (the log71 precedent), then "
                "encode endpoint_anchors (both structure_terminus) and run a log64-style single-sheet "
                "source-bind + render; only then add to contract/adapter/driver"),
        } if recommended else None),
        "rejected_near_misses": rejected,
        "recoveries": recoveries,
        "invariants": {
            "no_endpoint_anchors_encoded": True, "seam_contract_unchanged": True,
            "adapter_unchanged": True, "driver_unchanged": True, "eligible_set_unchanged": True,
            "no_eligibility_expansion": True, "no_generated_artifacts": True,
            "recovered_sheet_is_source_resolved_pending_owner_confirmation": True,
        },
        "method": ("contained read-only PDF probe: HH-HH footage annotation INTERSECT both-endpoint "
                   "bind (resolve_structure_position / resolve_nextlink_hh_callout) + same-frame "
                   "station-span consistency; never length-only, never a guess; reuses the canonical "
                   "classifier to fix the near-miss set"),
        "next_recommended_slice": (
            f"endpoint-anchor bridge for {recommended}: present recovered sheet "
            f"{recoveries[recommended]['recovered_sheet']} for owner confirmation, then encode "
            f"endpoint_anchors + log64-style single-sheet source-bind/render (contained slice)"
            if recommended else
            "no sheet safely recoverable; re-scope (recover the sheet by another owner-reviewed source)"),
        "gates": [{"name": n, "pass": bool(x), "detail": d} for n, x, d in gates],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "near_miss_sheet_locator_scout.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"[sheet-loc] result: {report['result']}  recommended: {recommended}")
    for lid in NEAR_MISSES:
        r = recoveries.get(lid) or {}
        print(f"[sheet-loc]   {lid}: footage_sheets={r.get('footage_sheets')} "
              f"both_bound={r.get('both_bound_sheets')} recovered_sheet={r.get('recovered_sheet')} "
              f"unique={r.get('uniquely_recovered')}")
    for n, x, _ in gates:
        print(f"[sheet-loc] {'PASS' if x else 'FAIL'}  {n}")
    print(f"[sheet-loc] VERDICT: {'PASS' if all_pass else 'FAIL'}  (report: {OUT_DIR})")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
