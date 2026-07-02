"""Tests for the DEFAULT-OFF, dependency-optional observability seam.

Locks: no DSN -> no-op False; DSN but sentry-sdk absent -> no-op False (never raises); DSN + a (faked) SDK
-> initialized with privacy-safe config (no PII, no request/upload bodies); Settings.from_env reads the
generic env names; create_app still builds with observability unconfigured.
"""
from __future__ import annotations

import dataclasses
import sys
import types

from truelinev2.api.app import create_app
from truelinev2.api.observability import init_observability
from truelinev2.config import Settings


def _settings(**over) -> Settings:
    return dataclasses.replace(Settings.for_proof(), **over)


def test_no_dsn_is_noop():
    assert init_observability(_settings()) is False


def test_dsn_without_sdk_is_noop_and_never_raises(monkeypatch):
    # Force `import sentry_sdk` to fail deterministically even if the package happens to be installed.
    monkeypatch.setitem(sys.modules, "sentry_sdk", None)
    s = _settings(observability_dsn="https://public@example.invalid/1")
    assert init_observability(s) is False


def test_dsn_with_sdk_initializes_privacy_safe(monkeypatch):
    captured = {}
    fake = types.ModuleType("sentry_sdk")
    fake.init = lambda **kw: captured.update(kw)  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "sentry_sdk", fake)
    s = _settings(
        observability_dsn="https://public@example.invalid/1",
        observability_environment="staging",
        observability_traces_sample_rate=0.0,
    )
    assert init_observability(s) is True
    assert captured["dsn"] == "https://public@example.invalid/1"
    assert captured["environment"] == "staging"
    # Never leak PII or request/upload bodies to the provider.
    assert captured["send_default_pii"] is False
    assert captured["max_request_body_size"] == "never"


def test_from_env_reads_generic_dsn_and_env(monkeypatch):
    monkeypatch.setenv("TL2_ALLOWED_ORIGINS", "http://localhost:3000")
    monkeypatch.setenv("FIELDROUTE_SENTRY_DSN", "https://public@example.invalid/2")
    monkeypatch.setenv("FIELDROUTE_ENV", "production")
    s = Settings.from_env()
    assert s.observability_dsn == "https://public@example.invalid/2"
    assert s.observability_environment == "production"


def test_from_env_falls_back_to_sentry_dsn_and_defaults_off(monkeypatch):
    monkeypatch.setenv("TL2_ALLOWED_ORIGINS", "http://localhost:3000")
    monkeypatch.delenv("FIELDROUTE_SENTRY_DSN", raising=False)
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    assert Settings.from_env().observability_dsn is None  # unconfigured => off
    monkeypatch.setenv("SENTRY_DSN", "https://public@example.invalid/3")
    assert Settings.from_env().observability_dsn == "https://public@example.invalid/3"


def test_create_app_builds_with_observability_unconfigured():
    # No DSN -> create_app must build cleanly (observability init is a silent no-op).
    app = create_app(_settings())
    assert app is not None
