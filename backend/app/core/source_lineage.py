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
