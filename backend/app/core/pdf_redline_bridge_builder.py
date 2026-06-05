"""Read-only, default-OFF builder for ``pdf_redline_bridge_candidate`` objects.

Consumes the canonical ``pdf_first_evidence`` payload + a caller-supplied KMZ IDENTITY INDEX
(built upstream from ``kmz_xref.ap_map`` / the KMZ render payload — the builder itself does NO
file I/O) and emits bridge candidates via :func:`pdf_redline_bridge.make_bridge_candidate`.

DOCTRINE (enforced here and by the schema validator):
  * **Identity-first.** A candidate is joined to the world ONLY by IDENTITY — the AP/HH/structure
    ``id`` (D5: PDF ``AP-120`` → KMZ TermPortHH ``120``) and/or a caller-provided route id. The
    builder does an EXACT dict lookup in ``kmz_identity_index``; it NEVER does nearest-match.
  * **No coordinates.** It reads ``geo_anchors[].id`` (identity) but NEVER ``geo_anchors[].coord``
    or any lat/lon. No world/page coordinate is ever copied into a candidate.
  * **Abstain-first.** If no identity target resolves, the candidate ``status='abstain'`` with a
    machine-readable ``abstain_reason`` and NO ``pdf_path_xy`` (no fake geometry). A wrong bridge
    is worse than none.
  * **Draw-free.** Emits data only — no PNG, no Leaflet layer, no rendering. ``pdf_path_xy`` stays
    empty; artifacts are referenced by basename in ``evidence_refs``.

INERT: no endpoint imports this. :func:`enabled` gates a FUTURE wiring site (default-OFF flag
``TRUELINE_PDF_KMZ_BRIDGE_BUILDER``); the pure functions below do not self-gate so they stay
unit-testable without env. Pure stdlib; no fitz, no ``main`` import. Never raises.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Mapping, Optional, Sequence

from app.core import pdf_redline_bridge as _bridge

BUILDER_FLAG = "TRUELINE_PDF_KMZ_BRIDGE_BUILDER"


def enabled() -> bool:
    """True only when the default-OFF flag is explicitly '1' (for the future call site)."""
    return os.getenv(BUILDER_FLAG, "0").strip() == "1"


def normalize_kmz_feature_key(structure_id: Any) -> Optional[str]:
    """Normalize a PDF structure id to the KMZ identity key (D5: TYPE:number → number).

    ``"AP-120"`` → ``"120"``; ``"120"`` → ``"120"``. Returns None when there is no id.
    Pure string identity — no geometry.
    """
    s = str(structure_id or "").strip()
    if not s:
        return None
    tail = s.rsplit("-", 1)[-1].strip()
    return tail or s


def _structure_ids(geo: Mapping[str, Any], card: Mapping[str, Any]) -> List[str]:
    """Ordered AP/HH/structure IDENTITY strings from geo_anchors (preferred) else end_structures.
    Reads ``id`` ONLY — never ``coord``."""
    ids: List[str] = []
    for a in (geo.get("geo_anchors") or []):
        if isinstance(a, Mapping):
            aid = str(a.get("id") or "").strip()
            if aid:
                ids.append(aid)
    if not ids:
        for s in (card.get("end_structures") or []):
            s = str(s or "").strip()
            if s:
                ids.append(s)
    return ids


def _evidence_refs(geo: Mapping[str, Any], card: Mapping[str, Any]) -> List[str]:
    """Collect artifact BASENAMES referenced by the card/geo — the proof a reviewer can open.
    Never includes coordinates."""
    refs: List[str] = []

    def _add(v: Any) -> None:
        if isinstance(v, str) and v.strip():
            refs.append(v.strip())
        elif isinstance(v, (list, tuple)):
            for x in v:
                if isinstance(x, str) and x.strip():
                    refs.append(x.strip())

    for block_key in ("pdf_path_trace", "pdf_redline"):
        block = geo.get(block_key)
        if isinstance(block, Mapping):
            _add(block.get("artifact_name"))
            _add(block.get("artifact_refs"))
    css = geo.get("cross_sheet_seam_stitch")
    if isinstance(css, Mapping):
        for seg in (css.get("segments") or []):
            if isinstance(seg, Mapping):
                _add(seg.get("artifact_name"))
    sc = geo.get("struct_connector")
    if isinstance(sc, Mapping):
        _add(sc.get("artifact_name"))
    _add(card.get("render_artifact_ref"))
    # de-dupe, preserve order
    seen: set = set()
    out: List[str] = []
    for r in refs:
        if r not in seen:
            seen.add(r)
            out.append(r)
    return out


def build_candidate_from_card(
    card: Mapping[str, Any],
    kmz_identity_index: Mapping[str, Any],
    *,
    session_id: Optional[str],
    pdf_plan_id: Optional[str],
    route_id_by_log: Optional[Mapping[str, str]] = None,
    created_from_flags: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Map ONE pdf_first_evidence card → a bridge candidate. Identity-only; never raises."""
    geo = card.get("geo") if isinstance(card.get("geo"), Mapping) else {}
    geo = geo or {}
    log_ids = card.get("log_ids") or []
    log_id = str(log_ids[0]).strip() if log_ids else None

    frame = geo.get("frame") if isinstance(geo.get("frame"), Mapping) else {}
    frame = frame or {}
    sheets = card.get("sheets") or []
    sheet = frame.get("sheet")
    if sheet is None and sheets:
        sheet = sheets[0]

    station_range = card.get("station_range") if isinstance(card.get("station_range"), Mapping) else {}
    station_range = station_range or {}

    ids = _structure_ids(geo, card)
    structure_start = ids[0] if ids else None
    structure_end = ids[-1] if len(ids) > 1 else None

    # IDENTITY JOIN (exact, never nearest): first structure id whose normalized key is in the index.
    kmz_feature: Optional[str] = None
    for sid in ids:
        key = normalize_kmz_feature_key(sid)
        if key and key in kmz_identity_index:
            entry = kmz_identity_index.get(key)
            kmz_feature = (entry.get("feature_id") if isinstance(entry, Mapping) and entry.get("feature_id")
                           else key)
            break

    route_id = None
    if route_id_by_log and log_id and log_id in route_id_by_log:
        route_id = str(route_id_by_log[log_id]).strip() or None

    blockers: List[str] = []
    abstain_reason: Optional[str] = None
    if not (session_id and log_id and pdf_plan_id):
        status = "blocked"
        if not log_id:
            blockers.append("no_log_id_in_card")
        if not pdf_plan_id:
            blockers.append("no_pdf_plan_id")
        if not session_id:
            blockers.append("no_session_id")
    elif route_id or kmz_feature:
        status = "candidate"
    else:
        status = "abstain"
        abstain_reason = ("no_ap_structure_identity_in_evidence" if not ids
                          else "kmz_identity_target_not_found")

    return _bridge.make_bridge_candidate(
        session_id=session_id,
        log_id=log_id,
        pdf_plan_id=pdf_plan_id,
        sheet=sheet,
        page=frame.get("page"),
        station_start=station_range.get("start"),
        station_end=station_range.get("end"),
        structure_start=structure_start,
        structure_end=structure_end,
        pdf_path_xy=None,                 # DRAW-FREE: never copy raw path geometry
        evidence_refs=_evidence_refs(geo, card),
        map_candidate_route_id=route_id,
        kmz_candidate_feature_id=kmz_feature,
        status=status,
        confidence=None,                  # not computed yet (reserved)
        blockers=blockers,
        abstain_reason=abstain_reason,
        created_from_flags=created_from_flags,
    )


def build_candidates_from_evidence(
    pdf_first_evidence: Mapping[str, Any],
    kmz_identity_index: Mapping[str, Any],
    *,
    session_id: Optional[str],
    pdf_plan_id: Optional[str] = None,
    route_id_by_log: Optional[Mapping[str, str]] = None,
    created_from_flags: Optional[Sequence[str]] = None,
) -> List[Dict[str, Any]]:
    """Build a bridge candidate per placement/review card in a pdf_first_evidence payload.

    ``pdf_plan_id`` falls back to ``source.plan_pdf`` when not given. ``fail_safe`` cards are
    excluded (no placement/evidence to bridge). Identity-only, draw-free; never raises."""
    if not isinstance(pdf_first_evidence, Mapping):
        return []
    if pdf_plan_id is None:
        src = pdf_first_evidence.get("source")
        if isinstance(src, Mapping):
            pdf_plan_id = src.get("plan_pdf") or None

    cards: List[Mapping[str, Any]] = []
    for key in ("placements", "review_items"):
        for c in (pdf_first_evidence.get(key) or []):
            if isinstance(c, Mapping):
                cards.append(c)

    out: List[Dict[str, Any]] = []
    for card in cards:
        try:
            out.append(build_candidate_from_card(
                card, kmz_identity_index,
                session_id=session_id, pdf_plan_id=pdf_plan_id,
                route_id_by_log=route_id_by_log, created_from_flags=created_from_flags,
            ))
        except Exception:
            continue  # a single malformed card must never sink the batch
    return out
