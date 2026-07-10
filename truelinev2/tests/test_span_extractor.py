"""Proof for the read-only SOURCE-SPAN EXTRACTOR MVP (truelinev2/harness/span_source.py + span_extractor.py).

Generic, name-free extraction of source-confirmed bore/span rows from bore-log / bore-schedule / span-table
source documents (text, markdown, CSV, XLSX, text-extractable PDF). It proves:

  * extracts a source-confirmed span when a source EXPLICITLY ties two stations (inline callout, explicit
    start/end columns, labeled start/end rows, CSV/XLSX/PDF);
  * refuses plan-only / station-ruler-only text;
  * refuses two unrelated standalone station labels;
  * distinguishes "a source file exists" from "a source-confirmed span exists";
  * feeds ReviewReadinessEvidence so its verdicts are compatible with the review-readiness classifier;
  * imports nothing from renderer / placement / backend / web / product runtime.

All fixtures are generic and built in tmp_path (never committed). Existing known bore-log fixtures are reused via
the generic ``harness.synth.borelog_xlsx`` builder. No real customer/person/place names appear here.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import openpyxl

from truelinev2.harness.review_readiness import (
    MISSING_BORE_SPAN_SOURCE,
    NO_SOURCE_CONFIRMED_SPAN,
    ReviewReadinessEvidence,
    SPAN_SOURCE_FOUND,
    classify_review_readiness,
)
from truelinev2.harness.span_extractor import (
    SPAN_ROW_CONFIRMED,
    NO_SOURCE_SPAN_FILE,
    STATION_RULER_ONLY,
    UNRELATED_STANDALONE_STATIONS,
    extract_spans_from_csv,
    extract_spans_from_documents,
    extract_spans_from_folder,
    extract_spans_from_pdf,
    extract_spans_from_text,
    extract_spans_from_xlsx,
    format_extraction,
    span_source_evidence_from_extraction,
)
from truelinev2.harness.span_source import documents_from_file
from truelinev2.harness.synth import borelog_xlsx

_HARNESS = Path(__file__).resolve().parents[1] / "harness"
_SPAN_MODULES = [_HARNESS / "span_source.py", _HARNESS / "span_extractor.py"]


# ----------------------------------------------------------------------------------------------------------- #
# (1) positive extraction — a source explicitly ties two stations together.
# ----------------------------------------------------------------------------------------------------------- #
def test_inline_station_pair_callout_text():
    ext = extract_spans_from_text("bore run 11+75 TO 13+25 along the corridor")
    assert ext.source_confirmed_span_count == 1
    r = ext.spans[0]
    assert r.start_station == "11+75" and r.end_station == "13+25"
    assert r.status == SPAN_ROW_CONFIRMED and r.confidence == "MEDIUM"
    assert r.detail["span_grammar"] == "INLINE_STATION_PAIR_CALLOUT"
    assert r.footage == 150.0 and r.detail["footage_source"] == "COMPUTED_FROM_STATIONS"


def test_dash_range_callout_text():
    ext = extract_spans_from_text("segment 20+00 - 21+50")
    assert ext.source_confirmed_span_count == 1
    assert ext.spans[0].start_station == "20+00" and ext.spans[0].end_station == "21+50"


def test_csv_explicit_start_end_columns(tmp_path):
    p = tmp_path / "schedule.csv"
    p.write_text("bore_id,start_station,end_station,footage\nB-1,11+75,13+25,150\nB-2,20+00,21+50,150\n",
                 encoding="utf-8")
    ext = extract_spans_from_csv(str(p))
    assert ext.source_confirmed_span_count == 2
    assert ext.spans[0].start_station == "11+75" and ext.spans[0].end_station == "13+25"
    assert ext.spans[0].footage == 150.0 and ext.spans[0].detail["footage_source"] == "PRINTED"
    assert ext.spans[0].detail["span_grammar"] == "EXPLICIT_START_END_COLUMNS"
    assert ext.spans[1].start_station == "20+00"


def test_markdown_pipe_table():
    md = "| bore_id | start | end |\n| --- | --- | --- |\n| B-1 | 11+75 | 13+25 |\n"
    ext = extract_spans_from_text(md)
    assert ext.source_confirmed_span_count == 1
    assert ext.spans[0].start_station == "11+75" and ext.spans[0].end_station == "13+25"


def test_xlsx_labeled_start_end_rows(tmp_path):
    """The generic Brenham-shape bore-log (single station column + a notes column labeling 'bore start' /
    'bore end') is a source-confirmed span."""
    p = tmp_path / "bore-log.xlsx"
    p.write_bytes(borelog_xlsx("11+75", "13+25"))
    ext = extract_spans_from_xlsx(str(p))
    assert ext.source_confirmed_span_count == 1
    r = ext.spans[0]
    assert r.start_station == "11+75" and r.end_station == "13+25"
    assert r.detail["span_grammar"] == "LABELED_START_END_ROWS" and r.source_kind == "XLSX_TABLE"
    assert r.footage == 150.0


def test_optional_structures_are_captured(tmp_path):
    p = tmp_path / "s.csv"
    p.write_text("start,end,start_structure,end_structure\n11+75,13+25,HH-1,VLT-2\n", encoding="utf-8")
    r = extract_spans_from_csv(str(p)).spans[0]
    assert r.start_structure == "HH-1" and r.end_structure == "VLT-2"


# --- depth/BOC (bottom-of-conduit) source-backed carry-through (additive; never invented) -------------------- #

def test_shape_a_explicit_columns_carries_depth_and_boc(tmp_path):
    """Shape A (explicit start/end columns): each row is its OWN bore -> depth/BOC are THAT row's reading,
    never blended across rows."""
    p = tmp_path / "schedule.csv"
    p.write_text("start,end,depth,boc\n11+75,13+25,4.5,5.0\n20+00,21+50,6.0,7.5\n", encoding="utf-8")
    ext = extract_spans_from_csv(str(p))
    assert ext.spans[0].depth == 4.5 and ext.spans[0].boc == 5.0
    assert ext.spans[1].depth == 6.0 and ext.spans[1].boc == 7.5


def test_shape_a_missing_depth_boc_columns_stays_none(tmp_path):
    p = tmp_path / "schedule.csv"
    p.write_text("start,end\n11+75,13+25\n", encoding="utf-8")
    r = extract_spans_from_csv(str(p)).spans[0]
    assert r.depth is None and r.boc is None


def test_shape_b_labeled_rows_carries_min_depth_and_boc(tmp_path):
    """Shape B (single station col + labeled start/end rows): depth/BOC is the MINIMUM reading recorded
    anywhere in the bore-log table (mirrors the strict reader's depth_min_ft / boc_min_ft semantics), not
    just the two labeled rows."""
    p = tmp_path / "bore-log.xlsx"
    p.write_bytes(borelog_xlsx("11+75", "13+25", depth=5.0, boc=6.0))
    r = extract_spans_from_xlsx(str(p)).spans[0]
    assert r.depth == 5.0 and r.boc == 6.0


def test_shape_b_no_depth_boc_columns_stays_none(tmp_path):
    p = tmp_path / "bore-log.xlsx"
    p.write_bytes(borelog_xlsx("11+75", "13+25"))                 # no boc column, depth column present
    r = extract_spans_from_xlsx(str(p)).spans[0]
    assert r.boc is None                                          # honest absence, no fabricated 0


# --- bore id / date / crew / notes source-backed carry-through (additive; never invented) ---------------- #

def _xlsx(path, header, rows) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(list(header))
    for r in rows:
        ws.append(list(r))
    wb.save(str(path))


def test_shape_a_carries_bore_id_date_crew_notes(tmp_path):
    """Shape A (explicit start/end columns): each row is its OWN bore -> bore id/date/crew/notes are THAT
    row's own values, never blended across rows (mirrors the depth/BOC rule above)."""
    p = tmp_path / "schedule.csv"
    p.write_text(
        "start,end,bore_id,date,crew,notes\n"
        "11+75,13+25,B-1,2026-01-05,Crew A,soft soil\n"
        "20+00,21+50,B-2,2026-01-06,Crew B,rock encountered\n",
        encoding="utf-8")
    ext = extract_spans_from_csv(str(p))
    assert ext.spans[0].bore_id == "B-1" and ext.spans[0].date == "2026-01-05"
    assert ext.spans[0].crew == "Crew A" and ext.spans[0].notes == "soft soil"
    assert ext.spans[1].bore_id == "B-2" and ext.spans[1].date == "2026-01-06"
    assert ext.spans[1].crew == "Crew B" and ext.spans[1].notes == "rock encountered"


def test_shape_a_missing_bore_id_date_crew_notes_columns_stays_none(tmp_path):
    p = tmp_path / "schedule.csv"
    p.write_text("start,end\n11+75,13+25\n", encoding="utf-8")
    r = extract_spans_from_csv(str(p)).spans[0]
    assert r.bore_id is None and r.date is None and r.crew is None and r.notes is None


def test_shape_a_empty_cell_is_absent_not_fabricated(tmp_path):
    p = tmp_path / "schedule.csv"
    p.write_text("start,end,bore_id,crew\n11+75,13+25,,\n", encoding="utf-8")
    r = extract_spans_from_csv(str(p)).spans[0]
    assert r.bore_id is None and r.crew is None            # empty cell -> absent, never ""


def test_bore_id_column_synonym_variants(tmp_path):
    for i, header_name in enumerate(["bore_id", "bore id", "bore", "id", "bore #", "bore no"]):
        p = tmp_path / ("bore-id-%d.csv" % i)
        p.write_text("start,end,%s\n11+75,13+25,B-%d\n" % (header_name, i), encoding="utf-8")
        r = extract_spans_from_csv(str(p)).spans[0]
        assert r.bore_id == "B-%d" % i, header_name


def test_date_column_synonym_variants(tmp_path):
    for i, header_name in enumerate(["date", "bore date", "install date", "drill date"]):
        p = tmp_path / ("date-%d.csv" % i)
        p.write_text("start,end,%s\n11+75,13+25,2026-01-0%d\n" % (header_name, i + 1), encoding="utf-8")
        r = extract_spans_from_csv(str(p)).spans[0]
        assert r.date == "2026-01-0%d" % (i + 1), header_name


def test_crew_column_synonym_variants(tmp_path):
    for i, header_name in enumerate(["crew", "crew name"]):
        p = tmp_path / ("crew-%d.csv" % i)
        p.write_text("start,end,%s\n11+75,13+25,Crew-%d\n" % (header_name, i), encoding="utf-8")
        r = extract_spans_from_csv(str(p)).spans[0]
        assert r.crew == "Crew-%d" % i, header_name


def test_notes_column_synonym_variants(tmp_path):
    for i, header_name in enumerate(["notes", "note", "comments", "comment", "remarks"]):
        p = tmp_path / ("notes-%d.csv" % i)
        p.write_text("start,end,%s\n11+75,13+25,note-%d\n" % (header_name, i), encoding="utf-8")
        r = extract_spans_from_csv(str(p)).spans[0]
        assert r.notes == "note-%d" % i, header_name


def test_shape_b_labeled_rows_carries_bore_id_date_crew_notes_from_start_row(tmp_path):
    """Shape B (single station col + labeled start/end rows, ROLE column named 'point' so it does not
    collide with a separate free-text 'notes' column): bore id/date/crew/notes are free-text metadata, so
    they mirror the pre-existing print_raw precedent for this shape -- the start row's own cell, else the
    end row's -- never a table-wide smear across unrelated rows."""
    p = tmp_path / "log.xlsx"
    _xlsx(p, ["station", "point", "bore_id", "date", "crew", "notes"],
          [["11+75", "bore start", "B-1", "2026-01-05", "Crew A", "soft soil"],
           ["13+25", "bore end", "B-1", "2026-01-05", "Crew A", "soft soil"]])
    r = extract_spans_from_xlsx(str(p)).spans[0]
    assert r.bore_id == "B-1" and r.date == "2026-01-05" and r.crew == "Crew A" and r.notes == "soft soil"


def test_shape_b_falls_back_to_end_row_when_start_row_cell_is_empty(tmp_path):
    p = tmp_path / "log.xlsx"
    _xlsx(p, ["station", "point", "bore_id"],
          [["11+75", "bore start", ""], ["13+25", "bore end", "B-9"]])
    r = extract_spans_from_xlsx(str(p)).spans[0]
    assert r.bore_id == "B-9"                              # start row empty -> falls back to end row


def test_shape_b_no_bore_id_date_crew_notes_columns_stays_none(tmp_path):
    p = tmp_path / "log.xlsx"
    _xlsx(p, ["station", "point"], [["11+75", "bore start"], ["13+25", "bore end"]])
    r = extract_spans_from_xlsx(str(p)).spans[0]
    assert r.bore_id is None and r.date is None and r.crew is None and r.notes is None


def test_shape_b_role_column_named_notes_never_smears_role_word_as_notes(tmp_path):
    """When the shape-B ROLE column itself is named 'notes' (the existing name-free Brenham-shape fixture,
    ``harness.synth.borelog_xlsx``, uses exactly this header), its cell text is the ROLE WORD
    ('bore start'/'bore end'), not free-text notes -- there is no genuine per-row notes association in that
    case, so notes stays honestly absent rather than reporting the role label as if it were a note."""
    p = tmp_path / "bore-log.xlsx"
    p.write_bytes(borelog_xlsx("11+75", "13+25"))
    r = extract_spans_from_xlsx(str(p)).spans[0]
    assert r.notes is None


def test_footage_printed_overrides_computed(tmp_path):
    p = tmp_path / "s.csv"
    p.write_text("start,end,length\n11+75,13+25,148\n", encoding="utf-8")
    r = extract_spans_from_csv(str(p)).spans[0]
    assert r.footage == 148.0 and r.detail["footage_source"] == "PRINTED"
    assert r.detail["computed_footage"] == 150.0


def test_extracts_from_text_pdf(tmp_path):
    """Text-extractable PDF bore log -> one page-scoped source-confirmed span."""
    import fitz
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "bore run 11+75 TO 13+25")
    p = tmp_path / "bore-log.pdf"
    doc.save(str(p))
    doc.close()
    ext = extract_spans_from_pdf(str(p))
    assert ext.source_confirmed_span_count == 1
    r = ext.spans[0]
    assert r.start_station == "11+75" and r.source_kind == "PDF_BORE_LOG" and r.source_page == 1


def test_folder_manifest_discovers_borelog(tmp_path):
    d = tmp_path / "pkg"
    (d / "uploads").mkdir(parents=True)
    (d / "uploads" / "bore-log.xlsx").write_bytes(borelog_xlsx("11+75", "13+25"))
    (d / "package.json").write_text(json.dumps({
        "package_id": "pkg", "provenance_class": "FRESH_NONRECOGNIZED",
        "uploads": [{"kind": "PLAN_PDF", "filename": "plan.pdf"},
                    {"kind": "BORE_LOG", "filename": "bore-log.xlsx"}], "bores": []}), encoding="utf-8")
    ext = extract_spans_from_folder(str(d))
    assert ext.source_confirmed_span_count == 1              # the BORE_LOG, not the (absent) plan
    assert any(f.endswith("bore-log.xlsx") for f in ext.source_files_seen)


# ----------------------------------------------------------------------------------------------------------- #
# (2)/(3) honest refusal.
# ----------------------------------------------------------------------------------------------------------- #
def test_refuses_station_ruler_only_text():
    ext = extract_spans_from_text("10+00\n11+00\n12+00\n13+00\n")
    assert not ext.has_source_confirmed_span
    assert ext.refusals[0].reason == STATION_RULER_ONLY


def test_refuses_two_unrelated_standalone_stations():
    ext = extract_spans_from_text("handhole at 5+00\nvault at 40+00\n")
    assert not ext.has_source_confirmed_span
    assert ext.refusals[0].reason == UNRELATED_STANDALONE_STATIONS


def test_refuses_table_with_no_span_columns(tmp_path):
    p = tmp_path / "t.csv"
    p.write_text("depth,notes\n5.0,soil\n6.0,rock\n", encoding="utf-8")
    ext = extract_spans_from_csv(str(p))
    assert not ext.has_source_confirmed_span
    assert ext.refusals[0].reason == "NO_TABLE_SPAN_COLUMNS"


def test_no_source_file_at_all_is_missing(tmp_path):
    ext = extract_spans_from_folder(str(tmp_path))           # empty folder
    assert not ext.source_files_seen
    assert ext.refusals[0].reason == NO_SOURCE_SPAN_FILE


# ----------------------------------------------------------------------------------------------------------- #
# (4) "source file exists" is distinct from "source-confirmed span exists".
# ----------------------------------------------------------------------------------------------------------- #
def test_distinguishes_file_exists_from_confirmed_span(tmp_path):
    (tmp_path / "ruler.txt").write_text("10+00\n11+00\n12+00\n", encoding="utf-8")
    ext = extract_spans_from_folder(str(tmp_path))
    assert ext.source_files_seen                            # a source file WAS inspected
    assert ext.source_confirmed_span_count == 0            # but no source-confirmed span
    assert not ext.has_source_confirmed_span


# ----------------------------------------------------------------------------------------------------------- #
# (5) compatibility with the review-readiness classifier via the bridge.
# ----------------------------------------------------------------------------------------------------------- #
def _readiness(ext):
    return classify_review_readiness(ReviewReadinessEvidence(
        package_id="pkg", plan_readable=True, recognized=False,
        span=span_source_evidence_from_extraction(ext)))


def test_bridge_confirmed_span_reaches_span_source_found():
    assert _readiness(extract_spans_from_text("bore run 11+75 TO 13+25")).status == SPAN_SOURCE_FOUND


def test_bridge_seen_but_unconfirmed_reaches_no_source_confirmed(tmp_path):
    (tmp_path / "ruler.txt").write_text("10+00\n11+00\n12+00\n", encoding="utf-8")
    assert _readiness(extract_spans_from_folder(str(tmp_path))).status == NO_SOURCE_CONFIRMED_SPAN


def test_bridge_no_file_reaches_missing_bore_span_source(tmp_path):
    assert _readiness(extract_spans_from_folder(str(tmp_path))).status == MISSING_BORE_SPAN_SOURCE


# ----------------------------------------------------------------------------------------------------------- #
# (6) no forbidden imports + (7) read-only + serialization.
# ----------------------------------------------------------------------------------------------------------- #
_FORBIDDEN_IMPORT_SEGMENTS = {
    "render", "renderer", "placement", "cap_review", "_cap_review",
    "api", "store", "web", "contracts", "match",
}


def _imported_modules(src: str):
    mods = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            for a in node.names:
                mods.add(a.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module)
    return mods


def test_span_modules_import_no_forbidden_modules():
    for mod_path in _SPAN_MODULES:
        for m in _imported_modules(mod_path.read_text(encoding="utf-8")):
            leaked = set(m.split(".")) & _FORBIDDEN_IMPORT_SEGMENTS
            assert not leaked, "%s imports forbidden module %r (%s)" % (mod_path.name, m, leaked)


def test_extractor_is_read_only(tmp_path):
    p = tmp_path / "s.csv"
    p.write_text("start,end\n11+75,13+25\n", encoding="utf-8")
    before = sorted(x.name for x in tmp_path.iterdir())
    extract_spans_from_csv(str(p))
    extract_spans_from_documents(documents_from_file(str(p)))
    assert sorted(x.name for x in tmp_path.iterdir()) == before


def test_extraction_is_json_serializable():
    ext = extract_spans_from_text("bore run 11+75 TO 13+25")
    text = format_extraction(ext)
    assert '"SPAN_ROW_CONFIRMED"' in text and '"source_confirmed_span_count"' in text


def test_no_invented_span_from_bare_stations():
    """Two stations with a connective that is NOT a span operator must not become a span."""
    ext = extract_spans_from_text("pole 5+00 and pole 9+00")
    assert not ext.has_source_confirmed_span


def test_four_digit_station_in_table_parses_via_canonical_parser(tmp_path):
    """Explicit-column tables use the canonical station parser, so 4+ digit stations parse correctly (they are
    not truncated to a trailing substring)."""
    p = tmp_path / "s.csv"
    p.write_text("start,end\n1000+00,1005+00\n", encoding="utf-8")
    r = extract_spans_from_csv(str(p)).spans[0]
    assert r.start_station == "1000+00" and r.end_station == "1005+00"
    assert r.footage == 500.0 and r.detail["start_ft"] == 100000.0


def test_four_digit_inline_callout_refuses_cleanly_without_misreading():
    """The inline callout grammar (reused, name-free) caps the station prefix, so a 4-digit inline pair is
    conservatively REFUSED — and the station-token counter reads the two full stations (never a truncated
    substring), so the refusal is UNRELATED_STANDALONE_STATIONS, not a collapsed/mis-read count."""
    ext = extract_spans_from_text("run 1000+00 TO 1005+00")
    assert not ext.has_source_confirmed_span
    assert ext.refusals[0].reason == UNRELATED_STANDALONE_STATIONS
