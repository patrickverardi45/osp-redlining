r"""M8.2d -- read-only real-corpus OPT-IN frame-translation validation.

Builds a REAL FrameGraph from the plan PDF text (the same safe-edge foundation the M8.2a
probe found and M8.2b/M8.2c added) and runs the matcher TWICE per bore: DEFAULT
(``frame_graph=None``) and OPT-IN (the real graph). It compares the two per log and
reports: the default vs opt-in distribution, per-log status deltas, newly-linked
cross-frame chains, logs still blocked by anchor ambiguity / missing evidence, the log11
focus, and -- critically -- any currently-PLACED log whose result changes under opt-in
(=> NOT_SAFE). Refused (ambiguous/conflicting) frame edges are reported.

This is READ-ONLY VALIDATION, not product activation. It changes NO engine / service /
decide / default behavior: ``run_match``'s persisted/default path is never touched, the
default run must reproduce the shipped 23/58, and report artifacts are written under
``data/outputs/`` ONLY. A product claim is made ONLY if the real opt-in output proves it.

Run (repo root): $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_frame_optin_validation
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from truelinev2.config import Settings, _REPO_ROOT
from truelinev2.extract.registry import select_dialect
from truelinev2.ingest.normalize import load_borelog
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.match.engine import run_match
from truelinev2.match.frames import (
    build_frame_edges,
    build_frame_graph,
    frame_for_sheet,
    parse_frame_equations,
    translate_between_sheets,
)
from truelinev2.proof.run_brenham_corpus import CORPUS_DIR, EXPECTED_COUNT, PDF, enumerate_corpus

# Corrected-source baseline 2026-06-10 (bore_log9/15/16 station OCR fixed;
# log9 places REVIEW via the M7 unique-footage fallback): default 24/58.
GOLDEN = {"AUTO_SELECT": 14, "REVIEW": 10, "ABSTAIN": 32, "ERROR": 2}
PLACED = ("AUTO_SELECT", "REVIEW")
LOG11 = "bore_log11"


def build_plan_frame_graph(plan, offset: int):
    """Build the SAFE FrameGraph from the plan PDF text -- the same parser foundation the
    probe used (per-sheet equations -> candidate edges -> safe-edge graph). Read-only;
    keeps ONLY HIGH/unique/conflict-free edges and records the refused conflicts."""
    all_edges = []
    for idx in range(plan.page_count):
        text = " ".join(ln for ln in plan.text_by_index(idx).splitlines() if ln.strip())
        sheet = idx - offset + 1
        all_edges.extend(build_frame_edges(parse_frame_equations(text), frame_for_sheet(sheet)))
    return build_frame_graph(all_edges)


def _run(bore, plan, dialect, offset, frame_graph) -> Dict[str, Any]:
    pl = run_match(bore, plan, dialect, offset, frame_graph=frame_graph)
    return {"status": pl.status.value, "tier": pl.tier, "reason": pl.reason,
            "sheets": list(pl.sheets), "station_span": pl.station_span}


def _dist(rows: List[Dict[str, Any]], key: str) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for r in rows:
        out[r[key]] = out.get(r[key], 0) + 1
    return out


def _safe_pairs_for(graph, sheet_refs: List[int]) -> List[List[int]]:
    """Sheet pairs among ``sheet_refs`` that are connected by a SAFE edge (translatable)."""
    pairs = []
    for a in sheet_refs:
        for b in sheet_refs:
            if a != b and translate_between_sheets(graph, a, b, 0.0) is not None:
                key = sorted([a, b])
                if key not in pairs:
                    pairs.append(key)
    return pairs


def main() -> int:
    out_dir = _REPO_ROOT / "data" / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path, md_path = out_dir / "frame_optin_validation.json", out_dir / "frame_optin_validation.md"

    if not os.path.isfile(PDF) or not os.path.isdir(CORPUS_DIR):
        report = {"status": "INPUTS_MISSING", "pdf": PDF, "corpus_dir": CORPUS_DIR,
                  "conclusion": "NEEDS_MORE_EVIDENCE"}
        json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"[m8.2d] STOP: inputs missing (pdf={os.path.isfile(PDF)} corpus={os.path.isdir(CORPUS_DIR)})")
        return 2
    corpus = enumerate_corpus(CORPUS_DIR)
    if len(corpus) != EXPECTED_COUNT:
        print(f"[m8.2d] STOP: expected {EXPECTED_COUNT} logs, got {len(corpus)} -- corpus drift.")
        return 3

    offset = Settings.for_proof().sheet_offset
    plan = PlanPdf(PDF)
    dialect = select_dialect(plan)
    graph = build_plan_frame_graph(plan, offset)

    rows: List[Dict[str, Any]] = []
    for p in corpus:
        try:
            bore = load_borelog(str(p))
        except Exception as e:  # ingest failure -> ERROR in BOTH runs (matches the sweep)
            rows.append({"bore_id": p.stem, "source_file": p.name, "sheet_refs": [],
                         "status_default": "ERROR", "status_optin": "ERROR",
                         "changed": False, "safe_pairs": [], "error": f"{type(e).__name__}: {e}"})
            continue
        d = _run(bore, plan, dialect, offset, None)
        o = _run(bore, plan, dialect, offset, graph)
        rows.append({
            "bore_id": bore.bore_id, "source_file": p.name, "sheet_refs": list(bore.sheet_refs),
            "status_default": d["status"], "status_optin": o["status"],
            "changed": d["status"] != o["status"], "default": d, "optin": o,
            "safe_pairs": _safe_pairs_for(graph, list(bore.sheet_refs)),
        })
    plan.close()

    default_dist, optin_dist = _dist(rows, "status_default"), _dist(rows, "status_optin")
    default_placed = sum(1 for r in rows if r["status_default"] in PLACED)
    optin_placed = sum(1 for r in rows if r["status_optin"] in PLACED)
    changed = [r for r in rows if r["changed"]]
    placed_changed = [r for r in changed if r["status_default"] in PLACED]      # the UNSAFE case
    newly_placed = [r for r in changed if r["status_default"] not in PLACED and r["status_optin"] in PLACED]
    auto_promotions = [r for r in changed if r["status_optin"] == "AUTO_SELECT" and r["status_default"] != "AUTO_SELECT"]
    optin_linked = [r for r in rows if r["safe_pairs"]]                          # bores whose sheets have a safe edge

    log11 = next((r for r in rows if r["bore_id"] == LOG11 or r["source_file"].startswith(LOG11)), None)
    log11_report = None
    if log11:
        log11_report = {
            "sheet_refs": log11["sheet_refs"],
            "safe_frame_edge_present": bool(log11["safe_pairs"]),
            "safe_pairs": log11["safe_pairs"],
            "status_default": log11["status_default"], "status_optin": log11["status_optin"],
            "translated_link_possible": bool(log11["safe_pairs"]),
            "status_changed": log11["changed"],
            "auto_promotion": log11["status_optin"] == "AUTO_SELECT" and log11["status_default"] != "AUTO_SELECT",
            "anchor_ambiguity_still_blocks": log11["status_optin"] == "ABSTAIN",
            "default_reason": log11["default"]["reason"] if "default" in log11 else None,
            "optin_reason": log11["optin"]["reason"] if "optin" in log11 else None,
        }

    default_matches_golden = all(default_dist.get(k, 0) == v for k, v in GOLDEN.items())
    if not default_matches_golden:
        conclusion = "NOT_SAFE"
        why = "default run did NOT reproduce the 23/58 golden -- opt-in comparison is untrustworthy"
    elif placed_changed:
        conclusion = "NOT_SAFE"
        why = f"{len(placed_changed)} currently-PLACED log(s) change status under opt-in"
    elif newly_placed or auto_promotions:
        conclusion = "NEEDS_MORE_EVIDENCE"
        why = ("opt-in surfaces new placement(s)/promotion(s) that REQUIRE visual grading before any "
               "product claim (no placed log regressed)")
    else:
        conclusion = "IMPLEMENTABLE"
        why = ("opt-in is behavior-safe on the real corpus: no placed log changed and no unverified "
               "promotion occurred (mechanics validated, zero regression)")

    report = {
        "milestone": "truelinev2 M8.2d -- real-corpus opt-in frame-translation validation (read-only)",
        "read_only": True, "default_run_match_unchanged": True,
        "pdf": PDF, "corpus_dir": CORPUS_DIR, "sheet_offset": offset, "logs": len(rows),
        "frame_graph": {"safe_edges": len(graph.edges),
                        "refused_conflicts": [c.model_dump() for c in graph.conflicts]},
        "default_distribution": default_dist, "default_placed": default_placed,
        "default_matches_golden": default_matches_golden, "golden": GOLDEN,
        "optin_distribution": optin_dist, "optin_placed": optin_placed,
        "status_changes": len(changed),
        "placed_logs_changed": [{"bore_id": r["bore_id"], "default": r["status_default"],
                                 "optin": r["status_optin"], "sheet_refs": r["sheet_refs"]}
                                for r in placed_changed],
        "newly_placed_under_optin": [{"bore_id": r["bore_id"], "optin": r["status_optin"],
                                      "sheet_refs": r["sheet_refs"]} for r in newly_placed],
        "auto_promotions": [r["bore_id"] for r in auto_promotions],
        "bores_with_safe_edge_between_sheets": [r["bore_id"] for r in optin_linked],
        "log11": log11_report,
        "rows": rows,
        "conclusion": conclusion, "conclusion_reason": why,
        "product_claim": ("NONE -- this is mechanics/safety validation; product readiness requires "
                          "visual grading of any opt-in placements, which this script does not do."),
    }
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    md = "\n".join([
        "# M8.2d -- real-corpus opt-in frame-translation validation (read-only)",
        "",
        f"- safe frame edges in graph: **{len(graph.edges)}**  ·  refused conflicts: **{len(graph.conflicts)}**",
        f"- DEFAULT distribution: `{default_dist}`  (placed={default_placed}; matches 23/58 golden: "
        f"**{default_matches_golden}**)",
        f"- OPT-IN distribution:  `{optin_dist}`  (placed={optin_placed})",
        f"- status changes: **{len(changed)}**  ·  placed-log changes (unsafe): **{len(placed_changed)}**  ·  "
        f"newly placed: **{len(newly_placed)}**  ·  auto promotions: **{len(auto_promotions)}**",
        f"- bores whose sheets share a safe edge: {[r['bore_id'] for r in optin_linked]}",
        "",
        "## Placed-log changes (must be empty to be safe)",
        (json.dumps(report["placed_logs_changed"], indent=2) if placed_changed else "  - (none)"),
        "",
        "## log11",
        (json.dumps(log11_report, indent=2) if log11_report else "  - (not found)"),
        "",
        f"## CONCLUSION: {conclusion}",
        f"{why}",
        "",
        f"**Product claim:** {report['product_claim']}",
    ])
    md_path.write_text(md + "\n", encoding="utf-8")

    print(f"[m8.2d] safe_edges={len(graph.edges)} conflicts={len(graph.conflicts)}")
    print(f"[m8.2d] DEFAULT {default_dist} placed={default_placed} golden_ok={default_matches_golden}")
    print(f"[m8.2d] OPT-IN  {optin_dist} placed={optin_placed}")
    print(f"[m8.2d] changes={len(changed)} placed_changed={len(placed_changed)} "
          f"newly_placed={len(newly_placed)} auto_promotions={len(auto_promotions)}")
    if log11_report:
        print(f"[m8.2d] log11 sheets={log11_report['sheet_refs']} safe_edge={log11_report['safe_frame_edge_present']} "
              f"default={log11_report['status_default']} optin={log11_report['status_optin']} "
              f"auto_promotion={log11_report['auto_promotion']}")
    print(f"[m8.2d] CONCLUSION: {conclusion} -- {why}")
    print(f"[m8.2d] report -> {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
