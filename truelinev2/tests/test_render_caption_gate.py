"""Caption gate: diagnostic caption band vs customer-facing product artifacts.

``render_redline_stroke`` historically burned a diagnostic caption band -- ``{bore_id} · {status} ·
{reason} · ...`` -- into the top 30px of every rendered stroke PNG. That is correct for diagnostics /
proof artifacts but must never reach a customer-facing product artifact (internal fixture ids and raw
engine reason codes are not product UI). The gate:

* ``caption`` is keyword-only and defaults to ``True`` -> every existing diagnostic / proof /
  adjudication call site renders BYTE-IDENTICAL output (locked here by an md5 equality).
* ``caption=False`` omits ONLY the band: no white top rectangle, no caption text; the stroke
  geometry, markers, evidence boxes, crop dimensions, and the Red Stroke Law RGB are untouched
  (locked here by a below-band pixel-identity check).

Self-contained + name-free: a tiny synthetic fitz plan, generic ids only. No engine, no store, no
placement -- render-only. No AUTO, no status change.
"""
from __future__ import annotations

import hashlib

import fitz
import pytest
from PIL import Image

from truelinev2.ingest.pdf import PlanPdf
from truelinev2.render.crop import REDLINE_STROKE_RGB, render_redline_stroke

# The caption text is drawn with fill (20,20,20) (render/crop.py) but Pillow antialiases glyphs, so
# the precise signature is DARKNESS in the band: glyph cores land near channel-sum ~60 (measured 63
# on a real artifact), while this fixture's band is otherwise pure paper (sum 765). Threshold 200
# separates the two with a wide margin.
_DARK_TEXT_SUM = 200
_BAND_H = 30                       # the caption band height painted by the renderer

# Stroke placed so the render clip's top band maps to EMPTY plan paper: bbox y=300, pad=130 ->
# clip starts at plan y=170; the only plan content (a black line) sits at y=500, far below.
_STROKE = [(200.0, 300.0), (400.0, 300.0)]


@pytest.fixture()
def plan(tmp_path):
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.draw_line((100, 500), (500, 500), color=(0, 0, 0), width=1)   # plan content, below the clip band
    p = tmp_path / "plan.pdf"
    doc.save(str(p))
    doc.close()
    pdf = PlanPdf(str(p))
    yield pdf
    pdf.close()


def _render(plan, out_dir, **kw):
    path = render_redline_stroke(
        plan, bore_id="rbl-1", sheet=1, offset=0, stroke_points=_STROKE,
        status="REVIEW", reason="SYNTHETIC_REASON_CODE", out_dir=str(out_dir), **kw)
    assert path
    return path


def _band_pixels(img):
    w = img.width
    return [img.getpixel((x, y)) for y in range(_BAND_H) for x in range(w)]


def test_default_render_is_byte_identical_to_explicit_caption_true(plan, tmp_path):
    """Backward compatibility LOCK: omitting ``caption`` == ``caption=True``, byte for byte, so every
    existing diagnostic/proof call site keeps producing identical artifacts."""
    default_png = _render(plan, tmp_path / "default")
    explicit_png = _render(plan, tmp_path / "explicit", caption=True)
    d = open(default_png, "rb").read()
    e = open(explicit_png, "rb").read()
    assert hashlib.md5(d).hexdigest() == hashlib.md5(e).hexdigest()


def test_caption_true_burns_the_diagnostic_band(plan, tmp_path):
    """Legacy diagnostic behavior: the band exists (dark caption text pixels in the top 30px)."""
    png = _render(plan, tmp_path / "diag", caption=True)
    img = Image.open(png).convert("RGB")
    assert min(sum(px) for px in _band_pixels(img)) < _DARK_TEXT_SUM   # caption text present


def test_caption_false_renders_a_clean_product_band(plan, tmp_path):
    """Product behavior: NO caption text, NO band -- the top 30px is the plan as-is (pure paper on
    this fixture) and everything below the band is pixel-identical to the caption=True render."""
    diag_png = _render(plan, tmp_path / "diag", caption=True)
    prod_png = _render(plan, tmp_path / "prod", caption=False)
    diag = Image.open(diag_png).convert("RGB")
    prod = Image.open(prod_png).convert("RGB")

    # Same crop dimensions -- the gate changes overlay text only, never the raster geometry.
    assert prod.size == diag.size

    band = _band_pixels(prod)
    assert set(band) == {(255, 255, 255)}                      # clean band: no caption text, no band
                                                               # rectangle -- blank paper on this fixture

    # Below the band: byte-identical content (stroke, markers, plan content untouched).
    w, h = prod.size
    assert (prod.crop((0, _BAND_H, w, h)).tobytes()
            == diag.crop((0, _BAND_H, w, h)).tobytes())

    # Red Stroke Law: the drawn stroke keeps the canonical RED in the product render.
    assert REDLINE_STROKE_RGB == (220, 25, 25)
    assert any(px == REDLINE_STROKE_RGB
               for px in prod.crop((0, _BAND_H, w, h)).getdata())
