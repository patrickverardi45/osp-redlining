"""READ-ONLY Target #41 signal dump — sub-route segmentation evidence for bore_log57 on route_465.

Gathers: (a) EVERY route with an endpoint near AP-157 + its length (is there a ~413ft route?),
(b) route_465 vertex geometry + cumulative offsets, (c) the point 413ft from AP-157 along route_465
and the nearest KMZ node/structure to it (candidate START), (d) what other bores could account for
route_465's remaining length. No verdict; raw signals only."""
from __future__ import annotations
import os, sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "backend"))
for k in ("TRUELINE_JWT_SECRET", "TRUELINE_AUTH_JWT_SECRET"):
    os.environ.setdefault(k, "t41d")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")
from backend import main as M
from backend.app.core import pdf_ap_route_resolver as R

DESKTOP = Path(r"C:\Users\Patrick\OneDrive\Attachments\Desktop")
KMZ = DESKTOP / "Brenham, TX - Phase 5_Design Team.kmz"
BORE = DESKTOP / "excel bore logs"
BORE_LEN = 413.0


def _hav(a, b): return R._haversine_ft(float(a[0]), float(a[1]), float(b[0]), float(b[1]))
def _cum(c):
    out = [0.0]
    for i in range(1, len(c)):
        out.append(out[-1] + _hav(c[i-1], c[i]))
    return out
def _pt_at(c, cum, off):
    off = max(0.0, min(off, cum[-1]))
    for i in range(1, len(c)):
        if cum[i] >= off:
            seg = cum[i]-cum[i-1]; t = 0 if seg <= 0 else (off-cum[i-1])/seg
            return (c[i-1][0]+t*(c[i][0]-c[i-1][0]), c[i-1][1]+t*(c[i][1]-c[i-1][1]))
    return tuple(c[-1])


def main():
    kb = KMZ.read_bytes()
    catalog = [r for r in (M._build_route_catalog(kb, KMZ.name) or []) if r.get("coords")]
    ref = M._build_kmz_reference(kb, KMZ.name) or {}
    pf = ref.get("point_features") or []
    terminals = R.terminal_nodes_from_point_features(pf)
    ap = next((t for t in terminals if str(t.get("name")) == "157"), None)
    al, ao = float(ap["lat"]), float(ap["lon"])
    print("="*90); print("Target #41 signal dump — route_465 sub-route segmentation evidence"); print("="*90)
    print(f"AP-157 node = {al},{ao}   bore_log57 length = {BORE_LEN}ft")

    # (a) ALL routes with an endpoint within 15ft of AP-157, any folder
    print("\n[ALL routes with an endpoint <=15ft of AP-157]")
    for r in catalog:
        c = r["coords"]; cum = _cum(c)
        d0, d1 = _hav(c[0], (al, ao)), _hav(c[-1], (al, ao))
        de = min(d0, d1)
        if de <= 15:
            print(f"   {r['route_id']:<12} folder={str(r.get('source_folder'))[:34]:<34} len={cum[-1]:.1f}ft "
                  f"end0->AP={d0:.1f} end1->AP={d1:.1f}  (len-vs-bore ratio {cum[-1]/BORE_LEN:.2f})")

    # (b)+(c) route_465 vertices + offset-413 point + nearest node
    r465 = next((r for r in catalog if str(r["route_id"]) == "route_465"), None)
    c = r465["coords"]; cum = _cum(c)
    # orient so AP-157 end is offset 0
    if _hav(c[0], (al, ao)) > _hav(c[-1], (al, ao)):
        c = list(reversed(c)); cum = _cum(c)
    print(f"\n[route_465] {len(c)} vertices, total {cum[-1]:.1f}ft, oriented from AP-157 (offset 0)")
    for i, (pt, off) in enumerate(zip(c, cum)):
        # nearest node to this vertex
        nd = min(pf, key=lambda f: _hav((f.get('lat'), f.get('lon')), pt) if f.get('lat') else 9e9)
        dnd = _hav((nd.get('lat'), nd.get('lon')), pt) if nd.get('lat') else 9e9
        tag = f" near node '{nd.get('name')}' [{str(nd.get('folder_path'))[:30]}] @{dnd:.1f}ft" if dnd <= 20 else ""
        print(f"   v{i:<2} off={off:6.1f}ft  ({pt[0]:.6f},{pt[1]:.6f}){tag}")

    S = _pt_at(c, cum, BORE_LEN)
    print(f"\n[CANDIDATE START] point at offset {BORE_LEN}ft from AP-157 along route_465 = ({S[0]:.6f},{S[1]:.6f})")
    near = sorted(((f, _hav((f.get('lat'), f.get('lon')), S)) for f in pf if f.get('lat')), key=lambda z: z[1])[:5]
    print("   5 nearest KMZ nodes to the candidate start:")
    for f, d in near:
        print(f"      '{f.get('name')}' [{str(f.get('folder_path'))[:38]}] @ {d:.1f}ft")

    # opposite-end + middle candidate endpoints for completeness
    print(f"\n[OTHER SEGMENT CANDIDATES on route_465 (total {cum[-1]:.1f}ft)]")
    print(f"   first-413 (from opposite end): covers offset {cum[-1]-BORE_LEN:.1f}..{cum[-1]:.1f}; END at offset {cum[-1]-BORE_LEN:.1f} (dist to AP-157 = {_hav(_pt_at(c,cum,cum[-1]-BORE_LEN),(al,ao)):.1f}ft)")
    mid0 = (cum[-1]-BORE_LEN)/2
    print(f"   middle-413: covers offset {mid0:.1f}..{mid0+BORE_LEN:.1f}; neither end at AP-157")

    # (d) neighbor bores that could drill the remaining length
    print(f"\n[NEIGHBOR BORES — could any drill route_465's remaining {cum[-1]-BORE_LEN:.1f}ft?]")
    for stem in ("bore_log56", "bore_log58", "bore_log59", "bore_log55", "bore_log60"):
        f = BORE / (stem + ".xlsx")
        if not f.exists():
            continue
        rows = M._read_bore_log_rows(f.read_bytes(), stem + ".xlsx")
        st = sorted(float(r["station_ft"]) for r in rows if r.get("station_ft") is not None)
        span = st[-1]-st[0] if st else 0
        print(f"   {stem}: span {span:.0f}ft (0+00->{st[-1]:.0f})")
    print("\n[done]")


if __name__ == "__main__":
    main()
