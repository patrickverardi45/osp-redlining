"""OWNER-PACKET-2 endpoint-anchor bridge (schema-2) -- offline tests.

Verifies the additive owner endpoint/boundary semantics for log53: present + exact,
identity/boundary ONLY (never coordinates), never authorizing drawing, and inert to
every frozen count. No corpus, no PDF parse, no render, no synthesized geometry.
"""
import copy

import pytest

from truelinev2.ingest.manual_adjudication import (
    BOUNDARY_KIND_ENUM,
    ENDPOINT_CLARITY_ENUM,
    ENDPOINT_STRUCTURE_CLASS_ENUM,
    PLACE_NEEDS_GEOMETRY,
    flag_on_disposition,
    load_adjudication,
    placement_geometry_readiness,
    resolve,
    summarize,
    validate_adjudication,
    validate_endpoint_anchors,
)

# coordinate/geometry key names that must NEVER appear in an anchor payload
_FORBIDDEN_COORD_KEYS = {
    "x", "y", "z", "xc", "yc", "x0", "y0", "x1", "y1", "cx", "cy", "xy",
    "lat", "lon", "lng", "coord", "coords", "coordinate", "coordinates",
    "px", "py", "pixel", "pixels", "point", "points",
    "symbol_xy", "anchor_xy", "stroke", "stroke_points", "geometry", "geom",
}


@pytest.fixture(scope="module")
def doc():
    return load_adjudication()


@pytest.fixture(scope="module")
def rec(doc):
    return {r["log_id"]: r for r in doc["logs"]}


# --- artifact still parses/validates with the new field -------------------------
def test_artifact_still_validates(doc):
    assert validate_adjudication(doc) == []


def test_schema_bumped_to_2(doc):
    assert doc["schema"] == "truelinev2-manual-adjudication-2"


def test_counts_frozen_27_23_4_0_0(doc):
    s = summarize(doc)
    assert (s["original_problem_logs"], s["recoverable_or_correct_as_drawn"],
            s["valid_abstain_no_good"], s["active_unknowns"],
            s["shared_print_owner_source_required_after_review"]) == (27, 23, 4, 0, 0)


# --- log53 endpoint_anchors present + EXACT -------------------------------------
def test_log53_evidence_refs_populated(rec):
    refs = rec["log53"]["evidence_refs"]
    assert refs == ["Screenshot 2026-06-14 032035.png", "Screenshot 2026-06-14 032447.png"]
    assert refs  # no longer empty


def test_log53_start_anchor_exact(rec):
    s = rec["log53"]["endpoint_anchors"]["start"]
    assert s["station"] == "21+63"
    assert s["boundary_kind"] == "structure_terminus"
    assert s["structure_class"] == "nextlink_hh"
    assert s["structure_label"] == "NEXTLINK HH"
    assert "SPLICE POINT 32" in s["owner_note_text"]
    assert s["clarity"] == "CLEAR"
    assert s["evidence_ref"] == "Screenshot 2026-06-14 032035.png"


def test_log53_end_anchor_is_matchline_continuation_not_terminus(rec):
    e = rec["log53"]["endpoint_anchors"]["end"]
    assert e["station"] == "24+11"
    assert e["boundary_kind"] == "matchline_continuation"
    assert e["boundary_kind"] != "structure_terminus"
    assert e["continues_to_sheet"] == 6
    assert e["continues_as"] == "STA 24+11 TO STA 26+38"
    # a continuation is NOT a terminus -> no terminus identity
    assert e["structure_class"] is None
    assert e["structure_label"] is None
    assert e["clarity"] == "CLEAR"
    assert e["evidence_ref"] == "Screenshot 2026-06-14 032447.png"


# --- NO coordinates / pixel geometry anywhere in the payload --------------------
def test_log53_anchor_has_no_coordinate_fields(rec):
    ea = rec["log53"]["endpoint_anchors"]
    for side in ("start", "end"):
        keys = {k.lower() for k in ea[side]}
        assert keys & _FORBIDDEN_COORD_KEYS == set()
        # every value is identity/boundary text or a sheet int -- never a coord pair
        for v in ea[side].values():
            assert not isinstance(v, (list, tuple, float))


# --- log53 remains NON-renderable / needs geometry resolution -------------------
def test_log53_still_needs_geometry(rec):
    out = placement_geometry_readiness(rec["log53"])
    assert out["status"] == PLACE_NEEDS_GEOMETRY
    assert out["has_positioned_geometry"] is False
    # bridge does not add coordinate keys to the readiness dict
    for forbidden in ("x", "y", "stroke_points", "lat", "lon", "coords"):
        assert forbidden not in out
    # the bridge sharpened the blocker without making it geometry-ready
    assert any("matchline continuation" in r for r in out["reasons"])
    assert any("positioned stroke path" in r for r in out["reasons"])


# --- bridge is machine-consumable downstream (resolve + overlay) ----------------
def test_resolve_carries_endpoint_anchors(doc):
    d = resolve(doc)["log53"]
    assert d.endpoint_anchors is not None
    assert d.endpoint_anchors["end"]["boundary_kind"] == "matchline_continuation"
    # a log without the bridge stays None (additive)
    assert resolve(doc)["log44"].endpoint_anchors is None


def test_flag_on_disposition_carries_endpoint_anchors(rec):
    d = flag_on_disposition(rec["log53"])
    assert d["endpoint_anchors"]["start"]["structure_class"] == "nextlink_hh"
    # drawable status unchanged: review_drawable, never auto-placed
    assert d["drawable_status"] == "review_drawable"
    # a log without the bridge -> None
    assert flag_on_disposition(rec["log44"]).get("endpoint_anchors") is None


# --- additive: a record without the field still validates -----------------------
def test_absent_endpoint_anchors_is_valid(rec):
    assert validate_endpoint_anchors(rec["log44"]) == []  # no endpoint_anchors key
    assert "endpoint_anchors" not in rec["log44"]


# --- enums are the documented sets ----------------------------------------------
def test_enums_match_doc_header(doc):
    assert set(doc["endpoint_anchor_boundary_kind_enum"]) == set(BOUNDARY_KIND_ENUM)
    assert set(doc["endpoint_anchor_structure_class_enum"]) == set(ENDPOINT_STRUCTURE_CLASS_ENUM)
    assert set(doc["endpoint_anchor_clarity_enum"]) == set(ENDPOINT_CLARITY_ENUM)


# --- fail-closed validation negatives -------------------------------------------
def test_rejects_coordinate_field(rec):
    bad = copy.deepcopy(rec["log53"])
    bad["endpoint_anchors"]["end"]["x"] = 1234.5
    errs = validate_endpoint_anchors(bad)
    assert any("forbidden coordinate" in e for e in errs)


def test_rejects_stroke_points_field(rec):
    bad = copy.deepcopy(rec["log53"])
    bad["endpoint_anchors"]["end"]["stroke_points"] = [[1, 2], [3, 4]]
    errs = validate_endpoint_anchors(bad)
    assert any("forbidden coordinate" in e for e in errs)


def test_rejects_unknown_anchor_field(rec):
    bad = copy.deepcopy(rec["log53"])
    bad["endpoint_anchors"]["start"]["made_up"] = "nope"
    errs = validate_endpoint_anchors(bad)
    assert any("unknown field" in e for e in errs)


def test_rejects_unknown_boundary_kind(rec):
    bad = copy.deepcopy(rec["log53"])
    bad["endpoint_anchors"]["end"]["boundary_kind"] = "teleporter"
    errs = validate_endpoint_anchors(bad)
    assert any("boundary_kind" in e and "not in enum" in e for e in errs)


def test_rejects_terminus_without_identity(rec):
    bad = copy.deepcopy(rec["log53"])
    bad["endpoint_anchors"]["end"]["boundary_kind"] = "structure_terminus"
    # end has null structure_class/label -> a terminus must be identified
    errs = validate_endpoint_anchors(bad)
    assert any("structure_terminus requires" in e for e in errs)


def test_rejects_continuation_carrying_terminus_identity(rec):
    bad = copy.deepcopy(rec["log53"])
    bad["endpoint_anchors"]["end"]["structure_class"] = "terminal"
    errs = validate_endpoint_anchors(bad)
    assert any("matchline_continuation must NOT carry" in e for e in errs)


def test_rejects_continuation_without_continues_to_sheet(rec):
    bad = copy.deepcopy(rec["log53"])
    del bad["endpoint_anchors"]["end"]["continues_to_sheet"]
    errs = validate_endpoint_anchors(bad)
    assert any("requires continues_to_sheet" in e for e in errs)


def test_rejects_unknown_side(rec):
    bad = copy.deepcopy(rec["log53"])
    bad["endpoint_anchors"]["middle"] = {"boundary_kind": "mid_run"}
    errs = validate_endpoint_anchors(bad)
    assert any("unknown side" in e for e in errs)


def test_tampered_artifact_fails_whole_validation(doc):
    bad = copy.deepcopy(doc)
    l53 = next(r for r in bad["logs"] if r["log_id"] == "log53")
    l53["endpoint_anchors"]["end"]["pixel"] = [10, 20]
    errs = validate_adjudication(bad)
    assert any("log53" in e and "forbidden coordinate" in e for e in errs)
