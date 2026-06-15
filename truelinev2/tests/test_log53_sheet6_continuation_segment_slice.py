"""OWNER-PACKET-2 log53 sheet-6 continuation segment -- offline tests.

Locks: the typed result enum, the continuation-callout grammar, the fact that the 26+38
endpoint is a flower_pot the dialect ALREADY models (no new dialect work needed), and the
end-anchor bridge that points the continuation to sheet 6. No PDF parse here (the proof runs
the real sheet-6 segment).
"""
from truelinev2.extract.structure_position import BRENHAM_STRUCTURE_LAYERS
from truelinev2.ingest.manual_adjudication import load_adjudication
from truelinev2.proof.run_log53_sheet6_continuation_segment_slice import (
    ALLOWED,
    R_CHAIN_NOT_CONNECTED,
    R_LABEL_NOT_FOUND,
    R_POT_NOT_FOUND,
    R_PROVEN,
    _CALLOUT_RE,
)


def test_result_enum_exact():
    assert ALLOWED == {
        "SHEET6_CONTINUATION_SEGMENT_PROVEN",
        "SHEET6_CONTINUATION_LABEL_FOUND_ENDPOINT_BLOCKED",
        "SHEET6_CONTINUATION_CHAIN_FOUND_ENDPOINT_BLOCKED",
        "SHEET6_CONTINUATION_CHAIN_AMBIGUOUS",
        "BLOCKED_SHEET6_CONTINUATION_LABEL_NOT_FOUND",
        "BLOCKED_SHEET6_CONTINUATION_LABEL_NOT_UNIQUE",
        "BLOCKED_SHEET6_CONDUIT_NOT_FOUND",
        "BLOCKED_SHEET6_FLOWER_POT_NOT_FOUND",
        "BLOCKED_SHEET6_FLOWER_POT_NOT_UNIQUE",
        "BLOCKED_SHEET6_CHAIN_NOT_CONNECTED",
        "BLOCKED_NO_SAFE_SHEET6_SEGMENT",
    }
    assert {R_PROVEN, R_LABEL_NOT_FOUND, R_POT_NOT_FOUND, R_CHAIN_NOT_CONNECTED} <= ALLOWED


def test_continuation_callout_grammar():
    # the printed continuation callout, with/without the second 'STA'
    assert _CALLOUT_RE.search("STA 24+11 TO STA 26+38 DIR. BORE (227') 2-1.25\" HDPE")
    assert _CALLOUT_RE.search("24+11 TO 26+38")
    assert _CALLOUT_RE.search("STA 24+11 TO 26+38")
    # must NOT match the sheet-5 segment (ends at 24+11) or a different run
    assert not _CALLOUT_RE.search("STA 21+63 TO STA 24+11 DIR. BORE (248')")
    assert not _CALLOUT_RE.search("STA 24+11 TO STA 26+39")


def test_flower_pot_endpoint_is_already_modeled():
    # the 26+38 endpoint is a flower_pot -> the dialect already covers it (no new dialect work)
    assert "flower_pot" in BRENHAM_STRUCTURE_LAYERS
    text_layer, symbol_layer, _fill = BRENHAM_STRUCTURE_LAYERS["flower_pot"]
    assert text_layer == "FLOWER POT - TEXT"
    assert symbol_layer == "FLOWER POT"


def test_slice_consumes_end_anchor_bridge():
    doc = load_adjudication()
    l53 = next(r for r in doc["logs"] if r["log_id"] == "log53")
    end = l53["endpoint_anchors"]["end"]
    assert end["boundary_kind"] == "matchline_continuation"
    assert end["continues_to_sheet"] == 6
    assert end["continues_as"] == "STA 24+11 TO STA 26+38"
