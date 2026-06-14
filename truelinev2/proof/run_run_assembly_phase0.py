r"""M9.4 Phase 0 -- gated REVIEW-only run-assembly lane feasibility (proof-only; READ-ONLY).

Answers: when a bore END terminal and another bore START junction-origin share the
SAME AP+splice terminal fact, can the engine safely emit a TYPED run-assembly
evidence item -- without moving a product bucket, drawing a stroke, or marking AUTO?

It consumes the SHIPPED M9.3.1 extractor (match/terminus_attribution.py) facts ONLY
-- the 7 clean terminal-END attributions + the 3 junction-origin facts -- and
evaluates each junction against a safety law. This Phase-0 proof itself SHIPS NO LANE;
it remains BANKED as the boundary proof. The convention-agnostic run-assembly core it
named HAS SINCE SHIPPED in M9.4.1 (match/run_assembly.py + review/run_assembly_review.py)
and was surfaced by the M9.4.2 reviewer-service (review/run_assembly_review_service.py);
this proof is retained as the historical boundary record and is still green.

WHAT THE EVIDENCE IS (and is NOT):
  The base fact is a SHARED TERMINAL NODE: the END bore TERMINATES at terminal T
  (END-direction ownership, M9.3.1), and a DIFFERENT bore's START sits at the same T
  (JUNCTION_ORIGIN -- it DEPARTS the junction). The relation is directional END -> START.
  It is REVIEW-only EVIDENCE. It is NOT a stationing continuation, NOT a geometric
  route, and NOT a product-bucket change. No geometry, no stroke, no AUTO.

  CONTINUITY IS NOT UNIFORM (M9.4 audit fix): a terminal is an END-OF-FEED node, so
  what DEPARTS it may be the trunk continuing OR a fiber-drop LATERAL. The proof reads
  the departing (START) bore's printed run class: a TRUNK-class departure is a
  plausible run continuation (RUN_ASSEMBLY_REVIEW_CANDIDATE); a DROP-class departure
  ("FOR FIBER DROP") is a branch off the terminus (JUNCTION_DROP_BRANCH), explicitly
  NOT the run continuing. A reviewer -- never this proof -- commits the run.

THE SAFETY LAW (all must hold before classifying the departure):
  0. the junction is bore-to-bore (start_bore != end_bore -- a self-junction is refused);
  1. END ownership is clean + unique (END is ENDPOINT_ATTRIBUTED; one terminal -> one
     bore END, the M9.3.1 invariant);
  2. the START side is JUNCTION_ORIGIN (NEVER ownership -- END-direction law);
  3. both sides carry the SAME normalized terminal fact (same AP + same splice token);
  4. the M9.1 two-field join corroborates the terminal (END kmz_join == BOUND);
  5. neither bore carries a PDF<->KMZ or source contradiction;
  6. no competing same-terminal JUNCTION_ORIGIN candidate;
  7. EVIDENCE-only -- it changes no product disposition.
Then the DEPARTURE RUN CLASS (trunk / drop) types the disposition.

KNOWN LIMITATION (named for M9.4.1): the competing-junction guard counts only
JUNCTION_ORIGIN departures (terminal-class start notes); physical drop/lateral
"... TO STA ..." run callouts at the node are not enumerated. Each item records
terminal_is_end_of_feed=True so a reviewer is never led to read a drop as the trunk.

FORBIDDEN (asserted, never used): treat START as ownership; move a product bucket;
mark AUTO; draw a stroke/segment/PNG; wire the reviewer service; proximity; AP-only /
splice-only; flat-sheet continuity; KMZ-geometry route inference; KMZ overriding a
PDF/source contradiction; customer literals in shared core (this proof is in proof/,
so the Brenham DROP_MARKER literal is allowed here; it is a named M9.4.1 profile field).

PROOF-ONLY / READ-ONLY: consults the shipped M9.3.1 extractor + M8.11 reviewer
contract WITHOUT altering any; no engine wiring; zero bores moved. M8.27 census +
product lanes + M9.0/M9.1/M9.2/M9.3/M9.3.1 frozen.

Exit codes: 0 PASS, 2 inputs missing, 3 corpus drift, 4 gate FAILURE.

Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_run_assembly_phase0
"""
from __future__ import annotations

import collections
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
from truelinev2.match import terminus_attribution as TA
from truelinev2.proof.run_brenham_corpus import EXPECTED_COUNT, PDF, enumerate_corpus
from truelinev2.proof.run_final_engine_truth_table import completion_bucket
from truelinev2.proof.run_kmz_correlation_audit import resolve_kmz
from truelinev2.proof.run_reviewer_service_contract import resolve_corpus
from truelinev2.review.reviewer_service import ReviewerBundleService, ReviewRunMode
from truelinev2.stations import feet_to_station

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "run_assembly_phase0"

EXPECT_STRUCTURES = 576
EXPECT_ROUTES = 539
BANKED_FULLEST_LANES = {
    "PLACED_REVIEW": 31, "PICK_CARD_ROUTE_SUGGESTION": 16,   # RECON-2A: +log37
    "HUMAN_ADJUSTABLE_LENGTH_REDLINE": 6, "OUT_OF_CLASS": 5,  # +log38; SOURCE_REVIEW 2->0
}
SOURCE_CONTRADICTION_BORES = {"log44"}                 # banked M8.25/M9.0
EXPECT_CLEAN_END = {"log42": 105, "log72": 117, "log12": 121, "log2": 148,
                    "log10": 152, "log57": 157, "log7": 163}
EXPECT_JUNCTIONS = {("log27", 152, "log10"), ("log39", 117, "log72"),
                    ("log65", 163, "log7")}
M92_NO_EQUATION = {"log14", "log61", "log62", "log67", "log68", "log70"}
# the printed drop-lateral marker (Brenham proof literal; an M9.4.1 profile field).
DROP_MARKER = "FOR FIBER DROP"

# typed run-assembly outcomes
RUN_ASSEMBLY_REVIEW_CANDIDATE = "RUN_ASSEMBLY_REVIEW_CANDIDATE"   # shared-terminal node; reviewer classifies
JUNCTION_DROP_BRANCH = "JUNCTION_DROP_BRANCH"                     # positively-detected drop lateral
SELF_JUNCTION_REFUSED = "SELF_JUNCTION_REFUSED"
START_JUNCTION_NOT_OWNERSHIP = "START_JUNCTION_NOT_OWNERSHIP"
PDF_KMZ_CONTRADICTION = "PDF_KMZ_CONTRADICTION"
SOURCE_CONTRADICTION = "SOURCE_CONTRADICTION"
COMPETING_JUNCTION_CANDIDATES = "COMPETING_JUNCTION_CANDIDATES"
UNMODELED_RUN_RELATIONSHIP = "UNMODELED_RUN_RELATIONSHIP"
# the relation/evidence the item carries (the FACT, not a committed run)
RELATION_SHARED_TERMINAL = "END_START_SHARED_TERMINAL"
EVIDENCE_SHARED_TERMINAL = "JUNCTION_SHARED_TERMINAL_EVIDENCE"


def _norm(s):
    return " ".join(str(s).upper().split()) if s else None


def departure_run_class(lines_by_sheet: Dict[object, list], start_station: str,
                        profile) -> str:
    """The printed run class of the bore DEPARTING a terminal: 'drop' if its
    start-station run callout carries the drop marker (a lateral), 'trunk' if a
    departing run callout exists without it, else 'unknown'. Read-only; uses the
    injected station/run grammar + the proof's DROP_MARKER (an M9.4.1 profile field)."""
    sta_re = re.compile(profile.station_line_re)
    for lines in lines_by_sheet.values():
        for i, ln in enumerate(lines):
            s = ln.strip()
            m = sta_re.match(s)
            if not m or m.group(1) != start_station:
                continue
            if profile.run_callout_marker not in s:        # must be a "TO STA" run callout
                continue
            window = " ".join([s] + [x.strip() for x in lines[i + 1:i + 1 + profile.note_window]])
            return "drop" if DROP_MARKER in window.upper() else "trunk"
    return "unknown"


def evaluate_junction(j: dict, by_id: Dict[str, TA.BoreTerminusResult],
                      start_terminal_count: Dict[object, int],
                      contradiction: Dict[str, str], dep_class: str) -> dict:
    """The run-assembly safety law over ONE junction fact. Pure; emits a typed
    evidence item or a typed blocker. EVIDENCE-only -- never a placement/bucket.
    The base relation is a SHARED-TERMINAL-NODE fact; the departure run class
    (trunk/drop) types the disposition (continuation candidate vs drop lateral)."""
    start_bore, ap, end_bore = j["start_bore"], j["terminal_ap"], j["end_bore_owner"]
    splice = j.get("splice_loc")
    row = {"end_bore": end_bore, "start_bore": start_bore, "terminal_ap": ap,
           "splice_loc": splice, "evidence_class": EVIDENCE_SHARED_TERMINAL,
           "relation": RELATION_SHARED_TERMINAL, "review_only": True,
           "evidence_only": True, "affects_product_disposition": False,
           "geometry": None, "auto": False, "terminal_is_end_of_feed": True,
           "departure_run_class": dep_class}

    # (0) bore-to-bore only -- a self-junction is degenerate.
    if end_bore is not None and start_bore == end_bore:
        return {**row, "disposition": SELF_JUNCTION_REFUSED,
                "why": f"{start_bore} START and END both sit at terminal AP {ap} -- "
                       f"a self-junction is not a bore-to-bore relation; refused"}
    if end_bore is None:
        return {**row, "disposition": UNMODELED_RUN_RELATIONSHIP,
                "why": f"terminal AP {ap} has no unique END owner -- no bore-to-bore junction"}
    end_r, start_r = by_id.get(end_bore), by_id.get(start_bore)
    if end_r is None or start_r is None:
        return {**row, "disposition": UNMODELED_RUN_RELATIONSHIP,
                "why": "a junction bore is absent from the extractor results"}

    # (1) END ownership clean + unique
    owners = TA.terminal_end_index(list(by_id.values())).get(ap, [])
    if (end_r.end.result != TA.ENDPOINT_ATTRIBUTED or end_r.end.ap != ap
            or owners != [end_bore]):
        return {**row, "disposition": UNMODELED_RUN_RELATIONSHIP,
                "why": f"END ownership of AP {ap} is not clean+unique to {end_bore} "
                       f"(owners={owners})"}
    # (2) START is JUNCTION_ORIGIN, never ownership
    if start_r.start.result != TA.JUNCTION_ORIGIN or start_r.start.ap != ap:
        return {**row, "disposition": START_JUNCTION_NOT_OWNERSHIP,
                "why": f"{start_bore} START is not a JUNCTION_ORIGIN for AP {ap} "
                       f"(result={start_r.start.result}) -- refused as ownership"}
    # (3) same normalized terminal fact
    if not (end_r.end.ap == start_r.start.ap
            and _norm(end_r.end.splice) == _norm(start_r.start.splice)):
        return {**row, "disposition": UNMODELED_RUN_RELATIONSHIP,
                "why": f"END/START do not share one terminal fact "
                       f"({end_r.end.ap}/{end_r.end.splice} vs "
                       f"{start_r.start.ap}/{start_r.start.splice})"}
    # (4) KMZ join corroborates
    if end_r.end.kmz_join != "KMZ_TERMINAL_JOIN_BOUND":
        return {**row, "disposition": UNMODELED_RUN_RELATIONSHIP,
                "why": f"terminal AP {ap} is not KMZ-join corroborated "
                       f"(join={end_r.end.kmz_join})"}
    # (5) contradiction blocks
    for b in (end_bore, start_bore):
        if b in contradiction:
            return {**row, "disposition": contradiction[b],
                    "why": f"{b} carries a {contradiction[b]} -- blocked until owner/source reread"}
    # (6) competing JUNCTION_ORIGIN departure
    if start_terminal_count.get(ap, 0) > 1:
        return {**row, "disposition": COMPETING_JUNCTION_CANDIDATES,
                "why": f"{start_terminal_count[ap]} JUNCTION_ORIGIN starts depart "
                       f"terminal AP {ap} -- the continuation branches; never chosen between"}

    # (7) classify by the departing bore's printed run class
    base = {**row, "end_station": end_r.end.station, "end_note": end_r.end.note_line,
            "start_station": start_r.start.station, "start_note": start_r.start.note_line,
            "end_ownership_clean_unique": True,
            "start_is_junction_origin_not_ownership": True,
            "same_terminal_fact": True, "kmz_join_corroborated": True,
            "competing_junction_candidates": 0}
    if dep_class == "drop":
        return {**base, "disposition": JUNCTION_DROP_BRANCH,
                "why": f"{start_bore} departs terminal AP {ap} as a FIBER-DROP lateral "
                       f"(printed '{DROP_MARKER}') -- a branch off {end_bore}'s "
                       f"end-of-feed terminus, NOT the trunk continuing"}
    # not a positively-detected drop -> a shared-terminal-node REVIEW candidate. The
    # reviewer classifies trunk-continuation vs other; this proof asserts the
    # shared-terminal FACT only, never a committed/geometric run. (Positively
    # confirming TRUNK needs per-bore run-callout attribution -- an M9.4.1 capability;
    # absence of a drop marker at the start callout is NOT proof of trunk.)
    return {**base, "disposition": RUN_ASSEMBLY_REVIEW_CANDIDATE,
            "why": f"{end_bore} END terminates at terminal AP {ap} ({splice}); "
                   f"{start_bore} departs the SAME terminal (departure run class: "
                   f"{dep_class}) -- a SHARED-TERMINAL-NODE review candidate; the "
                   f"reviewer classifies the continuation (shared-terminal FACT only, "
                   f"not a committed run, no drop marker positively detected)"}


def _lines_by_sheet(plan, bore, offset):
    return {s: plan.lines(s, offset) for s in sorted(set(bore.sheet_refs))}


def main() -> int:
    kmz_path, kmz_how = resolve_kmz()
    corpus_dir, how = resolve_corpus()
    print(f"[m9.4] kmz   : {kmz_path}  ({kmz_how})")
    print(f"[m9.4] corpus: {corpus_dir}  ({how})")
    if not os.path.isfile(kmz_path) or not os.path.isfile(PDF) \
            or not os.path.isdir(corpus_dir):
        print("[m9.4] STOP: inputs missing")
        return 2
    paths = enumerate_corpus(corpus_dir)
    if len(paths) != EXPECTED_COUNT:
        print(f"[m9.4] STOP: corpus drift ({len(paths)})")
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
    bore_lines: Dict[str, dict] = {}
    bore_start: Dict[str, str] = {}
    try:
        dialect = select_dialect(plan)
        offset = dialect.calibrate(plan, 13)
        for p in paths:
            try:
                bore = load_borelog(str(p))
            except Exception:
                continue
            lbs = _lines_by_sheet(plan, bore, offset)
            bore_lines[bore.bore_id] = lbs
            bore_start[bore.bore_id] = feet_to_station(bore.station_start_ft)
            results.append(TA.attribute_bore(
                bore.bore_id, feet_to_station(bore.station_start_ft),
                feet_to_station(bore.station_end_ft), lbs, BRENHAM_TERMINUS_PROFILE,
                kmz_model=model,
                source_contradiction=bore.bore_id in SOURCE_CONTRADICTION_BORES))
    finally:
        plan.close()

    by_id = {r.bore_id: r for r in results}
    clean_end = {r.bore_id: r.end.ap for r in results
                 if r.end.result == TA.ENDPOINT_ATTRIBUTED}
    junctions = TA.resolve_junctions(results)
    contradiction = {r.bore_id: r.disposition for r in results
                     if r.disposition in (PDF_KMZ_CONTRADICTION, SOURCE_CONTRADICTION)}
    start_terminal_count: Dict[object, int] = collections.Counter(
        j["terminal_ap"] for j in junctions)

    rows = []
    for j in junctions:
        sb = j["start_bore"]
        dep = departure_run_class(bore_lines.get(sb, {}), bore_start.get(sb, ""),
                                  BRENHAM_TERMINUS_PROFILE)
        rows.append(evaluate_junction(j, by_id, start_terminal_count, contradiction, dep))
    disp_census = collections.Counter(r["disposition"] for r in rows)
    candidates = [r for r in rows if r["disposition"] == RUN_ASSEMBLY_REVIEW_CANDIDATE]
    drops = [r for r in rows if r["disposition"] == JUNCTION_DROP_BRANCH]

    # ---- GATES ---------------------------------------------------------------
    got_junctions = {(j["start_bore"], j["terminal_ap"], j["end_bore_owner"])
                     for j in junctions}
    g1 = (len(model.structures) == EXPECT_STRUCTURES
          and len(model.routes) == EXPECT_ROUTES
          and got_junctions == EXPECT_JUNCTIONS and len(rows) == 3)
    print(f"[m9.4] {'PASS' if g1 else 'FAIL'}  G1 inputs + 3 junctions represented: "
          f"{sorted(got_junctions)}")
    ok &= g1

    g2 = (clean_end == EXPECT_CLEAN_END
          and all(by_id[b].end.kmz_join == "KMZ_TERMINAL_JOIN_BOUND" for b in EXPECT_CLEAN_END))
    print(f"[m9.4] {'PASS' if g2 else 'FAIL'}  G2 7 clean END anchors UNCHANGED "
          f"(each KMZ-join BOUND)")
    ok &= g2

    # G3: trunk departures -> RUN_ASSEMBLY_REVIEW_CANDIDATE; the log65 fiber-drop ->
    # JUNCTION_DROP_BRANCH (NOT a continuation -- the M9.4 audit correction).
    drop_bores = {(r["end_bore"], r["start_bore"]) for r in drops}
    g3 = (dict(disp_census) == {RUN_ASSEMBLY_REVIEW_CANDIDATE: 2, JUNCTION_DROP_BRANCH: 1}
          and drop_bores == {("log7", "log65")}
          and {(r["end_bore"], r["start_bore"]) for r in candidates}
              == {("log10", "log27"), ("log72", "log39")})
    print(f"[m9.4] {'PASS' if g3 else 'FAIL'}  G3 departure-class split: 2 "
          f"shared-terminal-node review candidates + 1 fiber-drop branch "
          f"(log7->log65 positively detected): {dict(sorted(disp_census.items()))}")
    ok &= g3

    # G4: every emitted item is a SHARED-TERMINAL fact (relation), review/evidence-only.
    g4 = all(r["relation"] == RELATION_SHARED_TERMINAL and r["review_only"]
             and r["evidence_only"] and not r["affects_product_disposition"]
             and r["geometry"] is None and r["auto"] is False
             and r["terminal_is_end_of_feed"] for r in rows)
    print(f"[m9.4] {'PASS' if g4 else 'FAIL'}  G4 all items SHARED-TERMINAL facts, "
          f"review/evidence-only (no bucket/AUTO/geometry; terminal=end-of-feed)")
    ok &= g4

    # G5: START-side is JUNCTION_ORIGIN, never ownership; no self-junction.
    starts_owned = [j["start_bore"] for j in junctions
                    if by_id[j["start_bore"]].start.result == TA.ENDPOINT_ATTRIBUTED]
    self_junctions = [j for j in junctions if j["start_bore"] == j["end_bore_owner"]]
    g5 = (not starts_owned and not self_junctions
          and all(by_id[j["start_bore"]].start.result == TA.JUNCTION_ORIGIN for j in junctions))
    print(f"[m9.4] {'PASS' if g5 else 'FAIL'}  G5 START=JUNCTION_ORIGIN (never "
          f"ownership); no self-junction (owned={starts_owned}, self={self_junctions})")
    ok &= g5

    # G6: END ownership clean + unique.
    g6 = (not TA.check_terminal_uniqueness(results)
          and all(TA.terminal_end_index(results).get(j["terminal_ap"]) == [j["end_bore_owner"]]
                  for j in junctions))
    print(f"[m9.4] {'PASS' if g6 else 'FAIL'}  G6 END ownership clean+unique "
          f"(one terminal -> one END bore)")
    ok &= g6

    # G7: contradictions blocked -- log46/log44 are NOT junction bores.
    junction_bores = {b for j in junctions for b in (j["start_bore"], j["end_bore_owner"])}
    g7 = ("log46" not in junction_bores and "log44" not in junction_bores
          and not (junction_bores & set(contradiction)))
    print(f"[m9.4] {'PASS' if g7 else 'FAIL'}  G7 contradictions blocked: log46/log44 "
          f"not junction bores")
    ok &= g7

    # G8: no competing JUNCTION_ORIGIN departure (one per terminal).
    g8 = all(start_terminal_count[j["terminal_ap"]] == 1 for j in junctions)
    print(f"[m9.4] {'PASS' if g8 else 'FAIL'}  G8 no competing JUNCTION_ORIGIN "
          f"departures: {dict(start_terminal_count)}")
    ok &= g8

    # G9: M9.2 no-equation negative intact; M9.3.1 census reproduces; no drift.
    bore_census = collections.Counter(r.disposition for r in results)
    g9 = (not (M92_NO_EQUATION & junction_bores)
          and dict(bore_census) == {
              "ENDPOINT_ATTRIBUTED": 7, "JUNCTION_ORIGIN": 3,
              "PDF_KMZ_CONTRADICTION": 1, "SOURCE_CONTRADICTION": 1,
              "SHEET_NEIGHBOR_REJECTED": 46}   # RECON-2A: +log37/log38
          and full.lane_counts == BANKED_FULLEST_LANES
          and completion_bucket(lane_by_id["log10"], "log10")[0] == "DRAWABLE_REVIEW")
    print(f"[m9.4] {'PASS' if g9 else 'FAIL'}  G9 M9.2 negative intact + M9.3.1 "
          f"census reproduces + no contract drift")
    ok &= g9

    # G10: read-only / unwired.
    import truelinev2.review.reviewer_service as rsvc
    import truelinev2.match.engine as eng
    wired = any("run_assembly" in inspect.getsource(m) for m in (rsvc, eng))
    g10 = not list(OUT_DIR.glob("*.png")) and not wired
    print(f"[m9.4] {'PASS' if g10 else 'FAIL'}  G10 read-only: no PNG; reviewer "
          f"service NOT wired to run-assembly (wired={wired}); 0 bores moved")
    ok &= g10

    def _project(r):
        return {k: r[k] for k in ("end_bore", "start_bore", "terminal_ap",
                                  "splice_loc", "end_station", "start_station",
                                  "relation", "departure_run_class", "disposition",
                                  "review_only", "evidence_only",
                                  "affects_product_disposition")}

    report = {
        "milestone": ("truelinev2 M9.4 Phase 0 -- gated REVIEW-only run-assembly lane "
                      "feasibility (proof-only; READ-ONLY; consumes M9.3.1 facts; no "
                      "lane shipped; zero bores moved)"),
        "kmz_path": kmz_path, "corpus_dir": corpus_dir, "plan_pdf": PDF,
        "verdict": "PASS" if ok else "FAILURE",
        "safety_law": [
            "0 bore-to-bore only (start_bore != end_bore; self-junction refused)",
            "1 END ownership clean + unique (one terminal -> one END bore)",
            "2 START side is JUNCTION_ORIGIN, never ownership (END-direction law)",
            "3 same normalized terminal fact (AP + splice) on both sides",
            "4 M9.1 two-field join corroborates the terminal (END join BOUND)",
            "5 no PDF<->KMZ or source contradiction on either bore",
            "6 no competing JUNCTION_ORIGIN departure",
            "7 EVIDENCE-only -- changes no product disposition",
            "then: the departing bore's printed run class (trunk/drop) types the item",
        ],
        "evidence_is": ("a SHARED-TERMINAL-NODE fact: the END bore terminates at "
                        "terminal T (end-of-feed) and the START bore departs T "
                        "(directional END->START). It is NOT a stationing or geometric "
                        "continuation and NOT a product-bucket change. A TRUNK departure "
                        "is a plausible run-continuation CANDIDATE; a DROP departure is "
                        "a fiber-drop LATERAL (branch), never the trunk continuing. The "
                        "reviewer, never this proof, commits the run."),
        "disposition_census": dict(sorted(disp_census.items())),
        "run_assembly_review_candidates": [_project(r) for r in candidates],
        "fiber_drop_branches": [_project(r) for r in drops],
        "junctions": rows,
        "clean_end_anchors": [{"bore_id": b, "terminal_ap": ap}
                              for b, ap in sorted(clean_end.items())],
        "contradictions_blocked": contradiction,
        "competing_guard_limitation": ("the competing-junction guard counts only "
                                       "JUNCTION_ORIGIN departures; physical drop/lateral "
                                       "run callouts at the node are not enumerated -- "
                                       "an M9.4.1 capability"),
        "lane_shipped": False, "bores_moved": 0, "review_only": True,
        "ship_recommendation": (
            "DEFER the shipped lane to M9.4.1 (Phase 0 proves the boundary; matches "
            "M9.3->M9.3.1). The 2 TRUNK departures (log10->log27, log72->log39) are "
            "safe RUN_ASSEMBLY_REVIEW_CANDIDATEs; the log7->log65 fiber-drop is a "
            "JUNCTION_DROP_BRANCH (a lateral, not the run continuing). M9.4.1 would "
            "ship a convention-agnostic core over the M9.3.1 typed facts with the "
            "DROP_MARKER as a profile field + a physical-departure enumerator for the "
            "competing guard; the evidence is a NEW review item (like the M8.20 group "
            "card), never a per-bore bucket change; UNWIRED until a separate, justified step."),
        "named_evidence_targets": [
            "M9.4.1: a convention-agnostic core run-assembly module over the M9.3.1 "
            "typed facts; inject the drop-marker grammar; enumerate ALL physical "
            "departures at a terminal (not only JUNCTION_ORIGIN starts) for the "
            "competing guard",
            "a reviewer-service surface for the continuity evidence (separate, "
            "justified milestone; a NEW review item, never a per-bore bucket change)",
            "owner source re-reads for log46 (PDF<->KMZ) + log44 (source) before any "
            "continuity touching those bores",
        ],
    }
    (OUT_DIR / "run_assembly_phase0.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8")

    print(f"\n[m9.4] junction dispositions: {dict(sorted(disp_census.items()))}")
    print(f"[m9.4] shared-terminal-node review candidates: "
          f"{[(r['end_bore'], '->', r['start_bore']) for r in candidates]}")
    print(f"[m9.4] fiber-drop branches: {[(r['end_bore'], '->', r['start_bore']) for r in drops]}")
    print(f"[m9.4] lane shipped: False | bores moved: 0 | review-only: True")
    print(f"[m9.4] verdict: {report['verdict']}")
    print(f"[m9.4] report -> {OUT_DIR / 'run_assembly_phase0.json'}")
    return 0 if ok else 4


if __name__ == "__main__":
    raise SystemExit(main())
