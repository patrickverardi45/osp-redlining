r"""OWNER-CORRECTION recon scout -- cross-sheet / parent-child logs (PROOF/REPORT ONLY; read-only).

The owner returned corrections for six logs recently surfaced in the cross_sheet_blocked evidence packet
(log48/67/69/70/11/47). This scout determines their IMPACT on the closure ledger / blocker taxonomy by
SOURCE-VERIFYING each owner-corrected terminus with the SHIPPED resolvers (read-only) -- never trusting the
owner prose alone, never the stale fixture alone. It ENCODES nothing, modifies NO fixture, parses no
coordinate into a placement, draws nothing, promotes nothing, and never guesses a class.

Findings (every bind below is the UNIQUE source-resolver result, not an assumption):

  SOURCE-VERIFIED owner corrections -> BRIDGE-READY candidates (pending an authorized FIXTURE correction):
    log67  installer_hh @ 1+45=0+00 (s17)  ->  flower_pot @ 4+14 (s20)   [cross-sheet 17->20]
    log69  installer_hh @ 1+45=0+00 (s17)  ->  installer_hh @ 4+54 (s17)  [SINGLE-SHEET -- both on s17]
    log70  installer_hh @ 1+45=0+00 (s17)  ->  flower_pot @ 2+15 (s20)   [cross-sheet 17->20]
    log47  flower_pot   @ 3+23     (s13)  ->  installer_hh @ 4+94 (s14)  [cross-sheet; join 10->13->14 backed]
    log11  nextlink_hh  @ 21+63=0+00 (s5) ->  flower_pot @ 6+30 (s17)    [cross-sheet 5->17; join backed]
  All three of log67/69/70 share the SAME source start structure (installer_hh on s17) -- the owner's "one
  reset HH start" is source-confirmed. log69's destination 4+54 binds installer_hh on SHEET 17 (not 20), so
  the corrected log69 is a SINGLE-SHEET run -- it leaves the cross-sheet class entirely and its 17<->20
  CONFLICTING_FRAME_EQUATIONS blocker is moot. For the still-cross-sheet log67/log70, the conflicting
  17<->20 crossing becomes a deferred RENDER-time concern, NOT a bridge blocker (identity-only bridge).

  PARENT/CHILD original-run reconstruction -> SUPERSEDES the prior CROSS_SHEET (direct 10<->12) read:
    log48  the original handwritten print spans sheets 10,11,12 with ONE parent reset and TWO child legs:
             parent reset  nextlink_hh @ 45+33=0+00 (s10)
             child A  -> flower_pot @ 5+14 (s11)
             child B  -> flower_pot @ 5+07 (s12)
    The owner's verbal sheet attribution is DISCREPANT with source (it placed the reset on s12 and the 5+07
    flower pot on s10; source binds the reset on s10, 5+07 on s12, 5+14 on s11). The prior 'single
    continuous traced run' fixture read mis-merged the two child legs. This needs OWNER confirmation of the
    source-true parent/child segmentation + a fixture correction; engine-drawable log50 (sheets [10,11]) is
    the candidate sibling for the s10->s11 (5+14) leg. NOT resolvable as a missing/direct matchline question.

This scout records the owner corrections as DATA, source-verifies them, classifies readiness, and names the
exact fixture corrections needed -- it writes NONE of them. Census frozen; seam unchanged; the six stay
unencoded in the reviewed artifact.

Proof-only; the JSON report is written under the gitignored data/outputs path.
Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_owner_correction_recon_scout
"""
from __future__ import annotations

import json
import os

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
from truelinev2.proof.run_all_redlines_closure_ledger import CROSS_SHEET, build_ledger
from truelinev2.proof.run_brenham_corpus import PDF
from truelinev2.seam import ELIGIBLE_EXEMPLARS

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "owner_correction_recon_scout"
TRUTH = _REPO_ROOT / "data" / "outputs" / "final_engine_truth_table" / \
    "final_engine_truth_table.json"
FROZEN_BUCKETS = {"DRAWABLE_REVIEW": 31, "HUMAN_ADJUSTABLE_REVIEW": 6,
                  "OUT_OF_CLASS": 1, "PICK_CARD_REVIEW": 17, "SOURCE_OR_KMZ_REQUIRED": 3}
ABSTAIN_4 = ("log5", "log31", "log38", "log43")
SEAM_ELIGIBLE = ("log53", "log64", "log71", "log59", "log66")
PROBE_CLASSES = ("installer_hh", "terminal_port_hh", "flower_pot")   # nextlink_hh via its own callout

# owner corrections recorded as DATA (from the owner packet). Each terminus: (class, station, sheet, reset).
# The class is the OWNER-NAMED expectation; the scout verifies it is the UNIQUE source bind.
CORRECTIONS = {
    "log67": {"start": ("installer_hh", "1+45", 17, True), "end": ("flower_pot", "4+14", 20, False),
              "prior_blocker": "CONFLICTING_FRAME_EQUATIONS (17<->20)",
              "fixture_was": "start 1+45=0+00 (class unnamed); end 4+14 FLOWER POT; sheets [17,20]",
              "fixture_correction": "name the start installer_hh @1+45=0+00 (s17); stations/sheets already match"},
    "log69": {"start": ("installer_hh", "1+45", 17, True), "end": ("installer_hh", "4+54", 17, False),
              "prior_blocker": "CONFLICTING_FRAME_EQUATIONS (17<->20)",
              "fixture_was": "start 2+15 FLOWER POT; end 4+54 INSTALLER HH; sheets [17,20]",
              "fixture_correction": "start 2+15 FLOWER POT -> installer_hh @1+45=0+00 (s17); end installer_hh @4+54 (s17); corrected_sheets [17,20] -> [17] (single sheet)"},
    "log70": {"start": ("installer_hh", "1+45", 17, True), "end": ("flower_pot", "2+15", 20, False),
              "prior_blocker": "CONFLICTING_FRAME_EQUATIONS (17<->20)",
              "fixture_was": "start 4+54 INSTALLER HH; end 2+15 FLOWER POT; sheets [17,20]; 'HH-HH=215'' note",
              "fixture_correction": "start 4+54 INSTALLER HH -> installer_hh @1+45=0+00 (s17); end flower_pot @2+15 (s20); reconcile the 'HH-HH=215'' annotation"},
    "log47": {"start": ("flower_pot", "3+23", 13, False), "end": ("installer_hh", "4+94", 14, False),
              "prior_blocker": "ENDPOINT_IDENTITY (end bare) + start-sheet attribution",
              "fixture_was": "start 3+23 FLOWER POT (sheet attribution off); end 4+94 bare (unnamed); sheets [10,13,14]",
              "fixture_correction": "name the end installer_hh @4+94 (s14); pin the start flower_pot to sheet 13"},
    "log11": {"start": ("nextlink_hh", "21+63", 5, True), "end": ("flower_pot", "6+30", 17, False),
              "prior_blocker": "ENDPOINT_IDENTITY (start, cross-log NEXTLINK HH)",
              "fixture_was": "start 21+63=0+00 (class unnamed/cross-log); end 6+30 FLOWER POT; sheets [5,17]",
              "fixture_correction": "name the start nextlink_hh @21+63=0+00 (s5); stations/sheets already match"},
}
CROSS_SHEET_AFTER = ("log67", "log70", "log47", "log11")   # still cross-sheet (bridge-ready after fixture)
SINGLE_SHEET_AFTER = ("log69",)                            # corrected log69 is single-sheet

# log48 parent/child original run (source-true legs). NOT encoded; for owner confirmation.
LOG48 = {
    "parent_reset": ("nextlink_hh", "45+33", 10, True),
    "children": [("flower_pot", "5+14", 11), ("flower_pot", "5+07", 12)],
    "owner_stated": ("log48 = 45+00 (s12) -> 5+07 FLOWER POT (s10); sibling 45+00 -> 5+14 (s10->s11)"),
    "owner_sheet_attribution": "DISCREPANT: source binds the reset on s10 (not s12), 5+07 on s12 (not s10), 5+14 on s11",
    "sibling_candidate": "log50 (engine-drawable, sheets [10,11]) -- candidate for the s10->s11 (5+14) leg",
}

R_COMPLETE = "OWNER_CORRECTION_RECON_COMPLETE"
B_TRUTH = "BLOCKED_RECON_TRUTH_MISSING"
B_PDF = "BLOCKED_RECON_PDF_MISSING"
B_SET = "BLOCKED_RECON_SET_DRIFTED"
B_ENCODED = "BLOCKED_RECON_SILENTLY_ENCODED"
ALLOWED = {R_COMPLETE, B_TRUTH, B_PDF, B_SET, B_ENCODED}


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


def resolve_class(plan, offset, sheet, station, reset) -> dict:
    """Run every shipped resolver at one terminus; return {class: xy} for each UNIQUE bind found.
    No class is invented; >=2 binds => ambiguous (the caller treats it as unverified)."""
    words = plan.words(sheet, offset)
    draw = plan.line_items(sheet, offset)
    labels = [f"{station}=0+00", station] if reset else [station, f"{station}=0+00"]
    bound = {}
    for cls in PROBE_CLASSES:
        for label in labels:
            kw = dict(label_text=label, structure_class=cls, words=words, drawings=draw,
                      layer_table=BRENHAM_STRUCTURE_LAYERS)
            if cls == "flower_pot":
                kw["context_texts"] = ("FLOWER", "POT")
            v = resolve_structure_position(**kw)
            if v.result == POSITION_BOUND and v.symbol_xy:
                bound[cls] = [round(c, 1) for c in v.symbol_xy]
                break
    nv = resolve_nextlink_hh_callout(station_sta=station, words=words, drawings=draw,
                                     callout_layer="ANNOTATION", symbol_layer="NEXTLINK")
    if nv.result == POSITION_BOUND and nv.symbol_xy:
        bound["nextlink_hh"] = [round(c, 1) for c in nv.symbol_xy]
    return bound


def verify_terminus(plan, offset, spec) -> dict:
    """Verify one owner-named terminus binds UNIQUELY as the owner-named class on the owner-stated sheet."""
    cls, sta, sheet, reset = spec
    bound = resolve_class(plan, offset, sheet, sta, reset)
    unique = len(bound) == 1
    matches = unique and cls in bound
    return {"owner_class": cls, "station": sta, "sheet": sheet, "classes_bound": sorted(bound),
            "xy": bound.get(cls), "unique": unique, "source_verified": bool(matches)}


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for stale in OUT_DIR.glob("*.png"):
        stale.unlink()

    doc = load_adjudication()
    rec = {r["log_id"]: r for r in doc["logs"]}
    gates, ver = [], {}
    result = B_SET

    gates.append(("G0 engine census frozen (OFF 31/6/1/17/3, ON 22/1/4, log44+abstains held)",
                  _census_frozen(doc), None))

    # G1 the corrected logs are exactly the live cross-sheet evidence-packet set (6) (incl. log48)
    ledger_cross = set()
    if TRUTH.is_file():
        rows = json.loads(TRUTH.read_text(encoding="utf-8"))["rows"]
        ledger_cross = {b for b, v in build_ledger(rows, doc).items() if v["category"] == CROSS_SHEET}
    corrected = set(CORRECTIONS) | {"log48"}
    gates.append(("G1 corrected logs (log11/47/48/67/69/70) == the live ledger CROSS_SHEET class (6)",
                  ledger_cross == corrected, {"ledger_cross": sorted(ledger_cross)}))

    if not os.path.isfile(PDF):
        gates.append(("G2 plan PDF present (read-only, to run the resolvers)", False, PDF))
        return _emit(gates, B_PDF, rec, ver)
    gates.append(("G2 plan PDF present (read-only)", True, None))

    plan = PlanPdf(PDF)
    try:
        offset = select_dialect(plan).calibrate(plan, 13)
        for lid, c in CORRECTIONS.items():
            ver[lid] = {"start": verify_terminus(plan, offset, c["start"]),
                        "end": verify_terminus(plan, offset, c["end"])}
        # log48 parent/child source verification
        l48 = {"parent_reset": verify_terminus(plan, offset, LOG48["parent_reset"]),
               "children": [verify_terminus(plan, offset, (cls, sta, sheet, False))
                            for cls, sta, sheet in LOG48["children"]]}
        ver["log48"] = l48
    finally:
        plan.close()

    # G3 SOURCE-VERIFIED: both termini of log67/69/70/47/11 bind UNIQUELY as the owner-named class
    verified = all(ver[l]["start"]["source_verified"] and ver[l]["end"]["source_verified"]
                   for l in CORRECTIONS)
    gates.append(("G3 owner corrections SOURCE-VERIFIED: both termini of log67/69/70/47/11 bind uniquely as the owner-named class",
                  verified, {l: (ver[l]["start"]["source_verified"], ver[l]["end"]["source_verified"]) for l in CORRECTIONS}))

    # G4 log69 is SINGLE-SHEET (both termini on s17); log67/log70/log47/log11 stay cross-sheet
    g69_single = (ver["log69"]["start"]["sheet"] == ver["log69"]["end"]["sheet"] == 17
                  and ver["log69"]["start"]["source_verified"] and ver["log69"]["end"]["source_verified"])
    cross_after = all(ver[l]["start"]["sheet"] != ver[l]["end"]["sheet"] for l in CROSS_SHEET_AFTER)
    gates.append(("G4 corrected log69 is SINGLE-SHEET (both termini s17 -> leaves cross-sheet); log67/70/47/11 stay cross-sheet",
                  g69_single and cross_after, None))

    # G5 log48 PARENT/CHILD: source binds the parent reset on s10 + both flower_pot children (5+14 s11,
    #    5+07 s12); the owner's verbal sheet attribution is DISCREPANT (the prior single-run read mis-merged)
    l48 = ver["log48"]
    parent_ok = l48["parent_reset"]["source_verified"] and l48["parent_reset"]["sheet"] == 10
    children_ok = (l48["children"][0]["source_verified"] and l48["children"][0]["sheet"] == 11
                   and l48["children"][1]["source_verified"] and l48["children"][1]["sheet"] == 12)
    gates.append(("G5 log48 PARENT/CHILD source-true: parent reset nextlink_hh @45+33=0+00 (s10) + 2 flower_pot children (5+14 s11, 5+07 s12)",
                  parent_ok and children_ok,
                  {"parent": l48["parent_reset"]["xy"], "child_5+14_s11": l48["children"][0]["xy"],
                   "child_5+07_s12": l48["children"][1]["xy"]}))

    # G6 ENCODES NOTHING + FIXTURE UNTOUCHED: the six carry no endpoint_anchors; still CROSS_SHEET in ledger
    fresh = {r["log_id"]: r for r in load_adjudication()["logs"]}
    encodes_nothing = (all(not fresh[l].get("endpoint_anchors") for l in corrected)
                       and ledger_cross == corrected)
    gates.append(("G6 ENCODES NOTHING + fixture untouched: the six carry no endpoint_anchors; still CROSS_SHEET",
                  encodes_nothing, None))

    if all(x for _, x, _ in gates):
        result = R_COMPLETE
    elif not gates[1][1]:
        result = B_SET
    elif not gates[-1][1]:
        result = B_ENCODED
    return _emit(gates, result, rec, ver)


def _emit(gates, result, rec, ver) -> int:
    pngs = sorted(p.name for p in OUT_DIR.glob("*.png"))
    gates.append(("G7 no render / zero PNG / seam unchanged (nothing promoted)",
                  len(pngs) == 0 and tuple(ELIGIBLE_EXEMPLARS) == SEAM_ELIGIBLE, {"pngs": pngs}))
    gates.append(("G8 result in allowed enum", result in ALLOWED, result))
    all_pass = all(x for _, x, _ in gates)

    def status(lid):
        if lid in SINGLE_SHEET_AFTER:
            return "BRIDGE_READY_SINGLE_SHEET_PENDING_FIXTURE_CORRECTION"
        if lid in CROSS_SHEET_AFTER:
            return "BRIDGE_READY_CROSS_SHEET_PENDING_FIXTURE_CORRECTION (crossing deferred to render)"
        return "PARENT_CHILD_RECON_BLOCKED_PENDING_OWNER_CLARIFICATION"

    impact = {lid: {"prior_blocker": c["prior_blocker"],
                    "owner_correction": {"start": list(c["start"]), "end": list(c["end"])},
                    "source_verified": (ver.get(lid, {}).get("start", {}).get("source_verified")
                                        and ver.get(lid, {}).get("end", {}).get("source_verified")),
                    "verification": ver.get(lid),
                    "new_status": status(lid),
                    "fixture_correction_needed": c["fixture_correction"]}
              for lid, c in CORRECTIONS.items()}
    impact["log48"] = {
        "prior_blocker": "CROSS_SHEET NO_PAIRED_FRAME_EQUATION (direct 10<->12) -- SUPERSEDED",
        "owner_correction": LOG48["owner_stated"],
        "source_truth": {"parent_reset": "nextlink_hh @45+33=0+00 (s10)",
                         "child_A": "flower_pot @5+14 (s11)", "child_B": "flower_pot @5+07 (s12)"},
        "owner_sheet_attribution": LOG48["owner_sheet_attribution"],
        "verification": ver.get("log48"),
        "new_status": status("log48"),
        "sibling_candidate": LOG48["sibling_candidate"],
        "fixture_correction_needed": ("split the mis-merged 'single continuous run' into the source-true "
                                      "parent reset (s10) + two child flower-pot legs (5+14 s11, 5+07 s12); "
                                      "owner must confirm the segmentation/direction; reconcile sibling log50")}
    report = {
        "milestone": "OWNER-CORRECTION recon scout -- cross-sheet / parent-child (proof/report only; read-only)",
        "verdict": "PASS" if all_pass else "FAIL",
        "result": result if all_pass else "BLOCKED",
        "method": ("recorded the owner corrections as data and SOURCE-VERIFIED every terminus with the shipped "
                   "resolvers; compared to the stale fixture; classified readiness; named fixture corrections"),
        "bridge_ready_after_fixture_correction": list(CROSS_SHEET_AFTER) + list(SINGLE_SHEET_AFTER),
        "single_sheet_now": list(SINGLE_SHEET_AFTER),
        "parent_child_reconstruction": ["log48"],
        "still_blocked": {"log48": "owner clarification of source-true parent/child segmentation + fixture correction",
                          "log67/log70 render": "the 17<->20 CONFLICTING crossing remains a deferred RENDER-time concern (NOT a bridge blocker)"},
        "impact_by_log": impact,
        "ledger_taxonomy_impact": (
            "log69 leaves CROSS_SHEET (single-sheet after correction); log67/log70/log47/log11 stay cross-sheet "
            "but move from join/identity-blocked to bridge-ready (endpoint identities source-verified; for "
            "log67/log70 the conflicting 17<->20 crossing is deferred to render, not the bridge); log48 moves "
            "from CROSS_SHEET (direct 10<->12) to PARENT_CHILD reconstruction. NONE of this changes the ledger "
            "YET -- it is gated on an authorized fixture correction; the engine census stays frozen."),
        "doctrine": {
            "no_encoding": "no endpoint_anchors written; the six stay unencoded",
            "no_fixture_modification": "the fixture is byte-unchanged; corrections are NAMED, not applied",
            "no_guess": "every class is the UNIQUE source-resolver bind; owner prose verified, never assumed",
            "owner_prose_vs_source": "log48 owner sheet attribution is discrepant -> flagged for owner clarification, not adopted",
            "no_new_resolver": True, "no_render": True, "no_seam_promotion": True, "engine_census_frozen": True,
        },
        "scope_guard": {"product_wiring": False, "broad_renderer": False, "match_review_wiring": False,
                        "runtime_batch": False, "deploy": False, "coordinates_invented": False,
                        "endpoint_anchors_encoded": False, "fixture_modified": False},
        "next_slice": ("authorize the fixture correction for the 5 source-verified logs (log67/69/70/47/11) -> "
                       "then endpoint-anchor bridge + sheet-local bind (log69 single-sheet; log67/70/47/11 "
                       "cross-sheet; log67/70 render crossing deferred). For log48: owner-confirm the source-true "
                       "parent/child segmentation (+ sibling log50), then correct the fixture. Each separately authorized."),
        "gates": [{"name": n, "pass": bool(x), "detail": d} for n, x, d in gates],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "owner_correction_recon_scout.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"[owner-recon] result: {report['result']}")
    for lid in ("log11", "log47", "log67", "log69", "log70"):
        v = ver.get(lid, {})
        if v:
            print(f"[owner-recon]   {lid}: start={v['start'].get('owner_class')}@{v['start'].get('station')}(s{v['start'].get('sheet')})"
                  f" end={v['end'].get('owner_class')}@{v['end'].get('station')}(s{v['end'].get('sheet')})"
                  f" verified={v['start'].get('source_verified') and v['end'].get('source_verified')}")
    print(f"[owner-recon]   log48: parent/child reconstruction (reset s10 -> FP 5+14 s11 + FP 5+07 s12); owner sheet attribution discrepant")
    for n, x, _ in gates:
        print(f"[owner-recon] {'PASS' if x else 'FAIL'}  {n}")
    print(f"[owner-recon] VERDICT: {'PASS' if all_pass else 'FAIL'}  (report: {OUT_DIR})")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
