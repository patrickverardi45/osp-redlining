"""PDF-AP Route Shadow Resolver — Brenham PH5 proof-slice (default-OFF SHADOW).

OBSERVATION ONLY. This module NEVER mutates matching, scoring, selection,
rendering, KMZ export, STATE, or the hardcoded ``CURRENT_PACKET_PRINT_SHEET_INDEX``.
It does not import from ``main.py``. Its sole purpose is to derive, for a
bore-log group, a PDF-evidence-based set of candidate ``route_id`` values that
can be COMPARED (in a diagnostic ``_diag`` field) against the hardcoded
print-sheet index result. Placement is unaffected regardless of the flag state.

Authoritative chain (proven in the 2026-05-29 PH5 proof slice):

    print token  (== Brenham plan SHEET number for this packet)
      -> PDF plan page whose OWN sheet number == that token
         (own sheet read deterministically from the "<n> OF <total>" title-block
          text — NOT OCR, NOT a hardcoded page offset)
      -> AP tags printed on that page  (e.g. AP-115 / AP-117 / AP-119)
      -> KMZ "Terminal Port Handhole" node whose name == that AP number (lat/lon)
      -> nearest KMZ route corridor  (min haversine distance)
      -> pdf_allowed_route_ids

Safety gate: if the bore-log NOTES name a street that is ABSENT from every plan
page in the active plan set, the resolver returns ``[]`` with
``reason="notes_street_absent_from_plan_set"`` and does NOT fall back to the
print-token sheets. This deliberately abstains on bore_log39 (CHERI LN), whose
street does not appear anywhere in the Brenham PH5 plan set — it must NOT be
force-placed onto the LAWNDALE sheets its print tokens happen to point at.

Pure core: ``resolve_pdf_ap_routes`` takes plain dict/list inputs and is fully
unit-testable without any PDF/KMZ I/O. ``build_plan_pages_from_pdf_paths`` is the
only function that touches a PDF (lazy ``pdfplumber`` import, already a backend
dependency); it degrades to ``[]`` if the library or files are unavailable.
"""

from __future__ import annotations

import math
import os
import re
from collections import deque
from typing import Any, Dict, List, Optional, Sequence

SCHEMA_VERSION = "pdf-ap-route-shadow-1"

# The four proof-slice bore logs this shadow is scoped to. Matched by filename
# stem (case-insensitive, extension-insensitive). Nothing else is ever emitted.
PROOF_SLICE_SOURCE_FILES = frozenset({
    "bore_log71",
    "bore_log72",
    "bore_log39",
    "bore_log4",
})

EARTH_RADIUS_FT = 20_925_524.9  # mean Earth radius in feet

_STREET_SUFFIX = r"(?:ST|AVE|DR|BLVD|LN|CT|RD|WAY|CIR|PL|HWY|TRL)"
_STREET_RE = re.compile(r"\b([A-Z][A-Z0-9'.\- ]*?\s" + _STREET_SUFFIX + r")\b")
_SHEET_OF_RE = re.compile(r"\b(\d{1,3})\s+OF\s+(\d{1,3})\b", re.IGNORECASE)
_AP_RE = re.compile(r"\bAP[\-_ ]?(\d{2,4})\b", re.IGNORECASE)
# AP Extraction V2 (shadow-only, default-OFF) — broad recovery from words+chars
# page text. Tolerant of a space between A and P and of separator glyphs, bounded
# so it cannot run greedily across a page. Validation against the terminal-id set
# (extract_ap_ids_v2) is what makes the broad match safe (drops noise like 1/4).
_AP_RE_V2 = re.compile(r"(?i)(?<![A-Za-z0-9])A\s{0,1}P\s{0,2}[\-_.]?\s{0,2}(\d{1,4})\b")

# Route source-folder substrings that are NOT bore-able corridors (drop lines to
# a single house). Excluded from nearest-corridor ranking entirely.
_NON_CORRIDOR_FOLDER_SUBSTRINGS = ("house drop",)

# Backbone class a bore-log redline belongs on. Terminal tails physically touch
# the AP terminal (~0 ft) but are short stubs, not the bored main line — so they
# are reported for transparency but are NOT chosen as pdf_allowed_route_ids.
_BACKBONE_FOLDER_SUBSTRINGS = ("underground cable",)

# Default sanity radius: a bore-log's plan-sheet AP terminals proven to sit
# 32-77 ft from their corridor in the PH5 proof slice; 250 ft is a generous
# fail-open so genuinely-near corridors are reported even with densification gaps.
DEFAULT_MAX_ROUTE_DIST_FT = 250.0


def _source_stem(source_file: Optional[str]) -> str:
    s = str(source_file or "").strip().lower()
    if s.endswith(".xlsx"):
        s = s[:-5]
    return s


def is_proof_slice_source(source_file: Optional[str]) -> bool:
    """True only for the four scoped proof-slice bore logs."""
    return _source_stem(source_file) in PROOF_SLICE_SOURCE_FILES


def _haversine_ft(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2.0) ** 2
    return 2.0 * EARTH_RADIUS_FT * math.asin(min(1.0, math.sqrt(a)))


def extract_street_names(text: Optional[str]) -> List[str]:
    """Extract canonical "<NAME> <SUFFIX>" street labels (house numbers stripped)."""
    if not text:
        return []
    out: List[str] = []
    for raw_line in str(text).upper().splitlines():
        for m in _STREET_RE.finditer(raw_line):
            street = re.sub(r"^\d+\s+", "", m.group(1).strip()).strip()
            street = re.sub(r"\s{2,}", " ", street)
            if street and street not in out:
                out.append(street)
    return out


def _street_in_set(street: str, plan_streets: set) -> bool:
    """Loose containment so 'LAWNDALE AVE' matches a plan label 'LAWNDALE AVE'
    and tolerates minor sub/superstring variation, without matching empties."""
    if not street:
        return False
    for ps in plan_streets:
        if not ps:
            continue
        if street == ps or street in ps or ps in street:
            return True
    return False


def build_plan_pages_from_texts(page_texts: Sequence[Optional[str]]) -> List[Dict[str, Any]]:
    """Pure: per-page raw text -> plan-page records.

    Each record: {page_index(1-based), sheet_number|None, ap_ids[int],
    streets[str], sheet_total|None}. ``sheet_number`` is read from the
    "<n> OF <total>" title-block token whose total equals the modal total across
    the document (the plan-set sheet count). No page offset is assumed.
    """
    parsed: List[Dict[str, Any]] = []
    total_counts: Dict[int, int] = {}
    for idx, txt in enumerate(page_texts):
        t = txt or ""
        ofs = [(int(a), int(b)) for a, b in _SHEET_OF_RE.findall(t)]
        for _n, tot in ofs:
            total_counts[tot] = total_counts.get(tot, 0) + 1
        ap_ids = sorted({int(x) for x in _AP_RE.findall(t)})
        streets = extract_street_names(t)
        parsed.append({"page_index": idx + 1, "_ofs": ofs, "ap_ids": ap_ids, "streets": streets})

    modal_total = max(total_counts, key=lambda k: total_counts[k]) if total_counts else None

    pages: List[Dict[str, Any]] = []
    for rec in parsed:
        own = None
        candidates = [n for (n, tot) in rec["_ofs"] if (modal_total is None or tot == modal_total)]
        if candidates:
            own = candidates[0]
        pages.append({
            "page_index": rec["page_index"],
            "sheet_number": own,
            "ap_ids": rec["ap_ids"],
            "streets": rec["streets"],
            "sheet_total": modal_total,
        })
    return pages


# ---- on-demand PDF extraction (lazy pdfplumber; degrades gracefully) ---------

_PLAN_PAGE_CACHE: Dict[tuple, List[Dict[str, Any]]] = {}


def build_plan_pages_from_pdf_paths(pdf_paths: Sequence[str]) -> List[Dict[str, Any]]:
    """Parse the given PDF paths into plan-page records (cached by path+mtime).

    Returns the UNION of plan pages across all paths. Pages from every PDF are
    merged; ``sheet_number`` is per-PDF (modal total computed per file). Returns
    [] (never raises) if pdfplumber is unavailable or no path is readable.
    """
    key_parts = []
    for p in pdf_paths or []:
        try:
            key_parts.append((str(p), os.path.getmtime(p)))
        except OSError:
            continue
    cache_key = tuple(sorted(key_parts))
    if not cache_key:
        return []
    if cache_key in _PLAN_PAGE_CACHE:
        return _PLAN_PAGE_CACHE[cache_key]

    try:
        import pdfplumber  # lazy; already a backend dependency
    except Exception:
        _PLAN_PAGE_CACHE[cache_key] = []
        return []

    merged: List[Dict[str, Any]] = []
    for path, _mtime in cache_key:
        try:
            with pdfplumber.open(path) as pdf:
                texts = []
                for page in pdf.pages:
                    try:
                        texts.append(page.extract_text() or "")
                    except Exception:
                        texts.append("")
        except Exception:
            continue
        for rec in build_plan_pages_from_texts(texts):
            rec = dict(rec)
            rec["pdf_path"] = os.path.basename(path)
            merged.append(rec)
    _PLAN_PAGE_CACHE[cache_key] = merged
    return merged


# ---- AP Extraction V2 (shadow-only; gated default-OFF in main.py) -----------
# Diagnosed 2026-05-29: on vector-heavy AutoCAD plan sheets, plain
# page.extract_text() drops/scrambles the positioned AP-callout glyphs, so the
# strict _AP_RE finds no contiguous "AP-NNN" (the abstain `no_ap_ids_on_print_
# token_sheets`). The glyphs ARE present in page.extract_words(use_text_flow=True)
# + page.chars. V2 recovers them and VALIDATES each recovered integer against the
# numeric Terminal Port Handhole KMZ node ids, dropping extraction noise. This is
# OBSERVATION-ONLY: it never feeds resolve_pdf_ap_routes / placement. The existing
# _AP_RE + build_plan_pages_from_texts are unchanged.

_PLAN_PAGE_V2_CACHE: Dict[tuple, List[Dict[str, Any]]] = {}


def extract_ap_ids_v2(text: Optional[str], valid_terminal_ids: Sequence[Any]) -> List[int]:
    """Pure AP-id recovery from words+chars page text, validated against the
    numeric Terminal Port Handhole node ids. Returns sorted unique ints; ONLY ids
    that match a known terminal (so positional-extraction noise like '1'/'4' is
    dropped). Never raises; returns [] on empty text or empty terminal set."""
    if not text:
        return []
    valid = {str(v).strip() for v in (valid_terminal_ids or ()) if str(v).strip()}
    if not valid:
        return []
    out = set()
    for d in _AP_RE_V2.findall(str(text)):
        if d.isdigit() and d in valid:
            out.add(int(d))
    return sorted(out)


def recover_ap_ids_for_sheets_v2(
    plan_pages_v2: Sequence[Dict[str, Any]], sheets: Sequence[Any]
) -> List[int]:
    """Pure: union ap_ids_v2 across pages whose sheet_number is in ``sheets``."""
    sset = {int(s) for s in (sheets or []) if str(s).strip().lstrip("-").isdigit()}
    return sorted({int(a) for p in (plan_pages_v2 or [])
                   if p.get("sheet_number") in sset for a in (p.get("ap_ids_v2") or [])})


def build_plan_pages_v2_from_pdf_paths(
    pdf_paths: Sequence[str], valid_terminal_ids: Sequence[Any]
) -> List[Dict[str, Any]]:
    """Like ``build_plan_pages_from_pdf_paths`` but each page record ALSO carries
    ``ap_ids_v2`` recovered from extract_words(use_text_flow)+chars and validated
    against ``valid_terminal_ids``. sheet_number/streets come from the SAME
    production logic (``build_plan_pages_from_texts`` on plain extract_text).
    Cached by (path+mtime, terminal-id set). Returns [] (never raises) if
    pdfplumber is unavailable or no path is readable. Shadow-only — no production
    placement consumer reads ``ap_ids_v2``."""
    key_parts = []
    for p in pdf_paths or []:
        try:
            key_parts.append((str(p), os.path.getmtime(p)))
        except OSError:
            continue
    valid = frozenset(str(v).strip() for v in (valid_terminal_ids or ()) if str(v).strip())
    if not key_parts:
        return []
    cache_key = (tuple(sorted(key_parts)), valid)
    if cache_key in _PLAN_PAGE_V2_CACHE:
        return _PLAN_PAGE_V2_CACHE[cache_key]

    try:
        import pdfplumber  # lazy; already a backend dependency
    except Exception:
        _PLAN_PAGE_V2_CACHE[cache_key] = []
        return []

    merged: List[Dict[str, Any]] = []
    for path, _mtime in cache_key[0]:
        try:
            with pdfplumber.open(path) as pdf:
                plain_texts: List[str] = []
                ap_v2_lists: List[List[int]] = []
                for page in pdf.pages:
                    try:
                        plain_texts.append(page.extract_text() or "")
                    except Exception:
                        plain_texts.append("")
                    ap_text = ""
                    try:
                        ap_text += " ".join(
                            str(w.get("text") or "")
                            for w in page.extract_words(use_text_flow=True, keep_blank_chars=False)
                        )
                    except Exception:
                        pass
                    try:
                        ap_text += " " + "".join(str(c.get("text") or "") for c in page.chars)
                    except Exception:
                        pass
                    ap_v2_lists.append(extract_ap_ids_v2(ap_text, valid))
        except Exception:
            continue
        for rec, ap_v2 in zip(build_plan_pages_from_texts(plain_texts), ap_v2_lists):
            rec = dict(rec)
            rec["ap_ids_v2"] = ap_v2
            rec["pdf_path"] = os.path.basename(path)
            merged.append(rec)
    _PLAN_PAGE_V2_CACHE[cache_key] = merged
    return merged


def terminal_nodes_from_point_features(point_features: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Filter KMZ point_features down to numerically-named Terminal Port Handhole
    nodes usable as AP anchors. Pure."""
    out: List[Dict[str, Any]] = []
    for pf in point_features or []:
        folder = str(pf.get("folder_path") or "").lower()
        name = str(pf.get("name") or "").strip()
        if "terminal port" not in folder:
            continue
        if not name.isdigit():
            continue
        lat, lon = pf.get("lat"), pf.get("lon")
        if lat is None or lon is None:
            continue
        out.append({"name": name, "lat": float(lat), "lon": float(lon),
                    "folder_path": pf.get("folder_path")})
    return out


def _agreement(pdf_ids: Sequence[str], hardcoded_ids: Sequence[str]) -> str:
    ps, hs = set(pdf_ids or []), set(hardcoded_ids or [])
    if not ps and not hs:
        return "both_empty"
    if not ps:
        return "pdf_empty_abstain"
    if not hs:
        return "hardcoded_empty"
    if ps == hs:
        return "equal"
    if ps & hs:
        return "overlap"
    return "conflict"


def resolve_pdf_ap_routes(
    *,
    source_file: Optional[str],
    print_tokens: Optional[Sequence[Any]],
    notes_text: Optional[str],
    plan_pages: Sequence[Dict[str, Any]],
    terminal_nodes: Sequence[Dict[str, Any]],
    route_catalog: Sequence[Dict[str, Any]],
    hardcoded_allowed_route_ids: Optional[Sequence[str]] = None,
    max_route_dist_ft: float = DEFAULT_MAX_ROUTE_DIST_FT,
) -> Dict[str, Any]:
    """Pure PDF-evidence route resolver. Returns the shadow diagnostic dict.

    Inputs are plain data (no I/O): ``plan_pages`` from
    ``build_plan_pages_from_*``; ``terminal_nodes`` from
    ``terminal_nodes_from_point_features``; ``route_catalog`` is STATE's catalog
    (each route: route_id, coords[[lat,lon]...], route_name, source_folder,
    route_role, length_ft).
    """
    hardcoded = [str(r) for r in (hardcoded_allowed_route_ids or [])]

    def _result(**over: Any) -> Dict[str, Any]:
        base: Dict[str, Any] = {
            "schema": SCHEMA_VERSION,
            "source_file": source_file,
            "print_tokens": list(print_tokens or []),
            "notes_streets": notes_streets,
            "pdf_sheets": sheets,
            "pdf_pages": [],
            "ap_ids_found": [],
            "ap_terminals_resolved": [],
            "centroid": None,
            "nearest_routes": [],
            "pdf_allowed_route_ids": [],
            "hardcoded_allowed_route_ids": hardcoded,
            "agreement": None,
            "reason": None,
        }
        base.update(over)
        base["agreement"] = _agreement(base["pdf_allowed_route_ids"], hardcoded)
        return base

    # print tokens -> integer sheet numbers
    sheets: List[int] = sorted({int(str(t).strip()) for t in (print_tokens or [])
                                if str(t).strip().isdigit()})

    notes_streets = extract_street_names(notes_text or "")
    plan_street_set = {s for p in plan_pages for s in (p.get("streets") or [])}

    # --- safety gate: notes street absent from the ENTIRE plan set -> abstain ---
    if notes_streets and all(not _street_in_set(s, plan_street_set) for s in notes_streets):
        return _result(
            reason="notes_street_absent_from_plan_set:" + ",".join(notes_streets),
        )

    if not sheets:
        return _result(reason="no_numeric_print_tokens")

    pages_for_sheets = [p for p in plan_pages if p.get("sheet_number") in sheets]
    if not pages_for_sheets:
        return _result(reason="no_plan_pages_for_print_tokens:" + ",".join(map(str, sheets)))

    pdf_pages = sorted({int(p["page_index"]) for p in pages_for_sheets})
    ap_ids_found = sorted({int(a) for p in pages_for_sheets for a in (p.get("ap_ids") or [])})

    if not ap_ids_found:
        return _result(pdf_pages=pdf_pages, reason="no_ap_ids_on_print_token_sheets")

    term_index = {str(t.get("name")).strip(): t for t in terminal_nodes
                  if str(t.get("name")).strip()}
    resolved: List[Dict[str, Any]] = []
    for ap in ap_ids_found:
        t = term_index.get(str(ap))
        if t is not None:
            resolved.append({"ap": ap, "name": str(t.get("name")),
                             "lat": float(t["lat"]), "lon": float(t["lon"])})

    if not resolved:
        return _result(pdf_pages=pdf_pages, ap_ids_found=ap_ids_found,
                       reason="no_ap_terminals_resolved")

    clat = sum(t["lat"] for t in resolved) / len(resolved)
    clon = sum(t["lon"] for t in resolved) / len(resolved)
    centroid = {"lat": round(clat, 7), "lon": round(clon, 7), "terminal_count": len(resolved)}

    # nearest corridor: min over (terminal, route vertex) haversine.
    # Rank ALL non-house-drop routes (transparency) but choose pdf_allowed only
    # from the BACKBONE class — a tail touches the terminal but is not the bore.
    ranked: List[Dict[str, Any]] = []
    ranked_backbone: List[Dict[str, Any]] = []
    for route in route_catalog or []:
        coords = route.get("coords") or []
        if not coords:
            continue
        folder = str(route.get("source_folder") or "").lower()
        if any(sub in folder for sub in _NON_CORRIDOR_FOLDER_SUBSTRINGS):
            continue
        best = min(
            _haversine_ft(t["lat"], t["lon"], float(c[0]), float(c[1]))
            for t in resolved for c in coords
        )
        entry = {
            "route_id": route.get("route_id"),
            "route_name": route.get("route_name"),
            "source_folder": route.get("source_folder"),
            "route_role": route.get("route_role"),
            "length_ft": route.get("length_ft"),
            "dist_ft": round(best, 1),
        }
        ranked.append(entry)
        if any(sub in folder for sub in _BACKBONE_FOLDER_SUBSTRINGS):
            ranked_backbone.append(entry)
    ranked.sort(key=lambda r: r["dist_ft"])
    ranked_backbone.sort(key=lambda r: r["dist_ft"])
    nearest_routes = ranked[:5]

    pdf_allowed = [r["route_id"] for r in ranked_backbone if r["dist_ft"] <= max_route_dist_ft][:2]
    if pdf_allowed:
        reason = "resolved_via_print_token_sheets"
    elif ranked and ranked[0]["dist_ft"] <= max_route_dist_ft:
        reason = "nearest_corridor_non_backbone_within_%dft" % int(max_route_dist_ft)
    else:
        reason = "no_corridor_within_%dft" % int(max_route_dist_ft)

    return _result(
        pdf_pages=pdf_pages,
        ap_ids_found=ap_ids_found,
        ap_terminals_resolved=resolved,
        centroid=centroid,
        nearest_routes=nearest_routes,
        pdf_allowed_route_ids=pdf_allowed,
        reason=reason,
    )


def apply_authoritative_override(
    shadow: Optional[Dict[str, Any]],
    group_rows: Any,
    find_route_callback,
    score_callback,
) -> Optional[Dict[str, Any]]:
    """Promote HIGH-CONFIDENCE PDF-AP evidence to an authoritative route choice.

    Returns ``{selected_route_id, scored_full, pdf_allowed_route_ids, ...}`` when
    the shadow is high-confidence — ``reason == "resolved_via_print_token_sheets"``
    AND ``pdf_allowed_route_ids`` is non-empty AND the first route resolves in
    the catalog AND scores — so the caller can promote it to the top of the
    rankings and use ``pdf_allowed_route_ids`` as the placement allow-set
    (the PDF plan-sheet/AP route WINS over the hardcoded print-sheet route).

    Returns ``None`` otherwise (empty/absent/low-confidence evidence) so the
    caller preserves existing behavior — e.g. bore_log39 (CHERI absent →
    pdf_allowed_route_ids == []) is never force-placed. Pure: route lookup and
    scoring are injected as callbacks (mirrors ``attempt_location_mismatch_rescue``);
    this function never touches geometry, scoring math, or STATE.
    """
    if not isinstance(shadow, dict):
        return None
    if shadow.get("reason") != "resolved_via_print_token_sheets":
        return None
    pdf_allowed = [str(r).strip() for r in (shadow.get("pdf_allowed_route_ids") or []) if str(r).strip()]
    if not pdf_allowed:
        return None
    rid = pdf_allowed[0]
    route = find_route_callback(rid)
    if not route:
        return None
    scored = score_callback(group_rows, route)
    if not isinstance(scored, dict) or not scored:
        return None
    return {
        "applied": True,
        "selected_route_id": rid,
        "scored_full": scored,
        "pdf_allowed_route_ids": pdf_allowed,
        "agreement": shadow.get("agreement"),
        "reason": shadow.get("reason"),
    }


# ---- Tail->Backbone Route Topology V2 (shadow-only; gated default-OFF) -------
# Diagnosed 2026-05-29 (Target #2): an AP terminal sits on a tail / vacant /
# house-drop stub, but the bored redline belongs on the connected PROPOSED
# BACKBONE ("underground cable") route. The nearest-corridor step lands on the
# stub (0-1 ft) and abstains (`nearest_corridor_non_backbone`) when the backbone
# is beyond the 250 ft radius — even though the stub's far end shares an EXACT
# vertex with that backbone. This pure layer traces terminal -> stub -> backbone
# by shared-vertex connectivity. OBSERVATION ONLY: it never feeds
# resolve_pdf_ap_routes / pdf_allowed_route_ids / placement.

# Shared-vertex threshold. Documented from the PH5 geometry: real tail/backbone
# junctions are EXACT 0.00 ft shared vertices (route_460 far-end == route_478
# vertex). 2 ft is a tight float-precision tolerance, NOT a tuned proximity knob —
# the 12 Sprint-2.5 densification-gap near-ties sit 20-65 ft from the backbone and
# deliberately DO NOT connect at this epsilon.
TOPOLOGY_EPSILON_FT = 2.0
TOPOLOGY_MAX_HOPS = 3

_ADJ_CACHE: Dict[tuple, Dict[str, set]] = {}


def _is_topology_backbone(source_folder: Optional[str]) -> bool:
    f = str(source_folder or "").lower()
    return any(sub in f for sub in _BACKBONE_FOLDER_SUBSTRINGS)


def _route_min_vertex_distance(a_coords, b_coords) -> float:
    return min(_haversine_ft(float(c1[0]), float(c1[1]), float(c2[0]), float(c2[1]))
               for c1 in a_coords for c2 in b_coords)


def build_route_adjacency(
    route_catalog: Sequence[Dict[str, Any]], epsilon_ft: float = TOPOLOGY_EPSILON_FT
) -> Dict[str, set]:
    """Pure: ``route_id -> set(route_id)`` connected by an EXACT shared vertex
    (min vertex-to-vertex distance <= ``epsilon_ft``). Candidate pairs come from a
    coarse coordinate-grid bucket, then are confirmed by exact haversine.
    Deterministic + order-independent. Cached by (epsilon, route-id set)."""
    routes = [r for r in (route_catalog or []) if r.get("coords")]
    by_id = {str(r.get("route_id")): r for r in routes}
    cache_key = (round(float(epsilon_ft), 4), tuple(sorted(by_id)))
    cached = _ADJ_CACHE.get(cache_key)
    if cached is not None:
        return cached
    buckets: Dict[tuple, set] = {}
    for rid, r in by_id.items():
        for c in r["coords"]:
            buckets.setdefault((round(float(c[0]), 5), round(float(c[1]), 5)), set()).add(rid)
    adj: Dict[str, set] = {rid: set() for rid in by_id}
    checked: set = set()
    for rids in buckets.values():
        if len(rids) < 2:
            continue
        srt = sorted(rids)
        for i in range(len(srt)):
            for j in range(i + 1, len(srt)):
                a, b = srt[i], srt[j]
                if (a, b) in checked:
                    continue
                checked.add((a, b))
                if _route_min_vertex_distance(by_id[a]["coords"], by_id[b]["coords"]) <= epsilon_ft:
                    adj[a].add(b)
                    adj[b].add(a)
    _ADJ_CACHE[cache_key] = adj
    return adj


def trace_backbone_via_topology(
    terminal_lat: float,
    terminal_lon: float,
    route_catalog: Sequence[Dict[str, Any]],
    *,
    epsilon_ft: float = TOPOLOGY_EPSILON_FT,
    max_hops: int = TOPOLOGY_MAX_HOPS,
    adjacency: Optional[Dict[str, set]] = None,
) -> Dict[str, Any]:
    """Pure deterministic trace: from the non-backbone stub routes whose vertex is
    within ``epsilon_ft`` of the terminal, BFS through non-backbone routes to the
    connected "underground cable" backbone. Returns
    ``{backbone_route_id, reason, hops, connected_count, path}`` — a SINGLE
    backbone only when exactly one is reachable at min hops; otherwise
    ``backbone_route_id=None`` with reason ``no_stub_at_terminal`` /
    ``no_backbone_reachable`` / ``ambiguous_multi_backbone:<ids>``. NEVER uses a
    nearest-distance tie-break to choose a winner (>=2 at min hops => abstain).
    Order-independent (sorted iteration)."""
    routes = [r for r in (route_catalog or []) if r.get("coords")]
    by_id = {str(r.get("route_id")): r for r in routes}
    is_bb = {rid: _is_topology_backbone(r.get("source_folder")) for rid, r in by_id.items()}
    adj = adjacency if adjacency is not None else build_route_adjacency(routes, epsilon_ft)

    def _near(coords) -> float:
        return min((_haversine_ft(float(terminal_lat), float(terminal_lon), float(c[0]), float(c[1]))
                    for c in coords), default=float("inf"))

    stubs = sorted(rid for rid, r in by_id.items()
                   if not is_bb.get(rid) and _near(r["coords"]) <= epsilon_ft)
    if not stubs:
        return {"backbone_route_id": None, "reason": "no_stub_at_terminal",
                "hops": None, "connected_count": 0, "path": []}

    reached: Dict[str, tuple] = {}
    seen = set(stubs)
    queue = deque((s, 1, [s]) for s in stubs)
    while queue:
        rid, hops, path = queue.popleft()
        for nb in sorted(adj.get(rid, ())):
            if is_bb.get(nb):
                if nb not in reached or hops < reached[nb][0]:
                    reached[nb] = (hops, path + [nb])
            elif nb not in seen and hops < max_hops:
                seen.add(nb)
                queue.append((nb, hops + 1, path + [nb]))

    if not reached:
        return {"backbone_route_id": None, "reason": "no_backbone_reachable",
                "hops": None, "connected_count": 0, "path": []}
    min_hops = min(h for h, _ in reached.values())
    winners = sorted(b for b, (h, _) in reached.items() if h == min_hops)
    if len(winners) == 1:
        w = winners[0]
        return {"backbone_route_id": w, "reason": "deterministic_single_backbone",
                "hops": min_hops, "connected_count": len(reached), "path": list(reached[w][1])}
    return {"backbone_route_id": None,
            "reason": "ambiguous_multi_backbone:" + ",".join(winners),
            "hops": min_hops, "connected_count": len(reached), "path": []}


def emit_backbone_via_topology(
    *,
    pdf_paths: Sequence[str],
    print_tokens: Optional[Sequence[Any]],
    terminal_nodes: Sequence[Dict[str, Any]],
    route_catalog: Sequence[Dict[str, Any]],
    epsilon_ft: float = TOPOLOGY_EPSILON_FT,
    max_hops: int = TOPOLOGY_MAX_HOPS,
) -> Dict[str, Any]:
    """Shadow orchestrator: recover the print-token sheets' AP terminals (via the
    V2 extractor), trace each to its connected backbone, summarize. Pure aside from
    build_plan_pages_v2's lazy PDF read. Never raises for missing inputs."""
    valid_ids = [str(t.get("name")).strip() for t in (terminal_nodes or [])
                 if str(t.get("name") or "").strip()]
    plan_pages_v2 = build_plan_pages_v2_from_pdf_paths(pdf_paths, valid_ids)
    sheets = sorted({int(str(t).strip()) for t in (print_tokens or []) if str(t).strip().isdigit()})
    ap_ids = recover_ap_ids_for_sheets_v2(plan_pages_v2, sheets)
    term_index = {str(t.get("name")).strip(): t for t in (terminal_nodes or [])
                  if str(t.get("name") or "").strip()}
    traced_terms = [term_index[str(a)] for a in ap_ids if str(a) in term_index]
    if not traced_terms:
        return {"reason": "no_ap_terminals_for_topology", "ap_ids": ap_ids,
                "epsilon_ft": epsilon_ft, "terminals_traced": 0,
                "backbones": [], "per_terminal": []}
    adj = build_route_adjacency(route_catalog, epsilon_ft)
    per_terminal: List[Dict[str, Any]] = []
    backbones = set()
    for t in traced_terms:
        tr = trace_backbone_via_topology(float(t["lat"]), float(t["lon"]), route_catalog,
                                         epsilon_ft=epsilon_ft, max_hops=max_hops, adjacency=adj)
        per_terminal.append({"ap": t.get("name"), "backbone_route_id": tr["backbone_route_id"],
                             "reason": tr["reason"], "hops": tr["hops"]})
        if tr["backbone_route_id"]:
            backbones.add(tr["backbone_route_id"])
    backbones_sorted = sorted(backbones)
    reason = ("deterministic_single_backbone" if len(backbones_sorted) == 1
              else "ambiguous_multi_backbone" if len(backbones_sorted) > 1
              else "no_backbone_reachable")
    return {"reason": reason, "ap_ids": ap_ids, "epsilon_ft": epsilon_ft,
            "terminals_traced": len(traced_terms), "backbones": backbones_sorted,
            "per_terminal": per_terminal}


def emit_shadow_for_group(
    *,
    source_file: Optional[str],
    print_tokens: Optional[Sequence[Any]],
    notes_text: Optional[str],
    pdf_paths: Sequence[str],
    point_features: Sequence[Dict[str, Any]],
    route_catalog: Sequence[Dict[str, Any]],
    hardcoded_allowed_route_ids: Optional[Sequence[str]] = None,
    extract_ap_v2: bool = False,
    topology_v2: bool = False,
) -> Dict[str, Any]:
    """Orchestrator used by the in-pipeline shadow seam. Assembles inputs from a
    live session (parses PDFs on demand, filters terminal nodes) and calls the
    pure resolver. Never raises for missing inputs — emits a reason instead.

    When ``extract_ap_v2`` is True (gated by default-OFF flag
    ``TRUELINE_PDF_AP_EXTRACT_V2`` in main.py), a read-only ``ap_ids_found_v2``
    field is added showing AP ids recovered by the words+chars extractor for the
    print-token sheets (APs that plain ``extract_text()`` drops on vector-heavy
    sheets). OBSERVATION ONLY — it does NOT feed ``resolve_pdf_ap_routes`` /
    placement / scoring / geometry. With ``extract_ap_v2`` False (default) the
    output is byte-identical (no extra key)."""
    plan_pages = build_plan_pages_from_pdf_paths(pdf_paths)
    if not plan_pages:
        return {
            "schema": SCHEMA_VERSION,
            "source_file": source_file,
            "print_tokens": list(print_tokens or []),
            "hardcoded_allowed_route_ids": [str(r) for r in (hardcoded_allowed_route_ids or [])],
            "pdf_allowed_route_ids": [],
            "agreement": _agreement([], hardcoded_allowed_route_ids or []),
            "reason": "pdf_plan_data_unavailable",
        }
    terminal_nodes = terminal_nodes_from_point_features(point_features)
    result = resolve_pdf_ap_routes(
        source_file=source_file,
        print_tokens=print_tokens,
        notes_text=notes_text,
        plan_pages=plan_pages,
        terminal_nodes=terminal_nodes,
        route_catalog=route_catalog,
        hardcoded_allowed_route_ids=hardcoded_allowed_route_ids,
    )
    # AP Extraction V2 — shadow-only diagnostic. Never mutates the resolve path
    # above; only annotates the returned dict. Default-OFF in main.py.
    if extract_ap_v2:
        try:
            valid_ids = [str(t.get("name")).strip() for t in terminal_nodes
                         if str(t.get("name") or "").strip()]
            plan_pages_v2 = build_plan_pages_v2_from_pdf_paths(pdf_paths, valid_ids)
            sheets = sorted({int(str(t).strip()) for t in (print_tokens or [])
                             if str(t).strip().isdigit()})
            result = dict(result)
            result["ap_ids_found_v2"] = recover_ap_ids_for_sheets_v2(plan_pages_v2, sheets)
            result["ap_extract_v2"] = True
        except Exception as _exc:
            result = dict(result)
            result["ap_ids_found_v2_error"] = type(_exc).__name__
    # Tail->backbone topology — shadow-only diagnostic. Never mutates the resolve
    # path above; only annotates the returned dict. Default-OFF in main.py.
    if topology_v2:
        try:
            result = dict(result)
            result["backbone_via_topology"] = emit_backbone_via_topology(
                pdf_paths=pdf_paths,
                print_tokens=print_tokens,
                terminal_nodes=terminal_nodes,
                route_catalog=route_catalog,
            )
        except Exception as _texc:
            result = dict(result)
            result["backbone_via_topology_error"] = type(_texc).__name__
    return result
