"""Target #28 — Primitive B: PDF leader-line / run-polyline connectivity (default-OFF, read-only).

Augments Target #27 Primitive A (nearest-label run-endpoints) with VECTOR-GEOMETRY evidence:
build a connected-component graph of page.lines + page.curves endpoints, then for each AP-class
record confirm the AP NUMBER that belongs to the structure label's OWN connected component
(not merely the nearest text). This:
  - geometry-CONFIRMS Primitive A's validated bindings (451->163, 413->157),
  - REJECTS nearest-label false positives whose AP digits are NOT in the structure component
    (e.g. sheet 8 STA 308 -> AP-110),
  - ABSTAINS with a machine-readable geometry reason when the local structure resolves to a
    different AP or none (e.g. sheet 10 STA 136: local structure is AP-125, not the hand
    table's far-end AP-166 — a multi-drive run whose far end is not a single isolable polyline).

NEVER degrades a Primitive A PASS: Primitive B only annotates / downgrades; it does not invent
AP ids. Pure helpers (geometry in -> verdict out, deterministic, never raise). Isolated in
scripts/; no engine import-as-production, no flag, no STATE, no placement.
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
    os.environ.setdefault(k, "t28")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

import pdf_run_endpoint_extractor as A  # Primitive A (pure)

SCHEMA_VERSION = "pdf-leader-run-following-1"
PLAN_PDF = Path(r"C:/Nova/knowledge/TrueLine-Wiki/raw/trueline/engineering-plans/brenham/Brenham - Phase 5_07-15-25.pdf")
PAGE_OFFSET = 13
SNAP = 2.0
NODE_NEAR_TOL = 20.0   # px: nodes near the structure label
COMP_AP_TOL = 22.0     # px: AP digit cluster must touch the structure's component


# ── pure vector-component graph ──────────────────────────────────────────────

class _UF:
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


def build_vector_components(lines: Sequence[Dict[str, Any]], curves: Sequence[Dict[str, Any]]):
    """Pure: UF over line/curve sub-segment endpoints. Returns (uf, node_set)."""
    uf = _UF(); nodes = set()
    def edge(p1, p2):
        a, b = _snap(*p1), _snap(*p2); uf.union(a, b); nodes.add(a); nodes.add(b)
    for ln in lines:
        edge((ln["x0"], ln["top"]), (ln["x1"], ln["bottom"]))
    for cv in curves:
        pts = cv.get("pts") or []
        for i in range(len(pts) - 1):
            edge((pts[i][0], pts[i][1]), (pts[i + 1][0], pts[i + 1][1]))
    return uf, nodes


def _cluster_numbers(chars: Sequence[Dict[str, Any]]) -> List[Tuple[str, float, float]]:
    return A._cluster_digit_numbers([A._c(dict(c)) for c in chars])


def ap_in_structure_component(
    *, struct_xy: Tuple[float, float], uf, nodes, num_clusters,
    valid_ap_ids, station_val: int,
) -> Dict[str, Any]:
    """Pure: the unique valid-AP digit cluster touching the structure label's connected
    component. Abstains (ap=None) on none / tie / different-AP. Never raises."""
    sx, sy = struct_xy
    snodes = [n for n in nodes if math.hypot(n[0] * SNAP - sx, n[1] * SNAP - sy) <= NODE_NEAR_TOL]
    if not snodes:
        return {"ap_id": None, "reason": "no_vector_nodes_near_structure"}
    sroots = {uf.find(n) for n in snodes}
    comp_pts = [(n[0] * SNAP, n[1] * SNAP) for n in nodes if uf.find(n) in sroots]
    cand: List[Tuple[int, float]] = []
    for (txt, cx, cy) in num_clusters:
        if not txt.isdigit():
            continue
        v = int(txt)
        if v in valid_ap_ids and v != station_val:
            dmin = min((math.hypot(qx - cx, qy - cy) for qx, qy in comp_pts), default=9e9)
            if dmin <= COMP_AP_TOL:
                cand.append((v, round(dmin, 1)))
    cand.sort(key=lambda t: t[1])
    if not cand:
        return {"ap_id": None, "reason": "no_valid_ap_in_structure_component", "candidates": []}
    if len(cand) >= 2 and cand[1][1] < 1.4 * cand[0][1]:
        return {"ap_id": None, "reason": f"ambiguous_component_ap_{cand[0][0]}_vs_{cand[1][0]}",
                "candidates": cand[:3]}
    return {"ap_id": cand[0][0], "reason": "unique_in_component", "candidates": cand[:3]}


def augment_records(
    records: Sequence[Dict[str, Any]],
    *, words, chars, lines, curves, valid_ap_ids,
) -> List[Dict[str, Any]]:
    """Pure: add `leader_connectivity` to each Primitive A record. Verdicts:
    confirmed | corrected | unconfirmed_review | abstain_geometry | n/a(non-ap)."""
    valid = {int(a) for a in valid_ap_ids}
    uf, nodes = build_vector_components(lines, curves)
    num_clusters = _cluster_numbers(chars)
    W = [A._c(dict(w)) for w in words]
    out: List[Dict[str, Any]] = []
    for rec in records:
        rec = dict(rec)
        if rec["structure_type"] != "ap":
            rec["leader_connectivity"] = {"verdict": "n/a_non_ap"}
            out.append(rec); continue
        # locate the structure label word nearest the record's sta_xy
        sx, sy = rec["evidence"]["sta_xy"]
        structs = [w for w in W if str(w.get("text", "")).upper() in A.STRUCT_KW
                   and A.STRUCT_KW[str(w["text"]).upper()] == "ap"]
        if not structs:
            rec["leader_connectivity"] = {"verdict": "abstain_geometry", "reason": "no_struct_word"}
            out.append(rec); continue
        st = min(structs, key=lambda w: math.hypot(w["cx"] - sx, w["cy"] - sy))
        comp = ap_in_structure_component(
            struct_xy=(st["cx"], st["cy"]), uf=uf, nodes=nodes, num_clusters=num_clusters,
            valid_ap_ids=valid, station_val=int(rec["station_ft"]))
        cap = comp.get("ap_id")
        a_ap = rec.get("ap_id")
        if cap is not None and a_ap is not None and cap == a_ap:
            verdict = "confirmed"
        elif cap is not None and a_ap is None:
            verdict = "recovered"
        elif cap is not None and a_ap is not None and cap != a_ap:
            verdict = "corrected"
        elif cap is None and a_ap is not None:
            verdict = "unconfirmed_review"   # Primitive A nearest-label not backed by geometry
        else:
            verdict = "abstain_geometry"
        rec["leader_connectivity"] = {"verdict": verdict, "component_ap": cap, **comp}
        out.append(rec)
    return out


# ── read-only I/O + grading ──────────────────────────────────────────────────

def main() -> None:
    from backend.app.core import pdf_ap_route_resolver as R
    out: List[str] = []
    def p(s: str = "") -> None:
        out.append(s)

    valid_aps = A._load_valid_aps()
    p("=" * 82)
    p("Target #28 — Primitive B leader/run connectivity (read-only; nothing placed)")
    p("=" * 82)
    p(f"schema={SCHEMA_VERSION}  valid AP universe={len(valid_aps)}")

    import pdfplumber
    all_aug: List[Dict[str, Any]] = []
    with pdfplumber.open(str(PLAN_PDF)) as pdf:
        for sheet in (8, 10):
            page = pdf.pages[sheet + PAGE_OFFSET - 1]
            words = page.extract_words(use_text_flow=True, keep_blank_chars=False)
            chars = list(page.chars)
            recs = A.extract_run_endpoints_from_layout(
                sheet=sheet, words=words, chars=chars, valid_ap_ids=valid_aps)
            aug = augment_records(recs, words=words, chars=chars,
                                  lines=page.lines, curves=page.curves, valid_ap_ids=valid_aps)
            all_aug.extend(aug)
            ap_recs = [r for r in aug if r["structure_type"] == "ap"]
            p(f"\n[SHEET {sheet}] {len(ap_recs)} AP-class records:")
            for r in ap_recs:
                lc = r["leader_connectivity"]
                p(f"   STA {r['station_ft']:.0f}: A.ap={r['ap_id']} conf={r['confidence']} | "
                  f"B.verdict={lc['verdict']} comp_ap={lc.get('component_ap')} ({lc.get('reason','')})")

    # TRUSTED = Primitive A ap CONFIRMED by Primitive B connectivity (both agree). Conservative.
    trusted = {(r["sheet"], r["station_ft"], r["ap_id"])
               for r in all_aug if r["structure_type"] == "ap"
               and r["leader_connectivity"]["verdict"] == "confirmed"}
    hand_ap = {(s, sta, a) for (s, sta, k, a) in R.BRENHAM_PH5_RUN_ENDPOINTS if s in (8, 10) and k == "ap"}
    reviews = [(r["sheet"], r["station_ft"], r["ap_id"]) for r in all_aug
               if r["structure_type"] == "ap" and r["leader_connectivity"]["verdict"] == "unconfirmed_review"]
    # RECOVERED/CORRECTED = geometry found an AP where A abstained or disagreed -> REVIEW candidates,
    # NOT auto-trusted (e.g. STA 136 geometry->125 conflicts with hand 166).
    candidates = [(r["sheet"], r["station_ft"], r["leader_connectivity"].get("component_ap"),
                   r["leader_connectivity"]["verdict"])
                  for r in all_aug if r["structure_type"] == "ap"
                  and r["leader_connectivity"]["verdict"] in ("recovered", "corrected")]

    p("\n" + "-" * 82)
    p("VALIDATION (Primitive B connectivity-trusted vs hand table, sheets 8&10 AP rows)")
    p("-" * 82)
    gate = [("sheet 10 STA 451 -> AP-163", (10, 451.0, 163)),
            ("sheet 8 STA 413 -> AP-157", (8, 413.0, 157))]
    for label, key in gate:
        p(f"   [{'PASS' if key in trusted else 'FAIL'}] {label}")
    p(f"\n   TRUSTED (A+B agree) = {sorted(trusted)}")
    p(f"   REPRODUCED vs hand  = {sorted(trusted & hand_ap)}")
    p(f"   hand rows NOT trusted (abstained) = {sorted(hand_ap - trusted)}")
    p(f"   FALSE-POSITIVE/REVIEW (A said AP, geometry did NOT confirm) = {reviews}")
    p(f"   GEOMETRY CANDIDATES (B found AP where A abstained/disagreed — REVIEW, not asserted) = {candidates}")

    json_path = ROOT / "scripts" / "pdf_leader_run_following.json"
    json_path.write_text(json.dumps({"schema_version": SCHEMA_VERSION, "records": all_aug}, indent=2), encoding="utf-8")
    _flush(out)
    print(f"[wrote {json_path}]")


def _flush(out: List[str]) -> None:
    out_path = ROOT / "scripts" / "pdf_leader_run_following.out"
    out_path.write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))
    print(f"[wrote {out_path}]")


def _selftest() -> None:
    """Deterministic check of the pure connectivity primitive on synthetic geometry."""
    # A structure label at (100,120). A leader component (line) reaching a '163' cluster at (150,120).
    lines = [{"x0": 100, "top": 120, "x1": 150, "bottom": 120}]
    curves = []
    uf, nodes = build_vector_components(lines, curves)
    # '163' digits centered ~ (150,120) -> in component; '999' far away.
    num = [("163", 150.0, 120.0), ("99", 600.0, 600.0)]
    r = ap_in_structure_component(struct_xy=(100, 120), uf=uf, nodes=nodes, num_clusters=num,
                                  valid_ap_ids={163, 157}, station_val=451)
    assert r["ap_id"] == 163, r
    # determinism
    r2 = ap_in_structure_component(struct_xy=(100, 120), uf=uf, nodes=nodes, num_clusters=num,
                                   valid_ap_ids={163, 157}, station_val=451)
    assert r == r2
    # station-collision excluded: if the only cluster equals the station value -> abstain
    r3 = ap_in_structure_component(struct_xy=(100, 120), uf=uf, nodes=nodes,
                                   num_clusters=[("163", 150.0, 120.0)], valid_ap_ids={163},
                                   station_val=163)
    assert r3["ap_id"] is None, r3
    # no component near structure -> abstain
    r4 = ap_in_structure_component(struct_xy=(900, 900), uf=uf, nodes=nodes, num_clusters=num,
                                   valid_ap_ids={163}, station_val=451)
    assert r4["ap_id"] is None and "no_vector_nodes" in r4["reason"], r4
    print("SELFTEST_OK: component-scoped AP recovery deterministic, station-safe, abstains cleanly.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "selftest":
        _selftest()
    else:
        main()
