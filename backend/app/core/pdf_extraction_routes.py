"""PDF Extraction E2b — route candidate grouping.

Takes an E2a ``pdf-extraction-classified-1`` record (bucket assignment)
plus an E1 ``pdf-extraction-raw-1`` record (true vertex geometry) and
produces a deterministic set of **candidate route polylines** per page
by connected-component clustering on endpoint proximity.

This is **geometry grouping only** — NO station-to-route binding, NO
matchline detection, NO label correlation.  Those land in E2c as a
separate ship.

Hard contracts (mirrors E1 / E2a doctrine):

* Pure helper.  No STATE, no env reads, no main-module imports, no
  caching at this layer (caller manages disk cache).
* No PyMuPDF dependency.  Operates entirely on the two JSON records
  produced upstream.
* No AI/LLM.  Grouping uses union-find on euclidean endpoint
  distance against an operator-tunable threshold.
* Output is **suggestion-grade**, not authoritative.  A "route
  candidate" is a geometrically-connected group of paths in the
  target color bucket; the operator (or E2c downstream) decides
  whether the candidate is actually a proposed route line.
* Deterministic: same inputs → byte-identical output (modulo input
  ordering, which is canonical from E2a).
* Bounded: per-bucket safety caps inherited from E2a (10000 paths
  cap); E2b adds its own `_MAX_CANDIDATES` cap on output.
* Graceful degradation: if the raw record is omitted, fall back to
  bbox-corner proxies for endpoint clustering, and flag the
  confidence as ``bbox_proxy`` so downstream knows the geometry
  is coarse.

Endpoint extraction model:

* For a path containing only line ("l") + curve ("c") items, the
  polyline endpoints are the FIRST point of the first item and the
  LAST point of the last item, in traversal order.
* For a path containing any rect ("re") or quad ("qu") op, the
  entire path is treated as CLOSED — endpoints are None, and the
  path becomes a self-contained closed candidate (eligible only if
  it passes ``min_length_pt`` on its perimeter).
* If a path's first vertex equals its last vertex within
  ``endpoint_eps_pt``, it is also treated as closed (a polygon
  drawn as a chain of lines).

Grouping algorithm:

1. Resolve each bucketed path's (start, end) endpoint pair via the
   raw record (or bbox-corner proxies if raw is absent).
2. Compute pairwise distance between every (path_i.endpoint_x,
   path_j.endpoint_y) for all i < j.
3. Union the two paths' connected-component sets whenever ANY
   endpoint of path_i is within ``endpoint_eps_pt`` of ANY endpoint
   of path_j.  This is O(N²) — N is the bucket size, typically <300.
4. Each connected component becomes one candidate.
5. Compute per-candidate: total_length_pt (sum of segment lengths
   across all paths), bbox (union of path bboxes), free_endpoints
   (endpoints that don't connect to another path in the group),
   dominant_orientation, confidence.
6. Filter candidates whose total_length_pt < min_length_pt to a
   separate ``filtered_short`` array (visible in the response for
   debugging but not promoted to the primary candidates list).
7. Sort candidates by (bbox.y0, bbox.x0, first source items_hash).

Schema version: pdf-extraction-routes-1.

Authoritative design: pivot reset plan §3 (E2b "route candidate
grouping") + ODOT_TULSA strategy report §6 (2026-05-26).
"""

from __future__ import annotations

import math
from typing import Any, Dict, Final, List, Optional, Tuple


SCHEMA_VERSION: Final[str] = "pdf-extraction-routes-1"
SOURCE_SCHEMA: Final[str] = "pdf-extraction-classified-1"
RAW_SOURCE_SCHEMA: Final[str] = "pdf-extraction-raw-1"
PARAMETERS_VERSION: Final[str] = "v1"

_DEFAULT_BUCKET: Final[str] = "proposed_red"
_DEFAULT_ENDPOINT_EPS_PT: Final[float] = 2.0
_DEFAULT_MIN_LENGTH_PT: Final[float] = 20.0

# Safety caps so a pathological page can't blow up the response.
_MAX_CANDIDATES: Final[int] = 5_000
_MAX_FILTERED_SHORT: Final[int] = 5_000

# Float precision matches E1 / E2a for end-to-end consistency.
_FLOAT_DECIMALS: Final[int] = 3

# Dominant-orientation thresholds.  ratio = bbox_width / bbox_height.
# Anything outside this band is "mixed" / "diagonal".  These are
# deterministic and operator-tunable in a future v2.
_HORIZONTAL_RATIO_MIN: Final[float] = 2.0
_VERTICAL_RATIO_MAX: Final[float] = 0.5


# ---------------------------------------------------------------------------
# Public errors
# ---------------------------------------------------------------------------

class PdfExtractionRoutesError(Exception):
    """Raised on schema mismatch."""


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _r(v: Any) -> float:
    try:
        return round(float(v), _FLOAT_DECIMALS)
    except (TypeError, ValueError):
        return 0.0


def _safe_xy(p: Any) -> Optional[Tuple[float, float]]:
    """Coerce a 2-list / 2-tuple to (x, y) floats.  None on failure."""
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


def _distance(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


# ---------------------------------------------------------------------------
# Endpoint + length extraction from raw items list
# ---------------------------------------------------------------------------

def _path_endpoints_and_length(
    items: List[Any], endpoint_eps_pt: float,
) -> Tuple[Optional[Tuple[float, float]], Optional[Tuple[float, float]], float, int, bool]:
    """Return (start, end, total_length_pt, segment_count, closed).

    * start / end are (x, y) of the path's traversal endpoints, or None
      for closed shapes.
    * total_length_pt sums euclidean segment lengths across line +
      chord-approximated curve segments + rectangle perimeters.
    * segment_count is the number of line/curve/rect/quad ops.
    * closed is True if the path is a closed shape (any re/qu op, OR
      the line-chain start == end within endpoint_eps_pt).
    """
    if not isinstance(items, list) or not items:
        return None, None, 0.0, 0, False

    has_closed_op = False
    start: Optional[Tuple[float, float]] = None
    end: Optional[Tuple[float, float]] = None
    total_length = 0.0
    segment_count = 0

    for it in items:
        if not isinstance(it, (list, tuple)) or not it:
            continue
        op = it[0]
        segment_count += 1
        if op == "l" and len(it) >= 3:
            p1 = _safe_xy(it[1])
            p2 = _safe_xy(it[2])
            if p1 is None or p2 is None:
                continue
            if start is None:
                start = p1
            end = p2
            total_length += _distance(p1, p2)
        elif op == "c" and len(it) >= 5:
            # Bezier curve: 4 control points.  Use chord length p1→p4
            # as an approximation for v1.  Acceptable for the route
            # candidate use case where CAD-emitted curves are short.
            p1 = _safe_xy(it[1])
            p4 = _safe_xy(it[4])
            if p1 is None or p4 is None:
                continue
            if start is None:
                start = p1
            end = p4
            total_length += _distance(p1, p4)
        elif op == "re" and len(it) >= 2:
            # Rectangle: closed shape.  Compute perimeter.
            rect = _safe_bbox(it[1])
            if rect is not None:
                rx0, ry0, rx1, ry1 = rect
                w = abs(rx1 - rx0)
                h = abs(ry1 - ry0)
                total_length += 2.0 * (w + h)
            has_closed_op = True
        elif op == "qu" and len(it) >= 5:
            # Quad: closed shape with 4 corners.  Compute perimeter.
            pts = [_safe_xy(it[i + 1]) for i in range(4)]
            if all(pt is not None for pt in pts):
                for i in range(4):
                    total_length += _distance(pts[i], pts[(i + 1) % 4])
            has_closed_op = True
        else:
            # Unknown op — preserve segment count but no geometry signal.
            segment_count -= 0  # no-op; keeps the counter explicit

    closed = has_closed_op or (
        start is not None
        and end is not None
        and _distance(start, end) <= endpoint_eps_pt
    )

    if closed:
        return None, None, _r(total_length), segment_count, True
    return start, end, _r(total_length), segment_count, False


# ---------------------------------------------------------------------------
# Union-Find (DSU)
# ---------------------------------------------------------------------------

class _UnionFind:
    def __init__(self, n: int) -> None:
        self.parent = list(range(n))
        self.rank = [0] * n

    def find(self, x: int) -> int:
        # Path compression.
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[x] != root:
            self.parent[x], x = root, self.parent[x]
        return root

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self.rank[ra] < self.rank[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        if self.rank[ra] == self.rank[rb]:
            self.rank[ra] += 1


# ---------------------------------------------------------------------------
# Orientation classification
# ---------------------------------------------------------------------------

def _dominant_orientation(bbox: Tuple[float, float, float, float]) -> str:
    w = max(0.0, bbox[2] - bbox[0])
    h = max(0.0, bbox[3] - bbox[1])
    if h <= 1e-9:
        return "horizontal" if w > 0 else "point"
    ratio = w / h
    if ratio >= _HORIZONTAL_RATIO_MIN:
        return "horizontal"
    if ratio <= _VERTICAL_RATIO_MAX:
        return "vertical"
    return "mixed"


def _union_bbox(
    a: Tuple[float, float, float, float],
    b: Tuple[float, float, float, float],
) -> Tuple[float, float, float, float]:
    return (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def group_route_candidates(
    classified_record: Dict[str, Any],
    raw_record: Optional[Dict[str, Any]] = None,
    bucket: str = _DEFAULT_BUCKET,
    endpoint_eps_pt: float = _DEFAULT_ENDPOINT_EPS_PT,
    min_length_pt: float = _DEFAULT_MIN_LENGTH_PT,
) -> Dict[str, Any]:
    """Group bucketed vector paths into candidate route polylines.

    Args:
        classified_record: an E2a ``pdf-extraction-classified-1`` page
            record (the source of the bucket assignment).
        raw_record:        an optional E1 ``pdf-extraction-raw-1`` page
            record providing true vertex geometry.  If omitted, falls
            back to bbox-corner proxies for endpoint clustering and the
            response carries ``confidence.kind="bbox_proxy"``.
        bucket:            which color bucket to group (default
            ``"proposed_red"``).
        endpoint_eps_pt:   max euclidean distance (PDF points) between
            two paths' endpoints to consider them connected.  Default 2.0.
        min_length_pt:     candidates whose total length is below this
            threshold are moved to ``filtered_short`` instead of being
            promoted to the primary candidates list.  Default 20.0.

    Returns:
        Dict matching schema ``pdf-extraction-routes-1``.

    Raises:
        PdfExtractionRoutesError if the classified record has the wrong
        schema_version, or if raw_record (when provided) has the wrong
        schema_version.  All other malformed input is tolerated.
    """
    if not isinstance(classified_record, dict):
        raise PdfExtractionRoutesError(
            f"classified_record must be a dict; got {type(classified_record).__name__}"
        )
    if classified_record.get("schema_version") != SOURCE_SCHEMA:
        raise PdfExtractionRoutesError(
            f"classified_record schema_version must be {SOURCE_SCHEMA!r}; "
            f"got {classified_record.get('schema_version')!r}"
        )
    if raw_record is not None:
        if not isinstance(raw_record, dict):
            raise PdfExtractionRoutesError(
                f"raw_record must be a dict if provided; got {type(raw_record).__name__}"
            )
        if raw_record.get("schema_version") != RAW_SOURCE_SCHEMA:
            raise PdfExtractionRoutesError(
                f"raw_record schema_version must be {RAW_SOURCE_SCHEMA!r}; "
                f"got {raw_record.get('schema_version')!r}"
            )

    # Validate parameters (defensive against silly inputs).
    if not isinstance(endpoint_eps_pt, (int, float)) or endpoint_eps_pt < 0:
        endpoint_eps_pt = _DEFAULT_ENDPOINT_EPS_PT
    if not isinstance(min_length_pt, (int, float)) or min_length_pt < 0:
        min_length_pt = _DEFAULT_MIN_LENGTH_PT
    endpoint_eps_pt = float(endpoint_eps_pt)
    min_length_pt = float(min_length_pt)

    bucket_name = str(bucket) if bucket else _DEFAULT_BUCKET
    color_buckets = classified_record.get("color_buckets") or {}
    bucket_entries = color_buckets.get(bucket_name) or []
    if not isinstance(bucket_entries, list):
        bucket_entries = []

    # Build raw items lookup by items_hash if raw_record is provided.
    raw_items_by_hash: Dict[str, List[Any]] = {}
    if raw_record is not None:
        for p in (raw_record.get("vector_paths") or []):
            if not isinstance(p, dict):
                continue
            h = p.get("items_hash")
            if isinstance(h, str) and h:
                raw_items_by_hash[h] = p.get("items") or []

    # ──── Per-path endpoint + length resolution ─────────────────────────
    # Each entry: {items_hash, bbox, start, end, length, segment_count,
    #              closed, bbox_proxy_used, has_geometry}
    per_path: List[Dict[str, Any]] = []
    matched_raw = 0
    unmatched_raw = 0
    for entry in bucket_entries:
        if not isinstance(entry, dict):
            continue
        h = entry.get("items_hash")
        bbox = _safe_bbox(entry.get("bbox"))
        if not isinstance(h, str) or not h or bbox is None:
            # No identity or no bbox → skip; cannot cluster meaningfully.
            continue
        items = raw_items_by_hash.get(h)
        start: Optional[Tuple[float, float]] = None
        end: Optional[Tuple[float, float]] = None
        length = 0.0
        segment_count = 0
        closed = False
        bbox_proxy_used = False
        has_geometry = False
        if items:
            matched_raw += 1
            has_geometry = True
            start, end, length, segment_count, closed = _path_endpoints_and_length(
                items, endpoint_eps_pt
            )
        else:
            # Fall back to bbox-corner proxies.  Use opposite corners
            # (x0,y0) and (x1,y1) as a coarse proxy for "endpoints" of
            # the bbox's diagonal.  Length proxy = bbox diagonal length.
            unmatched_raw += 1
            bbox_proxy_used = True
            start = (bbox[0], bbox[1])
            end = (bbox[2], bbox[3])
            length = _distance(start, end)
            segment_count = 0
            closed = False
        per_path.append({
            "items_hash":      h,
            "bbox":            bbox,
            "start":           start,
            "end":             end,
            "length":          _r(length),
            "segment_count":   segment_count,
            "closed":          closed,
            "bbox_proxy_used": bbox_proxy_used,
            "has_geometry":    has_geometry,
        })

    # ──── Connected-component grouping via union-find ───────────────────
    n = len(per_path)
    uf = _UnionFind(n)
    # O(N²) endpoint proximity check.  Per-bucket cap from E2a (~10K)
    # bounds N; typical ODOT plan-sheet proposed_red bucket is ~200.
    eps = endpoint_eps_pt
    for i in range(n):
        ai = per_path[i]
        if ai["closed"]:
            continue  # Closed shapes don't connect to others by endpoints.
        ai_start = ai["start"]
        ai_end = ai["end"]
        for j in range(i + 1, n):
            aj = per_path[j]
            if aj["closed"]:
                continue
            aj_start = aj["start"]
            aj_end = aj["end"]
            # 4 endpoint-to-endpoint distance checks.
            if (
                (ai_start is not None and aj_start is not None
                 and _distance(ai_start, aj_start) <= eps)
                or (ai_start is not None and aj_end is not None
                    and _distance(ai_start, aj_end) <= eps)
                or (ai_end is not None and aj_start is not None
                    and _distance(ai_end, aj_start) <= eps)
                or (ai_end is not None and aj_end is not None
                    and _distance(ai_end, aj_end) <= eps)
            ):
                uf.union(i, j)

    # ──── Assemble candidates per connected component ───────────────────
    components: Dict[int, List[int]] = {}
    for i in range(n):
        root = uf.find(i)
        components.setdefault(root, []).append(i)

    candidates_raw: List[Dict[str, Any]] = []
    for root, members in components.items():
        if not members:
            continue
        # Build candidate aggregates.
        paths = [per_path[i] for i in members]
        source_hashes = sorted({p["items_hash"] for p in paths})
        path_count = len(paths)
        segment_count = sum(p["segment_count"] for p in paths)
        total_length = _r(sum(p["length"] for p in paths))
        # Bbox union.
        b0, b1, b2, b3 = paths[0]["bbox"]
        bbox = (b0, b1, b2, b3)
        for p in paths[1:]:
            bbox = _union_bbox(bbox, p["bbox"])
        bbox_list = [_r(bbox[0]), _r(bbox[1]), _r(bbox[2]), _r(bbox[3])]
        # Free endpoints = endpoints of any path in the group that do NOT
        # have any neighbor in this same group within eps.
        all_endpoints: List[Tuple[float, float]] = []
        for p in paths:
            if p["closed"]:
                continue
            if p["start"] is not None:
                all_endpoints.append(p["start"])
            if p["end"] is not None:
                all_endpoints.append(p["end"])
        free_endpoints: List[List[float]] = []
        for k, ep in enumerate(all_endpoints):
            # Count occurrences of points within eps of this one
            # (including itself).  Anything > 1 means at least one
            # other endpoint shares this junction → not free.
            neighbors = sum(
                1 for k2, ep2 in enumerate(all_endpoints)
                if k2 != k and _distance(ep, ep2) <= eps
            )
            if neighbors == 0:
                free_endpoints.append([_r(ep[0]), _r(ep[1])])
        # De-dup free_endpoints within eps so we don't double-list the
        # same physical free end if the source path was split into
        # adjacent segments.
        unique_free: List[List[float]] = []
        for fe in free_endpoints:
            already = any(
                _distance((fe[0], fe[1]), (u[0], u[1])) <= eps for u in unique_free
            )
            if not already:
                unique_free.append(fe)

        orientation = _dominant_orientation(bbox)
        # Confidence kind:
        any_bbox_proxy = any(p["bbox_proxy_used"] for p in paths)
        all_closed = all(p["closed"] for p in paths)
        if any_bbox_proxy:
            kind = "bbox_proxy"
        elif all_closed:
            kind = "closed_shape_group"
        elif path_count == 1:
            kind = "single_path"
        else:
            kind = "multi_path_connected"

        candidates_raw.append({
            "source_items_hashes": source_hashes,
            "path_count":          path_count,
            "segment_count":       segment_count,
            "bbox":                bbox_list,
            "total_length_pt":     total_length,
            "free_endpoints":      unique_free,
            "dominant_orientation": orientation,
            "confidence": {
                "kind": kind,
                "free_endpoint_count": len(unique_free),
            },
        })

    # Sort BEFORE filtering so candidate_id assignment is deterministic.
    candidates_raw.sort(key=lambda c: (
        c["bbox"][1],
        c["bbox"][0],
        c["source_items_hashes"][0] if c["source_items_hashes"] else "",
    ))

    # Apply min-length filter.
    candidates: List[Dict[str, Any]] = []
    filtered_short: List[Dict[str, Any]] = []
    next_id = 0
    for cand in candidates_raw:
        if cand["total_length_pt"] < min_length_pt:
            if len(filtered_short) >= _MAX_FILTERED_SHORT:
                continue
            filtered_short.append({
                "source_items_hashes": cand["source_items_hashes"],
                "total_length_pt":     cand["total_length_pt"],
            })
            continue
        if len(candidates) >= _MAX_CANDIDATES:
            continue
        cand_with_id = {"candidate_id": f"rc_{next_id:04d}", **cand}
        candidates.append(cand_with_id)
        next_id += 1

    # ──── Assemble output envelope ──────────────────────────────────────
    page_size_px = classified_record.get("page_size_px") or [0.0, 0.0]
    try:
        page_w = _r(page_size_px[0])
        page_h = _r(page_size_px[1])
    except (TypeError, IndexError):
        page_w = page_h = 0.0

    return {
        "schema_version":         SCHEMA_VERSION,
        "source_schema_version":  SOURCE_SCHEMA,
        "raw_schema_version":     RAW_SOURCE_SCHEMA,
        "page_index":             classified_record.get("page_index"),
        "page_number":            classified_record.get("page_number"),
        "page_size_px":           [page_w, page_h],
        "page_rotation":          int(classified_record.get("page_rotation") or 0),
        "bucket":                 bucket_name,
        "parameters": {
            "version":          PARAMETERS_VERSION,
            "endpoint_eps_pt":  _r(endpoint_eps_pt),
            "min_length_pt":    _r(min_length_pt),
            "max_candidates":   _MAX_CANDIDATES,
        },
        "route_candidates": candidates,
        "filtered_short":   filtered_short,
        "meta": {
            "input_path_count":      len(bucket_entries),
            "matched_raw_paths":     matched_raw,
            "unmatched_raw_paths":   unmatched_raw,
            "candidate_count":       len(candidates),
            "filtered_short_count":  len(filtered_short),
            "raw_record_provided":   raw_record is not None,
        },
    }
