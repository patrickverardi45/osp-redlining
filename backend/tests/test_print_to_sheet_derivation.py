"""PI.4A — print-to-sheet derivation unit tests.

Covers the three pure helpers:
  - derive_confirmed_sheet_set
  - union_confirmed_sheet_sets
  - derive_print_to_sheet_index

Architectural invariants (codified in wiki/pi-4a-...-design.md §1.2):
  I-1  sheet_labels exposure is evidence exposure only.
  I-2  Helpers consume only surfaced deterministic evidence.

The synthetic unit suites use inline dicts / sets / lists — no PDF
dependencies, no fixture gating. A single fixture-gated test class
locks the Brenham AutoCAD byte-equivalence against an inline expected
mapping `{str(N): [N] for N in 1..30}` (no backend.main import).
"""

from __future__ import annotations

import copy
import os
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from backend.app.services import engineering_plan_parser as pp


# ---------------------------------------------------------------------------
# Fixture resolution (mirrors test_engineering_plan_parser.py)
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


# ===========================================================================
# derive_confirmed_sheet_set
# ===========================================================================


class TestDeriveConfirmedSheetSetInputValidation(unittest.TestCase):
    def test_none_input_returns_empty_set(self) -> None:
        self.assertEqual(pp.derive_confirmed_sheet_set(None), set())  # type: ignore[arg-type]

    def test_non_dict_input_returns_empty_set(self) -> None:
        for bad in ([], "not a dict", 42, object()):
            self.assertEqual(
                pp.derive_confirmed_sheet_set(bad),  # type: ignore[arg-type]
                set(),
                msg=f"unexpected output for {bad!r}",
            )

    def test_dict_missing_all_channels_returns_empty_set(self) -> None:
        self.assertEqual(pp.derive_confirmed_sheet_set({}), set())
        self.assertEqual(
            pp.derive_confirmed_sheet_set({"unrelated": "key"}), set()
        )


class TestDeriveConfirmedSheetSetSingleChannel(unittest.TestCase):
    def test_drawing_index_channel_only(self) -> None:
        out = pp.derive_confirmed_sheet_set({
            "drawing_index": [
                {"page": 1, "file_name": "X.DWG", "sheet_number": 3},
                {"page": 1, "file_name": "Y.DWG", "sheet_number": 5},
            ],
        })
        self.assertEqual(out, {3, 5})

    def test_sheet_labels_channel_only(self) -> None:
        out = pp.derive_confirmed_sheet_set({
            "sheet_labels": [
                {"page": 1, "sheet_label": 4, "raw_text": "SHEET 4"},
            ],
        })
        self.assertEqual(out, {4})

    def test_title_block_channel_only(self) -> None:
        out = pp.derive_confirmed_sheet_set({
            "title_block": {"sheet_number_first_seen": 1},
        })
        self.assertEqual(out, {1})

    def test_matchlines_channel_only(self) -> None:
        out = pp.derive_confirmed_sheet_set({
            "matchlines": [
                {"page": 1, "references_sheet": 6, "raw_text": "..."},
            ],
        })
        self.assertEqual(out, {6})


class TestDeriveConfirmedSheetSetMultiChannelUnion(unittest.TestCase):
    def test_all_four_channels_agree(self) -> None:
        out = pp.derive_confirmed_sheet_set({
            "drawing_index": [
                {"file_name": "X.DWG", "sheet_number": 1},
                {"file_name": "Y.DWG", "sheet_number": 2},
                {"file_name": "Z.DWG", "sheet_number": 3},
            ],
            "sheet_labels": [
                {"page": 1, "sheet_label": 1},
                {"page": 2, "sheet_label": 2},
                {"page": 3, "sheet_label": 3},
            ],
            "title_block": {"sheet_number_first_seen": 1},
            "matchlines": [{"references_sheet": 2}, {"references_sheet": 3}],
        })
        self.assertEqual(out, {1, 2, 3})

    def test_channels_disagree_produces_union(self) -> None:
        out = pp.derive_confirmed_sheet_set({
            "drawing_index": [
                {"sheet_number": 1},
                {"sheet_number": 2},
            ],
            "sheet_labels": [
                {"sheet_label": 3},
                {"sheet_label": 4},
            ],
        })
        self.assertEqual(out, {1, 2, 3, 4})


class TestDeriveConfirmedSheetSetFilters(unittest.TestCase):
    def test_sheet_zero_dropped_at_every_channel(self) -> None:
        out = pp.derive_confirmed_sheet_set({
            "drawing_index": [{"sheet_number": 0}, {"sheet_number": 5}],
            "sheet_labels": [{"sheet_label": 0}, {"sheet_label": 7}],
            "title_block": {"sheet_number_first_seen": 0},
            "matchlines": [{"references_sheet": 0}, {"references_sheet": 9}],
        })
        self.assertEqual(out, {5, 7, 9})
        self.assertNotIn(0, out)

    def test_negative_non_int_non_dict_per_record_dropped(self) -> None:
        out = pp.derive_confirmed_sheet_set({
            "drawing_index": [
                {"sheet_number": -3},
                "not-a-dict",
                {"sheet_number": "five"},
                {"sheet_number": 5},
            ],
            "sheet_labels": [
                None,
                {"sheet_label": -1},
                {"sheet_label": True},   # booleans rejected by _coerce_nonneg_int
                {"sheet_label": 8},
            ],
        })
        self.assertEqual(out, {5, 8})


# ===========================================================================
# union_confirmed_sheet_sets
# ===========================================================================


class TestUnionConfirmedSheetSets(unittest.TestCase):
    def test_empty_list_returns_empty_set(self) -> None:
        self.assertEqual(pp.union_confirmed_sheet_sets([]), set())

    def test_single_pdf_set_passthrough(self) -> None:
        self.assertEqual(
            pp.union_confirmed_sheet_sets([{1, 2, 3}]),
            {1, 2, 3},
        )

    def test_three_pdf_union(self) -> None:
        out = pp.union_confirmed_sheet_sets([{1, 2}, {2, 3}, {4}])
        self.assertEqual(out, {1, 2, 3, 4})

    def test_immutability_of_inputs(self) -> None:
        sets: List[Set[int]] = [{1, 2}, {3}]
        snapshot = [set(s) for s in sets]
        pp.union_confirmed_sheet_sets(sets)
        for got, expected in zip(sets, snapshot):
            self.assertEqual(got, expected)

    def test_input_validation_returns_empty(self) -> None:
        # None / string / bytes / non-iterable outer all return empty set.
        for bad in (None, "abc", b"abc", 42):
            self.assertEqual(
                pp.union_confirmed_sheet_sets(bad),  # type: ignore[arg-type]
                set(),
                msg=f"unexpected output for {bad!r}",
            )

    def test_non_iterable_elements_silently_skipped(self) -> None:
        # 42 is not iterable; should be skipped. The valid {3} contributes.
        out = pp.union_confirmed_sheet_sets([{1, 2}, 42, None, {3}])  # type: ignore[list-item]
        self.assertEqual(out, {1, 2, 3})

    def test_non_positive_ints_filtered_from_elements(self) -> None:
        out = pp.union_confirmed_sheet_sets([{0, 1, 2}, {-5, 3, 0}])
        self.assertEqual(out, {1, 2, 3})


# ===========================================================================
# derive_print_to_sheet_index
# ===========================================================================


class TestDerivePrintToSheetIndexInputValidation(unittest.TestCase):
    def test_none_tokens_returns_empty_dict(self) -> None:
        self.assertEqual(
            pp.derive_print_to_sheet_index({1, 2, 3}, None),
            {},
        )

    def test_empty_tokens_returns_empty_dict(self) -> None:
        self.assertEqual(
            pp.derive_print_to_sheet_index({1, 2, 3}, []),
            {},
        )

    def test_none_catalog_all_tokens_refuse(self) -> None:
        out = pp.derive_print_to_sheet_index(None, ["1", "2"])
        self.assertEqual(out, {"1": None, "2": None})


class TestDerivePrintToSheetIndexRefusal(unittest.TestCase):
    def test_non_numeric_token_refused(self) -> None:
        out = pp.derive_print_to_sheet_index({1, 2, 3}, ["T-3"])
        self.assertEqual(out, {"T-3": None})

    def test_negative_token_refused(self) -> None:
        # `str.isdigit()` returns False for "-5", so the token is refused.
        out = pp.derive_print_to_sheet_index({1, 2, 3, 5}, ["-5"])
        self.assertEqual(out, {"-5": None})

    def test_zero_token_refused(self) -> None:
        out = pp.derive_print_to_sheet_index({1, 2, 3}, ["0"])
        self.assertEqual(out, {"0": None})

    def test_int_not_in_catalog_refused(self) -> None:
        out = pp.derive_print_to_sheet_index({1, 2, 3}, ["99"])
        self.assertEqual(out, {"99": None})


class TestDerivePrintToSheetIndexSuccess(unittest.TestCase):
    def test_all_tokens_confirmed_emit_single_element_lists(self) -> None:
        out = pp.derive_print_to_sheet_index({1, 2, 3}, ["1", "2", "3"])
        self.assertEqual(out, {"1": [1], "2": [2], "3": [3]})

    def test_mixed_success_and_refusal_preserved_per_token(self) -> None:
        out = pp.derive_print_to_sheet_index({1, 2, 3}, ["1", "99", "3"])
        self.assertEqual(out, {"1": [1], "99": None, "3": [3]})


# ===========================================================================
# Immutability
# ===========================================================================


class TestImmutability(unittest.TestCase):
    def test_derive_confirmed_sheet_set_does_not_mutate_input(self) -> None:
        payload: Dict[str, Any] = {
            "drawing_index": [{"sheet_number": 3}, {"sheet_number": 5}],
            "sheet_labels": [{"sheet_label": 4}],
            "title_block": {"sheet_number_first_seen": 1},
            "matchlines": [{"references_sheet": 6}],
        }
        snapshot = copy.deepcopy(payload)
        pp.derive_confirmed_sheet_set(payload)
        self.assertEqual(payload, snapshot)

    def test_derive_print_to_sheet_index_does_not_mutate_catalog_or_tokens(self) -> None:
        catalog: Set[int] = {1, 2, 3}
        tokens = ["1", "99", "3"]
        catalog_snapshot = set(catalog)
        tokens_snapshot = list(tokens)
        pp.derive_print_to_sheet_index(catalog, tokens)
        self.assertEqual(catalog, catalog_snapshot)
        self.assertEqual(tokens, tokens_snapshot)


# ===========================================================================
# Fixture-gated Brenham AutoCAD byte-equivalence
# ===========================================================================


@unittest.skipUnless(_BRENHAM_AVAILABLE, _SKIP_REASON)
class TestBrenhamAutocadPrintIndexByteEquivalence(unittest.TestCase):
    """Locks PI.4A's derived view as byte-equivalent to the constant's
    Job A projection on the Brenham AutoCAD fixture.

    The expected mapping `{str(N): [N] for N in 1..30}` is INLINE — no
    import of backend.main is performed. This mirrors the projection
    that `_print_to_sheets_from_packet_index()` produces today from
    `CURRENT_PACKET_PRINT_SHEET_INDEX` for tokens 1..30.

    Test gates the implementation's byte-equivalence prerequisite for
    any future PI.4B activation phase.
    """

    AUTOCAD_FILENAME = "Brenham - Phase 5_07-15-25.pdf"

    def test_derived_print_to_sheet_index_matches_inline_expected(self) -> None:
        path = _fixture_path(self.AUTOCAD_FILENAME)
        if path is None:
            self.skipTest(f"{self.AUTOCAD_FILENAME} not present in fixture dir")
        all_result = pp.extract_all(str(path))
        catalog = pp.derive_confirmed_sheet_set(all_result)
        derived = pp.derive_print_to_sheet_index(
            catalog,
            [str(n) for n in range(1, 31)],
        )
        expected: Dict[str, Optional[List[int]]] = {
            str(n): [n] for n in range(1, 31)
        }
        self.assertEqual(derived, expected)


# ===========================================================================
# PI.4B.1 — Multi-fixture Brenham union byte-equivalence proof
# ===========================================================================
#
# Authorization gate for PI.4B.2. Proves that the union across all three
# Brenham Phase 5 fixtures (Revision summary + AutoCAD plan set + Fieldwire
# tabular report), each passed through PI.4A's derive_confirmed_sheet_set,
# then through union_confirmed_sheet_sets, produces the catalog {1..30}.
# When that union is then fed to derive_print_to_sheet_index for tokens
# "1".."30", the result must byte-equal the inline expected mapping
# `{str(N): [N] for N in 1..30}` — which mirrors the
# `print_token -> [sheet_int]` projection that
# `_print_to_sheets_from_packet_index()` emits today from
# `CURRENT_PACKET_PRINT_SHEET_INDEX`.
#
# The expected mapping is INLINE. No backend.main import. No
# CURRENT_PACKET_PRINT_SHEET_INDEX reference. No runtime dependency.
# No flag activation. No cache-primitive dependency — this test
# exercises the PI.4A pure helpers directly against the same evidence
# path used by PI.4A's byte-equivalence proof.
# ===========================================================================


@unittest.skipUnless(_BRENHAM_AVAILABLE, _SKIP_REASON)
class TestBrenhamMultiFixtureUnionByteEquivalence(unittest.TestCase):
    """PI.4B.1 — load-bearing multi-fixture union byte-equivalence proof.

    setUpClass runs `pp.extract_all` + `pp.derive_confirmed_sheet_set`
    once per fixture and caches the resulting three `Set[int]` on the
    class. All six test methods consume the cached sets — no per-test
    PDF parsing.

    Skips the entire class when any of the three Brenham fixtures is
    absent (the multi-fixture union claim is undefined otherwise).
    """

    REVISION_FILENAME = "BRENHAM PH5 - 18-02-2026.pdf"
    AUTOCAD_FILENAME = "Brenham - Phase 5_07-15-25.pdf"
    FIELDWIRE_FILENAME = "BRENHAM_PHASE_5_New_report_2026-03-23_1774300147.pdf"

    EXPECTED_SHEET_RANGE: Set[int] = set(range(1, 31))

    # Sheets that PI.3 must surface from the Revision PDF's three DWG
    # entries (BRENHAM-PH-5_P_3.DWG, _P_23.DWG, _P_24.DWG). Revision is
    # allowed to carry additional sheets via matchlines / sheet_labels;
    # the test only asserts this set as the lower bound.
    REVISION_REQUIRED_DWG_SHEETS: Set[int] = {3, 23, 24}

    _revision_set: Set[int]
    _autocad_set: Set[int]
    _fieldwire_set: Set[int]

    @classmethod
    def setUpClass(cls) -> None:
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
                "PI.4B.1 requires all three Brenham fixtures; missing: "
                + ", ".join(missing)
            )
        cls._revision_set = pp.derive_confirmed_sheet_set(
            pp.extract_all(str(revision_path))
        )
        cls._autocad_set = pp.derive_confirmed_sheet_set(
            pp.extract_all(str(autocad_path))
        )
        cls._fieldwire_set = pp.derive_confirmed_sheet_set(
            pp.extract_all(str(fieldwire_path))
        )

    def test_revision_catalog_contains_required_dwg_sheets_and_subset_of_thirty(self) -> None:
        self.assertTrue(
            self.REVISION_REQUIRED_DWG_SHEETS.issubset(self._revision_set),
            msg=(
                f"Revision catalog {sorted(self._revision_set)} missing "
                f"required DWG-derived sheets "
                f"{sorted(self.REVISION_REQUIRED_DWG_SHEETS)}"
            ),
        )
        self.assertTrue(
            self._revision_set.issubset(self.EXPECTED_SHEET_RANGE),
            msg=(
                f"Revision catalog {sorted(self._revision_set)} contains "
                f"value(s) outside {{1..30}}"
            ),
        )

    def test_fieldwire_catalog_subset_of_thirty_with_positive_ints(self) -> None:
        self.assertTrue(
            self._fieldwire_set.issubset(self.EXPECTED_SHEET_RANGE),
            msg=(
                f"Fieldwire catalog {sorted(self._fieldwire_set)} contains "
                f"value(s) outside {{1..30}}"
            ),
        )
        for v in self._fieldwire_set:
            self.assertIsInstance(v, int)
            self.assertGreater(v, 0)

    def test_autocad_catalog_equals_one_through_thirty(self) -> None:
        self.assertEqual(
            self._autocad_set,
            self.EXPECTED_SHEET_RANGE,
            msg=(
                "AutoCAD catalog does not equal {1..30}; got "
                f"{sorted(self._autocad_set)}"
            ),
        )

    def test_three_fixture_union_equals_one_through_thirty(self) -> None:
        union = pp.union_confirmed_sheet_sets([
            self._revision_set,
            self._autocad_set,
            self._fieldwire_set,
        ])
        self.assertEqual(
            union,
            self.EXPECTED_SHEET_RANGE,
            msg=(
                "Multi-fixture union does not equal {1..30}; got "
                f"{sorted(union)}"
            ),
        )

    def test_union_is_order_independent_across_permutations(self) -> None:
        forward = pp.union_confirmed_sheet_sets([
            self._revision_set,
            self._autocad_set,
            self._fieldwire_set,
        ])
        reverse = pp.union_confirmed_sheet_sets([
            self._fieldwire_set,
            self._autocad_set,
            self._revision_set,
        ])
        autocad_first = pp.union_confirmed_sheet_sets([
            self._autocad_set,
            self._revision_set,
            self._fieldwire_set,
        ])
        self.assertEqual(forward, reverse)
        self.assertEqual(forward, autocad_first)

    def test_derive_print_to_sheet_index_over_union_byte_equals_inline_expected(self) -> None:
        # THE PI.4B.2 AUTHORIZATION PROOF.
        # The inline expected mapping mirrors the projection of
        # CURRENT_PACKET_PRINT_SHEET_INDEX entries 1..30 today — but
        # nothing here imports backend.main or references the constant.
        union = pp.union_confirmed_sheet_sets([
            self._revision_set,
            self._autocad_set,
            self._fieldwire_set,
        ])
        derived = pp.derive_print_to_sheet_index(
            union,
            [str(n) for n in range(1, 31)],
        )
        expected: Dict[str, Optional[List[int]]] = {
            str(n): [n] for n in range(1, 31)
        }
        self.assertEqual(derived, expected)


if __name__ == "__main__":
    unittest.main()
