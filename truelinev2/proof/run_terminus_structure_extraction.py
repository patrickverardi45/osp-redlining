r"""M8.3b -- terminus-structure extraction PROOF (read-only; extraction quality, not placement).

Sweeps the corpus and, for every callout on every loadable bore's print sheets,
extracts terminus/access-structure evidence from (a) the callout box's textual tail
lines and (b) the words near its bbox -- then reports corpus-wide extraction quality,
the log48 two-route detail, and which blocked logs gain usable identity evidence.

READ-ONLY: no engine/decide/chains/gate change; nothing consumes this evidence for
placement; default behavior unchanged. Outputs to gitignored data/outputs/ only.

Run (repo root): $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_terminus_structure_extraction
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from truelinev2.config import Settings, _REPO_ROOT
from truelinev2.extract.registry import select_dialect
from truelinev2.ingest.normalize import load_borelog
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.proof.run_brenham_corpus import CORPUS_DIR, EXPECTED_COUNT, PDF, enumerate_corpus
from truelinev2.proof.terminus_structure_extraction import (
    classify_structure_text,
    extract_from_tail,
    merge_evidence,
)

OUT_JSON = _REPO_ROOT / "data" / "outputs" / "terminus_structure_extraction.json"
OUT_MD = _REPO_ROOT / "data" / "outputs" / "terminus_structure_extraction.md"
NEAR_X, NEAR_Y = 200.0, 120.0
# The 33 currently-abstaining logs (banked default sweep) for the gains report.
ABSTAINING = {"log5", "log6", "log7", "log9", "log11", "log12", "log15", "log16", "log27",
              "log29", "log31", "log36", "log41", "log43", "log44", "log45", "log46",
              "log47", "log48", "log52", "log53", "log54", "log58", "log59", "log63",
              "log64", "log66", "log67", "log68", "log69", "log70", "log71", "log72"}


def _nearby_text(plan: PlanPdf, sheet: int, offset: int, bbox: Optional[List[float]]) -> str:
    if not bbox:
        return ""
    cx, cy = (bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0
    return " ".join(w["text"] for w in plan.words(sheet, offset)
                    if abs(w["xc"] - cx) <= NEAR_X and abs(w["yc"] - cy) <= NEAR_Y)


def main() -> int:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    if not os.path.isfile(PDF) or not os.path.isdir(CORPUS_DIR):
        print("[m8.3b] STOP: inputs missing")
        return 2
    corpus = enumerate_corpus(CORPUS_DIR)
    if len(corpus) != EXPECTED_COUNT:
        print(f"[m8.3b] STOP: corpus drift ({len(corpus)})")
        return 3

    settings = Settings.for_proof()
    plan = PlanPdf(PDF)
    dialect = select_dialect(plan)
    offset = dialect.calibrate(plan, settings.sheet_offset)

    lines_cache: Dict[int, List[str]] = {}
    per_log: List[Dict[str, Any]] = []
    total_callouts = with_class = with_identity = 0
    tail_with_class = tail_with_identity = 0
    class_hist: Dict[str, int] = {}
    tail_hist: Dict[str, int] = {}

    for p in corpus:
        try:
            bore = load_borelog(str(p))
        except Exception as e:
            per_log.append({"bore_id": p.stem.replace("bore_log", "log"),
                            "error": f"{type(e).__name__}"})
            continue
        rows: List[Dict[str, Any]] = []
        for s in bore.sheet_refs:
            if s not in lines_cache:
                lines_cache[s] = plan.lines(s, offset)
            for c in dialect.extract_callouts(plan, s, offset):
                tail_ev = extract_from_tail(lines_cache[s], c.from_sta, c.to_sta)
                near_ev = classify_structure_text(_nearby_text(plan, s, offset, c.bbox),
                                                  source="nearby_words")
                ev = merge_evidence(tail_ev, near_ev)
                total_callouts += 1
                if ev.has_structure:
                    with_class += 1
                if ev.has_identity:
                    with_identity += 1
                if tail_ev.has_structure:
                    tail_with_class += 1
                if tail_ev.has_identity:
                    tail_with_identity += 1
                for k in ev.classes:
                    class_hist[k] = class_hist.get(k, 0) + 1
                for k in tail_ev.classes:
                    tail_hist[k] = tail_hist.get(k, 0) + 1
                rows.append({"sheet": s, "span": f"{c.from_sta}->{c.to_sta}",
                             "tail": tail_ev.to_dict(), "merged": ev.to_dict()})
        ids = sorted({i for r in rows for i in r["merged"]["ap_ids"]})
        classes = sorted({k for r in rows for k in r["merged"]["classes"]})
        per_log.append({"bore_id": bore.bore_id, "sheets": list(bore.sheet_refs),
                        "n_callouts": len(rows),
                        "n_with_structure": sum(1 for r in rows if r["merged"]["classes"]),
                        "n_with_identity": sum(1 for r in rows if r["merged"]["has_identity"]),
                        "classes_seen": classes, "ap_ids_seen": ids,
                        "abstaining": bore.bore_id in ABSTAINING,
                        "callouts": rows})
    plan.close()

    # log48 two-route focus (the M8.3a routes' END boxes)
    l48 = next((r for r in per_log if r.get("bore_id") == "log48"), {})
    def _find(rows, sheet, span_prefix):
        return [r for r in rows if r["sheet"] == sheet and r["span"].startswith(span_prefix)]
    log48_routes = {
        "route0_s12_end": [r["merged"] for r in _find(l48.get("callouts", []), 12, "3+5")],
        "route1_s11_end": [r["merged"] for r in _find(l48.get("callouts", []), 11, "1+89")],
    }

    gains = [{"bore_id": r["bore_id"], "classes": r["classes_seen"], "ap_ids": r["ap_ids_seen"],
              "identity_callouts": r["n_with_identity"]}
             for r in per_log
             if r.get("abstaining") and (r.get("classes_seen") or r.get("ap_ids_seen"))]

    report = {
        "milestone": "truelinev2 M8.3b -- terminus-structure extraction proof (read-only)",
        "read_only": True, "default_behavior_changed": False,
        "totals": {"callouts": total_callouts, "with_structure_class": with_class,
                   "with_named_identity": with_identity,
                   "structure_rate": round(with_class / max(1, total_callouts), 3),
                   "identity_rate": round(with_identity / max(1, total_callouts), 3)},
        "tail_only_totals": {
            "note": ("tail-lines = the callout box's OWN text (precise, per-callout terminus); "
                     "merged adds a 200x120 nearby-word window which OVER-COLLECTS adjacent "
                     "leader blocks on dense sheets -- window evidence is CONTEXT, not the "
                     "callout's own terminus"),
            "with_structure_class": tail_with_class,
            "with_named_identity": tail_with_identity,
            "structure_rate": round(tail_with_class / max(1, total_callouts), 3),
            "identity_rate": round(tail_with_identity / max(1, total_callouts), 3),
            "class_histogram": dict(sorted(tail_hist.items(), key=lambda kv: -kv[1]))},
        "class_histogram": dict(sorted(class_hist.items(), key=lambda kv: -kv[1])),
        "log48_two_routes": log48_routes,
        "abstaining_logs_with_new_identity_evidence": gains,
        "per_log": [{k: v for k, v in r.items() if k != "callouts"} for r in per_log],
    }
    OUT_JSON.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    L = ["# M8.3b -- terminus-structure extraction (read-only proof)", "",
         f"- callouts scanned: **{total_callouts}**",
         f"- with a structure class: **{with_class}** ({report['totals']['structure_rate']:.0%})",
         f"- with a NAMED identity (AP-N / SPLICE LOC N): **{with_identity}** "
         f"({report['totals']['identity_rate']:.0%})",
         f"- class histogram: {report['class_histogram']}", "",
         "## log48 two-route terminus evidence",
         f"- route 0 (s10->s12) end callouts: {json.dumps(log48_routes['route0_s12_end'], default=str)}",
         f"- route 1 (s10->s11) end callouts: {json.dumps(log48_routes['route1_s11_end'], default=str)}", "",
         "## Abstaining logs gaining identity/terminus evidence",
         ]
    for g in gains:
        L.append(f"- {g['bore_id']}: classes={g['classes']} ap_ids={g['ap_ids']} "
                 f"identity_callouts={g['identity_callouts']}")
    OUT_MD.write_text("\n".join(L) + "\n", encoding="utf-8")

    print(f"[m8.3b] callouts={total_callouts} merged: structure={with_class} identity={with_identity}")
    print(f"[m8.3b] TAIL-ONLY: structure={tail_with_class} identity={tail_with_identity} "
          f"classes={report['tail_only_totals']['class_histogram']}")
    print(f"[m8.3b] merged classes: {report['class_histogram']}")
    print(f"[m8.3b] log48 r0(s12-end): {[e['classes'] for e in log48_routes['route0_s12_end']]} "
          f"ids={[e['ap_ids'] for e in log48_routes['route0_s12_end']]}")
    print(f"[m8.3b] log48 r1(s11-end): {[e['classes'] for e in log48_routes['route1_s11_end']]} "
          f"ids={[e['ap_ids'] for e in log48_routes['route1_s11_end']]}")
    print(f"[m8.3b] abstaining logs w/ new evidence: {[g['bore_id'] for g in gains]}")
    print(f"[m8.3b] report -> {OUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
