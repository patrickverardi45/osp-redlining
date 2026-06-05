"""Pure composition of the PDF↔KMZ bridge candidate REVIEW block.

Composes the inert bridge pipeline — route-index extractor + AP→feature_id resolver + identity
index adapter + bridge builder — into a single read-only, DRAW-FREE block for the MRQ response
(``pdf_redline_bridge_candidates``). It is review/debug only:

  * **No rendering, no map geometry, no coordinates.** Each emitted candidate is re-validated with
    ``pdf_redline_bridge.validate_bridge_candidate`` which REJECTS any world/geometry key
    (lat/lon/coord/coords/geometry/segments/polyline). Invalid candidates are dropped, not exposed.
  * **Identity index source:** ``kmz_xref.ap_map`` + render feature ids when an ap_map is supplied
    (offline/scratch); otherwise the AP→feature_id resolver output (``render_only``) live. Never a
    coordinate or nearest-feature join.
  * **Never raises.** Missing/empty inputs -> empty ``candidates`` + ``blockers`` diagnostics.

INERT: imported by the MRQ endpoint only behind the default-OFF ``TRUELINE_PDF_KMZ_BRIDGE_BUILDER``
flag. Pure stdlib + the bridge modules; no fitz, no ``main`` import, no I/O, no endpoint.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence

from app.core import pdf_redline_bridge as _bridge
from app.core import pdf_redline_bridge_builder as _builder
from app.core import pdf_kmz_identity_index as _identity_index
from app.core import pdf_kmz_feature_resolver as _resolver
from app.core import pdf_bridge_route_index as _route_index

SCHEMA_VERSION = "pdf-redline-bridge-candidates-1"
FLAG = "TRUELINE_PDF_KMZ_BRIDGE_BUILDER"


def _empty_block(blockers: Sequence[str], session_id: Optional[str] = None) -> Dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "flag": FLAG,
        "session_id": session_id,
        "candidates": [],
        "counts_by_status": {},
        "identity_index": {"source": "none", "size": 0, "ambiguous": 0},
        "route_index": {"size": 0, "ambiguous": 0},
        "inputs": {"pdf_first_cards": 0, "mrq_rows": 0, "render_features": 0, "ap_map_entries": 0},
        "blockers": list(blockers),
        "warnings": [],
    }


def _card_count(evidence: Any) -> int:
    if not isinstance(evidence, Mapping):
        return 0
    return len(evidence.get("placements") or []) + len(evidence.get("review_items") or [])


def _ambiguous_count(index: Optional[Mapping[str, Any]]) -> int:
    return sum(1 for e in (index or {}).values()
              if isinstance(e, Mapping) and e.get("ambiguous"))


def assemble_bridge_candidates(
    *,
    pdf_first_evidence: Any,
    mrq_payload: Any = None,
    kmz_render_payload: Any = None,
    kmz_xref: Any = None,
    session_id: Optional[str] = None,
    pdf_plan_id: Optional[str] = None,
    created_from_flags: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Build the read-only ``pdf_redline_bridge_candidates`` block. Never raises; missing inputs
    yield empty candidates + blockers. Output carries NO world geometry (validated)."""
    try:
        blockers: List[str] = []
        warnings: List[str] = []

        # 1) route index (MRQ matcher-selected route ids; identity/data only) ------------------
        route_index = _route_index.extract_route_index(mrq_payload) if mrq_payload is not None else {}
        route_by_log = _route_index.to_route_id_by_log(route_index)
        _rows = (mrq_payload.get("rows") if isinstance(mrq_payload, Mapping)
                 else mrq_payload if isinstance(mrq_payload, list) else [])
        mrq_rows = len(_rows or [])

        # 2) identity index: render_only (resolver) by default; kmz_xref+render when ap_map present
        resolved = (_resolver.resolve_render_feature_ids(kmz_render_payload)
                    if kmz_render_payload is not None else {})
        render_features = (sum(len(kmz_render_payload.get(k) or [])
                               for k in ("points", "lines", "polygons"))
                           if isinstance(kmz_render_payload, Mapping) else 0)
        ap_map = kmz_xref.get("ap_map") if isinstance(kmz_xref, Mapping) else None
        ap_map_entries = len(ap_map) if isinstance(ap_map, Mapping) else 0
        if ap_map_entries:
            identity_index = _identity_index.build_identity_index(
                kmz_xref, feature_id_by_ap=_resolver.to_feature_id_by_ap(resolved))
            index_source = "kmz_xref+render"
        elif resolved:
            identity_index = resolved          # resolver output IS a canonical-keyed identity index
            index_source = "render_only"
        else:
            identity_index = {}
            index_source = "none"

        # 3) diagnostics / blockers ------------------------------------------------------------
        cards = _card_count(pdf_first_evidence)
        if not cards:
            blockers.append("no_pdf_first_evidence_cards")
        if not render_features and not ap_map_entries:
            blockers.append("no_kmz_render_features")
        if not identity_index:
            blockers.append("no_identity_index")
        if not route_by_log:
            blockers.append("no_route_index")

        # 4) build candidates (pure; identity-only, draw-free) ---------------------------------
        candidates = _builder.build_candidates_from_evidence(
            pdf_first_evidence if isinstance(pdf_first_evidence, Mapping) else {},
            identity_index,
            session_id=session_id, pdf_plan_id=pdf_plan_id,
            route_id_by_log=route_by_log, created_from_flags=created_from_flags,
        )

        # 5) DEFENSIVE: drop any candidate that fails validation (e.g. a stray world key) -------
        valid: List[Dict[str, Any]] = []
        for c in candidates:
            ok, errs = _bridge.validate_bridge_candidate(c)
            if ok:
                valid.append(c)
            else:
                warnings.append("dropped_invalid_candidate:%s" % (errs[0] if errs else "unknown"))

        counts: Dict[str, int] = {}
        for c in valid:
            st = str(c.get("status") or "unknown")
            counts[st] = counts.get(st, 0) + 1

        return {
            "schema_version": SCHEMA_VERSION,
            "flag": FLAG,
            "session_id": session_id,
            "candidates": valid,
            "counts_by_status": counts,
            "identity_index": {"source": index_source, "size": len(identity_index),
                               "ambiguous": _ambiguous_count(identity_index)},
            "route_index": {"size": len(route_index), "ambiguous": _ambiguous_count(route_index)},
            "inputs": {"pdf_first_cards": cards, "mrq_rows": mrq_rows,
                       "render_features": render_features, "ap_map_entries": ap_map_entries},
            "blockers": blockers,
            "warnings": warnings,
        }
    except Exception as exc:  # never break the MRQ response
        return _empty_block(["assembler_error:%s" % type(exc).__name__], session_id)
