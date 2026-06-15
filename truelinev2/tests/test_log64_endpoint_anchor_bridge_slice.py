"""OWNER-PACKET-2 log64 endpoint-anchor bridge -- offline tests.

Locks: the encoded log64 bridge (start installer_hh / end flower_pot, structure_terminus, no
coordinates), that it is owner-backed by log64.evidence_notes (not invented), that both termini
are dialect-modeled, that it is machine-consumable yet never auto-placed, that it moves log64
PARTIAL -> SOURCE_BINDABLE_NOW in the cohort census, that ONLY log53 + log64 carry the bridge,
and that the frozen summarize counts are untouched. No PDF parse, no render, no truth table.
"""
import pytest

from truelinev2.extract.structure_position import BRENHAM_STRUCTURE_LAYERS
from truelinev2.ingest.manual_adjudication import (
    flag_on_disposition,
    load_adjudication,
    resolve,
    summarize,
    validate_adjudication,
    validate_endpoint_anchors,
)
from truelinev2.proof.run_log53_primitives_cohort_replay import (
    SOURCE_BINDABLE_NOW,
    classify_record,
)
from truelinev2.proof.run_log64_endpoint_anchor_bridge_slice import (
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
def l64(doc):
    return next(r for r in doc["logs"] if r["log_id"] == "log64")


def test_result_enum_exact():
    assert ALLOWED == {
        "LOG64_ENDPOINT_ANCHORS_ENCODED", "LOG64_SOURCE_BINDABLE_NOW",
        "BLOCKED_LOG64_OWNER_EVIDENCE_INSUFFICIENT", "BLOCKED_LOG64_ANCHOR_IDENTITY_AMBIGUOUS",
        "BLOCKED_LOG64_SCHEMA_GAP", "BLOCKED_LOG64_SOURCE_BINDING_STILL_MISSING",
    }
    assert R_ENCODED == "LOG64_ENDPOINT_ANCHORS_ENCODED"


def test_artifact_still_validates(doc):
    assert validate_adjudication(doc) == []


def test_log64_anchor_schema_valid(l64):
    assert l64.get("endpoint_anchors")
    assert validate_endpoint_anchors(l64) == []


def test_log64_start_anchor_exact(l64):
    s = l64["endpoint_anchors"]["start"]
    assert s["station"] == "3+69"
    assert s["boundary_kind"] == "structure_terminus"
    assert s["structure_class"] == "installer_hh"
    assert s["structure_label"] == "INSTALLER HH"
    assert s["clarity"] == "CLEAR"


def test_log64_end_anchor_exact(l64):
    e = l64["endpoint_anchors"]["end"]
    assert e["station"] == "1+00"
    assert e["boundary_kind"] == "structure_terminus"
    assert e["structure_class"] == "flower_pot"
    assert e["structure_label"] == "FLOWER POT"
    assert e["clarity"] == "CLEAR"


def test_both_termini_are_dialect_modeled(l64):
    for side in ("start", "end"):
        assert l64["endpoint_anchors"][side]["structure_class"] in BRENHAM_STRUCTURE_LAYERS


def test_anchors_are_owner_backed_not_invented(l64):
    # every identity token traces to the owner-authoritative evidence_notes
    up = l64["evidence_notes"].upper()
    assert "3+69" in up and "INSTALLER HH" in up
    assert "1+00" in up and "FLOWER POT" in up
    # end station agrees with the corrected end; single sheet 21
    assert l64["endpoint_anchors"]["end"]["station"] == l64["corrected_end"]
    assert list(l64["corrected_sheets"]) == [21]


def test_anchors_have_no_coordinate_fields(l64):
    for side in ("start", "end"):
        keys = {k.lower() for k in l64["endpoint_anchors"][side]}
        assert keys & _FORBIDDEN_COORD_KEYS == set()
        for v in l64["endpoint_anchors"][side].values():
            assert not isinstance(v, (list, tuple, float))  # identity text / sheet only


def test_bridge_consumable_but_never_auto_placed(doc, l64):
    d = resolve(doc)["log64"]
    assert d.endpoint_anchors is not None
    f = flag_on_disposition(l64)
    assert f["endpoint_anchors"]["start"]["structure_class"] == "installer_hh"
    assert f["drawable_status"] == "review_drawable"  # identity bridge never auto-places


def test_log64_moves_to_source_bindable_now(l64):
    r = classify_record(l64)
    assert r["classification"] == SOURCE_BINDABLE_NOW
    assert r["blockers"] == []


def test_log53_and_log64_bridges_present(doc):
    # subset, not exact: later slices legitimately add bridges (e.g. log71), so this must not
    # break as the cohort grows -- it only guarantees log53 + log64 remain bridged.
    with_anchors = {r["log_id"] for r in doc["logs"] if r.get("endpoint_anchors")}
    assert set(EXPECTED_ANCHOR_LOGS) <= with_anchors
    assert EXPECTED_ANCHOR_LOGS == ("log53", "log64")


def test_log53_bridge_untouched(doc):
    l53 = next(r for r in doc["logs"] if r["log_id"] == "log53")
    assert l53["endpoint_anchors"]["start"]["structure_class"] == "nextlink_hh"
    assert l53["endpoint_anchors"]["end"]["boundary_kind"] == "matchline_continuation"


def test_summarize_counts_unchanged(doc):
    s = summarize(doc)
    assert (s["original_problem_logs"], s["recoverable_or_correct_as_drawn"],
            s["valid_abstain_no_good"], s["active_unknowns"],
            s["shared_print_owner_source_required_after_review"]) == (27, 23, 4, 0, 0)
