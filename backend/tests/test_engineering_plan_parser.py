"""Tests for engineering_plan_parser.

TWO LAYERS
----------
1. Layer-1 (always runs) — pure pattern, canonicalization, and safe-failure
   tests. No PDF reads required. These guard the regex / canonicalization
   contracts independently of any fixture availability.

2. Layer-2 (fixture-gated) — extraction-behavior assertions against the real
   Brenham Phase 5 engineering-plan PDFs. Skipped when fixtures absent.
   Invariants baseline-locked from the P4 smoke-test run on 2026-05-17.

FIXTURE RESOLUTION (mirrors test_kmz_fidelity_brenham.py)
---------------------------------------------------------
1. $TRUELINE_PLAN_FIXTURE_DIR  (absolute path to a directory)
2. C:\\Nova\\knowledge\\TrueLine-Wiki\\raw\\trueline\\engineering-plans\\brenham\\

If neither resolves, the Layer-2 classes skip with a clear reason.
PDFs are customer engineering data and are NEVER committed to the repo.

COMMAND
-------
    python -m pytest backend/tests/test_engineering_plan_parser.py -v

Required env (also required by every other backend test):
    TRUELINE_JWT_SECRET, TRUELINE_AUTH_JWT_SECRET, TRUELINE_ALLOWED_ORIGINS

IF A LAYER-2 TEST FAILS
-----------------------
A failure means the extractor's output for a real Brenham PDF changed.
Either (a) intentional — investigate the parser change, then update the
invariant constant below, OR (b) unintentional — investigate the regression.
NEVER bump invariants to green without understanding the cause.
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, Optional

_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

# Required env defaults — parser module itself does not consume these, but
# any future co-located import (e.g. `import main`) would. Setting now keeps
# the test resilient to future additions.
os.environ.setdefault("TRUELINE_JWT_SECRET", "lockdown-test-secret")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "lockdown-test-auth-secret")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

from app.services import engineering_plan_parser as pp  # noqa: E402


# ---------------------------------------------------------------------------
# Fixture resolution
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
    "Brenham plan PDFs not found. Set TRUELINE_PLAN_FIXTURE_DIR to a directory "
    "containing the three Brenham Phase 5 engineering-plan PDFs to enable "
    "fixture-gated tests."
)


def _fixture_path(name: str) -> Optional[Path]:
    if _BRENHAM_DIR is None:
        return None
    p = _BRENHAM_DIR / name
    return p if p.is_file() else None


# ===========================================================================
# Layer 1 — always-on pattern / canonicalization / safe-failure tests
# ===========================================================================


class TestApCanonicalization(unittest.TestCase):
    """AP IDs must canonicalize to a stable 'AP-N' form across all observed
    Brenham filename and callout variants."""

    def test_known_variants_canonicalize(self) -> None:
        cases = [
            ("AP-108", "AP-108"),
            ("AP 108", "AP-108"),
            ("AP_108", "AP-108"),
            ("AP108", "AP-108"),
            ("ap-108", "AP-108"),
            ("AP 1000", "AP-1000"),
            ("AP-008", "AP-8"),   # leading zeros stripped
        ]
        for raw, expected in cases:
            self.assertEqual(
                pp._canonicalize_ap(raw),
                expected,
                f"_canonicalize_ap({raw!r}) -> {expected!r}",
            )

    def test_empty_or_invalid_returns_empty_string(self) -> None:
        self.assertEqual(pp._canonicalize_ap(None), "")
        self.assertEqual(pp._canonicalize_ap(""), "")
        self.assertEqual(pp._canonicalize_ap("AP-"), "")
        self.assertEqual(pp._canonicalize_ap("no digits"), "")


class TestSpliceCanonicalization(unittest.TestCase):
    def test_known_variants_canonicalize(self) -> None:
        cases = [
            ("SPLICE LOC 27", "SPLICE-27"),
            ("SPLICE POINT 126", "SPLICE-126"),
            ("PROP. SPLICE POINT 28", "SPLICE-28"),
            ("SPLICE LOCATION 5", "SPLICE-5"),
            ("splice loc 99", "SPLICE-99"),
        ]
        for raw, expected in cases:
            self.assertEqual(
                pp._canonicalize_splice(raw),
                expected,
                f"_canonicalize_splice({raw!r}) -> {expected!r}",
            )

    def test_empty_or_invalid_returns_empty_string(self) -> None:
        self.assertEqual(pp._canonicalize_splice(None), "")
        self.assertEqual(pp._canonicalize_splice(""), "")
        self.assertEqual(pp._canonicalize_splice("SPLICE LOC"), "")


class TestStationHelpers(unittest.TestCase):
    def test_station_to_ft(self) -> None:
        self.assertEqual(pp._station_to_ft(0, 0), 0)
        self.assertEqual(pp._station_to_ft(15, 13), 1513)
        self.assertEqual(pp._station_to_ft(1, 5), 105)
        self.assertEqual(pp._station_to_ft(100, 0), 10000)

    def test_format_station(self) -> None:
        self.assertEqual(pp._format_station(15, 13), "15+13")
        self.assertEqual(pp._format_station(5, 5), "5+05")
        self.assertEqual(pp._format_station(0, 0), "0+00")


class TestDispatchDetection(unittest.TestCase):
    def test_fieldwire_signature(self) -> None:
        self.assertEqual(pp._dispatch_from_strings("Fieldwire", None, None), "fieldwire")
        self.assertEqual(pp._dispatch_from_strings(None, "Created with Fieldwire", None), "fieldwire")
        self.assertEqual(pp._dispatch_from_strings(None, None, "fieldwire export"), "fieldwire")

    def test_autocad_signature(self) -> None:
        self.assertEqual(
            pp._dispatch_from_strings("pdfplot16.hdi 16.03.191.00000", None, None),
            "autocad",
        )
        self.assertEqual(
            pp._dispatch_from_strings(None, "AutoCAD Map 3D 2024", None),
            "autocad",
        )

    def test_unknown_when_no_signature(self) -> None:
        self.assertEqual(pp._dispatch_from_strings(None, None, None), "unknown")
        self.assertEqual(pp._dispatch_from_strings("", "", ""), "unknown")
        self.assertEqual(pp._dispatch_from_strings("Some Other Tool", None, None), "unknown")


class TestSafeFailureContract(unittest.TestCase):
    """Every extractor must return empty/default outputs on missing or
    unreadable inputs. None may raise."""

    NONEXISTENT = "/this/path/does/not/exist/fake_plan.pdf"

    def test_missing_file_metadata(self) -> None:
        md = pp.extract_metadata(self.NONEXISTENT)
        self.assertEqual(md["page_count"], 0)
        self.assertEqual(md["dispatch_hint"], "unknown")
        self.assertIsNone(md["producer"])
        self.assertIsNone(md["creator"])

    def test_missing_file_title_block_all_none(self) -> None:
        tb = pp.extract_title_block(self.NONEXISTENT)
        self.assertIsNone(tb["project"])
        self.assertIsNone(tb["address"])
        self.assertIsNone(tb["revision_date"])

    def test_missing_file_list_extractors_return_empty(self) -> None:
        for extractor in (
            pp.extract_matchlines,
            pp.extract_station_callouts,
            pp.extract_ap_ids,
            pp.extract_splice_ids,
            pp.extract_drawing_index,
            pp.extract_fieldwire_table,
        ):
            self.assertEqual(
                extractor(self.NONEXISTENT),
                [],
                f"{extractor.__name__} should return [] for missing file",
            )

    def test_directory_path_returns_empty(self) -> None:
        path = str(_BACKEND_DIR)
        self.assertEqual(pp.extract_metadata(path)["page_count"], 0)
        self.assertEqual(pp.extract_matchlines(path), [])
        self.assertEqual(pp.extract_ap_ids(path), [])

    def test_malformed_pdf_bytes_return_empty(self) -> None:
        """A file with .pdf extension but garbage content must NOT raise."""
        tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        try:
            tmp.write(b"%PDF-not-really-a-pdf-just-garbage-bytes")
            tmp.flush()
            tmp.close()
            self.assertEqual(pp.extract_metadata(tmp.name)["page_count"], 0)
            self.assertEqual(pp.extract_matchlines(tmp.name), [])
            self.assertEqual(pp.extract_ap_ids(tmp.name), [])
            self.assertEqual(pp.extract_splice_ids(tmp.name), [])
            self.assertEqual(pp.extract_fieldwire_table(tmp.name), [])
        finally:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass

    def test_extract_all_schema_complete(self) -> None:
        result = pp.extract_all(self.NONEXISTENT)
        expected_keys = {
            "metadata", "title_block", "matchlines", "station_callouts",
            "ap_ids", "splice_ids", "drawing_index", "fieldwire_table",
        }
        self.assertEqual(set(result.keys()), expected_keys)
        for key in (
            "matchlines", "station_callouts", "ap_ids",
            "splice_ids", "drawing_index", "fieldwire_table",
        ):
            self.assertEqual(
                result[key], [],
                f"extract_all()[{key!r}] should be [] for missing file",
            )


# ===========================================================================
# Layer 2 — fixture-gated extraction-behavior tests
# Invariants locked from the P4 smoke-test run on 2026-05-17.
# ===========================================================================


_BRENHAM_REVISION: Dict[str, Any] = {
    "filename": "BRENHAM PH5 - 18-02-2026.pdf",
    "page_count": 4,
    "dispatch_hint": "unknown",
    "title_block_project": "BRENHAM PH 5",
    "matchline_count": 9,
    "expected_matchline_samples": [
        "MATCHLINE STA 16+25 - SEE SHEET 4",
        "MATCHLINE STA 9+38/5+43 - SEE SHEET 23",
        "MATCHLINE STA 2+07 - SEE SHEET 23",
    ],
    "station_callout_total": 47,
    "station_callout_kinds": {"range": 21, "equation": 3, "single": 23},
    "ap_id_canonicals": {"AP-109", "AP-111", "AP-115", "AP-117", "AP-119", "AP-120"},
    "splice_id_total": 9,
    "splice_id_canonicals": {"SPLICE-27", "SPLICE-28", "SPLICE-126"},
    "drawing_index_count": 3,
    "dwg_files": {
        "BRENHAM-PH-5_P_3.DWG",
        "BRENHAM-PH-5_P_23.DWG",
        "BRENHAM-PH-5_P_24.DWG",
    },
    "fieldwire_row_count": 0,
}


_BRENHAM_AUTOCAD: Dict[str, Any] = {
    "filename": "Brenham - Phase 5_07-15-25.pdf",
    "page_count": 43,
    "dispatch_hint": "autocad",
    "producer_contains": "pdfplot",
    "title_block_project": "BRENHAM PH 5",
    "title_block_revision_date": "JULY 15, 2025",
    "title_block_original_date": "MAY 22, 2025",
    "matchline_count": 48,
    "station_callout_total": 376,
    "station_callout_kinds": {"range": 147, "equation": 26, "single": 203},
    "ap_id_unique": 46,
    "ap_canonicals_must_include": {"AP-105", "AP-109", "AP-111", "AP-115", "AP-117"},
    "splice_id_total": 59,
    "splice_id_unique": 15,
    "splice_canonicals_must_include": {"SPLICE-13", "SPLICE-27", "SPLICE-28"},
    "drawing_index_count": 40,
    "fieldwire_row_count": 0,
}


_BRENHAM_FIELDWIRE: Dict[str, Any] = {
    "filename": "BRENHAM_PHASE_5_New_report_2026-03-23_1774300147.pdf",
    "page_count": 80,
    "dispatch_hint": "fieldwire",
    "producer_contains": "Fieldwire",
    "title_block_project": "BRENHAM PHASE 5",
    "matchline_count": 0,
    "station_callout_total": 4,
    "ap_id_unique": 70,
    "ap_canonicals_must_include": {"AP-105", "AP-108", "AP-1000"},
    "splice_id_total": 0,
    "drawing_index_count": 0,
    "fieldwire_row_count": 65,
    "fieldwire_first_row_id": 474,
    "fieldwire_first_row_ap_canonical": "AP-108",
    "fieldwire_first_row_status": "VERIFIED",
}


class _PdfExtractionMixin:
    """Shared setUpClass that runs every extractor once per PDF and caches.

    PI.1: switched from per-extractor calls to a single extract_all
    orchestration so the cached lists carry the new `source_sheet`
    enrichment. The per-extractor attribute names and their record
    contracts are unchanged; only the new additive `source_sheet`
    field appears on records.
    """

    INVARIANTS: Dict[str, Any] = {}

    @classmethod
    def setUpClass(cls) -> None:  # type: ignore[override]
        super().setUpClass()  # type: ignore[misc]
        path = _fixture_path(cls.INVARIANTS["filename"])
        if path is None:
            raise unittest.SkipTest(
                f"{cls.INVARIANTS['filename']} not present in fixture directory"
            )
        cls.path = str(path)
        cls.all_result = pp.extract_all(cls.path)
        cls.metadata = cls.all_result["metadata"]
        cls.title_block = cls.all_result["title_block"]
        cls.matchlines = cls.all_result["matchlines"]
        cls.station_callouts = cls.all_result["station_callouts"]
        cls.ap_ids = cls.all_result["ap_ids"]
        cls.splice_ids = cls.all_result["splice_ids"]
        cls.drawing_index = cls.all_result["drawing_index"]
        cls.fieldwire_table = cls.all_result["fieldwire_table"]

    # PI.1 source_sheet enrichment contract — inherited by every Brenham
    # fixture class. Verifies the new additive field is present and well-
    # typed without assuming any specific page-to-sheet mapping (which is
    # fixture-dependent and validated via the helper's unit tests).

    def test_pi1_source_sheet_present_on_all_list_records(self) -> None:  # type: ignore[no-untyped-def]
        for label, records in (
            ("matchlines",       self.matchlines),
            ("station_callouts", self.station_callouts),
            ("ap_ids",           self.ap_ids),
            ("splice_ids",       self.splice_ids),
            ("drawing_index",    self.drawing_index),
            ("fieldwire_table",  self.fieldwire_table),
        ):
            for r in records:
                self.assertIn(  # type: ignore[attr-defined]
                    "source_sheet", r,
                    msg=f"{label} record missing source_sheet: {r!r}",
                )

    def test_pi1_source_sheet_is_int_or_none(self) -> None:  # type: ignore[no-untyped-def]
        for records in (
            self.matchlines, self.station_callouts, self.ap_ids,
            self.splice_ids, self.drawing_index, self.fieldwire_table,
        ):
            for r in records:
                v = r.get("source_sheet")
                self.assertTrue(  # type: ignore[attr-defined]
                    v is None or isinstance(v, int),
                    msg=f"source_sheet must be int or None, got {v!r}",
                )

    def test_pi1_drawing_index_source_sheet_consistent_with_filename(self) -> None:  # type: ignore[no-untyped-def]
        """For each drawing_index record whose filename parses to a sheet
        number, the record's source_sheet must be either that number
        (single-DWG-per-page case) or None (multi-DWG-per-page conflict).
        Never a different number — that would indicate a derivation bug.
        """
        for r in self.drawing_index:
            parsed = pp._parse_sheet_from_dwg_filename(r.get("file_name"))
            if parsed is None:
                continue
            v = r.get("source_sheet")
            self.assertTrue(  # type: ignore[attr-defined]
                v is None or v == parsed,
                msg=(f"drawing_index record source_sheet={v!r} does not "
                     f"agree with parsed sheet {parsed} for filename "
                     f"{r.get('file_name')!r} on page {r.get('page')!r}"),
            )

    # PI.2 anchor-station co-location contract — inherited by every Brenham
    # fixture class. Verifies the new additive fields are present and well-
    # typed without locking specific per-anchor station values (fixture
    # replay is the source of truth for those).

    def test_pi2_station_fields_present_on_ap_and_splice_records(self) -> None:  # type: ignore[no-untyped-def]
        for label, records in (
            ("ap_ids", self.ap_ids),
            ("splice_ids", self.splice_ids),
        ):
            for r in records:
                for key in (
                    "station_ft", "station_source", "station_confidence",
                    "station_reason", "station_distance_chars",
                ):
                    self.assertIn(  # type: ignore[attr-defined]
                        key, r,
                        msg=f"{label} record missing {key}: {r!r}",
                    )

    def test_pi2_station_ft_when_present_is_non_negative_int(self) -> None:  # type: ignore[no-untyped-def]
        # Station 0+00 is a valid real-world station value (start of
        # plan stationing). Allow station_ft == 0; only reject negatives
        # and non-int types.
        for records in (self.ap_ids, self.splice_ids):
            for r in records:
                v = r.get("station_ft")
                if v is None:
                    continue
                self.assertIsInstance(v, int)  # type: ignore[attr-defined]
                self.assertGreaterEqual(v, 0)  # type: ignore[attr-defined]

    def test_pi2_station_confidence_value_in_enum(self) -> None:  # type: ignore[no-untyped-def]
        allowed = {"high", "medium", "low", "uncertain"}
        for records in (self.ap_ids, self.splice_ids):
            for r in records:
                self.assertIn(  # type: ignore[attr-defined]
                    r.get("station_confidence"), allowed,
                    msg=f"unexpected station_confidence: {r!r}",
                )

    # PI.3 drawing-index sheet_number contract — inherited by every Brenham
    # fixture class. Verifies the new additive field is present and exactly
    # tracks the standalone _parse_sheet_from_dwg_filename output, with
    # `None` as the canonical refusal sentinel. Independent of source_sheet,
    # which answers a different question (page→sheet attribution).

    def test_pi3_drawing_index_sheet_number_consistent_with_filename(self) -> None:  # type: ignore[no-untyped-def]
        """Every drawing_index record carries `sheet_number`. When the
        filename parses to a positive int via
        _parse_sheet_from_dwg_filename, sheet_number equals that int.
        Otherwise sheet_number is None. Multiplicity is preserved — the
        same parsed sheet on multiple records is fine."""
        for r in self.drawing_index:
            self.assertIn(  # type: ignore[attr-defined]
                "sheet_number", r,
                msg=f"drawing_index record missing sheet_number: {r!r}",
            )
            parsed = pp._parse_sheet_from_dwg_filename(r.get("file_name"))
            v = r.get("sheet_number")
            if isinstance(parsed, int) and parsed > 0:
                self.assertEqual(  # type: ignore[attr-defined]
                    v, parsed,
                    msg=(f"sheet_number={v!r} disagrees with parsed sheet "
                         f"{parsed} for filename {r.get('file_name')!r}"),
                )
            else:
                self.assertIsNone(  # type: ignore[attr-defined]
                    v,
                    msg=(f"sheet_number={v!r} should be None for "
                         f"unparseable filename {r.get('file_name')!r}"),
                )


@unittest.skipUnless(_BRENHAM_AVAILABLE, _SKIP_REASON)
class TestBrenhamRevisionExtraction(_PdfExtractionMixin, unittest.TestCase):
    """4-page revision summary PDF (small, fast)."""

    INVARIANTS = _BRENHAM_REVISION

    def test_page_count_and_dispatch(self) -> None:
        self.assertEqual(self.metadata["page_count"], self.INVARIANTS["page_count"])
        self.assertEqual(self.metadata["dispatch_hint"], self.INVARIANTS["dispatch_hint"])

    def test_title_block_project(self) -> None:
        self.assertEqual(self.title_block["project"], self.INVARIANTS["title_block_project"])

    def test_matchline_count_and_samples(self) -> None:
        self.assertEqual(len(self.matchlines), self.INVARIANTS["matchline_count"])
        raw_set = {r["raw_text"] for r in self.matchlines}
        for sample in self.INVARIANTS["expected_matchline_samples"]:
            self.assertIn(sample, raw_set, f"missing matchline: {sample}")

    def test_matchline_records_have_required_fields(self) -> None:
        for r in self.matchlines:
            self.assertIn("page", r)
            self.assertIn("station", r)
            self.assertIn("station_ft", r)
            self.assertIn("references_sheet", r)
            self.assertIsInstance(r["station_ft"], int)
            self.assertIsInstance(r["references_sheet"], int)

    def test_station_callout_distribution(self) -> None:
        self.assertEqual(len(self.station_callouts), self.INVARIANTS["station_callout_total"])
        kinds = {"range": 0, "equation": 0, "single": 0}
        for r in self.station_callouts:
            kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
        self.assertEqual(kinds, self.INVARIANTS["station_callout_kinds"])

    def test_ap_canonical_set(self) -> None:
        canon_set = {r["ap_id_canonical"] for r in self.ap_ids}
        self.assertEqual(canon_set, self.INVARIANTS["ap_id_canonicals"])
        for r in self.ap_ids:
            self.assertTrue(r["ap_id_canonical"].startswith("AP-"))

    def test_splice_canonical_set(self) -> None:
        self.assertEqual(len(self.splice_ids), self.INVARIANTS["splice_id_total"])
        canon_set = {r["splice_id_canonical"] for r in self.splice_ids}
        self.assertEqual(canon_set, self.INVARIANTS["splice_id_canonicals"])
        for r in self.splice_ids:
            self.assertTrue(r["splice_id_canonical"].startswith("SPLICE-"))

    def test_drawing_index_exact(self) -> None:
        self.assertEqual(len(self.drawing_index), self.INVARIANTS["drawing_index_count"])
        files = {r["file_name"] for r in self.drawing_index}
        self.assertEqual(files, self.INVARIANTS["dwg_files"])

    def test_fieldwire_does_not_fire_on_non_fieldwire_pdf(self) -> None:
        self.assertEqual(len(self.fieldwire_table), self.INVARIANTS["fieldwire_row_count"])

    def test_page_numbers_are_one_indexed_and_in_range(self) -> None:
        max_page = self.INVARIANTS["page_count"]
        for records in (self.matchlines, self.station_callouts,
                        self.ap_ids, self.splice_ids, self.drawing_index):
            for r in records:
                self.assertGreaterEqual(r["page"], 1)
                self.assertLessEqual(r["page"], max_page)


@unittest.skipUnless(_BRENHAM_AVAILABLE, _SKIP_REASON)
class TestBrenhamAutocadExtraction(_PdfExtractionMixin, unittest.TestCase):
    """43-page AutoCAD plan set (medium runtime)."""

    INVARIANTS = _BRENHAM_AUTOCAD

    def test_page_count_and_dispatch(self) -> None:
        self.assertEqual(self.metadata["page_count"], self.INVARIANTS["page_count"])
        self.assertEqual(self.metadata["dispatch_hint"], self.INVARIANTS["dispatch_hint"])
        producer = self.metadata["producer"] or ""
        self.assertIn(self.INVARIANTS["producer_contains"], producer)

    def test_title_block_dates(self) -> None:
        self.assertEqual(self.title_block["project"], self.INVARIANTS["title_block_project"])
        self.assertEqual(
            self.title_block["revision_date"],
            self.INVARIANTS["title_block_revision_date"],
        )
        self.assertEqual(
            self.title_block["original_date"],
            self.INVARIANTS["title_block_original_date"],
        )

    def test_matchline_count(self) -> None:
        self.assertEqual(len(self.matchlines), self.INVARIANTS["matchline_count"])

    def test_station_callout_distribution(self) -> None:
        self.assertEqual(len(self.station_callouts), self.INVARIANTS["station_callout_total"])
        kinds = {"range": 0, "equation": 0, "single": 0}
        for r in self.station_callouts:
            kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
        self.assertEqual(kinds, self.INVARIANTS["station_callout_kinds"])

    def test_ap_canonical_count_and_required_subset(self) -> None:
        canon_set = {r["ap_id_canonical"] for r in self.ap_ids}
        self.assertEqual(len(canon_set), self.INVARIANTS["ap_id_unique"])
        for required in self.INVARIANTS["ap_canonicals_must_include"]:
            self.assertIn(required, canon_set)

    def test_splice_canonical_count_and_required_subset(self) -> None:
        self.assertEqual(len(self.splice_ids), self.INVARIANTS["splice_id_total"])
        canon_set = {r["splice_id_canonical"] for r in self.splice_ids}
        self.assertEqual(len(canon_set), self.INVARIANTS["splice_id_unique"])
        for required in self.INVARIANTS["splice_canonicals_must_include"]:
            self.assertIn(required, canon_set)

    def test_drawing_index_count(self) -> None:
        self.assertEqual(len(self.drawing_index), self.INVARIANTS["drawing_index_count"])

    def test_fieldwire_does_not_fire(self) -> None:
        self.assertEqual(len(self.fieldwire_table), self.INVARIANTS["fieldwire_row_count"])


@unittest.skipUnless(_BRENHAM_AVAILABLE, _SKIP_REASON)
class TestBrenhamFieldwireExtraction(_PdfExtractionMixin, unittest.TestCase):
    """80-page Fieldwire tabular report (slowest)."""

    INVARIANTS = _BRENHAM_FIELDWIRE

    def test_page_count_and_dispatch(self) -> None:
        self.assertEqual(self.metadata["page_count"], self.INVARIANTS["page_count"])
        self.assertEqual(self.metadata["dispatch_hint"], self.INVARIANTS["dispatch_hint"])
        producer = self.metadata["producer"] or ""
        self.assertIn(self.INVARIANTS["producer_contains"], producer)

    def test_title_block_project(self) -> None:
        self.assertEqual(self.title_block["project"], self.INVARIANTS["title_block_project"])

    def test_no_matchlines_in_tabular_report(self) -> None:
        self.assertEqual(len(self.matchlines), self.INVARIANTS["matchline_count"])

    def test_no_splices_in_tabular_report(self) -> None:
        self.assertEqual(len(self.splice_ids), self.INVARIANTS["splice_id_total"])

    def test_no_drawing_index_in_tabular_report(self) -> None:
        self.assertEqual(len(self.drawing_index), self.INVARIANTS["drawing_index_count"])

    def test_minimal_station_callouts(self) -> None:
        self.assertEqual(len(self.station_callouts), self.INVARIANTS["station_callout_total"])

    def test_ap_canonical_count_and_required_subset(self) -> None:
        canon_set = {r["ap_id_canonical"] for r in self.ap_ids}
        self.assertEqual(len(canon_set), self.INVARIANTS["ap_id_unique"])
        for required in self.INVARIANTS["ap_canonicals_must_include"]:
            self.assertIn(required, canon_set)

    def test_fieldwire_table_row_count(self) -> None:
        self.assertEqual(len(self.fieldwire_table), self.INVARIANTS["fieldwire_row_count"])

    def test_fieldwire_table_first_row(self) -> None:
        self.assertGreater(len(self.fieldwire_table), 0)
        first = self.fieldwire_table[0]
        self.assertEqual(first["row_id"], self.INVARIANTS["fieldwire_first_row_id"])
        self.assertEqual(
            first["ap_id_canonical"],
            self.INVARIANTS["fieldwire_first_row_ap_canonical"],
        )
        self.assertEqual(first["status"], self.INVARIANTS["fieldwire_first_row_status"])

    def test_every_fieldwire_row_has_canonical_ap_and_parseable_date(self) -> None:
        date_re = re.compile(r"^\d{2}[-/]\d{2}[-/]\d{4}$")
        for row in self.fieldwire_table:
            self.assertTrue(row["ap_id_canonical"].startswith("AP-"))
            self.assertIsNotNone(row["status_date"])
            self.assertRegex(row["status_date"], date_re)


if __name__ == "__main__":
    unittest.main()
