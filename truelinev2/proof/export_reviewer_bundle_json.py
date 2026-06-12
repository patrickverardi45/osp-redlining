r"""Export the M8.11 default reviewer bundle for the static web adapter.

Proof/export only. This runner does not add an API route, mutate the reviewer
service contract, activate an opt-in solver, render artifacts, or write engine
state. It serializes the validated ``ReviewerBundleService`` baseline output
under a small versioned envelope that records the source Git HEAD.

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
from typing import Any, Dict

from truelinev2.config import _REPO_ROOT
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
_FORBIDDEN_GEOMETRY_KEYS = {"segments", "stroke_points", "artifact_refs"}
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


def build_export(bundle: ReviewerBundle, source_head: str) -> Dict[str, Any]:
    """Wrap the canonical bundle dump without renaming or mutating its fields."""
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

    def walk(value: Any, path: str = "$") -> None:
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
                walk(child, f"{path}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{path}[{index}]")

    walk(bundle)


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

    service = ReviewerBundleService(
        corpus_dir=corpus_dir,
        plan_pdf_path=PDF,
        project_id="brenham-ph5",
        bore_log_paths=corpus,
    )
    bundle = service.generate(ReviewRunMode.DEFAULT_BASELINE)
    export = build_export(bundle, source_git_head())

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(
        json.dumps(export, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        "[web-adapter] PASS: "
        f"{len(bundle.payloads)} cards, statuses {bundle.status_counts}"
    )
    print(f"[web-adapter] output -> {OUT_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
