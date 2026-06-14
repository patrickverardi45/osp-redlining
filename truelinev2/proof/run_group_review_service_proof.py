r"""M8.20 real GROUP REVIEW service proof.

Proves the shipped service output calls product-layer claim extraction, Law 1,
and the group-card contract without changing the per-bore reviewer bundle:

  G1 per-bore ``generate(default_baseline)`` is byte-identical before/after;
  G2 the real group service emits exactly one schema-v1 card for log8/log32;
  G3 origin/boundaries and blocked member statuses are exact; log42 excluded;
  G4 REVIEW-only, no AUTO, geometry, strokes, segments, or placement output;
  G5 the service imports no proof/render/KMZ code and per-bore generate remains
     unaware of group review;
  G6 the banked default per-bore counts and 58-payload contract are unchanged;
  G7 the new schema remains disjoint from M8.10/M8.11/M8.15 schemas;
  G8 nothing is rendered.

Outputs (gitignored): data/outputs/group_review_service_proof/
"""
from __future__ import annotations

import inspect
import json
import os

from truelinev2.config import _REPO_ROOT
from truelinev2.extract.structure_position import BRENHAM_LANE_DIALECT
from truelinev2.proof.run_brenham_corpus import PDF, enumerate_corpus
from truelinev2.proof.run_reviewer_service_contract import resolve_corpus
from truelinev2.review.design_stroke_cards import CARD_SCHEMA_VERSION
from truelinev2.review.group_review import GROUP_SCHEMA_VERSION
from truelinev2.review.group_review_service import GroupReviewService
from truelinev2.review.reviewer_payloads import SCHEMA_VERSION
from truelinev2.review.reviewer_service import (
    BUNDLE_SCHEMA_VERSION,
    ReviewerBundleService,
    ReviewRunMode,
)

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "group_review_service_proof"


def main() -> int:
    corpus_dir, how = resolve_corpus()
    print(f"[m8.20-service] corpus dir : {corpus_dir}  ({how})")
    if not os.path.isfile(PDF) or not os.path.isdir(corpus_dir):
        print("[m8.20-service] STOP: inputs missing")
        return 2
    paths = enumerate_corpus(corpus_dir)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = OUT_DIR / "group_review_service_proof.json"
    report_path.unlink(missing_ok=True)
    ok = True

    per_bore = ReviewerBundleService(
        corpus_dir=corpus_dir, plan_pdf_path=PDF, project_id="brenham-ph5",
        bore_log_paths=paths)
    group = GroupReviewService(
        corpus_dir=corpus_dir, plan_pdf_path=PDF, bore_log_paths=paths,
        lane_dialect=BRENHAM_LANE_DIALECT)

    before = per_bore.generate(ReviewRunMode.DEFAULT_BASELINE)
    before_bytes = before.model_dump_json()
    cards = group.generate()
    after = per_bore.generate(ReviewRunMode.DEFAULT_BASELINE)
    after_bytes = after.model_dump_json()

    g1 = before_bytes == after_bytes
    print(f"[m8.20-service] {'PASS' if g1 else 'FAIL'}  G1 per-bore bundle "
          f"byte-identical before/after group generation")
    ok &= g1

    card = cards[0] if len(cards) == 1 else None
    g2 = (card is not None and card.schema_version == GROUP_SCHEMA_VERSION
          and sorted(m.bore_id for m in card.members) == ["log32", "log8"])
    print(f"[m8.20-service] {'PASS' if g2 else 'FAIL'}  G2 one group card: "
          f"count={len(cards)}, members="
          f"{sorted(m.bore_id for m in card.members) if card else None}")
    ok &= g2

    g3 = (card is not None
          and card.shared_origin == "NEXTLINK@378,409"
          and sorted(card.boundaries) == ["1+76", "1+77"]
          and all(m.per_bore_status == "STRUCTURE_IDENTITY_BINDING_REQUIRED"
                  for m in card.members)
          and "log42" not in {m.bore_id for m in card.members})
    print(f"[m8.20-service] {'PASS' if g3 else 'FAIL'}  G3 exact origin, "
          f"boundaries, blocked members; log42 excluded")
    ok &= g3

    serialized = card.model_dump() if card else {}
    text = json.dumps(serialized)
    forbidden = ("segments", "stroke_points", "stroke_rgb", "walk_points",
                 "boundary_xy", ".png")
    g4 = (card is not None and card.mode == "REVIEW_ONLY"
          and card.review_only is True and card.auto is False
          and card.label == "SUGGESTION_NOT_PLACEMENT"
          and card.has_geometry is False and card.has_strokes is False
          and not any(key in text for key in forbidden))
    print(f"[m8.20-service] {'PASS' if g4 else 'FAIL'}  G4 REVIEW-only, "
          f"no AUTO/geometry/strokes/segments/PNG")
    ok &= g4

    import truelinev2.review.group_review_service as service_module
    service_src = inspect.getsource(service_module)
    per_bore_src = inspect.getsource(ReviewerBundleService.generate)
    g5 = ("truelinev2.proof" not in service_src
          and ".proof." not in service_src
          and "truelinev2.render" not in service_src
          and "KMZ" not in service_src and "kmz" not in service_src
          and "group_review" not in per_bore_src)
    print(f"[m8.20-service] {'PASS' if g5 else 'FAIL'}  G5 no proof/render/KMZ "
          f"imports; per-bore generate unaware")
    ok &= g5

    expected_status = {  # RECON-2A `STA ` activation: log37/log38 (only) move
        "AUTO_SELECT": 14, "REVIEW": 11, "ABSTAIN": 33, "ERROR": 0,
        "PLACED": 25}
    g6 = (before.status_counts == after.status_counts == expected_status
          and len(before.payloads) == len(after.payloads) == 58)
    print(f"[m8.20-service] {'PASS' if g6 else 'FAIL'}  G6 banked per-bore "
          f"counts + 58 payloads unchanged: {before.status_counts}")
    ok &= g6

    g7 = GROUP_SCHEMA_VERSION not in {
        BUNDLE_SCHEMA_VERSION, SCHEMA_VERSION, CARD_SCHEMA_VERSION}
    print(f"[m8.20-service] {'PASS' if g7 else 'FAIL'}  G7 group schema "
          f"disjoint: {GROUP_SCHEMA_VERSION}")
    ok &= g7

    g8 = not list(OUT_DIR.glob("*.png"))
    print(f"[m8.20-service] {'PASS' if g8 else 'FAIL'}  G8 no artifact rendered")
    ok &= g8

    report = {
        "milestone": "truelinev2 M8.20 GROUP REVIEW real service output",
        "corpus_dir_used": corpus_dir, "corpus_resolution": how,
        "plan_pdf": PDF, "verdict": "PASS" if ok else "FAILURE",
        "per_bore_byte_identical": g1,
        "per_bore_status_counts": before.status_counts,
        "group_cards": [c.model_dump() for c in cards],
    }
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"[m8.20-service] report -> {report_path}")
    print(f"[m8.20-service] {'PASS' if ok else 'FAILURE'}")
    return 0 if ok else 4


if __name__ == "__main__":
    raise SystemExit(main())
