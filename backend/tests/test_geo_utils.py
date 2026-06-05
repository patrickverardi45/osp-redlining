"""Unit tests for the extracted pure geo helpers (PR-1 cleanup) + a backend.main import smoke.

Covers app/utils/geo.py and confirms backend.main still imports with the helpers re-exported
under the same names.

COMMAND (from repo root):
    python -m pytest backend/tests/test_geo_utils.py -v
"""
from __future__ import annotations

import os

os.environ.setdefault("TRUELINE_JWT_SECRET", "geo-utils-test-secret")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "geo-utils-auth-test-secret")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

from app.utils import geo


def test_haversine_known_small_delta():
    # ~0.001 deg latitude near 30N ≈ 365 ft (1 deg lat ≈ 365k ft).
    d = geo._haversine_feet(30.0, -96.0, 30.001, -96.0)
    assert 350.0 < d < 380.0
    # zero distance + symmetry
    assert geo._haversine_feet(30.0, -96.0, 30.0, -96.0) == 0.0
    assert abs(geo._haversine_feet(30.0, -96.0, 30.001, -96.0)
               - geo._haversine_feet(30.001, -96.0, 30.0, -96.0)) < 1e-6


def test_route_length_sums_segments():
    coords = [(30.0, -96.0), (30.001, -96.0), (30.002, -96.0)]
    seg = geo._haversine_feet(30.0, -96.0, 30.001, -96.0)
    assert abs(geo._route_length_ft(coords) - 2 * seg) < 1e-6
    # empty / single-point -> 0.0 (no segments)
    assert geo._route_length_ft([]) == 0.0
    assert geo._route_length_ft([(30.0, -96.0)]) == 0.0


def test_route_bbox_min_max():
    bb = geo._route_bbox([(30.0, -96.5), (30.2, -96.1), (29.9, -96.3)])
    assert bb == {"min_lat": 29.9, "max_lat": 30.2, "min_lon": -96.5, "max_lon": -96.1}
    # empty -> None; degenerate point (len < 2) -> None
    assert geo._route_bbox([]) is None
    assert geo._route_bbox([(30.0,)]) is None


def test_backend_main_reexports_same_objects():
    from backend import main as M  # import smoke — monolith still loads
    assert M._haversine_feet is geo._haversine_feet
    assert M._route_length_ft is geo._route_length_ft
    assert M._route_bbox is geo._route_bbox
