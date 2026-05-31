"""READ-ONLY Target #39 signal dump — gather every delivered-corpus discriminator for bore_log57.
No verdict here; just surface the raw signals the alternate resolver will score."""
from __future__ import annotations
import os, sys, json
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "backend"))
for k in ("TRUELINE_JWT_SECRET", "TRUELINE_AUTH_JWT_SECRET"):
    os.environ.setdefault(k, "t39d")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")
from backend import main as M
from backend.app.core import pdf_ap_route_resolver as R
from backend.app.core import brenham_plan_sheet_graph as G

DESKTOP = Path(r"C:\Users\Patrick\OneDrive\Attachments\Desktop")
KMZ = DESKTOP / "Brenham, TX - Phase 5_Design Team.kmz"
BORE = DESKTOP / "excel bore logs"


def _hav(a, b):
    return R._haversine_ft(float(a[0]), float(a[1]), float(b[0]), float(b[1]))


def _len(coords):
    return sum(_hav(coords[i - 1], coords[i]) for i in range(1, len(coords)))


def facts(stem):
    f = BORE / (stem + ".xlsx")
    if not f.exists():
        return None
    rows = M._read_bore_log_rows(f.read_bytes(), stem + ".xlsx")
    st = sorted(float(r["station_ft"]) for r in rows if r.get("station_ft") is not None)
    toks = []
    for r in rows:
        for t in M._parse_print_tokens(r.get("print")):
            if t not in toks:
                toks.append(t)
    notes = [str(r.get("notes") or "").strip() for r in rows if str(r.get("notes") or "").strip().lower() not in ("", "nan")]
    return {"stem": stem, "stations": st, "smin": st[0], "smax": st[-1], "span": round(st[-1]-st[0],1),
            "sheets": sorted({int(t) for t in toks if str(t).isdigit()}), "notes": notes, "rows": len(rows)}


def main():
    kb = KMZ.read_bytes()
    catalog = [r for r in (M._build_route_catalog(kb, KMZ.name) or []) if r.get("coords")]
    by_id = {str(r["route_id"]): r for r in catalog}
    pf = (M._build_kmz_reference(kb, KMZ.name) or {}).get("point_features") or []
    terminals = R.terminal_nodes_from_point_features(pf)

    print("=" * 88); print("Target #39 signal dump — bore_log57 + siblings + route_465/AP-157 geometry"); print("=" * 88)

    # --- bore facts: bore_log57 (Seg A) + bore_log58 (Seg B of bore_log24) + neighbors ---
    for stem in ("bore_log57", "bore_log58", "bore_log56", "bore_log59"):
        fa = facts(stem)
        if fa:
            print(f"\n[{stem}] span {fa['smin']:.0f}-{fa['smax']:.0f} ({fa['span']}ft, {fa['rows']} rows) sheets={fa['sheets']}")
            for n in fa["notes"][:2]:
                print(f"    note: {n[:150]}")
        else:
            print(f"\n[{stem}] (absent)")

    # --- AP-157 node + route_465 ---
    ap157 = next((t for t in terminals if str(t.get("name")) == "157"), None)
    print(f"\n[AP-157 node] {ap157.get('lat') if ap157 else None},{ap157.get('lon') if ap157 else None}")
    r465 = by_id.get("route_465")
    if r465:
        c = r465["coords"]; L = _len(c)
        d0 = _hav(c[0], (ap157["lat"], ap157["lon"])) if ap157 else None
        d1 = _hav(c[-1], (ap157["lat"], ap157["lon"])) if ap157 else None
        print(f"[route_465] folder={r465.get('source_folder')!r} len={L:.1f}ft pts={len(c)} "
              f"end0->AP157={d0:.1f}ft end1->AP157={d1:.1f}ft")

    # --- all real-structure run-termini near END=413 on bore_log57 prints {8,10,13} (wide net 45ft) ---
    print("\n[REAL-STRUCTURE run-termini within 45ft of END=413 on sheets {8,10,13}]")
    for (sheet, sta, kind, ap) in R.BRENHAM_PH5_RUN_ENDPOINTS:
        if sheet in (8, 10, 13) and abs(sta - 413) <= 45:
            tag = "MATCHLINE(not a terminus)" if kind == "matchline" else f"REAL:{kind}"
            tail = None
            if kind == "ap" and ap is not None:
                t = next((x for x in terminals if str(x.get("name")) == str(ap)), None)
            print(f"   sheet {sheet} STA {sta:.0f} kind={kind} ap={ap}  -> {tag}")

    # --- corridor membership of the candidate sheets ---
    print("\n[CORRIDOR membership]")
    ev = G.evaluate_bore_log(prints=[8, 10, 13], station_min_ft=0.0, station_max_ft=413.0)
    print(f"   bore_log57 prints {{8,10,13}}: status={ev['status']} corridors={ev['corridors']}")
    print(f"   sheet 8 alone: {G.evaluate_bore_log(prints=[8], station_min_ft=0.0, station_max_ft=413.0)['corridors']}")

    # --- route_465 length vs bore span 413; and is there a connected chain to AP-157 ~413ft? ---
    if r465 and ap157:
        print(f"\n[LENGTH MATCH] bore span=413ft vs route_465 len={_len(r465['coords']):.1f}ft "
              f"(ratio {_len(r465['coords'])/413:.2f})")

    # --- ALL terminal-tail routes whose endpoint is within 12ft of AP-157 (the bore_log7-style test) ---
    print("\n[Terminal-tail routes ending at AP-157 (endpoint<=12ft), with length]")
    if ap157:
        al, ao = ap157["lat"], ap157["lon"]
        for r in catalog:
            fld = str(r.get("source_folder") or "").lower()
            if "terminal tail" not in fld:
                continue
            c = r["coords"]
            de = min(_hav(c[0], (al, ao)), _hav(c[-1], (al, ao)))
            if de <= 12:
                print(f"   {r['route_id']} len={_len(c):.1f}ft endpoint->AP157={de:.1f}ft")
    print("\n[done]")


if __name__ == "__main__":
    main()
