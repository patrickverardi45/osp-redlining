"""OWNER-PACKET-2 placement / redline readiness adapter -- offline tests.

Verifies the pure geometry-readiness classifier against the real reviewed artifact and
synthetic records. No PDF parse, no render call, no synthesized geometry.
"""
import pytest

from truelinev2.ingest.manual_adjudication import (
    PLACE_BLOCKED_ENGINE_LAW,
    PLACE_BLOCKED_SOURCE_VERIFY,
    PLACE_NEEDS_GEOMETRY,
    PLACE_RENDERABLE,
    load_adjudication,
    placement_geometry_readiness,
)
from truelinev2.render.crop import REDLINE_STROKE_RGB

PLACE_STATUSES = {PLACE_RENDERABLE, PLACE_NEEDS_GEOMETRY,
                  PLACE_BLOCKED_SOURCE_VERIFY, PLACE_BLOCKED_ENGINE_LAW}


@pytest.fixture(scope="module")
def doc():
    return load_adjudication()


@pytest.fixture(scope="module")
def rec(doc):
    return {r["log_id"]: r for r in doc["logs"]}


def _review_drawable_ids(doc):
    return sorted(r["log_id"] for r in doc["logs"]
                  if r["status"] in ("RECOVERED", "CORRECT_AS_DRAWN") and r["allowed_to_draw"])


# --- the 22 review-drawable rows ------------------------------------------------
def test_exactly_22_review_drawable(doc):
    assert len(_review_drawable_ids(doc)) == 22


@pytest.mark.parametrize("lid", _review_drawable_ids(load_adjudication()))
def test_review_drawable_needs_geometry(rec, lid):
    """No review-drawable row carries a positioned stroke path -> NEEDS_GEOMETRY_RESOLUTION."""
    out = placement_geometry_readiness(rec[lid])
    assert out["status"] == PLACE_NEEDS_GEOMETRY
    assert out["has_positioned_geometry"] is False
    # the renderer-needs-a-positioned-path reason is always present (no coordinate geometry)
    assert any("positioned stroke path" in r for r in out["reasons"])


def test_every_status_in_enum(doc, rec):
    for r in doc["logs"]:
        assert placement_geometry_readiness(rec[r["log_id"]])["status"] in PLACE_STATUSES


# --- log44 / abstains never renderable ------------------------------------------
def test_log44_blocked_source_verification(rec):
    out = placement_geometry_readiness(rec["log44"])
    assert out["status"] == PLACE_BLOCKED_SOURCE_VERIFY
    assert out["has_positioned_geometry"] is False


@pytest.mark.parametrize("lid", ["log5", "log31", "log38", "log43"])
def test_abstain_never_renderable(rec, lid):
    out = placement_geometry_readiness(rec[lid])
    assert out["status"] != PLACE_RENDERABLE
    assert out["has_positioned_geometry"] is False


# --- specific missing-geometry reasons are computed, not blanket -----------------
def test_multi_sheet_reason(rec):
    out = placement_geometry_readiness(rec["log46"])  # sheets [10,13,14]
    assert any("cross-sheet matchline" in r for r in out["reasons"])


def test_reset_origin_reason(rec):
    out = placement_geometry_readiness(rec["log6"])  # reset 0+56=0+00, start 0+00
    assert any("reset-local origin" in r for r in out["reasons"])


def test_no_sheet_reason(rec):
    out = placement_geometry_readiness(rec["log59"])  # corrected_sheets []
    assert any("no recorded sheet" in r for r in out["reasons"])


# --- nothing renderable from the artifact alone ---------------------------------
def test_zero_renderable_from_artifact(doc, rec):
    statuses = [placement_geometry_readiness(rec[l])["status"] for l in _review_drawable_ids(doc)]
    assert statuses.count(PLACE_RENDERABLE) == 0


def test_adapter_invents_no_coordinates(rec):
    """The readiness dict carries no x/y/coordinate/stroke_points fields."""
    out = placement_geometry_readiness(rec["log53"])
    for forbidden in ("x", "y", "stroke_points", "lat", "lon", "coords"):
        assert forbidden not in out


# --- red-stroke law re-affirmed -------------------------------------------------
def test_canonical_stroke_color_is_red():
    r, g, b = REDLINE_STROKE_RGB
    assert r >= 200 and g <= 80 and b <= 80
