"""READ-ONLY Target #43 — ambiguity-resolution input seam for blocked bores (default-OFF).

#41/#42 proved bore_log57 is blocked by ONE narrow missing field: the per-bore START structure (which
pit the drill began at). This module is the deterministic seam that consumes an office-provided start
structure and places the redline — WITHOUT inventing the value.

INPUT SCHEMA (per-bore ambiguity-resolution override; one record per blocked bore):
  {
    "bore_log_id": "bore_log57",
    "route_id": "route_465",                 # the terminal-tail route the bore lies on (#39)
    "end_structure": {"type": "ap", "id": "157"},     # the proven terminus (#37/#39)
    "start_structure": {                              # EXACTLY ONE of:
        "type": "kmz_node",   "name": "<KMZ node name>"            # a named structure on the route, OR
        # "type": "route_offset", "offset_ft": 413                  # offset along route from the END, OR
        # "type": "coordinate", "lat": <f>, "lon": <f>             # an explicit pit lat/lon
    },
    "notes": "office-provided; which structure/pit this bore started from"
  }

RESOLVER `resolve_placement_with_start(...)`:
  1. orient the route so the END terminus is offset 0
  2. resolve the START point coords from start_structure (node / offset / coordinate)
  3. project START onto the route; require it lie ON the route (<= ON_ROUTE_TOL) -> else blocker
  4. segment = route[0 .. start_offset]; seg_len = start_offset
  5. require |seg_len - bore_len| <= LEN_TOL*bore_len -> else blocker (start inconsistent with bore length)
  6. emit a default-OFF placement CANDIDATE {start_latlon, end_latlon, segment_coords} or a machine blocker

`enumerate_start_candidates(...)` lists every mapped structure on the route with its segment-to-END
length and whether it matches the bore length — the office's decision surface.

NO production placement, no flag wired, no STATE/geometry write. scripts/ only. Self-test SELFTEST_OK.
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
    os.environ.setdefault(k, "t43")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")
from backend import main as M
from backend.app.core import pdf_ap_route_resolver as R

DESKTOP = Path(r"C:\Users\Patrick\OneDrive\Attachments\Desktop")
KMZ = DESKTOP / "Brenham, TX - Phase 5_Design Team.kmz"
BORE = DESKTOP / "excel bore logs"
LEN_TOL = 0.10
ON_ROUTE_TOL = 20.0
ANCHOR_TOL = 20.0


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
def _project_offset(c, cum, pt):
    """nearest offset on the polyline to pt + the perpendicular distance."""
    best = (9e9, 0.0)
    for i in range(1, len(c)):
        # sample the segment
        for s in range(0, 21):
            t = s / 20.0
            q = (c[i-1][0]+t*(c[i][0]-c[i-1][0]), c[i-1][1]+t*(c[i][1]-c[i-1][1]))
            d = _hav(q, pt)
            if d < best[0]:
                best = (d, cum[i-1] + t*(cum[i]-cum[i-1]))
    return best  # (dist_ft, offset_ft)


def _oriented_route(route, end_latlon):
    c = list(route["coords"]); cum = _cum(c)
    if _hav(c[0], end_latlon) > _hav(c[-1], end_latlon):
        c = list(reversed(c)); cum = _cum(c)
    return c, cum


def _resolve_start_point(start_spec, c, cum, point_features) -> Tuple[Optional[Tuple[float, float]], Optional[str]]:
    t = start_spec.get("type")
    if t == "coordinate":
        return (float(start_spec["lat"]), float(start_spec["lon"])), None
    if t == "route_offset":
        return _pt_at(c, cum, float(start_spec["offset_ft"])), None
    if t == "kmz_node":
        nm = str(start_spec.get("name"))
        node = next((f for f in point_features if str(f.get("name")) == nm and f.get("lat")), None)
        if not node:
            return None, f"start_kmz_node_not_found:{nm}"
        return (float(node["lat"]), float(node["lon"])), None
    return None, f"unknown_start_type:{t}"


def resolve_placement_with_start(*, bore_log_id, bore_len_ft, end_latlon, route, start_spec,
                                 point_features) -> Dict[str, Any]:
    c, cum = _oriented_route(route, end_latlon)
    total = cum[-1]
    sp, err = _resolve_start_point(start_spec, c, cum, point_features)
    if err:
        return {"bore": bore_log_id, "verdict": "BLOCKED", "reason": err}
    dist, off = _project_offset(c, cum, sp)
    if dist > ON_ROUTE_TOL:
        return {"bore": bore_log_id, "verdict": "BLOCKED",
                "reason": f"start_not_on_route:{dist:.1f}ft_from_route(tol_{ON_ROUTE_TOL})"}
    seg_len = off  # END is at offset 0; start at offset `off`
    if abs(seg_len - bore_len_ft) > LEN_TOL * bore_len_ft:
        return {"bore": bore_log_id, "verdict": "BLOCKED",
                "reason": f"segment_len_{seg_len:.1f}ft_vs_bore_{bore_len_ft:.0f}ft_outside_{int(LEN_TOL*100)}pct"}
    seg_pts = [list(_pt_at(c, cum, o)) for o in [x for x in cum if x <= off] + [off]]
    start_pt = _pt_at(c, cum, off)
    return {"bore": bore_log_id, "verdict": "PLACEMENT_CANDIDATE",
            "start_latlon": [round(start_pt[0], 7), round(start_pt[1], 7)],
            "end_latlon": [round(end_latlon[0], 7), round(end_latlon[1], 7)],
            "segment_len_ft": round(seg_len, 1), "bore_len_ft": bore_len_ft,
            "route_total_ft": round(total, 1), "segment_coords": seg_pts,
            "note": "DEFAULT-OFF candidate; geometry computed by engine from the office-provided start structure"}


def enumerate_start_candidates(*, route, end_latlon, bore_len_ft, point_features) -> List[Dict[str, Any]]:
    c, cum = _oriented_route(route, end_latlon)
    out = []
    offs = sorted(set(list(cum) + [float(x) for x in range(0, int(cum[-1]) + 1, 30)]))
    seen = set()
    for off in offs:
        pt = _pt_at(c, cum, off)
        best = None
        for f in point_features:
            if not f.get("lat"):
                continue
            d = _hav((f["lat"], f["lon"]), pt)
            if d <= ANCHOR_TOL and (best is None or d < best[1]):
                best = (f, d)
        if best:
            nm = str(best[0].get("name")); fld = str(best[0].get("folder_path") or "").split("/")[-1].strip()
            key = (nm, fld)
            if key in seen:
                continue
            seen.add(key)
            seg_to_end = off
            out.append({"node": nm, "folder": fld, "offset_ft": round(off, 1),
                        "segment_to_end_ft": round(seg_to_end, 1),
                        "matches_bore_len": abs(seg_to_end - bore_len_ft) <= LEN_TOL * bore_len_ft})
    return out


# ── driver ──
def _bore_len(stem):
    rows = M._read_bore_log_rows((BORE / (stem + ".xlsx")).read_bytes(), stem + ".xlsx")
    st = sorted(float(r["station_ft"]) for r in rows if r.get("station_ft") is not None)
    return st[-1] if st else None


def main():
    kb = KMZ.read_bytes()
    catalog = {str(r["route_id"]): r for r in (M._build_route_catalog(kb, KMZ.name) or []) if r.get("coords")}
    pf = (M._build_kmz_reference(kb, KMZ.name) or {}).get("point_features") or []
    terminals = R.terminal_nodes_from_point_features(pf)
    def ap_latlon(name):
        t = next((x for x in terminals if str(x.get("name")) == str(name)), None)
        return (float(t["lat"]), float(t["lon"])) if t else None

    out = []
    def p(s=""): out.append(s)
    p("=" * 92); p("Target #43 — ambiguity-resolution input seam (default-OFF) — bore_log57 + bore_log7 control"); p("=" * 92)

    # --- bore_log57 candidate enumeration (the office decision surface) ---
    L57 = _bore_len("bore_log57"); end57 = ap_latlon("157"); r465 = catalog["route_465"]
    cands = enumerate_start_candidates(route=r465, end_latlon=end57, bore_len_ft=L57, point_features=pf)
    p(f"\n[bore_log57] bore_len={L57:.0f}ft end=AP-157 route=route_465 ({_cum(r465['coords'])[-1]:.0f}ft total)")
    p("   START-structure candidates on route_465 (segment = structure -> AP-157):")
    for c2 in cands:
        p(f"     '{c2['node']}' [{c2['folder']}] off={c2['offset_ft']}ft  seg_to_AP157={c2['segment_to_end_ft']}ft  "
          f"matches_413={c2['matches_bore_len']}")
    matched = [c2 for c2 in cands if c2["matches_bore_len"]]
    p(f"   => mapped structures whose segment to AP-157 == {L57:.0f}ft (+/-10%): {[c2['node'] for c2 in matched] or 'NONE'}")
    p("      (If NONE: the start is an UNMAPPED pit; office must supply its coordinate or a route_offset.)")

    # --- demonstrate the resolver mechanism for EACH input type (NOT asserting truth) ---
    p("\n   RESOLVER DEMONSTRATION (mechanism only — values are office inputs, not invented ground truth):")
    demos = [
        ("kmz_node 'SPLICE LOC 45'", {"type": "kmz_node", "name": "SPLICE LOC 45"}),
        ("kmz_node Flower Pot @289 (by offset proxy)", {"type": "route_offset", "offset_ft": 288.7}),
        ("route_offset 413 (the open-space point #41 computed)", {"type": "route_offset", "offset_ft": 413.0}),
    ]
    demo_out = []
    for label, spec in demos:
        res = resolve_placement_with_start(bore_log_id="bore_log57", bore_len_ft=L57, end_latlon=end57,
                                           route=r465, start_spec=spec, point_features=pf)
        demo_out.append({"input": label, "spec": spec, "result": res})
        if res["verdict"] == "PLACEMENT_CANDIDATE":
            p(f"     [{label}] -> PLACEMENT_CANDIDATE start={res['start_latlon']} end={res['end_latlon']} seg={res['segment_len_ft']}ft")
        else:
            p(f"     [{label}] -> BLOCKED ({res['reason']})")

    # --- bore_log7 CONTROL: start = SPLICE LOC 46, end = AP-163 on route_469 -> must place whole route ---
    L7 = _bore_len("bore_log7"); end7 = ap_latlon("163"); r469 = catalog["route_469"]
    ctrl = resolve_placement_with_start(bore_log_id="bore_log7", bore_len_ft=L7, end_latlon=end7,
                                        route=r469, start_spec={"type": "kmz_node", "name": "SPLICE LOC 46"},
                                        point_features=pf)
    p(f"\n[bore_log7 CONTROL] bore_len={L7:.0f}ft start='SPLICE LOC 46' end=AP-163 route=route_469")
    p(f"   => {ctrl['verdict']}" + (f" start={ctrl['start_latlon']} end={ctrl['end_latlon']} seg={ctrl['segment_len_ft']}ft"
                                    if ctrl['verdict'] == 'PLACEMENT_CANDIDATE' else f" ({ctrl.get('reason')})"))

    p("\n[SEAM] integration (default-OFF, NOT wired this session):")
    p("   mirror the shipped Target #14 pattern (_apply_terminal_tail_placement_override + flag")
    p("   TRUELINE_TERMINAL_TAIL_PLACEMENT). A new default-OFF flag TRUELINE_AMBIGUITY_START_OVERRIDE")
    p("   would, for bores present in an office-provided overrides JSON, call resolve_placement_with_start")
    p("   in an isolated post-rebuild pass and re-render ONLY those bores. Flag-OFF => byte-identical.")

    print("\n".join(out))
    verdict = {
        "schema_version": "target43-ambiguity-input-1",
        "input_schema_example": {
            "bore_log_id": "bore_log57", "route_id": "route_465",
            "end_structure": {"type": "ap", "id": "157"},
            "start_structure": {"type": "route_offset", "offset_ft": 413.0,
                                "_alt": ["{type:kmz_node,name:...}", "{type:coordinate,lat:..,lon:..}"]},
            "notes": "OFFICE MUST PROVIDE the real start; offset_ft here is the #41-computed open-space point, NOT confirmed ground truth"},
        "bore_log57": {"bore_len_ft": L57, "route_total_ft": round(_cum(r465['coords'])[-1], 1),
                       "start_candidates": cands, "mapped_match_to_bore_len": [c2["node"] for c2 in matched],
                       "resolver_demos": demo_out},
        "control_bore_log7": ctrl["verdict"],
        "ground_truth_invented": False,
    }
    (ROOT / "scripts" / "target43_ambiguity_resolution.json").write_text(json.dumps(verdict, indent=2), encoding="utf-8")
    (ROOT / "scripts" / "target43_ambiguity_resolution.out").write_text("\n".join(out) + "\n", encoding="utf-8")

    # selftest assertions
    assert ctrl["verdict"] == "PLACEMENT_CANDIDATE", f"CONTROL FAILED: {ctrl}"
    assert abs(ctrl["segment_len_ft"] - L7) <= LEN_TOL * L7
    # a 413 route_offset start must place (mechanism works); a wrong-length mapped node must BLOCK
    d413 = next(d for d in demo_out if "413" in d["input"])
    assert d413["result"]["verdict"] == "PLACEMENT_CANDIDATE", d413
    dsplice = next(d for d in demo_out if "SPLICE LOC 45" in d["input"])
    assert dsplice["result"]["verdict"] == "BLOCKED", dsplice  # 742ft != 413ft -> correctly blocked
    print("\nSELFTEST_OK (control places; 413-offset places; wrong-length start blocks; no ground truth invented)")


if __name__ == "__main__":
    main()
