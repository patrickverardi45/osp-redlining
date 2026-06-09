"""Bore-log format detection -> canonical Bore. Brenham flat-table + ODOT VeroFy."""
from __future__ import annotations

import openpyxl

from truelinev2.ingest.borelog_brenham import read_brenham_borelog
from truelinev2.ingest.borelog_odot import read_odot_borelog
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
        return read_odot_borelog(path)
    raise ValueError(f"unrecognized bore-log format: {path}")
