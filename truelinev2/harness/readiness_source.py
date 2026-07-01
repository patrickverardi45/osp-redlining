"""Seam 1 of the readiness runner: PACKAGE DISCOVERY / INPUT LOADING (read-only, name-free).

Resolves a package folder (or a case reference under an injected cold-packages root) into a ``PackageSource`` —
the manifest (reused loader), the located plan / bore-log presence, and any RECORDED read-only Track B observer
findings that already sit next to the manifest. It reads only; it opens no heavy engine, draws nothing, places
nothing, and imports nothing from render / placement / api / store / contracts / product runtime.

"Observer outputs where already available" are recorded in a name-free ``observer_findings.json`` beside
``package.json``: the normalized, already-run Track B outcomes (recognition, readability, span-source presence +
confirmed count, per-endpoint anchor statuses, route status, and any owner/adversarial terminal reclassification).
Seam 2 (``readiness_adapter``) turns a ``PackageSource`` into ``ReviewReadinessEvidence``; a fresh package with no
recorded findings is normalized live there instead.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from truelinev2.harness.package_validation import load_package_manifest

OBSERVER_FINDINGS_FILENAME = "observer_findings.json"

# --- PackageSource.kind ---------------------------------------------------------------------------------- #
SOURCE_PACKAGE_FOLDER = "PACKAGE_FOLDER"          # a folder with a package.json manifest
SOURCE_RECORDED_ONLY = "RECORDED_FINDINGS_ONLY"   # only observer_findings.json (no manifest)
SOURCE_NOT_FOUND = "NOT_FOUND"                     # neither a manifest nor recorded findings

_PLAN_KIND = "PLAN_PDF"
_BORELOG_KIND = "BORE_LOG"


@dataclass(frozen=True)
class ObserverFindings:
    """Normalized, RECORDED read-only Track B observer outcomes for one package. Every field is opaque data:
    booleans, status strings, counts. No name, no coordinate, no stroke."""
    recognized: bool
    plan_readable: bool
    keep_blocked: bool
    keep_blocked_reason: str
    span_source_files: Tuple[str, ...]           # span-carrying source FILES present (generic kinds)
    plan_span_layer_inspected: bool
    source_confirmed_span_count: int
    anchor_start_status: Optional[str]           # a G-a' anchor status, or None if the stage was not evaluated
    anchor_end_status: Optional[str]
    route_status: Optional[str]                  # a G-b / G-b''' route status, or None if not evaluated
    detail: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PackageSource:
    """What seam 1 resolved for a package. Read-only descriptor; opens nothing heavy."""
    package_id: str
    kind: str                                    # one of SOURCE_*
    findings: Optional[ObserverFindings]
    manifest: Optional[dict]
    plan_path: Optional[str]
    borelog_present: bool
    detail: Dict[str, Any] = field(default_factory=dict)


def parse_observer_findings(raw: dict) -> ObserverFindings:
    """Build ``ObserverFindings`` from a parsed dict with safe defaults (missing keys => not-evaluated)."""
    def _s(v):
        return None if v is None else str(v)
    return ObserverFindings(
        recognized=bool(raw.get("recognized", False)),
        plan_readable=bool(raw.get("plan_readable", True)),
        keep_blocked=bool(raw.get("keep_blocked", False)),
        keep_blocked_reason=str(raw.get("keep_blocked_reason", "")),
        span_source_files=tuple(str(x) for x in (raw.get("span_source_files") or ())),
        plan_span_layer_inspected=bool(raw.get("plan_span_layer_inspected", False)),
        source_confirmed_span_count=int(raw.get("source_confirmed_span_count", 0)),
        anchor_start_status=_s(raw.get("anchor_start_status")),
        anchor_end_status=_s(raw.get("anchor_end_status")),
        route_status=_s(raw.get("route_status")),
        detail=dict(raw.get("detail") or {}))


def load_observer_findings(path) -> Optional[ObserverFindings]:
    """Read a recorded ``observer_findings.json`` (read-only). Returns None if missing/unreadable."""
    p = Path(path)
    if not p.is_file():
        return None
    try:
        return parse_observer_findings(json.loads(p.read_text(encoding="utf-8")))
    except (ValueError, OSError):
        return None


def _locate_uploads(package_dir: Path, manifest: Optional[dict]) -> Tuple[Optional[str], bool]:
    """From the manifest uploads, return (plan_path or None, borelog_present). Read-only; checks existence."""
    if not manifest:
        return None, False
    plan_path: Optional[str] = None
    borelog_present = False
    for u in (manifest.get("uploads") or []):
        kind = u.get("kind")
        fp = package_dir / "uploads" / str(u.get("filename", ""))
        if kind == _PLAN_KIND and fp.is_file():
            plan_path = str(fp)
        elif kind == _BORELOG_KIND and fp.is_file():
            borelog_present = True
    return plan_path, borelog_present


def discover_package(package_dir) -> PackageSource:
    """Resolve a package folder into a ``PackageSource`` (read-only). Reuses the manifest loader; reads the
    recorded observer findings beside it; locates the plan / bore-log. Never writes."""
    package_dir = Path(package_dir)
    findings = load_observer_findings(package_dir / OBSERVER_FINDINGS_FILENAME)
    manifest = load_package_manifest(package_dir) if package_dir.is_dir() else None
    pid = str((manifest or {}).get("package_id") or package_dir.name or "package")
    plan_path, borelog_present = _locate_uploads(package_dir, manifest)

    if manifest is not None:
        kind = SOURCE_PACKAGE_FOLDER
    elif findings is not None:
        kind = SOURCE_RECORDED_ONLY
    else:
        kind = SOURCE_NOT_FOUND
    return PackageSource(
        package_id=pid, kind=kind, findings=findings, manifest=manifest,
        plan_path=plan_path, borelog_present=borelog_present,
        detail={"package_dir": str(package_dir), "has_recorded_findings": findings is not None})


def resolve_case_dir(case_id, cold_packages_root) -> Path:
    """Resolve a case reference (an anonymized package id) to its folder under an INJECTED cold-packages root.
    The root is a caller-supplied path — never a hardcoded location or name."""
    return Path(cold_packages_root) / str(case_id)
