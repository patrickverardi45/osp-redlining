"""Pure AP→render-``feature_id`` resolver for the PDF↔KMZ bridge.

Reads the KMZ RENDER PAYLOAD (``_build_kmz_render_payload`` output: ``points``/``lines``/
``polygons``, each a feature with ``feature_id`` + ``name`` + ``extended_data`` +
``description`` + ``classification`` + ``folder_path``) and resolves AP / TermPortHH / SPLICE
/ HH IDENTITIES to the real render ``feature_id`` the map payload uses.

Why: ``kmz_xref.ap_map`` is keyed by AP number but carries NO feature_id, so it cannot supply
one. The render payload is the only place the real feature ids live. This resolver bridges the
gap so :func:`pdf_kmz_identity_index.build_identity_index` can attach a REAL feature_id (via
``feature_id_by_ap``) instead of a synthesized token.

DOCTRINE (see wiki/PDF_KMZ_BRIDGE_DOCTRINE.md):
  * **Exact identity only.** Identity is parsed from TEXT fields (name → extended_data →
    description) via the shared ``pdf_redline_bridge.canonical_identity_key``. ``classification``/
    ``folder_path`` only provide a KIND HINT for a bare number.
  * **Coordinates are never read.** ``coord``/``coords``/``outer``/``inner`` are ignored — no
    nearest-feature, no route proximity, no lat/lon as proof.
  * **No guessing.** A feature with no parseable identity is omitted. When two distinct render
    features claim the same identity, the entry is marked ``ambiguous`` (feature_id nulled).

INERT: no endpoint, no UI, no rendering, no file I/O, no ``main`` import. Pure stdlib + the
schema module. Never raises.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping, Optional, Tuple

from app.core import pdf_redline_bridge as _bridge

SOURCE_RENDER_PAYLOAD = "kmz_render_payload"


def _kind_from_token(text: Any) -> Optional[str]:
    """Identity KIND implied by a field name / type token (e.g. an extended_data key
    'AP Number' -> 'ap'). Word-bounded so 'MAP'/'GAP' do not match 'AP'. Text only."""
    t = re.sub(r"[_\-]+", " ", str(text or "").upper())
    if "SPLICE" in t:
        return "splice"
    if "TERMPORT" in t or "TERMINAL PORT" in t or "ACCESS POINT" in t or re.search(r"\bAP\b", t):
        return "ap"
    if "HANDHOLE" in t or re.search(r"\bHH\b", t):
        return "hh"
    return None


def _kind_hint(feature: Mapping[str, Any]) -> Optional[str]:
    """Kind hint from a feature's classification + folder_path (so a bare number can be typed)."""
    parts = [str(feature.get("classification") or "")]
    fp = feature.get("folder_path")
    if isinstance(fp, (list, tuple)):
        parts.extend(str(p) for p in fp)
    return _kind_from_token(" ".join(parts))


def identity_from_feature(feature: Mapping[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    """Return ``(canonical_key, evidence)`` for one render feature, or ``(None, None)``.

    Priority: ``name`` -> ``extended_data`` -> ``description``/``description_raw``. Exact identity
    tokens only; NEVER reads coordinates."""
    hint = _kind_hint(feature)

    # 1) name / placemark_name
    name = feature.get("name") or feature.get("placemark_name")
    key = _bridge.canonical_identity_key(name, kind_hint=hint)
    if key:
        return key, "name:%s" % str(name)

    # 2) extended_data: flat {field: value}. Try the value (kind from the field name), then the key.
    ed = feature.get("extended_data")
    if isinstance(ed, Mapping):
        for fld, val in ed.items():
            kh = _kind_from_token(fld) or hint
            key = _bridge.canonical_identity_key(val, kind_hint=kh)
            if key:
                return key, "extended_data:%s=%s" % (fld, val)
            key = _bridge.canonical_identity_key(fld, kind_hint=hint)
            if key:
                return key, "extended_data_key:%s" % fld

    # 3) description / description_raw — require an EXPLICIT type token adjacent to a number
    #    (no bare numbers from free text -> avoids false identities).
    pat = re.compile(r"(AP|TERMPORTHH|TERMINAL PORT|SPLICE|HH)\s*[-#:]?\s*(\d+)", re.IGNORECASE)
    for src in ("description", "description_raw"):
        m = pat.search(str(feature.get(src) or ""))
        if m:
            key = _bridge.canonical_identity_key("%s %s" % (m.group(1), m.group(2)))
            if key:
                return key, "%s:%s" % (src, m.group(0))
    return None, None


def resolve_render_feature_ids(render_payload: Optional[Mapping[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Resolve identities in a KMZ render payload to render feature ids.

    Returns ``{canonical_key: {feature_id, source, raw_id, kind, evidence_refs,
    [ambiguous, ambiguous_reason]}}``. Identity-only; coordinates are ignored. Missing/empty
    payload -> ``{}``. Never raises."""
    if not isinstance(render_payload, Mapping):
        return {}
    buckets: Dict[str, List[Dict[str, Any]]] = {}
    for bucket in ("points", "lines", "polygons"):
        for feat in (render_payload.get(bucket) or []):
            if not isinstance(feat, Mapping):
                continue
            fid = str(feat.get("feature_id") or "").strip()
            if not fid:
                continue
            key, evidence = identity_from_feature(feat)
            if not key:
                continue  # coordinate-only / no parseable identity -> omit safely
            kind, raw_id = _bridge.parse_identity(key)
            buckets.setdefault(key, []).append({
                "feature_id": fid,
                "source": SOURCE_RENDER_PAYLOAD,
                "raw_id": raw_id,
                "kind": kind,
                "evidence_refs": [evidence] if evidence else [],
            })

    out: Dict[str, Dict[str, Any]] = {}
    for key, entries in buckets.items():
        distinct_fids = {e["feature_id"] for e in entries}
        base = dict(entries[0])
        if len(distinct_fids) > 1:
            base["feature_id"] = None
            base["ambiguous"] = True
            base["ambiguous_reason"] = "multiple_render_features_for_%s" % key
            base["evidence_refs"] = sorted({r for e in entries for r in e.get("evidence_refs", [])})
        out[key] = base
    return out


def to_feature_id_by_ap(resolved: Optional[Mapping[str, Mapping[str, Any]]]) -> Dict[str, str]:
    """Project the resolver output to the adapter's ``feature_id_by_ap`` shape:
    ``{raw_AP_number: feature_id}`` for ``kind == 'ap'`` entries with a single (non-ambiguous)
    feature_id. Ambiguous / non-AP / unresolved entries are skipped."""
    out: Dict[str, str] = {}
    for entry in (resolved or {}).values():
        if not isinstance(entry, Mapping) or entry.get("ambiguous"):
            continue
        if entry.get("kind") != "ap":
            continue
        fid = entry.get("feature_id")
        raw = entry.get("raw_id")
        if fid and raw:
            out[str(raw)] = str(fid)
    return out
