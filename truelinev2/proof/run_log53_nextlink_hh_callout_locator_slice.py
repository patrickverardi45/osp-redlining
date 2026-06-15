r"""OWNER-PACKET-2 -- log53 NEXTLINK HH callout-locator slice (PROOF for the first impl).

After SOURCE_FEATURE_PRESENT_DIALECT_GAP_CONFIRMED, this re-runs the log53 START binding
through the NEW bounded locator ``extract.structure_position.resolve_nextlink_hh_callout``
(ANNOTATION callout grammar -> ANNOTATION leader -> NEXTLINK square symbol). It proves
whether the start anchor now binds to the source-backed NEXTLINK HH symbol -- or names the
exact strict gate that still refuses.

Inputs are the committed endpoint_anchors.start (station 21+63, NEXTLINK HH) consumed from
the artifact -- NOT hardcoded. The callout/symbol LAYER names are injected here (the locator
holds no plan-set defaults); this proof does NOT wire them into the shared dialect.

No production placement, no renderer output, no stroke, no PNG, no dialect wiring, no
screenshot-pixel geometry, no invented coordinates (only real PDF/CAD extraction). Proof-only;
artifacts gitignored. Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_log53_nextlink_hh_callout_locator_slice
"""
from __future__ import annotations

import json
import os

from truelinev2.config import _REPO_ROOT
from truelinev2.extract.registry import select_dialect
from truelinev2.extract.structure_position import POSITION_BOUND, resolve_nextlink_hh_callout
from truelinev2.ingest.manual_adjudication import (
    activation_summary,
    apply_adjudications,
    load_adjudication,
    parent_run_duplicate_check,
)
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.proof.run_brenham_corpus import EXPECTED_COUNT, PDF, enumerate_corpus
from truelinev2.proof.run_reviewer_service_contract import resolve_corpus

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "log53_nextlink_hh_callout_locator_slice"
TRUTH = _REPO_ROOT / "data" / "outputs" / "final_engine_truth_table" / \
    "final_engine_truth_table.json"
# Brenham source layers for the start callout (INJECTED here; not wired into the dialect)
CALLOUT_LAYER = "ANNOTATION"
SYMBOL_LAYER = "NEXTLINK"
FROZEN_BUCKETS = {"DRAWABLE_REVIEW": 31, "HUMAN_ADJUSTABLE_REVIEW": 6,
                  "OUT_OF_CLASS": 1, "PICK_CARD_REVIEW": 17, "SOURCE_OR_KMZ_REQUIRED": 3}
ABSTAIN_4 = ("log5", "log31", "log38", "log43")

S_BOUND = "POSITION_BOUND"
ALLOWED = {S_BOUND, "BLOCKED_CALLOUT_NOT_FOUND", "BLOCKED_CALLOUT_NOT_UNIQUE",
           "BLOCKED_LEADER_NOT_FOUND", "BLOCKED_LEADER_NOT_UNIQUE",
           "BLOCKED_SYMBOL_NOT_FOUND", "BLOCKED_SYMBOL_NOT_UNIQUE",
           "BLOCKED_CALLOUT_SYMBOL_DISCONNECTED", "BLOCKED_LOCATOR_NOT_AVAILABLE"}


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for stale in OUT_DIR.glob("*.png"):
        stale.unlink()  # no render/stroke lane: a PNG must never exist

    doc = load_adjudication()
    truth = json.loads(TRUTH.read_text(encoding="utf-8"))
    baseline = {r["bore_id"]: dict(r) for r in truth["rows"]}
    off_rows = apply_adjudications(baseline, enabled=False)
    on_rows = apply_adjudications(baseline, enabled=True, doc=doc)
    summ = activation_summary(on_rows)
    rec = {r["log_id"]: r for r in doc["logs"]}
    start_a = (rec["log53"].get("endpoint_anchors") or {}).get("start") or {}
    station = start_a.get("station")

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
                  and summ["manual_abstain"] == 4, None))
    gates.append(("G3 endpoint_anchors.start consumed (nextlink_hh / NEXTLINK HH / 21+63)",
                  start_a.get("structure_class") == "nextlink_hh"
                  and start_a.get("structure_label") == "NEXTLINK HH" and station == "21+63", start_a))
    gates.append(("G4 log44 blocked / abstains held / no dup",
                  on_rows["log44"]["adjudication"]["drawable_status"] == "non_drawable"
                  and all(on_rows[l]["adjudication"]["drawable_status"] == "abstain" for l in ABSTAIN_4)
                  and not parent_run_duplicate_check(doc), None))

    status = "BLOCKED_LOCATOR_NOT_AVAILABLE"
    ev = {}
    if not os.path.isfile(PDF):
        gates.append(("G5 plan PDF present", False, f"missing {PDF}"))
        return _emit(gates, status, ev)
    corpus_dir, _ = resolve_corpus()
    corpus = {p.stem: p for p in enumerate_corpus(corpus_dir)} if os.path.isdir(corpus_dir) else {}
    gates.append(("G5 plan PDF + corpus present",
                  os.path.isfile(PDF) and len(corpus) == EXPECTED_COUNT,
                  {"pdf": os.path.isfile(PDF), "corpus": len(corpus)}))

    plan = PlanPdf(PDF)
    try:
        dialect = select_dialect(plan)
        offset = dialect.calibrate(plan, 13)
        words = plan.words(5, offset)
        draw = plan.line_items(5, offset)
        v = resolve_nextlink_hh_callout(station_sta=station, words=words, drawings=draw,
                                        callout_layer=CALLOUT_LAYER, symbol_layer=SYMBOL_LAYER)
        status = S_BOUND if v.result == POSITION_BOUND else v.result
        ev = {
            "resolve_result": v.result,
            "callout_source_layer": CALLOUT_LAYER,
            "leader_source_layer": CALLOUT_LAYER,
            "symbol_source_layer": SYMBOL_LAYER,
            "callout_word_xy": [round(c, 1) for c in v.word_xy] if v.word_xy else None,
            "callout_box": [round(c, 1) for c in v.label_box] if v.label_box else None,
            "leader": [round(c, 1) for c in v.leader] if v.leader else None,
            "bound_symbol_center": [round(c, 1) for c in v.symbol_xy] if v.symbol_xy else None,
            "detail": v.detail,
            "named_missing": v.named_missing_relationship,
            "screenshot_pixels_used": False,
        }
    finally:
        plan.close()

    return _emit(gates, status, ev)


def _emit(gates, status, ev) -> int:
    gates.append(("G6 result in allowed enum", status in ALLOWED, status))
    bound = status == S_BOUND
    gates.append(("G7 symbol center present iff POSITION_BOUND (real extraction, no invention)",
                  (bound and ev.get("bound_symbol_center")) or
                  (not bound and not ev.get("bound_symbol_center")), ev.get("bound_symbol_center")))
    pngs = sorted(p.name for p in OUT_DIR.glob("*.png"))
    gates.append(("G8 zero PNG / zero stroke (no render lane)", len(pngs) == 0, {"pngs": pngs}))
    all_pass = all(x for _, x, _ in gates)
    report = {
        "milestone": "OWNER-PACKET-2 -- log53 NEXTLINK HH callout-locator slice (proof for first impl)",
        "verdict": "PASS" if all_pass else "FAIL",
        "target": "log53", "sheet": 5,
        "question": ("does the new resolve_nextlink_hh_callout bind log53's start NEXTLINK HH via "
                     "ANNOTATION callout -> leader -> NEXTLINK symbol?"),
        "start_bindability_status": status,
        "evidence": ev,
        "dialect_wired": False,
        "no_screenshot_pixels": True,
        "gates": [{"name": n, "pass": bool(x), "detail": d} for n, x, d in gates],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "log53_nextlink_hh_callout_locator_slice.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"[log53-loc] start_bindability_status: {status}")
    for k in ("callout_source_layer", "leader_source_layer", "symbol_source_layer",
              "bound_symbol_center", "callout_box", "leader"):
        if ev.get(k) is not None:
            print(f"[log53-loc]   {k}: {ev[k]}")
    if ev.get("named_missing"):
        print(f"[log53-loc]   named_missing: {ev['named_missing'][:160]}")
    for n, x, _ in gates:
        print(f"[log53-loc] {'PASS' if x else 'FAIL'}  {n}")
    print(f"[log53-loc] VERDICT: {'PASS' if all_pass else 'FAIL'}  (report: {OUT_DIR})")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
