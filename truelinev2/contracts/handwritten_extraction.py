"""Phase-1 handwritten/scanned bore-log page extraction (contract-only, pure).

The real sources are printed "BORE LOG" forms filled by hand (scanned image) or digitally (text-layer
PDF): a header (date / crew / job name / print number) plus up to 4 printed STATION|DEPTH|BOC columns
forming a 50-ft station LADDER. There is NO Bore ID field on the form, and a page may contain more than
one bore (a non-ascending station step means the ladder RESET -- a new bore started). This module owns
the three pure, name-free, evidence-preserving steps between an untrusted page read and the existing
review machinery:

  1. ``validate_page_extraction`` -- schema + HONESTY invariants on one ``HandwrittenPageExtraction``
     record (a value may exist ONLY when its cell's status is READ; UNREADABLE/NOT_PRESENT cells are
     never allowed to carry a fabricated value).
  2. ``spans_from_page`` -- the ladder -> span NORMALIZER. Splits the page's station readings into
     maximal strictly-ascending runs (each reset is a run boundary), and turns every run of >= 2 usable
     (READ + parseable) stations into one conservative ``SpanProposal``. This is NORMALIZATION, never
     guessing: depth/BOC only get a value when it is literally constant across the run's READ cells;
     any UNREADABLE cell or any disagreement forces the field to ``None`` (the full per-station series is
     always preserved in ``station_readings`` so nothing is lost, only left unresolved).
  3. ``rbl_fanout_plan`` -- turns a list of ``SpanProposal`` into one single-row reviewed_bore_log SPEC
     per proposal (deterministic ids + display labels). Pure planning only: no store writes, no calls
     into ``reviewed_bore_log.py``. This exists because the current review machinery's adapter
     deliberately accepts exactly ONE eligible row per reviewed_bore_log (single-bore-per-job scope);
     a page with multiple bores/runs must fan out to multiple RBL specs sharing the same source page.

Naming: "extractor" is opaque runtime data (a tool/provider label), never a hardcoded provider name.
Nothing here calls an AI/OCR provider, touches the engine/renderer/dialect registry, or performs I/O --
it operates purely on already-built page-extraction dicts.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from truelinev2.stations import parse_station, strip_station_label

PAGE_RECORD_FORMAT = "trueline-handwritten-page-extraction-1"
SPAN_RECORD_FORMAT = "trueline-handwritten-span-proposal-1"

# HandwrittenPageExtraction.method
TEXT_LAYER = "TEXT_LAYER"
VISION_OCR = "VISION_OCR"
PAGE_METHODS = (TEXT_LAYER, VISION_OCR)

# Cell.status
READ = "READ"
UNREADABLE = "UNREADABLE"
NOT_PRESENT = "NOT_PRESENT"
CELL_STATUSES = (READ, UNREADABLE, NOT_PRESENT)

# Cell.confidence -- deliberately excludes HIGH: Phase-1 untrusted OCR/text-layer reads are NEVER trusted
# at HIGH confidence (mirrors extracted_row's confidence-banding doctrine, narrowed here on purpose).
LOW = "LOW"
MEDIUM = "MEDIUM"
CELL_CONFIDENCE_LEVELS = (LOW, MEDIUM)

# HandwrittenPageExtraction.page_status
EXTRACTED = "EXTRACTED"
REFUSED = "REFUSED"
PAGE_STATUSES = (EXTRACTED, REFUSED)

# SpanProposal.footage_derivation -- the only value Phase-1 emits (footage is always the station delta;
# a named string rather than a bare boolean so a future derivation method can be added additively).
DERIVED_FROM_STATIONS = "DERIVED_FROM_STATIONS"

_REQUIRED_CELL_KEYS = frozenset({"value", "verbatim", "status", "confidence", "region"})
_REQUIRED_HEADER_FIELDS = ("date", "crew", "job_name", "print_raw")
_REQUIRED_SOURCE_KEYS = frozenset({"upload_id", "sha256", "file_name", "page_index", "page_count"})
_NUM_RE = re.compile(r"[-+]?\d*\.?\d+")


class HandwrittenExtractionError(ValueError):
    """Base error for this module."""


class InvalidCellError(HandwrittenExtractionError):
    """A Cell dict fails schema or honesty invariants."""


class InvalidPageExtractionError(HandwrittenExtractionError):
    """A HandwrittenPageExtraction record fails schema or honesty invariants."""


# --------------------------------------------------------------------------- #
# 1. validate_page_extraction -- schema + honesty invariants.
# --------------------------------------------------------------------------- #
def _validate_cell(cell: Any, label: str) -> Dict[str, Any]:
    if not isinstance(cell, dict) or set(cell.keys()) != _REQUIRED_CELL_KEYS:
        raise InvalidCellError(
            "%s must be a dict with exactly keys %r (got %r)" % (label, sorted(_REQUIRED_CELL_KEYS), cell))
    status = cell["status"]
    if status not in CELL_STATUSES:
        raise InvalidCellError("%s.status must be one of %r (got %r)" % (label, CELL_STATUSES, status))
    confidence = cell["confidence"]
    if confidence is not None and confidence not in CELL_CONFIDENCE_LEVELS:
        raise InvalidCellError(
            "%s.confidence must be None or one of %r (got %r)" % (label, CELL_CONFIDENCE_LEVELS, confidence))
    verbatim = cell["verbatim"]
    if verbatim is not None and not isinstance(verbatim, str):
        raise InvalidCellError("%s.verbatim must be a string or None (got %r)" % (label, verbatim))
    region = cell["region"]
    if region is not None:
        if not isinstance(region, (list, tuple)) or len(region) != 4:
            raise InvalidCellError("%s.region must be None or a 4-tuple/list of floats (got %r)" % (label, region))
        for coord in region:
            if not isinstance(coord, (int, float)) or isinstance(coord, bool) or not (0.0 <= float(coord) <= 1.0):
                raise InvalidCellError("%s.region coordinates must be in [0, 1] (got %r)" % (label, region))
    value = cell["value"]
    if value is not None and not isinstance(value, (str, int, float)):
        raise InvalidCellError("%s.value must be str/float/None (got %r)" % (label, value))
    # HONESTY INVARIANT (the reason this module exists): a value may exist ONLY on a READ cell.
    # UNREADABLE/NOT_PRESENT must never carry a fabricated value.
    if value is not None and status != READ:
        raise InvalidCellError(
            "%s carries a value %r but status is %r (only READ cells may carry a value)" % (label, value, status))
    return cell


def validate_page_extraction(record: Dict[str, Any]) -> Dict[str, Any]:
    """Validate one ``HandwrittenPageExtraction`` record's schema + honesty invariants. Returns the SAME
    record unchanged on success; raises ``InvalidPageExtractionError``/``InvalidCellError`` otherwise.
    Pure -- no mutation, no I/O."""
    if not isinstance(record, dict):
        raise InvalidPageExtractionError("record must be a dict (got %r)" % (record,))
    if record.get("record_format") != PAGE_RECORD_FORMAT:
        raise InvalidPageExtractionError(
            "record_format must be %r (got %r)" % (PAGE_RECORD_FORMAT, record.get("record_format")))

    source = record.get("source")
    if not isinstance(source, dict) or set(source.keys()) != _REQUIRED_SOURCE_KEYS:
        raise InvalidPageExtractionError(
            "source must be a dict with exactly keys %r (got %r)" % (sorted(_REQUIRED_SOURCE_KEYS), source))
    if not isinstance(source["upload_id"], str) or not source["upload_id"]:
        raise InvalidPageExtractionError("source.upload_id must be a non-empty string")
    if not isinstance(source["sha256"], str) or not source["sha256"]:
        raise InvalidPageExtractionError("source.sha256 must be a non-empty string")
    if not isinstance(source["file_name"], str) or not source["file_name"]:
        raise InvalidPageExtractionError("source.file_name must be a non-empty string")
    page_index = source["page_index"]
    page_count = source["page_count"]
    if not isinstance(page_index, int) or isinstance(page_index, bool) or page_index < 0:
        raise InvalidPageExtractionError("source.page_index must be a non-negative int (got %r)" % (page_index,))
    if not isinstance(page_count, int) or isinstance(page_count, bool) or page_count < 1:
        raise InvalidPageExtractionError("source.page_count must be a positive int (got %r)" % (page_count,))
    if page_index >= page_count:
        raise InvalidPageExtractionError(
            "source.page_index %r must be < source.page_count %r" % (page_index, page_count))

    if record.get("method") not in PAGE_METHODS:
        raise InvalidPageExtractionError(
            "method must be one of %r (got %r)" % (PAGE_METHODS, record.get("method")))
    if not isinstance(record.get("extractor"), str) or not record["extractor"]:
        raise InvalidPageExtractionError("extractor must be a non-empty string (opaque runtime data)")

    header = record.get("header")
    if not isinstance(header, dict) or set(header.keys()) != set(_REQUIRED_HEADER_FIELDS):
        raise InvalidPageExtractionError(
            "header must be a dict with exactly keys %r (got %r)" % (list(_REQUIRED_HEADER_FIELDS), header))
    for field in _REQUIRED_HEADER_FIELDS:
        _validate_cell(header[field], "header.%s" % field)

    readings = record.get("readings")
    if not isinstance(readings, list):
        raise InvalidPageExtractionError("readings must be a list (got %r)" % (readings,))
    for i, reading in enumerate(readings):
        if not isinstance(reading, dict) or set(reading.keys()) != {
            "station", "depth_ft", "boc_ft", "column_index", "row_index"}:
            raise InvalidPageExtractionError("readings[%d] has an unexpected shape: %r" % (i, reading))
        _validate_cell(reading["station"], "readings[%d].station" % i)
        _validate_cell(reading["depth_ft"], "readings[%d].depth_ft" % i)
        _validate_cell(reading["boc_ft"], "readings[%d].boc_ft" % i)
        for key in ("column_index", "row_index"):
            v = reading[key]
            if not isinstance(v, int) or isinstance(v, bool) or v < 0:
                raise InvalidPageExtractionError(
                    "readings[%d].%s must be a non-negative int (got %r)" % (i, key, v))

    page_status = record.get("page_status")
    if page_status not in PAGE_STATUSES:
        raise InvalidPageExtractionError(
            "page_status must be one of %r (got %r)" % (PAGE_STATUSES, page_status))
    refusal = record.get("refusal")
    if page_status == REFUSED:
        if not isinstance(refusal, dict) or not refusal.get("code") or not refusal.get("reason"):
            raise InvalidPageExtractionError("page_status REFUSED requires refusal={code, reason}")
    elif refusal is not None:
        raise InvalidPageExtractionError("page_status EXTRACTED requires refusal=None (got %r)" % (refusal,))

    warnings = record.get("warnings")
    if not isinstance(warnings, list) or not all(isinstance(w, str) for w in warnings):
        raise InvalidPageExtractionError("warnings must be a list of strings")
    audit = record.get("audit")
    if not isinstance(audit, list):
        raise InvalidPageExtractionError("audit must be a list")

    return record


# --------------------------------------------------------------------------- #
# Local station-ladder helpers (kept local on purpose -- see module docstring).
# --------------------------------------------------------------------------- #
def _sheet_refs_from_print(print_val) -> Tuple[int, ...]:
    """Parse a print/sheet cell into engineering-sheet ints: every digit run, in print order, de-duped --
    mirrors the SAME rule used by the strict/generic readers (``harness/span_extractor.py::
    _sheet_refs_from_print``), reimplemented LOCALLY per this module's import-purity rule. Handles
    "29,30,31" -> (29, 30, 31) and "WP 23" -> (23,)."""
    out: List[int] = []
    for n in re.findall(r"\d+", str(print_val or "")):
        v = int(n)
        if v not in out:
            out.append(v)
    return tuple(out)


def _parse_station_feet(cell: Dict[str, Any]) -> Optional[float]:
    """A usable station reading requires status READ and a value that parses to feet. Accepts a numeric
    value directly, or a station-notation string (optionally "STA "-prefixed, e.g. "STA 3+50")."""
    if cell["status"] != READ or cell["value"] is None:
        return None
    value = cell["value"]
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return parse_station(strip_station_label(str(value)))


def _coerce_float(value) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    m = _NUM_RE.search(str(value))
    return float(m.group(0)) if m else None


def _values_agree(a, b) -> bool:
    fa, fb = _coerce_float(a), _coerce_float(b)
    if fa is not None and fb is not None:
        return abs(fa - fb) < 1e-9
    return str(a) == str(b)


def _series_value(run: List[Tuple[float, Dict[str, Any]]], field: str):
    """Constant-across-the-run READ cells -> that value; any UNREADABLE cell or disagreement -> None
    (never guessed). Returns (value_or_None, evidence_status, cells) where evidence_status is one of
    READ / UNREADABLE / NOT_PRESENT / VARIED (VARIED is a cell_evidence-only marker -- not a Cell.status
    -- meaning "readable cells disagreed, so the field was left unresolved")."""
    cells = [reading[field] for _, reading in run]
    if any(c["status"] == UNREADABLE for c in cells):
        return None, UNREADABLE, cells
    read_cells = [c for c in cells if c["status"] == READ]
    if not read_cells:
        return None, NOT_PRESENT, cells
    first = read_cells[0]["value"]
    if all(_values_agree(c["value"], first) for c in read_cells):
        return _coerce_float(first), READ, cells
    return None, "VARIED", cells


def _cell_evidence_entry(cell: Dict[str, Any], page_index: int) -> Dict[str, Any]:
    return {"status": cell["status"], "page_index": page_index,
            "region": cell["region"], "verbatim": cell["verbatim"]}


def _series_evidence_entry(cells: List[Dict[str, Any]], page_index: int, status_label: str) -> Dict[str, Any]:
    representative = next((c for c in cells if c["status"] == READ), cells[0] if cells else None)
    return {
        "status": status_label,
        "page_index": page_index,
        "region": representative["region"] if representative else None,
        "verbatim": representative["verbatim"] if representative else None,
    }


def _header_text(cell: Dict[str, Any]) -> Optional[str]:
    if cell["status"] != READ:
        return None
    text = cell["verbatim"] if cell["verbatim"] is not None else cell["value"]
    return None if text is None else str(text)


# --------------------------------------------------------------------------- #
# 2. spans_from_page -- the ladder -> span normalizer.
# --------------------------------------------------------------------------- #
def spans_from_page(record: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Split one validated page's station ladder into maximal strictly-ascending runs (a non-ascending
    step -- reset token -- is a run boundary, meaning a new bore) and turn each run of >= 2 usable
    (READ + parseable) stations into one conservative ``SpanProposal``. Runs with < 2 usable stations
    produce NO proposal (a single stray reading proves nothing about a bore's extent); a warning naming
    that run is folded into the warnings of every proposal this page DOES produce (page-scoped context).
    A REFUSED page yields no proposals. Never guesses: depth/BOC/date/crew/notes are None unless the
    source cell(s) were actually READ; confidence is never HIGH."""
    validate_page_extraction(record)
    if record["page_status"] != EXTRACTED:
        return []

    readings = sorted(record["readings"], key=lambda r: (r["column_index"], r["row_index"]))
    usable: List[Tuple[float, Dict[str, Any]]] = []
    for reading in readings:
        feet = _parse_station_feet(reading["station"])
        if feet is not None:
            usable.append((feet, reading))

    runs: List[List[Tuple[float, Dict[str, Any]]]] = []
    current: List[Tuple[float, Dict[str, Any]]] = []
    for feet, reading in usable:
        if current and feet <= current[-1][0]:
            runs.append(current)
            current = []
        current.append((feet, reading))
    if current:
        runs.append(current)

    skip_warnings = []
    for run in runs:
        if len(run) < 2:
            _, reading = run[0]
            skip_warnings.append(
                "run at column %d row %d has fewer than 2 usable station readings; skipped"
                % (reading["column_index"], reading["row_index"]))

    header = record["header"]
    date_val = _header_text(header["date"])
    crew_val = _header_text(header["crew"])
    job_name_val = _header_text(header["job_name"])
    notes_val = ("Job name: %s" % job_name_val) if job_name_val is not None else None
    print_cell = header["print_raw"]
    print_raw_val = _header_text(print_cell)
    sheet_refs = list(_sheet_refs_from_print(print_raw_val)) if print_raw_val else []

    page_index = record["source"]["page_index"]
    page_source = dict(record["source"])
    page_warnings = list(record.get("warnings") or []) + skip_warnings

    proposals: List[Dict[str, Any]] = []
    for run in runs:
        if len(run) < 2:
            continue
        start_feet, start_reading = run[0]
        end_feet, end_reading = run[-1]
        start_cell, end_cell = start_reading["station"], end_reading["station"]

        depth_ft, depth_status, depth_cells = _series_value(run, "depth_ft")
        boc_ft, boc_status, boc_cells = _series_value(run, "boc_ft")

        confidence = LOW
        if (start_cell["confidence"] == MEDIUM and end_cell["confidence"] == MEDIUM
                and print_cell["status"] == READ):
            confidence = MEDIUM

        cell_evidence = {
            "start_station": _cell_evidence_entry(start_cell, page_index),
            "end_station": _cell_evidence_entry(end_cell, page_index),
            "print_raw": _cell_evidence_entry(print_cell, page_index),
            "date": _cell_evidence_entry(header["date"], page_index),
            "crew": _cell_evidence_entry(header["crew"], page_index),
            "job_name": _cell_evidence_entry(header["job_name"], page_index),
            "depth_ft": _series_evidence_entry(depth_cells, page_index, depth_status),
            "boc_ft": _series_evidence_entry(boc_cells, page_index, boc_status),
        }

        proposals.append({
            "record_format": SPAN_RECORD_FORMAT,
            "source": page_source,
            "bore_id": None,
            "print_raw": print_raw_val,
            "sheet_refs": sheet_refs,
            "start_station": str(start_cell["value"]),
            "end_station": str(end_cell["value"]),
            "footage_ft": abs(end_feet - start_feet),
            "footage_derivation": DERIVED_FROM_STATIONS,
            "depth_ft": depth_ft,
            "boc_ft": boc_ft,
            "date": date_val,
            "crew": crew_val,
            "notes": notes_val,
            "station_readings": [reading for _, reading in run],
            "cell_evidence": cell_evidence,
            "confidence": confidence,
            "warnings": list(page_warnings),
        })
    return proposals


# --------------------------------------------------------------------------- #
# 3. rbl_fanout_plan -- pure planning, one single-row RBL spec per proposal.
# --------------------------------------------------------------------------- #
def rbl_fanout_plan(proposals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Turn a list of ``SpanProposal`` into one single-row reviewed_bore_log SPEC per proposal, with
    deterministic ids (``rbl-hw-p{page_index}-r{run_number}``, 1-based run numbering PER page in input
    order) and a human display label. Pure planning ONLY -- no store writes, no calls into
    ``reviewed_bore_log.py``; the caller is responsible for actually creating/persisting each RBL."""
    run_counters: Dict[int, int] = {}
    plan: List[Dict[str, Any]] = []
    for proposal in proposals:
        page_index = proposal["source"]["page_index"]
        run_counters[page_index] = run_counters.get(page_index, 0) + 1
        run_no = run_counters[page_index]
        rbl_id = "rbl-hw-p%d-r%d" % (page_index, run_no)
        label = "Page %d, run %d (%s -> %s)" % (
            page_index, run_no, proposal["start_station"], proposal["end_station"])
        plan.append({
            "reviewed_bore_log_id": rbl_id,
            "display_label": label,
            "source_upload_id": proposal["source"]["upload_id"],
            "page_index": page_index,
            "run_number": run_no,
            "proposal": proposal,
        })
    return plan
