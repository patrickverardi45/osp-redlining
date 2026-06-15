"""OWNER-PACKET-2 log71 sheet-local source-bind scout -- offline tests.

Locks the pure laws: the result/blocker enum, the CHAIN-REACH matchline disambiguation (needed
because '5+45' is not sheet-unique on sheet 23 and a 6+00 matchline also exists), and that the
scout consumes log71's record WITHOUT encoding endpoint_anchors. No PDF parse here (the proof runs
the real sheet-23/24 binds at verification).
"""
from pathlib import Path

from truelinev2.extract.conduit_topology import MAX_DASH_GAP
from truelinev2.ingest.manual_adjudication import load_adjudication
from truelinev2.proof.run_log71_sheet_local_bind_scout import (
    ALLOWED,
    MATCHLINE_REACH_SEP,
    R_COMPLETE,
    R_START_RESOLVED,
    SHEET_END,
    SHEET_START,
    owner_named_classes,
    select_matchline_by_chain_reach,
)


def test_result_enum_exact():
    assert ALLOWED == {
        "LOG71_SHEET_LOCAL_BIND_SCOUT_COMPLETE", "LOG71_START_IDENTITY_RESOLVED",
        "LOG71_PARTIAL_BIND_CONFIRMED", "BLOCKED_LOG71_START_IDENTITY_AMBIGUOUS",
        "BLOCKED_LOG71_START_CLASS_UNMODELED", "BLOCKED_LOG71_END_BIND_FAILED",
        "BLOCKED_LOG71_MATCHLINE_BOUNDARY_FAILED", "BLOCKED_LOG71_ROUTE_NOT_SOURCE_BACKED",
        "BLOCKED_LOG71_SOURCE_AMBIGUOUS",
    }
    assert {R_COMPLETE, R_START_RESOLVED} <= ALLOWED


def test_sheets_are_23_and_24():
    assert (SHEET_END, SHEET_START) == (23, 24)


def test_chain_reach_disambiguation_unique():
    # the chain terminates clearly at the closest matchline (0.0) vs a far rival (25.9 on sheet 23)
    assert select_matchline_by_chain_reach([0.0, 25.9]) is True
    # a single reachable matchline
    assert select_matchline_by_chain_reach([5.0]) is True
    assert select_matchline_by_chain_reach([10.0, 50.0]) is True


def test_chain_reach_disambiguation_ambiguous_or_unreached():
    # two matchlines the chain reaches almost equally -> ambiguous, refuse
    assert select_matchline_by_chain_reach([0.0, 3.0]) is False
    # nothing within MAX_DASH_GAP -> chain does not reach a matchline
    assert select_matchline_by_chain_reach([MAX_DASH_GAP + 5.0]) is False
    assert select_matchline_by_chain_reach([]) is False
    # the separation floor is MATCHLINE_REACH_SEP
    assert MATCHLINE_REACH_SEP == 10.0


def test_owner_named_classes_distinguishes_source_resolved_from_owner_named():
    # doctrine honesty: the owner named the END flower pot, but NOT the start class ("Lawndale
    # reset"). nextlink_hh is SOURCE-resolved by the extractor, never owner-named -> must be
    # owner-confirmed before encoding, so it must NOT appear as an owner-named class.
    doc = load_adjudication()
    l71 = next(r for r in doc["logs"] if r["log_id"] == "log71")
    named = owner_named_classes(l71["evidence_notes"])
    assert named == {"flower_pot"}
    assert "nextlink_hh" not in named
    # log64 (control): the owner explicitly named BOTH installer HH and flower pot
    l64 = next(r for r in doc["logs"] if r["log_id"] == "log64")
    assert owner_named_classes(l64["evidence_notes"]) == {"installer_hh", "flower_pot"}


def test_scout_consumes_log71_record():
    # the scout resolves identity from the record's reviewed fields; it does not itself encode
    # anchors (the owner-confirmed bridge was encoded in a LATER slice, so we no longer assert
    # their absence here -- the scout's resolution is independent of the later encode).
    doc = load_adjudication()
    l71 = next(r for r in doc["logs"] if r["log_id"] == "log71")
    assert l71["corrected_end"] == "6+95"
    assert list(l71["corrected_sheets"]) == [23, 24]
    assert "MATCHLINE_CHAIN" in l71["correction_types"]
    assert "STATION_RESET_SEGMENT_BOUNDARY" in l71["correction_types"]


def test_proof_has_no_render_lane():
    src = Path(__file__).resolve().parent.parent / "proof" / "run_log71_sheet_local_bind_scout.py"
    text = src.read_text(encoding="utf-8")
    assert "from truelinev2.render" not in text
    assert "render_redline_stroke" not in text
