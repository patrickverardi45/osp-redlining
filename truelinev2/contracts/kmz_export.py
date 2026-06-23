"""Permanent v2 product foundation — the kmz_export geometry-safety contract (contract-only).

Decides whether a processing_job's APPROVED redline output (its `redline_manifest` + `artifact_bundle`
output slots) can be exported to KMZ/KML — and REFUSES to fake coordinates when it cannot. This is the
geometry-SAFETY contract, not the export-package producer: `evaluate_export` is READ-ONLY, returns an
export record, persists nothing, and never touches the `export_package` slot.

Core rule (the whole point): a KMZ/KML export must NEVER fake coordinates. The current v2 redline manifest
carries only sheet/station/pixel/artifact data (no lat/long, no CRS — see redline_manifest.schema.json),
so it classifies `UNSUPPORTED_PIXEL_ONLY` and the export is BLOCKED with a named reason. The contract is
built ready for `GEOSPATIAL_COORDINATES` (verified lat/long the engine may emit in a FUTURE lane), but it
synthesizes nothing today.

What it must NEVER do (v1 anti-patterns, per the salvage audit): re-export the uploaded GIS_ROUTE
(KMZ/KML) as if it were approved output; snap stations/redlines to route/nearest-line; treat PDF or KMZ
bounding boxes as real-world coordinates; export without a CRS. `evaluate_export` reads ONLY the two
trusted output slots — never `job["uploads"]`. Contract-only: no engine execution, renderer, web/backend,
AI/OCR, billing/closeout, or deploy. The redline manifest schema is NOT modified by this lane.
"""
from __future__ import annotations

import hashlib
import io
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from truelinev2.contracts.processing_job import job_dir, load_job
from truelinev2.contracts.manifest_handoff import BUNDLE_STORE_SUBDIR, VALIDATION_VALIDATED
from truelinev2.contracts.published_bundle import MANIFEST_FILENAME, load_manifest, sha256_file
from truelinev2.contracts.published_bundle_store import BUNDLES_SUBDIR

KMZ_EXPORT_RECORD_FORMAT = "trueline-kmz-export-1"
KMZ_PACKAGE_FORMAT = "trueline-kmz-export-package-1"

# Export status (default BLOCKED is the safe state; EXPORTABLE is only ever set explicitly).
EXPORTABLE = "EXPORTABLE"
BLOCKED = "BLOCKED"

# Geometry basis taxonomy (generic). Only GEOSPATIAL_COORDINATES is directly emittable in this lane.
GEOSPATIAL_COORDINATES = "GEOSPATIAL_COORDINATES"
GEOREFERENCED_SHEET = "GEOREFERENCED_SHEET"
UNSUPPORTED_PIXEL_ONLY = "UNSUPPORTED_PIXEL_ONLY"
GEOMETRY_BASES = (GEOSPATIAL_COORDINATES, GEOREFERENCED_SHEET, UNSUPPORTED_PIXEL_ONLY)

# Blocker codes (named reasons; a blocked export records these instead of faking a KMZ).
MISSING_MANIFEST_SLOT = "MISSING_MANIFEST_SLOT"
MISSING_ARTIFACT_BUNDLE_SLOT = "MISSING_ARTIFACT_BUNDLE_SLOT"
UNTRUSTED_HANDOFF = "UNTRUSTED_HANDOFF"
MANIFEST_NOT_RESOLVABLE = "MANIFEST_NOT_RESOLVABLE"
GEOREFERENCE_NOT_RESOLVED = "GEOREFERENCE_NOT_RESOLVED"
AMBIGUOUS_CRS = "AMBIGUOUS_CRS"
SOURCE_CONFLICT = "SOURCE_CONFLICT"
COORDINATE_UNCERTAINTY = "COORDINATE_UNCERTAINTY"
FEATURE_NOT_TRACEABLE = "FEATURE_NOT_TRACEABLE"
BLOCKER_CODES = (MISSING_MANIFEST_SLOT, MISSING_ARTIFACT_BUNDLE_SLOT, UNTRUSTED_HANDOFF,
                 MANIFEST_NOT_RESOLVABLE, UNSUPPORTED_PIXEL_ONLY, GEOREFERENCE_NOT_RESOLVED,
                 AMBIGUOUS_CRS, SOURCE_CONFLICT, COORDINATE_UNCERTAINTY, FEATURE_NOT_TRACEABLE)

# Approved geometry provenance + confidence required to export (LOW / missing is too uncertain).
ENGINE_REVIEWED = "ENGINE_REVIEWED"
HUMAN_OVERRIDE = "HUMAN_OVERRIDE"
FIELD_GPS = "FIELD_GPS"
GEOMETRY_SOURCES = (ENGINE_REVIEWED, HUMAN_OVERRIDE, FIELD_GPS)
EXPORTABLE_CONFIDENCE = ("HIGH", "MEDIUM")

EXPORT_CRS = {"crs": "EPSG:4326", "datum": "WGS84", "units": "degrees"}
EXPORT_STROKE_KML_COLOR = "ff0000ff"   # KML aabbggrr opaque red — generic export style only


# --------------------------------------------------------------------------- #
# Layer A — pure geometry-basis + KML builders (NB: the `geometry` block below is a FUTURE manifest field;
# real schema-valid v2 manifests never carry it, so on real data the classifier returns
# UNSUPPORTED_PIXEL_ONLY. These functions never treat span/source_sheets/artifacts as geospatial.)
# --------------------------------------------------------------------------- #
def _has_geometry(log) -> bool:
    g = log.get("geometry")
    return isinstance(g, dict) and bool(g.get("coordinates"))


def classify_geometry_basis(manifest) -> str:
    """Classify the geometry basis of a manifest. ONLY an explicit per-feature `geometry` block (lat/long
    + CRS) or a verified manifest-level `georeference` counts as a geospatial basis — stations, source
    sheets, footage, and PNG artifacts are NEVER treated as geospatial."""
    drawn = [lg for lg in manifest.get("logs", []) if lg.get("drawn")]
    if drawn and all(_has_geometry(lg) for lg in drawn):
        return GEOSPATIAL_COORDINATES
    if isinstance(manifest.get("georeference"), dict):
        return GEOREFERENCED_SHEET            # recognized basis, but coords are not resolved in this lane
    return UNSUPPORTED_PIXEL_ONLY


def extract_exportable_features(manifest, *, source_manifest_id, source_artifact_bundle_id):
    """Build generic feature descriptors for drawn logs + collect per-feature blockers. Each exportable
    feature must carry a valid `geometry` block (EPSG:4326, approved source, sufficient confidence);
    anything else yields a named per-feature blocker. Returns (features, blockers)."""
    features, blockers = [], []
    for lg in manifest.get("logs", []):
        if not lg.get("drawn"):
            continue
        log_id = lg.get("log_id")
        feature_id = "feat-%s" % log_id
        geom = lg.get("geometry")
        fblock = []
        out_geom = None
        if not (isinstance(geom, dict) and geom.get("coordinates")):
            fblock.append((FEATURE_NOT_TRACEABLE,
                           "drawn log %r has no geospatial geometry to export" % log_id))
        else:
            if geom.get("crs") != "EPSG:4326":
                fblock.append((AMBIGUOUS_CRS,
                               "feature %r crs %r is not EPSG:4326" % (feature_id, geom.get("crs"))))
            if geom.get("source") not in GEOMETRY_SOURCES:
                fblock.append((SOURCE_CONFLICT,
                               "feature %r geometry source %r is not approved" % (feature_id, geom.get("source"))))
            if geom.get("confidence") not in EXPORTABLE_CONFIDENCE:
                fblock.append((COORDINATE_UNCERTAINTY,
                               "feature %r confidence %r is too uncertain to export"
                               % (feature_id, geom.get("confidence"))))
            if not fblock:
                out_geom = {"crs": geom.get("crs"), "datum": geom.get("datum"), "units": geom.get("units"),
                            "kind": geom.get("kind", "LineString"),
                            "coordinates": [list(c) for c in geom["coordinates"]],
                            "source": geom.get("source"), "confidence": geom.get("confidence")}
        closure = lg.get("closure")
        length_ft = closure.get("drawn_ft") if isinstance(closure, dict) else None
        fb_dicts = [{"code": c, "reason": r, "feature_id": feature_id} for c, r in fblock]
        features.append({
            "feature_id": feature_id, "source_manifest_id": source_manifest_id,
            "source_artifact_bundle_id": source_artifact_bundle_id, "source_log_id": log_id,
            "status": lg.get("status"), "length_ft": length_ft, "geometry": out_geom,
            "blockers": fb_dicts, "warnings": [],
        })
        blockers.extend(fb_dicts)
    return features, blockers


def _xml_escape(s) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def build_kml(features, *, source_manifest_id, source_artifact_bundle_id) -> str:
    """Deterministic KML TEXT for already-validated features (called only when there are no blockers).
    Red styling is generic export metadata; each Placemark carries traceability ExtendedData. No
    timestamps, features sorted by feature_id -> byte-stable. No binary KMZ is written."""
    parts = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>',
             '<name>redline export</name>',
             '<Style id="redline"><LineStyle><color>%s</color><width>3</width></LineStyle>'
             '<IconStyle><color>%s</color></IconStyle></Style>'
             % (EXPORT_STROKE_KML_COLOR, EXPORT_STROKE_KML_COLOR)]
    for f in sorted(features, key=lambda x: x["feature_id"]):
        g = f["geometry"]
        coord_str = " ".join("%s,%s" % (lon, lat) for lon, lat in g["coordinates"])
        inner = ('<Point><coordinates>%s</coordinates></Point>' % coord_str if g["kind"] == "Point"
                 else '<LineString><coordinates>%s</coordinates></LineString>' % coord_str)
        ext = ("".join('<Data name="%s"><value>%s</value></Data>' % (k, _xml_escape(v)) for k, v in (
            ("feature_id", f["feature_id"]), ("source_manifest_id", source_manifest_id),
            ("source_artifact_bundle_id", source_artifact_bundle_id),
            ("source_log_id", f["source_log_id"]), ("source", g["source"]),
            ("confidence", g["confidence"]))))
        parts.append('<Placemark><name>%s</name><styleUrl>#redline</styleUrl>'
                     '<ExtendedData>%s</ExtendedData>%s</Placemark>'
                     % (_xml_escape(f["feature_id"]), ext, inner))
    parts.append('</Document></kml>')
    return "\n".join(parts)


# --------------------------------------------------------------------------- #
# Layer A2 — binary KMZ packaging + structural validation (the file Google Earth opens). These NEVER
# synthesize coordinates: ``build_kmz_bytes`` only packs KML that ``build_kml`` already produced from
# VERIFIED geospatial features, and ``validate_kmz_bytes`` is read-only structural checking.
# --------------------------------------------------------------------------- #
KMZ_MEDIA_TYPE = "application/vnd.google-earth.kmz"
KMZ_KML_MEMBER = "doc.kml"          # the conventional root document Google Earth opens first
_WGS84_LON = (-180.0, 180.0)
_WGS84_LAT = (-90.0, 90.0)


def build_kmz_bytes(kml_text) -> bytes:
    """Pack already-built KML text into a valid KMZ (a zip whose root document is ``doc.kml``) — the exact
    container Google Earth opens. Deterministic: a fixed member name + a fixed (1980-01-01) zip timestamp =>
    byte-stable output for identical KML. No coordinates are synthesized here; the KML is built upstream from
    VERIFIED geospatial features only (a pixel-only manifest never reaches this)."""
    if not isinstance(kml_text, str) or not kml_text.strip():
        raise ValueError("build_kmz_bytes requires non-empty KML text")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(zipfile.ZipInfo(KMZ_KML_MEMBER), kml_text)     # ZipInfo => fixed 1980 date => reproducible
    return buf.getvalue()


def _strip_kml_ns(text) -> str:
    text = re.sub(r'xmlns(:\w+)?="[^"]+"', "", text)
    text = re.sub(r"(</?)\w+:", r"\1", text)
    return re.sub(r"\s\w+:(\w+=)", r" \1", text)


def validate_kmz_bytes(data) -> dict:
    """Read-only STRUCTURAL validation of a KMZ blob (the basis for any 'Google Earth can load this' claim
    short of a manual open): it must be a valid zip with an intact KML member that parses, carries >=1
    Placemark, and whose every coordinate is a well-formed WGS84 lon,lat. Returns
    {valid, errors, kml_member, members, placemark_count, coordinate_count, geometry_kinds}."""
    out = {"valid": False, "errors": [], "kml_member": None, "members": [],
           "placemark_count": 0, "coordinate_count": 0, "geometry_kinds": []}
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except (zipfile.BadZipFile, TypeError):
        out["errors"].append("not a valid zip archive")
        return out
    out["members"] = zf.namelist()
    if zf.testzip() is not None:
        out["errors"].append("corrupt zip member")
    kml_member = next((n for n in out["members"] if n.lower().endswith(".kml")), None)
    out["kml_member"] = kml_member
    if kml_member is None:
        out["errors"].append("no .kml member in the KMZ")
        return out
    try:
        root = ET.fromstring(_strip_kml_ns(zf.read(kml_member).decode("utf-8", "replace")))
    except ET.ParseError as exc:
        out["errors"].append("kml does not parse: %s" % exc)
        return out
    kinds = set()
    for pm in root.iter("Placemark"):
        out["placemark_count"] += 1
        for kind in ("LineString", "Point", "Polygon"):
            if pm.find(".//" + kind) is not None:
                kinds.add(kind)
    out["geometry_kinds"] = sorted(kinds)
    for cel in root.iter("coordinates"):
        for tok in (cel.text or "").split():
            parts = tok.split(",")
            if len(parts) < 2:
                continue
            try:
                lon, lat = float(parts[0]), float(parts[1])
            except ValueError:
                out["errors"].append("non-numeric coordinate %r" % (tok,))
                continue
            out["coordinate_count"] += 1
            if not (_WGS84_LON[0] <= lon <= _WGS84_LON[1] and _WGS84_LAT[0] <= lat <= _WGS84_LAT[1]):
                out["errors"].append("coordinate out of WGS84 range: %s,%s" % (lon, lat))
    if out["placemark_count"] == 0:
        out["errors"].append("no Placemark elements")
    if out["coordinate_count"] == 0:
        out["errors"].append("no coordinates")
    out["valid"] = not out["errors"]
    return out


# --------------------------------------------------------------------------- #
# Layer B — job-integrated, READ-ONLY evaluation (returns a record; persists nothing; never touches
# export_package; reads ONLY the two trusted output slots, never job["uploads"]).
# --------------------------------------------------------------------------- #
def _new_record(customer_project_id, processing_job_id) -> dict:
    return {"record_format": KMZ_EXPORT_RECORD_FORMAT, "customer_project_id": customer_project_id,
            "processing_job_id": processing_job_id, "source_manifest_id": None,
            "source_artifact_bundle_id": None, "geometry_basis": None, "status": BLOCKED,
            "blockers": [], "warnings": [], "features": [], "crs": None,
            "kml": None, "kml_sha256": None, "kmz_package": None}


def _block(record, code, reason) -> dict:
    record["status"] = BLOCKED
    record["blockers"].append({"code": code, "reason": reason, "feature_id": None})
    return record


def evaluate_export(store_root, customer_project_id, processing_job_id) -> dict:
    """Evaluate whether a job's approved redline output can be exported to KMZ/KML. READ-ONLY: returns an
    export record (EXPORTABLE or BLOCKED with named blockers); persists nothing; never sets export_package;
    never reads the uploaded GIS_ROUTE. Today, real (sheet/station/pixel) manifests return
    BLOCKED[UNSUPPORTED_PIXEL_ONLY] — the system abstains rather than fake coordinates."""
    job = load_job(store_root, customer_project_id, processing_job_id)
    record = _new_record(customer_project_id, processing_job_id)
    slots = job.get("slots") or {}
    m_slot, b_slot = slots.get("redline_manifest"), slots.get("artifact_bundle")
    if not m_slot:
        return _block(record, MISSING_MANIFEST_SLOT, "job has no redline_manifest output slot")
    if not b_slot:
        return _block(record, MISSING_ARTIFACT_BUNDLE_SLOT, "job has no artifact_bundle output slot")
    m_ref, b_ref = (m_slot.get("ref") or {}), (b_slot.get("ref") or {})
    record["source_manifest_id"] = m_ref.get("manifest_id")
    record["source_artifact_bundle_id"] = b_ref.get("bundle_id")
    if m_ref.get("validation_status") != VALIDATION_VALIDATED \
            or b_ref.get("validation_status") != VALIDATION_VALIDATED:
        return _block(record, UNTRUSTED_HANDOFF, "an output slot is not VALIDATED")

    bundle_id = b_ref.get("bundle_id")
    bundle_root = (job_dir(store_root, customer_project_id, processing_job_id)
                   / BUNDLE_STORE_SUBDIR / BUNDLES_SUBDIR / str(bundle_id))
    mpath = bundle_root / MANIFEST_FILENAME
    if not mpath.is_file():
        return _block(record, MANIFEST_NOT_RESOLVABLE,
                      "stored manifest not found for bundle %r" % (bundle_id,))
    if sha256_file(mpath) != m_ref.get("manifest_sha256"):
        return _block(record, MANIFEST_NOT_RESOLVABLE,
                      "stored manifest sha256 does not match the redline_manifest slot")
    manifest = load_manifest(bundle_root)

    basis = classify_geometry_basis(manifest)
    record["geometry_basis"] = basis
    if basis == UNSUPPORTED_PIXEL_ONLY:
        return _block(record, UNSUPPORTED_PIXEL_ONLY,
                      "manifest has no geospatial basis (sheet/station/pixel only); "
                      "refusing to fake coordinates")
    if basis == GEOREFERENCED_SHEET:
        return _block(record, GEOREFERENCE_NOT_RESOLVED,
                      "georeference present but features are not resolved to coordinates")

    features, fblockers = extract_exportable_features(
        manifest, source_manifest_id=record["source_manifest_id"],
        source_artifact_bundle_id=record["source_artifact_bundle_id"])
    record["features"] = features
    if fblockers:
        record["blockers"].extend(fblockers)
        record["status"] = BLOCKED
        return record

    kml = build_kml(features, source_manifest_id=record["source_manifest_id"],
                    source_artifact_bundle_id=record["source_artifact_bundle_id"])
    record["crs"] = dict(EXPORT_CRS)
    record["kml"] = kml
    record["kml_sha256"] = hashlib.sha256(kml.encode("utf-8")).hexdigest()
    record["kmz_package"] = {"filename": "redline_export.kmz", "format": KMZ_PACKAGE_FORMAT,
                             "members": [{"name": "doc.kml", "sha256": record["kml_sha256"]}],
                             "note": "interface descriptor only; no binary KMZ written in this lane"}
    record["status"] = EXPORTABLE
    return record
