import pytest

from truelinev2.context import IsolationError, TenantId, require_context
from truelinev2.security.isolation import assert_owns, scoped_prefix


def test_blank_tenant():
    with pytest.raises(IsolationError):
        require_context("", "s1")


def test_blank_session():
    with pytest.raises(IsolationError):
        require_context("acme", "")


def test_uuid_tenant_rejected():
    with pytest.raises(IsolationError):
        TenantId("123e4567-e89b-12d3-a456-426614174000")


def test_assert_owns():
    ctx = require_context("acme", "s1")
    assert_owns(ctx, "acme")  # ok
    with pytest.raises(IsolationError):
        assert_owns(ctx, "other")
    with pytest.raises(IsolationError):
        assert_owns(ctx, None)
    assert scoped_prefix(ctx) == "acme/s1"
