"""Slice 2 (Print-Reference audit): the GENERIC / readiness span extractor must PRESERVE bore-log
Print # / sheet references instead of dropping them.

The strict engine reader already carries them (``ingest.borelog_brenham.sheets_from_print`` ->
``Bore.sheet_refs`` + ``Bore.print_raw``, surfaced in the strict tier's extracted_row ``raw``). The generic
tier dropped them at BOTH levels: ``harness.span_extractor._parse_table`` never detected a print/sheet
column (so ``SpanRow`` could not carry one), and ``extract.borelog_rows._generic_span_rows`` therefore had
nothing to copy through. That severs the readiness lane's future reasoning chain
(print ref -> engineering sheet identity -> resolved PDF page -> station span -> REVIEW candidate).

The fix is ADDITIVE ONLY: a print/sheet column, WHEN PRESENT, is carried as ``print_raw`` (the verbatim
source text) separately from ``sheet_refs`` (ints parsed by the SAME ordered-dedup digit rule the strict
reader uses). No column -> both stay absent/empty exactly as before — sheet refs are never guessed, never
derived from stations/footage/pages. Rendering, matchline, AUTO, thresholds, recognized replay, manual
anchor, and readiness CLASSIFICATION are untouched (the readiness spine may only REASON from these fields
in a later slice).

Generic name-free fixtures in tmp_path only; no customer/person/place names.
"""
from __future__ import annotations

import openpyxl

from truelinev2.contracts.extracted_row import CONFIRMED
from truelinev2.contracts.customer_project import create_customer_project
from truelinev2.contracts.processing_job import create_job
from truelinev2.contracts.reviewed_bore_log import (
    add_extracted_rows,
    create_reviewed_bore_log,
    load_reviewed_bore_log,
    review_row_in_log,
)
from truelinev2.contracts.upload_pipeline import accept_upload
from truelinev2.extract import borelog_rows as br
from truelinev2.harness import span_extractor as se

AT = "2026-07-07T00:00:00Z"
BY = "op-1"
CP = "cp-0001"
JOB = "job-0001"
RBL = "rbl-1"


def _xlsx(path, header, rows) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(list(header))
    for r in rows:
        ws.append(list(r))
    wb.save(str(path))


# --------------------------------------------------------------------------------------------------- #
# The parse rule itself: verbatim raw text, ordered-dedup digit ints — the strict reader's exact rule.
# --------------------------------------------------------------------------------------------------- #
def test_sheet_refs_parse_rule_matches_strict_reader():
    from truelinev2.ingest.borelog_brenham import sheets_from_print
    for val in ("10, 11", "SHT 12", "7", "7,14", "10 & 11 & 10", "", None):
        assert list(se._sheet_refs_from_print(val)) == sheets_from_print(val)
    assert se._sheet_refs_from_print("10, 11") == (10, 11)
    assert se._sheet_refs_from_print(None) == ()


# --------------------------------------------------------------------------------------------------- #
# (1) "Print #" column (CSV, explicit start/end columns): carried on the SpanRow AND through the
# product extraction path into the extracted_row raw — print text verbatim, refs parsed.
# --------------------------------------------------------------------------------------------------- #
def test_csv_print_hash_column_is_preserved(tmp_path):
    p = tmp_path / "spans.csv"
    p.write_text("bore_id,start_station,end_station,footage,Print #\n"
                 "B-1,11+75,13+25,150,\"10, 11\"\n"
                 "B-2,20+00,21+50,150,12\n", encoding="utf-8")
    ext = se.extract_spans_from_csv(str(p))
    assert ext.source_confirmed_span_count == 2
    assert ext.spans[0].print_raw == "10, 11"
    assert ext.spans[0].sheet_refs == (10, 11)
    assert ext.spans[1].print_raw == "12" and ext.spans[1].sheet_refs == (12,)

    rows = br.extract_rows_from_borelog(str(p), "up-1", at=AT, by=BY)   # CSV -> the generic tier
    assert rows[0]["raw"]["print_raw"] == "10, 11"
    assert rows[0]["raw"]["sheet_refs"] == [10, 11]
    assert rows[1]["raw"]["sheet_refs"] == [12]


# --------------------------------------------------------------------------------------------------- #
# (2) "Sheet" / "Plan Sheet" header variants (XLSX + CSV), including the labeled-start/end-rows shape.
# --------------------------------------------------------------------------------------------------- #
def test_xlsx_sheet_and_csv_plan_sheet_variants(tmp_path):
    x = tmp_path / "spans.xlsx"
    _xlsx(x, ["start", "end", "Sheet"], [["11+75", "13+25", "SHT 12"]])
    r = se.extract_spans_from_xlsx(str(x)).spans[0]
    assert r.print_raw == "SHT 12" and r.sheet_refs == (12,)

    c = tmp_path / "spans2.csv"
    c.write_text("start,end,Plan Sheet\n11+75,13+25,7\n", encoding="utf-8")
    r2 = se.extract_spans_from_csv(str(c)).spans[0]
    assert r2.print_raw == "7" and r2.sheet_refs == (7,)


def test_labeled_start_end_rows_carry_sheet(tmp_path):
    # Shape B (single station column + labeled start/end rows): the print/sheet cell travels with the
    # single confirmed span (start row's value; end row's only as fallback).
    p = tmp_path / "log.xlsx"
    _xlsx(p, ["station", "sheet", "point"],
          [["11+75", "7", "bore start"], ["13+25", "7", "bore end"]])
    ext = se.extract_spans_from_xlsx(str(p))
    assert ext.source_confirmed_span_count == 1
    assert ext.spans[0].print_raw == "7" and ext.spans[0].sheet_refs == (7,)


# --------------------------------------------------------------------------------------------------- #
# (3) No print/sheet column -> NOTHING is fabricated: span fields empty, raw keys ABSENT.
# --------------------------------------------------------------------------------------------------- #
def test_no_print_sheet_column_fabricates_nothing(tmp_path):
    p = tmp_path / "spans.csv"
    p.write_text("bore_id,start_station,end_station,footage\nB-1,11+75,13+25,150\n", encoding="utf-8")
    r = se.extract_spans_from_csv(str(p)).spans[0]
    assert r.print_raw is None
    assert r.sheet_refs == ()
    raw = br.extract_rows_from_borelog(str(p), "up-1", at=AT, by=BY)[0]["raw"]
    assert "print_raw" not in raw and "sheet_refs" not in raw


# --------------------------------------------------------------------------------------------------- #
# (4) Existing generic extraction behavior unchanged: on a no-print source the extracted_row raw keeps
# EXACTLY its pre-slice key set and values (nothing added, renamed, or reordered away).
# --------------------------------------------------------------------------------------------------- #
def test_existing_generic_row_shape_unchanged(tmp_path):
    p = tmp_path / "spans.csv"
    p.write_text("bore_id,start_station,end_station,footage\nB-1,11+75,13+25,150\n", encoding="utf-8")
    row = br.extract_rows_from_borelog(str(p), "up-1", at=AT, by=BY)[0]
    assert set(row["raw"].keys()) == {
        "start_station", "end_station", "footage_ft", "footage_source", "source_file",
        "source_page", "source_kind", "span_grammar", "citation", "source_bore_ref",
    }
    assert row["raw"]["footage_ft"] == 150.0 and row["raw"]["footage_source"] == "PRINTED"
    assert row["raw"]["span_grammar"] == "EXPLICIT_START_END_COLUMNS"
    assert row["normalized"] == {"start_station": "11+75", "end_station": "13+25"}


# --------------------------------------------------------------------------------------------------- #
# (5) Reviewed rows PRESERVE the fields: extract -> append to a reviewed bore log -> human review
# (CONFIRMED) -> reload; the raw print/sheet provenance survives the review round-trip untouched.
# --------------------------------------------------------------------------------------------------- #
def test_reviewed_rows_preserve_print_fields(tmp_path):
    src = tmp_path / "spans.csv"
    src.write_text("bore_id,start_station,end_station,footage,print\nB-1,11+75,13+25,150,\"10, 11\"\n",
                   encoding="utf-8")
    store = tmp_path / "store"
    store.mkdir()
    create_customer_project(store, CP, "Label", AT)
    create_job(store, CP, JOB, AT, BY)
    up = accept_upload(store, CP, JOB, kind="BORE_LOG", filename="log.csv",
                       content=src.read_bytes(), stored_at=AT)
    create_reviewed_bore_log(store, CP, JOB, up["upload_id"], RBL, at=AT, by=BY)

    rows = br.extract_rows_from_borelog(str(src), up["upload_id"], at=AT, by=BY)
    add_extracted_rows(store, CP, JOB, RBL, rows, at=AT, by=BY)
    review_row_in_log(store, CP, JOB, RBL, rows[0]["row_id"], CONFIRMED, at=AT, by=BY)

    rbl = load_reviewed_bore_log(store, CP, JOB, RBL)
    stored = next(r for r in rbl["rows"] if r["row_id"] == rows[0]["row_id"])
    assert stored["review"]["status"] == CONFIRMED
    assert stored["raw"]["print_raw"] == "10, 11"
    assert stored["raw"]["sheet_refs"] == [10, 11]
