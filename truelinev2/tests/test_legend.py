from truelinev2.extract.legend import detect_legend_block, point_in_bbox


def _w(text, x0, y0, x1, y1):
    return {"text": text, "x0": x0, "y0": y0, "x1": x1, "y1": y1,
            "xc": (x0 + x1) / 2.0, "yc": (y0 + y1) / 2.0}


def _legend_words():
    labels = ["WATER", "STORM", "SEWER", "GAS", "ELECTRIC", "CATV", "FIBER", "CONDUIT"]
    return [_w(t, 100, 200 + i * 20, 180, 212 + i * 20) for i, t in enumerate(labels)]


def test_detects_vertical_legend_column():
    bbox = detect_legend_block(_legend_words())
    assert bbox is not None
    # a DIRECTIONAL BORE row in the same column/band is inside (excluded)
    assert point_in_bbox(150, 320, bbox, pad=12, pad_x_right=(bbox[2] - bbox[0]))


def test_no_legend_when_too_few_distinct():
    words = [_w("WATER", 100, 200, 180, 212), _w("GAS", 100, 300, 180, 312)]
    assert detect_legend_block(words) is None


def test_real_alignment_callout_is_outside_legend():
    bbox = detect_legend_block(_legend_words())
    # an anchor far from the legend column (out on the alignment) is NOT excluded
    assert not point_in_bbox(1500, 900, bbox, pad=12, pad_x_right=(bbox[2] - bbox[0]))
