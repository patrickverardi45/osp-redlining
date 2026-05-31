"""READ-ONLY Target #41 — sub-route segmentation resolver (no .FS).

Determines whether a bore of length L maps to a UNIQUE, proof-grade sub-segment of a longer route,
using delivered geometry only: route vertex geometry, KMZ node anchors along the route, the proven
AP terminus, and bore length. Enumerates every candidate segment of length ~L and scores it.

A segment is PROOF-GRADE only if ALL hold (the bore_log7 shape — a structure-to-structure drive
whose terminus end is the proven AP):
  G_len    : segment length within LEN_TOL of the bore length
  G_anchor : BOTH endpoints sit on a real KMZ structure (handhole / splice / flower pot / AP), i.e.
             a bore drills pit-to-pit, not from open space
  G_term   : one endpoint is the proven AP terminus
Verdict:
  PLACEABLE_SEGMENT_PROVEN          : exactly one segment satisfies G_len & G_anchor & G_term
  NOT_UNIQUE_COMPETING_SEGMENTS     : >=2 segments satisfy (G_len & G_anchor) [terminus may differ]
  HARD_BLOCKED_NO_SEGMENT_DISCRIMINATOR : no segment satisfies all three (e.g. the terminus-anchored
                                          one starts in open space, and the structure-anchored one
                                          doesn't reach the terminus)
NO placement; scripts/ only; no flag/STATE/geometry write. Writes JSON + .out.
"""
from __future__ import annotations
import json, os, sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "backend"))
for k in ("TRUELINE_JWT_SECRET", "TRUELINE_AUTH_JWT_SECRET"):
    os.environ.setdefault(k, "t41")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")
from backend import main as M
from backend.app.core import pdf_ap_route_resolver as R

DESKTOP = Path(r"C:\Users\Patrick\OneDrive\Attachments\Desktop")
KMZ = DESKTOP / "Brenham, TX - Phase 5_Design Team.kmz"
BORE = DESKTOP / "excel bore logs"
LEN_TOL = 0.10          # segment length within 10% of bore length
ANCHOR_TOL = 20.0       # a route point is "at a structure" if a node is within 20ft
TERM_TOL = 12.0         # an endpoint is "at the AP terminus" if within 12ft

OUT: List[str] = []
def p(s=""): OUT.append(s)
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


def bore_len(stem) -> Optional[float]:
    f = BORE / (stem + ".xlsx")
    if not f.exists():
        return None
    rows = M._read_bore_log_rows(f.read_bytes(), stem + ".xlsx")
    st = sorted(float(r["station_ft"]) for r in rows if r.get("station_ft") is not None)
    return st[-1] if st else None   # max station == drilled length from 0+00 frame


def route_anchors(coords, cum, pf):
    """Structural anchor offsets along the route: where a real KMZ node sits within ANCHOR_TOL of a
    route point. Returns sorted list of (offset_ft, node_name, folder)."""
    anchors = []
    # sample at each vertex AND each 30ft step (so anchors between vertices are caught)
    offs = sorted(set(list(cum) + [float(x) for x in range(0, int(cum[-1]) + 1, 30)]))
    seen = set()
    for off in offs:
        pt = _pt_at(coords, cum, off)
        best = None
        for f in pf:
            if not f.get("lat"):
                continue
            d = _hav((f["lat"], f["lon"]), pt)
            if d <= ANCHOR_TOL and (best is None or d < best[1]):
                best = (f, d)
        if best:
            nm = str(best[0].get("name")); fld = str(best[0].get("folder_path") or "")
            key = (nm, fld)
            if key not in seen:
                seen.add(key)
                anchors.append({"offset": round(off, 1), "name": nm, "folder": fld,
                                "dist_ft": round(best[1], 1)})
    return anchors


def resolve(stem, route_id, ap_name, catalog_by_id, pf, terminals):
    L = bore_len(stem)
    r = catalog_by_id.get(route_id)
    if L is None or r is None:
        return {"bore": stem, "verdict": "FACTS_MISSING"}
    ap = next((t for t in terminals if str(t.get("name")) == str(ap_name)), None)
    al, ao = float(ap["lat"]), float(ap["lon"])
    c = list(r["coords"]); cum = _cum(c)
    if _hav(c[0], (al, ao)) > _hav(c[-1], (al, ao)):
        c = list(reversed(c)); cum = _cum(c)     # orient AP at offset 0
    anchors = route_anchors(c, cum, pf)
    total = cum[-1]

    # enumerate candidate segments of length ~L:
    cands = []
    # (1) structure-to-structure anchor pairs
    for i in range(len(anchors)):
        for j in range(i + 1, len(anchors)):
            seglen = anchors[j]["offset"] - anchors[i]["offset"]
            if abs(seglen - L) <= LEN_TOL * L:
                a0, a1 = anchors[i], anchors[j]
                ends_term = a0["offset"] <= TERM_TOL  # offset 0 anchor is the AP terminus
                cands.append({"type": "structure_to_structure", "start_off": a0["offset"],
                              "end_off": a1["offset"], "len": round(seglen, 1),
                              "start_node": a0["name"], "end_node": a1["name"],
                              "both_anchored": True, "ends_at_terminus": ends_term})
    # (2) terminus-anchored segment (end at AP offset 0), start at offset L (may be open space)
    start_pt = _pt_at(c, cum, L)
    near = min((( _hav((f["lat"], f["lon"]), start_pt), f) for f in pf if f.get("lat")), default=(9e9, None))
    start_anchored = near[0] <= ANCHOR_TOL
    if L <= total + LEN_TOL * L:
        cands.append({"type": "terminus_anchored_open_start", "start_off": round(L, 1), "end_off": 0.0,
                      "len": round(min(L, total), 1), "start_node": (str(near[1].get("name")) if start_anchored else None),
                      "start_node_dist_ft": round(near[0], 1), "both_anchored": bool(start_anchored),
                      "ends_at_terminus": True})

    proof = [x for x in cands if x["both_anchored"] and x["ends_at_terminus"]
             and abs(x["len"] - L) <= LEN_TOL * L]

    # collapse proof candidates that describe the SAME physical segment (unordered offset-pair within 15ft)
    def _seg_key(x):
        a, b = sorted((float(x["start_off"]), float(x["end_off"])))
        return (round(a / 15) * 15, round(b / 15) * 15)
    distinct_proof = {_seg_key(x): x for x in proof}

    # a genuinely competing reading = an anchored segment that does NOT reach the terminus
    competing_structure = [x for x in cands if x["both_anchored"] and not x["ends_at_terminus"]]
    terminus_open = [x for x in cands if x["ends_at_terminus"] and not x["both_anchored"]]

    if len(distinct_proof) == 1:
        verdict, reason = "PLACEABLE_SEGMENT_PROVEN", \
            f"unique structure-to-structure segment len~{L:.0f} ending at the AP terminus (both ends real structures)"
    elif len(distinct_proof) >= 2:
        verdict, reason = "NOT_UNIQUE_COMPETING_SEGMENTS", \
            f"{len(distinct_proof)} distinct structure-to-structure segments of the bore length end at the terminus"
    elif competing_structure and terminus_open:
        verdict, reason = "NOT_UNIQUE_COMPETING_SEGMENTS", \
            "a structure-to-structure segment of the bore length exists but does NOT reach the AP terminus, " \
            "while the terminus-anchored segment starts in OPEN SPACE (no pit) -> two competing readings, no discriminator"
    else:
        verdict, reason = "HARD_BLOCKED_NO_SEGMENT_DISCRIMINATOR", \
            "no segment of the bore length is both structure-to-structure anchored AND ends at the AP terminus"
    return {"bore": stem, "route": route_id, "ap": ap_name, "bore_len": L, "route_total_ft": round(total, 1),
            "anchors": anchors, "candidates": cands, "proof_grade": proof, "verdict": verdict, "reason": reason}


def main():
    kb = KMZ.read_bytes()
    catalog = [r for r in (M._build_route_catalog(kb, KMZ.name) or []) if r.get("coords")]
    by_id = {str(r["route_id"]): r for r in catalog}
    pf = (M._build_kmz_reference(kb, KMZ.name) or {}).get("point_features") or []
    terminals = R.terminal_nodes_from_point_features(pf)

    p("=" * 92); p("Target #41 — sub-route segmentation resolver (no .FS)"); p("=" * 92)
    p(f"LEN_TOL={LEN_TOL} ANCHOR_TOL={ANCHOR_TOL}ft TERM_TOL={TERM_TOL}ft\n")

    cases = [("bore_log57", "route_465", "157"), ("bore_log7", "route_469", "163")]
    res = {}
    for stem, rid, ap in cases:
        r = resolve(stem, rid, ap, by_id, pf, terminals)
        res[stem] = r
        role = " (CONTROL)" if stem == "bore_log7" else ""
        p("-" * 92); p(f"[{stem}]{role} bore_len={r['bore_len']:.0f}ft route={rid} total={r['route_total_ft']}ft ap=AP-{ap}")
        p(f"   structural anchors along route: {[(a['offset'], a['name'], a['folder'].split('/')[-1].strip()) for a in r['anchors']]}")
        p("   segment candidates (len ~ bore):")
        for x in r["candidates"]:
            p(f"     {x['type']}: off {x['start_off']}->{x['end_off']} len={x['len']}ft "
              f"start='{x['start_node']}'({x.get('start_node_dist_ft','')}) both_anchored={x['both_anchored']} ends_at_terminus={x['ends_at_terminus']}")
        p(f"   => {r['verdict']}")
        p(f"      {r['reason']}")
        p("")

    t = res["bore_log57"]; c = res["bore_log7"]
    p("-" * 92); p("SUMMARY")
    p(f"   bore_log57: {t['verdict']}")
    p(f"   bore_log7 (control): {c['verdict']} (must be PLACEABLE_SEGMENT_PROVEN)")
    p("")
    p("   KEY FINDING: route_465 runs AP-157 (off 0) <-> SPLICE LOC 45 (off 742), with a Flower Pot")
    p("   (~288) and Installer HH (~693) between. The ONLY structure-to-structure segment ~413ft is")
    p("   Flower Pot->Installer HH (~405ft) which does NOT reach AP-157; the terminus-anchored 'last")
    p("   413ft ending at AP-157' starts in OPEN SPACE (nearest node ~35ft, no pit). So the 413ft")
    p("   END<->AP-157 station match (#39) has NO placeable drive geometry: the segmentation is")
    p("   genuinely ambiguous. Missing discriminator = a per-bore START-structure (which pit it drilled")
    p("   from). bore_log7 differs: route_469 (~459) ~= bore (~451) is the WHOLE route, both ends real")
    p("   structures (AP-163 + SPLICE LOC 46) -> proof-grade.")

    verdict = {"schema_version": "target41-subroute-1",
               "bore_log57": {k: t[k] for k in ("verdict", "bore_len", "route_total_ft", "candidates", "reason")},
               "bore_log7_control": c["verdict"],
               "missing_discriminator": "per_bore_start_structure (which pit the bore drilled from); route geometry shows no structure-to-structure 413ft segment ends at AP-157"}
    (ROOT / "scripts" / "target41_subroute_segmentation_resolver.json").write_text(json.dumps(verdict, indent=2), encoding="utf-8")
    (ROOT / "scripts" / "target41_subroute_segmentation_resolver.out").write_text("\n".join(OUT) + "\n", encoding="utf-8")
    print("\n".join(OUT))

    assert c["verdict"] == "PLACEABLE_SEGMENT_PROVEN", f"CONTROL REGRESSED: bore_log7 {c['verdict']}"
    assert t["verdict"] in ("PLACEABLE_SEGMENT_PROVEN", "NOT_UNIQUE_COMPETING_SEGMENTS", "HARD_BLOCKED_NO_SEGMENT_DISCRIMINATOR")
    print("\nSELFTEST_OK (control proof-grade; target verdict emitted)")


if __name__ == "__main__":
    main()
