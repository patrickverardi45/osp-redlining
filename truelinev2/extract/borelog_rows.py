"""Read-only deterministic bore-log TABLE extraction -> UNTRUSTED reviewable extracted_row dicts.

Parses an uploaded bore-log file into reviewable rows via the SAME v2-native readers the placement engine
uses (``truelinev2.ingest.normalize.load_borelog`` — READ-ONLY reuse; this module changes none of it) and
maps each parsed bore span into an UNTRUSTED ``extracted_row`` (``extraction_method=TABLE_IMPORT``, status
UNREVIEWED, ``normalized`` = candidate start/end stations — SUGGESTIONS, never truth).

This is a DETERMINISTIC table parse, NOT OCR:
  * no confidence is fabricated (``confidence=None``),
  * no geometry is placed and no redline is rendered,
  * the engine-eligibility gate is UNCHANGED — a human must still REVIEW (and the rows must be grouped)
    before the placement engine may consider them (``reviewed_bore_log`` owns that gate).

Its purpose is to make manual row entry no longer the default path: an uploaded ``.xlsx``/``.csv`` bore log
yields extracted rows the operator REVIEWS, instead of typing every station by hand.

Name-free: no customer / place / dialect literals — the format is auto-detected by the v2 reader.
"""
from __future__ import annotations

from truelinev2.contracts.extracted_row import TABLE_IMPORT, new_extracted_row
from truelinev2.ingest.normalize import load_borelog

_ROW_ID_PREFIX = "extracted"


class BoreLogExtractionError(Exception):
    """The uploaded bore-log file could not be parsed into reviewable rows."""


def _next_row_id(existing: set) -> str:
    """First free ``extracted-<n>`` id given the rows already on the reviewed_bore_log (so a re-run, or an
    extraction alongside an existing manual row, never collides)."""
    i = 1
    while f"{_ROW_ID_PREFIX}-{i}" in existing:
        i += 1
    return f"{_ROW_ID_PREFIX}-{i}"


def extract_rows_from_borelog(path, source_upload_id, *, at, by, existing_row_ids=()):
    """Parse ONE uploaded bore-log file into UNTRUSTED ``extracted_row`` dicts (TABLE_IMPORT, UNREVIEWED).

    The v2 reader yields one canonical bore span per file, so this returns a single-element list (the bore's
    start/end stations + footage + candidate sheet refs as raw, and start/end stations as the normalized
    candidate). The caller appends them via ``reviewed_bore_log.add_extracted_rows``; this function places no
    geometry, fabricates no confidence, and confers no engine eligibility.

    Raises ``BoreLogExtractionError`` on an unreadable / unrecognized file.
    """
    try:
        bore = load_borelog(str(path))
    except Exception as exc:  # noqa: BLE001 - normalize any reader failure to one honest error
        raise BoreLogExtractionError(
            "could not parse the uploaded bore-log file into rows: %s" % (exc,)) from exc

    raw = {
        "start_station": bore.station_start,
        "end_station": bore.station_end,
        "footage_ft": bore.span_ft,
        "sheet_refs": list(bore.sheet_refs),
        "depth_min_ft": bore.depth_min_ft,
        "source_file": bore.source_file,
        "print_raw": bore.print_raw,
    }
    # normalized = candidate SUGGESTIONS (never truth); mirrors the manual-entry row shape so the existing
    # review gate treats an extracted row identically to a typed one.
    normalized = {"start_station": bore.station_start, "end_station": bore.station_end}
    row = new_extracted_row(
        _next_row_id(set(existing_row_ids)), source_upload_id,
        raw=raw, normalized=normalized,
        extraction_method=TABLE_IMPORT, extractor_name=None, confidence=None, warnings=[],
        at=at, by=by,
    )
    return [row]
