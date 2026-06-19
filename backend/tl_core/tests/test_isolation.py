"""Fail-closed tenant/session isolation — the inverse of the monolith's permissive
`if caller is None: return` (Stream-6 1a) and anonymous session minting (1b)."""
from __future__ import annotations

import pytest

from tl_core.context import IsolationError, TenantId, require_context
from tl_core.security.isolation import assert_owns, scoped_prefix


def test_blank_tenant_rejected():
    with pytest.raises(IsolationError):
        require_context("", "s1")


def test_blank_session_rejected():
    with pytest.raises(IsolationError):
        require_context("acme", "")


def test_uuid_tenant_rejected():
    # tenant key must be a pilot slug, never a company UUID (Stream-6 1d footgun).
    with pytest.raises(IsolationError):
        TenantId("123e4567-e89b-12d3-a456-426614174000")


def test_assert_owns_allows_match():
    ctx = require_context("acme", "s1")
    assert_owns(ctx, "acme")  # must not raise


def test_assert_owns_denies_mismatch():
    ctx = require_context("acme", "s1")
    with pytest.raises(IsolationError):
        assert_owns(ctx, "globex")


def test_assert_owns_denies_none_owner():
    # A missing owner is DENIED (fail-closed), unlike the monolith's no-op.
    ctx = require_context("acme", "s1")
    with pytest.raises(IsolationError):
        assert_owns(ctx, None)


def test_scoped_prefix():
    assert scoped_prefix(require_context("acme", "s1")) == "acme/s1"
