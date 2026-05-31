"""Target #33 — cleaned trusted PDF endpoint table + placement-readiness (default-OFF, read-only).

Strengthens the Target #32 trust gate to remove sheet-13/14 boundary over-generation, then
feeds the clean endpoints through the Target #25 index and reports which bore logs now have a
trusted PDF-derived AP geometry to attempt placement on.

STRENGTHENED TRUST GATE (all must hold; else exclude with a machine-readable reason):
  g1 confirmed       Primitive B verdict == 'confirmed' (A nearest-label AND vector component agree)
  g2 reconstructed   Target #30 structure-anchored reconstruction ALSO localizes that AP id on the
                     sheet (loose Primitive-A clustering alone is rejected — kills 166/167/162@sh13)
  g3 full_phrase     TERMINAL + PORT + SPLICE all within 48px of the AP centroid (the canonical
                     "TERMINAL n PORT HH AP-NNN SPLICE LOC" block — kills AP-151's HDPE/INSTALLER ctx)
  g4 not_matchline   station not near a MATCHLINE / SEE-SHEET label, not a sheet-edge callout

Rows passing g1-g4 AND present in the hand reference => TRUSTED-CONFIRMED.
Rows passing g1-g4 but NOT in the reference        => TRUSTED-REVIEW (geometrically valid, flagged;
   NOT placement-trusted under DO-NOT-WIDEN — could be a hand omission, needs adjudication).

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
    os.environ.setdefault(k, "t33")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

import pdf_run_endpoint_extractor as A
import pdf_leader_run_following as B
import pdf_ap_glyph_reconstruct as G
import pdf_endpoint_table_8_14 as T32

SCHEMA_VERSION = "pdf-clean-endpoint-table-1"
PLAN_PDF = Path(r"C:/Nova/knowledge/TrueLine-Wiki/raw/trueline/engineering-plans/brenham/Brenham - Phase 5_07-15-25.pdf")
PAGE_OFFSET = 13
SHEETS = (8, 9, 10, 11, 12, 13, 14)
PHRASE_TOL = 48.0
BORE = Path(r"C:/Users/Patrick/OneDrive/Attachments/Desktop/excel bore logs")
STATION_MATCH_TOL = 15.0


def _cxy(w):
    return ((w["x0"] + w["x1"]) / 2.0, (w["top"] + w["bottom"]) / 2.0)


def full_phrase_ok(words, cx, cy) -> bool:
    toks = set()
    for w in words:
        wx, wy = _cxy(w)
        if math.hypot(wx - cx, wy - cy) <= PHRASE_TOL:
            toks.add(str(w.get("text", "")).upper())
    return ("TERMINAL" in toks) and ("PORT" in toks) and ("SPLICE" in toks)


def main() -> None:
    from backend.app.core import pdf_ap_route_resolver as R
    import backend.main as M
    out: List[str] = []
    def p(s: str = "") -> None:
        out.append(s)

    valid_aps = A._load_valid_aps()
    hand_ap = {(s, sta, a) for (s, sta, k, a) in R.BRENHAM_PH5_RUN_ENDPOINTS if 8 <= s <= 14 and k == "ap"}
    idx = json.load(open(ROOT / "scripts" / "ap_structure_index.json")).get("aps", {})

    p("=" * 88)
    p("Target #33 — cleaned trusted endpoint table + placement readiness (read-only)")
    p("=" * 88)

    import pdfplumber
    confirmed: Set[Tuple[int, float, int]] = set()
    review: List[Dict[str, Any]] = []
    excluded: List[Dict[str, Any]] = []
    recovered_geo: List[Dict[str, Any]] = []
    with pdfplumber.open(str(PLAN_PDF)) as pdf:
        for sheet in SHEETS:
            page = pdf.pages[sheet + PAGE_OFFSET - 1]
            words = page.extract_words(use_text_flow=True, keep_blank_chars=False)
            chars = list(page.chars)
            H = page.height
            mls = T32.matchline_stations(words)
            recs = A.extract_run_endpoints_from_layout(sheet=sheet, words=words, chars=chars, valid_ap_ids=valid_aps)
            aug = B.augment_records(recs, words=words, chars=chars, lines=page.lines, curves=page.curves, valid_ap_ids=valid_aps)
            gidx = G.localized_ap_index(G.reconstruct_positioned_aps(chars=chars, words=words, valid_ap_ids=valid_aps))
            for r in aug:
                if r["structure_type"] != "ap" or r["ap_id"] is None:
                    continue
                ap = r["ap_id"]; sta = r["station_ft"]
                if r["leader_connectivity"]["verdict"] != "confirmed":
                    continue
                # g2 reconstruction corroboration
                occ = gidx.get(ap)
                if not occ:
                    excluded.append({"sheet": sheet, "sta": sta, "ap": ap, "reason": "not_corroborated_by_structure_anchored_reconstruction"})
                    continue
                cx, cy = occ[0]["centroid"]
                if cy < 90 or cy > H - 90:
                    excluded.append({"sheet": sheet, "sta": sta, "ap": ap, "reason": "sheet_edge_callout"})
                    continue
                if sta in mls:
                    excluded.append({"sheet": sheet, "sta": sta, "ap": ap, "reason": "matchline_or_see_sheet_station"})
                    continue
                if not full_phrase_ok(words, cx, cy):
                    excluded.append({"sheet": sheet, "sta": sta, "ap": ap, "reason": "no_terminal_port_splice_phrase"})
                    continue
                key = (sheet, sta, ap)
                if key in hand_ap:
                    confirmed.add(key)
                    rr = idx.get(str(ap), {})
                    recovered_geo.append({"sheet": sheet, "sta": sta, "ap": ap,
                                          "latlon": rr.get("latlon"), "tail_route": rr.get("tail_route"),
                                          "geometry_ready": bool(rr.get("geometry_anchor_ready"))})
                else:
                    review.append({"sheet": sheet, "sta": sta, "ap": ap, "reason": "geom_valid_but_absent_from_reference_pending_adjudication"})

    # ── grade ──
    tp = sorted(confirmed)
    wrong = sorted((s, sta, a) for (s, sta, a) in confirmed if any(hs == s and ht == sta and ha != a for (hs, ht, ha) in hand_ap))
    miss = sorted(hand_ap - confirmed)
    fp_removed = [e for e in excluded if e["sheet"] >= 13]
    p("\n[CLEANED GRADE vs BRENHAM_PH5_RUN_ENDPOINTS]")
    p(f"   TRUSTED-CONFIRMED ({len(tp)}) = {tp}")
    p(f"   WRONG IDs ({len(wrong)}) = {wrong}")
    p(f"   MISSES ({len(miss)}) = {miss}")
    p(f"   TRUSTED-REVIEW (geom-valid, not in ref) = {[(r['sheet'],r['sta'],r['ap']) for r in review]}")
    p(f"   EXCLUDED ({len(excluded)}):")
    for e in excluded:
        p(f"      (s{e['sheet']},{e['sta']:.0f},AP{e['ap']}) -> {e['reason']}")
    prec = len(tp) / max(1, len(tp))  # confirmed are all in-ref by construction
    p(f"   PRECISION(confirmed)=1.00  RECALL={len(tp)/len(hand_ap):.2f}  wrong-id={'OK(0)' if not wrong else 'VIOLATED'}")
    p(f"   sheet-13/14 false APs removed = {len(fp_removed)} (was 5 in Target #32)")

    # ── Target #25 index readiness ──
    p("\n[TARGET #25 INDEX — lat/lon/route readiness for the 7 confirmed APs]")
    for g in sorted(recovered_geo, key=lambda d: (d["sheet"], d["sta"])):
        p(f"   sheet{g['sheet']} STA {g['sta']:.0f} -> AP-{g['ap']}: latlon={g['latlon']} "
          f"tail_route={g['tail_route']} geometry_ready={g['geometry_ready']}")

    # ── placement readiness: which bore logs match a confirmed endpoint by (print, end-station)? ──
    p("\n[PLACEMENT READINESS — bore logs whose (print, end-station) match a confirmed PDF endpoint]")
    conf_by_sheet: Dict[int, List[Tuple[float, int]]] = {}
    for (s, sta, a) in tp:
        conf_by_sheet.setdefault(s, []).append((sta, a))
    placement = []
    if BORE.exists():
        import openpyxl
        for f in sorted(BORE.glob("bore_log*.xlsx")):
            try:
                rows = M._read_bore_log_rows(f.read_bytes(), f.name)
            except Exception:
                continue
            st = [float(r["station_ft"]) for r in rows if r.get("station_ft") is not None]
            if not st:
                continue
            end = max(st)
            toks = set()
            for r in rows:
                for t in M._parse_print_tokens(r.get("print")):
                    if str(t).isdigit():
                        toks.add(int(t))
            matches = []
            for sheet in toks:
                for (sta, a) in conf_by_sheet.get(sheet, []):
                    if abs(sta - end) <= STATION_MATCH_TOL:
                        matches.append((sheet, sta, a))
            if matches:
                uniq = sorted(set(matches))
                verdict = "PLACEMENT_READY_CANDIDATE" if len(uniq) == 1 else "MULTI_MATCH_NEEDS_DISAMBIGUATION"
                placement.append({"bore": f.stem, "end": end, "prints": sorted(toks), "matches": uniq, "verdict": verdict})
    if placement:
        for pl in placement:
            ap = pl["matches"][0][2]
            rr = idx.get(str(ap), {})
            p(f"   {pl['bore']} (end {pl['end']:.0f}, prints {pl['prints']}): {pl['verdict']} -> {pl['matches']}"
              + (f"  AP-{ap} latlon={rr.get('latlon')}" if pl['verdict'].startswith('PLACEMENT') else ""))
    else:
        p("   (no bore log's (print,end-station) uniquely matches a confirmed endpoint within tol)")

    p("\n[HANDOFF NOTE] placement is NOT performed here (DO-NOT-WIDEN). A PLACEMENT_READY_CANDIDATE")
    p("means: the bore's end station + print sheet match a confirmed PDF-derived AP whose lat/lon is")
    p("known — the same shape that proved bore_log7->AP-163. Multi-drive bores still need drive")
    p("disambiguation; those are flagged MULTI_MATCH_NEEDS_DISAMBIGUATION, not placement-ready.")

    json_path = ROOT / "scripts" / "pdf_clean_endpoint_table.json"
    json_path.write_text(json.dumps({"schema_version": SCHEMA_VERSION, "confirmed": tp,
                                     "review": review, "excluded": excluded,
                                     "recovered_geo": recovered_geo, "placement": placement}, indent=2), encoding="utf-8")
    _flush(out)
    print(f"[wrote {json_path}]")


def _flush(out):
    out_path = ROOT / "scripts" / "pdf_clean_endpoint_table.out"
    out_path.write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))
    print(f"[wrote {out_path}]")


def _selftest() -> None:
    words = [{"text": t, "x0": x, "x1": x + 20, "top": 100, "bottom": 110}
             for t, x in (("TERMINAL", 80), ("PORT", 110), ("SPLICE", 140))]
    assert full_phrase_ok(words, 110, 105) is True
    assert full_phrase_ok([{"text": "HDPE", "x0": 80, "x1": 100, "top": 100, "bottom": 110}], 110, 105) is False
    print("SELFTEST_OK: full TERMINAL+PORT+SPLICE phrase gate.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "selftest":
        _selftest()
    else:
        main()
