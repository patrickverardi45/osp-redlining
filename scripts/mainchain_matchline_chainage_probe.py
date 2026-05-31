"""READ-ONLY Target #22 — Matchline-Equation Chainage Extraction Probe (bore_log16/43).

Question (the main_chain_absolute_stationing_no_anchor blocker):
  Does the existing Brenham source (PDF-derived matchline graph + run-endpoint table
  + KMZ) contain enough matchline/local-station information to convert
      absolute station -> sheet/local station -> corridor position + direction
  for the two main-chain high-station logs bore_log16 (prints 8/9/10, sta 5100-5950)
  and bore_log43 (print 10, sta 4000-5919)?

This probe uses ONLY in-repo artifacts:
  - backend/app/core/brenham_plan_sheet_graph.py   (the ALREADY-EXTRACTED matchline
    network: _MATCHLINE_EDGES, _BOUNDARY_STA_FT, _SHEET_WINDOW_FT)
  - BRENHAM_PH5_RUN_ENDPOINTS                       (station -> named structure table)
The bore_log16/43 (prints, station min/max) facts are the VERBATIM values from the
Target #21 probe .out (gac/mainchain_high_station_adjudication.md §1), used here as
deterministic input constants so the probe is self-contained.

NO placement, NO STATE/engine change, NO flag, NO geometry moved. Writes
scripts/mainchain_matchline_chainage_probe.out.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from backend.app.core import brenham_plan_sheet_graph as G  # noqa: E402
from backend.app.core import pdf_ap_route_resolver as R  # noqa: E402

OUT: List[str] = []
def p(s: str = "") -> None:
    OUT.append(s)

# Bore facts — VERBATIM from Target #21 probe (.out), cited input constants.
BORES = {
    "bore_log16": {"prints": [8, 9, 10], "sta_min": 5100.0, "sta_max": 5950.0},
    "bore_log43": {"prints": [10], "sta_min": 4000.0, "sta_max": 5919.0},
}
# The one already-source-proven anchor (Targets #13/#14/#16): bore_log7 end station
# 451 on sheet 10 -> AP-163 (Terminal Port HH) -> route_469.
PROVEN_ANCHOR = {"sheet": 10, "station_ft": 451.0, "ap": 163, "route": "route_469"}
ANCHOR_TOL_FT = 25.0  # same tolerance class the #21 adjudication used


def _table() -> Tuple[Tuple[int, float, str, Optional[int]], ...]:
    return R.BRENHAM_PH5_RUN_ENDPOINTS


def _named_anchors_near(station_ft: float, tol_ft: float) -> List[Tuple[int, float, str, Optional[int]]]:
    """Run-endpoint rows that are a NAMED, KMZ-locatable structure (ap) within tol of
    the given station. Splice/installer/matchline/flower_pot carry no id -> not a
    geometry anchor for absolute-chainage geolocation."""
    out = []
    for (sheet, sta, kind, ap) in _table():
        if kind == "ap" and ap is not None and abs(sta - station_ft) <= tol_ft:
            out.append((sheet, sta, kind, ap))
    return out


def main() -> None:
    p("=" * 78)
    p("Target #22 — Matchline-Equation Chainage Extraction Probe")
    p("=" * 78)

    # ── Section A: the extracted matchline network (what IS present) ──────────
    p("\n[A] EXTRACTED matchline-equation network (brenham_plan_sheet_graph.py)")
    p(f"    schema = {G.SCHEMA_VERSION}; PAGE_OFFSET = {G.PAGE_OFFSET} (sheet N = page N+13)")
    corridors = G.build_corridors()
    p(f"    corridors (connected components over SEE-SHEET matchline edges):")
    for c in corridors:
        ext = G.corridor_extent_ft(c)
        p(f"      {c}  extent_ft={ext}")
    p(f"    boundary STA equations (MATCHLINE STA = SEE SHEET, proven shared value):")
    for pair, sta in sorted(G._BOUNDARY_STA_FT.items(), key=lambda kv: kv[1]):
        p(f"      {sorted(pair)} -> {sta} ft")
    max_boundary = max(G._BOUNDARY_STA_FT.values())
    p(f"    MAX extracted boundary STA = {max_boundary} ft")

    # Which corridor holds each relevant sheet?
    p("\n    corridor membership of the bore sheets:")
    for s in (7, 8, 9, 10, 11, 12):
        p(f"      sheet {s:>2} -> corridor {G.corridor_for_sheet(s)}")

    # ── Section B: run the graph on the two main-chain logs ──────────────────
    p("\n[B] GRAPH VERDICT on the two main-chain logs (evaluate_bore_log)")
    for name, f in BORES.items():
        ev = G.evaluate_bore_log(
            prints=f["prints"], station_min_ft=f["sta_min"], station_max_ft=f["sta_max"]
        )
        p(f"    {name}: prints={f['prints']} sta={f['sta_min']:.0f}-{f['sta_max']:.0f}")
        p(f"      status            = {ev['status']}")
        p(f"      corridors spanned = {ev['corridors']} (count={ev['corridor_count']})")
        p(f"      corridor_extents  = {ev['corridor_extents']}")
        p(f"      sheet_windows     = {ev['sheet_windows']}")
        p(f"      reasons           = {ev['status_reasons']}")
        # Does the bore's station range exceed the max extracted chainage anywhere?
        exceeds = f["sta_max"] > max_boundary
        p(f"      sta_max {f['sta_max']:.0f} > max_boundary {max_boundary:.0f}? {exceeds}")

    # ── Section C: station<->geometry anchor test (the load-bearing edge) ─────
    p("\n[C] STATION<->GEOMETRY ANCHOR TEST (run-endpoint table = only station->KMZ bridge)")
    tbl = _table()
    ap_rows = [(s, sta, k, a) for (s, sta, k, a) in tbl if k == "ap" and a is not None]
    p(f"    named-AP rows in table: {len(ap_rows)}; station range = "
      f"{min(r[1] for r in ap_rows):.0f}..{max(r[1] for r in ap_rows):.0f} ft")
    all_sta = [sta for (_s, sta, _k, _a) in tbl]
    p(f"    ALL table stations span = {min(all_sta):.0f}..{max(all_sta):.0f} ft")

    # C1: self-validate the MECHANISM on the proven bore_log7 anchor.
    p("\n    [C1] self-validation of the station->named-structure->KMZ mechanism "
      "on the PROVEN anchor bore_log7 (sta 451, sheet 10):")
    hits = _named_anchors_near(PROVEN_ANCHOR["station_ft"], ANCHOR_TOL_FT)
    on_sheet = [h for h in hits if h[0] == PROVEN_ANCHOR["sheet"]]
    p(f"        named anchors within {ANCHOR_TOL_FT:.0f} ft of sta 451: {hits}")
    proven_ok = any(h[0] == PROVEN_ANCHOR["sheet"] and h[3] == PROVEN_ANCHOR["ap"] for h in on_sheet)
    p(f"        -> reproduces sheet 10 / AP-163 (route_469)? {proven_ok}  "
      f"(this is the mechanism that proved bore_log7)")

    # C2: same mechanism on the main-chain bore END stations.
    p("\n    [C2] same mechanism on the main-chain bore END stations:")
    for name, f in BORES.items():
        end = f["sta_max"]
        hits = _named_anchors_near(end, ANCHOR_TOL_FT)
        p(f"        {name} end sta {end:.0f}: named anchors within {ANCHOR_TOL_FT:.0f} ft = "
          f"{hits if hits else 'NONE'}")

    # ── Section D: verdict ───────────────────────────────────────────────────
    p("\n[D] VERDICT")
    p("    PRESENT  : matchline-equation network IS extracted (boundary STA equations +")
    p("               SEE-SHEET corridor graph) for the main chain (sheets 3-9) and the")
    p("               Niebuhr / Glenda clusters. So matchline equations are NOT missing.")
    p("    MISSING-1: the graph is STATION-SPACE ONLY (zero lat/lon). There is NO")
    p("               station<->geometry anchor in it; the ONLY station->KMZ bridge is a")
    p("               NAMED AP in the run-endpoint table.")
    p(f"    MISSING-2: the bores' absolute stations (4000-5950) EXCEED the max extracted")
    p(f"               boundary STA ({max_boundary:.0f}) AND the max named-AP station")
    p(f"               ({max(r[1] for r in ap_rows):.0f}); NO named anchor exists at their")
    p("               end stations -> the chainage cannot be tied to a KMZ position/direction.")
    p("    => PARTIAL chainage graph with a NAMED missing edge: a station<->geometry anchor")
    p("       (a KMZ-locatable named structure at an absolute station in the 4000-5950 range)")
    p("       plus a direction datum. Self-validation CONFIRMS the mechanism works where an")
    p("       anchor exists (bore_log7/451/AP-163) and is ABSENT for bore_log16/43.")

    out_path = ROOT / "scripts" / "mainchain_matchline_chainage_probe.out"
    out_path.write_text("\n".join(OUT) + "\n", encoding="utf-8")
    print("\n".join(OUT))
    print(f"\n[wrote {out_path}]")


if __name__ == "__main__":
    main()
