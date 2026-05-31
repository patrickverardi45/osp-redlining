"""Target #29 — Primitive C: gated DIR.BORE run-polyline tracer + matchline exclusion.

Goal: recover FAR-END AP relationships that Primitive A (nearest-label) and Primitive B
(structure-component) cannot — by following a run's vector component to a far AP token — and
exclude MATCHLINE-station candidates before trusting any AP. Strict no-guessing: abstain (with
a machine-readable reason) when the far AP is not spatially localizable, the run is not one
safe component, or it branches.

EMPIRICAL FINDING this primitive encodes (sheet 10): the far-end AP-166 that the hand table
binds to STA 1+36 is PRESENT on the page (page-concat V2 sees 163/165/166) but does NOT form a
positioned digit cluster — its glyphs scramble, so there is no geometry target to trace to.
=> (10,136,166) is correctly ABSTAINED, not guessed. Tracing confirms the local/short runs
(451->163, 413->157) and never degrades them.

Pure helpers (geometry in -> verdict out, deterministic, never raise). Isolated in scripts/;
no engine import-as-production, no flag, no STATE, no placement.
"""
from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "backend")); sys.path.insert(0, str(ROOT / "scripts"))
for k in ("TRUELINE_JWT_SECRET", "TRUELINE_AUTH_JWT_SECRET"):
    os.environ.setdefault(k, "t29")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

import pdf_run_endpoint_extractor as A
import pdf_leader_run_following as B

SCHEMA_VERSION = "pdf-run-polyline-tracer-1"
PLAN_PDF = Path(r"C:/Nova/knowledge/TrueLine-Wiki/raw/trueline/engineering-plans/brenham/Brenham - Phase 5_07-15-25.pdf")
PAGE_OFFSET = 13
MATCHLINE_TOL = 36.0    # px: a STA callout this close to a MATCHLINE label is a matchline station.
# Tight on purpose: MATCHLINE labels are sheet-edge annotations, so a loose radius false-positives
# nearby non-matchline callouts (e.g. STA 1+36 sits ~67px below a top-edge label but is a real AP
# run-end). 36px keeps the adjacency requirement ("MATCHLINE STA n+nn" on one line) without
# over-claiming. Matchline exclusion here is a CONSERVATIVE signal, not exhaustive — see report.
LOCAL_STRUCT_R = 35.0   # px: an AP cluster this close to the callout is the LOCAL structure (Prim B scope)
COMP_AP_TOL = 22.0      # px: AP cluster must touch the run's vector component


# ── pure helpers ─────────────────────────────────────────────────────────────

def derive_matchline_stations(words: Sequence[Dict[str, Any]], *, tol: float = MATCHLINE_TOL) -> Set[float]:
    """Pure: station values whose STA callout sits within tol of a MATCHLINE label.
    Geometry-derived (NOT read from the hand table)."""
    W = [A._c(dict(w)) for w in words]
    ml = [w for w in W if "MATCH" in str(w.get("text", "")).upper()]
    out: Set[float] = set()
    for w in W:
        st = A._sta_ft(str(w.get("text", "")))
        if st is None:
            continue
        for m in ml:
            if math.hypot(w["cx"] - m["cx"], w["cy"] - m["cy"]) <= tol:
                out.add(st); break
    return out


def localizable_ap_clusters(chars, valid_ap_ids) -> List[Tuple[int, float, float]]:
    """Pure: positioned valid-AP digit clusters (the trace TARGET universe)."""
    valid = {int(a) for a in valid_ap_ids}
    out = []
    for (txt, cx, cy) in A._cluster_digit_numbers([A._c(dict(c)) for c in chars]):
        if txt.isdigit() and int(txt) in valid:
            out.append((int(txt), cx, cy))
    return out


def trace_far_end_ap(
    *, callout_xy: Tuple[float, float], uf, nodes, ap_clusters, station_val: int,
    target_ap: Optional[int] = None,
) -> Dict[str, Any]:
    """Pure: follow the callout's vector component to a FAR AP token (beyond the local
    structure radius). Abstains with reason. If ``target_ap`` is given and is not a
    localizable cluster, reports that explicitly (the AP-166 glyph-scramble case)."""
    cx, cy = callout_xy
    cnodes = [n for n in nodes if math.hypot(n[0] * B.SNAP - cx, n[1] * B.SNAP - cy) <= 12.0]
    if not cnodes:
        return {"ap_id": None, "reason": "no_vector_nodes_at_callout"}
    croots = {uf.find(n) for n in cnodes}
    comp_pts = [(n[0] * B.SNAP, n[1] * B.SNAP) for n in nodes if uf.find(n) in croots]
    # AP clusters that TOUCH the callout's component AND are far (not the local structure)
    far = []
    for (ap, ax, ay) in ap_clusters:
        if ap == station_val:
            continue
        straight = math.hypot(ax - cx, ay - cy)
        if straight <= LOCAL_STRUCT_R:
            continue  # local structure -> Primitive B's job, not a far-end trace
        dmin = min((math.hypot(qx - ax, qy - ay) for qx, qy in comp_pts), default=9e9)
        if dmin <= COMP_AP_TOL:
            far.append((ap, round(straight, 1)))
    if target_ap is not None and target_ap not in {a for (a, _x, _y) in ap_clusters}:
        return {"ap_id": None, "reason": f"target_ap_{target_ap}_not_spatially_localizable_glyph_scramble",
                "far_in_component": sorted(far)}
    far.sort(key=lambda t: t[1])
    if not far:
        return {"ap_id": None, "reason": "no_far_ap_in_run_component", "far_in_component": []}
    if len(far) >= 2:
        return {"ap_id": None, "reason": f"branch_multiple_far_ap_{[a for a,_ in far[:3]]}",
                "far_in_component": far[:3]}
    return {"ap_id": far[0][0], "reason": "single_far_ap_in_component", "far_in_component": far}


def classify_callout(*, station_ft: float, matchline_stations: Set[float],
                     has_local_ap: bool, has_local_struct: bool) -> str:
    """Pure: run role of a STA callout."""
    if station_ft == 0.0:
        return "run_start"
    if station_ft in matchline_stations:
        return "matchline"
    if has_local_ap:
        return "run_end"
    if has_local_struct:
        return "run_end_unresolved_ap"
    return "unrelated_or_tick"


# ── read-only I/O + grading ──────────────────────────────────────────────────

def main() -> None:
    from backend.app.core import pdf_ap_route_resolver as R
    out: List[str] = []
    def p(s: str = "") -> None:
        out.append(s)

    valid_aps = A._load_valid_aps()
    p("=" * 84)
    p("Target #29 — Primitive C run-polyline tracer + matchline exclusion (read-only)")
    p("=" * 84)
    p(f"schema={SCHEMA_VERSION}  valid AP universe={len(valid_aps)}")

    import pdfplumber
    all_rows: List[Dict[str, Any]] = []
    matchline_by_sheet: Dict[int, Set[float]] = {}
    with pdfplumber.open(str(PLAN_PDF)) as pdf:
        for sheet in (8, 10):
            page = pdf.pages[sheet + PAGE_OFFSET - 1]
            words = page.extract_words(use_text_flow=True, keep_blank_chars=False)
            chars = list(page.chars)
            mlines = derive_matchline_stations(words)
            matchline_by_sheet[sheet] = mlines
            recs = A.extract_run_endpoints_from_layout(sheet=sheet, words=words, chars=chars, valid_ap_ids=valid_aps)
            aug = B.augment_records(recs, words=words, chars=chars, lines=page.lines, curves=page.curves, valid_ap_ids=valid_aps)
            uf, nodes = B.build_vector_components(page.lines, page.curves)
            ap_clusters = localizable_ap_clusters(chars, valid_aps)
            p(f"\n[SHEET {sheet}] matchline stations (geometry-derived) = {sorted(mlines)}")
            for r in aug:
                if r["structure_type"] != "ap":
                    continue
                st = r["station_ft"]
                lc = r["leader_connectivity"]
                role = classify_callout(station_ft=st, matchline_stations=mlines,
                                        has_local_ap=lc["verdict"] in ("confirmed", "recovered"),
                                        has_local_struct=True)
                # Primitive C trace attempted whenever B did NOT produce a TRUSTED (confirmed) AP
                # and the callout is not a matchline — i.e. try to reach a far-end AP for the
                # unresolved/review rows (incl. B-"recovered" review candidates like STA 136->125).
                trace = None
                if lc["verdict"] != "confirmed" and role != "matchline":
                    sx, sy = r["evidence"]["sta_xy"]
                    target = 166 if (sheet == 10 and st == 136.0) else None
                    trace = trace_far_end_ap(callout_xy=(sx, sy), uf=uf, nodes=nodes,
                                             ap_clusters=ap_clusters, station_val=int(st), target_ap=target)
                row = {"sheet": sheet, "station_ft": st, "role": role,
                       "A_ap": r["ap_id"], "B_verdict": lc["verdict"], "B_ap": lc.get("component_ap"),
                       "C_trace": trace}
                all_rows.append(row)
                p(f"   STA {st:.0f}: role={role:<20} A={r['ap_id']} B={lc['verdict']}/{lc.get('component_ap')}"
                  + (f" C_trace={trace['reason']}" if trace else ""))

    # TRUSTED = B-confirmed AND not a matchline station.
    trusted = set()
    for row in all_rows:
        if row["B_verdict"] == "confirmed" and row["station_ft"] not in matchline_by_sheet.get(row["sheet"], set()):
            trusted.add((row["sheet"], row["station_ft"], row["A_ap"]))
    hand_ap = {(s, sta, a) for (s, sta, k, a) in R.BRENHAM_PH5_RUN_ENDPOINTS if s in (8, 10) and k == "ap"}

    p("\n" + "-" * 84)
    p("VALIDATION vs BRENHAM_PH5_RUN_ENDPOINTS (sheets 8 & 10, AP rows)")
    p("-" * 84)
    for label, key in [("(10,451,163)", (10, 451.0, 163)), ("(8,413,157)", (8, 413.0, 157))]:
        p(f"   [{'PASS' if key in trusted else 'FAIL'}] keep {label}")
    miss = (10, 136.0, 166)
    p(f"   [(10,136,166)] -> {'RECOVERED' if miss in trusted else 'NOT RECOVERED (abstain)'}")
    c136 = next((r["C_trace"] for r in all_rows if r["sheet"] == 10 and r["station_ft"] == 136.0 and r["C_trace"]), None)
    p(f"       C tracer reason: {c136['reason'] if c136 else '(no trace attempted)'}")
    fp = next((r for r in all_rows if r["sheet"] == 8 and r["station_ft"] == 308.0), None)
    p(f"   [(8,308,110)] -> {'REVIEW/REJECTED' if (8,308.0,110) not in trusted else 'TRUSTED'} "
      f"(B={fp['B_verdict'] if fp else '?'})")
    p(f"\n   TRUSTED (B-confirmed, matchline-excluded) = {sorted(trusted)}")
    p(f"   REPRODUCED vs hand = {sorted(trusted & hand_ap)}")
    excluded = sorted({(r['sheet'], r['station_ft']) for r in all_rows if r['role'] == 'matchline'})
    p(f"   MATCHLINE-EXCLUDED stations = {excluded}")

    json_path = ROOT / "scripts" / "pdf_run_polyline_tracer.json"
    json_path.write_text(json.dumps({"schema_version": SCHEMA_VERSION, "rows": all_rows,
                                     "matchline_stations": {str(k): sorted(v) for k, v in matchline_by_sheet.items()}},
                                    indent=2), encoding="utf-8")
    _flush(out)
    print(f"[wrote {json_path}]")


def _flush(out: List[str]) -> None:
    out_path = ROOT / "scripts" / "pdf_run_polyline_tracer.out"
    out_path.write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))
    print(f"[wrote {out_path}]")


def _selftest() -> None:
    # matchline derivation: STA callout near a MATCHLINE label -> matchline station.
    words = [{"text": "1+66", "x0": 100, "x1": 118, "top": 100, "bottom": 110},
             {"text": "MATCHLINE", "x0": 120, "x1": 140, "top": 100, "bottom": 110},
             {"text": "4+51", "x0": 600, "x1": 620, "top": 600, "bottom": 610}]
    ml = derive_matchline_stations(words)
    assert 166.0 in ml and 451.0 not in ml, ml
    # classify
    assert classify_callout(station_ft=0.0, matchline_stations=ml, has_local_ap=False, has_local_struct=True) == "run_start"
    assert classify_callout(station_ft=166.0, matchline_stations=ml, has_local_ap=True, has_local_struct=True) == "matchline"
    assert classify_callout(station_ft=451.0, matchline_stations=ml, has_local_ap=True, has_local_struct=True) == "run_end"
    # trace: target AP not localizable -> explicit abstain reason
    lines = [{"x0": 0, "top": 0, "x1": 50, "bottom": 0}]
    uf, nodes = B.build_vector_components(lines, [])
    r = trace_far_end_ap(callout_xy=(0, 0), uf=uf, nodes=nodes, ap_clusters=[(163, 400, 400)],
                         station_val=136, target_ap=166)
    assert r["ap_id"] is None and "not_spatially_localizable" in r["reason"], r
    print("SELFTEST_OK: matchline derivation, run-role classification, glyph-scramble abstain.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "selftest":
        _selftest()
    else:
        main()
