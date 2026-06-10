r"""M8.2h -- read-only VISUAL / MANUAL review-target extraction for the three M8.2g
unresolved transitions (log42 [1,2], log57 [8,10,13], log65 [9,10]).

M8.2g graded all three `needs_manual_review`: each has an EXACT continuous box match but a
competing parsed reset/equation. The one open question is geometric --

    "Is the parsed reset/equation AT this bore's crossing, or is it a DIFFERENT matchline on
     the same sheet pair?"

This pass answers it with PAGE COORDINATES (display space, via PlanPdf.search/words -- the
same safe reader the engine uses; NO new renderer): for each target it locates the bore start
box, end box, and crossing box(es), the competing equation's text + position, the matchline
markers, and nearby HH / flower-pot / access-structure / station labels, then measures how far
the competing reset sits from the bore's crossing box. If the reset is far from the crossing it
is a DIFFERENT matchline (continuous link stands); if it sits on the crossing the strongest
signals conflict and a human must look; if the text cannot be located it stays unknown.

READ-ONLY: NO engine / decide / run_match / classifier / adapter change; frame translation
INACTIVE; default 23/58, M8.2d NOT_SAFE, M8.2f NEEDS_MORE_EVIDENCE, M8.2g all-needs-review are
all unchanged. Optional focused crops (reusing PlanPdf.render_clip) + the report go to gitignored
`data/outputs/` only. The verdict may be "still unknown" -- this pass does not force a result.

Run (repo root): $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_transition_visual_targets
"""
from __future__ import annotations

import json
import math
import os
import re
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
    classify_callout_transition,
    conflict_sheet_pairs,
)
from truelinev2.proof.run_brenham_corpus import CORPUS_DIR, EXPECTED_COUNT, PDF, enumerate_corpus
from truelinev2.proof.run_frame_optin_validation import build_plan_frame_graph

TARGETS = ("log42", "log57", "log65")
DIRTY = ("ambiguous", "conflict", "missing_evidence")
# A reset within this fraction of the page diagonal of the bore's crossing box is "at" the
# crossing; beyond it is a DIFFERENT matchline. Transparent; raw distances are reported too.
NEAR_FRAC = 0.12
CONFLICT_PRECISION_FT = 10.0
STRUCTURE_TOKENS = ("HH", "HANDHOLE", "FLOWER POT", "FLOWERPOT", "FP", "VAULT",
                    "PEDESTAL", "PED", "ACCESS", "SPLICE")
RENDER_CROPS = os.getenv("TL2_M82H_CROPS", "1") != "0"
CROP_DIR = _REPO_ROOT / "data" / "outputs" / "m8_2h_crops"


class Verdict(str, Enum):
    CONTINUOUS_STATION_CONFIRMED = "continuous_station_confirmed"
    RESET_EQUATION_CONFIRMED = "reset_equation_confirmed"
    DIFFERENT_MATCHLINE_CONFIRMED = "different_matchline_confirmed"
    PRECISION_CONFLICT_MANUAL_REVIEW = "precision_conflict_manual_review"
    STILL_UNKNOWN_MANUAL_REVIEW = "still_unknown_manual_review"


@dataclass(frozen=True)
class VisualEvidence:
    precision_conflict: bool          # log57-style: shared-side near-tolerance spread
    equation_located: bool            # the competing equation text was found on the sheet
    min_reset_distance: Optional[float]   # bore crossing box center -> nearest reset hit (display units)
    near_threshold: float             # NEAR_FRAC * page diagonal
    exact_box_match: bool             # default placement is an exact continuous box match
    crossing_station_in_equation: bool = False  # the eq references the bore's crossing station


@dataclass(frozen=True)
class VisualVerdict:
    verdict: Verdict
    rationale: str

    def to_dict(self) -> dict:
        return {"verdict": self.verdict.value, "rationale": self.rationale}


def classify_visual(ev: VisualEvidence) -> VisualVerdict:
    """Geometry-first, honest. Geometry can CONFIRM the reset is a different matchline (far
    from the crossing) but never fabricates a continuous/reset confirmation when the strongest
    signals collide on the crossing or the text cannot be located -- those stay manual."""
    if ev.precision_conflict:
        return VisualVerdict(
            Verdict.PRECISION_CONFLICT_MANUAL_REVIEW,
            "the competing 'conflict' is two sides of one matchline read slightly apart "
            "(extraction precision), not a semantic reset; a human confirms the single matchline")
    if not ev.equation_located:
        return VisualVerdict(
            Verdict.STILL_UNKNOWN_MANUAL_REVIEW,
            "the competing equation text could not be located on the sheet, so it cannot be placed "
            "relative to the bore crossing; manual review of the plan is required")
    near = ev.min_reset_distance is not None and ev.min_reset_distance <= ev.near_threshold
    if ev.crossing_station_in_equation or near:
        return VisualVerdict(
            Verdict.STILL_UNKNOWN_MANUAL_REVIEW,
            "the competing matchline equation references the bore's crossing station / sits at the "
            "crossing box -- it is the matchline AT this crossing, not a distant one; with an exact "
            "continuous box match ALSO present, the reset-vs-continuous question is genuine and a "
            "human must read the plan to decide")
    if ev.min_reset_distance is None:
        return VisualVerdict(
            Verdict.STILL_UNKNOWN_MANUAL_REVIEW,
            "the competing equation was located but the bore crossing box has no coordinates to "
            "measure against, so it cannot be placed relative to the crossing; manual review required")
    return VisualVerdict(
        Verdict.DIFFERENT_MATCHLINE_CONFIRMED,
        f"the competing reset references other stations and sits {ev.min_reset_distance:.0f} "
        f"display-units from the crossing box (> {ev.near_threshold:.0f}) -- it is a DIFFERENT "
        f"matchline on the sheet pair, not this crossing"
        + ("; with an exact continuous box match, the continuous link stands"
           if ev.exact_box_match else ""))


# --------------------------------------------------------------------------- geometry helpers
def _center(b: List[float]) -> Tuple[float, float]:
    return ((b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0)


def _dist(b1: List[float], b2: List[float]) -> float:
    (x1, y1), (x2, y2) = _center(b1), _center(b2)
    return math.hypot(x1 - x2, y1 - y2)


def _page_diagonal(plan: PlanPdf, sheet: int, offset: int) -> float:
    ws = plan.words(sheet, offset)
    if not ws:
        return 0.0
    return math.hypot(max(w["x1"] for w in ws), max(w["y1"] for w in ws))


def _eq_variants(a_raw: str, b_raw: str, sep: str, source: str) -> List[str]:
    return [source, f"STA {a_raw} {sep} {b_raw}", f"{a_raw} {sep} {b_raw}",
            f"{a_raw}{sep}{b_raw}", f"STA {a_raw}{sep}{b_raw}"]


def _locate(plan: PlanPdf, sheet: int, offset: int, texts: List[str]) -> List[List[float]]:
    seen, out = set(), []
    for t in texts:
        for h in plan.search(sheet, offset, t):
            key = tuple(round(v, 1) for v in h)
            if key not in seen:
                seen.add(key)
                out.append(h)
    return out


def _pair_equations(plan: PlanPdf, offset: int, a: int, b: int) -> List[Dict[str, Any]]:
    """Equations on sheet a or b that link the other sheet, with source + page hits + distance
    to the bore crossing box on the parsed sheet (filled by the caller)."""
    out: List[Dict[str, Any]] = []
    for s, other in ((a, b), (b, a)):
        idx = plan.page_index(s, offset)
        if not (0 <= idx < plan.page_count):
            continue
        text = " ".join(ln for ln in plan.text_by_index(idx).splitlines() if ln.strip())
        for eq in parse_frame_equations(text):
            if other in eq.linked_frames:
                hits = _locate(plan, s, offset,
                               _eq_variants(eq.a.raw, eq.b.raw, eq.separator, eq.source))
                out.append({
                    "parsed_on_sheet": s, "links_to": list(eq.linked_frames),
                    "a_raw": eq.a.raw, "b_raw": eq.b.raw, "separator": eq.separator,
                    "offset_ft": eq.offset_ft, "confidence": eq.confidence.value,
                    "has_matchline": eq.has_matchline, "source": eq.source,
                    "page_hits": hits, "located": bool(hits),
                })
    return out


def _nearby_structures(plan: PlanPdf, sheet: int, offset: int,
                       box: Optional[List[float]], near: float) -> List[Dict[str, Any]]:
    if not box:
        return []
    out = []
    for tok in STRUCTURE_TOKENS:
        for h in plan.search(sheet, offset, tok):
            d = _dist(box, h)
            if d <= near:
                out.append({"label": tok, "bbox": h, "dist_to_box": round(d, 1)})
    out.sort(key=lambda x: x["dist_to_box"])
    return out[:8]


def _matchlines(plan: PlanPdf, sheet: int, offset: int) -> List[List[float]]:
    return _locate(plan, sheet, offset, ["MATCH LINE", "MATCHLINE", "MATCH  LINE"])


def _box(c) -> Optional[List[float]]:
    return list(c.bbox) if getattr(c, "bbox", None) else None


def _crop(plan: PlanPdf, sheet: int, offset: int, bbox: Optional[List[float]],
          name: str) -> Optional[str]:
    if not (RENDER_CROPS and bbox):
        return None
    try:
        CROP_DIR.mkdir(parents=True, exist_ok=True)
        res = plan.render_clip(sheet, offset, bbox, zoom=2.5, pad=220.0)
        if res is None:
            return None
        img, _x, _y = res
        path = CROP_DIR / name
        img.save(str(path))
        return str(path)
    except Exception:
        return None


# --------------------------------------------------------------------------- per-target
def _target_detail(bore, plan, dialect, offset, graph, cp, stem: str) -> Dict[str, Any]:
    dpl = run_match(bore, plan, dialect, offset, frame_graph=None)
    chain = list(dpl.matched_callouts)
    exact = all(d is not None and abs(d) <= DEFAULT_LINK_TOL
                for d in (dpl.footage_delta, dpl.start_delta, dpl.end_delta))

    # dirty transitions, keeping the actual callout pair (so we have the crossing boxes)
    dirty_pairs = []
    for ca, cb in zip(chain, chain[1:]):
        t = classify_callout_transition(graph, cp, ca, cb)
        if t.classification.value in DIRTY:
            dirty_pairs.append((ca, cb, t))

    disputes = []
    for ca, cb, t in dirty_pairs:
        a, b = ca.sheet, cb.sheet
        eqs = _pair_equations(plan, offset, a, b)
        # measure each equation's distance to the bore crossing box on the SAME sheet
        box_by_sheet = {a: _box(ca), b: _box(cb)}
        precision = False
        offsets = [e["offset_ft"] for e in eqs]
        if len(eqs) >= 2:
            shared = (len({e["a_raw"] for e in eqs}) < len(eqs)
                      or len({e["b_raw"] for e in eqs}) < len(eqs))
            spread = round(max(offsets) - min(offsets), 2)
            precision = bool(t.conflict and shared and spread <= CONFLICT_PRECISION_FT)
        min_dist: Optional[float] = None
        for e in eqs:
            s = e["parsed_on_sheet"]
            box = box_by_sheet.get(s)
            near = _page_diagonal(plan, s, offset) * NEAR_FRAC
            e["near_threshold"] = round(near, 1)
            e["crossing_box_on_sheet"] = box
            ds = [round(_dist(box, h), 1) for h in e["page_hits"]] if box else []
            e["dist_box_to_hits"] = ds
            if ds:
                m = min(ds)
                min_dist = m if min_dist is None else min(min_dist, m)
        located = any(e["located"] for e in eqs)
        near_thr = max((e["near_threshold"] for e in eqs), default=0.0)
        # The crossing station (upstream box's end == downstream box's start in raw feet). If a
        # competing equation references it, the equation IS the matchline at this crossing.
        crossing_sta = (ca.to_sta or "").strip()
        crossing_in_eq = any((e["a_raw"] or "").strip() == crossing_sta
                             or (e["b_raw"] or "").strip() == crossing_sta for e in eqs)
        ev = VisualEvidence(precision_conflict=precision, equation_located=located,
                            min_reset_distance=min_dist, near_threshold=near_thr,
                            exact_box_match=exact, crossing_station_in_equation=crossing_in_eq)
        verdict = classify_visual(ev)
        disputes.append({
            "transition": t.to_dict(),
            "crossing_station": crossing_sta, "crossing_station_in_equation": crossing_in_eq,
            "crossing_boxes": {f"s{a}": box_by_sheet.get(a), f"s{b}": box_by_sheet.get(b)},
            "matchline_hits": {f"s{a}": _matchlines(plan, a, offset),
                               f"s{b}": _matchlines(plan, b, offset)},
            "nearby_structures": {f"s{a}": _nearby_structures(plan, a, offset, box_by_sheet.get(a), near_thr),
                                  f"s{b}": _nearby_structures(plan, b, offset, box_by_sheet.get(b), near_thr)},
            "competing_equations": eqs,
            "min_reset_distance": min_dist, "near_threshold": round(near_thr, 1),
            "reset_located": located, "precision_conflict": precision,
            "verdict": verdict.to_dict(),
            "crossing_crop": _crop(plan, b, offset, box_by_sheet.get(b),
                                   f"{stem}__crossing_s{b}.png"),
        })

    return {
        "bore_id": bore.bore_id, "log_key": stem.replace("bore_", ""), "source_file": stem,
        "sheet_refs": list(bore.sheet_refs), "span": f"{bore.station_start}->{bore.station_end}",
        "span_ft": bore.span_ft,
        "default": {"status": dpl.status.value, "tier": dpl.tier, "reason": dpl.reason,
                    "sheets": list(dpl.sheets), "footage": dpl.footage,
                    "footage_delta": dpl.footage_delta, "start_delta": dpl.start_delta,
                    "end_delta": dpl.end_delta},
        "exact_continuous_box_match": exact,
        "bore_start_box": {"sheet": chain[0].sheet, "sta": f"{chain[0].from_sta}->{chain[0].to_sta}",
                           "bbox": _box(chain[0])} if chain else None,
        "bore_end_box": {"sheet": chain[-1].sheet, "sta": f"{chain[-1].from_sta}->{chain[-1].to_sta}",
                         "bbox": _box(chain[-1])} if chain else None,
        "start_crop": _crop(plan, chain[0].sheet, offset, _box(chain[0]),
                            f"{stem}__start_s{chain[0].sheet}.png") if chain else None,
        "end_crop": _crop(plan, chain[-1].sheet, offset, _box(chain[-1]),
                          f"{stem}__end_s{chain[-1].sheet}.png") if chain else None,
        "disputes": disputes,
    }


def main() -> int:
    out_dir = _REPO_ROOT / "data" / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "transition_visual_targets.json"
    md_path = out_dir / "transition_visual_targets.md"

    if not os.path.isfile(PDF) or not os.path.isdir(CORPUS_DIR):
        json_path.write_text(json.dumps({"status": "INPUTS_MISSING", "pdf": PDF}, indent=2),
                             encoding="utf-8")
        print(f"[m8.2h] STOP: inputs missing (pdf={os.path.isfile(PDF)} corpus={os.path.isdir(CORPUS_DIR)})")
        return 2
    corpus = enumerate_corpus(CORPUS_DIR)
    if len(corpus) != EXPECTED_COUNT:
        print(f"[m8.2h] STOP: expected {EXPECTED_COUNT} logs, got {len(corpus)} -- corpus drift.")
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
        details[key] = _target_detail(load_borelog(str(p)), plan, dialect, offset, graph, cp, p.stem)
    plan.close()

    verdicts = {k: [d["verdict"]["verdict"] for d in v.get("disputes", [])]
                for k, v in details.items()}
    report = {
        "milestone": "truelinev2 M8.2h -- transition visual/manual review targets (read-only)",
        "read_only": True, "default_run_match_unchanged": True, "frame_translation_active": False,
        "default_distribution_note": "default remains AUTO_SELECT=14 REVIEW=9 ABSTAIN=33 ERROR=2 PLACED=23",
        "upstream_status": {"m8_2d": "NOT_SAFE", "m8_2f": "NEEDS_MORE_EVIDENCE",
                            "m8_2g": "all needs_manual_review"},
        "near_frac": NEAR_FRAC, "link_tol_ft": DEFAULT_LINK_TOL,
        "targets": details, "verdicts": verdicts,
    }
    json_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    md_path.write_text(_render_md(report), encoding="utf-8")

    for k in TARGETS:
        print(f"[m8.2h] {k}: {verdicts.get(k)}")
    print(f"[m8.2h] default 23/58 unchanged; M8.2d NOT_SAFE; M8.2f NEEDS_MORE_EVIDENCE; "
          f"M8.2g all-needs-review; classifier untouched")
    print(f"[m8.2h] report -> {md_path}")
    return 0


# --------------------------------------------------------------------------- markdown
def _fmt_box(b: Optional[List[float]]) -> str:
    return ("[%.0f,%.0f,%.0f,%.0f]" % tuple(b)) if b else "(not located)"


def _target_block(name: str, d: Dict[str, Any]) -> str:
    if "error" in d:
        return f"## {name}\n  - ERROR: {d['error']}\n"
    L = [f"## {name}",
         f"- sheets {d['sheet_refs']}, span {d['span']} ({d['span_ft']}ft); default "
         f"{d['default']['status']} ({d['default']['reason']}); exact continuous box match: "
         f"{d['exact_continuous_box_match']}",
         f"- bore START box: s{d['bore_start_box']['sheet']} {d['bore_start_box']['sta']} "
         f"@ {_fmt_box(d['bore_start_box']['bbox'])}"
         + (f"  crop=`{d['start_crop']}`" if d.get("start_crop") else ""),
         f"- bore END box:   s{d['bore_end_box']['sheet']} {d['bore_end_box']['sta']} "
         f"@ {_fmt_box(d['bore_end_box']['bbox'])}"
         + (f"  crop=`{d['end_crop']}`" if d.get("end_crop") else "")]
    for i, dd in enumerate(d["disputes"], 1):
        t = dd["transition"]
        L.append(f"- **dispute #{i}: s{t['from_sheet']}->s{t['to_sheet']} = `{t['classification']}`** "
                 f"-> **{dd['verdict']['verdict']}**")
        L.append(f"    - crossing boxes: " + ", ".join(
            f"{k} @ {_fmt_box(v)}" for k, v in dd["crossing_boxes"].items()))
        L.append(f"    - crossing station `{dd.get('crossing_station')}` referenced by a competing "
                 f"equation: {dd.get('crossing_station_in_equation')}")
        for e in dd["competing_equations"]:
            L.append(f"    - competing eq on s{e['parsed_on_sheet']}->s{e['links_to']}: "
                     f"`STA {e['a_raw']} {e['separator']} {e['b_raw']}` offset={e['offset_ft']}ft "
                     f"conf={e['confidence']} matchline={e['has_matchline']} located={e['located']} "
                     f"dist_box->hits={e.get('dist_box_to_hits')} (near<= {e.get('near_threshold')})")
        ml = dd["matchline_hits"]
        L.append(f"    - matchline markers: " + ", ".join(f"{k}={len(v)} hit(s)" for k, v in ml.items()))
        ns = {k: [s["label"] for s in v] for k, v in dd["nearby_structures"].items()}
        L.append(f"    - nearby structures: {ns}")
        L.append(f"    - min reset->crossing distance: {dd['min_reset_distance']} "
                 f"(threshold {dd['near_threshold']})  reset_located={dd['reset_located']}")
        if dd.get("crossing_crop"):
            L.append(f"    - crossing crop: `{dd['crossing_crop']}`")
        L.append(f"    - rationale: {dd['verdict']['rationale']}")
    L.append("")
    return "\n".join(L)


def _render_md(r: Dict[str, Any]) -> str:
    def recs(k):
        return ", ".join(r["verdicts"].get(k, [])) or "<none>"
    t = r["targets"]
    parts = [
        "# M8.2h Transition Visual / Manual Review Targets",
        "",
        "## Summary verdict",
        f"- **log42 [1,2]**: {recs('log42')}",
        f"- **log57 [8,10,13]**: {recs('log57')}",
        f"- **log65 [9,10]**: {recs('log65')}",
        "",
        "_Read-only. Coordinates are PDF DISPLAY space (rotation-mapped, same as the engine's",
        "reader). No engine/classifier/default change; frame translation INACTIVE; default 23/58,",
        "M8.2d NOT_SAFE, M8.2f NEEDS_MORE_EVIDENCE, M8.2g all-needs-review unchanged. A verdict of",
        "`still_unknown_manual_review` is a valid, honest outcome -- nothing is forced._",
        "",
        "## Why this pass exists",
        "M8.2g proved each target has an exact continuous box match AND a competing parsed reset. The",
        "only open question is geometric: is the parsed reset AT the bore's crossing, or a DIFFERENT",
        "matchline elsewhere on the sheet pair? This pass measures the distance from the competing reset",
        "to the bore's crossing box and hands the human exact page coordinates + crops to confirm.",
        "",
        "## How to read a target",
        "- coordinates are `[x0,y0,x1,y1]` in display space; `dist_box->hits` is the bore crossing box",
        "  center to each located equation hit (display units); `near` threshold = "
        f"{r['near_frac']} x page diagonal.",
        "- a reset FAR from the crossing box -> `different_matchline_confirmed` (continuous link stands).",
        "- a reset ON the crossing box with an exact box match -> signals collide -> manual review.",
        "- an unlocatable equation -> `still_unknown_manual_review`.",
        "",
        _target_block("Target 1 — log42 [1,2]", t.get("log42", {})),
        _target_block("Target 2 — log57 [8,10,13]", t.get("log57", {})),
        _target_block("Target 3 — log65 [9,10]", t.get("log65", {})),
        "## Visual review checklist for Patrick",
        "For each target, open the crossing crop (or the PDF at the crossing-box coordinates) and confirm:",
        "- does the redline run continuously across the sheet break, or is there a reset/equation label",
        "  right at the bore's crossing box?",
        "- if the competing equation is reported FAR from the crossing box, verify it annotates a",
        "  different matchline (a different bore/route), not this one.",
        "- for log57, confirm the two near-identical equations are the two sides of ONE matchline.",
        "",
        "## What remains blocked",
        "- Any `*_manual_review` / `still_unknown` target is blocked on Patrick's visual confirmation.",
        "- No classifier change and no opt-in attempt until the targets are confirmed and a",
        "  reset-localization precedence rule is defined.",
        "- log11 remains separately blocked on missing anchor/box/footage evidence.",
        "",
        "## Recommended next step",
        "1. Patrick confirms each verdict against the crops/coordinates here.",
        "2. For `different_matchline_confirmed` targets, the future fix is to LOCALIZE a reset edge to the",
        "   crossing before it may block a continuous link (parser/classifier work, separately gated).",
        "3. Only then attempt a classifier-gated opt-in, re-validated by M8.2d with zero regression.",
    ]
    return "\n".join(parts) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
