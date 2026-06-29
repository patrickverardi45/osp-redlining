"""Operator-entered job pricing — honest-billing contract tests.

Asserts: NO fake/default dollars (blank rate -> no base/final total, never $0 fabricated); operator-entered
provenance + disclaimer on every view; totals computed ONLY from operator rates × SERVER footage (footage
is never client-supplied); negative/non-numeric amounts rejected; persistence round-trip; kept DISTINCT from
the server-authoritative billing_summary. Name-free.
"""
from __future__ import annotations

import pytest

from truelinev2.contracts.customer_project import create_customer_project
from truelinev2.contracts.processing_job import create_job
from truelinev2.contracts import job_pricing as jp
from truelinev2.contracts.job_pricing import (
    JobPricingError, PRICING_DISCLAIMER, PROVENANCE_OPERATOR_ENTERED,
    load_job_pricing, pricing_view, save_job_pricing,
)

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
