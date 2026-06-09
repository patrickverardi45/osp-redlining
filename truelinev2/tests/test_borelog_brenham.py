import openpyxl

from truelinev2.ingest.borelog_brenham import read_brenham_borelog


def test_read_brenham(tmp_path):
    p = tmp_path / "bore_log99.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["station", "depth", "boc", "date", "crew", "print", "notes"])
    for sta, d in [("0+00", 4.3), ("1+50", 4.5), ("3+00", 4.4)]:
        ws.append([sta, d, 10, "2026-01-01", "tx", "8,9", ""])
    wb.save(str(p))

    bore = read_brenham_borelog(str(p))
    assert bore.bore_id == "log99"
    assert bore.station_start == "0+00" and bore.station_end == "3+00"
    assert bore.span_ft == 300.0
    assert bore.sheet_refs == [8, 9]
    assert bore.depth_min_ft == 4.3
