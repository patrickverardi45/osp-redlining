r"""M9.0 -- KMZ feature reader (pure; proof-only; UNWIRED).

The first piece of the v2 geo lane. Parses a design KMZ into a typed feature
model so the engine can REASON about cross-source (PDF<->KMZ) evidence. It does
NOT place, draw, or correlate by itself -- correlation is a separate, gated law
(see proof/run_kmz_correlation_audit). v2 stays PDF-FIRST: the KMZ never
overrides PDF; it can only corroborate or supply a missing anchor under a proven
zero-false gate.

What this module is and is not:
  * IS: a namespace-safe KML reader that emits typed STRUCTURE points (with
    their printed identity fields -- AP ids, splice-loc, sizes) and ROUTE
    polylines, classified by an INJECTED dialect (folder -> class). The Brenham
    design KMZ encodes structure attributes inside an HTML <table> in each
    Placemark's <description> (no ExtendedData), so the reader parses that.
  * IS NOT: a placement engine. No geometry output, no strokes, no PNG, no
    station math, no product-lane change. Nothing in resolve_bore / the sweep /
    the reviewer service consults it (UNWIRED).

Convention seam: every plan-set string (folder names, the AP/splice grammar)
lives in a ``KmzDialect`` (Brenham instance below, in extract/ like the other
dialects). This reader holds NO plan-set literals (drift-guard-enforced).
"""
from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import xml.etree.ElementTree as ET

# ---- typed feature model ----------------------------------------------------


@dataclass(frozen=True)
class KmzStructure:
    """One classified structure POINT and its printed identity fields."""
    kmz_class: str                 # dialect class (e.g. "terminal_port_hh")
    name: str
    ap_ids: Tuple[int, ...]        # AP ids parsed from name/Note/AP Number
    splice_loc: Optional[str]      # "SPLICE LOC NN" if present
    lon: float
    lat: float
    fields: Dict[str, str] = field(default_factory=dict)   # raw HTML-table kv

    def to_dict(self) -> dict:
        return {"kmz_class": self.kmz_class, "name": self.name,
                "ap_ids": list(self.ap_ids), "splice_loc": self.splice_loc,
                "lon": round(self.lon, 6), "lat": round(self.lat, 6),
                "fields": self.fields}


@dataclass(frozen=True)
class KmzRoute:
    """One classified route POLYLINE (e.g. a Vacant Pipe bore route). Brenham
    route placemarks carry NO id/length/endpoints in text -- a route is reached
    only via its endpoint STRUCTURES (which are AP-keyed), never a text key."""
    kmz_class: str
    vertices: Tuple[Tuple[float, float], ...]   # (lon, lat) in draw order
    fields: Dict[str, str] = field(default_factory=dict)

    @property
    def endpoints(self) -> Tuple[Tuple[float, float], Tuple[float, float]]:
        return (self.vertices[0], self.vertices[-1])

    def to_dict(self) -> dict:
        return {"kmz_class": self.kmz_class, "vertex_count": len(self.vertices),
                "endpoints": [list(self.vertices[0]), list(self.vertices[-1])],
                "fields": self.fields}


@dataclass(frozen=True)
class KmzModel:
    structures: Tuple[KmzStructure, ...]
    routes: Tuple[KmzRoute, ...]
    unclassified_placemarks: int
    folder_counts: Dict[str, int]


@dataclass(frozen=True)
class KmzDialect:
    """Everything a plan set configures for the KMZ reader. The reader holds no
    plan-set literals; another company supplies its own instance."""
    structure_folders: Dict[str, str]   # KMZ folder name -> structure class
    route_folders: Dict[str, str]       # KMZ folder name -> route class
    ap_token: str = r"AP\s*-?\s*(\d+)"  # AP id grammar inside name/notes
    splice_token: str = r"SPLICE LOC\s*\d+"
    # which structure class is the BORE TERMINUS that the AP/splice-loc two-field
    # join binds (M9.1). The universal join law reads this from the profile; it
    # never hardcodes a class. Empty -> this plan set declares no terminus class.
    terminal_class: str = ""


# Brenham/NEXTLINK KMZ dialect (folder taxonomy verified against the shipped
# "Brenham, TX - Phase 5" design KMZ; 1116 placemarks). Maps onto the SAME
# classes the PDF lane dialect uses (structure_position.BRENHAM_STRUCTURE_LAYERS
# + BRENHAM_CONDUIT_LAYERS) so AP/splice identity can join across sources.
BRENHAM_KMZ_DIALECT = KmzDialect(
    structure_folders={
        "Installer HH": "installer_hh",
        "Terminal Port Handhole": "terminal_port_hh",
        "Flower Pot": "flower_pot",
        "Splice HH": "splice_hh",
        "House": "house",
        "Business": "business",
        "School": "school",
    },
    route_folders={
        "Vacant Pipe": "bore_vacant_pipe",      # the bore routes (58 == bores)
        "Terminal Tail": "bore_port",
        "House Drop": "house_drop",
        "underground cable": "underground_cable",
        "Backbone": "backbone",
    },
    terminal_class="terminal_port_hh",          # the bore-terminus join class
)


# ---- reader -----------------------------------------------------------------

def _strip_ns(xml_text: str) -> str:
    """Drop xmlns decls + element/attribute namespace prefixes so a KML with
    gx:/kml: prefixes parses without registered namespaces (read-only)."""
    xml_text = re.sub(r'xmlns(:\w+)?="[^"]+"', "", xml_text)
    xml_text = re.sub(r"(</?)\w+:", r"\1", xml_text)
    xml_text = re.sub(r"\s\w+:(\w+=)", r" \1", xml_text)
    return xml_text


def _table_fields(description: Optional[str]) -> Dict[str, str]:
    """Parse the Placemark <description> HTML <table> into key/value pairs
    (Brenham encodes attributes there, not in ExtendedData). Adjacent <td>
    cells are treated as (key, value); empty keys are skipped."""
    if not description:
        return {}
    cells = re.findall(r"<td[^>]*>(.*?)</td>", description, re.S | re.I)
    cells = [re.sub(r"<[^>]+>", "", c).replace("&quot;", '"').strip()
             for c in cells]
    out: Dict[str, str] = {}
    for i in range(0, len(cells) - 1, 2):
        if cells[i] and cells[i] not in out:
            out[cells[i]] = cells[i + 1]
    return out


def _ap_ids(text: str, ap_token: str) -> Tuple[int, ...]:
    """AP ids in name+fields text. A range like 'AP115-121' yields only the
    printed anchor (115) plus any other explicit AP tokens -- never an inferred
    span (no guessing the in-between ids)."""
    return tuple(sorted({int(m) for m in re.findall(ap_token, text or "",
                                                     re.I)}))


def _coords(pm, tag: str) -> List[Tuple[float, float]]:
    el = pm.find(".//" + tag + "/coordinates")
    if el is None or not el.text:
        el = pm.find(".//coordinates")
    if el is None or not el.text:
        return []
    out = []
    for tok in el.text.split():
        parts = tok.split(",")
        if len(parts) >= 2:
            try:
                out.append((float(parts[0]), float(parts[1])))
            except ValueError:
                continue
    return out


def read_kmz(path: str, dialect: KmzDialect) -> KmzModel:
    """Parse a KMZ into the typed feature model. Pure; opens, reads doc.kml,
    closes. Unclassified placemarks are counted, never silently dropped."""
    with zipfile.ZipFile(path) as z:
        kml_name = next((n for n in z.namelist() if n.lower().endswith(".kml")),
                        "doc.kml")
        kml = z.read(kml_name).decode("utf-8", "replace")
    root = ET.fromstring(_strip_ns(kml))

    structures: List[KmzStructure] = []
    routes: List[KmzRoute] = []
    folder_counts: Dict[str, int] = {}
    seen = 0
    classified = 0
    for folder in root.iter("Folder"):
        fname = (folder.findtext("name") or "").strip()
        s_class = dialect.structure_folders.get(fname)
        r_class = dialect.route_folders.get(fname)
        pms = folder.findall("Placemark")
        if pms:
            folder_counts[fname] = folder_counts.get(fname, 0) + len(pms)
        for pm in pms:
            seen += 1
            name = (pm.findtext("name") or "").strip()
            fields = _table_fields(pm.findtext("description"))
            blob = " ".join([name, *(f"{k} {v}" for k, v in fields.items())])
            if s_class is not None and pm.find(".//Point") is not None:
                pts = _coords(pm, "Point")
                if not pts:
                    continue
                splice = None
                m = re.search(dialect.splice_token, blob, re.I)
                if m:
                    splice = m.group(0)
                structures.append(KmzStructure(
                    kmz_class=s_class, name=name,
                    ap_ids=_ap_ids(blob, dialect.ap_token), splice_loc=splice,
                    lon=pts[0][0], lat=pts[0][1], fields=fields))
                classified += 1
            elif r_class is not None and pm.find(".//LineString") is not None:
                verts = _coords(pm, "LineString")
                if len(verts) < 2:
                    continue
                routes.append(KmzRoute(kmz_class=r_class,
                                       vertices=tuple(verts), fields=fields))
                classified += 1
    return KmzModel(structures=tuple(structures), routes=tuple(routes),
                    unclassified_placemarks=seen - classified,
                    folder_counts=folder_counts)


def ap_index(model: KmzModel) -> Dict[int, Tuple[KmzStructure, ...]]:
    """AP id -> the structures carrying it (the cross-source JOIN KEY).
    Uniqueness is the caller's gate: an AP mapping to != 1 structure is not a
    safe anchor."""
    idx: Dict[int, List[KmzStructure]] = {}
    for s in model.structures:
        for ap in s.ap_ids:
            idx.setdefault(ap, []).append(s)
    return {k: tuple(v) for k, v in idx.items()}
