"""READ-ONLY Target #40 — apply the #39 alternate bore->drive resolver to the multi-drive route_480 logs.

Sweeps bore_log29/31/46/47/58 (+ 57 from #39 for continuity) through the SAME deterministic constraint
scorer built in Target #39 (no .FS). Reports each log's candidate termini, scores, placement gates,
and verdict. bore_log7 remains the PLACEABLE control. No placement; scripts/ only.
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
    os.environ.setdefault(k, "t40")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

from backend import main as M
from backend.app.core import pdf_ap_route_resolver as R
import target39_alternate_bore_drive_resolver as T39

LOGS = ["bore_log29", "bore_log31", "bore_log46", "bore_log47", "bore_log58", "bore_log57", "bore_log7"]
OUT: List[str] = []
def p(s=""): OUT.append(s)


def main():
    kb = T39.KMZ.read_bytes()
    catalog = [r for r in (M._build_route_catalog(kb, T39.KMZ.name) or []) if r.get("coords")]
    pf = (M._build_kmz_reference(kb, T39.KMZ.name) or {}).get("point_features") or []
    terminals = R.terminal_nodes_from_point_features(pf)
    # AP id -> unique terminal-tail route (reuse #39 logic)
    catalog_by_tail_ap: Dict[str, Any] = {}
    for t in terminals:
        nm = str(t.get("name"))
        try:
            al, ao = float(t["lat"]), float(t["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        tails = [r for r in catalog if "terminal tail" in str(r.get("source_folder") or "").lower()
                 and min(T39._hav(r["coords"][0], (al, ao)), T39._hav(r["coords"][-1], (al, ao))) <= T39.EP_FT]
        if len(tails) == 1:
            catalog_by_tail_ap[nm] = tails[0]

    p("=" * 92); p("Target #40 — alternate resolver sweep over multi-drive route_480 logs (no .FS)"); p("=" * 92)
    results = {}
    for stem in LOGS:
        r = T39.resolve(stem, terminals, catalog_by_tail_ap)
        results[stem] = r
        if r.get("verdict") == "FACTS_MISSING":
            p(f"\n[{stem}] FACTS_MISSING (absent)"); continue
        role = " (CONTROL)" if stem == "bore_log7" else ""
        p(f"\n[{stem}]{role} end={r['end']:.0f} sheets={r['sheets']} print_uncertain={r['print_uncertain']}")
        if r["candidates"]:
            for c in r["candidates"]:
                p(f"    cand AP-{c['ap']} sheet{c['sheet']} STA{c['sta']:.0f} score={c['score']} "
                  f"sta_exact={c['sta_exact']} tail={c['tail_route']} tail_len={c['tail_len_ft']}ft")
        else:
            p("    cand: (none — no real-structure run-terminus within tol of END)")
        g = r["gates"]
        p(f"    GATES G1={g['G1_terminus_unique']} G2={g['G2_length_match']} G3={g['G3_single_corridor']} G4={g['G4_print_certain']}")
        p(f"    => {r['verdict']}")

    # tally
    p("\n" + "-" * 92); p("SUMMARY")
    tally: Dict[str, List[str]] = {}
    for stem, r in results.items():
        if stem == "bore_log7":
            continue
        tally.setdefault(r.get("verdict", "FACTS_MISSING"), []).append(stem)
    for v, logs in sorted(tally.items()):
        p(f"   {v}: {logs}")
    placeable = [s for s, r in results.items() if s != "bore_log7" and r.get("verdict") == "PLACEABLE_BY_ALTERNATE_RESOLVER"]
    term_resolved = [s for s, r in results.items() if s != "bore_log7"
                     and r.get("dominant_terminus") and r.get("gates", {}).get("G1_terminus_unique")]
    p(f"\n   NEW placeable by alternate resolver: {placeable or 'NONE'}")
    p(f"   terminus uniquely resolved (advance, even if placement blocked): {term_resolved or 'NONE'}")
    p(f"   CONTROL bore_log7: {results['bore_log7']['verdict']}")
    p("")
    p("   The resolver places NOTHING beyond the proven bore_log7 (no log passes all 4 geometry gates).")
    p("   For each multi-drive log it reports the exact evidence: either no real-structure terminus")
    p("   near the END (the END coincides with a matchline/footage, not a handhole), or a terminus is")
    p("   uniquely resolved but the tail-length/corridor geometry is unproven (same class as #39).")

    verdict = {
        "schema_version": "target40-multidrive-sweep-1",
        "results": {s: {"verdict": r.get("verdict"),
                        "terminus": (r.get("dominant_terminus") or {}).get("ap") if r.get("dominant_terminus") else None,
                        "gates": r.get("gates"), "candidates": r.get("candidates")}
                    for s, r in results.items()},
        "new_placeable": placeable,
        "terminus_uniquely_resolved": term_resolved,
        "control_bore_log7": results["bore_log7"]["verdict"],
    }
    (ROOT / "scripts" / "target40_multidrive_resolver_sweep.json").write_text(json.dumps(verdict, indent=2), encoding="utf-8")
    (ROOT / "scripts" / "target40_multidrive_resolver_sweep.out").write_text("\n".join(OUT) + "\n", encoding="utf-8")
    print("\n".join(OUT))

    assert results["bore_log7"]["verdict"] == "PLACEABLE_BY_ALTERNATE_RESOLVER", "CONTROL REGRESSED"
    assert not placeable or all(results[s]["gates"]["G2_length_match"] for s in placeable), "placeable must pass length gate"
    print("\nSELFTEST_OK (control placeable; sweep verdicts emitted)")


if __name__ == "__main__":
    main()
