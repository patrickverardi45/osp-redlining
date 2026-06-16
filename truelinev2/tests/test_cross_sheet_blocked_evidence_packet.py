"""CROSS_SHEET BLOCKED evidence-target packet -- offline + PDF-gated tests.

Locks the packet's pure laws: the result enum; the included set is EXACTLY the live ledger CROSS_SHEET
class (6) = SOURCE_BLOCKED(log48/67/69/70) + IDENTITY_HELD(log11/47), disjoint; log11/log47 each carry one
owner-named flower_pot terminus and stay unencoded; the six carry NO endpoint_anchors (encodes nothing);
and the slice reuses the SHIPPED match.frames grammar + the cross_sheet scout, defining no new frame math.
The heavy read-only equation extraction (the conflicting 17<->20 crossings; log48's direct 10<->12
candidate) is verified PDF-gated by running the proof.
"""
import json
import os
from pathlib import Path

import pytest

from truelinev2.config import _REPO_ROOT
from truelinev2.ingest.manual_adjudication import load_adjudication
from truelinev2.proof.run_all_redlines_closure_ledger import CROSS_SHEET, build_ledger
from truelinev2.proof.run_brenham_corpus import PDF
from truelinev2.proof.run_cross_sheet_frame_join_scout import EXPECTED_BLOCKED, EXPECTED_SOURCE_BACKED
from truelinev2.seam import ELIGIBLE_EXEMPLARS
from truelinev2.proof.run_cross_sheet_blocked_evidence_packet import (
    ALLOWED,
    IDENTITY_HELD,
    INCLUDED,
    R_READY,
    SOURCE_BLOCKED,
    main,
)

DOC = load_adjudication()
REC = {r["log_id"]: r for r in DOC["logs"]}
TRUTH = _REPO_ROOT / "data" / "outputs" / "final_engine_truth_table" / "final_engine_truth_table.json"
PROOF = Path(__file__).resolve().parent.parent / "proof" / "run_cross_sheet_blocked_evidence_packet.py"
OUT = _REPO_ROOT / "data" / "outputs" / "cross_sheet_blocked_evidence_packet"


def test_result_enum_exact():
    assert ALLOWED == {
        "CROSS_SHEET_BLOCKED_EVIDENCE_PACKET_READY",
        "BLOCKED_PACKET_SET_DRIFTED",
        "BLOCKED_PACKET_JOIN_NOT_ACTUALLY_BLOCKED",
        "BLOCKED_PACKET_EVIDENCE_NOT_EXTRACTED",
        "BLOCKED_PACKET_SILENTLY_ENCODED",
    }
    assert R_READY in ALLOWED


def test_included_set_is_the_ledger_cross_sheet_class():
    rows = json.loads(TRUTH.read_text(encoding="utf-8"))["rows"]
    ledger_cross = {b for b, v in build_ledger(rows, DOC).items() if v["category"] == CROSS_SHEET}
    assert ledger_cross == set(INCLUDED)
    # log11/47/67/69/70 owner-bridged 2026-06-16 -> only log48 remains in the cross-sheet class
    assert INCLUDED == ("log48",)


def test_subcategories_are_disjoint_and_match_scout():
    assert SOURCE_BLOCKED == EXPECTED_BLOCKED == ("log48",)   # only log48's source gap remains
    assert IDENTITY_HELD == EXPECTED_SOURCE_BACKED == ()      # log11/47 since bridged
    assert set(SOURCE_BLOCKED).isdisjoint(IDENTITY_HELD)
    assert set(SOURCE_BLOCKED) | set(IDENTITY_HELD) == set(INCLUDED)


def test_identity_held_have_one_named_flower_pot_terminus():
    for lid in IDENTITY_HELD:
        assert "FLOWER POT" in str(REC[lid].get("evidence_notes") or "").upper()
        assert not REC[lid].get("endpoint_anchors")


def test_the_six_carry_no_endpoint_anchors():
    for lid in INCLUDED:
        assert not REC[lid].get("endpoint_anchors")       # encodes nothing; fixture untouched


def test_reuses_shipped_grammar_no_new_frame_math():
    src = PROOF.read_text(encoding="utf-8")
    assert "import truelinev2.match.frames" in src
    assert "from truelinev2.proof.run_cross_sheet_frame_join_scout import" in src
    top_defs = {ln.split("(")[0].strip() for ln in src.splitlines() if ln.startswith("def ")}
    for forbidden in ("def parse_frame_equations", "def build_frame_edges", "def detect_conflicts",
                      "def translate_between_sheets", "def scout_log"):
        assert forbidden not in top_defs
    assert "from truelinev2.render" not in src and "render_redline_stroke" not in src
    # encodes nothing: never writes endpoint_anchors into a record
    assert "endpoint_anchors\"] =" not in src and "endpoint_anchors'] =" not in src


def test_seam_unchanged():
    assert tuple(ELIGIBLE_EXEMPLARS) == ("log53", "log64", "log71", "log59", "log66")


@pytest.mark.skipif(not os.path.isfile(PDF), reason="Brenham plan PDF not present")
def test_end_to_end_packet_ready():
    rc = main()
    assert rc == 0
    data = json.loads((OUT / "cross_sheet_blocked_evidence_packet.json").read_text(encoding="utf-8"))
    assert data["verdict"] == "PASS" and data["result"] == R_READY
    assert data["source_blocked"] == list(SOURCE_BLOCKED)
    assert data["identity_held"] == list(IDENTITY_HELD)
    pkt = data["evidence_packet"]
    assert set(pkt) == {"log48", "log67_69_70", "log11", "log47"}
    # log67/69/70: two distinct printed 17<->20 crossings + a real conflict (owner choices)
    crossings = pkt["log67_69_70"]["printed_crossings_to_choose"]
    offsets = sorted({abs(e["offset_ft"]) for e in crossings})
    assert offsets == [1.0, 504.0] and pkt["log67_69_70"]["conflict"]
    # log48: a direct 10<->12 HIGH candidate is surfaced (sheet 11 handwritten -> no paired hop equation)
    assert pkt["log48"]["candidate_direct_10_12"] and len(pkt["log48"]["candidate_direct_10_12"]) >= 1
    # identity-held questions are present and nothing is encoded
    assert pkt["log11"]["owner_must_answer"] and pkt["log47"]["owner_must_answer"]
    assert data["scope_guard"]["endpoint_anchors_encoded"] is False
