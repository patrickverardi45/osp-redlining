"""Generate evidence-card crops for an EngineResult and wire ``render_artifact_ref``.

Imports the ``pdf`` subpackage (not ``fitz`` directly), preserving the import
boundary. Produces highlighted plan PNGs per selected/review callout — the
WORKSPACE_PLAN_EVIDENCE_PANEL artifact (never a world-map overlay).
"""
from __future__ import annotations

import os
from typing import List

from ..pdf import crop, text_extract
from . import evidence_card

DEFAULT_CARD_DIR = os.path.join("_analysis", "day3_cards")


def _safe(name: str) -> str:
    return name.replace("+", "p").replace(" ", "_").replace("/", "-")


def render_and_attach(result, pdf_path: str, out_dir: str = DEFAULT_CARD_DIR,
                      sheet_offset: int = 13):
    """Render a highlighted crop per callout for each selected/review segment and
    set ``render_artifact_ref`` on the segment's evidence-card artifact."""
    if not result.render_artifacts:
        evidence_card.attach_render_artifacts(result)

    segs = {s.segment_id: s for s in list(result.selected_segments) + list(result.review_items)}
    doc = text_extract.open_document(pdf_path)
    try:
        for art in result.render_artifacts:
            seg = segs.get(art.segment_id)
            if seg is None:
                continue
            refs: List[str] = []
            for i, c in enumerate(seg.callouts):
                if not c.bbox_display:
                    continue
                page = doc[c.sheet + sheet_offset - 1]
                fn = _safe(f"{seg.segment_id}_s{c.sheet}_{c.station_span.start}-{c.station_span.end}.png")
                outp = crop.render_highlight_crop(
                    page, c.bbox_display, os.path.join(out_dir, fn),
                    caption=f"{seg.segment_id} {seg.tier} {c.station_span.start}->{c.station_span.end} ({c.footage}')",
                )
                if outp:
                    refs.append(os.path.abspath(outp))
            if refs:
                art.ref = refs[0]
                art.payload["render_artifact_ref"] = refs
    finally:
        doc.close()
    return result
