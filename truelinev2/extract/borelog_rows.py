"""Read-only deterministic bore-log TABLE extraction -> UNTRUSTED reviewable extracted_row dicts.

Parses an uploaded bore-log file into reviewable rows, two-tier:
  1. the SAME v2-native readers the placement engine uses (``truelinev2.ingest.normalize.load_borelog`` —
     READ-ONLY reuse; this module changes none of it), unchanged and first, then
  2. when the engine reader does not recognize the file, the SHIPPED generic name-free span extractor
     (``truelinev2.harness.span_extractor`` — the readiness spine's reader) as a fallback: every
     SOURCE-CONFIRMED span row (a source file explicitly tying two stations together as one bore) becomes a
     reviewable row. Nothing is invented: a file confirming no span raises one honest
     ``BoreLogExtractionError`` carrying ``BORE_LOG_FORMAT_UNRECOGNIZED`` + the extractor's specific
     refusal reasons — never a silent empty success.

Either tier maps into an UNTRUSTED ``extracted_row`` (``extraction_method=TABLE_IMPORT``, status
UNREVIEWED, ``normalized`` = candidate start/end stations — SUGGESTIONS, never truth).

This is a DETERMINISTIC table parse, NOT OCR:
  * no confidence is fabricated (engine-reader rows keep ``confidence=None``; generic rows carry the span
    extractor's OWN source-derived band — HIGH for explicit start/end columns / labeled rows, MEDIUM for an
    inline station-pair callout — never a made-up score),
  * no geometry is placed and no redline is rendered,
  * the engine-eligibility gate is UNCHANGED — a human must still REVIEW (and the rows must be grouped)
    before the placement engine may consider them (``reviewed_bore_log`` owns that gate).

Its purpose is to make manual row entry no longer the default path: an uploaded ``.xlsx``/``.csv``/``.pdf``
bore log yields extracted rows the operator REVIEWS, instead of typing every station by hand.

Name-free: no customer / place / dialect literals — the named formats are auto-detected by the v2 reader
and the fallback grammar is the generic span-table/callout reader (which deliberately skips the named
dialect, so ``select_dialect`` is never weakened).
"""
from __future__ import annotations

import openpyxl

from truelinev2.contracts.extracted_row import HIGH, MEDIUM, TABLE_IMPORT, new_extracted_row
from truelinev2.ingest.normalize import load_borelog

_ROW_ID_PREFIX = "extracted"

# Kept in sync with contracts.uploaded_corpus_engine_handoff.BORE_LOG_FORMAT_UNRECOGNIZED (test-locked);
# defined locally so this extract adapter never imports that module's engine/renderer dependency chain.
BORE_LOG_FORMAT_UNRECOGNIZED = "BORE_LOG_FORMAT_UNRECOGNIZED"


class BoreLogExtractionError(Exception):
    """The uploaded bore-log file could not be parsed into reviewable rows."""


def _read_optional_fields(path) -> dict:
    """Read source-backed OPTIONAL bore-log columns the canonical Bore model does not carry (date / crew /
    boc), so the owner info card can show them WHEN PRESENT. Header-name matched on GENERIC field names (never
    customer/place names); date/crew = first non-empty value, boc = the minimum numeric reading. Returns {}
    on any read failure or when a column is absent/empty — the caller then surfaces an honest 'not available',
    never an invented value. READ-ONLY; opens nothing else and changes no engine/Bore behavior."""
    try:
        wb = openpyxl.load_workbook(str(path), data_only=True)
        try:
            rows = list(wb.worksheets[0].iter_rows(values_only=True))
        finally:
            wb.close()
    except Exception:  # noqa: BLE001 - any unreadable/foreign format -> no optional fields (honest)
        return {}
    if not rows:
        return {}
    header = [str(h).strip().lower() if h is not None else "" for h in rows[0]]

    def col(*names):
        for n in names:
            if n in header:
                return header.index(n)
        return None

    ci_date, ci_crew, ci_boc = col("date"), col("crew"), col("boc", "boc_ft")
    out: dict = {}
    bocs = []
    for r in rows[1:]:
        if not r:
            continue
        if ci_date is not None and "date" not in out and ci_date < len(r) and r[ci_date] not in (None, ""):
            out["date"] = str(r[ci_date]).strip()
        if ci_crew is not None and "crew" not in out and ci_crew < len(r) and r[ci_crew] not in (None, ""):
            out["crew"] = str(r[ci_crew]).strip()
        if ci_boc is not None and ci_boc < len(r):
            v = r[ci_boc]
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                bocs.append(float(v))
    if bocs:
        out["boc_min_ft"] = min(bocs)
    return out


def _next_row_id(existing: set) -> str:
    """First free ``extracted-<n>`` id given the rows already on the reviewed_bore_log (so a re-run, or an
    extraction alongside an existing manual row, never collides)."""
    i = 1
    while f"{_ROW_ID_PREFIX}-{i}" in existing:
        i += 1
    return f"{_ROW_ID_PREFIX}-{i}"


# The span extractor's source-derived confidence bands -> the extracted_row vocabulary (explicit mapping so
# an unexpected band never leaks through as a fabricated value; unknown -> None, honestly absent).
_GENERIC_CONFIDENCE = {"HIGH": HIGH, "MEDIUM": MEDIUM}


def _generic_span_rows(path, source_upload_id, *, at, by, existing_row_ids):
    """Fallback tier: parse the file with the SHIPPED generic name-free span extractor (the readiness
    spine's reader — READ-ONLY reuse) and map every SOURCE-CONFIRMED span row into an UNTRUSTED
    ``extracted_row``. A file confirming no span raises one honest ``BoreLogExtractionError`` naming
    ``BORE_LOG_FORMAT_UNRECOGNIZED`` + the extractor's specific refusal reasons (never an invented row,
    never a silent empty success). The refusal message carries ONLY the named code + the extractor's
    refusal-reason codes — never a filesystem path or a raw reader exception (whose text can embed the
    absolute server path of the stored payload). Lazy import keeps this module's load light."""
    from truelinev2.harness.span_extractor import extract_spans_from_documents
    from truelinev2.harness.span_source import documents_from_file

    extraction = extract_spans_from_documents(documents_from_file(str(path)))
    if not extraction.spans:
        reasons = sorted({r.reason for r in extraction.refusals})
        raise BoreLogExtractionError(
            "could not parse the uploaded bore-log file into rows (%s): not a recognized named bore-log "
            "format, and the generic span reader confirmed no source-tied span — a row must tie a start "
            "and an end station together as one bore (%s)"
            % (BORE_LOG_FORMAT_UNRECOGNIZED, ", ".join(reasons) or "no readable content"))

    rows = []
    used = set(existing_row_ids)
    for span in extraction.spans:
        raw = {
            "start_station": span.start_station,
            "end_station": span.end_station,
            "footage_ft": span.footage,
            "footage_source": span.detail.get("footage_source"),
            "source_file": span.source_file,
            "source_page": span.source_page,
            "source_kind": span.source_kind,
            "span_grammar": span.detail.get("span_grammar"),
            "citation": span.citation,
        }
        if span.start_structure:
            raw["start_structure"] = span.start_structure
        if span.end_structure:
            raw["end_structure"] = span.end_structure
        if span.detail.get("source_bore_ref"):
            raw["source_bore_ref"] = span.detail["source_bore_ref"]
        # Slice 2: the bore log's OWN print/sheet reference, when the source table carries one — raw text
        # and parsed engineering-sheet ints SEPARATELY (mirrors the strict tier's sheet_refs/print_raw so
        # the review gate and the readiness lane see one shape). Absent column -> absent keys, never guessed.
        if span.print_raw:
            raw["print_raw"] = span.print_raw
        if span.sheet_refs:
            raw["sheet_refs"] = list(span.sheet_refs)
        # normalized = candidate SUGGESTIONS (never truth); the same shape as manual/engine-reader rows so
        # the existing review gate treats a generic row identically.
        normalized = {"start_station": span.start_station, "end_station": span.end_station}
        row_id = _next_row_id(used)
        used.add(row_id)
        rows.append(new_extracted_row(
            row_id, source_upload_id, raw=raw, normalized=normalized,
            extraction_method=TABLE_IMPORT, extractor_name=None,
            confidence=_GENERIC_CONFIDENCE.get(span.confidence), warnings=[],
            at=at, by=by,
        ))
    return rows


def extract_rows_from_borelog(path, source_upload_id, *, at, by, existing_row_ids=()):
    """Parse ONE uploaded bore-log file into UNTRUSTED ``extracted_row`` dicts (TABLE_IMPORT, UNREVIEWED).

    Two deterministic tiers, engine reader FIRST (a file it recognizes yields byte-identical rows to the
    pre-fallback behavior): the v2 reader yields one canonical bore span per file (start/end stations +
    footage + candidate sheet refs as raw). When it does not recognize the file, the generic span extractor
    yields one row PER source-confirmed span instead (simple CSV/XLSX span tables, labeled start/end rows,
    inline station-pair callouts, text-PDF bore logs). The caller appends them via
    ``reviewed_bore_log.add_extracted_rows``; this function places no geometry, fabricates no confidence,
    and confers no engine eligibility.

    Raises ``BoreLogExtractionError`` (naming ``BORE_LOG_FORMAT_UNRECOGNIZED``) when NEITHER tier finds a
    source-confirmed span.
    """
    try:
        bore = load_borelog(str(path))
    except Exception:  # noqa: BLE001 - not a named format -> the generic source-confirmed tier
        return _generic_span_rows(path, source_upload_id, at=at, by=by,
                                  existing_row_ids=existing_row_ids)

    raw = {
        "start_station": bore.station_start,
        "end_station": bore.station_end,
        "footage_ft": bore.span_ft,
        "sheet_refs": list(bore.sheet_refs),
        "depth_min_ft": bore.depth_min_ft,
        "source_file": bore.source_file,
        "print_raw": bore.print_raw,
    }
    # Additively surface source-backed optional columns (date / crew / boc) the Bore model omits, WHEN
    # present — for the owner info card. Absent columns are simply not added (caller shows 'not available').
    raw.update(_read_optional_fields(path))
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
