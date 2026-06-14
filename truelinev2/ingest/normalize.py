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


def load_borelog(path: str, *, normalize_station_label: bool = True) -> Bore:
    """Load a bore log. ``normalize_station_label`` (DEFAULT ON since
    PARENT-CHILD-RECON-2A) is forwarded to the Brenham reader; see
    ``read_brenham_borelog`` -- it affects only the ``STA``-prefixed log37/log38.
    Pass ``False`` for the pre-activation byte-identical load."""
    fmt = detect_format(path)
    if fmt == "brenham_flat":
        return read_brenham_borelog(path, normalize_station_label=normalize_station_label)
    if fmt == "odot_construction_log":
        return read_odot_borelog(path)
    raise ValueError(f"unrecognized bore-log format: {path}")
