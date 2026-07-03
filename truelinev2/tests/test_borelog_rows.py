"""Contract tests for the read-only bore-log table extraction adapter (truelinev2/extract/borelog_rows).

The adapter maps a bore-log file into UNTRUSTED extracted_row dicts, two-tier: the v2 engine reader FIRST
(one canonical Bore per file; these tests monkeypatch it so the tier stays a pure unit test), then — only
when the engine reader does not recognize the file — the SHIPPED generic name-free span extractor (one row
per SOURCE-CONFIRMED span; exercised here on real tmp_path files through the real extractor). It must:
never fabricate confidence (engine rows None; generic rows carry the extractor's own source-derived band),
leave rows UNREVIEWED (not placement candidates), mirror the manual-entry normalized shape, avoid row-id
collisions, and raise ONE honest error naming BORE_LOG_FORMAT_UNRECOGNIZED when neither tier confirms a
span. Generic fixtures only — no customer/person/place names.
"""
from __future__ import annotations

import openpyxl
import pytest

from truelinev2.contracts import extracted_row as er
from truelinev2.extract import borelog_rows as br
from truelinev2.schema.models import Bore


def _bore(**kw) -> Bore:
    base = dict(bore_id="b1", station_start="04+94", station_end="11+69",
                station_start_ft=494.0, station_end_ft=1169.0, span_ft=675.0,
                sheet_refs=[7, 14], depth_min_ft=4.2, source_file="x.xlsx", print_raw="7,14")
    base.update(kw)
    return Bore(**base)


def test_extract_maps_bore_to_untrusted_table_import_row(monkeypatch):
    monkeypatch.setattr(br, "load_borelog", lambda p: _bore())
    rows = br.extract_rows_from_borelog("x.xlsx", "up-1", at="t", by="u")
    assert len(rows) == 1
    row = rows[0]
    assert row["extraction"]["extraction_method"] == er.TABLE_IMPORT
    assert row["extraction"]["confidence"] is None          # deterministic parse, never fabricated
    assert row["review"]["status"] == er.UNREVIEWED          # not a placement candidate until reviewed
    assert row["normalized"] == {"start_station": "04+94", "end_station": "11+69"}
    assert row["raw"]["footage_ft"] == 675.0
    assert row["raw"]["sheet_refs"] == [7, 14]
    assert row["source_upload_id"] == "up-1"


def test_extract_includes_optional_source_fields_when_present(monkeypatch):
    monkeypatch.setattr(br, "load_borelog", lambda p: _bore())
    monkeypatch.setattr(br, "_read_optional_fields",
                        lambda p: {"date": "2025-12-17", "crew": "tx1-1", "boc_min_ft": 7.0})
    raw = br.extract_rows_from_borelog("x.xlsx", "up-1", at="t", by="u")[0]["raw"]
    assert raw["date"] == "2025-12-17" and raw["crew"] == "tx1-1" and raw["boc_min_ft"] == 7.0


def test_extract_omits_optional_fields_when_absent(monkeypatch):
    # An absent / unreadable optional column is NEVER invented — the field is simply not present.
    monkeypatch.setattr(br, "load_borelog", lambda p: _bore())
    monkeypatch.setattr(br, "_read_optional_fields", lambda p: {})
    raw = br.extract_rows_from_borelog("x.xlsx", "up-1", at="t", by="u")[0]["raw"]
    assert "date" not in raw and "crew" not in raw and "boc_min_ft" not in raw


def test_extract_row_id_avoids_existing(monkeypatch):
    monkeypatch.setattr(br, "load_borelog", lambda p: _bore())
    rows = br.extract_rows_from_borelog("x.xlsx", "up-1", at="t", by="u",
                                        existing_row_ids=["extracted-1", "row-1"])
    assert rows[0]["row_id"] == "extracted-2"


def test_extract_raises_on_unreadable(monkeypatch):
    def boom(_path):
        raise ValueError("unrecognized bore-log format")
    monkeypatch.setattr(br, "load_borelog", boom)
    with pytest.raises(br.BoreLogExtractionError):
        br.extract_rows_from_borelog("x.xlsx", "up-1", at="t", by="u")


# --------------------------------------------------------------------------------------------------- #
# Generic fallback tier — real tmp_path files through the REAL span extractor (no monkeypatch): a file
# the engine reader does not recognize still yields reviewable rows when (and only when) a source
# EXPLICITLY ties two stations together as one bore.
# --------------------------------------------------------------------------------------------------- #
def test_generic_fallback_csv_span_table(tmp_path):
    p = tmp_path / "spans.csv"
    p.write_text("bore_id,start_station,end_station,footage\nB-1,11+75,13+25,150\nB-2,20+00,21+50,150\n",
                 encoding="utf-8")
    rows = br.extract_rows_from_borelog(str(p), "up-1", at="t", by="u")
    assert [r["row_id"] for r in rows] == ["extracted-1", "extracted-2"]
    for r in rows:
        assert r["extraction"]["extraction_method"] == er.TABLE_IMPORT
        assert r["review"]["status"] == er.UNREVIEWED        # not a placement candidate until reviewed
        assert r["source_upload_id"] == "up-1"
    first = rows[0]
    assert first["normalized"] == {"start_station": "11+75", "end_station": "13+25"}
    assert first["raw"]["footage_ft"] == 150.0 and first["raw"]["footage_source"] == "PRINTED"
    assert first["raw"]["span_grammar"] == "EXPLICIT_START_END_COLUMNS"
    assert first["raw"]["source_bore_ref"] == "B-1"
    assert first["raw"]["citation"]                          # source citation carried, never invented
    # confidence is the extractor's OWN source-derived band (explicit columns) — not fabricated
    assert first["extraction"]["confidence"] == er.HIGH


def test_generic_fallback_xlsx_span_table(tmp_path):
    """A generic XLSX span table (not the engine reader's named shape) extracts via the fallback tier."""
    p = tmp_path / "spans.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["bore_id", "start_station", "end_station", "footage"])
    ws.append(["B-1", "11+75", "13+25", 150])
    ws.append(["B-2", "20+00", "21+50", 150])
    wb.save(str(p))
    rows = br.extract_rows_from_borelog(str(p), "up-1", at="t", by="u")
    assert len(rows) == 2
    assert rows[0]["normalized"] == {"start_station": "11+75", "end_station": "13+25"}
    assert rows[1]["normalized"] == {"start_station": "20+00", "end_station": "21+50"}
    assert rows[0]["raw"]["source_kind"] == "XLSX_TABLE"


def test_generic_fallback_pdf_inline_callout(tmp_path):
    """A text-extractable PDF bore log with an inline station-pair callout extracts one row (MEDIUM —
    the extractor's own band for the inline grammar)."""
    fitz = pytest.importorskip("fitz")
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "bore run 11+75 TO 13+25")
    p = tmp_path / "bore-log.pdf"
    doc.save(str(p))
    doc.close()
    rows = br.extract_rows_from_borelog(str(p), "up-1", at="t", by="u")
    assert len(rows) == 1
    r = rows[0]
    assert r["normalized"] == {"start_station": "11+75", "end_station": "13+25"}
    assert r["raw"]["span_grammar"] == "INLINE_STATION_PAIR_CALLOUT"
    assert r["raw"]["source_kind"] == "PDF_BORE_LOG" and r["raw"]["source_page"] == 1
    assert r["extraction"]["confidence"] == er.MEDIUM
    assert r["review"]["status"] == er.UNREVIEWED


def test_generic_fallback_row_ids_avoid_existing(tmp_path):
    p = tmp_path / "spans.csv"
    p.write_text("start,end\n11+75,13+25\n20+00,21+50\n", encoding="utf-8")
    rows = br.extract_rows_from_borelog(str(p), "up-1", at="t", by="u",
                                        existing_row_ids=["extracted-1", "row-1"])
    assert [r["row_id"] for r in rows] == ["extracted-2", "extracted-3"]


def test_generic_fallback_unrecognized_raises_named_blocker(tmp_path):
    """Neither tier confirms a span -> ONE honest error naming BORE_LOG_FORMAT_UNRECOGNIZED + the
    extractor's specific refusal reason. No row is ever invented."""
    p = tmp_path / "rows.csv"
    p.write_text("a,b\n1,2\n", encoding="utf-8")
    with pytest.raises(br.BoreLogExtractionError) as exc:
        br.extract_rows_from_borelog(str(p), "up-1", at="t", by="u")
    msg = str(exc.value)
    assert br.BORE_LOG_FORMAT_UNRECOGNIZED in msg
    assert "NO_TABLE_SPAN_COLUMNS" in msg                    # the specific source-level refusal, actionable


def test_blocker_code_matches_engine_handoff_vocabulary():
    """The locally-defined code stays in sync with the canonical uploaded-corpus engine-handoff vocabulary
    (defined locally so the extract adapter never imports that module's engine/renderer chain)."""
    from truelinev2.contracts import uploaded_corpus_engine_handoff as uce
    assert br.BORE_LOG_FORMAT_UNRECOGNIZED == uce.BORE_LOG_FORMAT_UNRECOGNIZED
