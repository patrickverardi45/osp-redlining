"""M8.11 -- tests pinning the reviewer bundle service contract (no PDF).

Locks: the run-mode table is CLOSED and safe (default = all opt-ins OFF;
fullest-safe composes EXACTLY M8.5 + M8.8 -- collision and continuation never
compose, and blanket frame translation has no flag at this seam at all); the
bundle validator recomputes counts from the payloads and fails loudly on any
drift (payload count, lane counts, status arithmetic, schema versions,
flag/mode mismatch, duplicate bores); the bundle serializes to JSON; the seam
is not wired into the engine. Pure/offline -- the corpus run lives in the
M8.11 proof runner."""
from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from truelinev2.review.reviewer_payloads import (
    ConfidenceClass,
    HumanAction,
    ReviewerLane,
    ReviewerPayload,
)
from truelinev2.review.reviewer_service import (
    BUNDLE_SCHEMA_VERSION,
    MODE_FLAGS,
    CorpusSource,
    GenerationFlagState,
    ReviewerBundle,
    ReviewRunMode,
)


def _placed(bore_id="log1"):
    return ReviewerPayload(
        bore_id=bore_id, lane=ReviewerLane.PLACED_REVIEW,
        human_action=HumanAction.APPROVE_REJECT_EDIT,
        reason_code="EXACT_BOX_FOOTAGE_AND_ENDPOINTS", sheets=[10],
        station_start_ft=0.0, station_end_ft=415.0, footage_ft=415.0,
        confidence_class=ConfidenceClass.AUTO_EXACT_MATCH,
        evidence_summary="STA 0+00 TO STA 4+15")


def _out_of_class(bore_id="log2"):
    return ReviewerPayload(
        bore_id=bore_id, lane=ReviewerLane.OUT_OF_CLASS,
        human_action=HumanAction.ROUTE_TO_NAMED_SOLVER,
        reason_code="M87_END_STATION_NOT_FOUND",
        next_named_solver="structure-identity binding at the bore end")


def _source(n_payloads=2, **over):
    base = dict(corpus_dir="X:/corpus", plan_pdf_path="X:/plan.pdf",
                sheet_offset=13, bore_log_count=n_payloads,
                bore_log_files=[f"bore_log{i}.xlsx" for i in range(1, n_payloads + 1)])
    base.update(over)
    return CorpusSource(**base)


def _bundle(**over):
    payloads = over.pop("payloads", [_placed(), _out_of_class()])
    base = dict(
        project_id="test-project", run_mode=ReviewRunMode.DEFAULT_BASELINE,
        flag_state=MODE_FLAGS[ReviewRunMode.DEFAULT_BASELINE],
        status_counts={"AUTO_SELECT": 1, "REVIEW": 0, "ABSTAIN": 1, "ERROR": 0,
                       "PLACED": 1},
        lane_counts={"PLACED_REVIEW": 1, "OUT_OF_CLASS": 1},
        payloads=payloads, source=_source(len(payloads)))
    base.update(over)
    return ReviewerBundle(**base)


# --- the closed mode table -----------------------------------------------------------

def test_mode_table_is_closed_two_modes():
    assert set(MODE_FLAGS) == {ReviewRunMode.DEFAULT_BASELINE,
                               ReviewRunMode.FULLEST_SAFE_REVIEW}
    assert {m.value for m in ReviewRunMode} == {"default_baseline",
                                                "fullest_safe_review"}


def test_default_mode_is_all_flags_off():
    f = MODE_FLAGS[ReviewRunMode.DEFAULT_BASELINE]
    assert f.model_dump() == {
        "reset_collision_optin": False, "frame_continuation_optin": False,
        "reverse_endpoint_optin": False, "station_axis_interval_optin": False}


def test_fullest_safe_composes_exactly_m85_and_m88():
    f = MODE_FLAGS[ReviewRunMode.FULLEST_SAFE_REVIEW]
    assert f.reverse_endpoint_optin and f.station_axis_interval_optin
    # collision (demote gate) and continuation (corpus-inert) NEVER compose
    # at this seam pending owner activation; blanket frame translation
    # (M8.2d NOT_SAFE) has no flag here at all.
    assert not f.reset_collision_optin and not f.frame_continuation_optin
    assert "translation" not in {k.lower() for k in f.model_dump()}


def test_flag_state_is_frozen():
    f = MODE_FLAGS[ReviewRunMode.DEFAULT_BASELINE]
    with pytest.raises(ValidationError):
        f.reverse_endpoint_optin = True


# --- bundle validator: every drift fails loudly --------------------------------------

def test_valid_bundle_constructs_and_roundtrips():
    b = _bundle()
    assert b.bundle_schema_version == BUNDLE_SCHEMA_VERSION
    got = json.loads(b.model_dump_json())
    assert got["run_mode"] == "default_baseline"
    assert got["lane_counts"]["PLACED_REVIEW"] == 1
    assert got["payloads"][0]["schema_version"] == b.payload_schema_version


def test_every_bore_must_reach_a_lane():
    with pytest.raises(ValidationError, match="every bore must reach a lane"):
        _bundle(source=_source(3))


def test_lane_counts_are_recomputed():
    with pytest.raises(ValidationError, match="lane_counts drift"):
        _bundle(lane_counts={"PLACED_REVIEW": 2})


def test_status_arithmetic_enforced():
    with pytest.raises(ValidationError, match="PLACED must equal"):
        _bundle(status_counts={"AUTO_SELECT": 1, "REVIEW": 0, "ABSTAIN": 1,
                               "ERROR": 0, "PLACED": 2})
    with pytest.raises(ValidationError, match="sum to the bore log count"):
        _bundle(status_counts={"AUTO_SELECT": 1, "REVIEW": 0, "ABSTAIN": 5,
                               "ERROR": 0, "PLACED": 1})
    with pytest.raises(ValidationError, match="missing keys"):
        _bundle(status_counts={"AUTO_SELECT": 1, "REVIEW": 0, "PLACED": 1})


def test_placed_lane_must_match_placed_statuses():
    # 2 placed statuses but only 1 PLACED_REVIEW payload -> loud failure
    with pytest.raises(ValidationError, match="PLACED_REVIEW lane count"):
        _bundle(status_counts={"AUTO_SELECT": 1, "REVIEW": 1, "ABSTAIN": 0,
                               "ERROR": 0, "PLACED": 2})


def test_flag_state_must_match_mode_table():
    with pytest.raises(ValidationError, match="closed table"):
        _bundle(flag_state=MODE_FLAGS[ReviewRunMode.FULLEST_SAFE_REVIEW])


def test_schema_versions_pinned():
    with pytest.raises(ValidationError, match="bundle schema"):
        _bundle(bundle_schema_version="truelinev2-reviewer-bundle-99")
    with pytest.raises(ValidationError, match="payload schema"):
        _bundle(payload_schema_version="other")
    drifted = _placed()
    drifted = drifted.model_copy(update={"schema_version": "other"})
    with pytest.raises(ValidationError, match="schema_version drift"):
        _bundle(payloads=[drifted, _out_of_class()])


def test_duplicate_bore_ids_rejected():
    with pytest.raises(ValidationError, match="duplicate bore_id"):
        _bundle(payloads=[_placed("log1"), _out_of_class("log1")],
                status_counts={"AUTO_SELECT": 1, "REVIEW": 0, "ABSTAIN": 1,
                               "ERROR": 0, "PLACED": 1})


def test_source_count_must_match_files():
    with pytest.raises(ValidationError, match="bore_log_count"):
        _source(2, bore_log_files=["bore_log1.xlsx"])


# --- doctrine + seam isolation --------------------------------------------------------

def test_no_numeric_confidence_in_bundle_fields():
    fields = set(ReviewerBundle.model_fields) | set(GenerationFlagState.model_fields)
    assert not any("score" in f or "probability" in f or "percent" in f
                   for f in fields)


def test_engine_not_wired_to_service_seam():
    import truelinev2.match.engine as eng
    assert not [m for m in dir(eng)
                if "bundle" in m.lower() or "reviewer" in m.lower()]
