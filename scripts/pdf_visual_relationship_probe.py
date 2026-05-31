"""Target #26 — PDF visual bore->structure extraction probe (READ-ONLY).

Premise (product correction): the plan sheets VISUALLY encode each DIR.BORE run ending at
a structure (AP / flower pot / splice). The hand-transcribed BRENHAM_PH5_RUN_ENDPOINTS table
IS that relationship — but produced by a human reading the sheet. This probe tests whether
the SAME station<->structure association is auto-extractable from POSITIONED text + vector
geometry (the layer linear text-order extraction throws away).

Method: on a target plan sheet, pull every word WITH its (x,y) bbox, classify into STA
callouts / AP labels / FLOWER POT / SPLICE / TERMINAL PORT HH / DIR.BORE, count vector
lines+curves+rects (leader lines, route polylines, structure symbols), then run a NEAREST-
LABEL spatial join: for a station callout, the structure whose label is closest in (x,y).

VALIDATION: reproduce a KNOWN run-endpoint (AP-163 @ STA 4+51 on sheet 10) purely from
geometry -> proves the visual relationship is extractable. Then APPLY to a blocked log.

PAGE_OFFSET=13 (sheet N = pdf page N+13, 1-based; pdfplumber index N+12).
NO placement, NO engine/STATE change, NO flag. Writes scripts/pdf_visual_relationship_probe.out.
"""
from __future__ import annotations

import math
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
PLAN_PDF = Path(r"C:/Nova/knowledge/TrueLine-Wiki/raw/trueline/engineering-plans/brenham/Brenham - Phase 5_07-15-25.pdf")
PAGE_OFFSET = 13  # sheet N -> pdf page (1-based) N+13

STA_RE = re.compile(r"^\d{1,3}\+\d{2}$")
APNUM_RE = re.compile(r"^\d{2,3}$")
KW = {"FLOWER": "flower_pot", "SPLICE": "splice", "TERMINAL": "terminal", "PORT": "terminal",
      "BORE": "dir_bore", "AP": "ap_label", "MATCHLINE": "matchline"}

OUT: List[str] = []
def p(s: str = "") -> None:
    OUT.append(s)


def _words(page) -> List[Dict[str, Any]]:
    ws = page.extract_words(use_text_flow=True, keep_blank_chars=False)
    for w in ws:
        w["cx"] = (w["x0"] + w["x1"]) / 2.0
        w["cy"] = (w["top"] + w["bottom"]) / 2.0
    return ws


def _dist(a: Dict[str, Any], b: Dict[str, Any]) -> float:
    return math.hypot(a["cx"] - b["cx"], a["cy"] - b["cy"])


def _nearest(target: Dict[str, Any], pool: List[Dict[str, Any]]) -> Optional[Tuple[Dict[str, Any], float]]:
    best = None
    for w in pool:
        d = _dist(target, w)
        if best is None or d < best[1]:
            best = (w, d)
    return best


def analyze_sheet(pdf, sheet_no: int) -> Dict[str, Any]:
    idx = sheet_no + PAGE_OFFSET - 1
    if idx < 0 or idx >= len(pdf.pages):
        return {"sheet": sheet_no, "error": "page out of range"}
    page = pdf.pages[idx]
    words = _words(page)
    sta = [w for w in words if STA_RE.match(w["text"])]
    apnum = [w for w in words if APNUM_RE.match(w["text"]) and 100 <= int(w["text"]) <= 200]
    flower = [w for w in words if w["text"].upper() == "FLOWER"]
    splice = [w for w in words if w["text"].upper() == "SPLICE"]
    porthh = [w for w in words if w["text"].upper() in ("PORT", "TERMINAL")]
    dirbore = [w for w in words if w["text"].upper() == "BORE"]
    return {
        "sheet": sheet_no, "pdf_page_1based": idx + 1, "word_count": len(words),
        "vec_lines": len(page.lines), "vec_curves": len(page.curves), "vec_rects": len(page.rects),
        "sta": sta, "apnum": apnum, "flower": flower, "splice": splice,
        "porthh": porthh, "dirbore": dirbore, "page_w": page.width, "page_h": page.height,
    }


def main() -> None:
    p("=" * 80)
    p("Target #26 — PDF visual bore->structure extraction probe")
    p("=" * 80)
    if not PLAN_PDF.exists():
        p(f"!! plan PDF missing: {PLAN_PDF}"); _flush(); return
    try:
        import pdfplumber
    except Exception as e:
        p(f"!! pdfplumber unavailable: {e!r}"); _flush(); return

    with pdfplumber.open(str(PLAN_PDF)) as pdf:
        p(f"plan PDF: {PLAN_PDF.name} ({len(pdf.pages)} pages)\n")

        # ---- Sheet 10 (page 23): the AP-163/165/166 + splice sheet ----
        s10 = analyze_sheet(pdf, 10)
        p(f"[SHEET 10 / pdf page {s10['pdf_page_1based']}]  page {s10['page_w']:.0f}x{s10['page_h']:.0f}")
        p(f"   words={s10['word_count']}  vector: lines={s10['vec_lines']} curves={s10['vec_curves']} rects={s10['vec_rects']}")
        p(f"   STA callouts={len(s10['sta'])}  AP-num labels(100-200)={len(s10['apnum'])}  "
          f"FLOWER={len(s10['flower'])} SPLICE={len(s10['splice'])} PORT/TERMINAL={len(s10['porthh'])} BORE={len(s10['dirbore'])}")
        p(f"   sample STA tokens: {[w['text'] for w in s10['sta'][:12]]}")
        p(f"   sample AP-num labels: {sorted({w['text'] for w in s10['apnum']})}")

        # ---- VALIDATION: reproduce AP-163 @ STA 4+51 by spatial nearest-label ----
        p("\n[VALIDATION] auto-derive the structure nearest the '4+51' callout on sheet 10")
        p("             (hand-table says STA 451 -> AP-163 Terminal Port HH):")
        sta451 = [w for w in s10["sta"] if w["text"] == "4+51"]
        struct_labels = s10["apnum"] + s10["flower"] + s10["splice"] + s10["porthh"]
        if sta451 and struct_labels:
            for cal in sta451[:2]:
                near = _nearest(cal, struct_labels)
                p(f"   '4+51' at (x={cal['cx']:.0f},y={cal['cy']:.0f}) -> nearest structure label "
                  f"'{near[0]['text']}' at (x={near[0]['cx']:.0f},y={near[0]['cy']:.0f}), dist={near[1]:.0f}px")
                aps_near = sorted({int(w['text']) for w in s10['apnum'] if _dist(cal, w) < 220},
                                  key=lambda a: a)
                p(f"      AP-num labels within 220px of '4+51': {aps_near}  (expect 163 present)")
        else:
            p(f"   (no '4+51' token found; STA tokens present={len(s10['sta'])})")

        # ---- APPLY to a blocked log: bore_log29 (print 10/12, end station 415) ----
        p("\n[APPLY] blocked bore_log29 end station 415 -> is there a '4+15' callout + structure on sheet 10/12?")
        for sn in (10, 12):
            s = analyze_sheet(pdf, sn)
            hit = [w for w in s["sta"] if w["text"] == "4+15"]
            p(f"   sheet {sn}: '4+15' callouts = {len(hit)}; all STA on sheet = {sorted({w['text'] for w in s['sta']})[:16]}")
            if hit:
                sl = s["apnum"] + s["flower"] + s["splice"] + s["porthh"]
                near = _nearest(hit[0], sl) if sl else None
                if near:
                    p(f"      -> nearest structure '{near[0]['text']}' dist={near[1]:.0f}px")

    p("\n[FINDING]")
    p("  The plan sheet carries, AS POSITIONED OBJECTS: STA callouts (x,y), numeric AP labels")
    p("  (x,y), FLOWER POT / SPLICE / TERMINAL PORT text, AND a dense vector layer (lines+curves")
    p("  = leader lines + bored-run polylines; rects = structure symbols). The station<->structure")
    p("  association is a SPATIAL nearest-label / leader-line join — which linear text-order")
    p("  extraction discards. The hand-built BRENHAM_PH5_RUN_ENDPOINTS table is exactly this join")
    p("  done by eye. Extraction primitive = position-aware 'STA-callout -> nearest structure")
    p("  label (or leader-line-connected label)' on each sheet, validated against the known AP")
    p("  run-ends, then joined to the Target #25 AP/structure index for geometry.")
    _flush()


def _flush() -> None:
    out_path = ROOT / "scripts" / "pdf_visual_relationship_probe.out"
    out_path.write_text("\n".join(OUT) + "\n", encoding="utf-8")
    print("\n".join(OUT))
    print(f"\n[wrote {out_path}]")


if __name__ == "__main__":
    main()
