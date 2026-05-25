"""Tests for performance audit telemetry helpers.

Covers the env-gated _emit_perf_audit_row + _perf_audit_timer context
manager + _perf_audit_emit_and_pass shortcut.

Env-off must be byte-identical to legacy behavior (no JSONL writes,
no schema fields anywhere). Env-on must produce well-formed JSONL rows
with schema_version "perf-audit-1". Telemetry failures must be
swallowed and never propagate to the caller.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List

os.environ.setdefault("TRUELINE_JWT_SECRET", "perf-audit-test")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "perf-audit-test-auth")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

import backend.main as M


ENV_FLAG = "TRUELINE_PERF_AUDIT"


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            out.append(json.loads(line))
    return out


def _clear_audit_file() -> None:
    p = M.PERFORMANCE_AUDIT_PATH
    if p.exists():
        p.unlink()


# ── A. Env-off byte-identity ─────────────────────────────────────────────────


def test_env_off_emit_writes_nothing(monkeypatch) -> None:
    monkeypatch.delenv(ENV_FLAG, raising=False)
    _clear_audit_file()
    M._emit_perf_audit_row("test.stage", 42.0, phase="test_phase")
    assert not M.PERFORMANCE_AUDIT_PATH.exists()


def test_env_off_timer_contextmanager_yields_without_emission(monkeypatch) -> None:
    monkeypatch.delenv(ENV_FLAG, raising=False)
    _clear_audit_file()
    with M._perf_audit_timer("test.stage", phase="test_phase"):
        _ = 1 + 1
    assert not M.PERFORMANCE_AUDIT_PATH.exists()


def test_env_off_emit_and_pass_skips_bytes_measurement(monkeypatch) -> None:
    """Env-off path must skip the json.dumps(result) byte measurement
    entirely (otherwise large payloads pay measurement cost even with
    the flag off). Passes the result through untouched."""
    monkeypatch.delenv(ENV_FLAG, raising=False)
    _clear_audit_file()
    result = {"foo": "bar"}
    t0 = time.perf_counter()
    got = M._perf_audit_emit_and_pass("test.stage", t0, result, measure_bytes=True)
    assert got is result
    assert not M.PERFORMANCE_AUDIT_PATH.exists()


# ── B. Env-on row shape ─────────────────────────────────────────────────────


def test_env_on_emit_writes_row_with_required_fields(monkeypatch) -> None:
    monkeypatch.setenv(ENV_FLAG, "1")
    _clear_audit_file()
    M._emit_perf_audit_row(
        "kmz.build_route_catalog",
        123.456,
        phase="kmz_upload",
        stage_detail="design.kmz",
        bytes_in=2048,
        output_count=600,
    )
    rows = _read_jsonl(M.PERFORMANCE_AUDIT_PATH)
    assert len(rows) == 1
    r = rows[0]
    assert r["schema_version"] == "perf-audit-1"
    assert r["stage"] == "kmz.build_route_catalog"
    assert r["elapsed_ms"] == 123.456
    assert r["phase"] == "kmz_upload"
    assert r["stage_detail"] == "design.kmz"
    assert r["bytes_in"] == 2048
    assert r["output_count"] == 600
    assert "ts_iso" in r and r["ts_iso"].endswith("+00:00")


def test_env_on_timer_writes_row_with_elapsed_ms(monkeypatch) -> None:
    monkeypatch.setenv(ENV_FLAG, "1")
    _clear_audit_file()
    with M._perf_audit_timer("test.stage", phase="rebuild_full"):
        time.sleep(0.01)  # 10 ms — well above timer noise floor
    rows = _read_jsonl(M.PERFORMANCE_AUDIT_PATH)
    assert len(rows) == 1
    r = rows[0]
    assert r["stage"] == "test.stage"
    assert r["phase"] == "rebuild_full"
    # elapsed_ms must be >= 10ms (the sleep duration) and reasonably
    # bounded above (sleep timing on Windows can have wide jitter, so
    # allow up to 200ms before flagging instrumentation overhead bug).
    assert 10.0 <= r["elapsed_ms"] <= 200.0


def test_env_on_emit_and_pass_passes_result_and_measures_bytes(monkeypatch) -> None:
    monkeypatch.setenv(ENV_FLAG, "1")
    _clear_audit_file()
    result = {"foo": "bar", "size": list(range(100))}
    t0 = time.perf_counter()
    got = M._perf_audit_emit_and_pass(
        "payload.summary_build", t0, result, phase="summary_payload", measure_bytes=True,
    )
    assert got is result
    rows = _read_jsonl(M.PERFORMANCE_AUDIT_PATH)
    assert len(rows) == 1
    r = rows[0]
    assert r["stage"] == "payload.summary_build"
    assert r["phase"] == "summary_payload"
    # bytes_out must equal len(json.dumps(result, default=str))
    assert r["bytes_out"] == len(json.dumps(result, default=str))


def test_env_on_emit_truncates_oversized_stage_detail(monkeypatch) -> None:
    """stage_detail is truncated at 200 chars (defense against
    inadvertent enormous identifiers like full file paths)."""
    monkeypatch.setenv(ENV_FLAG, "1")
    _clear_audit_file()
    huge = "x" * 1000
    M._emit_perf_audit_row("test", 1.0, stage_detail=huge)
    rows = _read_jsonl(M.PERFORMANCE_AUDIT_PATH)
    assert len(rows) == 1
    assert len(rows[0]["stage_detail"]) == 200


# ── C. Failure isolation ─────────────────────────────────────────────────────


def test_emit_failure_swallowed_does_not_raise(monkeypatch, tmp_path) -> None:
    """If the JSONL file path is invalid / unwritable, the helper must
    swallow the OSError. The caller continues uninterrupted."""
    monkeypatch.setenv(ENV_FLAG, "1")
    # Point the audit path at a non-existent directory so open() fails.
    monkeypatch.setattr(
        M, "PERFORMANCE_AUDIT_PATH", tmp_path / "nonexistent_dir" / "out.jsonl"
    )
    # Should not raise — silent swallow.
    M._emit_perf_audit_row("test.stage", 5.0)


def test_timer_failure_inside_block_does_not_break_emission(monkeypatch) -> None:
    """If the wrapped block raises, the exception propagates AND the
    timer emits its measurement on the way out (telemetry never blocks
    error propagation, but also doesn't lose the timing signal)."""
    monkeypatch.setenv(ENV_FLAG, "1")
    _clear_audit_file()

    class _Sentinel(RuntimeError):
        pass

    try:
        with M._perf_audit_timer("test.fail_stage", phase="test"):
            raise _Sentinel("boom")
    except _Sentinel:
        pass
    else:
        raise AssertionError("Exception should have propagated")
    rows = _read_jsonl(M.PERFORMANCE_AUDIT_PATH)
    assert len(rows) == 1
    assert rows[0]["stage"] == "test.fail_stage"


# ── D. _perf_audit_enabled() helper ──────────────────────────────────────────


def test_perf_audit_enabled_returns_false_when_unset(monkeypatch) -> None:
    monkeypatch.delenv(ENV_FLAG, raising=False)
    assert M._perf_audit_enabled() is False


def test_perf_audit_enabled_returns_true_when_one(monkeypatch) -> None:
    monkeypatch.setenv(ENV_FLAG, "1")
    assert M._perf_audit_enabled() is True


def test_perf_audit_enabled_returns_false_for_zero(monkeypatch) -> None:
    monkeypatch.setenv(ENV_FLAG, "0")
    assert M._perf_audit_enabled() is False


def test_perf_audit_enabled_returns_false_for_garbage(monkeypatch) -> None:
    monkeypatch.setenv(ENV_FLAG, "yes")
    assert M._perf_audit_enabled() is False


# ── E. Schema preservation ───────────────────────────────────────────────────


def test_schema_version_constant_matches_emitted_rows(monkeypatch) -> None:
    monkeypatch.setenv(ENV_FLAG, "1")
    _clear_audit_file()
    M._emit_perf_audit_row("test", 1.0)
    rows = _read_jsonl(M.PERFORMANCE_AUDIT_PATH)
    assert len(rows) == 1
    assert rows[0]["schema_version"] == M.PERFORMANCE_AUDIT_SCHEMA_VERSION
    assert M.PERFORMANCE_AUDIT_SCHEMA_VERSION == "perf-audit-1"
