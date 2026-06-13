r"""M9.6 -- export the M9.4.2 RUN-ASSEMBLY review cards under a validated transport envelope.

The same validated envelope backs an offline fixture and the flag-gated, read-only v2
run-assembly API route (api/run_assembly_routes.py). It CONSUMES the shipped
``RunAssemblyReviewService.generate()`` output verbatim -- it does NOT reimplement any
run-assembly logic, mutate the per-bore reviewer bundle, move a product bucket, activate
an opt-in solver, render an artifact, or write engine state. The cards keep their own
M9.4.1 schema (``truelinev2-run-assembly-review-1``); this envelope is only a transport
wrapper (``truelinev2-web-run-assembly-export-1``).

Validation IS the contract (fail-closed): the envelope schema + service + card schema are
pinned; every card round-trips through the M9.4.1 ``RunAssemblyReviewCard`` validator
(which already forbids geometry/strokes/AUTO and pins the SUGGESTION label); and a
defensive walk forbids any geometry / PNG / product-bucket (lane/status/payload) key.

Output (gitignored):
  data/outputs/web_adapter/run_assembly_cards.v1.json

Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.export_run_assembly_cards_json
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Sequence

from truelinev2.config import _REPO_ROOT
from truelinev2.extract.kmz import BRENHAM_KMZ_DIALECT, read_kmz
from truelinev2.extract.terminus_profile import BRENHAM_TERMINUS_PROFILE
from truelinev2.proof.export_reviewer_bundle_json import source_git_head
from truelinev2.proof.run_brenham_corpus import EXPECTED_COUNT, PDF, enumerate_corpus
from truelinev2.proof.run_kmz_correlation_audit import resolve_kmz
from truelinev2.proof.run_reviewer_service_contract import resolve_corpus
from truelinev2.review.run_assembly_review import (
    RUN_ASSEMBLY_SCHEMA_VERSION,
    SUGGESTION_LABEL,
    RunAssemblyReviewCard,
)
from truelinev2.review.run_assembly_review_service import RunAssemblyReviewService

EXPORT_SCHEMA_VERSION = "truelinev2-web-run-assembly-export-1"
SERVICE_NAME = "RunAssemblyReviewService"
SOURCE_CONTRADICTION_BORES = ("log44",)             # banked M8.25/M9.0 (injected)
OUT_JSON = _REPO_ROOT / "data" / "outputs" / "web_adapter" / "run_assembly_cards.v1.json"

_FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
# keys that may NEVER appear anywhere in the transport envelope: geometry/stroke (a card
# is not a drawn redline) + product-bucket/lane/status/payload (the transport is NOT the
# per-bore product surface and never moves a bucket).
_FORBIDDEN_KEYS = {
    "segments", "stroke_points", "stroke_rgb", "walk_points", "boundary_xy",
    "lon", "lat", "geometry", "artifact_refs",
    "lane", "lane_counts", "status_counts", "payloads", "confidence_class",
}


def build_export(cards: Sequence[RunAssemblyReviewCard], source_head: str) -> Dict[str, Any]:
    """Wrap the validated run-assembly cards in the transport envelope (+ validate)."""
    export = {
        "export_schema_version": EXPORT_SCHEMA_VERSION,
        "source": {
            "engine": "truelinev2",
            "source_git_head": source_head,
            "service": SERVICE_NAME,
            "card_schema_version": RUN_ASSEMBLY_SCHEMA_VERSION,
        },
        "cards": [card.model_dump(mode="json") for card in cards],
    }
    validate_export(export)
    return export


def validate_export(export: Dict[str, Any]) -> None:
    """Fail closed if the transport envelope weakens the run-assembly review contract."""
    if export.get("export_schema_version") != EXPORT_SCHEMA_VERSION:
        raise ValueError("run-assembly export schema version drift")
    # strict top-level allowlist -- any extra envelope key (e.g. a smuggled product
    # bucket / lane / status) is rejected, fail-closed.
    if set(export) != {"export_schema_version", "source", "cards"}:
        raise ValueError("transport envelope top-level fields drift")

    source = export.get("source")
    if not isinstance(source, dict):
        raise ValueError("source metadata is required")
    if set(source) != {"engine", "source_git_head", "service", "card_schema_version"}:
        raise ValueError("transport envelope source fields drift")
    if not _FULL_SHA.fullmatch(str(source.get("source_git_head", ""))):
        raise ValueError("source_git_head must be a full Git SHA")
    if source.get("service") != SERVICE_NAME:
        raise ValueError("transport service drift (must be RunAssemblyReviewService)")
    if source.get("card_schema_version") != RUN_ASSEMBLY_SCHEMA_VERSION:
        raise ValueError("card schema version drift (must be the M9.4.1 card schema)")

    raw_cards = export.get("cards")
    if not isinstance(raw_cards, list):
        raise ValueError("cards must be a list")

    def walk(value: Any, path: str = "$") -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key in _FORBIDDEN_KEYS:
                    raise ValueError(f"forbidden geometry/bucket key {key!r} at {path}")
                if isinstance(key, str) and ".png" in key.lower():
                    raise ValueError(f"PNG reference forbidden as a key at {path}.{key}")
                if key == "label" and child != SUGGESTION_LABEL:
                    raise ValueError(f"suggestion label drift at {path}.{key}")
                walk(child, f"{path}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{path}[{index}]")
        elif isinstance(value, str) and ".png" in value.lower():
            raise ValueError(f"PNG reference forbidden at {path}")

    walk({"source": source, "cards": raw_cards})

    # every card must round-trip through the M9.4.1 card contract (which itself forbids
    # geometry/strokes/AUTO and pins the SUGGESTION label / DROP_BRANCH<->drop coupling).
    for index, raw in enumerate(raw_cards):
        if not isinstance(raw, dict):
            raise ValueError(f"card {index} must be an object")
        card = RunAssemblyReviewCard.model_validate(raw)
        if card.model_dump(mode="json") != raw:
            raise ValueError(f"card {index} fields drift")
        if raw.get("schema_version") != RUN_ASSEMBLY_SCHEMA_VERSION:
            raise ValueError(f"card {index} schema version drift")


def generate_export() -> Dict[str, Any]:
    """Generate + validate the run-assembly transport envelope without writing it.
    Raises FileNotFoundError / ValueError when inputs are missing or drift (the route
    maps these to a 503)."""
    kmz_path, _ = resolve_kmz()
    corpus_dir, _ = resolve_corpus()
    if not os.path.isfile(kmz_path) or not os.path.isfile(PDF) or not os.path.isdir(corpus_dir):
        raise FileNotFoundError("run-assembly transport inputs missing")
    corpus = enumerate_corpus(corpus_dir)
    if len(corpus) != EXPECTED_COUNT:
        raise ValueError(f"run-assembly corpus drift ({len(corpus)} != {EXPECTED_COUNT})")

    model = read_kmz(kmz_path, BRENHAM_KMZ_DIALECT)
    service = RunAssemblyReviewService(
        corpus_dir=corpus_dir, plan_pdf_path=PDF, bore_log_paths=corpus,
        kmz_model=model, terminus_profile=BRENHAM_TERMINUS_PROFILE,
        source_contradiction_bores=SOURCE_CONTRADICTION_BORES)
    cards = service.generate()
    return build_export(cards, source_git_head())


def main() -> int:
    kmz_path, kmz_how = resolve_kmz()
    corpus_dir, how = resolve_corpus()
    print(f"[m9.6-export] kmz   : {kmz_path}  ({kmz_how})")
    print(f"[m9.6-export] corpus: {corpus_dir}  ({how})")
    if not os.path.isfile(kmz_path) or not os.path.isfile(PDF) or not os.path.isdir(corpus_dir):
        print("[m9.6-export] STOP: inputs missing")
        return 2
    corpus = enumerate_corpus(corpus_dir)
    if len(corpus) != EXPECTED_COUNT:
        print(f"[m9.6-export] STOP: corpus drift ({len(corpus)} != {EXPECTED_COUNT})")
        return 3

    export = generate_export()
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(export, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"[m9.6-export] PASS: {len(export['cards'])} run-assembly cards "
          f"(schema {export['source']['card_schema_version']})")
    print(f"[m9.6-export] output -> {OUT_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
