r"""M8.2g -- read-only EVIDENCE REFINEMENT for the three M8.2f dirty transitions.

Targets exactly the cross-sheet transitions M8.2f flagged ambiguous/conflict:
  * log42 [1,2]   s2->s1  (raw_gap 0 vs a parsed reset edge ~246 ft)  -> ambiguous
  * log57 [8,10,13] s13->s8 (conflicting sheet pair 8,13)            -> conflict
  * log65 [9,10]  s10->s9 (raw_gap 0 vs a parsed reset edge ~3279 ft) -> ambiguous

For each it surfaces the REAL evidence M8.2f did not print -- the frame-equation SOURCE
TEXT and its context, the parsed offset/confidence/SEE-SHEET link, the default chain's
callout geometry, the default vs opt-in result, and a geometric plausibility test (an
offset larger than the furthest authored station on the joined sheets cannot be a real
adjacent-sheet reset) -- and recommends one of:
  continuous_station_confirmed / reset_equation_confirmed / parser_false_positive /
  true_conflict_abstain / needs_manual_review.

This is EVIDENCE GRADING, not implementation. READ-ONLY: NO engine / decide / default
run_match / classifier / adapter change; frame translation stays INACTIVE; the default
23/58 and the M8.2d NOT_SAFE / M8.2f NEEDS_MORE_EVIDENCE results are unchanged. Outputs go
to gitignored ``data/outputs/`` only.

Run (repo root): $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_transition_evidence_refinement
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from truelinev2.config import Settings, _REPO_ROOT
from truelinev2.extract.registry import select_dialect
from truelinev2.ingest.normalize import load_borelog
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.match.engine import run_match
from truelinev2.match.frames import parse_frame_equations
from truelinev2.match.transition_classifier import (
    DEFAULT_LINK_TOL,
    classify_chain,
    conflict_sheet_pairs,
    cross_sheet_transitions,
)
from truelinev2.proof.run_brenham_corpus import CORPUS_DIR, EXPECTED_COUNT, PDF, enumerate_corpus
from truelinev2.proof.run_frame_optin_validation import build_plan_frame_graph

PLACED = ("AUTO_SELECT", "REVIEW")
M5_CROP_DIR = _REPO_ROOT / "data" / "outputs" / "truelinev2" / "m5_brenham"
# Endpoint/footage deltas (ft) under which a default placement is a "tight" raw match.
TIGHT_DELTA_FT = 2.0
# Two conflicting equations that share a side and disagree by <= this are ONE imprecise
# matchline (an extraction-precision spread just over tolerance), not a semantic conflict.
CONFLICT_PRECISION_FT = 10.0
CONFLICT_TOL_FT = 2.0  # mirrors match/frames conflict tolerance (kept local; no private import)
# A dirty (non-linkable) transition is one the classifier refused to link.
DIRTY = ("ambiguous", "conflict", "missing_evidence")

TARGETS = ("log42", "log57", "log65")


# --------------------------------------------------------------------------- adjudication
class Recommendation(str, Enum):
    CONTINUOUS_STATION_CONFIRMED = "continuous_station_confirmed"
    RESET_EQUATION_CONFIRMED = "reset_equation_confirmed"
    PARSER_FALSE_POSITIVE = "parser_false_positive"
    TRUE_CONFLICT_ABSTAIN = "true_conflict_abstain"
    NEEDS_MANUAL_REVIEW = "needs_manual_review"


@dataclass(frozen=True)
class AdjEvidence:
    classification: str          # the M8.2f classifier verdict for the transition
    conflict: bool
    has_safe_edge: bool
    edge_offset_ft: Optional[float]
    raw_gap_ft: Optional[float]
    translated_gap_ft: Optional[float]
    edge_high_confidence: bool   # a linking equation is HIGH (matchline + unique SEE-SHEET)
    offset_geometrically_possible: bool  # |offset| <= furthest authored station on the joined sheets
    default_tight: bool          # default raw placement is an exact footage/endpoint match
    n_link_equations: int        # parsed equations linking the disputed pair
    conflict_shared_side: bool = False          # conflicting eqs share a station on one side
    conflict_offset_spread_ft: Optional[float] = None  # max-min offset among linking eqs


@dataclass(frozen=True)
class Adjudication:
    recommendation: Recommendation
    rationale: str
    future_rule: str

    def to_dict(self) -> dict:
        return {"recommendation": self.recommendation.value,
                "rationale": self.rationale, "future_rule": self.future_rule}


def adjudicate(ev: AdjEvidence) -> Adjudication:
    """Transparent, conservative evidence rule (no visual). It will not CONFIRM continuous vs
    reset when the textual/geometric evidence is not decisive -- it defers to a targeted visual
    grade. It CAN decisively expose a parser false positive (impossible offset) and an
    extraction-precision pseudo-conflict (two sides of one matchline read slightly apart)."""
    if ev.conflict or ev.classification == "conflict":
        if (ev.conflict_shared_side and ev.conflict_offset_spread_ft is not None
                and ev.conflict_offset_spread_ft <= CONFLICT_PRECISION_FT):
            return Adjudication(
                Recommendation.NEEDS_MANUAL_REVIEW,
                f"the two equations share a side and disagree by only "
                f"{ev.conflict_offset_spread_ft}ft -- they are the two sides of ONE matchline read "
                f"slightly apart (extraction precision just over the {CONFLICT_TOL_FT}ft conflict "
                f"tolerance), not two semantically different resets"
                + ("; the default is an exact continuous box match, which corroborates continuity"
                   if ev.default_tight else ""),
                "treat a shared-side near-tolerance offset spread as ONE imprecise matchline, not a "
                "conflict -- tighten extraction or set the conflict tolerance to the extraction precision")
        if ev.n_link_equations >= 2 and not ev.offset_geometrically_possible:
            return Adjudication(
                Recommendation.NEEDS_MANUAL_REVIEW,
                "conflicting equations on the pair, but at least one offset is geometrically "
                "impossible -- the conflict may dissolve once the bad equation is dropped",
                "discard geometrically-impossible edges before declaring a conflict; only a conflict "
                "among GEOMETRICALLY-POSSIBLE edges is a true abstain")
        return Adjudication(
            Recommendation.TRUE_CONFLICT_ABSTAIN,
            "two or more geometrically-possible frame equations disagree beyond tolerance; the safe "
            "action is to abstain -- never silently pick one",
            "a conflict among plausible frame equations forces abstain; do not auto-pick")
    # ambiguous: raw continuity present AND a safe reset edge that disagrees
    if ev.classification == "ambiguous":
        if not ev.offset_geometrically_possible and ev.default_tight:
            return Adjudication(
                Recommendation.PARSER_FALSE_POSITIVE,
                "the parsed reset offset exceeds the furthest authored station on the joined sheets "
                "(a physically impossible adjacent-sheet reset) while the raw-continuous placement is "
                "an exact footage/endpoint match -- the edge is a frame-parser false positive and the "
                "continuous link is the real one",
                "drop frame edges whose |offset| exceeds the max authored station on the joined sheets "
                "BEFORE they can block a continuous link")
        if ev.default_tight:
            return Adjudication(
                Recommendation.NEEDS_MANUAL_REVIEW,
                f"the default is an EXACT continuous box-footage+endpoints match (deltas ~0), which "
                f"corroborates continuity, yet a geometrically-possible {ev.edge_offset_ft}ft reset "
                f"equation also exists on this sheet pair -- most likely a DIFFERENT matchline on these "
                f"sheets, not the bore's crossing; a quick visual confirms which matchline is at the break",
                "localize a reset equation to the ACTUAL crossing before letting it override an exact "
                "continuous box match elsewhere on the same sheet pair")
        if ev.edge_high_confidence:
            return Adjudication(
                Recommendation.RESET_EQUATION_CONFIRMED,
                "a HIGH-confidence matchline + unique SEE-SHEET equation links the frames and the "
                "raw-continuous placement is NOT a tight match -- the reset is likely real and the "
                "equal raw station misleading",
                "a HIGH-confidence reset overrides raw equal-station continuity when continuity is not "
                "independently corroborated")
        return Adjudication(
            Recommendation.NEEDS_MANUAL_REVIEW,
            "raw continuity and a parsed reset disagree and the evidence is not decisive; visual grade "
            "of the crop required",
            "default undecided continuity-vs-reset cases to manual review rather than guess")
    return Adjudication(
        Recommendation.NEEDS_MANUAL_REVIEW,
        f"transition classified '{ev.classification}'; no decisive textual rule -- visual grade required",
        "default unclear transitions to manual review")


# --------------------------------------------------------------------------- evidence I/O
def _join_text(plan, idx: int) -> str:
    return " ".join(ln for ln in plan.text_by_index(idx).splitlines() if ln.strip())


def _pair_equations(plan, offset: int, a: int, b: int) -> List[Dict[str, Any]]:
    """Every parsed station equation on sheet ``a`` or ``b`` that links to the OTHER sheet,
    with its source text + surrounding context (the raw evidence behind any a<->b edge)."""
    out: List[Dict[str, Any]] = []
    for s, other in ((a, b), (b, a)):
        idx = s + offset - 1
        if idx < 0 or idx >= plan.page_count:
            continue
        text = _join_text(plan, idx)
        for eq in parse_frame_equations(text):
            if other in eq.linked_frames:
                pos = text.find(eq.source) if eq.source else -1
                ctx = text[max(0, pos - 90): pos + len(eq.source or "") + 90].strip() if pos >= 0 else ""
                out.append({
                    "parsed_on_sheet": s, "links_to": list(eq.linked_frames),
                    "a_raw": eq.a.raw, "b_raw": eq.b.raw, "separator": eq.separator,
                    "offset_ft": eq.offset_ft, "kind": eq.kind.value,
                    "confidence": eq.confidence.value, "has_matchline": eq.has_matchline,
                    "source": eq.source, "context": ctx,
                })
    return out


def _max_authored_station_ft(plan, dialect, offset: int, sheets: Tuple[int, ...]) -> float:
    """Furthest authored station (ft) on the joined sheets -- the ceiling a real
    adjacent-sheet reset offset cannot exceed."""
    mx = 0.0
    for s in sheets:
        try:
            for c in dialect.extract_callouts(plan, s, offset):
                mx = max(mx, c.to_ft, c.from_ft)
        except Exception:
            continue
    return round(mx, 2)


def _callout_row(c) -> Dict[str, Any]:
    return {"sheet": c.sheet, "from_sta": c.from_sta, "to_sta": c.to_sta,
            "from_ft": c.from_ft, "to_ft": c.to_ft, "footage": c.footage,
            "conduit": c.conduit, "text": (c.text or "")[:120]}


def _crop_path(stem: str, status: str, sheets: List[int]) -> Optional[str]:
    tag = ("_s%s" % sheets[0]) if sheets else ""
    p = M5_CROP_DIR / f"{stem}__{status}{tag}.png"
    return str(p) if p.is_file() else None


def _placement(pl) -> Dict[str, Any]:
    return {"status": pl.status.value, "tier": pl.tier, "reason": pl.reason,
            "sheets": list(pl.sheets), "footage": pl.footage,
            "footage_delta": pl.footage_delta, "start_delta": pl.start_delta,
            "end_delta": pl.end_delta, "caveats": list(pl.caveats),
            "chain": [_callout_row(c) for c in pl.matched_callouts]}


def _is_tight(pl) -> bool:
    ds = [pl.footage_delta, pl.start_delta, pl.end_delta]
    return all(d is not None and abs(d) <= TIGHT_DELTA_FT for d in ds)


def _target_detail(bore, plan, dialect, offset, graph, cp, stem: str) -> Dict[str, Any]:
    dpl = run_match(bore, plan, dialect, offset, frame_graph=None)
    opl = run_match(bore, plan, dialect, offset, frame_graph=graph)
    chain = list(dpl.matched_callouts)
    transitions = classify_chain(graph, cp, chain)
    cross = cross_sheet_transitions(transitions)
    dirty = [t for t in cross if t.classification.value in DIRTY]

    disputes = []
    for t in dirty:
        a, b = t.from_sheet, t.to_sheet
        eqs = _pair_equations(plan, offset, a, b)
        max_sta = _max_authored_station_ft(plan, dialect, offset, (a, b))
        offsets = [e["offset_ft"] for e in eqs]
        # Use the safe edge's offset when present, else the largest linking-equation offset
        # (covers the conflict case where no single safe edge survives).
        off_for_geom = (abs(t.edge_offset_ft) if t.edge_offset_ft is not None
                        else max((abs(o) for o in offsets), default=None))
        geom_possible = (off_for_geom is None) or (off_for_geom <= max_sta + TIGHT_DELTA_FT)
        high_conf = any(e["confidence"] == "HIGH" and e["has_matchline"] for e in eqs)
        spread = round(max(offsets) - min(offsets), 2) if len(offsets) >= 2 else None
        shared_side = (len(eqs) >= 2 and (len({e["a_raw"] for e in eqs}) < len(eqs)
                                          or len({e["b_raw"] for e in eqs}) < len(eqs)))
        ev = AdjEvidence(
            classification=t.classification.value, conflict=t.conflict,
            has_safe_edge=t.safe_edge, edge_offset_ft=t.edge_offset_ft,
            raw_gap_ft=t.raw_gap_ft, translated_gap_ft=t.translated_gap_ft,
            edge_high_confidence=high_conf, offset_geometrically_possible=geom_possible,
            default_tight=_is_tight(dpl), n_link_equations=len(eqs),
            conflict_shared_side=shared_side, conflict_offset_spread_ft=spread)
        disputes.append({
            "transition": t.to_dict(),
            "frame_equations": eqs,
            "max_authored_station_ft": max_sta,
            "offset_geometrically_possible": geom_possible,
            "edge_high_confidence": high_conf,
            "conflict_shared_side": shared_side,
            "conflict_offset_spread_ft": spread,
            "adjudication": adjudicate(ev).to_dict(),
        })

    return {
        "bore_id": bore.bore_id, "log_key": stem.replace("bore_", ""), "source_file": stem,
        "sheet_refs": list(bore.sheet_refs), "span": f"{bore.station_start}->{bore.station_end}",
        "span_ft": bore.span_ft,
        "default": _placement(dpl), "default_tight": _is_tight(dpl),
        "optin": {"status": opl.status.value, "tier": opl.tier, "reason": opl.reason},
        "all_cross_transitions": [t.to_dict() for t in cross],
        "disputes": disputes,
        "grading_crop": _crop_path(stem, dpl.status.value, list(dpl.sheets)),
    }


def main() -> int:
    out_dir = _REPO_ROOT / "data" / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "transition_evidence_refinement.json"
    md_path = out_dir / "transition_evidence_refinement.md"

    if not os.path.isfile(PDF) or not os.path.isdir(CORPUS_DIR):
        json_path.write_text(json.dumps({"status": "INPUTS_MISSING", "pdf": PDF}, indent=2),
                             encoding="utf-8")
        print(f"[m8.2g] STOP: inputs missing (pdf={os.path.isfile(PDF)} corpus={os.path.isdir(CORPUS_DIR)})")
        return 2
    corpus = enumerate_corpus(CORPUS_DIR)
    if len(corpus) != EXPECTED_COUNT:
        print(f"[m8.2g] STOP: expected {EXPECTED_COUNT} logs, got {len(corpus)} -- corpus drift.")
        return 3

    offset = Settings.for_proof().sheet_offset
    plan = PlanPdf(PDF)
    dialect = select_dialect(plan)
    graph = build_plan_frame_graph(plan, offset)
    cp = conflict_sheet_pairs(graph)

    by_stem = {p.stem.replace("bore_", ""): p for p in corpus}
    details: Dict[str, Dict[str, Any]] = {}
    for key in TARGETS:
        p = by_stem.get(key)
        if p is None:
            details[key] = {"error": "log not found in corpus"}
            continue
        bore = load_borelog(str(p))
        details[key] = _target_detail(bore, plan, dialect, offset, graph, cp, p.stem)
    plan.close()

    verdicts = {k: [dd["adjudication"]["recommendation"] for dd in v.get("disputes", [])]
                for k, v in details.items()}

    report = {
        "milestone": "truelinev2 M8.2g -- transition evidence refinement (read-only)",
        "read_only": True, "default_run_match_unchanged": True,
        "frame_translation_active": False,
        "default_distribution_note": "default remains AUTO_SELECT=14 REVIEW=9 ABSTAIN=33 ERROR=2 PLACED=23",
        "m8_2d_optin_status": "NOT_SAFE (unchanged)",
        "m8_2f_classifier_verdict": "NEEDS_MORE_EVIDENCE (unchanged; classifier not modified)",
        "link_tol_ft": DEFAULT_LINK_TOL, "tight_delta_ft": TIGHT_DELTA_FT,
        "frame_graph": {"safe_edges": len(graph.edges), "conflicts": len(graph.conflicts)},
        "targets": details, "verdicts": verdicts,
    }
    json_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    md_path.write_text(_render_md(report), encoding="utf-8")

    print(f"[m8.2g] safe_edges={len(graph.edges)} conflicts={len(graph.conflicts)}")
    for k in TARGETS:
        print(f"[m8.2g] {k}: {verdicts.get(k)}")
    print(f"[m8.2g] default unchanged (23/58); M8.2d NOT_SAFE; M8.2f NEEDS_MORE_EVIDENCE; classifier untouched")
    print(f"[m8.2g] report -> {md_path}")
    return 0


# --------------------------------------------------------------------------- markdown
def _eq_line(e: Dict[str, Any]) -> str:
    return (f"    - on s{e['parsed_on_sheet']} -> s{e['links_to']}: "
            f"`{e['a_raw']} {e['separator']} {e['b_raw']}` offset={e['offset_ft']}ft "
            f"conf={e['confidence']} matchline={e['has_matchline']}  source=`{e['source']}`")


def _target_block(name: str, sheets: str, d: Dict[str, Any]) -> str:
    if "error" in d:
        return f"## {name}\n  - ERROR: {d['error']}\n"
    dft, opt = d["default"], d["optin"]
    lines = [
        f"## {name}",
        f"- sheets {d['sheet_refs']}, span {d['span']} ({d['span_ft']}ft)",
        f"- **default**: {dft['status']} ({dft['reason']}) tier={dft['tier']} "
        f"footage={dft['footage']} delta(foot/start/end)="
        f"{dft['footage_delta']}/{dft['start_delta']}/{dft['end_delta']} "
        f"tight={d['default_tight']}",
        f"- **opt-in**: {opt['status']} ({opt['reason']})",
        f"- default chain:",
    ]
    for c in dft["chain"]:
        lines.append(f"    - s{c['sheet']} {c['from_sta']}->{c['to_sta']} "
                     f"({c['from_ft']:.0f}-{c['to_ft']:.0f}ft, {c['footage']:.0f}' {c['conduit']})")
    for i, dd in enumerate(d["disputes"], 1):
        t = dd["transition"]
        adj = dd["adjudication"]
        lines += [
            f"- **disputed transition #{i}: s{t['from_sheet']}->s{t['to_sheet']} = "
            f"`{t['classification']}`**",
            f"    - raw_gap={t['raw_gap_ft']}ft  translated_gap={t['translated_gap_ft']}ft  "
            f"edge_offset={t['edge_offset_ft']}ft  conflict={t['conflict']}",
            f"    - max authored station on joined sheets = {dd['max_authored_station_ft']}ft  "
            f"-> offset geometrically possible: {dd['offset_geometrically_possible']}",
            f"    - frame equation evidence ({len(dd['frame_equations'])}):",
        ]
        if dd["frame_equations"]:
            for e in dd["frame_equations"]:
                lines.append(_eq_line(e))
        else:
            lines.append("        - (no linking equation found in text -- edge is unexplained)")
        lines += [
            f"    - **recommendation: `{adj['recommendation']}`**",
            f"    - rationale: {adj['rationale']}",
            f"    - future rule: {adj['future_rule']}",
        ]
    lines.append(f"- grading crop to inspect: `{d['grading_crop']}`")
    lines.append("")
    return "\n".join(lines)


def _render_md(r: Dict[str, Any]) -> str:
    t = r["targets"]
    def recs(k):
        return ", ".join(r["verdicts"].get(k, [])) or "<none>"
    parts = [
        "# M8.2g Transition Evidence Refinement",
        "",
        "## Summary verdict",
        f"- **log42 [1,2]**: {recs('log42')}",
        f"- **log57 [8,10,13]**: {recs('log57')}",
        f"- **log65 [9,10]**: {recs('log65')}",
        "",
        "_Read-only evidence grading. No engine/classifier/default change; frame translation",
        "INACTIVE; default remains 23/58; M8.2d NOT_SAFE; M8.2f NEEDS_MORE_EVIDENCE. No activation._",
        "",
        "## Why this pass exists",
        "M8.2f's classifier refused to preserve 3 of the 8 M8.2d-regressed placements: log42 and",
        "log65 link by a raw equal-station that a parsed frame reset contradicts (`ambiguous`), and",
        "log57 threads a sheet pair with conflicting frame equations (`conflict`). M8.2f printed the",
        "offsets but not WHY the edges exist. This pass surfaces the equation source text + geometry",
        "so each dirty transition can be graded: real reset, real conflict, or parser false positive.",
        "",
        _target_block("Target 1 — log42 [1,2]", "[1,2]", t.get("log42", {})),
        _target_block("Target 2 — log57 [8,10,13]", "[8,10,13]", t.get("log57", {})),
        _target_block("Target 3 — log65 [9,10]", "[9,10]", t.get("log65", {})),
        "## Visual review checklist for Patrick",
        "Open each grading crop above and confirm, per target:",
        "- does the redline run continuously across the sheet break (continuous_station), or does the",
        "  plan show a real matchline reset/equation at that break (reset_equation)?",
        "- does the disputed frame equation's source text describe a real matchline, or is it an",
        "  unrelated number the parser mistook for an equation (parser_false_positive)?",
        "- for log57: are BOTH conflicting equations real, or is one a misparse (which would dissolve",
        "  the conflict)?",
        "",
        "## Future rule implications",
        "- Geometrically-impossible edges (|offset| > furthest authored station on the joined sheets)",
        "  should be dropped at parse time so they cannot block a continuous link or fabricate a conflict.",
        "- A reset overrides raw continuity ONLY when it is HIGH-confidence (matchline + unique SEE-SHEET)",
        "  AND geometrically possible.",
        "- A conflict among GEOMETRICALLY-POSSIBLE equations is a true abstain; a conflict that includes",
        "  an impossible edge is a parser bug, not a real ambiguity.",
        "",
        "## What remains blocked",
        "- Any transition graded `needs_manual_review` is blocked on Patrick's visual confirmation.",
        "- log11 remains blocked on missing anchor/box/footage evidence (separate from these 3).",
        "- No classifier change and no opt-in attempt until the 3 are graded and a precedence rule is set.",
        "",
        "## Recommended next step",
        "1. Patrick grades the 3 crops against this report's equation evidence.",
        "2. For any `parser_false_positive`, fix the frame-equation parser (drop impossible offsets) in a",
        "   separate, gated change -- then re-run M8.2f and confirm those transitions become clean.",
        "3. Only after the 3 are resolved, define the precedence rule and attempt a classifier-gated opt-in,",
        "   re-validated by M8.2d with zero regression. NOT started here.",
    ]
    return "\n".join(parts) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
