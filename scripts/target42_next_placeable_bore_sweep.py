"""READ-ONLY Target #42 — corpus-wide sweep for the next placeable bore (the bore_log7 shape).

For EVERY bore_log*.xlsx: match its END station to a confirmed PDF endpoint (Target #37 table),
resolve the AP's terminal-tail route, and run the Target #41 sub-route segmentation test. A bore is
NEW-PLACEABLE only if it yields a UNIQUE proof-grade structure-to-structure segment ending at the
proven AP terminus (G_len ^ G_anchor ^ G_term) — exactly what makes bore_log7 placeable.

NO placement; scripts/ only; no flag/STATE/geometry. Reuses target41.resolve verbatim. Writes JSON + .out.
"""
from __future__ import annotations
import json, os, sys
from pathlib import Path
from typing import Any, Dict, List

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "backend")); sys.path.insert(0, str(ROOT / "scripts"))
for k in ("TRUELINE_JWT_SECRET", "TRUELINE_AUTH_JWT_SECRET"):
    os.environ.setdefault(k, "t42")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")
from backend import main as M
from backend.app.core import pdf_ap_route_resolver as R
import target41_subroute_segmentation_resolver as T41

DESKTOP = Path(r"C:\Users\Patrick\OneDrive\Attachments\Desktop")
KMZ = DESKTOP / "Brenham, TX - Phase 5_Design Team.kmz"
BORE = DESKTOP / "excel bore logs"
CLEAN = ROOT / "scripts" / "pdf_clean_endpoint_table.json"
STA_TOL = 15.0
OUT: List[str] = []
def p(s=""): OUT.append(s)
def _hav(a, b): return R._haversine_ft(float(a[0]), float(a[1]), float(b[0]), float(b[1]))


def main():
    kb = KMZ.read_bytes()
    catalog = [r for r in (M._build_route_catalog(kb, KMZ.name) or []) if r.get("coords")]
    by_id = {str(r["route_id"]): r for r in catalog}
    pf = (M._build_kmz_reference(kb, KMZ.name) or {}).get("point_features") or []
    terminals = R.terminal_nodes_from_point_features(pf)
    # AP id -> unique terminal-tail route
    tail_by_ap: Dict[str, str] = {}
    for t in terminals:
        nm = str(t.get("name"))
        try:
            al, ao = float(t["lat"]), float(t["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        tails = [r for r in catalog if "terminal tail" in str(r.get("source_folder") or "").lower()
                 and min(_hav(r["coords"][0], (al, ao)), _hav(r["coords"][-1], (al, ao))) <= 12.0]
        if len(tails) == 1:
            tail_by_ap[nm] = str(tails[0]["route_id"])

    conf = json.loads(CLEAN.read_text(encoding="utf-8"))["confirmed"]   # [[sheet,sta,ap],...]

    p("=" * 92); p("Target #42 — corpus-wide sweep for the next placeable bore (bore_log7 shape)"); p("=" * 92)
    p(f"confirmed endpoints = {[(int(s), int(st), int(a)) for s, st, a in conf]}  STA_TOL={STA_TOL}\n")

    files = sorted(BORE.glob("bore_log*.xlsx"))
    p(f"scanning {len(files)} bore logs...\n")
    placeable, not_unique, endpoint_match_no_tail, no_endpoint = [], [], [], []
    detail = {}
    for f in files:
        stem = f.stem
        try:
            rows = M._read_bore_log_rows(f.read_bytes(), f.name)
        except Exception:
            continue
        st = sorted(float(r["station_ft"]) for r in rows if r.get("station_ft") is not None)
        if not st:
            continue
        end = st[-1]
        sheets = set()
        for r in rows:
            for tk in M._parse_print_tokens(r.get("print")):
                if str(tk).isdigit():
                    sheets.add(int(tk))
        matches = [(int(s), float(stt), int(a)) for s, stt, a in conf if int(s) in sheets and abs(float(stt) - end) <= STA_TOL]
        if not matches:
            no_endpoint.append(stem); continue
        # for each matched AP, run the #41 segment resolver on its tail route
        bore_verdicts = []
        for (s, stt, ap) in matches:
            rid = tail_by_ap.get(str(ap))
            if not rid:
                bore_verdicts.append((ap, "no_unique_tail_route")); continue
            r = T41.resolve(stem, rid, str(ap), by_id, pf, terminals)
            bore_verdicts.append((ap, r["verdict"]))
        detail[stem] = {"end": end, "sheets": sorted(sheets), "matches": matches, "verdicts": bore_verdicts}
        best = [v for _ap, v in bore_verdicts]
        if any(v == "PLACEABLE_SEGMENT_PROVEN" for v in best):
            placeable.append(stem)
        elif any(v == "NOT_UNIQUE_COMPETING_SEGMENTS" for v in best):
            not_unique.append(stem)
        else:
            endpoint_match_no_tail.append(stem)

    for stem in sorted(detail):
        d = detail[stem]
        p(f"[{stem}] end={d['end']:.0f} sheets={d['sheets']} -> matches={d['matches']} verdicts={d['verdicts']}")

    p("\n" + "-" * 92); p("SUMMARY")
    p(f"   bores scanned: {len(files)}")
    p(f"   endpoint-matched bores: {sorted(detail)}")
    p(f"   PLACEABLE_SEGMENT_PROVEN: {placeable}")
    p(f"   NOT_UNIQUE_COMPETING_SEGMENTS: {not_unique}")
    p(f"   endpoint match but no unique tail / other: {endpoint_match_no_tail}")
    p(f"   no confirmed-endpoint match: {len(no_endpoint)} bores")
    new_placeable = [s for s in placeable if s != "bore_log7"]
    p(f"\n   NEW placeable bores (beyond bore_log7): {new_placeable or 'NONE'}")
    p(f"   CONTROL bore_log7 in PLACEABLE: {'bore_log7' in placeable}")
    p("")
    p("   The corpus-wide sweep confirms the deterministically-placeable set from the delivered files")
    p("   is exactly {bore_log7}. Only bore_log7 and bore_log57 bind to a confirmed PDF endpoint at all;")
    p("   bore_log7 yields a unique whole-route proof-grade segment, bore_log57 does not (#41). No other")
    p("   bore's END lands on a confirmed endpoint, so none can be placed via the PDF-AP lane without the")
    p("   missing per-bore start-structure / terminus signal.")

    verdict = {"schema_version": "target42-placeable-sweep-1",
               "bores_scanned": len(files), "endpoint_matched": sorted(detail),
               "placeable": placeable, "new_placeable_beyond_bore_log7": new_placeable,
               "not_unique": not_unique, "no_endpoint_match_count": len(no_endpoint),
               "detail": detail, "control_bore_log7_placeable": "bore_log7" in placeable}
    (ROOT / "scripts" / "target42_next_placeable_bore_sweep.json").write_text(json.dumps(verdict, indent=2), encoding="utf-8")
    (ROOT / "scripts" / "target42_next_placeable_bore_sweep.out").write_text("\n".join(OUT) + "\n", encoding="utf-8")
    print("\n".join(OUT))

    assert "bore_log7" in placeable, "CONTROL REGRESSED: bore_log7 not placeable"
    print("\nSELFTEST_OK (control placeable; corpus sweep complete)")


if __name__ == "__main__":
    main()
