"""PDF Extraction E3 — auto-redline segment generation.

Takes the upstream extraction stack (E1 raw + E2b routes + E2c bindings)
plus an operator-supplied request payload that carries:

  * the confirmed ``route_candidate_id`` (operator picked one of E2b's
    candidates as the actual proposed-construction route on this page)
  * a list of bore-log-style rows or station ranges (operator-bound
    field data — NOT auto-associated from a different job)

and produces deterministic auto-redline segment SPECS — `source =
"auto_extracted"` records ready to be reviewed and (in a future
ship) persisted into the existing ``pdf-plan-segments-1`` storage.

**v1 PERSISTENCE POLICY: ALWAYS DRY-RUN.**

This module computes segment specs only.  The endpoint accepts a
``dry_run`` field for forward-compatibility, but v1 ignores its
value and never mutates the segments store.  Real persistence is
explicitly deferred to E3.1 after operator validation against
real Kelly PDFs.  This protects the existing manual + bore-log row
segment flows from any auto-extraction bug.

Hard contracts (mirrors E1 / E2a / E2b / E2c doctrine):

* Pure helper.  No STATE, no env reads, no main-module imports,
  no I/O.  Persistence (if any) is the caller's responsibility.
* No PyMuPDF dependency.  Operates entirely on the three JSON
  records produced upstream + the request payload.
* No AI/LLM.  Station validation = regex.  Coverage scoring =
  count of matched station anchors per segment range.
* Output is **suggestion-grade**, not authoritative.  Each
  segment carries a confidence + warnings; operator review is
  required before any persistence enables.
* Deterministic: same inputs → byte-identical output.
* Bounded: per-list safety caps prevent pathological payloads
  from blowing up the output.

Detection / generation rules:

* **Row validation**: each row must carry parseable
  ``start_station`` + ``end_station`` (e.g. "11+60", "STA 14+20",
  "STA. 19+54").  Rows that fail validation land in
  ``rejected_rows[]`` with a reason.
* **Range sanity**: end_station_ft must be > start_station_ft.
* **Route binding**: confirmed ``route_candidate_id`` must exist
  in ``routes_record.route_candidates``.  Otherwise the entire
  call fails with a top-level error.
* **Matched anchors**: for each generated segment, count station
  anchors from ``bindings_record.station_anchors`` that satisfy
  both: (a) ``route_candidate_id`` matches the confirmed one, and
  (b) the anchor's matched_text parses to ft within
  [start_ft, end_ft].
* **Confidence**:
    - "high":   matched_anchor_count >= 2
    - "medium": matched_anchor_count == 1 OR range_ft < 100
    - "low":    no matched anchors AND range_ft >= 100
  Confidence is a SUGGESTION, not a gate — the segment is always
  generated and surfaced.  Operator review decides acceptance.
* **Segment IDs**: deterministic ``ar_NNNN`` assigned post-sort.

Schema version: pdf-auto-redline-1.

Authoritative design: pivot reset plan §3 (E3 "auto-redline
pipeline") + E2c ship report § "Next recommended step".
"""

from __future__ import annotations

import re
from typing import Any, Dict, Final, List, Optional, Tuple


SCHEMA_VERSION: Final[str] = "pdf-auto-redline-1"
ROUTES_SOURCE_SCHEMA: Final[str] = "pdf-extraction-routes-1"
BINDINGS_SOURCE_SCHEMA: Final[str] = "pdf-extraction-bindings-1"
RAW_SOURCE_SCHEMA: Final[str] = "pdf-extraction-raw-1"
PARAMETERS_VERSION: Final[str] = "v1"

# v1 is dry-run only.  Set to True in a future ship after operator
# validation on real Kelly PDFs.
_PERSISTENCE_ENABLED_IN_V1: Final[bool] = False

# Per-list safety caps.
_MAX_GENERATED_SEGMENTS: Final[int] = 5_000
_MAX_REJECTED_ROWS: Final[int] = 5_000

_FLOAT_DECIMALS: Final[int] = 3

# Station regex: accepts "11+60", "104+25.5", "STA 11+60", "STA. 11+60".
# Captures the numeric station token only; STA prefix is optional.
_STATION_TOKEN_RE: Final = re.compile(
    r"^\s*(?:STA\.?\s+)?(\d{1,3})\+(\d{2}(?:\.\d+)?)\s*$",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class PdfAutoRedlineError(Exception):
    """Raised on schema mismatch / non-dict input / missing route candidate.

    Per-row failures (malformed station, end<start, etc.) do NOT raise —
    they surface in ``rejected_rows[]`` instead.
    """


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _r(v: Any) -> float:
    try:
        return round(float(v), _FLOAT_DECIMALS)
    except (TypeError, ValueError):
        return 0.0


def _parse_station_to_ft(s: Any) -> Optional[float]:
    """Parse a station string to feet.  Returns None for malformed input.

    Accepts: "11+60", "104+25.5", "STA 11+60", "STA. 11+60", "0+00".
    Returns 100*N + P (e.g. "11+60" → 1160.0).
    """
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s)
    if not isinstance(s, str):
        return None
    m = _STATION_TOKEN_RE.match(s)
    if not m:
        return None
    try:
        n = int(m.group(1))
        p = float(m.group(2))
        return float(n) * 100.0 + p
    except (TypeError, ValueError):
        return None


def _normalize_station_label(s: Any) -> str:
    """Return the station label stripped of STA prefix + normalized
    whitespace.  Empty string if not parseable.  Preserves the
    operator's original number/decimal precision."""
    if not isinstance(s, str):
        return ""
    m = _STATION_TOKEN_RE.match(s)
    if not m:
        return ""
    return f"{int(m.group(1))}+{m.group(2)}"


def _confidence_for(matched_count: int, range_ft: float) -> str:
    if matched_count >= 2:
        return "high"
    if matched_count == 1 or range_ft < 100.0:
        return "medium"
    return "low"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def generate_auto_redline_segments(
    raw_record: Dict[str, Any],
    routes_record: Dict[str, Any],
    bindings_record: Dict[str, Any],
    request_payload: Dict[str, Any],
) -> Dict[str, Any]:
    """Produce auto_extracted segment specs from extraction stack output.

    Args:
        raw_record:      E1 ``pdf-extraction-raw-1`` page record.
        routes_record:   E2b ``pdf-extraction-routes-1`` page record.
        bindings_record: E2c ``pdf-extraction-bindings-1`` page record.
        request_payload: dict carrying at least::

            {
              "route_candidate_id": "rc_0000",
              "rows": [
                {"start_station": "11+00", "end_station": "11+60",
                 "notes": "optional"}
              ],
              "dry_run": true        # optional; ignored in v1
            }

    Returns:
        Dict matching schema ``pdf-auto-redline-1``.

    Raises:
        PdfAutoRedlineError on:
          * non-dict / missing input
          * schema_version mismatch on any of the 3 source records
          * missing or unknown route_candidate_id in routes_record
          * missing or non-list ``rows`` payload field
    """
    # ──── Schema validation (raise-able) ────────────────────────────────
    for name, rec, expected in (
        ("raw_record",      raw_record,      RAW_SOURCE_SCHEMA),
        ("routes_record",   routes_record,   ROUTES_SOURCE_SCHEMA),
        ("bindings_record", bindings_record, BINDINGS_SOURCE_SCHEMA),
    ):
        if not isinstance(rec, dict):
            raise PdfAutoRedlineError(
                f"{name} must be a dict; got {type(rec).__name__}"
            )
        if rec.get("schema_version") != expected:
            raise PdfAutoRedlineError(
                f"{name} schema_version must be {expected!r}; "
                f"got {rec.get('schema_version')!r}"
            )
    if not isinstance(request_payload, dict):
        raise PdfAutoRedlineError(
            f"request_payload must be a dict; got {type(request_payload).__name__}"
        )

    # ──── Confirm route candidate ───────────────────────────────────────
    confirmed_id = str(request_payload.get("route_candidate_id") or "").strip()
    if not confirmed_id:
        raise PdfAutoRedlineError("request_payload.route_candidate_id is required.")

    candidate: Optional[Dict[str, Any]] = None
    for c in routes_record.get("route_candidates") or []:
        if isinstance(c, dict) and c.get("candidate_id") == confirmed_id:
            candidate = c
            break
    if candidate is None:
        raise PdfAutoRedlineError(
            f"route_candidate_id {confirmed_id!r} not found in routes_record. "
            f"Available: "
            f"{[c.get('candidate_id') for c in (routes_record.get('route_candidates') or []) if isinstance(c, dict)]}"
        )

    # ──── Validate rows payload ─────────────────────────────────────────
    rows = request_payload.get("rows")
    if not isinstance(rows, list):
        raise PdfAutoRedlineError(
            f"request_payload.rows must be a list; got {type(rows).__name__}"
        )

    # ──── Pre-compute the anchor pool for this route candidate ──────────
    # Collect station anchors from E2c bindings that are bound to the
    # confirmed route candidate AND whose matched_text parses to ft.
    anchor_pool: List[Dict[str, Any]] = []
    for a in bindings_record.get("station_anchors") or []:
        if not isinstance(a, dict):
            continue
        if a.get("route_candidate_id") != confirmed_id:
            continue
        ft = _parse_station_to_ft(a.get("matched_text"))
        if ft is None:
            continue
        anchor_pool.append({
            **a,
            "_station_ft": _r(ft),
        })

    available_anchor_count = len(anchor_pool)

    # ──── Per-row generation ────────────────────────────────────────────
    generated: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []

    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            rejected.append({
                "input_row_index": idx,
                "input_row":       row,
                "reason":          "row is not a dict",
                "rule_id":         "auto_redline_v1:row_shape",
            })
            continue
        start_raw = row.get("start_station")
        end_raw   = row.get("end_station")
        start_ft = _parse_station_to_ft(start_raw)
        end_ft   = _parse_station_to_ft(end_raw)
        if start_ft is None:
            rejected.append({
                "input_row_index": idx,
                "input_row":       row,
                "reason":          f"start_station unparseable: {start_raw!r}",
                "rule_id":         "auto_redline_v1:start_station_format",
            })
            continue
        if end_ft is None:
            rejected.append({
                "input_row_index": idx,
                "input_row":       row,
                "reason":          f"end_station unparseable: {end_raw!r}",
                "rule_id":         "auto_redline_v1:end_station_format",
            })
            continue
        if end_ft <= start_ft:
            rejected.append({
                "input_row_index": idx,
                "input_row":       row,
                "reason":          (
                    f"end_station_ft ({end_ft}) must be > start_station_ft "
                    f"({start_ft})"
                ),
                "rule_id":         "auto_redline_v1:end_before_start",
            })
            continue

        range_ft = end_ft - start_ft

        # Find anchors within the [start_ft, end_ft] range.
        matched_anchors: List[Dict[str, Any]] = []
        for a in anchor_pool:
            ft = a["_station_ft"]
            if start_ft <= ft <= end_ft:
                # Drop the internal helper field before exposing
                exposed = {k: v for k, v in a.items() if not k.startswith("_")}
                matched_anchors.append(exposed)

        warnings: List[str] = []
        if len(matched_anchors) == 0:
            warnings.append("no_station_anchors_in_range")
        # Range outside route's anchor extent?  Best-effort check using
        # the anchor pool min/max if available.
        if anchor_pool:
            anchor_min = min(a["_station_ft"] for a in anchor_pool)
            anchor_max = max(a["_station_ft"] for a in anchor_pool)
            if start_ft < anchor_min or end_ft > anchor_max:
                warnings.append("range_outside_anchored_extent")

        conf_kind = _confidence_for(len(matched_anchors), range_ft)

        generated.append({
            "start_label":        _normalize_station_label(start_raw),
            "end_label":          _normalize_station_label(end_raw),
            "start_station_ft":   _r(start_ft),
            "end_station_ft":     _r(end_ft),
            "length_ft":          _r(range_ft),
            "source":             "auto_extracted",
            "route_candidate_id": confirmed_id,
            "route_candidate_bbox": list(candidate.get("bbox") or []),
            "notes":              str(row.get("notes") or "") or None,
            "matched_anchor_count": len(matched_anchors),
            "matched_anchors":    matched_anchors,
            "confidence": {
                "kind":                 conf_kind,
                "matched_anchor_count": len(matched_anchors),
                "warnings":             warnings,
            },
            "rule_id":            "auto_redline_v1",
            "provenance": {
                "input_row_index": idx,
                "input_row":       row,
            },
        })

    # ──── Apply caps ────────────────────────────────────────────────────
    generated = generated[:_MAX_GENERATED_SEGMENTS]
    rejected = rejected[:_MAX_REJECTED_ROWS]

    # ──── Deterministic sort + ID assignment ────────────────────────────
    # Sort by (start_station_ft, end_station_ft, input_row_index).
    generated.sort(key=lambda s: (
        s["start_station_ft"],
        s["end_station_ft"],
        s["provenance"]["input_row_index"],
    ))
    for i, seg in enumerate(generated):
        seg["segment_id"] = f"ar_{i:04d}"

    rejected.sort(key=lambda r: r["input_row_index"])

    # ──── Page-level warnings ───────────────────────────────────────────
    page_warnings: List[str] = []
    if available_anchor_count == 0:
        page_warnings.append("no_station_anchors_bound_to_route_candidate")
    if len(generated) == 0 and len(rows) > 0:
        page_warnings.append("no_segments_generated_all_rows_rejected")

    # Dry-run intent vs persistence policy:
    dry_run_intent = bool(request_payload.get("dry_run", True))
    persisted = False  # v1 is always dry-run regardless of intent

    # ──── Assemble envelope ─────────────────────────────────────────────
    page_size_px = raw_record.get("page_size_px") or [0.0, 0.0]
    try:
        page_w = _r(page_size_px[0])
        page_h = _r(page_size_px[1])
    except (TypeError, IndexError):
        page_w = page_h = 0.0

    return {
        "schema_version":                 SCHEMA_VERSION,
        "source_routes_schema_version":   ROUTES_SOURCE_SCHEMA,
        "source_bindings_schema_version": BINDINGS_SOURCE_SCHEMA,
        "source_raw_schema_version":      RAW_SOURCE_SCHEMA,
        "page_index":                     raw_record.get("page_index"),
        "page_number":                    raw_record.get("page_number"),
        "page_size_px":                   [page_w, page_h],
        "page_rotation":                  int(raw_record.get("page_rotation") or 0),
        "bucket":                         routes_record.get("bucket"),
        "route_candidate_id":             confirmed_id,
        "route_candidate_bbox":           list(candidate.get("bbox") or []),
        "route_candidate_total_length_pt": _r(candidate.get("total_length_pt") or 0.0),
        "parameters": {
            "version": PARAMETERS_VERSION,
            "dry_run_intent": dry_run_intent,
        },
        "generated_segments": generated,
        "rejected_rows":      rejected,
        "warnings":           page_warnings,
        "meta": {
            "input_row_count":            len(rows),
            "generated_segment_count":    len(generated),
            "rejected_row_count":         len(rejected),
            "available_anchor_count":     available_anchor_count,
            "dry_run_intent":             dry_run_intent,
            "persisted":                  persisted,
            "persistence_enabled_in_v1":  _PERSISTENCE_ENABLED_IN_V1,
            "persistence_note":           (
                "v1 NEVER persists.  dry_run_intent is recorded for "
                "forward-compatibility; real persistence ships in E3.1 "
                "after operator validation against Kelly PDFs."
            ),
        },
    }
