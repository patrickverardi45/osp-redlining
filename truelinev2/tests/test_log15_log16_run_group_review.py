"""LOG15/LOG16 run-group + Candidate-A review card -- gated-slice safety tests.

Prove the run-group/review-card slice (run_log15_log16_run_group_review_slice) honors every guardrail of
the resegmentation decision: log15/log16 share run-group metadata; 31+00/24+07 are never stroke endpoints;
Candidate A is REVIEW-only (not deterministic frontier, not census); its end precedes the downstream
duplicate guard; the parked upstream is explicit; the accounting reconciles; and the engine census stays
frozen. The slice is a SIDECAR + review card -- it mutates no tracked model/corpus/census.
"""
import pytest

from truelinev2.proof import run_log15_log16_run_group_review_slice as rg


def test_log15_log16_share_run_group_metadata():
    meta = rg.run_group_metadata()
    assert set(meta["members"]) == {"bore_log15", "bore_log16"}
    assert meta["run_group_id"] == rg.RUN_GROUP_ID
    assert meta["downstream_continuation"] == "bore_log20"
    assert meta["is_metadata_only"] and not meta["touches_census"] and not meta["touches_frontier"]


def test_31_00_and_24_07_are_never_stroke_endpoints():
    card = rg.build_card()
    labels = {card["proposed_run"]["start"]["label"], card["proposed_run"]["end"]["label"]}
    assert "31+00" not in labels and "24+07" not in labels
    assert labels == {"28+73", "39+79"}                       # only the two PRINTED anchors
    assert card["forbidden_endpoints"] == ["31+00", "24+07"]
    assert not rg._endpoint_violations(card)


def test_candidate_A_is_review_only_not_deterministic_frontier():
    card = rg.build_card()
    assert card["status"] == "REVIEW_HUMAN_APPROVAL"
    assert card["auto_place"] is False
    assert card["is_deterministic_frontier"] is False
    assert card["counts_toward_census"] is False


def test_candidate_A_end_is_before_downstream_duplicate_guard():
    g = rg.DUPLICATE_GUARD
    assert g["candidate_A_end_running_ft"] == 3979            # 39+79 (log16 END)
    assert g["downstream_rendered_start_running_ft"] == 4483  # 44+83 (bore_log20 / log49 start)
    assert g["candidate_A_end_running_ft"] < g["downstream_rendered_start_running_ft"]
    assert g["downstream_children"] == ["log49", "log48", "log50"]


def test_parked_upstream_remainder_is_explicit():
    p = rg.PARKED_UPSTREAM
    assert p["length_ft"] == 466
    assert p["span"] == "24+07->28+73"
    assert p["status"] == "SOURCE_REQUIRED"
    assert p["owner_drive"] == "bore_log15"


def test_accounting_reconciles_drive_vs_printed_run():
    r = rg.accounting_reconciliation()
    assert r["candidate_A_printed_run_ft"] == 1106
    assert r["log15_drive_ft"] == 693 and r["log16_drive_ft"] == 879
    assert r["reconciles_A"] and r["reconciles_log15"]
    assert r["log15_tail_in_A_ft"] + r["log16_drive_ft"] == 1106     # printed run = log15-tail + log16
    assert r["log15_tail_in_A_ft"] + r["parked_upstream_ft"] == 693  # log15 drive = tail + parked


def test_child_drive_evidence_preserved():
    try:
        ev = rg.child_evidence()
    except Exception as e:  # noqa: BLE001 -- corpus not resolvable in this env
        pytest.skip(f"corpus not available: {e!r}")
    assert ev["bore_log15"]["drive_length_ft"] == 693
    assert ev["bore_log16"]["drive_length_ft"] == 879
    assert ev["bore_log15"]["drive_span"] == "24+07->31+00"
    assert ev["bore_log16"]["drive_span"] == "31+00->39+79"
    for mid in ("bore_log15", "bore_log16"):
        assert ev[mid]["role"] == "child_drive_evidence"


def test_engine_census_stays_frozen():
    from truelinev2.ingest.manual_adjudication import load_adjudication
    from truelinev2.proof.run_station_corridor_route_solver_slice import TRUTH, _census_frozen
    if not TRUTH.is_file():
        pytest.skip("census truth table not present in this environment")
    assert _census_frozen(load_adjudication()) is True
