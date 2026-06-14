r"""M9.3.1 -- TERMINUS_ATTRIBUTION extractor proof (drives the SHIPPED core).

Exercises the convention-agnostic core (match/terminus_attribution.py) over the
full Brenham corpus through the injected BRENHAM_TERMINUS_PROFILE. The M9.3 Phase-0
BORE-DISPOSITION census + ALL named controls (the 7 clean END attributions, the 3
junctions, log46, log68, log44) reproduce through shipped engine code with the core
holding zero plan-set literals. The per-endpoint taxonomy is a strict REFINEMENT of
M9.3: the shipped core splits the former NO_AP_SPLICE_PAIR into NO_AP_SPLICE_PAIR (a
partial id at a terminal-class note) and NON_TERMINAL_ENDPOINT (a bound note whose
class is not the terminal class) -- this changes no bore disposition and no control.
PROOF-ONLY: no placement, no engine wiring, no stroke/PNG/segment, no AUTO, no
tolerance/budget change, zero bores moved. The extractor is UNWIRED (unconsumed: no
resolve_bore / sweep / reviewer service / run_match imports it; no opt-in flag).
M8.27 census + product lanes + M9.0/M9.1/M9.2/M9.3 frozen.

Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_terminus_attribution_extract
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

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "terminus_attribution_extract"

EXPECT_STRUCTURES = 576
EXPECT_ROUTES = 539
BANKED_FULLEST_LANES = {
    "PLACED_REVIEW": 31, "PICK_CARD_ROUTE_SUGGESTION": 16,   # RECON-2A: +log37
    "HUMAN_ADJUSTABLE_LENGTH_REDLINE": 6, "OUT_OF_CLASS": 5,  # +log38; SOURCE_REVIEW 2->0
}
TARGETS = ("log10", "log68", "log7", "log42", "log44")
SOURCE_CONTRADICTION_BORES = {"log44"}                 # banked M8.25/M9.0

# Banked M9.3 controls (must reproduce EXACTLY through the shipped core).
EXPECT_CLEAN_END = {"log42": 105, "log72": 117, "log12": 121, "log2": 148,
                    "log10": 152, "log57": 157, "log7": 163}
EXPECT_JUNCTIONS = {("log27", 152, "log10"), ("log39", 117, "log72"),
                    ("log65", 163, "log7")}
EXPECT_BORE_CENSUS = {
    "ENDPOINT_ATTRIBUTED": 7, "JUNCTION_ORIGIN": 3, "PDF_KMZ_CONTRADICTION": 1,
    "SOURCE_CONTRADICTION": 1, "SHEET_NEIGHBOR_REJECTED": 46,  # RECON-2A: +log37/log38
}
# customer-literal guard mirror (the convention-clean-core gate)
FORBIDDEN = re.compile(r"(?i)\b(brenham|odot|tulsa|creek|nextlink|verofy)\b")
CORE_PLAN_VOCAB = ("terminal_port_hh", "FLOWER POT", "INSTALLER HH", "PORT HH",
                   "SPLICE LOC")


def _lines_by_sheet(plan, bore, offset) -> Dict[int, list]:
    return {s: plan.lines(s, offset) for s in sorted(set(bore.sheet_refs))}


def main() -> int:
    kmz_path, kmz_how = resolve_kmz()
    corpus_dir, how = resolve_corpus()
    print(f"[m9.3.1] kmz   : {kmz_path}  ({kmz_how})")
    print(f"[m9.3.1] corpus: {corpus_dir}  ({how})")
    if not os.path.isfile(kmz_path) or not os.path.isfile(PDF) \
            or not os.path.isdir(corpus_dir):
        print("[m9.3.1] STOP: inputs missing")
        return 2
    paths = enumerate_corpus(corpus_dir)
    if len(paths) != EXPECTED_COUNT:
        print(f"[m9.3.1] STOP: corpus drift ({len(paths)})")
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
    try:
        dialect = select_dialect(plan)
        offset = dialect.calibrate(plan, 13)
        for p in paths:
            try:
                bore = load_borelog(str(p))
            except Exception:
                continue
            r = TA.attribute_bore(
                bore.bore_id,
                feet_to_station(bore.station_start_ft),
                feet_to_station(bore.station_end_ft),
                _lines_by_sheet(plan, bore, offset),
                BRENHAM_TERMINUS_PROFILE,
                kmz_model=model,
                source_contradiction=bore.bore_id in SOURCE_CONTRADICTION_BORES)
            results.append(r)
    finally:
        plan.close()

    by_id = {r.bore_id: r for r in results}
    bore_census = collections.Counter(r.disposition for r in results)
    clean_end = {r.bore_id: r.end.ap for r in results
                 if r.end.result == TA.ENDPOINT_ATTRIBUTED}
    junctions = {(j["start_bore"], j["terminal_ap"], j["end_bore_owner"])
                 for j in TA.resolve_junctions(results)}
    uniq_violations = TA.check_terminal_uniqueness(results)

    # ---- GATES ---------------------------------------------------------------
    g1 = (len(model.structures) == EXPECT_STRUCTURES
          and len(model.routes) == EXPECT_ROUTES
          and all(b in by_id for b in TARGETS)
          and len(results) >= EXPECTED_COUNT - 2)
    print(f"[m9.3.1] {'PASS' if g1 else 'FAIL'}  G1 inputs intact: KMZ "
          f"{len(model.structures)}/{len(model.routes)}; targets present; "
          f"{len(results)} bores attributed via the shipped core")
    ok &= g1

    g2 = (clean_end == EXPECT_CLEAN_END
          and all(by_id[b].end.kmz_join == "KMZ_TERMINAL_JOIN_BOUND"
                  for b in EXPECT_CLEAN_END))
    print(f"[m9.3.1] {'PASS' if g2 else 'FAIL'}  G2 7 clean END attributions "
          f"reproduce (each KMZ-join BOUND): {dict(sorted(clean_end.items()))}")
    ok &= g2

    l68 = by_id["log68"]
    n148 = [n for n in l68.sheet_neighbors if n.ap == 148]
    g3 = (l68.disposition == TA.SHEET_NEIGHBOR_REJECTED
          and not l68.start.attributed and not l68.end.attributed
          and len(n148) == 1
          and n148[0].owning_station not in (l68.start_station, l68.end_station))
    print(f"[m9.3.1] {'PASS' if g3 else 'FAIL'}  G3 log68 AP-148 SHEET_NEIGHBOR_"
          f"REJECTED (owns STA {n148[0].owning_station if n148 else '?'})")
    ok &= g3

    l7, l42 = by_id["log7"], by_id["log42"]
    g4 = (l7.end.result == TA.ENDPOINT_ATTRIBUTED and l7.end.ap == 163
          and l7.end.kmz_join == "KMZ_TERMINAL_JOIN_BOUND"
          and l42.end.result == TA.ENDPOINT_ATTRIBUTED and l42.end.ap == 105
          and l42.end.kmz_join == "KMZ_TERMINAL_JOIN_BOUND")
    print(f"[m9.3.1] {'PASS' if g4 else 'FAIL'}  G4 M9.1 controls via the extractor: "
          f"log7 END AP-163, log42 END AP-105 -> both join BOUND")
    ok &= g4

    l44 = by_id["log44"]
    g5 = (l44.disposition == TA.SOURCE_CONTRADICTION
          and completion_bucket(lane_by_id["log44"], "log44")[0] == "SOURCE_OR_KMZ_REQUIRED")
    print(f"[m9.3.1] {'PASS' if g5 else 'FAIL'}  G5 log44 SOURCE_CONTRADICTION "
          f"(banked; bucket pinned)")
    ok &= g5

    starts_attributed = [r.bore_id for r in results
                         if r.start.result == TA.ENDPOINT_ATTRIBUTED]
    g6 = (junctions == EXPECT_JUNCTIONS and not starts_attributed)
    print(f"[m9.3.1] {'PASS' if g6 else 'FAIL'}  G6 junction-origins (NOT ownership): "
          f"{sorted(junctions)}; START-terminal ownership rejected "
          f"(starts attributed={starts_attributed})")
    ok &= g6

    l46 = by_id.get("log46")
    g7 = (l46 is not None and l46.disposition == TA.PDF_KMZ_CONTRADICTION
          and l46.end.ap == 161 and l46.end.kmz_join in TA._CONTRA_JOINS)
    print(f"[m9.3.1] {'PASS' if g7 else 'FAIL'}  G7 log46 PDF_KMZ_CONTRADICTION "
          f"(AP-161; join={l46.end.kmz_join if l46 else '?'})")
    ok &= g7

    g8 = (not uniq_violations and len(clean_end) == 7
          and len(set(clean_end.values())) == 7)
    print(f"[m9.3.1] {'PASS' if g8 else 'FAIL'}  G8 one-terminal-per-END uniqueness "
          f"(violations={uniq_violations}; 7 distinct terminals)")
    ok &= g8

    g9 = dict(bore_census) == EXPECT_BORE_CENSUS and sum(bore_census.values()) == 58  # RECON-2A: +log37/log38
    print(f"[m9.3.1] {'PASS' if g9 else 'FAIL'}  G9 bore census reproduces M9.3: "
          f"{dict(sorted(bore_census.items()))}")
    ok &= g9

    # G10: the CORE is convention-agnostic -- zero customer literals AND zero plan
    # vocabulary (terminal class / keywords come only from the injected profile).
    core_src = inspect.getsource(TA)
    leaks = [ln.strip() for ln in core_src.splitlines() if FORBIDDEN.search(ln)]
    vocab = [v for v in CORE_PLAN_VOCAB if v in core_src]
    g10 = not leaks and not vocab
    print(f"[m9.3.1] {'PASS' if g10 else 'FAIL'}  G10 universal core: 0 customer "
          f"literals (leaks={leaks}); 0 plan vocab in core (found={vocab})")
    ok &= g10

    # G11: read-only / UNWIRED -- nothing rendered; no placement-path module imports
    # the extractor; zero bores moved.
    import truelinev2.match.engine as eng
    import truelinev2.match.symbol_conduit_lane as scl
    import truelinev2.review.reviewer_service as rsvc
    import truelinev2.service as svcmod
    wired = any("terminus_attribution" in inspect.getsource(m)
                for m in (eng, scl, rsvc, svcmod))
    g11 = not list(OUT_DIR.glob("*.png")) and not wired
    print(f"[m9.3.1] {'PASS' if g11 else 'FAIL'}  G11 read-only: no PNG; extractor "
          f"UNWIRED from engine/lane/service (wired={wired}); 0 bores moved")
    ok &= g11

    # G12: no contract drift.
    g12 = (full.lane_counts == BANKED_FULLEST_LANES
           and completion_bucket(lane_by_id["log68"], "log68")[0] == "SOURCE_OR_KMZ_REQUIRED"
           and completion_bucket(lane_by_id["log10"], "log10")[0] == "DRAWABLE_REVIEW")
    print(f"[m9.3.1] {'PASS' if g12 else 'FAIL'}  G12 no contract drift: M8.11 lanes "
          f"{full.lane_counts == BANKED_FULLEST_LANES}; buckets pinned")
    ok &= g12

    report = {
        "milestone": ("truelinev2 M9.3.1 -- TERMINUS_ATTRIBUTION extractor "
                      "(shipped, UNWIRED/unconsumed; universal core + injected "
                      "profile; proof-only; zero bores moved)"),
        "taxonomy_note": ("bore-disposition census + all named controls reproduce "
                          "M9.3 Phase 0; per-endpoint taxonomy is a strict refinement "
                          "(NO_AP_SPLICE_PAIR split into NO_AP_SPLICE_PAIR + "
                          "NON_TERMINAL_ENDPOINT) -- no disposition/control changes"),
        "kmz_path": kmz_path, "corpus_dir": corpus_dir, "plan_pdf": PDF,
        "verdict": "PASS" if ok else "FAILURE",
        "core_module": "truelinev2/match/terminus_attribution.py (zero plan-set literals)",
        "profile": "truelinev2/extract/terminus_profile.py BRENHAM_TERMINUS_PROFILE",
        "bore_disposition_census": dict(sorted(bore_census.items())),
        "clean_end_attributions": [{"bore_id": b, "terminal_ap": ap,
                                    "kmz_join": by_id[b].end.kmz_join}
                                   for b, ap in sorted(clean_end.items())],
        "bore_to_bore_junctions": TA.resolve_junctions(results),
        "pdf_kmz_contradictions": sorted(r.bore_id for r in results
                                         if r.disposition == TA.PDF_KMZ_CONTRADICTION),
        "terminal_end_uniqueness_violations": uniq_violations,
        "source_contradiction_injected_banked": sorted(SOURCE_CONTRADICTION_BORES),
        "targets": [by_id[b].to_dict() for b in TARGETS if b in by_id],
        "unwired_unconsumed": True, "bores_moved": 0,
        "next_step": ("a run-assembly lane consuming the 3 junctions + the 7 clean "
                      "terminal anchors (still gated, REVIEW-only); owner source "
                      "re-read for log46 (PDF<->KMZ) + log44 (325'). No consumer "
                      "wiring in this milestone."),
    }
    (OUT_DIR / "terminus_attribution_extract.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8")

    print(f"\n[m9.3.1] bore dispositions: {dict(sorted(bore_census.items()))}")
    print(f"[m9.3.1] clean END attributions: {len(clean_end)} | junctions: "
          f"{len(junctions)} | PDF<->KMZ contradictions: {report['pdf_kmz_contradictions']}")
    print(f"[m9.3.1] verdict: {report['verdict']}")
    print(f"[m9.3.1] report -> {OUT_DIR / 'terminus_attribution_extract.json'}")
    return 0 if ok else 4


if __name__ == "__main__":
    raise SystemExit(main())
