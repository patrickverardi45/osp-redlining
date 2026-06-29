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
import re
import zipfile
from xml.etree import ElementTree as ET

from truelinev2.contracts.customer_project import validate_customer_project_id
from truelinev2.contracts.kmz_export import build_kmz_bytes  # generic, deterministic KML->KMZ packer (reused)
from truelinev2.contracts.processing_job import job_dir, load_job, validate_job_id

GIS_ROUTE_KIND = "GIS_ROUTE"

# KML aabbggrr — orange route line, matching the workspace map. Deliberately NOT red: red is reserved for
# redline strokes (the red-stroke law), and this KMZ is the operator's UPLOADED route, never redline output.
ROUTE_LINE_KML_COLOR = "ff0854d8"

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


def _xml_escape(s) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _table_fields(description) -> dict:
    """Parse a Placemark <description> HTML <table> into {key: value} (many KML exports embed attributes
    there rather than in ExtendedData). Adjacent <td> cells are paired (key, value). GENERIC + dialect-free:
    it reads whatever labels the file printed, verbatim, and invents nothing. Empty keys are skipped."""
    if not description:
        return {}
    cells = re.findall(r"<td[^>]*>(.*?)</td>", description, re.S | re.I)
    cells = [re.sub(r"<[^>]+>", "", c).replace("&quot;", '"').replace("&amp;", "&").strip() for c in cells]
    out = {}
    for i in range(0, len(cells) - 1, 2):
        key = cells[i]
        if key:
            out[key] = cells[i + 1]
    return out


def _street_label(fields) -> str:
    """The street label the FILE printed, verbatim, or None. Generic: picks the field whose key reads like a
    street name (e.g. 'Street Name'), else a bare 'Street' key. NEVER synthesizes or geocodes a street — a
    street that the source does not state stays None (honest absence, not a guess)."""
    for k, v in fields.items():
        kl = k.lower()
        if "street" in kl and "name" in kl:
            vv = (v or "").strip()
            if vv:
                return vv
    for k, v in fields.items():
        if k.lower().strip() == "street":
            vv = (v or "").strip()
            if vv:
                return vv
    return None


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
        description = None
        for ch in pm:
            tag = _strip_ns(ch.tag)
            if tag == "name" and name is None:
                name = (ch.text or "").strip() or None
            elif tag == "description" and description is None:
                description = ch.text
        # Verbatim street label when the file's <description> table prints one (premises points usually do);
        # None otherwise. Never invented — see _street_label.
        source_label = _street_label(_table_fields(description))
        for geom in pm.iter():
            gtype = _strip_ns(geom.tag)
            if gtype not in _GEOM_TYPES:
                continue
            coords = _coords_under(geom)
            if not coords:
                continue
            features.append({"type": gtype, "name": name, "coordinates": coords,
                             "source_label": source_label})

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


# --------------------------------------------------------------------------- #
# Route KMZ export — a Google-Earth-openable KMZ of the UPLOADED route (real WGS84 geometry + verbatim
# names / street labels). This is the operator's own uploaded DESIGN route, clearly labeled — it is NOT
# redline output. Redline geometry is pixel-only and is NEVER placed in this KMZ (the redline-KMZ authority
# stays kmz_export.evaluate_export, which honestly BLOCKS pixel-only). Invents nothing: it emits only the
# coordinates parsed from the file, styled as a route (orange), never red.
# --------------------------------------------------------------------------- #
def build_route_kml(features, *, doc_name="Uploaded route") -> str:
    """Deterministic KML TEXT for uploaded route features (LineString / Point / Polygon), preserving each
    placemark's `name` and any source-provided street label VERBATIM. Coordinates are echoed exactly as
    parsed (already WGS84-validated). No timestamps -> byte-stable for identical input."""
    parts = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>',
             '<name>%s</name>' % _xml_escape(doc_name),
             '<Style id="route"><LineStyle><color>%s</color><width>3</width></LineStyle></Style>'
             % ROUTE_LINE_KML_COLOR]
    for f in features:
        coords = f.get("coordinates") or []
        if not coords:
            continue
        gtype = f.get("type")
        coord_str = " ".join("%s,%s" % (lon, lat) for lon, lat in coords)
        if gtype == "Point":
            geom = "<Point><coordinates>%s</coordinates></Point>" % coord_str
        elif gtype == "Polygon":
            geom = ("<Polygon><outerBoundaryIs><LinearRing><coordinates>%s</coordinates>"
                    "</LinearRing></outerBoundaryIs></Polygon>" % coord_str)
        else:
            geom = "<LineString><coordinates>%s</coordinates></LineString>" % coord_str
        nm = f.get("name") or gtype
        label = f.get("source_label")
        desc = "<description>%s</description>" % _xml_escape("Street: %s" % label) if label else ""
        style = "<styleUrl>#route</styleUrl>" if gtype == "LineString" else ""
        parts.append("<Placemark><name>%s</name>%s%s%s</Placemark>"
                     % (_xml_escape(nm), style, desc, geom))
    parts.append("</Document></kml>")
    return "\n".join(parts)


def load_job_route_kmz(store_root, customer_project_id, job_id) -> dict:
    """Build a downloadable KMZ of the job's UPLOADED route so the operator can open it in Google Earth.
    Returns {present, reason, kmz_bytes, filename, feature_count}. Honest named states (no route upload /
    missing file / unparseable / no coordinates) -> present:False with kmz_bytes:None (the route route then
    answers 409, never a faked file). Reuses the deterministic build_kmz_bytes packer."""
    route = load_job_gis_route(store_root, customer_project_id, job_id)
    if not route.get("features"):
        return {"present": False, "reason": route.get("reason") or NO_COORDINATES_FOUND,
                "kmz_bytes": None, "filename": None, "feature_count": 0}
    kml = build_route_kml(route["features"], doc_name="Uploaded route")
    return {"present": True, "reason": None, "kmz_bytes": build_kmz_bytes(kml),
            "filename": "route.kmz", "feature_count": route.get("feature_count", 0)}
