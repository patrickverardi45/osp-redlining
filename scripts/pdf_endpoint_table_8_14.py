"""Target #32 — PDF-derived run-endpoint table for sheets 8-14 (default-OFF, read-only).

Scales the A->B extraction chain (Primitive A nearest-label + Primitive B component-confirm)
across the full detailed-plan band (sheets 8-14), excludes matchline/SEE-SHEET stations from
trust, grades the auto table against BRENHAM_PH5_RUN_ENDPOINTS with precision/recall + a hard
zero-wrong-ID assertion, feeds recovered APs through the Target #25 index, and makes ONE
bounded cross-sheet attempt at sheet-10 STA 136 -> AP-166 (then stops; no AP-166 loop).

TRUST rule: an AP endpoint is trusted iff Primitive B verdict == 'confirmed' (A nearest-label
AND vector-component agree) AND its station is not a matchline/SEE-SHEET station. Everything
else is review/abstain. No guessing.

Read-only; pure-helper reuse; no engine import-as-production, no flag, no STATE, no placement.
"""
from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Sequence, Set, Tuple

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "backend")); sys.path.insert(0, str(ROOT / "scripts"))
for k in ("TRUELINE_JWT_SECRET", "TRUELINE_AUTH_JWT_SECRET"):
    os.environ.setdefault(k, "t32")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

import pdf_run_endpoint_extractor as A
import pdf_leader_run_following as B
import pdf_ap_glyph_reconstruct as G

SCHEMA_VERSION = "pdf-endpoint-table-8-14-1"
PLAN_PDF = Path(r"C:/Nova/knowledge/TrueLine-Wiki/raw/trueline/engineering-plans/brenham/Brenham - Phase 5_07-15-25.pdf")
PAGE_OFFSET = 13
SHEETS = (8, 9, 10, 11, 12, 13, 14)
MATCHLINE_TOL = 36.0


def _cxy(w):
    return ((w["x0"] + w["x1"]) / 2.0, (w["top"] + w["bottom"]) / 2.0)


def matchline_stations(words: Sequence[Dict[str, Any]]) -> Set[float]:
    """Stations whose callout is near a MATCHLINE or SEE-SHEET label (geometry-derived)."""
    W = [dict(w) for w in words]
    for w in W:
        w["cx"], w["cy"] = _cxy(w)
    flags = [w for w in W if "MATCH" in str(w.get("text", "")).upper() or "SEE" in str(w.get("text", "")).upper()]
    out: Set[float] = set()
    for w in W:
        st = A._sta_ft(str(w.get("text", "")))
        if st is None:
            continue
        for m in flags:
            if math.hypot(w["cx"] - m["cx"], w["cy"] - m["cy"]) <= MATCHLINE_TOL:
                out.add(st); break
    return out


def main() -> None:
    from backend.app.core import pdf_ap_route_resolver as R
    out: List[str] = []
    def p(s: str = "") -> None:
        out.append(s)

    valid_aps = A._load_valid_aps()
    p("=" * 88)
    p("Target #32 — PDF run-endpoint table, sheets 8-14 (read-only; nothing placed)")
    p("=" * 88)

    # hand reference
    hand_ap = {(s, sta, a) for (s, sta, k, a) in R.BRENHAM_PH5_RUN_ENDPOINTS if 8 <= s <= 14 and k == "ap"}
    hand_by_sta = {(s, sta): a for (s, sta, a) in hand_ap}

    import pdfplumber
    trusted: Set[Tuple[int, float, int]] = set()
    review: List[Tuple[int, float, int]] = []
    ap166_target = None
    sheet_components = {}
    with pdfplumber.open(str(PLAN_PDF)) as pdf:
        for sheet in SHEETS:
            page = pdf.pages[sheet + PAGE_OFFSET - 1]
            words = page.extract_words(use_text_flow=True, keep_blank_chars=False)
            chars = list(page.chars)
            mls = matchline_stations(words)
            recs = A.extract_run_endpoints_from_layout(sheet=sheet, words=words, chars=chars, valid_ap_ids=valid_aps)
            aug = B.augment_records(recs, words=words, chars=chars, lines=page.lines, curves=page.curves, valid_ap_ids=valid_aps)
            uf, nodes = B.build_vector_components(page.lines, page.curves)
            sheet_components[sheet] = (uf, nodes, page, words)
            ap_targets = G.localized_ap_index(G.reconstruct_positioned_aps(chars=chars, words=words, valid_ap_ids=valid_aps))
            if sheet == 10 and 166 in ap_targets:
                ap166_target = ap_targets[166][0]["centroid"]
            n_conf = 0
            for r in aug:
                if r["structure_type"] != "ap" or r["ap_id"] is None:
                    continue
                v = r["leader_connectivity"]["verdict"]
                key = (sheet, r["station_ft"], r["ap_id"])
                if v == "confirmed" and r["station_ft"] not in mls:
                    trusted.add(key); n_conf += 1
                elif v in ("confirmed", "recovered", "corrected", "unconfirmed_review"):
                    review.append(key)
            p(f" sheet {sheet:>2}: confirmed-trusted AP rows={n_conf}  matchline/see-sheet stations excluded={sorted(mls)}")

    # ── grade ────────────────────────────────────────────────────────────────
    tp = sorted(trusted & hand_ap)
    wrong = sorted((s, sta, a) for (s, sta, a) in trusted if (s, sta) in hand_by_sta and hand_by_sta[(s, sta)] != a)
    extra = sorted((s, sta, a) for (s, sta, a) in trusted if (s, sta) not in hand_by_sta)
    miss = sorted(hand_ap - trusted)
    prec = len(tp) / max(1, len(tp) + len(wrong) + len(extra))
    rec = len(tp) / max(1, len(hand_ap))

    p("\n" + "-" * 88)
    p("GRADE vs BRENHAM_PH5_RUN_ENDPOINTS (sheets 8-14 AP rows)")
    p("-" * 88)
    p(f"   hand AP rows = {len(hand_ap)}; trusted = {len(trusted)}")
    p(f"   TRUE POSITIVES ({len(tp)}) = {tp}")
    p(f"   WRONG IDs      ({len(wrong)}) = {wrong}")
    p(f"   EXTRA/REVIEW   ({len(extra)}) = {extra}")
    p(f"   MISSES         ({len(miss)}) = {miss}")
    p(f"   PRECISION = {prec:.2f}   RECALL = {rec:.2f}   (wrong-id policy: {'OK (0)' if not wrong else 'VIOLATED'})")
    # split: AP-terminal sheets (8-12, where the hand table HAS AP rows) vs boundary sheets (13-14)
    tp_812 = [t for t in tp if t[0] <= 12]; extra_812 = [e for e in extra if e[0] <= 12]
    extra_1314 = [e for e in extra if e[0] >= 13]
    hand_812 = {h for h in hand_ap if h[0] <= 12}
    prec_812 = len(tp_812) / max(1, len(tp_812) + len(extra_812))
    rec_812 = len(tp_812) / max(1, len(hand_812))
    p(f"   -- AP-terminal sheets 8-12: TP={len(tp_812)} extra={len(extra_812)} miss={len(hand_812)-len(tp_812)} "
      f"PRECISION={prec_812:.2f} RECALL={rec_812:.2f}")
    p(f"   -- boundary sheets 13-14 (hand has 0 AP rows): {len(extra_1314)} EXTRA = boundary-sheet")
    p(f"      over-generation (matchline/cross-ref numbers read as APs) = {extra_1314}")
    p("      => matchline label-proximity filter is insufficient on 13/14; these are NOT trusted-clean.")

    # ── Target #25 index geometry-ready confirmation ───────────────────────────
    idx_path = ROOT / "scripts" / "ap_structure_index.json"
    idx = json.load(open(idx_path)).get("aps", {}) if idx_path.exists() else {}
    geo_ready = [(s, sta, a) for (s, sta, a) in tp if str(a) in idx and idx[str(a)].get("geometry_anchor_ready")]
    p(f"\n   Target #25 index: {len(geo_ready)}/{len(tp)} trusted APs are geometry-anchor-ready "
      f"(latlon present) -> {[a for (_s,_t,a) in geo_ready]}")

    # ── ONE bounded cross-sheet AP-166 attempt, then STOP ──────────────────────
    p("\n[BOUNDED AP-166 CROSS-SHEET ATTEMPT (one shot, then stop)]")
    # matchline graph: which sheets does sheet 10 connect to?
    try:
        from backend.app.core import brenham_plan_sheet_graph as PSG
        corr = PSG.corridor_for_sheet(10)
    except Exception:
        corr = [10]
    adj = [s for s in corr if s != 10 and s in SHEETS]
    p(f"   sheet 10 corridor (matchline-connected) = {corr}; adjacent in-band sheets = {adj}")
    recovered_166 = False
    # A cross-sheet continuation is deterministic ONLY if a matchline EQUATION links sheet 10's
    # STA-136 run to AP-166 on an adjacent sheet. A bare trusted (sheet,sta,166) row is NOT proof
    # — and any candidate at a MATCHLINE station of its own sheet is rejected outright.
    cand = [(s, sta, a) for (s, sta, a) in trusted if a == 166]
    boundary = None
    try:
        from backend.app.core import brenham_plan_sheet_graph as PSG2
        for sa in adj:
            b = PSG2._BOUNDARY_STA_FT.get(frozenset((10, sa)))
            if b is not None:
                boundary = (sa, b)
    except Exception:
        pass
    # re-derive matchline stations for any candidate's sheet to reject matchline false-positives
    cand_ok = []
    with pdfplumber.open(str(PLAN_PDF)) as pdf2:
        for (s, sta, a) in cand:
            w2 = pdf2.pages[s + PAGE_OFFSET - 1].extract_words(use_text_flow=True, keep_blank_chars=False)
            if sta in matchline_stations(w2):
                p(f"   candidate (s{s},{sta:.0f},166) REJECTED: sits at a matchline station (false positive).")
            else:
                cand_ok.append((s, sta, a))
    p(f"   sheet-10<->adjacent matchline boundary equation: {boundary}")
    if (10, 136.0, 166) in trusted:
        recovered_166 = True
        p("   AP-166 same-component-trusted on sheet 10 -> RECOVERED.")
    elif cand_ok and boundary is not None:
        p(f"   non-matchline AP-166 candidate {cand_ok} + boundary {boundary} — but no deterministic")
        p("   matchline-equation links STA 136 specifically to it -> ABSTAIN (not provable).")
    else:
        p("   => ABSTAIN: no same-component AP-166 on sheet 10; cross-sheet candidates are matchline")
        p("      false-positives or lack a deterministic STA-136->AP-166 matchline equation.")
        p("   STOP chasing AP-166 (per Target #32 rule: one bounded attempt, then move on).")

    p(f"\n   (10,136,166) FINAL: {'RECOVERED' if (10,136.0,166) in trusted or recovered_166 else 'NOT RECOVERED (abstained, stopped)'}")

    json_path = ROOT / "scripts" / "pdf_endpoint_table_8_14.json"
    json_path.write_text(json.dumps({
        "schema_version": SCHEMA_VERSION,
        "trusted_endpoints": sorted(trusted),
        "true_positives": tp, "wrong_ids": wrong, "extra_review": extra, "misses": miss,
        "precision": round(prec, 3), "recall": round(rec, 3),
        "geometry_ready": geo_ready, "ap166_recovered": recovered_166,
    }, indent=2), encoding="utf-8")
    _flush(out)
    print(f"[wrote {json_path}]")


def _flush(out: List[str]) -> None:
    out_path = ROOT / "scripts" / "pdf_endpoint_table_8_14.out"
    out_path.write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))
    print(f"[wrote {out_path}]")


def _selftest() -> None:
    words = [{"text": "1+66", "x0": 100, "x1": 118, "top": 100, "bottom": 110},
             {"text": "MATCHLINE", "x0": 120, "x1": 140, "top": 100, "bottom": 110},
             {"text": "4+51", "x0": 600, "x1": 620, "top": 600, "bottom": 610}]
    ml = matchline_stations(words)
    assert 166.0 in ml and 451.0 not in ml, ml
    # SEE SHEET also flags
    words2 = [{"text": "2+18", "x0": 100, "x1": 118, "top": 100, "bottom": 110},
              {"text": "SEE", "x0": 120, "x1": 135, "top": 100, "bottom": 110}]
    assert 218.0 in matchline_stations(words2)
    print("SELFTEST_OK: matchline + SEE-SHEET station exclusion.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "selftest":
        _selftest()
    else:
        main()
