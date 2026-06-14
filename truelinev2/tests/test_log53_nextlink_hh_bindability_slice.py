"""OWNER-PACKET-2 log53 NEXTLINK HH start-anchor bindability -- offline tests.

Locks the proof's pure laws: the mission outcome enum, the verdict->status mapping,
that the slice consumes the committed endpoint_anchors.start, and that it NEVER wires
nextlink_hh into the shared dialect. No PDF parse here (the proof runs the real sheet-5
binding attempt).
"""
from truelinev2.extract.structure_position import (
    BRENHAM_STRUCTURE_LAYERS,
    LABEL_BOX_NOT_UNIQUE,
    LABEL_WORD_NOT_UNIQUE,
    LEADER_NOT_UNIQUE,
    POSITION_BOUND,
    SYMBOL_CLASS_MISMATCH,
    SYMBOL_NOT_UNIQUE,
    StructurePositionVerdict,
)
from truelinev2.ingest.manual_adjudication import load_adjudication
from truelinev2.proof.run_log53_nextlink_hh_bindability_slice import (
    ALLOWED,
    B_CLASS,
    B_LOCATOR,
    B_NOT_FOUND,
    B_NOT_UNIQUE,
    B_NO_POS,
    B_POS_NOT_UNIQUE,
    PROOF_LOCAL_LAYER_TABLE,
    S_BOUND,
    _verdict_to_status,
)


def _v(result, **detail):
    return StructurePositionVerdict(label_text="x", structure_class="nextlink_hh",
                                    result=result, detail=detail)


def test_allowed_status_enum_exact():
    assert ALLOWED == {
        "POSITION_BOUND",
        "BLOCKED_SYMBOL_CLASS_MISMATCH",
        "BLOCKED_LABEL_NOT_FOUND",
        "BLOCKED_LABEL_NOT_UNIQUE",
        "BLOCKED_LOCATOR_NOT_AVAILABLE",
        "BLOCKED_SOURCE_POSITION_NOT_UNIQUE",
        "BLOCKED_NO_SOURCE_POSITION",
    }


def test_verdict_to_status_mapping():
    assert _verdict_to_status(_v(POSITION_BOUND)) == (S_BOUND, 5)
    assert _verdict_to_status(_v(SYMBOL_CLASS_MISMATCH)) == (B_CLASS, 4)
    assert _verdict_to_status(_v(SYMBOL_NOT_UNIQUE)) == (B_POS_NOT_UNIQUE, 3)
    assert _verdict_to_status(_v(LEADER_NOT_UNIQUE)) == (B_LOCATOR, 2)
    assert _verdict_to_status(_v(LABEL_BOX_NOT_UNIQUE)) == (B_LOCATOR, 1)
    assert _verdict_to_status(_v(LABEL_WORD_NOT_UNIQUE, word_hits=0)) == (B_NOT_FOUND, 0)
    assert _verdict_to_status(_v(LABEL_WORD_NOT_UNIQUE, word_hits=2)) == (B_NOT_UNIQUE, 0)


def test_no_dialect_wiring():
    # the production dialect is NOT mutated by this slice
    assert "nextlink_hh" not in BRENHAM_STRUCTURE_LAYERS
    assert set(BRENHAM_STRUCTURE_LAYERS) == {"installer_hh", "terminal_port_hh", "flower_pot"}
    # the nextlink_hh mapping lives ONLY in the proof-local table
    assert "nextlink_hh" in PROOF_LOCAL_LAYER_TABLE
    assert PROOF_LOCAL_LAYER_TABLE["nextlink_hh"][1] == "NEXTLINK"  # symbol layer


def test_slice_consumes_start_anchor_bridge():
    doc = load_adjudication()
    l53 = next(r for r in doc["logs"] if r["log_id"] == "log53")
    start = l53["endpoint_anchors"]["start"]
    assert start["structure_class"] == "nextlink_hh"
    assert start["structure_label"] == "NEXTLINK HH"
    assert start["station"] == "21+63"
    assert start["boundary_kind"] == "structure_terminus"
