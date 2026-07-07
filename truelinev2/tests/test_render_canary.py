"""Phase 5 hardening: a CI-safe render canary.

The deterministic 50/58 render corpus needs large, gitignored, private plan PDFs, so CI cannot run it.
This canary exercises the REAL redline-stroke render primitive (``render.crop.render_redline_stroke`` ->
``PlanPdf.render_clip`` raster + PIL stroke draw) on a SYNTHETIC blank PDF generated at test time (no
corpus, no customer/person/place names), and asserts STRUCTURAL invariants that are stable across
Pillow/fitz/OS:

  * the Red Stroke Law color constant is exactly (220, 25, 25);
  * a solid AUTO stroke draws that exact color in quantity (the stroke was rendered);
  * the background is not flooded (image corners are not the stroke color);
  * the horizontal stroke's red pixels form a narrow horizontal band (drawn in the right place).

Exact full-PNG hashes are intentionally NOT asserted: raster dimensions/bytes differ across fitz/Pillow
versions and platforms (CI = Linux, dev = Windows). This is still a real canary — it fails if the stroke
color, the draw, or the raster geometry obviously changes — without touching engine thresholds or the
private corpus, and without weakening the local deterministic tests.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

from truelinev2.ingest.pdf import PlanPdf
from truelinev2.render.crop import REDLINE_STROKE_RGB, render_redline_stroke


def _synthetic_plan(path: Path, *, w: int = 300, h: int = 300) -> None:
    """A one-page blank PDF (generic synthetic; no corpus). fitz is already a dependency."""
    import fitz

    doc = fitz.open()
    doc.new_page(width=w, height=h)
    doc.save(str(path))
    doc.close()


def test_redline_stroke_render_canary(tmp_path):
    assert REDLINE_STROKE_RGB == (220, 25, 25)          # Red Stroke Law constant lock

    pdf = tmp_path / "synthetic_plan.pdf"
    _synthetic_plan(pdf)
    plan = PlanPdf(str(pdf))
    try:
        out = render_redline_stroke(
            plan, bore_id="canary", sheet=1, offset=0,
            stroke_points=[(50.0, 150.0), (250.0, 150.0)],   # horizontal, mid-page
            status="AUTO_SELECT", reason="canary", out_dir=str(tmp_path / "out"),
            zoom=2.0, pad=130.0, caption=False)
    finally:
        plan.close()
    assert out is not None and Path(out).is_file()

    img = Image.open(out).convert("RGB")
    W, H = img.size
    data = list(img.getdata())                          # C-level; fast

    red_idx = [i for i, c in enumerate(data) if c == REDLINE_STROKE_RGB]
    assert len(red_idx) > 500                            # the stroke was actually drawn, in the exact red

    corners = [data[0], data[W - 1], data[(H - 1) * W], data[H * W - 1]]
    assert all(c != REDLINE_STROKE_RGB for c in corners)   # background not flooded with the stroke color

    ys = [i // W for i in red_idx]
    assert (max(ys) - min(ys)) < H * 0.3                # horizontal stroke -> narrow vertical band (right place)
