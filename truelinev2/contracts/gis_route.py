"""Phase 11 — generic, dialect-FREE GIS route reader for the product workspace (contract-only).

Reads a job's uploaded GIS_ROUTE (.kmz/.kml) into REAL WGS84 geometry (LineString / Point / Polygon) so the
workspace Map can show route CONTEXT from the operator's own upload. Dialect-agnostic: it returns the
coordinates literally present in the file regardless of folder/placemark naming.

It INVENTS nothing — no geocoding, no street-name synthesis, no snapping, no bbox-as-transform, no faked
coordinates. Placemark `<name>` text is echoed verbatim ONLY when present in the file (never generated).
Honest, NAMED empty states when there is no GIS_ROUTE upload, the file is missing, the bytes won't parse, or
the file carries no coordinates.

stdlib only (zipfile + xml.etree.ElementTree) — no new dependency. Distinct from the company-specific
`extract/kmz.py` (dialect-bound + proof-only). Reads ONLY the stored GIS_ROUTE upload; never the engine,
renderer, output slots, redline manifest, or any fixture.
"""
from __future__ import annotations

import io
import zipfile
from xml.etree import ElementTree as ET

from truelinev2.contracts.customer_project import validate_customer_project_id
from truelinev2.contracts.processing_job import job_dir, load_job, validate_job_id

GIS_ROUTE_KIND = "GIS_ROUTE"

# Honest, named result reasons (never invent geometry).
NO_GIS_ROUTE_UPLOADED = "NO_GIS_ROUTE_UPLOADED"
GIS_ROUTE_FILE_MISSING = "GIS_ROUTE_FILE_MISSING"
GIS_ROUTE_NOT_PARSEABLE = "GIS_ROUTE_NOT_PARSEABLE"
NO_COORDINATES_FOUND = "NO_COORDINATES_FOUND"

_GEOM_TYPES = ("LineString", "Point", "Polygon")


class GisRouteError(ValueError):
    """Base GIS-route error."""


def _strip_ns(tag: str) -> str:
    """Local tag name without the XML namespace ('{ns}LineString' -> 'LineString')."""
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _kml_text_from_bytes(data: bytes) -> bytes:
    """Return the KML XML bytes from a .kml (as-is) or .kmz (first .kml zip member, doc.kml preferred)."""
    if data[:2] == b"PK":  # zip magic -> .kmz
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = [n for n in zf.namelist() if n.lower().endswith(".kml")]
            if not names:
                raise GisRouteError("kmz has no .kml member")
            preferred = next((n for n in names if n.lower().endswith("doc.kml")), names[0])
            return zf.read(preferred)
    return data


def _parse_coords(text) -> list:
    """Parse a KML <coordinates> blob ('lon,lat[,alt] lon,lat[,alt] ...') into [[lon, lat], ...], dropping
    altitude and any tuple outside WGS84 range. Never invents or reorders."""
    if not text:
        return []
    out = []
    for tok in text.replace("\n", " ").replace("\t", " ").split():
        parts = tok.split(",")
        if len(parts) < 2:
            continue
        try:
            lon, lat = float(parts[0]), float(parts[1])
        except ValueError:
            continue
        if -180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0:
            out.append([lon, lat])
    return out


def _coords_under(geom) -> list:
    """First <coordinates> descendant of a geometry element, parsed (LineString/Point use direct child;
    Polygon's outer ring is nested under outerBoundaryIs/LinearRing — the first descendant suffices)."""
    for el in geom.iter():
        if _strip_ns(el.tag) == "coordinates":
            return _parse_coords(el.text)
    return []


def parse_gis_route(data: bytes) -> dict:
    """Parse KMZ/KML bytes into real WGS84 features + bbox. Returns a dict with `present`/`features`/`bbox`/
    `reason`/`feature_count`. Raises GisRouteError only on structurally-unreadable input (caught by the
    job-scoped loader and reported as an honest reason, never a 500)."""
    kml = _kml_text_from_bytes(data)
    try:
        root = ET.fromstring(kml)
    except ET.ParseError as exc:
        raise GisRouteError("kml is not well-formed xml: %s" % exc)

    placemarks = [e for e in root.iter() if _strip_ns(e.tag) == "Placemark"]
    features = []
    for pm in placemarks:
        name = None
        for ch in pm:
            if _strip_ns(ch.tag) == "name":
                name = (ch.text or "").strip() or None
                break
        for geom in pm.iter():
            gtype = _strip_ns(geom.tag)
            if gtype not in _GEOM_TYPES:
                continue
            coords = _coords_under(geom)
            if not coords:
                continue
            features.append({"type": gtype, "name": name, "coordinates": coords})

    all_pts = [pt for f in features for pt in f["coordinates"]]
    if not all_pts:
        return {"present": True, "reason": NO_COORDINATES_FOUND, "features": [], "bbox": None,
                "feature_count": 0}
    lons = [p[0] for p in all_pts]
    lats = [p[1] for p in all_pts]
    bbox = [min(lons), min(lats), max(lons), max(lats)]
    return {"present": True, "reason": None, "features": features, "bbox": bbox,
            "feature_count": len(features)}


def load_job_gis_route(store_root, customer_project_id, job_id) -> dict:
    """Read the job's uploaded GIS_ROUTE (.kmz/.kml) into real WGS84 geometry for the workspace map. Reads
    ONLY the stored GIS_ROUTE upload bytes; never invents. Honest named states for missing upload / missing
    file / unparseable bytes / no coordinates. Raises only the processing_job/customer_project contract
    errors (mapped to 404/403 by the route)."""
    validate_customer_project_id(customer_project_id)
    validate_job_id(job_id)
    job = load_job(store_root, customer_project_id, job_id)   # JobNotFoundError -> 404 at the route
    up = next((u for u in (job.get("uploads") or []) if u.get("kind") == GIS_ROUTE_KIND), None)
    if up is None:
        return {"present": False, "reason": NO_GIS_ROUTE_UPLOADED, "features": [], "bbox": None,
                "feature_count": 0, "upload": None}
    upload_ref = {"upload_id": up.get("upload_id"), "filename": up.get("original_filename"),
                  "kind": GIS_ROUTE_KIND}
    path = job_dir(store_root, customer_project_id, job_id) / up["stored_path"]
    if not path.is_file():
        return {"present": False, "reason": GIS_ROUTE_FILE_MISSING, "features": [], "bbox": None,
                "feature_count": 0, "upload": upload_ref}
    try:
        parsed = parse_gis_route(path.read_bytes())
    except Exception:   # malformed/unreadable upload -> honest not-available, never a 500
        return {"present": True, "reason": GIS_ROUTE_NOT_PARSEABLE, "features": [], "bbox": None,
                "feature_count": 0, "upload": upload_ref}
    parsed["upload"] = upload_ref
    return parsed
