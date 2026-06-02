"""SCRATCH authored matchline / station-frame resolver — DEFAULT-OFF.

Implements the authored-structure grammar the engine lacks:
  * station equations:  STA X+XX = 0+00      (physical_station -> local frame origin)
  * matchlines:         MATCHLINE STA A[/B] - SEE SHEET N

It does NOT modify the engine truth path. It is consulted only behind the
TRUELINE_MATCHLINE_FRAME_RESOLVER flag, to lift a bore the engine left FRAME_ONLY —
when that bore is in truth ONE authored cross-sheet run — into multiple authored
PDF evidence overlays (one canonical bore -> several overlays).

Doctrine (mirrors the OCR correction lane in ../_corrections):
  * per-bore resolutions are OWNER-REVIEWED data (frame_resolutions.json), never guessed;
  * EVERY claim is VERIFIED against the live PDF before anything is emitted;
  * EXACT authored-text / exact-station matching only — NO nearest snapping, NO scoring;
  * full evidence trail is returned; original PDF + logs untouched.
"""
from __future__ import annotations

import json
import os
import re

# Engine import: the live adapter (app.core.pdf_first_adapter._load_engine) inserts the vendored
# ``redline_pdf_first`` package root onto sys.path BEFORE this consult module is imported, so the
# top-level engine import resolves with no path bootstrap. (Scratch origin imported a sibling
# ``engine.redline_pdf_first``; the vendored layout imports the package directly.)
from redline_pdf_first.pdf import text_extract, crop

# (?:MATCHLINE )? STA A [/B] [-] SEE SHEET N   — A,B authored station strings; N target sheet.
_MATCHLINE_RE = re.compile(
    r"(?:MATCHLINE\s+)?STA\s+(\d+\+\d+)(?:\s*/\s*(\d+\+\d+))?\s*[-–]?\s*SEE\s+SHEET\s+(\d+)",
    re.I)
# STA X+XX = 0+00  — station-equation / frame-reset node.
_EQUATION_RE = re.compile(r"STA\s*(\d+\+\d+)\s*=\s*(\d+\+\d+)", re.I)


def _dedup(records, keyfn):
    out, seen = [], set()
    for r in records:
        k = keyfn(r)
        if k not in seen:
            seen.add(k)
            out.append(r)
    return out


def matchlines_in_text(text):
    """Pure: all authored MATCHLINE...SEE SHEET N labels in a text blob (PDF-free; testable)."""
    recs = [{"sta_a": m.group(1), "sta_b": m.group(2), "see_sheet": int(m.group(3)),
             "raw": " ".join(m.group(0).split())} for m in _MATCHLINE_RE.finditer(text)]
    return _dedup(recs, lambda r: (r["sta_a"], r["sta_b"], r["see_sheet"]))


def equations_in_text(text):
    """Pure: all authored STA X = 0+00 station-equation nodes in a text blob (PDF-free; testable)."""
    recs = [{"phys_sta": m.group(1), "local_origin": m.group(2), "raw": " ".join(m.group(0).split())}
            for m in _EQUATION_RE.finditer(text)]
    return _dedup(recs, lambda r: (r["phys_sta"], r["local_origin"]))


def _texts(page):
    """Authored-label text candidates for a page: blocks (grouped labels), lines, and a
    whitespace-normalized full join — robust to how PyMuPDF splits a rotated label."""
    seen, out = set(), []
    for b in text_extract.extract_blocks(page):
        t = " ".join((b.get("text") or "").split())
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    for ln in text_extract.extract_lines(page):
        t = " ".join(ln.split())
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    full = " ".join(" ".join(ln.split()) for ln in text_extract.extract_lines(page))
    if full:
        out.append(full)
    return out


def parse_matchlines(page):
    recs = []
    for t in _texts(page):
        recs.extend(matchlines_in_text(t))
    return _dedup(recs, lambda r: (r["sta_a"], r["sta_b"], r["see_sheet"]))


def parse_equations(page):
    recs = []
    for t in _texts(page):
        recs.extend(equations_in_text(t))
    return _dedup(recs, lambda r: (r["phys_sta"], r["local_origin"]))


def load_resolutions(path):
    if not os.path.isfile(path):
        return {}
    data = json.load(open(path, encoding="utf-8"))
    return {r["bore_id"]: r for r in data.get("resolutions", [])}


def _matchline_present(page, sta_a, sta_b, see_sheet):
    """Return the authored matchline on ``page`` carrying ``sta_a`` (and ``sta_b`` if given)
    to ``see_sheet`` — exact station-text + exact SEE SHEET match — else None."""
    for ml in parse_matchlines(page):
        if ml["see_sheet"] != see_sheet:
            continue
        stas = {ml["sta_a"], ml["sta_b"]}
        if sta_a in stas and (sta_b is None or sta_b in stas):
            return ml
    return None


def _anchor_label(a):
    """Display id for an anchor of any kind."""
    k = a.get("kind", "label")
    if k == "equation":
        return f"{a['phys_sta']}={a.get('local_origin', '0+00')}"
    if k == "station":
        return a["station"]
    return a["label"]


def _verify_anchor(page, a):
    """Verify ONE anchor against the live page; return ``(ok, bbox_display, detail)``.

    kind 'label'    -> exact AP/HH callout search (log12 matchline-pair class);
    kind 'equation' -> authored station-equation reset node ``STA X = 0+00`` (log38 class),
                       confirmed via parse_equations (exact phys_sta + local_origin);
    kind 'station'  -> an authored endpoint station present on the sheet.
    Exact authored match only — never nearest, never snapping, never span.
    """
    kind = a.get("kind", "label")
    if kind == "equation":
        want = (a["phys_sta"], a.get("local_origin", "0+00"))
        match = next((e for e in parse_equations(page)
                      if (e["phys_sta"], e["local_origin"]) == want), None)
        hits = text_extract.search_callout(page, a["phys_sta"])
        bbox = hits[0]["bbox_display"] if hits else None
        return (match is not None and bbox is not None), bbox, {"equation": (match or {}).get("raw")}
    query = a["station"] if kind == "station" else a["label"]
    hits = text_extract.search_callout(page, query)
    bbox = hits[0]["bbox_display"] if hits else None
    return bool(hits), bbox, {"found": query}


def verify_and_resolve(doc, resolution, sheet_offset, out_dir):
    """Verify ONE owner-reviewed resolution against the live PDF; only if every authored fact
    checks out, render one evidence overlay per anchor sheet. ``resolved`` is True only on full
    authored verification. No snapping, no scoring — exact verification of authored evidence."""
    os.makedirs(out_dir, exist_ok=True)
    bore = resolution["bore_id"]
    seam = resolution.get("matchline_seam")
    trail, gating = [], []

    home_sheet = resolution.get("home_sheet") or (seam["home_sheet"] if seam else None)
    home = doc[text_extract.page_index_for_sheet(home_sheet, sheet_offset)]

    # Cross-sheet runs carry an authored matchline seam; single-sheet host-anchored runs
    # (station-equation reset + host structure on ONE sheet, e.g. log54) carry no seam.
    if seam:
        ml = _matchline_present(home, seam["home_sta"], seam.get("neighbor_sta"), seam["neighbor_sheet"])
        gating.append(ml is not None)
        trail.append({"check": "matchline_seam", "sheet": seam["home_sheet"], "want": seam["raw"],
                      "found": (ml or {}).get("raw"), "ok": ml is not None})
        # Reciprocal is CORROBORATING only (extraction can drop a digit on the far side).
        nb = doc[text_extract.page_index_for_sheet(seam["neighbor_sheet"], sheet_offset)]
        recip = _matchline_present(nb, seam.get("neighbor_sta"), seam["home_sta"], seam["home_sheet"])
        trail.append({"check": "matchline_reciprocal", "sheet": seam["neighbor_sheet"],
                      "found": (recip or {}).get("raw"), "ok": recip is not None, "gating": False})

    overlays = []
    for a in resolution["anchors"]:
        page = doc[text_extract.page_index_for_sheet(a["sheet"], sheet_offset)]
        ok, bbox, detail = _verify_anchor(page, a)
        gating.append(ok and bbox is not None)
        lbl = _anchor_label(a)
        trail.append({"check": f"anchor:{a.get('kind', 'label')}", "id": lbl,
                      "sheet": a["sheet"], "role": a.get("role"), "ok": ok, **detail})
        if ok and bbox is not None:
            fn = (f"{bore}_s{a['sheet']}_{a.get('kind', 'label')}_{lbl}.png"
                  .replace("+", "p").replace("/", "-").replace("=", "eq").replace(" ", "_"))
            outp = crop.render_highlight_crop(
                page, bbox, os.path.join(out_dir, fn),
                caption=f"{bore} {a.get('role', '')} {a.get('kind', 'label')} {lbl} (sheet {a['sheet']})")
            if outp:
                overlays.append({"sheet": a["sheet"], "kind": a.get("kind", "label"), "id": lbl,
                                 "label": a.get("label", lbl),
                                 "station": a.get("station") or a.get("phys_sta") or "",
                                 "role": a.get("role"), "image": os.path.abspath(outp)})

    resolved = bool(overlays) and all(gating) and len(overlays) == len(resolution["anchors"])
    cross_sheet = bool(seam)
    # Honest tier: cross-sheet authored run -> matchline (C); single-sheet host-anchored
    # authored placement -> evidence_overlay (B). Never a fake-A traced line.
    status = ("matchline" if cross_sheet else "evidence_overlay") if resolved else None
    group = ("C" if cross_sheet else "B") if resolved else None
    geometry = ("MATCHLINE_FRAME_RESOLVED" if cross_sheet else "STATION_FRAME_RESOLVED") if resolved else None
    return {
        "bore_id": bore,
        "resolved": resolved,
        "geometry_status": geometry,
        "group": group,
        "status": status,
        "sheets": sorted({a["sheet"] for a in resolution["anchors"]}),
        "seam": seam,
        "anchors": resolution["anchors"],
        "overlays": overlays,
        "equations_home": parse_equations(home),
        "canonical_span": resolution.get("canonical_span"),
        "verification_trail": trail,
        "reason": None if resolved else "authored verification incomplete",
    }
