"""OWNER-PACKET-2 manual adjudication ingestion -- offline tests.

Validates the tracked correction artifact + screenshot evidence index and the
fail-closed loader/resolver seam. No corpus, no PDF parse, no engine re-run.
"""
import copy

import pytest

from truelinev2.ingest.manual_adjudication import (
    DEFAULT_ARTIFACT,
    DEFAULT_EVIDENCE_INDEX,
    RECOVERABLE_STATUS,
    AdjudicationError,
    load_adjudication,
    load_evidence_index,
    parent_run_duplicate_check,
    resolve,
    summarize,
    validate_adjudication,
)

EXPECTED_27 = {
    "log6", "log63", "log64", "log46", "log47", "log52", "log53", "log58", "log67",
    "log70", "log71", "log11", "log12", "log29", "log36", "log41", "log44", "log48",
    "log54", "log59", "log66", "log68", "log69",
    "log5", "log31", "log38", "log43",
}
SHARED_PRINT_11 = {
    "log6", "log46", "log47", "log52", "log53", "log58", "log63", "log64", "log67",
    "log70", "log71",
}
ABSTAIN_4 = {"log5", "log31", "log38", "log43"}


@pytest.fixture(scope="module")
def doc():
    return load_adjudication(DEFAULT_ARTIFACT)


@pytest.fixture(scope="module")
def disp(doc):
    return resolve(doc)


# --- structure + validation -----------------------------------------------------
def test_artifact_parses_and_validates(doc):
    assert validate_adjudication(doc) == []


def test_27_logs_exactly_once(doc):
    ids = [r["log_id"] for r in doc["logs"]]
    assert len(ids) == 27
    assert set(ids) == EXPECTED_27
    assert len(set(ids)) == len(ids)


def test_summary_27_23_4_0_0(doc):
    s = summarize(doc)
    assert s["original_problem_logs"] == 27
    assert s["recoverable_or_correct_as_drawn"] == 23
    assert s["valid_abstain_no_good"] == 4
    assert s["active_unknowns"] == 0
    assert s["shared_print_owner_source_required_after_review"] == 0


# --- the 23 recoverable / 4 abstain split ---------------------------------------
def test_23_recoverable(doc):
    rec = [r for r in doc["logs"] if r["status"] in RECOVERABLE_STATUS]
    assert len(rec) == 23
    assert all(not r["must_remain_abstained"] for r in rec)


@pytest.mark.parametrize("lid", sorted(ABSTAIN_4))
def test_abstain_stays_abstained(disp, lid):
    d = disp[lid]
    assert d.status == "ABSTAIN_NO_SAFE_SOURCE"
    assert d.must_remain_abstained is True
    assert d.allowed_to_draw is False
    assert d.correction_types == ()


# --- the 11 shared-print children ------------------------------------------------
def test_shared_print_children_set(doc):
    shared = {r["log_id"] for r in doc["logs"] if r.get("shared_print_child")}
    assert shared == SHARED_PRINT_11


@pytest.mark.parametrize("lid", sorted(SHARED_PRINT_11))
def test_shared_print_child_recovered(disp, lid):
    assert disp[lid].status in RECOVERABLE_STATUS
    assert disp[lid].must_remain_abstained is False


def test_no_shared_print_owner_source_required(doc):
    assert summarize(doc)["shared_print_owner_source_required_after_review"] == 0


# --- the specific corrected facts (gates 6/7/8) ---------------------------------
def test_log68_corrected_range_not_4_54(disp):
    d = disp["log68"]
    assert d.corrected_start == "5+03"
    assert d.corrected_end == "6+79"
    assert "4+54" not in (d.corrected_start, d.corrected_end)


@pytest.mark.parametrize("lid", ["log67", "log68", "log70"])
def test_print_ocr_corrected_to_17_20(disp, lid):
    assert disp[lid].corrected_prints == (17, 20)


def test_log69_owner_corrected_to_single_print_17(disp):
    # owner correction 2026-06-16: log69 is a single-sheet installer-to-installer run on print 17
    # (its 4+54 destination binds installer_hh on sheet 17, not 20) -> corrected_prints/sheets are [17]
    assert disp["log69"].corrected_prints == (17,)


def test_log41_correct_as_drawn(disp):
    assert disp["log41"].status == "CORRECT_AS_DRAWN"


# --- no parent/child duplicate overlapping redline ------------------------------
def test_no_parent_child_duplicate(doc):
    assert parent_run_duplicate_check(doc) == []


# --- evidence index ties to real logs -------------------------------------------
def test_evidence_index_ties_to_real_logs():
    idx = load_evidence_index(DEFAULT_EVIDENCE_INDEX)
    assert idx is not None
    shots = idx["screenshots"]
    assert len(shots) == 47
    cand = {s.get("candidate_log") for s in shots} - {None}
    assert cand <= EXPECTED_27
    assert set(idx["by_log"].keys()) <= EXPECTED_27
    clear = set(idx["coverage"]["logs_with_clear_support"])
    # every clear-supported log is one of the recoverable set
    doc = load_adjudication(DEFAULT_ARTIFACT)
    rec = {r["log_id"] for r in doc["logs"] if r["status"] in RECOVERABLE_STATUS}
    assert clear <= rec


# --- fail-closed validation negatives -------------------------------------------
def test_validation_rejects_abstain_flipped_to_draw(doc):
    bad = copy.deepcopy(doc)
    a = next(r for r in bad["logs"] if r["log_id"] == "log5")
    a["allowed_to_draw"] = True  # tamper: an abstain log must never be drawable
    errs = validate_adjudication(bad)
    assert any("log5" in e and "allowed_to_draw" in e for e in errs)


def test_validation_rejects_unknown_status(doc):
    bad = copy.deepcopy(doc)
    bad["logs"][0]["status"] = "SOLVED_BY_MAGIC"
    errs = validate_adjudication(bad)
    assert any("not in enum" in e for e in errs)


def test_validation_rejects_duplicate_recovered_geometry(doc):
    """parent_run_duplicate_check flags two same-family children with identical geometry."""
    bad = copy.deepcopy(doc)
    a = next(r for r in bad["logs"] if r["log_id"] == "log47")  # bore_log18
    b = next(r for r in bad["logs"] if r["log_id"] == "log46")  # bore_log18
    a["corrected_start"], a["corrected_end"], a["corrected_sheets"] = (
        b["corrected_start"], b["corrected_end"], b["corrected_sheets"])
    assert parent_run_duplicate_check(bad)


def test_missing_artifact_raises():
    with pytest.raises(AdjudicationError):
        load_adjudication(DEFAULT_ARTIFACT.parent / "does_not_exist.json")
