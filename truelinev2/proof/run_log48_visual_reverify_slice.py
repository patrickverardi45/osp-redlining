r"""LOG48 VISUAL RE-VERIFICATION (READ-ONLY; renders NO redline; proof-first lane).

OWNER REOPEN (2026-06-17): the prior log48 ABSTAIN report is wrong/incomplete -- it relied on PDF text
search for the handwritten value `5+09` and concluded "0x / only log50's 5+14 is drawn". Owner screenshots
show log48/Segment A HAS plan-side representation: a DISTINCT route that
  starts at the reset HH  STA 45+33=0+00  PLACE 24"x34"x24" NEXTLINK HH  PROP. SPLICE POINT 46  (sheet 10),
  runs up Woodson Ln  STA 0+00 -> 1+90 (190'),
  crosses the  1+90 - SEE SHEET 12  matchline (reciprocal SEE SHEET 10 on sheet 12),
  continues  STA 1+90 -> 3+50 (160')  through the 8-PORT HH AP-167 SPLICE LOC 46 @ 3+50,
  and ends  STA 3+50 -> 5+07 (157')  at the  STA 5+07 11"x11"x12" FLOWER POT  (sheet 12).
  190+160+157 = 507 ft = station 5+07 (internally consistent).
This is NOT log50's route: log50 = 0+00 -> 5+14 on sheets 10+11, crossing the 1+39 matchline, ending at the
5+14 FLOWER POT on sheet 11 (see run_log50_cross_sheet_assembly_slice).

This slice is a READ-ONLY EVIDENCE DUMP. It does NOT place a stroke, NOT mutate the corpus, NOT change the
census, NOT touch the loader/product/runtime/web/backend/main/deploy. It:
  1. extracts, per sheet (10/11/12), every  STA a TO STA b (NNN')  bore callout and every  SEE SHEET / MATCHLINE
     line, plus the coordinates of each owner-claimed token (text layer);
  2. rasterizes sheets 10/11/12 (full page) + high-DPI crops around each owner-claimed token so the labels can be
     read VISUALLY (not text-grep alone);
  3. runs the committed parent-source gate child_owns_route() for log48 on its OWN 5+07 route vs log50's 5+14
     route, proving the gate passes the former and rejects the latter (the anti sibling-mixup result).

All artifacts under gitignored data/outputs/. NO red stroke is placed (this is verification, not rendering).

Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_log48_visual_reverify_slice
"""
from __future__ import annotations

import json
import os
import re

import fitz  # read-only rasterization for visual verification (proof slice; not engine code)

from truelinev2.config import _REPO_ROOT
from truelinev2.extract.registry import select_dialect
from truelinev2.ingest.parent_source import (
    _own_span, child_owns_route, entry, siblings, span_collision_siblings,
)
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.proof.run_brenham_corpus import PDF

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "log48_visual_reverify"
SHEETS = (10, 11, 12)

# owner-claimed tokens -> (sheet, search_query, crop_name). Each is searched in the text layer; coords feed a
# high-DPI crop so the label is confirmed VISUALLY. A token absent from the text layer still gets a full-sheet
# raster fallback for manual reading.
CROP_TARGETS = [
    (10, "45+33", "s10_reset_hh_45+33"),
    (10, "SPLICE POINT 46", "s10_splice_point_46"),
    (10, "SLACK COIL", "s10_slack_coil"),
    (10, "SEE SHEET 12", "s10_matchline_see_sheet_12"),
    (10, "STA 0+00 TO STA 1+90", "s10_bore_0+00_to_1+90"),
    (10, "1+90", "s10_sta_1+90"),
    (11, "5+14", "s11_log50_terminus_5+14"),
    (11, "SEE SHEET 10", "s11_matchline_see_sheet_10"),
    (11, "1+39", "s11_sta_1+39"),
    (12, "STA 5+07", "s12_terminus_5+07"),
    (12, "5+07", "s12_sta_5+07"),
    (12, "FLOWER POT", "s12_flower_pot"),
    (12, "SEE SHEET 10", "s12_matchline_see_sheet_10"),
    (12, "AP-167", "s12_ap167"),
    (12, "SPLICE LOC 46", "s12_splice_loc_46"),
    (12, "8 PORT", "s12_8_port_hh"),
    (12, "STA 1+90 TO STA 3+50", "s12_bore_1+90_to_3+50"),
    (12, "STA 3+50 TO STA 5+07", "s12_bore_3+50_to_5+07"),
]

# owner checkpoints -> the search query whose text-layer presence answers it
CHECKPOINTS = {
    "reset_hh_45+33=0+00 (sheet10)": (10, "45+33"),
    "splice_point_46 (sheet10)": (10, "SPLICE POINT 46"),
    "bore 0+00->1+90 190ft (sheet10)": (10, "STA 0+00 TO STA 1+90"),
    "matchline 1+90 SEE SHEET 12 (sheet10)": (10, "SEE SHEET 12"),
    "reciprocal SEE SHEET 10 (sheet12)": (12, "SEE SHEET 10"),
    "bore 1+90->3+50 160ft (sheet12)": (12, "STA 1+90 TO STA 3+50"),
    "8-port HH AP-167 SPLICE LOC 46 @3+50 (sheet12)": (12, "AP-167"),
    "bore 3+50->5+07 157ft (sheet12)": (12, "STA 3+50 TO STA 5+07"),
    "terminus STA 5+07 FLOWER POT (sheet12)": (12, "STA 5+07"),
    "DISTINCT: log50 terminus 5+14 (sheet11)": (11, "5+14"),
    "DISTINCT: log50 matchline 1+39 (sheet11)": (11, "1+39"),
}

CALLOUT_RE = re.compile(r"STA\s+(\d+\+\d+)\s+TO\s+STA\s+(\d+\+\d+)", re.I)
FOOT_RE = re.compile(r"\((\d+)\s*['′’]?\s*\)")
SEE_RE = re.compile(r"SEE\s+SHEET\s+(\d+)", re.I)
STA_RE = re.compile(r"(\d+\+\d+)")


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def callouts_on(plan, sheet, off):
    """All STA a TO STA b (NNN') callouts on a sheet (regex over whitespace-normalized full text)."""
    full = _norm(plan.text_by_index(plan.page_index(sheet, off)))
    out = []
    for m in CALLOUT_RE.finditer(full):
        window = full[m.start(): m.start() + 140]
        fm = FOOT_RE.search(window)
        out.append({"from_sta": m.group(1), "to_sta": m.group(2),
                    "footage": int(fm.group(1)) if fm else None,
                    "context": _norm(window)[:120]})
    return out


def see_sheet_lines(plan, sheet, off):
    """Every line mentioning SEE SHEET / MATCHLINE, with the target sheet + any station on the line."""
    out = []
    for ln in plan.lines(sheet, off):
        u = ln.upper()
        if "SEE SHEET" in u or "MATCHLINE" in u:
            sm = SEE_RE.search(ln)
            out.append({"text": _norm(ln), "see_sheet": int(sm.group(1)) if sm else None,
                        "stations": STA_RE.findall(ln)})
    return out


def search_coords(plan, sheet, off, query):
    return [[round(v, 1) for v in b] for b in plan.search(sheet, off, query)]


def render_full(plan, sheet, off, zoom=2.2):
    idx = plan.page_index(sheet, off)
    if not (0 <= idx < plan.page_count):
        return None
    page = plan._doc[idx]
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), colorspace=fitz.csRGB, alpha=False)
    path = OUT_DIR / f"sheet{sheet}_full.png"
    pix.save(str(path))
    return {"path": str(path), "w": pix.width, "h": pix.height}


def render_crop(plan, sheet, off, query, name, zoom=5.0, pad=150.0):
    hits = plan.search(sheet, off, query)
    if not hits:
        return None
    res = plan.render_clip(sheet, off, hits[0], zoom=zoom, pad=pad)
    if not res:
        return None
    img, _, _ = res
    path = OUT_DIR / f"crop_{name}.png"
    img.save(str(path))
    return {"path": str(path), "query": query, "sheet": sheet, "bbox": [round(v, 1) for v in hits[0]],
            "n_hits": len(hits), "w": img.width, "h": img.height}


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for stale in OUT_DIR.glob("*.png"):
        stale.unlink()
    ev = {"pdf": PDF, "pdf_exists": os.path.isfile(PDF)}
    if not os.path.isfile(PDF):
        print("[log48-reverify] PDF MISSING -> scope blocked")
        (OUT_DIR / "log48_visual_reverify.json").write_text(json.dumps(ev, indent=2), encoding="utf-8")
        return 1

    plan = PlanPdf(PDF)
    try:
        off = select_dialect(plan).calibrate(plan, 13)
        ev["offset"] = off
        ev["page_index_0based"] = {f"sheet{s}": plan.page_index(s, off) for s in SHEETS}
        ev["page_human_1based"] = {f"sheet{s}": plan.page_index(s, off) + 1 for s in SHEETS}
        ev["page_count"] = plan.page_count

        # 1) per-sheet bore callouts + matchline lines (full inventory, not just owner-claimed)
        ev["callouts"] = {f"sheet{s}": callouts_on(plan, s, off) for s in SHEETS}
        ev["see_sheet_lines"] = {f"sheet{s}": see_sheet_lines(plan, s, off) for s in SHEETS}

        # 2) owner checkpoint presence (text layer) + coords
        ev["checkpoints"] = {}
        for label, (s, q) in CHECKPOINTS.items():
            coords = search_coords(plan, s, off, q)
            ev["checkpoints"][label] = {"sheet": s, "query": q, "found": bool(coords),
                                        "n_hits": len(coords), "coords": coords[:6]}

        # 3) rasters (full sheets) + crops (visual confirmation)
        ev["full_rasters"] = {f"sheet{s}": render_full(plan, s, off) for s in SHEETS}
        ev["crops"] = {}
        for s, q, name in CROP_TARGETS:
            ev["crops"][name] = render_crop(plan, s, off, q, name)

        # 4) parent-source gate: log48 OWN 5+07 route vs log50's 5+14 route (anti sibling-mixup)
        _, e48 = entry("log48")
        own_str, own_ft = _own_span("log48", e48)
        gate = {
            "log48_own_span_resolved": {"span": own_str, "ft": own_ft,
                                        "corpus_span": e48["entry_span"],
                                        "adj_corrected_span": e48.get("adj_corrected_span"),
                                        "siblings": siblings("log48"),
                                        "span_collision_siblings": span_collision_siblings("log48")},
            "log48_on_5+07_route_507ft_sheets_10_12": _verdict(child_owns_route("log48", 507.0, [10, 12])),
            "log48_on_5+14_route_514ft_sheets_10_11": _verdict(child_owns_route("log48", 514.0, [10, 11])),
            "log50_on_5+14_route_514ft_sheets_10_11": _verdict(child_owns_route("log50", 514.0, [10, 11])),
            "log50_on_5+07_route_507ft_sheets_10_12": _verdict(child_owns_route("log50", 507.0, [10, 12])),
        }
        ev["parent_source_gate"] = gate
    finally:
        plan.close()

    (OUT_DIR / "log48_visual_reverify.json").write_text(json.dumps(ev, indent=2, default=str), encoding="utf-8")
    _print(ev)
    return 0


def _verdict(t):
    ok, reason = t
    return {"owns": ok, "reason": reason}


def _print(ev):
    print(f"[log48-reverify] offset={ev['offset']}  page_count={ev['page_count']}")
    print(f"[log48-reverify] sheet->page(1based): {ev['page_human_1based']}")
    for s in SHEETS:
        cs = ev["callouts"][f"sheet{s}"]
        print(f"\n[log48-reverify] === SHEET {s} (page {ev['page_human_1based'][f'sheet{s}']}) "
              f"-- {len(cs)} bore callouts ===")
        for c in cs:
            print(f"    STA {c['from_sta']} TO {c['to_sta']}  ({c['footage']}')  | {c['context']}")
        for sl in ev["see_sheet_lines"][f"sheet{s}"]:
            print(f"    [matchline] see_sheet={sl['see_sheet']} sta={sl['stations']} | {sl['text']}")
    print("\n[log48-reverify] === OWNER CHECKPOINTS (text layer) ===")
    for label, r in ev["checkpoints"].items():
        print(f"    {'FOUND ' if r['found'] else 'ABSENT'} ({r['n_hits']}x) {label}  q={r['query']!r}")
    print("\n[log48-reverify] === PARENT-SOURCE GATE ===")
    g = ev["parent_source_gate"]
    print(f"    log48 own span resolved: {g['log48_own_span_resolved']['span']} "
          f"({g['log48_own_span_resolved']['ft']}ft); corpus={g['log48_own_span_resolved']['corpus_span']} "
          f"adj={g['log48_own_span_resolved']['adj_corrected_span']} "
          f"collision_siblings={g['log48_own_span_resolved']['span_collision_siblings']}")
    for k in ("log48_on_5+07_route_507ft_sheets_10_12", "log48_on_5+14_route_514ft_sheets_10_11",
              "log50_on_5+14_route_514ft_sheets_10_11", "log50_on_5+07_route_507ft_sheets_10_12"):
        v = g[k]
        print(f"    {k}: owns={v['owns']}\n        -> {v['reason']}")
    n_crops = sum(1 for v in ev["crops"].values() if v)
    print(f"\n[log48-reverify] rasters: 3 full sheets + {n_crops}/{len(ev['crops'])} crops -> {OUT_DIR}")


if __name__ == "__main__":
    raise SystemExit(main())
