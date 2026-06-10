r"""M8.2a — read-only frame-equation probe.

Tests whether matchline / station-frame equations are EXTRACTABLE from the real
plan PDF text, and whether they could feed a future frame-aware assembler. This is
a PROOF/PROBE only:

  * It reads existing corpus/PDF artifacts and the shipped READ-ONLY helpers
    (PlanPdf text, parse_station, the dialect's extract_callouts, the bore-log loader).
  * It NEVER calls a placement path — no run_match / RedlineService / builders /
    store writes. It changes NO engine/matcher/adapter code and moves NO placement.
  * It writes report artifacts under data/outputs/ ONLY.

Run (repo root): $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_frame_aware_probe

The matchline equation grammar: a plan sheet's matchline carries a frame equation
like ``MATCH LINE STA 3+23 / 0+69 - SEE SHEET 17``, meaning *this sheet's STA 3+23
== sheet 17's STA 0+69* (a frame translation of 254 ft). Today v2 links callouts by
RAW station number, so it would wrongly join ``0+69 -> 0+69`` across that matchline.
This probe checks whether the ``a / b`` values are recoverable from text so a future
assembler can translate frames instead of linking raw numbers.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from truelinev2.config import Settings, _REPO_ROOT
from truelinev2.stations import parse_station

# --- pure parser helpers (testable without a PDF) -----------------------------
_STA = r"\d+\+\d+(?:\.\d+)?"
_EQ = re.compile(rf"(?:STA\s*)?({_STA})\s*([=/])\s*(?:STA\s*)?({_STA})", re.I)
_SEE_SHEET = re.compile(r"SEE\s+SHEET\s+0*(\d{1,3})", re.I)
_MATCHLINE = re.compile(r"MATCH\s*LINE", re.I)


def find_equations(text: str) -> List[Dict[str, Any]]:
    """Pure: find station-pair equations (``a = b`` / ``a / b``) in a text blob.
    Returns one dict per hit with parsed feet, the implied frame offset (a-b), and
    the match span (for context extraction). A callout like ``STA 0+00 TO STA 2+99``
    has no ``=``/``/`` separator and is NOT matched."""
    out: List[Dict[str, Any]] = []
    for m in _EQ.finditer(text or ""):
        a_sta, sep, b_sta = m.group(1), m.group(2), m.group(3)
        a_ft, b_ft = parse_station(a_sta), parse_station(b_sta)
        parseable = a_ft is not None and b_ft is not None
        out.append({
            "a_sta": a_sta, "b_sta": b_sta, "sep": sep,
            "a_ft": a_ft, "b_ft": b_ft,
            "offset_ft": (round(a_ft - b_ft, 2) if parseable else None),
            "parseable": parseable,
            "raw": m.group(0), "start": m.start(), "end": m.end(),
        })
    return out


def find_see_sheets(text: str) -> List[int]:
    """Pure: the sheet numbers referenced by ``SEE SHEET N`` tokens, sorted/unique."""
    return sorted({int(x) for x in _SEE_SHEET.findall(text or "")})


def has_matchline(text: str) -> bool:
    return bool(_MATCHLINE.search(text or ""))


def classify_equation(eq: Dict[str, Any], nearby_see: List[int], nearby_ml: bool) -> Dict[str, str]:
    """Pure: kind + confidence for one equation given its nearby context.

    kind: cross_sheet (a SEE SHEET link is nearby -> a translation between two sheets)
          | frame_reset (one side is 0+00, no sheet link -> a local-frame reset)
          | station_equation (an equation we can't yet associate to a second sheet).
    confidence: HIGH (matchline marker AND exactly one nearby sheet link)
              | MEDIUM (matchline OR exactly one sheet link)
              | LOW (neither / ambiguous)."""
    if nearby_see:
        kind = "cross_sheet"
    elif eq.get("a_ft") == 0.0 or eq.get("b_ft") == 0.0:
        kind = "frame_reset"
    else:
        kind = "station_equation"
    if nearby_ml and len(nearby_see) == 1:
        conf = "HIGH"
    elif nearby_ml or len(nearby_see) == 1:
        conf = "MEDIUM"
    else:
        conf = "LOW"
    return {"kind": kind, "confidence": conf}


# --- PDF scan (read-only) -----------------------------------------------------

def _page_lines(plan, idx: int) -> List[str]:
    return [ln for ln in plan.text_by_index(idx).splitlines() if ln.strip()]


def scan_page(plan, idx: int, offset: int) -> List[Dict[str, Any]]:
    """Read-only: all equation candidates on one PDF page, each with nearby
    SEE-SHEET / matchline context and the inferred sheet number."""
    lines = _page_lines(plan, idx)
    joined = " ".join(lines)
    inferred_sheet = idx - offset + 1
    cands: List[Dict[str, Any]] = []
    for eq in find_equations(joined):
        ctx = joined[max(0, eq["start"] - 70): eq["end"] + 70]
        nearby_see = find_see_sheets(ctx)
        nearby_ml = has_matchline(ctx)
        cls = classify_equation(eq, nearby_see, nearby_ml)
        cands.append({
            "page_index": idx, "inferred_sheet": inferred_sheet,
            "a_sta": eq["a_sta"], "b_sta": eq["b_sta"], "sep": eq["sep"],
            "a_ft": eq["a_ft"], "b_ft": eq["b_ft"], "offset_ft": eq["offset_ft"],
            "parseable": eq["parseable"], "nearby_see_sheets": nearby_see,
            "nearby_matchline": nearby_ml, "kind": cls["kind"],
            "confidence": cls["confidence"], "raw": eq["raw"].strip(),
            "context": ctx.strip()[:200],
        })
    return cands


def build_frame_edges(cands: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Candidate FrameEquations: cross-sheet equations with EXACTLY ONE linked
    sheet (unique) and both stations parseable. offset(linked->source)=a_ft-b_ft."""
    edges: List[Dict[str, Any]] = []
    for c in cands:
        if c["kind"] == "cross_sheet" and c["parseable"] and len(c["nearby_see_sheets"]) == 1:
            edges.append({
                "from_sheet": c["inferred_sheet"], "to_sheet": c["nearby_see_sheets"][0],
                "a_sta": c["a_sta"], "b_sta": c["b_sta"], "offset_ft": c["offset_ft"],
                "confidence": c["confidence"], "page_index": c["page_index"],
            })
    return edges


def pair_conflicts(edges: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Flag sheet pairs that have inconsistent offsets across edges (ambiguity)."""
    by_pair: Dict[str, List[float]] = {}
    for e in edges:
        key = "-".join(str(s) for s in sorted((e["from_sheet"], e["to_sheet"])))
        by_pair.setdefault(key, []).append(abs(e["offset_ft"]))
    conflicts = []
    for key, offs in by_pair.items():
        if max(offs) - min(offs) > 2.0:  # >2 ft spread for the same pair = conflict
            conflicts.append({"pair": key, "offsets_ft": sorted(set(round(o, 1) for o in offs))})
    return conflicts


# --- log11 focus (read-only) --------------------------------------------------

def _find_corpus_file(corpus_dir: str, stem: str) -> Optional[Path]:
    p = Path(corpus_dir) / f"{stem}.xlsx"
    return p if p.is_file() else None


def probe_log11(plan, offset: int, corpus_dir: str, all_cands: List[Dict[str, Any]],
                edges: List[Dict[str, Any]]) -> Dict[str, Any]:
    """The canonical frame-blind case. Loads bore_log11's real sheet_refs, shows the
    equations on those sheets, and checks whether a SAFE translated relationship
    between its two sheets is extractable (explaining why a raw 0+69->0+69 link is unsafe)."""
    from truelinev2.ingest.normalize import load_borelog  # read-only

    res: Dict[str, Any] = {"bore_id": "log11"}
    f = _find_corpus_file(corpus_dir, "bore_log11")
    if f is None:
        res["status"] = "bore_log11.xlsx not found in corpus"
        return res
    try:
        bore = load_borelog(str(f))
    except Exception as e:  # never crash the probe on one log
        res["status"] = f"load error: {type(e).__name__}: {e}"
        return res

    refs = list(bore.sheet_refs)
    res.update({
        "status": "ok", "sheet_refs": refs,
        "span": f"{bore.station_start}->{bore.station_end}", "span_ft": bore.span_ft,
    })
    res["equations_on_ref_sheets"] = {
        str(s): [c for c in all_cands if c["inferred_sheet"] == s] for s in refs
    }
    # cross-link between the two ref sheets (either direction)
    refset = set(refs)
    linking = [e for e in edges
               if e["from_sheet"] in refset and e["to_sheet"] in refset
               and e["from_sheet"] != e["to_sheet"]]
    res["linking_equations"] = linking
    res["safe_translation_extractable"] = bool(linking)
    res["explains_why_raw_link_unsafe"] = any(abs(e["offset_ft"]) > 2.0 for e in linking)

    # corroborate anchor ambiguity (read-only extract; never places)
    try:
        from truelinev2.extract.registry import select_dialect  # read-only
        dialect = select_dialect(plan)
        anchor_counts = {}
        if dialect is not None:
            for s in refs:
                cos = dialect.extract_callouts(plan, s, offset)
                anchor_counts[str(s)] = sum(1 for c in cos if abs(c.from_ft - 0.0) <= 8.0)
        res["zero_anchor_counts_by_sheet"] = anchor_counts
        res["total_zero_anchors"] = sum(anchor_counts.values()) if anchor_counts else None
    except Exception as e:
        res["zero_anchor_counts_by_sheet"] = f"unavailable: {type(e).__name__}: {e}"
    return res


# --- conclusion ---------------------------------------------------------------

def derive_conclusion(parseable: int, edges: List[Dict[str, Any]],
                      conflicts: List[Dict[str, Any]], log11: Dict[str, Any]) -> str:
    if parseable == 0 or not edges:
        return "NOT_SAFE"
    log11_ok = log11.get("safe_translation_extractable") and log11.get("explains_why_raw_link_unsafe")
    log11_pair = "-".join(str(s) for s in sorted(log11.get("sheet_refs", []))) if log11.get("sheet_refs") else None
    log11_conflict = any(c["pair"] == log11_pair for c in conflicts)
    if log11_ok and not log11_conflict:
        return "IMPLEMENTABLE"
    return "NEEDS_MORE_EVIDENCE"


def _recommendation(conclusion: str) -> str:
    return {
        "IMPLEMENTABLE": ("Proceed to M8.2 frame-aware assembly per the Phase 0 file map: model "
                          "Frame/FrameEquation/FrameGraph in schema/, a matchline-equation extractor in "
                          "extract/, and a frame-aware chain builder in match/ — gated by unique-anchor + "
                          "run-identity + zero-placement-change, abstain-first. Still no tolerance widening."),
        "NEEDS_MORE_EVIDENCE": ("Extend the probe before any code: resolve the ambiguities listed "
                                "(missing/duplicate sheet links, offset conflicts), then re-run. Do NOT "
                                "implement until log11's two frames link uniquely and consistently."),
        "NOT_SAFE": ("Do NOT implement frame-aware assembly. The equations are not reliably extractable / "
                     "associable from text; bank the negative (as M8.1 did) and keep the segments abstaining."),
    }[conclusion]


def main() -> int:
    from truelinev2.proof.run_brenham_corpus import CORPUS_DIR, PDF
    from truelinev2.ingest.pdf import PlanPdf

    out_dir = _REPO_ROOT / "data" / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "frame_aware_probe.json"
    md_path = out_dir / "frame_aware_probe.md"

    if not os.path.isfile(PDF):
        report = {"status": "INPUTS_MISSING", "missing": PDF, "conclusion": "NEEDS_MORE_EVIDENCE",
                  "note": "canonical plan PDF not present; cannot probe equation text."}
        json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        md_path.write_text("# Frame-aware probe — INPUTS_MISSING\n\n"
                           f"Canonical PDF not found: `{PDF}`. Conclusion: NEEDS_MORE_EVIDENCE.\n",
                           encoding="utf-8")
        print(f"[m8.2a] STOP: PDF not found: {PDF}")
        return 2

    offset = Settings.for_proof().sheet_offset
    plan = PlanPdf(PDF)
    pages = plan.page_count
    all_cands: List[Dict[str, Any]] = []
    for idx in range(pages):
        all_cands.extend(scan_page(plan, idx, offset))

    parseable = sum(1 for c in all_cands if c["parseable"])
    unparseable = len(all_cands) - parseable
    edges = build_frame_edges(all_cands)
    conflicts = pair_conflicts(edges)

    # per-sheet candidate list
    per_sheet: Dict[str, int] = {}
    for c in all_cands:
        per_sheet[str(c["inferred_sheet"])] = per_sheet.get(str(c["inferred_sheet"]), 0) + 1

    # ambiguity report
    ambiguity = {
        "equations_without_sheet_link": sum(1 for c in all_cands
                                            if c["kind"] != "frame_reset" and not c["nearby_see_sheets"]),
        "equations_with_multiple_sheet_links": sum(1 for c in all_cands if len(c["nearby_see_sheets"]) >= 2),
        "unparseable_equations": unparseable,
        "cross_sheet_offset_conflicts": conflicts,
        "sheets_with_multiple_candidates": sorted(
            [s for s, n in per_sheet.items() if n >= 2], key=lambda x: int(x)),
    }

    log11 = probe_log11(plan, offset, CORPUS_DIR, all_cands, edges)
    plan.close()

    conclusion = derive_conclusion(parseable, edges, conflicts, log11)

    report = {
        "milestone": "truelinev2 M8.2a — read-only frame-equation probe",
        "read_only": True,
        "placement_paths_invoked": False,
        "read_only_entrypoints": ["PlanPdf.text_by_index", "stations.parse_station",
                                  "ingest.normalize.load_borelog", "extract.registry.select_dialect",
                                  "PlanDialect.extract_callouts (read-only)"],
        "pdf": PDF, "corpus_dir": CORPUS_DIR, "sheet_offset_used": offset,
        "pages_scanned": pages,
        "total_candidate_equations": len(all_cands),
        "parseable_equations": parseable,
        "unparseable_or_ambiguous_equations": unparseable,
        "candidate_frame_edges": len(edges),
        "per_sheet_candidate_counts": per_sheet,
        "frame_edges_sample": edges[:25],
        "ambiguity": ambiguity,
        "log11": log11,
        "candidates_sample": all_cands[:30],
        "conclusion": conclusion,
        "recommendation": _recommendation(conclusion),
    }
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    # markdown summary
    eqs = log11.get("linking_equations") or []
    eq_lines = "\n".join(
        f"  - sheet {e['from_sheet']} STA {e['a_sta']}  ==  sheet {e['to_sheet']} STA {e['b_sta']}  "
        f"(offset {e['offset_ft']} ft, {e['confidence']})" for e in eqs) or "  - (none found)"
    ctx_examples = "\n".join(f"  - `{c['raw']}`  (sheet {c['inferred_sheet']}, {c['confidence']}, "
                             f"see={c['nearby_see_sheets']})" for c in all_cands[:8]) or "  - (none)"
    md = f"""# M8.2a — frame-aware probe (read-only)

**Read-only.** No engine/matcher/adapter change. No placement invoked
(`placement_paths_invoked = false`). Outputs under `data/outputs/` only.

- PDF: `{PDF}`
- sheet offset used: **{offset}**
- **pages scanned: {pages}**
- **total candidate equations: {len(all_cands)}**
- parseable equations: **{parseable}**
- unparseable / ambiguous: **{unparseable}**
- candidate frame edges (cross-sheet, unique link): **{len(edges)}**

## Per-sheet candidate counts
{json.dumps(per_sheet, indent=2)}

## Ambiguity
- equations with no sheet link: {ambiguity['equations_without_sheet_link']}
- equations with ≥2 sheet links: {ambiguity['equations_with_multiple_sheet_links']}
- unparseable equations: {ambiguity['unparseable_equations']}
- cross-sheet offset conflicts: {ambiguity['cross_sheet_offset_conflicts']}

## log11 (canonical frame-blind case)
- status: {log11.get('status')}
- sheet_refs: {log11.get('sheet_refs')}
- span: {log11.get('span')}
- safe translated relationship extractable: **{log11.get('safe_translation_extractable')}**
- explains why raw `0+69 -> 0+69` is unsafe: **{log11.get('explains_why_raw_link_unsafe')}**
- zero-anchor counts by sheet: {log11.get('zero_anchor_counts_by_sheet')}
- linking equations:
{eq_lines}

## Example raw text contexts
{ctx_examples}

## Conclusion: {conclusion}

{report['recommendation']}
"""
    md_path.write_text(md, encoding="utf-8")

    print(f"[m8.2a] pages={pages} candidates={len(all_cands)} parseable={parseable} "
          f"edges={len(edges)} conflicts={len(conflicts)}")
    print(f"[m8.2a] log11 safe_translation={log11.get('safe_translation_extractable')} "
          f"explains_unsafe={log11.get('explains_why_raw_link_unsafe')} "
          f"linking={len(log11.get('linking_equations') or [])}")
    print(f"[m8.2a] CONCLUSION: {conclusion}")
    print(f"[m8.2a] report -> {json_path}")
    print(f"[m8.2a] summary -> {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
