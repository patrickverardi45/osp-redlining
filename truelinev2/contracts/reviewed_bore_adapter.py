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
  4. a positive footage exists: either an explicit footage value, or -- ONLY when the footage field is truly
     ABSENT (no footage/footage_ft alias key, or an empty value) -- the absolute station delta
     (``|end_ft - start_ft|``), flagged with an informational detail (never silently substituted without a
     trace). A footage field that IS present but zero, negative, or non-numeric DECLINES outright (fail-
     closed: the source's own numbers are inconsistent -- never silently replaced by the station delta).
     EXCEPTION (OCR-only preflight): when the row's ``extraction.extraction_method`` is ``OCR`` and no
     usable explicit footage exists, this DECLINES with ``OCR_ROW_REQUIRES_EXPLICIT_FOOTAGE`` instead of
     ever deriving footage from the station delta -- an OCR row's start/end stations are themselves
     untrusted reads, so silently multiplying two of them into a placement number is never acceptable.
     Non-OCR methods are unaffected.

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

from truelinev2.contracts.extracted_row import OCR
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
# A footage field is PRESENT (a non-empty footage/footage_ft alias key exists on the effective row) but its
# value is inconsistent with the source's own numbers -- fail-closed DECLINES rather than silently falling
# back to the station delta (that fallback is reserved for a footage field that is truly ABSENT; see
# ``bore_from_reviewed_rows`` below). Distinct codes so a caller can tell "not a number" from "zero/negative".
FOOTAGE_NOT_NUMERIC = "FOOTAGE_NOT_NUMERIC"
NONPOSITIVE_FOOTAGE = "NONPOSITIVE_FOOTAGE"

# Informational (NOT a decline) note returned alongside a successfully-built Bore when its footage came
# from the station delta rather than an explicit footage column -- so a caller can log/surface the honest
# provenance of that one derived number without treating it as a failure.
FOOTAGE_FROM_STATION_DELTA = "FOOTAGE_FROM_STATION_DELTA"

# OCR-ONLY PREFLIGHT (Phase-1 handwritten extraction): an OCR-extracted row's footage is UNTRUSTED
# arithmetic waiting to happen -- deriving it from the station delta would silently promote two
# independently-fallible OCR reads (start + end station) into a placement number with no human having
# ever confirmed the footage itself. So for extraction_method == OCR ONLY, a row with no usable explicit
# footage DECLINES with this named code instead of falling back to the station delta. Non-OCR methods
# (TABLE_IMPORT / MANUAL_ENTRY / TEXT_PARSE) are completely unaffected -- their station-delta fallback
# behavior below is unchanged.
OCR_ROW_REQUIRES_EXPLICIT_FOOTAGE = "OCR_ROW_REQUIRES_EXPLICIT_FOOTAGE"

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


def _normalized_layer(layer) -> Dict[str, Any]:
    return {_norm_key(k): v for k, v in layer.items()} if isinstance(layer, dict) else {}


def _pick(merged: Dict[str, Any], aliases: Tuple[str, ...]):
    for a in aliases:
        if a in merged and merged[a] not in (None, ""):
            return merged[a]
    return None


def _pick_field(row: Dict[str, Any], aliases: Tuple[str, ...]):
    """Resolve ONE logical field with PER-FIELD overlay precedence:
    ``review.corrected_values`` wins OVER raw/normalized ENTIRELY for this field the moment corrected_values
    carries ANY of the field's aliases -- this is what makes a human CORRECTION visible to the adapter
    (e.g. a CORRECTED footage_ft the per-row review route persisted at ``row["review"]["corrected_values"]``
    must be readable here, not shadowed by a differently-spelled raw column). An EXPLICIT null/empty
    correction CLEARS the field (returns None) and never falls back to raw/normalized -- a human explicitly
    blanking a value is a decision, not an omission; a required field left cleared then declines honestly.
    Only when corrected_values has NONE of the field's aliases at all does resolution fall back to
    raw < normalized (existing precedence, unchanged) -- so a TABLE_IMPORT/MANUAL_ENTRY/TEXT_PARSE row with
    no corrections resolves EXACTLY as before this evolution (byte-identical)."""
    corrected = _normalized_layer((row.get("review") or {}).get("corrected_values"))
    for a in aliases:
        if a in corrected:
            v = corrected[a]
            return v if v not in (None, "") else None
    merged: Dict[str, Any] = {}
    merged.update(_normalized_layer(row.get("raw")))
    merged.update(_normalized_layer(row.get("normalized")))
    return _pick(merged, aliases)


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

    start_raw = _pick_field(row, _FIELD_ALIASES["start_station"])
    end_raw = _pick_field(row, _FIELD_ALIASES["end_station"])
    start_ft = parse_station(start_raw) if start_raw is not None else None
    end_ft = parse_station(end_raw) if end_raw is not None else None
    if start_ft is None or end_ft is None:
        return None, STATION_UNPARSEABLE

    extraction_method = (row.get("extraction") or {}).get("extraction_method")

    detail = None
    # A CORRECTED footage counts as explicit HUMAN footage even for an OCR row -- that IS what a human
    # correction is for (see _pick_field's overlay precedence); only a raw-only DERIVED footage on an OCR
    # row is untrusted arithmetic and declines below.
    footage_raw = _pick_field(row, _FIELD_ALIASES["footage"])
    if footage_raw is not None:
        # Footage field is PRESENT (a non-empty alias key) -- trust it or decline; NEVER fall back to the
        # station delta here (that fallback is reserved for a truly absent field, below).
        footage = _coerce_ft(footage_raw)
        if footage is None:
            return None, FOOTAGE_NOT_NUMERIC
        if footage <= 0:
            if extraction_method == OCR:
                return None, OCR_ROW_REQUIRES_EXPLICIT_FOOTAGE
            return None, NONPOSITIVE_FOOTAGE
    else:
        # Footage field is truly ABSENT. Non-OCR methods keep the existing station-delta fallback; an
        # OCR row DECLINES here instead (see OCR_ROW_REQUIRES_EXPLICIT_FOOTAGE above).
        if extraction_method == OCR:
            return None, OCR_ROW_REQUIRES_EXPLICIT_FOOTAGE
        delta = abs(end_ft - start_ft)
        if delta <= 0:
            return None, NO_POSITIVE_FOOTAGE
        footage = delta
        detail = FOOTAGE_FROM_STATION_DELTA

    sheet_refs = _coerce_int_list(_pick_field(row, _FIELD_ALIASES["sheet_refs"]))
    print_raw = _as_str(_pick_field(row, _FIELD_ALIASES["print_raw"]))
    depth_min_ft = _coerce_ft(_pick_field(row, _FIELD_ALIASES["depth"]))

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
