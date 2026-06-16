"""OWNER-CORRECTION recon scout (cross-sheet / parent-child) -- offline + PDF-gated tests.

Locks the recon's pure laws: the result enum; the corrected set (log11/47/48/67/69/70) is the live ledger
CROSS_SHEET class; the cross-sheet-after / single-sheet-after / parent-child partition; the six carry no
endpoint_anchors and the scout writes no fixture/anchor; and it reuses the SHIPPED resolvers (no new
resolver). The heavy read-only SOURCE VERIFICATION (every owner-corrected terminus binds uniquely as the
owner-named class; log69 is single-sheet; log48's parent/child legs are source-true) is verified PDF-gated.
"""
import json
import os
from pathlib import Path

import pytest

from truelinev2.config import _REPO_ROOT
from truelinev2.ingest.manual_adjudication import load_adjudication
from truelinev2.proof.run_all_redlines_closure_ledger import CROSS_SHEET, build_ledger
from truelinev2.proof.run_brenham_corpus import PDF
from truelinev2.proof.run_log53_primitives_cohort_replay import classify_record
from truelinev2.seam import ELIGIBLE_EXEMPLARS
from truelinev2.proof.run_owner_correction_recon_scout import (
    ALLOWED,
    CORRECTIONS,
    CROSS_SHEET_AFTER,
    LOG48,
    R_COMPLETE,
    SINGLE_SHEET_AFTER,
    main,
)

DOC = load_adjudication()
REC = {r["log_id"]: r for r in DOC["logs"]}
TRUTH = _REPO_ROOT / "data" / "outputs" / "final_engine_truth_table" / "final_engine_truth_table.json"
PROOF = Path(__file__).resolve().parent.parent / "proof" / "run_owner_correction_recon_scout.py"
OUT = _REPO_ROOT / "data" / "outputs" / "owner_correction_recon_scout"
CORRECTED = set(CORRECTIONS) | {"log48"}


def test_result_enum_exact():
    assert ALLOWED == {
        "OWNER_CORRECTION_RECON_COMPLETE",
        "BLOCKED_RECON_TRUTH_MISSING",
        "BLOCKED_RECON_PDF_MISSING",
        "BLOCKED_RECON_SET_DRIFTED",
        "BLOCKED_RECON_SILENTLY_ENCODED",
    }
    assert R_COMPLETE in ALLOWED


def test_corrections_applied_only_log48_remains_cross_sheet():
    # after the 2026-06-16 bridge, the 5 source-verified corrections moved to SOURCE_BINDABLE_NOW;
    # only log48 (parent/child reconstruction) remains in the live CROSS_SHEET class
    rows = json.loads(TRUTH.read_text(encoding="utf-8"))["rows"]
    ledger_cross = {b for b, v in build_ledger(rows, DOC).items() if v["category"] == CROSS_SHEET}
    assert ledger_cross == {"log48"}
    assert CORRECTED == {"log11", "log47", "log48", "log67", "log69", "log70"}     # the documented set
    for lid in CORRECTIONS:
        assert classify_record(REC[lid])["classification"] == "SOURCE_BINDABLE_NOW"


def test_partition_constants():
    assert set(CORRECTIONS) == {"log67", "log69", "log70", "log47", "log11"}
    assert SINGLE_SHEET_AFTER == ("log69",)
    assert set(CROSS_SHEET_AFTER) == {"log67", "log70", "log47", "log11"}
    assert set(CROSS_SHEET_AFTER).isdisjoint(SINGLE_SHEET_AFTER)


def test_log48_parent_child_constant():
    assert LOG48["parent_reset"] == ("nextlink_hh", "45+33", 10, True)
    sheets = {sheet for _, _, sheet in LOG48["children"]}
    assert sheets == {11, 12}                          # the two child legs are on sheets 11 and 12
    assert "log50" in LOG48["sibling_candidate"]


def test_owner_correction_classes_are_modeled():
    from truelinev2.proof.run_log53_primitives_cohort_replay import MODELED_TERMINUS_CLASSES
    for c in CORRECTIONS.values():
        assert c["start"][0] in MODELED_TERMINUS_CLASSES
        assert c["end"][0] in MODELED_TERMINUS_CLASSES


def test_recon_scout_itself_encodes_nothing_corrections_since_applied():
    # the recon SCOUT writes no anchors (read-only); the corrections have SINCE been applied by the
    # separate owner-corrected-anchors slice -> the 5 now carry anchors, log48 (parent/child) stays unencoded
    for lid in CORRECTIONS:
        assert REC[lid].get("endpoint_anchors")
    assert not REC["log48"].get("endpoint_anchors")
    src = PROOF.read_text(encoding="utf-8")
    assert "endpoint_anchors\"] =" not in src and "endpoint_anchors'] =" not in src
    assert ".write_text" in src                         # writes only the gitignored report
    # reuses the shipped resolvers; defines no new resolver
    top_defs = {ln.split("(")[0].strip() for ln in src.splitlines() if ln.startswith("def ")}
    for forbidden in ("def resolve_structure_position", "def resolve_nextlink_hh_callout", "def classify_record"):
        assert forbidden not in top_defs
    assert "from truelinev2.render" not in src


def test_seam_unchanged():
    assert tuple(ELIGIBLE_EXEMPLARS) == ("log53", "log64", "log71", "log59", "log66")


@pytest.mark.skipif(not os.path.isfile(PDF), reason="Brenham plan PDF not present")
def test_end_to_end_source_verification():
    rc = main()
    assert rc == 0
    data = json.loads((OUT / "owner_correction_recon_scout.json").read_text(encoding="utf-8"))
    assert data["verdict"] == "PASS" and data["result"] == R_COMPLETE
    imp = data["impact_by_log"]
    assert set(imp) == CORRECTED
    # the 5 owner corrections are source-verified (both termini bind uniquely as the owner-named class)
    for lid in CORRECTIONS:
        assert imp[lid]["source_verified"] is True
        assert imp[lid]["verification"]["start"]["unique"] and imp[lid]["verification"]["end"]["unique"]
    # log69 is single-sheet (both termini on sheet 17)
    v69 = imp["log69"]["verification"]
    assert v69["start"]["sheet"] == v69["end"]["sheet"] == 17
    # log67/log70 stay cross-sheet (s17 -> s20)
    for lid in ("log67", "log70"):
        v = imp[lid]["verification"]
        assert v["start"]["sheet"] == 17 and v["end"]["sheet"] == 20
    # log48 parent/child legs are source-true (reset s10; FP 5+14 s11; FP 5+07 s12)
    l48 = imp["log48"]["verification"]
    assert l48["parent_reset"]["source_verified"] and l48["parent_reset"]["sheet"] == 10
    assert l48["children"][0]["sheet"] == 11 and l48["children"][1]["sheet"] == 12
    assert all(ch["source_verified"] for ch in l48["children"])
    # nothing encoded; no fixture modification
    assert data["scope_guard"]["endpoint_anchors_encoded"] is False
    assert data["scope_guard"]["fixture_modified"] is False
