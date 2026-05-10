"""Phase 1E — KMZ semantic ingestion lock-down regression suite.

Tests 01–12 share a single parse result built once in ``setUpClass``.
Test 13 re-parses three times to verify determinism.
Test 14 guards the top-level result schema.

All expected values are derivable by reading
``tests/fixtures/synthetic_kmz.py`` docstring — no magic numbers.

IF A TEST FAILS after a legitimate parser improvement:
  1. Confirm the change is intentional.
  2. Update the relevant EXPECTED_* constant below.
  3. Add a code comment explaining why (e.g. "updated in parser-v2 to …").
  DO NOT "fix to green" by tweaking expected values without understanding why.

STOP CONDITIONS (abort and report instead of pushing through):
  - A test would require editing main.py to pass → STOP
  - A test reveals a real parser bug → STOP and report; do not "fix to green"
  - Importing main fails outside an HTTP request context → STOP
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from typing import Any, Dict, List

# Put backend/ on sys.path so ``from main import …`` works regardless of cwd.
_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

# Module-level import: creates the FastAPI app and makes os.makedirs calls,
# but does NOT start a server.  All required packages (fastapi, boto3, pandas)
# must be installed in the active environment.
from main import _build_kmz_semantic  # noqa: E402
from tests.fixtures.synthetic_kmz import build_minimal_kmz_bytes  # noqa: E402

# ---------------------------------------------------------------------------
# Expected counts — each value is derivable from the fixture KML.
# See tests/fixtures/synthetic_kmz.py docstring for derivation.
# ---------------------------------------------------------------------------

EXPECTED_PARSER_VERSION = "semantic-1"
EXPECTED_FEATURE_COUNT = 5
EXPECTED_SKIPPED_PLACEMARK_COUNT = 0
# HH-001 (handhole+high) + VAULT-A (structure_marker+medium)
EXPECTED_ANCHOR_COUNT = 2

# Derived from the 5 placemarks in the fixture KML.
EXPECTED_BY_CLASSIFICATION: Dict[str, int] = {
    "handhole": 1,         # HH-001
    "structure_marker": 1, # VAULT-A
    "route_segment": 1,    # MAIN-LINE (LineString default)
    "annotation": 2,       # RESOLVED-PT, UNRESOLVED-PT (Point + name → low)
}

EXPECTED_BY_GEOMETRY_TYPE: Dict[str, int] = {
    "Point": 4,      # HH-001, VAULT-A, RESOLVED-PT, UNRESOLVED-PT
    "LineString": 1, # MAIN-LINE
}

EXPECTED_BY_CONFIDENCE: Dict[str, int] = {
    "high": 1,   # HH-001 (name_regex)
    "medium": 1, # VAULT-A (name_contains "vault")
    "low": 3,    # MAIN-LINE, RESOLVED-PT, UNRESOLVED-PT
}

# style_resolution sub-dict in index.
EXPECTED_STYLE_RESOLUTION: Dict[str, int] = {
    "ids_declared": 1,               # <Style id="styA">
    "ids_referenced": 2,             # styA (RESOLVED-PT) + missingStyle (UNRESOLVED-PT)
    "ids_referenced_unresolved": 1,  # missingStyle not declared
    "stylemap_count": 1,             # <StyleMap id="mapA">
    "stylemap_unresolved_count": 0,  # mapA resolves to styA which is in resolved_styles
    "stylemap_cycle_count": 0,       # always 0 in semantic-1
}

# len(resolved_styles) = styA + mapA
EXPECTED_STYLES_RESOLVED_COUNT = 2

# The unresolved styleUrl stripped of its leading '#'.
EXPECTED_MISSING_STYLE_URL = "missingStyle"

# Keys that _build_kmz_semantic is allowed to return at the top level.
# Add to this set (with a comment) if a new top-level field is intentionally added.
KNOWN_TOP_LEVEL_KEYS = {"parser_version", "features", "index", "warnings"}

# Every classification_debug dict must contain exactly these keys.
CLASSIFICATION_DEBUG_REQUIRED_KEYS = {
    "matched_by",
    "matched_tokens",
    "heuristic_sources",
    "coordinate_source",
}


# ---------------------------------------------------------------------------
# Canonicalizer for determinism tests.
# ---------------------------------------------------------------------------

def _canonicalize(payload: Dict[str, Any]) -> str:
    """Project a semantic payload to a deterministic, sorted JSON string.

    Strips volatile fields:
      - exact feature_id strings (positional index used instead)
      - exact float coordinates (presence flag only)
      - classification_samples literal id arrays (length only)
      - raw matched_tokens / heuristic_sources strings (keys only, to avoid
        Python repr drift across versions)

    Keeps all structurally stable fields so a genuine classification change
    or field removal will cause the string to differ.
    """
    if payload is None:
        return "null"

    index: Dict[str, Any] = payload.get("index") or {}
    features: List[Dict[str, Any]] = payload.get("features") or []

    def _project_feature(f: Dict[str, Any]) -> Dict[str, Any]:
        dbg: Dict[str, Any] = f.get("classification_debug") or {}
        return {
            "classification": f.get("classification"),
            "confidence": f.get("confidence"),
            "geometry_type": f.get("geometry_type"),
            "folder_path_str": f.get("folder_path_str"),
            "style_url": f.get("style_url"),
            # Coordinate presence only — not exact floats.
            "has_coords_hint": f.get("coords_hint") is not None,
            "has_full_geometry": f.get("full_geometry") is not None,
            # Style resolution presence only.
            "has_style_resolved": bool(f.get("style_resolved")),
            # Lifecycle label only (no confidence text).
            "lifecycle_label": (f.get("lifecycle") or {}).get("label"),
            # Debug key set only — avoids repr drift on token strings.
            "classification_debug_keys": sorted(dbg.keys()),
            "coordinate_source": dbg.get("coordinate_source"),
        }

    projected = sorted(
        [_project_feature(f) for f in features],
        key=lambda x: (
            x["classification"] or "",
            x["geometry_type"] or "",
            x["style_url"] or "",
        ),
    )

    canonical = {
        "parser_version": payload.get("parser_version"),
        "feature_count": index.get("feature_count"),
        "by_classification": dict(
            sorted((index.get("by_classification") or {}).items())
        ),
        "by_geometry_type": dict(
            sorted((index.get("by_geometry_type") or {}).items())
        ),
        "by_confidence": dict(
            sorted((index.get("by_confidence") or {}).items())
        ),
        "skipped_placemark_count": index.get("skipped_placemark_count"),
        "warnings_count": len(payload.get("warnings") or []),
        "style_resolution": index.get("style_resolution"),
        "styles_resolved_count": index.get("styles_resolved_count"),
        "missing_style_urls": sorted(index.get("missing_style_urls") or []),
        "features": projected,
    }
    return json.dumps(canonical, sort_keys=True, separators=(",", ":"))


# ---------------------------------------------------------------------------
# Test suite.
# ---------------------------------------------------------------------------

class TestSemanticIngestion(unittest.TestCase):
    """Lock-down regression suite for ``_build_kmz_semantic``.

    ``setUpClass`` builds the fixture bytes once and runs the parser once.
    Tests 01–12 inspect ``cls._result``.
    Test 13 re-parses three times to assert replay determinism.
    Test 14 guards the top-level key schema.
    """

    _bytes: bytes = b""
    _result: Dict[str, Any] = {}

    @classmethod
    def setUpClass(cls) -> None:
        cls._bytes = build_minimal_kmz_bytes()
        result = _build_kmz_semantic(cls._bytes, "fixture.kmz")
        if result is None:
            raise RuntimeError(
                "STOP: _build_kmz_semantic returned None for the synthetic fixture. "
                "The parser may have raised an unhandled exception. "
                "Check the [KMZ_SEM_TRACE] output above."
            )
        cls._result = result

    # ------------------------------------------------------------------
    # 01 — basic smoke
    # ------------------------------------------------------------------

    def test_01_parser_runs_without_exception(self) -> None:
        """_build_kmz_semantic must return a non-None dict for the fixture."""
        self.assertIsNotNone(self._result)
        self.assertIsInstance(self._result, dict)

    # ------------------------------------------------------------------
    # 02 — parser version
    # ------------------------------------------------------------------

    def test_02_parser_version_present(self) -> None:
        """parser_version must equal 'semantic-1'."""
        self.assertEqual(
            self._result.get("parser_version"),
            EXPECTED_PARSER_VERSION,
        )

    # ------------------------------------------------------------------
    # 03 — feature count
    # ------------------------------------------------------------------

    def test_03_feature_count_matches_fixture(self) -> None:
        """5 well-formed placemarks in the fixture → feature_count == 5.

        HH-001, VAULT-A, MAIN-LINE, RESOLVED-PT, UNRESOLVED-PT.
        """
        idx = self._result["index"]
        self.assertEqual(
            idx["feature_count"],
            EXPECTED_FEATURE_COUNT,
            "index.feature_count mismatch",
        )
        self.assertEqual(
            len(self._result["features"]),
            EXPECTED_FEATURE_COUNT,
            "len(features) mismatch",
        )

    # ------------------------------------------------------------------
    # 04 — classification breakdown
    # ------------------------------------------------------------------

    def test_04_classification_breakdown_stable(self) -> None:
        """by_classification must match expected counts exactly.

        handhole:1  HH-001 via name_regex (_KMZ_SEMANTIC_HANDHOLE_RE)
        structure_marker:1  VAULT-A via "vault" in name_l
        route_segment:1  MAIN-LINE default LineString
        annotation:2  RESOLVED-PT, UNRESOLVED-PT (Point + name present)
        """
        by_cls = dict(self._result["index"]["by_classification"])
        self.assertEqual(by_cls, EXPECTED_BY_CLASSIFICATION)

    # ------------------------------------------------------------------
    # 05 — geometry breakdown
    # ------------------------------------------------------------------

    def test_05_geometry_breakdown_stable(self) -> None:
        """by_geometry_type must match: Point:4, LineString:1."""
        by_geo = dict(self._result["index"]["by_geometry_type"])
        self.assertEqual(by_geo, EXPECTED_BY_GEOMETRY_TYPE)

    # ------------------------------------------------------------------
    # 06 — skipped placemark count
    # ------------------------------------------------------------------

    def test_06_skipped_placemark_count_stable(self) -> None:
        """skipped_placemark_count must be 0 for a well-formed fixture.

        Note: a Placemark with non-float <coordinates> text (e.g.
        'not-a-coord') does NOT trigger a skip.  _parse_coordinate_text
        silently returns [] for non-numeric tokens, so coords_hint becomes
        None without raising — the placemark still processes normally.
        The skip counter only fires when the per-placemark try-block raises
        an unhandled exception, which does not occur for any valid XML node.
        """
        count = self._result["index"].get("skipped_placemark_count", 0)
        self.assertEqual(count, EXPECTED_SKIPPED_PLACEMARK_COUNT)

    # ------------------------------------------------------------------
    # 07 — warnings / skipped count parity
    # ------------------------------------------------------------------

    def test_07_warnings_count_matches_skipped(self) -> None:
        """len(warnings) must equal skipped_placemark_count (both 0 here)."""
        warnings: List[str] = self._result.get("warnings") or []
        skipped: int = self._result["index"].get("skipped_placemark_count", 0)
        self.assertEqual(
            len(warnings),
            skipped,
            f"warnings has {len(warnings)} entries but skipped count is {skipped}",
        )

    # ------------------------------------------------------------------
    # 08 — style resolution health
    # ------------------------------------------------------------------

    def test_08_style_resolution_health_stable(self) -> None:
        """All six style_resolution fields must match expected values.

        ids_declared=1            <Style id="styA">
        ids_referenced=2          styA (RESOLVED-PT) + missingStyle (UNRESOLVED-PT)
        ids_referenced_unresolved=1  missingStyle not in resolved_styles
        stylemap_count=1          <StyleMap id="mapA">
        stylemap_unresolved_count=0  mapA resolves (normal→#styA which is declared)
        stylemap_cycle_count=0    hardcoded in semantic-1
        styles_resolved_count=2   len(resolved_styles) = styA + mapA
        """
        sr = self._result["index"].get("style_resolution")
        self.assertIsNotNone(sr, "index.style_resolution must be present")
        for field, expected in EXPECTED_STYLE_RESOLUTION.items():
            with self.subTest(field=field):
                self.assertEqual(
                    sr.get(field),
                    expected,
                    f"style_resolution.{field}: expected {expected}, got {sr.get(field)}",
                )
        # styles_resolved_count lives at the index level, not inside style_resolution.
        self.assertEqual(
            self._result["index"].get("styles_resolved_count"),
            EXPECTED_STYLES_RESOLVED_COUNT,
            "index.styles_resolved_count mismatch",
        )

    # ------------------------------------------------------------------
    # 09 — missing style URLs
    # ------------------------------------------------------------------

    def test_09_missing_style_urls_present(self) -> None:
        """missing_style_urls must contain 'missingStyle' (UNRESOLVED-PT's styleUrl)."""
        urls: List[str] = self._result["index"].get("missing_style_urls") or []
        self.assertIn(
            EXPECTED_MISSING_STYLE_URL,
            urls,
            f"Expected '{EXPECTED_MISSING_STYLE_URL}' in missing_style_urls, got {urls}",
        )

    # ------------------------------------------------------------------
    # 10 — classification_debug present on every feature
    # ------------------------------------------------------------------

    def test_10_classification_debug_present_on_every_feature(self) -> None:
        """Every feature must carry a non-None classification_debug dict (Phase 1C-D)."""
        for i, feature in enumerate(self._result["features"]):
            with self.subTest(
                feature_index=i, name=feature.get("placemark_name")
            ):
                self.assertIn("classification_debug", feature)
                self.assertIsInstance(
                    feature["classification_debug"],
                    dict,
                    f"feature[{i}].classification_debug must be a dict",
                )

    # ------------------------------------------------------------------
    # 11 — classification_debug key types
    # ------------------------------------------------------------------

    def test_11_classification_debug_keys_have_expected_types(self) -> None:
        """classification_debug must have 4 required keys with correct types."""
        for i, feature in enumerate(self._result["features"]):
            dbg: Dict[str, Any] = feature.get("classification_debug") or {}
            with self.subTest(
                feature_index=i, name=feature.get("placemark_name")
            ):
                for key in CLASSIFICATION_DEBUG_REQUIRED_KEYS:
                    self.assertIn(
                        key,
                        dbg,
                        f"feature[{i}].classification_debug missing key '{key}'",
                    )
                self.assertIsInstance(
                    dbg["matched_by"], list,
                    f"feature[{i}].classification_debug.matched_by must be list",
                )
                self.assertIsInstance(
                    dbg["matched_tokens"], list,
                    f"feature[{i}].classification_debug.matched_tokens must be list",
                )
                self.assertIsInstance(
                    dbg["heuristic_sources"], list,
                    f"feature[{i}].classification_debug.heuristic_sources must be list",
                )
                coord_src = dbg.get("coordinate_source")
                self.assertTrue(
                    coord_src is None or isinstance(coord_src, str),
                    f"feature[{i}].classification_debug.coordinate_source must be "
                    f"str or None, got {type(coord_src).__name__}",
                )

    # ------------------------------------------------------------------
    # 12 — anchor catalog
    # ------------------------------------------------------------------

    def test_12_anchor_catalog_present_when_anchors_exist(self) -> None:
        """anchor_catalog must contain exactly 2 entries: HH-001 and VAULT-A.

        Anchor eligibility: classification ∈ {handhole, station_label, reel,
        structure_marker} AND confidence ∈ {high, medium} AND coords_hint valid.

        HH-001   → handhole + high  → eligible
        VAULT-A  → structure_marker + medium → eligible
        MAIN-LINE  → route_segment + low  → ineligible (low confidence)
        RESOLVED-PT  → annotation + low  → ineligible (not in _ANCHOR_KINDS)
        UNRESOLVED-PT → annotation + low → ineligible
        """
        catalog: List[Dict[str, Any]] = (
            self._result["index"].get("anchor_catalog") or []
        )
        self.assertEqual(
            len(catalog),
            EXPECTED_ANCHOR_COUNT,
            f"Expected {EXPECTED_ANCHOR_COUNT} anchor entries, got {len(catalog)}",
        )
        classifications = {e["classification"] for e in catalog}
        self.assertIn(
            "handhole",
            classifications,
            "HH-001 (handhole+high) must appear in anchor_catalog",
        )
        self.assertIn(
            "structure_marker",
            classifications,
            "VAULT-A (structure_marker+medium) must appear in anchor_catalog",
        )

    # ------------------------------------------------------------------
    # 13 — replay determinism
    # ------------------------------------------------------------------

    def test_13_replay_determinism(self) -> None:
        """Three sequential parses of identical bytes must produce identical canonical JSON.

        Uses _canonicalize() which strips volatile fields (exact feature_ids,
        float coords, classification_sample id arrays, raw matched_token
        strings) and returns sorted JSON.  Any non-determinism in dict
        ordering, set iteration, or hash randomization will break equality.
        """
        runs = [
            _build_kmz_semantic(self._bytes, "fixture.kmz") for _ in range(3)
        ]
        # Confirm none of the three runs returned None.
        for i, run in enumerate(runs):
            self.assertIsNotNone(run, f"Run {i + 1} returned None")

        canons = [_canonicalize(r) for r in runs]  # type: ignore[arg-type]
        self.assertEqual(
            canons[0],
            canons[1],
            "Canonical output differs between run 1 and run 2 — parser is non-deterministic",
        )
        self.assertEqual(
            canons[1],
            canons[2],
            "Canonical output differs between run 2 and run 3 — parser is non-deterministic",
        )

    # ------------------------------------------------------------------
    # 14 — top-level key schema guard
    # ------------------------------------------------------------------

    def test_14_no_unexpected_top_level_keys(self) -> None:
        """Result keys must be a subset of the known stable set.

        Failure means a new top-level key was added to _build_kmz_semantic's
        return value.  Add it to KNOWN_TOP_LEVEL_KEYS with a comment
        explaining what it is and when it was added.
        """
        result_keys = set(self._result.keys())
        unexpected = result_keys - KNOWN_TOP_LEVEL_KEYS
        self.assertEqual(
            unexpected,
            set(),
            f"Unexpected top-level keys: {unexpected}. "
            "Add them to KNOWN_TOP_LEVEL_KEYS in this test file with a comment.",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
