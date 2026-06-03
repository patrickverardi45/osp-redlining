"""Deterministic design-geometry binder (pure; no rendering, no flags, no production wiring).

Contract
--------
    bind_design_path(bore_truth, resolver_proof, design_refs) -> BoundDesignPath

Mental model (owner/product truth)
-----------------------------------
  * The DESIGN (resolved KMZ anchor tables + route catalog + PDF station model) is the
    COORDINATE / REFERENCE system.
  * The BORE LOG is the actual field / as-built INSTRUCTION (a PROVEN station span + footage).
  * The REDLINE is the design geometry bound to the bore's PROVEN endpoint *identities* and
    validated against the bore footage — NOT drawn from labels, NOT from HH-symbol hunting,
    NOT from guessed conduit fragments, and NEVER fabricated.

This module ONLY decides BOUND vs ABSTAIN and emits the drawable-path spec. It draws nothing
and wires into nothing. Only a BOUND result may later be rendered. It is SINGLE-SHEET; a
cross-sheet (matchline-seam) frame ABSTAINs with ``cross_sheet_stitch_not_implemented`` (the
seam-stitched station model for log56/log58 is a later layer).

Determinism rules (by construction):
  * Endpoints bind by EXACT (kind,id,sheet) join to the resolved anchor table (reusing
    ``identity_binder.normalize_identity``); a (kind,id,sheet) resolving to >1 distinct coord
    is AMBIGUOUS and rejected (never picked). HH / flower-pot / terminal / station-only
    endpoints carry no AP/SPLICE identity and therefore do NOT bind (the log66 case).
  * The drawable route is the one whose authored terminus EXACTLY matches the bound END
    identity — no nearest, no scoring, no route_id guessing.
  * As-built footage is validated against the design route length; divergence beyond tolerance
    ABSTAINs (the design path is not the as-built path there). Pure; never raises.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from .identity_binder import normalize_identity  # pure AP/SPLICE id parser (reuse; no drift)

SCHEMA_VERSION = "design-path-binder-1"

STATUS_BOUND = "BOUND"
STATUS_ABSTAIN = "ABSTAIN"

# Machine-readable abstain reason codes.
ABSTAIN_NO_ENDPOINTS = "resolver_proof_missing_endpoints"
ABSTAIN_CROSS_SHEET = "cross_sheet_stitch_not_implemented"
ABSTAIN_ENDPOINT_NOT_ANCHORED = "endpoint_not_bound_to_resolved_design_anchor"
ABSTAIN_NO_DESIGN_GEOMETRY = "no_station_indexed_design_geometry_for_span"
ABSTAIN_LENGTH_MISMATCH = "as_built_footage_mismatches_design_length"

# As-built footage / design length ratio band. Outside -> the design path is not the as-built.
_TOL_LO, _TOL_HI = 0.80, 1.25

# normalize_identity kind -> anchors.json 'kind' (which uses AP / SPLICE).
_KIND_TO_ANCHOR = {"AP": "AP", "SPLICE_LOC": "SPLICE"}


# ── helpers (pure) ───────────────────────────────────────────────────────────────────────────
def _num(v: Any) -> Optional[float]:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _haversine_len_ft(coords: Optional[List[List[float]]]) -> Optional[float]:
    """Real geodesic length of a [lon,lat] polyline in FEET (fallback when route.length_ft is
    absent). Never fabricates — returns None for <2 points. Not a guess; the actual route length."""
    if not coords or len(coords) < 2:
        return None
    total_m = 0.0
    r = 6371000.0
    for a, b in zip(coords, coords[1:]):
        try:
            lon0, lat0 = float(a[0]), float(a[1])
            lon1, lat1 = float(b[0]), float(b[1])
        except (TypeError, ValueError, IndexError):
            return None
        p0, p1 = math.radians(lat0), math.radians(lat1)
        dphi = math.radians(lat1 - lat0)
        dlmb = math.radians(lon1 - lon0)
        h = math.sin(dphi / 2) ** 2 + math.cos(p0) * math.cos(p1) * math.sin(dlmb / 2) ** 2
        total_m += 2 * r * math.asin(min(1.0, math.sqrt(h)))
    return total_m * 3.280839895013123


def _identity_of(anchor: Optional[Dict[str, Any]]) -> Optional[Tuple[str, str]]:
    """The AP/SPLICE (kind,id) identity of an endpoint anchor from its authored structure text,
    else None. HH / flower-pot / terminal / station-only endpoints have NO AP/SPLICE identity."""
    if not isinstance(anchor, dict):
        return None
    for field in ("label", "structure", "id_text", "id"):
        txt = anchor.get(field)
        if isinstance(txt, str):
            tok = normalize_identity(txt)
            if tok:
                return tok
    return None


def _endpoints(resolver_proof: Dict[str, Any]) -> Tuple[Optional[Dict], Optional[Dict]]:
    anchors = resolver_proof.get("anchors") or []
    start = next((a for a in anchors if isinstance(a, dict)
                  and a.get("role") in ("start", "reset_origin", "reset")), None)
    end = next((a for a in anchors if isinstance(a, dict) and a.get("role") == "end"), None)
    return start, end


def _resolve_anchor(identity: Optional[Tuple[str, str]], sheet: Any,
                    anchors_idx: Dict[Any, List[Dict[str, Any]]]) -> Optional[Dict[str, Any]]:
    """EXACT (anchor_kind,id,sheet) single-coordinate join to the resolved anchor table. Returns
    ``{coord,sta,kind,id,sheet}`` or None (absent / ambiguous-distinct-coords -> None; no guess)."""
    if identity is None or not isinstance(sheet, int) or isinstance(sheet, bool):
        return None
    kind, key = identity
    anchor_kind = _KIND_TO_ANCHOR.get(kind, kind)
    rows = (anchors_idx.get((anchor_kind, str(key), sheet))
            or anchors_idx.get((anchor_kind, key, sheet)) or [])
    if not rows:
        return None
    by_coord: Dict[Tuple[float, float], Dict[str, Any]] = {}
    for r in rows:
        c = r.get("coord")
        if isinstance(c, (list, tuple)) and len(c) == 2:
            by_coord.setdefault((round(float(c[0]), 9), round(float(c[1]), 9)), r)
    if len(by_coord) != 1:
        return None  # ambiguous distinct coords -> reject (never pick one)
    r = next(iter(by_coord.values()))
    return {"coord": [float(r["coord"][0]), float(r["coord"][1])],
            "sta": _num(r.get("sta")), "kind": kind, "id": str(key), "sheet": sheet}


def _route_for_terminus(route_catalog: List[Dict[str, Any]],
                        identity: Optional[Tuple[str, str]]) -> Optional[Dict[str, Any]]:
    """The route whose authored terminus identity EXACTLY matches ``identity``, else None."""
    if not identity:
        return None
    kind, key = identity
    for rt in route_catalog or []:
        t = (rt.get("terminus") or {}) if isinstance(rt, dict) else {}
        if str(t.get("kind")) == str(kind) and str(t.get("id")) == str(key):
            return rt
    return None


def _ep_binding(role_res: Dict[str, Any]) -> Dict[str, Any]:
    a = role_res.get("anchor") or {}
    ident = role_res.get("identity")
    r = role_res.get("resolved")
    return {
        "identity": ({"kind": ident[0], "id": ident[1]} if ident else None),
        "station": a.get("station") or a.get("phys_sta"),
        "coord": (r.get("coord") if r else None),
        "sta": (r.get("sta") if r else None),
        "source": ("resolved_anchor_table" if r else None),
    }


def _abstain(bore_truth: Dict[str, Any], resolver_proof: Dict[str, Any], reason: str,
             detail: Optional[Dict[str, Any]] = None,
             binding: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "bore_log_id": bore_truth.get("bore_log_id"),
        "source_file": bore_truth.get("source_file"),
        "status": STATUS_ABSTAIN,
        "binding": binding or {},
        "pdf_path": None,
        "map_path": None,
        "validation": None,
        "evidence": {
            "proof_class": resolver_proof.get("proof_class") or resolver_proof.get("class"),
            "home_sheet": resolver_proof.get("home_sheet"),
            "seam": resolver_proof.get("seam") or resolver_proof.get("matchline_seam"),
            "why": reason,
        },
        "abstain_reason": reason,
        "abstain_detail": detail or {},
    }


# ── public contract ──────────────────────────────────────────────────────────────────────────
def bind_design_path(bore_truth: Dict[str, Any], resolver_proof: Dict[str, Any],
                     design_refs: Dict[str, Any]) -> Dict[str, Any]:
    """Bind a resolver-proven bore frame to drawable design geometry, or ABSTAIN.

    ``bore_truth``      field/as-built instruction: ``bore_log_id, source_file, footage_ft,
                        hh_hh_ft, boc_ft, corrections_applied`` (+ station fields).
    ``resolver_proof``  proven frame (a frame_resolutions entry shape is accepted directly):
                        ``proof_class|class, home_sheet, seam|matchline_seam,
                        anchors:[{role, label?, station?, phys_sta?, sheet?}]``.
    ``design_refs``     design coordinate system: ``anchor_tables`` (from
                        ``identity_binder.load_tables``) and optional ``route_catalog``
                        ``[{route_id, terminus:{kind,id}, coords:[[lon,lat],...], length_ft}]``.

    Returns a ``BoundDesignPath`` dict (``status`` BOUND or ABSTAIN). Pure; never raises.
    """
    try:
        bore_truth = bore_truth or {}
        resolver_proof = resolver_proof or {}
        design_refs = design_refs or {}

        # 1) cross-sheet (matchline seam) -> seam-stitch is a later layer (log56/log58 deferred).
        if resolver_proof.get("seam") or resolver_proof.get("matchline_seam"):
            return _abstain(bore_truth, resolver_proof, ABSTAIN_CROSS_SHEET, {
                "note": "matchline-seam frames (e.g. log56/log58) need a seam-stitched station "
                        "model joining both sheets' chainage at the seam; not implemented yet."})

        start, end = _endpoints(resolver_proof)
        if start is None or end is None:
            return _abstain(bore_truth, resolver_proof, ABSTAIN_NO_ENDPOINTS, {
                "have_roles": [a.get("role") for a in (resolver_proof.get("anchors") or [])
                               if isinstance(a, dict)]})

        tables = design_refs.get("anchor_tables") or {}
        anchors_idx = tables.get("anchors") or {}
        route_catalog = design_refs.get("route_catalog") or []
        home_sheet = resolver_proof.get("home_sheet")

        # 2) resolve each PROVEN endpoint's AP/SPLICE identity to an EXACT resolved design anchor.
        res: Dict[str, Dict[str, Any]] = {}
        for role, a in (("start", start), ("end", end)):
            ident = _identity_of(a)
            sheet = a.get("sheet") if isinstance(a.get("sheet"), int) else home_sheet
            res[role] = {"anchor": a, "identity": ident,
                         "resolved": _resolve_anchor(ident, sheet, anchors_idx)}

        binding = {
            "station_model": "kmz_chainage",
            "proof_class": resolver_proof.get("proof_class") or resolver_proof.get("class"),
            "start": _ep_binding(res["start"]),
            "end": _ep_binding(res["end"]),
            "geometry_source": None,
        }

        # 3) BOTH endpoints must bind to a resolved design anchor. The log66 case fails here:
        #    HH / station-only endpoints carry no AP/SPLICE identity in the resolved tables.
        unresolved = [r for r in ("start", "end") if res[r]["resolved"] is None]
        if unresolved:
            return _abstain(bore_truth, resolver_proof, ABSTAIN_ENDPOINT_NOT_ANCHORED, {
                "unresolved_endpoints": unresolved,
                "endpoint_identities": {r: res[r]["identity"] for r in ("start", "end")},
                "note": "endpoint is not an AP/SPLICE structure present in the resolved anchor "
                        "tables (HH / flower-pot / terminal / station-only endpoints do not "
                        "bind); no station-indexed design geometry anchors the span."}, binding)

        # 4) drawable design geometry = the authored route terminating at the END identity.
        route = _route_for_terminus(route_catalog, res["end"]["identity"])
        if route is None:
            return _abstain(bore_truth, resolver_proof, ABSTAIN_NO_DESIGN_GEOMETRY, {
                "end_identity": res["end"]["identity"],
                "note": "both endpoints bound to resolved anchors, but no design route geometry "
                        "terminates at the END anchor (route_catalog absent or no terminus "
                        "match); a page-space station->pixel model is also required for a PDF "
                        "path."}, binding)
        binding["geometry_source"] = "kmz_route:%s" % route.get("route_id")

        # 5) validate as-built footage vs design route length (confirm or diverge).
        footage = _num(bore_truth.get("footage_ft")) or _num(bore_truth.get("hh_hh_ft"))
        design_len = _num(route.get("length_ft")) or _haversine_len_ft(route.get("coords"))
        if design_len is None:
            return _abstain(bore_truth, resolver_proof, ABSTAIN_NO_DESIGN_GEOMETRY, {
                "route_id": route.get("route_id"),
                "note": "design route has no length_ft and no usable coords; cannot validate "
                        "as-built footage against design length."}, binding)
        ratio = (footage / design_len) if (footage and design_len) else None
        within = bool(ratio is not None and _TOL_LO <= ratio <= _TOL_HI)
        validation = {
            "bore_footage_ft": footage, "design_length_ft": round(design_len, 2),
            "ratio": (round(ratio, 4) if ratio is not None else None), "within_tol": within,
            "boc_ft": bore_truth.get("boc_ft"),
            "corrections_applied": bore_truth.get("corrections_applied") or [],
        }
        if not within:
            return _abstain(bore_truth, resolver_proof, ABSTAIN_LENGTH_MISMATCH, {
                "ratio": validation["ratio"], "tol": [_TOL_LO, _TOL_HI],
                "note": "as-built footage diverges from the design route length beyond tolerance "
                        "(or footage/length unavailable); the design path is not the as-built "
                        "path here."}, binding)

        # BOUND. Emit the drawable map path (Hero/KMZ bridge consumes it LATER). pdf_path needs a
        # station->pixel alignment model (not in these refs) -> None for now (documented, deferred).
        sc, ec = res["start"]["resolved"].get("sta"), res["end"]["resolved"].get("sta")
        return {
            "schema_version": SCHEMA_VERSION,
            "bore_log_id": bore_truth.get("bore_log_id"),
            "source_file": bore_truth.get("source_file"),
            "status": STATUS_BOUND,
            "binding": binding,
            "pdf_path": None,
            "map_path": {
                "route_id": route.get("route_id"),
                "coords": [[float(p[0]), float(p[1])] for p in (route.get("coords") or [])
                           if isinstance(p, (list, tuple)) and len(p) == 2],
                "chainage_range": ([sc, ec] if (sc is not None and ec is not None) else None),
                "length_ft": round(design_len, 2),
            },
            "validation": validation,
            "evidence": {
                "proof_class": binding["proof_class"], "home_sheet": home_sheet, "seam": None,
                "endpoints_resolved": {r: res[r]["resolved"] for r in ("start", "end")},
                "why": "both proven endpoints bound to resolved design anchors; design route "
                       "terminates at the END anchor; as-built footage within tolerance of the "
                       "design route length.",
                "caveats": [],
            },
            "abstain_reason": None,
            "abstain_detail": None,
        }
    except Exception as exc:  # pure: never raise into a caller
        return _abstain(bore_truth or {}, resolver_proof or {}, "binder_internal_error",
                        {"error": "%s: %s" % (type(exc).__name__, exc)})


__all__ = [
    "bind_design_path", "SCHEMA_VERSION", "STATUS_BOUND", "STATUS_ABSTAIN",
    "ABSTAIN_NO_ENDPOINTS", "ABSTAIN_CROSS_SHEET", "ABSTAIN_ENDPOINT_NOT_ANCHORED",
    "ABSTAIN_NO_DESIGN_GEOMETRY", "ABSTAIN_LENGTH_MISMATCH",
]
