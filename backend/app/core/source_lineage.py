"""Owner-reviewed source-lineage evidence (Slice 1a) — additive, default-OFF.

Projects the parent/child hierarchy recorded in the OWNER-REVIEWED ledger
``_redline_data/_lineage/source_lineage.json`` into an additive, card-level
``source_lineage`` evidence block for the Match Review queue. A bore log split
from a combined daily/source form is labelled with the source log it came from
(``daily_bundle``), the parent run it is a leg of (``continuous_run``), or a
manual-review marker (``uncertain``).

EVIDENCE-ONLY. This module never changes any draw / abstain / placement /
tiering / threshold / selector / closeout / cache-output decision — it only reads
the vendored ledger and projects it. Gated default-OFF by
``TRUELINE_SOURCE_LINEAGE_EVIDENCE`` at the call site: flag OFF => block absent
=> byte-identical payload. Pure; never raises during card build.

The ledger is OWNER-REVIEWED data (never guessed); see the Slice 0 / Slice 1
plan. ``segment_draw_scope.drawable`` is always True in the ledger — drawing a
child's own segment geometry is independent of closeout promotion
(``closeout_scope``: child / parent_run / hold).
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, Mapping, Optional

SOURCE_LINEAGE_SCHEMA_VERSION = "pdf-first-source-lineage-1"
SOURCE_LINEAGE_FLAG = "TRUELINE_SOURCE_LINEAGE_EVIDENCE"

# Vendored owner-reviewed ledger, alongside the matchline / corrections ledgers
# under app/core/_redline_data.
_DEFAULT_LINEAGE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "_redline_data", "_lineage", "source_lineage.json",
)


def _stem(source_file: Any) -> Optional[str]:
    """``bore_log56.xlsx`` (or a full path) -> ``bore_log56``; None if unusable."""
    if not source_file:
        return None
    try:
        base = os.path.basename(str(source_file)).strip()
    except Exception:
        return None
    if not base:
        return None
    dot = base.rfind(".")
    stem = base[:dot] if dot > 0 else base
    return stem or None


def load_lineage(path: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    """Load the owner-reviewed ledger and return a ``child_segment_id -> record``
    index. Returns ``{}`` if the file is missing or invalid — never raises."""
    p = path or _DEFAULT_LINEAGE_PATH
    try:
        if not os.path.isfile(p):
            return {}
        with open(p, encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        return {}
    index: Dict[str, Dict[str, Any]] = {}
    try:
        source_logs = data.get("source_logs") or {}
        for parent in source_logs.values():
            if not isinstance(parent, Mapping):
                continue
            children = parent.get("children") or []
            if not isinstance(children, (list, tuple)):
                continue
            for child in children:
                if not isinstance(child, Mapping):
                    continue
                cid = child.get("child_segment_id")
                if not cid:
                    continue
                sds = child.get("segment_draw_scope")
                index[str(cid)] = {
                    "schema_version": SOURCE_LINEAGE_SCHEMA_VERSION,
                    "source_log_id": parent.get("source_log_id"),
                    "parent_kind": parent.get("parent_kind"),
                    "review_status": parent.get("review_status"),
                    "parent_view": parent.get("parent_view"),
                    "child_segment_id": child.get("child_segment_id"),
                    "safe_standalone": child.get("safe_standalone"),
                    "closeout_scope": child.get("closeout_scope"),
                    "parent_ownership_label": child.get("parent_ownership_label"),
                    "segment_draw_scope": child.get("segment_draw_scope"),
                    "owner_questions": child.get("owner_questions"),
                    "scope_note": sds.get("scope_note") if isinstance(sds, Mapping) else None,
                }
    except Exception:
        return {}
    return index


def source_lineage_evidence(
    source_file: Any,
    index: Optional[Mapping[str, Mapping[str, Any]]],
) -> Optional[Dict[str, Any]]:
    """Return the card-level ``source_lineage`` evidence block for ``source_file``'s
    bore id, or ``None`` when the id is unknown / index empty. Pure; never raises;
    returns a shallow copy so callers cannot mutate the cached index."""
    try:
        if not index:
            return None
        cid = _stem(source_file)
        if cid is None:
            return None
        rec = index.get(cid)
        if rec is None:
            return None
        return dict(rec)
    except Exception:
        return None


# ── Slice 1a.1 — direct card-level attach (additive; reuses load_lineage/projection) ──
_DEFAULT_INDEX: Optional[Dict[str, Dict[str, Any]]] = None


def index() -> Dict[str, Dict[str, Any]]:
    """Lazy-load and cache the default (vendored) lineage index. Reuses load_lineage()."""
    global _DEFAULT_INDEX
    if _DEFAULT_INDEX is None:
        _DEFAULT_INDEX = load_lineage()
    return _DEFAULT_INDEX


def _log_id_to_child_id(log_id: Any) -> Optional[str]:
    """Card log id (engine short form ``log56``) -> ledger ``child_segment_id`` (``bore_log56``).
    Tolerates an already-``bore_``-prefixed id; returns None if unusable."""
    if not log_id:
        return None
    s = str(log_id).strip()
    if not s:
        return None
    if s.startswith("bore_"):
        return s
    if s.startswith("log"):
        return "bore_" + s
    return s


def source_lineage_for_log_id(
    log_ids: Any,
    idx: Optional[Mapping[str, Mapping[str, Any]]],
) -> Optional[Dict[str, Any]]:
    """Resolve ONE source-lineage record (shallow copy) for a card's ``log_ids``.

    Returns the record only when EXACTLY ONE distinct ledger child resolves (a
    single-log card, or a group whose ids all map to the same child). Returns None
    for unknown ids or an ambiguous multi-child group. Pure; never raises."""
    try:
        if not idx or not log_ids:
            return None
        if isinstance(log_ids, (str, bytes)):
            log_ids = [log_ids]
        resolved: Dict[str, Mapping[str, Any]] = {}
        for lid in log_ids:
            cid = _log_id_to_child_id(lid)
            if cid is None:
                continue
            rec = idx.get(cid)
            if rec is not None:
                resolved[cid] = rec
        if len(resolved) != 1:
            return None  # unknown, or ambiguous multi-child group
        return dict(next(iter(resolved.values())))
    except Exception:
        return None


def attach_card_lineage(
    envelope: Any,
    idx: Optional[Mapping[str, Mapping[str, Any]]],
) -> Any:
    """Additive: attach ``card["source_lineage"]`` onto each pdf_first_evidence card
    (placements / review_items / fail_safe) whose ``log_ids`` resolve to a single
    ledger child. In-place on the card dicts; copies each record (never mutates
    ``idx``). EVIDENCE-ONLY: touches no draw / tier / status / geo field. Never
    raises; returns ``envelope`` unchanged on any error."""
    try:
        if not isinstance(envelope, dict) or not idx:
            return envelope
        for key in ("placements", "review_items", "fail_safe"):
            cards = envelope.get(key)
            if not isinstance(cards, (list, tuple)):
                continue
            for card in cards:
                if not isinstance(card, dict):
                    continue
                sl = source_lineage_for_log_id(card.get("log_ids"), idx)
                if sl is not None:
                    card["source_lineage"] = sl
    except Exception:
        return envelope
    return envelope
