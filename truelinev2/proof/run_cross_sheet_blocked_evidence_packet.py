r"""CROSS_SHEET BLOCKED evidence-target PACKET (PROOF/REPORT ONLY; read-only; reuses shipped grammar).

The cross_sheet_frame_join scout partitioned the remaining CROSS_SHEET class (6 logs) into SOURCE_BACKED
(log11, log47 -- the frame join computes; held on a per-endpoint IDENTITY) and SOURCE_BLOCKED (log48,
log67, log69, log70 -- the frame join itself ABSTAINS on a named source gap). This slice prepares the
EXACT evidence/owner-confirmation targets needed to unblock all six -- class-level, not 1x1 -- and surfaces
the precise printed crossings the owner must choose between. It ENCODES nothing, modifies no fixture,
parses no coordinate into a placement, draws nothing, promotes nothing, and never guesses a crossing.

Two sub-categories (re-verified live from the shipped frame-join primitive, not memory):

  FRAME_JOIN_SOURCE_BLOCKED -- the cross-sheet matchline frame join can NOT be computed; needs a source/
    owner crossing answer (the bridge cannot proceed until the join is source-backed):
      log48  10->11->12: NO_PAIRED_FRAME_EQUATION. Sheet 11 is the original HANDWRITTEN print and prints
             no machine-readable paired matchline equation for 10<->11 or 11<->12. BUT a DIRECT 10<->12
             frame edge IS printed HIGH-confidence (candidate). Owner: provide the sheet-11 crossing
             stations, OR confirm the bore reconciles directly 10<->12.
      log67/69/70  17<->20: CONFLICTING_FRAME_EQUATIONS. The 17<->20 boundary prints TWO physical
             crossings ~504 ft apart -- a near-aligned one and a 504-ft-offset one. Owner: which crossing
             does THIS bore's route use?
  JOIN_SOURCE_BACKED_SECOND_TERMINUS_UNNAMED -- the frame join is source-backed and ONE terminus is owner-
    named (flower_pot); the SECOND terminus identity needs owner confirmation before the endpoint-anchor
    bridge (the log52/log58 lane). Included here as owner-confirmation targets:
      log11  join 5->17 source-backed; end FLOWER POT @ 6+30 owner-named; START is the reset 'STA 21+63=
             0+00' on sheet 5 -- the IDENTICAL reset log53 adjudicated as a NEXTLINK HH (cross-log, not in
             log11's own review). Owner: does log11 share log53's NEXTLINK HH start?
      log47  join 10->13->14 source-backed; start FLOWER POT @ 3+23 owner-named (binds on sheet 13, not the
             stated sheet 10); END 'STA 4+94, opposite side of Woodson Ln' is a BARE station (no owner-
             named structure). Owner: name the STA 4+94 structure (+ confirm the start sheet).

The crossings/equations are EXTRACTED with the SHIPPED grammar (match.frames.parse_frame_equations /
build_frame_edges / detect_conflicts) and PRESENTED for the owner to choose -- this slice NEVER picks a
crossing or names a structure. Census stays frozen; the seam is unchanged; the six stay UNencoded in the
reviewed artifact.

Proof-only; the JSON packet is written under the gitignored data/outputs path.
Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_cross_sheet_blocked_evidence_packet
"""
from __future__ import annotations

import json
import os

import truelinev2.match.frames as FR
from truelinev2.config import _REPO_ROOT
from truelinev2.extract.registry import select_dialect
from truelinev2.ingest.manual_adjudication import (
    activation_summary,
    apply_adjudications,
    load_adjudication,
    parent_run_duplicate_check,
)
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.proof.run_all_redlines_closure_ledger import CROSS_SHEET, build_ledger
from truelinev2.proof.run_brenham_corpus import PDF
from truelinev2.proof.run_cross_sheet_frame_join_scout import (
    ABSTAIN_CONFLICT,
    ABSTAIN_NO_EQUATION,
    ABSTAIN_REASONS,
    EXPECTED_BLOCKED,
    EXPECTED_SOURCE_BACKED,
    _sheet_text,
    scout_log,
)
from truelinev2.seam import ELIGIBLE_EXEMPLARS

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "cross_sheet_blocked_evidence_packet"
TRUTH = _REPO_ROOT / "data" / "outputs" / "final_engine_truth_table" / \
    "final_engine_truth_table.json"
FROZEN_BUCKETS = {"DRAWABLE_REVIEW": 31, "HUMAN_ADJUSTABLE_REVIEW": 6,
                  "OUT_OF_CLASS": 1, "PICK_CARD_REVIEW": 17, "SOURCE_OR_KMZ_REQUIRED": 3}
ABSTAIN_4 = ("log5", "log31", "log38", "log43")
SEAM_ELIGIBLE = ("log53", "log64", "log71", "log59", "log66")

SOURCE_BLOCKED = EXPECTED_BLOCKED          # ("log48","log67","log69","log70")
IDENTITY_HELD = EXPECTED_SOURCE_BACKED      # ("log11","log47")
INCLUDED = tuple(sorted(SOURCE_BLOCKED + IDENTITY_HELD, key=lambda s: int(s[3:])))

# the conflicting/absent boundaries to surface per blocked log (read from the live source)
CONFLICT_BOUNDARY = {"log67": (17, 20), "log69": (17, 20), "log70": (17, 20)}
LOG48_HOPS = ((10, 11), (11, 12))
LOG48_DIRECT = (10, 12)

R_READY = "CROSS_SHEET_BLOCKED_EVIDENCE_PACKET_READY"
B_DRIFT = "BLOCKED_PACKET_SET_DRIFTED"
B_NOT_BLOCKED = "BLOCKED_PACKET_JOIN_NOT_ACTUALLY_BLOCKED"
B_EVIDENCE = "BLOCKED_PACKET_EVIDENCE_NOT_EXTRACTED"
B_ENCODED = "BLOCKED_PACKET_SILENTLY_ENCODED"
ALLOWED = {R_READY, B_DRIFT, B_NOT_BLOCKED, B_EVIDENCE, B_ENCODED}


def _census_frozen(doc) -> bool:
    if not TRUTH.is_file():
        return False
    truth = json.loads(TRUTH.read_text(encoding="utf-8"))
    baseline = {r["bore_id"]: dict(r) for r in truth["rows"]}
    off_rows = apply_adjudications(baseline, enabled=False)
    on_rows = apply_adjudications(baseline, enabled=True, doc=doc)
    summ = activation_summary(on_rows)
    buckets = {}
    for r in off_rows.values():
        buckets[r["completion_bucket"]] = buckets.get(r["completion_bucket"], 0) + 1
    return (off_rows is baseline and buckets == FROZEN_BUCKETS
            and summ["manual_review_drawable"] == 22 and summ["manual_source_verification"] == 1
            and summ["manual_abstain"] == 4
            and on_rows["log44"]["adjudication"]["drawable_status"] == "non_drawable"
            and all(on_rows[l]["adjudication"]["drawable_status"] == "abstain" for l in ABSTAIN_4)
            and not parent_run_duplicate_check(doc))


def boundary_edges(plan, offset, a, b):
    """Candidate HIGH/identity frame edges + conflicts for the a<->b boundary, via the SHIPPED grammar.
    Returns (edges, conflicts) -- the printed crossings, presented (never picked)."""
    fa, fb = FR.frame_for_sheet(a), FR.frame_for_sheet(b)
    cand = (FR.build_frame_edges(FR.parse_frame_equations(_sheet_text(plan, offset, a)), fa)
            + FR.build_frame_edges(FR.parse_frame_equations(_sheet_text(plan, offset, b)), fb))
    pair = [e for e in cand if {str(e.from_frame), str(e.to_frame)} == {str(fa), str(fb)}]
    return pair, FR.detect_conflicts(pair)


def _edge_view(e) -> dict:
    return {"from": str(e.from_frame), "to": str(e.to_frame), "offset_ft": e.offset_ft,
            "confidence": str(e.confidence).split(".")[-1], "a_raw": e.a_raw, "b_raw": e.b_raw,
            "source": e.source}


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for stale in OUT_DIR.glob("*.png"):
        stale.unlink()

    doc = load_adjudication()
    rec = {r["log_id"]: r for r in doc["logs"]}
    gates, evidence = [], {}
    result = B_DRIFT

    gates.append(("G0 engine census frozen (OFF 31/6/1/17/3, ON 22/1/4, log44+abstains held)",
                  _census_frozen(doc), None))

    # G1 the included set is EXACTLY the live ledger CROSS_SHEET class (6) = blocked(4) + identity-held(2)
    ledger_cross = set()
    if TRUTH.is_file():
        rows = json.loads(TRUTH.read_text(encoding="utf-8"))["rows"]
        ledger_cross = {b for b, v in build_ledger(rows, doc).items() if v["category"] == CROSS_SHEET}
    gates.append(("G1 included set == live ledger CROSS_SHEET class (6) = SOURCE_BLOCKED(4) + IDENTITY_HELD(2)",
                  ledger_cross == set(INCLUDED) and set(SOURCE_BLOCKED).isdisjoint(IDENTITY_HELD),
                  sorted(ledger_cross)))

    if not os.path.isfile(PDF):
        gates.append(("G2 plan PDF present (read-only, to read printed matchline equations)", False, PDF))
        return _emit(gates, B_EVIDENCE, rec, evidence)
    gates.append(("G2 plan PDF present (read-only)", True, None))

    plan = PlanPdf(PDF)
    try:
        offset = select_dialect(plan).calibrate(plan, 13)
        graph = FR._build_plan_frame_graph(plan, offset)
        scout = {lid: scout_log(graph, plan, offset, rec[lid]) for lid in INCLUDED}

        # G3 live re-verify: SOURCE_BLOCKED join abstains with a NAMED reason; IDENTITY_HELD join is backed
        blocked_named = all(not scout[l]["source_backed"] and scout[l]["blocker"] in ABSTAIN_REASONS
                            for l in SOURCE_BLOCKED)
        held_backed = all(scout[l]["source_backed"] for l in IDENTITY_HELD)
        gates.append(("G3 live: SOURCE_BLOCKED(4) join abstains w/ named reason; IDENTITY_HELD(2) join source-backed",
                      blocked_named and held_backed, {l: scout[l]["blocker"] for l in SOURCE_BLOCKED}))

        # G4 extract the EXACT conflicting crossings for log67/69/70 (a real detected conflict; >=2 crossings)
        e1720, c1720 = boundary_edges(plan, offset, 17, 20)
        evidence["crossing_17_20"] = {"edges": [_edge_view(e) for e in e1720],
                                      "conflicts": [{"pair": list(c.frame_pair), "offsets_ft": c.offsets_ft}
                                                    for c in c1720],
                                      "distinct_offsets": sorted({abs(e.offset_ft) for e in e1720})}
        conflict_ok = bool(c1720) and len({abs(e.offset_ft) for e in e1720}) >= 2
        gates.append(("G4 log67/69/70 17<->20: a real CONFLICT with >=2 distinct printed crossings extracted (owner choices)",
                      conflict_ok, {"n_edges": len(e1720), "n_conflicts": len(c1720),
                                    "offsets": evidence["crossing_17_20"]["distinct_offsets"]}))

        # G5 log48: 10<->11 & 11<->12 have NO paired edge (sheet 11 handwritten); a DIRECT 10<->12 HIGH edge
        #    exists as a candidate the owner can confirm.
        hop_edges = {f"{a}_{b}": boundary_edges(plan, offset, a, b)[0] for a, b in LOG48_HOPS}
        direct_edges, _ = boundary_edges(plan, offset, *LOG48_DIRECT)
        direct_high = [e for e in direct_edges if str(e.confidence).endswith("HIGH")]
        evidence["log48"] = {
            "hops_no_paired_equation": {k: len(v) == 0 for k, v in hop_edges.items()},
            "direct_10_12_candidates": [_edge_view(e) for e in direct_high]}
        log48_ok = all(len(v) == 0 for v in hop_edges.values()) and len(direct_high) >= 1
        gates.append(("G5 log48: 10<->11 & 11<->12 NO paired equation (sheet 11 handwritten); DIRECT 10<->12 HIGH edge present (candidate)",
                      log48_ok, {"hops_empty": evidence["log48"]["hops_no_paired_equation"],
                                 "direct_high": len(direct_high)}))

        # G6 IDENTITY_HELD: log11/log47 each carry exactly ONE owner-named modeled (flower_pot) terminus;
        #    the SECOND terminus is the owner question (no endpoint_anchors yet on either).
        held_ok = True
        for l in IDENTITY_HELD:
            notes_up = str(rec[l].get("evidence_notes") or "").upper()
            held_ok = held_ok and ("FLOWER POT" in notes_up) and not rec[l].get("endpoint_anchors")
        gates.append(("G6 IDENTITY_HELD log11/log47: one owner-named flower_pot terminus + join source-backed; 2nd terminus = owner question",
                      held_ok, None))
    finally:
        plan.close()

    # G7 ENCODES NOTHING: all six carry no endpoint_anchors; still in the ledger CROSS_SHEET class
    encodes_nothing = (all(not rec[l].get("endpoint_anchors") for l in INCLUDED)
                       and ledger_cross == set(INCLUDED))
    gates.append(("G7 ENCODES NOTHING: all six carry no endpoint_anchors; still CROSS_SHEET (fixture untouched)",
                  encodes_nothing, None))

    if all(x for _, x, _ in gates):
        result = R_READY
    elif not gates[1][1]:
        result = B_DRIFT
    elif not gates[3][1]:
        result = B_NOT_BLOCKED
    elif not (gates[4][1] and gates[5][1]):
        result = B_EVIDENCE
    elif not gates[-1][1]:
        result = B_ENCODED
    return _emit(gates, result, rec, evidence)


def _emit(gates, result, rec, evidence) -> int:
    pngs = sorted(p.name for p in OUT_DIR.glob("*.png"))
    gates.append(("G8 no render / zero PNG / seam unchanged (nothing promoted)",
                  len(pngs) == 0 and tuple(ELIGIBLE_EXEMPLARS) == SEAM_ELIGIBLE, {"pngs": pngs}))
    gates.append(("G9 result in allowed enum", result in ALLOWED, result))
    all_pass = all(x for _, x, _ in gates)

    x1720 = evidence.get("crossing_17_20", {})
    packet = {
        "log48": {
            "log_id": "log48", "sub_category": "FRAME_JOIN_SOURCE_BLOCKED",
            "current_blocker": ABSTAIN_NO_EQUATION,
            "source_sheets": [10, 11, 12], "run": "STA 45+33=0+00 (s10) -> STA 5+14 FLOWER POT (s12)",
            "exact_missing": ("sheet 11 is the original HANDWRITTEN print and prints no machine-readable "
                              "paired matchline equation for 10<->11 or 11<->12; a DIRECT 10<->12 frame edge "
                              "IS printed HIGH-confidence as a candidate"),
            "candidate_direct_10_12": evidence.get("log48", {}).get("direct_10_12_candidates"),
            "owner_must_answer": ["provide the sheet-11 matchline crossing stations for 10<->11 and 11<->12, "
                                  "OR confirm the bore reconciles DIRECTLY 10<->12 (e.g. STA 1+91/1+92 or STA 1+90/1+90)"],
            "what_unlocks_if_confirmed": ("the 10->12 cross-sheet frame join becomes source-backed -> endpoint-"
                                          "anchor bridge + sheet-local source-bind (the log52/log58 lane)")},
        "log67_69_70": {
            "log_ids": ["log67", "log69", "log70"], "sub_category": "FRAME_JOIN_SOURCE_BLOCKED",
            "current_blocker": ABSTAIN_CONFLICT,
            "source_sheets": [17, 20],
            "exact_missing": ("the 17<->20 boundary prints TWO conflicting physical crossings; the shipped "
                              "primitive refuses to guess which applies per bore"),
            "printed_crossings_to_choose": x1720.get("edges"),
            "conflict": x1720.get("conflicts"),
            "owner_must_answer": [
                "log67 (STA 1+45=0+00 -> 4+14 FLOWER POT): which 17<->20 crossing does its route use?",
                "log69 (STA 2+15 -> 4+54): which 17<->20 crossing?",
                "log70 (STA 4+54 INSTALLER HH -> 2+15 FLOWER POT, HH-HH 215'): which 17<->20 crossing?"],
            "what_unlocks_if_confirmed": ("the chosen 17<->20 frame edge makes each join source-backed -> "
                                          "endpoint-anchor bridge + sheet-local bind per bore")},
        "log11": {
            "log_id": "log11", "sub_category": "JOIN_SOURCE_BACKED_SECOND_TERMINUS_UNNAMED",
            "current_blocker": "ENDPOINT_IDENTITY (start) -- join 5->17 source-backed",
            "source_sheets": [5, 17], "run": "reset STA 21+63=0+00 (s5) -> STA 6+30 FLOWER POT (s17)",
            "exact_missing": ("the END is owner-named FLOWER POT @ 6+30; the START reset 'STA 21+63=0+00' on "
                              "sheet 5 is the IDENTICAL reset log53 adjudicated as a NEXTLINK HH (cross-log, "
                              "not named in log11's own owner review)"),
            "owner_must_answer": ["does log11 share log53's NEXTLINK HH start at STA 21+63=0+00 on sheet 5?"],
            "what_unlocks_if_confirmed": ("both termini modeled (NEXTLINK HH start + FLOWER POT end) -> "
                                          "endpoint-anchor bridge (the log52/log58 lane)")},
        "log47": {
            "log_id": "log47", "sub_category": "JOIN_SOURCE_BACKED_SECOND_TERMINUS_UNNAMED",
            "current_blocker": "ENDPOINT_IDENTITY (end) + start-sheet attribution -- join 10->13->14 source-backed",
            "source_sheets": [10, 13, 14], "run": "STA 3+23 FLOWER POT -> STA 4+94 opposite side of Woodson Ln",
            "exact_missing": ("the START is owner-named FLOWER POT @ 3+23 (but binds on sheet 13, not the stated "
                              "sheet 10); the END 'STA 4+94, opposite side of Woodson Ln' is a BARE station with "
                              "no owner-named structure (an installer_hh binds there but the owner never named it)"),
            "owner_must_answer": ["what named structure is at STA 4+94 opposite Woodson Ln (is it an INSTALLER HH)?",
                                  "is the start FLOWER POT on sheet 13 (where it binds) or sheet 10 (as stated)?"],
            "what_unlocks_if_confirmed": ("both termini modeled + the start sheet fixed -> endpoint-anchor "
                                          "bridge across the source-backed 10->13->14 join")},
    }
    report = {
        "milestone": "CROSS_SHEET BLOCKED evidence-target packet (proof/report only; read-only)",
        "verdict": "PASS" if all_pass else "FAIL",
        "result": result if all_pass else "BLOCKED",
        "class": "CROSS_SHEET_FRAME_JOIN_NEEDED (remaining 6)",
        "included": list(INCLUDED),
        "source_blocked": list(SOURCE_BLOCKED), "identity_held": list(IDENTITY_HELD),
        "log11_log47_determination": ("INCLUDED as owner-confirmation targets: their cross-sheet JOIN is "
                                      "source-backed and one terminus is owner-named flower_pot; only the SECOND "
                                      "terminus identity is unconfirmed -- a distinct sub-category from the "
                                      "source-gap of log48/67/69/70, surfaced together for class-level closure"),
        "evidence_packet": packet,
        "doctrine": {
            "no_encoding": "no endpoint_anchors written; the six stay UNencoded in the reviewed artifact",
            "no_guess": "crossings/equations are EXTRACTED and PRESENTED; this slice never picks a crossing or names a structure",
            "source_untrusted_until_owner_confirmed": True,
            "no_new_frame_math": True, "no_render": True, "no_seam_promotion": True,
            "fixture_unmodified": True, "engine_census_frozen": True,
        },
        "scope_guard": {"product_wiring": False, "broad_renderer": False, "match_review_wiring": False,
                        "runtime_batch": False, "deploy": False, "coordinates_invented": False,
                        "endpoint_anchors_encoded": False},
        "next_slice": ("present this packet to the owner. On each answer: for log48/67/69/70 the chosen/recovered "
                       "crossing makes the frame join source-backed -> endpoint-anchor bridge + sheet-local bind; "
                       "for log11/log47 the confirmed second terminus -> endpoint-anchor bridge across the already-"
                       "source-backed join. Each separately authorized; nothing encoded here."),
        "gates": [{"name": n, "pass": bool(x), "detail": d} for n, x, d in gates],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "cross_sheet_blocked_evidence_packet.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"[xsheet-packet] result: {report['result']}")
    print(f"[xsheet-packet]   source_blocked={list(SOURCE_BLOCKED)}  identity_held={list(IDENTITY_HELD)}")
    if x1720.get("distinct_offsets"):
        print(f"[xsheet-packet]   17<->20 crossings (distinct |offset|): {x1720['distinct_offsets']}")
    for n, x, _ in gates:
        print(f"[xsheet-packet] {'PASS' if x else 'FAIL'}  {n}")
    print(f"[xsheet-packet] VERDICT: {'PASS' if all_pass else 'FAIL'}  (packet: {OUT_DIR})")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
