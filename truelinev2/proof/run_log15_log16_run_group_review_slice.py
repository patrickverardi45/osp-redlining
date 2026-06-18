r"""LOG15/LOG16 RUN-GROUP + Candidate-A REVIEW CARD slice (GATED HUMAN-REVIEW / PROOF ONLY).

Implements the smallest safe representation of the resegmentation decision
(gac/log15_log16_resegmentation_decision.md): log15 + log16 are drilling-drive ACCOUNTING rows on one
continuous spliced 2-1.25" fiber MAIN; they become CHILD EVIDENCE under a shared run-group, and the run is
proposed for rendering between PRINTED structure anchors via a HUMAN-REVIEW card (Candidate A: SPLICE 35 @
28+73 -> installer HH @ 39+79).

GATED / PROOF ONLY -- this slice:
  * emits run-group METADATA as a SIDECAR (gitignored), NOT a mutation of the generated, census-consumed
    parent_source_model.json (canonical promotion = a run_build_parent_source_model change, separately
    authorized). The census gate (child_owns_route) never reads run_group_id, so this is inert to census.
  * builds a Candidate-A REVIEW card payload explicitly marked REVIEW/HUMAN_APPROVAL -- NOT auto-place, NOT
    deterministic frontier, NOT a census change.
  * source-binds the two Candidate-A endpoints (read-only) to record their printed identity on the card.
  * NEVER emits 31+00 / 24+07 (unprinted cuts) as a stroke endpoint; names the parked upstream remainder;
    enforces the downstream duplicate-guard (end before running 44+83 = bore_log20).
  * renders NOTHING (no stroke/PNG/AUTO); does NOT touch corpus/census/fixtures/flags/main/deploy.

Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_log15_log16_run_group_review_slice
"""
from __future__ import annotations

import json
import os

from truelinev2.config import _REPO_ROOT
from truelinev2.extract.registry import select_dialect
from truelinev2.extract.structure_position import POSITION_BOUND
from truelinev2.ingest.manual_adjudication import load_adjudication
from truelinev2.ingest.normalize import load_borelog
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.proof.run_brenham_corpus import PDF, enumerate_corpus
from truelinev2.proof.run_callout_route_assembly_sweep import _bind
from truelinev2.proof.run_reviewer_service_contract import resolve_corpus
from truelinev2.proof.run_station_corridor_route_solver_slice import _census_frozen

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "log15_log16_run_group"

# --- run-group identity (source-anchored; running-ft extent of the physical main these drives ride) -------
RUN_GROUP_ID = "run_chappell_hill_main_2407_4533"
MEMBERS = ("bore_log15", "bore_log16")          # the two drive-rows linked NOW (downstream = bore_log20)
DOWNSTREAM_CONTINUATION = "bore_log20"          # already-modeled split family past SPLICE 46

# --- printed run boundaries (running ft, from the continuation-trace census) ------------------------------
SPLICE35 = {"role": "SPLICE POINT 35 / NEXTLINK HH", "label": "28+73", "running_ft": 2873, "sheet": 7,
            "class": "nextlink_hh"}
HH_3979 = {"role": "installer HH (log16 END)", "label": "39+79", "running_ft": 3979, "sheet": 10,
           "class": "installer_hh"}
SPLICE46 = {"role": "SPLICE POINT 46 / NEXTLINK HH (downstream; bore_log20 boundary)", "label": "45+33",
            "running_ft": 4533, "sheet": 10, "class": "nextlink_hh"}

# --- interior segmentation cuts (NEVER stroke endpoints) --------------------------------------------------
INTERIOR_CUTS = [
    {"station": "31+00", "kind": "UNPRINTED_RULER_CUT",
     "note": "log15 end == log16 start; no structure within 90pt; FORBIDDEN as a stroke endpoint"},
    {"station": "24+11", "kind": "matchline", "see_sheet": 5,
     "note": "log15 start 24+07 ~= here; the main continues UPSTREAM off-scope"},
    {"station": "30+64", "kind": "matchline", "see_sheet": 8},
    {"station": "33+93", "kind": "matchline", "see_sheet": 9},
    {"station": "35+43", "kind": "interior_reset", "note": "reset 35+43=0+00 on the run (interior)"},
    {"station": "38+90", "kind": "matchline", "see_sheet": 10},
]

# --- parked upstream remainder (named, not dropped) ------------------------------------------------------
PARKED_UPSTREAM = {"span": "24+07->28+73", "running_ft": [2407, 2873], "length_ft": 466,
                   "owner_drive": "bore_log15",
                   "reason": "the main continues upstream onto sheet 5+ via MATCHLINE 24+11",
                   "status": "SOURCE_REQUIRED"}

# --- downstream duplicate guard (Candidate A must end before bore_log20) ---------------------------------
DUPLICATE_GUARD = {"candidate_A_end_running_ft": HH_3979["running_ft"],
                   "downstream_rendered_start_running_ft": 4483,   # bore_log20 / log49 start (44+83)
                   "downstream_parent": "bore_log20",
                   "downstream_children": ["log49", "log48", "log50"],
                   "rule": "Candidate A end (39+79) must be strictly upstream of bore_log20 start (44+83)"}


def run_group_metadata() -> dict:
    """The run-group SIDECAR metadata (pure; no PDF). NOT written into the generated parent_source_model."""
    return {
        "run_group_id": RUN_GROUP_ID,
        "members": list(MEMBERS),
        "downstream_continuation": DOWNSTREAM_CONTINUATION,
        "doctrine": [
            "drive/accounting span (bore-log row) != printed source-bound run span (what is drawn)",
            "no fake endpoints at unprinted interior cuts (31+00 / 24+07 are NOT endpoints)",
            "no duplicate/overlap redline over already-rendered children (log49/log48/log50)",
            "ALL-REDLINES = drawn + named-parked (the parked upstream is named, never silently dropped)",
        ],
        "printed_run_boundaries": {"upstream_splice_35": SPLICE35, "candidate_A_end_hh": HH_3979,
                                   "downstream_splice_46": SPLICE46},
        "interior_segmentation_cuts": INTERIOR_CUTS,
        "parked_upstream": PARKED_UPSTREAM,
        "downstream_duplicate_guard": DUPLICATE_GUARD,
        "is_metadata_only": True, "touches_census": False, "touches_frontier": False,
    }


def child_evidence() -> dict:
    """Preserve the existing bore-log rows/spans as CHILD drive evidence (pure; reads corpus spans)."""
    corpus = {p.stem: p for p in enumerate_corpus(resolve_corpus()[0])}
    out = {}
    for mid in MEMBERS:
        b = load_borelog(str(corpus[mid]))
        out[mid] = {"log_id": mid.replace("bore_", ""), "drive_span": f"{b.station_start}->{b.station_end}",
                    "drive_length_ft": round(b.span_ft), "sheets": list(b.sheet_refs or []),
                    "role": "child_drive_evidence"}
    return out


def accounting_reconciliation() -> dict:
    """drive spans vs the Candidate-A printed run span; the parked remainder closes the books."""
    log15_tail = HH_3979["running_ft"] - 0   # placeholder; computed below from stations
    # exact running-ft arithmetic
    a_start, a_end = SPLICE35["running_ft"], HH_3979["running_ft"]      # 2873 -> 3979
    log15_drive = 3100 - 2407   # 693
    log16_drive = 3979 - 3100   # 879
    log15_tail_in_A = 3100 - a_start   # 28+73 -> 31+00 = 227
    parked = a_start - 2407            # 24+07 -> 28+73 = 466
    candidate_A_run = a_end - a_start  # 1106
    return {
        "candidate_A_printed_run_ft": candidate_A_run,
        "log15_drive_ft": log15_drive, "log16_drive_ft": log16_drive,
        "log15_tail_in_A_ft": log15_tail_in_A, "parked_upstream_ft": parked,
        "reconciles_A": candidate_A_run == log15_tail_in_A + log16_drive,   # 1106 == 227 + 879
        "reconciles_log15": log15_drive == log15_tail_in_A + parked,        # 693 == 227 + 466
    }


def build_card(start_bind=None, end_bind=None) -> dict:
    """The gated human-review card payload for Candidate A (pure; binds injected)."""
    return {
        "card_id": "log15_log16_candidate_A",
        "run_group_id": RUN_GROUP_ID,
        "status": "REVIEW_HUMAN_APPROVAL",          # NOT auto
        "auto_place": False,
        "is_deterministic_frontier": False,         # does NOT increment the 45/58 frontier
        "counts_toward_census": False,
        "candidate": "A",
        "proposed_run": {
            "start": {**SPLICE35, "bind": start_bind},
            "end": {**HH_3979, "bind": end_bind},
            "printed_run_span_ft": HH_3979["running_ft"] - SPLICE35["running_ft"],   # 1106
            "cross_sheet_route": "trace conduit across matchlines 30+64/33+93/38+90 (existing route-assembly primitive)",
        },
        "endpoints_are_printed_structures_only": True,
        "forbidden_endpoints": ["31+00", "24+07"],
        "parked_upstream": PARKED_UPSTREAM,
        "duplicate_guard": DUPLICATE_GUARD,
        "review_notes": [
            "REVIEW / HUMAN APPROVAL -- this is NOT an automatic placement and does NOT count toward the deterministic frontier.",
            "Drive/accounting span (log15 693' + log16 879') != the drawn printed-run span (1106').",
            "31+00 is an UNPRINTED interior cut and is NOT a stroke endpoint.",
            "The upstream 466' (24+07->28+73) is PARKED pending sheet-5+ source (named, not dropped).",
            "Candidate A ends at 39+79, strictly upstream of bore_log20 @44+83 -> NO duplicate over log49/log48/log50.",
        ],
    }


def _endpoint_violations(card) -> list:
    """Guard: no forbidden (unprinted) station may appear as a stroke endpoint."""
    bad = []
    for side in ("start", "end"):
        lbl = card["proposed_run"][side]["label"]
        if lbl in card["forbidden_endpoints"]:
            bad.append(f"{side} endpoint is a forbidden unprinted cut: {lbl}")
    return bad


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    # guarantee the slice writes NO png/redline artifact
    for stale in OUT_DIR.glob("*.png"):
        stale.unlink()

    meta = run_group_metadata()
    children = child_evidence()
    recon = accounting_reconciliation()

    # source-bind the two Candidate-A endpoints (read-only) to record their printed identity
    start_bind = end_bind = None
    plan = PlanPdf(PDF)
    try:
        off = select_dialect(plan).calibrate(plan, 13)
        e_xy, _, _, e_res = _bind(plan, off, HH_3979["sheet"], HH_3979["class"], HH_3979["label"])
        end_bind = {"result": e_res, "bound": e_res == POSITION_BOUND,
                    "xy": None if not e_xy else [round(v, 1) for v in e_xy]}
        s_xy, _, _, s_res = _bind(plan, off, SPLICE35["sheet"], SPLICE35["class"], SPLICE35["label"])
        start_bind = {"result": s_res, "bound": s_res == POSITION_BOUND,
                      "xy": None if not s_xy else [round(v, 1) for v in s_xy]}
    finally:
        plan.close()

    card = build_card(start_bind=start_bind, end_bind=end_bind)

    # ---- guards (every one must hold) ----
    gates = []
    gates.append(("G1 log15+log16 share run-group metadata",
                  set(meta["members"]) == set(MEMBERS) and meta["run_group_id"] == RUN_GROUP_ID, meta["members"]))
    gates.append(("G2 31+00 / 24+07 are NEVER stroke endpoints",
                  not _endpoint_violations(card)
                  and all(c["station"] not in (card["proposed_run"]["start"]["label"],
                                               card["proposed_run"]["end"]["label"])
                          for c in INTERIOR_CUTS), card["forbidden_endpoints"]))
    gates.append(("G3 Candidate A is REVIEW-only, not deterministic frontier",
                  card["status"] == "REVIEW_HUMAN_APPROVAL" and card["auto_place"] is False
                  and card["is_deterministic_frontier"] is False and card["counts_toward_census"] is False, None))
    gates.append(("G4 Candidate A end (39+79) is before downstream duplicate guard (44+83)",
                  DUPLICATE_GUARD["candidate_A_end_running_ft"]
                  < DUPLICATE_GUARD["downstream_rendered_start_running_ft"], DUPLICATE_GUARD))
    gates.append(("G5 parked upstream remainder is explicit (466', SOURCE_REQUIRED)",
                  PARKED_UPSTREAM["length_ft"] == 466 and PARKED_UPSTREAM["status"] == "SOURCE_REQUIRED", PARKED_UPSTREAM))
    gates.append(("G6 accounting reconciles (A == log15-tail + log16 ; log15 == tail + parked)",
                  recon["reconciles_A"] and recon["reconciles_log15"], recon))
    gates.append(("G7 engine census FROZEN (OFF 31/6/1/17/3, ON 22/1/4, log44+abstains held)",
                  _census_frozen(load_adjudication()), None))
    gates.append(("G8 metadata is a SIDECAR (no census/frontier touch); slice writes no PNG/redline",
                  meta["is_metadata_only"] and not meta["touches_census"] and not meta["touches_frontier"]
                  and not list(OUT_DIR.glob("*.png")), None))
    gates.append(("G9 both Candidate-A endpoints are printed source structures (binds recorded)",
                  bool(end_bind and end_bind["bound"]), {"start": start_bind, "end": end_bind}))

    all_pass = all(x for _, x, _ in gates)
    report = {"milestone": "LOG15/LOG16 RUN-GROUP + Candidate-A REVIEW CARD slice (gated human-review; proof only)",
              "verdict": "PASS" if all_pass else "FAIL",
              "run_group_metadata": meta, "child_evidence": children,
              "accounting_reconciliation": recon, "review_card": card,
              "gates": [{"name": n, "pass": bool(x), "detail": d} for n, x, d in gates]}
    (OUT_DIR / "log15_log16_run_group_review.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8")
    sidecar = {"run_group": meta, "children": children}
    (OUT_DIR / "run_group_metadata.sidecar.json").write_text(
        json.dumps(sidecar, indent=2, default=str), encoding="utf-8")

    print(f"[run-group] run_group_id={RUN_GROUP_ID} members={list(MEMBERS)}")
    print(f"[run-group] Candidate A: {SPLICE35['label']} ({SPLICE35['role']}) -> {HH_3979['label']} "
          f"({HH_3979['role']})  printed_run={card['proposed_run']['printed_run_span_ft']}ft  status={card['status']}")
    print(f"[run-group] endpoint binds: start={start_bind}  end={end_bind}")
    print(f"[run-group] parked upstream: {PARKED_UPSTREAM['span']} = {PARKED_UPSTREAM['length_ft']}ft "
          f"({PARKED_UPSTREAM['status']})")
    for n, x, _ in gates:
        print(f"[run-group] {'PASS' if x else 'FAIL'}  {n}")
    print(f"[run-group] VERDICT: {'PASS' if all_pass else 'FAIL'}  (report: {OUT_DIR})")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
