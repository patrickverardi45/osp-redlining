"""KMZ Hardening Stage B2b — derived street-hint primitives.

Pure, deterministic, safe-failure helpers for shadow-only street derivation
from engineering-plan PDF text channels. Stage B2b is OBSERVATION ONLY:
nothing here mutates STATE, calls into the matching engine, route filter,
score helper, or selection cascade. It produces a `Dict[int, List[str]]`
sheet -> streets map and a `Dict[str, Optional[List[str]]]` token -> streets
projection that the shadow telemetry writer transcribes into a JSONL row.

Design context: B2a probe (2026-05-28) measured the existing
`notes_street_evidence.STREET_PATTERN` regex against real Brenham + ODOT
PDFs. Signal exists for text-rich PDFs but the raw regex produces extensive
noise: title-block boilerplate dominance, leading filler words, reversed
text from rotated title blocks, numeric callouts glued to addresses, and
construction-phrase false positives. This module implements the denoise
pipeline B2a identified, then composes with PI.1 `derive_page_to_sheet_index`
output to produce per-sheet street sets, then projects per-token streets
parametric with `derive_print_to_sheet_index`.

Schema version: kmz-stage-b2-streets-1.

DO NOT IMPORT FROM main.py. DO NOT TOUCH STATE. DO NOT INVOKE MATCHING.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from .notes_street_evidence import (
    STREET_PATTERN,
    _FILLER_WORDS,
    _normalize_street,
)

SCHEMA_VERSION = "kmz-stage-b2-streets-1"

# ── Denoise constants ─────────────────────────────────────────────────────


# Phrases that, when they appear as the LEADING tokens of a candidate street
# match, indicate the match is construction context rather than a real street
# label (e.g., "PROPOSED CARLEE DR" — the "PROPOSED" tag belongs to the
# linework adjacent to the real street label, not part of the name).
_CONSTRUCTION_LEADERS: frozenset = frozenset({
    "PROPOSED", "PROP", "PROP.",
    "EXISTING", "EX", "EX.",
    "TEMPORARY", "TEMP", "TEMP.",
    "PERMANENT", "PERM", "PERM.",
    "CONSTRUCTION", "DETAIL", "DETAILS",
    "DEPTH", "ELEVATION", "ELEV", "ELEV.",
    "HH", "HANDHOLE", "INSTALLER", "FLOWER",
    "NEXTLINK", "VAULT", "SPLICE", "PORT",
    "NI", "AP", "PROFILE", "PLAN",
    "INSTALL", "PLACE", "TRAFFIC", "STRUCTURE",
    "ABOVE", "BELOW", "GROUND",
    "INCLUDING", "ROW",
})


# Reverse-text indicators: known engineering-context words whose REVERSED
# form appearing in extracted text suggests the page was extracted in reverse
# reading order (rotated title-block stamp, columnar disruption, etc.).
#
# B2b.1 — graduated detection. The previous B2b version skipped any page on
# a single substring hit, which discarded 50-100% of Brenham + ODOT_CREEK
# pages because `ENILHCTAM` (MATCHLINE reversed) can incidentally appear in
# column-shuffled MATCHLINE text on legitimate plan pages. New policy:
# require ≥2 DISTINCT indicators OR a single indicator appearing ≥3 times
# before declaring the page reversed. Short / typo'd indicators removed
# (TFARD too short; the prior EERHTHCTAEP was a typo of PEACHTREE-reversed
# and matched nothing real — dropped).
_REVERSE_TEXT_INDICATORS: frozenset = frozenset({
    "LANOISSEFORP",      # PROFESSIONAL reversed
    "DESOPORP",          # PROPOSED reversed
    "GNITSIXE",          # EXISTING reversed
    "ENILHCTAM",         # MATCHLINE reversed
})

_REVERSE_TEXT_DISTINCT_INDICATORS_FLOOR = 2
_REVERSE_TEXT_SAME_INDICATOR_OCCURRENCE_FLOOR = 3


# B2b.1 — expanded boilerplate vocabulary. Engineering-plan text contains
# many uppercase noun phrases that end in a road-type suffix (`...CT`, `...ST`,
# etc.) but are NOT street names. The B2b probe surfaced multi-paragraph
# captures starting with words like `DRAWING INDEX HECTOR ELIZONDO ...
# E STONE ST`. B2b.1 scans every non-final token (not just the leader) and
# uses an expanded vocabulary.
_BOILERPLATE_TOKENS: frozenset = frozenset(_CONSTRUCTION_LEADERS | {
    # Engineering-plan organization
    "DRAWING", "INDEX", "CONTRACTOR", "COORDINATOR", "MANAGER", "DIRECTOR",
    "OFFICE", "PERMIT", "PROJECT", "DEPARTMENT", "OPERATIONS",
    # Construction context (extends the leader set)
    "INSTALLATION", "INSPECTION", "MAINTENANCE", "EMERGENCY",
    "RESPONSIBILITY", "COMPLIANCE", "STAGE",
    # Geography that's never a street body
    "BRENHAM", "CITY", "COUNTY", "STATE", "TEXAS", "OKLAHOMA",
})


# B2b.1 — hard caps on candidate shape. Real US street names are short noun
# phrases; engineering-plan note blocks captured by the generic STREET_PATTERN
# can be 30+ tokens / hundreds of chars. Cap to plausible street-name shapes.
_MAX_TOKEN_COUNT = 5
_MAX_CHAR_LENGTH = 40

# B2b.1 — filler ratio. If >40% of the non-final tokens (i.e. excluding the
# road-type suffix) are common filler/glue words, the candidate is paragraph
# noise rather than a street label.
_FILLER_RATIO_THRESHOLD = 0.40

# B2b.1 — single-letter sequence rejection. Column-shuffled PDF text can
# produce sequences like `L D A N V D E R A I C ... CT` where each token is
# one or two letters glued together by spaces. Reject candidates containing
# ≥3 adjacent single-letter tokens before the suffix.
_SINGLE_LETTER_RUN_FLOOR = 3


# Frequency-filter floor: if a candidate street appears on more than this
# fraction of total pages with text, treat it as title-block boilerplate
# (project address) rather than a per-sheet street. Tuned conservatively
# against the Brenham B2a probe: "1305 E STONE ST" appeared on 23 of 43
# pages = 0.535 → filter floor of 0.70 keeps "real" per-sheet streets while
# dropping single-pdf-wide boilerplate.
DEFAULT_FREQUENCY_FILTER_FLOOR = 0.70


_NUMERIC_PREFIX_RE = re.compile(r"^\d[\d.,'\"-]*\s+")


# ── Pure denoise helpers ──────────────────────────────────────────────────


def strip_numeric_prefix(raw: str) -> str:
    """Drop a leading numeric token (e.g. address number, callout number)
    from a candidate match. Mirrors B2a finding: regex often captures
    `06 708 PEACHTREE DR` where the `06` is a callout digit glued to the
    real `708 PEACHTREE DR` address. We strip ONLY the first numeric run.
    """
    if not isinstance(raw, str):
        return ""
    return _NUMERIC_PREFIX_RE.sub("", raw, count=1).strip()


def has_construction_leader(candidate: str) -> bool:
    """Return True iff the candidate's leading non-numeric token is a
    construction-context word (PROPOSED / EXISTING / DEPTH / etc.). These
    matches are filler glued to a real label and should be dropped.

    NOTE: B2b shipped this as a leader-only check. B2b.1 keeps the function
    for back-compat but the primary boilerplate filter is now
    `has_boilerplate_anywhere`, which scans every non-final token.
    """
    if not isinstance(candidate, str):
        return False
    tokens = candidate.upper().split()
    if not tokens:
        return False
    return tokens[0] in _CONSTRUCTION_LEADERS


def has_boilerplate_anywhere(candidate: str) -> bool:
    """B2b.1 — return True iff ANY non-final token of the candidate is in
    `_BOILERPLATE_TOKENS`. Catches greedy multi-word captures like
    `DRAWING INDEX HECTOR ELIZONDO ... E STONE ST` where the original
    leader-only check missed because `DRAWING` was the first token but
    wasn't in `_CONSTRUCTION_LEADERS`. B2b.1 expanded the vocabulary AND
    expanded the scan to every word before the road-type suffix.
    """
    if not isinstance(candidate, str):
        return False
    tokens = candidate.upper().split()
    if len(tokens) < 2:
        return False
    # Inspect all tokens BEFORE the final suffix word.
    body = tokens[:-1]
    for tok in body:
        if tok in _BOILERPLATE_TOKENS:
            return True
    return False


def candidate_exceeds_size_caps(candidate: str) -> bool:
    """B2b.1 — return True iff the candidate is longer than the hard caps
    on plausible street-name shape (max 5 tokens / max 40 chars).
    """
    if not isinstance(candidate, str) or not candidate:
        return False
    if len(candidate) > _MAX_CHAR_LENGTH:
        return True
    if len(candidate.split()) > _MAX_TOKEN_COUNT:
        return True
    return False


def candidate_has_adjacent_single_letters(candidate: str) -> bool:
    """B2b.1 — return True iff the candidate body contains a run of
    >= `_SINGLE_LETTER_RUN_FLOOR` adjacent single-letter tokens. Detects
    column-shuffled PDF artifacts like `L D A N V D E R A I C ... CT`.
    """
    if not isinstance(candidate, str):
        return False
    tokens = candidate.upper().split()
    if len(tokens) < 2:
        return False
    body = tokens[:-1]
    run = 0
    for tok in body:
        if len(tok) == 1 and tok.isalpha():
            run += 1
            if run >= _SINGLE_LETTER_RUN_FLOOR:
                return True
        else:
            run = 0
    return False


def candidate_filler_ratio(candidate: str) -> float:
    """B2b.1 — return the fraction of non-final tokens that are in the
    filler/glue word set `_FILLER_WORDS`. Real street names have ≤ 0
    filler tokens in the body; paragraph noise often has >0.4.
    """
    if not isinstance(candidate, str):
        return 0.0
    tokens = candidate.upper().split()
    if len(tokens) < 2:
        return 0.0
    body = tokens[:-1]
    if not body:
        return 0.0
    filler_count = sum(1 for tok in body if tok in _FILLER_WORDS)
    return filler_count / len(body)


def page_reverse_text_signal(text: str) -> Dict[str, Any]:
    """B2b.1 — graduated reverse-text detection. Returns a dict describing
    which indicators matched, with what counts, and whether the page should
    be skipped under the policy:
      - >= 2 DISTINCT indicators, OR
      - any single indicator appearing >= 3 times.

    A single incidental substring no longer triggers a skip — that was the
    B2b over-aggression that discarded 50-100% of legitimate Brenham + ODOT
    pages because `ENILHCTAM` (MATCHLINE reversed) can appear in column-
    shuffled MATCHLINE callouts on real plan sheets.

    Returns:
      {
        "should_skip": bool,
        "indicators_matched": List[str],  # sorted, deduplicated
        "indicator_counts": Dict[str, int],
        "distinct_indicator_count": int,
        "max_indicator_occurrences": int,
      }

    Pure. Never raises. Never mutates input.
    """
    out: Dict[str, Any] = {
        "should_skip": False,
        "indicators_matched": [],
        "indicator_counts": {},
        "distinct_indicator_count": 0,
        "max_indicator_occurrences": 0,
    }
    if not isinstance(text, str) or not text:
        return out
    upper = text.upper()
    counts: Dict[str, int] = {}
    for needle in _REVERSE_TEXT_INDICATORS:
        n = upper.count(needle)
        if n > 0:
            counts[needle] = n
    if not counts:
        return out
    matched = sorted(counts.keys())
    distinct = len(matched)
    max_occ = max(counts.values())
    out["indicators_matched"] = matched
    out["indicator_counts"] = counts
    out["distinct_indicator_count"] = distinct
    out["max_indicator_occurrences"] = max_occ
    out["should_skip"] = (
        distinct >= _REVERSE_TEXT_DISTINCT_INDICATORS_FLOOR
        or max_occ >= _REVERSE_TEXT_SAME_INDICATOR_OCCURRENCE_FLOOR
    )
    return out


def page_text_is_reversed(text: str) -> bool:
    """Back-compat wrapper around `page_reverse_text_signal`. Returns the
    `should_skip` decision. Use `page_reverse_text_signal` directly for
    diagnostic detail.
    """
    return bool(page_reverse_text_signal(text).get("should_skip", False))


# ── Tier A: constrained engineering-plan callout patterns ─────────────────
#
# B2b.1 — engineering plans have predictable label conventions. Instead of
# running a greedy regex over the entire page text (Tier B), extract only
# matches that appear in known contexts: profile labels, plan labels,
# sheet-title labels, station-line callouts, matchline-adjacent labels, and
# street-and-cross patterns. These produce HIGH-context-confidence rows.

_TIER_A_STREET_BODY = (
    r"(?:[NSEW]\s+)?[A-Z][A-Z0-9'.-]{0,30}"
    r"(?:\s+[A-Z][A-Z0-9'.-]{0,30}){0,4}"
)
_TIER_A_STREET_SUFFIX = (
    r"(?:ST|STREET|RD|ROAD|DR|DRIVE|LN|LANE|AVE|AVENUE|BLVD|BOULEVARD|"
    r"CT|COURT|CIR|CIRCLE|TRL|TRAIL|PKWY|PARKWAY|WAY|PL|PLACE|HWY|HIGHWAY)"
)
_TIER_A_STREET = rf"{_TIER_A_STREET_BODY}\s+{_TIER_A_STREET_SUFFIX}\b"

_TIER_A_PATTERNS: List[Tuple[str, re.Pattern]] = [
    (
        "profile",
        re.compile(
            rf"\bPROFILE\s*[-–:]?\s*({_TIER_A_STREET})",
            re.IGNORECASE,
        ),
    ),
    (
        "plan",
        re.compile(
            rf"\bPLAN\s*[-–:]?\s*({_TIER_A_STREET})",
            re.IGNORECASE,
        ),
    ),
    (
        "sheet_title",
        re.compile(
            rf"\bSHEET\s+\d{{1,3}}(?:\s+OF\s+\d{{1,3}})?[^\n]{{0,40}}?({_TIER_A_STREET})",
            re.IGNORECASE,
        ),
    ),
    (
        "station_line",
        re.compile(
            rf"({_TIER_A_STREET})\s*[-–]\s*STA\s+\d+\+\d{{2}}",
            re.IGNORECASE,
        ),
    ),
    (
        "matchline_adjacent",
        re.compile(
            rf"\bMATCHLINE\s+STA\s+\d+\+\d{{2}}(?:/\d+\+\d{{2}})?"
            rf"\s*-?\s*SEE\s+SHEET\s+\d+[^\n]{{0,40}}?({_TIER_A_STREET})",
            re.IGNORECASE,
        ),
    ),
    (
        "street_and_cross",
        re.compile(
            rf"({_TIER_A_STREET})\s*(?:&|\bAND\b)\s*({_TIER_A_STREET})",
            re.IGNORECASE,
        ),
    ),
]


def extract_tier_a_callouts(text: str) -> List[Dict[str, str]]:
    """B2b.1 — Tier A constrained extraction. Scan the page text for
    explicit engineering-plan callout patterns (profile / plan / sheet
    title / station line / matchline-adjacent / street-and-cross). Each
    matched street is returned with its CONTEXT label so downstream
    confidence calibration can reason about HOW it was found, not just
    that it was.

    Returns a list of `{street, context, raw_match}` dicts. Streets are
    normalized via `_normalize_street`. Empty list if text is invalid or
    no patterns match.

    Pure. Never raises. Never mutates input.
    """
    out: List[Dict[str, str]] = []
    if not isinstance(text, str) or not text:
        return out
    try:
        for context_label, pat in _TIER_A_PATTERNS:
            for m in pat.finditer(text):
                groups = [g for g in m.groups() if g]
                for g in groups:
                    street = _normalize_street(g)
                    if not street:
                        continue
                    # Apply the same B2b.1 hard-cap filters even to Tier A
                    # captures so a pathological context doesn't smuggle in
                    # a noise paragraph.
                    if candidate_exceeds_size_caps(street):
                        continue
                    if has_boilerplate_anywhere(street):
                        continue
                    if candidate_has_adjacent_single_letters(street):
                        continue
                    if candidate_filler_ratio(street) > _FILLER_RATIO_THRESHOLD:
                        continue
                    out.append({
                        "street": street,
                        "context": context_label,
                        "raw_match": (m.group(0) or "")[:80],
                    })
    except Exception:
        return out
    # Dedupe while preserving first-seen order + first context.
    seen: Set[str] = set()
    deduped: List[Dict[str, str]] = []
    for item in out:
        key = item["street"]
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def extract_page_street_labels_from_text(text: str) -> Dict[str, Any]:
    """Pure helper — extract per-page street candidates with the B2b.1
    two-tier denoise pipeline.

    Pipeline:
      1. Graduated reverse-text guard (`page_reverse_text_signal`): skip
         only when ≥2 distinct indicators OR a single indicator ≥3 times.
      2. Tier A: constrained engineering-plan callouts
         (`extract_tier_a_callouts`). HIGH-context-confidence matches.
      3. Tier B: generic STREET_PATTERN over the page text, then per-
         candidate denoise: numeric-prefix strip, hard size caps, boiler-
         plate-anywhere scan, single-letter sequence rejection, filler-
         ratio cap.

    Returns a dict with (additive over B2b; existing field names preserved):
      - "raw_candidates": List[str] (Tier B raw STREET_PATTERN hits)
      - "tier_a_callouts": List[Dict] (NEW B2b.1; from `extract_tier_a_callouts`)
      - "filtered_streets": List[str] (UNION of Tier A streets + Tier B
        candidates that passed every per-page filter)
      - "reverse_text_skipped": bool
      - "reverse_text_indicators": List[str] (NEW B2b.1; the indicators
        whose presence triggered the skip, or that matched without triggering)
      - "construction_leader_drops": int (PRESERVED; now counts the
        broader boilerplate-anywhere drops in B2b.1 — same int field, same
        semantic of "boilerplate filter dropped this candidate")
      - "numeric_prefix_strips": int
      - "empty_after_strip_drops": int
      - "length_cap_drops": int (NEW B2b.1)
      - "filler_ratio_drops": int (NEW B2b.1)
      - "single_letter_drops": int (NEW B2b.1)

    Pure. Never raises. Never mutates input.
    """
    out: Dict[str, Any] = {
        "raw_candidates": [],
        "tier_a_callouts": [],
        "filtered_streets": [],
        "reverse_text_skipped": False,
        "reverse_text_indicators": [],
        "construction_leader_drops": 0,
        "numeric_prefix_strips": 0,
        "empty_after_strip_drops": 0,
        "length_cap_drops": 0,
        "filler_ratio_drops": 0,
        "single_letter_drops": 0,
    }
    if not isinstance(text, str) or not text:
        return out

    reverse_signal = page_reverse_text_signal(text)
    out["reverse_text_indicators"] = list(reverse_signal.get("indicators_matched") or [])
    if reverse_signal.get("should_skip"):
        out["reverse_text_skipped"] = True
        return out

    # ── Tier A: constrained callouts ─────────────────────────────────────
    tier_a = extract_tier_a_callouts(text)
    out["tier_a_callouts"] = tier_a
    tier_a_streets: List[str] = []
    seen_tier_a: Set[str] = set()
    for item in tier_a:
        s = item.get("street") if isinstance(item, dict) else None
        if not isinstance(s, str):
            continue
        norm = _normalize_street(s)
        if not norm or norm in seen_tier_a:
            continue
        seen_tier_a.add(norm)
        tier_a_streets.append(norm)

    # ── Tier B: generic STREET_PATTERN + hard-cap denoise ────────────────
    try:
        raw_hits = STREET_PATTERN.findall(text)
    except Exception:
        raw_hits = []

    raw_uniq: List[str] = []
    seen_raw: Set[str] = set()
    for hit in raw_hits:
        norm = _normalize_street(hit)
        if not norm:
            continue
        if norm in seen_raw:
            continue
        seen_raw.add(norm)
        raw_uniq.append(norm)
    out["raw_candidates"] = raw_uniq

    filtered: List[str] = list(tier_a_streets)
    seen_filtered: Set[str] = set(tier_a_streets)
    for candidate in raw_uniq:
        original = candidate
        stripped = strip_numeric_prefix(candidate)
        if stripped != original:
            out["numeric_prefix_strips"] += 1
        if not stripped:
            out["empty_after_strip_drops"] += 1
            continue

        # B2b.1 — hard caps first (cheapest checks).
        if candidate_exceeds_size_caps(stripped):
            out["length_cap_drops"] += 1
            continue
        if candidate_has_adjacent_single_letters(stripped):
            out["single_letter_drops"] += 1
            continue
        # B2b.1 — boilerplate-anywhere scan (replaces the prior leader-only
        # check; same int counter field name for telemetry continuity).
        if has_boilerplate_anywhere(stripped):
            out["construction_leader_drops"] += 1
            continue
        if candidate_filler_ratio(stripped) > _FILLER_RATIO_THRESHOLD:
            out["filler_ratio_drops"] += 1
            continue
        # Drop candidates whose body is entirely filler (no real street
        # noun-token left). Counted under construction_leader_drops for
        # telemetry continuity.
        tokens = stripped.upper().split()
        non_filler = [t for t in tokens[:-1] if t not in _FILLER_WORDS]
        if len(tokens) > 1 and not non_filler:
            out["construction_leader_drops"] += 1
            continue

        stripped_norm = _normalize_street(stripped)
        if not stripped_norm:
            continue
        if stripped_norm in seen_filtered:
            continue
        seen_filtered.add(stripped_norm)
        filtered.append(stripped_norm)

    out["filtered_streets"] = filtered
    return out


def compute_title_block_address_streets(
    title_block: Optional[Dict[str, Any]],
) -> List[str]:
    """Pure helper — extract the per-PDF project-address verbatim street
    tokens from an already-parsed `title_block` dict (produced by PI.4A
    `extract_title_block`). Returns the WITH-NUMBER form (e.g.,
    "1305 E STONE ST") so title-block subtraction matches the project
    address verbatim WITHOUT colliding with the legitimate per-sheet
    corridor name (e.g., "E STONE ST") that may share the post-strip form.

    Used by `apply_cross_page_denoise` to subtract per-PDF boilerplate
    from per-page RAW candidates (pre-strip) so the address number stays
    as the disambiguator.

    Pure. Never raises.
    """
    if not isinstance(title_block, dict):
        return []
    addr = title_block.get("address")
    if not isinstance(addr, str) or not addr:
        return []
    # The title_block.address is "<street>, <city, ST zip>".  Run STREET_PATTERN
    # over the whole string and collect normalized matches WITH the address
    # number prefix intact (do not strip).
    try:
        hits = STREET_PATTERN.findall(addr)
    except Exception:
        return []
    out: List[str] = []
    seen: Set[str] = set()
    for hit in hits:
        norm = _normalize_street(hit)
        if norm and norm not in seen:
            seen.add(norm)
            out.append(norm)
    return out


def apply_cross_page_denoise(
    per_page_records: Sequence[Dict[str, Any]],
    title_block_streets: Optional[Sequence[str]] = None,
    *,
    frequency_filter_floor: float = DEFAULT_FREQUENCY_FILTER_FLOOR,
) -> List[Dict[str, Any]]:
    """Apply title-block subtraction + frequency-filter denoise across pages.

    Title-block subtraction operates on the WITH-NUMBER form of the project
    address (e.g., "1305 E STONE ST"); it is checked against each page's
    `raw_candidates` (pre-strip) so the legitimate per-sheet corridor name
    (e.g., "E STONE ST" without an address number) is NOT collaterally
    dropped. A page that contains the verbatim title-block address has
    `title_block_drops` incremented, but its other `filtered_streets` are
    preserved.

    Then compute per-street page-frequency across all pages; any street that
    appears on `>= frequency_filter_floor` fraction of pages is treated as
    project-wide boilerplate and dropped. This catches title-block
    boilerplate as a second line of defense and also catches any other
    cross-page repetition (e.g., a recurring tradename in a legend).

    Returns a NEW list of per-page records with extra fields:
      - `title_block_subtracted: bool`
      - `title_block_drops: int`
      - `frequency_filter_drops: int`
      - `final_streets: List[str]` (post all denoise)

    Pure. Never raises. Never mutates inputs.
    """
    if not isinstance(per_page_records, (list, tuple)):
        return []
    # WITH-NUMBER title-block forms (e.g., "1305 E STONE ST").
    title_set: Set[str] = {
        _normalize_street(s) for s in (title_block_streets or [])
        if isinstance(s, str) and _normalize_street(s)
    }

    pages_with_text = 0
    street_page_count: Dict[str, int] = {}
    for rec in per_page_records:
        if not isinstance(rec, dict):
            continue
        if rec.get("reverse_text_skipped"):
            continue
        attempted = bool(rec.get("raw_candidates"))
        if not attempted:
            continue
        pages_with_text += 1
        for s in set(rec.get("filtered_streets") or []):
            if not isinstance(s, str):
                continue
            norm = _normalize_street(s)
            if not norm:
                continue
            street_page_count[norm] = street_page_count.get(norm, 0) + 1

    floor_count = int(max(1, round(pages_with_text * float(frequency_filter_floor))))

    out: List[Dict[str, Any]] = []
    for rec in per_page_records:
        if not isinstance(rec, dict):
            continue
        new_rec = dict(rec)
        new_rec["title_block_subtracted"] = bool(title_set)
        new_rec["title_block_drops"] = 0
        new_rec["frequency_filter_drops"] = 0
        if rec.get("reverse_text_skipped"):
            new_rec["final_streets"] = []
            out.append(new_rec)
            continue

        # Title-block subtraction: count how many of the page's RAW
        # candidates match the verbatim project-address form. Tracked for
        # observability; does NOT remove from `filtered_streets` because the
        # post-strip form of the title-block address would collide with the
        # legitimate per-sheet corridor name. Frequency filter handles the
        # actual removal of cross-page boilerplate.
        raw_candidates = rec.get("raw_candidates") or []
        for cand in raw_candidates:
            if isinstance(cand, str) and _normalize_street(cand) in title_set:
                new_rec["title_block_drops"] += 1

        final: List[str] = []
        for s in rec.get("filtered_streets") or []:
            if not isinstance(s, str):
                continue
            norm = _normalize_street(s)
            if not norm:
                continue
            page_freq = street_page_count.get(norm, 0)
            # `pages_with_text` == 0 means degenerate (no text-bearing pages);
            # bypass frequency filter. Floor is inclusive.
            # A street appearing on only ONE page cannot be boilerplate by
            # definition — boilerplate is cross-page repetition. Require
            # at least 2 page occurrences before the frequency filter can
            # drop a street.
            if (
                pages_with_text > 1
                and page_freq >= floor_count
                and page_freq >= 2
            ):
                new_rec["frequency_filter_drops"] += 1
                continue
            final.append(norm)
        new_rec["final_streets"] = final
        out.append(new_rec)
    return out


# ── PDF wrapper ────────────────────────────────────────────────────────────


def extract_page_street_labels(
    pdf_path: Any,
    title_block: Optional[Dict[str, Any]] = None,
    *,
    frequency_filter_floor: float = DEFAULT_FREQUENCY_FILTER_FLOOR,
) -> List[Dict[str, Any]]:
    """Extract per-page denoised street labels from a PDF file.

    Opens the PDF via pdfplumber, extracts text per page, runs the per-page
    denoise pipeline, then composes with `title_block` (optional, as
    produced by PI.4A `extract_title_block`) plus a frequency filter to
    drop project-address boilerplate.

    Returns a list of per-page records, 1-indexed, with the union of the
    per-page denoise fields plus the cross-page denoise fields. On any
    error (missing pdfplumber, broken PDF, OS failure), returns []. Never
    raises.

    Safe-failure. Never mutates inputs. NO STATE access.
    """
    try:
        import pdfplumber  # type: ignore
    except ImportError:
        return []

    per_page: List[Dict[str, Any]] = []
    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            for page_idx, page in enumerate(pdf.pages, 1):
                try:
                    text = page.extract_text() or ""
                except Exception:
                    text = ""
                rec = extract_page_street_labels_from_text(text)
                rec["page"] = page_idx
                per_page.append(rec)
    except Exception:
        return []

    tb_streets = compute_title_block_address_streets(title_block)
    return apply_cross_page_denoise(
        per_page, tb_streets, frequency_filter_floor=frequency_filter_floor
    )


# ── Per-sheet + per-token derivation ──────────────────────────────────────


def derive_sheet_to_streets(
    page_streets: Sequence[Dict[str, Any]],
    page_to_sheet: Optional[Dict[int, Optional[int]]],
) -> Dict[int, List[str]]:
    """Aggregate per-page denoised streets into a per-sheet map.

    Uses PI.1's `derive_page_to_sheet_index` output (1-indexed page -> sheet
    int OR None) to group page-level evidence by sheet. Streets are
    deduplicated per sheet; ordering reflects first-seen across pages.

    Pure. Never raises. Never mutates inputs.
    """
    out: Dict[int, List[str]] = {}
    if not isinstance(page_streets, (list, tuple)):
        return out
    if not isinstance(page_to_sheet, dict):
        return out
    for rec in page_streets:
        if not isinstance(rec, dict):
            continue
        page = rec.get("page")
        if not isinstance(page, int) or isinstance(page, bool):
            continue
        sheet = page_to_sheet.get(page)
        if not isinstance(sheet, int) or isinstance(sheet, bool) or sheet <= 0:
            continue
        bucket = out.setdefault(int(sheet), [])
        for s in rec.get("final_streets") or []:
            if not isinstance(s, str):
                continue
            norm = _normalize_street(s)
            if not norm:
                continue
            if norm not in bucket:
                bucket.append(norm)
    return out


def derive_print_to_sheet_streets(
    sheet_to_streets: Optional[Dict[int, List[str]]],
    observed_print_tokens: Optional[Sequence[str]],
) -> Dict[str, Optional[List[str]]]:
    """Project derived per-sheet streets onto observed print tokens.

    For each observed print token T:
      - non-str token → silently skipped
      - non-digit token → {T: None}
      - int(T) <= 0 → {T: None}
      - int(T) > 0 but not present in `sheet_to_streets` → {T: None}
      - int(T) > 0 AND has streets → {T: [street_name, ...]}

    Mirrors `derive_print_to_sheet_index` shape exactly; parametric.

    NOTE: B2b derives NO route_ids. Route_id resolution is gated behind
    Stage B3, which is explicitly not started. This function is the
    end of the B2b derivation chain.

    Pure. Never raises. Never mutates inputs.
    """
    out: Dict[str, Optional[List[str]]] = {}
    if observed_print_tokens is None:
        return out
    if isinstance(observed_print_tokens, (str, bytes)):
        return out
    try:
        iter_tokens = iter(observed_print_tokens)
    except TypeError:
        return out

    catalog: Dict[int, List[str]] = {}
    if isinstance(sheet_to_streets, dict):
        for k, v in sheet_to_streets.items():
            if isinstance(k, bool):
                continue
            if not isinstance(k, int) or k <= 0:
                continue
            if not isinstance(v, list):
                continue
            cleaned = [str(x) for x in v if isinstance(x, str) and x]
            if cleaned:
                catalog[int(k)] = cleaned

    for token in iter_tokens:
        if not isinstance(token, str):
            continue
        if not token.isdigit():
            out[token] = None
            continue
        try:
            value = int(token)
        except (TypeError, ValueError):
            out[token] = None
            continue
        if value <= 0:
            out[token] = None
            continue
        streets = catalog.get(value)
        if not streets:
            out[token] = None
        else:
            out[token] = list(streets)
    return out


# ── Constant-comparison for shadow telemetry ──────────────────────────────


def compare_derived_to_constant(
    token: str,
    derived_streets: Optional[List[str]],
    constant_entry: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Compare a per-token derived street set against the hardcoded Brenham
    constant entry. Pure, observation-only. Returns a dict describing the
    agreement / disagreement / confidence tier for one token.

    Confidence tiers:
      - "high"    : derived non-empty AND derived ⊆ constant
                    (derived agrees and is at least as specific)
      - "medium"  : derived non-empty AND nonzero intersection with constant
                    AND derived is not a subset (partial agreement)
      - "low"     : derived empty (no signal recovered)
      - "abstain" : derived non-empty AND zero intersection with constant
                    (conflict — operator review needed)
      - "null"    : neither derived nor constant has any signal

    Pure. Never raises. Never mutates inputs.
    """
    out: Dict[str, Any] = {
        "token": str(token) if isinstance(token, (str, int, float)) else "",
        "derived_streets": list(derived_streets) if isinstance(derived_streets, list) else [],
        "constant_streets": [],
        "agreement": "no_constant_entry",
        "confidence": "null",
    }
    if isinstance(constant_entry, dict):
        cs = constant_entry.get("streets") or []
        if isinstance(cs, list):
            out["constant_streets"] = [str(s).strip().upper() for s in cs if isinstance(s, str)]

    derived_set: Set[str] = {
        _normalize_street(s) for s in out["derived_streets"]
        if isinstance(s, str) and _normalize_street(s)
    }
    constant_set: Set[str] = {
        _normalize_street(s) for s in out["constant_streets"]
        if isinstance(s, str) and _normalize_street(s)
    }

    if not derived_set and not constant_set:
        out["agreement"] = "both_empty"
        out["confidence"] = "null"
        return out
    if not derived_set and constant_set:
        out["agreement"] = "derived_empty_constant_present"
        out["confidence"] = "low"
        return out
    if derived_set and not constant_set:
        out["agreement"] = "derived_present_no_constant"
        out["confidence"] = "low"
        return out
    if derived_set <= constant_set:
        out["agreement"] = "derived_subset_of_constant"
        out["confidence"] = "high"
        return out
    if derived_set & constant_set:
        out["agreement"] = "partial_overlap"
        out["confidence"] = "medium"
        return out
    out["agreement"] = "disjoint_conflict"
    out["confidence"] = "abstain"
    return out
