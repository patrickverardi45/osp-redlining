"""Stroke-color LAW (Patrick, 2026-06-11) -- drawn redline/stroke/bore-path
overlays are ALWAYS red, regardless of source conduit layer color, AUTO/REVIEW
status, sheet, or proof type. Source PDF evidence is never recolored.

Locks: the canonical constant IS red and is not any source-layer color; every
stroke renderer pins ITS stroke color to the canonical object (identity, not
copy -- a renderer cannot drift to purple/blue/green/source colors without
failing here); renderer sources reference the pinned name, never a raw stroke
literal."""
from __future__ import annotations

import inspect

from truelinev2.render import crop
from truelinev2.proof import (
    run_cross_sheet_conduit_join_probe as b9,
    run_log51_symbol_anchored_stroke_proof as b7,
    run_origin_conduit_topology_probe as b6,
    run_symbol_anchored_stroke_proof as b3,
)

# Source-layer colors observed in the Brenham PDF (0-1 floats) and the old
# overlay accents (0-255) that a stroke must NEVER inherit.
FORBIDDEN_STROKE_COLORS = [
    (140, 60, 160),   # purple accent (the b.6/b.9 regression this law fixes)
    (30, 90, 200),    # blue accent
    (20, 140, 60),    # green accent
    (110, 110, 110),  # grey evidence
    (173, 221, 247),  # BORE - PORT light blue (0.678,0.867,0.969 * 255)
    (169, 83, 160),   # BORE - VACANT PIPE purple (0.663,0.325,0.627 * 255)
]


def test_canonical_stroke_color_is_red():
    r, g, b = crop.REDLINE_STROKE_RGB
    assert r >= 200 and g <= 80 and b <= 80, "canonical stroke color must be RED"
    assert tuple(crop.REDLINE_STROKE_RGB) not in {tuple(c) for c in
                                                  FORBIDDEN_STROKE_COLORS}


def test_every_stroke_renderer_pins_the_canonical_object():
    pins = [(b3, "STROKE_RGB"), (b7, "STROKE_RGB"),
            (b6, "CHAIN_STROKE_RGB"), (b9, "CHAIN_STROKE_RGB")]
    for mod, name in pins:
        val = getattr(mod, name)
        assert val is crop.REDLINE_STROKE_RGB, (
            f"{mod.__name__}.{name} must BE the canonical red object -- a "
            f"copied or recolored stroke constant is the inheritance bug")


def test_renderer_sources_use_the_pin_not_raw_literals():
    sources = {
        "crop.render_redline_stroke": inspect.getsource(crop.render_redline_stroke),
        "b3._render_png": inspect.getsource(b3._render_png),
        "b7._render_png": inspect.getsource(b7._render_png),
        "b6._render_png": inspect.getsource(b6._render_png),
        "b9._render_png": inspect.getsource(b9._render_png),
    }
    pin_names = ("REDLINE_STROKE_RGB", "STROKE_RGB", "CHAIN_STROKE_RGB")
    for label, src in sources.items():
        assert any(p in src for p in pin_names), (
            f"{label} must reference the canonical stroke-color pin")
        assert "(220, 25, 25)" not in src, (
            f"{label} must not carry a raw stroke literal beside the pin")
        assert "purple" not in src, (
            f"{label} must not define a purple stroke accent")
