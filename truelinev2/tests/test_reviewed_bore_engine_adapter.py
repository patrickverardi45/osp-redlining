"""Contract tests: the reviewed-row -> engine ``Bore`` adapter (strict-reader fallback).

Two layers:
  1. Pure unit tests of ``reviewed_bore_adapter.bore_from_reviewed_rows`` against hand-built
     reviewed_bore_log dicts (no store/job scaffolding needed -- the derived-eligibility gate reads only
     plain dict shape).
  2. Wiring tests of ``uploaded_corpus_engine_handoff._run_engine`` (the strict-reader ValueError branch)
     proving the adapter is consulted ONLY there, and an end-to-end product-store test proving a customer
     bore log the strict reader cannot parse (a plain CSV) still reaches a real ENGINE verdict via its
     human-reviewed rows, instead of dead-ending on BORE_LOG_FORMAT_UNRECOGNIZED.

No customer/project/location/operator name anywhere.
"""
from __future__ import annotations

import base64
from pathlib import Path

import pytest

from truelinev2.contracts.customer_project import create_customer_project
from truelinev2.contracts.extracted_row import CONFIRMED, MANUAL_ENTRY, new_extracted_row, review_row
from truelinev2.contracts.processing_job import create_job, job_dir
from truelinev2.contracts.reviewed_bore_log import (
    GROUPING_CONFIRMED,
    SEPARATE_BORE,
    add_extracted_rows,
    create_reviewed_bore_log,
    define_segment_group,
    load_reviewed_bore_log,
    review_row_in_log,
    set_grouping_status,
)
from truelinev2.contracts.reviewed_bore_adapter import (
    FOOTAGE_FROM_STATION_DELTA,
    FOOTAGE_NOT_NUMERIC,
    MULTIPLE_ELIGIBLE_ROWS,
    NONPOSITIVE_FOOTAGE,
    NOT_ENGINE_READY,
    NO_POSITIVE_FOOTAGE,
    STATION_UNPARSEABLE,
    bore_from_reviewed_rows,
)
from truelinev2.contracts.upload_pipeline import accept_upload
from truelinev2.contracts import product_workflow as pw
from truelinev2.contracts import uploaded_corpus_engine_handoff as uce
from truelinev2.extract.borelog_rows import extract_rows_from_borelog

AT = "2026-07-10T00:00:00Z"
BY = "op-1"
CP = "cp-0001"
JOB = "job-0001"
RBL = "rbl-1"

# Minimal valid 1-page blank PDF (no dialect text) -- same fixture bytes used across the uploaded-corpus
# engine-handoff test suite (test_uploaded_corpus_engine_handoff.py / test_product_pipeline_api.py).
_PDF = base64.b64decode(
    "JVBERi0xLjcKJcK1wrYKJSBXcml0dGVuIGJ5IE11UERGIDEuMjcuMgoKMSAwIG9iago8PC9UeXBlL0NhdGFsb2cvUGFnZXMg"
    "MiAwIFIvSW5mbzw8L1Byb2R1Y2VyKE11UERGIDEuMjcuMik+Pj4+CmVuZG9iagoKMiAwIG9iago8PC9UeXBlL1BhZ2VzL0Nv"
    "dW50IDEvS2lkc1s0IDAgUl0+PgplbmRvYmoKCjMgMCBvYmoKPDw+PgplbmRvYmoKCjQgMCBvYmoKPDwvVHlwZS9QYWdlL01l"
    "ZGlhQm94WzAgMCA2MTIgNzkyXS9Sb3RhdGUgMC9SZXNvdXJjZXMgMyAwIFIvUGFyZW50IDIgMCBSPj4KZW5kb2JqCgp4cmVm"
    "CjAgNQowMDAwMDAwMDAwIDY1NTM1IGYgCjAwMDAwMDAwNDIgMDAwMDAgbiAKMDAwMDAwMDEyMCAwMDAwMCBuIAowMDAwMDAw"
    "MTcyIDAwMDAwIG4gCjAwMDAwMDAxOTMgMDAwMDAgbiAKCnRyYWlsZXIKPDwvU2l6ZSA1L1Jvb3QgMSAwIFIvSURbPDI1QzNB"
    "MjRFNEVDMjgwQzJBQzY1QzM4NEMzQTJDMjg1PjwxQjAyRUMzMkUxRDMwNUYzNDJBRjZFMjI2MkYzNTZDND5dPj4Kc3RhcnR4"
    "cmVmCjI4NAolJUVPRgo=")


# --------------------------------------------------------------------------- #
# Hand-built reviewed_bore_log dict helpers (no store/job scaffolding needed).
# --------------------------------------------------------------------------- #
def _row(row_id, raw, *, normalized=None, status=CONFIRMED, corrected_values=None):
    row = new_extracted_row(row_id, "up-1", raw=raw, normalized=(normalized or {}),
                            extraction_method=MANUAL_ENTRY, at=AT, by=BY)
    if status is not None:
        review_row(row, status, at=AT, by=BY, corrected_values=corrected_values)
    return row


def _group(member_row_ids, *, status=GROUPING_CONFIRMED, relation=SEPARATE_BORE):
    return {"group_id": "g-1", "member_row_ids": list(member_row_ids), "relation": relation,
            "grouping_status": status, "reason": None, "audit": []}


def _rbl(rows, groups, *, rbl_id="rbl-x"):
    return {"record_format": "trueline-reviewed-bore-log-1", "reviewed_bore_log_id": rbl_id,
            "customer_project_id": "cp-1", "processing_job_id": "job-1", "source_upload_id": "up-1",
            "rows": rows, "groups": groups, "audit": []}


# --------------------------------------------------------------------------- #
# Unit tests: bore_from_reviewed_rows fail-closed conditions + field fidelity.
# --------------------------------------------------------------------------- #
def test_corrected_values_beat_normalized_and_raw():
    row = _row("row-1",
               raw={"start_station": "0+00", "end_station": "1+00", "footage": "100"},
               normalized={"start_station": "0+05", "end_station": "1+05"},
               corrected_values={"start_station": "2+00", "end_station": "5+00", "footage": "300"})
    rbl = _rbl([row], [_group(["row-1"])])
    bore, detail = bore_from_reviewed_rows(rbl, source_filename="src.csv")
    assert bore is not None and detail is None
    assert bore.station_start == "2+00" and bore.station_end == "5+00"
    assert bore.station_start_ft == 200.0 and bore.station_end_ft == 500.0
    assert bore.span_ft == 300.0                 # the CORRECTED footage, not raw's 100


def test_alias_tolerance_footage_vs_footage_ft():
    a = _row("row-1", raw={"start_station": "0+00", "end_station": "1+00", "footage": 100})
    b = _row("row-1", raw={"start_station": "0+00", "end_station": "1+00", "footage_ft": 100})
    for row in (a, b):
        rbl = _rbl([row], [_group(["row-1"])])
        bore, detail = bore_from_reviewed_rows(rbl, source_filename="src.csv")
        assert bore is not None and detail is None
        assert bore.span_ft == 100.0


def test_alias_tolerance_sheet_refs_present_and_absent():
    with_refs = _row("row-1", raw={"start_station": "0+00", "end_station": "1+00", "footage": 100,
                                   "sheet_refs": [11, 11, "12"]})
    without_refs = _row("row-1", raw={"start_station": "0+00", "end_station": "1+00", "footage": 100})
    bore_a, _ = bore_from_reviewed_rows(_rbl([with_refs], [_group(["row-1"])]), source_filename="x.csv")
    bore_b, _ = bore_from_reviewed_rows(_rbl([without_refs], [_group(["row-1"])]), source_filename="x.csv")
    assert bore_a.sheet_refs == [11, 12]           # ordered-dedup
    assert bore_b.sheet_refs == []                 # absent -> empty, never guessed


def test_station_unparseable_declines():
    row = _row("row-1", raw={"start_station": "not-a-station", "end_station": "1+00", "footage": 100})
    rbl = _rbl([row], [_group(["row-1"])])
    bore, reason = bore_from_reviewed_rows(rbl, source_filename="x.csv")
    assert bore is None and reason == STATION_UNPARSEABLE


def test_no_positive_footage_declines():
    # Same start/end station (zero delta) and no explicit footage -> nothing positive to fall back to.
    row = _row("row-1", raw={"start_station": "5+00", "end_station": "5+00"})
    rbl = _rbl([row], [_group(["row-1"])])
    bore, reason = bore_from_reviewed_rows(rbl, source_filename="x.csv")
    assert bore is None and reason == NO_POSITIVE_FOOTAGE


def test_not_engine_ready_declines_zero_and_unreviewed_rows():
    # Zero rows -> never ready (reviewed_bore_log.is_engine_ready's own invariant): the adapter's dedicated
    # ZERO_ELIGIBLE_ROWS code is an unreachable defensive branch under that invariant, so "zero eligible"
    # and "not engine ready" collapse to the SAME observable decline here -- proven by both shapes below.
    empty = _rbl([], [])
    bore, reason = bore_from_reviewed_rows(empty, source_filename="x.csv")
    assert bore is None and reason == NOT_ENGINE_READY

    unreviewed = _row("row-1", raw={"start_station": "0+00", "end_station": "1+00", "footage": 100},
                      status=None)                 # left UNREVIEWED, no group
    rbl = _rbl([unreviewed], [])
    bore, reason = bore_from_reviewed_rows(rbl, source_filename="x.csv")
    assert bore is None and reason == NOT_ENGINE_READY


def test_multiple_eligible_rows_declines():
    row1 = _row("row-1", raw={"start_station": "0+00", "end_station": "1+00", "footage": 100})
    row2 = _row("row-2", raw={"start_station": "2+00", "end_station": "3+00", "footage": 100})
    rbl = _rbl([row1, row2], [_group(["row-1", "row-2"])])   # both CONFIRMED + grouped -> both eligible
    bore, reason = bore_from_reviewed_rows(rbl, source_filename="x.csv")
    assert bore is None and reason == MULTIPLE_ELIGIBLE_ROWS


def test_explicit_zero_footage_declines_not_station_delta():
    # Footage field is PRESENT (explicit "0") even though start/end stations differ (a real 150' delta) --
    # a present-but-invalid footage must DECLINE, never silently fall back to the station delta.
    row = _row("row-1", raw={"start_station": "0+00", "end_station": "1+50", "footage": "0"})
    rbl = _rbl([row], [_group(["row-1"])])
    bore, reason = bore_from_reviewed_rows(rbl, source_filename="x.csv")
    assert bore is None and reason == NONPOSITIVE_FOOTAGE


def test_explicit_negative_footage_declines_not_station_delta():
    row = _row("row-1", raw={"start_station": "0+00", "end_station": "1+50", "footage": "-25"})
    rbl = _rbl([row], [_group(["row-1"])])
    bore, reason = bore_from_reviewed_rows(rbl, source_filename="x.csv")
    assert bore is None and reason == NONPOSITIVE_FOOTAGE


def test_explicit_non_numeric_footage_declines():
    row = _row("row-1", raw={"start_station": "0+00", "end_station": "1+50", "footage": "n/a"})
    rbl = _rbl([row], [_group(["row-1"])])
    bore, reason = bore_from_reviewed_rows(rbl, source_filename="x.csv")
    assert bore is None and reason == FOOTAGE_NOT_NUMERIC


def test_empty_footage_value_still_falls_back_to_station_delta():
    # An empty-string footage value counts as ABSENT (same as no key at all) -- the station-delta fallback
    # still applies and still carries its honest-provenance detail.
    row = _row("row-1", raw={"start_station": "0+00", "end_station": "1+50", "footage": ""})
    rbl = _rbl([row], [_group(["row-1"])])
    bore, detail = bore_from_reviewed_rows(rbl, source_filename="x.csv")
    assert bore is not None
    assert bore.span_ft == pytest.approx(150.0)
    assert detail == FOOTAGE_FROM_STATION_DELTA


def test_footage_fallback_from_station_delta_carries_detail():
    row = _row("row-1", raw={"start_station": "0+00", "end_station": "1+50"})   # no footage column at all
    rbl = _rbl([row], [_group(["row-1"])])
    bore, detail = bore_from_reviewed_rows(rbl, source_filename="x.csv")
    assert bore is not None
    assert bore.span_ft == pytest.approx(150.0)
    assert detail == FOOTAGE_FROM_STATION_DELTA


def test_bore_field_fidelity():
    row = _row("row-1", raw={"start_station": "5+00", "end_station": "7+00", "footage": 200,
                             "sheet_refs": [3, "3", 5], "print_raw": "P-12", "depth_min_ft": "4.5"})
    rbl = _rbl([row], [_group(["row-1"])], rbl_id="rbl-fidelity")
    bore, detail = bore_from_reviewed_rows(rbl, source_filename="original_upload.csv")
    assert detail is None
    assert bore.bore_id == "rbl-fidelity"                       # the reviewed_bore_log's own id
    assert bore.source_file == "original_upload.csv"            # caller-supplied original filename
    assert bore.sheet_refs == [3, 5]                             # ordered-dedup ints
    assert bore.print_raw == "P-12"
    assert bore.depth_min_ft == 4.5                              # string -> float coercion
    assert bore.station_start_ft == 500.0 and bore.station_end_ft == 700.0
    assert bore.span_ft == 200.0


# --------------------------------------------------------------------------- #
# Wiring tests: _run_engine's ValueError branch (strict reader fails on a real file).
# --------------------------------------------------------------------------- #
def test_run_engine_blocker_carries_reviewed_rows_detail_on_decline(tmp_path):
    borelog_path = tmp_path / "unreadable.csv"
    borelog_path.write_text("not,a,workbook\n", encoding="utf-8")
    plan_path = tmp_path / "plan.pdf"
    plan_path.write_bytes(_PDF)
    empty_rbl = _rbl([], [])                        # NOT_ENGINE_READY -> adapter declines

    bore, placement, offset, dialect_name, extra_legs, matchline, used, blocker = uce._run_engine(
        str(plan_path), str(borelog_path), rbl=empty_rbl)

    assert bore is None and placement is None
    assert blocker["code"] == uce.BORE_LOG_FORMAT_UNRECOGNIZED
    assert blocker["reviewed_rows_detail"] == NOT_ENGINE_READY   # additive detail; SAME named code/copy


def test_run_engine_no_rbl_keeps_prior_blocker_shape(tmp_path):
    # No rbl supplied at all (rbl=None, the default) -> behaves EXACTLY as before the adapter existed: no
    # reviewed_rows_detail key added.
    borelog_path = tmp_path / "unreadable.csv"
    borelog_path.write_text("not,a,workbook\n", encoding="utf-8")
    plan_path = tmp_path / "plan.pdf"
    plan_path.write_bytes(_PDF)

    bore, placement, offset, dialect_name, extra_legs, matchline, used, blocker = uce._run_engine(
        str(plan_path), str(borelog_path))

    assert bore is None
    assert blocker["code"] == uce.BORE_LOG_FORMAT_UNRECOGNIZED
    assert "reviewed_rows_detail" not in blocker


def test_run_engine_uses_adapter_and_stamps_bore_source(tmp_path):
    borelog_path = tmp_path / "spans.csv"
    borelog_path.write_text("ignored -- the adapter reads the reviewed rows, not this file\n",
                            encoding="utf-8")
    plan_path = tmp_path / "plan.pdf"
    plan_path.write_bytes(_PDF)
    row = _row("row-1", raw={"start_station": "5+03", "end_station": "7+53", "footage": "250"})
    rbl = _rbl([row], [_group(["row-1"])], rbl_id="rbl-wired")

    bore, placement, offset, dialect_name, extra_legs, matchline, used, blocker = uce._run_engine(
        str(plan_path), str(borelog_path), rbl=rbl)

    # The strict reader failed on this CSV, but the adapter supplied a real Bore, so _run_engine proceeded
    # into the normal engine code path (dialect selection etc.) instead of returning the file-format blocker.
    assert bore is not None
    assert bore.bore_id == "rbl-wired"
    assert bore.station_start_ft == 503.0 and bore.station_end_ft == 753.0 and bore.span_ft == 250.0
    # Provenance marker threaded on the existing matchline/verdict dict (no tuple-shape change) -- present
    # regardless of whether the (blank) plan yields a placeable candidate.
    assert matchline.get("bore_source") == "REVIEWED_ROWS_ADAPTER"


# --------------------------------------------------------------------------- #
# End-to-end: a CSV bore log the strict reader cannot parse, extracted -> CONFIRMED -> grouped, reaches a
# real ENGINE verdict via the FULL product redline path (never BORE_LOG_FORMAT_UNRECOGNIZED).
# --------------------------------------------------------------------------- #
def test_e2e_csv_borelog_reaches_engine_via_reviewed_rows(tmp_path):
    create_customer_project(tmp_path, CP, "Label", AT)
    create_job(tmp_path, CP, JOB, AT, BY)
    accept_upload(tmp_path, CP, JOB, kind="PLAN_PDF", filename="plan.pdf", content=_PDF, stored_at=AT)
    csv_bytes = b"start_station,end_station,footage\n5+03,7+53,250\n"
    bore_up = accept_upload(tmp_path, CP, JOB, kind="BORE_LOG", filename="spans.csv",
                            content=csv_bytes, stored_at=AT)

    # /extract (simulated with the SAME deterministic extractor the route calls): the strict engine reader
    # cannot read this plain CSV, so extraction falls to the shipped generic span-table reader, which
    # confirms ONE source-tied span row (never a fabricated one).
    borelog_path = job_dir(tmp_path, CP, JOB) / bore_up["stored_path"]
    rows = extract_rows_from_borelog(str(borelog_path), bore_up["upload_id"], at=AT, by=BY)
    assert len(rows) == 1
    row_id = rows[0]["row_id"]

    create_reviewed_bore_log(tmp_path, CP, JOB, bore_up["upload_id"], RBL, at=AT, by=BY)
    add_extracted_rows(tmp_path, CP, JOB, RBL, rows, at=AT, by=BY)
    # Human review: CONFIRM the extracted row, then group + confirm the grouping (single-bore-per-job
    # scope) -- the real /extract -> CONFIRM -> group flow, engine-ready per reviewed_bore_log.py.
    review_row_in_log(tmp_path, CP, JOB, RBL, row_id, CONFIRMED, at=AT, by=BY)
    define_segment_group(tmp_path, CP, JOB, RBL, "g-1", [row_id], SEPARATE_BORE, at=AT, by=BY)
    set_grouping_status(tmp_path, CP, JOB, RBL, "g-1", GROUPING_CONFIRMED, at=AT, by=BY)

    registry = {"corpora": [], "configured": True}      # never recognizes -> forces the uploaded-corpus lane
    out = pw.run_product_redline(tmp_path, CP, JOB, registry=registry, at=AT, by=BY)

    # The core assertion: the product redline path reaches a real ENGINE verdict for this reviewed-row-only
    # bore log -- NEVER the strict-reader dead end.
    codes = {b["code"] for b in out["blockers"]}
    assert uce.BORE_LOG_FORMAT_UNRECOGNIZED not in codes
    # A blank/synthetic plan has no drawable geometry for ANY dialect, so the engine's honest outcome is
    # ABSTAIN -- proving a real placement ATTEMPT ran (the bore reached the engine), not that extraction
    # dead-ended before the engine could even try.
    assert out["path"] == pw.PATH_ABSTAIN
    assert out["runnable"] is False

    # Directly confirm the adapter supplies a real, field-faithful Bore for this exact reviewed_bore_log
    # (bore_source REVIEWED_ROWS_ADAPTER is the marker _run_engine stamps on this same successful path).
    rbl_record = load_reviewed_bore_log(tmp_path, CP, JOB, RBL)
    bore, detail = bore_from_reviewed_rows(rbl_record, source_filename="spans.csv")
    assert bore is not None and detail is None
    assert bore.station_start_ft == 503.0 and bore.station_end_ft == 753.0 and bore.span_ft == 250.0
