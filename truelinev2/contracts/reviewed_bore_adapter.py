"""Reviewed-row -> engine ``Bore`` adapter (the strict-reader FALLBACK, never the primary path).

Today the uploaded-corpus engine handoff (``uploaded_corpus_engine_handoff.py::_run_engine``) opens the
job's ORIGINAL bore-log file with the strict, format-specific reader (``ingest.normalize.load_borelog``).
When that reader does not recognize the file (a customer CSV / structured-text bore log, say) it raises
``ValueError`` and the handoff dead-ends with the named ``BORE_LOG_FORMAT_UNRECOGNIZED`` blocker -- even
though the SAME file may already have been extracted into reviewable rows (``/extract``) and human-REVIEWED
into an engine-ready ``reviewed_bore_log`` (``reviewed_bore_log.py``). This module is the missing bridge: it
turns those human-reviewed rows into a real ``Bore`` so the deterministic engine can run on them exactly as
it would on a strictly-parsed file.

FAIL-CLOSED, never a guess. ``bore_from_reviewed_rows`` hands back a ``Bore`` ONLY when ALL of the following
hold; any single miss declines (returns ``None`` + a machine-readable reason) rather than fabricating a
placement input:
  1. the reviewed_bore_log is ENGINE-READY (``reviewed_bore_log.is_engine_ready`` -- every non-rejected row
     is reviewed AND grouped AND the grouping is CONFIRMED),
  2. it resolves to EXACTLY ONE engine-eligible row (single-bore-per-job is the current product scope; more
     than one eligible row is an unmodeled multi-bore relationship, not something this adapter guesses at),
  3. the row's EFFECTIVE start + end stations (see precedence below) both parse via ``stations.parse_station``,
  4. a positive footage exists: either an explicit footage value, or -- when none is present -- the absolute
     station delta (``|end_ft - start_ft|``), which is used ONLY as a fallback and is flagged with an
     informational detail (never silently substituted without a trace).

Effective row values are resolved by the SAME precedence the reviewed-row rendering surface already uses
(``render.station_dots.py::resolve_bore_fields`` -- corrected_values > normalized > raw, human CORRECTED
always wins). That precedence idea is reused here on purpose (rows carry the same free-form raw/normalized/
corrected_values layers everywhere), but the resolution is reimplemented LOCALLY: this module must stay
import-pure (stdlib + schema.models + stations + reviewed_bore_log only) and must never pull in
``render/`` (a rendering module has no business being an engine-input dependency).

Field names are alias-tolerant (a free-form extractor may write ``footage`` or ``footage_ft``, ``print`` or
``print_raw``, etc.) -- see ``_FIELD_ALIASES``. Column keys are folded case/punctuation-insensitively so
``"Start Station"`` and ``start_station`` resolve identically.

Pure contract module: no engine/renderer/PDF/dialect/web import, no I/O, no side effects.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple

from truelinev2.contracts.reviewed_bore_log import engine_eligible_row_ids, is_engine_ready
from truelinev2.schema.models import Bore
from truelinev2.stations import parse_station

# Machine-readable decline reasons (returned as the second tuple element when Bore is None). These are
# INTERNAL adapter codes -- never surfaced to a customer directly; the caller keeps the EXISTING
# BORE_LOG_FORMAT_UNRECOGNIZED blocker/copy unchanged and may attach one of these as additive detail.
NOT_ENGINE_READY = "NOT_ENGINE_READY"
ZERO_ELIGIBLE_ROWS = "ZERO_ELIGIBLE_ROWS"
MULTIPLE_ELIGIBLE_ROWS = "MULTIPLE_ELIGIBLE_ROWS"
STATION_UNPARSEABLE = "STATION_UNPARSEABLE"
NO_POSITIVE_FOOTAGE = "NO_POSITIVE_FOOTAGE"

# Informational (NOT a decline) note returned alongside a successfully-built Bore when its footage came
# from the station delta rather than an explicit footage column -- so a caller can log/surface the honest
# provenance of that one derived number without treating it as a failure.
FOOTAGE_FROM_STATION_DELTA = "FOOTAGE_FROM_STATION_DELTA"

# Case-insensitive field aliases for pulling canonical bore fields off a free-form reviewed row (mirrors the
# alias-tolerance PRINCIPLE in render.station_dots.resolve_bore_fields, reimplemented locally so this module
# stays render-import-free). These are DATA keys observed across the generic extractor
# (extract/borelog_rows.py: start_station/end_station/footage_ft/sheet_refs/print_raw/depth_min_ft) and
# manual/typed rows -- never customer/name tokens.
_FIELD_ALIASES: Dict[str, Tuple[str, ...]] = {
    "start_station": ("start_station", "start_sta", "from_station", "sta_start"),
    "end_station": ("end_station", "end_sta", "to_station", "sta_end"),
    "footage": ("footage_ft", "footage", "ft", "feet", "length", "bore_footage"),
    "sheet_refs": ("sheet_refs",),
    "print_raw": ("print_raw", "print", "print_no", "print_number", "print_num", "sheet_print"),
    "depth": ("depth_min_ft", "depth", "bore_depth"),
}
_NUM_RE = re.compile(r"[-+]?\d*\.?\d+")


def _norm_key(k) -> str:
    """Fold a free-form column key to snake_case for alias matching (mirrors station_dots._norm_key)."""
    return re.sub(r"[^a-z0-9]+", "_", str(k).strip().lower()).strip("_")


def _effective_values(row: Dict[str, Any]) -> Dict[str, Any]:
    """Effective row values by precedence raw < normalized < review.corrected_values (human CORRECTED wins
    last). Keys normalized for alias matching. Reads a plain extracted_row dict; no schema coupling."""
    merged: Dict[str, Any] = {}
    layers = (row.get("raw"), row.get("normalized"), (row.get("review") or {}).get("corrected_values"))
    for layer in layers:
        if isinstance(layer, dict):
            for k, v in layer.items():
                merged[_norm_key(k)] = v
    return merged


def _pick(merged: Dict[str, Any], aliases: Tuple[str, ...]):
    for a in aliases:
        if a in merged and merged[a] not in (None, ""):
            return merged[a]
    return None


def _coerce_ft(value) -> Optional[float]:
    """Coerce a numeric-ish value ("176", "176'", 176, 176.0) to float; None when absent/non-numeric."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    m = _NUM_RE.search(str(value))
    return float(m.group(0)) if m else None


def _coerce_int(value) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(round(value))
    m = _NUM_RE.search(str(value))
    return int(round(float(m.group(0)))) if m else None


def _coerce_int_list(value) -> list:
    """Ordered-dedup list of ints from a sheet_refs value (a list, a single scalar, or absent -> [])."""
    if value is None:
        return []
    items = value if isinstance(value, (list, tuple)) else [value]
    out, seen = [], set()
    for item in items:
        n = _coerce_int(item)
        if n is None or n in seen:
            continue
        seen.add(n)
        out.append(n)
    return out


def _as_str(value) -> Optional[str]:
    return None if value is None else str(value)


def bore_from_reviewed_rows(rbl: dict, *, source_filename: str) -> Tuple[Optional[Bore], Optional[str]]:
    """Build a real engine ``Bore`` from a reviewed_bore_log's human-reviewed rows, or decline honestly.

    Returns ``(bore, detail)``:
      * ``(Bore, None)`` on success (no derived-footage note),
      * ``(Bore, FOOTAGE_FROM_STATION_DELTA)`` on success when footage had to be derived from the station
        delta (no explicit footage column present) -- still a success, just an honest provenance note,
      * ``(None, <decline reason>)`` when any fail-closed condition (see module docstring) is not met.

    ``bore.bore_id`` is the reviewed_bore_log's own id (a stable, generic, name-free identity already
    scoped to this job); ``bore.source_file`` is the caller-supplied original upload filename (the reviewed
    row's own free-form fields are never trusted for THAT identity). ``sheet_refs``/``print_raw``/
    ``depth_min_ft`` are pulled from the effective row values when present, else left empty/None -- never
    guessed.
    """
    if not is_engine_ready(rbl):
        return None, NOT_ENGINE_READY
    eligible_ids = engine_eligible_row_ids(rbl)
    if not eligible_ids:
        return None, ZERO_ELIGIBLE_ROWS
    if len(eligible_ids) > 1:
        return None, MULTIPLE_ELIGIBLE_ROWS

    row = next((r for r in rbl.get("rows", []) if r.get("row_id") == eligible_ids[0]), None)
    if row is None:
        return None, ZERO_ELIGIBLE_ROWS

    merged = _effective_values(row)
    start_raw = _pick(merged, _FIELD_ALIASES["start_station"])
    end_raw = _pick(merged, _FIELD_ALIASES["end_station"])
    start_ft = parse_station(start_raw) if start_raw is not None else None
    end_ft = parse_station(end_raw) if end_raw is not None else None
    if start_ft is None or end_ft is None:
        return None, STATION_UNPARSEABLE

    detail = None
    footage = _coerce_ft(_pick(merged, _FIELD_ALIASES["footage"]))
    if footage is None or footage <= 0:
        delta = abs(end_ft - start_ft)
        if delta <= 0:
            return None, NO_POSITIVE_FOOTAGE
        footage = delta
        detail = FOOTAGE_FROM_STATION_DELTA

    sheet_refs = _coerce_int_list(_pick(merged, _FIELD_ALIASES["sheet_refs"]))
    print_raw = _as_str(_pick(merged, _FIELD_ALIASES["print_raw"]))
    depth_min_ft = _coerce_ft(_pick(merged, _FIELD_ALIASES["depth"]))

    bore = Bore(
        bore_id=rbl["reviewed_bore_log_id"],
        project=None,
        source_file=source_filename,
        sheet_refs=sheet_refs,
        station_start=str(start_raw),
        station_end=str(end_raw),
        station_start_ft=start_ft,
        station_end_ft=end_ft,
        span_ft=footage,
        depth_min_ft=depth_min_ft,
        print_raw=print_raw,
    )
    return bore, detail
