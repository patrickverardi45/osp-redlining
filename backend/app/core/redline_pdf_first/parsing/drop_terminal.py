"""Fiber-drop endpoint reader (authored PDF-space evidence; review-grade).

For a FRAME_ONLY bore on a fiber-drop sheet, read the AUTHORED plan blocks
(rotation-safe) and attribute flower-pot / terminal-cluster evidence to the bore
by EXACT authored station — never by pixel proximity, never by KMZ coordinates.

What it does:
  * classify the bore as FIBER_DROP iff its callout block contains "FOR FIBER DROP"
  * read standalone ``STA x+xx … FLOWER POT`` pedestal blocks (each carries its OWN
    printed station — the join key)
  * read terminal-cluster blocks ``PLACE <size> TERMINAL <N> PORT HH AP-<id>
    SPLICE LOC <id> TERMINAL TAIL = <ft>'``
  * attribute each flower pot to THIS bore by exact station vs the authored span:
      sta == an endpoint -> that endpoint is a DROP terminus
      start < sta < end  -> intermediate drop
      else               -> EXCLUDED (belongs to an adjacent bore)
  * the non-flower-pot endpoint (the bore origin) is the DROP_TERMINAL_CLUSTER hub
  * AP/SPLICE tokens are recorded ONLY as ``context_identities`` (terminal-area
    context shared across drops) — never anchors, never promoted.

NO coords / lat / lon / KMZ / route_id / scoring / nearest / snapping / scaling.
Positions are de-rotated ``page_bbox_display`` (authored PDF space) only.
Pure read; never raises into selection.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from ..pdf import text_extract
from . import station as st

_FLOWER = re.compile(r"FLOWER\s*POT", re.I)
_TERMINAL = re.compile(r"TERMINAL\s+(\d+)\s*PORT\s*HH", re.I)
_PLACE = re.compile(r"PLACE\s+([0-9\"'xX×]+)", re.I)
_AP = re.compile(r"\bAP[-\s]?(\d+)\b", re.I)
_LOC = re.compile(r"\b(?:SPLICE\s*(?:POINT|LOC)?\s*|LOC)[-\s]?(\d+)\b", re.I)
_TAIL = re.compile(r"TERMINAL\s*TAIL\s*=\s*(\d+)", re.I)
_STA = re.compile(r"\bSTA\s+(\d+\+\d+(?:\.\d+)?)", re.I)
_FIBER_DROP = re.compile(r"FOR\s+FIBER\s+DROP", re.I)
_STA_EQ_TOL = 0.5  # authored stations are exact; tolerate float rounding only


def _sta_ft(text: str):
    m = _STA.search(text or "")
    if not m:
        return None, None
    return st.parse_station(m.group(1)), m.group(1)


def _context_identities(end_structures: List[str]) -> List[Dict[str, str]]:
    """AP / SPLICE_LOC tokens recorded as CLUSTER CONTEXT only (not endpoint
    identity, not anchors, not promoted)."""
    out: List[Dict[str, str]] = []
    seen = set()
    for s in (end_structures or []):
        m = _AP.search(s)
        if m:
            key = ("AP", m.group(1))
        else:
            m = _LOC.search(s)
            key = ("SPLICE_LOC", "LOC" + m.group(1)) if m else None
        if key and key not in seen:
            seen.add(key)
            out.append({"kind": key[0], "id": key[1], "role": "cluster_context",
                        "source": "structures_near", "note": "terminal-area context; "
                        "shared across drops; NOT endpoint identity; NOT an anchor"})
    return out


def _terminal_cluster(text: str, bbox_display) -> Dict[str, Any]:
    t = _TERMINAL.search(text)
    place = _PLACE.search(text)
    ap = _AP.search(text)
    loc = _LOC.search(text)
    tail = _TAIL.search(text)
    sta_ft, sta_str = _sta_ft(text)
    return {
        "label": " / ".join(ln.strip() for ln in text.splitlines() if ln.strip())[:160],
        "port_count": int(t.group(1)) if t else None,
        "place_size": place.group(1) if place else None,
        "terminal_tail_ft": int(tail.group(1)) if tail else None,
        "ap_id": ap.group(1) if ap else None,
        "splice_loc_id": ("LOC" + loc.group(1)) if loc else None,
        "authored_sta": sta_str,
        "page_bbox_display": bbox_display,
        "source": "PDF_PLAN_AUTHORED",
    }


def extract(page, callout: Dict[str, Any], seg, sheet_offset: int = 13) -> Optional[Dict[str, Any]]:
    """Return a ``drop_terminal`` dict for a fiber-drop bore, or ``None`` when the
    bore is not a fiber drop / has no flower-pot terminus. Never raises."""
    try:
        if page is None or callout is None or seg is None or seg.placement is None:
            return None
        p = seg.placement
        start_ft = float(p.station_span_ft.start)
        end_ft = float(p.station_span_ft.end)
        lo, hi = min(start_ft, end_ft), max(start_ft, end_ft)
        from_sta = callout.get("from_sta")
        to_sta = callout.get("to_sta")

        blocks = text_extract.extract_blocks(page)

        # 1) classify: the bore's OWN callout block must say FOR FIBER DROP.
        bore_q = f"STA {from_sta} TO STA {to_sta}"
        bore_block = next((b for b in blocks if bore_q in (b.get("text") or "")), None)
        if bore_block is None or not _FIBER_DROP.search(bore_block.get("text") or ""):
            return None

        # 2) classify blocks: standalone flower pots vs terminal clusters.
        flower_blocks: List[Dict[str, Any]] = []
        cluster_blocks: List[Dict[str, Any]] = []
        for b in blocks:
            text = b.get("text") or ""
            if _TERMINAL.search(text):
                cluster_blocks.append(b)
            elif _FLOWER.search(text):
                flower_blocks.append(b)

        # 3) attribute flower pots by EXACT authored station (no proximity).
        endpoints_drop: List[Dict[str, Any]] = []
        intermediate: List[Dict[str, Any]] = []
        excluded: List[Dict[str, Any]] = []
        endpoint_stas = {round(start_ft, 2), round(end_ft, 2)}
        for b in flower_blocks:
            sta_ft, sta_str = _sta_ft(b.get("text") or "")
            if sta_ft is None:
                continue
            rec = {"authored_sta": sta_str, "sta_ft": sta_ft,
                   "page_bbox_display": b.get("bbox_display")}
            if any(abs(sta_ft - e) <= _STA_EQ_TOL for e in endpoint_stas):
                rec["endpoint"] = "drop"
                endpoints_drop.append(rec)
            elif lo + _STA_EQ_TOL < sta_ft < hi - _STA_EQ_TOL:
                rec["endpoint"] = "intermediate"
                intermediate.append(rec)
            else:
                rec["endpoint"] = "excluded"
                rec["reason"] = "outside_bore_span"
                excluded.append(rec)

        if not endpoints_drop:
            return None  # no authored flower-pot terminus -> not a clean drop bore

        # 4) HUB endpoint = the bore endpoint that is NOT a flower-pot drop.
        drop_stas = {round(r["sta_ft"], 2) for r in endpoints_drop}
        hub_sta_ft = next((e for e in (start_ft, end_ft) if round(e, 2) not in drop_stas), None)
        hub = None
        if hub_sta_ft is not None:
            hub = {"authored_sta": (from_sta if abs(hub_sta_ft - start_ft) <= _STA_EQ_TOL else to_sta),
                   "kind": "DROP_TERMINAL_CLUSTER",
                   "basis": "bore_origin_no_standalone_flowerpot"}

        # 5) authored terminal clusters on the sheet (evidence). Cross-reference the
        #    one whose AP matches a context identity by EXACT AP-string join.
        clusters = [_terminal_cluster(b.get("text") or "", b.get("bbox_display")) for b in cluster_blocks]
        ctx = _context_identities(seg.end_structures)
        ctx_aps = {c["id"] for c in ctx if c["kind"] == "AP"}
        for c in clusters:
            c["matches_context_ap"] = bool(c.get("ap_id") and c["ap_id"] in ctx_aps)

        drop = sorted(endpoints_drop, key=lambda r: r["sta_ft"])[-1]  # far terminus
        return {
            "bore_class": "FIBER_DROP",
            "attribution_rule": "exact_authored_station",   # NOT proximity / nearest
            "confidence": "REVIEW",                          # never AUTO
            "endpoints": {
                "hub": hub,
                "drop": {"authored_sta": drop["authored_sta"], "kind": "FLOWER_POT",
                         "basis": "exact_authored_station_join",
                         "page_bbox_display": drop["page_bbox_display"]},
            },
            "flower_pots": endpoints_drop + intermediate,
            "intermediate_drops": intermediate,
            "excluded_flower_pots": excluded,
            "context_identities": ctx,
            "sheet_terminal_clusters": clusters,
            "caveats": ["FLOWER_POT_UNLABELED_IN_KMZ",
                        "TERMINAL_CONTEXT_NOT_ENDPOINT_IDENTITY",
                        "SHEET_PRINT_UNCERTAIN_PER_SOURCE_LINEAGE"],
            "rules": ("exact authored STA join; no proximity/nearest/snapping/scaling; "
                      "no KMZ/route_id; AP/SPLICE are context only (never promoted)"),
        }
    except Exception:
        return None
