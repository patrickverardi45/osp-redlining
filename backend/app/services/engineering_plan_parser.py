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

# PI.1 — per-page sheet-label scan. More permissive than _TB_SHEET_RE because
# many engineering sheets carry a bare "SHEET 5" tag without the "of N"
# tail. Used by extract_sheet_labels to produce direct (page, sheet) evidence
# that derive_page_to_sheet_index consumes.
_SHEET_LABEL_RE = re.compile(
    r'\bSHEET\s+(\d{1,4})(?:\s+OF\s+\d{1,4})?\b',
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


def _parse_sheet_from_dwg_filename(fname: Optional[str]) -> Optional[int]:
    """Extract the sheet number embedded in a *.DWG filename, if any.

    Strategy: strip the .DWG suffix and return the LAST digit group as int.
    Returns None when no digit group precedes .DWG, or on any failure.

    Examples:
      'BRENHAM-PH-5_P_3.DWG'  -> 3
      'T-001.DWG'             -> 1
      'MAIN-PLAN.DWG'         -> None
    """
    if not fname or not isinstance(fname, str):
        return None
    try:
        base = re.sub(r"\.dwg\s*$", "", fname, flags=re.IGNORECASE)
        groups = re.findall(r"\d+", base)
        if not groups:
            return None
        return int(groups[-1])
    except Exception:
        return None


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


def extract_sheet_labels(pdf_path: Union[str, Path]) -> List[Dict[str, Any]]:
    """Extract `SHEET N` / `SHEET N OF M` labels from each PDF page.

    Per record: page (1-indexed), sheet_label (int), raw_text.

    This is per-page evidence — multiple matches per page are emitted as
    separate records so derive_page_to_sheet_index can detect agreement
    vs. conflict deterministically. Never raises; returns [] on failure.
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
                for m in _SHEET_LABEL_RE.finditer(text):
                    try:
                        sheet = int(m.group(1))
                    except (ValueError, TypeError):
                        continue
                    if sheet <= 0:
                        continue
                    results.append({
                        "page": page_idx,
                        "sheet_label": sheet,
                        "raw_text": m.group(0),
                    })
        except Exception:
            return results
    return results


# ---------------------------------------------------------------------------
# PI.1 — Page-to-sheet index derivation
# ---------------------------------------------------------------------------
# Pure, deterministic, safe-failure helper that fuses pre-extracted PDF
# evidence into a page -> engineering-sheet mapping. The output keys are
# 1-indexed PDF page numbers; values are int sheet numbers when resolvable
# or None when ambiguous / unresolved.
#
# This helper is consumer-agnostic — no STATE, no FastAPI, no PDF I/O — and
# is NOT wired into any pipeline by this commit. Existing extractors retain
# byte-identical output when called individually; extract_all uses the
# helper internally to enrich records with `source_sheet`.
#
# Derivation rules (layered, deterministic, in evidence-gathering order):
#
#   1. title_block.sheet_number_first_seen — treated as page-1 evidence
#      (best available anchor when no per-page scan is provided).
#   2. sheet_labels — direct (page, sheet) evidence from per-page text scan.
#   3. drawing_index — per-record file_name is parsed for its trailing
#      sheet number; the record's `page` becomes evidence for that sheet.
#      (Only useful when each page references its OWN drawing; an index
#      page listing many drawings becomes a conflict cluster on that page
#      and is correctly emitted as None.)
#   4. matchline records — currently NOT used as page-to-sheet evidence
#      because their extracted shape only carries the TARGET sheet
#      (references_sheet), not the source. Reserved for a future phase.
#   5. Conflict resolution: a page with multiple disagreeing candidates
#      maps to None. A page with a single candidate maps to that sheet.
#      Pages with no evidence are simply absent from the result.
#
# All inputs are tolerant: None / wrong-type / missing-keys never raise.
# Inputs are not mutated.
# ---------------------------------------------------------------------------

def derive_page_to_sheet_index(
    metadata: Optional[Dict[str, Any]],
    title_block: Optional[Dict[str, Any]],
    drawing_index: Optional[List[Dict[str, Any]]],
    matchlines: Optional[List[Dict[str, Any]]],
    sheet_labels: Optional[List[Dict[str, Any]]] = None,
) -> Dict[int, Optional[int]]:
    """Fuse pre-extracted evidence into a {page: sheet_or_None} index.

    Pure function. Never raises. Never mutates inputs. See the section
    header above for the full input contract and derivation rules.
    """
    evidence: Dict[int, set] = {}

    # ── Rule 1: title_block anchor (best applied to page 1) ─────────────────
    if isinstance(title_block, dict):
        try:
            anchor = _coerce_nonneg_int(title_block.get("sheet_number_first_seen"))
            if anchor is not None and anchor > 0:
                evidence.setdefault(1, set()).add(int(anchor))
        except Exception:
            pass

    # ── Rule 2: explicit sheet labels per page ──────────────────────────────
    if isinstance(sheet_labels, list):
        for rec in sheet_labels:
            try:
                if not isinstance(rec, dict):
                    continue
                page = _coerce_nonneg_int(rec.get("page"))
                sheet = _coerce_nonneg_int(rec.get("sheet_label"))
                if page is None or page <= 0:
                    continue
                if sheet is None or sheet <= 0:
                    continue
                evidence.setdefault(int(page), set()).add(int(sheet))
            except Exception:
                continue

    # ── Rule 3: drawing_index file_name parsing ─────────────────────────────
    if isinstance(drawing_index, list):
        for rec in drawing_index:
            try:
                if not isinstance(rec, dict):
                    continue
                page = _coerce_nonneg_int(rec.get("page"))
                if page is None or page <= 0:
                    continue
                fname = rec.get("file_name")
                sheet = _parse_sheet_from_dwg_filename(fname if isinstance(fname, str) else None)
                if sheet is None or sheet <= 0:
                    continue
                evidence.setdefault(int(page), set()).add(int(sheet))
            except Exception:
                continue

    # ── Rule 4: matchlines reserved (no source-sheet field today) ───────────
    # Intentionally a no-op. metadata input is accepted for forward-compat.
    _ = metadata
    _ = matchlines

    # ── Rule 5: resolve per-page evidence ───────────────────────────────────
    result: Dict[int, Optional[int]] = {}
    for page, candidates in evidence.items():
        if len(candidates) == 1:
            try:
                result[int(page)] = int(next(iter(candidates)))
            except Exception:
                result[int(page)] = None
        else:
            # Conflicting candidates -> emit None deterministically.
            result[int(page)] = None
    return result


def _apply_source_sheet(
    records: List[Dict[str, Any]],
    page_to_sheet: Dict[int, Optional[int]],
) -> List[Dict[str, Any]]:
    """Return a new list of records with `source_sheet` set from the
    page-to-sheet map. Never mutates the input list or its dicts.

    Records that already carry a `source_sheet` value are NOT overwritten —
    the helper respects upstream-provided values. Records lacking a usable
    `page` integer receive `source_sheet=None`.
    """
    out: List[Dict[str, Any]] = []
    if not isinstance(records, list):
        return out
    safe_map = page_to_sheet if isinstance(page_to_sheet, dict) else {}
    for rec in records:
        if not isinstance(rec, dict):
            out.append(rec)
            continue
        new_rec = dict(rec)
        existing = _coerce_nonneg_int(new_rec.get("source_sheet"))
        if existing is not None:
            new_rec["source_sheet"] = int(existing)
        else:
            page = _coerce_nonneg_int(new_rec.get("page"))
            sheet = safe_map.get(int(page)) if page is not None else None
            new_rec["source_sheet"] = sheet if isinstance(sheet, int) else None
        out.append(new_rec)
    return out


def extract_all(pdf_path: Union[str, Path]) -> Dict[str, Any]:
    """Convenience: run every extractor. Each is independently safe-fail.

    Records in the six list-valued sections are enriched with a
    `source_sheet` field derived via derive_page_to_sheet_index. AP and
    splice records additionally carry the PI.2 co-location fields
    (`station_ft`, `station_source`, `station_confidence`,
    `station_reason`, `station_distance_chars`) derived via
    extract_anchor_positions + derive_anchor_station_colocations.

    Records in the original extractor calls remain byte-identical when
    the extractors are invoked individually; the enrichment is applied
    only here, at the orchestration layer.
    """
    metadata = extract_metadata(pdf_path)
    title_block = extract_title_block(pdf_path)
    matchlines = extract_matchlines(pdf_path)
    station_callouts = extract_station_callouts(pdf_path)
    ap_ids = extract_ap_ids(pdf_path)
    splice_ids = extract_splice_ids(pdf_path)
    drawing_index = extract_drawing_index(pdf_path)
    fieldwire_table = extract_fieldwire_table(pdf_path)
    sheet_labels = extract_sheet_labels(pdf_path)

    try:
        page_to_sheet = derive_page_to_sheet_index(
            metadata, title_block, drawing_index, matchlines,
            sheet_labels=sheet_labels,
        )
    except Exception:
        page_to_sheet = {}

    # PI.1: page → sheet enrichment on every list record.
    ap_ids_pi1 = _apply_source_sheet(ap_ids, page_to_sheet)
    splice_ids_pi1 = _apply_source_sheet(splice_ids, page_to_sheet)

    # PI.2: anchor → station co-location on ap and splice records only.
    anchor_positions = extract_anchor_positions(pdf_path)
    try:
        colocations = derive_anchor_station_colocations(anchor_positions)
    except Exception:
        colocations = []
    ap_ids_pi2 = _apply_station_colocation(
        ap_ids_pi1, colocations, "ap", "ap_id_canonical",
    )
    splice_ids_pi2 = _apply_station_colocation(
        splice_ids_pi1, colocations, "splice", "splice_id_canonical",
    )

    return {
        "metadata":         metadata,
        "title_block":      title_block,
        "matchlines":       _apply_source_sheet(matchlines, page_to_sheet),
        "station_callouts": _apply_source_sheet(station_callouts, page_to_sheet),
        "ap_ids":           ap_ids_pi2,
        "splice_ids":       splice_ids_pi2,
        "drawing_index":    _apply_source_sheet(drawing_index, page_to_sheet),
        "fieldwire_table":  _apply_source_sheet(fieldwire_table, page_to_sheet),
    }


# ---------------------------------------------------------------------------
# PI.2 — Anchor → station co-location
# ---------------------------------------------------------------------------
# Pure, deterministic, safe-failure helpers that associate AP and splice
# anchor records with nearby station callouts on the same engineering
# sheet/page when the PDF text supports it. The signal class is strictly
# same-page text-character distance; cross-page reasoning is refused.
#
# Public surface:
#   - extract_anchor_positions(pdf_path)
#     Re-scans each PDF page and emits positional anchor + station
#     records (carrying text_start / text_end alongside the canonical
#     id / station_ft). The existing extractors strip positional
#     metadata on purpose; this one preserves it for co-location use.
#
#   - derive_anchor_station_colocations(anchor_positions)
#     Pure function. For each ap/splice anchor in the input, finds the
#     nearest qualifying station on the same page by text-character
#     distance. Equation-kind stations are skipped (foreign stationing
#     system). Ties with disagreeing station_ft are refused.
#
#   - _apply_station_colocation(records, colocations, anchor_type,
#                                canonical_key)
#     Pure function. Enriches a list of AP or splice records with the
#     five PI.2 fields by joining on (page, canonical) keys.
#
# Distance bands (deterministic, inclusive upper bounds):
#   - tight:     [0, _COLOCATION_TIGHT_MAX]    -> confidence high
#   - proximity: (TIGHT_MAX, _COLOCATION_MEDIUM_MAX]  -> confidence medium
#   - loose:     (MEDIUM_MAX, _COLOCATION_LOOSE_MAX]  -> confidence low
#   - refusal:   > _COLOCATION_LOOSE_MAX
#
# Refusal cascade emits station_ft=None, station_source="none",
# station_confidence="uncertain", with an attributable station_reason.
# See the design and implementation plan in
# wiki/pi-2-anchor-station-colocation-design.md and
# wiki/pi-2-implementation-plan.md.
#
# This module remains consumer-agnostic. No STATE, no FastAPI, no
# imports from main.py. The PI.2 enrichment fields appear only on
# records returned by extract_all; individual extractors stay
# byte-identical to pre-PI.2.
# ---------------------------------------------------------------------------

_COLOCATION_TIGHT_MAX: int = 30
_COLOCATION_MEDIUM_MAX: int = 80
_COLOCATION_LOOSE_MAX: int = 150

_COLOCATION_KIND_AP: str = "ap"
_COLOCATION_KIND_SPLICE: str = "splice"
_COLOCATION_KIND_STATION_SINGLE: str = "station_single"
_COLOCATION_KIND_STATION_RANGE: str = "station_range"
_COLOCATION_KIND_STATION_EQUATION: str = "station_equation"

_COLOCATION_SOURCE_TIGHT: str = "same_page_text_proximity_tight"
_COLOCATION_SOURCE_PROXIMITY: str = "same_page_text_proximity"
_COLOCATION_SOURCE_LOOSE: str = "same_page_text_proximity_loose"
_COLOCATION_SOURCE_NONE: str = "none"
_COLOCATION_SOURCE_UPSTREAM: str = "upstream_provided"

_COLOCATION_CONF_HIGH: str = "high"
_COLOCATION_CONF_MEDIUM: str = "medium"
_COLOCATION_CONF_LOW: str = "low"
_COLOCATION_CONF_UNCERTAIN: str = "uncertain"

_COLOCATION_AMBIGUITY_TIED_DISTANCE: str = "tied_nearest_station_distance"
_COLOCATION_AMBIGUITY_ALL_EQUATIONS: str = "page_has_only_equation_stations"
_COLOCATION_AMBIGUITY_NO_STATIONS: str = "page_has_no_station_callouts"
_COLOCATION_AMBIGUITY_OUT_OF_WINDOW: str = "nearest_station_out_of_window"

_COLOCATION_STATION_KIND_NAME: Dict[str, str] = {
    _COLOCATION_KIND_STATION_SINGLE: "single",
    _COLOCATION_KIND_STATION_RANGE: "range",
}


def extract_anchor_positions(
    pdf_path: Union[str, Path],
) -> List[Dict[str, Any]]:
    """Re-scan each PDF page and emit positional anchor + station records.

    See section header for the full output contract. Returns [] on any
    failure; never raises.
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

                # Stations first, so the station-single pass can avoid
                # double-counting ranges and equations via `consumed`.
                consumed: List[tuple] = []

                for m in _STATION_RANGE_RE.finditer(text):
                    s1n, s1p, s2n, s2p = (int(g) for g in m.groups())
                    results.append({
                        "page": page_idx,
                        "kind": _COLOCATION_KIND_STATION_RANGE,
                        "canonical": None,
                        "station_ft": _station_to_ft(s1n, s1p),
                        "second_station_ft": _station_to_ft(s2n, s2p),
                        "text_start": m.start(),
                        "text_end": m.end(),
                        "raw_text": m.group(0),
                    })
                    consumed.append((m.start(), m.end()))

                for m in _STATION_EQ_RE.finditer(text):
                    s1n, s1p, s2n, s2p = (int(g) for g in m.groups())
                    results.append({
                        "page": page_idx,
                        "kind": _COLOCATION_KIND_STATION_EQUATION,
                        "canonical": None,
                        "station_ft": _station_to_ft(s1n, s1p),
                        "second_station_ft": _station_to_ft(s2n, s2p),
                        "text_start": m.start(),
                        "text_end": m.end(),
                        "raw_text": m.group(0),
                    })
                    consumed.append((m.start(), m.end()))

                for m in _STATION_RE.finditer(text):
                    if any(s <= m.start() < e for s, e in consumed):
                        continue
                    sn, sp = int(m.group(1)), int(m.group(2))
                    results.append({
                        "page": page_idx,
                        "kind": _COLOCATION_KIND_STATION_SINGLE,
                        "canonical": None,
                        "station_ft": _station_to_ft(sn, sp),
                        "second_station_ft": None,
                        "text_start": m.start(),
                        "text_end": m.end(),
                        "raw_text": m.group(0),
                    })

                for m in _AP_ID_RE.finditer(text):
                    raw = m.group(0)
                    canonical = _canonicalize_ap(raw)
                    if not canonical:
                        continue
                    results.append({
                        "page": page_idx,
                        "kind": _COLOCATION_KIND_AP,
                        "canonical": canonical,
                        "station_ft": None,
                        "second_station_ft": None,
                        "text_start": m.start(),
                        "text_end": m.end(),
                        "raw_text": raw,
                    })

                for m in _SPLICE_RE.finditer(text):
                    raw = m.group(0)
                    canonical = _canonicalize_splice(raw)
                    if not canonical:
                        continue
                    results.append({
                        "page": page_idx,
                        "kind": _COLOCATION_KIND_SPLICE,
                        "canonical": canonical,
                        "station_ft": None,
                        "second_station_ft": None,
                        "text_start": m.start(),
                        "text_end": m.end(),
                        "raw_text": raw,
                    })
        except Exception:
            return results
    return results


def _colocation_distance(anchor: Dict[str, Any], station: Dict[str, Any]) -> Optional[int]:
    """Gap between the closest edges of two text matches. Returns None
    on any malformed positional fields. Floors at zero so touching or
    overlapping matches map to distance 0.
    """
    try:
        ats = anchor.get("text_start")
        ate = anchor.get("text_end")
        sts = station.get("text_start")
        ste = station.get("text_end")
        if not (isinstance(ats, int) and isinstance(ate, int)
                and isinstance(sts, int) and isinstance(ste, int)):
            return None
        return max(0, min(abs(ats - ste), abs(sts - ate)))
    except Exception:
        return None


def _colocation_refusal(
    *,
    page: int,
    anchor_type: str,
    canonical: str,
    anchor_ts: int,
    anchor_te: int,
    reason: str,
    ambiguity_flag: str,
    distance: Optional[int] = None,
) -> Dict[str, Any]:
    """Build a refusal-shaped co-location record. Attributable and
    deterministic; never raises.
    """
    return {
        "page": int(page),
        "anchor_type": str(anchor_type),
        "anchor_canonical": str(canonical),
        "anchor_text_start": int(anchor_ts),
        "anchor_text_end": int(anchor_te),
        "station_ft": None,
        "station_kind": None,
        "station_source": _COLOCATION_SOURCE_NONE,
        "station_confidence": _COLOCATION_CONF_UNCERTAIN,
        "station_reason": str(reason),
        "station_distance_chars": int(distance) if distance is not None else None,
        "ambiguity_flags": [str(ambiguity_flag)],
    }


def derive_anchor_station_colocations(
    anchor_positions: Optional[List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    """For each ap/splice anchor, find the nearest qualifying station on
    the same page by text-character distance.

    Pure function. Never raises. Never mutates inputs.
    """
    if not isinstance(anchor_positions, list):
        return []

    by_page: Dict[int, List[Dict[str, Any]]] = {}
    for rec in anchor_positions:
        try:
            if not isinstance(rec, dict):
                continue
            page = _coerce_nonneg_int(rec.get("page"))
            if page is None:
                continue
            by_page.setdefault(int(page), []).append(rec)
        except Exception:
            continue

    results: List[Dict[str, Any]] = []

    for rec in anchor_positions:
        try:
            if not isinstance(rec, dict):
                continue
            kind = rec.get("kind")
            if kind not in (_COLOCATION_KIND_AP, _COLOCATION_KIND_SPLICE):
                continue

            ts = rec.get("text_start")
            te = rec.get("text_end")
            page = _coerce_nonneg_int(rec.get("page"))
            canonical = rec.get("canonical")
            if not isinstance(ts, int) or not isinstance(te, int):
                continue
            if page is None or not isinstance(canonical, str) or not canonical:
                continue

            anchor_type = "ap" if kind == _COLOCATION_KIND_AP else "splice"

            same_page = by_page.get(int(page), [])
            non_equation: List[Dict[str, Any]] = []
            equation: List[Dict[str, Any]] = []
            for s in same_page:
                s_kind = s.get("kind")
                if s_kind in (_COLOCATION_KIND_STATION_SINGLE, _COLOCATION_KIND_STATION_RANGE):
                    non_equation.append(s)
                elif s_kind == _COLOCATION_KIND_STATION_EQUATION:
                    equation.append(s)

            if not non_equation and not equation:
                results.append(_colocation_refusal(
                    page=int(page), anchor_type=anchor_type, canonical=canonical,
                    anchor_ts=ts, anchor_te=te,
                    reason="page has no station callouts",
                    ambiguity_flag=_COLOCATION_AMBIGUITY_NO_STATIONS,
                ))
                continue

            if not non_equation:
                results.append(_colocation_refusal(
                    page=int(page), anchor_type=anchor_type, canonical=canonical,
                    anchor_ts=ts, anchor_te=te,
                    reason="page has only equation-kind stations (foreign stationing system)",
                    ambiguity_flag=_COLOCATION_AMBIGUITY_ALL_EQUATIONS,
                ))
                continue

            best: Optional[int] = None
            candidates: List[Dict[str, Any]] = []
            for s in non_equation:
                d = _colocation_distance(rec, s)
                if d is None:
                    continue
                if best is None or d < best:
                    best = d
                    candidates = [s]
                elif d == best:
                    candidates.append(s)

            if best is None:
                results.append(_colocation_refusal(
                    page=int(page), anchor_type=anchor_type, canonical=canonical,
                    anchor_ts=ts, anchor_te=te,
                    reason="no usable station candidates (malformed positions)",
                    ambiguity_flag=_COLOCATION_AMBIGUITY_NO_STATIONS,
                ))
                continue

            if best > _COLOCATION_LOOSE_MAX:
                results.append(_colocation_refusal(
                    page=int(page), anchor_type=anchor_type, canonical=canonical,
                    anchor_ts=ts, anchor_te=te,
                    reason=(f"nearest station out of window "
                            f"(distance {best} > {_COLOCATION_LOOSE_MAX})"),
                    ambiguity_flag=_COLOCATION_AMBIGUITY_OUT_OF_WINDOW,
                    distance=best,
                ))
                continue

            # Tied: refuse if candidates disagree on station_ft; accept
            # if they agree (pick deterministically by text_start, then
            # text_end).
            station_fts: set = set()
            for s in candidates:
                sft = _coerce_nonneg_int(s.get("station_ft"))
                if sft is not None:
                    station_fts.add(int(sft))

            if not station_fts:
                results.append(_colocation_refusal(
                    page=int(page), anchor_type=anchor_type, canonical=canonical,
                    anchor_ts=ts, anchor_te=te,
                    reason="nearest candidates lack a usable station_ft",
                    ambiguity_flag=_COLOCATION_AMBIGUITY_NO_STATIONS,
                    distance=best,
                ))
                continue

            if len(station_fts) >= 2:
                results.append(_colocation_refusal(
                    page=int(page), anchor_type=anchor_type, canonical=canonical,
                    anchor_ts=ts, anchor_te=te,
                    reason=(f"tied nearest stations disagree on station_ft "
                            f"(distance {best}, values {sorted(station_fts)})"),
                    ambiguity_flag=_COLOCATION_AMBIGUITY_TIED_DISTANCE,
                    distance=best,
                ))
                continue

            winner = sorted(
                candidates,
                key=lambda s: (
                    int(s.get("text_start") or 0),
                    int(s.get("text_end") or 0),
                ),
            )[0]
            winner_station_ft = _coerce_nonneg_int(winner.get("station_ft"))
            winner_kind = winner.get("kind")
            station_kind_name = _COLOCATION_STATION_KIND_NAME.get(
                winner_kind, "single",
            )

            if best <= _COLOCATION_TIGHT_MAX:
                source = _COLOCATION_SOURCE_TIGHT
                confidence = _COLOCATION_CONF_HIGH
            elif best <= _COLOCATION_MEDIUM_MAX:
                source = _COLOCATION_SOURCE_PROXIMITY
                confidence = _COLOCATION_CONF_MEDIUM
            else:
                source = _COLOCATION_SOURCE_LOOSE
                confidence = _COLOCATION_CONF_LOW

            station_token = str(winner.get("raw_text") or f"STA {winner_station_ft}")
            if station_kind_name == "range":
                reason = (
                    f"matched {station_token} at {best} chars text distance "
                    f"(range; using start)"
                )
            else:
                reason = (
                    f"matched {station_token} at {best} chars text distance"
                )

            results.append({
                "page": int(page),
                "anchor_type": anchor_type,
                "anchor_canonical": canonical,
                "anchor_text_start": int(ts),
                "anchor_text_end": int(te),
                "station_ft": int(winner_station_ft),
                "station_kind": station_kind_name,
                "station_source": source,
                "station_confidence": confidence,
                "station_reason": reason,
                "station_distance_chars": int(best),
                "ambiguity_flags": [],
            })
        except Exception:
            continue

    return results


def _apply_station_colocation(
    records: Optional[List[Dict[str, Any]]],
    colocations: Optional[List[Dict[str, Any]]],
    anchor_type: str,
    canonical_key: str,
) -> List[Dict[str, Any]]:
    """Return a fresh list of records, each enriched with the five PI.2
    station_* fields. Pure. Never raises. Never mutates inputs.

    Match join: (record.page, record[canonical_key]) against
    (colocation.page, colocation.anchor_canonical) filtered by
    colocation.anchor_type == anchor_type.

    Records carrying a pre-existing station_ft (upstream-provided) are
    preserved; PI.2 does NOT overwrite them. The metadata fields are
    set to upstream-indicator defaults so downstream consumers can tell
    the value came from outside PI.2.
    """
    if not isinstance(records, list):
        return []

    lookup: Dict[tuple, Dict[str, Any]] = {}
    if isinstance(colocations, list):
        for c in colocations:
            try:
                if not isinstance(c, dict):
                    continue
                if c.get("anchor_type") != anchor_type:
                    continue
                page = _coerce_nonneg_int(c.get("page"))
                canon = c.get("anchor_canonical")
                if page is None or not isinstance(canon, str):
                    continue
                lookup[(int(page), canon)] = c
            except Exception:
                continue

    out: List[Dict[str, Any]] = []
    for rec in records:
        if not isinstance(rec, dict):
            out.append(rec)
            continue
        new_rec = dict(rec)

        existing_station_ft = _coerce_nonneg_int(new_rec.get("station_ft"))
        if existing_station_ft is not None:
            new_rec["station_ft"] = int(existing_station_ft)
            new_rec.setdefault("station_source", _COLOCATION_SOURCE_UPSTREAM)
            new_rec.setdefault("station_confidence", _COLOCATION_CONF_UNCERTAIN)
            new_rec.setdefault(
                "station_reason",
                "station_ft pre-set upstream; co-location not applied",
            )
            new_rec.setdefault("station_distance_chars", None)
            out.append(new_rec)
            continue

        try:
            page = _coerce_nonneg_int(new_rec.get("page"))
            canonical_val = new_rec.get(canonical_key)
        except Exception:
            page = None
            canonical_val = None

        if page is None or not isinstance(canonical_val, str) or not canonical_val:
            new_rec["station_ft"] = None
            new_rec["station_source"] = _COLOCATION_SOURCE_NONE
            new_rec["station_confidence"] = _COLOCATION_CONF_UNCERTAIN
            new_rec["station_reason"] = "no co-location (missing page or canonical)"
            new_rec["station_distance_chars"] = None
            out.append(new_rec)
            continue

        c = lookup.get((int(page), canonical_val))
        if c is None:
            new_rec["station_ft"] = None
            new_rec["station_source"] = _COLOCATION_SOURCE_NONE
            new_rec["station_confidence"] = _COLOCATION_CONF_UNCERTAIN
            new_rec["station_reason"] = "no co-location"
            new_rec["station_distance_chars"] = None
            out.append(new_rec)
            continue

        sft = c.get("station_ft")
        new_rec["station_ft"] = int(sft) if isinstance(sft, int) else None
        new_rec["station_source"] = str(c.get("station_source") or _COLOCATION_SOURCE_NONE)
        new_rec["station_confidence"] = str(c.get("station_confidence") or _COLOCATION_CONF_UNCERTAIN)
        new_rec["station_reason"] = str(c.get("station_reason") or "")
        dc = c.get("station_distance_chars")
        new_rec["station_distance_chars"] = int(dc) if isinstance(dc, int) else None
        out.append(new_rec)

    return out


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


# ---------------------------------------------------------------------------
# P5.4 — Bounded footage-range boost computation
# ---------------------------------------------------------------------------
# Pure, deterministic helper that COMPUTES a hypothetical A3 footage boost
# over a ranking list. Returns (new_rankings, meta) without mutating inputs.
#
# This function is consumer-agnostic — it does not import main.py, does not
# read STATE, and is not wired into any pipeline by this commit.
#
# The compute function does NOT decide whether the boost is applied —
# callers do. In SHADOW mode the caller discards new_rankings and uses
# meta for diagnostic emission only. In a future ACTIVE mode (not P5.4
# shadow) the caller would adopt new_rankings as the post-boost state.
#
# Anchors are evidence, NOT authority:
#   - never selects a route
#   - never modifies its inputs
#   - never inflates evidence confidence
#   - never bridges score gaps larger than the configured reorder_gap
#   - boost magnitude is hard-capped per entry
#
# Conditions under which boost is NOT applied (meta.applied = False):
#   - rankings is None / empty
#   - sheet_origins is None / empty
#   - len(rankings) <= 1 (no ambiguity to resolve)
#   - evaluate_footage_range_containment.would_boost is False
#   - covered_sheets resolves to no hint_route_ids via print_to_sheets
#   - no ranking entry's route_id is in the resolved hint_route_ids
#   - top-2 score gap > reorder_gap (gap too wide for bounded boost)
#
# All hard-stops emit an attributable `skipped_reason`.
# ---------------------------------------------------------------------------

_FOOTAGE_BOOST_MAX_PER_ENTRY: float = 0.02
_FOOTAGE_BOOST_REORDER_GAP: float = 0.10


def _ranking_score(entry: Dict[str, Any]) -> float:
    """Read the score from a ranking entry, preferring combined_score
    over score. Returns 0.0 on any failure.
    """
    try:
        val = entry.get("combined_score")
        if val is None:
            val = entry.get("score")
        if val is None:
            return 0.0
        return float(val)
    except Exception:
        return 0.0


def _ranking_route_id(entry: Dict[str, Any]) -> str:
    try:
        return str(entry.get("route_id") or "").strip()
    except Exception:
        return ""


def _resolve_hint_route_ids(
    covered_sheets: Sequence[int],
    sheet_to_route_ids: Optional[Mapping[Any, Any]],
) -> List[str]:
    """For each covered sheet, look up the route_ids that map to it via
    `sheet_to_route_ids`. Deduplicated, preserves first-seen order.
    Safe-failure: returns [] on any error.

    Expected shape: {sheet_int: [route_id_str, ...]}.
    """
    if not covered_sheets or not sheet_to_route_ids:
        return []
    out: List[str] = []
    try:
        for sheet in covered_sheets:
            try:
                key = _coerce_nonneg_int(sheet)
                if key is None:
                    continue
                rids = sheet_to_route_ids.get(int(key))
                if not rids:
                    continue
                try:
                    for rid in rids:
                        s = str(rid or "").strip()
                        if s and s not in out:
                            out.append(s)
                except TypeError:
                    # rids isn't iterable — tolerate a single string value.
                    s = str(rids or "").strip()
                    if s and s not in out:
                        out.append(s)
            except Exception:
                continue
    except Exception:
        return []
    return out


def compute_plan_aware_footage_boost(
    rankings: Optional[List[Dict[str, Any]]],
    normalized_group: Optional[Dict[str, Any]],
    sheet_origins: Optional[Dict[int, Dict[str, Any]]],
    print_to_sheets: Optional[Mapping[Any, Any]] = None,
    sheet_to_route_ids: Optional[Mapping[Any, Any]] = None,
    boost_per_entry: float = _FOOTAGE_BOOST_MAX_PER_ENTRY,
    reorder_gap: float = _FOOTAGE_BOOST_REORDER_GAP,
) -> "tuple[List[Dict[str, Any]], Dict[str, Any]]":
    """Compute the hypothetical A3 footage boost over a ranking list.

    Returns (new_rankings, meta). new_rankings is always a fresh list of
    fresh dicts (no shared mutation with inputs). meta describes the
    decision in full attributable detail.

    Never raises on malformed input. Inputs are not mutated.
    """
    # ── Step 0: defensive input handling ─────────────────────────────────────
    try:
        rankings_in = list(rankings or [])
    except Exception:
        rankings_in = []
    rankings_copy = [dict(entry) if isinstance(entry, dict) else {} for entry in rankings_in]

    def _no_boost(reason: str, *, evidence: Optional[Dict[str, Any]] = None,
                  extra: Optional[Dict[str, Any]] = None) -> "tuple[List[Dict[str, Any]], Dict[str, Any]]":
        meta: Dict[str, Any] = {
            "applied": False,
            "skipped_reason": reason,
            "boost_per_entry": float(boost_per_entry),
            "reorder_gap": float(reorder_gap),
            "evidence": dict(evidence or {}),
            "hint_route_ids": [],
            "boosted_route_ids": [],
            "would_reorder": False,
            "top_score_gap_before": 0.0,
            "top_score_gap_after": 0.0,
            "top_route_id_before": _ranking_route_id(rankings_copy[0]) if rankings_copy else "",
            "top_route_id_after": _ranking_route_id(rankings_copy[0]) if rankings_copy else "",
            "per_ranking_deltas": [
                {
                    "route_id": _ranking_route_id(e),
                    "score_before": _ranking_score(e),
                    "score_after": _ranking_score(e),
                    "boost": 0.0,
                    "was_eligible": False,
                }
                for e in rankings_copy
            ],
        }
        if extra:
            for k, v in extra.items():
                meta.setdefault(k, v)
        return rankings_copy, meta

    if not rankings_copy:
        return _no_boost("no_rankings")
    if len(rankings_copy) <= 1:
        return _no_boost("single_candidate_no_ambiguity")
    if not isinstance(sheet_origins, dict) or not sheet_origins:
        return _no_boost("no_topology_available")

    # ── Step 1: evaluate P5.2 evidence ───────────────────────────────────────
    try:
        evidence = evaluate_footage_range_containment(
            normalized_group, sheet_origins, print_to_sheets
        )
    except Exception:
        return _no_boost("evidence_evaluation_error")

    if not evidence.get("would_boost"):
        return _no_boost("p52_would_boost_false", evidence=evidence)

    # ── Step 2: resolve hint route_ids from covered_sheets ───────────────────
    covered_sheets = list(evidence.get("covered_sheets") or [])
    hint_route_ids = _resolve_hint_route_ids(covered_sheets, sheet_to_route_ids)
    if not hint_route_ids:
        return _no_boost("no_hint_route_ids_for_covered_sheets", evidence=evidence)

    # ── Step 3: identify eligible rankings ───────────────────────────────────
    hint_set = set(hint_route_ids)
    eligible_indices: List[int] = []
    for idx, entry in enumerate(rankings_copy):
        if _ranking_route_id(entry) in hint_set:
            eligible_indices.append(idx)
    if not eligible_indices:
        return _no_boost("no_eligible_route_in_rankings",
                         evidence=evidence,
                         extra={"hint_route_ids": list(hint_route_ids)})

    # ── Step 4: gap-too-wide gate ────────────────────────────────────────────
    top_score = _ranking_score(rankings_copy[0])
    second_score = _ranking_score(rankings_copy[1])
    gap_before = round(top_score - second_score, 6)

    if gap_before > float(reorder_gap):
        # Active mode would skip; shadow surfaces this as "would not fire".
        meta = {
            "applied": False,
            "skipped_reason": "gap_too_wide_to_reorder",
            "boost_per_entry": float(boost_per_entry),
            "reorder_gap": float(reorder_gap),
            "evidence": dict(evidence),
            "hint_route_ids": list(hint_route_ids),
            "boosted_route_ids": [],
            "would_reorder": False,
            "top_score_gap_before": gap_before,
            "top_score_gap_after": gap_before,
            "top_route_id_before": _ranking_route_id(rankings_copy[0]),
            "top_route_id_after": _ranking_route_id(rankings_copy[0]),
            "per_ranking_deltas": [
                {
                    "route_id": _ranking_route_id(e),
                    "score_before": _ranking_score(e),
                    "score_after": _ranking_score(e),
                    "boost": 0.0,
                    "was_eligible": _ranking_route_id(e) in hint_set,
                }
                for e in rankings_copy
            ],
        }
        return rankings_copy, meta

    # ── Step 5: apply bounded boost ──────────────────────────────────────────
    bp = float(boost_per_entry)
    if bp < 0.0:
        bp = 0.0
    boosted: List[Dict[str, Any]] = []
    deltas: List[Dict[str, Any]] = []
    boosted_route_ids: List[str] = []
    for idx, entry in enumerate(rankings_copy):
        rid = _ranking_route_id(entry)
        score_before = _ranking_score(entry)
        is_eligible = rid in hint_set
        new_entry = dict(entry)
        if is_eligible:
            score_after = round(min(1.0, score_before + bp), 6)
            applied_boost = round(score_after - score_before, 6)
            new_entry["combined_score"] = score_after
            new_entry["score"] = score_after
            new_entry["plan_footage_pre_boost_score"] = round(score_before, 6)
            new_entry["plan_footage_post_boost_score"] = score_after
            new_entry["plan_footage_bias"] = {
                "applied": True,
                "boost": applied_boost,
                "classification": str(evidence.get("classification") or ""),
                "confidence": str(evidence.get("confidence") or ""),
                "covered_sheets": list(covered_sheets),
                "evidence_ratio": float(evidence.get("consistency_ratio") or 0.0),
            }
            if rid and rid not in boosted_route_ids:
                boosted_route_ids.append(rid)
        else:
            score_after = score_before
            applied_boost = 0.0
            new_entry.setdefault("plan_footage_bias", {"applied": False, "boost": 0.0})
        boosted.append(new_entry)
        deltas.append({
            "route_id": rid,
            "score_before": round(score_before, 6),
            "score_after": round(score_after, 6),
            "boost": applied_boost,
            "was_eligible": bool(is_eligible),
        })

    # Stable sort matching the existing _plan_aware_ranking_boost tie-break.
    boosted.sort(key=lambda item: (
        -_ranking_score(item),
        float(item.get("length_gap_ft") or 0.0),
        float(item.get("route_length_ft") or 0.0),
        str(item.get("route_name") or ""),
    ))

    top_after = _ranking_score(boosted[0])
    second_after = _ranking_score(boosted[1]) if len(boosted) > 1 else top_after
    gap_after = round(top_after - second_after, 6)

    top_before_rid = _ranking_route_id(rankings_copy[0])
    top_after_rid = _ranking_route_id(boosted[0])
    would_reorder = top_before_rid != top_after_rid

    meta = {
        "applied": True,
        "skipped_reason": None,
        "boost_per_entry": bp,
        "reorder_gap": float(reorder_gap),
        "evidence": dict(evidence),
        "hint_route_ids": list(hint_route_ids),
        "boosted_route_ids": list(boosted_route_ids),
        "would_reorder": bool(would_reorder),
        "top_score_gap_before": gap_before,
        "top_score_gap_after": gap_after,
        "top_route_id_before": top_before_rid,
        "top_route_id_after": top_after_rid,
        "per_ranking_deltas": deltas,
    }
    return boosted, meta


# ---------------------------------------------------------------------------
# P5.2B — Localized sub-extent plausibility evaluation
# ---------------------------------------------------------------------------
# Pure, deterministic, safe-failure helper that evaluates whether a bore-log
# group's measured span plausibly fits inside SOME contiguous sub-window of
# the engineering-plan region the group references.
#
# This is the SUB-EXTENT counterpart to evaluate_footage_range_containment
# (P5.2). P5.2 asks "does the span equal the full plan-sheet extent?";
# P5.2B asks "does the span fit inside some deterministic sub-extent?" —
# a strictly weaker question, intentionally.
#
# This helper is consumer-agnostic — no STATE, no FastAPI, no PDF I/O, no
# imports from main.py — and is NOT wired into any pipeline by this commit.
#
# Anchors are evidence, NOT authority:
#   - never picks a route
#   - never modifies its inputs
#   - never auto-resolves ambiguity
#   - emits a `would_boost` flag for diagnostic use only; a future P5.4B
#     consumer decides whether to convert evidence to a score boost.
#
# Sub-extents are plausibility, NOT certainty:
#   - a plausible fit is bounded evidence, not engineering truth
#   - corroborating anchors (matchline crossings on covered sheets) are
#     required for the strongest classification
#   - lack of corroboration demotes to weak, never to refusal
#
# Input contracts:
#
#   normalized_group:
#     - span_ft: int or float, > 0. Required; absent triggers no_data.
#     - print_tokens: list of strings or ints. May be empty.
#
#   sheet_origins:
#     - The dict returned by derive_sheet_station_origins, keyed by
#       integer sheet number.
#
#   print_to_sheets (optional):
#     - Mapping print_token -> iterable of int sheet numbers.
#
#   chain_adjacency (optional):
#     - Mapping int sheet -> iterable of int adjacent sheets.
#     - When absent, contiguity falls back to a numeric-consecutive
#       heuristic AND multi-sheet candidates carry the
#       chain_adjacency_unverified flag (cannot achieve fit_strong).
#
#   anchor_hints (optional):
#     - Dict with the following inspected keys (all optional):
#       - matchline_crossings: iterable[int sheet]
#       - ap_tokens: iterable[str]       (accepted; not used for corroboration)
#       - splice_ids: iterable[str]      (accepted; not used for corroboration)
#       - structure_ids: iterable[str]   (accepted; not used for corroboration)
#     - Only matchline_crossings is sheet-attributable in this flat
#       schema; other anchor types are reserved for a future sheet-tagged
#       schema and are not consulted by the current implementation.
#     - Unknown keys are ignored safely.
#
# Output:
#
#   {
#     "classification":          str,    # subextent_fit_strong / fit_weak /
#                                        # fit_ambiguous / subextent_overflow /
#                                        # subextent_uncertain / no_data
#     "confidence":              str,    # high / medium / low / uncertain
#     "group_span_ft":           int,
#     "candidate_subextents":    list[dict],
#     "best_candidate_index":    int | None,
#     "covered_sheets":          list[int],
#     "missing_sheets":          list[int],
#     "has_reset_boundary":      bool,
#     "ambiguity_flags":         list[str],   # sorted unique
#     "reasons":                 list[str],   # emission order
#     "would_boost":             bool,
#   }
#
# Candidate sub-extent shape:
#
#   {
#     "sheet_set":              list[int],   # sorted ascending
#     "max_subextent_ft":       int,
#     "fit_ratio":              float,       # rounded to 6 dp
#     "corroborating_anchors":  list[str],   # e.g. "matchline_crossing:3"
#     "chain_method":           str,         # single_sheet | contiguous_chain
#     "demotion_reasons":       list[str],
#   }
#
# Ratio bands (deterministic, explicit):
#   - eligible for fit_strong:  _RATIO_SUBEXTENT_MIN <= ratio <= _RATIO_SUBEXTENT_MAX
#   - weak (below subextent):   _RATIO_TRIVIAL_MIN <= ratio < _RATIO_SUBEXTENT_MIN
#   - weak (trivial floor):     0 < ratio < _RATIO_TRIVIAL_MIN
#   - overflow:                 ratio > _RATIO_SUBEXTENT_MAX
#
# Demotion (lifts preliminary_strong to fit_weak, never the reverse):
#   - reset boundary inside candidate sheet set
#   - chain_adjacency_unverified (multi-sheet without explicit adjacency)
#   - sheet confidence is low or uncertain on any sheet in the set
#   - no corroborating anchor for the candidate
#
# Aggregate classification:
#   - >= 2 fit_strong candidates  -> subextent_fit_ambiguous
#   - exactly 1 fit_strong        -> subextent_fit_strong
#   - >= 1 fit_weak candidate     -> subextent_fit_weak
#   - all candidates overflow     -> subextent_overflow
#   - no candidates / no usable   -> subextent_uncertain
# ---------------------------------------------------------------------------

_SUBEXTENT_CLASS_FIT_STRONG: str = "subextent_fit_strong"
_SUBEXTENT_CLASS_FIT_WEAK: str = "subextent_fit_weak"
_SUBEXTENT_CLASS_FIT_AMBIGUOUS: str = "subextent_fit_ambiguous"
_SUBEXTENT_CLASS_OVERFLOW: str = "subextent_overflow"
_SUBEXTENT_CLASS_UNCERTAIN: str = "subextent_uncertain"
_SUBEXTENT_CLASS_NO_DATA: str = "no_data"

_SUBEXTENT_CHAIN_SINGLE: str = "single_sheet"
_SUBEXTENT_CHAIN_CONTIGUOUS: str = "contiguous_chain"

_SUBEXTENT_AMBIGUITY_MISSING_TOPOLOGY: str = "missing_topology"
_SUBEXTENT_AMBIGUITY_CHAIN_UNVERIFIED: str = "chain_adjacency_unverified"
_SUBEXTENT_AMBIGUITY_RESET_BOUNDARY: str = "reset_boundary_in_candidate"
_SUBEXTENT_AMBIGUITY_MULTIPLE_STRONG: str = "multiple_strong_candidates"
_SUBEXTENT_AMBIGUITY_P52_DISAGREE: str = "p52_disagreement"

_RATIO_TRIVIAL_MIN: float = 0.05
_RATIO_SUBEXTENT_MIN: float = 0.15
_RATIO_SUBEXTENT_MAX: float = 1.00
_SUBEXTENT_BOOST_CAP: float = 0.01

# Internal candidate classes — never exit the helper's output schema.
_SUBEXTENT_INTERNAL_PRELIM_STRONG: str = "_prelim_strong"
_SUBEXTENT_INTERNAL_WEAK: str = "_weak"
_SUBEXTENT_INTERNAL_TRIVIAL: str = "_trivial"
_SUBEXTENT_INTERNAL_OVERFLOW: str = "_overflow"


def _subextent_matchline_crossings_set(
    anchor_hints: Optional[Dict[str, Any]],
) -> set:
    """Normalize anchor_hints['matchline_crossings'] to a set of int
    sheets. Returns empty set on any malformed input. Never raises.
    """
    out: set = set()
    if not isinstance(anchor_hints, dict):
        return out
    try:
        raw = anchor_hints.get("matchline_crossings")
        if raw is None:
            return out
        try:
            for entry in raw:
                try:
                    n = _coerce_nonneg_int(entry)
                    if n is not None and n >= 0:
                        out.add(int(n))
                except Exception:
                    continue
        except TypeError:
            return out
    except Exception:
        return out
    return out


def _subextent_has_any_id_anchor(
    anchor_hints: Optional[Dict[str, Any]],
) -> bool:
    """True if anchor_hints carries any non-empty ID list. Used only to
    distinguish 'no anchor hints at all' from 'anchor hints present but
    no matchline corroboration'. Never raises.
    """
    if not isinstance(anchor_hints, dict):
        return False
    for key in ("ap_tokens", "splice_ids", "structure_ids"):
        try:
            raw = anchor_hints.get(key)
            if raw is None:
                continue
            try:
                for entry in raw:
                    if entry is None:
                        continue
                    try:
                        if str(entry).strip():
                            return True
                    except Exception:
                        continue
            except TypeError:
                continue
        except Exception:
            continue
    return False


def _subextent_check_chain_validity(
    sheets: Sequence[int],
    chain_adjacency: Optional[Mapping[int, Sequence[int]]],
) -> "tuple[bool, bool]":
    """Decide whether a sorted sheet set forms a contiguous chain.

    Returns (is_chain_valid, chain_adjacency_unverified).

      - is_chain_valid: True if the sheets form an evaluatable chain.
      - chain_adjacency_unverified: True iff we fell back to the numeric
        heuristic (no authoritative adjacency data provided).

    When chain_adjacency is provided, each adjacent pair in the sorted
    set must have one in the other's adjacency list. When absent, we
    fall back to consecutive-integer heuristic and flag as unverified.
    """
    if not sheets or len(sheets) < 2:
        return (False, False)
    ordered = list(sheets)

    if chain_adjacency is not None:
        try:
            for a, b in zip(ordered[:-1], ordered[1:]):
                a_has = False
                b_has = False
                try:
                    a_adj = chain_adjacency.get(int(a))
                except Exception:
                    a_adj = None
                try:
                    b_adj = chain_adjacency.get(int(b))
                except Exception:
                    b_adj = None
                if a_adj is not None:
                    try:
                        for x in a_adj:
                            try:
                                if _coerce_nonneg_int(x) == int(b):
                                    a_has = True
                                    break
                            except Exception:
                                continue
                    except TypeError:
                        pass
                if b_adj is not None:
                    try:
                        for x in b_adj:
                            try:
                                if _coerce_nonneg_int(x) == int(a):
                                    b_has = True
                                    break
                            except Exception:
                                continue
                    except TypeError:
                        pass
                if not (a_has or b_has):
                    return (False, False)
            return (True, False)
        except Exception:
            return (False, False)

    # Fallback: numeric-consecutive heuristic, flagged as unverified.
    try:
        for a, b in zip(ordered[:-1], ordered[1:]):
            if int(b) - int(a) != 1:
                return (False, True)
        return (True, True)
    except Exception:
        return (False, False)


def _subextent_empty_result(
    classification: str = _SUBEXTENT_CLASS_NO_DATA,
    confidence: str = _CONFIDENCE_UNCERTAIN,
    group_span_ft: int = 0,
    reasons: Optional[List[str]] = None,
    ambiguity_flags: Optional[List[str]] = None,
    covered_sheets: Optional[List[int]] = None,
    missing_sheets: Optional[List[int]] = None,
    has_reset_boundary: bool = False,
) -> Dict[str, Any]:
    return {
        "classification": classification,
        "confidence": confidence,
        "group_span_ft": int(group_span_ft),
        "candidate_subextents": [],
        "best_candidate_index": None,
        "covered_sheets": list(covered_sheets or []),
        "missing_sheets": list(missing_sheets or []),
        "has_reset_boundary": bool(has_reset_boundary),
        "ambiguity_flags": sorted(set(ambiguity_flags or [])),
        "reasons": list(reasons or []),
        "would_boost": False,
    }


def evaluate_localized_subextent_plausibility(
    normalized_group: Optional[Dict[str, Any]],
    sheet_origins: Optional[Dict[int, Dict[str, Any]]],
    print_to_sheets: Optional[Mapping[Any, Any]] = None,
    chain_adjacency: Optional[Mapping[int, Sequence[int]]] = None,
    anchor_hints: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Sub-extent plausibility evaluation between a bore-log group and
    the engineering-plan sheets it references.

    Sibling to evaluate_footage_range_containment. Answers the strictly
    weaker question of whether the span plausibly fits inside SOME
    contiguous sub-window of the referenced sheets.

    Pure function. Never raises. Never mutates inputs. Emits attributable
    reasons for every classification.

    Anchors are evidence, NOT authority.
    Sub-extents are plausibility, NOT certainty.
    """
    # ── Step 0: defensive input validation ───────────────────────────────────
    if not isinstance(normalized_group, dict):
        return _subextent_empty_result(
            reasons=["normalized_group is not a dict"],
        )

    span_raw = normalized_group.get("span_ft")
    span_val = _coerce_positive_number(span_raw)
    if span_val is None:
        return _subextent_empty_result(
            reasons=["normalized_group.span_ft missing, non-positive, or non-numeric"],
        )
    group_span_ft = int(round(span_val))

    matchline_crossings_set = _subextent_matchline_crossings_set(anchor_hints)
    has_any_anchor_hint = bool(matchline_crossings_set) or _subextent_has_any_id_anchor(anchor_hints)

    # ── Step 1: resolve referenced sheets ────────────────────────────────────
    print_tokens_raw = normalized_group.get("print_tokens")
    if not isinstance(print_tokens_raw, list):
        print_tokens_raw = []
    # Read-only snapshot; never mutate caller's list.
    print_tokens = list(print_tokens_raw)
    referenced_sheets = _resolve_referenced_sheets(print_tokens, print_to_sheets)

    if not referenced_sheets and not has_any_anchor_hint:
        return _subextent_empty_result(
            group_span_ft=group_span_ft,
            reasons=["no referenced sheets and no anchor hints"],
        )

    # ── Step 2: normalize sheet_origins to local read-only view ──────────────
    if not isinstance(sheet_origins, dict):
        sheet_origins_local: Dict[int, Dict[str, Any]] = {}
    else:
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

    # ── Step 3: classify each referenced sheet as usable / unusable / missing
    reasons: List[str] = []
    ambiguity_flags: set = set()

    usable_sheets: List[int] = []
    unusable_sheets: List[int] = []
    missing_sheets: List[int] = []
    sheet_lengths: Dict[int, int] = {}
    sheet_confidences: Dict[int, str] = {}
    sheet_methods: Dict[int, str] = {}
    sheet_resets: Dict[int, bool] = {}

    for sheet_no in referenced_sheets:
        entry = sheet_origins_local.get(sheet_no)
        if entry is None:
            missing_sheets.append(sheet_no)
            continue
        try:
            length_val = _coerce_nonneg_int(entry.get("length_ft"))
            method = str(entry.get("method") or _METHOD_UNCERTAIN)
            conf = str(entry.get("confidence") or _CONFIDENCE_UNCERTAIN)
            has_reset = bool(entry.get("has_reset_boundary"))

            if length_val is None or length_val <= 0:
                unusable_sheets.append(sheet_no)
                continue
            if method in (_METHOD_SINGLE_SHEET_ISOLATED, _METHOD_UNCERTAIN):
                unusable_sheets.append(sheet_no)
                continue

            usable_sheets.append(sheet_no)
            sheet_lengths[sheet_no] = int(length_val)
            sheet_confidences[sheet_no] = conf
            sheet_methods[sheet_no] = method
            sheet_resets[sheet_no] = has_reset
        except Exception:
            unusable_sheets.append(sheet_no)
            continue

    if missing_sheets:
        ambiguity_flags.add(_SUBEXTENT_AMBIGUITY_MISSING_TOPOLOGY)
        reasons.append(
            f"No topology for referenced sheets: {sorted(missing_sheets)}"
        )

    covered_sheets_final = sorted(usable_sheets)

    if not covered_sheets_final:
        # All sheets either missing or unusable.
        if unusable_sheets:
            reasons.append("no covered sheet has usable extent method")
        elif missing_sheets:
            # Already accounted for above; emit a concise summary.
            reasons.append("no usable sheet length among covered sheets")
        else:
            # anchor-hints-only path: no resolvable sheets.
            reasons.append("no usable sheet length among covered sheets")
        return _subextent_empty_result(
            classification=_SUBEXTENT_CLASS_UNCERTAIN,
            confidence=_CONFIDENCE_UNCERTAIN,
            group_span_ft=group_span_ft,
            reasons=reasons,
            ambiguity_flags=list(ambiguity_flags),
            covered_sheets=[],
            missing_sheets=sorted(missing_sheets),
            has_reset_boundary=False,
        )

    # ── Step 4: enumerate candidate sub-extents ──────────────────────────────
    raw_candidates: List[Dict[str, Any]] = []

    # Single-sheet candidate per usable sheet.
    for s in covered_sheets_final:
        raw_candidates.append({
            "sheet_set": [s],
            "max_subextent_ft": int(sheet_lengths[s]),
            "chain_method": _SUBEXTENT_CHAIN_SINGLE,
            "chain_unverified": False,
        })

    # Contiguous-chain candidate when >= 2 covered sheets.
    if len(covered_sheets_final) >= 2:
        is_chain_valid, chain_unverified = _subextent_check_chain_validity(
            covered_sheets_final, chain_adjacency
        )
        if is_chain_valid:
            raw_candidates.append({
                "sheet_set": list(covered_sheets_final),
                "max_subextent_ft": int(sum(sheet_lengths[s] for s in covered_sheets_final)),
                "chain_method": _SUBEXTENT_CHAIN_CONTIGUOUS,
                "chain_unverified": bool(chain_unverified),
            })
        else:
            reasons.append(
                f"non-contiguous sheet set {covered_sheets_final} rejected as candidate"
            )

    # ── Step 5: score and classify each candidate ────────────────────────────
    has_reset_overall = False
    scored: List[Dict[str, Any]] = []
    rank_to_label = {v: k for k, v in _CONFIDENCE_RANK.items()}

    for rc in raw_candidates:
        sheet_set = list(rc["sheet_set"])
        max_ft = int(rc["max_subextent_ft"])
        chain_method = str(rc["chain_method"])
        chain_unverified = bool(rc.get("chain_unverified"))

        if max_ft > 0:
            fit_ratio = round(float(group_span_ft) / float(max_ft), 6)
        else:
            fit_ratio = 0.0

        candidate_has_reset = any(sheet_resets.get(s, False) for s in sheet_set)
        if candidate_has_reset:
            has_reset_overall = True

        per_sheet_ranks = [
            _CONFIDENCE_RANK.get(sheet_confidences.get(s, _CONFIDENCE_UNCERTAIN), 0)
            for s in sheet_set
        ]
        worst_rank = min(per_sheet_ranks) if per_sheet_ranks else 0
        worst_conf = rank_to_label.get(worst_rank, _CONFIDENCE_UNCERTAIN)

        corroborating: List[str] = []
        for s in sheet_set:
            if int(s) in matchline_crossings_set:
                corroborating.append(f"matchline_crossing:{int(s)}")

        demotion_reasons: List[str] = []
        if fit_ratio > _RATIO_SUBEXTENT_MAX:
            internal_class = _SUBEXTENT_INTERNAL_OVERFLOW
        elif fit_ratio < _RATIO_TRIVIAL_MIN:
            internal_class = _SUBEXTENT_INTERNAL_TRIVIAL
            demotion_reasons.append(
                f"fit_ratio_below_trivial:{fit_ratio:.6f}<{_RATIO_TRIVIAL_MIN}"
            )
        elif fit_ratio < _RATIO_SUBEXTENT_MIN:
            internal_class = _SUBEXTENT_INTERNAL_WEAK
            demotion_reasons.append(
                f"fit_ratio_below_subextent_min:{fit_ratio:.6f}<{_RATIO_SUBEXTENT_MIN}"
            )
        else:
            internal_class = _SUBEXTENT_INTERNAL_PRELIM_STRONG

        # Demotions: lift preliminary_strong DOWN to weak; never the reverse.
        # All applicable demotion reasons accumulate so observers can see
        # every gate that blocked fit_strong.
        if internal_class == _SUBEXTENT_INTERNAL_PRELIM_STRONG:
            if candidate_has_reset:
                internal_class = _SUBEXTENT_INTERNAL_WEAK
                demotion_reasons.append(_SUBEXTENT_AMBIGUITY_RESET_BOUNDARY)
                ambiguity_flags.add(_SUBEXTENT_AMBIGUITY_RESET_BOUNDARY)
            if chain_unverified:
                internal_class = _SUBEXTENT_INTERNAL_WEAK
                demotion_reasons.append(_SUBEXTENT_AMBIGUITY_CHAIN_UNVERIFIED)
                ambiguity_flags.add(_SUBEXTENT_AMBIGUITY_CHAIN_UNVERIFIED)
            if worst_conf == _CONFIDENCE_LOW:
                internal_class = _SUBEXTENT_INTERNAL_WEAK
                demotion_reasons.append("low_sheet_confidence")
            elif worst_conf == _CONFIDENCE_UNCERTAIN:
                internal_class = _SUBEXTENT_INTERNAL_WEAK
                demotion_reasons.append("uncertain_sheet_confidence")
            if not corroborating:
                internal_class = _SUBEXTENT_INTERNAL_WEAK
                demotion_reasons.append("no_corroborating_anchor")

        scored.append({
            "sheet_set": sheet_set,
            "max_subextent_ft": int(max_ft),
            "fit_ratio": float(fit_ratio),
            "corroborating_anchors": list(corroborating),
            "chain_method": chain_method,
            "demotion_reasons": list(demotion_reasons),
            "_class": internal_class,
        })

    # ── Step 6: deterministic sort — strongest first ─────────────────────────
    class_priority = {
        _SUBEXTENT_INTERNAL_PRELIM_STRONG: 3,
        _SUBEXTENT_INTERNAL_WEAK: 2,
        _SUBEXTENT_INTERNAL_TRIVIAL: 1,
        _SUBEXTENT_INTERNAL_OVERFLOW: 0,
    }
    scored.sort(key=lambda c: (
        -class_priority.get(c["_class"], 0),
        -float(c["fit_ratio"]),
        c["sheet_set"][0] if c["sheet_set"] else 0,
    ))

    # ── Step 7: aggregate classification ─────────────────────────────────────
    strong_count = sum(1 for c in scored if c["_class"] == _SUBEXTENT_INTERNAL_PRELIM_STRONG)
    weak_count = sum(1 for c in scored if c["_class"] == _SUBEXTENT_INTERNAL_WEAK)
    trivial_count = sum(1 for c in scored if c["_class"] == _SUBEXTENT_INTERNAL_TRIVIAL)
    overflow_count = sum(1 for c in scored if c["_class"] == _SUBEXTENT_INTERNAL_OVERFLOW)

    best_candidate_index: Optional[int] = None
    if strong_count >= 2:
        classification = _SUBEXTENT_CLASS_FIT_AMBIGUOUS
        ambiguity_flags.add(_SUBEXTENT_AMBIGUITY_MULTIPLE_STRONG)
        reasons.append("multiple plausible sub-extents map to disjoint routes")
    elif strong_count == 1:
        classification = _SUBEXTENT_CLASS_FIT_STRONG
        best_candidate_index = 0
    elif weak_count >= 1:
        classification = _SUBEXTENT_CLASS_FIT_WEAK
        best_candidate_index = 0
    elif trivial_count >= 1:
        classification = _SUBEXTENT_CLASS_FIT_WEAK
        best_candidate_index = 0
        top = scored[0]
        reasons.append(
            f"fit ratio below trivial threshold "
            f"({top['fit_ratio']:.6f} < {_RATIO_TRIVIAL_MIN})"
        )
    elif overflow_count >= 1:
        classification = _SUBEXTENT_CLASS_OVERFLOW
        reasons.append("group span exceeds every candidate sub-extent")
    else:
        classification = _SUBEXTENT_CLASS_UNCERTAIN

    # ── Step 8: derive overall confidence ────────────────────────────────────
    if classification == _SUBEXTENT_CLASS_FIT_STRONG:
        top = scored[0]
        per_sheet_ranks = [
            _CONFIDENCE_RANK.get(sheet_confidences.get(s, _CONFIDENCE_UNCERTAIN), 0)
            for s in top["sheet_set"]
        ]
        worst_rank = min(per_sheet_ranks) if per_sheet_ranks else 0
        overall_confidence = rank_to_label.get(worst_rank, _CONFIDENCE_UNCERTAIN)
        if missing_sheets and overall_confidence == _CONFIDENCE_HIGH:
            overall_confidence = _CONFIDENCE_MEDIUM
            reasons.append(
                "Confidence demoted to medium: at least one referenced "
                "sheet had no topology data."
            )
    elif classification == _SUBEXTENT_CLASS_FIT_AMBIGUOUS:
        overall_confidence = _CONFIDENCE_MEDIUM
    elif classification == _SUBEXTENT_CLASS_FIT_WEAK:
        overall_confidence = _CONFIDENCE_LOW
    elif classification == _SUBEXTENT_CLASS_OVERFLOW:
        overall_confidence = _CONFIDENCE_MEDIUM
    else:
        overall_confidence = _CONFIDENCE_UNCERTAIN

    # ── Step 9: emit deterministic output (strip internal class field) ───────
    output_candidates: List[Dict[str, Any]] = []
    for c in scored:
        output_candidates.append({
            "sheet_set": list(c["sheet_set"]),
            "max_subextent_ft": int(c["max_subextent_ft"]),
            "fit_ratio": float(c["fit_ratio"]),
            "corroborating_anchors": list(c["corroborating_anchors"]),
            "chain_method": str(c["chain_method"]),
            "demotion_reasons": list(c["demotion_reasons"]),
        })

    would_boost = classification == _SUBEXTENT_CLASS_FIT_STRONG

    return {
        "classification": classification,
        "confidence": overall_confidence,
        "group_span_ft": int(group_span_ft),
        "candidate_subextents": output_candidates,
        "best_candidate_index": best_candidate_index,
        "covered_sheets": list(covered_sheets_final),
        "missing_sheets": sorted(missing_sheets),
        "has_reset_boundary": bool(has_reset_overall),
        "ambiguity_flags": sorted(set(ambiguity_flags)),
        "reasons": list(reasons),
        "would_boost": bool(would_boost),
    }
