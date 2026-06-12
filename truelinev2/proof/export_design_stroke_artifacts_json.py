r"""Export graded-PASS design-stroke artifact references for the static web adapter.

Proof/export only. This runner does not add an API route, serve or copy images,
render geometry, mutate reviewer state, or wire the design-stroke lane into the
engine. It exports only canonical artifact filenames from validated M8.15
design-stroke cards.

Output (gitignored):
  data/outputs/web_adapter/design_stroke_artifacts.v1.json

Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.export_design_stroke_artifacts_json
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict

from truelinev2.config import _REPO_ROOT
from truelinev2.extract.registry import select_dialect
from truelinev2.extract.structure_position import BRENHAM_LANE_DIALECT
from truelinev2.ingest.normalize import load_borelog
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.match.symbol_conduit_lane import LANE_NAME, resolve_bore
from truelinev2.proof.export_reviewer_bundle_json import source_git_head
from truelinev2.proof.run_brenham_corpus import EXPECTED_COUNT, PDF, enumerate_corpus
from truelinev2.proof.run_design_path_adherence_proof import PATRICK_DESIGN_GRADES
from truelinev2.proof.run_design_stroke_cards_proof import ELIGIBLE
from truelinev2.proof.run_reviewer_service_contract import resolve_corpus
from truelinev2.review.design_stroke_cards import (
    CARD_SCHEMA_VERSION,
    GRADE_ACCEPTED,
    KIND_STROKE,
    DesignStrokeCardPacket,
    build_card_packet,
)
from truelinev2.service import _build_plan_frame_graph

EXPORT_SCHEMA_VERSION = "truelinev2-web-design-stroke-artifacts-1"
OUT_JSON = (
    _REPO_ROOT
    / "data"
    / "outputs"
    / "web_adapter"
    / "design_stroke_artifacts.v1.json"
)

_FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
_ARTIFACT_FILENAME = re.compile(r"^[a-z0-9_]+_redline_stroke\.png$")
_FORBIDDEN_KEYS = {"segments", "stroke_points"}
_TOP_LEVEL_KEYS = {"export_schema_version", "source", "artifacts"}
_SOURCE_KEYS = {
    "engine",
    "source_git_head",
    "card_contract",
    "lane",
    "served",
}
_ARTIFACT_KEYS = {
    "source_bore_id",
    "lane_status",
    "design_grade",
    "sheets",
    "artifact_refs",
}


def build_export(
    packet: DesignStrokeCardPacket, source_head: str
) -> Dict[str, Any]:
    """Build a refs-only manifest from accepted design-stroke cards."""
    artifacts = []
    for card in packet.cards:
        if card.kind != KIND_STROKE or card.design_grade != GRADE_ACCEPTED:
            continue
        artifacts.append(
            {
                "source_bore_id": card.bore_id,
                "lane_status": card.lane_status,
                "design_grade": card.design_grade,
                "sheets": [segment.sheet for segment in card.segments],
                "artifact_refs": list(card.artifact_refs),
            }
        )

    export = {
        "export_schema_version": EXPORT_SCHEMA_VERSION,
        "source": {
            "engine": "truelinev2",
            "source_git_head": source_head,
            "card_contract": CARD_SCHEMA_VERSION,
            "lane": LANE_NAME,
            "served": False,
        },
        "artifacts": artifacts,
    }
    validate_export(export)
    return export


def validate_export(export: Dict[str, Any]) -> None:
    """Fail closed if the manifest carries anything beyond safe references."""
    if set(export) != _TOP_LEVEL_KEYS:
        raise ValueError("top-level export fields drift")
    if export.get("export_schema_version") != EXPORT_SCHEMA_VERSION:
        raise ValueError("export schema version drift")

    source = export.get("source")
    if not isinstance(source, dict) or set(source) != _SOURCE_KEYS:
        raise ValueError("source metadata fields drift")
    if not _FULL_SHA.fullmatch(str(source.get("source_git_head", ""))):
        raise ValueError("source_git_head must be a full Git SHA")
    if source.get("engine") != "truelinev2":
        raise ValueError("source engine drift")
    if source.get("card_contract") != CARD_SCHEMA_VERSION:
        raise ValueError("card contract drift")
    if source.get("lane") != LANE_NAME:
        raise ValueError("lane drift")
    if source.get("served") is not False:
        raise ValueError("design-stroke artifacts must not be served")

    artifacts = export.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ValueError("graded-PASS artifact rows are required")

    bore_ids = []
    for index, artifact in enumerate(artifacts):
        path = f"$.artifacts[{index}]"
        if not isinstance(artifact, dict) or set(artifact) != _ARTIFACT_KEYS:
            raise ValueError(f"artifact fields drift at {path}")
        bore_id = artifact.get("source_bore_id")
        if not isinstance(bore_id, str) or not bore_id:
            raise ValueError(f"source_bore_id is required at {path}")
        bore_ids.append(bore_id)
        if artifact.get("design_grade") != GRADE_ACCEPTED:
            raise ValueError(f"only graded-PASS cards may export at {path}")

        sheets = artifact.get("sheets")
        refs = artifact.get("artifact_refs")
        if (
            not isinstance(sheets, list)
            or not sheets
            or any(type(sheet) is not int for sheet in sheets)
        ):
            raise ValueError(f"sheets must be a nonempty integer list at {path}")
        if not isinstance(refs, list) or len(refs) != len(sheets):
            raise ValueError(f"one artifact filename per sheet is required at {path}")
        for ref in refs:
            if not isinstance(ref, str) or not _ARTIFACT_FILENAME.fullmatch(ref):
                raise ValueError(f"artifact ref must be a bare filename at {path}")
            if "/" in ref or "\\" in ref or "://" in ref:
                raise ValueError(f"paths and URLs are forbidden at {path}")

    if len(bore_ids) != len(set(bore_ids)):
        raise ValueError("duplicate source_bore_id")

    def walk(value: Any, path: str = "$") -> None:
        if isinstance(value, (bytes, bytearray, memoryview)):
            raise ValueError(f"binary payload forbidden at {path}")
        if isinstance(value, dict):
            for key, child in value.items():
                if key in _FORBIDDEN_KEYS:
                    raise ValueError(f"geometry key {key!r} at {path}")
                walk(child, f"{path}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{path}[{index}]")
        elif isinstance(value, str):
            if re.match(r"^[a-zA-Z]:[\\/]", value) or value.startswith(("/", "\\")):
                raise ValueError(f"absolute path forbidden at {path}")
            if re.match(r"^(?:https?|file|data):", value, re.IGNORECASE):
                raise ValueError(f"URL/binary locator forbidden at {path}")

    walk(export)


def generate_export() -> Dict[str, Any]:
    """Generate and validate the refs-only manifest without writing it."""
    corpus_dir, _ = resolve_corpus()
    if not os.path.isfile(PDF) or not os.path.isdir(corpus_dir):
        raise FileNotFoundError("design-stroke export inputs missing")

    corpus = {path.stem: path for path in enumerate_corpus(corpus_dir)}
    if len(corpus) != EXPECTED_COUNT:
        raise ValueError(
            f"design-stroke corpus drift ({len(corpus)} != {EXPECTED_COUNT})"
        )

    plan = PlanPdf(PDF)
    try:
        dialect = select_dialect(plan)
        offset = dialect.calibrate(plan, 13)
        graph = _build_plan_frame_graph(plan, offset)
        outcomes = []
        for stem in ELIGIBLE:
            bore = load_borelog(str(corpus[stem]))
            outcomes.append(
                resolve_bore(
                    plan,
                    bore,
                    offset,
                    BRENHAM_LANE_DIALECT,
                    frame_graph=graph,
                )
            )
        packet, refusals = build_card_packet(outcomes, PATRICK_DESIGN_GRADES)
    finally:
        plan.close()

    if refusals:
        raise ValueError(f"design-stroke card refusals: {refusals}")
    return build_export(packet, source_git_head())


def main() -> int:
    corpus_dir, how = resolve_corpus()
    print(f"[design-stroke-export] corpus dir : {corpus_dir}  ({how})")
    print(f"[design-stroke-export] plan PDF   : {PDF}")
    if not os.path.isfile(PDF) or not os.path.isdir(corpus_dir):
        print("[design-stroke-export] STOP: inputs missing")
        return 2

    corpus = {path.stem: path for path in enumerate_corpus(corpus_dir)}
    if len(corpus) != EXPECTED_COUNT:
        print(
            f"[design-stroke-export] STOP: corpus drift "
            f"({len(corpus)} != {EXPECTED_COUNT})"
        )
        return 3

    try:
        export = generate_export()
    except ValueError as exc:
        print(f"[design-stroke-export] STOP: {exc}")
        return 4
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(
        json.dumps(export, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    ref_count = sum(len(row["artifact_refs"]) for row in export["artifacts"])
    print(
        "[design-stroke-export] PASS: "
        f"{len(export['artifacts'])} graded-PASS cards, {ref_count} refs, "
        "served=false"
    )
    print(f"[design-stroke-export] output -> {OUT_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
