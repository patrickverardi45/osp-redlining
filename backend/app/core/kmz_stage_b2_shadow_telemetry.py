"""KMZ Hardening Stage B2b — shadow telemetry writer.

Append-only JSONL writer that persists one row per (session, plan_id, sheet)
when the B2b shadow flag is enabled. Mirrors the PT.ACT R3.g
`_append_plausibility_shadow_row` pattern exactly: safe-failure, size-trigger
trim, schema-versioned rows, no input mutation.

Stage B2b is OBSERVATION ONLY. This module never mutates routing state,
never invokes the matching engine, never calls into score/select/filter
helpers. It transcribes already-computed derive_print_to_sheet_streets +
compare_derived_to_constant output into a JSONL row.

JSONL target: <uploads_dir>/kmz_stage_b2_shadow.jsonl
Schema version: kmz-stage-b2-shadow-1

DO NOT IMPORT FROM main.py. DO NOT TOUCH STATE.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


SCHEMA_VERSION = "kmz-stage-b2-shadow-2"
# Schema history:
#   kmz-stage-b2-shadow-1 (shipped at 05572a2 with B2b)
#   kmz-stage-b2-shadow-2 (B2b.1) — additive per_page fields:
#     `tier_a_count`, `length_cap_drops`, `filler_ratio_drops`,
#     `single_letter_drops`, `reverse_text_indicators`. All pre-existing
#     fields preserved with identical semantics. Readers of v1 can ignore
#     the new fields safely.

# Telemetry file shape constants. Mirror PT.ACT R3.g constraints.
DEFAULT_MAX_ROWS = 5000
DEFAULT_TRIM_TRIGGER_BYTES = 8 * 1024 * 1024
DEFAULT_BASENAME = "kmz_stage_b2_shadow.jsonl"


def _trunc(value: Any, limit: int) -> Optional[str]:
    """Coerce value to string and truncate to limit chars. Returns None
    when value is None."""
    if value is None:
        return None
    try:
        s = str(value)
    except Exception:
        return None
    return s if len(s) <= limit else s[:limit]


def build_row(
    *,
    session_id: Optional[str],
    plan_id: Optional[str],
    source_file: Optional[str],
    per_page_records: Sequence[Dict[str, Any]],
    sheet_to_streets: Dict[int, List[str]],
    per_token_comparisons: Sequence[Dict[str, Any]],
    n_pages_total: int,
    n_pages_reverse_skipped: int,
    title_block_streets: Sequence[str],
) -> Dict[str, Any]:
    """Build one shadow-row dict in the schema `kmz-stage-b2-shadow-1`.

    Pure. Never raises. Never mutates inputs. Bounded sizes per field to
    keep JSONL lines manageable.

    `per_token_comparisons` is the per-token cascade output of
    `compare_derived_to_constant`; the caller iterates each observed token
    and accumulates the comparison dicts before passing them here.
    """
    # Bound per-page records to first 200 + last 100 to keep total row
    # manageable (real PDFs are 4-50 pages so this is rarely exercised).
    pages_bounded: List[Dict[str, Any]] = []
    if isinstance(per_page_records, (list, tuple)):
        all_records = [r for r in per_page_records if isinstance(r, dict)]
        if len(all_records) <= 300:
            pages_bounded = list(all_records)
        else:
            pages_bounded = list(all_records[:200]) + list(all_records[-100:])

    # Project per-page records into compact form (strip large fields).
    # B2b.1 — adds tier_a_count + length_cap_drops + filler_ratio_drops +
    # single_letter_drops + reverse_text_indicators alongside the existing
    # B2b fields. All B2b field names preserved for v1 -> v2 readability.
    pages_compact: List[Dict[str, Any]] = []
    for rec in pages_bounded:
        pages_compact.append({
            "page": int(rec.get("page") or 0),
            "raw_candidate_count": len(rec.get("raw_candidates") or []),
            "tier_a_count": len(rec.get("tier_a_callouts") or []),
            "filtered_count": len(rec.get("filtered_streets") or []),
            "final_count": len(rec.get("final_streets") or []),
            "reverse_text_skipped": bool(rec.get("reverse_text_skipped", False)),
            "reverse_text_indicators": list(rec.get("reverse_text_indicators") or [])[:6],
            "construction_leader_drops": int(rec.get("construction_leader_drops") or 0),
            "numeric_prefix_strips": int(rec.get("numeric_prefix_strips") or 0),
            "frequency_filter_drops": int(rec.get("frequency_filter_drops") or 0),
            "title_block_drops": int(rec.get("title_block_drops") or 0),
            "title_block_subtracted": bool(rec.get("title_block_subtracted", False)),
            "length_cap_drops": int(rec.get("length_cap_drops") or 0),
            "filler_ratio_drops": int(rec.get("filler_ratio_drops") or 0),
            "single_letter_drops": int(rec.get("single_letter_drops") or 0),
            "final_streets": list(rec.get("final_streets") or [])[:25],
        })

    # Confidence tally across per-token comparisons.
    tally = {"high": 0, "medium": 0, "low": 0, "abstain": 0, "null": 0}
    comparisons_compact: List[Dict[str, Any]] = []
    if isinstance(per_token_comparisons, (list, tuple)):
        for cmp in per_token_comparisons:
            if not isinstance(cmp, dict):
                continue
            conf = cmp.get("confidence")
            if isinstance(conf, str) and conf in tally:
                tally[conf] += 1
            comparisons_compact.append({
                "token": _trunc(cmp.get("token"), 50),
                "derived_streets": list(cmp.get("derived_streets") or [])[:10],
                "constant_streets": list(cmp.get("constant_streets") or [])[:10],
                "agreement": _trunc(cmp.get("agreement"), 100),
                "confidence": _trunc(cmp.get("confidence"), 50),
            })
    comparisons_compact = comparisons_compact[:60]

    # Sheet -> streets bounded to first 60 sheets.
    sheets_bounded: Dict[str, List[str]] = {}
    if isinstance(sheet_to_streets, dict):
        for k, v in list(sheet_to_streets.items())[:60]:
            sheets_bounded[str(k)] = list(v or [])[:15]

    row: Dict[str, Any] = {
        "schema_version":          SCHEMA_VERSION,
        "decided_at":              datetime.now(timezone.utc).isoformat(),
        "emit_id":                 uuid.uuid4().hex,
        "session_id":              _trunc(session_id, 200),
        "plan_id":                 _trunc(plan_id, 200),
        "source_file":             _trunc(source_file, 300),
        "n_pages_total":           int(n_pages_total),
        "n_pages_reverse_skipped": int(n_pages_reverse_skipped),
        "title_block_streets":     list(title_block_streets or [])[:5],
        "per_page":                pages_compact,
        "sheet_to_streets":        sheets_bounded,
        "per_token_comparisons":   comparisons_compact,
        "confidence_tally":        tally,
    }
    return row


def append_shadow_row(
    row: Dict[str, Any],
    *,
    target_path: Optional[Path] = None,
    max_rows: int = DEFAULT_MAX_ROWS,
    trim_trigger_bytes: int = DEFAULT_TRIM_TRIGGER_BYTES,
) -> bool:
    """Append a row to the kmz_stage_b2_shadow.jsonl file. Returns True on
    success, False on any failure. Never raises.

    Caller decides whether to write (i.e., the shadow flag check happens
    upstream; this function does not know about the flag — it is purely a
    write primitive).

    Size-trigger trim: after append, if the file exceeds `trim_trigger_bytes`,
    perform a single read+rewrite to keep only the most recent `max_rows`
    entries. Mirrors PT.ACT R3.g.
    """
    if not isinstance(row, dict):
        return False
    if target_path is None:
        return False
    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(row, separators=(",", ":")) + "\n"
        with open(target_path, "a", encoding="utf-8") as fh:
            fh.write(line)
    except Exception:
        return False

    try:
        size = os.path.getsize(target_path)
    except OSError:
        return True
    if size > trim_trigger_bytes:
        try:
            with open(target_path, "r", encoding="utf-8") as fh:
                lines = fh.readlines()
            if len(lines) > max_rows:
                lines = lines[-max_rows:]
                with open(target_path, "w", encoding="utf-8") as fh:
                    fh.writelines(lines)
        except Exception:
            # Trim failure is non-fatal; the row already landed.
            pass
    return True
