"""Rotated-page geometry lock for the human source-anchor capture/render round-trip.

Regression coverage for the manual-redline misalignment on rotated plan pages (the real customer plan is
rotation 270): the browser must capture clicks in the SAME coordinate space the stroke renderer draws in.

- ``PlanPdf.page_rect_bounds`` is that space — ``page.rect`` as fitz renders it (matches ``render_page_png``
  / ``get_pixmap`` AND ``render_clip``). It is what the product plan-page / source-anchor routes now use.
- ``PlanPdf.page_bounds_display`` (``page.rect`` * ``rotation_matrix``) is LEFT UNCHANGED for its raw
  text/vector-geometry consumers (sheet-label index / route-isolation harness); on a rotated page it
  double-rotates into a negative-origin, aspect-swapped rect that does NOT match the raster — which is
  exactly why it must not back the click/render round-trip.

These tests build tiny synthetic PDFs with PyMuPDF (as ``test_review_candidate`` does) and assert the
raster/render basis directly, so they never depend on any large corpus fixture.
"""
from __future__ import annotations

import fitz

from truelinev2.ingest.pdf import PlanPdf


def _make_pdf(tmp_path, name, *, width, height, rotation):
    doc = fitz.open()
    doc.new_page(width=width, height=height)
    if rotation:
        doc[0].set_rotation(rotation)
    p = tmp_path / name
    doc.save(str(p))
    doc.close()
    return str(p)


def test_page_rect_bounds_matches_raster_and_render_basis_on_rotated_page(tmp_path):
    # Portrait mediabox 612x792 rotated 270 -> fitz renders a 792x612 LANDSCAPE page (mirrors the real plan).
    plan = PlanPdf(_make_pdf(tmp_path, "rot270.pdf", width=612, height=792, rotation=270))
    try:
        page = plan._page(1, 0)
        assert page.rotation == 270

        rb = plan.page_rect_bounds(1, 0)
        # 1) page_rect_bounds IS page.rect (the display rectangle fitz actually renders).
        assert rb == (float(page.rect.x0), float(page.rect.y0), float(page.rect.x1), float(page.rect.y1))
        assert rb == (0.0, 0.0, 792.0, 612.0)

        # 2) It matches the RASTER the browser marks on: render_page_png = get_pixmap(page.rect) * zoom.
        zoom = 2.0
        png = plan.render_page_png(1, 0, zoom=zoom)
        from PIL import Image  # local import: keep module import surface minimal
        import io
        w_px, h_px = Image.open(io.BytesIO(png)).size
        assert (w_px, h_px) == (round((rb[2] - rb[0]) * zoom), round((rb[3] - rb[1]) * zoom)) == (1584, 1224)

        # 3) It matches the RENDER basis: render_clip clips against page.rect, so a bbox expressed in
        #    page_rect_bounds space yields a clip whose origin is on-page and whose pixels are clip*zoom.
        rendered = plan.render_clip(1, 0, [300.0, 250.0, 500.0, 350.0], zoom=zoom, pad=50.0)
        assert rendered is not None
        img, clip_x0, clip_y0 = rendered
        assert (clip_x0, clip_y0) == (250.0, 200.0)                     # bbox +/- pad, inside page.rect
        assert img.size == (round(300 * zoom), round(200 * zoom)) == (600, 400)

        # 4) On a rotated page the two spaces DIVERGE: a mid-page on-screen click maps to the correct
        #    mid-page point under page_rect_bounds, but to a wrong (shifted) point under page_bounds_display.
        bd = plan.page_bounds_display(1, 0)
        assert rb != bd
        fy = 0.5
        y_rect = rb[1] + fy * (rb[3] - rb[1])
        y_disp = bd[1] + fy * (bd[3] - bd[1])
        assert y_rect == fy * page.rect.height == 306.0                 # correct: 50% down the rendered page
        assert y_disp != y_rect                                         # broken basis lands elsewhere (216.0)
    finally:
        plan.close()


def test_page_rect_bounds_equals_page_bounds_display_on_unrotated_page(tmp_path):
    # Rotation 0 -> rotation_matrix is identity -> the two are byte-identical (no behaviour change for the
    # entire rotation-0 deterministic corpus / existing demos).
    plan = PlanPdf(_make_pdf(tmp_path, "flat.pdf", width=612, height=792, rotation=0))
    try:
        assert plan._page(1, 0).rotation == 0
        rb = plan.page_rect_bounds(1, 0)
        bd = plan.page_bounds_display(1, 0)
        assert rb == bd == (0.0, 0.0, 612.0, 792.0)
    finally:
        plan.close()


def test_page_bounds_display_is_unchanged_on_rotated_page(tmp_path):
    # GUARD: this fix must NOT touch page_bounds_display (its raw text/vector consumers — sheet-label index,
    # route-isolation harness — rely on the existing rotation_matrix mapping). Lock its rotated-page output.
    plan = PlanPdf(_make_pdf(tmp_path, "rot270.pdf", width=612, height=792, rotation=270))
    try:
        bd = plan.page_bounds_display(1, 0)
        assert bd == (0.0, -180.0, 612.0, 612.0)                       # page.rect(0,0,792,612) * rot270
        # ...and it is deliberately NOT the raster/render basis.
        assert bd != plan.page_rect_bounds(1, 0)
    finally:
        plan.close()
