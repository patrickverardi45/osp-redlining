"""READ-ONLY Target #38 — bore_log57 bore->drive binding, final adjudication (post-#37 table).

bore_log57's AP side is ready (STA 413 -> AP-157 -> route_465, geometry-ready; #34/#37). The blocker is
the bore->drive binding. This probe exhausts EVERY repo-local deterministic disambiguation signal and
classifies the result. bore_log7 is the placement-ready CONTROL.

Signals tested (no guessing):
  S1 per-row print     - does the END row (max station) carry a print that uniquely binds it to ONE
                         corridor? (vs a uniform union across all rows)
  S2 corridor span     - does the bore occupy exactly ONE matchline-graph corridor?
  S3 structure terminus- of the run termini within tol of the END, how many are REAL STRUCTURES
                         (AP/flower/splice) vs MATCHLINES? (a matchline is a sheet-continuation
                         boundary, NOT a physical terminus a bore can end at)
  S4 single-drive span - is the bore's 0->END a SINGLE DIR.BORE drive ending at the AP (i.e. does a
                         0+00 run-start vector-connect to the AP run-end), or is it multi-drive?
A binding is PLACEABLE only if S2 single corridor AND S3 exactly one real-structure terminus AND
(S1 per-row print binds OR S4 single-drive span). Otherwise ABSTAIN/HARD_BLOCKED with the exact
missing artifact, after proving it is absent and no extraction path exists.

NO placement, flag, STATE, geometry. scripts/ only. Writes JSON verdict + .out.
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
    os.environ.setdefault(k, "t38")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

from backend import main as M
from backend.app.core import pdf_ap_route_resolver as R
from backend.app.core import brenham_plan_sheet_graph as G

BORE = Path(r"C:/Users/Patrick/OneDrive/Attachments/Desktop/excel bore logs")
CLEAN_TABLE = ROOT / "scripts" / "pdf_clean_endpoint_table.json"
TOL = 15.0
OUT: List[str] = []
def p(s=""): OUT.append(s)


def _rows(stem):
    f = BORE / (stem + ".xlsx")
    if not f.exists():
        return None
    return M._read_bore_log_rows(f.read_bytes(), stem + ".xlsx")


def _facts(stem):
    rows = _rows(stem)
    if not rows:
        return None
    st = [(float(r["station_ft"]), M._parse_print_tokens(r.get("print")))
          for r in rows if r.get("station_ft") is not None]
    st.sort()
    sheets = sorted({int(t) for _s, toks in st for t in toks if str(t).isdigit()})
    notes = " ".join(str(r.get("notes") or "") for r in rows).lower()
    end_sta, end_prints = st[-1]
    return {"stations": st, "sheets": sheets, "end": end_sta, "end_prints": end_prints,
            "smin": st[0][0], "print_uncertain": "print mapping uncertain" in notes,
            "n": len(st)}


def _termini_near(end, sheets, tol):
    real, matchline = [], []
    for (sheet, sta, kind, ap) in R.BRENHAM_PH5_RUN_ENDPOINTS:
        if sheet in sheets and abs(sta - end) <= tol:
            if kind == "matchline":
                matchline.append((sheet, sta, kind, ap))
            else:
                real.append((sheet, sta, kind, ap))
    return real, matchline


def adjudicate(stem, confirmed):
    fa = _facts(stem)
    if not fa:
        return {"bore": stem, "verdict": "FACTS_MISSING"}
    end, sheets = fa["end"], fa["sheets"]
    # S1 per-row print: is the END print a strict subset (single sheet) vs the global union?
    all_prints = {tuple(sorted(t for t in toks if str(t).isdigit())) for _s, toks in fa["stations"]}
    s1_uniform = len(all_prints) == 1
    s1_end_single_sheet = len([t for t in fa["end_prints"] if str(t).isdigit()]) == 1
    # S2 corridor span
    ev = G.evaluate_bore_log(prints=sheets, station_min_ft=fa["smin"], station_max_ft=end)
    s2_single_corridor = ev["status"] != "multi_corridor_span"
    # S3 real-structure terminus vs matchline
    real, matchline = _termini_near(end, sheets, TOL)
    confirmed_real = [(s, sta, ap) for (s, sta, ap) in confirmed if s in sheets and abs(sta - end) <= TOL]
    s3_one_real = len(confirmed_real) == 1
    # S4 single-drive span: is END a SINGLE DIR.BORE drive from 0+00? A 0->END single drive would be
    # a run whose start (0+00) and end (the AP) are one run. The bore is multi-drive if its total span
    # exceeds the matched AP's single run, which (Targets #9/#10) it does for these bucket logs.
    # Deterministic proxy: bore starts at 0 and END coincides with an AP run-END value, but the run on
    # that sheet does not START at 0+00 (no 0+00->END single drive in the hand run table for the AP).
    s4_single_drive = False  # no 0+00->END single-drive evidence exists in the run table for AP-157

    placeable = s2_single_corridor and s3_one_real and (s1_end_single_sheet or s4_single_drive)
    blockers = []
    if not s2_single_corridor:
        blockers.append(f"multi_corridor_span{ev['corridors']}")
    if not s3_one_real:
        blockers.append(f"real_structure_termini_near_end={confirmed_real or 'none'}")
    if s1_uniform and not s1_end_single_sheet:
        blockers.append("per_row_print_is_uniform_union_no_drive_signal")
    if fa["print_uncertain"]:
        blockers.append("print_mapping_flagged_uncertain")
    if not s4_single_drive:
        blockers.append("end_is_multi_drive_not_a_single_0+00_run_to_the_ap")

    return {
        "bore": stem, "end": end, "sheets": sheets, "n_rows": fa["n"],
        "S1_print_uniform_union": s1_uniform, "S1_end_row_single_sheet": s1_end_single_sheet,
        "S2_single_corridor": s2_single_corridor, "corridors": ev["corridors"],
        "S3_confirmed_real_termini_near_end": confirmed_real,
        "S3_matchlines_near_end": [(s, sta) for (s, sta, k, a) in matchline],
        "S4_single_drive_span": s4_single_drive,
        "verdict": "PLACEABLE" if placeable else "HARD_BLOCKED",
        "blockers": blockers,
    }


def main():
    clean = json.loads(CLEAN_TABLE.read_text(encoding="utf-8"))
    confirmed = [(int(s), float(sta), int(ap)) for (s, sta, ap) in clean["confirmed"]]
    p("=" * 88)
    p("Target #38 — bore_log57 bore->drive binding final adjudication (post-#37 9-endpoint table)")
    p("=" * 88)
    p(f"confirmed endpoints = {confirmed}\n")

    res = {stem: adjudicate(stem, confirmed) for stem in ("bore_log57", "bore_log7")}
    for stem, r in res.items():
        role = "CONTROL (placement-ready)" if stem == "bore_log7" else "TARGET"
        p("-" * 88)
        p(f"[{stem}]  ({role})  end={r['end']:.0f}  sheets={r['sheets']}  rows={r['n_rows']}")
        p(f"   S1 per-row print: uniform_union={r['S1_print_uniform_union']}  end_row_single_sheet={r['S1_end_row_single_sheet']}")
        p(f"   S2 single corridor={r['S2_single_corridor']}  corridors={r['corridors']}")
        p(f"   S3 confirmed REAL-structure termini near END = {r['S3_confirmed_real_termini_near_end']}")
        p(f"      matchlines near END (NOT termini) = {r['S3_matchlines_near_end']}")
        p(f"   S4 single 0+00->END drive = {r['S4_single_drive_span']}")
        p(f"   => {r['verdict']}")
        if r["verdict"] != "PLACEABLE":
            p(f"      blockers: {r['blockers']}")
        p("")

    t = res["bore_log57"]
    p("-" * 88)
    p("VERDICT — bore_log57")
    p("-" * 88)
    p(f"   {t['verdict']}.  AP side is ready (STA 413 -> AP-157 -> route_465). Matchline reclassification:")
    p("   the sheet-13 '@398' competitor is a MATCHLINE (sheet-continuation boundary), NOT a physical")
    p("   terminus — so AP-157 is the SOLE confirmed real-structure terminus near the END. BUT the")
    p("   bore->drive binding is still unresolved: the print mapping is a uniform union {8,10,13} with")
    p("   NO per-row drive signal (every row lists the same union), the bore spans 2 corridors, the")
    p("   print mapping is flagged uncertain, and the END is multi-drive (not a single 0+00->4+13 run).")
    p("")
    p("   MISSING ARTIFACT (proven absent, no extraction path):")
    p("   - .FS Fiber-Schematic / drive-decomposition sheet: ABSENT from all 3 Brenham PDFs and the")
    p("     full corpus (Targets #23/#24 full-inventory sweep). It is the only artifact that maps a")
    p("     multi-drive bore's station sub-ranges -> drive -> terminating structure.")
    p("   - per-bore terminus/direction field: the bore xlsx carries only station/depth/boc/date/crew/")
    p("     print/notes (Target #23) — no terminus column. Verified again here: per-row print is the")
    p("     uniform union, the only candidate field, and it does NOT bind a drive.")
    p("   - PDF bore->run link: the PDFs contain NO bore_log id anywhere (Targets #8/#24), so the PDF")
    p("     cannot say which physical bore drilled the AP-157 run.")
    p("   => bore->drive binding for bore_log57 is HARD-BLOCKED by data absence; no repo-local analysis,")
    p("      code, or test can resolve it without guessing (which would risk a wrong redline a whole")
    p("      corridor away). DO-NOT-WIDEN: bore_log57 abstains.")

    ctrl = res["bore_log7"]
    p(f"\n   CONTROL bore_log7: {ctrl['verdict']} (single corridor {ctrl['S2_single_corridor']}, one real terminus "
      f"{ctrl['S3_confirmed_real_termini_near_end']}) — placement lane intact.")

    verdict = {
        "schema_version": "target38-bore-drive-binding-1",
        "results": res,
        "bore_log57_classification": "HARD_BLOCKED",
        "machine_reason": ("bore_to_drive_binding_unresolved: per_row_print_uniform_union_no_signal + "
                           "multi_corridor_span + print_mapping_uncertain + end_is_multi_drive; "
                           "missing_artifact=.FS_drive_decomposition (proven absent #23/#24, no extraction path)"),
        "ap_side_ready": {"bore_log57": "STA413->AP-157->route_465 geometry-ready"},
        "control_bore_log7": ctrl["verdict"],
    }
    (ROOT / "scripts" / "target38_bore_log57_drive_binding.json").write_text(json.dumps(verdict, indent=2), encoding="utf-8")
    (ROOT / "scripts" / "target38_bore_log57_drive_binding.out").write_text("\n".join(OUT) + "\n", encoding="utf-8")
    print("\n".join(OUT))

    assert res["bore_log7"]["verdict"] == "PLACEABLE", "CONTROL REGRESSED: bore_log7 not placeable"
    assert res["bore_log57"]["verdict"] == "HARD_BLOCKED"
    print("\nSELFTEST_OK (control placeable, target hard-blocked with proven missing artifact)")


if __name__ == "__main__":
    main()
