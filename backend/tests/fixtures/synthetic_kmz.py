"""Synthetic KMZ fixture for Phase 1E regression tests.

Builds a deterministic in-memory KMZ (a ZIP archive containing doc.kml) that
exercises ``_build_kmz_semantic`` with a fully auditable, source-controlled
KML document.  No binary files are committed to git.

HOW TO VERIFY EXPECTED COUNTS
------------------------------
Read the KML constant below and trace each Placemark through
``_kmz_semantic_classify`` in ``backend/main.py``.  Every count is derivable
by inspection without running the parser.

EXPECTED COUNTS
---------------
feature_count                           : 5
skipped_placemark_count                 : 0
  (all placemarks are well-formed XML; the parser handles non-float coords
   gracefully via _parse_coordinate_text without raising, so no skip fires)
parser_version                          : "semantic-1"

by_classification:
  handhole         : 1  ← HH-001  (name_regex on HH-001 hits _KMZ_SEMANTIC_HANDHOLE_RE)
  structure_marker : 1  ← VAULT-A (geometry_type=Point + "vault" in name_l → name_contains)
  route_segment    : 1  ← MAIN-LINE (LineString default; "main-line" lacks backbone/route tokens)
  annotation       : 2  ← RESOLVED-PT, UNRESOLVED-PT (Point + name present → low annotation)

by_geometry_type:
  Point      : 4  (HH-001, VAULT-A, RESOLVED-PT, UNRESOLVED-PT)
  LineString : 1  (MAIN-LINE)

by_confidence:
  high   : 1  (HH-001)
  medium : 1  (VAULT-A)
  low    : 3  (MAIN-LINE, RESOLVED-PT, UNRESOLVED-PT)

anchor_catalog (handhole|station_label|reel|structure_marker + high|medium + valid coord):
  count : 2
  ├─ HH-001  (handhole + high)
  └─ VAULT-A (structure_marker + medium)

style_resolution:
  ids_declared               : 1   (<Style id="styA">)
  ids_referenced             : 2   (RESOLVED-PT→#styA, UNRESOLVED-PT→#missingStyle)
  ids_referenced_unresolved  : 1   (#missingStyle not declared)
  stylemap_count             : 1   (<StyleMap id="mapA">)
  stylemap_unresolved_count  : 0   (mapA normal-pair→#styA which IS in resolved_styles)
  stylemap_cycle_count       : 0   (hardcoded in semantic-1)

styles_resolved_count        : 2   (styA + mapA both resolve; len(resolved_styles))
missing_style_urls           : ["missingStyle"]
"""

import io
import zipfile

# KML namespace matches KML_NS["kml"] in main.py.
_KML_NS = "http://www.opengis.net/kml/2.2"

_MINIMAL_KML = """\
<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>

    <!-- ── Style declarations ─────────────────────────────────────────── -->

    <!-- 1 declared Style → ids_declared = 1 -->
    <Style id="styA">
      <IconStyle>
        <color>ff0000ff</color>
        <Icon><href>icon.png</href></Icon>
      </IconStyle>
    </Style>

    <!-- 1 StyleMap whose normal pair resolves to styA → stylemap_count = 1,
         stylemap_unresolved_count = 0, styles_resolved_count = 2 -->
    <StyleMap id="mapA">
      <Pair><key>normal</key><styleUrl>#styA</styleUrl></Pair>
      <Pair><key>highlight</key><styleUrl>#styA</styleUrl></Pair>
    </StyleMap>

    <!-- ── Placemarks ─────────────────────────────────────────────────── -->

    <!-- Placemark 1 · HH-001
         geometry : Point  → coordinate_source = "Point"
         name     : "HH-001" matches _KMZ_SEMANTIC_HANDHOLE_RE (HH + dash + digit)
         result   : handhole / high
         anchor   : YES  (handhole ∈ _ANCHOR_KINDS, high ∈ _ACCEPTED_CONFIDENCE, coord valid)
         sequence : sequence_number=1, sequence_kind="handhole" (HH-001 → int("001")=1) -->
    <Placemark>
      <name>HH-001</name>
      <Point><coordinates>-96.0,30.0,0</coordinates></Point>
    </Placemark>

    <!-- Placemark 2 · VAULT-A
         geometry : Point  → coordinate_source = "Point"
         name     : "vault-a" contains structure_token "vault"
         result   : structure_marker / medium  (geometry_type=Point + name_contains)
         anchor   : YES  (structure_marker ∈ _ANCHOR_KINDS, medium ∈ _ACCEPTED_CONFIDENCE) -->
    <Placemark>
      <name>VAULT-A</name>
      <Point><coordinates>-96.1,30.1,0</coordinates></Point>
    </Placemark>

    <!-- Placemark 3 · MAIN-LINE
         geometry : LineString  → coordinate_source = "LineString"
         name     : "main-line" does NOT contain backbone/feeder/cable/route/lateral/trunk
         result   : route_segment / low  (LineString default)
         anchor   : NO  (low ∉ _ACCEPTED_CONFIDENCE) -->
    <Placemark>
      <name>MAIN-LINE</name>
      <LineString>
        <coordinates>-96.0,30.0,0 -96.1,30.1,0</coordinates>
      </LineString>
    </Placemark>

    <!-- Placemark 4 · RESOLVED-PT
         geometry : Point  → coordinate_source = "Point"
         styleUrl : #styA  → resolves (styA declared above)
         result   : annotation / low  (Point + name present, no stronger signal)
         anchor   : NO  (annotation ∉ _ANCHOR_KINDS)
         ids_referenced += "styA",  style_resolved = truthy → features_with_resolved_style++ -->
    <Placemark>
      <name>RESOLVED-PT</name>
      <styleUrl>#styA</styleUrl>
      <Point><coordinates>-96.2,30.2,0</coordinates></Point>
    </Placemark>

    <!-- Placemark 5 · UNRESOLVED-PT
         geometry : Point  → coordinate_source = "Point"
         styleUrl : #missingStyle  → does NOT resolve (not declared)
         result   : annotation / low
         anchor   : NO
         ids_referenced += "missingStyle" → ids_referenced_unresolved = 1
         missing_style_urls = ["missingStyle"] -->
    <Placemark>
      <name>UNRESOLVED-PT</name>
      <styleUrl>#missingStyle</styleUrl>
      <Point><coordinates>-96.3,30.3,0</coordinates></Point>
    </Placemark>

  </Document>
</kml>
"""


def build_minimal_kmz_bytes() -> bytes:
    """Return bytes of a freshly built, deterministic KMZ archive.

    The archive contains exactly one file (``doc.kml``).  A fixed
    ``ZipInfo`` date is used so that the same call always produces the
    same SHA-256 hash — important for the ingestion-ledger SHA stability
    test (Phase 1G) and useful for manual spot-checks.

    Returns
    -------
    bytes
        A valid ZIP (KMZ) file that the parser accepts via
        ``_extract_kml_bytes``.
    """
    buf = io.BytesIO()
    info = zipfile.ZipInfo("doc.kml", date_time=(2024, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(info, _MINIMAL_KML.encode("utf-8"))
    return buf.getvalue()
