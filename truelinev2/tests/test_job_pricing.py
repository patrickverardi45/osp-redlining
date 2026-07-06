"""Operator-entered job pricing — honest-billing contract tests.

Asserts: NO fake/default dollars (blank rate -> no base/final total, never $0 fabricated); operator-entered
provenance + disclaimer on every view; totals computed ONLY from operator rates × SERVER footage (footage
is never client-supplied); negative/non-numeric amounts rejected; persistence round-trip; kept DISTINCT from
the server-authoritative billing_summary. Name-free.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from truelinev2.contracts.customer_project import create_customer_project
from truelinev2.contracts.processing_job import create_job
from truelinev2.contracts import job_pricing as jp
from truelinev2.contracts.job_pricing import (
    JobPricingError, PRICING_DISCLAIMER, PROVENANCE_OPERATOR_ENTERED,
    load_job_pricing, parse_station_ft, pricing_view, reviewed_footage, row_footage, save_job_pricing,
)
from truelinev2.contracts.reviewed_bore_log import REVIEWED_BORE_LOG_RECORD_FORMAT, write_reviewed_bore_log

AT, BY, CP, JOB = "2026-06-29T00:00:00Z", "op-1", "cp-0001", "job-0001"


def _job(tmp_path):
    create_customer_project(tmp_path, CP, "Label", AT)
    create_job(tmp_path, CP, JOB, AT, BY)


def _footage(monkeypatch, value):
    """Force the SERVER footage quantity (the value normally summed from the validated manifest)."""
    monkeypatch.setattr(jp, "job_effective_footage",
                        lambda *a, **k: {"available": value is not None, "footage": value,
                                         "incomplete": False, "source_manifest_id": "m-1"})


def test_blank_pricing_has_no_fake_dollars(tmp_path):
    _job(tmp_path)
    v = pricing_view(tmp_path, CP, JOB)
    assert v["cost_per_foot"] is None          # NO invented default rate
    assert v["base_total"] is None and v["final_total"] is None   # no dollars without a rate
    assert v["exception_total"] == "0.00"
    assert v["exceptions"] == []
    assert v["provenance"] == PROVENANCE_OPERATOR_ENTERED and v["disclaimer"] == PRICING_DISCLAIMER
    assert v["footage_available"] is False     # no validated manifest in a fresh job


def test_save_and_reload_roundtrip(tmp_path):
    _job(tmp_path)
    save_job_pricing(tmp_path, CP, JOB, cost_per_foot="5.00",
                     exceptions=[{"label": "TXDOT permit", "amount": "250", "note": "right-of-way"}],
                     at=AT, by=BY)
    rec = load_job_pricing(tmp_path, CP, JOB)
    assert rec["cost_per_foot"] == "5.00"
    assert rec["exceptions"] == [{"label": "TXDOT permit", "amount": "250.00", "note": "right-of-way"}]
    assert rec["provenance"] == PROVENANCE_OPERATOR_ENTERED
    assert rec["updated_by"] == BY


def test_blank_rate_stays_blank(tmp_path):
    _job(tmp_path)
    save_job_pricing(tmp_path, CP, JOB, cost_per_foot="", exceptions=[], at=AT, by=BY)
    assert load_job_pricing(tmp_path, CP, JOB)["cost_per_foot"] is None   # blank stays blank, not 0
    save_job_pricing(tmp_path, CP, JOB, cost_per_foot=None, exceptions=[], at=AT, by=BY)
    assert load_job_pricing(tmp_path, CP, JOB)["cost_per_foot"] is None


def test_negative_or_nonnumeric_amount_rejected(tmp_path):
    _job(tmp_path)
    with pytest.raises(JobPricingError):
        save_job_pricing(tmp_path, CP, JOB, cost_per_foot="-1", exceptions=[], at=AT, by=BY)
    with pytest.raises(JobPricingError):
        save_job_pricing(tmp_path, CP, JOB, cost_per_foot="abc", exceptions=[], at=AT, by=BY)
    with pytest.raises(JobPricingError):
        save_job_pricing(tmp_path, CP, JOB, cost_per_foot="5",
                         exceptions=[{"label": "x", "amount": "-9"}], at=AT, by=BY)
    with pytest.raises(JobPricingError):     # exception needs a label
        save_job_pricing(tmp_path, CP, JOB, cost_per_foot="5",
                         exceptions=[{"label": "", "amount": "9"}], at=AT, by=BY)


def test_totals_math_uses_server_footage(tmp_path, monkeypatch):
    _job(tmp_path)
    _footage(monkeypatch, "1000")     # server-computed footage (NOT client-supplied)
    save_job_pricing(tmp_path, CP, JOB, cost_per_foot="5.00",
                     exceptions=[{"label": "TXDOT", "amount": "250.00"},
                                 {"label": "Restoration", "amount": "100"}],
                     at=AT, by=BY)
    v = pricing_view(tmp_path, CP, JOB)
    assert v["footage"] == "1000" and v["footage_available"] is True
    assert v["base_total"] == "5000.00"          # 1000 × 5.00
    assert v["exception_total"] == "350.00"       # 250 + 100
    assert v["final_total"] == "5350.00"          # base + exceptions
    assert v["totals_note"] is None


def test_exceptions_without_rate_have_no_base_or_final(tmp_path, monkeypatch):
    _job(tmp_path)
    _footage(monkeypatch, "1000")
    save_job_pricing(tmp_path, CP, JOB, cost_per_foot=None,
                     exceptions=[{"label": "TXDOT", "amount": "250"}], at=AT, by=BY)
    v = pricing_view(tmp_path, CP, JOB)
    assert v["base_total"] is None and v["final_total"] is None   # no rate -> no totals (honest)
    assert v["exception_total"] == "250.00"
    assert v["totals_note"] and "cost per foot" in v["totals_note"].lower()


def test_rate_entered_but_footage_unavailable(tmp_path, monkeypatch):
    _job(tmp_path)
    _footage(monkeypatch, None)        # no validated manifest yet
    save_job_pricing(tmp_path, CP, JOB, cost_per_foot="5.00", exceptions=[], at=AT, by=BY)
    v = pricing_view(tmp_path, CP, JOB)
    assert v["base_total"] is None and v["final_total"] is None
    assert v["footage_available"] is False and v["totals_note"] and "footage" in v["totals_note"].lower()


# --------------------------------------------------------------------------- #
# Footage from CONFIRMED reviewed bore-log station ranges (owner-directed: no manual footage math).
# --------------------------------------------------------------------------- #
def _row(row_id, start=None, end=None, footage_ft=None, footage=None, status="CONFIRMED"):
    raw = {}
    if start is not None:
        raw["start_station"] = start
    if end is not None:
        raw["end_station"] = end
    if footage_ft is not None:
        raw["footage_ft"] = footage_ft
    if footage is not None:
        raw["footage"] = footage
    normalized = {k: raw[k] for k in ("start_station", "end_station") if k in raw}
    return {"row_id": row_id, "source_upload_id": "up-x",
            "extraction": {"extraction_method": "TABLE_IMPORT", "extractor_name": None,
                           "confidence": None, "warnings": []},
            "raw": raw, "normalized": normalized,
            "review": {"status": status, "reviewed_by": BY, "reviewed_at": AT,
                       "corrected_values": None, "reason": None},
            "audit": []}


def _write_rbl(tmp_path, rows, rbl_id="rbl-main"):
    write_reviewed_bore_log(tmp_path, {
        "record_format": REVIEWED_BORE_LOG_RECORD_FORMAT, "reviewed_bore_log_id": rbl_id,
        "customer_project_id": CP, "processing_job_id": JOB, "source_upload_id": "up-x",
        "rows": rows, "groups": [], "audit": []})


def test_parse_station_ft():
    assert parse_station_ft("1+00") == Decimal("100")
    assert parse_station_ft("3+00") == Decimal("300")
    assert parse_station_ft("10+25") == Decimal("1025")
    assert parse_station_ft("0+00") == Decimal("0")
    assert parse_station_ft("2+99") == Decimal("299")
    assert parse_station_ft("11+40") == Decimal("1140")
    for bad in (None, "", "abc", "1", "1+5", "1+000", "1-00", "+00", "1+", "1++00"):
        assert parse_station_ft(bad) is None, bad


def test_row_footage_from_station_delta():
    # The owner's canonical cases: end_station_ft - start_station_ft.
    assert row_footage(_row("r", "1+00", "3+00")) == (Decimal("200"), "STATION_DELTA", None)
    assert row_footage(_row("r", "0+00", "2+99"))[0] == Decimal("299")
    assert row_footage(_row("r", "10+25", "11+40"))[0] == Decimal("115")


def test_row_footage_explicit_value_wins_first():
    ft, source, reason = row_footage(_row("r", "1+00", "3+00", footage_ft=200.0))
    assert (ft, source, reason) == (Decimal("200"), "EXPLICIT_FOOTAGE", None)
    # An explicit reviewed footage is TRUSTED and used before the station delta, even if they disagree.
    assert row_footage(_row("r", "1+00", "3+00", footage_ft=250))[:2] == (Decimal("250"), "EXPLICIT_FOOTAGE")
    # A non-positive / bad explicit value falls through to the station delta rather than blocking the row.
    assert row_footage(_row("r", "1+00", "3+00", footage_ft=0))[:2] == (Decimal("200"), "STATION_DELTA")
    assert row_footage(_row("r", "1+00", "3+00", footage="oops"))[:2] == (Decimal("200"), "STATION_DELTA")


def test_row_footage_invalid_ranges_report_a_reason():
    for start, end in (("3+00", "1+00"), ("1+00", "1+00")):        # negative, zero
        ft, source, reason = row_footage(_row("r", start, end))
        assert ft is None and source == "STATION_RANGE" and reason
    assert row_footage(_row("r", None, None))[0] is None            # missing
    assert row_footage(_row("r", "abc", "3+00"))[0] is None         # malformed start


def test_reviewed_footage_sums_valid_and_lists_invalid_without_zeroing(tmp_path):
    _job(tmp_path)
    _write_rbl(tmp_path, [
        _row("r1", "1+00", "3+00"),                      # 200 (valid)
        _row("r2", "0+00", "2+99"),                      # 299 (valid)
        _row("r3", "3+00", "1+00"),                      # invalid (negative) — must NOT zero the total
        _row("r4", None, None, status="UNREVIEWED"),     # not confirmed -> ignored entirely
    ])
    rev = reviewed_footage(tmp_path, CP, JOB)
    assert rev["available"] is True
    assert rev["total_footage"] == "499"                             # 200 + 299 (one bad row does not zero it)
    assert {r["row_id"] for r in rev["valid_rows"]} == {"r1", "r2"}
    assert [r["row_id"] for r in rev["invalid_rows"]] == ["r3"]      # r4 (unreviewed) is neither valid nor invalid


def test_pricing_view_computes_15_per_ft_times_200_equals_3000(tmp_path):
    _job(tmp_path)
    _write_rbl(tmp_path, [_row("r1", "1+00", "3+00")])               # 200 ft from the confirmed row
    save_job_pricing(tmp_path, CP, JOB, cost_per_foot="15", exceptions=[], at=AT, by=BY)
    v = pricing_view(tmp_path, CP, JOB)
    assert v["footage"] == "200" and v["footage_available"] is True
    assert v["footage_source"] == "REVIEWED_BORE_LOG_STATIONS"
    assert v["base_total"] == "3000.00" and v["final_total"] == "3000.00"     # $15/ft × 200 ft
    assert v["totals_note"] is None and v["footage_unavailable_rows"] == []


def test_pricing_view_sums_rows_and_adds_exceptions(tmp_path):
    _job(tmp_path)
    _write_rbl(tmp_path, [_row("r1", "1+00", "3+00"), _row("r2", "10+25", "11+40")])   # 200 + 115 = 315
    save_job_pricing(tmp_path, CP, JOB, cost_per_foot="15",
                     exceptions=[{"label": "Restoration", "amount": "500"}], at=AT, by=BY)
    v = pricing_view(tmp_path, CP, JOB)
    assert v["footage"] == "315"
    assert v["base_total"] == "4725.00"                              # 315 × 15
    assert v["exception_total"] == "500.00" and v["final_total"] == "5225.00"


def test_pricing_view_falls_back_to_manifest_when_no_station_rows(tmp_path, monkeypatch):
    # A confirmed row that carries NO station range keeps the existing manifest-footage behaviour (no
    # regression for general-upload jobs), and the unmeasurable row is still surfaced honestly.
    _job(tmp_path)
    _write_rbl(tmp_path, [_row("r1", None, None)])                   # confirmed but no stations/footage
    _footage(monkeypatch, "150")                                    # validated-manifest drawn footage
    save_job_pricing(tmp_path, CP, JOB, cost_per_foot="15", exceptions=[], at=AT, by=BY)
    v = pricing_view(tmp_path, CP, JOB)
    assert v["footage"] == "150" and v["footage_source"] == "DRAWN_MANIFEST"
    assert v["base_total"] == "2250.00"                              # 150 × 15 (unchanged)
    assert len(v["footage_unavailable_rows"]) == 1                   # the confirmed-but-unmeasurable row shows why
