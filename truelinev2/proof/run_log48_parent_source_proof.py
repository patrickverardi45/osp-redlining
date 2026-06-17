r"""PHASE 5 -- targeted log48 render attempt THROUGH the parent-source model (PROOF; read-only; renders NOTHING).

Owner truth: log48 is Segment A of original handwritten bore_log20 (corpus span 0+00->5+09); the 0+00->5+14
route is the SIBLING Segment C (log50). log48's adjudication is CORRUPTED (it carries Segment C's trace:
'STA 45+33=0+00 ... 5+14 FLOWER POT'). This proof attempts log48 ONLY through the parent-source model and
shows it must ABSTAIN -- it cannot render its own child, and the only drawable route is the sibling's, which
the parent-source gate blocks. NO render, NO corpus mutation, NO census change.

Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_log48_parent_source_proof
"""
from __future__ import annotations

import json

from truelinev2.config import _REPO_ROOT
from truelinev2.extract.registry import select_dialect
from truelinev2.ingest import parent_source as ps
from truelinev2.ingest.manual_adjudication import load_adjudication
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.proof.run_brenham_corpus import PDF
from truelinev2.proof.run_callout_route_assembly_sweep import SCALE, solve_log

OUT = _REPO_ROOT / "data" / "outputs" / "log48_parent_source_proof"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    adj = {r["log_id"]: r for r in load_adjudication()["logs"]}
    _, e48 = ps.entry("log48")
    report = {
        "milestone": "PHASE 5 -- log48 targeted render through the parent-source model (proof; ABSTAIN expected)",
        "parent": ps.parent_of("log48"),
        "siblings": ps.siblings("log48"),
        "span_collision_siblings": ps.span_collision_siblings("log48"),
        "log48_corpus_span": e48["entry_span"],
        "log48_adjudication_span": e48.get("adj_corrected_span"),
        "log50_sibling_corpus_span": ps.entry("log50")[1]["entry_span"],
    }
    # the model uses the CORPUS span as log48's identity, REJECTING the corrupted adjudication
    own_str, own_ft = ps._own_span("log48", e48)
    report["log48_own_span_used_by_gate"] = own_str
    report["corrupted_adjudication_rejected"] = (own_str == e48["entry_span"] != e48.get("adj_corrected_span"))
    # the gate blocks the sibling 5+14 route
    g_ok, g_reason = ps.child_owns_route("log48", 514.0, [10, 11])
    report["gate_blocks_sibling_5_14"] = (not g_ok)
    report["gate_reason"] = g_reason

    plan = PlanPdf(PDF)
    try:
        off = select_dialect(plan).calibrate(plan, 13)
        # EXPERIMENT A: log48 via its CORPUS identity (Segment A 0+00->5+09) -- no own start reset exists
        corpus_rec = {"log48": {"log_id": "log48", "corrected_start": "0+00", "corrected_end": "5+09",
                                "corrected_sheets": [10, 11, 12], "span_ft": 509.0, "status": "RECOVERED",
                                "evidence_notes": "", "endpoint_anchors": None,
                                "allowed_to_draw": True, "must_remain_abstained": False}}
        vA = solve_log(plan, off, "log48", corpus_rec)
        report["corpus_path_resolvable"] = bool(vA.get("legs"))
        report["corpus_path_blocker"] = vA.get("blocker")
        # EXPERIMENT B: log48 via the CORRUPTED adjudication -> Segment C's route -> gated
        vB = solve_log(plan, off, "log48", adj)
        if vB.get("legs"):
            drawn = (vB.get("closure") or {}).get("drawn_ft") or sum(l["len_pt"] for l in vB["legs"]) / SCALE
            sheets = sorted({l["sheet"] for l in vB["legs"]})
            bk, br = ps.child_owns_route("log48", drawn, sheets)
            report["corrupted_path_route"] = {"start": f"{vB.get('start_class')}@{vB.get('bound_labels',{}).get('start')}",
                                              "end": f"{vB.get('end_class')}@{vB.get('bound_labels',{}).get('end')}",
                                              "drawn_ft": round(drawn, 1), "sheets": sheets}
            report["corrupted_path_gated_out"] = (not bk)
            report["corrupted_path_gate_reason"] = br
    finally:
        plan.close()

    abstain = (not report["corpus_path_resolvable"]
               and report["gate_blocks_sibling_5_14"]
               and report.get("corrupted_path_gated_out", True)
               and report["corrupted_adjudication_rejected"])
    report["verdict"] = "ABSTAIN_NO_OWN_SOURCE_ROUTE" if abstain else "UNEXPECTED_REVIEW"
    report["rendered"] = []
    report["missing_evidence"] = (
        "log48 (Segment A of bore_log20) has NO source-stable route distinct from sibling Segment C (log50): "
        "same start (0+00), same uncertain print (10,11,12), spans within ~1% (509 vs 514), and the ONLY trace "
        "(log48's adjudication) is CORRUPTED with Segment C's route (45+33=0+00 -> 5+14). To render log48 safely "
        "we need Segment A's OWN start reset (mainline STA X+XX=0+00) and/or end-structure identity (the 5+09 "
        "terminus), which live only in the original handwritten bore_log20 parent's column-A trace -- recoverable "
        "via the Phase 2/3 parent reassembly, not from the current split-child corpus or the corrupted adjudication.")
    report["no_render"] = True
    report["no_corpus_mutation"] = True
    report["census_frozen"] = True

    (OUT / "log48_parent_source_proof.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"[log48-proof] VERDICT: {report['verdict']}")
    print(f"[log48-proof] parent={report['parent']} siblings={report['siblings']}")
    print(f"[log48-proof] log48 corpus span={report['log48_corpus_span']} (own used by gate={report['log48_own_span_used_by_gate']}); "
          f"adjudication span={report['log48_adjudication_span']} (corrupted, rejected={report['corrupted_adjudication_rejected']})")
    print(f"[log48-proof] sibling log50 span={report['log50_sibling_corpus_span']}; gate blocks 5+14={report['gate_blocks_sibling_5_14']}")
    print(f"[log48-proof] corpus path resolvable={report['corpus_path_resolvable']} (blocker: {report['corpus_path_blocker']})")
    print(f"[log48-proof] corrupted path route={report.get('corrupted_path_route')} gated_out={report.get('corrupted_path_gated_out')}")
    print(f"[log48-proof] missing evidence: {report['missing_evidence'][:160]}...")
    return 0 if abstain else 1


if __name__ == "__main__":
    raise SystemExit(main())
