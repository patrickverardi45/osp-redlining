"""Optional error observability — a DEFAULT-OFF, dependency-optional Sentry-style seam.

``init_observability(settings)`` is a NO-OP unless a DSN is configured AND the optional ``sentry-sdk``
package is installed. It NEVER raises: a missing DSN returns False (local/dev/CI untouched); a DSN with the
SDK absent logs one warning and returns False. When it does activate, it is configured to NEVER send request
bodies / upload contents (``send_default_pii=False``, ``max_request_body_size="never"``) — the redline/source
payloads and tenant data stay out of the observability provider.

This keeps observability an explicit *deployment* decision backed by a proven provider, not something baked
into the app. ``sentry-sdk`` is intentionally NOT a hard requirement in ``requirements.txt``; a deployment
that wants observability installs it and sets the DSN. Env: ``FIELDROUTE_SENTRY_DSN`` (or ``SENTRY_DSN``).
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from truelinev2.config import Settings

_LOG = logging.getLogger("truelinev2.observability")


def init_observability(settings: "Settings") -> bool:
    """Initialize error observability if — and only if — a DSN is configured and ``sentry-sdk`` is present.

    Returns True when a provider was initialized, False otherwise. Never raises: any missing dependency or
    absent DSN is a silent, safe no-op so the app runs identically without observability configured.
    """
    dsn = settings.observability_dsn
    if not dsn:
        return False
    try:
        import sentry_sdk  # optional dependency — not in requirements.txt by default
    except ImportError:
        _LOG.warning(
            "observability DSN is set but 'sentry-sdk' is not installed; skipping observability (no crash). "
            "Install sentry-sdk in the deployment to enable it."
        )
        return False

    sentry_sdk.init(
        dsn=dsn,
        environment=settings.observability_environment,
        # Privacy-safe defaults: never attach PII or request/upload bodies. The redline/source payloads and
        # tenant identity must never leave the app through the observability channel.
        send_default_pii=False,
        max_request_body_size="never",
        traces_sample_rate=settings.observability_traces_sample_rate,
    )
    _LOG.info("observability initialized (environment=%s)", settings.observability_environment)
    return True
