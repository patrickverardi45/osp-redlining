"""Pure ``log_id`` / ``source_file`` -> ``route_id`` extractor for bridge candidate enrichment.

Reads the Match Review Queue payload (its ``rows``: each carries ``source_file`` + the matcher's
``selected_route_id`` + ``selected_route_name`` + ``group_id``) and produces a map the bridge
builder consumes as ``route_id_by_log`` to populate ``map_candidate_route_id``.

DOCTRINE (see wiki/PDF_KMZ_BRIDGE_DOCTRINE.md):
  * **Data extraction only.** The route id is the matcher's ALREADY-SELECTED ``selected_route_id``
    for that source file, copied verbatim. NEVER inferred by nearest geometry, PDF coordinates,
    or KMZ proximity.
  * **Canonical log_id.** ``log_id = os.path.splitext(source_file)[0]`` — the EXACT derivation
    ``pdf_first_adapter.group_committed_rows`` uses — so the key matches a pdf_first card's
    ``log_ids``. Both ``source_file`` and the derived ``log_id`` are emitted as keys.
  * **No guessing.** A row without a ``selected_route_id`` is omitted. When one key resolves to
    more than one DISTINCT route id, the entry is marked ``ambiguous`` (route_id nulled).

INERT: no endpoint, no UI, no rendering, no file I/O, no ``main`` import. Pure stdlib. Never raises.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Mapping, Optional

SOURCE_MRQ = "match_review_queue"


def log_id_from_source_file(source_file: Any) -> str:
    """Canonical log_id = filename without extension (mirrors ``group_committed_rows``)."""
    return os.path.splitext(str(source_file or "").strip())[0]


def _rows_of(mrq_payload: Any) -> List[Mapping[str, Any]]:
    """Accept either the full MRQ payload dict (``{"rows": [...]}``) or a bare list of rows."""
    rows = mrq_payload.get("rows") if isinstance(mrq_payload, Mapping) else mrq_payload
    return [r for r in (rows or []) if isinstance(r, Mapping)]


def extract_route_index(mrq_payload: Any) -> Dict[str, Dict[str, Any]]:
    """Build ``{key: {route_id, route_name, source, source_file, evidence_refs,
    [ambiguous, ambiguous_reason]}}`` keyed by BOTH ``source_file`` and the derived ``log_id``.

    Reads the matcher's selected route only — no geometry, no coordinates. Missing/empty payload
    -> ``{}``. Never raises."""
    buckets: Dict[str, List[Dict[str, Any]]] = {}
    for row in _rows_of(mrq_payload):
        sf = str(row.get("source_file") or "").strip()
        rid = str(row.get("selected_route_id") or "").strip()
        if not sf or not rid:
            continue  # no source file or no SELECTED route -> nothing to extract (never guess)
        rec = {
            "route_id": rid,
            "route_name": (str(row.get("selected_route_name")).strip()
                           if row.get("selected_route_name") else None),
            "source": SOURCE_MRQ,
            "source_file": sf,
            "evidence_refs": (["group:%s" % row.get("group_id")] if row.get("group_id") else []),
        }
        log_id = log_id_from_source_file(sf)
        for key in {sf, log_id}:                 # set() -> emit each distinct key once
            buckets.setdefault(key, []).append(rec)

    out: Dict[str, Dict[str, Any]] = {}
    for key, recs in buckets.items():
        distinct = {r["route_id"] for r in recs}
        base = dict(recs[0])
        if len(distinct) > 1:
            base["route_id"] = None
            base["ambiguous"] = True
            base["ambiguous_reason"] = "multiple_selected_routes_for_%s" % key
            base["evidence_refs"] = sorted({e for r in recs for e in r.get("evidence_refs", [])})
        out[key] = base
    return out


def to_route_id_by_log(route_index: Optional[Mapping[str, Mapping[str, Any]]]) -> Dict[str, str]:
    """Project to the builder's ``route_id_by_log`` shape: ``{key: route_id}`` for non-ambiguous
    entries (both ``source_file`` and ``log_id`` keys). Ambiguous / unresolved entries are skipped."""
    out: Dict[str, str] = {}
    for key, entry in (route_index or {}).items():
        if not isinstance(entry, Mapping) or entry.get("ambiguous"):
            continue
        rid = entry.get("route_id")
        if rid:
            out[str(key)] = str(rid)
    return out
