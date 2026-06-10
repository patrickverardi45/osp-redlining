r"""M8.6 -- station-equation ownership proof over the REAL Brenham plan.

Proof-only (no engine wiring, no flag, no placement): extracts every reset
annotation ``STA X=0+00`` per sheet, binds each to its adjacent structure label,
parses ``HH - HH = N'`` distance notes, and proves:

  1. NO COLLAPSE: every reset annotation is its own StructureOrigin (distinct
     parent stations never merge on the shared local ``0+00`` side);
  2. the screenshot pattern on its real sheet: ``STA 2+72=0+00`` and
     ``STA 2+22=0+00`` are two installer-HH structures; parent delta 50 ft is
     EXACTLY corroborated by the sheet's ``HH - HH = 50'`` note; a bore interval
     ``2+22 TO 2+72`` is 50 ft of footage math bounded by those two origins.

Exit nonzero if the spotlight pattern fails (honest gate -- nothing is forced).

Run (repo root): $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_station_equation_ownership
"""
from __future__ import annotations

import json
import os
from typing import Dict, List

from truelinev2.config import Settings, _REPO_ROOT
from truelinev2.extract.registry import select_dialect
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.proof.run_brenham_corpus import PDF
from truelinev2.proof.station_equation_ownership import (
    StructureOrigin,
    bore_interval_footage,
    corroborate_pairs,
    extract_reset_origins,
    origins_bounding_interval,
    parse_hh_distances,
    prove_no_collapse,
)

OUT_JSON = _REPO_ROOT / "data" / "outputs" / "station_equation_ownership.json"
OUT_MD = _REPO_ROOT / "data" / "outputs" / "station_equation_ownership.md"

# The screenshot pattern (Patrick, 2026-06-10): two installer-HH reset origins
# 50 ft apart with an HH-HH note; bore interval 2+22 TO 2+72 = 50 ft.
SPOT_PARENTS = (222.0, 272.0)
SPOT_BORE = ("2+22", "2+72")
SPOT_HH_FT = 50.0


def main() -> int:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    if not os.path.isfile(PDF):
        print("[m8.6] STOP: plan PDF missing")
        return 2
    settings = Settings.for_proof()
    plan = PlanPdf(PDF)
    dialect = select_dialect(plan)
    offset = dialect.calibrate(plan, settings.sheet_offset)

    all_origins: List[StructureOrigin] = []
    hh_notes_by_sheet: Dict[int, List[float]] = {}
    for sheet in range(1, plan.page_count - offset + 1):
        lines = plan.lines(sheet, offset)
        all_origins.extend(extract_reset_origins(lines, sheet))
        notes = parse_hh_distances(" ".join(lines))
        if notes:
            hh_notes_by_sheet[sheet] = notes
    plan.close()

    no_collapse = prove_no_collapse(all_origins)
    bound = sum(1 for o in all_origins if o.structure_type)

    # spotlight: find the sheet carrying BOTH 2+22=0+00 and 2+72=0+00
    spot_sheet = None
    for o in all_origins:
        if o.parent_station_ft == SPOT_PARENTS[0]:
            if any(x.sheet == o.sheet and x.parent_station_ft == SPOT_PARENTS[1]
                   for x in all_origins):
                spot_sheet = o.sheet
                break
    spotlight: Dict[str, object] = {"sheet": spot_sheet}
    if spot_sheet is not None:
        spot_origins = [o for o in all_origins if o.sheet == spot_sheet
                        and o.parent_station_ft in SPOT_PARENTS]
        notes = hh_notes_by_sheet.get(spot_sheet, [])
        pairs = corroborate_pairs(spot_origins, notes)
        interval = bore_interval_footage(*SPOT_BORE)
        bounding = origins_bounding_interval(all_origins, SPOT_PARENTS[0], SPOT_PARENTS[1])
        spotlight.update({
            "origins": [o.to_dict() for o in spot_origins],
            "hh_notes_on_sheet": notes,
            "pair_corroboration": pairs,
            "bore_interval": f"{SPOT_BORE[0]} TO {SPOT_BORE[1]}",
            "bore_interval_ft": interval,
            "interval_bounded_by_two_origins": bool(bounding),
            "not_collapsed": prove_no_collapse(spot_origins),
        })
        ok = (len(spot_origins) == 2
              and spotlight["not_collapsed"]["no_collapse"]
              and all(o.structure_type == "installer_hh" for o in spot_origins)
              and interval == SPOT_HH_FT
              and any(p["parent_delta_ft"] == SPOT_HH_FT and p["hh_note_exact_match"]
                      for p in pairs)
              and bool(bounding))
    else:
        ok = False
    spotlight["verdict"] = "PASS" if ok else "FAILURE"

    report = {
        "milestone": "truelinev2 M8.6 -- station-equation ownership / frame-origin binding (proof-only)",
        "doctrine": ("STA X=0+00 is ONE physical structure with TWO station identities "
                     "(parent station + local origin); multiple =0+00 annotations are "
                     "DISTINCT origins; 0+00 is never globally unique; HH-HH notes and "
                     "bore-interval footage math are corroborating evidence; a shared "
                     "structure may be an INTERIOR run boundary, not a final terminus."),
        "plan_wide": {
            "reset_origins": len(all_origins),
            "structure_bound": bound,
            "sheets_with_hh_notes": sorted(hh_notes_by_sheet),
            "no_collapse": no_collapse,
            "per_sheet_counts": {s: sum(1 for o in all_origins if o.sheet == s)
                                 for s in sorted({o.sheet for o in all_origins})},
        },
        "spotlight": spotlight,
        "origins": [o.to_dict() for o in all_origins],
    }
    OUT_JSON.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    L = ["# M8.6 -- station-equation ownership proof", "",
         f"- plan-wide reset origins: {len(all_origins)} "
         f"(structure-bound: {bound}); no-collapse: {no_collapse}",
         f"- spotlight sheet {spot_sheet}: origins "
         f"{[o.origin_id for o in all_origins if o.sheet == spot_sheet and o.parent_station_ft in SPOT_PARENTS]}",
         f"- spotlight detail: {json.dumps(spotlight, default=str)[:1200]}", "",
         f"## VERDICT: {spotlight['verdict']}"]
    OUT_MD.write_text("\n".join(L) + "\n", encoding="utf-8")

    print(f"[m8.6] plan-wide reset origins={len(all_origins)} structure_bound={bound} "
          f"no_collapse={no_collapse['no_collapse']}")
    print(f"[m8.6] spotlight sheet={spot_sheet} "
          f"origins={[o.to_dict()['parent_station'] for o in all_origins if o.sheet == spot_sheet and o.parent_station_ft in SPOT_PARENTS] if spot_sheet else []} "
          f"hh_notes={hh_notes_by_sheet.get(spot_sheet, []) if spot_sheet else []}")
    print(f"[m8.6] VERDICT: {spotlight['verdict']}")
    print(f"[m8.6] report -> {OUT_MD}")
    return 0 if spotlight["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
