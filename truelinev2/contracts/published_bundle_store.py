"""Phase-2I durable published-bundle store contract (adapter-neutral; proof/contract, not wiring).

A durable store is a stable, static-serving-safe layout that holds COMPLETED, VALIDATED bundles so a
website/backend can read them later WITHOUT rendering live. It is filesystem-shaped but vendor-neutral
(the same `bundles/<id>/` + `store_index.json` layout maps directly onto an object store / CDN prefix):

    <store_root>/
        store_index.json                       # MUTABLE registry: latest_valid pointer + all bundles
        bundles/<bundle_id>/                    # IMMUTABLE published bundle (never overwritten)
            redline_manifest.json
            artifacts/<log_id>/<file>.png
            _published_bundle_index.json
            _store_bundle_meta.json             # immutable per-bundle metadata

`bundle_id` is a CONTENT/VERSION key (`<project>-<render_commit>-<manifest_sha256[:12]>`): same
manifest content -> same id, so storing is idempotent and historical bundles are immutable. The
store admits ONLY bundles that pass the Phase-2E bundle validator + reconciliation + `mock_example:false`.

No engine, no renderer, no web/backend wiring; copies/validates an existing published bundle only.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from truelinev2.contracts.published_bundle import (
    INDEX_FILENAME,
    MANIFEST_FILENAME,
    load_manifest,
    sha256_file,
    validate_bundle,
)
from truelinev2.contracts.redline_manifest_publisher import load_schema, reconciliation_errors

STORE_FORMAT = "trueline-redline-bundle-store-1"
STORE_INDEX_FILENAME = "store_index.json"
BUNDLES_SUBDIR = "bundles"
STORE_META_FILENAME = "_store_bundle_meta.json"

WEBSITE_READ_CONTRACT = [
    "Read a COMPLETED, VALIDATED bundle only (validate_bundle must pass); never render live.",
    "Resolve artifacts by manifest path + sha256 within the bundle root; never infer status from PNG filenames.",
    "Never read parent_source_model.json / placement_status or any stale source/model field.",
    "Covered/blocked logs carry NO artifacts; render only kind == FINAL_REDLINE_PNG.",
    "mock_example MUST be false (refuse to serve a mock/example bundle).",
    "Consume via the store's latest_valid pointer, or an explicit immutable bundle_id.",
]


class StoreError(ValueError):
    """Base durable-store error."""


class BundleRejectedError(StoreError):
    """Source bundle is not admissible to the store (invalid / mock / count drift)."""


class BundleImmutableError(StoreError):
    """A stored bundle id already exists with different content (refusing to overwrite)."""


def compute_bundle_id(manifest, manifest_sha256) -> str:
    """Immutable content/version key: <project_id>-<render_commit>-<manifest_sha256[:12]>."""
    pid = manifest.get("project_id") or "project"
    rc = (manifest.get("engine") or {}).get("render_commit") or "norc"
    return "%s-%s-%s" % (pid, rc, manifest_sha256[:12])


def admission_errors(bundle_root, schema=None):
    """Return (errors, bundle_report, manifest). [] errors => admissible to the store."""
    schema = schema or load_schema()
    rep = validate_bundle(bundle_root, schema)
    errs = []
    if not rep["valid"]:
        for key in ("schema_errors", "unsafe_paths", "missing_files",
                    "checksum_mismatches", "structure_errors"):
            errs += ["%s: %s" % (key, e) for e in rep.get(key, [])]
    manifest = load_manifest(bundle_root)
    errs += ["count_drift: " + e for e in reconciliation_errors(manifest)]  # status/count drift
    if manifest.get("mock_example") is not False:
        errs.append("mock_example is not False (refusing to store a mock/example bundle)")
    return errs, rep, manifest


def _bundle_meta(manifest, rep, bundle_id, created_at):
    s = manifest.get("summary", {})
    return {
        "store_format": STORE_FORMAT,
        "bundle_id": bundle_id,
        "project_id": manifest.get("project_id"),
        "project_name": manifest.get("project_name"),
        "render_commit": (manifest.get("engine") or {}).get("render_commit"),
        "manifest_sha256": rep["manifest_sha256"],
        "manifest_entrypoint": MANIFEST_FILENAME,
        "artifact_count": rep["artifact_count"],
        "total_bytes": rep["total_bytes"],
        "summary": {"total_logs": s.get("total_logs"), "drawn": s.get("drawn_count"),
                    "covered": s.get("covered_count"), "blocked": s.get("blocked_count")},
        "created_at": created_at,
    }


def load_store_index(store_root) -> dict:
    p = Path(store_root) / STORE_INDEX_FILENAME
    if p.is_file():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"store_format": STORE_FORMAT, "latest_valid": None, "bundles": {}}


def write_store_index(store_root, index) -> str:
    Path(store_root).mkdir(parents=True, exist_ok=True)
    out = Path(store_root) / STORE_INDEX_FILENAME
    out.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    return str(out)


def store_bundle(source_bundle_root, store_root, *, schema=None, created_at=None) -> dict:
    """Copy a validated bundle into the durable store under an immutable content-keyed id, write its
    immutable metadata, and repoint `latest_valid`. Idempotent for identical content; never overwrites
    an existing immutable bundle. Raises BundleRejectedError / BundleImmutableError / StoreError."""
    source = Path(source_bundle_root)
    store_root = Path(store_root)
    schema = schema or load_schema()

    errs, rep, manifest = admission_errors(source, schema)
    if errs:
        raise BundleRejectedError("source bundle not admissible:\n  " + "\n  ".join(errs))

    bundle_id = compute_bundle_id(manifest, rep["manifest_sha256"])
    dest = store_root / BUNDLES_SUBDIR / bundle_id

    if dest.exists():
        existing = dest / MANIFEST_FILENAME
        existing_sha = sha256_file(existing) if existing.is_file() else None
        if existing_sha != rep["manifest_sha256"]:
            raise BundleImmutableError(
                "bundle id %s already exists with different content (refusing to overwrite)" % bundle_id)
        action = "already_stored"  # immutable: do not touch the existing bundle dir
    else:
        dest.mkdir(parents=True)
        shutil.copy2(source / MANIFEST_FILENAME, dest / MANIFEST_FILENAME)
        if (source / INDEX_FILENAME).is_file():
            shutil.copy2(source / INDEX_FILENAME, dest / INDEX_FILENAME)
        if (source / "artifacts").is_dir():
            shutil.copytree(source / "artifacts", dest / "artifacts")
        copy_rep = validate_bundle(dest, schema)  # checksum-verify the stored copy
        if not copy_rep["valid"]:
            raise StoreError("stored copy failed validation for %s" % bundle_id)
        (dest / STORE_META_FILENAME).write_text(
            json.dumps(_bundle_meta(manifest, rep, bundle_id, created_at), indent=2) + "\n",
            encoding="utf-8")
        action = "stored"

    meta = json.loads((dest / STORE_META_FILENAME).read_text(encoding="utf-8"))
    index = load_store_index(store_root)  # MUTABLE registry
    index["bundles"][bundle_id] = {
        **meta,
        "manifest_entrypoint": "%s/%s/%s" % (BUNDLES_SUBDIR, bundle_id, MANIFEST_FILENAME),
        "valid_at_store_time": True,
    }
    index["latest_valid"] = bundle_id  # keep latest-valid pointer; historical bundles retained
    write_store_index(store_root, index)
    return {"bundle_id": bundle_id, "action": action, "dest": str(dest),
            "store_root": str(store_root), "meta": meta, "store_index": index}


def validate_store(store_root, schema=None) -> dict:
    """Validate the whole store: every registered bundle still validates, and latest_valid points to
    a valid bundle. Catches missing/partial/checksum/unsafe via validate_bundle + latest-pointer drift."""
    store_root = Path(store_root)
    schema = schema or load_schema()
    index = load_store_index(store_root)
    report = {"valid": False, "store_root": str(store_root),
              "bundle_count": len(index.get("bundles", {})),
              "latest_valid": index.get("latest_valid"),
              "invalid_bundles": [], "latest_pointer_ok": False, "errors": []}
    for bid in index.get("bundles", {}):
        bdir = store_root / BUNDLES_SUBDIR / bid
        if not bdir.is_dir():
            report["invalid_bundles"].append({"bundle_id": bid, "reason": "missing bundle dir"})
            continue
        rep = validate_bundle(bdir, schema)
        if not rep["valid"]:
            report["invalid_bundles"].append({"bundle_id": bid, "reason": "bundle validation failed"})
    latest = index.get("latest_valid")
    if not latest:
        report["errors"].append("no latest_valid pointer")
    else:
        ldir = store_root / BUNDLES_SUBDIR / latest
        report["latest_pointer_ok"] = ldir.is_dir() and validate_bundle(ldir, schema)["valid"]
        if not report["latest_pointer_ok"]:
            report["errors"].append("latest_valid points to an invalid/missing bundle: %s" % latest)
    report["valid"] = (not report["invalid_bundles"] and report["latest_pointer_ok"]
                       and not report["errors"])
    return report


def website_read_errors(bundle_root, schema=None):
    """Machine-checkable subset of the website read contract for a bundle the site intends to serve."""
    schema = schema or load_schema()
    errs = []
    rep = validate_bundle(bundle_root, schema)
    if not rep["valid"]:
        errs.append("bundle is not valid for serving")
    manifest = load_manifest(bundle_root)
    if manifest.get("mock_example") is not False:
        errs.append("mock_example != false (must not serve a mock bundle)")
    for lg in manifest.get("logs", []):
        if (lg.get("covered") or lg.get("blocked")) and lg.get("artifacts"):
            errs.append("%s is covered/blocked but carries artifacts" % lg["log_id"])
    return errs
