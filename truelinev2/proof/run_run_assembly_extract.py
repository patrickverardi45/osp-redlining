r"""M9.4.1 -- RUN_ASSEMBLY extractor proof (drives the SHIPPED core).

Exercises the convention-agnostic core (match/run_assembly.py) over the full Brenham
corpus through the injected BRENHAM_TERMINUS_PROFILE. The M9.4 Phase-0 conclusions
reproduce through shipped engine code with the core holding zero plan-set literals:
the 3 bore-to-bore junctions resolve to exactly 2 RUN_ASSEMBLY_REVIEW_CANDIDATEs
(log10->log27, log72->log39) + 1 JUNCTION_DROP_BRANCH (log7->log65). The M9.4.1
capability OVER Phase 0:
  * the drop-marker grammar is PROFILE-INJECTED (the core holds no 'FOR FIBER DROP');
  * the competing guard enumerates the physical departures WITHIN THE TERMINAL'S OWN
    FRAME (the END bore's sheets), not only JUNCTION_ORIGIN starts -- on Brenham that is
    1 per terminal (the log7->log65 fiber-drop callout is claimed by log65, not an extra
    lateral), preserving the 3 relations while CLOSING the same-frame Phase-0 gap. NAMED
    LIMITATION (still open): a matchline-adjacent lateral drawn SOLELY on a sheet outside
    the END bore's frame is not yet enumerated (a station token is frame-local; a corpus-
    wide scan would false-positive -- the M9.2 trap); the cross-sheet case needs the M9.2
    frame-equation graph -- a separate, justified step, never a silent widen;
  * the evidence is surfaced as a NEW M8.20-style review card -- REVIEW/evidence-only,
    no geometry, no AUTO, never a per-bore bucket change.

PROOF-ONLY: no placement, no engine wiring, no stroke/PNG/segment, no AUTO, no
tolerance/budget change, zero bores moved. The core is UNWIRED (no resolve_bore /
sweep / reviewer service / engine / run_match imports it; no opt-in flag). M8.27
census + product lanes + M9.0/M9.1/M9.2/M9.3/M9.3.1 + the M9.4 Phase-0 boundary frozen.
(The synthetic non-Brenham universality -- a different injected drop marker, a
competing unclaimed lateral -> COMPETING, every typed blocker -- is pinned offline in
tests/test_run_assembly.py.)

Exit codes: 0 PASS, 2 inputs missing, 3 corpus drift, 4 gate FAILURE.

Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_run_assembly_extract
"""
from __future__ import annotations

import collections
import dataclasses
import inspect
import json
import os
import re
from typing import Dict, List

from truelinev2.config import _REPO_ROOT
from truelinev2.extract.kmz import BRENHAM_KMZ_DIALECT, read_kmz
from truelinev2.extract.registry import select_dialect
from truelinev2.extract.terminus_profile import BRENHAM_TERMINUS_PROFILE
from truelinev2.ingest.normalize import load_borelog
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.match import run_assembly as RA
from truelinev2.match import terminus_attribution as TA
from truelinev2.proof.run_brenham_corpus import EXPECTED_COUNT, PDF, enumerate_corpus
from truelinev2.proof.run_final_engine_truth_table import completion_bucket
from truelinev2.proof.run_kmz_correlation_audit import resolve_kmz
from truelinev2.proof.run_reviewer_service_contract import resolve_corpus
from truelinev2.proof.run_run_assembly_phase0 import (EXPECT_CLEAN_END,
                                                      EXPECT_JUNCTIONS,
                                                      M92_NO_EQUATION)
from truelinev2.review.reviewer_service import ReviewerBundleService, ReviewRunMode
from truelinev2.review.run_assembly_review import (CONTINUATION_CANDIDATE,
                                                   DROP_BRANCH,
                                                   build_run_assembly_cards)
from truelinev2.stations import feet_to_station

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "run_assembly_extract"

EXPECT_STRUCTURES = 576
EXPECT_ROUTES = 539
BANKED_FULLEST_LANES = {
    "PLACED_REVIEW": 30, "PICK_CARD_ROUTE_SUGGESTION": 16,
    "HUMAN_ADJUSTABLE_LENGTH_REDLINE": 6, "OUT_OF_CLASS": 4,
    "SOURCE_REVIEW_REQUIRED": 2,
}
SOURCE_CONTRADICTION_BORES = {"log44"}                 # banked M8.25/M9.0
EXPECT_BORE_CENSUS = {
    "ENDPOINT_ATTRIBUTED": 7, "JUNCTION_ORIGIN": 3, "PDF_KMZ_CONTRADICTION": 1,
    "SOURCE_CONTRADICTION": 1, "SHEET_NEIGHBOR_REJECTED": 44,
}
EXPECT_CANDIDATES = {("log10", "log27"), ("log72", "log39")}
EXPECT_DROPS = {("log7", "log65")}
# customer-literal guard mirror + the drop literal that MUST be injected (not in core)
FORBIDDEN = re.compile(r"(?i)\b(brenham|odot|tulsa|creek|nextlink|verofy)\b")
CORE_PLAN_VOCAB = ("FOR FIBER DROP", "terminal_port_hh", "FLOWER POT",
                   "INSTALLER HH", "PORT HH", "SPLICE LOC", "AP-")


def _lines_by_sheet(plan, bore, offset) -> Dict[int, list]:
    return {s: plan.lines(s, offset) for s in sorted(set(bore.sheet_refs))}


def main() -> int:
    kmz_path, kmz_how = resolve_kmz()
    corpus_dir, how = resolve_corpus()
    print(f"[m9.4.1] kmz   : {kmz_path}  ({kmz_how})")
    print(f"[m9.4.1] corpus: {corpus_dir}  ({how})")
    if not os.path.isfile(kmz_path) or not os.path.isfile(PDF) \
            or not os.path.isdir(corpus_dir):
        print("[m9.4.1] STOP: inputs missing")
        return 2
    paths = enumerate_corpus(corpus_dir)
    if len(paths) != EXPECTED_COUNT:
        print(f"[m9.4.1] STOP: corpus drift ({len(paths)})")
        return 3
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ok = True

    model = read_kmz(kmz_path, BRENHAM_KMZ_DIALECT)
    svc = ReviewerBundleService(corpus_dir=corpus_dir, plan_pdf_path=PDF,
                                project_id="brenham-ph5", bore_log_paths=paths)
    full = svc.generate(ReviewRunMode.FULLEST_SAFE_REVIEW)
    lane_by_id = {p.bore_id: p.lane.value for p in full.payloads}

    plan = PlanPdf(PDF)
    results: List[TA.BoreTerminusResult] = []
    lines_by_id: Dict[str, dict] = {}
    try:
        dialect = select_dialect(plan)
        offset = dialect.calibrate(plan, 13)
        for p in paths:
            try:
                bore = load_borelog(str(p))
            except Exception:
                continue
            lbs = _lines_by_sheet(plan, bore, offset)
            lines_by_id[bore.bore_id] = lbs
            results.append(TA.attribute_bore(
                bore.bore_id, feet_to_station(bore.station_start_ft),
                feet_to_station(bore.station_end_ft), lbs, BRENHAM_TERMINUS_PROFILE,
                kmz_model=model,
                source_contradiction=bore.bore_id in SOURCE_CONTRADICTION_BORES))
    finally:
        plan.close()

    by_id = {r.bore_id: r for r in results}
    # ---- drive the SHIPPED core ---------------------------------------------
    evidence = RA.extract_run_assembly(results, lines_by_id, BRENHAM_TERMINUS_PROFILE)
    ev_by_pair = {(e.end_bore, e.start_bore): e for e in evidence}
    disp_census = collections.Counter(e.disposition for e in evidence)
    candidates = {(e.end_bore, e.start_bore) for e in evidence if e.is_continuation_candidate}
    drops = {(e.end_bore, e.start_bore) for e in evidence if e.is_drop_branch}
    cards = build_run_assembly_cards(evidence)

    junctions = TA.resolve_junctions(results)
    got_junctions = {(j["start_bore"], j["terminal_ap"], j["end_bore_owner"])
                     for j in junctions}
    clean_end = {r.bore_id: r.end.ap for r in results
                 if r.end.result == TA.ENDPOINT_ATTRIBUTED}
    bore_census = collections.Counter(r.disposition for r in results)

    # ---- GATES ---------------------------------------------------------------
    g1 = (len(model.structures) == EXPECT_STRUCTURES
          and len(model.routes) == EXPECT_ROUTES
          and got_junctions == EXPECT_JUNCTIONS and len(evidence) == 3)
    print(f"[m9.4.1] {'PASS' if g1 else 'FAIL'}  G1 inputs + 3 junctions + 3 evidence "
          f"items via the shipped core: {sorted(got_junctions)}")
    ok &= g1

    g2 = (clean_end == EXPECT_CLEAN_END
          and all(by_id[b].end.kmz_join == "KMZ_TERMINAL_JOIN_BOUND" for b in EXPECT_CLEAN_END))
    print(f"[m9.4.1] {'PASS' if g2 else 'FAIL'}  G2 7 clean END anchors UNCHANGED "
          f"(each KMZ-join BOUND)")
    ok &= g2

    g3 = (dict(disp_census) == {RA.RUN_ASSEMBLY_REVIEW_CANDIDATE: 2,
                                RA.JUNCTION_DROP_BRANCH: 1}
          and candidates == EXPECT_CANDIDATES and drops == EXPECT_DROPS)
    print(f"[m9.4.1] {'PASS' if g3 else 'FAIL'}  G3 disposition split: 2 review "
          f"candidates {sorted(candidates)} + 1 drop branch {sorted(drops)}: "
          f"{dict(sorted(disp_census.items()))}")
    ok &= g3

    g4 = all(e.relation == RA.RELATION_SHARED_TERMINAL and e.review_only
             and e.evidence_only and not e.affects_product_disposition
             and e.geometry is None and e.auto is False
             and e.terminal_is_end_of_feed for e in evidence)
    print(f"[m9.4.1] {'PASS' if g4 else 'FAIL'}  G4 all evidence SHARED-TERMINAL facts, "
          f"review/evidence-only (no bucket/AUTO/geometry; terminal=end-of-feed)")
    ok &= g4

    # G5: the STRONGER guard considers the physical departures WITHIN the terminal's own
    # frame (the END bore's sheets), beyond only JUNCTION_ORIGIN starts. On Brenham each
    # terminal has exactly 1 physical departure: the AP-163 node prints the log65
    # fiber-drop callout (claimed by log65 -> 0 unclaimed extra); AP-152/117 print
    # none. So competing_departures == 1 everywhere -> the 3 relations are preserved.
    # (A cross-sheet lateral outside the END bore's frame is a NAMED open target -- M9.2.)
    jo_by_ap: Dict[object, list] = {}
    for r in results:
        if r.start.result == TA.JUNCTION_ORIGIN and r.start.ap is not None:
            jo_by_ap.setdefault(r.start.ap, []).append(r.bore_id)
    counts, node_laterals = {}, {}
    for j in junctions:
        ap, eb = j["terminal_ap"], j["end_bore_owner"]
        c, extra = RA.physical_departure_count(ap, eb, jo_by_ap.get(ap, []), by_id,
                                               lines_by_id, BRENHAM_TERMINUS_PROFILE)
        counts[ap] = c
        node_laterals[ap] = len(RA.run_callout_departures(
            lines_by_id.get(eb, {}), by_id[eb].end_station, BRENHAM_TERMINUS_PROFILE))
    g5 = (all(e.competing_departures == 1 for e in evidence)
          and set(counts.values()) == {1}
          and node_laterals[163] == 1 and node_laterals[152] == 0 and node_laterals[117] == 0)
    print(f"[m9.4.1] {'PASS' if g5 else 'FAIL'}  G5 competing guard enumerates physical "
          f"departures in the terminal's own frame (END-bore sheets): counts={counts}; "
          f"node callouts at terminal {node_laterals} (AP-163's drop claimed by log65 -> 0 extra)")
    ok &= g5

    # G6: log65 is a JUNCTION_DROP_BRANCH driven by departure_run_class == 'drop'
    # (the injected marker), and CANNOT be a continuation candidate.
    dep65 = RA.departure_run_class(lines_by_id["log65"], by_id["log65"].start_station,
                                   BRENHAM_TERMINUS_PROFILE)
    e65 = ev_by_pair[("log7", "log65")]
    g6 = (dep65 == RA.DEP_DROP and e65.disposition == RA.JUNCTION_DROP_BRANCH
          and e65.disposition != RA.RUN_ASSEMBLY_REVIEW_CANDIDATE
          and ("log7", "log65") not in candidates)
    print(f"[m9.4.1] {'PASS' if g6 else 'FAIL'}  G6 log65 departure_run_class={dep65} "
          f"-> JUNCTION_DROP_BRANCH (CANNOT be promoted to a continuation candidate)")
    ok &= g6

    # G7: the CORE is convention-agnostic -- zero customer literals AND zero plan
    # vocabulary INCLUDING the drop marker (it must come only from the profile).
    core_src = inspect.getsource(RA)
    leaks = [ln.strip() for ln in core_src.splitlines() if FORBIDDEN.search(ln)]
    vocab = [v for v in CORE_PLAN_VOCAB if v in core_src]
    g7 = not leaks and not vocab
    print(f"[m9.4.1] {'PASS' if g7 else 'FAIL'}  G7 universal core: 0 customer literals "
          f"(leaks={leaks}); 0 plan vocab incl. drop marker in core (found={vocab})")
    ok &= g7

    # G8: the drop grammar is PROFILE-INJECTED -- with drop_markers=() the SAME real
    # log65 callout reads as a non-drop trunk run (the 'FOR FIBER DROP' is not baked
    # into the core; it is read only from the profile).
    no_drop_profile = dataclasses.replace(BRENHAM_TERMINUS_PROFILE, drop_markers=())
    dep65_nomarker = RA.departure_run_class(lines_by_id["log65"],
                                            by_id["log65"].start_station, no_drop_profile)
    g8 = dep65 == RA.DEP_DROP and dep65_nomarker == RA.DEP_TRUNK
    print(f"[m9.4.1] {'PASS' if g8 else 'FAIL'}  G8 drop grammar injected: Brenham "
          f"profile -> {dep65}; drop_markers=() -> {dep65_nomarker} (no baked literal)")
    ok &= g8

    # G9: the review cards -- exactly 3 (2 candidate + 1 drop), all REVIEW/no-geometry;
    # a typed blocker yields NO card.
    cont_classes = collections.Counter(c.continuation_class for c in cards)
    blocker_ev = RA.RunAssemblyEvidence(
        end_bore="x", start_bore="y", terminal_ap=1, splice_loc=None,
        disposition=RA.COMPETING_JUNCTION_CANDIDATES)
    g9 = (len(cards) == 3
          and dict(cont_classes) == {CONTINUATION_CANDIDATE: 2, DROP_BRANCH: 1}
          and all(c.review_only and not c.auto and not c.has_geometry
                  and not c.has_strokes for c in cards)
          and build_run_assembly_cards([blocker_ev]) == [])
    print(f"[m9.4.1] {'PASS' if g9 else 'FAIL'}  G9 review cards: 3 cards "
          f"{dict(cont_classes)} (review/no-geometry); blocker -> 0 cards")
    ok &= g9

    # G10: read-only / UNWIRED -- nothing rendered; no placement-path module imports
    # the core; zero bores moved; no contract drift.
    import truelinev2.match.engine as eng
    import truelinev2.match.symbol_conduit_lane as scl
    import truelinev2.review.reviewer_service as rsvc
    import truelinev2.service as svcmod
    wired = any("run_assembly" in inspect.getsource(m)
                for m in (eng, scl, rsvc, svcmod))
    no_drift = (full.lane_counts == BANKED_FULLEST_LANES
                and dict(bore_census) == EXPECT_BORE_CENSUS
                and completion_bucket(lane_by_id["log10"], "log10")[0] == "DRAWABLE_REVIEW"
                and completion_bucket(lane_by_id["log7"], "log7")[0] == "DRAWABLE_REVIEW")
    g10 = not list(OUT_DIR.glob("*.png")) and not wired and no_drift
    print(f"[m9.4.1] {'PASS' if g10 else 'FAIL'}  G10 read-only: no PNG; core UNWIRED "
          f"from engine/lane/service (wired={wired}); 0 bores moved; no drift")
    ok &= g10

    # G11: Phase-0 parity -- the shipped core reproduces the M9.4 Phase-0 boundary
    # exactly, and the M9.2 no-equation negative stays intact (none are junction bores).
    junction_bores = {b for j in junctions for b in (j["start_bore"], j["end_bore_owner"])}
    g11 = (got_junctions == EXPECT_JUNCTIONS
           and candidates == EXPECT_CANDIDATES and drops == EXPECT_DROPS
           and not (M92_NO_EQUATION & junction_bores))
    print(f"[m9.4.1] {'PASS' if g11 else 'FAIL'}  G11 Phase-0 parity + M9.2 negative "
          f"intact (no_equation bores not junctions: {sorted(M92_NO_EQUATION & junction_bores)})")
    ok &= g11

    report = {
        "milestone": ("truelinev2 M9.4.1 -- RUN_ASSEMBLY extractor (shipped core + "
                      "M8.20-style review card; UNWIRED/unconsumed; universal core + "
                      "injected drop grammar; proof-only; zero bores moved)"),
        "kmz_path": kmz_path, "corpus_dir": corpus_dir, "plan_pdf": PDF,
        "verdict": "PASS" if ok else "FAILURE",
        "core_module": "truelinev2/match/run_assembly.py (zero plan-set literals)",
        "review_card": "truelinev2/review/run_assembly_review.py (schema truelinev2-run-assembly-review-1)",
        "profile": "truelinev2/extract/terminus_profile.py BRENHAM_TERMINUS_PROFILE (drop_markers injected)",
        "capability_over_phase0": [
            "drop-marker grammar is PROFILE-INJECTED (the core holds no drop literal)",
            "the competing guard enumerates physical departures WITHIN the terminal's own "
            "frame (the END bore's sheets), beyond only JUNCTION_ORIGIN starts -- a same-"
            "frame fiber-drop lateral can no longer hide",
            "the evidence is a NEW M8.20-style review card (REVIEW/evidence-only)",
        ],
        "known_limitation": (
            "the competing guard is frame-scoped to the END bore's sheets, NOT corpus-"
            "wide -- a station token is frame-local and recurs in every sheet's "
            "stationing, so a corpus-wide scan would false-positive (the M9.2 matchline "
            "trap). A matchline-adjacent lateral drawn SOLELY on a sheet outside the END "
            "bore's frame is therefore not yet enumerated; associating a far-sheet "
            "callout with this node requires the cross-sheet frame-equation graph (the "
            "M9.2 matchline track) -- a separate, justified capability, never a silent widen."),
        "disposition_census": dict(sorted(disp_census.items())),
        "physical_departure_counts": {str(k): v for k, v in sorted(counts.items())},
        "node_callouts_at_terminal": {str(k): v for k, v in sorted(node_laterals.items())},
        "run_assembly_review_candidates": [ev_by_pair[p].to_dict() for p in sorted(candidates)],
        "fiber_drop_branches": [ev_by_pair[p].to_dict() for p in sorted(drops)],
        "evidence": [e.to_dict() for e in evidence],
        "review_cards": [c.model_dump() for c in cards],
        "clean_end_anchors": [{"bore_id": b, "terminal_ap": ap}
                              for b, ap in sorted(clean_end.items())],
        "lane_shipped_into_product": False, "bores_moved": 0, "review_only": True,
        "unwired_unconsumed": True,
        "next_step": ("a reviewer-service surface for the run-assembly cards (separate, "
                      "justified milestone; a NEW review item, never a per-bore bucket "
                      "change); cross-sheet competing-lateral enumeration via the M9.2 "
                      "frame-equation graph (the named competing-guard limitation above); "
                      "owner source re-reads for log46 (PDF<->KMZ) + log44 (325'). No "
                      "consumer wiring in this milestone."),
    }
    (OUT_DIR / "run_assembly_extract.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8")

    print(f"\n[m9.4.1] dispositions: {dict(sorted(disp_census.items()))}")
    print(f"[m9.4.1] review candidates: {sorted(candidates)} | drop branches: {sorted(drops)}")
    print(f"[m9.4.1] review cards: {len(cards)} | core UNWIRED | bores moved: 0")
    print(f"[m9.4.1] verdict: {report['verdict']}")
    print(f"[m9.4.1] report -> {OUT_DIR / 'run_assembly_extract.json'}")
    return 0 if ok else 4


if __name__ == "__main__":
    raise SystemExit(main())
