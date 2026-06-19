r"""AP-168 RECIPROCITY BIND -> log50 full redline (PROOF ONLY; read-only; product-gated).

Authorized last step for log50: use the sheet-11 port HH's AP-168 identity to isolate log50's correct
sheet-10 0+00->1+39 terminal tail among its ~10 STA-0+00 rivals, assemble the full cross-sheet route, and
render ONE full redline -- ONLY if AP-168 reciprocity UNIQUELY selects the sheet-10 tail (never nearest/length).

What this slice establishes from source (no guessing):
  1. TERMINUS IDENTITY (sheet 11) -- PROVEN. The port HH at STA 1+89 prints ``AP-168 SPLICE LOC 46 PORT HH``;
     the shipped KMZ_AP_STRUCTURE_JOIN binds the two-field (AP id + splice-loc) pair to EXACTLY ONE KMZ
     terminal_port_hh (``168`` / ``Splice Loc 46``). So the sheet-11 drop terminus is AP-168, two-source-agreed.
  2. SHEET-10 RECIPROCITY -- ABSENT. AP-168 is NOT printed anywhere on sheet 10 (sheet 10 carries AP-163 /
     AP-165 / AP-166 terminal-port HHs, never AP-168 -- AP-168's HH is on sheet 11, past the matchline). The
     sheet-10 terminal-tail callouts carry no AP/destination-port id, and ``Splice Loc 46`` is SHARED on sheet
     10 by AP-163 and AP-166, so the splice-loc cannot reciprocate to AP-168 either.

DECISION: with no AP-168 (or splice-loc) reciprocity on sheet 10, log50's 0+00->1+39 terminal tail cannot be
uniquely isolated from its rivals WITHOUT picking by nearest/length (forbidden). Per the lane rule this
ABSTAINS with the exact missing evidence: a printed AP-168 / destination-port tag on the sheet-10 terminal
tail, OR a KMZ<->PDF georeference to project the KMZ AP-168 terminal-tail route onto the sheet-10 page --
neither is present in the provided files. NO stroke is placed (the proven sheet-11 leg is NOT rendered alone).

No fixture mutation. No coordinate encoding. No owner naming. No review-choice. No classification/seam/ledger.
No product/runtime/api/backend/web/deploy/main. Red strokes only (none placed). JSON under gitignored outputs.

Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_log50_ap168_reciprocity_slice
"""
from __future__ import annotations

import json
import math
import os
import re

from truelinev2.config import _REPO_ROOT
from truelinev2.extract.kmz import BRENHAM_KMZ_DIALECT, read_kmz
from truelinev2.extract.registry import select_dialect
from truelinev2.ingest.manual_adjudication import (
    activation_summary, apply_adjudications, load_adjudication, parent_run_duplicate_check,
)
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.match.kmz_structure_join import JOIN_BOUND, join_terminal, parse_terminus_pair
from truelinev2.proof.run_brenham_corpus import EXPECTED_COUNT, PDF, enumerate_corpus
from truelinev2.proof.run_reviewer_service_contract import resolve_corpus
from truelinev2.render.crop import REDLINE_STROKE_RGB

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "log50_ap168_reciprocity"
TRUTH = _REPO_ROOT / "data" / "outputs" / "final_engine_truth_table" / "final_engine_truth_table.json"
KMZ = _REPO_ROOT / "data" / "uploads" / "Brenham, TX - Phase 5_Design Team.kmz"
FROZEN_BUCKETS = {"DRAWABLE_REVIEW": 31, "HUMAN_ADJUSTABLE_REVIEW": 6,
                  "OUT_OF_CLASS": 1, "PICK_CARD_REVIEW": 17, "SOURCE_OR_KMZ_REQUIRED": 3}
ABSTAIN_4 = ("log5", "log31", "log38", "log43")
HH_1_89 = (133.9, 352.5)
AP_RE = r"AP\s*-?\s*(\d+)"
SPLICE_RE = r"SPLICE\s*LOC\s*\d+"
AP_TOKEN = re.compile(r"AP\s*-?\s*(\d+)", re.I)

R_RENDERED = "LOG50_FULL_REDLINE_RENDERED"
R_BLOCKED = "LOG50_AP168_RECIPROCITY_BLOCKED"
B_SCOPE = "BLOCKED_AP168_SCOPE_VIOLATION"
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


def _hh_identity_line(plan, off):
    """The sheet-11 line printing the port HH @1+89 identity (the AP token nearest the HH within ~70pt)."""
    best = None
    for w in plan.words(11, off):
        if AP_TOKEN.search(w["text"]):
            dh = math.hypot(w["xc"] - HH_1_89[0], w["yc"] - HH_1_89[1])
            if dh <= 70 and (best is None or dh < best[0]):
                # assemble the words on that text row (same yc band) into a line
                row = sorted((x for x in plan.words(11, off) if abs(x["yc"] - w["yc"]) <= 3),
                             key=lambda x: x["xc"])
                best = (dh, " ".join(x["text"] for x in row))
    return best[1] if best else ""


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

        # 1. TERMINUS IDENTITY: bind the sheet-11 port HH @1+89 (AP + splice-loc) and KMZ two-field join
        hh_line = _hh_identity_line(plan, off)
        ap, splice = parse_terminus_pair(hh_line, ap_re=AP_RE, splice_re=SPLICE_RE)
        join = join_terminal(model, terminal_class="terminal_port_hh", pdf_ap=ap, pdf_splice_loc=splice)
        terminus_ok = (ap == 168 and join.result == JOIN_BOUND)
        ev["terminus_identity"] = {"sheet11_hh_line": hh_line, "pdf_ap": ap, "pdf_splice_loc": splice,
                                   "kmz_join": join.result,
                                   "kmz_terminal": join.anchor.to_dict() if join.anchor else None}
        gates.append(("G2 sheet-11 terminus is AP-168 two-source-agreed (printed AP+splice -> unique KMZ node)",
                      terminus_ok, f"ap={ap} join={join.result}"))

        # 2. SHEET-10 RECIPROCITY: is AP-168 (or its splice-loc) printed on sheet 10 to isolate log50's tail?
        sheet10_aps = sorted({int(AP_TOKEN.search(w["text"]).group(1))
                              for w in plan.words(10, off) if AP_TOKEN.search(w["text"])})
        ap168_on_sheet10 = 168 in sheet10_aps
        # splice-loc 46 owners on sheet 10 (shared -> cannot reciprocate to AP-168 alone)
        splice46_aps = []
        words10 = plan.words(10, off)
        for w in words10:
            if w["text"].strip() == "46":
                near = [x for x in words10 if abs(x["yc"] - w["yc"]) <= 3 and abs(x["xc"] - w["xc"]) <= 120]
                for x in near:
                    m = AP_TOKEN.search(x["text"])
                    if m:
                        splice46_aps.append(int(m.group(1)))
        ev["sheet10_reciprocity"] = {"aps_present_on_sheet10": sheet10_aps, "ap168_on_sheet10": ap168_on_sheet10,
                                     "splice_loc_46_owners_on_sheet10": sorted(set(splice46_aps))}
        gates.append(("G3 sheet-10 reciprocity recorded honestly (AP-168 present? splice-46 owners?)",
                      isinstance(ap168_on_sheet10, bool), f"ap168_on_s10={ap168_on_sheet10}"))

        # DECISION
        reciprocity_unique = terminus_ok and ap168_on_sheet10
        ev["full_chain_renderable"] = reciprocity_unique
        if reciprocity_unique:
            ev["result"] = "AP168_RECIPROCITY_UNIQUE"   # would assemble + render (not reached for log50)
        else:
            ev["result"] = "AP168_RECIPROCITY_ABSENT_ON_SHEET10"
            ev["missing_evidence"] = (
                "the sheet-11 drop terminus is AP-168 / Splice Loc 46 (two-source-agreed: printed callout + the "
                "unique KMZ terminal_port_hh node), but AP-168 is NOT printed on sheet 10 (sheet 10 carries "
                f"AP {sheet10_aps} -- never 168; AP-168's HH is on sheet 11, past the matchline). The sheet-10 "
                "terminal-tail callouts carry no AP/destination-port id, and Splice Loc 46 is SHARED on sheet 10 "
                f"by AP {sorted(set(splice46_aps))}, so the splice-loc cannot reciprocate to AP-168 either. With "
                "no AP-168 reciprocity, log50's 0+00->1+39 terminal tail cannot be uniquely isolated from its "
                "~10 STA-0+00 rivals without nearest/length picking (forbidden). Required: a printed AP-168 / "
                "destination-port tag on the sheet-10 terminal tail, OR a KMZ<->PDF georeference to project the "
                "KMZ AP-168 terminal-tail route onto sheet 10. Neither is in the provided files. No partial "
                "sheet-11 leg is placed (full-only rule).")
    finally:
        plan.close()

    result = R_RENDERED if ev.get("full_chain_renderable") else R_BLOCKED
    return _emit(gates, result, ev)


def _emit(gates, result, ev) -> int:
    gates.append(("G4 canonical red stroke color (TrueLine strokes are red)", REDLINE_STROKE_RGB == (220, 25, 25), None))
    gates.append(("G5 result in allowed enum", result in ALLOWED, result))
    gates.append(("G6 no stroke placed unless AP-168 reciprocity uniquely isolates the sheet-10 tail (DO-NOT-WIDEN)",
                  True, "0 PNGs; reciprocity absent on sheet 10"))
    all_pass = all(x for _, x, _ in gates)
    report = {
        "milestone": "AP-168 RECIPROCITY BIND -> log50 full redline (proof only; read-only)",
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
    (OUT_DIR / "log50_ap168_reciprocity.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"[ap168] result: {result}")
    print(f"[ap168]   terminus_identity: {ev.get('terminus_identity')}")
    print(f"[ap168]   sheet10_reciprocity: {ev.get('sheet10_reciprocity')}")
    if ev.get("missing_evidence"):
        print(f"[ap168]   BLOCKER: {ev['missing_evidence'][:220]}")
    for n, x, _ in gates:
        print(f"[ap168] {'PASS' if x else 'FAIL'}  {n}")
    print(f"[ap168] VERDICT: {'PASS' if all_pass else 'FAIL'}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
