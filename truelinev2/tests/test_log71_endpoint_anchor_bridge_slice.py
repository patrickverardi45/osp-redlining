"""OWNER-PACKET-2 log71 endpoint-anchor bridge -- offline tests.

Locks the encoded log71 bridge: BOTH endpoints are structure_terminus (start owner-CONFIRMED
nextlink_hh; end owner-NAMED flower_pot), no coordinates, the 5+45 matchline is route context in
the end anchor (NOT a third anchor; schema is start/end termini only), the bridge is consumable
yet never auto-placed, it moves log71 PARTIAL -> SOURCE_BINDABLE_NOW, and ONLY log53+log64+log71
carry the bridge. No PDF parse, no truth table.
"""
import pytest

from truelinev2.ingest.manual_adjudication import (
    flag_on_disposition,
    load_adjudication,
    resolve,
    summarize,
    validate_adjudication,
    validate_endpoint_anchors,
)
from truelinev2.proof.run_log53_primitives_cohort_replay import (
    MODELED_TERMINUS_CLASSES,
    SOURCE_BINDABLE_NOW,
    classify_record,
)
from truelinev2.proof.run_log71_endpoint_anchor_bridge_slice import (
    ALLOWED,
    EXPECTED_ANCHOR_LOGS,
    R_ENCODED,
)

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
def l71(doc):
    return next(r for r in doc["logs"] if r["log_id"] == "log71")


def test_result_enum_exact():
    assert ALLOWED == {
        "LOG71_ENDPOINT_ANCHORS_ENCODED", "BLOCKED_LOG71_SCHEMA_GAP",
        "BLOCKED_LOG71_OWNER_CONFIRMATION_NOT_REPRESENTABLE",
        "BLOCKED_LOG71_MATCHLINE_ANCHOR_AMBIGUOUS",
        "BLOCKED_LOG71_ENDPOINT_ANCHOR_VALIDATION_FAILED",
    }
    assert R_ENCODED == "LOG71_ENDPOINT_ANCHORS_ENCODED"


def test_artifact_still_validates(doc):
    assert validate_adjudication(doc) == []


def test_log71_anchor_schema_valid(l71):
    assert l71.get("endpoint_anchors")
    assert validate_endpoint_anchors(l71) == []


def test_log71_start_is_owner_confirmed_nextlink_hh(l71):
    s = l71["endpoint_anchors"]["start"]
    assert s["station"] == "7+50"
    assert s["boundary_kind"] == "structure_terminus"
    assert s["structure_class"] == "nextlink_hh"
    assert s["structure_label"] == "NEXTLINK HH"
    assert s["clarity"] == "CLEAR"
    # the class came from owner CONFIRMATION (recorded in owner_note_text), not the original notes
    assert "OWNER-CONFIRMED" in s["owner_note_text"].upper()
    assert "7+50" in l71["evidence_notes"]        # the reset station IS owner-documented


def test_log71_end_is_owner_named_flower_pot(l71):
    e = l71["endpoint_anchors"]["end"]
    assert e["station"] == "6+95"
    assert e["boundary_kind"] == "structure_terminus"
    assert e["structure_class"] == "flower_pot"
    assert e["structure_label"] == "FLOWER POT"
    # the end is owner-NAMED directly in evidence_notes
    up = l71["evidence_notes"].upper()
    assert "6+95" in up and "FLOWER POT" in up


def test_both_termini_classes_are_modeled(l71):
    for side in ("start", "end"):
        assert l71["endpoint_anchors"][side]["structure_class"] in MODELED_TERMINUS_CLASSES


def test_matchline_5_45_is_route_context_not_a_third_anchor(l71):
    ea = l71["endpoint_anchors"]
    assert set(ea) == {"start", "end"}                 # schema is start/end termini only
    assert "5+45" in ea["end"]["owner_note_text"]      # the crossing is preserved as route context
    # the end is a real terminus, NOT a matchline_continuation
    assert ea["end"]["boundary_kind"] == "structure_terminus"


def test_anchors_have_no_coordinate_fields(l71):
    for side in ("start", "end"):
        keys = {k.lower() for k in l71["endpoint_anchors"][side]}
        assert keys & _FORBIDDEN_COORD_KEYS == set()
        for v in l71["endpoint_anchors"][side].values():
            assert not isinstance(v, (list, tuple, float))


def test_bridge_consumable_but_never_auto_placed(doc, l71):
    assert resolve(doc)["log71"].endpoint_anchors is not None
    f = flag_on_disposition(l71)
    assert f["endpoint_anchors"]["start"]["structure_class"] == "nextlink_hh"
    assert f["drawable_status"] == "review_drawable"


def test_log71_moves_to_source_bindable_now(l71):
    r = classify_record(l71)
    assert r["classification"] == SOURCE_BINDABLE_NOW
    assert r["blockers"] == []


def test_log53_log64_log71_bridges_present(doc):
    # subset, not exact: later slices may add more bridges; this guarantees these three are present
    with_anchors = {r["log_id"] for r in doc["logs"] if r.get("endpoint_anchors")}
    assert set(EXPECTED_ANCHOR_LOGS) <= with_anchors
    assert EXPECTED_ANCHOR_LOGS == ("log53", "log64", "log71")


def test_log53_log64_bridges_untouched(doc):
    rec = {r["log_id"]: r for r in doc["logs"]}
    assert rec["log53"]["endpoint_anchors"]["end"]["boundary_kind"] == "matchline_continuation"
    assert rec["log64"]["endpoint_anchors"]["start"]["structure_class"] == "installer_hh"


def test_summarize_counts_unchanged(doc):
    s = summarize(doc)
    assert (s["original_problem_logs"], s["recoverable_or_correct_as_drawn"],
            s["valid_abstain_no_good"], s["active_unknowns"],
            s["shared_print_owner_source_required_after_review"]) == (27, 23, 4, 0, 0)
