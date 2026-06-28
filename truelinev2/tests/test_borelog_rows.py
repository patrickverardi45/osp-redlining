"""Contract tests for the read-only bore-log table extraction adapter (truelinev2/extract/borelog_rows).

The adapter maps a parsed canonical Bore (from the v2 reader) into UNTRUSTED extracted_row dicts. It must:
never fabricate confidence, leave rows UNREVIEWED (not placement candidates), mirror the manual-entry
normalized shape, avoid row-id collisions, and raise a single honest error on an unreadable file. The
underlying reader (load_borelog) is monkeypatched so these stay pure unit tests with no fixture file.
"""
from __future__ import annotations

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
