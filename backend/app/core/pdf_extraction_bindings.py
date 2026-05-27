"""PDF Extraction E2c — label-to-geometry binding.

Takes an E1 ``pdf-extraction-raw-1`` record (text blocks + raw vector
items) and an E2b ``pdf-extraction-routes-1`` record (route candidates
with provenance items_hashes) and binds each meaningful text label
(station, matchline, construction keyword) to its nearest route
candidate by perpendicular distance.

This is **label-to-route association only** — NO auto-redline
generation, NO operator-facing acceptance, NO bore-log projection.
That work lands in E3+ after operator-side validation of E2c.

Hard contracts (mirrors E1 / E2a / E2b doctrine):

* Pure helper.  No STATE, no env reads, no main-module imports,
  no caching at this layer (caller manages disk cache).
* No PyMuPDF dependency.  Operates entirely on the two JSON
  records produced upstream.
* No AI/LLM.  Detection = regex on text + euclidean point-to-
  segment distance.
* Output is **suggestion-grade**, not authoritative.  A "station
  anchor" is the operator's nearest CAD station-label text to a
  candidate polyline; the operator (or E3) decides whether the
  binding is correct.
* Deterministic: same inputs → byte-identical output.
* Bounded: per-list safety caps prevent pathological pages from
  blowing up the output.

Detection rules:

* **Station**: regex ``\\b(\\d{1,3}\\+\\d{2}(?:\\.\\d+)?)\\b`` —
  e.g., "11+60", "104+25.5".  Captures the numeric token.
* **Matchline**: regex ``\\bMATCH\\s*LINE`` — captures the text
  block.  Sheet reference (when present) extracted via
  ``(?:SEE\\s+SHEET|SHEET)\\s+(\\d+)`` on the surrounding text.
* **Construction keyword**: case-insensitive whole-word search
  for each of: BORE, HANDHOLE, POTHOLE, CONDUIT, HDPE, FIBER,
  UNDERGROUND, PROPOSED, EXISTING.  One binding record per
  matched keyword per text block.

Binding algorithm:

1. For each text block in raw_record, compute its anchor point
   (bbox center).
2. For each route candidate in routes_record:
   * Broad phase: if distance from text anchor to candidate bbox
     > ``broad_phase_distance_pt``, skip the candidate.
   * Narrow phase: for each path in the candidate's
     source_items_hashes, look up its items in raw_record and
     compute min perpendicular distance from the anchor to any
     line/curve segment.
3. Bind to the closest candidate iff its distance is
   <= ``max_bind_distance_pt`` (default 75 pt ≈ 1 inch).
4. If no candidate within threshold → emit to ``unbound_text[]``
   with the smallest distance observed (or None if no candidate).

Schema version: pdf-extraction-bindings-1.

Authoritative design: pivot reset plan §3 (E2c "label-to-geometry
binding") + ODOT_TULSA strategy report §6 (2026-05-26).
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, Final, List, Optional, Tuple


SCHEMA_VERSION: Final[str] = "pdf-extraction-bindings-1"
ROUTES_SOURCE_SCHEMA: Final[str] = "pdf-extraction-routes-1"
RAW_SOURCE_SCHEMA: Final[str] = "pdf-extraction-raw-1"
PARAMETERS_VERSION: Final[str] = "v1"

# Distance thresholds (PDF points; 1 pt = 1/72 inch).
_DEFAULT_MAX_BIND_DISTANCE_PT: Final[float] = 75.0   # ~1 inch
_DEFAULT_BROAD_PHASE_DISTANCE_PT: Final[float] = 150.0  # ~2 inches

# Per-list safety caps.
_MAX_STATION_ANCHORS: Final[int] = 5_000
_MAX_MATCHLINE_RECORDS: Final[int] = 2_000
_MAX_CONSTRUCTION_LABELS: Final[int] = 5_000
_MAX_UNBOUND_TEXT: Final[int] = 5_000

_FLOAT_DECIMALS: Final[int] = 3

# Construction keyword library.  Order matters — longer phrases checked
# first so "HAND HOLE" matches before "HANDHOLE" doesn't (we check
# each keyword independently; ordering is for deterministic output
# only).  All comparisons are case-insensitive.
_CONSTRUCTION_KEYWORDS: Final[Tuple[str, ...]] = (
    "BORE",
    "HANDHOLE",
    "POTHOLE",
    "CONDUIT",
    "HDPE",
    "FIBER",
    "UNDERGROUND",
    "PROPOSED",
    "EXISTING",
)

# Pre-compile regex patterns (deterministic; module-level).
_STATION_RE: Final = re.compile(r"\b(\d{1,3}\+\d{2}(?:\.\d+)?)\b")
_MATCHLINE_RE: Final = re.compile(r"MATCH\s*LINE", re.IGNORECASE)
_MATCHLINE_SHEET_REF_RE: Final = re.compile(
    r"(?:SEE\s+SHEET|SHEET)\s+(\d+)", re.IGNORECASE
)
# Word-boundary keyword search (compiled per-keyword for performance).
_CONSTRUCTION_RES: Final[Dict[str, "re.Pattern[str]"]] = {
    kw: re.compile(rf"\b{re.escape(kw)}\b", re.IGNORECASE)
    for kw in _CONSTRUCTION_KEYWORDS
}


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class PdfExtractionBindingsError(Exception):
    """Raised on schema mismatch / non-dict input."""


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def _r(v: Any) -> float:
    try:
        return round(float(v), _FLOAT_DECIMALS)
    except (TypeError, ValueError):
        return 0.0


def _safe_xy(p: Any) -> Optional[Tuple[float, float]]:
    if not isinstance(p, (list, tuple)) or len(p) < 2:
        return None
    try:
        return (float(p[0]), float(p[1]))
    except (TypeError, ValueError):
        return None


def _safe_bbox(b: Any) -> Optional[Tuple[float, float, float, float]]:
    if not isinstance(b, (list, tuple)) or len(b) < 4:
        return None
    try:
        return (float(b[0]), float(b[1]), float(b[2]), float(b[3]))
    except (TypeError, ValueError):
        return None


def _bbox_center(b: Tuple[float, float, float, float]) -> Tuple[float, float]:
    return ((b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0)


def _point_to_bbox_distance(
    p: Tuple[float, float], bbox: Tuple[float, float, float, float]
) -> float:
    """Min euclidean distance from a point to a bbox.  Returns 0 when
    the point is inside the bbox."""
    x0, y0, x1, y1 = bbox
    dx = max(x0 - p[0], 0.0, p[0] - x1)
    dy = max(y0 - p[1], 0.0, p[1] - y1)
    return math.hypot(dx, dy)


def _point_to_segment_distance(
    p: Tuple[float, float],
    a: Tuple[float, float],
    b: Tuple[float, float],
) -> float:
    """Perpendicular distance from point p to line segment ab.
    Handles a==b by returning |p-a|."""
    ax, ay = a
    bx, by = b
    px, py = p
    dx = bx - ax
    dy = by - ay
    seg_len_sq = dx * dx + dy * dy
    if seg_len_sq <= 1e-12:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / seg_len_sq
    t = max(0.0, min(1.0, t))
    cx = ax + t * dx
    cy = ay + t * dy
    return math.hypot(px - cx, py - cy)


def _iter_path_segments(items: List[Any]):
    """Yield (a, b) pairs for line + curve segments (chord-approximated).

    Closed shapes (rect, quad) yield their 4 edges as segments.
    Malformed items are skipped silently.
    """
    if not isinstance(items, list):
        return
    for it in items:
        if not isinstance(it, (list, tuple)) or not it:
            continue
        op = it[0]
        if op == "l" and len(it) >= 3:
            a = _safe_xy(it[1])
            b = _safe_xy(it[2])
            if a and b:
                yield (a, b)
        elif op == "c" and len(it) >= 5:
            # Chord approximation: p1 → p4
            a = _safe_xy(it[1])
            b = _safe_xy(it[4])
            if a and b:
                yield (a, b)
        elif op == "re" and len(it) >= 2:
            rect = _safe_bbox(it[1])
            if rect:
                rx0, ry0, rx1, ry1 = rect
                corners = [(rx0, ry0), (rx1, ry0), (rx1, ry1), (rx0, ry1)]
                for i in range(4):
                    yield (corners[i], corners[(i + 1) % 4])
        elif op == "qu" and len(it) >= 5:
            pts = [_safe_xy(it[i + 1]) for i in range(4)]
            if all(pt is not None for pt in pts):
                for i in range(4):
                    yield (pts[i], pts[(i + 1) % 4])


def _point_to_candidate_distance(
    p: Tuple[float, float],
    candidate: Dict[str, Any],
    raw_items_by_hash: Dict[str, List[Any]],
) -> Optional[float]:
    """Min perpendicular distance from point p to any segment in any
    path of the route candidate.  Returns None when no segment found
    (e.g., bbox_proxy candidate with no geometry)."""
    min_d: Optional[float] = None
    for h in candidate.get("source_items_hashes") or []:
        items = raw_items_by_hash.get(h)
        if not items:
            continue
        for a, b in _iter_path_segments(items):
            d = _point_to_segment_distance(p, a, b)
            if min_d is None or d < min_d:
                min_d = d
    return min_d


# ---------------------------------------------------------------------------
# Text-block iteration
# ---------------------------------------------------------------------------

def _iter_text_blocks(raw_record: Dict[str, Any]):
    """Yield (text_str, bbox_tuple, anchor_point, block_no) for each
    well-formed text block."""
    for idx, b in enumerate(raw_record.get("text_blocks") or []):
        if not isinstance(b, dict):
            continue
        text = b.get("text")
        if not isinstance(text, str) or not text.strip():
            continue
        bbox = _safe_bbox(b.get("bbox"))
        if bbox is None:
            continue
        anchor = _bbox_center(bbox)
        bno = b.get("block_no")
        try:
            block_no = int(bno) if bno is not None else idx
        except (TypeError, ValueError):
            block_no = idx
        yield text, bbox, anchor, block_no


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def bind_labels_to_routes(
    raw_record: Dict[str, Any],
    routes_record: Dict[str, Any],
    classified_record: Optional[Dict[str, Any]] = None,
    max_bind_distance_pt: float = _DEFAULT_MAX_BIND_DISTANCE_PT,
    broad_phase_distance_pt: float = _DEFAULT_BROAD_PHASE_DISTANCE_PT,
) -> Dict[str, Any]:
    """Bind text labels to route candidates by perpendicular distance.

    Args:
        raw_record:        E1 ``pdf-extraction-raw-1`` record (text +
            true vector items).
        routes_record:     E2b ``pdf-extraction-routes-1`` record
            (candidate route polylines).
        classified_record: optional E2a record.  Reserved for future
            label-color-bucket cross-references; ignored in v1.
        max_bind_distance_pt: max anchor-to-candidate distance to
            accept a binding.  Default 75 pt (~1 inch).
        broad_phase_distance_pt: anchor-to-candidate-bbox cutoff for
            broad-phase culling.  Default 150 pt.

    Returns:
        Dict matching schema ``pdf-extraction-bindings-1``.

    Raises:
        PdfExtractionBindingsError on missing/wrong-schema inputs.
    """
    if not isinstance(raw_record, dict):
        raise PdfExtractionBindingsError(
            f"raw_record must be a dict; got {type(raw_record).__name__}"
        )
    if raw_record.get("schema_version") != RAW_SOURCE_SCHEMA:
        raise PdfExtractionBindingsError(
            f"raw_record schema_version must be {RAW_SOURCE_SCHEMA!r}; "
            f"got {raw_record.get('schema_version')!r}"
        )
    if not isinstance(routes_record, dict):
        raise PdfExtractionBindingsError(
            f"routes_record must be a dict; got {type(routes_record).__name__}"
        )
    if routes_record.get("schema_version") != ROUTES_SOURCE_SCHEMA:
        raise PdfExtractionBindingsError(
            f"routes_record schema_version must be {ROUTES_SOURCE_SCHEMA!r}; "
            f"got {routes_record.get('schema_version')!r}"
        )

    # Validate parameter ranges defensively.
    if not isinstance(max_bind_distance_pt, (int, float)) or max_bind_distance_pt < 0:
        max_bind_distance_pt = _DEFAULT_MAX_BIND_DISTANCE_PT
    if not isinstance(broad_phase_distance_pt, (int, float)) or broad_phase_distance_pt < 0:
        broad_phase_distance_pt = _DEFAULT_BROAD_PHASE_DISTANCE_PT
    max_bind = float(max_bind_distance_pt)
    broad = float(broad_phase_distance_pt)

    # Build raw items lookup table.
    raw_items_by_hash: Dict[str, List[Any]] = {}
    for p in (raw_record.get("vector_paths") or []):
        if not isinstance(p, dict):
            continue
        h = p.get("items_hash")
        if isinstance(h, str) and h:
            raw_items_by_hash[h] = p.get("items") or []

    # Candidate prep: precompute bboxes for broad-phase culling.
    candidates: List[Dict[str, Any]] = []
    for c in (routes_record.get("route_candidates") or []):
        if not isinstance(c, dict):
            continue
        bbox = _safe_bbox(c.get("bbox"))
        cid = c.get("candidate_id")
        if bbox is None or not isinstance(cid, str):
            continue
        candidates.append({
            "candidate_id": cid,
            "bbox":         bbox,
            "raw":          c,
        })

    def _bind_anchor(anchor: Tuple[float, float]) -> Tuple[Optional[str], Optional[float]]:
        """Return (best_candidate_id, distance_pt) or (None, None) if no
        candidate is within max_bind_distance_pt.  Broad-phase culls
        candidates whose bbox is beyond broad_phase_distance_pt."""
        best_id: Optional[str] = None
        best_d: Optional[float] = None
        for c in candidates:
            bbox_d = _point_to_bbox_distance(anchor, c["bbox"])
            if bbox_d > broad:
                continue
            d = _point_to_candidate_distance(anchor, c["raw"], raw_items_by_hash)
            if d is None:
                # No geometry — fall back to bbox-edge distance.
                d = bbox_d
            if best_d is None or d < best_d:
                best_d = d
                best_id = c["candidate_id"]
        if best_d is None or best_d > max_bind:
            return None, best_d
        return best_id, best_d

    # ──── Detect + bind per text block ──────────────────────────────────
    station_anchors: List[Dict[str, Any]] = []
    matchline_records: List[Dict[str, Any]] = []
    construction_labels: List[Dict[str, Any]] = []
    unbound_text: List[Dict[str, Any]] = []

    text_block_count = 0
    for text, bbox, anchor, block_no in _iter_text_blocks(raw_record):
        text_block_count += 1
        any_match = False

        # Station matches (every numeric station token in the text).
        for m in _STATION_RE.finditer(text):
            station_str = m.group(1)
            cand_id, distance = _bind_anchor(anchor)
            record = {
                "raw_text":            text,
                "matched_text":        station_str,
                "text_bbox":           [_r(bbox[0]), _r(bbox[1]), _r(bbox[2]), _r(bbox[3])],
                "anchor_point":        [_r(anchor[0]), _r(anchor[1])],
                "block_no":            block_no,
                "route_candidate_id":  cand_id,
                "distance_pt":         _r(distance) if distance is not None else None,
                "rule_id":             "station_regex_v1",
                "confidence": {
                    "kind": "bound" if cand_id else "unbound",
                    "within_max_bind_distance_pt": cand_id is not None,
                },
            }
            if cand_id:
                station_anchors.append(record)
                any_match = True
            else:
                # Still useful — surface in unbound list with kind hint.
                unbound_text.append({**record, "rule_id": "station_regex_v1"})
                any_match = True

        # Matchline matches.
        if _MATCHLINE_RE.search(text):
            sheet_ref_m = _MATCHLINE_SHEET_REF_RE.search(text)
            sheet_ref = int(sheet_ref_m.group(1)) if sheet_ref_m else None
            station_in_matchline_m = _STATION_RE.search(text)
            station_in_matchline = station_in_matchline_m.group(1) if station_in_matchline_m else None
            cand_id, distance = _bind_anchor(anchor)
            record = {
                "raw_text":            text,
                "text_bbox":           [_r(bbox[0]), _r(bbox[1]), _r(bbox[2]), _r(bbox[3])],
                "anchor_point":        [_r(anchor[0]), _r(anchor[1])],
                "block_no":            block_no,
                "station":             station_in_matchline,
                "references_sheet":    sheet_ref,
                "route_candidate_id":  cand_id,
                "distance_pt":         _r(distance) if distance is not None else None,
                "rule_id":             "matchline_regex_v1",
                "confidence": {
                    "kind": "bound" if cand_id else "unbound",
                    "has_sheet_ref":  sheet_ref is not None,
                },
            }
            if cand_id:
                matchline_records.append(record)
            else:
                unbound_text.append({**record, "rule_id": "matchline_regex_v1"})
            any_match = True

        # Construction keyword matches (one record per matched keyword
        # in the text block).  Deterministic iteration order from
        # _CONSTRUCTION_KEYWORDS tuple.
        for kw in _CONSTRUCTION_KEYWORDS:
            if _CONSTRUCTION_RES[kw].search(text):
                cand_id, distance = _bind_anchor(anchor)
                record = {
                    "raw_text":            text,
                    "keyword":             kw,
                    "text_bbox":           [_r(bbox[0]), _r(bbox[1]), _r(bbox[2]), _r(bbox[3])],
                    "anchor_point":        [_r(anchor[0]), _r(anchor[1])],
                    "block_no":            block_no,
                    "route_candidate_id":  cand_id,
                    "distance_pt":         _r(distance) if distance is not None else None,
                    "rule_id":             f"construction_keyword_v1:{kw}",
                    "confidence": {
                        "kind": "bound" if cand_id else "unbound",
                    },
                }
                if cand_id:
                    construction_labels.append(record)
                else:
                    unbound_text.append({**record, "rule_id": f"construction_keyword_v1:{kw}"})
                any_match = True

        # Note: blocks with no regex/keyword match are silently ignored
        # (e.g., generic body text, headers).  They are NOT added to
        # unbound_text — unbound_text only carries matched-but-not-bound
        # records.

        if any_match:
            pass  # already accounted for above

    # ──── Apply caps ────────────────────────────────────────────────────
    station_anchors = station_anchors[:_MAX_STATION_ANCHORS]
    matchline_records = matchline_records[:_MAX_MATCHLINE_RECORDS]
    construction_labels = construction_labels[:_MAX_CONSTRUCTION_LABELS]
    unbound_text = unbound_text[:_MAX_UNBOUND_TEXT]

    # ──── Deterministic sort ────────────────────────────────────────────
    def _sort_key_with_text(r: Dict[str, Any]) -> Tuple[float, float, str, str]:
        bbox = r.get("text_bbox") or [0.0, 0.0, 0.0, 0.0]
        return (
            round(float(bbox[1] if len(bbox) > 1 else 0.0), 1),
            round(float(bbox[0] if len(bbox) > 0 else 0.0), 1),
            str(r.get("rule_id") or ""),
            str(r.get("matched_text") or r.get("keyword") or r.get("raw_text") or ""),
        )

    station_anchors.sort(key=_sort_key_with_text)
    matchline_records.sort(key=_sort_key_with_text)
    construction_labels.sort(key=_sort_key_with_text)
    unbound_text.sort(key=_sort_key_with_text)

    # ──── Assemble envelope ─────────────────────────────────────────────
    page_size_px = raw_record.get("page_size_px") or [0.0, 0.0]
    try:
        page_w = _r(page_size_px[0])
        page_h = _r(page_size_px[1])
    except (TypeError, IndexError):
        page_w = page_h = 0.0

    return {
        "schema_version":                SCHEMA_VERSION,
        "source_routes_schema_version":  ROUTES_SOURCE_SCHEMA,
        "source_raw_schema_version":     RAW_SOURCE_SCHEMA,
        "page_index":                    raw_record.get("page_index"),
        "page_number":                   raw_record.get("page_number"),
        "page_size_px":                  [page_w, page_h],
        "page_rotation":                 int(raw_record.get("page_rotation") or 0),
        "bucket":                        routes_record.get("bucket"),
        "parameters": {
            "version":                   PARAMETERS_VERSION,
            "max_bind_distance_pt":      _r(max_bind),
            "broad_phase_distance_pt":   _r(broad),
            "construction_keywords":     list(_CONSTRUCTION_KEYWORDS),
        },
        "station_anchors":     station_anchors,
        "matchline_records":   matchline_records,
        "construction_labels": construction_labels,
        # Reserved field for future symbol detection.  Empty in v1.
        "symbol_candidates":   [],
        "unbound_text":        unbound_text,
        "meta": {
            "input_text_block_count":      text_block_count,
            "input_route_candidate_count": len(candidates),
            "station_anchor_count":        len(station_anchors),
            "matchline_count":             len(matchline_records),
            "construction_label_count":    len(construction_labels),
            "symbol_candidate_count":      0,
            "unbound_count":               len(unbound_text),
            "classified_record_provided":  classified_record is not None,
        },
    }
