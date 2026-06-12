r"""Slice 2b: copy graded-PASS design-stroke PNGs into the web app + emit a SERVED manifest.

This runner extends the refs-only Slice 2a export
(:mod:`truelinev2.proof.export_design_stroke_artifacts_json`) with export-time
file COPY. It copies ONLY the manifest-approved bare stroke PNGs from the
canonical lane-sweep output into the static web app's ``public`` tree under a
source-SHA namespace, then writes a served manifest whose refs each gain a
site-absolute web URL.

Static copy is one serving path; the opt-in live reviewer API is the alternate
current handoff path.

What it deliberately does NOT do: add an API route or auth; change matching,
grades, reviewer semantics, or geometry; render anything; copy PDFs; copy
un-approved artifacts; accept arbitrary paths/URLs/``..``/``/``/``\``; preload
images; or write back to the engine. The reviewer-truth refs come verbatim from
Slice 2a's validated ``build_export`` -- this module only packages and copies.

Source PNGs (must already exist -- run the lane sweep first):
  data/outputs/symbol_conduit_lane_sweep/<bore>_lane_s<sheet>_redline_stroke.png
Copy destination (gitignored in the web repo; PNGs are NEVER committed):
  <web public>/engine-artifacts/<source_sha>/<filename>
Served manifest (gitignored here; copy it into the web fixture by hand):
  data/outputs/web_adapter/design_stroke_artifacts.served.v1.json

Run (repo root), after run_symbol_conduit_lane_sweep, with the web repo present:
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.export_design_stroke_artifacts_served
Override the web public dir (default = the sibling trueline-web-experience):
  $env:TL2_WEB_PUBLIC_DIR="C:\path\to\trueline-web-experience\public"
"""
from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path
from typing import Any, Callable, Dict, List

from truelinev2.config import _REPO_ROOT
from truelinev2.extract.registry import select_dialect
from truelinev2.extract.structure_position import BRENHAM_LANE_DIALECT
from truelinev2.ingest.normalize import load_borelog
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.match.symbol_conduit_lane import resolve_bore
from truelinev2.proof.export_design_stroke_artifacts_json import (
    EXPORT_SCHEMA_VERSION,
    _ARTIFACT_FILENAME,
    _FULL_SHA,
    build_export,
)
from truelinev2.proof.export_reviewer_bundle_json import source_git_head
from truelinev2.proof.run_brenham_corpus import EXPECTED_COUNT, PDF, enumerate_corpus
from truelinev2.proof.run_design_path_adherence_proof import PATRICK_DESIGN_GRADES
from truelinev2.proof.run_design_stroke_cards_proof import ELIGIBLE
from truelinev2.proof.run_reviewer_service_contract import resolve_corpus
from truelinev2.proof.run_symbol_conduit_lane_sweep import OUT_DIR as LANE_SWEEP_DIR
from truelinev2.review.design_stroke_cards import GRADE_ACCEPTED, build_card_packet
from truelinev2.service import _build_plan_frame_graph

# Default web public dir = the sibling static web app. Override with the env var
# to point at another checkout; the runner fails closed if it does not exist.
DEFAULT_WEB_PUBLIC = Path(r"C:\Nova\projects\trueline-web-experience\public")
WEB_PUBLIC_ENV = "TL2_WEB_PUBLIC_DIR"
ARTIFACT_SUBDIR = "engine-artifacts"

SERVED_OUT_JSON = (
    _REPO_ROOT
    / "data"
    / "outputs"
    / "web_adapter"
    / "design_stroke_artifacts.served.v1.json"
)

_FORBIDDEN_KEYS = {"segments", "stroke_points"}
_TOP_LEVEL_KEYS = {"export_schema_version", "source", "artifacts"}
_SOURCE_KEYS = {"engine", "source_git_head", "card_contract", "lane", "served"}
_ARTIFACT_KEYS = {
    "source_bore_id",
    "lane_status",
    "design_grade",
    "sheets",
    "artifact_refs",
    "artifact_urls",
}
# A served web URL: site-absolute, SHA-namespaced, bare engine filename leaf.
# No scheme, no ``..``, no backslash -- nothing the browser could resolve
# off-site or off-tree.
_SERVED_URL = re.compile(
    r"^/engine-artifacts/[0-9a-f]{40}/[a-z0-9_]+_redline_stroke\.png$"
)
_SAFE_RELATIVE_URL = re.compile(r"^/[a-z0-9_./-]+$")


def served_url(sha: str, filename: str) -> str:
    """The one canonical URL shape the web app will load on demand."""
    return f"/{ARTIFACT_SUBDIR}/{sha}/{filename}"


def build_served_export(
    base: Dict[str, Any],
    url_for: Callable[[str, str], str] = served_url,
) -> Dict[str, Any]:
    """Turn a validated Slice 2a refs-only manifest into a served manifest.

    Reviewer-truth fields are carried verbatim; the only additions are the
    flipped ``served`` flag and one ``artifact_urls`` entry per existing ref.
    The result is validated before return.
    """
    sha = str(base["source"]["source_git_head"])
    artifacts: List[Dict[str, Any]] = []
    for row in base["artifacts"]:
        refs = list(row["artifact_refs"])
        artifacts.append(
            {
                "source_bore_id": row["source_bore_id"],
                "lane_status": row["lane_status"],
                "design_grade": row["design_grade"],
                "sheets": list(row["sheets"]),
                "artifact_refs": refs,
                "artifact_urls": [url_for(sha, ref) for ref in refs],
            }
        )
    served = {
        "export_schema_version": base["export_schema_version"],
        "source": {**base["source"], "served": True},
        "artifacts": artifacts,
    }
    validate_served_export(served, url_for=url_for)
    return served


def validate_served_export(
    export: Dict[str, Any],
    url_for: Callable[[str, str], str] = served_url,
) -> None:
    """Fail closed if the served manifest carries anything beyond safe in-app refs."""
    if set(export) != _TOP_LEVEL_KEYS:
        raise ValueError("top-level export fields drift")
    if export.get("export_schema_version") != EXPORT_SCHEMA_VERSION:
        raise ValueError("export schema version drift")

    source = export.get("source")
    if not isinstance(source, dict) or set(source) != _SOURCE_KEYS:
        raise ValueError("source metadata fields drift")
    sha = str(source.get("source_git_head", ""))
    if not _FULL_SHA.fullmatch(sha):
        raise ValueError("source_git_head must be a full Git SHA")
    if source.get("engine") != "truelinev2":
        raise ValueError("source engine drift")
    if source.get("served") is not True:
        raise ValueError("served manifest must set served=true")

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
        urls = artifact.get("artifact_urls")
        if (
            not isinstance(sheets, list)
            or not sheets
            or any(type(sheet) is not int for sheet in sheets)
        ):
            raise ValueError(f"sheets must be a nonempty integer list at {path}")
        if not isinstance(refs, list) or len(refs) != len(sheets):
            raise ValueError(f"one artifact filename per sheet is required at {path}")
        if not isinstance(urls, list) or len(urls) != len(refs):
            raise ValueError(f"one served url per artifact ref is required at {path}")
        for ref, url in zip(refs, urls):
            if not isinstance(ref, str) or not _ARTIFACT_FILENAME.fullmatch(ref):
                raise ValueError(f"artifact ref must be a bare filename at {path}")
            if (
                not isinstance(url, str)
                or not _SAFE_RELATIVE_URL.fullmatch(url)
                or ".." in url
                or "\\" in url
                or "//" in url
                or "?" in url
                or "#" in url
            ):
                raise ValueError(
                    f"served url must be a safe API-relative path at {path}"
                )
            if url != url_for(sha, ref):
                raise ValueError(f"served url must match source sha + ref at {path}")

    if len(bore_ids) != len(set(bore_ids)):
        raise ValueError("duplicate source_bore_id")

    approved_urls = {
        url
        for artifact in export["artifacts"]
        for url in artifact["artifact_urls"]
    }

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
            if ".." in value or "\\" in value:
                raise ValueError(f"path traversal forbidden at {path}")
            if re.match(r"^(?:https?|file|data):", value, re.IGNORECASE):
                raise ValueError(f"URL/binary locator forbidden at {path}")
            if re.match(r"^[a-zA-Z]:[\\/]", value):
                raise ValueError(f"absolute path forbidden at {path}")
            # A leading '/' is allowed ONLY for an exact, validated artifact URL.
            if value.startswith("/") and value not in approved_urls:
                raise ValueError(f"absolute path forbidden at {path}")

    walk(export)


def resolve_web_public_dir() -> Path:
    """Resolve the web ``public`` dir, failing closed on a wrong/missing target."""
    raw = os.environ.get(WEB_PUBLIC_ENV) or str(DEFAULT_WEB_PUBLIC)
    web_public = Path(raw)
    if web_public.name != "public":
        raise ValueError(
            f"{WEB_PUBLIC_ENV} must point at a web 'public' dir, got {web_public}"
        )
    if not web_public.is_dir():
        raise FileNotFoundError(f"web public dir not found: {web_public}")
    return web_public


def copy_artifacts(
    export: Dict[str, Any], source_dir: Path, web_public: Path
) -> List[str]:
    """Copy ONLY manifest-approved bare PNG filenames into the SHA namespace.

    Re-validates every filename as a bare engine artifact name (defense in
    depth), confirms each source PNG exists and is non-empty, and refuses to let
    any name escape ``source_dir`` or the destination via traversal. Clears only
    stale stroke PNGs in the target SHA leaf so the served set stays == the
    manifest set. Returns the basenames copied.
    """
    sha = str(export["source"]["source_git_head"])
    if not _FULL_SHA.fullmatch(sha):
        raise ValueError("refusing to copy under a non-SHA namespace")

    source_dir = Path(source_dir).resolve()
    dest = (Path(web_public) / ARTIFACT_SUBDIR / sha).resolve()
    dest.mkdir(parents=True, exist_ok=True)
    for stale in dest.glob("*_redline_stroke.png"):
        stale.unlink()

    copied: List[str] = []
    for artifact in export["artifacts"]:
        for ref in artifact["artifact_refs"]:
            if not _ARTIFACT_FILENAME.fullmatch(ref) or os.path.basename(ref) != ref:
                raise ValueError(f"refusing to copy non-bare filename: {ref!r}")
            src = (source_dir / ref).resolve()
            if src.parent != source_dir:
                raise ValueError(f"source path escaped sweep dir: {ref!r}")
            if not src.is_file() or src.stat().st_size == 0:
                raise FileNotFoundError(
                    f"approved stroke PNG missing/empty "
                    f"(run the lane sweep first): {src}"
                )
            dst = (dest / ref).resolve()
            if dst.parent != dest:
                raise ValueError(f"dest path escaped sha dir: {ref!r}")
            shutil.copy2(src, dst)
            copied.append(ref)
    return copied


def main() -> int:
    corpus_dir, how = resolve_corpus()
    print(f"[served-export] corpus dir : {corpus_dir}  ({how})")
    print(f"[served-export] plan PDF   : {PDF}")
    print(f"[served-export] sweep dir  : {LANE_SWEEP_DIR}")
    if not os.path.isfile(PDF) or not os.path.isdir(corpus_dir):
        print("[served-export] STOP: inputs missing")
        return 2

    corpus = {path.stem: path for path in enumerate_corpus(corpus_dir)}
    if len(corpus) != EXPECTED_COUNT:
        print(
            f"[served-export] STOP: corpus drift "
            f"({len(corpus)} != {EXPECTED_COUNT})"
        )
        return 3

    try:
        web_public = resolve_web_public_dir()
    except (ValueError, FileNotFoundError) as exc:
        print(f"[served-export] STOP: {exc}")
        return 5
    print(f"[served-export] web public : {web_public}")

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
        print(f"[served-export] STOP: card refusals: {refusals}")
        return 4

    base = build_export(packet, source_git_head())  # Slice 2a: validated, refs-only
    served = build_served_export(base)  # served=true + per-ref URLs, validated

    if not LANE_SWEEP_DIR.is_dir():
        print(
            f"[served-export] STOP: lane-sweep dir missing "
            f"(run run_symbol_conduit_lane_sweep first): {LANE_SWEEP_DIR}"
        )
        return 6
    try:
        copied = copy_artifacts(served, LANE_SWEEP_DIR, web_public)
    except (FileNotFoundError, ValueError) as exc:
        print(f"[served-export] STOP: {exc}")
        return 6

    SERVED_OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    SERVED_OUT_JSON.write_text(
        json.dumps(served, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    sha = served["source"]["source_git_head"]
    dest = web_public / ARTIFACT_SUBDIR / sha
    print(
        "[served-export] PASS: "
        f"{len(served['artifacts'])} graded-PASS cards, "
        f"{len(copied)} PNGs copied, served=true"
    )
    print(f"[served-export] images   -> {dest}")
    print(f"[served-export] manifest -> {SERVED_OUT_JSON}")
    print(
        "[served-export] NOTE: copy the manifest into the web fixture by hand; "
        "the copied PNGs are gitignored and MUST NOT be committed"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
