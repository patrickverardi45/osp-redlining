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
from typing import Any, Dict, Iterator, List, Mapping, Optional, Sequence, Union

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


# ---------------------------------------------------------------------------
# P5.2 — Footage range containment evaluation
# ---------------------------------------------------------------------------
# Pure, deterministic, safe-failure helper that compares a bore-log group's
# measured stationing span against the expected plan-stationing extent of
# the sheets it references.
#
# This helper is SPAN-CONSISTENCY only — NOT absolute coordinate containment.
# Bore-log station_ft is generally NOT in the same coordinate system as plan
# station callouts, so we compare LENGTHS (span_ft vs plan-sheet length sum),
# not absolute ranges. This is a deliberate constraint of the P5 design.
#
# This helper is consumer-agnostic — no STATE, no FastAPI, no PDF I/O, no
# imports from main.py — and is not wired into any pipeline by this commit.
#
# Anchors are evidence, NOT authority:
#   - never picks a route
#   - never modifies its input
#   - never auto-resolves ambiguity
#   - emits a `would_boost` flag for diagnostic use only; downstream code
#     (a future P5.4) decides whether to convert evidence to a score boost.
#
# Input contracts:
#
#   normalized_group:
#     - span_ft: int or float, > 0. The bore-log group's measured stationing
#       extent. Required; absent or non-positive triggers no_data.
#     - print_tokens: list of strings or ints. Bore-log print/sheet
#       references. May be empty (treated as no_data).
#
#   sheet_origins:
#     - The dict returned by derive_sheet_station_origins, keyed by
#       integer sheet number. Each entry must carry length_ft, method,
#       confidence, has_reset_boundary at minimum.
#
#   print_to_sheets (optional):
#     - A mapping print_token -> iterable of int sheet numbers, e.g. the
#       resolved view of CURRENT_PACKET_PRINT_SHEET_INDEX[token]["sheet"].
#       When provided, each print token resolves through this mapping.
#       When absent, each print token is treated as an int sheet number
#       directly via best-effort coercion.
#
# Output:
#
#   {
#     "classification":            str    # contained_consistent / partial_consistent
#                                         # / out_of_range / uncertain / no_data
#     "confidence":                str    # high / medium / low / uncertain
#     "group_span_ft":             int
#     "expected_plan_span_ft":     int    # 0 when topology unavailable
#     "consistency_ratio":         float  # min/max, 0-1; 0.0 when expected is 0
#     "referenced_sheets":         list[int]   # sorted dedup of group's sheets
#     "missing_sheets":            list[int]   # referenced sheets with no topology
#     "covered_sheets":            list[int]   # referenced sheets that had topology
#     "sheet_confidence_levels":   dict[int, str]   # per-sheet confidence
#     "sheet_methods":             dict[int, str]   # per-sheet method
#     "has_reset_boundary":        bool   # any covered sheet has slash form
#     "ambiguity_flags":           list[str]
#     "reasons":                   list[str]
#     "would_boost":               bool   # evidence-only; consumer decides
#   }
#
# Classification thresholds (deterministic, explicit):
#   - contained_consistent: consistency_ratio >= 0.85
#   - partial_consistent:   0.60 <= ratio < 0.85
#   - out_of_range:         ratio < 0.60
#   - uncertain:            unable to compute (no covered sheets, etc.)
#   - no_data:              insufficient input (no span, no prints)
#
# Confidence demotion rules:
#   - Any missing referenced sheet -> never high
#   - Any reset boundary on covered sheets -> never high
#   - Worst per-sheet confidence flows up to the overall confidence
#   - out_of_range with no missing sheets and high topology -> medium
#     (the data is good, the result is just a clean negative)
# ---------------------------------------------------------------------------

_CLASS_CONTAINED = "contained_consistent"
_CLASS_PARTIAL = "partial_consistent"
_CLASS_OUT_OF_RANGE = "out_of_range"
_CLASS_UNCERTAIN = "uncertain"
_CLASS_NO_DATA = "no_data"

_RATIO_CONTAINED_MIN = 0.85
_RATIO_PARTIAL_MIN = 0.60

_CONFIDENCE_RANK = {
    _CONFIDENCE_HIGH: 3,
    _CONFIDENCE_MEDIUM: 2,
    _CONFIDENCE_LOW: 1,
    _CONFIDENCE_UNCERTAIN: 0,
}


def _coerce_positive_number(value: Any) -> Optional[float]:
    """Strict numeric coercion for span_ft. Returns None for None, booleans,
    NaN, ±inf, non-numeric strings, or any non-positive value.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            if value != value:  # NaN
                return None
            if value in (float("inf"), float("-inf")):
                return None
            f = float(value)
            return f if f > 0 else None
        except Exception:
            return None
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        try:
            f = float(s)
            if f != f:
                return None
            return f if f > 0 else None
        except Exception:
            return None
    return None


def _resolve_referenced_sheets(
    print_tokens: List[Any],
    print_to_sheets: Optional[Mapping[Any, Any]],
) -> List[int]:
    """Resolve a group's print tokens to a sorted, deduplicated list of
    sheet numbers. Never raises on malformed input.
    """
    sheets: set = set()
    for tok in print_tokens or []:
        try:
            if tok is None:
                continue
            tok_key = tok
            if print_to_sheets is not None:
                # Try the token as-is, then as a string.
                mapped = None
                if tok_key in print_to_sheets:
                    mapped = print_to_sheets[tok_key]
                else:
                    try:
                        s_key = str(tok).strip()
                        if s_key and s_key in print_to_sheets:
                            mapped = print_to_sheets[s_key]
                    except Exception:
                        mapped = None
                if mapped is not None:
                    try:
                        for s in mapped:
                            n = _coerce_nonneg_int(s)
                            if n is not None and n >= 0:
                                sheets.add(int(n))
                    except TypeError:
                        # mapped wasn't iterable
                        n = _coerce_nonneg_int(mapped)
                        if n is not None and n >= 0:
                            sheets.add(int(n))
                    continue
                # Fall through: token wasn't in the mapping; try direct coerce.
            n = _coerce_nonneg_int(tok)
            if n is not None and n >= 0:
                sheets.add(int(n))
        except Exception:
            continue
    return sorted(sheets)


def _empty_containment_result(
    classification: str = _CLASS_NO_DATA,
    confidence: str = _CONFIDENCE_UNCERTAIN,
    reasons: Optional[List[str]] = None,
    ambiguity_flags: Optional[List[str]] = None,
    group_span_ft: int = 0,
) -> Dict[str, Any]:
    return {
        "classification": classification,
        "confidence": confidence,
        "group_span_ft": int(group_span_ft),
        "expected_plan_span_ft": 0,
        "consistency_ratio": 0.0,
        "referenced_sheets": [],
        "missing_sheets": [],
        "covered_sheets": [],
        "sheet_confidence_levels": {},
        "sheet_methods": {},
        "has_reset_boundary": False,
        "ambiguity_flags": list(ambiguity_flags or []),
        "reasons": list(reasons or []),
        "would_boost": False,
    }


def evaluate_footage_range_containment(
    normalized_group: Optional[Dict[str, Any]],
    sheet_origins: Optional[Dict[int, Dict[str, Any]]],
    print_to_sheets: Optional[Mapping[Any, Any]] = None,
) -> Dict[str, Any]:
    """Span-consistency evaluation between a bore-log group and the
    engineering-plan sheets it references.

    See the section header for full input/output contracts. Returns a
    populated result dict on every input — never raises. Does NOT mutate
    its inputs.

    This is evidence-emission only; the `would_boost` flag is a hint and
    has no authority over route selection.
    """
    # ── Step 0: defensive input validation ───────────────────────────────────
    if not isinstance(normalized_group, dict):
        return _empty_containment_result(
            reasons=["normalized_group is not a dict"]
        )

    span_raw = normalized_group.get("span_ft")
    span_ft_val = _coerce_positive_number(span_raw)
    if span_ft_val is None:
        return _empty_containment_result(
            reasons=["normalized_group.span_ft missing, non-positive, or non-numeric"]
        )
    group_span_ft = int(round(span_ft_val))

    print_tokens_raw = normalized_group.get("print_tokens")
    if not isinstance(print_tokens_raw, list):
        print_tokens_raw = []
    # Read-only snapshot — never mutate caller's list.
    print_tokens = list(print_tokens_raw)

    if not isinstance(sheet_origins, dict):
        sheet_origins_local: Dict[int, Dict[str, Any]] = {}
    else:
        # Build a shallow normalized view keyed by int. Caller's dict is
        # not mutated; we copy keys we trust.
        sheet_origins_local = {}
        for k, v in sheet_origins.items():
            try:
                n = _coerce_nonneg_int(k)
                if n is None or n < 0:
                    continue
                if not isinstance(v, dict):
                    continue
                sheet_origins_local[int(n)] = v
            except Exception:
                continue

    # ── Step 1: resolve referenced sheets ────────────────────────────────────
    referenced_sheets = _resolve_referenced_sheets(print_tokens, print_to_sheets)
    if not referenced_sheets:
        return _empty_containment_result(
            group_span_ft=group_span_ft,
            reasons=["no referenced sheets resolvable from print_tokens"],
        )

    # ── Step 2: gather per-sheet evidence ────────────────────────────────────
    covered: List[int] = []
    missing: List[int] = []
    sheet_lengths: List[int] = []
    sheet_confidence_levels: Dict[int, str] = {}
    sheet_methods: Dict[int, str] = {}
    has_reset_boundary = False
    invalid_lengths: List[int] = []

    for sheet_no in referenced_sheets:
        entry = sheet_origins_local.get(sheet_no)
        if entry is None:
            missing.append(sheet_no)
            continue
        try:
            length_raw = entry.get("length_ft")
            length_val = _coerce_nonneg_int(length_raw)
            if length_val is None or length_val < 0:
                invalid_lengths.append(sheet_no)
                missing.append(sheet_no)
                continue
            covered.append(sheet_no)
            sheet_lengths.append(int(length_val))
            conf = str(entry.get("confidence") or _CONFIDENCE_UNCERTAIN)
            method = str(entry.get("method") or _METHOD_UNCERTAIN)
            sheet_confidence_levels[sheet_no] = conf
            sheet_methods[sheet_no] = method
            if bool(entry.get("has_reset_boundary")):
                has_reset_boundary = True
        except Exception:
            invalid_lengths.append(sheet_no)
            missing.append(sheet_no)
            continue

    reasons: List[str] = []
    ambiguity_flags: List[str] = []

    if missing:
        ambiguity_flags.append("missing_topology")
        reasons.append(
            f"No topology for referenced sheets: {sorted(missing)}"
        )
    if invalid_lengths:
        reasons.append(
            f"Sheets with invalid length_ft skipped: {sorted(invalid_lengths)}"
        )

    # ── Step 3: handle no-coverage case ──────────────────────────────────────
    if not covered:
        return {
            **_empty_containment_result(
                classification=_CLASS_UNCERTAIN,
                confidence=_CONFIDENCE_UNCERTAIN,
                group_span_ft=group_span_ft,
                ambiguity_flags=ambiguity_flags,
                reasons=reasons + ["no covered sheets — cannot derive expected span"],
            ),
            "referenced_sheets": referenced_sheets,
            "missing_sheets": sorted(missing),
            "covered_sheets": [],
            "sheet_confidence_levels": {},
            "sheet_methods": {},
            "has_reset_boundary": False,
        }

    # ── Step 4: compute expected span + ratio ────────────────────────────────
    expected_plan_span_ft = int(sum(sheet_lengths))

    # Multi-print groups whose sheets are non-contiguous deserve a flag.
    if len(covered) >= 2:
        gaps = [
            covered[i + 1] - covered[i]
            for i in range(len(covered) - 1)
        ]
        if any(g > 1 for g in gaps):
            ambiguity_flags.append("non_contiguous_sheet_references")
            reasons.append(
                f"Referenced sheets are non-contiguous: {covered}"
            )

    if expected_plan_span_ft <= 0:
        consistency_ratio = 0.0
        classification = _CLASS_UNCERTAIN
        reasons.append("expected_plan_span_ft is zero — sheet lengths sum to 0")
    else:
        ratio = (
            min(group_span_ft, expected_plan_span_ft)
            / max(group_span_ft, expected_plan_span_ft)
        )
        # Stable rounding for deterministic comparison and output.
        consistency_ratio = round(ratio, 6)
        if consistency_ratio >= _RATIO_CONTAINED_MIN:
            classification = _CLASS_CONTAINED
            reasons.append(
                f"Group span {group_span_ft} ft consistent with plan "
                f"sheet length sum {expected_plan_span_ft} ft "
                f"(ratio {consistency_ratio:.3f} >= {_RATIO_CONTAINED_MIN})."
            )
        elif consistency_ratio >= _RATIO_PARTIAL_MIN:
            classification = _CLASS_PARTIAL
            reasons.append(
                f"Group span {group_span_ft} ft partially consistent with "
                f"plan sheet length sum {expected_plan_span_ft} ft "
                f"(ratio {consistency_ratio:.3f})."
            )
        else:
            classification = _CLASS_OUT_OF_RANGE
            reasons.append(
                f"Group span {group_span_ft} ft is out of range vs plan "
                f"sheet length sum {expected_plan_span_ft} ft "
                f"(ratio {consistency_ratio:.3f} < {_RATIO_PARTIAL_MIN})."
            )

    # ── Step 5: derive overall confidence ────────────────────────────────────
    if classification == _CLASS_UNCERTAIN:
        overall_confidence = _CONFIDENCE_UNCERTAIN
    else:
        # Start from the worst per-sheet confidence among covered sheets.
        per_sheet_ranks = [
            _CONFIDENCE_RANK.get(sheet_confidence_levels[s], 0)
            for s in covered
        ]
        worst_rank = min(per_sheet_ranks) if per_sheet_ranks else 0
        rank_to_label = {v: k for k, v in _CONFIDENCE_RANK.items()}
        overall_confidence = rank_to_label.get(worst_rank, _CONFIDENCE_UNCERTAIN)

        # Demotions:
        if missing:
            # Any missing topology -> never high.
            if overall_confidence == _CONFIDENCE_HIGH:
                overall_confidence = _CONFIDENCE_MEDIUM
                reasons.append(
                    "Confidence demoted to medium: at least one referenced "
                    "sheet had no topology data."
                )

        if has_reset_boundary:
            # Reset boundaries lower confidence by one step (never lower
            # than low).
            if overall_confidence == _CONFIDENCE_HIGH:
                overall_confidence = _CONFIDENCE_MEDIUM
                reasons.append(
                    "Confidence demoted to medium: covered sheets include a "
                    "slash-form (stationing reset) boundary."
                )
            elif overall_confidence == _CONFIDENCE_MEDIUM:
                overall_confidence = _CONFIDENCE_LOW
                reasons.append(
                    "Confidence demoted to low: covered sheets include a "
                    "slash-form (stationing reset) boundary."
                )

        if "non_contiguous_sheet_references" in ambiguity_flags:
            if overall_confidence == _CONFIDENCE_HIGH:
                overall_confidence = _CONFIDENCE_MEDIUM
                reasons.append(
                    "Confidence demoted to medium: referenced sheets are "
                    "non-contiguous."
                )

    # ── Step 6: derive `would_boost` evidence flag ───────────────────────────
    # Strictly evidence-emission. A future consumer (P5.4) decides whether
    # to convert evidence to score. The flag is true only when:
    #   - classification is contained_consistent or partial_consistent
    #   - confidence is high or medium
    #   - no missing sheets
    #   - no reset boundaries
    #   - reference set is contiguous
    would_boost = (
        classification in (_CLASS_CONTAINED, _CLASS_PARTIAL)
        and overall_confidence in (_CONFIDENCE_HIGH, _CONFIDENCE_MEDIUM)
        and not missing
        and not has_reset_boundary
        and "non_contiguous_sheet_references" not in ambiguity_flags
    )

    # ── Step 7: emit deterministic result ────────────────────────────────────
    return {
        "classification": classification,
        "confidence": overall_confidence,
        "group_span_ft": int(group_span_ft),
        "expected_plan_span_ft": int(expected_plan_span_ft),
        "consistency_ratio": float(consistency_ratio),
        "referenced_sheets": list(referenced_sheets),
        "missing_sheets": sorted(missing),
        "covered_sheets": sorted(covered),
        "sheet_confidence_levels": dict(sheet_confidence_levels),
        "sheet_methods": dict(sheet_methods),
        "has_reset_boundary": bool(has_reset_boundary),
        "ambiguity_flags": sorted(set(ambiguity_flags)),
        "reasons": list(reasons),
        "would_boost": bool(would_boost),
    }
