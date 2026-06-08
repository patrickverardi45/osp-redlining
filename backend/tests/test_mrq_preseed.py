"""Background MRQ evidence preseed — behavior tests (default-OFF).

Proves the ``TRUELINE_MRQ_EVIDENCE_PRESEED`` preseed: the upload endpoint schedules a
background task ONLY when the flag is on; ``_preseed_mrq_evidence`` reuses
``mrq_evidence_cache.get_or_build`` (no duplicate build when warm), safely no-ops when
not ready / cache off, and never lets a builder failure escape. Touches no draw /
selector / resolver / cache-strategy / upload-parser behavior.
"""
from __future__ import annotations

import asyncio
import contextlib
import os
from pathlib import Path

os.environ.setdefault("TRUELINE_JWT_SECRET", "preseed-test-secret")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "preseed-test-auth-secret")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

from backend import main  # noqa: E402 — env defaults must precede the monolith import
from app.core import mrq_evidence_cache as cache  # noqa: E402
from app.core import pdf_first_adapter  # noqa: E402


@contextlib.contextmanager
def _noop_scope(_sid):
    yield


def _ready(monkeypatch, *, rows, plan, cache_on=True):
    """Wire _preseed to see a ready/not-ready session with the cache on/off."""
    monkeypatch.setattr(main, "_session_scope", _noop_scope)
    monkeypatch.setattr(main, "STATE", {"committed_rows": list(rows)})
    monkeypatch.setattr(main, "_resolve_engineering_plan_pdf_paths",
                        lambda sid: ([Path(plan)] if plan else []))
    monkeypatch.setattr(cache, "enabled", lambda: cache_on)
    monkeypatch.setenv("TRUELINE_PDF_FIRST_ENGINE", "1")


# ── gate ─────────────────────────────────────────────────────────────────────
def test_gate_default_off_and_on(monkeypatch):
    monkeypatch.delenv("TRUELINE_MRQ_EVIDENCE_PRESEED", raising=False)
    assert main._mrq_preseed_enabled() is False
    monkeypatch.setenv("TRUELINE_MRQ_EVIDENCE_PRESEED", "1")
    assert main._mrq_preseed_enabled() is True


# ── _preseed_mrq_evidence: gating + no-op safety ─────────────────────────────
def test_preseed_flag_off_is_noop(monkeypatch):
    calls = []
    monkeypatch.setattr(cache, "get_or_build", lambda *a, **k: calls.append(1))
    monkeypatch.delenv("TRUELINE_MRQ_EVIDENCE_PRESEED", raising=False)
    main._preseed_mrq_evidence("sid-1")
    assert calls == []  # flag off -> never touches the cache


def test_preseed_skips_when_cache_off(monkeypatch):
    calls = []
    monkeypatch.setenv("TRUELINE_MRQ_EVIDENCE_PRESEED", "1")
    _ready(monkeypatch, rows=[{"source_file": "bore_log7.xlsx"}], plan="p.pdf", cache_on=False)
    monkeypatch.setattr(cache, "get_or_build", lambda *a, **k: calls.append(1))
    main._preseed_mrq_evidence("sid-1")
    assert calls == []  # cache off -> skip


def test_preseed_skips_when_not_ready(monkeypatch):
    calls = []
    monkeypatch.setenv("TRUELINE_MRQ_EVIDENCE_PRESEED", "1")
    monkeypatch.setattr(cache, "get_or_build", lambda *a, **k: calls.append(1))
    _ready(monkeypatch, rows=[{"source_file": "bore_log7.xlsx"}], plan=None)   # no plan
    main._preseed_mrq_evidence("sid-1")
    _ready(monkeypatch, rows=[], plan="p.pdf")                                 # no rows
    main._preseed_mrq_evidence("sid-1")
    assert calls == []  # not ready -> skip both orderings


def test_preseed_warms_cache_when_ready(monkeypatch):
    seen = {}

    def _gob(sid, rows, plan, card_dir, builder, observer=None):
        seen.update(sid=sid, rows=rows, plan=plan, card_dir=card_dir, builder=builder)
        return {"source": {"logs": ["log7"]}}

    monkeypatch.setenv("TRUELINE_MRQ_EVIDENCE_PRESEED", "1")
    _ready(monkeypatch, rows=[{"source_file": "bore_log7.xlsx"}], plan="p.pdf")
    monkeypatch.setattr(cache, "get_or_build", _gob)
    main._preseed_mrq_evidence("sid-1")
    assert seen["sid"] == "sid-1"
    assert seen["plan"] == "p.pdf"
    # reuses the SAME builder Match Review uses
    assert seen["builder"] is pdf_first_adapter.build_session_evidence_from_committed_rows


def test_preseed_builder_failure_is_swallowed(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("build blew up")

    monkeypatch.setenv("TRUELINE_MRQ_EVIDENCE_PRESEED", "1")
    _ready(monkeypatch, rows=[{"source_file": "bore_log7.xlsx"}], plan="p.pdf")
    monkeypatch.setattr(cache, "get_or_build", _boom)
    main._preseed_mrq_evidence("sid-1")  # must NOT raise


def test_preseed_cache_hit_avoids_duplicate_build(monkeypatch, tmp_path):
    # REAL cache + get_or_build: prove a warm hit skips a second build.
    plan = tmp_path / "plan.pdf"
    plan.write_bytes(b"%PDF-1.4 test")
    builds = []

    def _builder(plan_pdf, rows, card_out_dir=None):
        builds.append(1)
        return {"source": {"logs": ["log7"]}, "placements": []}

    monkeypatch.setenv("TRUELINE_MRQ_EVIDENCE_PRESEED", "1")
    monkeypatch.setenv("TRUELINE_MRQ_EVIDENCE_CACHE", "1")
    monkeypatch.setenv("TRUELINE_PDF_FIRST_ENGINE", "1")
    monkeypatch.setattr(main, "_session_scope", _noop_scope)
    monkeypatch.setattr(main, "STATE", {"committed_rows": [{"source_file": "bore_log7.xlsx"}]})
    monkeypatch.setattr(main, "_resolve_engineering_plan_pdf_paths", lambda sid: [plan])
    monkeypatch.setattr(pdf_first_adapter, "build_session_evidence_from_committed_rows", _builder)
    cache.clear()
    main._preseed_mrq_evidence("sid-hit")
    main._preseed_mrq_evidence("sid-hit")
    assert builds == [1]  # built once (cold); second call hit the warm cache
    cache.clear()


# ── upload endpoint scheduling (flag OFF schedules nothing / ON schedules one) ─
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


def _run_bore_upload(monkeypatch, preseed_on):
    monkeypatch.setattr(main, "_resolve_engineering_plan_session_id", lambda s, q: "sid-1")
    monkeypatch.setattr(main, "_is_closeout_locked", lambda: False)
    monkeypatch.setattr(main, "_read_bore_log_rows", lambda b, n: [{"source_file": n, "station": "0+00"}])
    monkeypatch.setattr(main, "_rebuild_field_data_outputs", lambda **k: None)
    monkeypatch.setattr(main, "_summary_payload", lambda: {})
    monkeypatch.setattr(main, "_session_scope", _noop_scope)
    monkeypatch.setattr(main, "STATE", {})
    if preseed_on:
        monkeypatch.setenv("TRUELINE_MRQ_EVIDENCE_PRESEED", "1")
    else:
        monkeypatch.delenv("TRUELINE_MRQ_EVIDENCE_PRESEED", raising=False)
    bt = _CapturingBT()
    asyncio.run(main.upload_structured_bore_files(
        _FakeRequest(), bt, [_FakeUpload("bore_log7.xlsx")], "sid-1"))
    return bt


def test_upload_endpoint_schedules_nothing_when_flag_off(monkeypatch):
    bt = _run_bore_upload(monkeypatch, preseed_on=False)
    assert bt.tasks == []


def test_upload_endpoint_schedules_one_task_when_flag_on(monkeypatch):
    bt = _run_bore_upload(monkeypatch, preseed_on=True)
    assert len(bt.tasks) == 1
    fn, args, _ = bt.tasks[0]
    assert fn is main._preseed_mrq_evidence
    assert args == ("sid-1",)


# ── A+B+C gate: session-level preseed status (persisted, worker-independent) ──
def test_set_preseed_status_writes_block(monkeypatch):
    monkeypatch.setattr(main, "_session_scope", _noop_scope)
    st = {}
    monkeypatch.setattr(main, "STATE", st)
    main._set_preseed_status("sid-1", "building", rows=50)
    assert st["mrq_preseed"] == {"status": "building", "rows": 50}


def test_set_preseed_status_never_raises(monkeypatch):
    @contextlib.contextmanager
    def _boom_scope(_sid):
        raise RuntimeError("scope down")
        yield  # pragma: no cover
    monkeypatch.setattr(main, "_session_scope", _boom_scope)
    main._set_preseed_status("sid-1", "building")  # must NOT raise (best-effort)


def test_preseed_status_ready_on_build(monkeypatch):
    monkeypatch.setenv("TRUELINE_MRQ_EVIDENCE_PRESEED", "1")
    _ready(monkeypatch, rows=[{"source_file": "bore_log7.xlsx"}], plan="p.pdf")
    monkeypatch.setattr(cache, "get_or_build", lambda *a, **k: {"source": {"logs": ["log7"]}})
    main._preseed_mrq_evidence("sid-1")
    assert main.STATE.get("mrq_preseed", {}).get("status") == "ready"


def test_preseed_status_skipped_not_ready(monkeypatch):
    monkeypatch.setenv("TRUELINE_MRQ_EVIDENCE_PRESEED", "1")
    _ready(monkeypatch, rows=[], plan="p.pdf")  # no rows -> not_ready
    main._preseed_mrq_evidence("sid-1")
    assert main.STATE.get("mrq_preseed", {}).get("status") == "skipped:not_ready"


def test_preseed_status_failed_on_builder_error(monkeypatch):
    monkeypatch.setenv("TRUELINE_MRQ_EVIDENCE_PRESEED", "1")
    _ready(monkeypatch, rows=[{"source_file": "bore_log7.xlsx"}], plan="p.pdf")

    def _boom(*a, **k):
        raise RuntimeError("build blew up")

    monkeypatch.setattr(cache, "get_or_build", _boom)
    main._preseed_mrq_evidence("sid-1")  # must NOT raise
    assert str(main.STATE.get("mrq_preseed", {}).get("status", "")).startswith("failed:")


def test_upload_sets_scheduled_status_when_on(monkeypatch):
    bt = _run_bore_upload(monkeypatch, preseed_on=True)
    assert len(bt.tasks) == 1
    assert main.STATE.get("mrq_preseed") == {"status": "scheduled"}


def test_upload_no_status_key_when_flag_off(monkeypatch):
    bt = _run_bore_upload(monkeypatch, preseed_on=False)
    assert bt.tasks == []
    assert "mrq_preseed" not in main.STATE  # OFF -> no key -> FE gate inert / byte-identical


# ── is_cached read-only peek (drives the MRQ endpoint "preparing" guard) ─────
def test_is_cached_cold_warm_flag_off(monkeypatch, tmp_path):
    plan = tmp_path / "plan.pdf"
    plan.write_bytes(b"%PDF-1.4 test")
    rows = [{"source_file": "bore_log7.xlsx"}]
    cache.clear()
    monkeypatch.setenv("TRUELINE_MRQ_EVIDENCE_CACHE", "1")
    assert cache.is_cached("sid-c", rows, str(plan)) is False          # cold
    cache.get_or_build("sid-c", rows, str(plan), None, lambda *a, **k: {"x": 1})
    assert cache.is_cached("sid-c", rows, str(plan)) is True           # warm (same key)
    assert cache.is_cached("sid-other", rows, str(plan)) is False      # different session
    monkeypatch.setenv("TRUELINE_MRQ_EVIDENCE_CACHE", "0")
    assert cache.is_cached("sid-c", rows, str(plan)) is False          # flag off -> always cold
    cache.clear()
