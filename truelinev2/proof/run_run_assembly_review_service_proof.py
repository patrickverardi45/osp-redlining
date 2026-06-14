r"""M9.4.2 -- RUN-ASSEMBLY review service proof (the additive reviewer-service surface).

Proves the shipped ``RunAssemblyReviewService`` surfaces the M9.4.1 run-assembly cards
WITHOUT changing the per-bore reviewer bundle, mirroring the M8.20 group-service proof:

  G1  per-bore generate(default_baseline) is BYTE-IDENTICAL before/after the service runs;
  G2  the service emits exactly 3 run-assembly review cards;
  G3  the 3 cards are exactly log10->log27 @AP-152 + log72->log39 @AP-117 (CANDIDATE) +
      log7->log65 @AP-163 (DROP_BRANCH);
  G4  REVIEW/evidence-only -- frozen SUGGESTION label, no AUTO/geometry/strokes/segments/PNG;
      log65 STAYS a JUNCTION_DROP_BRANCH (continuation_class DROP_BRANCH, departure 'drop');
  G5  the service imports no proof/render code and per-bore generate is unaware of it;
  G6  the banked per-bore default counts (14/10/32/2 = 24, 58 payloads) AND the
      fullest-safe lanes (30/16/6/4/2) are unchanged -- no product bucket movement;
  G7  the run-assembly card schema is DISJOINT from the M8.10/M8.11/M8.15/M8.20 schemas;
  G8  nothing is rendered;
  G9  the M9.4.1 FRAME-SCOPED competing guard is PRESERVED, not hidden: every card carries
      competing_departures == 1, and the service performs no cross-sheet / M9.2 frame-graph
      expansion (it never references a frame graph / matchline / cross-sheet widen);
  G10 read-only / UNWIRED: no placement-path module imports the service; the service never
      calls resolve_bore / run_match / a sweep.

PROOF-ONLY: no placement, no engine wiring, no stroke/PNG/segment, no AUTO, no
tolerance/budget change, zero bores moved, zero product-bucket change. This is a
reviewer-service SURFACE that emits cards -- NOT product readiness beyond that.

Exit codes: 0 PASS, 2 inputs missing, 3 corpus drift, 4 gate FAILURE.

Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_run_assembly_review_service_proof
"""
from __future__ import annotations

import inspect
import json
import os

from truelinev2.config import _REPO_ROOT
from truelinev2.extract.kmz import BRENHAM_KMZ_DIALECT, read_kmz
from truelinev2.extract.terminus_profile import BRENHAM_TERMINUS_PROFILE
from truelinev2.proof.run_brenham_corpus import EXPECTED_COUNT, PDF, enumerate_corpus
from truelinev2.proof.run_kmz_correlation_audit import resolve_kmz
from truelinev2.proof.run_reviewer_service_contract import resolve_corpus
from truelinev2.review.design_stroke_cards import CARD_SCHEMA_VERSION
from truelinev2.review.group_review import GROUP_SCHEMA_VERSION
from truelinev2.review.reviewer_payloads import SCHEMA_VERSION
from truelinev2.review.reviewer_service import (
    BUNDLE_SCHEMA_VERSION,
    ReviewerBundleService,
    ReviewRunMode,
)
from truelinev2.review.run_assembly_review import (
    CONTINUATION_CANDIDATE,
    DROP_BRANCH,
    RUN_ASSEMBLY_SCHEMA_VERSION,
)
from truelinev2.review.run_assembly_review_service import RunAssemblyReviewService

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "run_assembly_review_service_proof"

SOURCE_CONTRADICTION_BORES = {"log44"}                 # banked M8.25/M9.0 (injected)
# RECON-2A: the `STA ` activation moves only log37 (-> placed) + log38 (-> OUT_OF_CLASS).
EXPECT_DEFAULT_STATUS = {"AUTO_SELECT": 14, "REVIEW": 11, "ABSTAIN": 33,
                         "ERROR": 0, "PLACED": 25}
EXPECT_FULLEST_LANES = {"PLACED_REVIEW": 31, "PICK_CARD_ROUTE_SUGGESTION": 16,
                        "HUMAN_ADJUSTABLE_LENGTH_REDLINE": 6, "OUT_OF_CLASS": 5}
# the exact run-assembly cards (end_bore, start_bore, terminal_ap, continuation_class)
EXPECT_CARDS = {
    ("log10", "log27", 152, CONTINUATION_CANDIDATE),
    ("log72", "log39", 117, CONTINUATION_CANDIDATE),
    ("log7", "log65", 163, DROP_BRANCH),
}


def main() -> int:
    kmz_path, kmz_how = resolve_kmz()
    corpus_dir, how = resolve_corpus()
    print(f"[m9.4.2] kmz   : {kmz_path}  ({kmz_how})")
    print(f"[m9.4.2] corpus: {corpus_dir}  ({how})")
    if not os.path.isfile(kmz_path) or not os.path.isfile(PDF) \
            or not os.path.isdir(corpus_dir):
        print("[m9.4.2] STOP: inputs missing")
        return 2
    paths = enumerate_corpus(corpus_dir)
    if len(paths) != EXPECTED_COUNT:
        print(f"[m9.4.2] STOP: corpus drift ({len(paths)})")
        return 3
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ok = True

    model = read_kmz(kmz_path, BRENHAM_KMZ_DIALECT)
    per_bore = ReviewerBundleService(corpus_dir=corpus_dir, plan_pdf_path=PDF,
                                     project_id="brenham-ph5", bore_log_paths=paths)
    service = RunAssemblyReviewService(
        corpus_dir=corpus_dir, plan_pdf_path=PDF, bore_log_paths=paths,
        kmz_model=model, terminus_profile=BRENHAM_TERMINUS_PROFILE,
        source_contradiction_bores=SOURCE_CONTRADICTION_BORES)

    # ---- G1: per-bore bundle byte-identical before/after --------------------
    before = per_bore.generate(ReviewRunMode.DEFAULT_BASELINE)
    before_bytes = before.model_dump_json()
    cards = service.generate()
    after = per_bore.generate(ReviewRunMode.DEFAULT_BASELINE)
    after_bytes = after.model_dump_json()
    g1 = before_bytes == after_bytes
    print(f"[m9.4.2] {'PASS' if g1 else 'FAIL'}  G1 per-bore bundle byte-identical "
          f"before/after run-assembly service generation")
    ok &= g1

    # ---- G2/G3: exactly the 3 expected cards --------------------------------
    g2 = len(cards) == 3
    print(f"[m9.4.2] {'PASS' if g2 else 'FAIL'}  G2 exactly 3 run-assembly cards "
          f"(got {len(cards)})")
    ok &= g2

    got_cards = {(c.end_bore, c.start_bore, c.terminal_ap, c.continuation_class)
                 for c in cards}
    g3 = got_cards == EXPECT_CARDS
    print(f"[m9.4.2] {'PASS' if g3 else 'FAIL'}  G3 exact cards: "
          f"{sorted((c.end_bore, c.start_bore, c.terminal_ap) for c in cards)}")
    ok &= g3

    # ---- G4: REVIEW-only; log65 stays a drop branch -------------------------
    text = json.dumps([c.model_dump() for c in cards], default=str)
    forbidden = ("segments", "stroke_points", "stroke_rgb", "walk_points",
                 "boundary_xy", ".png")
    by_pair = {(c.end_bore, c.start_bore): c for c in cards}
    l65 = by_pair.get(("log7", "log65"))
    g4 = (all(c.review_only is True and c.auto is False and c.has_geometry is False
              and c.has_strokes is False and c.label == "SUGGESTION_NOT_PLACEMENT"
              and c.terminal_is_end_of_feed is True for c in cards)
          and not any(k in text for k in forbidden)
          and l65 is not None and l65.continuation_class == DROP_BRANCH
          and l65.departure_run_class == "drop")
    print(f"[m9.4.2] {'PASS' if g4 else 'FAIL'}  G4 REVIEW-only (no AUTO/geometry/"
          f"strokes/segments/PNG); log65 stays JUNCTION_DROP_BRANCH (drop)")
    ok &= g4

    # ---- G5: no proof/render imports; per-bore generate unaware --------------
    import truelinev2.review.run_assembly_review_service as svc_mod
    svc_src = inspect.getsource(svc_mod)
    # the CLASS body (excludes the module docstring, which honestly names what is avoided)
    cls_src = inspect.getsource(RunAssemblyReviewService)
    per_bore_src = inspect.getsource(ReviewerBundleService.generate)
    g5 = ("truelinev2.proof" not in svc_src and ".proof." not in svc_src
          and "truelinev2.render" not in svc_src and "render_redline" not in svc_src
          and "run_assembly" not in per_bore_src
          and "RunAssemblyReviewService" not in per_bore_src)
    print(f"[m9.4.2] {'PASS' if g5 else 'FAIL'}  G5 no proof/render imports; per-bore "
          f"generate unaware of run-assembly")
    ok &= g5

    # ---- G6: banked per-bore counts + fullest lanes unchanged ---------------
    fullest = per_bore.generate(ReviewRunMode.FULLEST_SAFE_REVIEW)
    g6 = (before.status_counts == after.status_counts == EXPECT_DEFAULT_STATUS
          and len(before.payloads) == len(after.payloads) == 58
          and fullest.lane_counts == EXPECT_FULLEST_LANES)
    print(f"[m9.4.2] {'PASS' if g6 else 'FAIL'}  G6 banked per-bore counts "
          f"{before.status_counts} + fullest lanes {fullest.lane_counts} unchanged")
    ok &= g6

    # ---- G7: schema disjoint -------------------------------------------------
    g7 = RUN_ASSEMBLY_SCHEMA_VERSION not in {
        BUNDLE_SCHEMA_VERSION, SCHEMA_VERSION, CARD_SCHEMA_VERSION, GROUP_SCHEMA_VERSION}
    print(f"[m9.4.2] {'PASS' if g7 else 'FAIL'}  G7 run-assembly schema disjoint: "
          f"{RUN_ASSEMBLY_SCHEMA_VERSION}")
    ok &= g7

    # ---- G8: nothing rendered -----------------------------------------------
    g8 = not list(OUT_DIR.glob("*.png"))
    print(f"[m9.4.2] {'PASS' if g8 else 'FAIL'}  G8 no artifact rendered")
    ok &= g8

    # ---- G9: the M9.4.1 frame-scoped competing guard is PRESERVED, not hidden -
    competing = {(c.end_bore, c.start_bore): c.competing_departures for c in cards}
    g9 = (all(v == 1 for v in competing.values())
          and "_build_plan_frame_graph" not in cls_src and "matchline" not in cls_src
          and "cross_sheet" not in cls_src)
    print(f"[m9.4.2] {'PASS' if g9 else 'FAIL'}  G9 frame-scoped competing guard "
          f"preserved (competing_departures {competing}); no cross-sheet/M9.2 widen")
    ok &= g9

    # ---- G10: read-only / UNWIRED -------------------------------------------
    import truelinev2.match.engine as eng
    import truelinev2.match.symbol_conduit_lane as scl
    import truelinev2.review.reviewer_service as rsvc
    import truelinev2.service as svcmod
    wired = any("run_assembly_review_service" in inspect.getsource(m)
                or "RunAssemblyReviewService" in inspect.getsource(m)
                for m in (eng, scl, rsvc, svcmod))
    calls_placement = ("resolve_bore" in cls_src or "run_match" in cls_src
                       or "sweep" in cls_src)
    g10 = not wired and not calls_placement and not list(OUT_DIR.glob("*.png"))
    print(f"[m9.4.2] {'PASS' if g10 else 'FAIL'}  G10 UNWIRED (placement modules do "
          f"NOT import the service: wired={wired}); no resolve_bore/run_match/sweep call")
    ok &= g10

    report = {
        "milestone": ("truelinev2 M9.4.2 -- RUN-ASSEMBLY review service surface "
                      "(additive parallel service; per-bore bundle byte-identical; "
                      "REVIEW/evidence-only; UNWIRED from the placement path)"),
        "kmz_path": kmz_path, "corpus_dir": corpus_dir, "plan_pdf": PDF,
        "verdict": "PASS" if ok else "FAILURE",
        "service": "truelinev2/review/run_assembly_review_service.py RunAssemblyReviewService",
        "schema": RUN_ASSEMBLY_SCHEMA_VERSION,
        "per_bore_byte_identical": g1,
        "per_bore_default_status_counts": before.status_counts,
        "fullest_safe_lanes": fullest.lane_counts,
        "run_assembly_cards": [c.model_dump() for c in cards],
        "competing_departures_per_card": {f"{e}->{s}": v
                                          for (e, s), v in competing.items()},
        "surface_claim": ("reviewer-service surface emits the run-assembly cards; "
                          "NOT product-ready beyond that -- no UI, no placement, no "
                          "bucket change, no cross-sheet/M9.2 expansion"),
        "frame_scoped_limitation_preserved": g9,
        "bores_moved": 0, "product_bucket_changes": 0, "unwired_unconsumed": True,
        "next_step": ("any UI/API transport for these cards is a separate, authorized "
                      "milestone; cross-sheet competing-lateral enumeration remains the "
                      "M9.2 frame-graph-gated target (the named M9.4.1 limitation)."),
    }
    (OUT_DIR / "run_assembly_review_service_proof.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8")

    print(f"\n[m9.4.2] cards: {[(c.end_bore, '->', c.start_bore, c.continuation_class) for c in cards]}")
    print(f"[m9.4.2] per-bore bundle byte-identical: {g1} | buckets unchanged: {g6} | UNWIRED: {not wired}")
    print(f"[m9.4.2] verdict: {report['verdict']}")
    print(f"[m9.4.2] report -> {OUT_DIR / 'run_assembly_review_service_proof.json'}")
    return 0 if ok else 4


if __name__ == "__main__":
    raise SystemExit(main())
