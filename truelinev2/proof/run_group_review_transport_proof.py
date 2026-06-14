r"""M8.20 GROUP REVIEW API/bundle transport proof.

Proves the additive reviewer transport without changing per-bore truth:

  G1 the live export validates and the API bundle handler returns it;
  G2 the nested per-bore bundle is byte-identical to canonical M8.11 output;
  G3 one schema-v1 GROUP REVIEW card contains log8/log32 only;
  G4 origin, boundaries, mode, label, and blocked member statuses are exact;
  G5 log42 is excluded;
  G6 no AUTO, geometry, strokes, PNGs, segments, or placement output appears;
  G7 the all-58 default census and payload count are unchanged;
  G8 product services import no proof module and per-bore generate is unaware.

Outputs (gitignored): data/outputs/group_review_transport_proof/
"""
from __future__ import annotations

import inspect
import json
import os
from types import SimpleNamespace

from truelinev2.api import reviewer_routes
from truelinev2.config import _REPO_ROOT
from truelinev2.proof.export_reviewer_bundle_json import (
    generate_export,
    validate_export,
)
from truelinev2.proof.run_brenham_corpus import PDF, enumerate_corpus
from truelinev2.proof.run_reviewer_service_contract import resolve_corpus
from truelinev2.review.group_review import GROUP_SCHEMA_VERSION
from truelinev2.review.group_review_service import GroupReviewService
from truelinev2.review.reviewer_service import (
    ReviewerBundleService,
    ReviewRunMode,
)

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "group_review_transport_proof"


def main() -> int:
    corpus_dir, how = resolve_corpus()
    print(f"[m8.20-transport] corpus dir : {corpus_dir}  ({how})")
    if not os.path.isfile(PDF) or not os.path.isdir(corpus_dir):
        print("[m8.20-transport] STOP: inputs missing")
        return 2

    paths = enumerate_corpus(corpus_dir)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = OUT_DIR / "group_review_transport_proof.json"
    report_path.unlink(missing_ok=True)
    ok = True

    canonical = ReviewerBundleService(
        corpus_dir=corpus_dir,
        plan_pdf_path=PDF,
        project_id="brenham-ph5",
        bore_log_paths=paths,
    ).generate(ReviewRunMode.DEFAULT_BASELINE)
    canonical_json = canonical.model_dump_json()

    export = generate_export()
    validate_export(export)
    app = SimpleNamespace(state=SimpleNamespace())
    setattr(app.state, "tl2_reviewer_bundle_export", export)
    response = reviewer_routes.get_reviewer_bundle(
        SimpleNamespace(app=app),
        mode="default_baseline",
    )

    g1 = response is export and "group_review" in response
    print(
        f"[m8.20-transport] {'PASS' if g1 else 'FAIL'}  "
        "G1 live export validates and API handler returns group_review"
    )
    ok &= g1

    transported_json = json.dumps(
        response["bundle"],
        separators=(",", ":"),
    )
    g2 = transported_json == canonical_json
    print(
        f"[m8.20-transport] {'PASS' if g2 else 'FAIL'}  "
        "G2 per-bore bundle byte-identical"
    )
    ok &= g2

    section = response["group_review"]
    cards = section["cards"]
    card = cards[0] if len(cards) == 1 else None
    member_ids = sorted(m["bore_id"] for m in card["members"]) if card else []
    g3 = (
        section["schema_version"] == GROUP_SCHEMA_VERSION
        and card is not None
        and card["schema_version"] == GROUP_SCHEMA_VERSION
        and member_ids == ["log32", "log8"]
    )
    print(
        f"[m8.20-transport] {'PASS' if g3 else 'FAIL'}  "
        f"G3 one schema-v1 group card: members={member_ids}"
    )
    ok &= g3

    g4 = (
        card is not None
        and card["shared_origin"] == "NEXTLINK@378,409"
        and sorted(card["boundaries"]) == ["1+76", "1+77"]
        and card["mode"] == "REVIEW_ONLY"
        and card["review_only"] is True
        and card["auto"] is False
        and card["label"] == "SUGGESTION_NOT_PLACEMENT"
        and all(
            member["per_bore_status"]
            == "STRUCTURE_IDENTITY_BINDING_REQUIRED"
            for member in card["members"]
        )
    )
    print(
        f"[m8.20-transport] {'PASS' if g4 else 'FAIL'}  "
        "G4 exact origin/boundaries/REVIEW-only/blocked statuses"
    )
    ok &= g4

    g5 = card is not None and "log42" not in member_ids
    print(
        f"[m8.20-transport] {'PASS' if g5 else 'FAIL'}  G5 log42 excluded"
    )
    ok &= g5

    group_text = json.dumps(section).lower()
    forbidden = (
        '"segments"',
        '"stroke_points"',
        '"stroke_rgb"',
        '"walk_points"',
        '"boundary_xy"',
        ".png",
        '"placement"',
    )
    g6 = (
        card is not None
        and card["auto"] is False
        and card["has_geometry"] is False
        and card["has_strokes"] is False
        and not any(token in group_text for token in forbidden)
    )
    print(
        f"[m8.20-transport] {'PASS' if g6 else 'FAIL'}  "
        "G6 no AUTO/geometry/strokes/PNGs/segments/placement"
    )
    ok &= g6

    expected_status = {  # RECON-2A `STA ` activation: log37/log38 (only) move
        "AUTO_SELECT": 14,
        "REVIEW": 11,
        "ABSTAIN": 33,
        "ERROR": 0,
        "PLACED": 25,
    }
    g7 = (
        response["bundle"]["status_counts"] == expected_status
        and len(response["bundle"]["payloads"]) == 58
    )
    print(
        f"[m8.20-transport] {'PASS' if g7 else 'FAIL'}  "
        f"G7 all-58 census unchanged: {response['bundle']['status_counts']}"
    )
    ok &= g7

    group_service_src = inspect.getsource(GroupReviewService)
    per_bore_src = inspect.getsource(ReviewerBundleService.generate)
    g8 = (
        "truelinev2.proof" not in group_service_src
        and ".proof." not in group_service_src
        and "group_review" not in per_bore_src
    )
    print(
        f"[m8.20-transport] {'PASS' if g8 else 'FAIL'}  "
        "G8 product service has no proof import; per-bore generate unaware"
    )
    ok &= g8

    report = {
        "milestone": "truelinev2 M8.20 GROUP REVIEW API/bundle transport",
        "corpus_dir_used": corpus_dir,
        "corpus_resolution": how,
        "plan_pdf": PDF,
        "verdict": "PASS" if ok else "FAILURE",
        "per_bore_byte_identical": g2,
        "status_counts": response["bundle"]["status_counts"],
        "group_review": section,
    }
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"[m8.20-transport] report -> {report_path}")
    print(f"[m8.20-transport] {'PASS' if ok else 'FAILURE'}")
    return 0 if ok else 4


if __name__ == "__main__":
    raise SystemExit(main())
