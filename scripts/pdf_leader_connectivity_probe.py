"""Target #28 — vector-connectivity feasibility probe (READ-ONLY).

Tests whether the plan-sheet VECTOR layer (page.lines + page.curves) can be SAFELY followed
to connect a STA callout to its end-structure label — BEFORE building Primitive B on top of
it. The Target #28 rule: if the geometry cannot be followed without guessing, abstain.

Method: build an undirected graph of all line/curve sub-segment endpoints (snapped to a grid),
union-find into connected components, then for a (callout-region, structure-region) pair ask:
do they touch the SAME vector component, and is the component a plausible leader/run (not the
whole hatch blob)? Run on a KNOWN-GOOD pair (sheet10 451->AP-163) and the MISS (sheet10
136->AP-166), plus the EXTRA (sheet8 308->AP-110).

NO placement, NO engine/STATE change, NO flag. Writes scripts/pdf_leader_connectivity_probe.out.
"""
from __future__ import annotations

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
PLAN_PDF = Path(r"C:/Nova/knowledge/TrueLine-Wiki/raw/trueline/engineering-plans/brenham/Brenham - Phase 5_07-15-25.pdf")
PAGE_OFFSET = 13
SNAP = 2.0  # px grid for endpoint snapping

OUT: List[str] = []
def p(s: str = "") -> None:
    OUT.append(s)


def _c(o: Dict[str, Any]) -> Tuple[float, float]:
    return ((o["x0"] + o["x1"]) / 2.0, (o["top"] + o["bottom"]) / 2.0)


class UF:
    def __init__(self): self.par: Dict[Any, Any] = {}
    def find(self, x):
        self.par.setdefault(x, x)
        while self.par[x] != x:
            self.par[x] = self.par[self.par[x]]; x = self.par[x]
        return x
    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb: self.par[ra] = rb


def _snap(x: float, y: float) -> Tuple[int, int]:
    return (int(round(x / SNAP)), int(round(y / SNAP)))


def build_components(page) -> Tuple[UF, Dict[Tuple[int, int], int]]:
    uf = UF()
    deg: Dict[Tuple[int, int], int] = {}
    def add_edge(p1, p2):
        a, b = _snap(*p1), _snap(*p2)
        uf.union(a, b)
        deg[a] = deg.get(a, 0) + 1; deg[b] = deg.get(b, 0) + 1
    for ln in page.lines:
        add_edge((ln["x0"], ln["top"]), (ln["x1"], ln["bottom"]))
    for cv in page.curves:
        pts = cv.get("pts") or []
        for i in range(len(pts) - 1):
            add_edge((pts[i][0], pts[i][1]), (pts[i + 1][0], pts[i + 1][1]))
    return uf, deg


def comp_size(uf: UF) -> Dict[Any, int]:
    sz: Dict[Any, int] = {}
    for n in list(uf.par):
        r = uf.find(n); sz[r] = sz.get(r, 0) + 1
    return sz


def nodes_near(deg: Dict[Tuple[int, int], int], cx: float, cy: float, r: float) -> List[Tuple[int, int]]:
    out = []
    for node in deg:
        nx, ny = node[0] * SNAP, node[1] * SNAP
        if math.hypot(nx - cx, ny - cy) <= r:
            out.append(node)
    return out


def test_pair(uf, deg, sz, callout, struct, r=20.0):
    cnodes = nodes_near(deg, callout[0], callout[1], r)
    snodes = nodes_near(deg, struct[0], struct[1], r)
    if not cnodes or not snodes:
        return {"connected": False, "reason": "no vector nodes near callout or structure",
                "c_nodes": len(cnodes), "s_nodes": len(snodes)}
    croots = {uf.find(n) for n in cnodes}
    sroots = {uf.find(n) for n in snodes}
    shared = croots & sroots
    if not shared:
        return {"connected": False, "reason": "callout and structure in different vector components",
                "c_nodes": len(cnodes), "s_nodes": len(snodes),
                "c_comp_sizes": sorted({sz[r_] for r_ in croots}, reverse=True)[:3],
                "s_comp_sizes": sorted({sz[r_] for r_ in sroots}, reverse=True)[:3]}
    comp_sizes = sorted({sz[r_] for r_ in shared}, reverse=True)
    # A shared HUGE component = hatch blob (not a specific leader) -> unsafe to call a connection
    safe = max(comp_sizes) <= 400
    return {"connected": True, "reason": "shared vector component" if safe else
            "shared component is a large hatch blob (>400 nodes) — NOT a specific leader",
            "shared_comp_sizes": comp_sizes[:3], "safe_specific_leader": safe}


def main() -> None:
    p("=" * 80)
    p("Target #28 — vector-connectivity feasibility probe")
    p("=" * 80)
    if not PLAN_PDF.exists():
        p("!! plan PDF missing"); _flush(); return
    import pdfplumber

    # (sheet, callout_text, ap, structure_label_text) — structure label position resolved at runtime
    cases = [
        (10, "4+51", 163, ("TERMINAL", "PORT")),   # KNOWN GOOD (Primitive A passes)
        (10, "1+36", 166, ("TERMINAL", "PORT")),   # MISS to recover
        (8,  "3+08", 110, ("PORT",)),              # EXTRA to classify
    ]
    with pdfplumber.open(str(PLAN_PDF)) as pdf:
        for sheet, sta, ap, struct_kw in cases:
            page = pdf.pages[sheet + PAGE_OFFSET - 1]
            uf, deg = build_components(page)
            sz = comp_size(uf)
            big = sorted(sz.values(), reverse=True)[:5]
            ws = [dict(w) for w in page.extract_words(use_text_flow=True, keep_blank_chars=False)]
            cal = [w for w in ws if w["text"] == sta]
            structs = [w for w in ws if str(w.get("text", "")).upper() in struct_kw]
            p(f"\n[sheet {sheet}] '{sta}'->AP-{ap}; vector nodes={len(deg)} components_top5_sizes={big}")
            if not cal:
                p("   no callout found"); continue
            c_xy = _c(cal[0])
            # nearest structure label to the callout
            if not structs:
                p("   no structure label found"); continue
            st = min(structs, key=lambda s: math.hypot(_c(s)[0]-c_xy[0], _c(s)[1]-c_xy[1]))
            s_xy = _c(st)
            res = test_pair(uf, deg, sz, c_xy, s_xy)
            p(f"   callout@({c_xy[0]:.0f},{c_xy[1]:.0f})  struct '{st['text']}'@({s_xy[0]:.0f},{s_xy[1]:.0f})  "
              f"straight={math.hypot(s_xy[0]-c_xy[0],s_xy[1]-c_xy[1]):.0f}px")
            p(f"   -> {res}")

    p("\n[FEASIBILITY VERDICT]")
    p("  If the KNOWN-GOOD pair (451->163) does NOT yield a small isolable shared component, the")
    p("  vector layer is hatch/glyph soup and CANNOT be followed safely -> Primitive B must abstain")
    p("  and Primitive A (nearest-label, validated) remains the method. If it DOES, connectivity is")
    p("  usable and Primitive B can disambiguate by connection.")
    _flush()


def _flush() -> None:
    out_path = ROOT / "scripts" / "pdf_leader_connectivity_probe.out"
    out_path.write_text("\n".join(OUT) + "\n", encoding="utf-8")
    print("\n".join(OUT))
    print(f"\n[wrote {out_path}]")


if __name__ == "__main__":
    main()
