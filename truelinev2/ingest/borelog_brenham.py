"""Brenham bore-log reader: a flat .xlsx table with headers
``station | depth | boc | date | crew | print | notes`` -> canonical Bore.
"""
from __future__ import annotations

import os
import re
from typing import List

import openpyxl

from truelinev2.schema.models import Bore
from truelinev2.stations import parse_station


def sheets_from_print(print_val) -> List[int]:
    out: List[int] = []
    for n in re.findall(r"\d+", str(print_val or "")):
        v = int(n)
        if v not in out:
            out.append(v)
    return out


def read_brenham_borelog(path: str) -> Bore:
    wb = openpyxl.load_workbook(path, data_only=True)
    try:
        ws = wb.worksheets[0]
        rows = list(ws.iter_rows(values_only=True))
    finally:
        wb.close()
    if not rows:
        raise ValueError(f"empty bore log: {path}")

    header = [str(h).strip().lower() if h is not None else "" for h in rows[0]]

    def col(*names):
        for n in names:
            if n in header:
                return header.index(n)
        return None

    ci_sta = col("station")
    ci_print = col("print")
    ci_depth = col("depth_ft", "depth")
    if ci_sta is None:
        ci_sta = 0

    stations = []
    print_val = None
    depths: List[float] = []
    for r in rows[1:]:
        if not r:
            continue
        raw = r[ci_sta] if ci_sta < len(r) else None
        ft = parse_station(raw)
        if ft is not None:
            stations.append((ft, str(raw).strip()))
        if print_val is None and ci_print is not None and ci_print < len(r):
            pv = r[ci_print]
            if pv not in (None, ""):
                print_val = pv
        if ci_depth is not None and ci_depth < len(r):
            v = r[ci_depth]
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                depths.append(float(v))

    if not stations:
        raise ValueError(f"no parseable stations in {path}")
    stations.sort(key=lambda t: t[0])
    base = os.path.basename(path)
    log_id = os.path.splitext(base)[0].replace("bore_log", "log")
    return Bore(
        bore_id=log_id,
        source_file=base,
        sheet_refs=sheets_from_print(print_val),
        station_start=stations[0][1],
        station_end=stations[-1][1],
        station_start_ft=stations[0][0],
        station_end_ft=stations[-1][0],
        span_ft=round(stations[-1][0] - stations[0][0], 2),
        depth_min_ft=(min(depths) if depths else None),
        print_raw=(str(print_val) if print_val is not None else None),
    )
