r"""Export the M8.11 default reviewer bundle plus additive GROUP REVIEW cards.

The same validated envelope backs the static fixture and the flag-gated,
read-only v2 reviewer API. The canonical per-bore ``ReviewerBundleService``
output remains verbatim under ``bundle``; the parallel ``GroupReviewService``
output is carried separately under ``group_review``. This runner does not
mutate either service contract, activate an opt-in solver, render artifacts,
or write engine state.

Output (gitignored):
  data/outputs/web_adapter/reviewer_bundle.v1.json

Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.export_reviewer_bundle_json
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, Sequence

from truelinev2.config import _REPO_ROOT
from truelinev2.extract.structure_position import BRENHAM_LANE_DIALECT
from truelinev2.proof.run_brenham_corpus import (
    EXPECTED_COUNT,
    PDF,
    enumerate_corpus,
)
from truelinev2.proof.run_reviewer_service_contract import resolve_corpus
from truelinev2.review.reviewer_payloads import (
    ConfidenceClass,
    SUGGESTION_LABEL,
)
from truelinev2.review.group_review import (
    GROUP_SCHEMA_VERSION,
    SharedAlignmentGroupCard,
)
from truelinev2.review.group_review_service import GroupReviewService
from truelinev2.review.reviewer_service import (
    ReviewerBundle,
    ReviewerBundleService,
    ReviewRunMode,
)

EXPORT_SCHEMA_VERSION = "truelinev2-web-reviewer-bundle-export-1"
OUT_JSON = (
    _REPO_ROOT / "data" / "outputs" / "web_adapter" / "reviewer_bundle.v1.json"
)

_FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
_FORBIDDEN_GEOMETRY_KEYS = {
    "segments",
    "stroke_points",
    "stroke_rgb",
    "walk_points",
    "boundary_xy",
    "artifact_refs",
}
_CONFIDENCE_CLASSES = {item.value for item in ConfidenceClass}


def source_git_head(repo_root: Path = _REPO_ROOT) -> str:
    """Return the exact source revision used for this static export."""
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    head = result.stdout.strip().lower()
    if not _FULL_SHA.fullmatch(head):
        raise ValueError(f"expected a full Git SHA, got {head!r}")
    return head


def build_export(
    bundle: ReviewerBundle,
    source_head: str,
    *,
    group_cards: Sequence[SharedAlignmentGroupCard],
) -> Dict[str, Any]:
    """Wrap the canonical bundle plus a separate validated group section."""
    export = {
        "export_schema_version": EXPORT_SCHEMA_VERSION,
        "source": {
            "engine": "truelinev2",
            "source_git_head": source_head,
            "service": "ReviewerBundleService",
            "run_mode": bundle.run_mode.value,
            "bundle_schema_version": bundle.bundle_schema_version,
            "payload_schema_version": bundle.payload_schema_version,
        },
        "bundle": bundle.model_dump(mode="json"),
        "group_review": {
            "schema_version": GROUP_SCHEMA_VERSION,
            "service": "GroupReviewService",
            "cards": [card.model_dump(mode="json") for card in group_cards],
        },
    }
    validate_export(export)
    return export


def validate_export(export: Dict[str, Any]) -> None:
    """Fail closed if the static adapter export weakens reviewer truth."""
    if export.get("export_schema_version") != EXPORT_SCHEMA_VERSION:
        raise ValueError("export schema version drift")

    source = export.get("source")
    if not isinstance(source, dict):
        raise ValueError("source metadata is required")
    if not _FULL_SHA.fullmatch(str(source.get("source_git_head", ""))):
        raise ValueError("source_git_head must be a full Git SHA")
    if source.get("run_mode") != ReviewRunMode.DEFAULT_BASELINE.value:
        raise ValueError("web adapter export must use default_baseline")

    bundle = export.get("bundle")
    if not isinstance(bundle, dict):
        raise ValueError("canonical reviewer bundle is required")
    if bundle.get("run_mode") != ReviewRunMode.DEFAULT_BASELINE.value:
        raise ValueError("canonical bundle run_mode must be default_baseline")

    group_review = export.get("group_review")
    if not isinstance(group_review, dict):
        raise ValueError("separate group_review section is required")
    if set(group_review) != {"schema_version", "service", "cards"}:
        raise ValueError("group_review fields drift")
    if group_review.get("schema_version") != GROUP_SCHEMA_VERSION:
        raise ValueError("group_review schema version drift")
    if group_review.get("service") != "GroupReviewService":
        raise ValueError("group_review service drift")
    raw_cards = group_review.get("cards")
    if not isinstance(raw_cards, list):
        raise ValueError("group_review cards must be a list")

    def walk(value: Any, path: str = "$", *, forbid_png: bool = False) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key in _FORBIDDEN_GEOMETRY_KEYS:
                    raise ValueError(f"geometry/artifact key {key!r} at {path}")
                if key == "confidence_class" and child is not None:
                    if isinstance(child, (int, float)):
                        raise ValueError(f"numeric confidence at {path}.{key}")
                    if child not in _CONFIDENCE_CLASSES:
                        raise ValueError(
                            f"unknown confidence class {child!r} at {path}.{key}"
                        )
                if key == "label" and child != SUGGESTION_LABEL:
                    raise ValueError(f"suggestion label drift at {path}.{key}")
                walk(child, f"{path}.{key}", forbid_png=forbid_png)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{path}[{index}]", forbid_png=forbid_png)
        elif forbid_png and isinstance(value, str) and ".png" in value.lower():
            raise ValueError(f"PNG reference forbidden at {path}")

    walk(bundle)
    walk(group_review, "$.group_review", forbid_png=True)
    for index, raw in enumerate(raw_cards):
        if not isinstance(raw, dict):
            raise ValueError(f"group_review card {index} must be an object")
        card = SharedAlignmentGroupCard.model_validate(raw)
        if card.model_dump(mode="json") != raw:
            raise ValueError(f"group_review card {index} fields drift")


def generate_export() -> Dict[str, Any]:
    """Generate and validate the default-baseline export without writing it."""
    corpus_dir, _ = resolve_corpus()
    if not os.path.isfile(PDF) or not os.path.isdir(corpus_dir):
        raise FileNotFoundError("reviewer bundle inputs missing")

    corpus = enumerate_corpus(corpus_dir)
    if len(corpus) != EXPECTED_COUNT:
        raise ValueError(
            f"reviewer corpus drift ({len(corpus)} != {EXPECTED_COUNT})"
        )

    service = ReviewerBundleService(
        corpus_dir=corpus_dir,
        plan_pdf_path=PDF,
        project_id="brenham-ph5",
        bore_log_paths=corpus,
    )
    bundle = service.generate(ReviewRunMode.DEFAULT_BASELINE)
    group_service = GroupReviewService(
        corpus_dir=corpus_dir,
        plan_pdf_path=PDF,
        bore_log_paths=corpus,
        lane_dialect=BRENHAM_LANE_DIALECT,
    )
    group_cards = group_service.generate()
    return build_export(
        bundle,
        source_git_head(),
        group_cards=group_cards,
    )


def main() -> int:
    corpus_dir, how = resolve_corpus()
    print(f"[web-adapter] corpus dir : {corpus_dir}  ({how})")
    print(f"[web-adapter] plan PDF   : {PDF}")
    if not os.path.isfile(PDF) or not os.path.isdir(corpus_dir):
        print("[web-adapter] STOP: inputs missing")
        return 2

    corpus = enumerate_corpus(corpus_dir)
    if len(corpus) != EXPECTED_COUNT:
        print(
            f"[web-adapter] STOP: corpus drift "
            f"({len(corpus)} != {EXPECTED_COUNT})"
        )
        return 3

    export = generate_export()
    bundle = export["bundle"]

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(
        json.dumps(export, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        "[web-adapter] PASS: "
        f"{len(bundle['payloads'])} per-bore cards, "
        f"{len(export['group_review']['cards'])} group cards, "
        f"statuses {bundle['status_counts']}"
    )
    print(f"[web-adapter] output -> {OUT_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
