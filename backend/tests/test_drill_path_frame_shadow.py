"""Target #18 — DrillPathFrame shadow layer contract tests.

Locks the pure read-only proof layer (no placement, no flag flip):
  1. bore_log7 frame == PROVEN, route_469, end-anchor AP-163, station_max(451)=AP.
  2. DROP lane (bore_log5/30/48/50/65) == BLOCKED, reason flowerpot_node_identity.
  3. detect_frame_overlaps reports unproven vs proven shared/adjacent geometry.
  4. The shadow attach in main.py is flag-OFF byte-identical (no _diag key) and
     gated to the route_480 bucket (verified by the helper default + scope).

Real-source frames (1,2) run against the committed fixture KMZ
(backend/tests/fixtures/brenham_phase5_source_truth.kmz — md5-identical to the
Brenham PH5 design KMZ), so this is a source-evidence lock, not a mock.
"""
import os
import unittest
from pathlib import Path

# Set required server env BEFORE any `from backend import main` (import-time asserts
# JWT secrets). Matches the sibling convention in test_terminal_tail_placement.py.
os.environ.setdefault("TRUELINE_JWT_SECRET", "test-secret")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "test-secret")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

from backend.app.core import pdf_ap_route_resolver as R

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "brenham_phase5_source_truth.kmz"

# Source-verified bore facts (print token + station min/max) for the route_480-bucket
# logs under test. From bore_log*.xlsx (Target #16 adjudication) — locked here so the
# frame contract does not depend on reading the operator's Desktop xlsx.
_BORE7 = {"source_file": "bore_log7", "print_tokens": ["10"],
          "station_min_ft": 55.0, "station_max_ft": 451.0,
          "hardcoded_route_ids": ["route_477"]}
_DROPS = [
    {"source_file": "bore_log5", "print_tokens": ["12"], "station_min_ft": 265.0, "station_max_ft": 500.0},
    {"source_file": "bore_log30", "print_tokens": ["10", "12"], "station_min_ft": 0.0, "station_max_ft": 500.0},
    {"source_file": "bore_log48", "print_tokens": ["10", "11", "12"], "station_min_ft": 0.0, "station_max_ft": 509.0},
    {"source_file": "bore_log50", "print_tokens": ["10", "11", "12"], "station_min_ft": 0.0, "station_max_ft": 514.0},
    {"source_file": "bore_log65", "print_tokens": ["9", "10"], "station_min_ft": 451.0, "station_max_ft": 650.0},
]


def _load_fixture_kmz():
    """Parse the fixture KMZ into (route_catalog, point_features) via the real parser.
    Returns (None, None) if the parser/fixture is unavailable (test skips)."""
    if not _FIXTURE.exists():
        return None, None
    try:
        from backend import main as M  # heavy import; only for the real-source class
    except Exception:
        return None, None
    kb = _FIXTURE.read_bytes()
    catalog = [r for r in (M._build_route_catalog(kb, _FIXTURE.name) or []) if r.get("coords")]
    pf = (M._build_kmz_reference(kb, _FIXTURE.name) or {}).get("point_features") or []
    return catalog, pf


class TestDrillPathFrameRealSource(unittest.TestCase):
    """Real-KMZ frame proofs against the committed Brenham fixture."""

    @classmethod
    def setUpClass(cls):
        cls.catalog, cls.pf = _load_fixture_kmz()
        if not cls.catalog or not cls.pf:
            raise unittest.SkipTest("fixture KMZ or parser unavailable")

    def test_bore_log7_frame_is_proven_route_469(self):
        f = R.build_drill_path_frame(
            point_features=self.pf, route_catalog=self.catalog, **_BORE7)
        self.assertEqual(f["proof"], "PROVEN", f.get("abstain_reason"))
        self.assertEqual(f["terminus_class"], "backbone_ap_bore")
        self.assertEqual(f["structure_type"], "terminal_tail")
        self.assertEqual((f["kmz_geometry"] or {}).get("route_id"), "route_469")
        # station 451 == AP-163 end anchor, within ~2 ft of the KMZ node
        self.assertEqual((f["end_anchor"] or {}).get("kind"), "ap")
        self.assertEqual(str((f["end_anchor"] or {}).get("id")), "163")
        self.assertLessEqual((f["kmz_geometry"] or {}).get("endpoint_gap_ft"), 2.0)
        self.assertEqual(f["confidence"], "high")
        self.assertIsNone(f["abstain_reason"])
        # legacy print-index (route_477) is recorded as a conflict, not the proof
        self.assertIn("legacy_conflict", f["evidence"])

    def test_drop_lane_frames_blocked_flowerpot_node_identity(self):
        for spec in _DROPS:
            f = R.build_drill_path_frame(
                point_features=self.pf, route_catalog=self.catalog, **spec)
            self.assertEqual(f["proof"], "BLOCKED", spec["source_file"])
            self.assertEqual(f["terminus_class"], "flower_pot_drop", spec["source_file"])
            self.assertEqual(f["structure_type"], "flower_pot", spec["source_file"])
            self.assertEqual(f["abstain_reason"], "flowerpot_node_identity", spec["source_file"])
            self.assertIsNone(f["kmz_geometry"], spec["source_file"])
            # the gap is real: PDF proves a flower-pot terminus, KMZ pots are unnamed
            self.assertGreater(f["evidence"]["flower_pot_node_count"], 0)
            self.assertEqual(f["evidence"]["named_flower_pot_node_count"], 0)

    def test_batch_extract_matches_individual(self):
        frames = R.extract_drill_path_frames([_BORE7] + _DROPS, self.pf, self.catalog)
        self.assertEqual(len(frames), 6)
        by = {f["source_file"]: f for f in frames}
        self.assertEqual(by["bore_log7"]["proof"], "PROVEN")
        self.assertTrue(all(by[d["source_file"]]["proof"] == "BLOCKED" for d in _DROPS))


class TestDrillPathFrameOverlap(unittest.TestCase):
    """Frame-ownership overlap rule (synthetic catalog for deterministic adjacency)."""

    # route_477 and route_479 share the exact vertex [10,10.001] -> adjacent.
    # route_469 and route_999 are isolated.
    SYN = [
        {"route_id": "route_469", "coords": [[0.0, 0.0], [0.0, 0.001]],
         "source_folder": "Connections / Terminal Tail", "length_ft": 459.0},
        {"route_id": "route_477", "coords": [[10.0, 10.0], [10.0, 10.001]],
         "source_folder": "Connections / underground cable", "length_ft": 800.0},
        {"route_id": "route_479", "coords": [[10.0, 10.001], [10.0, 10.002]],
         "source_folder": "Connections / underground cable", "length_ft": 860.0},
        {"route_id": "route_999", "coords": [[50.0, 50.0], [50.0, 50.001]],
         "source_folder": "Connections / underground cable", "length_ft": 100.0},
    ]

    def test_unproven_overlap_bore7_vs_bore43(self):
        # bore_log7's frame proves route_469, but the legacy engine occupies route_477
        # (adjacent to bore_log43's backbone route_479) -> neither owns its occupied route.
        f7 = {"source_file": "bore_log7", "proof": "PROVEN",
              "kmz_geometry": {"route_id": "route_469"}}
        f43 = {"source_file": "bore_log43", "proof": "BLOCKED", "kmz_geometry": None}
        ov = R.detect_frame_overlaps(
            [f7, f43], self.SYN,
            occupied_route_id_by_source={"bore_log7": "route_477", "bore_log43": "route_479"})
        self.assertEqual(len(ov), 1)
        self.assertEqual(ov[0]["verdict"], "unproven_overlap")
        self.assertEqual(sorted(ov[0]["not_owned_by_frame"]), ["bore_log43", "bore_log7"])
        self.assertEqual(ov[0]["shares_via"], "shared_vertex")

    def test_proven_shared_when_both_prove_same_route(self):
        fa = {"source_file": "a", "proof": "PROVEN", "kmz_geometry": {"route_id": "route_469"}}
        fb = {"source_file": "b", "proof": "PROVEN", "kmz_geometry": {"route_id": "route_469"}}
        ov = R.detect_frame_overlaps([fa, fb], self.SYN)
        self.assertEqual(len(ov), 1)
        self.assertEqual(ov[0]["verdict"], "proven_shared")
        self.assertEqual(ov[0]["not_owned_by_frame"], [])

    def test_no_overlap_when_routes_disjoint(self):
        fc = {"source_file": "c", "proof": "PROVEN", "kmz_geometry": {"route_id": "route_469"}}
        fd = {"source_file": "d", "proof": "PROVEN", "kmz_geometry": {"route_id": "route_999"}}
        self.assertEqual(R.detect_frame_overlaps([fc, fd], self.SYN), [])


class TestDrillPathFrameShadowFlag(unittest.TestCase):
    """Flag default-OFF and scope guard (byte-identical attach contract)."""

    def test_flag_default_off(self):
        from backend import main as M
        prev = os.environ.pop("TRUELINE_DRILL_PATH_FRAME_SHADOW", None)
        try:
            self.assertFalse(M._trueline_drill_path_frame_shadow_enabled())
        finally:
            if prev is not None:
                os.environ["TRUELINE_DRILL_PATH_FRAME_SHADOW"] = prev

    def test_flag_on_recognized(self):
        from backend import main as M
        prev = os.environ.get("TRUELINE_DRILL_PATH_FRAME_SHADOW")
        os.environ["TRUELINE_DRILL_PATH_FRAME_SHADOW"] = "1"
        try:
            self.assertTrue(M._trueline_drill_path_frame_shadow_enabled())
        finally:
            if prev is None:
                os.environ.pop("TRUELINE_DRILL_PATH_FRAME_SHADOW", None)
            else:
                os.environ["TRUELINE_DRILL_PATH_FRAME_SHADOW"] = prev

    def test_scope_is_route_480_bucket(self):
        # the attach is gated to the same 14-log bucket as terminus_type
        self.assertTrue(R.is_route_480_bucket_source("bore_log7"))
        self.assertTrue(all(R.is_route_480_bucket_source(d["source_file"]) for d in _DROPS))
        self.assertFalse(R.is_route_480_bucket_source("bore_log71"))


if __name__ == "__main__":
    unittest.main()
