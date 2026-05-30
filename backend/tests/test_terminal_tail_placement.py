"""Target #14 — Terminal Tail AP-anchored placement override tests.

Locks the pure resolver `resolve_terminal_tail_route_for_ap`:
- returns the UNIQUE Terminal Tail KMZ route whose endpoint is at the AP terminal AND
  whose length matches the PDF run length within tolerance;
- returns None when zero match, when >=2 match (ambiguous — no guessing), when the
  only tail's length is off, when the tail endpoint is too far from the AP, when the
  AP terminal is absent, and for non-tail folders (Vacant Pipe / House Drop / backbone).
The override itself (main.py) is an isolated post-rebuild pass proven by
scripts/bore_log7_before_after.py (before/after: only bore_log7 changes).
No placement / scoring / geometry of any other log is touched.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "backend"))

from backend.app.core import pdf_ap_route_resolver as R

FT = 1.0 / 364567.0          # ~1 ft in latitude degrees near lat 30 (lon held constant)
AP_LAT, AP_LON = 30.150000, -96.380000
RUN = 451.0


def _route(rid, folder, coords, length_ft):
    # length_ft is the catalog-populated field the resolver reads (NOT computed from coords).
    return {"route_id": rid, "route_name": rid, "source_folder": folder,
            "route_role": "x", "length_ft": float(length_ft), "coords": [list(c) for c in coords]}


def _tail_at_ap(rid, length_ft, ap_at_coord0=True, offset_from_ap_ft=0.0):
    """A Terminal Tail running north `length_ft` from a point `offset_from_ap_ft` from AP."""
    base = (AP_LAT + offset_from_ap_ft * FT, AP_LON)
    far = (base[0] + length_ft * FT, AP_LON)
    coords = [base, far] if ap_at_coord0 else [far, base]
    return _route(rid, "Connections / Terminal Tail", coords, length_ft)


AP_FEATURES = [{"name": "163", "folder_path": "Nodes / Terminal Port Handhole",
                "lat": AP_LAT, "lon": AP_LON}]


class TestResolveTerminalTail(unittest.TestCase):

    def test_unique_length_matched_tail_at_ap(self):
        cat = [
            _tail_at_ap("route_469", 459.0),                              # MATCH (459 ≈ 451)
            _route("route_533", "Connections / Vacant Pipe", [(AP_LAT, AP_LON), (AP_LAT + 194 * FT, AP_LON)], 194.0),  # wrong folder
            _route("route_375", "Connections / House Drop", [(AP_LAT, AP_LON), (AP_LAT + 52 * FT, AP_LON)], 52.0),    # wrong folder
            _tail_at_ap("route_900", 100.0),                             # tail at AP but wrong length
            _tail_at_ap("route_901", 459.0, offset_from_ap_ft=200.0),    # right length, endpoint 200 ft off AP
        ]
        self.assertEqual(
            R.resolve_terminal_tail_route_for_ap(163, AP_FEATURES, cat, run_len_ft=RUN),
            "route_469")

    def test_coord_order_irrelevant(self):
        # tail with AP at coords[-1] (reversed) still resolves.
        cat = [_tail_at_ap("route_469", 459.0, ap_at_coord0=False)]
        self.assertEqual(
            R.resolve_terminal_tail_route_for_ap(163, AP_FEATURES, cat, run_len_ft=RUN),
            "route_469")

    def test_ambiguous_two_tails_returns_none(self):
        cat = [_tail_at_ap("route_469", 459.0), _tail_at_ap("route_470", 455.0)]
        self.assertIsNone(
            R.resolve_terminal_tail_route_for_ap(163, AP_FEATURES, cat, run_len_ft=RUN))

    def test_length_mismatch_returns_none(self):
        cat = [_tail_at_ap("route_469", 200.0)]   # |200-451| > 10%
        self.assertIsNone(
            R.resolve_terminal_tail_route_for_ap(163, AP_FEATURES, cat, run_len_ft=RUN))

    def test_endpoint_too_far_returns_none(self):
        cat = [_tail_at_ap("route_469", 459.0, offset_from_ap_ft=200.0)]  # 200 ft off AP
        self.assertIsNone(
            R.resolve_terminal_tail_route_for_ap(163, AP_FEATURES, cat, run_len_ft=RUN))

    def test_no_tail_only_backbone_returns_none(self):
        cat = [_route("route_479", "Connections / underground cable",
                      [(AP_LAT, AP_LON), (AP_LAT + 459 * FT, AP_LON)], 459.0)]   # backbone, not a tail
        self.assertIsNone(
            R.resolve_terminal_tail_route_for_ap(163, AP_FEATURES, cat, run_len_ft=RUN))

    def test_ap_not_found_returns_none(self):
        cat = [_tail_at_ap("route_469", 459.0)]
        self.assertIsNone(
            R.resolve_terminal_tail_route_for_ap(999, AP_FEATURES, cat, run_len_ft=RUN))

    def test_ap_must_be_terminal_port_folder(self):
        # an AP-named node in a NON-terminal folder is not an AP anchor.
        feats = [{"name": "163", "folder_path": "Nodes / Flower Pot", "lat": AP_LAT, "lon": AP_LON}]
        cat = [_tail_at_ap("route_469", 459.0)]
        self.assertIsNone(
            R.resolve_terminal_tail_route_for_ap(163, feats, cat, run_len_ft=RUN))

    def test_no_run_len_endpoint_only_unique(self):
        # without a run-length gate, the single tail at the AP still resolves uniquely.
        cat = [_tail_at_ap("route_469", 459.0)]
        self.assertEqual(
            R.resolve_terminal_tail_route_for_ap(163, AP_FEATURES, cat, run_len_ft=None),
            "route_469")

    def test_pure_no_raise_on_garbage(self):
        self.assertIsNone(R.resolve_terminal_tail_route_for_ap(None, None, None, run_len_ft=None))


if __name__ == "__main__":
    unittest.main()
