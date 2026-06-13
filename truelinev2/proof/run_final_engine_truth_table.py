r"""M8.27 -- the final all-58 engine TRUTH TABLE + completion map (proof-only).

ONE authoritative completion map for the full Brenham corpus. Joins the three
SHIPPED truth surfaces per bore -- without altering any of them:

  * PRODUCT axis (authoritative): the M8.11 reviewer service bundle under the
    ``fullest_safe_review`` mode (M8.5 + M8.8 opt-ins) -> exactly one M8.10
    ``ReviewerLane`` per bore. This is product truth (what the reviewer does).
  * ROUTE-STROKE axis (proof-only, default-OFF lane): the M8.14.c symbol_conduit
    lane ``resolve_bore`` status -> can a route-FOLLOWING red stroke be drawn?
    The lane is UNWIRED; a stroke-eligible status is a PROOF artifact, NOT a
    product placement. The two axes are orthogonal (e.g. log59 is stroke-
    eligible yet a product PICK_CARD; log8/32/42 are product PLACED yet stroke
    STRUCTURE_IDENTITY).
  * GROUP axis (separate review surface): the M8.20 group-review card -- ONE
    shared-alignment card (log8 + log32). It is the 59th review item (58 per-
    bore payloads + 1 group card); members keep their UNCHANGED per-bore lane.

Every bore gets a derived ``completion_bucket`` (a UI-readiness VIEW over the
contract lane -- it never rewrites the M8.10 lane) plus the boolean columns the
UI needs: can_draw_now / can_show_review / needs_source_kmz_owner /
engine_law_required, the exact missing-evidence target, and the proof/blocker
path. ``completion_bucket`` is a pure function of the contract lane (+ a banked
4-bore OUT_OF_CLASS refinement grounded in M8.16/M8.25/M8.26).

PROOF-ONLY: no placement change, no engine wiring, no stroke/PNG/segment, no
AUTO, no tolerance/budget change. Reads the shipped M8.10/M8.11/M8.15/M8.20
contracts + the symbol_conduit lane; changes none of them. Census frozen.

Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_final_engine_truth_table
"""
from __future__ import annotations

import collections
import json
import os
import re
from pathlib import Path
from typing import Dict, List, Optional

from truelinev2.config import _REPO_ROOT
from truelinev2.extract.registry import select_dialect
from truelinev2.extract.structure_position import BRENHAM_LANE_DIALECT
from truelinev2.ingest.normalize import load_borelog
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.match.symbol_conduit_lane import resolve_bore as stroke_resolve
from truelinev2.proof.run_brenham_corpus import EXPECTED_COUNT, PDF, enumerate_corpus
from truelinev2.proof.run_reviewer_service_contract import resolve_corpus
from truelinev2.review.group_review import GROUP_SCHEMA_VERSION
from truelinev2.review.group_review_service import GroupReviewService
from truelinev2.review.reviewer_payloads import ReviewerLane
from truelinev2.review.reviewer_service import (ReviewerBundleService,
                                                ReviewRunMode)
from truelinev2.service import _build_plan_frame_graph

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "final_engine_truth_table"

# ---- completion buckets (a UI-readiness VIEW; never a contract change) -------
B_DRAWABLE = "DRAWABLE_REVIEW"
B_GROUP = "GROUP_REVIEW"
B_PICK = "PICK_CARD_REVIEW"
B_ADJUST = "HUMAN_ADJUSTABLE_REVIEW"
B_SOURCE = "SOURCE_REVIEW_REQUIRED"
B_OUT = "OUT_OF_CLASS"
B_SRC_KMZ = "SOURCE_OR_KMZ_REQUIRED"
B_ENGINE = "ENGINE_LAW_REQUIRED"
B_PROOF_ONLY = "PROOF_ONLY_NOT_PRODUCT"

# Direct contract-lane -> completion-bucket map (no blur: 1:1 with M8.10).
_LANE_TO_BUCKET = {
    ReviewerLane.PLACED_REVIEW.value: B_DRAWABLE,
    ReviewerLane.PICK_CARD_ROUTE_SUGGESTION.value: B_PICK,
    ReviewerLane.HUMAN_ADJUSTABLE_LENGTH_REDLINE.value: B_ADJUST,
    ReviewerLane.SOURCE_REVIEW_REQUIRED.value: B_SOURCE,
    ReviewerLane.UNSAFE_ABSTAIN.value: "UNSAFE_ABSTAIN",
}

# The 4 OUT_OF_CLASS bores refined by their NAMED M8.7 blocker (grounded, banked).
# OUT_OF_CLASS is a routing bucket: M8.7 prove_interval_path runs BEFORE the M8.9
# frame-ownership classifier, so a bore whose M8.7 verdict is non-conflict is
# routed here even when its CONTENT is review-actionable. We refine by that
# verdict + the banked probe findings:
#   - source/plan/geo gaps with no printed plan lever -> SOURCE_OR_KMZ_REQUIRED
#   - M87_MULTIPLE_PATHS_PICK_CARD with genuinely printed rival runs (no source
#     defect) -> PICK_CARD_REVIEW: a human picks the route NOW; an engine auto-
#     pick discriminator is an OPTIONAL later enhancement, never a precondition
#     (the structurally identical M8.9 parallel-runs case ships as a product
#     PICK_CARD for log36/log59/log66). Audited M8.27.
# Drift in the OUT_OF_CLASS set fails the gate loudly.
OUT_OF_CLASS_REFINE = {
    "log43": (B_SRC_KMZ, "M8.25: print-10 drawn axis stops at 45+33; "
              "45+33->59+19 (1386') is a printed-evidence VOID -> owner "
              "bore_log17 Segment-A source re-read or KMZ/geo"),
    "log44": (B_SRC_KMZ, "M8.25: 325' span matches NO print-18 run "
              "(source-vs-plan mismatch) -> owner source re-read"),
    "log68": (B_SRC_KMZ, "M8.16: the bore's sheets print NO matchline frame "
              "equation -> unprovable from plan text; geo/KMZ corroboration"),
    "log11": (B_PICK, "M8.7 MULTIPLE_PATHS_PICK_CARD: two distinct PRINTED "
              "ladder intervals (parallel runs) hold the bore end, no source "
              "defect -> a human pick selects the route NOW; an engine auto-pick "
              "(printed-interval membership discriminator) is an OPTIONAL later "
              "enhancement, not a precondition for review"),
}

# Route-stroke statuses that need NEW engine doctrine to ever draw the route-
# following stroke (the placement may already exist on the product axis).
_STROKE_ENGINE_LAW = {
    "STRUCTURE_IDENTITY_BINDING_REQUIRED": "origin/structure-identity binder",
    "DESIGN_PATH_NOT_TRACEABLE": "a parallel-strand discriminator",
}
# Route-stroke statuses whose missing evidence is source/geo (not an engine law).
_STROKE_SOURCE_KMZ = {
    "END_IDENTITY_UNPRINTED": "a printed end-structure identity (M8.26 honest-"
                              "negative: no zero-false gate) -> KMZ/geo or "
                              "SOURCE_REVIEW",
    "CROSS_SHEET_CONTINUATION_REQUIRED": "a printed matchline equation / "
                                         "reciprocal callout (M8.16) -> often "
                                         "geo/KMZ",
}

# Documented split-source families (M8.25; engine consumes NO family relation --
# annotation only, never placement proof).
KNOWN_FAMILIES = {"bore_log17": ("log43", "log44")}

BANKED_STROKE_CENSUS = {
    "END_IDENTITY_UNPRINTED": 25,
    "CROSS_SHEET_CONTINUATION_REQUIRED": 13,
    "PICK_CARD_WITH_END_ANCHOR": 5,
    "END_POSITION_UNRESOLVED": 5,
    "STROKE_ELIGIBLE_REVIEW": 4,
    "STRUCTURE_IDENTITY_BINDING_REQUIRED": 3,
    "DESIGN_PATH_NOT_TRACEABLE": 1,
    "BORE_SOURCE_UNPARSEABLE": 2,
}
BANKED_FULLEST_LANES = {
    "PLACED_REVIEW": 30, "PICK_CARD_ROUTE_SUGGESTION": 16,
    "HUMAN_ADJUSTABLE_LENGTH_REDLINE": 6, "OUT_OF_CLASS": 4,
    "SOURCE_REVIEW_REQUIRED": 2,
}
BANKED_DEFAULT_STATUS = {"AUTO_SELECT": 14, "REVIEW": 10, "ABSTAIN": 32,
                         "ERROR": 2, "PLACED": 24}
CONTROLS = {"log8": ("PLACED_REVIEW", "STRUCTURE_IDENTITY_BINDING_REQUIRED", True),
            "log32": ("PLACED_REVIEW", "STRUCTURE_IDENTITY_BINDING_REQUIRED", True),
            "log42": ("PLACED_REVIEW", "STRUCTURE_IDENTITY_BINDING_REQUIRED", False)}


def _num(b: str) -> int:
    m = re.search(r"(\d+)", b)
    return int(m.group(1)) if m else 0


def _family_of(bore) -> Optional[str]:
    src = Path(bore.source_file).stem if bore.source_file else None
    for fam, members in KNOWN_FAMILIES.items():
        if bore.bore_id in members:
            return fam
    return src   # standalone: its own source id is its "family"


def completion_bucket(product_lane: str, bore_id: str):
    """Pure: contract lane -> UI-readiness bucket (+ OUT_OF_CLASS refine reason).
    A 1:1 map for the five non-OUT_OF_CLASS lanes; OUT_OF_CLASS refines per the
    banked named blocker. Never rewrites the contract lane -- a derived VIEW."""
    if product_lane == ReviewerLane.OUT_OF_CLASS.value:
        return OUT_OF_CLASS_REFINE.get(bore_id, (B_OUT, "unrefined out-of-class"))
    return _LANE_TO_BUCKET[product_lane], None


def _build_rows(payloads, stroke_status, group_members, bores) -> List[dict]:
    bore_by_id = {b.bore_id: b for b in bores}
    rows = []
    for p in payloads:
        bid = p.bore_id
        lane = p.lane.value
        st = stroke_status.get(bid, "BORE_SOURCE_UNPARSEABLE")
        bucket, oc_reason = completion_bucket(lane, bid)

        # can_draw_now is a PRODUCT-placement fact (only PLACED_REVIEW draws a
        # redline now). The review/source/engine-law columns derive from the
        # completion BUCKET (the UI-readiness view) so a routing-order OUT_OF_
        # CLASS pick-card (log11) is correctly review-eligible.
        can_draw = (lane == ReviewerLane.PLACED_REVIEW.value)
        can_show_review = bucket in (B_DRAWABLE, B_PICK, B_ADJUST)
        needs_src = bucket in (B_SOURCE, B_SRC_KMZ)
        # engine-law: an OUT_OF_CLASS refined to ENGINE_LAW (product-blocked on a
        # new law), OR a placed bore whose proof-only ROUTE-STROKE needs new
        # doctrine (the placement already exists; only the stroke does not)
        stroke_law = _STROKE_ENGINE_LAW.get(st)
        engine_law = (bucket == B_ENGINE) or bool(stroke_law)

        # exact missing-evidence target
        if bucket == B_DRAWABLE:
            missing = (f"route-following stroke needs {stroke_law}"
                       if stroke_law else
                       (f"route stroke source/geo: {_STROKE_SOURCE_KMZ[st]}"
                        if st in _STROKE_SOURCE_KMZ else None))
        elif oc_reason:
            missing = oc_reason
        else:
            missing = (p.named_missing_relationship
                       or (p.candidates[0].missing_relationship_to_promote
                           if p.candidates else None)
                       or (p.suspect_values.get("fix")
                           if p.suspect_values else None))

        # proof / blocker path
        if bucket == B_DRAWABLE:
            proof = f"M8.11 PLACED_REVIEW ({p.reason_code}; {p.confidence_class.value})"
        elif bucket == B_PICK:
            proof = "M8.9 frame-ownership -> M8.10 PICK_CARD_ROUTE_SUGGESTION"
        elif bucket == B_ADJUST:
            proof = "M8.9 footage-certain -> M8.10 HUMAN_ADJUSTABLE_LENGTH_REDLINE"
        elif bucket == B_SOURCE:
            proof = "M8.10 SOURCE_REVIEW_REQUIRED (ingest-unparseable)"
        else:  # SRC_KMZ / ENGINE from OUT_OF_CLASS
            proof = f"M8.7/M8.10 OUT_OF_CLASS ({p.reason_code})"

        rows.append({
            "bore_id": bid,
            "source_id": (Path(bore_by_id[bid].source_file).stem
                          if bid in bore_by_id and bore_by_id[bid].source_file
                          else None),
            "source_family": (_family_of(bore_by_id[bid])
                              if bid in bore_by_id else None),
            "sheets": list(p.sheets),
            "span": (f"{p.station_start_sta}->{p.station_end_sta}"
                     if p.station_start_sta else None),
            "product_lane": lane,                       # M8.10 contract (verbatim)
            "confidence_class": (p.confidence_class.value
                                 if p.confidence_class else None),
            "stroke_status": st,                        # symbol_conduit (proof-only)
            "group_review_member": bid in group_members,
            "completion_bucket": bucket,                # derived UI-readiness view
            "can_draw_now": can_draw,
            "can_show_review": can_show_review,
            "needs_source_kmz_owner": needs_src,
            "engine_law_required": engine_law,
            "more_doctrine_required": engine_law,
            "proof_or_blocker": proof,
            "missing_evidence": missing,
            # proof-only route stroke exists but is NOT a product placement
            "proof_only_route_stroke_eligible": st == "STROKE_ELIGIBLE_REVIEW",
        })
    rows.sort(key=lambda r: _num(r["bore_id"]))
    return rows


def main() -> int:
    corpus_dir, how = resolve_corpus()
    print(f"[m8.27] corpus dir : {corpus_dir}  ({how})")
    if not os.path.isfile(PDF) or not os.path.isdir(corpus_dir):
        print("[m8.27] STOP: inputs missing")
        return 2
    paths = enumerate_corpus(corpus_dir)
    if len(paths) != EXPECTED_COUNT:
        print(f"[m8.27] STOP: corpus drift ({len(paths)})")
        return 3
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ok = True

    # --- PRODUCT axis (M8.11) -------------------------------------------------
    svc = ReviewerBundleService(corpus_dir=corpus_dir, plan_pdf_path=PDF,
                                project_id="brenham-ph5", bore_log_paths=paths)
    full = svc.generate(ReviewRunMode.FULLEST_SAFE_REVIEW)
    default = svc.generate(ReviewRunMode.DEFAULT_BASELINE)

    # --- ROUTE-STROKE axis (symbol_conduit; proof-only) + bores ---------------
    bores = []
    stroke_status: Dict[str, str] = {}
    plan = PlanPdf(PDF)
    try:
        dialect = select_dialect(plan)
        offset = dialect.calibrate(plan, 13)
        graph = _build_plan_frame_graph(plan, offset)
        for pth in paths:
            try:
                bore = load_borelog(str(pth))
            except Exception:
                stroke_status[pth.stem.replace("bore_log", "log")] = \
                    "BORE_SOURCE_UNPARSEABLE"
                continue
            bores.append(bore)
            stroke_status[bore.bore_id] = stroke_resolve(
                plan, bore, offset, BRENHAM_LANE_DIALECT, frame_graph=graph).status
    finally:
        plan.close()

    # --- GROUP axis (M8.20 card; the 59th review item) ------------------------
    cards = GroupReviewService(corpus_dir=corpus_dir, plan_pdf_path=PDF,
                               bore_log_paths=paths,
                               lane_dialect=BRENHAM_LANE_DIALECT).generate()
    group_members = {m.bore_id for c in cards for m in c.members}

    rows = _build_rows(full.payloads, stroke_status, group_members, bores)
    by_id = {r["bore_id"]: r for r in rows}
    bucket_counts = collections.Counter(r["completion_bucket"] for r in rows)
    stroke_census = collections.Counter(stroke_status.values())
    group_cards = [{
        "card_id": f"GROUP:{'+'.join(sorted((m.bore_id for m in c.members), key=_num))}",
        "schema_version": c.schema_version,
        "members": sorted((m.bore_id for m in c.members), key=_num),
        "shared_origin": c.shared_origin, "boundaries": sorted(c.boundaries),
        "completion_bucket": B_GROUP, "review_only": c.review_only,
        "has_geometry": c.has_geometry, "has_strokes": c.has_strokes,
    } for c in cards]

    # ---- GATES ---------------------------------------------------------------
    corpus_ids = sorted((p.stem.replace("bore_log", "log") for p in paths),
                        key=_num)
    row_ids = sorted((r["bore_id"] for r in rows), key=_num)

    g1 = len(rows) == EXPECTED_COUNT == 58 and row_ids == corpus_ids
    print(f"[m8.27] {'PASS' if g1 else 'FAIL'}  G1 all 58 production logs "
          f"represented ({len(rows)} rows)")
    ok &= g1

    total_review_items = len(rows) + len(group_cards)
    g2 = len(group_cards) == 1 and total_review_items == 59
    print(f"[m8.27] {'PASS' if g2 else 'FAIL'}  G2 58 vs 59 explained: "
          f"{len(rows)} per-bore + {len(group_cards)} group card = "
          f"{total_review_items} review items")
    ok &= g2

    g3 = len(set(row_ids)) == len(row_ids) and set(row_ids) == set(corpus_ids)
    print(f"[m8.27] {'PASS' if g3 else 'FAIL'}  G3 no duplicate/missing bore ids")
    ok &= g3

    derived_lanes = collections.Counter(r["product_lane"] for r in rows)
    g4 = (dict(derived_lanes) == BANKED_FULLEST_LANES
          and full.lane_counts == BANKED_FULLEST_LANES)
    print(f"[m8.27] {'PASS' if g4 else 'FAIL'}  G4 product lanes reconcile with "
          f"M8.11 fullest_safe_review: {dict(sorted(derived_lanes.items()))}")
    ok &= g4

    g5 = sum(bucket_counts.values()) == 58 and all(
        r["completion_bucket"] for r in rows)
    print(f"[m8.27] {'PASS' if g5 else 'FAIL'}  G5 completion buckets total 58 "
          f"(all assigned): {dict(sorted(bucket_counts.items()))}")
    ok &= g5

    g6 = (len(group_cards) == 1
          and group_cards[0]["members"] == ["log8", "log32"]
          and group_cards[0]["schema_version"] == GROUP_SCHEMA_VERSION
          and not group_cards[0]["has_geometry"]
          and all(by_id[m]["group_review_member"] for m in ["log8", "log32"]))
    print(f"[m8.27] {'PASS' if g6 else 'FAIL'}  G6 group card represented "
          f"separately (members {group_cards[0]['members'] if group_cards else None})")
    ok &= g6

    # proof-only not exposed as product truth: the 4 route-eligible strokes are
    # NOT all product-placed (log59 is a PICK_CARD); every stroke-eligible row
    # is flagged proof_only and never upgrades its product lane.
    elig = [r for r in rows if r["proof_only_route_stroke_eligible"]]
    g7 = (len(elig) == 4
          and {r["bore_id"] for r in elig} == {"log25", "log51", "log59", "log65"}
          and by_id["log59"]["product_lane"] == "PICK_CARD_ROUTE_SUGGESTION"
          and all(r["can_draw_now"] == (r["product_lane"] == "PLACED_REVIEW")
                  for r in rows))
    print(f"[m8.27] {'PASS' if g7 else 'FAIL'}  G7 proof-only route strokes not "
          f"exposed as product truth (eligible={sorted(r['bore_id'] for r in elig)}; "
          f"log59 product={by_id['log59']['product_lane']})")
    ok &= g7

    g8 = all(by_id[b]["product_lane"] == pl
             and by_id[b]["stroke_status"] == ss
             and by_id[b]["group_review_member"] == gm
             for b, (pl, ss, gm) in CONTROLS.items())
    print(f"[m8.27] {'PASS' if g8 else 'FAIL'}  G8 log8/log32/log42: product "
          f"PLACED + stroke STRUCTURE_IDENTITY; log8/32 group, log42 excluded")
    ok &= g8

    g9 = all(by_id[b]["product_lane"] == "OUT_OF_CLASS"
             and by_id[b]["stroke_status"] == "END_IDENTITY_UNPRINTED"
             and by_id[b]["completion_bucket"] == B_SRC_KMZ
             for b in ("log43", "log44"))
    print(f"[m8.27] {'PASS' if g9 else 'FAIL'}  G9 log43/log44 OUT_OF_CLASS + "
          f"END_IDENTITY + SOURCE_OR_KMZ (M8.25)")
    ok &= g9

    eid = [r["bore_id"] for r in rows
           if r["stroke_status"] == "END_IDENTITY_UNPRINTED"]
    g10 = (len(eid) == 25
           and not any(r["proof_only_route_stroke_eligible"] for r in rows
                       if r["stroke_status"] == "END_IDENTITY_UNPRINTED"))
    print(f"[m8.27] {'PASS' if g10 else 'FAIL'}  G10 END_IDENTITY_UNPRINTED "
          f"honest-negative represented (25; none drew a stroke)")
    ok &= g10

    g11 = dict(stroke_census) == BANKED_STROKE_CENSUS
    print(f"[m8.27] {'PASS' if g11 else 'FAIL'}  G11 all-58 stroke census "
          f"unchanged 25/13/5/5/4/3/1/2: {dict(sorted(stroke_census.items()))}")
    ok &= g11

    g12 = default.status_counts == BANKED_DEFAULT_STATUS
    print(f"[m8.27] {'PASS' if g12 else 'FAIL'}  G12 M8.11 default_baseline "
          f"unchanged (24 placed): {default.status_counts}")
    ok &= g12

    # column reconciliation: every needs_source_kmz_owner row is SOURCE/SRC_KMZ;
    # can_draw_now == product-placed; no UNSAFE rows.
    g13 = (all((r["completion_bucket"] in (B_SOURCE, B_SRC_KMZ))
               == r["needs_source_kmz_owner"] for r in rows)
           and all(r["can_draw_now"] == (r["product_lane"] == "PLACED_REVIEW")
                   for r in rows)
           and not any(r["completion_bucket"] == "UNSAFE_ABSTAIN" for r in rows))
    print(f"[m8.27] {'PASS' if g13 else 'FAIL'}  G13 column reconciliation "
          f"(needs_source<->bucket; can_draw<->placed; 0 unsafe)")
    ok &= g13

    g14 = not list(OUT_DIR.glob("*.png"))
    print(f"[m8.27] {'PASS' if g14 else 'FAIL'}  G14 proof-only: nothing "
          f"rendered (no PNG/segment/placement change)")
    ok &= g14

    # G15 (M8.27 audit fix): log11 is a routing-order OUT_OF_CLASS pick-card,
    # review-eligible NOW -- not engine-blocked. ZERO bores are product-blocked
    # on a new engine law; the engine-law need is ONLY the proof-only route-
    # stroke doctrine of already-placed bores (exactly log7/log8/log32/log42).
    eng_law_bores = sorted((r["bore_id"] for r in rows
                            if r["engine_law_required"]), key=_num)
    product_engine_blocked = [r["bore_id"] for r in rows
                              if r["completion_bucket"] == B_ENGINE]
    g15 = (by_id["log11"]["completion_bucket"] == B_PICK
           and by_id["log11"]["can_show_review"] is True
           and by_id["log11"]["engine_law_required"] is False
           and not product_engine_blocked
           and eng_law_bores == ["log7", "log8", "log32", "log42"])
    print(f"[m8.27] {'PASS' if g15 else 'FAIL'}  G15 log11 review-eligible "
          f"pick-card; 0 product-blocked on engine law; route-stroke doctrine "
          f"only for {eng_law_bores}")
    ok &= g15

    # ---- counts the final report headlines -----------------------------------
    drawable = sum(1 for r in rows if r["can_draw_now"])
    review_ready = sum(1 for r in rows if r["can_show_review"])
    source_kmz_owner = sum(1 for r in rows if r["needs_source_kmz_owner"])
    engine_law = sum(1 for r in rows if r["engine_law_required"])

    report = {
        "milestone": ("truelinev2 M8.27 -- final all-58 engine truth table + "
                      "completion map (proof-only; product axis = M8.11 "
                      "fullest_safe_review; route-stroke axis = symbol_conduit "
                      "proof-only; group axis = M8.20 card)"),
        "corpus_dir_used": corpus_dir, "corpus_resolution": how, "plan_pdf": PDF,
        "verdict": "PASS" if ok else "FAILURE",
        "review_items": {"per_bore": len(rows), "group_cards": len(group_cards),
                         "total": total_review_items,
                         "note": ("58 production bore logs (log2..log72, 13 "
                                  "numbering gaps, no dups) + 1 M8.20 group "
                                  "review card = 59 review items")},
        "product_lane_counts": dict(sorted(derived_lanes.items())),
        "completion_bucket_counts": dict(sorted(bucket_counts.items())),
        "route_stroke_census": dict(sorted(stroke_census.items())),
        "headline_counts": {
            "drawable_now": drawable, "review_ready": review_ready,
            "source_kmz_owner_review": source_kmz_owner,
            "engine_law_required": engine_law,
            "proof_only_route_strokes": len(elig)},
        "group_cards": group_cards,
        "rows": rows,
    }
    (OUT_DIR / "final_engine_truth_table.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8")
    (OUT_DIR / "final_engine_truth_table.md").write_text(
        _markdown(report), encoding="utf-8")

    print(f"\n[m8.27] product lanes      : {dict(sorted(derived_lanes.items()))}")
    print(f"[m8.27] completion buckets : {dict(sorted(bucket_counts.items()))}")
    print(f"[m8.27] drawable now={drawable}  review-ready={review_ready}  "
          f"source/kmz/owner={source_kmz_owner}  engine-law={engine_law}")
    print(f"[m8.27] verdict: {report['verdict']}")
    print(f"[m8.27] report -> {OUT_DIR / 'final_engine_truth_table.json'}")
    return 0 if ok else 4


def _markdown(report: dict) -> str:
    rows = report["rows"]
    L = ["# M8.27 -- Final all-58 engine truth table + completion map", "",
         f"Verdict: **{report['verdict']}**  ·  "
         f"{report['review_items']['note']}", "",
         "Product axis = M8.11 `fullest_safe_review` (authoritative). "
         "Route-stroke axis = symbol_conduit lane (PROOF-ONLY, default-OFF, "
         "UNWIRED). Group axis = M8.20 card (separate review surface).", "",
         "## Headline counts", "",
         f"- drawable now (product placement): **{report['headline_counts']['drawable_now']}**",
         f"- review-ready (placed / pick / adjustable): **{report['headline_counts']['review_ready']}**",
         f"- source/KMZ/owner review: **{report['headline_counts']['source_kmz_owner_review']}**",
         f"- engine-law/doctrine required: **{report['headline_counts']['engine_law_required']}**",
         f"- proof-only route strokes (NOT product placements): **{report['headline_counts']['proof_only_route_strokes']}**",
         "", "## Completion buckets", "", "| count | bucket |", "|---:|---|"]
    for k, v in report["completion_bucket_counts"].items():
        L.append(f"| {v} | `{k}` |")
    L += ["", "## Group review card (the 59th review item)", ""]
    for c in report["group_cards"]:
        L.append(f"- `{c['card_id']}` ({c['schema_version']}): members "
                 f"{c['members']}, origin {c['shared_origin']}, boundaries "
                 f"{c['boundaries']}, review-only, no geometry")
    L += ["", "## Per-bore truth table", "",
          "| bore | src/family | product_lane | stroke_status | bucket | "
          "draw? | review? | src/kmz? | eng-law? | grp | missing evidence |",
          "|---|---|---|---|---|:-:|:-:|:-:|:-:|:-:|---|"]
    for r in rows:
        L.append(
            f"| {r['bore_id']} | {r['source_family'] or ''} | "
            f"{r['product_lane']} | {r['stroke_status']} | "
            f"{r['completion_bucket']} | {'Y' if r['can_draw_now'] else ''} | "
            f"{'Y' if r['can_show_review'] else ''} | "
            f"{'Y' if r['needs_source_kmz_owner'] else ''} | "
            f"{'Y' if r['engine_law_required'] else ''} | "
            f"{'Y' if r['group_review_member'] else ''} | "
            f"{(r['missing_evidence'] or '')[:80]} |")
    return "\n".join(L)


if __name__ == "__main__":
    raise SystemExit(main())
