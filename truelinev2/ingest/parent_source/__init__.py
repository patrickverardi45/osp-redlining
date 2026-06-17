"""ORIGINAL_HANDWRITTEN_PARENT_SOURCE_MODEL -- resolver + render gate.

Loads the committed canonical model (parent_source_model.json, source-derived by
run_build_parent_source_model) and enforces the doctrine: the ORIGINAL handwritten bore log is the
canonical PARENT; the split rows are children/siblings/segments grouped underneath; a child entry may be
placed/rendered ONLY through its parent group, which disambiguates ownership (span + sheets) so a child
cannot claim a sibling's route -- the log48<-log50 failure.

Additive: consumes the committed JSON, never the user's dataset; no corpus/loader/census change.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import List, Optional, Tuple

_MODEL_PATH = Path(__file__).resolve().parent / "parent_source_model.json"
SPAN_REL_TOL = 0.10   # OCR/recording tolerance when comparing a drawn span to a child's recorded span


def _ft(span: Optional[str]) -> Optional[float]:
    """'0+00->5+09' (or 'STA 3+50->STA 4+08') -> abs station delta in ft; None if unparseable."""
    m = re.match(r"\s*(?:STA\s*)?(\d+)\+(\d+)\s*->\s*(?:STA\s*)?(\d+)\+(\d+)", span or "")
    if not m:
        return None
    a = int(m.group(1)) * 100 + int(m.group(2))
    b = int(m.group(3)) * 100 + int(m.group(4))
    return float(abs(b - a))


def _own_span(child_id: str, e: dict):
    """The child's CANONICAL own span (string, ft). The CORPUS split-row span is the per-child identity.
    An owner OCR correction (adj_corrected_span) refines it ONLY when it does not collide with a span-
    colliding sibling -- a correction that lands on a SIBLING's span is the parent/child mixup (the log48
    adjudication carries log50's 5+14 route); that correction is REJECTED and the corpus identity kept."""
    corpus_str = e["entry_span"]
    adj_str = e.get("adj_corrected_span")
    adj = _ft(adj_str)
    if adj is not None:
        sib_spans = [_ft(se["entry_span"]) for sib in span_collision_siblings(child_id)
                     for _, se in [entry(sib)] if se]
        collides = any(s is not None and abs(adj - s) <= SPAN_REL_TOL * s for s in sib_spans)
        if not collides:
            return adj_str, adj
    return corpus_str, _ft(corpus_str)


@lru_cache(maxsize=1)
def load_model() -> dict:
    return json.loads(_MODEL_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _index() -> dict:
    """Map BOTH log_id ('log48') and source_entry_id ('bore_log48') -> (parent_record, entry_record)."""
    out = {}
    for p in load_model()["parents"]:
        for e in p["entries"]:
            out[e["log_id"]] = (p, e)
            out[e["source_entry_id"]] = (p, e)
    return out


def entry(child_id: str) -> Tuple[Optional[dict], Optional[dict]]:
    return _index().get(child_id, (None, None))


def parent_of(child_id: str) -> Optional[str]:
    p, _ = entry(child_id)
    return p["source_parent_id"] if p else None


def is_split_family_member(child_id: str) -> bool:
    p, _ = entry(child_id)
    return bool(p and p["is_split_family"])


def siblings(child_id: str) -> List[str]:
    """Other child log_ids under the same parent (empty for a standalone bore)."""
    p, e = entry(child_id)
    if not p:
        return []
    return [o["log_id"] for o in p["entries"] if o is not e]


def span_collision_siblings(child_id: str) -> List[str]:
    """Sibling source_entry_ids that SHARE this child's start station -- the dangerous mixup case."""
    _, e = entry(child_id)
    return list(e["ownership_disambiguation"]["span_collision_with_sibling"]) if e else []


def child_owns_route(child_id: str, span_ft: Optional[float],
                     sheets) -> Tuple[bool, str]:
    """Does a candidate route (drawn span_ft + sheet set) belong to THIS child per the parent model?

    DISAMBIGUATION RULE (prevents the log48<-log50 mixup, where two children share a 0+00 start and spans
    within ~1% so closure alone cannot separate them): when the child has a span-colliding sibling, the
    candidate must NOT match a colliding sibling's recorded span BETTER than its own; and it must close the
    child's OWN recorded span on the child's OWN sheet set. Returns (ok, reason)."""
    p, e = entry(child_id)
    if not e:
        return False, f"{child_id} is not in the parent-source model (cannot place without a parent group)"
    own_str, own = _own_span(child_id, e)
    if own is None or span_ft is None:
        return False, f"{child_id}: unparseable span (own={own_str!r}, candidate={span_ft!r})"
    # 1) a colliding sibling must not match better (the core anti-mixup gate). Siblings are compared on
    # their CORPUS span (their canonical per-child identity), so a corrupted adjudication cannot hide a collision.
    for sib_id in span_collision_siblings(child_id):
        _, se = entry(sib_id)
        sib = _ft(se["entry_span"]) if se else None
        if sib is not None and abs(span_ft - sib) < abs(span_ft - own):
            return False, (f"{child_id} candidate span {span_ft:.0f}ft matches sibling {sib_id} "
                           f"({se['entry_span']}) better than its own {e['entry_span']} -- the parent group "
                           f"blocks a child from claiming a sibling's route")
    # 2) must close the child's own recorded span
    if abs(span_ft - own) > SPAN_REL_TOL * own:
        return False, (f"{child_id} candidate span {span_ft:.0f}ft does not close its own recorded span "
                       f"{own_str} (~{own:.0f}ft, tol {int(SPAN_REL_TOL*100)}%)")
    # 3) must be on the child's own sheet set (when known)
    own_sheets = set(e["sheet_context"] or [])
    if own_sheets and not (set(sheets or []) & own_sheets):
        return False, (f"{child_id} candidate sheets {list(sheets or [])} are disjoint from its own "
                       f"{sorted(own_sheets)}")
    return True, (f"{child_id} owns this route through parent {p['source_parent_id']} "
                  f"(span {own_str}, sheets {sorted(own_sheets)})")
