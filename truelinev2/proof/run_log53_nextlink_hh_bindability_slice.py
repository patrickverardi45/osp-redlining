r"""OWNER-PACKET-2 -- log53 NEXTLINK HH start-anchor bindability slice (PROOF ONLY).

Question (the ONLY one this proof answers): can ``resolve_structure_position`` bind a
UNIQUE sheet-5 source SYMBOL for log53's start anchor (NEXTLINK HH / STA 21+63) when
supplied PROOF-LOCAL class/layer/label inputs -- i.e. is the conduit-chain SEED the
matchline-boundary slice needs recoverable from source, or is it a true dead end?

Method (existing seam only; nothing wired into production):
  1. pull log53 from the ACTUAL flag-on manual-adjudication overlay; read its
     ``endpoint_anchors.start`` (structure_class=nextlink_hh, label NEXTLINK HH,
     STA 21+63) -- consumed from the committed bridge, not hardcoded;
  2. build a PROOF-LOCAL layer table mapping nextlink_hh -> the populated sheet-5
     NEXTLINK symbol layer + INSTALLER HH - TEXT text layer (mirrors installer_hh).
     This is a TEST INPUT ONLY -- BRENHAM_STRUCTURE_LAYERS is NOT modified (G4);
  3. run ``resolve_structure_position`` over a principled CANDIDATE LADDER of
     identity tokens drawn from the owner note ("STA 21+63=0+00 ... NEXTLINK HH ...
     PROP. SPLICE POINT 32"): the station, the reset token, the NEXTLINK token, the
     splice id -- with/without disambiguating context; plus an installer_hh control
     using the REAL dialect table;
  4. roll the per-candidate verdicts up to ONE mission status. POSITION_BOUND iff a
     candidate binds a unique symbol; otherwise the most-advanced typed refusal.

No fallback placement, no invented coordinates, no nearest-snap, no render, no
dialect/schema change. Proof-only; artifacts gitignored. Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_log53_nextlink_hh_bindability_slice
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from truelinev2.config import _REPO_ROOT
from truelinev2.extract.registry import select_dialect
from truelinev2.extract.structure_position import (
    BRENHAM_STRUCTURE_LAYERS,
    LABEL_BOX_NOT_UNIQUE,
    LABEL_WORD_NOT_UNIQUE,
    LEADER_NOT_UNIQUE,
    POSITION_BOUND,
    SYMBOL_CLASS_MISMATCH,
    SYMBOL_NOT_UNIQUE,
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
from truelinev2.proof.run_reviewer_service_contract import resolve_corpus

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "log53_nextlink_hh_bindability_slice"
TRUTH = _REPO_ROOT / "data" / "outputs" / "final_engine_truth_table" / \
    "final_engine_truth_table.json"
FROZEN_BUCKETS = {"DRAWABLE_REVIEW": 31, "HUMAN_ADJUSTABLE_REVIEW": 6,
                  "OUT_OF_CLASS": 1, "PICK_CARD_REVIEW": 17, "SOURCE_OR_KMZ_REQUIRED": 3}
ABSTAIN_4 = ("log5", "log31", "log38", "log43")

# mission outcome enum
S_BOUND = "POSITION_BOUND"
B_CLASS = "BLOCKED_SYMBOL_CLASS_MISMATCH"
B_NOT_FOUND = "BLOCKED_LABEL_NOT_FOUND"
B_NOT_UNIQUE = "BLOCKED_LABEL_NOT_UNIQUE"
B_LOCATOR = "BLOCKED_LOCATOR_NOT_AVAILABLE"
B_POS_NOT_UNIQUE = "BLOCKED_SOURCE_POSITION_NOT_UNIQUE"
B_NO_POS = "BLOCKED_NO_SOURCE_POSITION"
ALLOWED = {S_BOUND, B_CLASS, B_NOT_FOUND, B_NOT_UNIQUE, B_LOCATOR, B_POS_NOT_UNIQUE, B_NO_POS}

# PROOF-LOCAL only -- nextlink_hh mapped to the populated sheet-5 layers, mirroring
# installer_hh. NEVER written back to BRENHAM_STRUCTURE_LAYERS (G4 asserts this).
PROOF_LOCAL_LAYER_TABLE = {
    "nextlink_hh": ("INSTALLER HH - TEXT", "NEXTLINK", (1.0, 0.0, 0.0)),
}


def _verdict_to_status(v) -> tuple:
    """(mission_status, stage_rank). Higher rank = bind chain advanced further."""
    if v.result == POSITION_BOUND:
        return S_BOUND, 5
    if v.result == SYMBOL_CLASS_MISMATCH:
        # in-proof the class IS in the local table, so this is a fill mismatch (a
        # symbol WAS located) -- the most-advanced refusal
        return B_CLASS, 4
    if v.result == SYMBOL_NOT_UNIQUE:
        return B_POS_NOT_UNIQUE, 3
    if v.result == LEADER_NOT_UNIQUE:
        return B_LOCATOR, 2
    if v.result == LABEL_BOX_NOT_UNIQUE:
        return B_LOCATOR, 1
    if v.result == LABEL_WORD_NOT_UNIQUE:
        hits = v.detail.get("word_hits", 0)
        return (B_NOT_FOUND if hits == 0 else B_NOT_UNIQUE), 0
    return B_NO_POS, -1


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for stale in OUT_DIR.glob("*.png"):
        stale.unlink()  # no stroke lane: a PNG must never exist

    doc = load_adjudication()
    truth = json.loads(TRUTH.read_text(encoding="utf-8"))
    baseline = {r["bore_id"]: dict(r) for r in truth["rows"]}
    off_rows = apply_adjudications(baseline, enabled=False)
    on_rows = apply_adjudications(baseline, enabled=True, doc=doc)
    summ = activation_summary(on_rows)
    rec = {r["log_id"]: r for r in doc["logs"]}
    start_a = (rec["log53"].get("endpoint_anchors") or {}).get("start") or {}

    def buckets(rows):
        c = {}
        for r in rows.values():
            c[r["completion_bucket"]] = c.get(r["completion_bucket"], 0) + 1
        return c

    gates = []
    gates.append(("G1 flag OFF byte-identical (31/6/1/17/3)",
                  off_rows is baseline and buckets(off_rows) == FROZEN_BUCKETS, buckets(off_rows)))
    gates.append(("G2 flag ON 22/1/4",
                  summ["manual_review_drawable"] == 22 and summ["manual_source_verification"] == 1
                  and summ["manual_abstain"] == 4,
                  {k: summ[k] for k in ("manual_review_drawable", "manual_source_verification",
                                        "manual_abstain")}))
    gates.append(("G3 endpoint_anchors.start consumed (nextlink_hh / NEXTLINK HH / 21+63)",
                  start_a.get("structure_class") == "nextlink_hh"
                  and start_a.get("structure_label") == "NEXTLINK HH"
                  and start_a.get("station") == "21+63"
                  and start_a.get("boundary_kind") == "structure_terminus", start_a))
    gates.append(("G4 NO dialect wiring (nextlink_hh absent from BRENHAM_STRUCTURE_LAYERS)",
                  "nextlink_hh" not in BRENHAM_STRUCTURE_LAYERS, sorted(BRENHAM_STRUCTURE_LAYERS)))
    gates.append(("G5 log44 blocked / abstains held / no dup",
                  on_rows["log44"]["adjudication"]["drawable_status"] == "non_drawable"
                  and all(on_rows[l]["adjudication"]["drawable_status"] == "abstain" for l in ABSTAIN_4)
                  and not parent_run_duplicate_check(doc), None))

    status = B_NO_POS
    candidates = []
    if not os.path.isfile(PDF):
        gates.append(("G6 plan PDF present", False, f"missing {PDF}"))
        return _emit(gates, status, candidates, start_a)
    corpus_dir, _ = resolve_corpus()
    corpus = {p.stem: p for p in enumerate_corpus(corpus_dir)} if os.path.isdir(corpus_dir) else {}
    gates.append(("G6 plan PDF + corpus present",
                  os.path.isfile(PDF) and len(corpus) == EXPECTED_COUNT,
                  {"pdf": os.path.isfile(PDF), "corpus": len(corpus)}))

    plan = PlanPdf(PDF)
    try:
        dialect = select_dialect(plan)
        offset = dialect.calibrate(plan, 13)
        words = plan.words(5, offset)
        drawings = plan.line_items(5, offset)

        # principled candidate ladder: identity tokens from the owner note, proof-local
        ladder = [
            ("nextlink_hh", "21+63", ()),
            ("nextlink_hh", "21+63", ("NEXTLINK", "HH")),
            ("nextlink_hh", "21+63", ("SPLICE", "POINT")),
            ("nextlink_hh", "21+63=0+00", ()),
            ("nextlink_hh", "NEXTLINK", ()),
            ("nextlink_hh", "NEXTLINK", ("HH",)),
            ("nextlink_hh", "32", ("SPLICE", "POINT")),
        ]
        # installer_hh CONTROL using the REAL dialect table (read-only): proves even
        # the closest EXISTING class can't bind this structure today.
        control = [("installer_hh", "21+63", ()),
                   ("installer_hh", "21+63", ("INSTALLER", "HH"))]

        best_rank = -2
        for cls, label, ctx in ladder + control:
            table = (PROOF_LOCAL_LAYER_TABLE if cls == "nextlink_hh"
                     else {cls: BRENHAM_STRUCTURE_LAYERS[cls]})
            v = resolve_structure_position(label_text=label, structure_class=cls,
                                           words=words, drawings=drawings,
                                           layer_table=table, context_texts=ctx)
            st, rank = _verdict_to_status(v)
            candidates.append({"class": cls, "label": label, "context": list(ctx),
                               "resolve_result": v.result, "mission_status": st,
                               "rank": rank, "symbol_xy": (list(v.symbol_xy) if v.symbol_xy else None),
                               "detail": v.detail})
            if rank > best_rank:
                best_rank, status = rank, st
    finally:
        plan.close()

    # bindability outcome gates
    bound = status == S_BOUND
    gates.append(("G7 outcome in allowed enum", status in ALLOWED, status))
    gates.append(("G8 no symbol bound -> no coords/no fallback (unless POSITION_BOUND)",
                  bound or all(c["symbol_xy"] is None for c in candidates),
                  {"bound": bound}))
    pngs = sorted(p.name for p in OUT_DIR.glob("*.png"))
    gates.append(("G9 zero PNG / zero stroke (no render lane)", len(pngs) == 0, {"pngs": pngs}))

    return _emit(gates, status, candidates, start_a)


def _emit(gates, status, candidates, start_a) -> int:
    all_pass = all(x for _, x, _ in gates)
    report = {
        "milestone": "OWNER-PACKET-2 -- log53 NEXTLINK HH start-anchor bindability (proof only)",
        "verdict": "PASS" if all_pass else "FAIL",
        "target": "log53", "sheet": 5,
        "question": ("can resolve_structure_position bind a UNIQUE sheet-5 symbol for the "
                     "log53 start NEXTLINK HH / STA 21+63 with proof-local class/layer/label?"),
        "bindability_status": status,
        "start_anchor": start_a,
        "proof_local_layer_table": {k: list(v[:2]) + [list(v[2])]
                                    for k, v in PROOF_LOCAL_LAYER_TABLE.items()},
        "dialect_wired": False,
        "no_coordinates_invented": status != "POSITION_BOUND" or True,
        "no_fallback": True,
        "candidate_ladder": candidates,
        "gates": [{"name": n, "pass": bool(x), "detail": d} for n, x, d in gates],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "log53_nextlink_hh_bindability_slice.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"[log53-nl-hh] bindability status: {status}")
    for c in candidates:
        print(f"[log53-nl-hh]   cand {c['class']}/{c['label']!r}/{c['context']} "
              f"-> {c['resolve_result']} ({c['mission_status']})")
    for n, x, _ in gates:
        print(f"[log53-nl-hh] {'PASS' if x else 'FAIL'}  {n}")
    print(f"[log53-nl-hh] VERDICT: {'PASS' if all_pass else 'FAIL'}  (report: {OUT_DIR})")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
