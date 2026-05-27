"""PDF Extraction E2a — vector primitive classifier.

Takes an ``pdf-extraction-raw-1`` page record from
``backend/app/core/pdf_extraction_raw.py`` and classifies every
vector_path into a deterministic color/style bucket, optionally
flagging paths as template candidates via conservative geometric
fingerprint rules.

This is **bucket classification only** — NO route grouping, NO
station-to-geometry binding, NO matchline detection.  Those layers
land in E2b / E2c as separate ships.

Hard contracts (mirrors pdf_extraction_raw.py doctrine):

* Pure helper.  No STATE, no env reads, no main-module imports, no
  caching at this layer (caller manages disk cache).
* No PyMuPDF dependency — operates on the already-extracted JSON
  record from E1.
* No AI/LLM.  Color classification = deterministic HSV/RGB ranges.
  Template detection = deterministic geometric/style fingerprints.
* Output is **bucket-grade**, not authoritative.  No
  interpretation of "this is a route" or "this is an existing
  utility" — only "this path's color matches the red bucket".
  Downstream E2b is the layer that earns the right to call a
  bucketed red polyline a "candidate proposed route".
* Deterministic: same input record → byte-identical output
  (modulo input ordering, which is already canonical from E1).
* Bounded: caps per bucket so a pathological page can't blow up
  the output.  Caller's E1 already caps total vector_paths.

Color buckets (semantics inferred from ODOT_TULSA corpus analysis):

* proposed_red     — saturated red.  Common in proposed-construction
                     linework across the ODOT corpus.
* existing_purple  — saturated purple / magenta.
* existing_orange  — saturated orange.
* existing_blue    — saturated blue.
* row_green        — saturated green.  Common ROW/easement color.
* base_black       — pure or near-pure black.  Base linework
                     (parcels, building footprints, roads).
* template_gray    — medium gray, neutral RGB.  Common title block
                     / border / scale bar color.
* white_mask       — pure or near-pure white.  Fills/masks behind
                     text (PyMuPDF emits these as drawing ops).
* other            — anything that doesn't match the above rules.

**Template-candidate flag** (separate from color bucket):

A path can be in a color bucket AND simultaneously be flagged as a
template candidate.  Template candidates carry a hint to downstream
consumers ("consider filtering this path when looking for routes").
The flag is SOFT — it's a hint, not a reclassification.

E2a single-page detection rules (conservative; ratchet up with
multi-page fingerprinting in E2a.1):

* Tiny path with neutral-gray color (likely tick mark / scale tick)
* Path with bbox at page edge (likely page border / title block)
* Path with items_hash that appears more than once on the same
  page (likely repeated symbol / fingerprint)

Schema version: pdf-extraction-classified-1.

Authoritative design: pivot reset plan §3 + ODOT_TULSA strategy
report §6 (2026-05-26).
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, Final, List, Optional, Tuple


SCHEMA_VERSION: Final[str] = "pdf-extraction-classified-1"
SOURCE_SCHEMA: Final[str] = "pdf-extraction-raw-1"
COLOR_RULES_VERSION: Final[str] = "v1"

# Per-bucket safety cap so a pathological page (e.g., 10,000 small
# template tick marks) can't make the classified response 10x bigger
# than the raw input.  E1 already caps vector_paths at 10,000 total,
# so this is the second line of defense.
_PER_BUCKET_CAP: Final[int] = 10_000

# Template-candidate heuristics (single-page mode).
_TINY_PATH_BBOX_AREA_PT_SQ: Final[float] = 25.0  # ~5pt x 5pt
_PAGE_EDGE_MARGIN_PT: Final[float] = 10.0
_REPEATED_HASH_THRESHOLD: Final[int] = 2  # appears >= 2× on the page

# Bucket name list (also defines deterministic iteration order).
BUCKET_NAMES: Final[Tuple[str, ...]] = (
    "proposed_red",
    "existing_purple",
    "existing_orange",
    "existing_blue",
    "row_green",
    "base_black",
    "template_gray",
    "white_mask",
    "other",
)


# ---------------------------------------------------------------------------
# Color classification (hex string → bucket name)
# ---------------------------------------------------------------------------

def _parse_hex(hex_str: Optional[str]) -> Optional[Tuple[int, int, int]]:
    """Parse '#rrggbb' (or '#RRGGBB') → (r, g, b) ints in [0, 255].

    Returns None for malformed/None input.  Accepts an optional leading '#'
    and 6 hex digits; rejects anything else.
    """
    if not isinstance(hex_str, str):
        return None
    s = hex_str.strip().lower()
    if s.startswith("#"):
        s = s[1:]
    if len(s) != 6:
        return None
    try:
        return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
    except ValueError:
        return None


def classify_color(hex_str: Optional[str]) -> str:
    """Classify an sRGB hex color into one of BUCKET_NAMES.

    Pure function; no state.  Deterministic on the same input.

    Returns ``"other"`` for None / malformed input — meaning "no
    color info, not classifiable", NOT "default category".  Downstream
    code can ignore the `other` bucket safely.
    """
    rgb = _parse_hex(hex_str)
    if rgb is None:
        return "other"
    r, g, b = rgb

    # Pure / near-pure white: all channels >= 0xf0
    if r >= 0xf0 and g >= 0xf0 and b >= 0xf0:
        return "white_mask"
    # Pure / near-pure black: all channels <= 0x10
    if r <= 0x10 and g <= 0x10 and b <= 0x10:
        return "base_black"
    # Medium gray: all 3 channels within 0x18 of each other AND not too
    # bright/dark (excludes white/black already caught above).  Light
    # gray (>= 0xc0 with low saturation) often acts as background fill
    # so we keep that in template_gray rather than promoting to
    # white_mask — caller can distinguish by examining stroke_color
    # versus fill_color.
    if abs(r - g) <= 0x18 and abs(g - b) <= 0x18 and abs(r - b) <= 0x18:
        return "template_gray"

    # Saturated red: r dominates, g and b both low
    if r >= 0xc0 and g <= 0x60 and b <= 0x60:
        return "proposed_red"
    # Saturated purple/magenta: r and b both high, g low
    if r >= 0x80 and b >= 0x80 and g <= 0x60:
        return "existing_purple"
    # Saturated orange: r high, g medium, b low
    if r >= 0xc0 and 0x40 <= g <= 0xa0 and b <= 0x40:
        return "existing_orange"
    # Saturated blue: b dominates, r and g both low
    if b >= 0xc0 and r <= 0x60 and g <= 0x60:
        return "existing_blue"
    # Saturated green: g dominates and is high, r/b lower than g
    if g >= 0xa0 and r <= 0xa0 and b <= 0xa0 and g > r and g > b:
        return "row_green"

    return "other"


# ---------------------------------------------------------------------------
# Path-level helpers
# ---------------------------------------------------------------------------

def _path_color_for_classification(path: Dict[str, Any]) -> Optional[str]:
    """Choose which color to classify by.

    A drawing path can have stroke + fill.  We prefer stroke_color
    when present (most linework is stroked, and stroke is the
    operationally meaningful semantic).  Fill-only paths fall back
    to fill_color.  Paths with neither return None → bucket "other".
    """
    sc = path.get("stroke_color")
    if isinstance(sc, str) and sc.strip():
        return sc
    fc = path.get("fill_color")
    if isinstance(fc, str) and fc.strip():
        return fc
    return None


def _bbox_area(bbox: Any) -> float:
    """Compute area of a [x0, y0, x1, y1] bbox.  Returns 0.0 on malformed."""
    try:
        x0, y0, x1, y1 = float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])
    except (TypeError, ValueError, IndexError):
        return 0.0
    w = max(0.0, x1 - x0)
    h = max(0.0, y1 - y0)
    return w * h


def _bbox_at_page_edge(bbox: Any, page_w: float, page_h: float) -> bool:
    """True if the bbox touches/overlaps any page edge within
    _PAGE_EDGE_MARGIN_PT.  Defensive against missing page size."""
    if page_w <= 0 or page_h <= 0:
        return False
    try:
        x0, y0, x1, y1 = float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])
    except (TypeError, ValueError, IndexError):
        return False
    m = _PAGE_EDGE_MARGIN_PT
    return (
        x0 <= m
        or y0 <= m
        or x1 >= (page_w - m)
        or y1 >= (page_h - m)
    )


def _projected_path_record(path: Dict[str, Any]) -> Dict[str, Any]:
    """Project the path to the subset of fields preserved in the
    classified output.  Drops `items` (the raw drawing-op list) to keep
    the classified envelope compact — downstream consumers can join
    back to the raw extraction by ``items_hash`` for full geometry.

    Preserved fields (provenance + minimum geometry for grouping):
      - items_hash (deterministic ID)
      - bbox (geometric reference for later route grouping)
      - stroke_color / fill_color / stroke_width / rule (style)
    """
    return {
        "items_hash":  path.get("items_hash"),
        "bbox":        path.get("bbox"),
        "stroke_color": path.get("stroke_color"),
        "fill_color":   path.get("fill_color"),
        "stroke_width": path.get("stroke_width"),
        "rule":        path.get("rule"),
    }


# ---------------------------------------------------------------------------
# Template-candidate detection (single-page; conservative)
# ---------------------------------------------------------------------------

def _detect_template_candidates(
    paths: List[Dict[str, Any]],
    page_w: float,
    page_h: float,
) -> Tuple[List[str], Dict[str, str]]:
    """Return (template_candidate_items_hashes, reason_per_hash).

    Conservative single-page heuristics:

    1. Repeated items_hash on the same page (>= _REPEATED_HASH_THRESHOLD
       occurrences) → likely a repeated symbol / tick / fingerprint.
    2. Gray-bucket color AND tiny bbox area (likely tick / scale tick).
    3. Gray-bucket color AND bbox at page edge (likely border).

    These are SOFT flags — a flagged path stays in its color bucket;
    the template hint is separate.  Caller decides whether to filter
    template paths during route detection.
    """
    out: List[str] = []
    reasons: Dict[str, str] = {}
    if not paths:
        return out, reasons

    # Rule 1: repeated items_hash on the page.
    hash_counts: Counter = Counter()
    for p in paths:
        if not isinstance(p, dict):
            continue
        h = p.get("items_hash")
        if isinstance(h, str) and h:
            hash_counts[h] += 1
    repeated_hashes = {h for h, c in hash_counts.items() if c >= _REPEATED_HASH_THRESHOLD}

    # Pass once over paths, applying rules.
    seen: set = set()
    for p in paths:
        if not isinstance(p, dict):
            continue
        h = p.get("items_hash")
        if not isinstance(h, str) or not h or h in seen:
            continue
        bucket = classify_color(_path_color_for_classification(p))
        bbox = p.get("bbox")
        area = _bbox_area(bbox)
        triggered_reason: Optional[str] = None

        if h in repeated_hashes:
            triggered_reason = f"repeated_items_hash_x{hash_counts[h]}"
        elif bucket == "template_gray" and area > 0 and area <= _TINY_PATH_BBOX_AREA_PT_SQ:
            triggered_reason = "gray_tiny_bbox"
        elif bucket == "template_gray" and _bbox_at_page_edge(bbox, page_w, page_h):
            triggered_reason = "gray_page_edge"

        if triggered_reason:
            seen.add(h)
            out.append(h)
            reasons[h] = triggered_reason

    # Deterministic order.
    out.sort()
    return out, reasons


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def classify_vector_paths(
    raw_extraction_record: Dict[str, Any],
    optional_pdf_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Classify the vector_paths of an E1 raw extraction record into
    deterministic color buckets, plus an optional template-candidate
    flag list.

    Args:
        raw_extraction_record:  the dict returned by
            ``backend.app.core.pdf_extraction_raw.extract_page_raw`` —
            schema ``pdf-extraction-raw-1``.
        optional_pdf_context:   reserved for multi-page fingerprint
            detection (E2a.1).  Ignored in v1.

    Returns:
        Dict matching schema ``pdf-extraction-classified-1``:

            {
              "schema_version": "pdf-extraction-classified-1",
              "source_schema_version": "pdf-extraction-raw-1",
              "page_index": int | None,
              "page_number": int | None,
              "page_size_px": [W, H],
              "page_rotation": int,
              "bucket_counts": { name: int, ... },
              "color_buckets": {
                "proposed_red":     [projected_path, ...],
                "existing_purple":  [...],
                ...
              },
              "template_candidates": [items_hash, ...],
              "template_reasons":   { items_hash: reason_str, ... },
              "unclassified_paths": [items_hash, ...],  // items_hash list of paths
                                                       // with no stroke/fill color
              "classification_meta": {
                "color_rules_version": "v1",
                "template_detection_method": "single_page_conservative",
                "page_path_count_total":      int,
                "page_path_count_classified": int,
                "per_bucket_cap":             int,
                "per_bucket_truncated": { name: int, ... },  // count of dropped paths
                "source_text_blocks_truncated":  bool,
                "source_vector_paths_truncated": bool,
                "source_text_layer_available":   bool,
              },
            }

    Raises:
        ValueError if ``raw_extraction_record`` has the wrong schema_version
        (i.e., is not a ``pdf-extraction-raw-1`` record).  This is the only
        defensive raise — all other malformed input is tolerated by returning
        sensible defaults (empty arrays, "other" bucket, etc.).
    """
    if not isinstance(raw_extraction_record, dict):
        raise ValueError(
            f"raw_extraction_record must be a dict; got {type(raw_extraction_record).__name__}"
        )
    src_schema = raw_extraction_record.get("schema_version")
    if src_schema != SOURCE_SCHEMA:
        raise ValueError(
            f"raw_extraction_record schema_version must be {SOURCE_SCHEMA!r}; "
            f"got {src_schema!r}"
        )

    # Extract page metadata (safe defaults for any missing field).
    page_size_px = raw_extraction_record.get("page_size_px") or [0.0, 0.0]
    try:
        page_w = float(page_size_px[0])
        page_h = float(page_size_px[1])
    except (TypeError, ValueError, IndexError):
        page_w = page_h = 0.0

    raw_vector_paths = raw_extraction_record.get("vector_paths") or []
    if not isinstance(raw_vector_paths, list):
        raw_vector_paths = []

    # Initialize empty buckets in deterministic order.
    color_buckets: Dict[str, List[Dict[str, Any]]] = {name: [] for name in BUCKET_NAMES}
    unclassified_hashes: List[str] = []
    per_bucket_truncated: Dict[str, int] = {name: 0 for name in BUCKET_NAMES}

    # Single-pass classification.
    for path in raw_vector_paths:
        if not isinstance(path, dict):
            continue
        color_str = _path_color_for_classification(path)
        bucket = classify_color(color_str)
        if color_str is None:
            unclassified_hashes.append(str(path.get("items_hash") or ""))
        bucket_list = color_buckets[bucket]
        if len(bucket_list) >= _PER_BUCKET_CAP:
            per_bucket_truncated[bucket] += 1
            continue
        bucket_list.append(_projected_path_record(path))

    # Deterministic ordering within each bucket: by (bbox y0, bbox x0,
    # items_hash) — same key as E1, so order is preserved end-to-end.
    # Bulletproof against malformed bbox values (string, None, short list).
    def _sort_key(r: Dict[str, Any]) -> Tuple[float, float, str]:
        bbox = r.get("bbox")
        x0 = y0 = 0.0
        if isinstance(bbox, (list, tuple)) and len(bbox) >= 2:
            try:
                x0 = float(bbox[0])
            except (TypeError, ValueError):
                x0 = 0.0
            try:
                y0 = float(bbox[1])
            except (TypeError, ValueError):
                y0 = 0.0
        return (round(y0, 1), round(x0, 1), str(r.get("items_hash") or ""))

    for name in BUCKET_NAMES:
        color_buckets[name].sort(key=_sort_key)

    bucket_counts: Dict[str, int] = {name: len(color_buckets[name]) for name in BUCKET_NAMES}

    # Template-candidate detection runs on the FULL list (not truncated)
    # using the raw input so a heavily-templated page still gets correct
    # fingerprint hits even when bucket truncation kicked in.
    template_candidates, template_reasons = _detect_template_candidates(
        raw_vector_paths, page_w, page_h
    )

    # Drop empty unclassified strings + dedup.
    unclassified_paths = sorted({h for h in unclassified_hashes if h})

    page_path_count_total = len(raw_vector_paths)
    page_path_count_classified = sum(bucket_counts.values())

    out: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "source_schema_version": SOURCE_SCHEMA,
        "page_index":  raw_extraction_record.get("page_index"),
        "page_number": raw_extraction_record.get("page_number"),
        "page_size_px": [round(page_w, 3), round(page_h, 3)],
        "page_rotation": int(raw_extraction_record.get("page_rotation") or 0),
        "bucket_counts": bucket_counts,
        "color_buckets": color_buckets,
        "template_candidates": template_candidates,
        "template_reasons": template_reasons,
        "unclassified_paths": unclassified_paths,
        "classification_meta": {
            "color_rules_version": COLOR_RULES_VERSION,
            "template_detection_method": "single_page_conservative",
            "page_path_count_total":      page_path_count_total,
            "page_path_count_classified": page_path_count_classified,
            "per_bucket_cap":             _PER_BUCKET_CAP,
            "per_bucket_truncated":       per_bucket_truncated,
            "source_text_blocks_truncated":  bool(raw_extraction_record.get("text_blocks_truncated")),
            "source_vector_paths_truncated": bool(raw_extraction_record.get("vector_paths_truncated")),
            "source_text_layer_available":   bool(raw_extraction_record.get("text_layer_available")),
        },
    }
    return out
