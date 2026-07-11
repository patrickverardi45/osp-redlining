"""Vision-provider package -- the VENDOR ISOLATION BOUNDARY for Phase-1 handwritten bore-log extraction.

``truelinev2/extract/handwritten_borelog.py`` loads a provider module BY DOTTED MODULE PATH at runtime
(the ``TL2_HANDWRITTEN_BORELOG_PROVIDER`` env value, e.g. ``"truelinev2.extract.vision_providers.fake"``)
and calls its ``build_provider(config) -> provider_callable``. No vendor/model literal lives in the seam
or in ``config.py`` -- exactly ONE module under this package is a real vendor messages-API adapter (see
its own module docstring for which one, and for the vendor name it alone is allowed to name).

Two exception types a provider module may raise to signal a SPECIFIC, honest refusal back through the
seam (``truelinev2/extract/handwritten_borelog.py``'s ``_load_provider``/``_run_provider_with_timeout``):

  ``ProviderUnavailable``   -- raised by ``build_provider(config)`` when the provider cannot be
                               constructed at all (SDK not installed, a required env var is unset, ...).
                               Mapped by the seam to the existing ``HANDWRITTEN_VISION_PROVIDER_NOT_CONFIGURED``
                               page refusal (same code an unset/unknown provider name already produces).
  ``ProviderOutputInvalid`` -- raised by a provider CALLABLE when it cannot produce a valid extraction
                               for the ONE page it was given (malformed/refused model response, missing
                               fixture, ...). Mapped by the seam to the existing
                               ``HANDWRITTEN_PROVIDER_OUTPUT_INVALID`` page refusal.

Any OTHER exception a provider callable raises (network errors, SDK auth/permission errors, a bare
``RuntimeError``, ...) is an UNNAMED provider failure: the seam maps it to the new
``HANDWRITTEN_PROVIDER_ERROR`` page refusal, with the reason reduced to the exception's CLASS NAME ONLY --
never its message, which may embed request/URL/header details that must never be logged or surfaced.
"""
from __future__ import annotations


class ProviderUnavailable(Exception):
    """``build_provider(config)`` cannot construct a usable provider callable (missing SDK, missing a
    required env var, ...). The seam maps this to ``HANDWRITTEN_VISION_PROVIDER_NOT_CONFIGURED``."""


class ProviderOutputInvalid(Exception):
    """A provider CALLABLE could not produce a valid extraction for the page it was given (malformed
    output, no fixture, a refused model response, ...). The seam maps this to
    ``HANDWRITTEN_PROVIDER_OUTPUT_INVALID``."""


__all__ = ["ProviderUnavailable", "ProviderOutputInvalid"]
