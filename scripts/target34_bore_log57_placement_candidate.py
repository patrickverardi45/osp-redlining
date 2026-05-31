"""READ-ONLY Target #34 — first trusted PDF-derived placement attempt beyond bore_log7.

Question: can bore_log57 be SAFELY auto-placed as a redline using ONLY the trusted
PDF-derived endpoint table (Target #33) + the Target #25 AP/structure index + existing
route geometry — without guessing?

Primary candidate: bore_log57 -> AP-157 (the first NEW PLACEMENT_READY_CANDIDATE the
Target #33 cleanup surfaced). bore_log7 -> AP-163 is run as a CONTROL: it must still
PASS every gate (the gate is the exact shape that proved bore_log7 -> route_469; if the
control regressed, the gate is mis-calibrated).

Placement-readiness gate (mirrors the bore_log7 proof — all four required):
  G1 structure_side_trusted : bore END station matches EXACTLY ONE confirmed PDF-derived
                              AP endpoint (Target #33 clean table) within TOL, and that AP
                              is geometry_anchor_ready in the Target #25 index
                              (lat/lon + terminal-tail route present).
  G2 single_corridor        : matchline-graph status is NOT multi_corridor_span.
  G3 no_competing_terminus  : no competing UNNAMED run terminus (matchline/splice/flower
                              pot) within TOL of the END on the bore's print sheets.
  G4 print_mapping_certain  : the bore's own notes do NOT flag "print mapping uncertain".

PLACEMENT_READY  <=> G1 and G2 and G3 and G4.
Otherwise        -> ABSTAIN with the exact failing gate(s) (machine-readable blocker).

This is the structure-side analogue of resolve_terminal_tail_route_for_ap: G1 establishes
the AP and its terminal-tail route; G2-G4 establish that the BORE's END uniquely belongs
to that AP's drive/corridor. A clean structure side (G1) is NECESSARY but NOT SUFFICIENT.

NO placement, NO geometry write, NO engine/STATE change, NO flag. Pure read-only adjudication
over the committed trusted artifacts + read-only bore xlsx. Writes the JSON verdict + .out.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))
for k in ("TRUELINE_JWT_SECRET", "TRUELINE_AUTH_JWT_SECRET"):
    os.environ.setdefault(k, "t34-place")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

from backend import main as M  # noqa: E402
from backend.app.core import pdf_ap_route_resolver as R  # noqa: E402
from backend.app.core import brenham_plan_sheet_graph as G  # noqa: E402

BORE = Path(r"C:\Users\Patrick\OneDrive\Attachments\Desktop\excel bore logs")
CLEAN_TABLE = ROOT / "scripts" / "pdf_clean_endpoint_table.json"
AP_INDEX = ROOT / "scripts" / "ap_structure_index.json"
TOL = 15.0  # same terminus tolerance class used in Targets #10/#21/#23/#33

# Candidate bores from the Target #33 clean table's PLACEMENT block.
# bore_log7 is the CONTROL (proven -> route_469); bore_log57 is the TARGET.
CANDIDATES = ["bore_log57", "bore_log7"]

OUT: List[str] = []
def p(s: str = "") -> None:
    OUT.append(s)


def _facts(stem: str) -> Optional[Dict[str, Any]]:
    f = BORE / (stem + ".xlsx")
    if not f.exists():
        return None
    rows = M._read_bore_log_rows(f.read_bytes(), stem + ".xlsx")
    st = sorted(float(r["station_ft"]) for r in rows if r.get("station_ft") is not None)
    toks: List[str] = []
    for r in rows:
        for t in M._parse_print_tokens(r.get("print")):
            if t not in toks:
                toks.append(t)
    sheets = sorted({int(t) for t in toks if str(t).isdigit()})
    notes = [str(r.get("notes") or "").strip() for r in rows
             if str(r.get("notes") or "").strip() and str(r.get("notes")).strip().lower() != "nan"]
    return {"rows": len(rows), "sheets": sheets, "stations": st,
            "smin": st[0] if st else None, "smax": st[-1] if st else None, "notes": notes}


def _confirmed_table() -> List[Tuple[int, float, int]]:
    d = json.loads(CLEAN_TABLE.read_text(encoding="utf-8"))
    return [(int(s), float(sta), int(ap)) for (s, sta, ap) in d.get("confirmed", [])]


def _ap_index() -> Dict[str, Dict[str, Any]]:
    return json.loads(AP_INDEX.read_text(encoding="utf-8")).get("aps", {})


def _termini_near(end_ft: float, sheets: List[int], tol: float):
    """All run-endpoint rows on the bore's print sheets within tol of the END station."""
    named, allh = [], []
    for (sheet, sta, kind, ap) in R.BRENHAM_PH5_RUN_ENDPOINTS:
        if sheet in sheets and abs(sta - end_ft) <= tol:
            allh.append((sheet, sta, kind, ap))
            if kind == "ap" and ap is not None:
                named.append((sheet, sta, kind, ap))
    return named, allh


def adjudicate(stem: str, table: List[Tuple[int, float, int]], apidx: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    fa = _facts(stem)
    if not fa or fa["smax"] is None:
        return {"bore": stem, "verdict": "ABSTAIN", "blockers": ["facts_missing"],
                "missing_artifact": "bore xlsx / station column"}
    end = fa["smax"]
    sheets = fa["sheets"]

    # --- G1: structure side trusted (clean table, unique, geometry-ready) ---
    confirmed_hits = [(s, sta, ap) for (s, sta, ap) in table
                      if s in sheets and abs(sta - end) <= TOL]
    g1_ap = None
    g1_route = None
    g1_latlon = None
    if len(confirmed_hits) == 1:
        s, sta, ap = confirmed_hits[0]
        idx = apidx.get(str(ap), {})
        if idx.get("geometry_anchor_ready") and idx.get("latlon") and idx.get("tail_route"):
            g1_ap, g1_route, g1_latlon = ap, idx["tail_route"], idx["latlon"]
    g1 = g1_ap is not None

    # --- corridor / competing-terminus context ---
    ev = G.evaluate_bore_log(prints=sheets, station_min_ft=fa["smin"], station_max_ft=fa["smax"])
    named, allh = _termini_near(end, sheets, TOL)
    competing = [(h[0], h[1], h[2]) for h in allh if h[3] is None]  # unnamed termini near END
    notes_blob = " ".join(fa["notes"]).lower()

    # --- G2 / G3 / G4 (bore-side drive disambiguation) ---
    g2 = ev["status"] != "multi_corridor_span"
    g3 = len(competing) == 0
    g4 = "print mapping uncertain" not in notes_blob

    blockers: List[str] = []
    if not g1:
        blockers.append("structure_side_not_uniquely_trusted")
    if not g2:
        blockers.append("multi_corridor_span")
    if not g3:
        blockers.append("competing_unnamed_terminus_within_tol")
    if not g4:
        blockers.append("print_mapping_flagged_uncertain")

    placeable = g1 and g2 and g3 and g4
    rec: Dict[str, Any] = {
        "bore": stem,
        "prints": sheets,
        "station_span": [fa["smin"], end],
        "rows": fa["rows"],
        "gates": {"G1_structure_side_trusted": g1, "G2_single_corridor": g2,
                  "G3_no_competing_terminus": g3, "G4_print_mapping_certain": g4},
        "structure_side": {
            "confirmed_endpoint_hits": confirmed_hits,
            "resolved_ap": g1_ap, "tail_route": g1_route, "latlon": g1_latlon,
            "geometry_ready": g1,
        },
        "bore_side": {
            "corridor_status": ev["status"], "corridors": ev["corridors"],
            "named_ap_termini_near_end": named,
            "competing_unnamed_termini_near_end": competing,
            "notes": fa["notes"],
        },
        "verdict": "PLACEMENT_READY" if placeable else "ABSTAIN",
        "blockers": blockers,
    }
    if not placeable:
        rec["missing_artifact"] = (
            ".FS Fiber-Schematic / drive-decomposition sheet (which drive/terminus this "
            "bore's END belongs to) OR a per-bore terminus-structure/direction field — "
            "absent from all provided Brenham sources (Target #23/#24). "
            "Structure side (AP + tail route + lat/lon) IS ready; the BORE->drive binding is not."
        ) if g1 else "trusted PDF-derived AP endpoint for this bore's END station"
    return rec


def main() -> None:
    p("=" * 84)
    p("Target #34 — bore_log57 PDF-derived placement-readiness adjudication (READ-ONLY)")
    p("=" * 84)
    p(f"TOL={TOL} ft. Gate = G1 structure-side-trusted AND G2 single-corridor AND")
    p("G3 no-competing-terminus AND G4 print-mapping-certain  (the bore_log7 proof shape).")
    p(f"Trusted endpoints: {CLEAN_TABLE.name}   AP index: {AP_INDEX.name}\n")

    table = _confirmed_table()
    apidx = _ap_index()
    p(f"Confirmed PDF-derived endpoints (Target #33): {len(table)} -> "
      f"{[(s, int(sta), ap) for (s, sta, ap) in table]}\n")

    results = [adjudicate(stem, table, apidx) for stem in CANDIDATES]

    for r in results:
        role = "CONTROL (proven bore_log7->route_469)" if r["bore"] == "bore_log7" else "TARGET"
        p("-" * 84)
        p(f"[{r['bore']}]  ({role})")
        p(f"   prints={r['prints']}  station={r['station_span'][0]:.0f}-{r['station_span'][1]:.0f}  rows={r['rows']}")
        ss = r["structure_side"]
        p(f"   STRUCTURE SIDE: confirmed_hits={ss['confirmed_endpoint_hits']}  "
          f"-> AP-{ss['resolved_ap']}  tail={ss['tail_route']}  latlon={ss['latlon']}  ready={ss['geometry_ready']}")
        bs = r["bore_side"]
        p(f"   BORE SIDE: corridor_status={bs['corridor_status']}  corridors={bs['corridors']}")
        p(f"              named_AP_termini_near_END={bs['named_ap_termini_near_end']}")
        p(f"              competing_unnamed_termini={bs['competing_unnamed_termini_near_end']}")
        if bs["notes"]:
            p(f"              notes={bs['notes'][0][:140]}")
        g = r["gates"]
        p(f"   GATES: G1={g['G1_structure_side_trusted']}  G2={g['G2_single_corridor']}  "
          f"G3={g['G3_no_competing_terminus']}  G4={g['G4_print_mapping_certain']}")
        p(f"   => {r['verdict']}")
        if r["verdict"] != "PLACEMENT_READY":
            p(f"      blockers: {r['blockers']}")
            p(f"      missing artifact: {r.get('missing_artifact')}")
        p("")

    # --- assertions: control must pass, target must abstain (no-guessing guarantee) ---
    by = {r["bore"]: r for r in results}
    ctrl_ok = by["bore_log7"]["verdict"] == "PLACEMENT_READY" and \
        by["bore_log7"]["structure_side"]["tail_route"] == "route_469"
    tgt_abstain = by["bore_log57"]["verdict"] == "ABSTAIN"
    tgt_struct_ready = by["bore_log57"]["structure_side"]["geometry_ready"] is True

    p("-" * 84)
    p("SUMMARY")
    p("-" * 84)
    p(f"  CONTROL bore_log7 : {by['bore_log7']['verdict']} (re-derives route_469: "
      f"{by['bore_log7']['structure_side']['tail_route']}) -> control_ok={ctrl_ok}")
    p(f"  TARGET  bore_log57: {by['bore_log57']['verdict']}  structure_side_ready={tgt_struct_ready}  "
      f"blockers={by['bore_log57']['blockers']}")
    p("")
    p("  VERDICT: bore_log57 is NOT safely placeable. Structure side (AP-157 -> route_465, "
      "lat/lon) is clean & geometry-ready (Target #33 resolved the endpoint-side ambiguity), "
      "but the BORE-side drive-disambiguation is unresolved: its END (sta 413) sits within "
      "tol of BOTH AP-157 (sheet 8) and a sheet-13 matchline (sta 398), the bore spans two "
      "corridors, and its print mapping is flagged uncertain. Binding it to AP-157 over the "
      "sheet-13 corridor = guessing -> wrong-redline risk. ABSTAIN per DO-NOT-WIDEN.")
    p("  bore_log7 control unchanged (PLACEMENT_READY -> route_469); gate calibration confirmed.")

    verdict_json = {
        "schema_version": "target34-placement-readiness-1",
        "tol_ft": TOL,
        "confirmed_endpoints": [[s, sta, ap] for (s, sta, ap) in table],
        "results": results,
        "control_ok": ctrl_ok,
        "target_abstains": tgt_abstain,
        "target_structure_side_ready": tgt_struct_ready,
        "headline": ("bore_log57 ABSTAIN: structure side ready (AP-157->route_465), "
                     "bore->drive binding unresolved (multi_corridor + matchline@398 + "
                     "print_mapping_uncertain); .FS drive-decomposition sheet missing."),
    }
    (ROOT / "scripts" / "target34_bore_log57_placement_candidate.json").write_text(
        json.dumps(verdict_json, indent=2), encoding="utf-8")
    (ROOT / "scripts" / "target34_bore_log57_placement_candidate.out").write_text(
        "\n".join(OUT) + "\n", encoding="utf-8")
    print("\n".join(OUT))

    # hard self-assertions (probe fails loudly if the safety invariants break)
    assert ctrl_ok, "CONTROL REGRESSED: bore_log7 no longer PLACEMENT_READY->route_469"
    assert tgt_abstain, "TARGET UNSAFE: bore_log57 did not abstain"
    assert tgt_struct_ready, "structure side for bore_log57 should be geometry-ready"
    print("\nSELFTEST_OK (control passes, target abstains, structure side ready)")


if __name__ == "__main__":
    main()
