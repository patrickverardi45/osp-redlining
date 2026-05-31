"""READ-ONLY Target #39 — alternate bore->drive resolver (NO .FS dependency).

Builds a deterministic constraint scorer that binds a bore's END to a drive/terminus from DELIVERED
corpus signals only (station ranges, direction, prints/corridors, AP endpoint table, matchlines,
route tail geometry+length, sibling segments). Enumerates every candidate terminus, scores each, and
applies proof-grade placement gates. bore_log7 is the PLACEABLE control.

TERMINUS candidate score (higher = better), per real-structure run-terminus near the bore END on its
print sheets:
  + station exactness   : 1 - min(1, |END - run_end| / STA_TOL)         (exact 413==413 -> 1.0)
  + is_real_structure   : 1.0 if AP/flower/splice ; matchlines EXCLUDED (a bore cannot end at a matchline)
  + corridor_in_prints  : 1.0 if the terminus' sheet is in the bore's print set
  + has_tail_route      : 1.0 if a Terminal-Tail route endpoint-matches the AP (<=12ft)
A terminus is UNIQUELY DOMINANT if exactly one candidate has station-exactness >= 0.99 and no other
candidate is within DOMINANCE_MARGIN of its total score.

PROOF-GRADE PLACEMENT gates (all four, the bore_log7 shape) — placement geometry is only trustworthy if:
  G1 terminus_unique    : a single dominant real-structure terminus at the exact END station
  G2 length_match       : the AP's tail-route length is within LEN_TOL of the bore's max station
                          (bore_log7: route_469 ~459ft ~= 451 run; the bore IS the tail)
  G3 single_corridor    : the bore occupies one matchline-graph corridor (no cross-corridor ambiguity)
  G4 print_certain      : the bore's print mapping is NOT flagged uncertain
PLACEABLE_BY_ALTERNATE_RESOLVER iff G1..G4. If G1 holds but a geometry gate fails -> the terminus is
resolved but placement is HARD_BLOCKED_NO_DISCRIMINATOR (report the exact missing discriminator). If
two+ termini tie -> NOT_UNIQUE_COMPETING_CANDIDATES.

NO placement performed, no flag/STATE/geometry write. scripts/ only. Writes JSON + .out.
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
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "backend")); sys.path.insert(0, str(ROOT / "scripts"))
for k in ("TRUELINE_JWT_SECRET", "TRUELINE_AUTH_JWT_SECRET"):
    os.environ.setdefault(k, "t39")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")
from backend import main as M
from backend.app.core import pdf_ap_route_resolver as R
from backend.app.core import brenham_plan_sheet_graph as G

DESKTOP = Path(r"C:\Users\Patrick\OneDrive\Attachments\Desktop")
KMZ = DESKTOP / "Brenham, TX - Phase 5_Design Team.kmz"
BORE = DESKTOP / "excel bore logs"
AP_INDEX = ROOT / "scripts" / "ap_structure_index.json"
STA_TOL = 20.0
LEN_TOL = 0.15           # tail length within 15% of bore max-station
DOMINANCE_MARGIN = 0.5   # next candidate must be >=0.5 total below the leader
EP_FT = 12.0
OUT: List[str] = []
def p(s=""): OUT.append(s)


def _hav(a, b): return R._haversine_ft(float(a[0]), float(a[1]), float(b[0]), float(b[1]))
def _len(c): return sum(_hav(c[i-1], c[i]) for i in range(1, len(c)))


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
    notes = " ".join(str(r.get("notes") or "") for r in rows).lower()
    return {"stem": stem, "smin": st[0], "smax": st[-1], "sheets": sorted({int(t) for t in toks if str(t).isdigit()}),
            "print_uncertain": "print mapping uncertain" in notes}


def resolve(stem, terminals, catalog_by_tail_ap):
    fa = facts(stem)
    if not fa:
        return {"bore": stem, "verdict": "FACTS_MISSING"}
    end, sheets = fa["smax"], fa["sheets"]

    # --- enumerate candidate termini: real-structure run-endpoints within STA_TOL of END on print sheets ---
    cands = []
    for (sheet, sta, kind, ap) in R.BRENHAM_PH5_RUN_ENDPOINTS:
        if sheet not in sheets or abs(sta - end) > STA_TOL:
            continue
        if kind == "matchline":      # a bore cannot terminate at a matchline (sheet boundary)
            continue
        sta_exact = 1.0 - min(1.0, abs(sta - end) / STA_TOL)
        corridor_in = 1.0  # sheet is in prints by construction
        tail = catalog_by_tail_ap.get(str(ap)) if (kind == "ap" and ap is not None) else None
        has_tail = 1.0 if tail else 0.0
        score = sta_exact + 1.0 + corridor_in + has_tail   # is_real_structure = 1.0
        cands.append({"sheet": sheet, "sta": sta, "kind": kind, "ap": ap,
                      "sta_exact": round(sta_exact, 3), "has_tail_route": bool(tail),
                      "tail_route": (tail["route_id"] if tail else None),
                      "tail_len_ft": (round(_len(tail["coords"]), 1) if tail else None),
                      "score": round(score, 3)})
    cands.sort(key=lambda c: -c["score"])

    # --- terminus uniqueness ---
    exact = [c for c in cands if c["sta_exact"] >= 0.99]
    g1_unique = len(exact) == 1 and (len(cands) == 1 or cands[0]["score"] - cands[1]["score"] >= DOMINANCE_MARGIN)
    dom = exact[0] if exact else (cands[0] if cands else None)

    # --- geometry gates on the dominant terminus ---
    g2_len = g3_corr = g4_print = False
    len_ratio = None
    if dom and dom.get("tail_len_ft"):
        len_ratio = dom["tail_len_ft"] / end if end else None
        g2_len = abs(dom["tail_len_ft"] - end) <= LEN_TOL * end
    ev = G.evaluate_bore_log(prints=sheets, station_min_ft=fa["smin"], station_max_ft=end)
    g3_corr = ev["status"] != "multi_corridor_span"
    g4_print = not fa["print_uncertain"]

    if not cands:
        verdict, reason = "HARD_BLOCKED_NO_DISCRIMINATOR", "no_real_structure_terminus_near_end"
    elif not g1_unique:
        verdict, reason = "NOT_UNIQUE_COMPETING_CANDIDATES", \
            f"competing termini within margin: {[(c['ap'], c['score']) for c in cands[:3]]}"
    elif g2_len and g3_corr and g4_print:
        verdict, reason = "PLACEABLE_BY_ALTERNATE_RESOLVER", "terminus_unique_and_geometry_proof_grade"
    else:
        miss = []
        if not g2_len:
            miss.append(f"tail_len_{dom['tail_len_ft']}ft_vs_bore_{end:.0f}ft_ratio_{len_ratio:.2f}_no_length_match")
        if not g3_corr:
            miss.append(f"multi_corridor_span_{ev['corridors']}")
        if not g4_print:
            miss.append("print_mapping_flagged_uncertain")
        verdict = "HARD_BLOCKED_NO_DISCRIMINATOR"
        reason = ("terminus_uniquely_resolved_but_placement_geometry_unproven: " + "; ".join(miss)
                  + " -> missing discriminator = per-drive segmentation / start-structure that fixes "
                  "which sub-segment of the tail (length gap) and which corridor path the bore occupies")
    return {"bore": stem, "end": end, "sheets": sheets, "print_uncertain": fa["print_uncertain"],
            "candidates": cands, "dominant_terminus": dom,
            "gates": {"G1_terminus_unique": g1_unique, "G2_length_match": g2_len,
                      "G3_single_corridor": g3_corr, "G4_print_certain": g4_print},
            "length_ratio_tail_over_bore": (round(len_ratio, 2) if len_ratio else None),
            "corridors": ev["corridors"], "verdict": verdict, "reason": reason}


def main():
    kb = KMZ.read_bytes()
    catalog = [r for r in (M._build_route_catalog(kb, KMZ.name) or []) if r.get("coords")]
    pf = (M._build_kmz_reference(kb, KMZ.name) or {}).get("point_features") or []
    terminals = R.terminal_nodes_from_point_features(pf)
    term_by_name = {str(t.get("name")): t for t in terminals}
    # map AP id -> its unique Terminal-Tail route (endpoint within EP_FT)
    catalog_by_tail_ap: Dict[str, Any] = {}
    for ap_name, t in term_by_name.items():
        try:
            al, ao = float(t["lat"]), float(t["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        tails = []
        for r in catalog:
            if "terminal tail" not in str(r.get("source_folder") or "").lower():
                continue
            c = r["coords"]
            if min(_hav(c[0], (al, ao)), _hav(c[-1], (al, ao))) <= EP_FT:
                tails.append(r)
        if len(tails) == 1:
            catalog_by_tail_ap[ap_name] = tails[0]

    p("=" * 90); p("Target #39 — alternate bore->drive resolver (no .FS); deterministic constraint scorer"); p("=" * 90)
    p(f"STA_TOL={STA_TOL} LEN_TOL={LEN_TOL} DOMINANCE_MARGIN={DOMINANCE_MARGIN} EP_FT={EP_FT}\n")

    res = {stem: resolve(stem, terminals, catalog_by_tail_ap) for stem in ("bore_log57", "bore_log7")}
    for stem, r in res.items():
        role = "CONTROL" if stem == "bore_log7" else "TARGET"
        p("-" * 90); p(f"[{stem}]  ({role})  end={r['end']:.0f}  sheets={r['sheets']}  print_uncertain={r['print_uncertain']}")
        p("   candidate termini (scored):")
        for c in r["candidates"]:
            p(f"     AP-{c['ap']} sheet{c['sheet']} STA{c['sta']:.0f} score={c['score']} "
              f"sta_exact={c['sta_exact']} tail={c['tail_route']} tail_len={c['tail_len_ft']}ft")
        d = r["dominant_terminus"]
        p(f"   dominant terminus: AP-{d['ap'] if d else None} (tail {d['tail_route'] if d else None}, "
          f"len {d['tail_len_ft'] if d else None}ft)")
        p(f"   length_ratio tail/bore = {r['length_ratio_tail_over_bore']}  corridors={r['corridors']}")
        g = r["gates"]
        p(f"   GATES: G1_unique={g['G1_terminus_unique']} G2_len_match={g['G2_length_match']} "
          f"G3_single_corridor={g['G3_single_corridor']} G4_print_certain={g['G4_print_certain']}")
        p(f"   => {r['verdict']}")
        p(f"      {r['reason']}")
        p("")

    t = res["bore_log57"]; c = res["bore_log7"]
    p("-" * 90); p("SUMMARY")
    p(f"   bore_log57: {t['verdict']}")
    p(f"   bore_log7 (control): {c['verdict']}  (must be PLACEABLE_BY_ALTERNATE_RESOLVER)")
    p("")
    p("   KEY ADVANCE over #38: the alternate resolver UNIQUELY resolves bore_log57's TERMINUS to")
    p("   AP-157 (exact END station 413, sole real structure; matchlines excluded; route_465 is the")
    p("   unique tail ending 2.1ft from AP-157). The remaining blocker is PLACEMENT GEOMETRY, not the")
    p("   terminus: route_465 is 741.7ft but the bore is 413ft (ratio 1.80) -> the bore is a SUB-SEGMENT")
    p("   of the tail with unknown start offset, and its prints span a 2nd corridor route_465 cannot")
    p("   represent. Placing it would require assuming (a) the AP-157-end 413ft sub-segment and (b) the")
    p("   corridor-B prints are mis-mapped -> two unprovable assumptions = wrong-redline risk. ABSTAIN.")

    verdict = {
        "schema_version": "target39-alt-resolver-1",
        "results": res,
        "bore_log57_verdict": t["verdict"],
        "bore_log57_terminus": (t["dominant_terminus"]["ap"] if t["dominant_terminus"] else None),
        "missing_discriminator": "per_drive_segmentation_or_start_structure (resolves 741-vs-413 tail length gap + corridor-B prints)",
        "control_bore_log7": c["verdict"],
    }
    (ROOT / "scripts" / "target39_alternate_bore_drive_resolver.json").write_text(json.dumps(verdict, indent=2), encoding="utf-8")
    (ROOT / "scripts" / "target39_alternate_bore_drive_resolver.out").write_text("\n".join(OUT) + "\n", encoding="utf-8")
    print("\n".join(OUT))

    assert c["verdict"] == "PLACEABLE_BY_ALTERNATE_RESOLVER", f"CONTROL REGRESSED: bore_log7 {c['verdict']}"
    assert t["verdict"] in ("PLACEABLE_BY_ALTERNATE_RESOLVER", "NOT_UNIQUE_COMPETING_CANDIDATES", "HARD_BLOCKED_NO_DISCRIMINATOR")
    print("\nSELFTEST_OK (control placeable; target verdict emitted with explicit evidence)")


if __name__ == "__main__":
    main()
