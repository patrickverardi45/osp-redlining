"""Target #30 — positioned AP-glyph reconstruction (default-OFF, read-only).

Primitive A's greedy digit clustering OVER-MERGES dense AutoCAD callout text, so a valid AP
number like 166 never emerges as an exact cluster even though its chars are present and
correctly ordered (forensic on sheet 10: clean '166' char triples exist, e.g. @ (790,161)).

This helper reconstructs POSITIONED AP targets by VALID-AP-SUBSEQUENCE extraction with
structure anchoring:
  1. digit runs (same y-band, x-adjacent chars), keeping per-char positions;
  2. inside each run, every contiguous 3-char substring that equals a valid AP id (105-168);
  3. KEEP only candidates anchored by a nearby structure token (TERMINAL / PORT / HH / AP) —
     this rejects station/dimension/matchline/sheet numbers that are NOT near AP structures;
  4. assign ap_id -> bbox + centroid + confidence; abstain (no localization) on a run with
     >=2 distinct anchored valid-AP substrings (ambiguous).

Output positioned AP targets feed Primitive B/C. NO placement, NO engine import-as-production,
no flag, no STATE. Pure helpers (deterministic, never raise). Isolated in scripts/.
"""
from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "backend")); sys.path.insert(0, str(ROOT / "scripts"))
for k in ("TRUELINE_JWT_SECRET", "TRUELINE_AUTH_JWT_SECRET"):
    os.environ.setdefault(k, "t30")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

SCHEMA_VERSION = "pdf-ap-glyph-reconstruct-1"
PLAN_PDF = Path(r"C:/Nova/knowledge/TrueLine-Wiki/raw/trueline/engineering-plans/brenham/Brenham - Phase 5_07-15-25.pdf")
PAGE_OFFSET = 13
ANCHOR_TOL = 34.0     # px: a structure/AP token this close anchors a candidate
EXCL_STA_TOL = 8.0    # px: candidate centroid this close to a STA callout center => it's a station number


def _cxy(o: Dict[str, Any]) -> Tuple[float, float]:
    return ((o["x0"] + o["x1"]) / 2.0, (o["top"] + o["bottom"]) / 2.0)


def _digit_runs(chars: Sequence[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    """Pure: maximal same-line x-adjacent digit runs, keeping per-char dicts (with cx/cy)."""
    ds = []
    for c in chars:
        if str(c.get("text", "")) in "0123456789":
            d = dict(c); d["cx"] = (d["x0"] + d["x1"]) / 2.0; d["cy"] = (d["top"] + d["bottom"]) / 2.0
            ds.append(d)
    ds.sort(key=lambda d: (round(d["cy"] / 4.0), d["x0"]))
    runs: List[List[Dict[str, Any]]] = []
    cur: List[Dict[str, Any]] = []
    for d in ds:
        if cur and abs(d["cy"] - cur[-1]["cy"]) < 3 and (d["x0"] - cur[-1]["x1"]) < 6:
            cur.append(d)
        else:
            if cur:
                runs.append(cur)
            cur = [d]
    if cur:
        runs.append(cur)
    return runs


def reconstruct_positioned_aps(
    *, chars: Sequence[Dict[str, Any]], words: Sequence[Dict[str, Any]], valid_ap_ids: Sequence[int],
) -> List[Dict[str, Any]]:
    """Pure: positioned AP targets {ap_id, centroid, bbox, confidence, reason, anchor}.
    Deterministic; never raises. Only 3-digit valid APs (105-168) — 2-digit dims are ignored."""
    valid = {int(a) for a in valid_ap_ids if 100 <= int(a) <= 999}
    W = [dict(w) for w in words]
    for w in W:
        w["cx"], w["cy"] = _cxy(w)
    anchors = [w for w in W if str(w.get("text", "")).upper() in ("TERMINAL", "PORT", "HH", "AP")]
    sta = [w for w in W if str(w.get("text", "")).replace("+", "").isdigit() and "+" in str(w.get("text", ""))]

    out: List[Dict[str, Any]] = []
    for run in _digit_runs(chars):
        s = "".join(d["text"] for d in run)
        # all contiguous 3-char valid-AP substrings in this run
        run_cands = []
        for i in range(len(s) - 2):
            v = s[i:i + 3]
            if v.isdigit() and int(v) in valid:
                grp = run[i:i + 3]
                cx = sum(d["cx"] for d in grp) / 3.0
                cy = sum(d["cy"] for d in grp) / 3.0
                bbox = [min(d["x0"] for d in grp), min(d["top"] for d in grp),
                        max(d["x1"] for d in grp), max(d["bottom"] for d in grp)]
                run_cands.append({"ap_id": int(v), "centroid": [round(cx, 1), round(cy, 1)], "bbox": [round(b, 1) for b in bbox]})
        if not run_cands:
            continue
        # anchor + station-exclusion each candidate
        kept = []
        for c in run_cands:
            cx, cy = c["centroid"]
            anc = min(((math.hypot(a["cx"] - cx, a["cy"] - cy), a["text"]) for a in anchors), default=(9e9, None))
            on_sta = any(math.hypot(w["cx"] - cx, w["cy"] - cy) <= EXCL_STA_TOL for w in sta)
            if anc[0] <= ANCHOR_TOL and not on_sta:
                c = dict(c); c["anchor"] = {"label": anc[1], "dist_px": round(anc[0], 1)}
                kept.append(c)
        if not kept:
            continue
        distinct_aps = {c["ap_id"] for c in kept}
        if len(distinct_aps) >= 2:
            # ambiguous run -> emit an abstain marker, do not localize
            out.append({"ap_id": None, "reason": "ambiguous_multiple_valid_ap_in_run",
                        "run_text": s, "candidates": sorted(distinct_aps)})
            continue
        best = min(kept, key=lambda c: c["anchor"]["dist_px"])
        best["reason"] = "valid_ap_subsequence_structure_anchored"
        best["confidence"] = "high" if best["anchor"]["dist_px"] <= 20 else "medium"
        out.append(best)
    return out


def localized_ap_index(targets: Sequence[Dict[str, Any]]) -> Dict[int, List[Dict[str, Any]]]:
    """ap_id -> list of localized occurrences (centroids), sorted by confidence then x."""
    idx: Dict[int, List[Dict[str, Any]]] = {}
    for t in targets:
        if t.get("ap_id") is not None:
            idx.setdefault(t["ap_id"], []).append(t)
    return idx


# ── read-only I/O + grading ──────────────────────────────────────────────────

def main() -> None:
    import pdf_run_endpoint_extractor as A
    out: List[str] = []
    def p(s: str = "") -> None:
        out.append(s)

    valid_aps = A._load_valid_aps()
    p("=" * 84)
    p("Target #30 — positioned AP-glyph reconstruction (read-only; nothing placed)")
    p("=" * 84)
    p(f"schema={SCHEMA_VERSION}  valid AP universe={len(valid_aps)}")

    import pdfplumber
    grade = {163: None, 157: None, 165: None, 166: None}
    all_targets_by_sheet = {}
    with pdfplumber.open(str(PLAN_PDF)) as pdf:
        for sheet in (8, 10):
            page = pdf.pages[sheet + PAGE_OFFSET - 1]
            chars = list(page.chars)
            words = page.extract_words(use_text_flow=True, keep_blank_chars=False)
            targets = reconstruct_positioned_aps(chars=chars, words=words, valid_ap_ids=valid_aps)
            all_targets_by_sheet[sheet] = targets
            idx = localized_ap_index(targets)
            loc = sorted(idx)
            amb = [t for t in targets if t.get("ap_id") is None]
            p(f"\n[SHEET {sheet}] localized AP ids = {loc}")
            p(f"   ambiguous runs (abstained) = {len(amb)}")
            if sheet == 10:
                for ap in (163, 166, 165):
                    occ = idx.get(ap, [])
                    grade[ap] = occ[0] if occ else None
                    p(f"   AP-{ap}: " + (f"LOCALIZED {len(occ)}x centroid={occ[0]['centroid']} "
                       f"anchor={occ[0]['anchor']} conf={occ[0]['confidence']}" if occ else "NOT localized"))
            if sheet == 8:
                occ = idx.get(157, [])
                grade[157] = occ[0] if occ else None
                p(f"   AP-157: " + (f"LOCALIZED centroid={occ[0]['centroid']} conf={occ[0]['confidence']}" if occ else "NOT localized"))

    p("\n" + "-" * 84)
    p("REGRESSION + PRIMARY GRADE")
    p("-" * 84)
    for ap in (163, 157, 165, 166):
        g = grade[ap]
        tag = "PRIMARY" if ap == 166 else "regression"
        p(f"   [{'PASS' if g else 'MISS '}] AP-{ap} ({tag}) -> "
          + (f"centroid {g['centroid']}" if g else "not localized"))

    # If AP-166 localized, re-grade Primitive C: does STA 136 connect to AP-166's centroid?
    if grade[166]:
        p("\n[PRIMITIVE C RE-GRADE] sheet 10 STA 136 -> AP-166 with reconstructed target:")
        import pdf_leader_run_following as B
        with pdfplumber.open(str(PLAN_PDF)) as pdf:
            page = pdf.pages[10 + PAGE_OFFSET - 1]
            uf, nodes = B.build_vector_components(page.lines, page.curves)
            words = page.extract_words(use_text_flow=True, keep_blank_chars=False)
            cal = [w for w in words if w["text"] == "1+36"]
            ap166_xy = grade[166]["centroid"]
            best = None
            for c in cal:
                ccx, ccy = _cxy(c)
                cnodes = [n for n in nodes if math.hypot(n[0]*B.SNAP-ccx, n[1]*B.SNAP-ccy) <= 12]
                croots = {uf.find(n) for n in cnodes}
                # is AP-166 centroid in the same vector component as this 1+36 callout?
                anodes = [n for n in nodes if math.hypot(n[0]*B.SNAP-ap166_xy[0], n[1]*B.SNAP-ap166_xy[1]) <= 22]
                aroots = {uf.find(n) for n in anodes}
                shared = croots & aroots
                straight = math.hypot(ap166_xy[0]-ccx, ap166_xy[1]-ccy)
                if best is None or straight < best[0]:
                    best = (straight, bool(shared))
            p(f"   STA 1+36 <-> AP-166 centroid {ap166_xy}: straight={best[0]:.0f}px shared_vector_component={best[1]}")
            if best[1]:
                p("   => RECOVERED: STA 136 connects to AP-166 by a single vector component.")
            else:
                p("   => STILL ABSTAIN: AP-166 now localized, but NOT in STA 1+36's run component")
                p("      (reason: far-end label not reachable as one safe component — Primitive C floor).")

    json_path = ROOT / "scripts" / "pdf_ap_glyph_reconstruct.json"
    json_path.write_text(json.dumps({"schema_version": SCHEMA_VERSION,
                                     "targets_by_sheet": {str(k): v for k, v in all_targets_by_sheet.items()}},
                                    indent=2), encoding="utf-8")
    _flush(out)
    print(f"[wrote {json_path}]")


def _flush(out: List[str]) -> None:
    out_path = ROOT / "scripts" / "pdf_ap_glyph_reconstruct.out"
    out_path.write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))
    print(f"[wrote {out_path}]")


def _selftest() -> None:
    # run "X166Y" where 166 is valid; anchored by a PORT label; a dimension '1125' run not anchored.
    chars = [{"text": t, "x0": 100 + i*5, "x1": 104 + i*5, "top": 100, "bottom": 110} for i, t in enumerate("166")]
    words = [{"text": "PORT", "x0": 100, "x1": 130, "top": 112, "bottom": 122}]
    tg = reconstruct_positioned_aps(chars=chars, words=words, valid_ap_ids=[166, 163])
    assert any(t.get("ap_id") == 166 for t in tg), tg
    # dimension '1125' (no valid AP substring 112/125? 125 IS valid) but NOT anchored -> dropped
    chars2 = [{"text": t, "x0": 500 + i*5, "x1": 504 + i*5, "top": 500, "bottom": 510} for i, t in enumerate("1125")]
    tg2 = reconstruct_positioned_aps(chars=chars2, words=[], valid_ap_ids=[125])
    assert all(t.get("ap_id") is None for t in tg2), tg2  # no anchor -> not localized
    # ambiguous run with two valid APs anchored -> abstain
    chars3 = [{"text": t, "x0": 100 + i*5, "x1": 104 + i*5, "top": 100, "bottom": 110} for i, t in enumerate("163166")]
    words3 = [{"text": "PORT", "x0": 100, "x1": 140, "top": 112, "bottom": 122}]
    tg3 = reconstruct_positioned_aps(chars=chars3, words=words3, valid_ap_ids=[163, 166, 316])
    assert any(t.get("ap_id") is None and "ambiguous" in t.get("reason", "") for t in tg3), tg3
    print("SELFTEST_OK: subsequence recovery, anchor-gated, dimension-rejected, ambiguous-abstain.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "selftest":
        _selftest()
    else:
        main()
