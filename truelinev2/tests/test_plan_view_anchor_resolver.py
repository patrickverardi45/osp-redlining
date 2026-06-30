"""Proof for the read-only plan-view anchor resolver (gate G-a').

It upgrades a located station LABEL to a source-backed anchor (leader-traced symbol / leader tip / unique nearby
symbol / unique route terminus) and refuses on every ambiguity or when only label text exists. It NEVER snaps to
the nearest passing line. Name-free synthetic geometry; class_verified always False; no placement/AUTO.
"""
from __future__ import annotations

import fitz

from truelinev2.extract.plan_view_anchor_resolver import (
    AMBIGUOUS_ANCHOR,
    ANCHOR_RESOLVED_TO_LEADER_TIP,
    ANCHOR_RESOLVED_TO_ROUTE_ENDPOINT,
    ANCHOR_RESOLVED_TO_SYMBOL,
    LABEL_ONLY_NO_ANCHOR,
    NO_SUPPORTED_ANCHOR,
    UNMEASURABLE,
    resolve_label_anchor,
    resolve_plan_view_anchor_for_path,
)


def _draw(x0, y0, x1, y1, lines=None):
    return {"x0": float(x0), "y0": float(y0), "x1": float(x1), "y1": float(y1),
            "xc": (x0 + x1) / 2.0, "yc": (y0 + y1) / 2.0, "lines": list(lines or []),
            "layer": "", "type": "s", "fill": None, "color": (0, 0, 0)}


def _box_lines(x0, y0, x1, y1):
    return [(x0, y0, x1, y0), (x1, y0, x1, y1), (x1, y1, x0, y1), (x0, y1, x0, y0)]


def _word(text, xc, yc):
    return {"text": text, "xc": float(xc), "yc": float(yc),
            "x0": xc - 5, "y0": yc - 4, "x1": xc + 5, "y1": yc + 4, "block": 0}


_W = [_word("5+00", 100, 100)]   # the located label (station 5+00 == 500 ft) at (100, 100)


def _resolve(draws):
    return resolve_label_anchor(_W, draws, draws, label_token="5+00", label_xy=(100.0, 100.0))


# --- resolution matrix (synthetic geometry, direct dicts) -------------------------------------------------- #
def test_label_to_leader_to_symbol_resolves():
    box = _draw(85, 90, 115, 110, _box_lines(85, 90, 115, 110))
    leader = _draw(113, 100, 160, 100, [(113, 100, 160, 100)])
    symbol = _draw(156, 96, 164, 104, _box_lines(156, 96, 164, 104))
    r = _resolve([box, leader, symbol])
    assert r.status == ANCHOR_RESOLVED_TO_SYMBOL and r.method == "LEADER_TRACED_SYMBOL"
    assert abs(r.x - 160) < 3 and abs(r.y - 100) < 3 and r.class_verified is False and r.resolved


def test_leader_without_symbol_resolves_to_leader_tip():
    box = _draw(85, 90, 115, 110, _box_lines(85, 90, 115, 110))
    leader = _draw(113, 100, 160, 100, [(113, 100, 160, 100)])
    r = _resolve([box, leader])                              # leader exits the box but no symbol at the tip
    assert r.status == ANCHOR_RESOLVED_TO_LEADER_TIP and abs(r.x - 160) < 3


def test_unique_nearby_symbol_resolves_when_no_leader():
    symbol = _draw(106, 96, 114, 104, _box_lines(106, 96, 114, 104))   # 8x8 symbol 10 pt from the label
    r = _resolve([symbol])
    assert r.status == ANCHOR_RESOLVED_TO_SYMBOL and r.method == "PROXIMITY_SYMBOL" and abs(r.x - 110) < 3


def test_unique_route_terminus_resolves():
    route = _draw(105, 100, 200, 100, [(105, 100, 200, 100)])   # a route line ENDING 5 pt from the label
    r = _resolve([route])
    assert r.status == ANCHOR_RESOLVED_TO_ROUTE_ENDPOINT and abs(r.x - 105) < 3


def test_passing_line_is_not_snapped_to():
    passing = _draw(0, 90, 300, 90, [(0, 90, 300, 90)])         # passes 10 pt below the label, no endpoint near
    r = _resolve([passing])
    assert r.status == LABEL_ONLY_NO_ANCHOR and r.x is None      # never snap to the nearest passing line


def test_no_linework_is_no_supported_anchor():
    far = _draw(0, 0, 50, 0, [(0, 0, 50, 0)])
    r = _resolve([far])
    assert r.status == NO_SUPPORTED_ANCHOR


def test_ambiguous_label_boxes_refuse():
    b1 = _draw(85, 90, 115, 110, _box_lines(85, 90, 115, 110))
    b2 = _draw(80, 85, 120, 115, _box_lines(80, 85, 120, 115))   # two frames contain the word (grid clutter)
    r = _resolve([b1, b2])
    assert r.status == AMBIGUOUS_ANCHOR


def test_ambiguous_nearby_symbols_refuse():
    s1 = _draw(106, 96, 114, 104, _box_lines(106, 96, 114, 104))
    s2 = _draw(86, 96, 94, 104, _box_lines(86, 96, 94, 104))
    r = _resolve([s1, s2])
    assert r.status == AMBIGUOUS_ANCHOR


def test_ambiguous_route_termini_refuse():
    r1 = _draw(105, 100, 200, 100, [(105, 100, 200, 100)])       # terminus at (105,100)
    r2 = _draw(95, 100, 95, 200, [(95, 100, 95, 200)])           # terminus at (95,100)
    r = _resolve([r1, r2])
    assert r.status == AMBIGUOUS_ANCHOR


# --- path level ------------------------------------------------------------------------------------------- #
def _plan(tmp_path, labels, name="plan.pdf"):
    doc = fitz.open()
    page = doc.new_page(width=300, height=200)
    for text, x, y in labels:
        page.insert_text((x, y), text, fontsize=8)
    p = tmp_path / name
    doc.save(str(p))
    doc.close()
    return str(p)


def test_path_unmeasurable_when_label_absent(tmp_path):
    r = resolve_plan_view_anchor_for_path(_plan(tmp_path, [("9+99", 100, 100)]), 1, 500.0)
    assert r.status == UNMEASURABLE and r.x is None


def test_path_label_present_but_no_drawings_is_no_supported(tmp_path):
    r = resolve_plan_view_anchor_for_path(_plan(tmp_path, [("5+00", 100, 100)]), 1, 500.0)
    assert r.status == NO_SUPPORTED_ANCHOR and r.x is None and r.class_verified is False
