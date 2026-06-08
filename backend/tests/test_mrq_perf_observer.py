"""MRQ cold-build perf instrumentation — behavior-neutral invariant tests.

Locks the optional ``perf_observer`` on the PDF-first evidence builders
(``pdf_first_adapter.build_session_evidence_from_rows`` /
``build_session_evidence_from_committed_rows``): when supplied it emits per-log +
summary timing dicts WITHOUT changing the returned envelope, and a raising observer
never breaks the build. Default (None) => byte-identical (no timing work). The engine
+ render are stubbed so the test runs without the scratch-tree engine. NEVER asserts
any draw / tier / placement / geo change — there is none.
"""
from __future__ import annotations

from app.core import pdf_first_adapter as A


class _FakeEng:
    ENGINE_VERSION = "fake-1"

    def select_redline_from_rows(self, plan_pdf_path, rows, *, source_file=None,
                                 sheet_offset=13, anchor_tables=None):
        return {"_src": source_file}  # sentinel; _envelope_from_result is stubbed


def _fake_env(_result):
    # Fresh deterministic envelope each call (lists copied) so the with/without-observer
    # builds accumulate identical content.
    return {
        "placements": [{"log_ids": ["log1"], "tier": "T", "geo": None}],
        "review_items": [],
        "fail_safe": [],
        "counts_by_tier": {"T": 1},
        "warnings": [],
    }


def _patch_engine(monkeypatch):
    monkeypatch.setattr(A, "_load_engine", lambda: (_FakeEng(), None))
    monkeypatch.setattr(A, "_render_crops", lambda *a, **k: None)
    monkeypatch.setattr(A, "_anchor_tables", lambda: None)
    monkeypatch.setattr(A, "_envelope_from_result", _fake_env)
    # resolver consult OFF -> no corrections / resolver branch
    monkeypatch.delenv("TRUELINE_MATCHLINE_FRAME_RESOLVER", raising=False)


_LOGS = [("log1", [{"station": "0+00"}], "log1.xlsx")]


def test_perf_observer_does_not_change_envelope(monkeypatch):
    _patch_engine(monkeypatch)
    env_none = A.build_session_evidence_from_rows("plan.pdf", _LOGS)            # default None
    events = []
    env_obs = A.build_session_evidence_from_rows("plan.pdf", _LOGS, perf_observer=events.append)
    assert env_none == env_obs            # envelope byte-identical with/without observer
    assert env_obs["status"] == "OK"
    assert events                          # observer WAS called


def test_perf_observer_emits_expected_stages(monkeypatch):
    _patch_engine(monkeypatch)
    events = []
    A.build_session_evidence_from_rows("plan.pdf", _LOGS, perf_observer=events.append)
    stages = [e["stage"] for e in events]
    for s in ("mrq_pf.select", "mrq_pf.render", "mrq_pf.select_total",
              "mrq_pf.render_total", "mrq_pf.envelope_assembly"):
        assert s in stages, s
    # every event carries ONLY safe keys + a numeric elapsed_ms; detail is a log-id only
    for e in events:
        assert set(e) <= {"stage", "elapsed_ms", "detail", "input_count", "output_count"}
        assert isinstance(e["elapsed_ms"], float)
        if "detail" in e:
            assert e["detail"].startswith("log=")  # never row / file / PDF content


def test_perf_observer_raising_never_breaks_build(monkeypatch):
    _patch_engine(monkeypatch)

    def _boom(_evt):
        raise RuntimeError("telemetry sink boom")

    env = A.build_session_evidence_from_rows("plan.pdf", _LOGS, perf_observer=_boom)
    assert env["status"] == "OK"           # a raising observer must not affect the build


def test_committed_rows_entry_threads_perf_observer(monkeypatch):
    _patch_engine(monkeypatch)
    events = []
    env = A.build_session_evidence_from_committed_rows(
        "plan.pdf", [{"source_file": "log1.xlsx", "station": "0+00"}],
        perf_observer=events.append)
    assert env is not None and env["status"] == "OK"
    assert any(e["stage"] == "mrq_pf.render_total" for e in events)


def test_default_path_has_no_observer_overhead(monkeypatch):
    # perf_observer omitted -> _po is None -> no timing events, plain envelope.
    _patch_engine(monkeypatch)
    env = A.build_session_evidence_from_rows("plan.pdf", _LOGS)
    assert env["status"] == "OK"
    assert "placements" in env and env["counts_by_surface"]["placements"] == 1
