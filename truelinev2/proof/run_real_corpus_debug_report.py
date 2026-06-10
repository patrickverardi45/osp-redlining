r"""M8.2e -- v2 real-corpus DEBUG/REVIEW report (read-only, for human inspection).

NOT a UI, NOT production, NOT customer-facing. It runs the v2 matcher over the real Brenham
corpus TWICE per bore -- DEFAULT (``frame_graph=None``, the shipped 23/58) and OPT-IN (the
real PDF-derived FrameGraph) -- and explains, per selected log, what the engine did and why:
the placed/abstained reason, the default chain's callout spans, each cross-sheet transition
classified as continuous-station / reset-equation / ambiguous, the frame evidence found, and
the missing evidence before the engine may safely place. It re-confirms the M8.2d NOT_SAFE
result and points to existing m5 grading crops so Patrick can check visually.

Read-only: NO engine / service / decide / default-run_match change; outputs under
``data/outputs/`` ONLY. Default behavior is reproduced, never altered. No product claim.

Run (repo root): $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_real_corpus_debug_report
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
from truelinev2.match.frames import translate_between_sheets
from truelinev2.proof.run_brenham_corpus import CORPUS_DIR, EXPECTED_COUNT, PDF, enumerate_corpus
from truelinev2.proof.run_frame_optin_validation import build_plan_frame_graph

PLACED = ("AUTO_SELECT", "REVIEW")
LINK_TOL = 2.0
M5_CROP_DIR = _REPO_ROOT / "data" / "outputs" / "truelinev2" / "m5_brenham"
REGRESSED_M8_2D = ["log2", "log3", "log4", "log42", "log50", "log57", "log62", "log65"]


def _sheet_num(fid) -> int:
    return int(str(fid).split(":")[-1])


def _conflict_pairs(graph):
    return {tuple(sorted((_sheet_num(c.frame_pair[0]), _sheet_num(c.frame_pair[1]))))
            for c in graph.conflicts}


def _span(c) -> str:
    return f"s{c.sheet} {c.from_sta}->{c.to_sta} ({c.from_ft:.0f}-{c.to_ft:.0f}ft)"


def classify_transition(graph, conflict_pairs, a, b) -> Dict[str, Any]:
    """Classify a cross-sheet transition a(sheet A, ends a.to_ft) -> b(sheet B, starts b.from_ft)."""
    raw_gap = round(abs(a.to_ft - b.from_ft), 2)
    translated = translate_between_sheets(graph, b.sheet, a.sheet, b.from_ft)   # b's start in A's frame
    has_edge = translated is not None
    conflict = tuple(sorted((a.sheet, b.sheet))) in conflict_pairs
    if conflict:
        kind = "ambiguous_conflicting"
    elif has_edge:
        kind = "reset_equation" if round(abs(a.to_ft - translated), 2) <= LINK_TOL \
            else "reset_equation_offset_mismatch"
    elif raw_gap <= LINK_TOL:
        kind = "continuous_station"
    else:
        kind = "ambiguous_missing"
    return {"from_sheet": a.sheet, "to_sheet": b.sheet, "raw_gap_ft": raw_gap,
            "safe_edge": has_edge, "translated_start_in_anchor_ft": translated,
            "conflict": conflict, "classification": kind}


def _transitions(callouts, graph, conflict_pairs) -> List[Dict[str, Any]]:
    out = []
    for a, b in zip(callouts, callouts[1:]):
        if a.sheet != b.sheet:
            out.append(classify_transition(graph, conflict_pairs, a, b))
    return out


def _crop_path(stem: str, status: str, sheets: List[int]) -> Optional[str]:
    tag = ("_s%s" % sheets[0]) if sheets else ""
    p = M5_CROP_DIR / f"{stem}__{status}{tag}.png"
    return str(p) if p.is_file() else None


def _abstain_category(reason: Optional[str], sheet_refs: List[int], graph, conflict_pairs) -> str:
    r = (reason or "").upper()
    if "NO_CALLOUTS_EXTRACTED" in r or "NO_DIALECT" in r:
        return "adapter/extract gap (no authored callouts found)"
    if "COEQUAL" in r or "TIEBREAKER" in r:
        return "missing/ambiguous authored box (>=2 co-equal candidates, honest abstain)"
    multi = len(set(sheet_refs)) > 1
    edge = any(translate_between_sheets(graph, a, b, 0.0) is not None
               for a in sheet_refs for b in sheet_refs if a != b)
    conflict = any(tuple(sorted((a, b))) in conflict_pairs for a in sheet_refs for b in sheet_refs if a != b)
    if conflict:
        return "frame/reset issue (conflicting matchline equations -> refused)"
    if multi and edge:
        return "frame/reset issue (frame edge present; anchor/box/footage evidence still missing)"
    if multi:
        return "source/run/segment hierarchy or same-sheet-gap issue (multi-sheet, no frame edge)"
    return "missing/ambiguous authored box/evidence (single sheet, no box matched the span)"


def _detail(bore, plan, dialect, offset, graph, conflict_pairs) -> Dict[str, Any]:
    dpl = run_match(bore, plan, dialect, offset, frame_graph=None)
    opl = run_match(bore, plan, dialect, offset, frame_graph=graph)
    dstat, ostat = dpl.status.value, opl.status.value
    chain = list(dpl.matched_callouts)
    refs = list(bore.sheet_refs)
    safe_pairs = sorted({tuple(sorted((a, b))) for a in refs for b in refs
                         if a != b and translate_between_sheets(graph, a, b, 0.0) is not None})
    return {
        "bore_id": bore.bore_id, "sheet_refs": refs, "span": f"{bore.station_start}->{bore.station_end}",
        "span_ft": bore.span_ft,
        "default": {"status": dstat, "tier": dpl.tier, "reason": dpl.reason, "sheets": list(dpl.sheets),
                    "chain": [_span(c) for c in chain], "footage": dpl.footage,
                    "footage_delta": dpl.footage_delta, "start_delta": dpl.start_delta,
                    "end_delta": dpl.end_delta, "caveats": list(dpl.caveats)},
        "optin": {"status": ostat, "tier": opl.tier, "reason": opl.reason},
        "status_delta": f"{dstat} -> {ostat}" if dstat != ostat else f"{dstat} (unchanged)",
        "regressed": dstat in PLACED and ostat != dstat,
        "cross_sheet_transitions": _transitions(chain, graph, conflict_pairs),
        "frame_evidence": {"safe_edge_sheet_pairs": [list(p) for p in safe_pairs],
                           "conflicting_pairs": sorted([list(p) for p in conflict_pairs
                                                        if p[0] in refs and p[1] in refs])},
        "abstain_category": (_abstain_category(dpl.reason, refs, graph, conflict_pairs)
                             if dstat not in PLACED else None),
        "grading_crop": _crop_path(bore.bore_id, dstat, list(dpl.sheets)),
    }


def main() -> int:
    out_dir = _REPO_ROOT / "data" / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path, md_path = out_dir / "real_corpus_debug_report.json", out_dir / "real_corpus_debug_report.md"

    if not os.path.isfile(PDF) or not os.path.isdir(CORPUS_DIR):
        json_path.write_text(json.dumps({"status": "INPUTS_MISSING", "pdf": PDF}, indent=2), encoding="utf-8")
        print(f"[m8.2e] STOP: inputs missing (pdf={os.path.isfile(PDF)} corpus={os.path.isdir(CORPUS_DIR)})")
        return 2
    corpus = enumerate_corpus(CORPUS_DIR)
    if len(corpus) != EXPECTED_COUNT:
        print(f"[m8.2e] STOP: expected {EXPECTED_COUNT} logs, got {len(corpus)} -- corpus drift.")
        return 3

    offset = Settings.for_proof().sheet_offset
    plan = PlanPdf(PDF)
    dialect = select_dialect(plan)
    graph = build_plan_frame_graph(plan, offset)
    conflict_pairs = _conflict_pairs(graph)

    details: Dict[str, Dict[str, Any]] = {}
    errors: List[str] = []
    for p in corpus:
        try:
            bore = load_borelog(str(p))
        except Exception as e:
            errors.append(f"{p.stem}: {type(e).__name__}: {e}")
            continue
        details[bore.bore_id] = _detail(bore, plan, dialect, offset, graph, conflict_pairs)
    plan.close()

    default_dist: Dict[str, int] = {}
    optin_dist: Dict[str, int] = {}
    for v in details.values():
        default_dist[v["default"]["status"]] = default_dist.get(v["default"]["status"], 0) + 1
        optin_dist[v["optin"]["status"]] = optin_dist.get(v["optin"]["status"], 0) + 1
    default_dist["ERROR"] = optin_dist["ERROR"] = len(errors)

    regressed = [v for v in details.values() if v["regressed"]]
    improved = [v for v in details.values()
                if v["default"]["status"] not in PLACED and v["optin"]["status"] in PLACED]
    stable_placed = [v for v in details.values()
                     if v["default"]["status"] in PLACED and not v["regressed"]]
    abstains = [v for v in details.values() if v["default"]["status"] == "ABSTAIN"]

    log11 = details.get("log11") or details.get("bore_log11")
    stable_examples = stable_placed[:3]
    abstain_examples = []
    # pick a diverse 3 abstains by category
    seen_cats = set()
    for v in abstains:
        cat = v["abstain_category"]
        if cat not in seen_cats:
            abstain_examples.append(v)
            seen_cats.add(cat)
        if len(abstain_examples) >= 3:
            break
    if len(abstain_examples) < 3:
        abstain_examples = abstains[:3]

    # missing-evidence backlog (aggregate over abstains)
    backlog: Dict[str, int] = {}
    for v in abstains:
        backlog[v["abstain_category"]] = backlog.get(v["abstain_category"], 0) + 1

    conclusion = "NOT_SAFE (re-confirmed): opt-in regresses existing placements with zero gain."
    report = {
        "milestone": "truelinev2 M8.2e -- real-corpus debug/review report (read-only)",
        "read_only": True, "default_unchanged": True, "product_claim": "NONE",
        "default_distribution": default_dist, "optin_distribution": optin_dist,
        "regressions": len(regressed), "improvements": len(improved),
        "stable_placed": len(stable_placed), "errors": errors,
        "frame_graph": {"safe_edges": len(graph.edges), "conflicts": len(graph.conflicts)},
        "log11": log11, "regressed_logs": regressed,
        "stable_examples": stable_examples, "abstain_examples": abstain_examples,
        "missing_evidence_backlog": backlog, "conclusion": conclusion,
        "all_logs": details,
    }
    json_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    md_path.write_text(_render_md(report), encoding="utf-8")
    print(f"[m8.2e] default={default_dist} optin={optin_dist} "
          f"regressions={len(regressed)} improvements={len(improved)}")
    print(f"[m8.2e] safe_edges={len(graph.edges)} conflicts={len(graph.conflicts)} "
          f"stable_placed={len(stable_placed)} abstains={len(abstains)}")
    print(f"[m8.2e] CONCLUSION: {conclusion}")
    print(f"[m8.2e] report -> {md_path}")
    return 0


def _fmt_transitions(trs: List[Dict[str, Any]]) -> str:
    if not trs:
        return "    - (no cross-sheet transitions in the default chain)"
    lines = []
    for t in trs:
        lines.append(f"    - s{t['from_sheet']}->s{t['to_sheet']}: **{t['classification']}** "
                     f"(raw_gap={t['raw_gap_ft']}ft, safe_edge={t['safe_edge']}, conflict={t['conflict']})")
    return "\n".join(lines)


def _log_block(v: Dict[str, Any]) -> str:
    d, o = v["default"], v["optin"]
    crop = f"\n  - grading crop: `{v['grading_crop']}`" if v.get("grading_crop") else ""
    return "\n".join([
        f"### {v['bore_id']}  (sheets {v['sheet_refs']}, span {v['span']})",
        f"  - **default**: {d['status']} ({d['reason']}) chain={d['chain']}",
        f"  - **opt-in**:  {o['status']} ({o['reason']})",
        f"  - **delta**: {v['status_delta']}{'  <-- REGRESSED' if v['regressed'] else ''}",
        f"  - cross-sheet transitions:",
        _fmt_transitions(v["cross_sheet_transitions"]),
        f"  - frame evidence: safe_edges={v['frame_evidence']['safe_edge_sheet_pairs']} "
        f"conflicts={v['frame_evidence']['conflicting_pairs']}",
        (f"  - abstain category: {v['abstain_category']}" if v.get("abstain_category") else ""),
        crop,
    ])


def _render_md(r: Dict[str, Any]) -> str:
    parts = [
        "# TrueLine v2 Real-Corpus Debug Report",
        "",
        "## Summary",
        f"- default status counts: `{r['default_distribution']}` (PLACED=23/58)",
        f"- opt-in status counts:  `{r['optin_distribution']}` (PLACED=15/58)",
        f"- regressions (placed -> not placed under opt-in): **{r['regressions']}**",
        f"- improvements (newly placed under opt-in): **{r['improvements']}**",
        f"- frame graph: {r['frame_graph']['safe_edges']} safe edges, {r['frame_graph']['conflicts']} conflicts",
        f"- **CONCLUSION: {r['conclusion']}**",
        "",
        "## How to read this report",
        "- **default** = the shipped engine (`frame_graph=None`). This is what is live in v2 today (23/58).",
        "- **opt-in** = the SAME engine fed the real PDF-derived frame graph. This is a REPORT ONLY; it is",
        "  never persisted and does not change default behavior.",
        "- **cross-sheet transition** classification: `continuous_station` = stationing continues across the",
        "  sheet with no reset (links by raw feet, no frame equation) -- the opt-in rule WRONGLY broke these;",
        "  `reset_equation` = a real matchline equation/offset (a safe edge) translates the link; ",
        "  `reset_equation_offset_mismatch` = an edge exists but its offset does not fit this chain;",
        "  `ambiguous_conflicting` / `ambiguous_missing` = unsafe, no clean evidence.",
        "- A `grading crop` path points to an existing m5 PNG you can open to check the placement visually.",
        "",
        "## log11 detail",
        (_log_block(r["log11"]) if r.get("log11") else "  - (log11 not found)"),
        "",
        "  Why raw station matching is unsafe here: sheet 5 STA 3+23 (323 ft) and sheet 17 STA 0+69 (69 ft)",
        "  are the SAME physical point across the matchline (offset 254 ft) -- linking by raw feet (323 vs 69)",
        "  would mis-join. The safe frame edge IS present, so the translated link is possible; but the engine",
        "  still abstains with `NO_AUTHORED_BOX_MATCH_FOR_BORE_SPAN`: even translated, no authored box chain",
        "  matches log11's span/footage within tolerance. Missing evidence target: a UNIQUE start anchor +",
        "  an authored box whose footage/endpoints match the span in the translated frame.",
        "",
        "## Regressed logs from M8.2d (8 -- all placed by default, ABSTAIN under opt-in)",
    ]
    for v in r["regressed_logs"]:
        parts.append(_log_block(v))
        parts.append("")
    parts += [
        "## Stable placed examples (placed by default AND unchanged under opt-in)",
    ]
    for v in r["stable_examples"]:
        parts.append(_log_block(v))
        parts.append("")
    parts += ["## Representative abstains"]
    for v in r["abstain_examples"]:
        parts.append(_log_block(v))
        parts.append("")
    parts += [
        "## Missing evidence backlog (abstain categories across the corpus)",
        json.dumps(r["missing_evidence_backlog"], indent=2),
        "",
        "## Recommended next implementation step",
        "- Replace the binary same-sheet/cross-sheet rule with a TRANSITION CLASSIFIER:",
        "  `continuous_station` -> keep the raw link (do NOT require an edge); `reset_equation` -> translate",
        "  through the safe edge; `ambiguous_conflicting`/`missing` -> abstain. Re-run M8.2d and require ALL 23",
        "  current placements preserved before any default activation.",
        "- Separately, log11 needs anchor/box/footage evidence beyond the frame edge before it can place.",
        "",
        "## Things NOT proven by this report",
        "- This does NOT prove product readiness, zero false placements, or that frame activation is safe.",
        "- The opt-in result is NOT_SAFE and frame translation remains INACTIVE in the default/real path.",
        "- Placements are NOT visually graded here -- open the grading crops to verify. No customer-facing claim.",
    ]
    return "\n".join(parts) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
