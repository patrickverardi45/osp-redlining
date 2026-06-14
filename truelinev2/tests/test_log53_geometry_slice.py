"""OWNER-PACKET-2 Geometry Slice 1 (log53) -- offline tests.

Tests the pure verdict->classification mapping and that log53's reviewed facts feed the
solver correctly. No PDF parse here (the proof runs the real sheet-5 geometry).
"""
from truelinev2.extract.tick_path import (
    EXHAUSTED,
    MULTIPLE,
    NOT_COVERED,
    READY,
    STRUCTURE_REQUIRED,
)
from truelinev2.ingest.manual_adjudication import (
    apply_adjudications,
    load_adjudication,
)
from truelinev2.proof.run_log53_geometry_slice import classify_geometry
from truelinev2.stations import parse_station


def test_classify_geometry_mapping():
    assert classify_geometry(READY, 50) == "GEOMETRY_READY"
    assert classify_geometry(STRUCTURE_REQUIRED, 50) == "BLOCKED_STRUCTURE_IDENTITY_BINDING_REQUIRED"
    assert classify_geometry(NOT_COVERED, 50) == "BLOCKED_NO_POSITIONED_TICK_PATH"
    assert classify_geometry(MULTIPLE, 50) == "BLOCKED_AMBIGUOUS_SHEET_GEOMETRY"
    assert classify_geometry(EXHAUSTED, 50) == "BLOCKED_ENGINE_LAW"


def test_classify_no_ladder_overrides():
    # zero clean ladder ticks -> NO_ROUTE_LADDER regardless of token
    assert classify_geometry(READY, 0) == "BLOCKED_NO_ROUTE_LADDER"
    assert classify_geometry(NOT_COVERED, 0) == "BLOCKED_NO_ROUTE_LADDER"


def test_log53_facts_from_artifact():
    doc = load_adjudication()
    l53 = next(r for r in doc["logs"] if r["log_id"] == "log53")
    assert l53["corrected_start"] == "21+63"
    assert l53["corrected_end"] == "24+11"
    assert l53["corrected_sheets"] == [5]
    assert l53["span_ft"] == 248.0
    # absolute plan stations parse and the span matches the reviewed 248'
    assert parse_station("24+11") - parse_station("21+63") == 248.0


def test_log53_is_review_drawable_under_flag():
    doc = load_adjudication()
    baseline = {r["log_id"]: {"bore_id": r["log_id"], "completion_bucket": "PICK_CARD_REVIEW",
                              "source_family": r.get("parent") or r["log_id"], "can_draw_now": False}
                for r in doc["logs"]}
    on = apply_adjudications(baseline, enabled=True, doc=doc)
    assert on["log53"]["adjudication"]["drawable_status"] == "review_drawable"
