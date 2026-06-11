r"""M8.14.b.9 Phase 0 -- matchline-joined cross-sheet conduit chain probe.

Case: **log65** (chosen over log50 because every link is PRINTED/DRAWN: the
s9<->s10 matchline carries a HIGH-confidence frame equation, while s10<->s11
has NO printed equation -- log50's join would need evidence that does not
exist on its sheets yet).

The bore (4+51 -> 6+50, 199 ft) is drawn as two sheet-local conduit pieces:
  sheet 10: AP-163 PORT HH (4+51, b.2-bound symbol) -> matchline   [160 ft]
  sheet  9: matchline -> 6+50 FLOWER POT (b.8-bound symbol)        [ 39 ft]

General cross-sheet join law (every clause printed or drawn; no guessing):
  1. A bound structure anchors each sheet's conduit chain (containment, b.6).
  2. Each chain TERMINATES at its sheet's drawn matchline (within the dashed-
     line gap -- the same constant that joins dashes joins the last dash to
     the boundary; nothing widened).
  3. ONE printed frame equation is typeset AT BOTH matchlines (frame-graph
     HIGH edge, M8.2a grammar) -- the human-visible "these edges are the same
     place" statement.
  4. The printed run callouts on the two sheets SHARE the boundary station,
     and that station IS the equation's local-side value.
  5. Footage closure: the printed segment footages sum to the bore span, and
     each sheet's drawn structure->matchline distance over its printed
     footage yields an implied scale; the two implied scales must AGREE
     (drawn geometry corroborates the printed math on both sides).

Verdict here: **CROSS_SHEET_CONTINUATION_PROVEN** for log65 (all gates).
Proof-only: NO stroke is drawn; the cross-sheet joined stroke is the named
next artifact (b.10), gated on Patrick's grade of this probe.

Outputs (gitignored): data/outputs/cross_sheet_conduit_join_probe/

Run (repo root): $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_cross_sheet_conduit_join_probe
"""
from __future__ import annotations

import json
import math
import os
import re
from typing import Dict, List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw

from truelinev2.config import _REPO_ROOT
from truelinev2.extract.conduit_topology import (
    MAX_DASH_GAP,
    connected_chain,
    dash_endpoints,
    symbol_footprint,
)
from truelinev2.extract.registry import select_dialect
from truelinev2.extract.structure_position import (
    BRENHAM_CONDUIT_LAYERS,
    BRENHAM_STRUCTURE_LAYERS,
    POSITION_BOUND,
    resolve_structure_position,
)
from truelinev2.ingest.normalize import load_borelog
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.match.frames import translate_between_sheets
from truelinev2.proof.run_brenham_corpus import EXPECTED_COUNT, PDF, enumerate_corpus
from truelinev2.proof.run_reviewer_service_contract import resolve_corpus
from truelinev2.render.crop import REDLINE_STROKE_RGB
from truelinev2.service import _build_plan_frame_graph

# Stroke-color law: the bore's drawn conduit-path overlay is ALWAYS red
# (never the source layer's color) -- pinned to the canonical constant.
CHAIN_STROKE_RGB = REDLINE_STROKE_RGB

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "cross_sheet_conduit_join_probe"
# Brenham dialect fact (proof-local until a resolver lane ships): the drawn
# sheet-boundary lives on the MATCHLINE CAD layer.
MATCHLINE_LAYER = "MATCHLINE"
SHEET_A, SHEET_B = 10, 9            # A holds the start-side chain, B the end
EXPECT_EDGE_SOURCE = "STA 38+90/6+11"
BOUNDARY_STA_LOCAL = 611.0          # 6+11 -- the shared boundary station
SEG_A_FT, SEG_B_FT = 160.0, 39.0    # printed run callout footages
EQ_NEAR_PT = 25.0                   # equation text typeset AT the matchline
SCALE_REL_TOL = 0.05                # the two implied scales must AGREE tightly
PROVEN = "CROSS_SHEET_CONTINUATION_PROVEN"
NOT_PROVEN = "CROSS_SHEET_CONTINUATION_NOT_PROVEN"

PROVEN_LAW = ("bound structure per sheet + chain terminates at its drawn "
              "matchline + ONE printed frame equation typeset at both "
              "matchlines + shared boundary station + footage closure with "
              "agreeing implied scales")


# --- pure helpers (offline-testable) ----------------------------------------------------

def nearest_gap(points: Sequence[Tuple[float, float]],
                bbox: Tuple[float, float, float, float]) -> Optional[float]:
    """Min distance from any point to a bbox (0 inside). None without points."""
    best = None
    for x, y in points:
        dx = max(bbox[0] - x, 0.0, x - bbox[2])
        dy = max(bbox[1] - y, 0.0, y - bbox[3])
        d = math.hypot(dx, dy)
        best = d if best is None or d < best else best
    return best


def matchline_bboxes(drawings: Sequence[dict], layer: str,
                     min_len: float = 100.0) -> List[Tuple[float, float, float, float]]:
    """The sheet's drawn boundary lines: long thin drawings on the matchline
    layer (length floor excludes legend ticks; injected layer name)."""
    out = []
    for d in drawings:
        if d.get("layer") != layer:
            continue
        w, h = d["x1"] - d["x0"], d["y1"] - d["y0"]
        if max(w, h) >= min_len and min(w, h) <= 6.0:
            out.append((d["x0"], d["y0"], d["x1"], d["y1"]))
    return out


def find_run_callout_footage(lines: Sequence[str], start_sta: str,
                             end_sta: str) -> Optional[float]:
    """Printed footage of the run callout ``STA <a> TO [STA] <b> ... (NNN')``
    -- footage searched on the callout line and the next two lines."""
    pat = re.compile(rf"STA\s*{re.escape(start_sta)}\s*TO\s*(?:STA\s*)?"
                     rf"{re.escape(end_sta)}\b", re.I)
    foot = re.compile(r"\((\d+(?:,\d{3})?)'\)")
    for i, ln in enumerate(lines):
        if not pat.search(ln):
            continue
        for cand in lines[i:i + 3]:
            m = foot.search(cand)
            if m:
                return float(m.group(1).replace(",", ""))
    return None


def cross_sheet_join_verdict(*, equation_edge: bool, eq_at_matchline_a: bool,
                             eq_at_matchline_b: bool, chain_a_reaches: bool,
                             chain_b_reaches: bool, seg_a_ft: Optional[float],
                             seg_b_ft: Optional[float], span_ft: float,
                             scale_a: Optional[float], scale_b: Optional[float],
                             rel_tol: float = SCALE_REL_TOL) -> dict:
    """The join law as a pure decision. Any missing clause -> NOT_PROVEN with
    the exact missing artifact named; nothing is ever inferred to fill a gap."""
    missing = []
    if not equation_edge:
        missing.append("a printed matchline frame equation joining the two "
                       "sheets (frame-graph HIGH edge)")
    if not (eq_at_matchline_a and eq_at_matchline_b):
        missing.append("the equation text typeset AT both drawn matchlines")
    if not chain_a_reaches:
        missing.append("sheet A's conduit chain terminating at its matchline")
    if not chain_b_reaches:
        missing.append("sheet B's conduit chain terminating at its matchline")
    if seg_a_ft is None or seg_b_ft is None:
        missing.append("printed run-callout footages on both sheets")
    elif abs((seg_a_ft + seg_b_ft) - span_ft) > 0.5:
        missing.append(f"footage closure (printed {seg_a_ft}+{seg_b_ft} != "
                       f"bore span {span_ft})")
    if scale_a is None or scale_b is None or scale_a <= 0:
        missing.append("drawn structure->matchline distances on both sheets")
    elif abs(scale_a - scale_b) / scale_a > rel_tol:
        missing.append(f"implied-scale agreement (sheet A {scale_a:.4f} vs "
                       f"sheet B {scale_b:.4f} pt/ft)")
    if missing:
        return {"verdict": NOT_PROVEN, "named_missing": "; ".join(missing)}
    return {"verdict": PROVEN, "law": PROVEN_LAW}


def _render_png(plan, offset, a, b) -> Optional[str]:
    """Two corridor clips stacked: sheet A above, sheet B below, with the
    structures ringed, chains boxed, matchlines + equation text marked."""
    clips = []
    for s in (a, b):
        rendered = plan.render_clip(s["sheet"], offset, s["clip"], zoom=2.0,
                                    pad=50.0)
        if rendered is None:
            return None
        img, cx0, cy0 = rendered
        draw = ImageDraw.Draw(img)
        z = 2.0

        def px(p, cx0=cx0, cy0=cy0):
            return ((p[0] - cx0) * z, (p[1] - cy0) * z)

        orange, blue = (235, 130, 20), (30, 90, 200)
        for d in s["chain"]:  # the bore's conduit-path overlay: ALWAYS red
            (x0, y0), (x1, y1) = px((d["x0"], d["y0"])), px((d["x1"], d["y1"]))
            draw.rectangle([x0 - 3, y0 - 3, x1 + 3, y1 + 3],
                           outline=CHAIN_STROKE_RGB, width=3)
        x, y = px(s["anchor_xy"])
        draw.ellipse([x - 13, y - 13, x + 13, y + 13], outline=(255, 255, 255), width=7)
        draw.ellipse([x - 13, y - 13, x + 13, y + 13], outline=s["anchor_color"], width=4)
        ml = s["matchline"]
        (x0, y0), (x1, y1) = px((ml[0], ml[1])), px((ml[2], ml[3]))
        draw.rectangle([x0 - 3, y0 - 3, x1 + 3, y1 + 3], outline=blue, width=4)
        ex, ey = px(s["eq_xy"])
        draw.rectangle([ex - 44, ey - 12, ex + 44, ey + 12], outline=orange, width=3)
        cap = s["caption"]
        draw.rectangle([0, 0, img.width, 26], fill=(255, 255, 255))
        draw.text((8, 7), cap[:200], fill=(20, 20, 20))
        clips.append(img)
    w = max(i.width for i in clips)
    out = Image.new("RGB", (w, sum(i.height for i in clips) + 8), (255, 255, 255))
    out.paste(clips[0], (0, 0))
    out.paste(clips[1], (0, clips[0].height + 8))
    os.makedirs(OUT_DIR, exist_ok=True)
    path = str(OUT_DIR / "log65_s10_s9_cross_sheet_join.png")
    out.save(path)
    return path


def main() -> int:
    corpus_dir, how = resolve_corpus()
    print(f"[m8.14b9p0] corpus dir : {corpus_dir}  ({how})")
    if not os.path.isfile(PDF) or not os.path.isdir(corpus_dir):
        print("[m8.14b9p0] STOP: inputs missing")
        return 2
    corpus = {p.stem: p for p in enumerate_corpus(corpus_dir)}
    if len(corpus) != EXPECTED_COUNT:
        print(f"[m8.14b9p0] STOP: corpus drift ({len(corpus)})")
        return 3
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for stale in OUT_DIR.glob("*.png"):
        stale.unlink()

    plan = PlanPdf(PDF)
    ok = True
    try:
        dialect = select_dialect(plan)
        offset = dialect.calibrate(plan, 13)
        bore = load_borelog(str(corpus["bore_log65"]))
        span_ft = bore.station_end_ft - bore.station_start_ft
        dA = plan.line_items(SHEET_A, offset)
        dB = plan.line_items(SHEET_B, offset)

        # G1 anchors reproduce: AP-163 on sheet 10 (b.2), end pot on sheet 9 (b.8)
        ap = resolve_structure_position(
            label_text="AP-163", structure_class="terminal_port_hh",
            words=plan.words(SHEET_A, offset), drawings=dA,
            layer_table=BRENHAM_STRUCTURE_LAYERS)
        pot = resolve_structure_position(
            label_text="6+50", structure_class="flower_pot",
            words=plan.words(SHEET_B, offset), drawings=dB,
            layer_table=BRENHAM_STRUCTURE_LAYERS, context_texts=("FLOWER", "POT"))
        g1 = (ap.result == POSITION_BOUND and pot.result == POSITION_BOUND
              and bore.station_start_ft == 451.0 and bore.station_end_ft == 650.0)
        print(f"[m8.14b9p0] {'PASS' if g1 else 'FAIL'}  G1 anchors: AP-163 "
              f"{[round(c, 1) for c in ap.symbol_xy] if ap.symbol_xy else None} s{SHEET_A} / "
              f"pot {[round(c, 1) for c in pot.symbol_xy] if pot.symbol_xy else None} s{SHEET_B}")
        ok &= g1

        # G2 the printed frame equation joins the sheets (HIGH edge + translate)
        graph = _build_plan_frame_graph(plan, offset)
        edge = next((e for e in graph.edges
                     if {e.from_frame, e.to_frame} == {f"sheet:{SHEET_A}", f"sheet:{SHEET_B}"}
                     and e.source == EXPECT_EDGE_SOURCE), None)
        tr = translate_between_sheets(graph, SHEET_A, SHEET_B, BOUNDARY_STA_LOCAL)
        g2 = edge is not None and str(edge.confidence.value) == "HIGH" and tr == 3890.0
        print(f"[m8.14b9p0] {'PASS' if g2 else 'FAIL'}  G2 frame equation: "
              f"{edge.source if edge else None} translate(6+11)->s9={tr}")
        ok &= g2

        # G3 the equation text is typeset AT both drawn matchlines
        mlA = matchline_bboxes(dA, MATCHLINE_LAYER)
        mlB = matchline_bboxes(dB, MATCHLINE_LAYER)
        def eq_word(sheet):
            for w in plan.words(sheet, offset):
                if w["text"] == "38+90/6+11":
                    return (w["xc"], w["yc"])
            return None
        eqA, eqB = eq_word(SHEET_A), eq_word(SHEET_B)
        gapA = min((nearest_gap([eqA], bb) for bb in mlA), default=None) if eqA else None
        gapB = min((nearest_gap([eqB], bb) for bb in mlB), default=None) if eqB else None
        ml_a = min(mlA, key=lambda bb: nearest_gap([eqA], bb)) if eqA and mlA else None
        ml_b = min(mlB, key=lambda bb: nearest_gap([eqB], bb)) if eqB and mlB else None
        g3 = (gapA is not None and gapA <= EQ_NEAR_PT
              and gapB is not None and gapB <= EQ_NEAR_PT)
        print(f"[m8.14b9p0] {'PASS' if g3 else 'FAIL'}  G3 equation at both "
              f"matchlines: s{SHEET_A} gap={gapA and round(gapA, 1)} "
              f"s{SHEET_B} gap={gapB and round(gapB, 1)} (<= {EQ_NEAR_PT})")
        ok &= g3

        # G4 each sheet's conduit chain terminates at ITS matchline
        layer = BRENHAM_CONDUIT_LAYERS["VACANT HDPE"]
        chainA = connected_chain([d for d in dA if d["layer"] == layer],
                                 symbol_footprint(dA, "NEXTLINK", tuple(ap.symbol_xy)))
        chainB = connected_chain([d for d in dB if d["layer"] == layer],
                                 symbol_footprint(dB, "FLOWER POT", tuple(pot.symbol_xy)))
        reachA = nearest_gap(dash_endpoints(chainA), ml_a) if ml_a else None
        reachB = nearest_gap(dash_endpoints(chainB), ml_b) if ml_b else None
        g4 = (reachA is not None and reachA <= MAX_DASH_GAP
              and reachB is not None and reachB <= MAX_DASH_GAP)
        print(f"[m8.14b9p0] {'PASS' if g4 else 'FAIL'}  G4 chains reach their "
              f"matchlines: s{SHEET_A} {len(chainA)} segs gap="
              f"{reachA and round(reachA, 1)} / s{SHEET_B} {len(chainB)} segs "
              f"gap={reachB and round(reachB, 1)} (<= {MAX_DASH_GAP})")
        ok &= g4

        # G5 printed callouts share the boundary station; footage closure;
        #     drawn distances at printed footages give AGREEING implied scales
        segA = find_run_callout_footage(plan.lines(SHEET_A, offset), "4+51", "6+11")
        segB = find_run_callout_footage(plan.lines(SHEET_B, offset), "6+11", "6+50")
        distA = nearest_gap([tuple(ap.symbol_xy)], ml_a) if ml_a else None
        distB = nearest_gap([tuple(pot.symbol_xy)], ml_b) if ml_b else None
        scaleA = (distA / segA) if distA and segA else None
        scaleB = (distB / segB) if distB and segB else None
        verdict = cross_sheet_join_verdict(
            equation_edge=g2, eq_at_matchline_a=bool(g3), eq_at_matchline_b=bool(g3),
            chain_a_reaches=bool(reachA is not None and reachA <= MAX_DASH_GAP),
            chain_b_reaches=bool(reachB is not None and reachB <= MAX_DASH_GAP),
            seg_a_ft=segA, seg_b_ft=segB, span_ft=span_ft,
            scale_a=scaleA, scale_b=scaleB)
        g5 = (segA == SEG_A_FT and segB == SEG_B_FT
              and verdict["verdict"] == PROVEN)
        print(f"[m8.14b9p0] {'PASS' if g5 else 'FAIL'}  G5 closure: printed "
              f"{segA}+{segB} == span {span_ft}; implied scales "
              f"{scaleA and round(scaleA, 4)} / {scaleB and round(scaleB, 4)} "
              f"-> {verdict['verdict']}")
        if verdict["verdict"] != PROVEN:
            print(f"[m8.14b9p0]      missing: {verdict['named_missing']}")
        ok &= g5

        png = None
        if ml_a and ml_b:
            png = _render_png(plan, offset, {
                "sheet": SHEET_A, "chain": chainA, "anchor_xy": tuple(ap.symbol_xy),
                "anchor_color": (30, 90, 200), "matchline": ml_a, "eq_xy": eqA,
                "clip": [min(ml_a[0], ap.symbol_xy[0]), 300,
                         max(ml_a[2], ap.symbol_xy[0]), 400],
                "caption": ("sheet 10: AP-163 (blue ring) -> RED conduit-path "
                            "overlay -> MATCHLINE (blue box) with printed "
                            "equation 38+90/6+11 (orange) · 160' segment"),
            }, {
                "sheet": SHEET_B, "chain": chainB, "anchor_xy": tuple(pot.symbol_xy),
                "anchor_color": (20, 140, 60), "matchline": ml_b, "eq_xy": eqB,
                "clip": [min(pot.symbol_xy[0], ml_b[0]) - 40, 300,
                         max(ml_b[2], pot.symbol_xy[0]) + 10, 400],
                "caption": ("sheet 9: same equation at ITS matchline (orange) "
                            "-> RED conduit-path overlay -> 6+50 flower pot "
                            "(green ring) · 39' segment · joined span = 199' = bore"),
            })
        pngs = sorted(p.name for p in OUT_DIR.glob("*.png"))
        g6 = png is not None and len(pngs) == 1 and "stroke" not in pngs[0]
        print(f"[m8.14b9p0] {'PASS' if g6 else 'FAIL'}  G6 exactly one probe "
              f"PNG (no stroke artifact): {pngs}")
        ok &= g6

        report = {
            "milestone": ("truelinev2 M8.14.b.9 Phase 0 -- matchline-joined "
                          "cross-sheet conduit chain probe (log65; PROVEN)"),
            "corpus_dir_used": corpus_dir, "corpus_resolution": how,
            "plan_pdf": PDF, "verdict": "PASS" if ok else "FAILURE",
            "honesty": ("every clause printed or drawn: bound structures, "
                        "chains terminating at drawn matchlines, ONE printed "
                        "equation typeset at both boundaries, shared boundary "
                        "station, printed footage closure, agreeing implied "
                        "scales; proof-only -- no stroke, no placement, no "
                        "engine wiring; log50 remains blocked (its s10<->s11 "
                        "matchline prints NO frame equation -- that absence "
                        "is the exact missing artifact for its lane)"),
            "join": verdict,
            "evidence": {
                "frame_edge": EXPECT_EDGE_SOURCE, "translate_6p11_to_s9": tr,
                "eq_gap_to_matchline_pt": {"s10": gapA, "s9": gapB},
                "chain_reach_gap_pt": {"s10": reachA, "s9": reachB},
                "printed_footages": {"s10": segA, "s9": segB, "span": span_ft},
                "implied_scales": {"s10": scaleA, "s9": scaleB},
                "anchors": {"ap163_s10": list(ap.symbol_xy),
                            "pot_s9": list(pot.symbol_xy)},
            },
            "named_next_artifact": ("b.10: the log65 cross-sheet joined "
                                    "symbol-anchored stroke (two sheet-local "
                                    "strokes sharing the matchline boundary), "
                                    "gated on Patrick's grade of this probe"),
            "png": png,
        }
        (OUT_DIR / "cross_sheet_conduit_join_probe.json").write_text(
            json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(f"[m8.14b9p0] verdict: {report['verdict']}")
        print(f"[m8.14b9p0] VISUAL FILE for Patrick: {png}")
        print(f"[m8.14b9p0] report -> "
              f"{OUT_DIR / 'cross_sheet_conduit_join_probe.json'}")
    finally:
        plan.close()
    return 0 if ok else 4


if __name__ == "__main__":
    raise SystemExit(main())
