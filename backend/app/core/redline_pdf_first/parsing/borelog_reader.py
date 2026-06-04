"""Bore-log reader — TWO ingestion paths, ONE internal model.

  * ``read_borelog(path)``           — .xlsx via ``openpyxl`` (file-fed, original).
  * ``from_rows(rows, source_file)`` — TrueLine-style ``committed_rows`` (row-fed).

Both normalize to the SAME bore model through ``_build_bore_model``, so file-fed
and row-fed selection are equivalent by construction (no duplicate parsing brain).
``openpyxl`` only; no ``fitz``; no Brenham constants; NO invented values — a log
with no parseable station raises (honest fail-safe), exactly like the file path.

Extracts: log id / source file, station start/end (+ feet + span), the ``print``
column (-> candidate sheet numbers), and depth if present (not required by the
funnel). ``from_rows`` additionally preserves richer committed_rows fields
(notes / boc_ft / date / crew) under ``extras`` — the selector does not key on
them today, but they are carried, never dropped, and never fabricated.
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Mapping, Optional, Sequence

import openpyxl

from . import station as st


def _sheets_from_print(print_val) -> List[int]:
    if print_val is None:
        return []
    out: List[int] = []
    for n in re.findall(r"\d+", str(print_val)):
        v = int(n)
        if v not in out:
            out.append(v)
    return out


def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


_STA_PREFIX_RE = re.compile(r"(?i)^\s*sta\.?\s+")


def _norm_station(raw):
    """Strip an optional authored ``STA ``/``STA.`` label prefix that some bore logs
    put on the station cell (``'STA 3+50'`` vs the bare ``'3+50'`` used elsewhere)
    before parsing. Identity-preserving: bare stations are returned unchanged; only a
    leading STA label is removed, so the same value parses on BOTH ingestion paths.
    Does NOT touch PDF station-tick parsing (that uses parsing/station_labels)."""
    if raw is None:
        return raw
    return _STA_PREFIX_RE.sub("", str(raw).strip())


def _build_bore_model(stations, print_val, depths, source_path_or_name,
                      extras: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """The single internal bore model both ingestion paths produce.

    ``stations`` is a list of ``(station_ft, station_text)``; ``depths`` a list of
    floats; ``print_val`` the raw print cell (or None). Raises ``ValueError`` when
    no station parsed (honest fail-safe — never invents a span).
    """
    if not stations:
        raise ValueError(f"no parseable stations in {source_path_or_name!r}")
    stations = sorted(stations, key=lambda t: t[0])
    start_ft, start_s = stations[0]
    end_ft, end_s = stations[-1]
    base = os.path.basename(str(source_path_or_name)) if source_path_or_name else ""
    log_id = os.path.splitext(base)[0].replace("bore_log", "log") if base else "log-unknown"
    model: Dict[str, Any] = {
        "log_id": log_id,
        "source_file": base or None,
        "station_start": start_s,
        "station_end": end_s,
        "station_start_ft": start_ft,
        "station_end_ft": end_ft,
        "span_ft": round(end_ft - start_ft, 2),
        "print_raw": (str(print_val) if print_val is not None else None),
        "candidate_sheets": _sheets_from_print(print_val),
        "depth_ft_min": (min(depths) if depths else None),
        "row_count": len(stations),
    }
    if extras:
        model["extras"] = extras
    return model


def read_borelog(path: str) -> Dict[str, Any]:
    """File-fed: read a bore-log .xlsx and normalize to the shared bore model."""
    wb = openpyxl.load_workbook(path, data_only=True)
    try:
        ws = wb.worksheets[0]
        rows = list(ws.iter_rows(values_only=True))
    finally:
        wb.close()
    if not rows:
        raise ValueError(f"empty bore log: {path}")

    header = [str(h).strip().lower() if h is not None else "" for h in rows[0]]

    def col(*names: str):
        # First matching header wins. Aliases accept either the canonical *_ft
        # header (depth_ft / boc_ft) or the legacy bare header (depth / boc): both
        # are feet, so this normalizes units WITHOUT guessing and stays
        # byte-identical for existing depth/boc sheets. Mirrors from_rows and the
        # module's documented "boc_ft carried under extras, never dropped" contract.
        for name in names:
            if name in header:
                return header.index(name)
        return None

    ci_station = col("station")
    ci_print = col("print")
    ci_depth = col("depth_ft", "depth")
    ci_boc = col("boc_ft", "boc")
    if ci_station is None:
        ci_station = 0

    stations: List = []
    print_val = None
    depths: List[float] = []
    boc_vals: List[float] = []
    for r in rows[1:]:
        if not r:
            continue
        raw = _norm_station(r[ci_station] if ci_station < len(r) else None)
        ft = st.parse_station(raw)
        if ft is not None:
            stations.append((ft, str(raw).strip()))
        if print_val is None and ci_print is not None and ci_print < len(r):
            pv = r[ci_print]
            if pv not in (None, ""):
                print_val = pv
        if ci_depth is not None and ci_depth < len(r) and _is_number(r[ci_depth]):
            depths.append(float(r[ci_depth]))
        if ci_boc is not None and ci_boc < len(r) and _is_number(r[ci_boc]):
            boc_vals.append(float(r[ci_boc]))

    # boc_ft carried under extras (NOT a selection input) so the file path stops
    # dropping the 'boc' column — matching from_rows. No boc column -> extras stays
    # None and the model is byte-identical to before this change.
    extras = {"boc_ft_min": min(boc_vals)} if boc_vals else None
    return _build_bore_model(stations, print_val, depths, path, extras=extras)


def from_rows(rows: Sequence[Mapping[str, Any]],
              source_file: Optional[str] = None) -> Dict[str, Any]:
    """Row-fed: normalize TrueLine-style ``committed_rows`` into the SAME bore
    model as :func:`read_borelog`.

    ``rows`` is a sequence of dicts (one per station reading) with the live
    TrueLine committed_rows shape: ``station`` (text '####+##'), ``station_ft``,
    ``depth_ft``, ``boc_ft``, ``date``, ``crew``, ``print``, ``notes``,
    ``source_file``. Stations are RE-PARSED from the ``station`` TEXT via the same
    parser ``read_borelog`` uses (not the pre-computed ``station_ft``), so the two
    paths cannot drift. The first non-empty ``print`` drives candidate sheets;
    numeric ``depth_ft`` feeds ``depth_ft_min``. ``notes``/``boc_ft``/``date``/
    ``crew`` are preserved under ``extras`` (not selection inputs today). Missing
    ``source_file`` falls back to the first row's ``source_file``. No parseable
    station -> ``ValueError`` (honest fail-safe; never invents a value).
    """
    rows = list(rows or [])
    if not rows:
        raise ValueError("empty committed_rows (no rows)")

    sf = source_file
    if sf is None:
        for r in rows:
            if isinstance(r, Mapping) and r.get("source_file"):
                sf = str(r.get("source_file"))
                break

    stations: List = []
    print_val = None
    depths: List[float] = []
    boc_vals: List[float] = []
    notes_rows = 0
    date_first: Optional[str] = None
    crew_first: Optional[str] = None
    for r in rows:
        if not isinstance(r, Mapping):
            continue
        raw = _norm_station(r.get("station"))
        ft = st.parse_station(raw)
        if ft is not None:
            stations.append((ft, str(raw).strip()))
        if print_val is None:
            pv = r.get("print")
            if pv not in (None, ""):
                print_val = pv
        if _is_number(r.get("depth_ft")):
            depths.append(float(r["depth_ft"]))
        if _is_number(r.get("boc_ft")):
            boc_vals.append(float(r["boc_ft"]))
        if str(r.get("notes") or "").strip():
            notes_rows += 1
        if date_first is None and str(r.get("date") or "").strip():
            date_first = str(r.get("date")).strip()
        if crew_first is None and str(r.get("crew") or "").strip():
            crew_first = str(r.get("crew")).strip()

    extras = {
        "input": "committed_rows",
        "rows_in": len(rows),
        "boc_ft_min": (min(boc_vals) if boc_vals else None),
        "notes_rows": notes_rows,
        "date": date_first,
        "crew": crew_first,
    }
    return _build_bore_model(stations, print_val, depths, sf, extras=extras)
