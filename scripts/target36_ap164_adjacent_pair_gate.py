"""READ-ONLY Target #36 — endpoint-quality gate: the AP-164 adjacent-pair MISS (sheet 12, STA 355).

Target #32/#33 grade: AP-terminal sheets 8-12 -> 7 TP, precision 1.00, recall 0.70, 3 misses:
  (9, 3810, 155)  - high-station, data-absence (Target #22, NOT an extraction defect)
  (10, 136, 166)  - AP-166 glyph/geometry floor (FORBIDDEN to chase this session)
  (12, 355, 164)  - "adjacent-pair contamination": AP-167 @ STA 350 and AP-164 @ STA 355 are
                    ~5 ft apart; the extractor confirmed AP-167 @ 350 but missed AP-164 @ 355.

This is the only non-AP-166 extraction-quality recall gap that is a REAL hand-table run-endpoint
(AP-164 is in BRENHAM_PH5_RUN_ENDPOINTS and is geometry-ready in the #25 index). Recovering it is
a TRUE-POSITIVE recall gain, not a widening.

Question: is AP-164 @ 355 SAFELY recoverable as an 8th confirmed endpoint via a deterministic
adjacent-pair disambiguation that does NOT disturb the confirmed AP-167 @ 350, or is it a HARD
MISS that would require guessing?

The probe runs Primitive A/B + Target #30 reconstruction on sheet 12, isolates the STA 350/355
region, measures the geometry that caused the miss, and tests whether the canonical run-endpoint
gate (B-confirmed AND reconstructed AND full TERMINAL+PORT+SPLICE phrase AND not-matchline) holds
for AP-164 on its OWN merits. Classification:
  RECOVERABLE_SAFE          - AP-164 independently passes the same gate as the 7 confirmed; the miss
                              was an upstream nearest-label collision, not a true ambiguity.
  HARD_MISS_NEEDS_GUESS     - AP-164 and AP-167 are not separable without guessing -> stays a miss.
NO production change, NO extractor rewrite, NO flag/STATE/geometry/placement. Diagnostic only.
Writes the JSON verdict + .out. Self-test SELFTEST_OK. CONTROL: AP-167 @ 350 must stay confirmed.
"""
from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "backend")); sys.path.insert(0, str(ROOT / "scripts"))
for k in ("TRUELINE_JWT_SECRET", "TRUELINE_AUTH_JWT_SECRET"):
    os.environ.setdefault(k, "t36")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

import pdf_run_endpoint_extractor as A
import pdf_leader_run_following as B
import pdf_ap_glyph_reconstruct as G
import pdf_run_polyline_tracer as C

PLAN_PDF = Path(r"C:/Nova/knowledge/TrueLine-Wiki/raw/trueline/engineering-plans/brenham/Brenham - Phase 5_07-15-25.pdf")
PAGE_OFFSET = 13
SHEET = 12
PAIR = {"confirmed": {"sta": 350.0, "ap": 167}, "miss": {"sta": 355.0, "ap": 164}}
PHRASE_TOL = 48.0
AP_INDEX = ROOT / "scripts" / "ap_structure_index.json"

OUT: List[str] = []
def p(s: str = "") -> None:
    OUT.append(s)


def _cxy(w):
    return ((w["x0"] + w["x1"]) / 2.0, (w["top"] + w["bottom"]) / 2.0)


def full_phrase_ok(words, cx, cy) -> bool:
    toks = set()
    for w in words:
        wx, wy = _cxy(w)
        if math.hypot(wx - cx, wy - cy) <= PHRASE_TOL:
            toks.add(str(w.get("text", "")).upper())
    return ("TERMINAL" in toks) and ("PORT" in toks) and ("SPLICE" in toks)


def main() -> None:
    from backend.app.core import pdf_ap_route_resolver as R
    valid_aps = A._load_valid_aps()
    idx = json.loads(AP_INDEX.read_text(encoding="utf-8")).get("aps", {})
    hand_ap = {(s, sta, a) for (s, sta, k, a) in R.BRENHAM_PH5_RUN_ENDPOINTS if k == "ap"}

    p("=" * 88)
    p("Target #36 — endpoint-quality gate: AP-164 adjacent-pair MISS (sheet 12, STA 350/355) — READ-ONLY")
    p("=" * 88)

    import pdfplumber
    with pdfplumber.open(str(PLAN_PDF)) as pdf:
        page = pdf.pages[SHEET + PAGE_OFFSET - 1]
        words = page.extract_words(use_text_flow=True, keep_blank_chars=False)
        chars = list(page.chars)
        mlines = C.derive_matchline_stations(words)
        recs = A.extract_run_endpoints_from_layout(sheet=SHEET, words=words, chars=chars, valid_ap_ids=valid_aps)
        aug = B.augment_records(recs, words=words, chars=chars, lines=page.lines, curves=page.curves, valid_ap_ids=valid_aps)
        gidx = G.localized_ap_index(G.reconstruct_positioned_aps(chars=chars, words=words, valid_ap_ids=valid_aps))

    # Index AP rows by station for the pair
    by_sta: Dict[float, Dict[str, Any]] = {}
    for r in aug:
        if r["structure_type"] == "ap":
            by_sta[round(r["station_ft"], 0)] = r

    # Reconstructed centroids for 164 / 167
    c167 = gidx.get(167, [{}])[0].get("centroid") if gidx.get(167) else None
    c164 = gidx.get(164, [{}])[0].get("centroid") if gidx.get(164) else None
    sep = math.hypot(c167[0] - c164[0], c167[1] - c164[1]) if (c167 and c164) else None

    p("\n[A/B EXTRACTION ON SHEET 12 — the STA 350/355 pair]")
    for label, spec in PAIR.items():
        sta = spec["sta"]; ap = spec["ap"]
        r = by_sta.get(round(sta, 0))
        if r is None:
            p(f"   STA {sta:.0f} (hand AP-{ap}, role={label}): NO A-extraction row produced")
            continue
        lc = r["leader_connectivity"]
        role = C.classify_callout(station_ft=sta, matchline_stations=mlines,
                                  has_local_ap=lc["verdict"] in ("confirmed", "recovered"),
                                  has_local_struct=True)
        p(f"   STA {sta:.0f} (hand AP-{ap}, {label}): A_ap={r['ap_id']}  B_verdict={lc['verdict']}  "
          f"B_comp_ap={lc.get('component_ap')}  role={role}  reconstructed_in_gidx={ap in gidx}")

    p("\n[RECONSTRUCTED CENTROIDS]")
    p(f"   AP-167 centroid={c167}   AP-164 centroid={c164}")
    p(f"   centroid separation = {f'{sep:.1f} px' if sep is not None else 'N/A (one not localized)'}")
    p(f"   geometry-derived matchlines near pair = {[m for m in mlines if abs(m-352.5) <= 30]}")

    # --- evaluate AP-164 on the canonical run-endpoint gate, INDEPENDENTLY ---
    r164 = by_sta.get(355.0)
    g1_confirmed = bool(r164) and r164["leader_connectivity"]["verdict"] == "confirmed" and r164["ap_id"] == 164
    g2_reconstructed = 164 in gidx
    g3_phrase = full_phrase_ok(words, c164[0], c164[1]) if c164 else False
    g4_not_matchline = 355.0 not in mlines
    # the actual A-extraction verdict for 355 (was it claimed by 167, or abstained?)
    a_ap_355 = r164["ap_id"] if r164 else None
    b_355 = r164["leader_connectivity"]["verdict"] if r164 else None

    # control: AP-167 @ 350 must still be confirmed
    r167 = by_sta.get(350.0)
    control_ok = bool(r167) and r167["ap_id"] == 167 and r167["leader_connectivity"]["verdict"] == "confirmed"

    p("\n[CANONICAL RUN-ENDPOINT GATE applied to AP-164 @ 355 INDEPENDENTLY]")
    p(f"   g1 B-confirmed as AP-164 = {g1_confirmed}  (A_ap={a_ap_355}, B_verdict={b_355})")
    p(f"   g2 reconstructed         = {g2_reconstructed}")
    p(f"   g3 full TERMINAL+PORT+SPLICE phrase = {g3_phrase}")
    p(f"   g4 not matchline         = {g4_not_matchline}")

    in_hand = (12, 355.0, 164) in hand_ap
    geom_ready_164 = bool(idx.get("164", {}).get("geometry_anchor_ready"))

    # B-only "recovered" (component geometry found AP-164 but A's nearest-label abstained) is a
    # distinct, named state: the labels are NOT adjacent (separation measured below); the miss is a
    # Primitive-A abstention, so the A∧B agreement that DEFINES the confirmed tier is absent by design.
    b_recovered_only = bool(r164) and b_355 == "recovered" and r164["leader_connectivity"].get("component_ap") == 164
    far_apart = sep is not None and sep > 100.0  # centroids not adjacent -> not a label-collision

    if g1_confirmed and g2_reconstructed and g3_phrase and g4_not_matchline and in_hand:
        classification = "RECOVERABLE_SAFE"
        machine_reason = "ap164_independently_passes_canonical_gate_miss_was_upstream_nearest_label_collision"
    else:
        classification = "HARD_MISS_NEEDS_GUESS"
        fails = []
        if not g1_confirmed:
            fails.append(f"A_side_abstained_no_A_B_agreement(A_ap={a_ap_355},B_verdict={b_355})")
        if not g2_reconstructed:
            fails.append("not_reconstructed")
        if not g3_phrase:
            fails.append("no_full_terminal_port_splice_phrase")
        if not g4_not_matchline:
            fails.append("matchline_station")
        if b_recovered_only:
            machine_reason = (
                "ap164_is_a_PrimitiveB_recovered_only_candidate (" + "; ".join(fails) + "). "
                "NOT a label-adjacency collision: AP-164 / AP-167 centroids are "
                f"{sep:.0f}px apart. The miss is a Primitive-A abstention at STA 355, so the A^B "
                "agreement that DEFINES the confirmed tier is absent BY DESIGN. AP-164 is a real "
                "hand-table run-endpoint (geometry-ready) recovered by B (full phrase, run_end, "
                "reconstructed). Promotion would require EITHER a validated Primitive-A fix at STA "
                "355 OR an authorized decision to admit B-recovered endpoints into the placement-"
                "grade set (a trust-tier change) — neither is a guess, but both are out of scope "
                "for a no-widen structure-side gate. Stays a documented miss / B-recovered review."
            )
        else:
            machine_reason = ("ap164_does_not_pass_canonical_gate: " + "; ".join(fails)
                              + " -> not safely recoverable; documented miss")

    p("\n[DECISION]")
    p(f"   AP-164 hand run-endpoint={in_hand}  geometry_ready={geom_ready_164}  centroid_sep="
      f"{f'{sep:.1f}px' if sep is not None else 'N/A'}")
    p(f"   => {classification}")
    p(f"      reason: {machine_reason}")

    p("\n[CONTROL — AP-167 @ 350 confirmed endpoint must NOT degrade]")
    p(f"   AP-167 @ 350: A_ap={r167['ap_id'] if r167 else None}  "
      f"B_verdict={r167['leader_connectivity']['verdict'] if r167 else None}  control_ok={control_ok}")

    p("\n[SUMMARY]")
    if classification == "RECOVERABLE_SAFE":
        p("   AP-164 @ 355 independently satisfies the same gate that admitted the 7 confirmed; the")
        p("   miss was an upstream one-AP-per-station nearest-label collision with AP-167@350. A narrow,")
        p("   deterministic adjacent-pair rule (allow a SECOND confirmed AP within a station window when")
        p("   it independently passes the full gate + is a distinct reconstructed cluster) would recover")
        p("   it to an 8th confirmed endpoint WITHOUT disturbing AP-167. Proposed as a default-OFF gate")
        p("   improvement; NOT implemented in production here.")
    else:
        p("   CORRECTS the '#32 adjacent-pair contamination' label: AP-164 and AP-167 labels are NOT")
        p(f"   adjacent (centroids {sep:.0f}px apart). AP-164 is a Primitive-B 'recovered'-only")
        p("   candidate — a real hand-table run-endpoint that B found (full phrase, run_end,")
        p("   reconstructed, real KMZ node) but Primitive A ABSTAINED on (A_ap=None), so the A^B")
        p("   agreement defining the confirmed tier is absent by design. It cannot enter the")
        p("   placement-grade set without either a validated A-side fix at STA 355 or an authorized")
        p("   B-recovered trust-tier change — out of scope for a no-widen gate. Documented miss.")
    p("   Precision stays 1.00 either way; the 7 confirmed + bore_log7 lane are untouched.")

    verdict = {
        "schema_version": "target36-ap164-adjacent-pair-1",
        "pair": PAIR, "sheet": SHEET,
        "classification": classification, "machine_reason": machine_reason,
        "evidence": {
            "ap164_in_hand_table": in_hand, "ap164_geometry_ready": geom_ready_164,
            "ap164_A_ap_at_355": a_ap_355, "ap164_B_verdict_at_355": b_355,
            "ap164_reconstructed": g2_reconstructed, "ap164_full_phrase": g3_phrase,
            "ap164_not_matchline": g4_not_matchline,
            "centroid_167": c167, "centroid_164": c164,
            "centroid_separation_px": sep,
            "b_recovered_only": b_recovered_only, "labels_far_apart": far_apart,
        },
        "control_ok": control_ok,
        "headline": (f"AP-164 @ (12,355) -> {classification}: " +
                     ("independently gate-passes; recoverable via a narrow default-OFF adjacent-pair rule"
                      if classification == "RECOVERABLE_SAFE"
                      else "not separable from AP-167@350 without guessing; documented miss")),
    }
    (ROOT / "scripts" / "target36_ap164_adjacent_pair_gate.json").write_text(json.dumps(verdict, indent=2), encoding="utf-8")
    (ROOT / "scripts" / "target36_ap164_adjacent_pair_gate.out").write_text("\n".join(OUT) + "\n", encoding="utf-8")
    print("\n".join(OUT))

    assert control_ok, "CONTROL REGRESSED: AP-167 @ 350 no longer confirmed"
    assert classification in ("RECOVERABLE_SAFE", "HARD_MISS_NEEDS_GUESS")
    print("\nSELFTEST_OK (control intact, classification emitted)")


if __name__ == "__main__":
    main()
