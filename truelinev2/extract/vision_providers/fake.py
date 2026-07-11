"""Deterministic, fixture-driven FAKE vision provider -- for tests and proofs only. Never calls a network,
never invents a reading: it reads a pre-built, schema-shaped ``HandwrittenPageExtraction`` dict from a
fixtures directory and returns it verbatim (defaulting ``method``/``extractor`` when the fixture omits
them); a page with no matching fixture file refuses honestly rather than fabricating a result.

Wired the SAME way the real vendor messages-API adapter is: ``build_provider(config)`` reads its own env
var (``TL2_HANDWRITTEN_FAKE_FIXTURES``, a directory path) through ``config.get_env`` -- this seam never
names that env var, or any other provider's env var, anywhere outside the provider's own module.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Dict

from truelinev2.contracts.handwritten_extraction import VISION_OCR
from truelinev2.extract.vision_providers import ProviderOutputInvalid, ProviderUnavailable

# This provider's OWN env var -- read only through ``config.get_env`` inside ``build_provider``, never
# named by the seam (``truelinev2/extract/handwritten_borelog.py``) or by ``config.py``.
_FIXTURES_DIR_ENV = "TL2_HANDWRITTEN_FAKE_FIXTURES"
_DEFAULT_EXTRACTOR_NAME = "fake_vision_fixture"


def build_provider(config) -> Callable[[bytes, dict], dict]:
    """``config`` is the small read-only view ``handwritten_borelog.py``'s factory passes every provider
    module: ``timeout_seconds`` + ``get_env`` (bound ``os.environ.get``). No fixtures-dir env value ->
    ``ProviderUnavailable`` (the factory maps this to the existing NOT_CONFIGURED page refusal)."""
    fixtures_dir = config.get_env(_FIXTURES_DIR_ENV)
    if not fixtures_dir:
        raise ProviderUnavailable("%s is not set" % _FIXTURES_DIR_ENV)
    root = Path(fixtures_dir)

    def _call(page_png_bytes: bytes, context: Dict) -> dict:
        sha = context.get("sha256")
        page_index = context.get("page_index")
        fixture_path = root / ("%s-p%s.json" % (sha, page_index))
        if not fixture_path.is_file():
            # Honest refusal -- never invents a reading when no fixture exists for this exact page.
            raise ProviderOutputInvalid("no fixture for this page")
        try:
            record = json.loads(fixture_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ProviderOutputInvalid("fixture file is not valid JSON") from exc
        if not isinstance(record, dict):
            raise ProviderOutputInvalid("fixture file is not a JSON object")
        record = dict(record)
        record.setdefault("method", VISION_OCR)
        record.setdefault("extractor", _DEFAULT_EXTRACTOR_NAME)
        return record

    return _call
