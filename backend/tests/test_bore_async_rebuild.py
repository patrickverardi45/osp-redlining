"""Fast-return bore-log upload safety — behavior tests (default-OFF TRUELINE_BORE_ASYNC_REBUILD).

Locks the route-level gating that makes POST /api/upload-structured-bore-files persist committed
bore rows in a MINIMAL session scope and return immediately, deferring the heavy
``_rebuild_field_data_outputs`` + MRQ preseed to a background finalizer. Motivation: on large
batches the synchronous rebuild + inflated-blob serialize timed out / OOM'd the 2 GB worker BEFORE
committed_rows was durable (observed: 20/58-log uploads -> field data files = 0). Flag OFF is
byte-identical to prod 1c9ee82; the heavy work is NOT moved and the route is unchanged.

Coverage (maps to the authorized test list):
  - flag OFF route behavior unchanged (rebuild runs in-request; preseed task is _preseed_mrq_evidence)
  - flag ON persists committed_rows and does NOT call rebuild before the response
  - flag ON returns quickly with processing=true
  - background finalizer scheduled after the durable commit
  - finalizer failure/raise does NOT erase committed_rows (durable)
  - batched accumulation by source_file still works under the flag
  - D32 large-batch on_demand path still reached through the finalizer; no heavy continuation > N
  - auth (no session) + closeout-lock protections preserved
"""
from __future__ import annotations

import asyncio
import contextlib
import os

os.environ.setdefault("TRUELINE_JWT_SECRET", "bore-async-test-secret")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "bore-async-test-auth-secret")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

from backend import main  # noqa: E402 — env defaults must precede the monolith import
from app.core import pdf_first_adapter as A  # noqa: E402
from app.core import mrq_evidence_cache as cache  # noqa: E402


@contextlib.contextmanager
def _noop_scope(_sid):
    yield


class _CapturingBT:
    def __init__(self):
        self.tasks = []

    def add_task(self, fn, *args, **kwargs):
        self.tasks.append((fn, args, kwargs))


class _FakeUpload:
    def __init__(self, name):
        self.filename = name

    async def read(self):
        return b"xlsxbytes"


class _FakeRequest:
    def __init__(self):
        self.query_params = {}


def _run_upload(monkeypatch, *, async_on, preseed_on=False, existing_rows=None,
                files=("bore_log7.xlsx",), closeout_locked=False, resolve_session="sid-1"):
    """Drive the real route with stubbed deps. Returns a dict with bt / ok kwargs / STATE /
    the captured rebuild calls / the raw response."""
    rebuild_calls = []
    ok_sink = {}
    monkeypatch.setattr(main, "_resolve_engineering_plan_session_id", lambda s, q: resolve_session)
    monkeypatch.setattr(main, "_is_closeout_locked", lambda: closeout_locked)
    monkeypatch.setattr(main, "_json_closeout_locked_response", lambda: "LOCKED")
    monkeypatch.setattr(main, "_read_bore_log_rows",
                        lambda b, n: [{"source_file": n, "station": "0+00"}])
    monkeypatch.setattr(main, "_rebuild_field_data_outputs", lambda **k: rebuild_calls.append(k))
    monkeypatch.setattr(main, "_summary_payload", lambda: {})
    monkeypatch.setattr(main, "_session_scope", _noop_scope)
    monkeypatch.setattr(main, "_ok", lambda **k: (ok_sink.update(k) or {"_kind": "ok", **k}))
    monkeypatch.setattr(main, "_err", lambda msg, **k: {"_kind": "err", "error": msg, **k})
    state = {"committed_rows": list(existing_rows)} if existing_rows is not None else {}
    monkeypatch.setattr(main, "STATE", state)
    if async_on:
        monkeypatch.setenv("TRUELINE_BORE_ASYNC_REBUILD", "1")
    else:
        monkeypatch.delenv("TRUELINE_BORE_ASYNC_REBUILD", raising=False)
    if preseed_on:
        monkeypatch.setenv("TRUELINE_MRQ_EVIDENCE_PRESEED", "1")
    else:
        monkeypatch.delenv("TRUELINE_MRQ_EVIDENCE_PRESEED", raising=False)
    bt = _CapturingBT()
    uploads = [_FakeUpload(n) for n in files]
    resp = asyncio.run(main.upload_structured_bore_files(_FakeRequest(), bt, uploads, resolve_session))
    return {"bt": bt, "ok": ok_sink, "state": state, "rebuild_calls": rebuild_calls, "resp": resp}


# ── flag gate ────────────────────────────────────────────────────────────────
def test_flag_default_off_and_on(monkeypatch):
    monkeypatch.delenv("TRUELINE_BORE_ASYNC_REBUILD", raising=False)
    assert main._bore_async_rebuild_enabled() is False
    monkeypatch.setenv("TRUELINE_BORE_ASYNC_REBUILD", "1")
    assert main._bore_async_rebuild_enabled() is True
    monkeypatch.setenv("TRUELINE_BORE_ASYNC_REBUILD", "0")
    assert main._bore_async_rebuild_enabled() is False


# ── flag OFF: byte-identical to prod ─────────────────────────────────────────
def test_flag_off_runs_rebuild_in_request_and_schedules_preseed(monkeypatch):
    r = _run_upload(monkeypatch, async_on=False, preseed_on=True)
    # rebuild runs synchronously in-request (ROWS_ONLY), exactly as prod
    assert len(r["rebuild_calls"]) == 1
    assert r["rebuild_calls"][0].get("scope") == main.RebuildScope.ROWS_ONLY
    # the scheduled task is the ORIGINAL preseed (not the finalizer)
    assert len(r["bt"].tasks) == 1
    assert r["bt"].tasks[0][0] is main._preseed_mrq_evidence
    # original success message; no processing flag; no async status key
    assert r["ok"].get("message") == "Bore logs uploaded successfully"
    assert "processing" not in r["ok"]
    assert "field_data_rebuild" not in r["state"]


def test_flag_off_with_preseed_off_schedules_nothing(monkeypatch):
    r = _run_upload(monkeypatch, async_on=False, preseed_on=False)
    assert len(r["rebuild_calls"]) == 1          # still rebuilds in-request
    assert r["bt"].tasks == []                   # preseed off -> no task (prod behavior)
    assert "mrq_preseed" not in r["state"]


# ── flag ON: fast-return, durable commit, deferred rebuild ───────────────────
def test_flag_on_persists_rows_and_skips_rebuild_in_request(monkeypatch):
    r = _run_upload(monkeypatch, async_on=True, preseed_on=True)
    # committed_rows persisted in-request (durable at this minimal scope exit)
    assert [row["source_file"] for row in r["state"]["committed_rows"]] == ["bore_log7.xlsx"]
    assert r["state"]["loaded_field_data_files"] == 1
    assert r["state"]["latest_structured_file"] == "bore_log7.xlsx"
    # the heavy rebuild is NOT called on the request path
    assert r["rebuild_calls"] == []
    # processing status marker set
    assert r["state"]["field_data_rebuild"]["status"] == "processing"


def test_flag_on_returns_quickly_with_processing_flag(monkeypatch):
    r = _run_upload(monkeypatch, async_on=True, preseed_on=True)
    assert r["ok"].get("processing") is True
    assert r["ok"].get("message") == "Bore logs uploaded, processing"
    assert r["ok"].get("session_id") == "sid-1"


def test_flag_on_schedules_finalizer_after_commit(monkeypatch):
    r = _run_upload(monkeypatch, async_on=True, preseed_on=True)
    assert len(r["bt"].tasks) == 1
    fn, args, _ = r["bt"].tasks[0]
    assert fn is main._bore_finalize_rebuild_and_preseed
    assert args == ("sid-1",)
    # preseed flag on -> early gate signal persisted so the FE keeps MRQ gated
    assert r["state"].get("mrq_preseed") == {"status": "scheduled"}


def test_flag_on_schedules_finalizer_even_when_preseed_off(monkeypatch):
    # The rebuild deferral must happen regardless of preseed; only the finalizer's preseed step is gated.
    r = _run_upload(monkeypatch, async_on=True, preseed_on=False)
    assert r["rebuild_calls"] == []                                  # still deferred
    assert len(r["bt"].tasks) == 1
    assert r["bt"].tasks[0][0] is main._bore_finalize_rebuild_and_preseed
    assert "mrq_preseed" not in r["state"]                           # preseed off -> no gate key


def test_flag_on_accumulates_by_source_file(monkeypatch):
    # Batched accumulation: a prior file's rows survive; the new file is added (merge by source_file).
    existing = [{"source_file": "bore_log1.xlsx", "station": "0+00"}]
    r = _run_upload(monkeypatch, async_on=True, preseed_on=True,
                    existing_rows=existing, files=("bore_log2.xlsx",))
    files_present = sorted({row["source_file"] for row in r["state"]["committed_rows"]})
    assert files_present == ["bore_log1.xlsx", "bore_log2.xlsx"]
    assert r["state"]["loaded_field_data_files"] == 2


# ── auth + closeout protections preserved (run BEFORE any commit) ─────────────
def test_no_session_returns_error_and_commits_nothing(monkeypatch):
    r = _run_upload(monkeypatch, async_on=True, preseed_on=True, resolve_session=None)
    assert r["resp"].get("_kind") == "err"
    assert r["bt"].tasks == []
    assert "committed_rows" not in r["state"]


def test_closeout_lock_blocks_commit_under_flag(monkeypatch):
    r = _run_upload(monkeypatch, async_on=True, preseed_on=True, closeout_locked=True)
    assert r["resp"] == "LOCKED"
    assert r["bt"].tasks == []
    assert "committed_rows" not in r["state"]
    assert "field_data_rebuild" not in r["state"]


# ── background finalizer ─────────────────────────────────────────────────────
def test_finalizer_runs_rebuild_then_preseed_in_order(monkeypatch):
    order = []
    monkeypatch.setenv("TRUELINE_MRQ_EVIDENCE_PRESEED", "1")
    monkeypatch.setattr(main, "_session_scope", _noop_scope)
    monkeypatch.setattr(main, "STATE", {"committed_rows": [{"source_file": "bore_log7.xlsx"}]})
    monkeypatch.setattr(main, "_rebuild_field_data_outputs", lambda **k: order.append("rebuild"))
    monkeypatch.setattr(main, "_preseed_mrq_evidence", lambda sid: order.append("preseed"))
    main._bore_finalize_rebuild_and_preseed("sid-1")
    assert order == ["rebuild", "preseed"]                       # rebuild first, THEN preseed
    assert main.STATE["field_data_rebuild"]["status"] == "ready"


def test_finalizer_preseed_off_skips_preseed(monkeypatch):
    order = []
    monkeypatch.delenv("TRUELINE_MRQ_EVIDENCE_PRESEED", raising=False)
    monkeypatch.setattr(main, "_session_scope", _noop_scope)
    monkeypatch.setattr(main, "STATE", {"committed_rows": [{"source_file": "bore_log7.xlsx"}]})
    monkeypatch.setattr(main, "_rebuild_field_data_outputs", lambda **k: order.append("rebuild"))
    monkeypatch.setattr(main, "_preseed_mrq_evidence", lambda sid: order.append("preseed"))
    main._bore_finalize_rebuild_and_preseed("sid-1")
    assert order == ["rebuild"]                                  # preseed gated off


def test_finalizer_rebuild_failure_keeps_committed_rows_durable(monkeypatch):
    committed = [{"source_file": "bore_log7.xlsx", "station": "0+00"}]
    state = {"committed_rows": committed, "redline_segments": ["stale"], "station_points": ["stale"]}
    preseed_calls = []

    def _boom(**k):
        raise RuntimeError("rebuild OOM-ish failure")

    monkeypatch.setenv("TRUELINE_MRQ_EVIDENCE_PRESEED", "1")
    monkeypatch.setattr(main, "_session_scope", _noop_scope)
    monkeypatch.setattr(main, "STATE", state)
    monkeypatch.setattr(main, "_rebuild_field_data_outputs", _boom)
    monkeypatch.setattr(main, "_preseed_mrq_evidence", lambda sid: preseed_calls.append(sid))
    main._bore_finalize_rebuild_and_preseed("sid-1")               # must NOT raise
    # committed_rows untouched (durable) even though the rebuild blew up
    assert main.STATE["committed_rows"] == committed
    assert main.STATE["field_data_rebuild"]["status"] == "failed"
    # partial derived outputs cleared so the map never renders half-built
    assert main.STATE["redline_segments"] == []
    assert main.STATE["station_points"] == []
    # preseed still attempted (MRQ is built from committed_rows independently of the rebuild)
    assert preseed_calls == ["sid-1"]


def test_finalizer_never_raises_when_scope_down(monkeypatch):
    @contextlib.contextmanager
    def _boom_scope(_sid):
        raise RuntimeError("scope down")
        yield  # pragma: no cover

    monkeypatch.setenv("TRUELINE_MRQ_EVIDENCE_PRESEED", "1")
    monkeypatch.setattr(main, "_session_scope", _boom_scope)
    monkeypatch.setattr(main, "_preseed_mrq_evidence", lambda sid: None)
    main._bore_finalize_rebuild_and_preseed("sid-1")              # best-effort: must NOT raise


# ── D32 large-batch safety preserved THROUGH the finalizer (>N -> on_demand) ──
def test_finalizer_preserves_d32_on_demand_above_threshold(monkeypatch, tmp_path):
    plan = tmp_path / "plan.pdf"
    plan.write_bytes(b"%PDF-1.4 test")
    distinct = 5
    rows = [{"source_file": "bore_log%d.xlsx" % i} for i in range(distinct)]
    calls, set_calls = [], []

    def _fake_build(plan_pdf, r, *, card_out_dir=None, perf_observer=None, render_heavy=True):
        calls.append(render_heavy)
        if render_heavy:  # would be the <=N heavy continuation
            return {"source": {"logs": ["x"]},
                    "placements": [{"log_ids": ["x"], "geo": {"pdf_path_trace": {"artifact_name": "x.png"}}}]}
        return {"source": {"logs": [str(i) for i in range(distinct)]},
                "heavy_evidence_pending": True,
                "placements": [{"log_ids": ["bore_log%d" % i]} for i in range(distinct)]}

    monkeypatch.setenv("TRUELINE_MRQ_EVIDENCE_PRESEED", "1")
    monkeypatch.setenv("TRUELINE_MRQ_LAZY_EVIDENCE", "1")
    monkeypatch.setenv("TRUELINE_PDF_FIRST_ENGINE", "1")
    monkeypatch.setenv("TRUELINE_MRQ_LAZY_MAX_CONTINUATION_LOGS", "1")  # N=1, distinct=5 > N
    monkeypatch.delenv("TRUELINE_PERF_AUDIT", raising=False)
    monkeypatch.setattr(main, "_session_scope", _noop_scope)
    monkeypatch.setattr(main, "STATE", {"committed_rows": rows})
    monkeypatch.setattr(main, "_resolve_engineering_plan_pdf_paths", lambda sid: [plan])
    monkeypatch.setattr(main, "_rebuild_field_data_outputs", lambda **k: None)  # finalizer's rebuild stubbed
    monkeypatch.setattr(cache, "enabled", lambda: True)
    monkeypatch.setattr(cache, "get_or_build",
                        lambda sid, r, p, cd, builder, observer=None: builder(p, r, card_out_dir=cd))
    monkeypatch.setattr(cache, "set_cached", lambda sid, r, p, payload: set_calls.append(payload) or True)
    monkeypatch.setattr(A, "build_session_evidence_from_committed_rows", _fake_build)

    main._bore_finalize_rebuild_and_preseed("sid-lb")

    assert calls == [False]                                       # NO heavy continuation for >N
    env = set_calls[0]
    assert env.get("heavy_evidence_mode") == "on_demand"         # D32 on-demand reached via finalizer
    assert "heavy_evidence_pending" not in env                   # no infinite auto-poll
    assert len(env.get("placements") or []) == distinct          # all cards kept (no truncation)
