"""READ-ONLY Target #23 — remaining route_480-bucket proof sweep.

Closes out the 6 still-unproven route_480 logs that are NOT in the proven (bore_log7),
DROP (5/30/48/50/65), or main-chain (16/43) lanes:
    multi_drive_terminus_ambiguous : bore_log57
    no_run_terminus_match          : bore_log29, 31, 46, 47, 58

Question: can ANY become PROVEN from existing source evidence? If not, name the exact
missing artifact per log.

Three lanes, encoded deterministically in ONE probe (more rigorous than parallel agents):
  L1 bore facts   — prints, station min/max/span, rows, notes (from the real xlsx).
  L2 run/matchline— for the bore END station, ALL run termini within TOL on its print
                    sheets (uniqueness = the proof gate, exactly as bore_log7 was proven);
                    + matchline station-graph corridor context.
  L3 KMZ/route    — route_480-bucket membership; a KMZ binding is only reachable if L2
                    yields a UNIQUE named (AP) terminus (the bore_log7 mechanism).

A log is PROVABLE only if its END station has EXACTLY ONE named-AP run terminus within
TOL on a print sheet (the bore_log7 pattern). 0 -> no_run_terminus_match; >=2 -> ambiguous.

NO placement, NO engine/STATE change, NO flag, NO geometry. In-repo table + matchline
graph + read-only xlsx. Writes scripts/route480_remaining_proof_sweep.out.
"""
from __future__ import annotations

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
    os.environ.setdefault(k, "t23-sweep")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

from backend import main as M  # noqa: E402
from backend.app.core import pdf_ap_route_resolver as R  # noqa: E402
from backend.app.core import brenham_plan_sheet_graph as G  # noqa: E402

BORE = Path(r"C:\Users\Patrick\OneDrive\Attachments\Desktop\excel bore logs")
LOGS = ["bore_log57", "bore_log29", "bore_log31", "bore_log46", "bore_log47", "bore_log58"]
TOL = 15.0  # same terminus tolerance class used in Targets #10/#21

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
    notes = [str(r.get("notes") or "").strip() for r in rows if str(r.get("notes") or "").strip()]
    return {
        "rows": len(rows), "sheets": sheets, "stations": st,
        "smin": st[0] if st else None, "smax": st[-1] if st else None,
        "notes": notes[:3],
    }


def _termini_near(end_ft: float, sheets: List[int], tol: float):
    """All run-endpoint rows on the bore's print sheets within tol of the END station.
    Returns (named_ap_hits, all_hits)."""
    named, allh = [], []
    for (sheet, sta, kind, ap) in R.BRENHAM_PH5_RUN_ENDPOINTS:
        if sheet in sheets and abs(sta - end_ft) <= tol:
            allh.append((sheet, sta, kind, ap))
            if kind == "ap" and ap is not None:
                named.append((sheet, sta, kind, ap))
    return named, allh


def main() -> None:
    p("=" * 80)
    p("Target #23 — remaining route_480-bucket proof sweep (57, 29, 31, 46, 47, 58)")
    p("=" * 80)
    p(f"TOL={TOL} ft. PROVABLE gate = EXACTLY ONE named-AP run terminus within TOL on a")
    p("print sheet (the bore_log7 mechanism). 0 -> no_run_terminus_match; >=2 -> ambiguous.\n")

    table = []
    for stem in LOGS:
        fa = _facts(stem)
        if not fa or fa["smax"] is None:
            p(f"[{stem}] FACTS MISSING -> UNKNOWN_INSUFFICIENT (file/station absent)")
            table.append((stem, "BLOCKED", "facts_missing", "bore xlsx / station column"))
            continue
        end = fa["smax"]
        named, allh = _termini_near(end, fa["sheets"], TOL)

        # matchline-graph context (corridor membership + extent fit)
        ev = G.evaluate_bore_log(prints=fa["sheets"], station_min_ft=fa["smin"], station_max_ft=fa["smax"])

        p(f"[{stem}]  prints={fa['sheets']}  sta={fa['smin']:.0f}-{end:.0f} "
          f"(span {end-fa['smin']:.0f}, {fa['rows']} rows)")
        p(f"   L1 notes: {fa['notes'] if fa['notes'] else '(none)'}")
        p(f"   L2 run termini within {TOL:.0f} ft of END {end:.0f} on sheets {fa['sheets']}:")
        p(f"        all hits   = {allh if allh else 'NONE'}")
        p(f"        named-AP   = {named if named else 'NONE'}")
        p(f"   L2 matchline-graph: status={ev['status']} corridors={ev['corridors']} "
          f"extents={ev['corridor_extents']}")

        # Verdict — ADVERSARIAL gate: a unique named-AP hit is NOT enough. A competing
        # terminus within TOL (named OR unnamed matchline/splice), a multi-corridor span,
        # or a flagged-uncertain print mapping all make the END frame-ambiguous (the
        # Target #10 multi_drive_unknown finding; bore_log57 = AP-157 vs sheet-13 matchline).
        notes_blob = " ".join(fa["notes"]).lower()
        print_uncertain = "print mapping uncertain" in notes_blob
        competing = [h for h in allh if h not in named]  # unnamed termini co-located with END
        multi_corridor = ev["status"] == "multi_corridor_span"
        if len(named) == 1 and not competing and not multi_corridor and not print_uncertain:
            verdict = "PROVABLE_CANDIDATE"
            artifact = f"none — unique unambiguous anchor {named[0]} (verify vs ground truth)"
        elif len(named) >= 1 and (competing or multi_corridor or len(named) >= 2):
            verdict = "BLOCKED:multi_drive_terminus_ambiguous"
            why = []
            if len(named) >= 2:
                why.append(f"{len(named)} named APs")
            if competing:
                why.append(f"competing unnamed termini {[(h[0], h[1], h[2]) for h in competing]}")
            if multi_corridor:
                why.append("END spans 2 corridors")
            if print_uncertain:
                why.append("print mapping flagged uncertain")
            artifact = (".FS drive-decomposition sheet (which drive/terminus this bore ends at; "
                        + "; ".join(why) + ")")
        elif len(allh) >= 1:
            # only unnamed termini (matchline/splice/flowerpot) -> not a backbone-AP proof
            verdict = "BLOCKED:non_ap_terminus_only"
            artifact = (".FS drive-decomposition OR a terminus-structure id on the bore log "
                        f"(end coincides only with unnamed {sorted({h[2] for h in allh})})")
        else:
            verdict = "BLOCKED:no_run_terminus_match"
            artifact = (".FS drive-decomposition sheet (continuous multi-drive bore; END "
                        "station hits no single run terminus) OR a bore-log terminus field")
        p(f"   => {verdict}")
        p(f"      missing artifact: {artifact}\n")
        table.append((stem, verdict, ev["status"], artifact))

    # Summary table
    p("-" * 80)
    p("SUMMARY (deterministic verdict table)")
    p("-" * 80)
    p(f"  {'log':<12} {'verdict':<42} {'graph_status'}")
    for stem, verdict, gstatus, _art in table:
        p(f"  {stem:<12} {verdict:<42} {gstatus}")
    provable = [t for t in table if t[1] == "PROVABLE_CANDIDATE"]
    p(f"\n  PROVABLE candidates: {len(provable)} -> {[t[0] for t in provable] or 'NONE'}")
    p(f"  BLOCKED            : {len(table) - len(provable)} / {len(table)}")
    p("\n  Cross-check: Targets #8/#9/#10 already proved no bore↔drive/AP binding key exists")
    p("  in any provided file (xlsx has no AP/terminus column; the .FS Fiber-Schematic /")
    p("  drive-decomposition sheet referenced by the Fieldwire register is ABSENT from the")
    p("  3 PDFs). This sweep re-confirms that at the per-log terminus level.")

    out_path = ROOT / "scripts" / "route480_remaining_proof_sweep.out"
    out_path.write_text("\n".join(OUT) + "\n", encoding="utf-8")
    print("\n".join(OUT))
    print(f"\n[wrote {out_path}]")


if __name__ == "__main__":
    main()
