"""Bore-log format detection -> canonical Bore.

M1 supports the Brenham flat-table format. The ODOT VeroFy "Construction Log"
(2-sheet key/value form) is detected and explicitly deferred to M2 so the seam
is honest rather than silently mis-parsing.
"""
from __future__ import annotations

import openpyxl

from truelinev2.ingest.borelog_brenham import read_brenham_borelog
from truelinev2.schema.models import Bore


def detect_format(path: str) -> str:
    try:
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        names = wb.sheetnames
        wb.close()
    except Exception:
        return "unknown"
    if "Construction Log" in names:
        return "odot_construction_log"
    return "brenham_flat"


def load_borelog(path: str) -> Bore:
    fmt = detect_format(path)
    if fmt == "brenham_flat":
        return read_brenham_borelog(path)
    if fmt == "odot_construction_log":
        raise NotImplementedError(
            "ODOT VeroFy Construction Log ingestion is deferred to M2 (ODOT dialect).")
    raise ValueError(f"unrecognized bore-log format: {path}")
