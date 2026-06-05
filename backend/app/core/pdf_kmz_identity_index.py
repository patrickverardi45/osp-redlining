"""Pure KMZ IDENTITY-INDEX adapter for the PDF↔KMZ bridge builder.

Converts existing KMZ identity sources — primarily ``kmz_xref.ap_map`` (and optionally extra
identity records resolved from the KMZ render payload / kml_items) — into a normalized index
keyed by the SHARED canonical identity key (e.g. ``AP-120``) that
:mod:`pdf_redline_bridge_builder` consumes.

DOCTRINE (see wiki/PDF_KMZ_BRIDGE_DOCTRINE.md):
  * **Identity only.** Keys are ``KIND-NUMBER`` (``pdf_redline_bridge.canonical_identity_key``).
    The PDF side ("AP-120") and the KMZ side (ap_map key "120" + kind hint, "TermPortHH 120") map
    to the SAME key. The KIND prefix prevents bare-number collisions (AP-120 ≠ HH-120).
  * **Coordinates are ignored.** Source ``lonlat`` / coords are NEVER stored as a join key and
    NEVER used for matching — they are dropped from the index entirely. (The later candidate→world
    resolver reads world geometry straight from the KMZ source, not via this identity index.)
  * **No nearest, no guessing.** An entry without a resolvable kind+number is skipped. When two
    sources disagree on the same canonical key, the entry is marked ``ambiguous`` (feature_id
    nulled) so the builder ABSTAINS rather than picking one.

Output entry shape (matches the bridge builder's expectations)::

    "AP-120": {
        "feature_id": "kmz:termporthh:120",   # or caller-resolved render feature_id
        "source": "kmz_xref",
        "label": "AP-120",
        "raw_id": "120",
        "kind": "ap",
        "folder": "Terminal Port Handhole",   # optional, non-join metadata (type label)
        "route_id": None,                      # optional
        "evidence_refs": [],
        # "ambiguous": True / "ambiguous_reason": "..."  (only when a conflict is detected)
    }

INERT: no endpoint, no UI, no renderer. Pure stdlib + the schema module; no file I/O, no fitz,
no ``main`` import. Never raises.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence

from app.core import pdf_redline_bridge as _bridge

SOURCE_KMZ_XREF = "kmz_xref"


def classify_kind(folder: Any, default: str = "ap") -> str:
    """Map a KMZ folder/type label to an identity kind. ``ap_map`` entries are AP / TermPortHH by
    default; only an explicit SPLICE folder overrides. Type label ONLY — never coordinates.
    NOTE: 'Terminal Port Handhole' stays ``ap`` (do not fall through to ``hh`` on 'Handhole')."""
    f = str(folder or "").strip().lower()
    if "splice" in f:
        return "splice"
    return default


def _synth_feature_id(kind: str, raw_id: str) -> str:
    """Stable identity token used when the caller did not resolve a real KMZ render feature_id.
    It is an IDENTITY string (kind+number), never a coordinate."""
    tag = "termporthh" if kind == "ap" else kind
    return "kmz:%s:%s" % (tag, raw_id)


def _entry(*, key: str, raw_id: str, kind: str, feature_id: Optional[str], source: str,
           folder: Any = None, route_id: Any = None) -> Dict[str, Any]:
    return {
        "feature_id": feature_id or _synth_feature_id(kind, raw_id),
        "source": source,
        "label": key,
        "raw_id": raw_id,
        "kind": kind,
        "folder": (str(folder) if folder else None),
        "route_id": (str(route_id) if route_id else None),
        "evidence_refs": [],
        # source coordinates (lonlat/coords) are intentionally DROPPED — identity only.
    }


def build_identity_index(
    kmz_xref: Optional[Mapping[str, Any]],
    *,
    feature_id_by_ap: Optional[Mapping[str, str]] = None,
    extra_identities: Optional[Sequence[Mapping[str, Any]]] = None,
) -> Dict[str, Dict[str, Any]]:
    """Build ``{canonical_key: identity_entry}`` from ``kmz_xref`` (its ``ap_map``) and any
    ``extra_identities``.

    ``feature_id_by_ap``: optional caller-resolved EXACT map ``raw_AP_number -> render feature_id``
    (e.g. derived deterministically from the KMZ render payload). When absent, a stable identity
    token is synthesized. ``extra_identities``: optional records ``{"id"|("raw_id"+"kind"),
    "feature_id"?, "folder"?, "route_id"?, "source"?}`` merged from other KMZ sources — used for
    cross-source ambiguity detection. Missing/empty xref → empty index (never crashes).
    Coordinates anywhere in the inputs are ignored."""
    feature_id_by_ap = feature_id_by_ap or {}
    buckets: Dict[str, List[Dict[str, Any]]] = {}

    # 1) Primary source: kmz_xref.ap_map (keyed by AP number).
    ap_map = kmz_xref.get("ap_map") if isinstance(kmz_xref, Mapping) else None
    if isinstance(ap_map, Mapping):
        for raw_key, raw_val in ap_map.items():
            val = raw_val if isinstance(raw_val, Mapping) else {}
            kind = classify_kind(val.get("folder"))
            _, raw_id = _bridge.parse_identity(raw_key, kind_hint=kind)
            key = _bridge.canonical_identity_key(raw_key, kind_hint=kind)
            if not key or not raw_id:
                continue  # no resolvable kind+number -> skip, never guess
            buckets.setdefault(key, []).append(_entry(
                key=key, raw_id=raw_id, kind=kind,
                feature_id=feature_id_by_ap.get(raw_id),
                source=SOURCE_KMZ_XREF, folder=val.get("folder"),
            ))

    # 2) Optional extra identity sources (render payload / kml_items already resolved by caller).
    for item in (extra_identities or []):
        if not isinstance(item, Mapping):
            continue
        if item.get("id") is not None:
            kind, raw_id = _bridge.parse_identity(item.get("id"))
            key = _bridge.canonical_identity_key(item.get("id"))
        else:
            kind = str(item.get("kind") or "").strip().lower() or None
            _, raw_id = _bridge.parse_identity(item.get("raw_id"), kind_hint=kind)
            key = _bridge.canonical_identity_key(item.get("raw_id"), kind_hint=kind)
        if not key or not raw_id or not kind:
            continue
        buckets.setdefault(key, []).append(_entry(
            key=key, raw_id=raw_id, kind=kind,
            feature_id=item.get("feature_id"),
            source=str(item.get("source") or "extra"),
            folder=item.get("folder"), route_id=item.get("route_id"),
        ))

    # 3) Collapse duplicates; flag conflicts as ambiguous (never expose a guessed target).
    index: Dict[str, Dict[str, Any]] = {}
    for key, entries in buckets.items():
        distinct = {(e["feature_id"], e["kind"]) for e in entries}
        if len(distinct) > 1:
            amb = dict(entries[0])
            amb["ambiguous"] = True
            amb["ambiguous_reason"] = "multiple_conflicting_identities_for_%s" % key
            amb["feature_id"] = None
            index[key] = amb
        else:
            index[key] = entries[0]
    return index
