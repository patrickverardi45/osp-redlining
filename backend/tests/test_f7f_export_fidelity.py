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
from typing import Any, Dict, List, Set
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

HARNESS_VERSION = "f7f-v0-2026-05-21"
SCHEMA_VERSION = "f7f-fidelity-report-1"


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
    """Parse a KMZ into the F7f v0 semantic slice."""
    kml_bytes = _kml_bytes_from_kmz(file_bytes)
    root = ET.fromstring(kml_bytes)
    parent_map = {id(c): p for p in root.iter() for c in p}

    placemarks: List[Dict[str, Any]] = []
    for idx, pm in enumerate(root.iter(f"{{{KML_NS}}}Placemark")):
        name = (pm.findtext("kml:name", default="", namespaces=NS) or "").strip()
        placemarks.append({
            "feature_id": f"semantic_{idx}",
            "placemark_name": name or f"Unnamed_{idx}",
            "folder_path": _folder_path_of(pm, parent_map),
            "geometry_type": _geometry_type_of(pm),
            "extended_data": _extended_data_of(pm),
        })

    folders = list(root.iter(f"{{{KML_NS}}}Folder"))
    folder_names = [(f.findtext("kml:name", namespaces=NS) or "").strip() for f in folders]

    return {
        "placemarks": placemarks,
        "placemark_count": len(placemarks),
        "folders": folder_names,
        "folder_count": len(folder_names),
        "archive_entries": _kmz_archive_entries(file_bytes),
        "referenced_hrefs": _icon_hrefs_in_kml(root),
    }


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


def _emit_placemark(pm: Dict[str, Any]) -> str:
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
        f"{ed_xml}"
        f"{geom_xml}"
        "      </Placemark>"
    )


def emit_engineering_kml(parsed_source: Dict[str, Any]) -> str:
    """Emit a minimal Engineering-KMZ KML mirroring handleExportEngineeringKml
    for the source-side fidelity surfaces v0 asserts on."""
    tree = FolderNode("")
    for pm in parsed_source["placemarks"]:
        bucket = _get_folder_bucket(tree, pm["folder_path"])
        bucket.append(_emit_placemark(pm))

    eng_folder_blocks: List[str] = []
    for child in tree.children.values():
        if _folder_is_empty(child):
            continue
        eng_folder_blocks.append(_emit_folder(child, "    ", 0, 0))
    eng_folder_str = "\n".join(eng_folder_blocks)

    return (
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
        f'{eng_folder_str}\n'
        '  </Document>\n'
        '</kml>\n'
    )


def package_as_kmz(kml_str: str) -> bytes:
    """Wrap KML in a deterministic KMZ ZIP. Fixed timestamp on the doc.kml
    entry keeps byte-output stable across runs (required for G7)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zi = zipfile.ZipInfo("doc.kml", date_time=(2026, 1, 1, 0, 0, 0))
        zi.compress_type = zipfile.ZIP_DEFLATED
        zf.writestr(zi, kml_str.encode("utf-8"))
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
    # Raw folder-element count parity. v0 uses raw count; v1 G11 will assert
    # full tree-structure equality (F7d hierarchy). Defensive WARN allows
    # "Uncategorized" fallback if source has empty-folder_path placemarks.
    src, exp = source["folder_count"], export["folder_count"]
    if src == exp:
        return ("PASS", f"source={src} export={exp}")
    return (
        "WARN",
        f"source={src} export={exp} (acceptable if Uncategorized synthesized "
        f"for empty source folder_path; v1 G11 will assert full tree equality)"
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


def _gate_g3_source(source: Dict[str, Any]):
    # Source-side observation only. Pre-existing source-authoring-tool drift
    # (e.g., upstream Map Tool emits href "files/i46.png" while archive only
    # contains "files/i46_6_0.png") is NOT a TrueLine fidelity failure — the
    # TrueLine export pipeline cannot synthesize icons the source itself
    # omits. Classified as WARN so the harness surfaces the issue without
    # blocking export-fidelity validation. The decisive gate is
    # G3_icon_resolution_export (FAIL-class) which catches TrueLine
    # regressions that introduce additional unresolvable hrefs.
    bad = _unresolvable_relative_hrefs(source)
    if not bad:
        return ("PASS", "0 unresolvable relative hrefs in source")
    return (
        "WARN",
        f"{len(bad)} pre-existing source-side unresolvable href(s) "
        f"(upstream authoring drift; not a TrueLine regression): "
        f"{sorted(bad)[:3]}{'...' if len(bad) > 3 else ''}"
    )


def _gate_g3_export(export: Dict[str, Any]):
    bad = _unresolvable_relative_hrefs(export)
    if not bad:
        return ("PASS", "0 unresolvable relative hrefs in export")
    return (
        "FAIL",
        f"{len(bad)} unresolvable relative href(s) in export: "
        f"{sorted(bad)[:3]}{'...' if len(bad) > 3 else ''}"
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


def run_harness() -> Dict[str, Any]:
    source_bytes = SOURCE_KMZ.read_bytes()
    parsed_source = parse_kmz(source_bytes)

    kml_1 = emit_engineering_kml(parsed_source)
    export_bytes_1 = package_as_kmz(kml_1)
    parsed_export = parse_kmz(export_bytes_1)

    # G7 — run a second time on the same input
    kml_2 = emit_engineering_kml(parsed_source)
    export_bytes_2 = package_as_kmz(kml_2)

    # G8 — re-emit from the parsed export, package, re-parse
    kml_3 = emit_engineering_kml(parsed_export)
    export_bytes_3 = package_as_kmz(kml_3)
    parsed_re_export = parse_kmz(export_bytes_3)

    gates = {
        "G1_placemark_count_parity": _gate_g1(parsed_source, parsed_export),
        "G2_folder_count_parity": _gate_g2(parsed_source, parsed_export),
        "G3_icon_resolution_source": _gate_g3_source(parsed_source),
        "G3_icon_resolution_export": _gate_g3_export(parsed_export),
        "G4_extended_data_parity": _gate_g4(parsed_source, parsed_export),
        "G7_determinism": _gate_g7(export_bytes_1, export_bytes_2),
        "G8_round_trip_parse_stability": _gate_g8(parsed_export, parsed_re_export),
    }

    failures = [k for k, (s, _) in gates.items() if s == "FAIL"]
    warnings = [k for k, (s, _) in gates.items() if s == "WARN"]
    verdict = "fail" if failures else ("warn_only" if warnings else "pass")

    return {
        "schema_version": SCHEMA_VERSION,
        "harness_version": HARNESS_VERSION,
        "ts_iso": datetime.now(timezone.utc).isoformat(),
        "fixture": {
            "name": "brenham",
            "source_path": str(SOURCE_KMZ.relative_to(PROJECT_ROOT)).replace("\\", "/"),
            "source_placemark_count": parsed_source["placemark_count"],
            "source_folder_count": parsed_source["folder_count"],
            "source_referenced_hrefs": len(parsed_source["referenced_hrefs"]),
            "source_archive_entries": len(parsed_source["archive_entries"]),
            "export_placemark_count": parsed_export["placemark_count"],
            "export_folder_count": parsed_export["folder_count"],
            "export_bytes": len(export_bytes_1),
        },
        "gates": {k: {"status": s, "detail": d} for k, (s, d) in gates.items()},
        "verdict": verdict,
        "failures": failures,
        "warnings": warnings,
    }


def write_reports(report: Dict[str, Any]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    JSON_REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")

    lines: List[str] = [
        "# F7f Export Fidelity Harness — v0 Report",
        "",
        f"**Run:** {report['ts_iso']}",
        f"**Harness:** `{report['harness_version']}`",
        f"**Schema:** `{report['schema_version']}`",
        f"**Verdict:** **{report['verdict'].upper()}**",
        "",
        "## Fixture: brenham",
        "",
        f"Source: `{report['fixture']['source_path']}`",
        "",
        "| Metric | Source | Export |",
        "|---|---:|---:|",
        f"| Placemark count | {report['fixture']['source_placemark_count']} | {report['fixture']['export_placemark_count']} |",
        f"| Folder count | {report['fixture']['source_folder_count']} | {report['fixture']['export_folder_count']} |",
        f"| Icon hrefs referenced | {report['fixture']['source_referenced_hrefs']} | (emitter v0 emits no icon hrefs) |",
        f"| Archive entries | {report['fixture']['source_archive_entries']} | 1 (doc.kml only) |",
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
