r"""Phase-2J read-only STATIC BUNDLE CONSUMER (the website/backend READ side of the durable store).

This is the first read-only integration surface a website/backend would import to SERVE a published
redline bundle from the Phase-2I durable store. It is the mirror of `published_bundle_store` (the
write/admit side): this module only READS a COMPLETED, VALIDATED bundle and never renders, solves,
publishes, or writes into the store.

Read path (vendor-neutral; the same `bundles/<id>/` + `store_index.json` layout maps onto an object
store / CDN prefix):

    store_root/store_index.json        --(latest_valid | explicit bundle_id)-->
    store_root/bundles/<id>/redline_manifest.json   (the served manifest payload)
    store_root/bundles/<id>/artifacts/<log>/<file>.png   (resolved by manifest path + sha256)

Website read contract enforced on EVERY served bundle (see `published_bundle_store.WEBSITE_READ_CONTRACT`):
  * serve a COMPLETED, VALIDATED bundle only (`validate_bundle` must pass) -- never render live;
  * `mock_example` MUST be false (refuse a mock/example bundle);
  * covered/blocked logs carry NO artifacts; expose only `kind == FINAL_REDLINE_PNG`;
  * resolve artifacts by manifest path + sha256 -- NEVER infer status from PNG filenames;
  * never read `parent_source_model` / `placement_status` or any stale source/model field;
  * consume via the store's `latest_valid` pointer or an explicit immutable `bundle_id`.

GATE: default-OFF, v2-only. The consumer refuses to operate unless `TL2_STATIC_BUNDLE_CONSUMER_OPTIN=1`
(env) or an explicit `enable=True` is passed. It can NEVER activate in production by accident.

Dependency-closure note (proves "no live render"): this module imports ONLY stdlib + the three pure
contract modules (`published_bundle`, `published_bundle_store`, `redline_manifest_publisher`). It
imports nothing from the engine / renderer / solver / match / ingest packages.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

from truelinev2.contracts.published_bundle import (
    MANIFEST_FILENAME,
    is_safe_relative_path,
    load_manifest,
    sha256_file,
    validate_bundle,
)
from truelinev2.contracts.published_bundle_store import (
    BUNDLES_SUBDIR,
    load_store_index,
    website_read_errors,
)
from truelinev2.contracts.redline_manifest_publisher import load_schema

CONSUMER_OPTIN_ENV = "TL2_STATIC_BUNDLE_CONSUMER_OPTIN"
FINAL_KIND = "FINAL_REDLINE_PNG"
# Stale source/model fields a consumer must NEVER read or serve. These are already structurally
# impossible in a schema-valid manifest (`additionalProperties: false`), but they are named + checked
# here so a rejection is explicit and the contract is self-documenting.
FORBIDDEN_MANIFEST_FIELDS = ("parent_source_model", "placement_status")
_CONTENT_TYPES = {".png": "image/png", ".json": "application/json"}


class ConsumerError(ValueError):
    """Base read-only-consumer error."""


class ConsumerDisabledError(ConsumerError):
    """The default-OFF consumer gate is not enabled."""


class BundleNotReadableError(ConsumerError):
    """A requested bundle is missing, unregistered, or fails the website read contract."""


class ArtifactNotServableError(ConsumerError):
    """An artifact path is not a manifest-listed FINAL_REDLINE_PNG, is unsafe, or fails checksum."""


def consumer_enabled() -> bool:
    """The default-OFF gate: True only when ``TL2_STATIC_BUNDLE_CONSUMER_OPTIN == "1"``."""
    return os.getenv(CONSUMER_OPTIN_ENV, "0") == "1"


def _within_bundle(bundle_root, rel: str) -> bool:
    """Mirror of `published_bundle._within_root`; kept local so the consumer is self-contained.

    True iff `rel` resolves to a path inside `bundle_root` (defends against `..` traversal even after
    realpath/symlink resolution)."""
    root = os.path.realpath(str(bundle_root))
    target = os.path.realpath(os.path.join(root, rel))
    return target == root or target.startswith(root + os.sep)


def _content_type(path) -> str:
    return _CONTENT_TYPES.get(Path(path).suffix.lower(), "application/octet-stream")


def consumer_read_errors(bundle_root, schema=None):
    """Machine-checkable gate enforced before SERVING any bundle ([] => servable, read-only).

    A superset of `published_bundle_store.website_read_errors` (valid bundle + `mock_example:false` +
    no covered/blocked-with-artifacts) plus explicit rejection of stale source/model fields.
    """
    schema = schema or load_schema()
    errs = list(website_read_errors(bundle_root, schema))
    manifest = load_manifest(bundle_root)
    for field in FORBIDDEN_MANIFEST_FIELDS:
        if field in manifest:
            errs.append("manifest carries forbidden stale field %r (must not be served)" % field)
    for lg in manifest.get("logs", []):
        for field in FORBIDDEN_MANIFEST_FIELDS:
            if field in lg:
                errs.append("%s carries forbidden stale field %r" % (lg.get("log_id"), field))
    return errs


class ReadableBundle:
    """A single COMPLETED, VALIDATED bundle, read-only. Constructed by `StaticBundleConsumer.open_bundle`
    AFTER `consumer_read_errors` passes; do not construct directly with an unvalidated bundle."""

    def __init__(self, bundle_id, bundle_root, schema):
        self.bundle_id = bundle_id
        self.bundle_root = Path(bundle_root)
        self.schema = schema
        self.manifest = load_manifest(self.bundle_root)
        self.manifest_sha256 = sha256_file(self.bundle_root / MANIFEST_FILENAME)

    def manifest_payload(self):
        """The exact object a static website serves as `redline_manifest.json` (validated,
        `mock_example:false`). The Phase-1 mock UI consumes this unchanged."""
        return self.manifest

    def summary(self):
        return dict(self.manifest.get("summary", {}))

    def final_artifacts(self):
        """[(log_id, artifact_record)] for every `kind == FINAL_REDLINE_PNG` only -- the website
        renders nothing else. Covered/blocked logs contribute nothing (they carry no artifacts)."""
        out = []
        for lg in self.manifest.get("logs", []):
            for a in (lg.get("artifacts") or []):
                if a.get("kind") == FINAL_KIND:
                    out.append((lg["log_id"], a))
        return out

    def _final_index(self):
        """{manifest_path: (log_id, record)} for FINAL_REDLINE_PNG artifacts -- the serve allowlist."""
        return {a["path"]: (lid, a) for lid, a in self.final_artifacts()}

    def resolve_artifact(self, rel_path, *, read_bytes=True):
        """Resolve ONE artifact by its manifest path (allowlist; never by on-disk filename scan).

        Rejects (ArtifactNotServableError): a path that is not a manifest-listed FINAL_REDLINE_PNG,
        an unsafe / `..`-traversing / outside-root path, a missing file, or a sha256/byte drift vs the
        manifest record. Returns a served-artifact descriptor: ``{bundle_id, log_id, path,
        content_type, bytes, sha256[, data]}`` (``data`` present only when ``read_bytes``)."""
        entry = self._final_index().get(rel_path)
        if entry is None:
            raise ArtifactNotServableError(
                "path %r is not a FINAL_REDLINE_PNG in this bundle's manifest "
                "(serve by manifest path only; no filename inference)" % (rel_path,))
        log_id, rec = entry
        if not is_safe_relative_path(rel_path) or not _within_bundle(self.bundle_root, rel_path):
            raise ArtifactNotServableError("path %r is unsafe / escapes the bundle root" % (rel_path,))
        ap = self.bundle_root / rel_path
        if not ap.is_file():
            raise ArtifactNotServableError("artifact missing on disk: %r" % (rel_path,))
        size = ap.stat().st_size
        desc = {"bundle_id": self.bundle_id, "log_id": log_id, "path": rel_path,
                "content_type": _content_type(rel_path), "bytes": size, "sha256": rec.get("sha256")}
        if read_bytes:
            data = ap.read_bytes()
            actual = hashlib.sha256(data).hexdigest()
            if actual != rec.get("sha256"):
                raise ArtifactNotServableError(
                    "sha256 drift for %r (manifest %s != on-disk %s)" % (rel_path, rec.get("sha256"), actual))
            if size != rec.get("bytes"):
                raise ArtifactNotServableError(
                    "byte-size drift for %r (manifest %r != on-disk %d)" % (rel_path, rec.get("bytes"), size))
            desc["data"] = data
        return desc


class StaticBundleConsumer:
    """Read-only consumer of a durable bundle store. Default-OFF: pass ``enable=True`` or set
    ``TL2_STATIC_BUNDLE_CONSUMER_OPTIN=1``. Never writes, never renders, never publishes."""

    def __init__(self, store_root, *, enable=None, schema=None):
        enabled = consumer_enabled() if enable is None else bool(enable)
        if not enabled:
            raise ConsumerDisabledError(
                "static bundle consumer is default-OFF; set %s=1 or pass enable=True"
                % CONSUMER_OPTIN_ENV)
        self.store_root = Path(store_root)
        self.schema = schema or load_schema()
        self.index = load_store_index(self.store_root)

    def latest_valid_id(self) -> str:
        bid = self.index.get("latest_valid")
        if not bid:
            raise BundleNotReadableError("store has no latest_valid pointer")
        return bid

    def registered_ids(self):
        return list((self.index.get("bundles") or {}).keys())

    def _bundle_root(self, bundle_id) -> Path:
        # `bundle_id` must be a single safe path segment (defends against `..`/slash traversal even
        # before the registry allowlist check below).
        if not isinstance(bundle_id, str) or not bundle_id or "/" in bundle_id \
                or "\\" in bundle_id or bundle_id in (".", ".."):
            raise BundleNotReadableError("unsafe bundle id %r" % (bundle_id,))
        d = self.store_root / BUNDLES_SUBDIR / bundle_id
        if not d.is_dir():
            raise BundleNotReadableError("bundle %r not present in store" % (bundle_id,))
        return d

    def open_bundle(self, bundle_id=None) -> ReadableBundle:
        """Resolve `latest_valid` (or an explicit immutable `bundle_id`), enforce the website read
        contract, and return a ReadableBundle. Raises BundleNotReadableError on any failure."""
        bid = bundle_id or self.latest_valid_id()
        if bid not in (self.index.get("bundles") or {}):
            raise BundleNotReadableError("bundle id %r is not registered in store_index" % (bid,))
        root = self._bundle_root(bid)
        errs = consumer_read_errors(root, self.schema)
        if errs:
            raise BundleNotReadableError(
                "bundle %s fails the website read contract:\n  %s" % (bid, "\n  ".join(errs)))
        return ReadableBundle(bid, root, self.schema)

    def open_latest(self) -> ReadableBundle:
        return self.open_bundle(None)
