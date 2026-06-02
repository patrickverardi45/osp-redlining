"""SCRATCH BOC-offset evidence + placement-proof gate — DEFAULT-OFF, engine truth path UNTOUCHED.

Every bore log carries a per-station BOC (back-of-curb) offset in the xlsx 'boc' column. The
file-fed engine path (parsing.borelog_reader.read_borelog) reads only station/print/depth and
DROPS 'boc', so station/footage geometry alone can win a placement on the wrong sheet.

This scratch lane:
  * read_borelog_boc(path) — the engine's own bore model (via read_borelog, so NO parsing drift)
    AUGMENTED with a 'boc_evidence' block (per-station boc + endpoint boc). Helper-pure,
    non-mutating, default-off: the engine selection path neither imports nor calls this.
  * prove_candidate(...) — the candidate proof GATE. Station/footage is not enough: a candidate
    must carry, on its sheet, the authored endpoint STATION+STRUCTURE; and WHEN a nearby authored
    offset callout exists it MUST match the bore-log boc EXACTLY. A geometry-only candidate (no
    authored endpoint structure) is BLOCKED; a structure whose nearby offset != boc is DOWNGRADED.

Exact authored-text matching ONLY — never nearest, never snapping, never scoring, never span. The
co-location gate is a single FIXED radius (binary presence), not a nearest-ranking.
"""
from __future__ import annotations

import os
import re

import openpyxl

# Engine import: the live adapter guarantees the vendored ``redline_pdf_first`` package root is on
# sys.path before this consult module is imported (no path bootstrap needed in the vendored layout).
from redline_pdf_first.pdf import text_extract as tx          # PDF text primitives only
from redline_pdf_first.parsing import borelog_reader as br     # reuse engine read (no drift)

_STA = re.compile(r"(?i)^\s*sta\.?\s+")
_STA_FT = re.compile(r"^(\d+)\+(\d+)$")
_OFFSET = re.compile(r"^(\d{1,2})'$")   # small plan offset callouts: 11', 17', 25' ...


def _norm(s):
    return _STA.sub("", str(s).strip()) if s is not None else s


def _sta_ft(s):
    m = _STA_FT.match(_norm(s) or "")
    return int(m.group(1)) * 100 + int(m.group(2)) if m else None


# --------------------------------------------------------------------------- read path (scratch)
def boc_evidence_for(xlsx_path):
    """Read the 'boc' column the file-fed engine path drops; return it as evidence metadata
    aligned to stations. NON-MUTATING (data_only read). 'boc' missing -> by_station empty."""
    wb = openpyxl.load_workbook(xlsx_path, data_only=True)
    try:
        rows = list(wb.worksheets[0].iter_rows(values_only=True))
    finally:
        wb.close()
    header = [str(h).strip().lower() if h is not None else "" for h in rows[0]]
    si = header.index("station") if "station" in header else 0
    bi = header.index("boc") if "boc" in header else None
    by_station, best = [], (None, None, -1)
    for r in rows[1:]:
        if not r or si >= len(r):
            continue
        ft = _sta_ft(r[si])
        if ft is None:
            continue
        boc = r[bi] if (bi is not None and bi < len(r)) else None
        sta = str(_norm(r[si]))
        by_station.append({"station": sta, "boc_ft": boc})
        if ft > best[2]:
            best = (sta, boc, ft)
    return {"column_present": bi is not None, "by_station": by_station,
            "endpoint_station": best[0], "endpoint_boc_ft": best[1],
            "source": "xlsx 'boc' column (dropped by read_borelog; preserved here as evidence)"}


def read_borelog_boc(path):
    """Engine file-fed bore model (read_borelog) AUGMENTED with a 'boc_evidence' block.
    The engine's own read_borelog is unchanged; this is the scratch/default-off read path."""
    model = dict(br.read_borelog(path))
    model["boc_evidence"] = boc_evidence_for(path)
    return model


def endpoint_boc_ft(xlsx_path):
    """Convenience: (endpoint_station_text, boc_ft) from boc_evidence_for."""
    ev = boc_evidence_for(xlsx_path)
    return ev["endpoint_station"], ev["endpoint_boc_ft"]


# --------------------------------------------------------------------------- placement-proof gate
def structure_on_sheet(page, end_sta, structure_kw):
    """Exact: an authored text block carrying BOTH 'STA <end_sta>' and ``structure_kw``."""
    want = f"STA {end_sta}".upper()
    for b in tx.extract_blocks(page):
        t = " ".join((b.get("text") or "").split()).upper()
        if want in t and structure_kw.upper() in t:
            return True, " ".join((b.get("text") or "").split()), b["bbox_display"]
    return False, None, None


def _ctr(b):
    return ((b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0)


def _dist(a, b):
    (ax, ay), (bx, by) = _ctr(a), _ctr(b)
    return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5


def nearby_offset_callouts(page, anchor_bbox, radius=130.0):
    """All authored small offset callouts ('<n>'') co-located (<= radius px) with the anchor."""
    out = []
    for w in tx.extract_words(page):
        m = _OFFSET.match(w["text"].strip())
        if not m:
            continue
        d = _dist(anchor_bbox, w["bbox_display"])
        if d <= radius:
            out.append({"text": w["text"].strip(), "ft": int(m.group(1)), "dist": round(d, 1)})
    return sorted(out, key=lambda o: o["dist"])


def prove_candidate(page, end_sta, boc_ft, structure_kw="INSTALLER HH", radius=130.0):
    """Placement-proof gate for ONE candidate page. Verdicts:
      BOC_CONTEXT_CORROBORATED            structure + a co-located '<boc>'' offset callout
      BLOCKED_NO_AUTHORED_ENDPOINT_STRUCTURE   geometry/footage-only (no authored endpoint label)
      DOWNGRADE_BOC_OFFSET_MISMATCH       structure + nearby offset callout(s) but NONE == boc
      DOWNGRADE_STRUCTURE_ONLY_NO_BOC_CALLOUT  structure but no offset callout to check
    corroborated is True only for BOC_CONTEXT_CORROBORATED."""
    s_ok, block, _ = structure_on_sheet(page, end_sta, structure_kw)
    if not s_ok:
        return {"corroborated": False, "structure_ok": False, "boc_ok": False,
                "verdict": "BLOCKED_NO_AUTHORED_ENDPOINT_STRUCTURE", "block": None,
                "boc_token": f"{int(boc_ft)}'", "nearby_offsets": [], "boc_dists": []}
    sta_hits = tx.search_callout(page, f"STA {end_sta}") or tx.search_callout(page, end_sta)
    abox = sta_hits[0]["bbox_display"]
    offs = nearby_offset_callouts(page, abox, radius)
    boc_hits = [o["dist"] for o in offs if o["ft"] == int(boc_ft)]
    if boc_hits:
        verdict, corro = "BOC_CONTEXT_CORROBORATED", True
    elif offs:
        verdict, corro = "DOWNGRADE_BOC_OFFSET_MISMATCH", False
    else:
        verdict, corro = "DOWNGRADE_STRUCTURE_ONLY_NO_BOC_CALLOUT", False
    return {"corroborated": corro, "structure_ok": True, "boc_ok": bool(boc_hits),
            "verdict": verdict, "block": block, "boc_token": f"{int(boc_ft)}'",
            "nearby_offsets": offs, "boc_dists": sorted(boc_hits)}
