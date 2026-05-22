"""F7f v0 — Export Fidelity Harness for Engineering KMZ.

Runs round-trip comparison: parse source KMZ → Python emitter port → re-parse
exported KMZ → verify v0 acceptance gates. Replaces visual-only Google Earth
validation for the structural fidelity axes covered by the v0 gate set.

v0 scope (per the F7f design packet at
wiki/kmz-ingestion/f7f-export-fidelity-harness-2026-05-20.md):
- Single fixture: Brenham (backend/tests/fixtures/brenham_phase5_source_truth.kmz)
- 6 gates: G1 (placemark count), G2 (folder count), G3 (icon resolution),
  G4 (ExtendedData per-placemark parity), G7 (determinism), G8 (round-trip
  parse stability).

Deferred to v1 (see packet §1.2/§3/§9):
- Synthetic minimal + adversarial fixtures
- G6 adversarial-broken-case detection
- G11 F7d folder-hierarchy tree equality (currently approximated via raw
  folder count in G2)
- G12 F7g lineage per-placemark (F7g not shipped)
- W1–W4 warn-class gates (only minimal warnings currently emitted)

v0 technical debt — symmetric stdlib parser:
This harness uses a stdlib-only parser slice rather than calling
backend.main._build_kmz_semantic directly. Rationale:
- Local venv pandas DLL is blocked by Windows Application Control policy
  (see wiki bug B-PARSER-FIXTURE-1 environment context); importing main.py
  fails before any parser call.
- The harness must run in any pytest environment without environment
  remediation.
The parser slice covers exactly the fields F7f v0 asserts on (placemark
name, folder_path, extended_data, geometry_type, icon hrefs). It is
SYMMETRIC — used to parse both the source AND the export — so any drift
from production semantics still surfaces structural regressions between
the two sides. v1 should either:
  (a) resolve the pandas DLL block and call _build_kmz_semantic directly, or
  (b) implement F7f packet §2.3 Option B (headless Node.js emitter) for
      true production-emitter parity.

Production code touched: ZERO. backend/main.py and web/src/components/
RedlineMap.tsx are read-only references for this harness.

Usage:
    venv/Scripts/pytest.exe backend/tests/test_f7f_export_fidelity.py -v

Outputs (gitignored via backend/tests/output/.gitignore):
    backend/tests/output/f7f_fidelity_report.json
    backend/tests/output/f7f_fidelity_report.md
"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
import xml.etree.ElementTree as ET

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[2]
TESTS_DIR = Path(__file__).resolve().parent
SOURCE_KMZ = TESTS_DIR / "fixtures" / "brenham_phase5_source_truth.kmz"
OUTPUT_DIR = TESTS_DIR / "output"
JSON_REPORT = OUTPUT_DIR / "f7f_fidelity_report.json"
MD_REPORT = OUTPUT_DIR / "f7f_fidelity_report.md"

# ---------------------------------------------------------------------------
# KML constants
# ---------------------------------------------------------------------------
KML_NS = "http://www.opengis.net/kml/2.2"
GX_NS = "http://www.google.com/kml/ext/2.2"
NS = {"kml": KML_NS, "gx": GX_NS}

HARNESS_VERSION = "f7f-v3-2026-05-22"
SCHEMA_VERSION = "f7f-fidelity-report-3"
KNOWN_ANOMALIES_PATH = TESTS_DIR / "fixtures" / "f7f_known_anomalies.json"
KNOWN_ANOMALIES_SCHEMA_VERSION = "f7f-known-anomalies-1"

# F7-final cleanup (2026-05-22) — Customer-facing root wrapper that the
# production emitter (handleExportEngineeringKml in web/src/components/
# RedlineMap.tsx) now substitutes for the source <Document name>. The harness's
# Python emitter port + folder-tree normalization mirror this so the gates
# continue to compare apples-to-apples after the change.
ENG_CONTEXT_WRAPPER = "Engineering Context"

# TrueLine-generated folder names (emitted by handleExportEngineeringKml).
# Used in semantic_diff to separate source-derived folders from TrueLine-
# injected folders in the export tree. The v0 Brenham fixture has no
# per-session photo/station/redline data, so the export's TL-folder count is 0
# — but the harness shape is forward-compatible for v2+ fixtures that DO
# include TL data. F7-final cleanup renamed "As-Built Redlines" → "Redlines".
TL_FOLDER_NAMES = frozenset({
    "Photos",
    "Stations",
    "Selected Field Submission",
    "Redlines",
})


# ===========================================================================
# Parser slice (stdlib only).
# Mirrors the subset of backend/main.py:_build_kmz_semantic that F7f v0
# asserts on. See module docstring for the technical-debt rationale.
# ===========================================================================

def _kml_bytes_from_kmz(file_bytes: bytes) -> bytes:
    with zipfile.ZipFile(io.BytesIO(file_bytes)) as z:
        doc = next((n for n in z.namelist() if n.endswith("doc.kml")), None)
        if doc is None:
            raise ValueError("doc.kml not found in KMZ archive")
        return z.read(doc)


def _kmz_archive_entries(file_bytes: bytes) -> Set[str]:
    with zipfile.ZipFile(io.BytesIO(file_bytes)) as z:
        return set(z.namelist())


def _folder_path_of(elem, parent_map) -> List[str]:
    """Return ancestor Folder/Document names (Document → ... → leaf order).
    Mirrors backend/main.py:_folder_path semantics."""
    names: List[str] = []
    current = elem
    while id(current) in parent_map:
        current = parent_map[id(current)]
        tag = current.tag.split("}")[-1]
        if tag in {"Folder", "Document"}:
            name = (current.findtext("kml:name", default="", namespaces=NS) or "").strip()
            if name:
                names.append(name)
    names.reverse()
    return names


def _extended_data_of(placemark) -> Dict[str, str]:
    ed: Dict[str, str] = {}
    ed_elem = placemark.find("kml:ExtendedData", NS)
    if ed_elem is None:
        return ed
    for data in ed_elem.findall("kml:Data", NS):
        name = data.get("name") or ""
        value = (data.findtext("kml:value", default="", namespaces=NS) or "").strip()
        if name:
            ed[name] = value
    return ed


def _geometry_type_of(placemark) -> str:
    for tag in ("Point", "LineString", "Polygon", "LinearRing", "MultiGeometry"):
        if placemark.find(f"kml:{tag}", NS) is not None:
            return tag
    return "Unknown"


def _icon_hrefs_in_kml(root) -> Set[str]:
    """Every <href> in the KML tree (covers <IconStyle><Icon><href>...)."""
    hrefs: Set[str] = set()
    for href in root.iter(f"{{{KML_NS}}}href"):
        text = (href.text or "").strip()
        if text:
            hrefs.add(text)
    return hrefs


def parse_kmz(file_bytes: bytes) -> Dict[str, Any]:
    """Parse a KMZ into the F7f semantic slice (v2 extended).

    v1 additions over v0:
      - per-placemark `style_url` extraction
      - `folder_tree` — (parent_path, name, child_count, pm_count) tuples
      - `document_name` — used for Document-wrapper normalization
      - `geometry_counts` — dict keyed by geometry type
      - `style_urls` — set of referenced style URLs
      - `extended_data_keys` — union of all ExtendedData keys

    v2 additions over v1:
      - per-placemark `icon_href` resolved via styleUrl -> Style/StyleMap chain
      - `style_id_to_icon_href` map (diagnostic; populated once per parse)
    """
    kml_bytes = _kml_bytes_from_kmz(file_bytes)
    root = ET.fromstring(kml_bytes)
    parent_map = {id(c): p for p in root.iter() for c in p}

    style_id_to_icon_href = _parse_style_icon_hrefs(root)

    placemarks: List[Dict[str, Any]] = []
    for idx, pm in enumerate(root.iter(f"{{{KML_NS}}}Placemark")):
        name = (pm.findtext("kml:name", default="", namespaces=NS) or "").strip()
        placemarks.append({
            "feature_id": f"semantic_{idx}",
            "placemark_name": name or f"Unnamed_{idx}",
            "folder_path": _folder_path_of(pm, parent_map),
            "geometry_type": _geometry_type_of(pm),
            "extended_data": _extended_data_of(pm),
            "style_url": _style_url_of(pm),
            "icon_href": _resolve_icon_href(pm, style_id_to_icon_href),
        })

    folders = list(root.iter(f"{{{KML_NS}}}Folder"))
    folder_names = [(f.findtext("kml:name", namespaces=NS) or "").strip() for f in folders]

    return {
        "placemarks": placemarks,
        "placemark_count": len(placemarks),
        "folders": folder_names,
        "folder_count": len(folder_names),
        "folder_tree": _walk_folder_tree(root),
        "document_name": _document_name_of(root),
        "geometry_counts": _count_geometries(placemarks),
        "style_urls": _collect_style_urls(placemarks),
        "extended_data_keys": _collect_ed_keys(placemarks),
        "archive_entries": _kmz_archive_entries(file_bytes),
        "referenced_hrefs": _icon_hrefs_in_kml(root),
        "style_id_to_icon_href": style_id_to_icon_href,
    }


# ---------------------------------------------------------------------------
# v1 parser-slice extensions
# ---------------------------------------------------------------------------

def _style_url_of(placemark) -> str:
    return (placemark.findtext("kml:styleUrl", default="", namespaces=NS) or "").strip()


def _document_name_of(root) -> str:
    """The name of the topmost <Document> element (empty string if none).
    Used by the Document-wrapper normalization in G2 / G11 / semantic_diff."""
    for doc in root.iter(f"{{{KML_NS}}}Document"):
        return (doc.findtext("kml:name", default="", namespaces=NS) or "").strip()
    return ""


def _walk_folder_tree(root) -> List[Any]:
    """Walk all <Folder> elements depth-first. Returns a list of tuples:
        (parent_path: Tuple[str, ...], folder_name: str,
         direct_child_folder_count: int, direct_placemark_count: int)

    parent_path is the tuple of ancestor <Folder> names ONLY (excluding
    <Document>). Used by G11 (tree equality) and semantic_diff."""
    result: List[Any] = []

    def visit(elem, parent_folder_names):
        for child in list(elem):
            tag = child.tag.split("}")[-1]
            if tag == "Folder":
                name = (child.findtext("kml:name", default="", namespaces=NS) or "").strip()
                direct_child_folders = sum(
                    1 for c in child if c.tag.split("}")[-1] == "Folder"
                )
                direct_placemarks = sum(
                    1 for c in child if c.tag.split("}")[-1] == "Placemark"
                )
                result.append((parent_folder_names, name, direct_child_folders, direct_placemarks))
                visit(child, parent_folder_names + (name,))
            elif tag == "Document":
                # Document is a container but not a Folder — recurse without
                # adding to path.
                visit(child, parent_folder_names)
            # Other elements (Style, Placemark, name, etc.) — no recursion needed.

    visit(root, ())
    return result


def _normalize_folder_path(fp: List[str]) -> List[str]:
    """Mirror of the production emitter's normalizeFolderPath helper.

    The production emitter (handleExportEngineeringKml) replaces the first
    element of every source-derived folder_path array (the source <Document>
    name) with ENG_CONTEXT_WRAPPER before tree insertion. The harness's
    Python emitter port applies the same substitution so the emitted folder
    tree matches production's shape, which keeps G2 + G11 + semantic_diff
    apples-to-apples after the F7-final cleanup."""
    path = fp or []
    if not path:
        return path
    return [ENG_CONTEXT_WRAPPER, *path[1:]]


def _normalize_export_folder_tree(folder_tree: List[Any]) -> List[Any]:
    """Peel the ENG_CONTEXT_WRAPPER ('Engineering Context') Folder wrapper
    from an export's folder tree.

    F7-final cleanup (2026-05-22): the production emitter now wraps every
    source-derived folder under a stable <Folder name="Engineering Context">
    sibling at the top of the export tree, replacing the prior source-
    Document-name wrapper. For tree-structure comparison against a source
    that has no such wrapper, we peel here.

    Returns folders with:
      - The wrapper Folder entry removed
      - Every descendant's parent_path stripped of its leading wrapper name

    No-op when no wrapper is detected (defensive — e.g., synthetic fixtures
    that don't produce any source-derived folders)."""
    wrapper = ENG_CONTEXT_WRAPPER
    has_wrapper = any(
        pp == () and name == wrapper for (pp, name, _, _) in folder_tree
    )
    if not has_wrapper:
        return list(folder_tree)
    result: List[Any] = []
    for parent_path, name, child_count, pm_count in folder_tree:
        if parent_path == () and name == wrapper:
            continue  # peel the wrapper itself
        if parent_path and parent_path[0] == wrapper:
            new_parent_path = parent_path[1:]
        else:
            new_parent_path = parent_path
        result.append((new_parent_path, name, child_count, pm_count))
    return result


def _count_geometries(placemarks: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for pm in placemarks:
        gt = pm.get("geometry_type", "Unknown")
        counts[gt] = counts.get(gt, 0) + 1
    return counts


def _collect_style_urls(placemarks: List[Dict[str, Any]]) -> Set[str]:
    return {pm["style_url"] for pm in placemarks if pm.get("style_url")}


def _collect_ed_keys(placemarks: List[Dict[str, Any]]) -> Set[str]:
    keys: Set[str] = set()
    for pm in placemarks:
        keys.update((pm.get("extended_data") or {}).keys())
    return keys


def _load_known_anomalies() -> Dict[str, Any]:
    """Load the F7f known-anomalies registry. Validates schema_version and
    requires a non-empty `rationale` field per fixture entry."""
    if not KNOWN_ANOMALIES_PATH.exists():
        raise FileNotFoundError(
            f"F7f known-anomalies file missing: {KNOWN_ANOMALIES_PATH}. "
            f"v1 requires this file to exist."
        )
    data = json.loads(KNOWN_ANOMALIES_PATH.read_text(encoding="utf-8"))
    if data.get("schema_version") != KNOWN_ANOMALIES_SCHEMA_VERSION:
        raise ValueError(
            f"F7f known-anomalies schema mismatch: expected "
            f"{KNOWN_ANOMALIES_SCHEMA_VERSION!r}, got "
            f"{data.get('schema_version')!r}"
        )
    for fixture_name, entry in data.get("fixtures", {}).items():
        if not (entry.get("rationale") or "").strip():
            raise ValueError(
                f"F7f known-anomalies fixture {fixture_name!r} missing required "
                f"non-empty 'rationale' field. See "
                f"backend/tests/fixtures/f7f_known_anomalies.md for the policy."
            )
    return data


# ---------------------------------------------------------------------------
# v2 — Style/icon-href resolution
# ---------------------------------------------------------------------------

def _parse_style_icon_hrefs(root) -> Dict[str, str]:
    """Build a map of `style_id -> icon_href` for every <Style> declaring an
    <IconStyle><Icon><href>. Also resolves <StyleMap> entries one level deep
    via their 'normal' Pair styleUrl. Used by `_resolve_icon_href` to derive
    per-placemark icon hrefs.

    Mirrors the slice of backend/main.py:_kmz_semantic_parse_styles that F7f
    v2 needs for icon-href preservation gating. Same symmetric-parser-slice
    rationale as v0/v1 (stdlib-only)."""
    result: Dict[str, str] = {}
    for style in root.iter(f"{{{KML_NS}}}Style"):
        style_id = (style.get("id") or "").strip()
        if not style_id:
            continue
        icon_elem = style.find("kml:IconStyle/kml:Icon", NS)
        if icon_elem is None:
            continue
        href_text = (icon_elem.findtext("kml:href", default="", namespaces=NS) or "").strip()
        if href_text:
            result[style_id] = href_text

    # StyleMap → normal style → IconStyle chain (one level deep).
    for sm in root.iter(f"{{{KML_NS}}}StyleMap"):
        sm_id = (sm.get("id") or "").strip()
        if not sm_id:
            continue
        for pair in sm.findall("kml:Pair", NS):
            key = (pair.findtext("kml:key", default="", namespaces=NS) or "").strip()
            if key != "normal":
                continue
            ref = (pair.findtext("kml:styleUrl", default="", namespaces=NS) or "").strip()
            if ref.startswith("#"):
                ref = ref[1:]
            if ref in result:
                result[sm_id] = result[ref]
            break

    return result


def _resolve_icon_href(placemark, style_id_to_icon_href: Dict[str, str]) -> str:
    """Return the icon_href for a placemark via its <styleUrl> → Style chain.
    Empty string if the placemark has no styleUrl, the styleUrl points
    outside the document, or the referenced Style has no IconStyle."""
    style_url = _style_url_of(placemark)
    if not style_url.startswith("#"):
        return ""
    return style_id_to_icon_href.get(style_url[1:], "")


# ===========================================================================
# Python emitter port. Mirrors handleExportEngineeringKml's source-side
# emission for v0. Preserves the load-bearing prior ships:
#   F7d — nested folder hierarchy
#   F7e — engPointStyle LabelStyle scale=0
#   R7g — engRedlineStyle width=8
#   R7h — xmlns:gx (root element)
#   R7j — <Document><open>1</open> + per-folder <visibility>/<open>
#
# v0 simplification: TL folders (Photos, Stations, Selected Field Submission,
# As-Built Redlines) are NOT emitted because the v0 fixture has no
# per-session photo/station/redline data. v0 tests source-side fidelity;
# TL-folder lifecycle is covered by visual + v1 multi-fixture harness.
# ===========================================================================

class FolderNode:
    __slots__ = ("name", "placemarks", "children")

    def __init__(self, name: str) -> None:
        self.name = name
        self.placemarks: List[str] = []
        # dict preserves insertion order in Python 3.7+ (matches TS Map)
        self.children: Dict[str, "FolderNode"] = {}


def _get_folder_bucket(tree: FolderNode, fp: List[str]) -> List[str]:
    path = fp or []
    if not path:
        bucket = tree.children.get("Uncategorized")
        if bucket is None:
            bucket = FolderNode("Uncategorized")
            tree.children["Uncategorized"] = bucket
        return bucket.placemarks
    cur = tree
    for seg in path:
        nxt = cur.children.get(seg)
        if nxt is None:
            nxt = FolderNode(seg)
            cur.children[seg] = nxt
        cur = nxt
    return cur.placemarks


def _folder_is_empty(node: FolderNode) -> bool:
    if node.placemarks:
        return False
    for child in node.children.values():
        if not _folder_is_empty(child):
            return False
    return True


def _emit_folder(node: FolderNode, indent: str, visibility: int = 0, open_: int = 0) -> str:
    child_blocks: List[str] = []
    for child in node.children.values():
        if _folder_is_empty(child):
            continue
        child_blocks.append(_emit_folder(child, indent + "  "))
    inner_parts = child_blocks + node.placemarks
    inner = "\n".join(inner_parts) if inner_parts else ""
    return (
        f"{indent}<Folder>\n"
        f"{indent}  <name>{escape(node.name, quote=False)}</name>\n"
        f"{indent}  <visibility>{visibility}</visibility>\n"
        f"{indent}  <open>{open_}</open>\n"
        f"{inner}\n"
        f"{indent}</Folder>"
    )


def _emit_placemark(pm: Dict[str, Any], style_url_override: Optional[str] = None) -> str:
    name = escape(pm["placemark_name"], quote=False)
    ed = pm.get("extended_data", {}) or {}
    if ed:
        rows = "".join(
            "          <Data name=\"" + escape(k, quote=True) + "\"><value>"
            + escape(v, quote=False) + "</value></Data>\n"
            for k, v in ed.items()
        )
        ed_xml = f"        <ExtendedData>\n{rows}        </ExtendedData>\n"
    else:
        ed_xml = ""
    if style_url_override:
        style_xml = f"        <styleUrl>{escape(style_url_override, quote=False)}</styleUrl>\n"
    else:
        style_xml = ""
    geom = pm.get("geometry_type", "Point")
    if geom == "LineString":
        geom_xml = "        <LineString><tessellate>1</tessellate><coordinates>0,0 1,1</coordinates></LineString>\n"
    elif geom == "Polygon":
        geom_xml = (
            "        <Polygon><outerBoundaryIs><LinearRing>"
            "<coordinates>0,0 1,0 1,1 0,0</coordinates>"
            "</LinearRing></outerBoundaryIs></Polygon>\n"
        )
    else:
        geom_xml = "        <Point><coordinates>0,0</coordinates></Point>\n"
    return (
        "      <Placemark>\n"
        f"        <name>{name}</name>\n"
        f"{style_xml}"
        f"{ed_xml}"
        f"{geom_xml}"
        "      </Placemark>"
    )


def emit_engineering_kml(parsed_source: Dict[str, Any]) -> Tuple[str, Set[str]]:
    """Emit a minimal Engineering-KMZ KML mirroring handleExportEngineeringKml
    for the source-side fidelity surfaces v0-v2 assert on.

    v2 addition (mirrors RedlineMap.tsx:2781-2792):
      For every source placemark whose geometry is a Point AND has a resolved
      icon_href, emit a per-feature <Style id="pt_{feature_id}_{idx}"> with
      an <IconStyle><Icon><href>{icon_href}</href></Icon></IconStyle> block
      and a <LabelStyle><scale>0</scale></LabelStyle> (F7e). The placemark
      then uses an explicit <styleUrl>#pt_...</styleUrl> override pointing
      at the per-feature style.

      Other geometry types still use the generic eng* document-level styles
      (line/polygon per-feature styling deferred to v3).

    Returns (kml_str, referenced_hrefs) so package_as_kmz can embed source
    asset bytes for each referenced relative href."""
    tree = FolderNode("")
    feature_styles: List[str] = []
    referenced_hrefs: Set[str] = set()
    pt_style_idx = 0

    for pm in parsed_source["placemarks"]:
        style_url_override: Optional[str] = None
        icon_href = (pm.get("icon_href") or "").strip()
        if pm.get("geometry_type") == "Point" and icon_href:
            pt_style_id = f"pt_{pm['feature_id']}_{pt_style_idx}"
            pt_style_idx += 1
            feature_styles.append(
                f'    <Style id="{pt_style_id}">\n'
                f'      <IconStyle><scale>0.8</scale><Icon><href>{escape(icon_href, quote=False)}</href></Icon></IconStyle>\n'
                f'      <LabelStyle><scale>0</scale></LabelStyle>\n'
                f'    </Style>'
            )
            style_url_override = f"#{pt_style_id}"
            referenced_hrefs.add(icon_href)

        bucket = _get_folder_bucket(tree, _normalize_folder_path(pm["folder_path"]))
        bucket.append(_emit_placemark(pm, style_url_override))

    eng_folder_blocks: List[str] = []
    for child in tree.children.values():
        if _folder_is_empty(child):
            continue
        eng_folder_blocks.append(_emit_folder(child, "    ", 0, 0))
    eng_folder_str = "\n".join(eng_folder_blocks)

    feature_styles_xml = "\n".join(feature_styles) + "\n" if feature_styles else ""

    kml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<kml xmlns="http://www.opengis.net/kml/2.2" '
        'xmlns:gx="http://www.google.com/kml/ext/2.2">\n'
        '  <Document>\n'
        '    <open>1</open>\n'
        '    <name>Engineering KMZ Context + Redlines</name>\n'
        '    <Style id="engLineStyle">\n'
        '      <LineStyle><color>ff94a3b8</color><width>2</width></LineStyle>\n'
        '    </Style>\n'
        '    <Style id="engPointStyle">\n'
        '      <IconStyle><scale>0.8</scale></IconStyle>\n'
        '      <LabelStyle><scale>0</scale></LabelStyle>\n'
        '    </Style>\n'
        '    <Style id="engPolyStyle">\n'
        '      <LineStyle><color>8894a3b8</color><width>1</width></LineStyle>\n'
        '      <PolyStyle><color>1a94a3b8</color><fill>1</fill><outline>1</outline></PolyStyle>\n'
        '    </Style>\n'
        '    <Style id="engRedlineStyle">\n'
        '      <LineStyle><color>ff0000ff</color><width>8</width></LineStyle>\n'
        '    </Style>\n'
        f'{feature_styles_xml}'
        f'{eng_folder_str}\n'
        '  </Document>\n'
        '</kml>\n'
    )
    return (kml, referenced_hrefs)


def package_as_kmz(
    kml_str: str,
    source_archive_bytes: Optional[bytes] = None,
    referenced_hrefs: Optional[Set[str]] = None,
) -> bytes:
    """Wrap KML in a deterministic KMZ ZIP. Fixed timestamp on every entry
    (doc.kml + all embedded assets) keeps byte-output stable across runs
    (required for G7).

    v2 addition (mirrors RedlineMap.tsx:3154-3162): if source_archive_bytes
    and referenced_hrefs are both provided, the packager opens the source
    archive and copies bytes for every referenced relative href into the
    export ZIP at the same path. Mirrors production's kmzAssetsRef + fflate
    behavior. Hrefs that point to absolute URLs (http://, https://, data:,
    file:) are skipped (they need no archive entry). Hrefs that are not
    present in the source archive are silently skipped (those are the
    upstream-source-authoring anomalies documented in f7f_known_anomalies.json)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zi = zipfile.ZipInfo("doc.kml", date_time=(2026, 1, 1, 0, 0, 0))
        zi.compress_type = zipfile.ZIP_DEFLATED
        zf.writestr(zi, kml_str.encode("utf-8"))

        if source_archive_bytes is not None and referenced_hrefs:
            with zipfile.ZipFile(io.BytesIO(source_archive_bytes)) as src_zip:
                src_entries = set(src_zip.namelist())
                # Sort for deterministic emission order.
                for href in sorted(referenced_hrefs):
                    if href.startswith(("http://", "https://", "data:", "file:")):
                        continue
                    if href not in src_entries:
                        continue  # upstream anomaly — source itself missing this asset
                    asset_bytes = src_zip.read(href)
                    asset_zi = zipfile.ZipInfo(href, date_time=(2026, 1, 1, 0, 0, 0))
                    asset_zi.compress_type = zipfile.ZIP_DEFLATED
                    zf.writestr(asset_zi, asset_bytes)
    return buf.getvalue()


# ===========================================================================
# Gate runners
# ===========================================================================

def _gate_g1(source: Dict[str, Any], export: Dict[str, Any]):
    src, exp = source["placemark_count"], export["placemark_count"]
    if src == exp:
        return ("PASS", f"source={src} export={exp}")
    return ("FAIL", f"source={src} != export={exp}")


def _gate_g2(source: Dict[str, Any], export: Dict[str, Any]):
    """Folder count parity after ENG_CONTEXT_WRAPPER normalization.

    F7-final cleanup (2026-05-22): the TrueLine engineering KMZ emitter now
    wraps source-derived folders under a stable <Folder name="Engineering
    Context"> top-level sibling (replacing the prior source-Document-name
    wrapper). Raw export folder count is therefore source_count + 1 by design.
    G2 normalizes the export side by peeling the wrapper before comparison."""
    src_count = source["folder_count"]
    normalized_export_tree = _normalize_export_folder_tree(export["folder_tree"])
    exp_count_normalized = len(normalized_export_tree)
    exp_count_raw = export["folder_count"]
    if src_count == exp_count_normalized:
        return (
            "PASS",
            f"source={src_count} export_normalized={exp_count_normalized} "
            f"(export_raw={exp_count_raw}, {ENG_CONTEXT_WRAPPER!r} wrapper peeled)"
        )
    return (
        "FAIL",
        f"source={src_count} != export_normalized={exp_count_normalized} "
        f"(export_raw={exp_count_raw}, {ENG_CONTEXT_WRAPPER!r} wrapper peeled)"
    )


def _unresolvable_relative_hrefs(parsed: Dict[str, Any]) -> Set[str]:
    refs = parsed["referenced_hrefs"]
    entries = parsed["archive_entries"]
    bad: Set[str] = set()
    for h in refs:
        if h.startswith(("http://", "https://", "data:")):
            continue
        if h not in entries:
            bad.add(h)
    return bad


def _gate_g3_source(
    source: Dict[str, Any],
    fixture_name: str,
    known_anomalies: Dict[str, Any],
):
    """Source-side icon-href resolution gate (delta-based against known anomalies).

    Behavior:
      PASS — all current unresolvable hrefs are in the known-anomalies set,
             OR there are zero unresolvable hrefs at all.
      FAIL — NEW unresolvable href(s) appeared beyond the documented set
             (catches source-quality regressions or new fixture drift).
      WARN — known anomalies have been fixed at the source; the
             f7f_known_anomalies.json file should be updated to remove the
             resolved entries so the suppression doesn't go silent."""
    current = _unresolvable_relative_hrefs(source)
    fixture_entry = (known_anomalies.get("fixtures", {}).get(fixture_name) or {})
    known = set(fixture_entry.get("source_unresolvable_hrefs", []))
    new_unresolved = current - known
    gone_unresolved = known - current
    if new_unresolved:
        return (
            "FAIL",
            f"{len(new_unresolved)} NEW source-side unresolved href(s) beyond "
            f"the documented known-anomalies set: {sorted(new_unresolved)[:3]}"
            f"{'...' if len(new_unresolved) > 3 else ''}. "
            f"Either fix the source or update "
            f"backend/tests/fixtures/f7f_known_anomalies.json."
        )
    if gone_unresolved:
        return (
            "WARN",
            f"{len(gone_unresolved)} previously-known anomalies no longer "
            f"present in source: {sorted(gone_unresolved)}. Update "
            f"backend/tests/fixtures/f7f_known_anomalies.json to remove "
            f"these entries (anomaly fixed at source)."
        )
    if not current:
        return ("PASS", "0 unresolvable hrefs in source")
    return (
        "PASS",
        f"{len(current)} source-side unresolved href(s); all match the "
        f"documented known-anomalies set for {fixture_name!r}"
    )


def _gate_g3_export(source: Dict[str, Any], export: Dict[str, Any]):
    """Export-side icon-href resolution gate (v2 delta-based against source).

    Production (and the v2 Python port) preserves source icon_href references
    in per-feature styles AND embeds source asset bytes in the export KMZ
    archive. The upstream-source authoring anomalies documented in
    f7f_known_anomalies.json (5 Brenham hrefs whose source archive entries
    don't exist) therefore propagate to the export at the same rate — that
    is correct production behavior: the export pipeline cannot synthesize
    icons the source itself omits.

    Gate semantics:
      PASS — export's unresolvable set is a subset of source's unresolvable
             set (propagation; not regression).
      FAIL — NEW unresolvable href(s) appear in export beyond source's set
             (catches port regressions that break asset embedding, or
             production-emitter regressions if v3+ swaps to production
             parser path)."""
    src_bad = _unresolvable_relative_hrefs(source)
    exp_bad = _unresolvable_relative_hrefs(export)
    new_in_export = exp_bad - src_bad
    if new_in_export:
        return (
            "FAIL",
            f"{len(new_in_export)} NEW unresolvable href(s) in export beyond "
            f"the source's unresolvable set (port or asset-embedding regression): "
            f"{sorted(new_in_export)[:3]}"
        )
    if not exp_bad:
        return ("PASS", "0 unresolvable relative hrefs in export")
    return (
        "PASS",
        f"{len(exp_bad)} export-side unresolved href(s); all also unresolved "
        f"in source (faithful propagation, not regression)"
    )


def _gate_g4(source: Dict[str, Any], export: Dict[str, Any]):
    # Match by feature_id (semantic_N enumeration order) — preserved by the
    # emitter port since it iterates parsed_source["placemarks"] in order.
    src_ed = {pm["feature_id"]: pm["extended_data"] for pm in source["placemarks"]}
    exp_ed = {pm["feature_id"]: pm["extended_data"] for pm in export["placemarks"]}
    mismatches = []
    for fid, sed in src_ed.items():
        eed = exp_ed.get(fid, {})
        if sed != eed:
            mismatches.append({
                "feature_id": fid,
                "source_keys": sorted(sed.keys()),
                "export_keys": sorted(eed.keys()),
                "missing_in_export": sorted(set(sed.keys()) - set(eed.keys())),
                "extra_in_export": sorted(set(eed.keys()) - set(sed.keys())),
            })
    if not mismatches:
        return ("PASS", f"all {len(src_ed)} placemarks have matching ExtendedData")
    return (
        "FAIL",
        f"{len(mismatches)} ExtendedData mismatch(es); first: {mismatches[0]}"
    )


def _gate_g7(export_bytes_1: bytes, export_bytes_2: bytes):
    if export_bytes_1 == export_bytes_2:
        return ("PASS", f"two consecutive exports byte-identical ({len(export_bytes_1)} bytes)")
    return (
        "FAIL",
        f"runs differ; len1={len(export_bytes_1)} len2={len(export_bytes_2)}"
    )


def _gate_g8(export: Dict[str, Any], re_export: Dict[str, Any]):
    e, r = export["placemark_count"], re_export["placemark_count"]
    if e == r:
        return ("PASS", f"round-trip placemark count stable ({e})")
    return ("FAIL", f"round-trip placemark count drift: export={e} re-export={r}")


def _gate_g11(source: Dict[str, Any], export: Dict[str, Any]):
    """Folder hierarchy tree equality after ENG_CONTEXT_WRAPPER normalization.

    Explicit tree-tuple equality: build the (parent_path, folder_name) tuple
    set from source and from normalized-export trees; assert set equality.
    Catches F7d folder-structure regressions that raw count parity (G2)
    alone would miss."""
    src_tree = source["folder_tree"]
    exp_tree_normalized = _normalize_export_folder_tree(export["folder_tree"])
    src_tuples = {(pp, name) for (pp, name, _, _) in src_tree}
    exp_tuples = {(pp, name) for (pp, name, _, _) in exp_tree_normalized}
    if src_tuples == exp_tuples:
        return (
            "PASS",
            f"{len(src_tuples)} folder tuples match after {ENG_CONTEXT_WRAPPER!r} "
            f"wrapper normalization (parent_path, name) set equality holds"
        )
    only_src = src_tuples - exp_tuples
    only_exp = exp_tuples - src_tuples
    return (
        "FAIL",
        f"tree mismatch: only_in_source={sorted(only_src)[:3]} "
        f"only_in_export={sorted(only_exp)[:3]}"
    )


# ===========================================================================
# Semantic diff builder (v1 informational regression backbone)
# ===========================================================================

def _build_semantic_diff(
    source: Dict[str, Any], export: Dict[str, Any]
) -> Dict[str, Any]:
    """Build the F7f v1 informational semantic-diff summary.

    Compares source and export along six axes (folder tree, placemark names,
    geometry counts, style/icon references, ExtendedData keys, TL-vs-source
    folder split). Not gate-class; intended as the regression backbone — future
    runs can diff JSON reports for any changed axis even when gate verdicts
    stay PASS."""
    exp_tree_normalized = _normalize_export_folder_tree(export["folder_tree"])

    src_tuples = {(pp, name) for (pp, name, _, _) in source["folder_tree"]}
    exp_tuples = {(pp, name) for (pp, name, _, _) in exp_tree_normalized}

    src_names = [pm["placemark_name"] for pm in source["placemarks"]]
    exp_names = [pm["placemark_name"] for pm in export["placemarks"]]
    src_names_set = set(src_names)
    exp_names_set = set(exp_names)

    def _sample(items, k=5):
        return sorted(items)[:k] if items else []

    # TL-vs-source folder split — applied to top-level folders in the
    # NORMALIZED export tree. TL folders are emitted as top-level siblings
    # under <Document> by the engineering KMZ emitter.
    top_level_export_folder_names = sorted({
        name for (pp, name, _, _) in exp_tree_normalized if pp == ()
    })
    tl_folders = sorted(n for n in top_level_export_folder_names if n in TL_FOLDER_NAMES)
    source_derived_folders = sorted(
        n for n in top_level_export_folder_names if n not in TL_FOLDER_NAMES
    )

    return {
        "folder_tree": {
            "source_folder_count": len(src_tuples),
            "export_folder_count_normalized": len(exp_tuples),
            "equivalent": src_tuples == exp_tuples,
            "source_only_folders": [list(t) for t in sorted(src_tuples - exp_tuples)][:10],
            "export_only_folders": [list(t) for t in sorted(exp_tuples - src_tuples)][:10],
        },
        "placemark_names": {
            "source_count": len(src_names),
            "export_count": len(exp_names),
            "source_set_size": len(src_names_set),
            "export_set_size": len(exp_names_set),
            "equivalent_as_set": src_names_set == exp_names_set,
            "source_only_sample": _sample(src_names_set - exp_names_set),
            "export_only_sample": _sample(exp_names_set - src_names_set),
        },
        "geometry_counts": {
            "source": dict(sorted(source["geometry_counts"].items())),
            "export": dict(sorted(export["geometry_counts"].items())),
            "equivalent": source["geometry_counts"] == export["geometry_counts"],
        },
        "style_url_refs": {
            "source_count": len(source["style_urls"]),
            "export_count": len(export["style_urls"]),
            "source": sorted(source["style_urls"]),
            "export": sorted(export["style_urls"]),
            "equivalent_as_set": source["style_urls"] == export["style_urls"],
            "note": (
                "By design, set equality is NOT expected: source uses shared "
                "styleUrl strings (e.g., 14 shared IDs referenced by many "
                "placemarks each), production export uses per-feature unique "
                "style IDs (one per Point with icon_href). The load-bearing "
                "fidelity axis is icon_href_refs.equivalent_as_set below."
            ),
        },
        "icon_href_refs": {
            "source_count": len(source["referenced_hrefs"]),
            "export_count": len(export["referenced_hrefs"]),
            "source": sorted(source["referenced_hrefs"]),
            "export": sorted(export["referenced_hrefs"]),
            "equivalent_as_set": source["referenced_hrefs"] == export["referenced_hrefs"],
            "source_only_hrefs": sorted(source["referenced_hrefs"] - export["referenced_hrefs"]),
            "export_only_hrefs": sorted(export["referenced_hrefs"] - source["referenced_hrefs"]),
            "note": (
                "v2 Python emitter port preserves icon hrefs via per-feature "
                "<Style><IconStyle><Icon><href> emission for every source Point "
                "with a resolved icon_href, and embeds source asset bytes in "
                "the export KMZ archive (mirrors RedlineMap.tsx:2781-2792 + "
                "3154-3162). source_only_hrefs (if non-empty) typically "
                "indicates source styles declared but never referenced by any "
                "placemark — these are NOT regressions."
            ),
        },
        "extended_data_keys": {
            "source_count": len(source["extended_data_keys"]),
            "export_count": len(export["extended_data_keys"]),
            "source": sorted(source["extended_data_keys"]),
            "export": sorted(export["extended_data_keys"]),
            "equivalent_as_set": source["extended_data_keys"] == export["extended_data_keys"],
        },
        "tl_vs_source_folder_split": {
            "top_level_export_folder_names": top_level_export_folder_names,
            "source_derived_folder_count": len(source_derived_folders),
            "source_derived_folders": source_derived_folders,
            "tl_generated_folder_count": len(tl_folders),
            "tl_generated_folders": tl_folders,
            "tl_folder_vocabulary": sorted(TL_FOLDER_NAMES),
        },
    }


def run_harness() -> Dict[str, Any]:
    fixture_name = SOURCE_KMZ.name
    known_anomalies = _load_known_anomalies()

    source_bytes = SOURCE_KMZ.read_bytes()
    parsed_source = parse_kmz(source_bytes)

    kml_1, refs_1 = emit_engineering_kml(parsed_source)
    export_bytes_1 = package_as_kmz(kml_1, source_bytes, refs_1)
    parsed_export = parse_kmz(export_bytes_1)

    # G7 — run a second time on the same input
    kml_2, refs_2 = emit_engineering_kml(parsed_source)
    export_bytes_2 = package_as_kmz(kml_2, source_bytes, refs_2)

    # G8 — re-emit from the parsed export, package (asset bytes come from
    # export_bytes_1 which now contains the embedded source assets), re-parse.
    kml_3, refs_3 = emit_engineering_kml(parsed_export)
    export_bytes_3 = package_as_kmz(kml_3, export_bytes_1, refs_3)
    parsed_re_export = parse_kmz(export_bytes_3)

    gates = {
        "G1_placemark_count_parity": _gate_g1(parsed_source, parsed_export),
        "G2_folder_count_parity": _gate_g2(parsed_source, parsed_export),
        "G3_icon_resolution_source": _gate_g3_source(parsed_source, fixture_name, known_anomalies),
        "G3_icon_resolution_export": _gate_g3_export(parsed_source, parsed_export),
        "G4_extended_data_parity": _gate_g4(parsed_source, parsed_export),
        "G7_determinism": _gate_g7(export_bytes_1, export_bytes_2),
        "G8_round_trip_parse_stability": _gate_g8(parsed_export, parsed_re_export),
        "G11_folder_hierarchy_tree_equality": _gate_g11(parsed_source, parsed_export),
    }

    failures = [k for k, (s, _) in gates.items() if s == "FAIL"]
    warnings = [k for k, (s, _) in gates.items() if s == "WARN"]
    verdict = "fail" if failures else ("warn_only" if warnings else "pass")

    semantic_diff = _build_semantic_diff(parsed_source, parsed_export)

    return {
        "schema_version": SCHEMA_VERSION,
        "harness_version": HARNESS_VERSION,
        "ts_iso": datetime.now(timezone.utc).isoformat(),
        "fixture": {
            "name": "brenham",
            "source_path": str(SOURCE_KMZ.relative_to(PROJECT_ROOT)).replace("\\", "/"),
            "document_name": parsed_source["document_name"],
            "source_placemark_count": parsed_source["placemark_count"],
            "source_folder_count": parsed_source["folder_count"],
            "source_referenced_hrefs": len(parsed_source["referenced_hrefs"]),
            "source_archive_entries": len(parsed_source["archive_entries"]),
            "export_placemark_count": parsed_export["placemark_count"],
            "export_folder_count": parsed_export["folder_count"],
            "export_referenced_hrefs": len(parsed_export["referenced_hrefs"]),
            "export_archive_entries": len(parsed_export["archive_entries"]),
            "export_bytes": len(export_bytes_1),
        },
        "known_anomalies_schema": known_anomalies.get("schema_version"),
        "gates": {k: {"status": s, "detail": d} for k, (s, d) in gates.items()},
        "semantic_diff": semantic_diff,
        "verdict": verdict,
        "failures": failures,
        "warnings": warnings,
    }


def write_reports(report: Dict[str, Any]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    JSON_REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")

    lines: List[str] = [
        "# F7f Export Fidelity Harness Report",
        "",
        f"**Run:** {report['ts_iso']}",
        f"**Harness:** `{report['harness_version']}`",
        f"**Schema:** `{report['schema_version']}`",
        f"**Known-anomalies schema:** `{report.get('known_anomalies_schema', 'n/a')}`",
        f"**Verdict:** **{report['verdict'].upper()}**",
        "",
        "## Fixture: brenham",
        "",
        f"Source: `{report['fixture']['source_path']}`",
        f"Document name: `{report['fixture'].get('document_name', '')}`",
        "",
        "| Metric | Source | Export |",
        "|---|---:|---:|",
        f"| Placemark count | {report['fixture']['source_placemark_count']} | {report['fixture']['export_placemark_count']} |",
        f"| Folder count | {report['fixture']['source_folder_count']} | {report['fixture']['export_folder_count']} |",
        f"| Icon hrefs referenced | {report['fixture']['source_referenced_hrefs']} | {report['fixture'].get('export_referenced_hrefs', 'n/a')} (v2: per-feature `<IconStyle><Icon><href>` for points with resolved icon_href) |",
        f"| Archive entries | {report['fixture']['source_archive_entries']} | {report['fixture'].get('export_archive_entries', 1)} (doc.kml + embedded source assets per referenced relative href) |",
        f"| Export size (bytes) | — | {report['fixture']['export_bytes']} |",
        "",
        "## Gates",
        "",
        "| Gate | Status | Detail |",
        "|---|---|---|",
    ]
    for k, v in report["gates"].items():
        lines.append(f"| `{k}` | **{v['status']}** | {v['detail']} |")
    lines.append("")

    # ----- Semantic diff section (v1) -----
    sd = report.get("semantic_diff") or {}
    if sd:
        lines.extend([
            "## Semantic Diff",
            "",
            "Informational comparison along six axes. Not gate-class; intended ",
            "as the regression backbone — future runs can diff JSON reports for ",
            "any changed axis even when all gates remain PASS.",
            "",
            "### Folder tree",
            "",
            f"- Source folder count: **{sd['folder_tree']['source_folder_count']}**",
            f"- Export folder count (normalized): **{sd['folder_tree']['export_folder_count_normalized']}**",
            f"- Equivalent: **{sd['folder_tree']['equivalent']}**",
        ])
        if sd["folder_tree"]["source_only_folders"]:
            lines.append(f"- Source-only folders (sample): `{sd['folder_tree']['source_only_folders']}`")
        if sd["folder_tree"]["export_only_folders"]:
            lines.append(f"- Export-only folders (sample): `{sd['folder_tree']['export_only_folders']}`")
        lines.extend([
            "",
            "### Placemark names",
            "",
            f"- Source placemark count: **{sd['placemark_names']['source_count']}**",
            f"- Export placemark count: **{sd['placemark_names']['export_count']}**",
            f"- Source unique-name set size: {sd['placemark_names']['source_set_size']}",
            f"- Export unique-name set size: {sd['placemark_names']['export_set_size']}",
            f"- Equivalent as set: **{sd['placemark_names']['equivalent_as_set']}**",
        ])
        if sd["placemark_names"]["source_only_sample"]:
            lines.append(f"- Source-only names (sample): `{sd['placemark_names']['source_only_sample']}`")
        if sd["placemark_names"]["export_only_sample"]:
            lines.append(f"- Export-only names (sample): `{sd['placemark_names']['export_only_sample']}`")
        lines.extend([
            "",
            "### Geometry counts",
            "",
            f"- Source: `{sd['geometry_counts']['source']}`",
            f"- Export: `{sd['geometry_counts']['export']}`",
            f"- Equivalent: **{sd['geometry_counts']['equivalent']}**",
            "",
            "### Style URL references",
            "",
            f"- Source unique style URLs: {sd['style_url_refs']['source_count']}",
            f"- Export unique style URLs: {sd['style_url_refs']['export_count']}",
            f"- Equivalent as set: **{sd['style_url_refs']['equivalent_as_set']}**",
            "",
            "### Icon href references",
            "",
            f"- Source unique icon hrefs: {sd['icon_href_refs']['source_count']}",
            f"- Export unique icon hrefs: {sd['icon_href_refs']['export_count']}",
            f"- Note: {sd['icon_href_refs']['note']}",
            "",
            "### ExtendedData keys (union across all placemarks)",
            "",
            f"- Source key count: {sd['extended_data_keys']['source_count']}",
            f"- Export key count: {sd['extended_data_keys']['export_count']}",
            f"- Equivalent as set: **{sd['extended_data_keys']['equivalent_as_set']}**",
            "",
            "### TL-generated vs source-derived folder split (top-level only)",
            "",
            f"- Top-level export folders (normalized): `{sd['tl_vs_source_folder_split']['top_level_export_folder_names']}`",
            f"- Source-derived folder count: **{sd['tl_vs_source_folder_split']['source_derived_folder_count']}**",
            f"- TL-generated folder count: **{sd['tl_vs_source_folder_split']['tl_generated_folder_count']}**",
            f"- TL folder vocabulary: `{sd['tl_vs_source_folder_split']['tl_folder_vocabulary']}`",
            "",
        ])

    if report["failures"]:
        lines.append(f"### Failures ({len(report['failures'])})")
        for f in report["failures"]:
            lines.append(f"- `{f}`")
        lines.append("")
    if report["warnings"]:
        lines.append(f"### Warnings ({len(report['warnings'])})")
        for w in report["warnings"]:
            lines.append(f"- `{w}`")
        lines.append("")
    MD_REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ===========================================================================
# Pytest entry
# ===========================================================================

def test_f7f_v0_brenham_fixture_present():
    assert SOURCE_KMZ.exists(), (
        f"F7f fixture missing: {SOURCE_KMZ}. Commit the Brenham source KMZ "
        f"to this path per the F7f v0 design."
    )
    size = SOURCE_KMZ.stat().st_size
    assert size > 1000, (
        f"F7f fixture suspiciously small ({size} bytes); expected ~47 KB."
    )


def test_f7f_v0_round_trip_fidelity():
    report = run_harness()
    write_reports(report)
    assert report["verdict"] != "fail", (
        f"F7f v0 verdict={report['verdict']!r}; failures={report['failures']!r}. "
        f"See {JSON_REPORT.relative_to(PROJECT_ROOT).as_posix()} for details."
    )


if __name__ == "__main__":
    report = run_harness()
    write_reports(report)
    print(json.dumps(report, indent=2))
    raise SystemExit(1 if report["verdict"] == "fail" else 0)
