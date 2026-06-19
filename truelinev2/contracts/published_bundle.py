"""Phase-2E published-bundle contract (durable artifact-store / static-serving boundary).

A "published run bundle" is a self-contained directory the website will later serve statically:

    <bundle_root>/
        redline_manifest.json            # the published manifest (mock_example:false)
        artifacts/<log_id>/<file>.png    # final redline stroke artifacts
        _published_bundle_index.json     # this module's emitted index/metadata

This module validates a bundle WITHOUT moving the (large) artifacts into the repo: it checks the
manifest is schema-valid, and that every artifact reference is a SAFE RELATIVE path that stays
inside the bundle root, exists on disk, and matches its recorded `sha256` + `bytes` +
`published:true` + `example_placeholder:false`. It also proves static-serving compatibility (no
absolute Windows paths, no `..` traversal, no backslashes, no working-dir `data/outputs` leakage)
and emits a small bundle index. Contract-only: no engine, no renderer, no web/backend wiring.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from truelinev2.contracts.redline_manifest_publisher import load_schema, validate_manifest

MANIFEST_FILENAME = "redline_manifest.json"
INDEX_FILENAME = "_published_bundle_index.json"
BUNDLE_FORMAT = "trueline-redline-published-bundle-1"
_CHUNK = 1024 * 256


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def is_safe_relative_path(p) -> bool:
    """True iff `p` is a forward-slash, in-bundle relative path safe to serve statically.

    Rejects: non-strings/empty, backslashes, leading slash, drive letters (``C:``), UNC,
    ``..`` segments, empty segments (``//``), and any working-dir ``data/outputs`` leakage.
    """
    if not isinstance(p, str) or not p:
        return False
    if "\\" in p:                      # static URLs use forward slashes only
        return False
    if p.startswith("/"):              # absolute (posix)
        return False
    if len(p) >= 2 and p[1] == ":":    # Windows drive letter (e.g. C:)
        return False
    if "data/outputs" in p:            # must be bundle-relative, not tied to the working dir
        return False
    segs = p.split("/")
    if any(seg in ("", "..", ".") for seg in segs):
        return False
    return True


def _within_root(bundle_root: Path, rel: str) -> bool:
    root = os.path.realpath(str(bundle_root))
    target = os.path.realpath(os.path.join(root, rel))
    return target == root or target.startswith(root + os.sep)


def load_manifest(bundle_root) -> dict:
    return json.loads((Path(bundle_root) / MANIFEST_FILENAME).read_text(encoding="utf-8"))


def validate_bundle(bundle_root, schema=None) -> dict:
    """Validate a published bundle. Returns a report dict (see keys below)."""
    bundle_root = Path(bundle_root)
    report = {
        "bundle_root": str(bundle_root), "manifest_filename": MANIFEST_FILENAME,
        "valid": False, "manifest_present": False, "manifest_sha256": None,
        "schema_errors": [], "artifact_count": 0, "total_bytes": 0,
        "checksum_mismatches": [], "missing_files": [], "unsafe_paths": [],
        "structure_errors": [], "static_serving_safe": False,
    }
    mpath = bundle_root / MANIFEST_FILENAME
    if not mpath.is_file():
        report["structure_errors"].append("missing %s at bundle root" % MANIFEST_FILENAME)
        return report
    report["manifest_present"] = True
    report["manifest_sha256"] = sha256_file(mpath)
    manifest = json.loads(mpath.read_text(encoding="utf-8"))
    report["schema_errors"] = validate_manifest(manifest, schema or load_schema())

    for lg in manifest.get("logs", []):
        lid = lg.get("log_id")
        arts = lg.get("artifacts", []) or []
        if lg.get("drawn") and not arts:
            report["structure_errors"].append("%s is drawn but has no artifacts" % lid)
        if (lg.get("covered") or lg.get("blocked")) and arts:
            report["structure_errors"].append("%s is covered/blocked but carries artifacts" % lid)
        for a in arts:
            report["artifact_count"] += 1
            p = a.get("path", "")
            if not is_safe_relative_path(p) or not _within_root(bundle_root, p):
                report["unsafe_paths"].append("%s: %r" % (lid, p))
                continue
            ap = bundle_root / p
            if not ap.is_file():
                report["missing_files"].append("%s: %s" % (lid, p))
                continue
            size = ap.stat().st_size
            report["total_bytes"] += size
            if a.get("sha256") != sha256_file(ap):
                report["checksum_mismatches"].append("%s: sha256 mismatch %s" % (lid, p))
            if a.get("bytes") != size:
                report["checksum_mismatches"].append("%s: bytes %r != on-disk %d" % (lid, a.get("bytes"), size))
            if a.get("published") is not True:
                report["structure_errors"].append("%s: artifact published != true (%s)" % (lid, p))
            if a.get("example_placeholder") is not False:
                report["structure_errors"].append("%s: artifact example_placeholder != false (%s)" % (lid, p))

    report["static_serving_safe"] = not report["unsafe_paths"]
    report["valid"] = not (report["schema_errors"] or report["checksum_mismatches"]
                           or report["missing_files"] or report["unsafe_paths"]
                           or report["structure_errors"])
    return report


def build_bundle_index(bundle_root, report, generated_at=None) -> dict:
    """Build the bundle index/metadata from the manifest + a validation report."""
    manifest = load_manifest(bundle_root)
    idx = {
        "bundle_format": BUNDLE_FORMAT,
        "run_label": Path(bundle_root).name,
        "project_id": manifest.get("project_id"),
        "project_name": manifest.get("project_name"),
        "schema_version": manifest.get("schema_version"),
        "engine_head": manifest.get("engine", {}).get("engine_head"),
        "render_commit": manifest.get("engine", {}).get("render_commit"),
        "manifest_filename": MANIFEST_FILENAME,
        "manifest_sha256": report.get("manifest_sha256"),
        "artifact_count": report.get("artifact_count"),
        "total_bytes": report.get("total_bytes"),
        "validation": {
            "valid": report.get("valid"),
            "static_serving_safe": report.get("static_serving_safe"),
            "checksum_mismatches": len(report.get("checksum_mismatches", [])),
            "missing_files": len(report.get("missing_files", [])),
            "unsafe_paths": len(report.get("unsafe_paths", [])),
            "schema_errors": len(report.get("schema_errors", [])),
        },
    }
    if generated_at:
        idx["generated_at"] = generated_at
    return idx


def write_bundle_index(bundle_root, index) -> str:
    out = Path(bundle_root) / INDEX_FILENAME
    out.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    return str(out)
