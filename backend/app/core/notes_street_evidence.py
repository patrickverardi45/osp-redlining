"""Diagnostic-only helper for B-MATCH-LOC-EVIDENCE-1.

Extracts street references from bore-log notes and compares them to the
street_hints emitted by `_route_filter_for_print_tokens`. Emits a
`location_evidence_mismatch` diagnostic dict when the notes name streets that
do not appear in the print-filter hints. Pure function; never mutates inputs;
never influences route selection, scoring, or route assignment.

STREET_PATTERN is lifted byte-identical from
`backend/app/core/corridor_engine.py` so corridor_engine remains dormant
(no import; no module-load side effects). The pattern is greedy in
free-form notes context (it can consume leading filler words like
"WORKING NEAR CHERI LN"), so each raw match is trimmed by
`_trim_to_street_name` which walks the match tail-first, keeps up to 3
non-filler tokens, and stops at filler words ("AT", "NEAR", "ALONG", ...).

Deferred limitation (B-MATCH-LOC-EVIDENCE-1 sprint, 2026-05-23): bare
proper-noun street names lacking a road-type suffix (e.g. "HUISACHE" in
bore_log71 notes "LAWNDALE AVE & HUISACHE") are NOT detected because
STREET_PATTERN requires a trailing suffix. LAWNDALE AVE in the same notes
is still extracted and is sufficient to flag bore_log71. Bare-name
detection is out of scope for this sprint.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence

STREET_PATTERN = re.compile(
    r"\b(?:[NSEW]\s+)?[A-Z0-9][A-Z0-9'&.-]*(?:\s+[A-Z0-9][A-Z0-9'&.-]*)*\s+(?:ST|STREET|RD|ROAD|DR|DRIVE|LN|LANE|AVE|AVENUE|BLVD|BOULEVARD|CT|COURT|CIR|CIRCLE|TRL|TRAIL|PKWY|PARKWAY|WAY|PL|PLACE|HWY|HIGHWAY)\b",
    re.IGNORECASE,
)

_DIRECTIONS = frozenset({"N", "S", "E", "W"})

_FILLER_WORDS = frozenset({
    "AT", "ON", "ALONG", "NEAR", "BORE", "BORED", "BORING", "WORKING",
    "WORK", "AREA", "TO", "FROM", "AND", "OR", "INTERSECTION",
    "CROSSING", "BETWEEN", "THE", "OF", "FOR", "WITH", "BY", "OUT",
    "IN", "INTO", "BACK", "THEN", "ONTO", "OFF", "DOWN", "UP", "WAS",
    "ARE", "IS", "DRILLED", "INSTALLED", "REROUTED", "ACROSS",
})


def _normalize_street(value: Any) -> str:
    text = str(value or "").strip().upper()
    if not text:
        return ""
    return re.sub(r"\s+", " ", text)


def _trim_to_street_name(raw_match: str) -> Optional[str]:
    tokens = _normalize_street(raw_match).split()
    if len(tokens) < 2:
        return None
    suffix = tokens[-1]
    name_parts: List[str] = []
    for token in reversed(tokens[:-1]):
        if token in _FILLER_WORDS:
            break
        name_parts.insert(0, token)
        if len(name_parts) >= 3:
            break
    if not name_parts:
        return None
    return " ".join(name_parts + [suffix])


def extract_street_references(text: Any) -> List[str]:
    raw = str(text or "")
    if not raw:
        return []
    seen: set = set()
    ordered: List[str] = []
    for match in STREET_PATTERN.findall(raw):
        trimmed = _trim_to_street_name(match)
        if not trimmed or trimmed in seen:
            continue
        seen.add(trimmed)
        ordered.append(trimmed)
    return ordered


def compute_location_evidence_mismatch(
    group_rows: Sequence[Dict[str, Any]],
    filter_meta: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Return a diagnostic dict iff bore-log notes contain street names that
    are disjoint from the print-filter street_hints. Returns None otherwise.

    Vacuous cases that intentionally return None (no signal to emit):
    - no group rows
    - no notes content
    - no street references extractable from notes
    - filter has no street_hints to compare against
    - notes streets intersect filter streets (at least one alignment)
    """
    if not group_rows:
        return None

    notes_blob = " ".join(str((row or {}).get("notes") or "") for row in group_rows)
    notes_streets = extract_street_references(notes_blob)
    if not notes_streets:
        return None

    raw_hints = (filter_meta or {}).get("street_hints") or []
    filter_streets: List[str] = []
    seen: set = set()
    for hint in raw_hints:
        normalized = _normalize_street(hint)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        filter_streets.append(normalized)

    if not filter_streets:
        return None

    if set(notes_streets) & set(filter_streets):
        return None

    return {
        "notes_streets": list(notes_streets),
        "filter_streets": list(filter_streets),
        "severity": "REVIEW",
        "source": "bore_log_notes_vs_print_filter",
    }
