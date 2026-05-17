"""Deterministic engineering-plan PDF parser.

PURE module. No STATE, no FastAPI, no module-level disk reads, no OCR.
Failure-safe — every extractor returns empty/partial results on any error.

Extracts the seven signal classes identified in the P1 reconnaissance:
  - extract_metadata        producer / creator / page_count / dispatch_hint
  - extract_title_block     project, address, dates, sheet number
  - extract_matchlines      MATCHLINE STA X+XX - SEE SHEET Y
  - extract_station_callouts STA X+XX (single / range / equation forms)
  - extract_ap_ids          AP-### / AP ### / AP_### canonicalized to AP-N
  - extract_splice_ids      SPLICE LOC|POINT|LOCATION ### canonicalized
  - extract_drawing_index   *.DWG references with sheet-context guess
  - extract_fieldwire_table tabular AP rows from Fieldwire reports

Uses pdfplumber only. No pytesseract, no pdf2image, no OCR. If pdfplumber
is not installed, every extractor returns empty results without raising.

This module is consumer-agnostic — it does not import main.py, does not
read STATE, and is not wired into any pipeline by this commit.
"""

from __future__ import annotations

import re
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Union

try:
    import pdfplumber  # type: ignore
    _PDFPLUMBER_AVAILABLE = True
except Exception:
    pdfplumber = None  # type: ignore
    _PDFPLUMBER_AVAILABLE = False


# ---------------------------------------------------------------------------
# Compiled regex patterns (built once at import time)
# ---------------------------------------------------------------------------

_MATCHLINE_RE = re.compile(
    r'MATCHLINE\s+STA\s+(\d+)\+(\d{1,2})(?:/(\d+)\+(\d{1,2}))?'
    r'\s*-\s*SEE\s+SHEET\s+(\d+)',
    re.IGNORECASE,
)
_STATION_RANGE_RE = re.compile(
    r'\bSTA\s+(\d+)\+(\d{1,2})\s+TO\s+STA\s+(\d+)\+(\d{1,2})\b',
    re.IGNORECASE,
)
_STATION_EQ_RE = re.compile(
    r'\bSTA\s+(\d+)\+(\d{1,2})\s*=\s*(\d+)\+(\d{1,2})\b',
    re.IGNORECASE,
)
_STATION_RE = re.compile(
    r'\bSTA\s+(\d+)\+(\d{1,2})\b',
    re.IGNORECASE,
)
_AP_ID_RE = re.compile(
    r'\bAP[\-_\s]?(\d{2,4})\b',
    re.IGNORECASE,
)
_SPLICE_RE = re.compile(
    r'\b(?:PROP\.?\s+)?SPLICE\s+(?:LOC|POINT|LOCATION)\s*#?\s*(\d{1,4})\b',
    re.IGNORECASE,
)
_DWG_FILE_RE = re.compile(
    r'\b([A-Z][A-Z0-9_\-]{2,40}\.DWG)\b',
    re.IGNORECASE,
)
_FIELDWIRE_HINT_RE = re.compile(r'fieldwire', re.IGNORECASE)
_AUTOCAD_HINT_RE = re.compile(r'(autocad|pdfplot)', re.IGNORECASE)

# Fieldwire table row pattern:
#   ROWID  AP NNN   <plan text spanning>   @ASSIGNEE   STATUS - MM-DD-YYYY
_FIELDWIRE_ROW_RE = re.compile(
    r'^(?P<row_id>\d+)\s+'
    r'AP\s+(?P<ap_num>\d{1,4})\s+'
    r'(?P<plan_ref>.+?)\s+'
    r'(?P<assignee>@[A-Z][A-Z0-9_]{1,8})\s+'
    r'(?P<status>[A-Z][A-Z\s]{2,20}?)\s*-\s*'
    r'(?P<status_date>\d{2}[-/]\d{2}[-/]\d{4})\s*$',
    re.MULTILINE,
)

# Title-block patterns (applied to first ~3 pages of text)
_TB_PROJECT_RE = re.compile(
    r'\b(BRENHAM\s+PH(?:ASE)?\s*\d+)\b',
    re.IGNORECASE,
)
_TB_ADDRESS_RE = re.compile(
    r'(\d{1,6}\s+[A-Z][A-Z\s]{1,40}?(?:ST|AVE|RD|DR|BLVD|CT|LN|HWY|PKWY|WAY|TER|CIR)\.?)'
    r'[\s\n,]+([A-Z][A-Z\s]+,\s*[A-Z]{2}\s+\d{5})',
    re.IGNORECASE,
)
_TB_REV_DATE_RE = re.compile(
    r'REVISION\s*[:\s]+(?P<rev>'
    r'[A-Z]+\s+\d{1,2},?\s+\d{4}'      # MAY 22, 2025
    r'|\d{1,2}[-/]\d{1,2}[-/]\d{2,4}'   # 07-15-25
    r'|\d{4}[-/]\d{1,2}[-/]\d{1,2}'     # 2025-07-15
    r')',
    re.IGNORECASE,
)
_TB_LONG_DATE_RE = re.compile(
    r'\b([A-Z]+\s+\d{1,2},?\s+\d{4})\b',
    re.IGNORECASE,
)
_TB_SHEET_RE = re.compile(
    r'\b(?:SHEET\s+)?(\d+)\s+OF\s+\d+\b',
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Small pure helpers
# ---------------------------------------------------------------------------

def _station_to_ft(stations: int, plus: int) -> int:
    return int(stations) * 100 + int(plus)


def _format_station(stations: int, plus: int) -> str:
    return f"{int(stations)}+{int(plus):02d}"


def _canonicalize_ap(raw: Optional[str]) -> str:
    if not raw:
        return ""
    digits = re.sub(r'\D', '', str(raw))
    if not digits:
        return ""
    return f"AP-{int(digits)}"


def _canonicalize_splice(raw: Optional[str]) -> str:
    if not raw:
        return ""
    digits = re.sub(r'\D', '', str(raw))
    if not digits:
        return ""
    return f"SPLICE-{int(digits)}"


def _dispatch_from_strings(*values: Optional[str]) -> str:
    blob = " ".join(str(v) for v in values if v)
    if _FIELDWIRE_HINT_RE.search(blob):
        return "fieldwire"
    if _AUTOCAD_HINT_RE.search(blob):
        return "autocad"
    return "unknown"


# ---------------------------------------------------------------------------
# Safe-open helper — every extractor uses this and only this for PDF I/O
# ---------------------------------------------------------------------------

@contextmanager
def _safe_pdf(pdf_path: Union[str, Path]) -> Iterator[Optional[Any]]:
    """Yield a pdfplumber.PDF or None. Never raises."""
    if not _PDFPLUMBER_AVAILABLE:
        yield None
        return
    try:
        p = Path(pdf_path) if not isinstance(pdf_path, Path) else pdf_path
    except Exception:
        yield None
        return
    if not p.is_file():
        yield None
        return
    pdf = None
    try:
        pdf = pdfplumber.open(str(p))
    except Exception:
        yield None
        return
    try:
        yield pdf
    finally:
        try:
            if pdf is not None:
                pdf.close()
        except Exception:
            pass


def _safe_page_text(page: Any) -> str:
    try:
        return page.extract_text() or ""
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Public extractors
# ---------------------------------------------------------------------------

def extract_metadata(pdf_path: Union[str, Path]) -> Dict[str, Any]:
    """Return PDF metadata + producer-based dispatch hint.

    Output keys always present (None when unknown):
      producer, creator, title, subject, page_count, dispatch_hint
    dispatch_hint ∈ {'fieldwire', 'autocad', 'unknown'}.
    """
    base: Dict[str, Any] = {
        "producer": None,
        "creator": None,
        "title": None,
        "subject": None,
        "page_count": 0,
        "dispatch_hint": "unknown",
    }
    with _safe_pdf(pdf_path) as pdf:
        if pdf is None:
            return base
        try:
            md = dict(pdf.metadata or {})
            producer = md.get("Producer") or md.get("/Producer")
            creator = md.get("Creator") or md.get("/Creator")
            title = md.get("Title") or md.get("/Title")
            subject = md.get("Subject") or md.get("/Subject")
            base["producer"] = str(producer) if producer else None
            base["creator"] = str(creator) if creator else None
            base["title"] = str(title) if title else None
            base["subject"] = str(subject) if subject else None
            base["page_count"] = len(pdf.pages)
            base["dispatch_hint"] = _dispatch_from_strings(
                base["producer"], base["creator"], base["title"], base["subject"]
            )
            return base
        except Exception:
            return base


def extract_title_block(pdf_path: Union[str, Path]) -> Dict[str, Any]:
    """Best-effort extraction of title-block fields from the first 3 pages.

    All fields default to None when not detected. Never raises.
    """
    out: Dict[str, Any] = {
        "project": None,
        "address": None,
        "revision_date": None,
        "original_date": None,
        "sheet_number_first_seen": None,
    }
    with _safe_pdf(pdf_path) as pdf:
        if pdf is None:
            return out
        try:
            scan_pages = pdf.pages[:3]
            blob = "\n".join(_safe_page_text(p) for p in scan_pages)

            proj = _TB_PROJECT_RE.search(blob)
            if proj:
                out["project"] = " ".join(proj.group(1).upper().split())

            addr = _TB_ADDRESS_RE.search(blob)
            if addr:
                street = " ".join(addr.group(1).split()).upper()
                citystate = " ".join(addr.group(2).split()).upper()
                out["address"] = f"{street}, {citystate}"

            rev = _TB_REV_DATE_RE.search(blob)
            if rev:
                out["revision_date"] = rev.group("rev").strip()

            for m in _TB_LONG_DATE_RE.finditer(blob):
                v = m.group(1).strip()
                if v and v != out["revision_date"]:
                    out["original_date"] = v
                    break

            sheet = _TB_SHEET_RE.search(blob)
            if sheet:
                try:
                    out["sheet_number_first_seen"] = int(sheet.group(1))
                except ValueError:
                    pass

            return out
        except Exception:
            return out


def extract_matchlines(pdf_path: Union[str, Path]) -> List[Dict[str, Any]]:
    """Extract MATCHLINE STA X+XX [/Y+YY] - SEE SHEET Z entries.

    Per record: page, station, station_ft, references_sheet,
    second_station (optional, when slash form present), second_station_ft, raw_text.
    """
    results: List[Dict[str, Any]] = []
    with _safe_pdf(pdf_path) as pdf:
        if pdf is None:
            return results
        try:
            for page_idx, page in enumerate(pdf.pages, 1):
                text = _safe_page_text(page)
                if not text:
                    continue
                for m in _MATCHLINE_RE.finditer(text):
                    primary_n, primary_p = int(m.group(1)), int(m.group(2))
                    record: Dict[str, Any] = {
                        "page": page_idx,
                        "station": _format_station(primary_n, primary_p),
                        "station_ft": _station_to_ft(primary_n, primary_p),
                        "references_sheet": int(m.group(5)),
                        "second_station": None,
                        "second_station_ft": None,
                        "raw_text": m.group(0),
                    }
                    if m.group(3) and m.group(4):
                        sec_n, sec_p = int(m.group(3)), int(m.group(4))
                        record["second_station"] = _format_station(sec_n, sec_p)
                        record["second_station_ft"] = _station_to_ft(sec_n, sec_p)
                    results.append(record)
        except Exception:
            return results
    return results


def extract_station_callouts(pdf_path: Union[str, Path]) -> List[Dict[str, Any]]:
    """Extract STA X+XX callouts. Three kinds:
      'range'    — STA A+BB TO STA C+DD
      'equation' — STA A+BB = C+DD
      'single'   — STA A+BB (excluding spans already captured as range/equation)
    """
    results: List[Dict[str, Any]] = []
    with _safe_pdf(pdf_path) as pdf:
        if pdf is None:
            return results
        try:
            for page_idx, page in enumerate(pdf.pages, 1):
                text = _safe_page_text(page)
                if not text:
                    continue
                consumed: List[tuple] = []

                for m in _STATION_RANGE_RE.finditer(text):
                    s1n, s1p, s2n, s2p = (int(g) for g in m.groups())
                    results.append({
                        "page": page_idx,
                        "kind": "range",
                        "station": _format_station(s1n, s1p),
                        "station_ft": _station_to_ft(s1n, s1p),
                        "second_station": _format_station(s2n, s2p),
                        "second_station_ft": _station_to_ft(s2n, s2p),
                        "raw_text": m.group(0),
                    })
                    consumed.append((m.start(), m.end()))

                for m in _STATION_EQ_RE.finditer(text):
                    s1n, s1p, s2n, s2p = (int(g) for g in m.groups())
                    results.append({
                        "page": page_idx,
                        "kind": "equation",
                        "station": _format_station(s1n, s1p),
                        "station_ft": _station_to_ft(s1n, s1p),
                        "second_station": _format_station(s2n, s2p),
                        "second_station_ft": _station_to_ft(s2n, s2p),
                        "raw_text": m.group(0),
                    })
                    consumed.append((m.start(), m.end()))

                for m in _STATION_RE.finditer(text):
                    if any(s <= m.start() < e for s, e in consumed):
                        continue
                    sn, sp = int(m.group(1)), int(m.group(2))
                    results.append({
                        "page": page_idx,
                        "kind": "single",
                        "station": _format_station(sn, sp),
                        "station_ft": _station_to_ft(sn, sp),
                        "second_station": None,
                        "second_station_ft": None,
                        "raw_text": m.group(0),
                    })
        except Exception:
            return results
    return results


def extract_ap_ids(pdf_path: Union[str, Path]) -> List[Dict[str, Any]]:
    """Extract AP identifiers (AP-NNN / AP NNN / AP_NNN), canonicalized to AP-N.

    Per record: page, ap_id_raw, ap_id_canonical.
    """
    results: List[Dict[str, Any]] = []
    with _safe_pdf(pdf_path) as pdf:
        if pdf is None:
            return results
        try:
            for page_idx, page in enumerate(pdf.pages, 1):
                text = _safe_page_text(page)
                if not text:
                    continue
                for m in _AP_ID_RE.finditer(text):
                    raw = m.group(0)
                    canonical = _canonicalize_ap(raw)
                    if not canonical:
                        continue
                    results.append({
                        "page": page_idx,
                        "ap_id_raw": raw,
                        "ap_id_canonical": canonical,
                    })
        except Exception:
            return results
    return results


def extract_splice_ids(pdf_path: Union[str, Path]) -> List[Dict[str, Any]]:
    """Extract splice identifiers (SPLICE LOC|POINT|LOCATION), canonicalized."""
    results: List[Dict[str, Any]] = []
    with _safe_pdf(pdf_path) as pdf:
        if pdf is None:
            return results
        try:
            for page_idx, page in enumerate(pdf.pages, 1):
                text = _safe_page_text(page)
                if not text:
                    continue
                for m in _SPLICE_RE.finditer(text):
                    raw = m.group(0)
                    canonical = _canonicalize_splice(raw)
                    if not canonical:
                        continue
                    results.append({
                        "page": page_idx,
                        "splice_id_raw": raw,
                        "splice_id_canonical": canonical,
                    })
        except Exception:
            return results
    return results


def extract_drawing_index(pdf_path: Union[str, Path]) -> List[Dict[str, Any]]:
    """Extract *.DWG file references (drawing-index entries and title-block refs)."""
    results: List[Dict[str, Any]] = []
    seen_keys: set = set()
    with _safe_pdf(pdf_path) as pdf:
        if pdf is None:
            return results
        try:
            for page_idx, page in enumerate(pdf.pages, 1):
                text = _safe_page_text(page)
                if not text:
                    continue
                for m in _DWG_FILE_RE.finditer(text):
                    fname = m.group(1).upper()
                    key = (page_idx, fname)
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)
                    results.append({
                        "page": page_idx,
                        "file_name": fname,
                    })
        except Exception:
            return results
    return results


def extract_fieldwire_table(pdf_path: Union[str, Path]) -> List[Dict[str, Any]]:
    """Extract Fieldwire tabular AP rows via text-pattern (Fieldwire emits
    rows as flowed text, not bordered tables; pdfplumber.extract_tables
    returns nothing on these files).

    Only runs when the producer/creator/subject metadata or page-1 text
    matches a Fieldwire signature. Returns [] otherwise.
    """
    results: List[Dict[str, Any]] = []
    md = extract_metadata(pdf_path)
    is_fw = md.get("dispatch_hint") == "fieldwire"

    if not is_fw:
        # Fall back to page-1 content check for cases where metadata is stripped
        with _safe_pdf(pdf_path) as pdf:
            if pdf is None:
                return results
            try:
                first_text = _safe_page_text(pdf.pages[0]) if pdf.pages else ""
            except Exception:
                first_text = ""
            if not _FIELDWIRE_HINT_RE.search(first_text or ""):
                return results

    with _safe_pdf(pdf_path) as pdf:
        if pdf is None:
            return results
        try:
            for page_idx, page in enumerate(pdf.pages, 1):
                text = _safe_page_text(page)
                if not text:
                    continue
                for row_no, m in enumerate(_FIELDWIRE_ROW_RE.finditer(text), 1):
                    ap_raw = f"AP {m.group('ap_num')}"
                    results.append({
                        "page": page_idx,
                        "row_match_index": row_no,
                        "row_id": int(m.group("row_id")),
                        "ap_id_raw": ap_raw,
                        "ap_id_canonical": _canonicalize_ap(ap_raw),
                        "plan_ref": " ".join(m.group("plan_ref").split()),
                        "assignee": m.group("assignee"),
                        "status": m.group("status").strip(),
                        "status_date": m.group("status_date"),
                    })
        except Exception:
            return results
    return results


def extract_all(pdf_path: Union[str, Path]) -> Dict[str, Any]:
    """Convenience: run every extractor. Each is independently safe-fail."""
    return {
        "metadata":         extract_metadata(pdf_path),
        "title_block":      extract_title_block(pdf_path),
        "matchlines":       extract_matchlines(pdf_path),
        "station_callouts": extract_station_callouts(pdf_path),
        "ap_ids":           extract_ap_ids(pdf_path),
        "splice_ids":       extract_splice_ids(pdf_path),
        "drawing_index":    extract_drawing_index(pdf_path),
        "fieldwire_table":  extract_fieldwire_table(pdf_path),
    }


# ---------------------------------------------------------------------------
# P5.1 — Sheet station-origin derivation
# ---------------------------------------------------------------------------
# Pure, deterministic, safe-failure helper that interprets already-extracted
# matchline and station-callout records to derive per-sheet plan-stationing
# extent (origin / end / length) with an explicit method + confidence label.
#
# This is NOT an extractor — it performs no PDF I/O. It is consumer-agnostic:
# no STATE, no FastAPI, no imports from main.py. It is not wired into any
# pipeline by this commit.
#
# Input record contracts (best-effort; missing or invalid fields trigger a
# record-level skip, never an exception):
#
#   matchline:
#     - source_sheet (preferred, int): engineering sheet number this
#       matchline is printed on. Falls back to `page` (int) when absent.
#     - references_sheet (int): the sheet this matchline points at.
#     - station_ft (int, >= 0): primary station value, in source-sheet
#       coordinates.
#     - second_station_ft (int, >= 0, optional): when present indicates a
#       slash-form matchline (stationing reset across the boundary). The
#       value is in the REFERENCED sheet's coordinates and is intentionally
#       NOT used as a source-sheet station.
#
#   station_callout:
#     - source_sheet (preferred, int) or `page` fallback.
#     - kind in {'range', 'equation', 'single'} — anything else is treated
#       as 'single'.
#     - station_ft (int, >= 0): primary value, in source-sheet coordinates.
#     - second_station_ft (int, >= 0, optional): for 'range' both endpoints
#       belong to this sheet; for 'equation' the second value is in a
#       different stationing system and is intentionally ignored; for
#       'single' there is no second value.
#
# Output: dict keyed by sheet number (int). Sheets with zero usable records
# are not present in the output. Empty or None input -> {}.
#
# Confidence is determined purely by the count and class of observed
# records — never by absolute station magnitudes. This keeps the helper
# deterministic and explainable.
# ---------------------------------------------------------------------------

_METHOD_MATCHLINE_CHAIN = "matchline_chain"
_METHOD_MATCHLINE_PARTIAL = "matchline_partial"
_METHOD_MATCHLINE_SINGLE = "matchline_single"
_METHOD_CALLOUTS_ONLY = "callouts_only"
_METHOD_SINGLE_SHEET_ISOLATED = "single_sheet_isolated"
_METHOD_UNCERTAIN = "uncertain"

_CONFIDENCE_HIGH = "high"
_CONFIDENCE_MEDIUM = "medium"
_CONFIDENCE_LOW = "low"
_CONFIDENCE_UNCERTAIN = "uncertain"


def _coerce_nonneg_int(value: Any) -> Optional[int]:
    """Strict int coercion. Returns None for None, booleans, NaN, non-integer
    floats, non-numeric strings, or any value that triggers an exception.
    Whole-number floats (e.g. 5.0) are accepted; negative results are
    rejected by the caller, not here.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        try:
            if value != value:  # NaN
                return None
            if value in (float("inf"), float("-inf")):
                return None
            if value.is_integer():
                return int(value)
            return None
        except Exception:
            return None
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        try:
            return int(s)
        except Exception:
            return None
    return None


def _record_source_sheet(record: Dict[str, Any]) -> Optional[int]:
    """Resolve the source-sheet identifier for a record. Prefers
    `source_sheet`; falls back to `page` only when `source_sheet` is absent
    or non-coercible. Returns None when neither resolves to an int.
    """
    if not isinstance(record, dict):
        return None
    src = _coerce_nonneg_int(record.get("source_sheet"))
    if src is not None:
        return src
    return _coerce_nonneg_int(record.get("page"))


def _empty_sheet_bucket() -> Dict[str, Any]:
    return {
        "_matchline_stations": [],
        "_callout_stations": [],
        "_chain_anchor_set": set(),
        "matchline_count": 0,
        "callout_count": 0,
        "has_reset_boundary": False,
    }


def derive_sheet_station_origins(
    matchlines: Optional[List[Dict[str, Any]]],
    station_callouts: Optional[List[Dict[str, Any]]],
) -> Dict[int, Dict[str, Any]]:
    """Derive deterministic per-sheet plan-stationing extent from already-
    extracted matchline and station-callout records.

    See the section header above for the full input/output contract.
    Returns {} on None or empty inputs. Never raises.
    """
    by_sheet: Dict[int, Dict[str, Any]] = {}

    # ── Pass 1: ingest matchlines ────────────────────────────────────────────
    try:
        iterable_ml = list(matchlines or [])
    except Exception:
        iterable_ml = []
    for record in iterable_ml:
        try:
            if not isinstance(record, dict):
                continue
            src = _record_source_sheet(record)
            if src is None or src < 0:
                continue
            station_ft = _coerce_nonneg_int(record.get("station_ft"))
            if station_ft is None or station_ft < 0:
                continue
            references_sheet = _coerce_nonneg_int(record.get("references_sheet"))
            second_station_ft = _coerce_nonneg_int(record.get("second_station_ft"))
            has_slash = second_station_ft is not None and second_station_ft >= 0

            bucket = by_sheet.setdefault(src, _empty_sheet_bucket())
            bucket["_matchline_stations"].append(station_ft)
            bucket["matchline_count"] += 1
            if has_slash:
                bucket["has_reset_boundary"] = True
            if references_sheet is not None and references_sheet >= 0:
                bucket["_chain_anchor_set"].add(references_sheet)
        except Exception:
            continue

    # ── Pass 2: ingest station callouts ──────────────────────────────────────
    try:
        iterable_cl = list(station_callouts or [])
    except Exception:
        iterable_cl = []
    for record in iterable_cl:
        try:
            if not isinstance(record, dict):
                continue
            src = _record_source_sheet(record)
            if src is None or src < 0:
                continue
            station_ft = _coerce_nonneg_int(record.get("station_ft"))
            if station_ft is None or station_ft < 0:
                continue
            kind = str(record.get("kind") or "").strip().lower()
            second_station_ft = _coerce_nonneg_int(record.get("second_station_ft"))

            bucket = by_sheet.setdefault(src, _empty_sheet_bucket())
            bucket["_callout_stations"].append(station_ft)
            bucket["callout_count"] += 1

            # Range callouts: both endpoints are in this sheet's coords.
            # Equation callouts: second value is a different stationing
            # system; intentionally ignored. Single: no second value.
            if (kind == "range"
                    and second_station_ft is not None
                    and second_station_ft >= 0):
                bucket["_callout_stations"].append(second_station_ft)
        except Exception:
            continue

    # ── Pass 3: derive method / confidence / extent per sheet ────────────────
    output: Dict[int, Dict[str, Any]] = {}
    for sheet_no, bucket in by_sheet.items():
        try:
            matchline_stations = bucket["_matchline_stations"]
            callout_stations = bucket["_callout_stations"]
            all_stations = matchline_stations + callout_stations
            if not all_stations:
                continue

            origin = min(all_stations)
            end = max(all_stations)
            length = end - origin

            ml_count = int(bucket["matchline_count"])
            cl_count = int(bucket["callout_count"])
            notes: List[str] = []

            if ml_count >= 2:
                method = _METHOD_MATCHLINE_CHAIN
                confidence = _CONFIDENCE_HIGH
            elif ml_count == 1 and cl_count >= 1:
                method = _METHOD_MATCHLINE_PARTIAL
                confidence = _CONFIDENCE_MEDIUM
            elif ml_count == 1 and cl_count == 0:
                method = _METHOD_MATCHLINE_SINGLE
                confidence = _CONFIDENCE_LOW
                notes.append(
                    "Only one matchline observed; sheet extent inferred "
                    "from a single boundary."
                )
            elif ml_count == 0 and cl_count >= 2:
                method = _METHOD_CALLOUTS_ONLY
                confidence = _CONFIDENCE_LOW
            elif ml_count == 0 and cl_count == 1:
                method = _METHOD_SINGLE_SHEET_ISOLATED
                confidence = _CONFIDENCE_UNCERTAIN
                notes.append(
                    "Only one station callout observed; sheet extent is "
                    "a point, not a range."
                )
            else:
                method = _METHOD_UNCERTAIN
                confidence = _CONFIDENCE_UNCERTAIN

            # A zero-or-negative length collapses confidence to uncertain
            # regardless of method, because we cannot meaningfully derive
            # a sheet length from a single point. The single-callout case
            # is already uncertain; everything else is demoted.
            if length <= 0 and method != _METHOD_SINGLE_SHEET_ISOLATED:
                notes.append(
                    "Derived sheet extent has zero length; downgrading "
                    "to uncertain."
                )
                method = _METHOD_UNCERTAIN
                confidence = _CONFIDENCE_UNCERTAIN

            if bucket["has_reset_boundary"]:
                notes.append(
                    "At least one slash-form matchline observed on this "
                    "sheet (stationing reset across boundary)."
                )

            output[int(sheet_no)] = {
                "origin_ft": int(origin),
                "end_ft": int(end),
                "length_ft": int(length),
                "method": method,
                "confidence": confidence,
                "chain_anchor_sheets": sorted(bucket["_chain_anchor_set"]),
                "has_reset_boundary": bool(bucket["has_reset_boundary"]),
                "matchline_count": ml_count,
                "callout_count": cl_count,
                "notes": notes,
            }
        except Exception:
            continue

    return output
