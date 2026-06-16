"""CROSS_SHEET_FRAME_JOIN scout -- offline tests.

Locks the scout's pure laws (the heavy read-only PDF probe is verified by running the proof): the result
+ abstain-reason enums; the scouted set is EXACTLY the closure ledger's CROSS_SHEET_FRAME_JOIN_NEEDED class
(8 logs); the scout reuses the SHIPPED frame-join primitive (match.frames.translate_between_sheets) and
defines NO new join/frame grammar of its own and draws nothing; and -- PDF-gated -- the shipped primitive
partitions the 8 into 4 SOURCE-BACKED (log11/47/52/58) + 4 BLOCKED with named abstain reasons (log48 =
one-sided matchline; log67/69/70 = conflicting equations), encoding nothing.
"""
import json
import os
from pathlib import Path

import pytest

import truelinev2.match.frames as FR
from truelinev2.config import _REPO_ROOT
from truelinev2.ingest.manual_adjudication import load_adjudication
from truelinev2.proof.run_all_redlines_closure_ledger import CROSS_SHEET, build_ledger
from truelinev2.proof.run_brenham_corpus import PDF
from truelinev2.proof.run_cross_sheet_frame_join_scout import (
    ABSTAIN_CONFLICT,
    ABSTAIN_NO_EQUATION,
    ABSTAIN_REASONS,
    ALLOWED,
    EXPECTED_8,
    EXPECTED_BLOCKED,
    EXPECTED_SOURCE_BACKED,
    R_COMPLETE,
    scout_log,
)

DOC = load_adjudication()
REC = {r["log_id"]: r for r in DOC["logs"]}
TRUTH = _REPO_ROOT / "data" / "outputs" / "final_engine_truth_table" / "final_engine_truth_table.json"


def test_result_and_abstain_enums():
    assert R_COMPLETE == "CROSS_SHEET_FRAME_JOIN_SCOUT_COMPLETE"
    assert R_COMPLETE in ALLOWED
    assert {ABSTAIN_NO_EQUATION, ABSTAIN_CONFLICT} <= ABSTAIN_REASONS
    assert EXPECTED_8 == ("log11", "log47", "log48", "log52", "log58", "log67", "log69", "log70")
    assert set(EXPECTED_SOURCE_BACKED).isdisjoint(EXPECTED_BLOCKED)
    assert set(EXPECTED_SOURCE_BACKED) | set(EXPECTED_BLOCKED) == set(EXPECTED_8)


def test_scouted_set_is_the_ledger_cross_sheet_class():
    rows = json.loads(TRUTH.read_text(encoding="utf-8"))["rows"]
    ledger = build_ledger(rows, DOC)
    cross = tuple(sorted((b for b, v in ledger.items() if v["category"] == CROSS_SHEET),
                         key=lambda s: int(s[3:])))
    assert cross == EXPECTED_8


def test_reuses_shipped_primitive_no_new_math_no_render():
    # the join primitive is the SHIPPED one; the scout defines no new frame/join grammar and draws nothing
    assert FR.translate_between_sheets.__module__ == "truelinev2.match.frames"
    src = (Path(__file__).resolve().parent.parent / "proof" / "run_cross_sheet_frame_join_scout.py").read_text(encoding="utf-8")
    assert "import truelinev2.match.frames" in src
    top_defs = {ln.split("(")[0].strip() for ln in src.splitlines() if ln.startswith("def ")}
    for forbidden in ("def translate_between_sheets", "def translate_station_ft",
                      "def parse_frame_equations", "def build_frame_edges", "def detect_conflicts"):
        assert forbidden not in top_defs
    assert "from truelinev2.render" not in src
    assert "render_redline_stroke" not in src


def test_scout_encodes_nothing():
    # the 8 carry NO endpoint_anchors -- the scout reads only; the encoding bridge is a separate step
    for lid in EXPECTED_8:
        assert not REC[lid].get("endpoint_anchors")


@pytest.mark.skipif(not os.path.isfile(PDF), reason="Brenham plan PDF not present")
def test_shipped_primitive_partitions_the_eight():
    from truelinev2.extract.registry import select_dialect
    from truelinev2.ingest.pdf import PlanPdf
    plan = PlanPdf(PDF)
    try:
        offset = select_dialect(plan).calibrate(plan, 13)
        graph = FR._build_plan_frame_graph(plan, offset)
        scout = {lid: scout_log(graph, plan, offset, REC[lid]) for lid in EXPECTED_8}
    finally:
        plan.close()
    source_backed = tuple(sorted((l for l, s in scout.items() if s["source_backed"]), key=lambda s: int(s[3:])))
    blocked = tuple(sorted((l for l, s in scout.items() if not s["source_backed"]), key=lambda s: int(s[3:])))
    assert source_backed == EXPECTED_SOURCE_BACKED
    assert blocked == EXPECTED_BLOCKED
    # every blocked log names a real abstain reason; the primitive never returned a raw fallback (None==abstain)
    for lid in blocked:
        assert scout[lid]["blocker"] in ABSTAIN_REASONS
        assert any(h["abstain_reason"] in ABSTAIN_REASONS and h["translated_ft"] is None
                   for h in scout[lid]["hops"])
    # the specific named source gaps the scout reports
    assert scout["log48"]["blocker"] == ABSTAIN_NO_EQUATION          # one-sided interior matchline
    for lid in ("log67", "log69", "log70"):
        assert scout[lid]["blocker"] == ABSTAIN_CONFLICT             # two conflicting 17<->20 crossings
    # SOURCE-BACKED logs resolve every hop via a safe edge
    for lid in source_backed:
        assert scout[lid]["hops"] and all(h["safe_edge"] for h in scout[lid]["hops"])
