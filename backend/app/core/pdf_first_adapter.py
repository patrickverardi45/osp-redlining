"""PDF-first redline engine -> TrueLine evidence-panel adapter (Day 4).

THIN TRANSLATION SHIM. This module is the *only* TrueLine-side code that talks
to the clean-room PDF-first redline engine (the scratch package
``redline_pdf_first``). It carries NO selection / matching / geometry / scoring
intelligence of its own: it calls the engine, asks the engine to render its own
evidence-card crops, and translates the frozen ``EngineResult`` contract into a
WORKSPACE_PLAN_EVIDENCE_PANEL payload (Option B) for the same project workspace.

Hard invariants (enforced by design + the clean-room test suite):
  * The engine is IMPORT-ISOLATED. It is imported lazily from a path given by
    ``TRUELINE_PDF_FIRST_ENGINE_PATH`` (falling back to the dev scratch path).
    Importing THIS module never imports ``fitz``, never imports ``main`` or any
    sibling ``app.core`` module, and never raises if the engine is absent.
  * NOTHING raises into the caller. Every public function catches and returns a
    contained ERROR envelope (mirrors the engine's own no-raise contract), so a
    flag-gated ``main.py`` branch can never crash a request.
  * NO coordinate-snapping, NO KMZ-as-source, NO route scoring, NO manual
    placement, NO Leaflet ``route_polyline`` geometry (that is Phase 2). The
    render target stays ``evidence_card`` and the adapter NEVER emits ``coords``.
  * Tier -> surface mapping is fixed (see ``_SURFACE_BY_TIER``):
        AUTO_SELECT                    -> placements   (accepted placement evidence)
        AUTO_PLACED_REQUIRES_APPROVAL  -> review_items (named caveat)
        SHARED_SEGMENT_REVIEW          -> review_items (grouped; log_ids/group_id)
        MULTI_LOG_SEGMENT_REVIEW       -> review_items (grouped; log_ids/group_id)
        CONTINUATION_REVIEW            -> review_items (continuation caveat)
        FAIL_SAFE                      -> fail_safe    (candidates only; nothing placed)
  * Separate drill/log records are always preserved (grouping carries a
    ``records`` list of per-log cards; merging never collapses individual logs).

This module writes nothing into ``main.py``. The single flag-gated branch that
surfaces ``build_session_evidence(...)`` behind ``TRUELINE_PDF_FIRST_ENGINE=1``
is delivered as a ready-to-paste patch in the Day-4 report and applied
separately, once the upload/storage input-resolution seam is confirmed.
"""
from __future__ import annotations

import os
import sys
import tempfile
import traceback
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

SCHEMA_VERSION = "pdf-first-evidence-1"
RENDER_TARGET_EVIDENCE_CARD = "evidence_card"
GENERATED_BY = "pdf_first_adapter"

# Frozen tier names — mirror ``redline_pdf_first.contracts``. The engine's
# contract is frozen; these are kept LOCAL so that importing this module never
# imports the engine. (The clean-room test suite cross-checks them against the
# live engine by running the demonstrated logs end-to-end.)
TIER_AUTO_SELECT = "AUTO_SELECT"
TIER_AUTO_PLACED_REQUIRES_APPROVAL = "AUTO_PLACED_REQUIRES_APPROVAL"
TIER_SHARED_SEGMENT_REVIEW = "SHARED_SEGMENT_REVIEW"
TIER_MULTI_LOG_SEGMENT_REVIEW = "MULTI_LOG_SEGMENT_REVIEW"
TIER_CONTINUATION_REVIEW = "CONTINUATION_REVIEW"
TIER_FAIL_SAFE = "FAIL_SAFE"

_SURFACE_BY_TIER: Dict[str, str] = {
    TIER_AUTO_SELECT: "placement",
    TIER_AUTO_PLACED_REQUIRES_APPROVAL: "review",
    TIER_SHARED_SEGMENT_REVIEW: "review",
    TIER_MULTI_LOG_SEGMENT_REVIEW: "review",
    TIER_CONTINUATION_REVIEW: "review",
    TIER_FAIL_SAFE: "fail_safe",
}

# Map-geometry keys the Friday evidence surface must NEVER carry (Phase-2 only).
_GEOMETRY_KEYS = ("coords", "route_polyline", "lat", "lon", "latlon", "map_points")

# Vendored engine location. The clean-room ``redline_pdf_first`` package is vendored INTO this
# package's directory (``backend/app/core/redline_pdf_first``), so the engine root is simply this
# file's directory — ``import redline_pdf_first`` resolves once that dir is on sys.path (see
# ``_load_engine``). An env override (``TRUELINE_PDF_FIRST_ENGINE_PATH``) still wins, for an
# out-of-tree engine. (Was the clean-room scratch path; vendored for live-app portability.)
_DEFAULT_ENGINE_ROOT = os.path.dirname(os.path.abspath(__file__))

_engine_mod: Any = None
_engine_err: Optional[str] = None

__all__ = [
    "SCHEMA_VERSION",
    "engine_available",
    "select_and_render",
    "build_group_review",
    "build_session_evidence",
    "group_committed_rows",
    "build_session_evidence_from_rows",
    "build_session_evidence_from_committed_rows",
]


# ─────────────────────────────────────────────────────────────────────────────
# Engine loading — lazy + import-isolated + never-raises.
# ─────────────────────────────────────────────────────────────────────────────
def _load_engine() -> Tuple[Any, Optional[str]]:
    """Lazily import the clean-room engine package, import-isolated. Caches the
    module (or the error string) so repeated calls are cheap. Never raises."""
    global _engine_mod, _engine_err
    if _engine_mod is not None or _engine_err is not None:
        return _engine_mod, _engine_err
    try:
        root = (os.environ.get("TRUELINE_PDF_FIRST_ENGINE_PATH") or _DEFAULT_ENGINE_ROOT).strip()
        if root and root not in sys.path:
            sys.path.insert(0, root)
        import redline_pdf_first as eng  # lazy by intent; keeps fitz out of module import
        _engine_mod = eng
    except Exception as exc:  # missing/broken engine must not crash the caller
        _engine_err = f"{type(exc).__name__}: {exc}"
    return _engine_mod, _engine_err


def engine_available() -> bool:
    """True when the clean-room engine package imports cleanly. Never raises."""
    eng, _ = _load_engine()
    return eng is not None


# ─────────────────────────────────────────────────────────────────────────────
# Slice-B AP/structure-anchored geometry — STRICTLY flag-gated + additive.
# When ``TRUELINE_AP_ANCHORED_GEOMETRY`` is truthy the engine is handed the
# RESOLVED anchor tables so it can attach a COORD-FREE chainage frame + EXACT
# AP/SPLICE_LOC ``geo_anchors`` to each placement; we then surface that as a
# ``geo`` EVIDENCE block on the card. Flag OFF: tables are never loaded, never
# passed, never surfaced — the envelope is byte-identical. This is review-panel
# metadata ONLY: render_target stays ``evidence_card`` and NO coords/
# route_polyline/map_points top-level (map-draw) keys are ever emitted.
# ─────────────────────────────────────────────────────────────────────────────
# Vendored owner-reviewed data ledgers (anchors.json / sheet_station_model.json at the root for
# Slice-B; ``_matchline`` / ``_boc`` / ``_corrections`` subdirs for the resolver consult). An env
# override (``TRUELINE_AP_ANCHORED_ANALYSIS_DIR``) still wins. (Was the scratch _analysis path.)
_DEFAULT_ANALYSIS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_redline_data")
_anchor_tables_by_dir: Dict[str, Any] = {}


def _ap_anchored_enabled() -> bool:
    return str(os.environ.get("TRUELINE_AP_ANCHORED_GEOMETRY", "")).strip().lower() in {
        "1", "true", "yes", "on"}


def _pdf_redline_enabled() -> bool:
    """PDF redline DRAW flag. STACKS on the metadata flag (BOTH required). Flag OFF
    => no overlay rendered, no pdf_redline surfaced => envelope byte-identical."""
    if not _ap_anchored_enabled():
        return False
    return str(os.environ.get("TRUELINE_PDF_REDLINE_RENDER", "")).strip().lower() in {
        "1", "true", "yes", "on"}


def _pdf_path_trace_enabled() -> bool:
    """PDF bore-path TRACE flag. STACKS on the redline draw flag (which stacks on
    the metadata flag) — all THREE required (TRUELINE_AP_ANCHORED_GEOMETRY +
    TRUELINE_PDF_REDLINE_RENDER + TRUELINE_PDF_PATH_TRACE). OFF => no trace rendered,
    no pdf_path_trace surfaced => envelope byte-identical."""
    if not _pdf_redline_enabled():
        return False
    return str(os.environ.get("TRUELINE_PDF_PATH_TRACE", "")).strip().lower() in {
        "1", "true", "yes", "on"}


def _pdf_path_trace_dash_chain_enabled() -> bool:
    """PDF bore-path DASH-CHAIN reconstruction flag (the FOURTH, stacked on the
    other three). When ON and the base single-polyline trace is BLOCKED, the engine
    reconstructs the authored dashed run (layer + corridor + station-tick bound) ->
    REVIEW_DASH_CHAINED / READY_DASH_CHAINED. OFF => base trace only (BLOCKED) =>
    pdf_path_trace surfaced identically whether this flag is unset or '0'."""
    if not _pdf_path_trace_enabled():
        return False
    return str(os.environ.get("TRUELINE_PDF_PATH_TRACE_DASH_CHAIN", "")).strip().lower() in {
        "1", "true", "yes", "on"}


def _matchline_frame_resolver_enabled() -> bool:
    """Default-OFF resolver/correction/false-A-override consult flag (the proven scratch lane,
    ported to the live row-fed path). When unset the row-fed path applies NO source corrections
    and runs NO resolver consult, so the evidence envelope is byte-identical to pre-wiring. This
    is an INDEPENDENT switch (does NOT stack on the geometry flags), but the false-A OVERRIDE
    sub-case only engages when the geometry/path-trace flags are also on (an A trace exists to
    supersede); LIFTS of blocked/fail-safe FRAME_ONLY bores engage regardless."""
    return str(os.environ.get("TRUELINE_MATCHLINE_FRAME_RESOLVER", "")).strip().lower() in {
        "1", "true", "yes", "on"}


def _resolve_analysis_dir() -> str:
    return (os.environ.get("TRUELINE_AP_ANCHORED_ANALYSIS_DIR") or _DEFAULT_ANALYSIS_DIR).strip()


def _anchor_tables() -> Optional[Dict[str, Any]]:
    """RESOLVED anchor tables when the flag is ON, else None. Cached per dir.
    Never raises (a load failure degrades to None -> geometry-free, never a guess)."""
    if not _ap_anchored_enabled():
        return None
    d = _resolve_analysis_dir()
    if d in _anchor_tables_by_dir:
        return _anchor_tables_by_dir[d]
    tables: Optional[Dict[str, Any]] = None
    try:
        eng, _ = _load_engine()
        if eng is not None and hasattr(eng, "load_anchor_tables"):
            tables = eng.load_anchor_tables(d)
    except Exception:
        tables = None
    _anchor_tables_by_dir[d] = tables
    return tables


def _geo_block(placement: Any) -> Optional[Dict[str, Any]]:
    """Evidence-only projection of an engine ``placement``: geometry_status +
    coord-free frame + EXACT geo_anchors + evidence_trail. NOT a map-draw surface."""
    if placement is None:
        return None
    fr = getattr(placement, "frame", None)
    frame = None if fr is None else {
        "sheet": fr.sheet, "page": fr.page, "datum_ft": fr.datum_ft,
        "chainage_start_ft": fr.chainage_start_ft, "chainage_end_ft": fr.chainage_end_ft,
        "axis": fr.axis, "eqs_used": list(fr.eqs_used), "multi_sheet": fr.multi_sheet,
        "caveat": fr.caveat, "note": fr.note,
    }
    anchors = [{
        "kind": a.kind, "id": a.id, "sheet": a.sheet, "sta": a.sta,
        "coord": list(a.coord), "chainage_ft": a.chainage_ft, "pxdist": a.pxdist,
        "source": a.source, "provenance": a.provenance,
    } for a in (getattr(placement, "geo_anchors", None) or [])]
    block = {
        "geometry_status": getattr(placement, "geometry_status", None),
        "frame": frame,
        "geo_anchors": anchors,
        "drop_terminal": getattr(placement, "drop_terminal", None),
        "evidence_trail": getattr(placement, "evidence_trail", None),
    }
    # pdf_redline surfaced ONLY under the draw flag (else key absent -> byte-identical).
    # Refs reduced to basenames so no absolute server path leaves the backend.
    if _pdf_redline_enabled():
        block["pdf_redline"] = _sanitize_overlay_block(getattr(placement, "pdf_redline", None))
    # pdf_path_trace surfaced ONLY under the (stacked) path-trace flag. Page-space
    # authored run trace; never coords/KMZ. Flag OFF -> key absent -> byte-identical.
    if _pdf_path_trace_enabled():
        block["pdf_path_trace"] = _sanitize_overlay_block(getattr(placement, "pdf_path_trace", None))
    return block


# ─────────────────────────────────────────────────────────────────────────────
# Envelope construction helpers (pure translation; no decision logic).
# ─────────────────────────────────────────────────────────────────────────────
def _cards_root() -> str:
    return os.path.join(tempfile.gettempdir(), "pdf_first_cards")


def _empty_counts_by_surface() -> Dict[str, int]:
    return {"placements": 0, "review_items": 0, "fail_safe": 0}


def _error_envelope(message: str, source: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Contained ERROR result — same shape as a normal envelope, status=ERROR."""
    return {
        "schema_version": SCHEMA_VERSION,
        "engine_version": None,
        "contract_version": None,
        "render_target": RENDER_TARGET_EVIDENCE_CARD,
        "generated_by": GENERATED_BY,
        "status": "ERROR",
        "source": source or {},
        "counts_by_tier": {},
        "counts_by_surface": _empty_counts_by_surface(),
        "placements": [],
        "review_items": [],
        "fail_safe": [],
        "groups": [],
        "warnings": [f"adapter error: {message}"],
    }


def _strip_geometry(card: Dict[str, Any]) -> Dict[str, Any]:
    """Defensive guarantee: the engine never emits map geometry, but ensure the
    Phase-2 geometry keys can never leak onto the Friday evidence surface. Does
    NOT touch ``render_target`` — FAIL_SAFE cards keep ``render_target=None``
    (nothing is placed); only segment cards are pinned to ``evidence_card``."""
    for key in _GEOMETRY_KEYS:
        card.pop(key, None)
    return card


def _basename_refs(value: Any) -> Any:
    """Reduce an artifact ref (str | list | None) to basename(s) so no absolute server
    path leaves the backend; the gated artifact route (`/api/pdf-first-evidence/...`)
    re-roots the basename under the owned session dir. Pure; preserves str-vs-list
    shape; falsy passes through unchanged."""
    if not value:
        return value
    if isinstance(value, str):
        return os.path.basename(value)
    if isinstance(value, (list, tuple)):
        return [os.path.basename(v) if isinstance(v, str) else v for v in value]
    return value


def _sanitize_overlay_block(block: Any) -> Any:
    """Shallow-copy a ``pdf_redline`` / ``pdf_path_trace`` block with ``artifact_refs``
    reduced to basenames + a convenience ``artifact_name`` (first basename) for the UI.
    Does NOT mutate the engine's placement dict. Non-dicts pass through unchanged."""
    if not isinstance(block, dict):
        return block
    out = dict(block)
    refs = _basename_refs(out.get("artifact_refs"))
    if refs:
        out["artifact_refs"] = refs
        out["artifact_name"] = refs[0] if isinstance(refs, list) else refs
    return out


def _artifacts_by_segid(result: Any) -> Dict[str, Any]:
    """Index the engine's render artifacts by segment_id, PREFERRING the evidence
    card artifact (``kind == 'evidence_card'``). That artifact's payload carries the
    full card (``log_ids`` / ``segment_id`` / ``tier`` / ``station_range`` + the crop
    ``render_artifact_ref``). The overlay artifacts (``pdf_redline_overlay`` /
    ``pdf_path_trace_overlay``) carry only a ``*_ref`` payload and must NOT overwrite
    the card — their refs are surfaced through the ``geo`` block. Without this
    preference, the last-appended overlay would erase the card's identity when the
    draw/trace flags are on. Flag-OFF: only the evidence-card artifact exists, so the
    result is byte-identical."""
    out: Dict[str, Any] = {}
    for art in (getattr(result, "render_artifacts", None) or []):
        seg_id = getattr(art, "segment_id", None)
        if not seg_id:
            continue
        if seg_id not in out or getattr(art, "kind", "") == "evidence_card":
            out[seg_id] = art
    return out


def _segment_card(seg: Any, artifacts: Mapping[str, Any]) -> Dict[str, Any]:
    """Build one evidence/review card for a selected/review segment, reusing the
    engine's own card builder (so the crop ref + caveat + metadata stay canonical)."""
    art = artifacts.get(seg.segment_id)
    if art is not None and getattr(art, "payload", None):
        # The engine already built this card (incl. render_artifact_ref after crop render).
        card = dict(art.payload)
    else:
        from redline_pdf_first.render.evidence_card import build_segment_card
        card = build_segment_card(seg)
    card["surface"] = _SURFACE_BY_TIER.get(getattr(seg, "tier", ""), "review")
    card = _strip_geometry(card)
    # No raw absolute server paths in the envelope: reduce the crop artifact ref to a
    # basename (the gated artifact route re-roots it under the owned session dir).
    if card.get("render_artifact_ref"):
        card["render_artifact_ref"] = _basename_refs(card["render_artifact_ref"])
    card["render_target"] = RENDER_TARGET_EVIDENCE_CARD  # Friday surface is always evidence_card
    # Slice-B (flag-gated): attach the AP/structure-anchored geometry metadata as
    # a `geo` EVIDENCE block. OFF -> key absent -> byte-identical card.
    if _ap_anchored_enabled():
        geo = _geo_block(getattr(seg, "placement", None))
        if geo is not None:
            card["geo"] = geo
    return card


def _render_crops(result: Any, plan_pdf_path: str,
                  card_out_dir: Optional[str], sheet_offset: int) -> None:
    """Ask the engine to render its OWN highlighted evidence crops and wire
    ``render_artifact_ref``. Best-effort: a crop failure must never sink the
    envelope, so we fall back to metadata-only cards (render_artifact_ref None)."""
    out_dir = card_out_dir or _cards_root()
    try:
        from redline_pdf_first.render import crop_renderer
        crop_renderer.render_and_attach(result, plan_pdf_path, out_dir=out_dir,
                                        sheet_offset=sheet_offset)
    except Exception:
        try:
            from redline_pdf_first.render.evidence_card import attach_render_artifacts
            attach_render_artifacts(result)
        except Exception:
            pass  # leave result.render_artifacts empty; envelope still valid
    # PDF redline overlay — ONLY under the stacked draw flag. Flag OFF -> not called
    # -> placement.pdf_redline stays None -> envelope byte-identical.
    if _pdf_redline_enabled():
        try:
            from redline_pdf_first.render import redline_overlay
            redline_overlay.render_and_attach_redline(result, plan_pdf_path,
                                                      out_dir=out_dir, sheet_offset=sheet_offset)
        except Exception:
            pass
    # PDF bore-path trace — ONLY under the (stacked) path-trace flag. Flag OFF ->
    # not called -> placement.pdf_path_trace stays None -> envelope byte-identical.
    # The 4th flag (dash-chain) only changes the BLOCKED fallback; unset vs '0' is
    # byte-identical because dash_chain=False then yields the same base trace.
    if _pdf_path_trace_enabled():
        try:
            from redline_pdf_first.render import redline_overlay
            redline_overlay.render_and_attach_path_trace(
                result, plan_pdf_path, out_dir=out_dir, sheet_offset=sheet_offset,
                dash_chain=_pdf_path_trace_dash_chain_enabled())
        except Exception:
            pass


def _envelope_from_result(result: Any) -> Dict[str, Any]:
    """Translate one ``EngineResult`` into a single-log evidence envelope.
    Routes purely by per-item ``tier`` (never by which engine list it landed in)."""
    from redline_pdf_first.render.evidence_card import build_failsafe_card

    artifacts = _artifacts_by_segid(result)
    placements: List[Dict[str, Any]] = []
    review_items: List[Dict[str, Any]] = []
    fail_safe: List[Dict[str, Any]] = []
    counts_by_tier: Dict[str, int] = {}

    for seg in list(result.selected_segments) + list(result.review_items):
        tier = getattr(seg, "tier", "")
        counts_by_tier[tier] = counts_by_tier.get(tier, 0) + 1
        card = _segment_card(seg, artifacts)
        if tier == TIER_AUTO_SELECT:
            placements.append(card)
        else:
            review_items.append(card)

    for fs in result.fail_safe_items:
        tier = getattr(fs, "tier", TIER_FAIL_SAFE)
        counts_by_tier[tier] = counts_by_tier.get(tier, 0) + 1
        fail_safe.append(_strip_geometry(build_failsafe_card(fs)))

    return {
        "schema_version": SCHEMA_VERSION,
        "engine_version": getattr(result, "engine_version", None),
        "contract_version": getattr(result, "contract_version", None),
        "render_target": RENDER_TARGET_EVIDENCE_CARD,
        "generated_by": GENERATED_BY,
        "status": getattr(result, "status", "OK"),
        "source": dict(getattr(result, "source", {}) or {}),
        "counts_by_tier": counts_by_tier,
        "counts_by_surface": {
            "placements": len(placements),
            "review_items": len(review_items),
            "fail_safe": len(fail_safe),
        },
        "placements": placements,
        "review_items": review_items,
        "fail_safe": fail_safe,
        "groups": [],
        "warnings": list(getattr(result, "warnings", []) or []),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Public API.
# ─────────────────────────────────────────────────────────────────────────────
def select_and_render(bore_log_path: str, plan_pdf_path: str, *,
                      sheet_offset: int = 13,
                      card_out_dir: Optional[str] = None) -> Dict[str, Any]:
    """Run the engine on ONE bore log + plan PDF, render its evidence crops, and
    return a WORKSPACE_PLAN_EVIDENCE_PANEL envelope. Never raises."""
    source = {"bore_log": bore_log_path, "plan_pdf": plan_pdf_path}
    eng, err = _load_engine()
    if eng is None:
        return _error_envelope(f"engine unavailable ({err})", source)
    try:
        result = eng.select_redline(bore_log_path, plan_pdf_path, sheet_offset,
                                    anchor_tables=_anchor_tables())
        _render_crops(result, plan_pdf_path, card_out_dir, sheet_offset)
        return _envelope_from_result(result)
    except Exception as exc:
        detail = "".join(traceback.format_exception_only(type(exc), exc)).strip()
        return _error_envelope(detail, source)


def build_group_review(results: Sequence[Any], group_id: str = "group") -> Dict[str, Any]:
    """Translate the engine's cross-log ``grouping.classify`` verdict for a
    cluster of per-log ``EngineResult`` objects into a grouped review item.
    Carries ``group_id`` / ``log_ids`` and PRESERVES separate per-log records.
    Never raises."""
    eng, err = _load_engine()
    if eng is None:
        return {
            "group_id": group_id, "log_ids": [], "surface": "review",
            "tier": None, "kind": "ERROR",
            "caveat": {"code": "ENGINE_UNAVAILABLE", "text": err or "engine unavailable"},
            "signals": {}, "records": [],
        }
    try:
        from redline_pdf_first.rulebook import grouping
        g = grouping.classify(list(results), group_id=group_id)
        records: List[Dict[str, Any]] = []
        for r in results:
            arts = _artifacts_by_segid(r)
            for seg in list(r.selected_segments) + list(r.review_items):
                records.append(_segment_card(seg, arts))
        return {
            "group_id": g.get("group_id", group_id),
            "log_ids": list(g.get("log_ids", [])),
            "surface": "review",
            "tier": g.get("group_tier"),
            "kind": g.get("kind"),
            "caveat": {"code": g.get("kind"), "text": g.get("note")},
            "signals": {
                "shared_boxes": g.get("shared_boxes", {}),
                "parallel_pairs": g.get("parallel_pairs", []),
                "span_relations": g.get("span_relations", []),
                "false_overlaps": g.get("false_overlaps", 0),
                "per_log_tier": g.get("per_log_tier", {}),
            },
            "records": records,  # separate drill/log records preserved
        }
    except Exception as exc:
        return {
            "group_id": group_id, "log_ids": [], "surface": "review",
            "tier": None, "kind": "ERROR",
            "caveat": {"code": "GROUPING_ERROR", "text": str(exc)},
            "signals": {}, "records": [],
        }


def build_session_evidence(plan_pdf_path: str,
                           bore_logs: Sequence[Tuple[str, str]], *,
                           groups: Optional[Mapping[str, Sequence[str]]] = None,
                           sheet_offset: int = 13,
                           card_out_dir: Optional[str] = None) -> Dict[str, Any]:
    """Session-level entry for the (separately applied) ``main.py`` flag branch.

    ``bore_logs``  : sequence of ``(log_id, bore_log_path)``.
    ``groups``     : optional ``{group_id: [log_id, ...]}`` cluster definitions.

    Runs the engine per log, renders crops, merges every log's placements /
    review items / fail-safe candidates into one envelope, and appends a grouped
    review block per cluster (preserving separate per-log records). Never raises.
    """
    bore_logs = list(bore_logs or [])
    source = {"plan_pdf": plan_pdf_path, "bore_logs": [bl for _, bl in bore_logs]}
    eng, err = _load_engine()
    if eng is None:
        return _error_envelope(f"engine unavailable ({err})", source)

    placements: List[Dict[str, Any]] = []
    review_items: List[Dict[str, Any]] = []
    fail_safe: List[Dict[str, Any]] = []
    warnings: List[str] = []
    counts_by_tier: Dict[str, int] = {}
    results_by_log: Dict[str, Any] = {}

    try:
        for log_id, bore_log_path in bore_logs:
            try:
                result = eng.select_redline(bore_log_path, plan_pdf_path, sheet_offset,
                                            anchor_tables=_anchor_tables())
                _render_crops(result, plan_pdf_path, card_out_dir, sheet_offset)
            except Exception as exc:
                warnings.append(f"[{log_id}] {type(exc).__name__}: {exc}")
                continue
            results_by_log[log_id] = result
            env = _envelope_from_result(result)
            placements.extend(env["placements"])
            review_items.extend(env["review_items"])
            fail_safe.extend(env["fail_safe"])
            warnings.extend(env.get("warnings", []))
            for tier, n in env["counts_by_tier"].items():
                counts_by_tier[tier] = counts_by_tier.get(tier, 0) + n

        group_blocks: List[Dict[str, Any]] = []
        if groups:
            for gid, log_ids in groups.items():
                res = [results_by_log[lid] for lid in log_ids if lid in results_by_log]
                if res:
                    group_blocks.append(build_group_review(res, group_id=gid))

        return {
            "schema_version": SCHEMA_VERSION,
            "engine_version": getattr(eng, "ENGINE_VERSION", None) or getattr(eng, "__version__", None),
            "contract_version": getattr(eng, "CONTRACT_VERSION", None),
            "render_target": RENDER_TARGET_EVIDENCE_CARD,
            "generated_by": GENERATED_BY,
            "status": "OK" if results_by_log else "ERROR",
            "source": source,
            "counts_by_tier": counts_by_tier,
            "counts_by_surface": {
                "placements": len(placements),
                "review_items": len(review_items),
                "fail_safe": len(fail_safe),
            },
            "placements": placements,
            "review_items": review_items,
            "fail_safe": fail_safe,
            "groups": group_blocks,
            "warnings": warnings,
        }
    except Exception as exc:
        detail = "".join(traceback.format_exception_only(type(exc), exc)).strip()
        return _error_envelope(detail, source)


# ─────────────────────────────────────────────────────────────────────────────
# Day-4f — row-fed entry: run the engine on REAL TrueLine committed_rows
# (no .xlsx, no synthetic corpus). Uses the Day-4e engine row-fed foundation.
# ─────────────────────────────────────────────────────────────────────────────
def group_committed_rows(committed_rows: Sequence[Mapping[str, Any]]
                         ) -> List[Tuple[str, List[Mapping[str, Any]], str]]:
    """Partition TrueLine ``committed_rows`` into per-bore-log groups keyed by
    ``source_file`` (the natural per-.xlsx partition the engine consumes). Pure,
    read-only, first-seen order preserved; returns ``[(log_id, rows, source_file)]``.
    This is input marshalling, NOT selection logic — it only buckets rows by a
    field they already carry."""
    groups: Dict[str, List[Mapping[str, Any]]] = {}
    order: List[str] = []
    for r in committed_rows or []:
        if not isinstance(r, Mapping):
            continue
        sf = str(r.get("source_file") or "").strip()
        if not sf:
            continue
        if sf not in groups:
            groups[sf] = []
            order.append(sf)
        groups[sf].append(r)
    return [(os.path.splitext(sf)[0], groups[sf], sf) for sf in order]


def build_session_evidence_from_rows(plan_pdf_path: str,
                                     logs: Sequence[Tuple[str, Sequence[Mapping[str, Any]], Optional[str]]], *,
                                     groups: Optional[Mapping[str, Sequence[str]]] = None,
                                     sheet_offset: int = 13,
                                     card_out_dir: Optional[str] = None) -> Dict[str, Any]:
    """Row-fed sibling of :func:`build_session_evidence`. ``logs`` is a sequence of
    ``(log_id, rows, source_file)`` where ``rows`` is TrueLine ``committed_rows`` for
    one bore log. Runs the engine via ``select_redline_from_rows`` per log and reuses
    the SAME translation/grouping helpers. Never raises (contained ERROR envelope)."""
    logs = list(logs or [])
    source = {"plan_pdf": plan_pdf_path, "input": "committed_rows",
              "logs": [lid for lid, _, _ in logs]}
    eng, err = _load_engine()
    if eng is None:
        return _error_envelope(f"engine unavailable ({err})", source)

    placements: List[Dict[str, Any]] = []
    review_items: List[Dict[str, Any]] = []
    fail_safe: List[Dict[str, Any]] = []
    warnings: List[str] = []
    counts_by_tier: Dict[str, int] = {}
    results_by_log: Dict[str, Any] = {}

    # Default-OFF consult (TRUELINE_MATCHLINE_FRAME_RESOLVER): owner-reviewed source-station
    # corrections applied to a COPY of each log's rows BEFORE the engine, plus a post-engine
    # matchline/station-frame resolver + narrow false-A override. Flag OFF -> _consult stays None,
    # nothing is imported, no rows are corrected -> the evidence envelope is byte-identical.
    _consult = None
    _consult_doc = None
    _consult_data_dir: Optional[str] = None
    _corrections_applied: List[Dict[str, Any]] = []
    if _matchline_frame_resolver_enabled():
        try:
            from app.core import redline_consult as _rc  # lazy: engine root already on sys.path
            _consult = _rc
            _consult_data_dir = _resolve_analysis_dir()
            _consult_doc = _rc.open_document(plan_pdf_path)  # one PDF handle for the session run
        except Exception as exc:
            warnings.append(f"[resolver-consult] disabled: {type(exc).__name__}: {exc}")
            _consult = None

    try:
        for log_id, rows, source_file in logs:
            # Owner-reviewed source-station OCR corrections -> corrected COPY fed to the engine
            # (STATE rows untouched). A stale/typo'd correction records an error + falls back to RAW.
            if _consult is not None:
                try:
                    rows, _chg, _corr_rec = _consult.apply_corrections(log_id, rows, _consult_data_dir)
                    if _corr_rec is not None:
                        _ca = {"log_id": log_id, "category": _corr_rec.get("category"),
                               "cells_changed": _corr_rec.get("cells_changed", 0)}
                        if _corr_rec.get("correction_error"):
                            _ca["correction_error"] = _corr_rec["correction_error"]
                        _corrections_applied.append(_ca)
                except Exception:
                    pass  # a correction failure must never block the engine run
            try:
                result = eng.select_redline_from_rows(
                    plan_pdf_path, rows, source_file=source_file, sheet_offset=sheet_offset,
                    anchor_tables=_anchor_tables())
                _render_crops(result, plan_pdf_path, card_out_dir, sheet_offset)
            except Exception as exc:
                warnings.append(f"[{log_id}] {type(exc).__name__}: {exc}")
                continue
            results_by_log[log_id] = result
            env = _envelope_from_result(result)
            # Post-engine resolver consult: LIFT a blocked/fail-safe FRAME_ONLY bore into matchline
            # (C) / station-frame (B) review evidence, or OVERRIDE a geometry-only false-A placement.
            if _consult is not None and _consult_doc is not None:
                env = _consult.apply_resolver(
                    log_id, env, _consult_doc, sheet_offset,
                    card_out_dir or _cards_root(), _consult_data_dir)
            placements.extend(env["placements"])
            review_items.extend(env["review_items"])
            fail_safe.extend(env["fail_safe"])
            warnings.extend(env.get("warnings", []))
            for tier, n in env["counts_by_tier"].items():
                counts_by_tier[tier] = counts_by_tier.get(tier, 0) + n

        group_blocks: List[Dict[str, Any]] = []
        if groups:
            for gid, lids in groups.items():
                res = [results_by_log[lid] for lid in lids if lid in results_by_log]
                if res:
                    group_blocks.append(build_group_review(res, group_id=gid))

        out = {
            "schema_version": SCHEMA_VERSION,
            "engine_version": getattr(eng, "ENGINE_VERSION", None) or getattr(eng, "__version__", None),
            "contract_version": getattr(eng, "CONTRACT_VERSION", None),
            "render_target": RENDER_TARGET_EVIDENCE_CARD,
            "generated_by": GENERATED_BY,
            "status": "OK" if results_by_log else "ERROR",
            "source": source,
            "counts_by_tier": counts_by_tier,
            "counts_by_surface": {
                "placements": len(placements),
                "review_items": len(review_items),
                "fail_safe": len(fail_safe),
            },
            "placements": placements,
            "review_items": review_items,
            "fail_safe": fail_safe,
            "groups": group_blocks,
            "warnings": warnings,
        }
        # Resolver consult summary — present ONLY when the flag is on (off => key absent =>
        # envelope byte-identical). Customer-safe: counts + owner-reviewed correction provenance.
        if _matchline_frame_resolver_enabled():
            out["resolver"] = {
                "flag": "TRUELINE_MATCHLINE_FRAME_RESOLVER",
                "consult_active": bool(_consult is not None and _consult_doc is not None),
                "resolved_count": counts_by_tier.get("MATCHLINE_FRAME_RESOLVER", 0),
                "corrections_applied": _corrections_applied,
            }
        return out
    except Exception as exc:
        detail = "".join(traceback.format_exception_only(type(exc), exc)).strip()
        return _error_envelope(detail, source)
    finally:
        if _consult_doc is not None:
            try:
                _consult_doc.close()
            except Exception:
                pass


def build_session_evidence_from_committed_rows(plan_pdf_path: str,
                                               committed_rows: Sequence[Mapping[str, Any]], *,
                                               sheet_offset: int = 13,
                                               card_out_dir: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """main.py-facing entry: group REAL ``committed_rows`` by ``source_file`` then run
    the row-fed engine. Returns the evidence envelope, or ``None`` when no committed
    row carries a ``source_file`` (degenerate -> caller omits the key). Never raises."""
    logs = group_committed_rows(committed_rows)
    if not logs:
        return None
    return build_session_evidence_from_rows(
        plan_pdf_path, logs, sheet_offset=sheet_offset, card_out_dir=card_out_dir)
