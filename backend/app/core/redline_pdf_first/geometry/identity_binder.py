"""Deterministic AP/SPLICE_LOC identity binder (Slice B — metadata only).

Given a selected segment's AUTHORED endpoint identities (the AP / SPLICE LOC text
already on the callout) and the RESOLVED KMZ anchor tables (``anchors.json`` +
``sheet_station_model.json``), attach a COORD-FREE chainage ``frame`` and the
EXACT-match ``geo_anchors`` to ``placement``, and set ``geometry_status``.

HARD rules (enforced by construction):
  * EXACT ``(kind, id, sheet)`` string joins only. No fuzzy, no proximity, no
    nearest, no route_id, no scoring.
  * A ``(kind,id,sheet)`` must resolve to exactly ONE distinct coordinate, else
    it is AMBIGUOUS and is rejected (never picked).
  * Coordinates are copied VERBATIM from anchors.json. No snapping, no scaling,
    no interpolation. Raw-KMZ items absent from anchors.json are NOT used (no
    promotion).
  * ``chainage = STA - datum`` where datum is the low bound of the span's cluster
    in ``sheet_station_model.json``. Subtraction only; STA is never moved.

Pure; never raises into the caller (returns having left placement untouched on
any internal error).
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from ..contracts import (
    Frame,
    GeoAnchor,
    SelectedSegment,
    GEOMETRY_STATUS_AP_ANCHORED,
    GEOMETRY_STATUS_FRAME_ONLY,
    GEOMETRY_STATUS_FAIL_SAFE_IDENTITY,
    GEO_ANCHOR_SOURCE_RESOLVED,
)

# AP-151 / AP 151 / AP151  ->  ("AP", "151")
_AP_RX = re.compile(r"\bAP[-\s]?(\d+)\b", re.I)
# SPLICE LOC 34 / SPLICE POINT 34 / SPLICE 34 / LOC34  ->  ("SPLICE_LOC", "LOC34")
_LOC_RX = re.compile(r"\b(?:SPLICE\s*(?:POINT|LOC)?\s*|LOC)[-\s]?(\d+)\b", re.I)

# anchors.json 'kind' uses AP / SPLICE; PDF identity uses AP / SPLICE_LOC.
_KIND_TO_ANCHOR = {"AP": "AP", "SPLICE_LOC": "SPLICE"}


def normalize_identity(text: str) -> Optional[Tuple[str, str]]:
    """Normalize one authored structure string to ``(kind, id)`` for an exact
    join, or ``None`` for non-anchor structures (FLOWER POT, INSTALLER HH,
    terminals, ports). AP is matched before SPLICE so ``AP-...`` always wins."""
    if not text:
        return None
    m = _AP_RX.search(text)
    if m:
        return ("AP", m.group(1))
    m = _LOC_RX.search(text)
    if m:
        return ("SPLICE_LOC", "LOC" + m.group(1))
    return None


def load_tables(analysis_dir: str) -> Dict[str, Any]:
    """Load + index the RESOLVED anchor tables from ``analysis_dir``.

    Returns ``{'anchors': {(anchor_kind,id,sheet): [rows]}, 'station_model': {...},
    'dir': analysis_dir}``. Never raises: a missing/broken file yields an empty
    index (binding then degrades to FRAME_ONLY / FAIL_SAFE_IDENTITY, never a guess).
    Non-integer anchor sheets (e.g. ``"NXp3"``) are intentionally dropped — only
    integer plan sheets can satisfy the exact join.
    """
    anchors_idx: Dict[Tuple[str, str, int], List[Dict[str, Any]]] = {}
    station_model: Dict[str, Any] = {}
    try:
        with open(os.path.join(analysis_dir, "anchors.json"), "r", encoding="utf-8") as fh:
            raw = json.load(fh)
        for row in (raw.get("anchors") or []):
            sheet = row.get("sheet")
            if not isinstance(sheet, int) or isinstance(sheet, bool):
                continue
            key = (str(row.get("kind")), str(row.get("id")), int(sheet))
            anchors_idx.setdefault(key, []).append(row)
    except Exception:
        anchors_idx = {}
    try:
        with open(os.path.join(analysis_dir, "sheet_station_model.json"), "r", encoding="utf-8") as fh:
            station_model = json.load(fh)
    except Exception:
        station_model = {}
    return {"anchors": anchors_idx, "station_model": station_model, "dir": analysis_dir}


def _cluster_datum(sm: Dict[str, Any], value_ft: float) -> float:
    """Low bound of the cluster containing ``value_ft``; else vmin; else 0.0."""
    for cl in (sm.get("clusters") or []):
        if isinstance(cl, list) and len(cl) == 2 and cl[0] <= value_ft <= cl[1]:
            return float(cl[0])
    vmin = sm.get("vmin")
    return float(vmin) if isinstance(vmin, (int, float)) and not isinstance(vmin, bool) else 0.0


def _build_frame(sheet: int, start_ft: float, end_ft: float,
                 multi_sheet: bool, station_model: Dict[str, Any]) -> Optional[Frame]:
    sm = station_model.get(str(sheet))
    if not isinstance(sm, dict):
        return None
    datum = _cluster_datum(sm, start_ft)
    return Frame(
        sheet=sheet,
        page=sm.get("page"),
        datum_ft=datum,
        chainage_start_ft=start_ft - datum,
        chainage_end_ft=end_ft - datum,
        axis={"vmin": sm.get("vmin"), "vmax": sm.get("vmax"),
              "clusters": list(sm.get("clusters") or [])},
        eqs_used=list(sm.get("eqs") or []),
        multi_sheet=multi_sheet,
        caveat=("MATCHLINE_FRAME" if multi_sheet else None),
        note="chainage = STA - datum (datum = low bound of the span's cluster); "
             "no snapping, no scaling",
    )


def bind_segment(seg: SelectedSegment, tables: Dict[str, Any]) -> None:
    """Populate ``seg.placement.{frame, geo_anchors, evidence_trail,
    geometry_status}`` by EXACT identity join. No-op when there is no placement.
    Never raises."""
    try:
        p = getattr(seg, "placement", None)
        if p is None:
            return
        anchors_idx: Dict[Tuple[str, str, int], List[Dict[str, Any]]] = tables.get("anchors") or {}
        station_model: Dict[str, Any] = tables.get("station_model") or {}
        sheets = [s for s in (list(seg.sheets) or list(p.route_key.sheets)) if isinstance(s, int)]
        start_ft = float(p.station_span_ft.start)
        end_ft = float(p.station_span_ft.end)
        lo, hi = min(start_ft, end_ft), max(start_ft, end_ft)

        # 1) normalize authored endpoint identities (order-stable, deduped)
        tokens: List[Tuple[str, str]] = []
        raw_tokens: List[str] = []
        for s in (seg.end_structures or []):
            raw_tokens.append(s)
            tok = normalize_identity(s)
            if tok and tok not in tokens:
                tokens.append(tok)

        geo_anchors: List[GeoAnchor] = []
        matched: List[Dict[str, Any]] = []
        rejected: List[Dict[str, Any]] = []

        for (kind, key) in tokens:
            anchor_kind = _KIND_TO_ANCHOR.get(kind)
            bound = False
            saw_sheet = False
            for sheet in sheets:
                rows = anchors_idx.get((anchor_kind, key, sheet)) or []
                if not rows:
                    continue
                saw_sheet = True
                # group occurrences by distinct (rounded) coordinate
                by_coord: Dict[Tuple[float, float], List[Dict[str, Any]]] = {}
                for r in rows:
                    c = r.get("coord")
                    if isinstance(c, list) and len(c) == 2:
                        ck = (round(float(c[0]), 9), round(float(c[1]), 9))
                        by_coord.setdefault(ck, []).append(r)
                if len(by_coord) != 1:
                    rejected.append({"kind": kind, "id": key, "sheet": sheet,
                                     "reason": "ambiguous_distinct_coords",
                                     "distinct_coord_count": len(by_coord)})
                    continue
                occ = next(iter(by_coord.values()))
                # occurrence choice (NOT identity choice): prefer a station inside
                # the authored span, else the tightest pxdist; coord is identical.
                within = [r for r in occ
                          if isinstance(r.get("sta"), (int, float)) and lo <= r["sta"] <= hi]
                pool = sorted(within or occ,
                              key=lambda r: (r.get("pxdist") if isinstance(r.get("pxdist"), (int, float)) else 1e9))
                best = pool[0]
                sta = float(best["sta"]) if isinstance(best.get("sta"), (int, float)) else None
                coord = [float(best["coord"][0]), float(best["coord"][1])]
                sm = station_model.get(str(sheet)) or {}
                datum = _cluster_datum(sm, sta) if sta is not None else 0.0
                geo_anchors.append(GeoAnchor(
                    kind=kind, id=key, sheet=sheet, sta=sta, coord=coord,
                    chainage_ft=(sta - datum) if sta is not None else None,
                    pxdist=(float(best["pxdist"]) if isinstance(best.get("pxdist"), (int, float)) else None),
                    source=GEO_ANCHOR_SOURCE_RESOLVED,
                    provenance={"table": "anchors.json", "anchor_kind": anchor_kind,
                                "id": key, "sheet": sheet, "occurrences": len(occ), "sta": sta},
                ))
                matched.append({"kind": kind, "id": key, "sheet": sheet, "sta": sta, "coord": coord})
                bound = True
                break  # first sheet with an exact single-coord match wins
            if not bound and not saw_sheet:
                rejected.append({"kind": kind, "id": key, "sheets": sheets,
                                 "reason": "absent_on_sheet"})

        # 2) coord-free chainage frame on the PRIMARY sheet (the one whose cluster
        #    contains the span start), else the first sheet.
        primary: Optional[int] = None
        for sheet in sheets:
            sm = station_model.get(str(sheet))
            if isinstance(sm, dict):
                for cl in (sm.get("clusters") or []):
                    if isinstance(cl, list) and len(cl) == 2 and cl[0] <= lo <= cl[1]:
                        primary = sheet
                        break
            if primary is not None:
                break
        if primary is None and sheets:
            primary = sheets[0]
        frame = (_build_frame(primary, start_ft, end_ft, len(sheets) > 1, station_model)
                 if primary is not None else None)

        # 3) status (identity first): any exact anchor -> AP_ANCHORED; else a
        #    computable frame -> FRAME_ONLY; else FAIL_SAFE_IDENTITY. Never a guess.
        if geo_anchors:
            status = GEOMETRY_STATUS_AP_ANCHORED
            reason = f"{len(geo_anchors)} exact RESOLVED anchor(s) on sheet(s) {sheets}"
        elif frame is not None:
            status = GEOMETRY_STATUS_FRAME_ONLY
            reason = "frame computed; no exact RESOLVED anchor for the authored identities"
        else:
            status = GEOMETRY_STATUS_FAIL_SAFE_IDENTITY
            reason = "no sheet frame and no exact identity anchor"

        p.frame = frame
        p.geo_anchors = geo_anchors
        p.geometry_status = status
        p.evidence_trail = {
            "identity_tokens": [{"kind": k, "id": v} for (k, v) in tokens],
            "raw_structures": raw_tokens,
            "matched": matched,
            "rejected": rejected,
            "frame_primary_sheet": primary,
            "status_reason": reason,
            "rules": ("EXACT (kind,id,sheet) join; single-distinct-coord; verbatim coord; "
                      "STA-datum; no promotion/snap/nearest/scoring/scaling/route_id"),
        }
    except Exception:
        # Honest fail-safe: never raise into selection; leave placement as-is.
        return
