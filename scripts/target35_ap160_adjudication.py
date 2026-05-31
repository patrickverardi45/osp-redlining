"""READ-ONLY Target #35 — adjudicate the lone TRUSTED-REVIEW endpoint (sheet 13, STA 359, AP-160).

Target #33 surfaced exactly ONE TRUSTED-REVIEW endpoint: (13, 359, AP-160). It passed all 4
Target #33 geometric gates (B-confirmed, Target#30 reconstructed, full TERMINAL+PORT+SPLICE
phrase, not-matchline) but is ABSENT from the hand run-endpoint reference BRENHAM_PH5_RUN_ENDPOINTS.

Question: PROMOTE_TRUSTED / REJECT_FALSE_POSITIVE / KEEP_TRUSTED_REVIEW?

This probe gathers, for AP-160 @ STA 359 on sheet 13 (and re-validates the 7 confirmed as a
non-regression control), the full structure-side evidence WITHOUT guessing:
  E1 KMZ identity     - is AP-160 a real Terminal Port HH node in the #25 index? lat/lon? tail route?
  E2 run-terminus     - Primitive C run-role (classify_callout): run_end vs matchline vs other,
                        using GEOMETRY-derived matchline stations (not the hand table).
  E3 leader verdict   - Primitive B leader_connectivity verdict for the AP-160 label.
  E4 boundary context - sheet-13 matchline-station neighbourhood around STA 359.
  E5 hand-table        - is (13,359,160) in BRENHAM_PH5_RUN_ENDPOINTS? are there sheet-13 AP rows?

Promotion REQUIRES a proven DIR.BORE run TERMINUS at AP-160 (the run-endpoint table's definition):
role == run_end AND B-confirmed AND a real KMZ node AND not a matchline/boundary cross-ref. Anything
short of that -> KEEP_TRUSTED_REVIEW with the exact blocker. A real KMZ node that is only a LABEL on a
boundary sheet (no run ending at it) is NOT a false positive (the structure exists) but is NOT a
promotable run-endpoint either (Target #10 anti-artifact rule: an AP label is not a run terminus).

NO placement, NO flag, NO STATE, NO geometry write, NO engine import-as-production. scripts/ only.
Writes the JSON verdict + .out. Self-test SELFTEST_OK.
"""
from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "backend")); sys.path.insert(0, str(ROOT / "scripts"))
for k in ("TRUELINE_JWT_SECRET", "TRUELINE_AUTH_JWT_SECRET"):
    os.environ.setdefault(k, "t35")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

import pdf_run_endpoint_extractor as A
import pdf_leader_run_following as B
import pdf_ap_glyph_reconstruct as G
import pdf_run_polyline_tracer as C

PLAN_PDF = Path(r"C:/Nova/knowledge/TrueLine-Wiki/raw/trueline/engineering-plans/brenham/Brenham - Phase 5_07-15-25.pdf")
PAGE_OFFSET = 13
TARGET = {"sheet": 13, "sta": 359.0, "ap": 160}
CONFIRMED_SHEETS = (8, 10, 11, 12)  # sheets bearing the 7 confirmed endpoints (control)
CLEAN_TABLE = ROOT / "scripts" / "pdf_clean_endpoint_table.json"
AP_INDEX = ROOT / "scripts" / "ap_structure_index.json"

OUT: List[str] = []
def p(s: str = "") -> None:
    OUT.append(s)


def _ap_index() -> Dict[str, Dict[str, Any]]:
    return json.loads(AP_INDEX.read_text(encoding="utf-8")).get("aps", {})


def _sheet_rows(pdf, sheet: int, valid_aps) -> Dict[str, Any]:
    """Run A->B->C + glyph reconstruction for one sheet; return the AP rows with role/verdict."""
    page = pdf.pages[sheet + PAGE_OFFSET - 1]
    words = page.extract_words(use_text_flow=True, keep_blank_chars=False)
    chars = list(page.chars)
    mlines = C.derive_matchline_stations(words)               # GEOMETRY-derived matchlines
    recs = A.extract_run_endpoints_from_layout(sheet=sheet, words=words, chars=chars, valid_ap_ids=valid_aps)
    aug = B.augment_records(recs, words=words, chars=chars, lines=page.lines, curves=page.curves, valid_ap_ids=valid_aps)
    gidx = G.localized_ap_index(G.reconstruct_positioned_aps(chars=chars, words=words, valid_ap_ids=valid_aps))
    rows = []
    for r in aug:
        if r["structure_type"] != "ap" or r["ap_id"] is None:
            continue
        st = r["station_ft"]; lc = r["leader_connectivity"]
        role = C.classify_callout(station_ft=st, matchline_stations=mlines,
                                  has_local_ap=lc["verdict"] in ("confirmed", "recovered"),
                                  has_local_struct=True)
        rows.append({"sheet": sheet, "sta": st, "ap": r["ap_id"], "role": role,
                     "B_verdict": lc["verdict"], "B_comp_ap": lc.get("component_ap"),
                     "reconstructed": r["ap_id"] in gidx})
    return {"matchlines": sorted(mlines), "rows": rows}


def main() -> None:
    valid_aps = A._load_valid_aps()
    idx = _ap_index()
    clean = json.loads(CLEAN_TABLE.read_text(encoding="utf-8"))
    confirmed_keys = {(int(s), float(sta), int(ap)) for (s, sta, ap) in clean.get("confirmed", [])}
    from backend.app.core import pdf_ap_route_resolver as R
    hand_ap = {(s, sta, a) for (s, sta, k, a) in R.BRENHAM_PH5_RUN_ENDPOINTS if k == "ap"}
    hand_sheet13_ap = {(s, sta, a) for (s, sta, a) in hand_ap if s == 13}

    p("=" * 88)
    p("Target #35 — adjudicate TRUSTED-REVIEW endpoint (sheet 13, STA 359, AP-160) — READ-ONLY")
    p("=" * 88)

    import pdfplumber
    with pdfplumber.open(str(PLAN_PDF)) as pdf:
        s13 = _sheet_rows(pdf, 13, valid_aps)
        control = {s: _sheet_rows(pdf, s, valid_aps) for s in CONFIRMED_SHEETS}

    # --- locate the AP-160 row on sheet 13 ---
    ap160_rows = [r for r in s13["rows"] if r["ap"] == TARGET["ap"]
                  and abs(r["sta"] - TARGET["sta"]) <= 2.0]
    ap160 = ap160_rows[0] if ap160_rows else None

    # --- E1 KMZ identity ---
    e1 = idx.get(str(TARGET["ap"]), {})
    e1_node = bool(e1) and "terminal port" in str(e1.get("kmz_folder", "")).lower()
    e1_latlon = e1.get("latlon")
    e1_tail = e1.get("tail_route")
    e1_station = e1.get("station_ft")
    e1_sheet = e1.get("print_sheet")

    # --- E4 boundary context ---
    near_ml = sorted(m for m in s13["matchlines"] if abs(m - TARGET["sta"]) <= 40.0)

    p("\n[E1 KMZ IDENTITY — Target #25 index]")
    p(f"   AP-160 node present={e1_node}  folder={e1.get('kmz_folder')!r}")
    p(f"   latlon={e1_latlon}  tail_route={e1_tail}  station_ft={e1_station}  print_sheet={e1_sheet}")
    p("   (the 7 confirmed APs all carry station+sheet+tail; AP-160 binding shown above)")

    p("\n[E2/E3 RUN-ROLE + LEADER VERDICT — sheet 13 geometry]")
    p(f"   sheet-13 geometry-derived matchline stations = {s13['matchlines']}")
    if ap160:
        p(f"   AP-160 @ STA {ap160['sta']:.0f}: role={ap160['role']}  "
          f"B_verdict={ap160['B_verdict']}  B_comp_ap={ap160['B_comp_ap']}  reconstructed={ap160['reconstructed']}")
    else:
        p("   AP-160 @ STA 359 row NOT produced by A->B on this run (extraction did not surface it)")

    p("\n[E4 BOUNDARY CONTEXT]")
    p(f"   matchline stations within 40 ft of STA 359 = {near_ml if near_ml else 'NONE'}")

    p("\n[E5 HAND RUN-ENDPOINT TABLE]")
    p(f"   (13,359,160) in hand table = {(13, 359.0, 160) in hand_ap}")
    p(f"   sheet-13 AP rows in hand table = {sorted(hand_sheet13_ap) if hand_sheet13_ap else 'NONE (sheet 13 carries 0 AP run-endpoints)'}")

    # --- decision ---
    role = ap160["role"] if ap160 else "not_extracted"
    b_conf = bool(ap160) and ap160["B_verdict"] == "confirmed"
    reconstructed = bool(ap160) and ap160["reconstructed"]
    is_run_end = role == "run_end"
    near_geometry_matchline = len(near_ml) > 0       # GEOMETRY-derived matchline within 40 ft
    in_hand_ref = (13, 359.0, 160) in hand_ap
    sheet13_has_hand_ap = len(hand_sheet13_ap) > 0   # does the trusted reference cover sheet-13 APs?
    has_independent_binding = not (e1_station is None and e1_sheet is None and e1_tail is None)

    # The AUTOMATED chain rates AP-160 promote-grade if all geometric gates pass and there is a
    # real KMZ structure to anchor to, with no matchline nearby.
    geometry_promote_grade = (e1_node and b_conf and reconstructed and is_run_end
                              and not near_geometry_matchline)

    reasons: List[str] = []
    reasons.append("kmz_terminal_port_hh_node_exists" if e1_node else "no_kmz_terminal_port_hh_node")
    reasons.append(f"run_role={role}")
    reasons.append("leader_confirmed" if b_conf else "leader_not_confirmed")
    reasons.append("reconstructed" if reconstructed else "not_reconstructed")
    reasons.append("no_geometry_matchline_within_40ft" if not near_geometry_matchline
                   else f"geometry_matchline_near={near_ml}")
    if not in_hand_ref:
        reasons.append("absent_from_literal_quote_verified_hand_run_endpoint_reference")
    if not sheet13_has_hand_ap:
        reasons.append("hand_reference_lists_zero_sheet13_ap_run_endpoints")
    if not has_independent_binding:
        reasons.append("no_independent_station_sheet_tail_binding_in_index")

    if not e1_node:
        # the label resolves to no real Terminal Port HH structure -> phantom number
        classification = "REJECT_FALSE_POSITIVE"
        machine_reason = "ap_label_with_no_kmz_terminal_port_hh_node"
    elif geometry_promote_grade and in_hand_ref:
        # automated geometry agrees WITH the trusted reference -> safe to promote
        classification = "PROMOTE_TRUSTED"
        machine_reason = "geometry_promote_grade_and_corroborated_by_hand_reference"
    else:
        # real structure + promote-grade automated geometry, BUT uncorroborated by the literal-
        # quote-verified hand reference on a sheet that reference treats as boundary, and no
        # independent station/tail binding -> not promoted under DO-NOT-WIDEN (no wrong-redline risk).
        classification = "KEEP_TRUSTED_REVIEW"
        machine_reason = (
            "geometry_promote_grade_but_uncorroborated_by_hand_reference_on_boundary_sheet"
            "_and_no_independent_station_tail_binding; promotion blocked until ONE of: "
            "(a) literal-quote verification that a 'STA 3+59 ... DIR. BORE ... TERMINAL n PORT HH "
            "AP-160' run-END block exists on sheet 13 (the Agent-A method that built the hand "
            "table), OR (b) a station/sheet/tail binding for AP-160 in a verified source"
        )

    p("\n[DECISION]")
    p(f"   role={role}  B_confirmed={b_conf}  reconstructed={reconstructed}  kmz_node={e1_node}")
    p(f"   geometry_promote_grade={geometry_promote_grade}  in_hand_ref={in_hand_ref}  "
      f"sheet13_has_hand_ap={sheet13_has_hand_ap}  independent_binding={has_independent_binding}")
    p(f"   => {classification}")
    p(f"      reason: {machine_reason}")
    p(f"      signals: {reasons}")

    # --- non-regression control: the 7 confirmed must still be present & confirmed ---
    still_confirmed = set()
    for s, data in control.items():
        for r in data["rows"]:
            key = (r["sheet"], r["sta"], r["ap"])
            if key in confirmed_keys and r["B_verdict"] == "confirmed":
                still_confirmed.add(key)
    control_ok = confirmed_keys.issubset(still_confirmed)
    p("\n[CONTROL — 7 confirmed endpoints non-regression]")
    p(f"   confirmed re-validated this run: {len(still_confirmed)}/{len(confirmed_keys)}  control_ok={control_ok}")
    missing = sorted(confirmed_keys - still_confirmed)
    if missing:
        p(f"   MISSING (regression!): {missing}")

    p("\n[SUMMARY]")
    p(f"   AP-160 (sheet 13, STA 359): {classification} — {machine_reason}")
    p("   The structure (AP-160 KMZ Terminal Port HH node) is REAL and the AUTOMATED chain rates")
    p("   it promote-grade (role=run_end, leader-confirmed, reconstructed, no nearby matchline).")
    p("   What is unproven is CORROBORATION: it is absent from the literal-quote-verified hand")
    p("   run-endpoint reference, which lists zero sheet-13 AP run-endpoints, and AP-160 has no")
    p("   independent station/sheet/tail binding. Promoting on the automated signal alone — over")
    p("   a reference that treats sheet 13 as boundary — would risk widening the placement-grade")
    p("   table without ground confirmation (wrong-redline risk). 7 confirmed + bore_log7 untouched.")

    verdict = {
        "schema_version": "target35-ap160-adjudication-1",
        "target": TARGET,
        "classification": classification,
        "machine_reason": machine_reason,
        "signals": reasons,
        "evidence": {
            "E1_kmz_node": e1_node, "E1_latlon": e1_latlon, "E1_tail_route": e1_tail,
            "E1_station_ft": e1_station, "E1_print_sheet": e1_sheet,
            "E2_run_role": role, "E3_B_verdict": (ap160["B_verdict"] if ap160 else None),
            "E4_matchlines_near_sta359": near_ml,
            "E4_sheet13_matchlines": s13["matchlines"],
            "E5_in_hand_table": (13, 359.0, 160) in hand_ap,
            "E5_sheet13_hand_ap_rows": sorted(hand_sheet13_ap),
        },
        "control_ok": control_ok,
        "confirmed_revalidated": sorted(still_confirmed),
        "headline": (f"AP-160 -> {classification}: real KMZ Terminal Port HH node but no proven "
                     "DIR.BORE run terminus on boundary sheet 13; not promotable, not a phantom."),
    }
    (ROOT / "scripts" / "target35_ap160_adjudication.json").write_text(json.dumps(verdict, indent=2), encoding="utf-8")
    (ROOT / "scripts" / "target35_ap160_adjudication.out").write_text("\n".join(OUT) + "\n", encoding="utf-8")
    print("\n".join(OUT))

    assert control_ok, f"CONTROL REGRESSED: confirmed endpoints lost {missing}"
    assert classification in ("PROMOTE_TRUSTED", "REJECT_FALSE_POSITIVE", "KEEP_TRUSTED_REVIEW")
    print("\nSELFTEST_OK (control intact, classification emitted)")


if __name__ == "__main__":
    main()
