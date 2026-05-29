"""NXT052 OSP KMZ ingestion generalization regression.

Proves TrueLine's KMZ parser + ``_build_route_catalog`` generalize the FULL OSP
semantic stack beyond Brenham PH5 on a real, non-PH5 NextLink design
(``NXT052 - NEXTLINK - Brenham, TX.kmz``). Unlike the Fiber-Pulling long-haul KMZ
(which honestly degraded to 100% ``route_role == "other"``), NXT052 carries the
same OSP folder hierarchy as PH5 and resolves to REAL OSP roles — so this is the
stronger ingestion-generalization claim: route_catalog + role inference +
address-point extraction all work on a different NextLink packet.

SCOPE — what this proves and does NOT prove:
  * PROVES: OSP-role KMZ ingestion generalization (LineStrings -> 333 routes with
    house_drop / vacant_pipe / terminal_tail / underground_cable roles, no
    "other"; 186 address points; usable Brenham, TX coordinates; Points excluded
    from routes).
  * Does NOT prove Trust Ledger matching / redline-placement generalization.
    NXT052 is a DESIGN-side KMZ with no bore-log / station / print data, so a
    proof/abstain audit on a non-PH5 corpus STILL REQUIRES real bore-log/station
    data. This test does not fabricate bore logs and does not run the ledger.

DATA HANDLING — the raw customer KMZ (NextLink / Brenham) is NOT committed. The
test is fixture-gated: it resolves the operator-provided file via env
``TRUELINE_NXT052_KMZ`` -> tests/fixtures copy -> the known local Desktop path,
and ``skipUnless`` it is present, so CI without the customer file skips cleanly.
Expected values live as in-test constants (aggregate numbers only).

Read-only: builds a route_catalog + parses address points in-memory from KMZ
bytes; touches no STATE, no matching/scoring/selection/redline, no production.
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
# `from app.auth import ...`) importable for standalone runs; pytest from repo
# root also works.
_REPO_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_REPO_ROOT), str(_REPO_ROOT / "backend")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

os.environ.setdefault("TRUELINE_JWT_SECRET", "nxt052-ingest-test")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "nxt052-ingest-test-auth")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

from backend import main as M  # noqa: E402 — must follow env defaults

# ── Fixture resolution (operator-provided; NOT committed) ──────────────────
_NXT052_CANDIDATES = [
    os.environ.get("TRUELINE_NXT052_KMZ"),
    str(Path(__file__).resolve().parent / "fixtures" / "NXT052 - NEXTLINK - Brenham, TX.kmz"),
    r"C:/Users/Patrick/OneDrive/Attachments/Desktop/NXT052 - NEXTLINK - Brenham, TX.kmz",
]
NXT052 = next((p for p in _NXT052_CANDIDATES if p and Path(p).exists()), None)
HAS_NXT052 = NXT052 is not None
_SKIP_REASON = (
    "NXT052 KMZ not found (operator-provided, intentionally not committed). "
    "Set TRUELINE_NXT052_KMZ=<path> to run."
)

# Corpus shape observed on the real file (read-only audit, 2026-05-29).
EXPECTED_ROUTES = 333
EXPECTED_PLACEMARKS = 1129
EXPECTED_LINESTRINGS = 333
EXPECTED_POINTS = 796
EXPECTED_ADDRESS_POINTS = 186
EXPECTED_ROLE_DIST = {
    "house_drop": 275,
    "vacant_pipe": 33,
    "terminal_tail": 22,
    "underground_cable": 3,
}  # sums to 333; NO "other"
REQUIRED_FOLDER_SUBSTRINGS = ("House Drop", "Vacant Pipe", "Terminal Tail", "underground cable")
# Brenham, TX metro bbox ([lat, lon] convention). Brenham ~ (30.167, -96.398).
_BRENHAM_LAT = (29.8, 30.6)
_BRENHAM_LON = (-96.8, -96.0)


def _count_tag(text: str, tag: str) -> int:
    return len(re.findall(r"<%s[ >/]" % re.escape(tag), text))


@unittest.skipUnless(HAS_NXT052, _SKIP_REASON)
class Nxt052OspKmzIngestion(unittest.TestCase):
    """Route-catalog + OSP-role + address-point extraction on NXT052."""

    catalog: list
    address_points: list
    kml_text: str

    @classmethod
    def setUpClass(cls) -> None:
        with open(NXT052, "rb") as fh:
            kmz_bytes = fh.read()
        with zipfile.ZipFile(io.BytesIO(kmz_bytes)) as kz:
            kml_name = next(n for n in kz.namelist() if n.lower().endswith(".kml"))
            cls.kml_text = kz.read(kml_name).decode("utf-8", "ignore")
        name = os.path.basename(NXT052)
        cls.catalog = M._build_route_catalog(kmz_bytes, name)
        cls.address_points = M.parse_address_points_from_kml(kmz_bytes, name)

    @classmethod
    def _role_dist(cls) -> dict:
        d: dict = {}
        for r in cls.catalog:
            d[r.get("route_role")] = d.get(r.get("route_role"), 0) + 1
        return d

    # 1) builds without error + non-trivial result
    def test_route_catalog_builds_without_error(self) -> None:
        self.assertIsInstance(self.catalog, list)
        self.assertGreater(len(self.catalog), 100)

    # 2) route count matches the real corpus
    def test_route_count_matches_corpus(self) -> None:
        self.assertEqual(len(self.catalog), EXPECTED_ROUTES)

    # 3) coordinates usable + within the Brenham, TX bbox ([lat, lon] convention)
    def test_coordinates_in_brenham_bbox(self) -> None:
        for r in self.catalog:
            coords = r.get("coords") or []
            self.assertGreaterEqual(len(coords), 2)
            for pt in (coords[0], coords[-1]):
                lat, lon = float(pt[0]), float(pt[1])
                self.assertTrue(_BRENHAM_LAT[0] <= lat <= _BRENHAM_LAT[1], f"lat {lat} out of Brenham bbox")
                self.assertTrue(_BRENHAM_LON[0] <= lon <= _BRENHAM_LON[1], f"lon {lon} out of Brenham bbox")

    # 4) address points extracted by the existing parser
    def test_address_point_count(self) -> None:
        self.assertEqual(len(self.address_points), EXPECTED_ADDRESS_POINTS)

    # 5) route_role distribution resolves to REAL OSP roles (no "other")
    def test_route_role_distribution_exact(self) -> None:
        dist = self._role_dist()
        self.assertEqual(dist, EXPECTED_ROLE_DIST)
        self.assertNotIn("other", dist)
        self.assertEqual(sum(dist.values()), EXPECTED_ROUTES)

    # 6) total route length is sane (~56,366 ft observed)
    def test_total_length_sane(self) -> None:
        total = sum((r.get("length_ft") or 0.0) for r in self.catalog)
        self.assertGreater(total, 50_000.0)
        self.assertLess(total, 62_000.0)

    # 7) source_folder hierarchy carries the OSP semantics
    def test_source_folders_osp_semantics(self) -> None:
        folders = {str(r.get("source_folder") or "") for r in self.catalog}
        blob = " | ".join(folders)
        for needle in REQUIRED_FOLDER_SUBSTRINGS:
            self.assertIn(needle, blob, f"missing OSP folder semantic: {needle}")

    # 8) LineStrings ARE routes; Points are EXCLUDED from the route_catalog
    def test_linestrings_included_points_excluded(self) -> None:
        placemarks = _count_tag(self.kml_text, "Placemark")
        linestrings = _count_tag(self.kml_text, "LineString")
        points = _count_tag(self.kml_text, "Point")
        self.assertEqual(placemarks, EXPECTED_PLACEMARKS)
        self.assertEqual(linestrings, EXPECTED_LINESTRINGS)
        self.assertEqual(points, EXPECTED_POINTS)
        self.assertEqual(len(self.catalog), linestrings)  # LineStrings -> routes 1:1
        self.assertGreater(points, 0)
        self.assertLess(len(self.catalog), placemarks)  # the 796 Points are not routes


if __name__ == "__main__":
    if not HAS_NXT052:
        print("SKIP:", _SKIP_REASON)
    unittest.main(verbosity=2)
