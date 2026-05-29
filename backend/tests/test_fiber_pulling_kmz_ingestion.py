"""Fiber-Pulling KMZ ingestion generalization regression.

Proves TrueLine's KMZ parser + ``_build_route_catalog`` generalize BEYOND
Brenham PH5 on a large, real, non-Brenham long-haul fiber KMZ
(Edgewood -> Memphis, Dallas-Memphis Level 3, ~1,906 route-miles). At ~7,321
routes / 10,895 placemarks this corpus is ~13.6x Brenham's 539 routes, so it
exercises ingestion scale + a very different folder/name/role shape.

SCOPE — what this proves and does NOT prove:
  * PROVES: KMZ ingestion + route_catalog extraction generalize (LineStrings ->
    routes, coordinates usable, Points/Polygons excluded, route_role honestly
    degrades to "other" for non-OSP long-haul corridors).
  * Does NOT prove Trust Ledger matching / redline-placement generalization.
    The packet's XLSX are fiber-splicing SOW/pricing sheets, NOT bore logs, so
    there is NO station/print/footage data. A proof/abstain Trust Ledger audit
    on a non-Brenham corpus STILL REQUIRES real bore-log/station data. This test
    deliberately does not fabricate bore logs and does not run the ledger.

DATA HANDLING — the 3.5 MB raw customer KMZ (Level3 / AW Solutions) is NOT
committed. The test is fixture-gated: it locates an operator-provided
``Fiber-Pulling.zip`` (env ``TRUELINE_FIBER_PULLING_ZIP`` -> tests/fixtures copy
-> the known local Desktop path) and ``skipUnless`` it is present, so CI without
the customer file skips cleanly. Expected counts live as in-test constants
(aggregate numbers only — no raw geometry / no customer PII committed).

Read-only: builds a route_catalog in-memory from KMZ bytes; touches no STATE,
no matching/scoring/selection/redline, no production.
"""

from __future__ import annotations

import io
import os
import re
import sys
import unittest
import zipfile
from pathlib import Path

# Make `backend` (for `from backend import main`) AND `backend/app` (main.py does
# `from app.auth import ...`) importable for standalone runs. Mirrors the replay
# harness; pytest from repo root also works.
_REPO_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_REPO_ROOT), str(_REPO_ROOT / "backend")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

os.environ.setdefault("TRUELINE_JWT_SECRET", "fiber-ingest-test")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "fiber-ingest-test-auth")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

from backend import main as M  # noqa: E402 — must follow env defaults

# ── Fixture resolution (operator-provided; NOT committed) ──────────────────
_FIBER_ZIP_CANDIDATES = [
    os.environ.get("TRUELINE_FIBER_PULLING_ZIP"),
    str(Path(__file__).resolve().parent / "fixtures" / "Fiber-Pulling.zip"),
    r"C:/Users/Patrick/OneDrive/Attachments/Desktop/Fiber-Pulling.zip",
]
FIBER_ZIP = next((p for p in _FIBER_ZIP_CANDIDATES if p and Path(p).exists()), None)
HAS_FIBER_ZIP = FIBER_ZIP is not None
_SKIP_REASON = (
    "Fiber-Pulling.zip not found (operator-provided, intentionally not committed). "
    "Set TRUELINE_FIBER_PULLING_ZIP=<path> to run."
)

# KMZ entry inside the zip, and the corpus shape observed on the real file
# (read-only audit, 2026-05-29). These are aggregate regression anchors.
KMZ_ENTRY = "Attachment B Edgewood to Memphis KMZ file .kmz"
EXPECTED_ROUTES = 7321          # == LineString count (one route per LineString)
EXPECTED_PLACEMARKS = 10895
EXPECTED_LINESTRINGS = 7321
EXPECTED_POINTS = 1045
EXPECTED_POLYGONS = 2538
# Continental-US bounding box sanity for coordinate usability.
_US_LON = (-125.0, -66.0)
_US_LAT = (24.0, 50.0)


def _count_tag(text: str, tag: str) -> int:
    return len(re.findall(r"<%s[ >/]" % re.escape(tag), text))


@unittest.skipUnless(HAS_FIBER_ZIP, _SKIP_REASON)
class FiberPullingKmzIngestion(unittest.TestCase):
    """Route-catalog extraction on the non-Brenham long-haul fiber KMZ."""

    catalog: list
    kml_text: str

    @classmethod
    def setUpClass(cls) -> None:
        with zipfile.ZipFile(FIBER_ZIP) as z:
            kmz_bytes = z.read(KMZ_ENTRY)
        # Raw KML feature counts (from the KMZ's inner doc.kml).
        with zipfile.ZipFile(io.BytesIO(kmz_bytes)) as kz:
            kml_name = next(n for n in kz.namelist() if n.lower().endswith(".kml"))
            cls.kml_text = kz.read(kml_name).decode("utf-8", "ignore")
        # The read-only ingestion under test.
        cls.catalog = M._build_route_catalog(kmz_bytes, KMZ_ENTRY)

    # 1) builds without error + non-trivial result
    def test_route_catalog_builds_without_error(self) -> None:
        self.assertIsInstance(self.catalog, list)
        self.assertGreater(len(self.catalog), 1000)

    # 2) route count matches the real corpus (exact regression anchor)
    def test_route_count_matches_corpus(self) -> None:
        self.assertEqual(len(self.catalog), EXPECTED_ROUTES)

    # 3) coordinates exist and are usable (>=2 pts, within continental US)
    def test_coordinates_present_and_usable(self) -> None:
        for r in self.catalog:
            coords = r.get("coords") or []
            self.assertGreaterEqual(len(coords), 2)
        # route_catalog stores coords as [lat, lon] (per _parse_coordinate_text;
        # the V3 coord-orientation fix confirmed this convention). Spot-check the
        # longest route's endpoints fall in the continental-US bbox in that order.
        longest = max(self.catalog, key=lambda r: r.get("length_ft") or 0)
        for pt in (longest["coords"][0], longest["coords"][-1]):
            lat, lon = float(pt[0]), float(pt[1])
            self.assertTrue(_US_LAT[0] <= lat <= _US_LAT[1], f"lat {lat} out of US bbox")
            self.assertTrue(_US_LON[0] <= lon <= _US_LON[1], f"lon {lon} out of US bbox")

    # 4) LineStrings ARE included (one route per LineString)
    def test_linestrings_included(self) -> None:
        linestrings = _count_tag(self.kml_text, "LineString")
        self.assertEqual(linestrings, EXPECTED_LINESTRINGS)
        self.assertEqual(len(self.catalog), linestrings)

    # 5) Points and Polygons are EXCLUDED from the route_catalog
    def test_points_and_polygons_excluded(self) -> None:
        placemarks = _count_tag(self.kml_text, "Placemark")
        points = _count_tag(self.kml_text, "Point")
        polygons = _count_tag(self.kml_text, "Polygon")
        self.assertEqual(placemarks, EXPECTED_PLACEMARKS)
        self.assertEqual(points, EXPECTED_POINTS)
        self.assertEqual(polygons, EXPECTED_POLYGONS)
        # The KMZ HAS points + polygons, yet NONE became routes.
        self.assertGreater(points, 0)
        self.assertGreater(polygons, 0)
        self.assertEqual(len(self.catalog), EXPECTED_LINESTRINGS)
        self.assertLess(len(self.catalog), placemarks)

    # 6) route_role honestly degrades to "other" (OSP role taxonomy doesn't fit
    #    long-haul trench/bore corridors — no fake backbone/tail/drop labels)
    def test_route_role_degrades_to_other(self) -> None:
        roles: dict = {}
        for r in self.catalog:
            roles[r.get("route_role")] = roles.get(r.get("route_role"), 0) + 1
        dominant = max(roles, key=roles.get)
        self.assertEqual(dominant, "other")
        self.assertGreaterEqual(roles.get("other", 0), int(0.9 * len(self.catalog)))

    # 7) total route length is sane for a ~1,906-mile long-haul span
    def test_total_length_sane(self) -> None:
        total = sum((r.get("length_ft") or 0.0) for r in self.catalog)
        # ~10.06M ft observed; assert a wide, non-brittle band.
        self.assertGreater(total, 5_000_000.0)
        self.assertLess(total, 20_000_000.0)


if __name__ == "__main__":
    if not HAS_FIBER_ZIP:
        print("SKIP:", _SKIP_REASON)
    unittest.main(verbosity=2)
