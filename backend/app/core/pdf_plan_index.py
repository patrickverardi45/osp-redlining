"""PDF Plan Mode Step 2A — plan set index + per-page classification.

Extracts a deterministic, human-reviewable index of an engineering PDF:
per-page text-layer extraction, regex-based detection of route names,
matchlines, station labels, construction keywords, plus a coarse
classification (plan_sheet / detail_sheet / cover_sheet / notes_sheet
/ unknown) and a redline_candidate hint.

Hard contracts:

* Pure helper. No STATE, no env reads, no main-module imports, no
  caching at this layer (caller manages disk cache).
* PyMuPDF (``import fitz``) is imported LAZILY so test envs that do
  not install PyMuPDF can still import this module.  Missing PyMuPDF
  surfaces as ``PdfPlanIndexError`` which the route handler converts
  to a 500.
* No OCR.  Extraction uses the PDF text layer only.  If the layer is
  empty for a page, ``text_layer_available`` is False for that page
  and detection lists come back empty — the UI must label this as a
  scanned/raster page rather than claim "no construction content".
* Output is suggestion-grade, not authoritative.  Classifications are
  heuristic; operator review is required for any downstream use.
* Deterministic: same PDF bytes → byte-identical JSON output.
* Bounded:
    - per-page text excerpt capped at 240 chars
    - per-page station labels capped at 20 unique
    - per-page matchline refs capped at 10
    - per-page route names capped at 8
    - per-page construction keywords capped at 12 unique
    - per-page title candidates capped at 3
    - PDF page count read but processing stops gracefully at first
      page-load exception (whole PDF still returns; failed page gets
      ``page_load_error``)

Schema version: pdf-plan-index-1.

Authoritative design: lane planning §1-§3 (PDF Plan Mode planning doc).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Final, List, Optional, Tuple


SCHEMA_VERSION: Final[str] = "pdf-plan-index-1"

_TEXT_EXCERPT_CAP: Final[int] = 240
_STATION_CAP: Final[int] = 20
_MATCHLINE_CAP: Final[int] = 10
_ROUTE_CAP: Final[int] = 8
_KEYWORD_CAP: Final[int] = 12
_TITLE_CAP: Final[int] = 3


# ---------------------------------------------------------------------------
# Regex pattern library
# ---------------------------------------------------------------------------
# Station: e.g. "11+60", "104+25.5", "STA 14+20".  Captures the numeric
# token only; the surrounding "STA"/"STATION" prefix is optional.
_STATION_RX: Final = re.compile(r"\b(\d{1,3}\+\d{2}(?:\.\d+)?)\b")

# Matchline reference: captures up to ~80 chars after MATCHLINE/MATCH LINE
# so the operator can see the destination sheet inline.
_MATCHLINE_RX: Final = re.compile(
    r"\bMATCH\s*LINE[^\r\n]{0,80}", re.IGNORECASE
)

# Route designators common across Oklahoma + Texas DOT plans + generic
# numbered highways.  Patterns are intentionally permissive on punctuation
# and whitespace so OCR-adjacent variants still match.
_ROUTE_PATTERNS: Final[Tuple[re.Pattern[str], ...]] = (
    re.compile(r"\b(?:OK|SH|US|FM|I|CR|SR)\s*-?\s*\d{1,4}\b", re.IGNORECASE),
    re.compile(r"\bSTATE\s+HIGHWAY\s+\d{1,4}\b", re.IGNORECASE),
    re.compile(r"\bU\.?\s*S\.?\s+(?:HIGHWAY\s+)?\d{1,4}\b", re.IGNORECASE),
    re.compile(r"\b(?:STATE|US|U\.S\.)\s+ROUTE\s+\d{1,4}\b", re.IGNORECASE),
    re.compile(r"\bHIGHWAY\s+\d{1,4}\b", re.IGNORECASE),
    re.compile(r"\bINTERSTATE\s+\d{1,4}\b", re.IGNORECASE),
)

# Construction keyword library (case-insensitive substring match against
# the page's lowercased text).  Each entry is the canonical lowercase
# token returned in the output.  Order is preserved on output.
_CONSTRUCTION_KEYWORDS: Final[Tuple[str, ...]] = (
    "proposed underground",
    "existing underground",
    "directional bore",
    "dir. bore",
    "bore",
    "pothole repair",
    "pothole",
    "handhole",
    "hand hole",
    "splice point",
    "splice can",
    "splice",
    "fiber optic",
    "fiber",
    "conduit",
    "hdpe",
    "vacant hdpe",
    "vault",
    "manhole",
    "pull box",
    "pullbox",
    "junction box",
    "house drop",
    "service drop",
    "drop",
    "trench",
    "trenching",
    "casing",
    "sleeve",
    "terminal",
    "underground construction",
    "underground",
    "cable",
    "duct",
)

# Detail-sheet vocabulary.  Strong signals that a page is a reference /
# typical-section / detail page rather than a plan view.
_DETAIL_KEYWORDS: Final[Tuple[str, ...]] = (
    "detail",
    "details",
    "typical section",
    "typical",
    "not to scale",
    "n.t.s.",
    "nts",
    "section a-a",
    "elevation",
    "isometric",
)

# Notes / legend / abbreviations vocabulary.
_NOTES_KEYWORDS: Final[Tuple[str, ...]] = (
    "general notes",
    "construction notes",
    "specific notes",
    "legend",
    "abbreviations",
    "symbols",
    "key map",
    "specifications",
)

# Cover / title / index vocabulary.
_COVER_KEYWORDS: Final[Tuple[str, ...]] = (
    "title sheet",
    "cover sheet",
    "sheet index",
    "index of sheets",
    "drawing index",
    "project information",
    "vicinity map",
    "location map",
)


class PdfPlanIndexError(Exception):
    """Raised on extraction failure or missing PyMuPDF dependency."""


@dataclass
class _PageRaw:
    page_index: int
    text: str
    blocks: List[Tuple[float, float, float, float, str]]
    text_layer_available: bool
    page_load_error: Optional[str] = None


# ---------------------------------------------------------------------------
# Per-page extraction helpers (pure, regex-only)
# ---------------------------------------------------------------------------

def _uniq_preserving_order(items: List[str]) -> List[str]:
    seen: set = set()
    out: List[str] = []
    for it in items:
        if it not in seen:
            seen.add(it)
            out.append(it)
    return out


def _normalize_route_token(s: str) -> str:
    """Collapse whitespace and uppercase for stable comparison."""
    return re.sub(r"\s+", " ", s).strip().upper()


def _extract_stations(text: str) -> List[str]:
    if not text:
        return []
    matches = _STATION_RX.findall(text)
    return _uniq_preserving_order(matches)[:_STATION_CAP]


def _extract_matchlines(text: str) -> List[str]:
    if not text:
        return []
    raw = _MATCHLINE_RX.findall(text)
    cleaned = [re.sub(r"\s+", " ", m).strip() for m in raw]
    return _uniq_preserving_order(cleaned)[:_MATCHLINE_CAP]


def _extract_routes(text: str) -> List[str]:
    if not text:
        return []
    hits: List[str] = []
    for rx in _ROUTE_PATTERNS:
        for m in rx.findall(text):
            hits.append(_normalize_route_token(m))
    return _uniq_preserving_order(hits)[:_ROUTE_CAP]


def _extract_construction_keywords(lower_text: str) -> List[str]:
    if not lower_text:
        return []
    hits = [kw for kw in _CONSTRUCTION_KEYWORDS if kw in lower_text]
    return _uniq_preserving_order(hits)[:_KEYWORD_CAP]


def _extract_title_candidates(
    blocks: List[Tuple[float, float, float, float, str]],
) -> List[str]:
    """Find the topmost non-empty short-line text blocks as title guesses.

    PyMuPDF block tuples are (x0, y0, x1, y1, text[, block_no, block_type]).
    We sort by y0 ascending (top of page) and take up to _TITLE_CAP entries
    whose stripped text is between 3 and 80 chars (excludes long body
    paragraphs and noise glyphs).
    """
    if not blocks:
        return []
    sorted_blocks = sorted(blocks, key=lambda b: (round(b[1], 1), round(b[0], 1)))
    candidates: List[str] = []
    for b in sorted_blocks:
        try:
            text = str(b[4] or "").strip()
        except Exception:
            continue
        # Collapse internal whitespace, drop pure-numeric noise.
        text = re.sub(r"\s+", " ", text)
        if len(text) < 3 or len(text) > 80:
            continue
        if text.isnumeric():
            continue
        if text in candidates:
            continue
        candidates.append(text)
        if len(candidates) >= _TITLE_CAP:
            break
    return candidates


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

def _count_keyword_hits(lower_text: str, vocab: Tuple[str, ...]) -> int:
    if not lower_text:
        return 0
    return sum(1 for kw in vocab if kw in lower_text)


def _classify_page(
    *,
    page_index: int,
    page_count: int,
    lower_text: str,
    stations: List[str],
    matchlines: List[str],
    routes: List[str],
    construction_keywords: List[str],
    text_layer_available: bool,
) -> str:
    """Coarse, deterministic, suggestion-grade classification.

    Priority order:
      1. plan_sheet  — strong geometric signal (stations OR matchlines)
                       AND has at least one construction keyword
      2. detail_sheet — detail vocab >= 2 and weak/absent station chain
      3. notes_sheet  — notes vocab >= 2 and absent station chain
      4. cover_sheet  — cover vocab >= 1, OR page_index==0 with low text
                        volume and no station chain
      5. unknown      — fallback (also when text layer is unavailable)

    A page with stations + matchlines but ZERO construction keywords is
    still classified plan_sheet (e.g. profile-only sheets); we deliberately
    err toward operator review on borderline cases by separating the
    keyword evidence into the redline_candidate signal rather than the
    classification.
    """
    if not text_layer_available:
        return "unknown"

    has_stations = len(stations) >= 3
    has_matchlines = len(matchlines) >= 1

    if has_stations or has_matchlines:
        return "plan_sheet"

    detail_score = _count_keyword_hits(lower_text, _DETAIL_KEYWORDS)
    notes_score = _count_keyword_hits(lower_text, _NOTES_KEYWORDS)
    cover_score = _count_keyword_hits(lower_text, _COVER_KEYWORDS)

    # Detail wins if its specific vocab strongly dominates and there is
    # no station chain.  Threshold of 2 avoids one-off mentions in plan
    # callouts (e.g. "see detail A") triggering misclassification.
    if detail_score >= 2 and not has_stations:
        return "detail_sheet"

    if notes_score >= 2 and not has_stations:
        return "notes_sheet"

    if cover_score >= 1 and not has_stations:
        return "cover_sheet"

    # Heuristic for unlabeled cover pages: first page with low text volume.
    if page_index == 0 and len(lower_text) < 600 and not has_stations:
        return "cover_sheet"

    # If the page has construction keywords but no station chain, lean
    # plan_sheet anyway (single-bore detail pages can lack stations).
    if construction_keywords:
        return "plan_sheet"

    return "unknown"


def _compute_redline_candidate(
    classification: str,
    stations: List[str],
    matchlines: List[str],
    construction_keywords: List[str],
) -> bool:
    """A page is a redline candidate if it's a plan_sheet AND has either
    a station chain or construction keywords the operator can anchor
    work onto.

    detail_sheet / cover_sheet / notes_sheet / unknown are never
    redline candidates regardless of incidental keyword matches.
    """
    if classification != "plan_sheet":
        return False
    if len(stations) >= 3:
        return True
    if matchlines:
        return True
    if construction_keywords:
        return True
    return False


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------

def extract_plan_set_index(pdf_path: Path) -> Dict[str, Any]:
    """Extract a plan-set page index from an engineering PDF.

    Args:
        pdf_path:  path to the source PDF (must exist + be readable).

    Returns:
        A dict with the shape documented at the top of this module
        (schema ``pdf-plan-index-1``).

    Raises:
        PdfPlanIndexError on missing file, missing PyMuPDF, or PDF
        open failure.  Per-page exceptions are caught and reported in
        the page record's ``page_load_error`` field so a single bad
        page does not prevent the rest of the index from returning.
    """
    if not isinstance(pdf_path, Path):
        pdf_path = Path(pdf_path)
    if not pdf_path.is_file():
        raise PdfPlanIndexError(f"PDF not found: {pdf_path}")

    try:
        import fitz  # PyMuPDF
    except ImportError as e:
        raise PdfPlanIndexError(f"PyMuPDF unavailable: {e}") from e

    try:
        doc = fitz.open(str(pdf_path))
    except Exception as e:
        raise PdfPlanIndexError(
            f"failed to open PDF: {type(e).__name__}: {e}"
        ) from e

    pages_out: List[Dict[str, Any]] = []
    any_text_layer = False

    try:
        page_count = int(getattr(doc, "page_count", 0) or 0)
        for page_index in range(page_count):
            page_record = _extract_one_page(doc, page_index)
            pages_out.append(page_record)
            if page_record.get("text_layer_available"):
                any_text_layer = True
    finally:
        try:
            doc.close()
        except Exception:
            pass

    return {
        "schema_version": SCHEMA_VERSION,
        "page_count": len(pages_out),
        "text_extraction_available": any_text_layer,
        "pages": pages_out,
    }


def _extract_one_page(doc: Any, page_index: int) -> Dict[str, Any]:
    page_record: Dict[str, Any] = {
        "page_index": page_index,
        "page_number": page_index + 1,
        "title_candidates": [],
        "route_names": [],
        "matchline_refs": [],
        "station_labels": [],
        "construction_keywords": [],
        "classification": "unknown",
        "redline_candidate": False,
        "text_layer_available": False,
        "raw_text_excerpt": "",
    }

    try:
        page = doc.load_page(page_index)
    except Exception as e:
        page_record["page_load_error"] = f"{type(e).__name__}: {e}"
        return page_record

    try:
        text = page.get_text("text") or ""
    except Exception as e:
        page_record["page_load_error"] = (
            f"get_text(text) failed: {type(e).__name__}: {e}"
        )
        return page_record

    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text_stripped = text.strip()
    text_layer_available = bool(text_stripped)
    page_record["text_layer_available"] = text_layer_available
    page_record["raw_text_excerpt"] = text_stripped[:_TEXT_EXCERPT_CAP]

    blocks: List[Tuple[float, float, float, float, str]] = []
    try:
        raw_blocks = page.get_text("blocks") or []
        for b in raw_blocks:
            if len(b) >= 5 and isinstance(b[4], str):
                try:
                    blocks.append((float(b[0]), float(b[1]), float(b[2]), float(b[3]), b[4]))
                except (TypeError, ValueError):
                    continue
    except Exception:
        # blocks API is best-effort for title heuristics; ignore failure
        blocks = []

    if not text_layer_available:
        # No text layer: leave all detection arrays empty + classification
        # stays "unknown".  This is the OCR-required path; UI labels it
        # so operator knows to expect raster scans here.
        page_count_in_doc = int(getattr(doc, "page_count", 0) or 0)
        page_record["classification"] = _classify_page(
            page_index=page_index,
            page_count=page_count_in_doc,
            lower_text="",
            stations=[],
            matchlines=[],
            routes=[],
            construction_keywords=[],
            text_layer_available=False,
        )
        return page_record

    lower_text = text.lower()

    stations = _extract_stations(text)
    matchlines = _extract_matchlines(text)
    routes = _extract_routes(text)
    construction_keywords = _extract_construction_keywords(lower_text)
    titles = _extract_title_candidates(blocks)

    classification = _classify_page(
        page_index=page_index,
        page_count=int(getattr(doc, "page_count", 0) or 0),
        lower_text=lower_text,
        stations=stations,
        matchlines=matchlines,
        routes=routes,
        construction_keywords=construction_keywords,
        text_layer_available=True,
    )
    redline_candidate = _compute_redline_candidate(
        classification, stations, matchlines, construction_keywords
    )

    page_record.update(
        {
            "title_candidates": titles,
            "route_names": routes,
            "matchline_refs": matchlines,
            "station_labels": stations,
            "construction_keywords": construction_keywords,
            "classification": classification,
            "redline_candidate": redline_candidate,
        }
    )
    return page_record
