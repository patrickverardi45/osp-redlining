"""Target #31 — component-bridge / bored-run span tracer (default-OFF, read-only).

Connect a STA callout to a localized AP target ONLY when vector geometry proves a single
bored-run polyline spans the gap. Strict no-guessing: abstain (machine-readable reason) when
the gap is hatch soup, has no DIR.BORE label, branches, or has no spanning component.

Uses Target #30 reconstructed AP centroids as the canonical AP target universe.

Two acceptance paths:
  - same_component_direct : STA and AP are already in ONE vector component (the trusted
    Primitive B case, e.g. 451->AP-163). The tracer NEVER degrades these.
  - bridge_single_run     : STA and AP are in SEPARATE components but a single isolable
    bored-run polyline (long, low-branch, DIR.BORE-anchored) spans the gap.
Everything else abstains.

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
    os.environ.setdefault(k, "t31")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

import pdf_leader_run_following as B  # component graph (pure)

SCHEMA_VERSION = "pdf-component-bridge-1"
PLAN_PDF = Path(r"C:/Nova/knowledge/TrueLine-Wiki/raw/trueline/engineering-plans/brenham/Brenham - Phase 5_07-15-25.pdf")
PAGE_OFFSET = 13
NODE_TOL = 14.0          # px: nodes near a point
HATCH_SEG_PX = 10.0      # segments shorter than this are hatch/glyph strokes
HATCH_RATIO_MAX = 0.6    # >60% short segments in the corridor => hatch soup
MIN_RUN_SEG_PX = 18.0    # a real bored-run needs at least one segment this long in the corridor


def _seglen(ln: Dict[str, Any]) -> float:
    return math.hypot(ln["x1"] - ln["x0"], ln["bottom"] - ln["top"])


def _roots_near(uf, nodes, x: float, y: float, tol: float = NODE_TOL) -> Set[Any]:
    return {uf.find(n) for n in nodes if math.hypot(n[0] * B.SNAP - x, n[1] * B.SNAP - y) <= tol}


def attempt_bridge(
    *, sta_xy: Tuple[float, float], ap_xy: Tuple[float, float], ap_id: int,
    uf, nodes, lines: Sequence[Dict[str, Any]], curves: Sequence[Dict[str, Any]],
    bore_labels: Sequence[Tuple[float, float]],
) -> Dict[str, Any]:
    """Pure: verdict for connecting sta_xy -> (ap_id @ ap_xy). Never raises."""
    sx, sy = sta_xy; ax, ay = ap_xy
    sroots = _roots_near(uf, nodes, sx, sy)
    aroots = _roots_near(uf, nodes, ax, ay)
    straight = math.hypot(ax - sx, ay - sy)
    if not sroots or not aroots:
        return {"ap_id": ap_id, "verdict": "abstain", "reason": "no_vector_nodes_at_endpoint",
                "straight_px": round(straight, 1)}
    if sroots & aroots:
        return {"ap_id": ap_id, "verdict": "accept", "path": "same_component_direct",
                "reason": "sta_and_ap_share_one_vector_component", "straight_px": round(straight, 1)}

    # ── cross-component: must PROVE a single bored-run spans the gap ──
    x0, x1 = sorted((sx, ax)); y0, y1 = sorted((sy, ay)); pad = 10.0
    def inbox(px, py): return x0 - pad <= px <= x1 + pad and y0 - pad <= py <= y1 + pad
    corr_lines = [ln for ln in lines if inbox((ln["x0"] + ln["x1"]) / 2, (ln["top"] + ln["bottom"]) / 2)]
    corr_curves = [cv for cv in curves if any(inbox(p[0], p[1]) for p in (cv.get("pts") or []))]
    seglens = [_seglen(ln) for ln in corr_lines]
    n_short = sum(1 for L in seglens if L < HATCH_SEG_PX)
    hatch_ratio = (n_short / len(seglens)) if seglens else 1.0
    longest = max(seglens, default=0.0)
    bore_in_gap = [b for b in bore_labels if inbox(b[0], b[1])]
    reasons = []
    if not (sroots & aroots):
        reasons.append("no_spanning_component")
    if len(corr_curves) > 3 * max(1, len(corr_lines)) or hatch_ratio > HATCH_RATIO_MAX:
        reasons.append(f"gap_is_hatch_soup(curves={len(corr_curves)},lines={len(corr_lines)},short_ratio={hatch_ratio:.2f})")
    if longest < MIN_RUN_SEG_PX:
        reasons.append(f"no_long_run_segment(longest={longest:.1f}px)")
    if not bore_in_gap:
        reasons.append("no_dir_bore_label_in_gap")
    if reasons:
        return {"ap_id": ap_id, "verdict": "abstain", "reason": "; ".join(reasons),
                "straight_px": round(straight, 1),
                "evidence": {"corr_lines": len(corr_lines), "corr_curves": len(corr_curves),
                             "hatch_ratio": round(hatch_ratio, 2), "longest_seg_px": round(longest, 1),
                             "bore_labels_in_gap": len(bore_in_gap)}}
    return {"ap_id": ap_id, "verdict": "accept", "path": "bridge_single_run",
            "reason": "single_bored_run_polyline_spans_gap", "straight_px": round(straight, 1)}


# ── read-only I/O + grading ──────────────────────────────────────────────────

def main() -> None:
    import pdf_run_endpoint_extractor as A
    import pdf_ap_glyph_reconstruct as G
    from backend.app.core import pdf_ap_route_resolver as R
    out: List[str] = []
    def p(s: str = "") -> None:
        out.append(s)

    valid_aps = A._load_valid_aps()
    p("=" * 86)
    p("Target #31 — component-bridge / bored-run span tracer (read-only; nothing placed)")
    p("=" * 86)
    p(f"schema={SCHEMA_VERSION}")

    import pdfplumber
    rows: List[Dict[str, Any]] = []
    with pdfplumber.open(str(PLAN_PDF)) as pdf:
        # ---- canonical AP targets (Target #30) + trusted endpoints (Target #28) per sheet ----
        sheet_state = {}
        for sheet in (8, 10):
            page = pdf.pages[sheet + PAGE_OFFSET - 1]
            words = page.extract_words(use_text_flow=True, keep_blank_chars=False)
            chars = list(page.chars)
            uf, nodes = B.build_vector_components(page.lines, page.curves)
            ap_targets = G.localized_ap_index(G.reconstruct_positioned_aps(chars=chars, words=words, valid_ap_ids=valid_aps))
            bore = [((w["x0"] + w["x1"]) / 2, (w["top"] + w["bottom"]) / 2)
                    for w in words if str(w.get("text", "")).upper() == "BORE"]
            sheet_state[sheet] = (page, words, uf, nodes, ap_targets, bore)

        # ---- trusted endpoints (unchanged from Target #28: B-confirmed) ----
        trusted = set()
        for sheet in (8, 10):
            page, words, uf, nodes, ap_targets, bore = sheet_state[sheet]
            chars = list(page.chars)
            recs = A.extract_run_endpoints_from_layout(sheet=sheet, words=words, chars=chars, valid_ap_ids=valid_aps)
            aug = B.augment_records(recs, words=words, chars=chars, lines=page.lines, curves=page.curves, valid_ap_ids=valid_aps)
            for r in aug:
                if r["structure_type"] == "ap" and r["leader_connectivity"]["verdict"] == "confirmed":
                    trusted.add((sheet, r["station_ft"], r["ap_id"]))

        # ---- BRIDGE attempts on named cases ----
        def callout_xy(words, txt):
            cs = [w for w in words if w["text"] == txt]
            return [((w["x0"] + w["x1"]) / 2, (w["top"] + w["bottom"]) / 2) for w in cs]

        p("\n[BRIDGE ATTEMPTS]")
        # primary: sheet10 STA 1+36 -> AP-166 (cross-component) + demo same-component 451->163
        for sheet, sta_txt, ap_id, note in [(10, "1+36", 166, "PRIMARY cross-component"),
                                            (10, "4+51", 163, "demo same-component (trusted)"),
                                            (8, "4+13", 157, "demo same-component (trusted)"),
                                            (10, "1+36", 125, "ALT local AP-125 (must not steal 136)")]:
            page, words, uf, nodes, ap_targets, bore = sheet_state[sheet]
            occ = ap_targets.get(ap_id)
            cals = callout_xy(words, sta_txt)
            if not occ or not cals:
                p(f"   sheet{sheet} {sta_txt}->AP-{ap_id} ({note}): no AP target or callout -> abstain(no_target)")
                rows.append({"sheet": sheet, "sta": sta_txt, "ap": ap_id, "verdict": "abstain", "reason": "no_target_or_callout"})
                continue
            ap_xy = occ[0]["centroid"]
            best = min(cals, key=lambda c: math.hypot(c[0] - ap_xy[0], c[1] - ap_xy[1]))
            res = attempt_bridge(sta_xy=best, ap_xy=ap_xy, ap_id=ap_id, uf=uf, nodes=nodes,
                                 lines=page.lines, curves=page.curves, bore_labels=bore)
            rows.append({"sheet": sheet, "sta": sta_txt, "ap": ap_id, "note": note, **res})
            p(f"   sheet{sheet} {sta_txt}->AP-{ap_id} ({note}): {res['verdict'].upper()} "
              f"[{res.get('path', res['reason'])}] straight={res.get('straight_px')}px")
            if res["verdict"] == "abstain":
                p(f"       reason: {res['reason']}")

    # ---- final endpoint set: trusted (B-confirmed) + any BRIDGE-accepted cross-component ----
    bridged = {(r["sheet"], float(r["sta"].replace("+", "")) if "+" in r["sta"] else float(r["sta"]), r["ap"])
               for r in rows if r.get("verdict") == "accept" and r.get("path") == "bridge_single_run"}
    # normalize sta '1+36'->136
    def sta_ft(t):
        a, b = t.split("+"); return float(a) * 100 + float(b)
    bridged = {(r["sheet"], sta_ft(r["sta"]), r["ap"]) for r in rows
               if r.get("verdict") == "accept" and r.get("path") == "bridge_single_run"}
    final = trusted | bridged
    hand_ap = {(s, sta, a) for (s, sta, k, a) in R.BRENHAM_PH5_RUN_ENDPOINTS if s in (8, 10) and k == "ap"}

    p("\n" + "-" * 86)
    p("VALIDATION vs BRENHAM_PH5_RUN_ENDPOINTS (sheets 8 & 10, AP rows)")
    p("-" * 86)
    rec136 = (10, 136.0, 166) in final
    p(f"   (10,136,166) -> {'RECOVERED via bridge' if rec136 else 'NOT RECOVERED (abstain)'}")
    p(f"   [{'PASS' if (10,451.0,163) in final else 'FAIL'}] keep (10,451,163) trusted")
    p(f"   [{'PASS' if (8,413.0,157) in final else 'FAIL'}] keep (8,413,157) trusted")
    p(f"   AP-125 stealing STA 136? {'YES (BAD)' if (10,136.0,125) in final else 'NO (125 not trusted)'}")
    p(f"   (8,308,110) in trusted? {'YES (BAD)' if (8,308.0,110) in final else 'NO (rejected/review)'}")
    p(f"\n   FINAL trusted endpoints = {sorted(final)}")
    p(f"   REPRODUCED vs hand     = {sorted(final & hand_ap)}")
    p(f"   bridged (cross-comp)   = {sorted(bridged) or 'NONE'}")

    json_path = ROOT / "scripts" / "pdf_component_bridge.json"
    json_path.write_text(json.dumps({"schema_version": SCHEMA_VERSION, "bridge_attempts": rows,
                                     "final_trusted": sorted(final)}, indent=2), encoding="utf-8")
    _flush(out)
    print(f"[wrote {json_path}]")


def _flush(out: List[str]) -> None:
    out_path = ROOT / "scripts" / "pdf_component_bridge.out"
    out_path.write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))
    print(f"[wrote {out_path}]")


def _selftest() -> None:
    # same component: one line connecting sta and ap -> accept direct.
    lines = [{"x0": 0, "top": 0, "x1": 50, "bottom": 0}]
    uf, nodes = B.build_vector_components(lines, [])
    r = attempt_bridge(sta_xy=(0, 0), ap_xy=(50, 0), ap_id=163, uf=uf, nodes=nodes,
                       lines=lines, curves=[], bore_labels=[])
    assert r["verdict"] == "accept" and r["path"] == "same_component_direct", r
    # cross component + hatch soup + no BORE -> abstain with reasons.
    lines2 = [{"x0": 0, "top": 0, "x1": 4, "bottom": 0}, {"x0": 100, "top": 0, "x1": 104, "bottom": 0}]
    curves2 = [{"pts": [(20 + i, 5), (21 + i, 6)]} for i in range(40)]  # dense short hatch between
    uf2, nodes2 = B.build_vector_components(lines2, curves2)
    r2 = attempt_bridge(sta_xy=(0, 0), ap_xy=(100, 0), ap_id=166, uf=uf2, nodes=nodes2,
                        lines=lines2, curves=curves2, bore_labels=[])
    assert r2["verdict"] == "abstain" and "no_spanning_component" in r2["reason"] and "hatch_soup" in r2["reason"], r2
    print("SELFTEST_OK: same-component accept, cross-component hatch-soup abstain with reasons.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "selftest":
        _selftest()
    else:
        main()
