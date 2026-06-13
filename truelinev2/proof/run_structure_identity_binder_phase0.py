r"""M9.8 Phase 0 -- STRUCTURE-IDENTITY BINDER feasibility (proof-only / read-only).

Decides whether the shipped M9.3.1 endpoint-attribution primitive can be generalized
from per-endpoint attribution into a per-CANDIDATE-FRAME discriminator that REDUCES
review-only state (pick-card / human-adjustable) WITHOUT guessing -- i.e. picks the one
frame that carries this bore's terminal-class AP+splice (FULL_PAIR) identity.

THE BINDER (zero-false; reuses the SHIPPED M9.3.1 primitives unchanged):
  For a review-only bore, enumerate its CANDIDATE FRAMES (the M8.9 frame_ownership
  candidate_frames -- the sheet-local tick clusters whose drawn axis contains the bore
  END). For EACH candidate SHEET SEPARATELY, run TA.detect_endpoint_note +
  TA.attribute_endpoint at the bore END station. A sheet carries a TERMINAL IDENTITY iff
  that single-sheet attribution returns ENDPOINT_ATTRIBUTED (terminal class + FULL_PAIR
  AP+splice; partials return NO_AP_SPLICE_PAIR, wrong class returns NON_TERMINAL_ENDPOINT).
  BIND iff EXACTLY ONE candidate sheet carries a terminal identity; 0 -> ABSTAIN; >=2 ->
  ABSTAIN (fork); a PDF<->KMZ contradiction -> ABSTAIN (source contradiction).

  NEVER: proximity, length/footage agreement, nearest-of-N, AP-only, splice-only. The bind
  signal is printed terminal-class FULL_PAIR identity ON a specific sheet -- nothing else.

  This STRENGTHENS M9.3.1's union scan: M9.3.1 reads the bore's referenced sheets together
  and first-binds; the binder evaluates EACH candidate SHEET independently and refuses unless
  the identity is on exactly one. It thereby catches a cross-sheet >=2 identity fork the union
  scan would mask (synthetic-verified; no such fork occurs in this corpus). SCOPE/PRECISION:
  an M8.9 "frame" is a tick CLUSTER and the binder keys on SHEET -- lossless HERE because no
  candidate sheet hosts >1 cluster (gated, G10b); and it resolves WHICH sheet, never WHICH
  interval within a sheet, so it CANNOT resolve a within-frame interval fork (the parallel-run
  cases log5/11/36/59/66, whose real ambiguity is >=2 holding intervals on one sheet).

MEASURED RESULT (Brenham, live):
  * POSITIVE CONTROL log12 (HUMAN_ADJUSTABLE, "2 frames plausible") -> BIND@sheet 3:
    AP-121 SPLICE LOC 28 prints on sheet 3 only (candidate frames {2,3}); the binder
    resolves the frame question zero-false. CAVEAT: sheet 3 carries 2 holding intervals,
    so the FRAME-IDENTITY is bound but a residual within-frame interval fork remains --
    the binder does NOT by itself promote log12 to PLACED (route still not unique).
  * 10 pick-card candidates (log5/11/36/59/66 parallel-runs; log6/41/58/63/64 multi-frame)
    -> ALL ABSTAIN_NO_TERMINAL_IDENTITY: zero candidate frames carry a terminal FULL_PAIR
    note at the bore end. Causal, not coincidental -- a bore is a pick-card BECAUSE its end
    prints no terminal AP+splice (the M8.26 honest-negative wall); that same absence denies
    the attribution a FULL_PAIR. None of the 10 is in the 7 M9.3.1 clean-END set.

VERDICT: STRUCTURE_IDENTITY_BINDER_FEASIBLE_YIELD_1 -- the binder is a sound, zero-false
frame/terminal-identity discriminator, but its corpus yield is ONLY the positive control
(1 frame-identity bind, log12), and even that is a frame fact not a placement; 0 of the 10
pick-cards resolve. This is effectively another honest-negative for broad review reduction
(consistent with M9.5 / M8.26): engine headroom on the current printed evidence is
near-exhausted. NO product bucket moved; NO bore promoted in Phase 0.

PROOF-ONLY: no placement, no wiring, no AUTO, no geometry/strokes/PNG, no reviewer-service,
no UI/API, no deploy; reads the SHIPPED M8.9 candidate_frames + M9.3.1 attribution and the
M8.27 truth table, changes none of them; zero bores moved.

Exit codes: 0 PASS, 2 inputs missing, 3 corpus drift, 4 gate FAILURE.

Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_structure_identity_binder_phase0
"""
from __future__ import annotations

import glob
import inspect
import json
import os
import re
from typing import Dict, List, Optional, Sequence, Tuple

from truelinev2.config import Settings, _REPO_ROOT
from truelinev2.extract.kmz import BRENHAM_KMZ_DIALECT, read_kmz
from truelinev2.extract.registry import select_dialect
from truelinev2.extract.station_axis import parse_tick
from truelinev2.extract.terminus_profile import BRENHAM_TERMINUS_PROFILE
from truelinev2.ingest.normalize import load_borelog
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.match import terminus_attribution as TA
from truelinev2.proof.frame_ownership_candidates import candidate_frames
from truelinev2.proof.run_brenham_corpus import EXPECTED_COUNT, PDF, enumerate_corpus
from truelinev2.proof.run_kmz_correlation_audit import resolve_kmz
from truelinev2.proof.run_reviewer_service_contract import resolve_corpus
from truelinev2.proof.station_equation_ownership import extract_reset_origins, parse_hh_distances
from truelinev2.stations import feet_to_station

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "structure_identity_binder_phase0"

# verdict tokens (the task's closed set)
FEASIBLE = "STRUCTURE_IDENTITY_BINDER_FEASIBLE_YIELD_N"   # N substituted at emit time
HONEST_NEGATIVE = "HONEST_NEGATIVE_NO_SAFE_YIELD"
BLOCKED = "BLOCKED_NEEDS_SOURCE_REREAD"

# per-bore binder verdicts
BIND = "BIND"
ABSTAIN_NONE = "ABSTAIN_NO_TERMINAL_IDENTITY"
ABSTAIN_FORK = "ABSTAIN_IDENTITY_FORK"
ABSTAIN_CONTRA = "ABSTAIN_SOURCE_CONTRADICTION"

POSITIVE_CONTROL = "log12"
PARALLEL_RUN_CANDIDATES = ["log5", "log11", "log36", "log59", "log66"]
MULTI_FRAME_CANDIDATES = ["log6", "log41", "log58", "log63", "log64"]
PICK_CARD_CANDIDATES = PARALLEL_RUN_CANDIDATES + MULTI_FRAME_CANDIDATES
ALL_CANDIDATES = [POSITIVE_CONTROL] + PICK_CARD_CANDIDATES

EXPECT_BUCKET = {  # the M8.27 completion bucket each candidate must currently sit in
    "log12": "HUMAN_ADJUSTABLE_REVIEW",
    **{b: "PICK_CARD_REVIEW" for b in PICK_CARD_CANDIDATES},
}
EXPECT_DRAWABLE = 30


def _code_only(src: str) -> str:
    """Strip docstrings + line comments so a drift guard scans CODE, never prose
    (the helpers' docstrings honestly enumerate the forbidden operations they avoid)."""
    src = re.sub(r'(?s)""".*?"""', "", src)
    src = re.sub(r"(?s)'''.*?'''", "", src)
    src = re.sub(r"#.*", "", src)
    return src


# ---- pure binder helpers (testable offline) ---------------------------------

def frame_terminal_identities(end_station: str,
                              lines_by_sheet: Dict[int, Sequence[str]],
                              profile, kmz_model=None
                              ) -> Tuple[List[tuple], bool]:
    """For EACH frame (sheet) separately, run the SHIPPED M9.3.1 terminal-note
    attribution at ``end_station``. Returns (identities, contradiction) where
    identities is a list of (sheet, ap, splice, kmz_join) for frames whose END note
    is a terminal-class FULL_PAIR (ENDPOINT_ATTRIBUTED). FULL_PAIR only (AP+splice);
    AP-only/splice-only/partial -> NO_AP_SPLICE_PAIR (not an identity); wrong class ->
    NON_TERMINAL_ENDPOINT (not an identity). No proximity, no length, no nearest."""
    identities: List[tuple] = []
    contradiction = False
    for sheet, lines in lines_by_sheet.items():
        note, competing = TA.detect_endpoint_note({sheet: lines}, end_station, profile)
        att = TA.attribute_endpoint("END", end_station, note, competing,
                                    terminal_class=profile.terminal_class, kmz_model=kmz_model)
        if att.result == TA.ENDPOINT_ATTRIBUTED:
            identities.append((sheet, att.ap, att.splice, att.kmz_join))
        elif att.result == TA.PDF_KMZ_CONTRADICTION:
            contradiction = True
    return identities, contradiction


def bind_verdict(identities: List[tuple], contradiction: bool) -> Tuple[str, Optional[tuple]]:
    """Exactly-one terminal identity is the ONLY bind path. 0 -> ABSTAIN_NONE; >=2 ->
    ABSTAIN_FORK; contradiction -> ABSTAIN_CONTRA. Never binds on count/length/nearness."""
    if contradiction:
        return ABSTAIN_CONTRA, None
    if len(identities) == 0:
        return ABSTAIN_NONE, None
    if len(identities) >= 2:
        return ABSTAIN_FORK, None
    return BIND, identities[0]


# ---- harness (per-bore candidate frames, mirroring the M8.9 runner) ----------

def _bore_candidate_frames(bore, plan, dialect, offset):
    axis_sheets = sorted({x for r in bore.sheet_refs for x in (r - 1, r, r + 1) if x >= 1})
    ticks_by_sheet = {s: tuple(t for t in (parse_tick(w["text"]) for w in plan.words(s, offset))
                               if t is not None) for s in axis_sheets}
    callouts = [c for s in axis_sheets for c in dialect.extract_callouts(plan, s, offset)]
    origins, hh = [], {}
    for s in axis_sheets:
        lines = plan.lines(s, offset)
        origins.extend(extract_reset_origins(lines, s))
        notes = parse_hh_distances(" ".join(lines))
        if notes:
            hh[s] = notes
    return candidate_frames(bore_start_ft=bore.station_start_ft, bore_end_ft=bore.station_end_ft,
                            span_ft=bore.span_ft, ticks_by_sheet=ticks_by_sheet, callouts=callouts,
                            origins=origins, hh_notes_by_sheet=hh, sheet_refs=list(bore.sheet_refs))


# ---- synthetic gate fixtures (BRENHAM grammar; terminal class PORT HH) -------

def _terminal_note_lines(sta: str, ap: int = 999, splice: int = 99) -> List[str]:
    return [f"STA {sta}", f"PORT HH AP-{ap} SPLICE LOC {splice}"]

def _run_callout_lines(sta: str) -> List[str]:
    return [f"STA {sta} TO STA 9+99 - 1.25\" HDPE"]                 # a run callout, NOT a note

def _ap_only_lines(sta: str) -> List[str]:
    return [f"STA {sta}", "PORT HH AP-999"]                          # AP-only -> not FULL_PAIR

def _splice_only_lines(sta: str) -> List[str]:
    return [f"STA {sta}", "PORT HH SPLICE LOC 99"]                   # splice-only -> not FULL_PAIR

def _non_terminal_lines(sta: str) -> List[str]:
    return [f"STA {sta}", "INSTALLER HH AP-999 SPLICE LOC 99"]       # wrong class -> not terminal


def _synthetic_gates(profile) -> dict:
    sta = "4+51"
    pos = frame_terminal_identities(sta, {3: _terminal_note_lines(sta), 2: _run_callout_lines(sta)}, profile)
    none0 = frame_terminal_identities(sta, {2: _run_callout_lines(sta), 5: _run_callout_lines(sta)}, profile)
    fork = frame_terminal_identities(sta, {2: _terminal_note_lines(sta, 111), 3: _terminal_note_lines(sta, 222)}, profile)
    ap_only = frame_terminal_identities(sta, {3: _ap_only_lines(sta)}, profile)
    sp_only = frame_terminal_identities(sta, {3: _splice_only_lines(sta)}, profile)
    nonterm = frame_terminal_identities(sta, {3: _non_terminal_lines(sta)}, profile)
    # "nearest/length decoy": a frame with NO terminal note is never an identity, however near.
    decoy = frame_terminal_identities(sta, {99: _run_callout_lines(sta)}, profile)
    return {
        "positive_exactly_one": bind_verdict(*pos)[0] == BIND and pos[0][0][0] == 3,
        "zero_identities": bind_verdict(*none0)[0] == ABSTAIN_NONE,
        "two_identities_fork": bind_verdict(*fork)[0] == ABSTAIN_FORK,
        "ap_only_abstains": bind_verdict(*ap_only)[0] == ABSTAIN_NONE,
        "splice_only_abstains": bind_verdict(*sp_only)[0] == ABSTAIN_NONE,
        "non_terminal_class_abstains": bind_verdict(*nonterm)[0] == ABSTAIN_NONE,
        "nearest_length_decoy_abstains": bind_verdict(*decoy)[0] == ABSTAIN_NONE,
        "contradiction_abstains": bind_verdict([], True)[0] == ABSTAIN_CONTRA,
    }


def main() -> int:
    kmz_path, kmz_how = resolve_kmz()
    corpus_dir, how = resolve_corpus()
    print(f"[m9.8] kmz   : {kmz_path}  ({kmz_how})")
    print(f"[m9.8] corpus: {corpus_dir}  ({how})")
    if not os.path.isfile(kmz_path) or not os.path.isfile(PDF) or not os.path.isdir(corpus_dir):
        print("[m9.8] STOP: inputs missing")
        return 2
    paths = enumerate_corpus(corpus_dir)
    if len(paths) != EXPECTED_COUNT:
        print(f"[m9.8] STOP: corpus drift ({len(paths)})")
        return 3
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ok = True

    # ---- G1: live M8.27 truth table loaded; candidate set matches the review map -
    m827 = glob.glob(str(_REPO_ROOT / "data" / "outputs" / "final_engine_truth_table" / "*.json"))
    if not m827:
        print("[m9.8] STOP: M8.27 truth table JSON missing (run run_final_engine_truth_table first)")
        return 2
    tt = json.load(open(m827[0], encoding="utf-8"))
    bucket_by_bore = {r["bore_id"]: r["completion_bucket"] for r in tt["rows"]}
    drawable = sum(1 for v in bucket_by_bore.values() if v == "DRAWABLE_REVIEW")
    g1 = (all(bucket_by_bore.get(b) == EXPECT_BUCKET[b] for b in ALL_CANDIDATES)
          and drawable == EXPECT_DRAWABLE)
    print(f"[m9.8] {'PASS' if g1 else 'FAIL'}  G1 M8.27 loaded; candidates in expected buckets; "
          f"DRAWABLE={drawable}")
    ok &= g1

    # ---- G2: reuse M9.3.1 primitives unchanged; no proximity/length/nearest in binder
    # (scan CODE only -- the docstrings honestly say "no proximity/length/nearest", which
    # must not trip the drift guard.)
    binder_src = inspect.getsource(frame_terminal_identities) + inspect.getsource(bind_verdict)
    binder_code = _code_only(binder_src)
    forbidden = re.compile(r"(?i)proximit|distance|nearest|length|footage|closest|snap")
    g2 = ("TA.detect_endpoint_note" in binder_code and "TA.attribute_endpoint" in binder_code
          and not forbidden.search(binder_code))
    print(f"[m9.8] {'PASS' if g2 else 'FAIL'}  G2 binder reuses M9.3.1 detect+attribute; "
          f"0 proximity/length/nearest tokens")
    ok &= g2

    # ---- G3/G4: synthetic positive + negatives ------------------------------
    syn = _synthetic_gates(BRENHAM_TERMINUS_PROFILE)
    g3 = syn["positive_exactly_one"]
    print(f"[m9.8] {'PASS' if g3 else 'FAIL'}  G3 synthetic positive: exactly-one terminal "
          f"identity -> BIND@correct frame")
    ok &= g3
    g4 = all(v for k, v in syn.items() if k != "positive_exactly_one")
    print(f"[m9.8] {'PASS' if g4 else 'FAIL'}  G4 synthetic negatives all ABSTAIN: "
          f"{ {k: v for k, v in syn.items() if k != 'positive_exactly_one'} }")
    ok &= g4

    # ---- live sweep over the 11 candidates ----------------------------------
    model = read_kmz(kmz_path, BRENHAM_KMZ_DIALECT)
    settings = Settings.for_proof()
    plan = PlanPdf(PDF)
    rows: List[dict] = []
    try:
        dialect = select_dialect(plan)
        offset = dialect.calibrate(plan, settings.sheet_offset)
        bore_by_id = {}
        for p in paths:
            try:
                b = load_borelog(str(p))
            except Exception:
                continue
            bore_by_id[b.bore_id] = b
        for bid in ALL_CANDIDATES:
            b = bore_by_id.get(bid)
            if b is None:
                rows.append({"bore_id": bid, "verdict": "MISSING"}); continue
            end_sta = feet_to_station(b.station_end_ft)
            cands = _bore_candidate_frames(b, plan, dialect, offset)
            cand_sheets = sorted({c.sheet for c in cands})
            n_holding = {c.sheet: c.n_holding_intervals for c in cands}
            lbs = {s: plan.lines(s, offset) for s in cand_sheets}
            ids, contra = frame_terminal_identities(end_sta, lbs, BRENHAM_TERMINUS_PROFILE, model)
            verdict, bound = bind_verdict(ids, contra)
            bound_sheet = bound[0] if bound else None
            route_unique = (bound_sheet is not None and n_holding.get(bound_sheet) == 1)
            # per-sheet == per-frame only when no candidate sheet hosts >1 tick cluster
            # (an M8.9 "frame" is a TickCluster; the binder keys on sheet). Measured, gated.
            same_sheet_multi_cluster = len(cands) != len(cand_sheets)
            parallel = bid in PARALLEL_RUN_CANDIDATES
            ambiguity_class = ("positive_control" if bid == POSITIVE_CONTROL else
                               "parallel_run_within_frame" if parallel else "multi_frame")
            reason = (None if verdict == BIND else
                      "no candidate frame prints a terminal-class AP+splice (FULL_PAIR) note at the bore end"
                      if verdict == ABSTAIN_NONE else
                      ">=2 candidate frames each print a terminal identity (genuine fork)"
                      if verdict == ABSTAIN_FORK else
                      "PDF<->KMZ terminal contradiction -> owner source re-read")
            if verdict == ABSTAIN_NONE and parallel:
                reason += ("; NOTE the real ambiguity for this parallel-run bore is WITHIN-frame "
                           "(>=2 holding intervals) -- a per-frame terminal-identity binder is "
                           "structurally incapable of resolving a within-frame interval fork even "
                           "given an identity (it resolves WHICH sheet, never WHICH interval)")
            rows.append({
                "bore_id": bid, "bucket": bucket_by_bore.get(bid), "end_sta": end_sta,
                "sheet_refs": list(b.sheet_refs), "candidate_frames": cand_sheets,
                "ambiguity_class": ambiguity_class,
                "n_holding_intervals": n_holding,
                "same_sheet_multi_cluster": same_sheet_multi_cluster,
                "identities": [(s, ap, sp) for (s, ap, sp, j) in ids],
                "verdict": verdict, "bound_frame": bound_sheet,
                "bound_route_unique": route_unique,
                "abstain_reason": reason,
                "missing_evidence_target": (None if verdict == BIND else
                    "a printed terminal-class AP+splice note at the bore end on exactly one "
                    "candidate frame (the M8.26 end-identity wall) -- owner source re-read or new coverage"),
            })
    finally:
        plan.close()

    by_id = {r["bore_id"]: r for r in rows}

    # ---- G5: real positive control -----------------------------------------
    pc = by_id[POSITIVE_CONTROL]
    g5 = (pc["verdict"] == BIND and pc["bound_frame"] == 3
          and pc["identities"] and pc["identities"][0][1] == 121)
    print(f"[m9.8] {'PASS' if g5 else 'FAIL'}  G5 positive control log12 -> {pc['verdict']} "
          f"@s{pc['bound_frame']} (AP {pc['identities'][0][1] if pc['identities'] else None}); "
          f"route_unique={pc['bound_route_unique']}")
    ok &= g5

    # ---- G6: real pick-card sweep ------------------------------------------
    pc_verdicts = {b: by_id[b]["verdict"] for b in PICK_CARD_CANDIDATES}
    g6 = all(v == ABSTAIN_NONE for v in pc_verdicts.values())
    print(f"[m9.8] {'PASS' if g6 else 'FAIL'}  G6 10 pick-cards all ABSTAIN_NO_TERMINAL_IDENTITY: "
          f"{pc_verdicts}")
    ok &= g6

    # ---- yield ---------------------------------------------------------------
    binds = [r["bore_id"] for r in rows if r["verdict"] == BIND]
    N = len(binds)
    route_unique_binds = [r["bore_id"] for r in rows if r["verdict"] == BIND and r["bound_route_unique"]]
    new_pickcards_resolved = [b for b in PICK_CARD_CANDIDATES if by_id[b]["verdict"] == BIND]

    # ---- G7: 30 placed unchanged (binder is read-only) ----------------------
    g7 = drawable == EXPECT_DRAWABLE and not new_pickcards_resolved  # no candidate left its bucket
    print(f"[m9.8] {'PASS' if g7 else 'FAIL'}  G7 30 placed unchanged; no candidate promoted in "
          f"Phase 0 (binder is read-only evidence)")
    ok &= g7

    # ---- G8: no product bucket movement ------------------------------------
    g8 = all(r.get("bucket") == EXPECT_BUCKET.get(r["bore_id"]) for r in rows if r["bore_id"] in EXPECT_BUCKET)
    print(f"[m9.8] {'PASS' if g8 else 'FAIL'}  G8 no product-bucket movement (all candidates still in "
          f"their M8.27 bucket)")
    ok &= g8

    # ---- G9: posture -- no AUTO/geometry/render/reviewer-service/UI/API ------
    # scan the BIND helpers + the candidate-frame harness CODE (NOT the whole module, which
    # would self-match the guard's own check strings). The forbidden-token regex (G2) stays
    # scoped to the bind DECISION helpers because _bore_candidate_frames legitimately calls the
    # SHIPPED parse_hh_distances ("distance") for evidence-gathering -- not proximity binding.
    posture_code = binder_code + _code_only(inspect.getsource(_bore_candidate_frames))
    g9 = (not list(OUT_DIR.glob("*.png"))
          and "run_match" not in posture_code and "resolve_bore" not in posture_code
          and "render" not in posture_code and "AUTO" not in posture_code
          and "Status" not in posture_code and "reviewer_service" not in posture_code)
    print(f"[m9.8] {'PASS' if g9 else 'FAIL'}  G9 posture: no PNG/AUTO/geometry/render/placement/"
          f"reviewer-service in the binder")
    ok &= g9

    # ---- G10b: per-sheet == per-frame (no candidate sheet hosts >1 tick cluster) ---
    # an M8.9 "frame" is a TickCluster; the binder keys on SHEET. Lossless iff no candidate
    # sheet carries >1 cluster -- MEASURED here so the per-sheet collapse is gated, not assumed.
    multi = [r["bore_id"] for r in rows if r.get("same_sheet_multi_cluster")]
    g10b = not multi
    print(f"[m9.8] {'PASS' if g10b else 'FAIL'}  G10b per-sheet==per-frame: no candidate sheet hosts "
          f">1 tick cluster (lossless per-sheet binding); multi-cluster bores={multi}")
    ok &= g10b

    # ---- G10: yield report (printed) ----------------------------------------
    print(f"[m9.8] G10 yield report:")
    for r in rows:
        print(f"        {r['bore_id']:7s} [{r.get('bucket')}] cand_frames={r.get('candidate_frames')} "
              f"identities={r.get('identities')} -> {r['verdict']}"
              + (f" @s{r['bound_frame']} (route_unique={r['bound_route_unique']})" if r['verdict'] == BIND else ""))

    # ---- G11: derived verdict ----------------------------------------------
    any_contra = any(r["verdict"] == ABSTAIN_CONTRA for r in rows)
    if N >= 1:
        verdict = FEASIBLE.replace("_N", f"_{N}")
    elif any_contra and not binds:
        verdict = BLOCKED
    else:
        verdict = HONEST_NEGATIVE
    g11 = (verdict == "STRUCTURE_IDENTITY_BINDER_FEASIBLE_YIELD_1" and binds == [POSITIVE_CONTROL]
           and not new_pickcards_resolved)
    print(f"[m9.8] {'PASS' if g11 else 'FAIL'}  G11 verdict={verdict} (binds={binds}; "
          f"route_unique_binds={route_unique_binds}; new_pickcards_resolved={new_pickcards_resolved})")
    ok &= g11

    report = {
        "milestone": ("truelinev2 M9.8 Phase 0 -- STRUCTURE-IDENTITY BINDER feasibility "
                      "(proof-only; per-candidate-frame terminal-identity discriminator; zero bores moved)"),
        "kmz_path": kmz_path, "corpus_dir": corpus_dir, "plan_pdf": PDF,
        "verdict": verdict if ok else "FAILURE",
        "yield_N": N,
        "frame_identity_yield_N": N,         # N = zero-false FRAME-identity binds (NOT placements)
        "product_yield": len(route_unique_binds),   # bores actually promotable to PLACED = 0
        "frame_identity_binds": binds,
        "route_unique_binds": route_unique_binds,
        "new_pick_cards_resolved": new_pickcards_resolved,
        "per_sheet_equals_per_frame": g10b,  # gated: no candidate sheet hosts >1 tick cluster
        "synthetic_gates": syn,
        "positive_control": pc,
        "per_candidate": rows,
        "honest_caveat": ("yield_N counts zero-false FRAME-identity binds, NOT placements: "
                          "product_yield is 0 (no bore promoted, no bucket moved). The only bind is the "
                          "positive control log12 (a FRAME/terminal-identity fact: AP-121 on sheet 3 only); "
                          "its bound frame carries 2 holding intervals, so a residual within-frame interval "
                          "fork remains -- the frame-bind does NOT alone promote log12 to PLACED (it stays "
                          "HUMAN_ADJUSTABLE). The 5 parallel-run pick-cards (log5/11/36/59/66) print no "
                          "terminal AP+splice at their end AND their real fork is WITHIN-frame (>=2 holding "
                          "intervals) -- a per-frame binder is structurally incapable of resolving a within-"
                          "frame interval fork even given an identity. The 5 multi-frame pick-cards "
                          "(log6/41/58/63/64) likewise print no terminal identity in any candidate frame "
                          "(the M8.26 wall). The cross-sheet >=2-identity fork the per-sheet binder would "
                          "catch is synthetic-verified only (no such fork occurs in this corpus). Engine "
                          "headroom on current printed evidence is near-exhausted; further yield needs owner "
                          "source re-reads / new printed coverage, not a new solver."),
        "bores_moved": 0, "product_bucket_changes": 0, "read_only": True, "auto": False,
        "next_step": ("if log12's residual interval fork is later resolved (a within-frame route "
                      "discriminator) AND a separately-authorized wiring step is approved, the frame-"
                      "identity fact could promote log12; the 10 pick-cards remain owner-source/"
                      "coverage-gated. No wiring in this milestone."),
    }
    (OUT_DIR / "structure_identity_binder_phase0.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"\n[m9.8] verdict: {report['verdict']}  (yield N={N}: {binds})")
    print(f"[m9.8] report -> {OUT_DIR / 'structure_identity_binder_phase0.json'}")
    return 0 if ok else 4


if __name__ == "__main__":
    raise SystemExit(main())
