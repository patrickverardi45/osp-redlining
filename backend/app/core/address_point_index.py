"""KMZ address-point index for B-MATCH-LOC-EVIDENCE-1 V3.

Parses Point placemarks from a KML/KMZ file and extracts subscriber-address
metadata from each placemark's `<description>` HTML table. The output is a
list of dicts with normalized fields ready for proximity-based candidate
route discovery.

Pure read-only; no project state touched; no corridor_engine import.

Schema per point:
  {
    "lon": float,
    "lat": float,
    "street_name": str,            # e.g. "Lawndale Avenue"
    "street_number": str,          # e.g. "802"
    "address": str,                # e.g. "802 Lawndale Ave, Brenham, TX 77833, USA"
    "ap_number": str,
    "node_type": str,              # "House", "Business", etc.
    "splice_location": str,
    "folder_path": str,            # KMZ folder hierarchy as " / "-joined string
  }

Only points that have BOTH valid coordinates AND a non-empty Street Name
field are included. Points without subscriber address evidence are dropped
because they are not useful for location-evidence matching.
"""

from __future__ import annotations

import io
import re
import zipfile
import xml.etree.ElementTree as ET
from typing import Any, Dict, List

KML_NS = {"kml": "http://www.opengis.net/kml/2.2"}

_DESC_ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
_DESC_CELL_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.IGNORECASE | re.DOTALL)
_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _strip_ns(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def _extract_kml_bytes(file_bytes: bytes, filename: str) -> bytes:
    """Return raw KML bytes, unwrapping a KMZ wrapper if needed."""
    name = (filename or "").lower()
    if name.endswith(".kmz") or file_bytes[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
            for entry in zf.namelist():
                if entry.lower().endswith(".kml"):
                    return zf.read(entry)
        raise ValueError(f"KMZ {filename!r} contains no .kml file")
    return file_bytes


def _parent_map(root: ET.Element) -> Dict[ET.Element, ET.Element]:
    return {child: parent for parent in root.iter() for child in parent}


def _folder_path(node: ET.Element, parent_map: Dict[ET.Element, ET.Element]) -> List[str]:
    path: List[str] = []
    cur = parent_map.get(node)
    while cur is not None:
        tag = _strip_ns(cur.tag)
        if tag in ("Folder", "Document"):
            name_el = cur.find("kml:name", KML_NS)
            if name_el is not None and (name_el.text or "").strip():
                path.insert(0, name_el.text.strip())
        cur = parent_map.get(cur)
    return path


def _parse_description_kv(desc_html: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not desc_html or "<" not in desc_html:
        return out
    for row in _DESC_ROW_RE.findall(desc_html):
        cells = _DESC_CELL_RE.findall(row)
        cells = [_HTML_TAG_RE.sub("", cell).strip() for cell in cells]
        if len(cells) >= 2 and cells[0]:
            out[cells[0]] = cells[1]
    return out


def _parse_point_coords(coord_text: str) -> tuple:
    if not coord_text:
        return ()
    raw = coord_text.strip().split()
    if not raw:
        return ()
    parts = raw[0].split(",")
    if len(parts) < 2:
        return ()
    try:
        return (float(parts[0]), float(parts[1]))
    except ValueError:
        return ()


def parse_address_points_from_kml(file_bytes: bytes, filename: str) -> List[Dict[str, Any]]:
    """Return a list of subscriber-address Points extracted from the KMZ/KML.

    Points without coordinates or without a non-empty Street Name field are
    dropped. The output is deterministically ordered by (lon, lat) for
    reproducibility across runs.
    """
    kml_bytes = _extract_kml_bytes(file_bytes, filename)
    root = ET.fromstring(kml_bytes)
    parent_map = _parent_map(root)

    out: List[Dict[str, Any]] = []
    for placemark in root.findall(".//kml:Placemark", KML_NS):
        point_node = placemark.find(".//kml:Point/kml:coordinates", KML_NS)
        if point_node is None:
            continue
        coords = _parse_point_coords(point_node.text or "")
        if not coords:
            continue
        desc = placemark.findtext("kml:description", namespaces=KML_NS) or ""
        kv = _parse_description_kv(desc)
        street_name = (kv.get("Street Name") or "").strip()
        if not street_name:
            continue
        fp = _folder_path(placemark, parent_map)
        out.append({
            "lon": coords[0],
            "lat": coords[1],
            "street_name": street_name,
            "street_number": (kv.get("Street Number") or "").strip(),
            "address": (kv.get("Address") or "").strip(),
            "ap_number": (kv.get("AP Number") or "").strip(),
            "node_type": (kv.get("Node Type") or "").strip(),
            "splice_location": (kv.get("Splice Location") or "").strip(),
            "folder_path": " / ".join(fp),
        })

    out.sort(key=lambda p: (p["lon"], p["lat"]))
    return out
