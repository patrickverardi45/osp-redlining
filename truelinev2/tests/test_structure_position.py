"""M8.14.b.2 -- tests pinning the structure-position solver (synthetic; no PDF).

Locks the chain-of-custody contract: word -> label box -> same-layer leader
(box edges excluded by the xor rule) -> unique symbol cluster at the tip ->
class-color check; every hop uniqueness-mandatory (0 / >= 2 -> named abstain);
label centroids are never positions; rival symbols are reported, never chosen."""
from __future__ import annotations

from truelinev2.extract.structure_position import (
    LABEL_BOX_NOT_UNIQUE,
    LABEL_WORD_NOT_UNIQUE,
    LEADER_NOT_UNIQUE,
    POSITION_BOUND,
    SYMBOL_CLASS_MISMATCH,
    SYMBOL_NOT_UNIQUE,
    cluster_symbols,
    corroborate_pair_scale,
    find_leaders,
    resolve_structure_position,
)

TABLE = {"installer_hh": ("HH - TEXT", "SYM", (1.0, 0.0, 0.0))}
RED, BLUE = (1.0, 0.0, 0.0), (0.2, 0.4, 0.7)


def _word(text, x, y):
    return {"text": text, "xc": x, "yc": y, "block": 0}


def _draw(layer, x0, y0, x1, y1, lines=(), fill=None, dtype="f"):
    return {"layer": layer, "type": dtype, "fill": fill, "color": fill,
            "x0": x0, "y0": y0, "x1": x1, "y1": y1,
            "xc": (x0 + x1) / 2.0, "yc": (y0 + y1) / 2.0, "lines": list(lines)}


def _box(x0=100.0, y0=100.0, x1=150.0, y1=116.0, layer="HH - TEXT"):
    """A label box drawing whose line items are its own edges + a diagonal --
    the real-plan shape; the xor rule must exclude all of them as leaders."""
    edges = [(x0, y0, x1, y0), (x1, y0, x1, y1), (x1, y1, x0, y1),
             (x0, y1, x0, y0), (x0, y1, x1, y0)]
    return _draw(layer, x0, y0, x1, y1, lines=edges, dtype="fs")


def _leader(fx=125.0, fy=116.0, tx=180.0, ty=160.0, layer="HH - TEXT"):
    return _draw(layer, min(fx, tx), min(fy, ty), max(fx, tx), max(fy, ty),
                 lines=[(fx, fy, tx, ty)], dtype="s")


def _symbol(cx=180.0, cy=162.0, fill=RED, layer="SYM", n=3):
    return [_draw(layer, cx - 2 + i, cy - 2, cx + 2 + i, cy + 2, fill=fill)
            for i in range(n)]


def _scene(symbol_fill=RED):
    return ([_word("0+55=0+00", 125.0, 108.0)],
            [_box(), _leader()] + _symbol(fill=symbol_fill))


def _resolve(words, drawings, cls="installer_hh", text="0+55=0+00"):
    return resolve_structure_position(label_text=text, structure_class=cls,
                                      words=words, drawings=drawings,
                                      layer_table=TABLE)


# --- happy path -------------------------------------------------------------------------

def test_full_chain_binds_symbol_position_not_label():
    words, drawings = _scene()
    v = _resolve(words, drawings)
    assert v.result == POSITION_BOUND
    # the bound position is the SYMBOL cluster, far from the label word/box
    assert abs(v.symbol_xy[0] - 181.0) <= 1.5 and abs(v.symbol_xy[1] - 162.0) <= 1.5
    assert v.word_xy == (125.0, 108.0)
    assert v.symbol_xy != v.word_xy
    assert v.leader == (125.0, 116.0, 180.0, 160.0)  # oriented box-end first


def test_rival_clusters_reported_never_selected():
    words, drawings = _scene()
    drawings += _symbol(cx=400.0, cy=162.0)  # a rival HH symbol far away
    v = _resolve(words, drawings)
    assert v.result == POSITION_BOUND
    assert abs(v.symbol_xy[0] - 181.0) <= 1.5
    assert any(abs(x - 401.0) <= 1.5 for x, _ in v.rival_cluster_xys)


# --- uniqueness-mandatory abstains ------------------------------------------------------

def test_label_word_missing_or_duplicated_abstains():
    _, drawings = _scene()
    v = _resolve([], drawings)
    assert v.result == LABEL_WORD_NOT_UNIQUE
    dup = [_word("0+55=0+00", 125.0, 108.0), _word("0+55=0+00", 300.0, 50.0)]
    v2 = _resolve(dup, drawings)
    assert v2.result == LABEL_WORD_NOT_UNIQUE
    assert v2.named_missing_relationship


def test_glyph_sized_drawings_are_not_label_boxes():
    words = [_word("0+55=0+00", 125.0, 108.0)]
    glyph = _draw("HH - TEXT", 124.0, 107.0, 127.0, 111.0)  # ~3x4 pt glyph fill
    v = _resolve(words, [glyph, _leader()] + _symbol())
    assert v.result == LABEL_BOX_NOT_UNIQUE


def test_box_edges_and_diagonal_never_count_as_leaders():
    leaders = find_leaders([_box()], "HH - TEXT", (100.0, 100.0, 150.0, 116.0))
    assert leaders == []


def test_two_leaders_abstain():
    words, _ = _scene()
    drawings = [_box(), _leader(), _leader(fx=110.0, fy=116.0, tx=60.0, ty=170.0)]
    drawings += _symbol()
    v = _resolve(words, drawings)
    assert v.result == LEADER_NOT_UNIQUE
    assert "never chosen between" in v.named_missing_relationship


def test_no_symbol_at_leader_tip_abstains_with_rivals():
    words, _ = _scene()
    drawings = [_box(), _leader()] + _symbol(cx=400.0, cy=162.0)  # only far rival
    v = _resolve(words, drawings)
    assert v.result == SYMBOL_NOT_UNIQUE
    assert v.symbol_xy is None
    assert any(abs(x - 401.0) <= 1.5 for x, _ in v.rival_cluster_xys)


def test_wrong_class_fill_refused():
    words, drawings = _scene(symbol_fill=BLUE)
    v = _resolve(words, drawings)
    assert v.result == SYMBOL_CLASS_MISMATCH
    assert v.symbol_xy is None
    assert "class fill" in v.named_missing_relationship


def test_unknown_structure_class_abstains():
    words, drawings = _scene()
    v = _resolve(words, drawings, cls="flower_pot")
    assert v.result == SYMBOL_CLASS_MISMATCH
    assert "no layer/color entry" in v.named_missing_relationship


# --- context disambiguation (M8.14.b.4) -------------------------------------------------

def _ctx_scene():
    """Duplicated identity text: one hit inside a note box that ALSO holds the
    FLOWER/POT context words; the other hit is a bare run-callout token."""
    words = [_word("2+99", 125.0, 108.0), _word("FLOWER", 112.0, 112.0),
             _word("POT", 138.0, 112.0), _word("2+99", 400.0, 50.0)]
    return words, [_box(), _leader()] + _symbol()


def test_context_disambiguates_duplicated_identity_text():
    words, drawings = _ctx_scene()
    v = _resolve(words, drawings, text="2+99")
    assert v.result == LABEL_WORD_NOT_UNIQUE  # b.2 contract: no context -> abstain
    v2 = resolve_structure_position(label_text="2+99", structure_class="installer_hh",
                                    words=words, drawings=drawings, layer_table=TABLE,
                                    context_texts=("FLOWER", "POT"))
    assert v2.result == POSITION_BOUND
    assert v2.word_xy == (125.0, 108.0)  # the note token, never the callout token


def test_context_unsatisfied_abstains():
    words, drawings = _ctx_scene()
    v = resolve_structure_position(label_text="2+99", structure_class="installer_hh",
                                   words=words, drawings=drawings, layer_table=TABLE,
                                   context_texts=("FLOWER", "POT", "MISSING"))
    assert v.result == LABEL_BOX_NOT_UNIQUE
    assert "context words" in v.named_missing_relationship


def test_two_context_boxes_abstain():
    words, drawings = _ctx_scene()
    words += [_word("2+99", 225.0, 108.0), _word("FLOWER", 212.0, 112.0),
              _word("POT", 238.0, 112.0)]
    drawings += [_box(x0=200.0, x1=250.0)]
    v = resolve_structure_position(label_text="2+99", structure_class="installer_hh",
                                   words=words, drawings=drawings, layer_table=TABLE,
                                   context_texts=("FLOWER", "POT"))
    assert v.result == LABEL_BOX_NOT_UNIQUE


def test_brenham_table_carries_flower_pot_class():
    from truelinev2.extract.structure_position import BRENHAM_STRUCTURE_LAYERS
    layer, symbol, fill = BRENHAM_STRUCTURE_LAYERS["flower_pot"]
    assert layer == "FLOWER POT - TEXT" and symbol == "FLOWER POT"
    assert fill == (0.0, 0.0, 0.0)


# --- helpers ----------------------------------------------------------------------------

def test_cluster_symbols_groups_tight_separates_far():
    clusters = cluster_symbols(_symbol() + _symbol(cx=400.0), "SYM")
    assert len(clusters) == 2
    assert all(c.drawings == 3 for c in clusters)
    assert all(RED in c.fills for c in clusters)


def test_pair_scale_corroboration():
    ok = corroborate_pair_scale((861.3, 354.2), (291.6, 355.3), 396.0, 1.44)
    assert ok["consistent"] and abs(ok["pair_scale_pt_per_ft"] - 1.4387) < 0.01
    bad = corroborate_pair_scale((0.0, 0.0), (100.0, 0.0), 396.0, 1.44)
    assert not bad["consistent"]
