"""Phase 10 — downloadable closeout export bundle (a real .zip; contract-only).

Turns the export from a descriptor-of-references into a SELF-DESCRIBING, DOWNLOADABLE closeout bundle (a
zip) assembled from a job's EXISTING trusted output: the validated redline bundle (FINAL_REDLINE_PNG bytes
+ the manifest JSON), plus the closeout / export-package / KMZ-export state and the reviewed-bore-log
metadata. It RENDERS nothing, INVENTS nothing, and FAKES no PDF/KMZ — a pixel-only redline manifest is
reported honestly as BLOCKED inside the bundle's status JSON, never a fabricated KMZ.

Honesty / boundaries:
  * Artifact bytes come ONLY from the durable bundle store, resolved by manifest path + sha256 (the read
    consumer re-verifies the checksum) — never an on-disk filename scan, never a re-render.
  * It reads ONLY trusted slots/records (the validated artifact_bundle slot, closeout/export/kmz/reviewed
    records) — never ``job["uploads"]`` raw files, never the engine.
  * Deterministic: fixed member names + a fixed (1980) zip timestamp => byte-stable for identical content.
  * No new manifest enum, no schema change, no engine/renderer/fixture/coordinate change.
"""
from __future__ import annotations

import io
import json
import zipfile

from truelinev2.contracts.customer_project import validate_customer_project_id
from truelinev2.contracts.processing_job import job_dir, load_job, validate_job_id
from truelinev2.contracts.manifest_handoff import ARTIFACT_BUNDLE_SLOT, BUNDLE_STORE_SUBDIR
from truelinev2.contracts.published_bundle_consumer import StaticBundleConsumer
from truelinev2.contracts.closeout_review import (
    CloseoutNotFoundError, closeout_summary, load_closeout_review,
)
from truelinev2.contracts.export_package import (
    ExportPackageNotFoundError, export_package_view, load_export_package,
)
from truelinev2.contracts.kmz_export import (
    EXPORTABLE as KMZ_EXPORTABLE_STATUS, build_kmz_bytes, evaluate_export,
)
from truelinev2.contracts.reviewed_bore_log import list_reviewed_bore_logs

EXPORT_ZIP_MEDIA_TYPE = "application/zip"
EXPORT_ZIP_FILENAME = "redline_export_%s.zip"

# In-zip member layout (fixed, self-describing).
MANIFEST_MEMBER = "redline_manifest.json"
README_MEMBER = "README.txt"
STATUS_DIR = "status/"
KMZ_MEMBER = "redline_export.kmz"            # included ONLY when the KMZ export is genuinely EXPORTABLE


class ExportBundleError(ValueError):
    """Base export-bundle error."""


class NoRedlineBundleError(ExportBundleError):
    """The job has no validated redline bundle to export (nothing to package yet)."""


def _open_bundle(store_root, customer_project_id, job_id):
    """Open the job's attached, validated redline bundle (read-only consumer). Raises NoRedlineBundleError
    if the job has no validated artifact_bundle slot (set ONLY by a SUCCEEDED handoff)."""
    job = load_job(store_root, customer_project_id, job_id)
    slot = (job.get("slots") or {}).get(ARTIFACT_BUNDLE_SLOT)
    if not slot:
        raise NoRedlineBundleError("job has no validated redline bundle to export")
    bundle_store = job_dir(store_root, customer_project_id, job_id) / BUNDLE_STORE_SUBDIR
    return StaticBundleConsumer(bundle_store, enable=True).open_bundle(slot["ref"]["bundle_id"])


def _readme(job_id, manifest, kmz, artifact_count, kmz_included) -> str:
    """Plain-English description of the bundle contents + honest provenance/limitation notes."""
    origin = manifest.get("bundle_origin")
    summary = manifest.get("summary", {})
    lines = [
        "FieldRoute redline export bundle",
        "================================",
        "job: %s" % job_id,
        "bundle_origin: %s" % origin,
        "render_commit: %s" % (manifest.get("engine", {}) or {}).get("render_commit"),
        "frontier (this bundle): %s" % summary.get("frontier"),
        "",
        "Contents:",
        "  redline_manifest.json        the published redline manifest (drawn/covered/blocked truth)",
        "  artifacts/<log>/*.png        %d FINAL_REDLINE_PNG redline render(s), sha256-verified" % artifact_count,
        "  status/closeout_review.json  server-authoritative closeout status + summary",
        "  status/export_package.json   the export-package descriptor (included/omitted sections)",
        "  status/kmz_export.json       KMZ/KML geometry-export safety verdict",
        "  status/reviewed_bore_logs.json  the reviewed bore-log rows / review state / grouping",
    ]
    if kmz_included:
        lines.append("  redline_export.kmz           valid KMZ (real geospatial geometry)")
    lines += [
        "",
        "Honesty notes:",
        "  * Redline geometry is the engine's, rendered from the plan's own drawn vectors — never invented.",
    ]
    if kmz.get("status") != KMZ_EXPORTABLE_STATUS:
        codes = ", ".join(sorted({b.get("code") for b in (kmz.get("blockers") or [])})) or "BLOCKED"
        lines.append("  * KMZ/KML is NOT included: the redline manifest is %s (%s). The system refuses to "
                     "fake geographic coordinates for pixel-space redlines." % (kmz.get("geometry_basis"), codes))
    return "\n".join(lines) + "\n"


def build_export_zip(store_root, customer_project_id, job_id) -> tuple:
    """Assemble the job's downloadable closeout zip from EXISTING trusted output. Returns (zip_bytes,
    filename). Raises NoRedlineBundleError if the job has no validated redline bundle yet."""
    validate_customer_project_id(customer_project_id)
    validate_job_id(job_id)
    bundle = _open_bundle(store_root, customer_project_id, job_id)
    manifest = bundle.manifest_payload()

    kmz = evaluate_export(store_root, customer_project_id, job_id)
    try:
        co = load_closeout_review(store_root, customer_project_id, job_id)
        closeout = {**co, "summary": closeout_summary(co)}
    except CloseoutNotFoundError:
        closeout = None
    try:
        ep = load_export_package(store_root, customer_project_id, job_id)
        export_pkg = {"record": ep, "view": export_package_view(ep)}
    except ExportPackageNotFoundError:
        export_pkg = None
    rbls = list_reviewed_bore_logs(store_root, customer_project_id, job_id)

    def _put(z, name, text):
        z.writestr(zipfile.ZipInfo(name), text)        # ZipInfo => fixed 1980 date => reproducible

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        _put(z, MANIFEST_MEMBER, json.dumps(manifest, indent=2, sort_keys=True))
        artifact_count = 0
        for _log_id, art in bundle.final_artifacts():
            desc = bundle.resolve_artifact(art["path"], read_bytes=True)   # sha256-verified bytes
            z.writestr(zipfile.ZipInfo(desc["path"]), desc["data"])
            artifact_count += 1
        _put(z, STATUS_DIR + "kmz_export.json", json.dumps(kmz, indent=2, sort_keys=True))
        if closeout is not None:
            _put(z, STATUS_DIR + "closeout_review.json", json.dumps(closeout, indent=2, sort_keys=True))
        if export_pkg is not None:
            _put(z, STATUS_DIR + "export_package.json", json.dumps(export_pkg, indent=2, sort_keys=True))
        _put(z, STATUS_DIR + "reviewed_bore_logs.json", json.dumps(rbls, indent=2, sort_keys=True))
        kmz_included = kmz.get("status") == KMZ_EXPORTABLE_STATUS and bool(kmz.get("kml"))
        if kmz_included:
            z.writestr(zipfile.ZipInfo(KMZ_MEMBER), build_kmz_bytes(kmz["kml"]))
        _put(z, README_MEMBER, _readme(job_id, manifest, kmz, artifact_count, kmz_included))
    if artifact_count == 0:
        raise NoRedlineBundleError("the validated bundle has no FINAL_REDLINE_PNG artifacts to export")
    return buf.getvalue(), EXPORT_ZIP_FILENAME % job_id
