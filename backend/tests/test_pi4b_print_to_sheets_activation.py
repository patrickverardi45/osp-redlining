"""PI.4B.2 — feature-flagged derived-preferred activation seam tests.

Exercises `_print_to_sheets_from_packet_index` under the
`TRUELINE_PI4A_DERIVED_PRINT_INDEX` flag (default OFF). Covers:

  - Flag OFF byte-identical legacy behavior + no STATE write
  - Flag ON, no session_id -> constant fallback for every token
  - Flag ON, mocked catalog matching constant -> derived_byte_equivalent
  - Flag ON, partial catalog -> derived + constant_fallback mix
  - Flag ON, synthetic disagreement -> constant wins; example recorded
  - Diagnostic shape: required keys + types
  - Verbose sub-flag toggles `attribution_per_token`
  - Disagreement examples capped at _PI4B_DISAGREEMENT_EXAMPLES_CAP
  - Fixture-gated end-to-end Brenham proof via PI.4B.0 cache primitive

All non-fixture tests mock `_build_confirmed_sheet_set_for_session`
and/or `pp.derive_print_to_sheet_index` for determinism. STATE is
snapshotted + restored around every test via `_StateScope`.
"""

from __future__ import annotations

import os

# Set required env vars before importing backend.main (mirrors the prelude in
# test_confirmed_sheet_set_cache.py, test_p53_diagnostic_emission.py, etc.).
os.environ.setdefault("TRUELINE_JWT_SECRET", "pi4b2-test-secret")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "pi4b2-test-auth-secret")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from unittest.mock import patch

from backend import main as M
from backend.app.services import engineering_plan_parser as pp


# ---------------------------------------------------------------------------
# Brenham fixture resolution (mirrors test_print_to_sheet_derivation.py)
# ---------------------------------------------------------------------------

_FIXTURE_DEFAULT = Path(
    r"C:\Nova\knowledge\TrueLine-Wiki\raw\trueline\engineering-plans\brenham"
)


def _resolve_fixture_dir() -> Optional[Path]:
    env = os.environ.get("TRUELINE_PLAN_FIXTURE_DIR", "").strip()
    if env:
        p = Path(env)
        if p.is_dir():
            return p
    if _FIXTURE_DEFAULT.is_dir():
        return _FIXTURE_DEFAULT
    return None


_BRENHAM_DIR = _resolve_fixture_dir()
_BRENHAM_AVAILABLE = _BRENHAM_DIR is not None
_SKIP_REASON = (
    "Brenham plan PDFs not found. Set TRUELINE_PLAN_FIXTURE_DIR to a "
    "directory containing the Brenham Phase 5 engineering-plan PDFs to "
    "enable fixture-gated tests."
)


def _fixture_path(name: str) -> Optional[Path]:
    if _BRENHAM_DIR is None:
        return None
    p = _BRENHAM_DIR / name
    return p if p.is_file() else None


# ---------------------------------------------------------------------------
# STATE swap helper — mirrors test_confirmed_sheet_set_cache.py
# ---------------------------------------------------------------------------


class _StateScope:
    """Snapshot M.STATE on enter, restore on exit. Lets each test mutate
    STATE freely without leaking into sibling tests.
    """

    def __init__(self, initial: Optional[Dict[str, Any]] = None) -> None:
        self.initial = initial or {}
        self._saved: Dict[str, Any] = {}

    def __enter__(self) -> Dict[str, Any]:
        self._saved = dict(M.STATE)
        M.STATE.clear()
        M.STATE.update(self.initial)
        return M.STATE

    def __exit__(self, *args: Any) -> None:
        M.STATE.clear()
        M.STATE.update(self._saved)


# ---------------------------------------------------------------------------
# Flag context manager — sets/clears the two PI.4B env vars deterministically
# ---------------------------------------------------------------------------


class _FlagContext:
    """Set the PI.4B flag env vars to a specific state for the duration of
    the `with` block. Snapshots whatever value the env had before and
    restores it on exit.
    """

    def __init__(self, derived_on: bool = False, verbose_on: bool = False) -> None:
        self.derived_on = derived_on
        self.verbose_on = verbose_on
        self._sentinel = object()
        self._saved: Dict[str, Any] = {}

    def __enter__(self) -> "_FlagContext":
        for key, on in (
            (M._PI4B_DERIVED_FLAG_ENV, self.derived_on),
            (M._PI4B_VERBOSE_FLAG_ENV, self.verbose_on),
        ):
            self._saved[key] = os.environ.get(key, self._sentinel)
            if on:
                os.environ[key] = "1"
            else:
                os.environ.pop(key, None)
        return self

    def __exit__(self, *args: Any) -> None:
        for key, prior in self._saved.items():
            if prior is self._sentinel:
                os.environ.pop(key, None)
            else:
                os.environ[key] = prior  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Reference: the byte-identical projection of CURRENT_PACKET_PRINT_SHEET_INDEX
# ---------------------------------------------------------------------------


def _expected_constant_projection() -> Dict[str, List[int]]:
    out: Dict[str, List[int]] = {}
    for token, entry in M.CURRENT_PACKET_PRINT_SHEET_INDEX.items():
        sheet = entry.get("sheet")
        if isinstance(sheet, int) and not isinstance(sheet, bool):
            out[str(token)] = [int(sheet)]
    return out


def _full_constant_catalog() -> Set[int]:
    return {
        int(entry["sheet"])
        for entry in M.CURRENT_PACKET_PRINT_SHEET_INDEX.values()
        if isinstance(entry.get("sheet"), int)
        and not isinstance(entry.get("sheet"), bool)
    }


# ===========================================================================
# Flag OFF — byte-identical legacy + no STATE write
# ===========================================================================


class TestFlagOffByteIdentical(unittest.TestCase):
    """S2.1: flag OFF -> projection byte-identical to today; no STATE write."""

    def test_flag_off_output_byte_identical_to_constant_projection(self) -> None:
        expected = _expected_constant_projection()
        with _StateScope(), _FlagContext(derived_on=False):
            self.assertFalse(M._trueline_pi4a_derived_print_index_enabled())
            got = M._print_to_sheets_from_packet_index()
            self.assertEqual(got, expected)

    def test_flag_off_does_not_write_attribution_state_key(self) -> None:
        with _StateScope(), _FlagContext(derived_on=False):
            M._print_to_sheets_from_packet_index()
            self.assertNotIn(M._PI4B_ATTRIBUTION_STATE_KEY, M.STATE)


# ===========================================================================
# Flag ON, no session_id — catalog unavailable, full constant fallback
# ===========================================================================


class TestFlagOnNoSession(unittest.TestCase):
    """S2.2: flag ON + empty session_id -> all tokens constant_fallback."""

    def test_no_session_falls_back_to_constant_with_unavailable_source(self) -> None:
        expected = _expected_constant_projection()
        with _StateScope({}), _FlagContext(derived_on=True):
            self.assertTrue(M._trueline_pi4a_derived_print_index_enabled())
            got = M._print_to_sheets_from_packet_index()
            self.assertEqual(got, expected)
            diag = M.STATE.get(M._PI4B_ATTRIBUTION_STATE_KEY)
            self.assertIsInstance(diag, dict)
            self.assertEqual(diag["catalog_source"], M._PI4B_CATALOG_SOURCE_UNAVAILABLE)
            self.assertEqual(diag["catalog_size"], 0)
            self.assertEqual(diag["session_id"], "")
            self.assertEqual(diag["tokens_total"], len(expected))
            self.assertEqual(diag["tokens_constant_fallback"], len(expected))
            self.assertEqual(diag["tokens_derived"], 0)
            self.assertEqual(diag["tokens_disagreement"], 0)
            self.assertEqual(diag["tokens_refused_both"], 0)
            self.assertEqual(diag["disagreement_examples"], [])


# ===========================================================================
# Flag ON, mocked catalog == full constant — all tokens derived_byte_equivalent
# ===========================================================================


class TestFlagOnAllDerivedByteEquivalent(unittest.TestCase):
    """S2.3: flag ON + catalog covers every constant sheet -> all tokens
    emit derived_byte_equivalent; output byte-equal to constant projection.
    """

    def test_all_tokens_emit_derived_byte_equivalent(self) -> None:
        catalog = _full_constant_catalog()
        expected = _expected_constant_projection()
        with _StateScope({"_session_id_hint": "test-session"}), \
                _FlagContext(derived_on=True), \
                patch.object(M, "_build_confirmed_sheet_set_for_session",
                             return_value=set(catalog)):
            got = M._print_to_sheets_from_packet_index()
            self.assertEqual(got, expected)
            diag = M.STATE[M._PI4B_ATTRIBUTION_STATE_KEY]
            self.assertEqual(diag["catalog_size"], len(catalog))
            self.assertEqual(diag["tokens_total"], len(expected))
            self.assertEqual(diag["tokens_derived"], len(expected))
            self.assertEqual(diag["tokens_constant_fallback"], 0)
            self.assertEqual(diag["tokens_disagreement"], 0)
            self.assertEqual(diag["tokens_refused_both"], 0)
            self.assertEqual(diag["disagreement_examples"], [])


# ===========================================================================
# Flag ON, partial catalog — mixed derived + constant_fallback
# ===========================================================================


class TestFlagOnMixedFallback(unittest.TestCase):
    """S2.4: flag ON + catalog covers only some sheets -> derived where
    present in catalog, constant_fallback elsewhere; output byte-equal
    to constant projection (constants are correct for both branches).
    """

    def test_mixed_catalog_derived_where_present_constant_elsewhere(self) -> None:
        partial: Set[int] = {1, 2, 3, 5}
        expected = _expected_constant_projection()
        tokens_in_catalog = sum(
            1 for tok, entry in M.CURRENT_PACKET_PRINT_SHEET_INDEX.items()
            if isinstance(entry.get("sheet"), int)
            and not isinstance(entry.get("sheet"), bool)
            and int(entry["sheet"]) in partial
        )
        tokens_total = len(expected)
        with _StateScope({"_session_id_hint": "test-session"}), \
                _FlagContext(derived_on=True), \
                patch.object(M, "_build_confirmed_sheet_set_for_session",
                             return_value=set(partial)):
            got = M._print_to_sheets_from_packet_index()
            self.assertEqual(got, expected)
            diag = M.STATE[M._PI4B_ATTRIBUTION_STATE_KEY]
            self.assertEqual(diag["tokens_derived"], tokens_in_catalog)
            self.assertEqual(
                diag["tokens_constant_fallback"],
                tokens_total - tokens_in_catalog,
            )
            self.assertEqual(diag["tokens_disagreement"], 0)
            self.assertEqual(diag["tokens_refused_both"], 0)


# ===========================================================================
# Flag ON, synthetic disagreement — constant wins; example recorded
# ===========================================================================


class TestFlagOnDisagreementConstantWins(unittest.TestCase):
    """S2.5: derived returns [7] for token "5" while constant says sheet 5.
    Output uses constant; diagnostic records the disagreement example.
    """

    @staticmethod
    def _fake_derive_with_token5_disagreement(
        catalog: Any, tokens: Any,
    ) -> Dict[str, Optional[List[int]]]:
        mapping: Dict[str, Optional[List[int]]] = {}
        catalog_set = set(catalog) if catalog else set()
        for t in tokens:
            if t == "5":
                mapping[t] = [7]  # injected disagreement
                continue
            if not isinstance(t, str) or not t.isdigit():
                mapping[t] = None
                continue
            n = int(t)
            mapping[t] = [n] if n > 0 and n in catalog_set else None
        return mapping

    def test_disagreement_uses_constant_and_records_example(self) -> None:
        catalog = _full_constant_catalog()
        expected = _expected_constant_projection()
        with _StateScope({"_session_id_hint": "test-session"}), \
                _FlagContext(derived_on=True), \
                patch.object(M, "_build_confirmed_sheet_set_for_session",
                             return_value=set(catalog)), \
                patch.object(M._engineering_plan_parser,
                             "derive_print_to_sheet_index",
                             side_effect=self._fake_derive_with_token5_disagreement):
            got = M._print_to_sheets_from_packet_index()
            self.assertEqual(got["5"], [5])
            self.assertEqual(got, expected)
            diag = M.STATE[M._PI4B_ATTRIBUTION_STATE_KEY]
            self.assertEqual(diag["tokens_disagreement"], 1)
            self.assertEqual(len(diag["disagreement_examples"]), 1)
            example = diag["disagreement_examples"][0]
            self.assertEqual(example["token"], "5")
            self.assertEqual(example["derived_sheet"], 7)
            self.assertEqual(example["constant_sheet"], 5)


# ===========================================================================
# Diagnostic shape — required keys + types
# ===========================================================================


class TestDiagnosticShape(unittest.TestCase):
    """S2.6: flag ON -> diagnostic dict has the required keys with the
    correct types. S2.7 is asserted in TestFlagOffByteIdentical.
    """

    REQUIRED_KEYS = {
        "enabled", "session_id", "catalog_size", "catalog_source",
        "tokens_total", "tokens_derived", "tokens_constant_fallback",
        "tokens_disagreement", "tokens_refused_both", "disagreement_examples",
    }

    def test_required_keys_present_with_correct_types(self) -> None:
        with _StateScope(), _FlagContext(derived_on=True):
            M._print_to_sheets_from_packet_index()
            diag = M.STATE[M._PI4B_ATTRIBUTION_STATE_KEY]
            self.assertEqual(set(diag.keys()), self.REQUIRED_KEYS)
            self.assertIs(diag["enabled"], True)
            self.assertIsInstance(diag["session_id"], str)
            self.assertIsInstance(diag["catalog_size"], int)
            self.assertIsInstance(diag["catalog_source"], str)
            self.assertIsInstance(diag["tokens_total"], int)
            self.assertIsInstance(diag["tokens_derived"], int)
            self.assertIsInstance(diag["tokens_constant_fallback"], int)
            self.assertIsInstance(diag["tokens_disagreement"], int)
            self.assertIsInstance(diag["tokens_refused_both"], int)
            self.assertIsInstance(diag["disagreement_examples"], list)


# ===========================================================================
# Verbose sub-flag — attribution_per_token presence
# ===========================================================================


class TestVerboseSubFlag(unittest.TestCase):
    """S2.8 / S2.9: attribution_per_token is included iff
    TRUELINE_PI4B_VERBOSE_ATTRIBUTION is ON.
    """

    def test_verbose_on_includes_attribution_per_token(self) -> None:
        partial: Set[int] = {1, 2, 3}
        with _StateScope({"_session_id_hint": "test-session"}), \
                _FlagContext(derived_on=True, verbose_on=True), \
                patch.object(M, "_build_confirmed_sheet_set_for_session",
                             return_value=set(partial)):
            M._print_to_sheets_from_packet_index()
            diag = M.STATE[M._PI4B_ATTRIBUTION_STATE_KEY]
            self.assertIn("attribution_per_token", diag)
            apt = diag["attribution_per_token"]
            self.assertIsInstance(apt, dict)
            # Every constant token is recorded.
            self.assertEqual(
                set(apt.keys()),
                {str(k) for k in M.CURRENT_PACKET_PRINT_SHEET_INDEX},
            )
            # Tokens whose constant sheet is in the catalog get
            # derived_byte_equivalent; the rest get constant_fallback.
            self.assertEqual(apt["1"], M._PI4B_ATTR_DERIVED_BYTE_EQUIVALENT)
            self.assertEqual(apt["2"], M._PI4B_ATTR_DERIVED_BYTE_EQUIVALENT)
            self.assertEqual(apt["3"], M._PI4B_ATTR_DERIVED_BYTE_EQUIVALENT)
            self.assertEqual(apt["4"], M._PI4B_ATTR_CONSTANT_FALLBACK)

    def test_verbose_off_omits_attribution_per_token(self) -> None:
        with _StateScope(), _FlagContext(derived_on=True, verbose_on=False):
            M._print_to_sheets_from_packet_index()
            diag = M.STATE[M._PI4B_ATTRIBUTION_STATE_KEY]
            self.assertNotIn("attribution_per_token", diag)


# ===========================================================================
# Disagreement cap
# ===========================================================================


class TestDisagreementExamplesCap(unittest.TestCase):
    """S2.10: disagreement_examples capped at _PI4B_DISAGREEMENT_EXAMPLES_CAP
    while tokens_disagreement counts every disagreement uncapped.
    """

    @staticmethod
    def _fake_derive_disagree_all(
        catalog: Any, tokens: Any,
    ) -> Dict[str, Optional[List[int]]]:
        # For every token, emit a sheet number guaranteed not to match the
        # constant (99 is outside the 1..30 range used in CURRENT_PACKET_PRINT_SHEET_INDEX).
        return {t: [99] for t in tokens}

    def test_examples_capped_total_uncapped(self) -> None:
        catalog: Set[int] = {99}
        total_tokens = len(M.CURRENT_PACKET_PRINT_SHEET_INDEX)
        self.assertGreater(
            total_tokens,
            M._PI4B_DISAGREEMENT_EXAMPLES_CAP,
            "test prerequisite: constant must hold more tokens than the cap",
        )
        with _StateScope({"_session_id_hint": "test-session"}), \
                _FlagContext(derived_on=True), \
                patch.object(M, "_build_confirmed_sheet_set_for_session",
                             return_value=set(catalog)), \
                patch.object(M._engineering_plan_parser,
                             "derive_print_to_sheet_index",
                             side_effect=self._fake_derive_disagree_all):
            M._print_to_sheets_from_packet_index()
            diag = M.STATE[M._PI4B_ATTRIBUTION_STATE_KEY]
            self.assertEqual(diag["tokens_disagreement"], total_tokens)
            self.assertEqual(
                len(diag["disagreement_examples"]),
                M._PI4B_DISAGREEMENT_EXAMPLES_CAP,
            )


# ===========================================================================
# End-to-end: real Brenham fixtures through PI.4B.0 cache + PI.4B.2 seam
# ===========================================================================


@unittest.skipUnless(_BRENHAM_AVAILABLE, _SKIP_REASON)
class TestBrenhamE2ECacheActivation(unittest.TestCase):
    """End-to-end proof: the real PI.4B.0 cache primitive, fed real Brenham
    PDF paths, produces a catalog that drives the PI.4B.2 seam to emit
    every constant token as derived_byte_equivalent. Second call exercises
    the cache-hit attribution branch.

    The class patches `_resolve_engineering_plan_pdf_paths` to point to
    the three Brenham fixtures so the cache builder runs against real
    PDFs without requiring a true session folder layout on disk.
    """

    REVISION_FILENAME = "BRENHAM PH5 - 18-02-2026.pdf"
    AUTOCAD_FILENAME = "Brenham - Phase 5_07-15-25.pdf"
    FIELDWIRE_FILENAME = "BRENHAM_PHASE_5_New_report_2026-03-23_1774300147.pdf"

    fixture_paths: List[Path]

    @classmethod
    def setUpClass(cls) -> None:
        # Defensive guards. The class decorator
        # `@skipUnless(_BRENHAM_AVAILABLE)` already skips when the resolved
        # fixture directory does not exist. The two checks below additionally
        # skip when the directory exists but does not contain usable PDFs —
        # for example, a checkout where only the JSON lockdown fixtures are
        # present under backend/tests/fixtures/engineering_plans/brenham and
        # no real *.pdf files are available. Without these guards the test
        # would still run, derive 0 tokens, and fail on the
        # `tokens_derived == len(expected)` assertion even though the
        # constant-fallback projection itself would be byte-correct.
        pdf_files = (
            sorted(_BRENHAM_DIR.glob("*.pdf"))
            if _BRENHAM_DIR is not None
            else []
        )
        if not pdf_files:
            raise unittest.SkipTest(
                "PI.4B.2 E2E requires PDF fixtures; resolved directory "
                f"{_BRENHAM_DIR!r} contains 0 PDF files."
            )

        revision_path = _fixture_path(cls.REVISION_FILENAME)
        autocad_path = _fixture_path(cls.AUTOCAD_FILENAME)
        fieldwire_path = _fixture_path(cls.FIELDWIRE_FILENAME)
        missing: List[str] = []
        if revision_path is None:
            missing.append(cls.REVISION_FILENAME)
        if autocad_path is None:
            missing.append(cls.AUTOCAD_FILENAME)
        if fieldwire_path is None:
            missing.append(cls.FIELDWIRE_FILENAME)
        if missing:
            raise unittest.SkipTest(
                "PI.4B.2 E2E requires all three Brenham fixtures; missing: "
                + ", ".join(missing)
            )
        cls.fixture_paths = [revision_path, autocad_path, fieldwire_path]

    def test_first_call_builds_then_second_call_cache_hits(self) -> None:
        expected = _expected_constant_projection()
        session_id = "brenham-e2e-session"
        with _StateScope({"_session_id_hint": session_id}), \
                _FlagContext(derived_on=True), \
                patch.object(M, "_resolve_engineering_plan_pdf_paths",
                             return_value=self.fixture_paths):
            # First call: builds catalog from 3 PDFs.
            got_first = M._print_to_sheets_from_packet_index()
            diag_first = M.STATE[M._PI4B_ATTRIBUTION_STATE_KEY]
            self.assertEqual(got_first, expected)
            self.assertEqual(
                diag_first["catalog_source"],
                f"{M._PI4B_CATALOG_SOURCE_BUILT_PREFIX}3_pdfs",
            )
            self.assertEqual(diag_first["session_id"], session_id)
            self.assertEqual(diag_first["tokens_total"], len(expected))
            self.assertEqual(diag_first["tokens_derived"], len(expected))
            self.assertEqual(diag_first["tokens_constant_fallback"], 0)
            self.assertEqual(diag_first["tokens_disagreement"], 0)
            self.assertEqual(diag_first["tokens_refused_both"], 0)

            # Second call: catalog cache hit.
            got_second = M._print_to_sheets_from_packet_index()
            diag_second = M.STATE[M._PI4B_ATTRIBUTION_STATE_KEY]
            self.assertEqual(got_second, got_first)
            self.assertEqual(
                diag_second["catalog_source"],
                M._PI4B_CATALOG_SOURCE_CACHE_HIT,
            )
            self.assertEqual(diag_second["tokens_derived"], len(expected))


if __name__ == "__main__":
    unittest.main()
