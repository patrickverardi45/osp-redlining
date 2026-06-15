"""OWNER-PACKET-2 log53 NEXTLINK HH callout locator -- offline unit tests.

Exercises the bounded resolve_nextlink_hh_callout chain (callout grammar -> leader ->
symbol) over SYNTHETIC source items for every strict gate, plus the real-artifact start
anchor consumption. No PDF parse here (the proof runs the real sheet-5 binding).
"""
import copy

import pytest

from truelinev2.extract.structure_position import (
    CALLOUT_LEADER_NOT_FOUND,
    CALLOUT_LEADER_NOT_UNIQUE,
    CALLOUT_NOT_FOUND,
    CALLOUT_NOT_UNIQUE,
    CALLOUT_SYMBOL_DISCONNECTED,
    CALLOUT_SYMBOL_NOT_FOUND,
    CALLOUT_SYMBOL_NOT_UNIQUE,
    POSITION_BOUND,
    resolve_nextlink_hh_callout,
)
from truelinev2.ingest.manual_adjudication import load_adjudication

CALLOUT = "ANNOTATION"
SYMBOL = "NEXTLINK"


def _w(text, xc, yc):
    return {"text": text, "xc": xc, "yc": yc}


def _scene():
    """A minimal scene that BINDS: callout box + grammar + 1 leader + 1 symbol at tip."""
    words = [_w("21+63=0+00", 738, 474), _w("NEXTLINK", 775, 480), _w("HH", 790, 480)]
    drawings = [
        {"layer": CALLOUT, "x0": 709, "y0": 467, "x1": 800, "y1": 500, "xc": 754, "yc": 483},
        {"layer": CALLOUT, "x0": 684, "y0": 446, "x1": 709, "y1": 467, "xc": 696, "yc": 456,
         "lines": [(709, 467, 684, 446)]},  # leader: one end in box, tip at (684,446)
        {"layer": SYMBOL, "xc": 680, "yc": 441, "fill": (1.0, 1.0, 1.0)},  # symbol near tip
    ]
    return words, drawings


def _run(words, drawings):
    return resolve_nextlink_hh_callout(station_sta="21+63", words=words, drawings=drawings,
                                       callout_layer=CALLOUT, symbol_layer=SYMBOL)


def test_position_bound_happy_path():
    words, draw = _scene()
    v = _run(words, draw)
    assert v.result == POSITION_BOUND
    assert v.symbol_xy == (680, 441)
    assert v.detail["callout_layer"] == CALLOUT and v.detail["symbol_layer"] == SYMBOL


def test_callout_not_found_without_reset_token():
    words, draw = _scene()
    words = [w for w in words if w["text"] != "21+63=0+00"]
    assert _run(words, draw).result == CALLOUT_NOT_FOUND


def test_callout_not_found_when_grammar_missing():
    words, draw = _scene()
    words = [w for w in words if w["text"] not in ("NEXTLINK", "HH")]
    assert _run(words, draw).result == CALLOUT_NOT_FOUND


def test_callout_not_unique_with_two_reset_tokens():
    words, draw = _scene()
    words.append(_w("21+63=0+00", 200, 200))
    assert _run(words, draw).result == CALLOUT_NOT_UNIQUE


def test_leader_not_found():
    words, draw = _scene()
    draw = [d for d in draw if "lines" not in d]  # drop the leader
    assert _run(words, draw).result == CALLOUT_LEADER_NOT_FOUND


def test_leader_not_unique():
    words, draw = _scene()
    draw.append({"layer": CALLOUT, "x0": 684, "y0": 500, "x1": 709, "y1": 520, "xc": 696,
                 "yc": 510, "lines": [(709, 500, 684, 520)]})  # a 2nd leader off the box
    assert _run(words, draw).result == CALLOUT_LEADER_NOT_UNIQUE


def test_symbol_not_found():
    words, draw = _scene()
    draw = [d for d in draw if d["layer"] != SYMBOL]
    assert _run(words, draw).result == CALLOUT_SYMBOL_NOT_FOUND


def test_symbol_disconnected_when_far_from_tip():
    words, draw = _scene()
    for d in draw:
        if d["layer"] == SYMBOL:
            d["xc"], d["yc"] = 900, 441  # exists but far from the leader tip
    assert _run(words, draw).result == CALLOUT_SYMBOL_DISCONNECTED


def test_symbol_not_unique_two_clusters_at_tip():
    words, draw = _scene()
    # two clusters both within TIP_TOL of tip (684,446) but > CLUSTER_RADIUS apart
    draw = [d for d in draw if d["layer"] != SYMBOL]
    draw.append({"layer": SYMBOL, "xc": 680, "yc": 444, "fill": (1.0, 1.0, 1.0)})
    draw.append({"layer": SYMBOL, "xc": 688, "yc": 442, "fill": (1.0, 1.0, 1.0)})
    assert _run(words, draw).result == CALLOUT_SYMBOL_NOT_UNIQUE


def test_no_nearest_snap_without_leader():
    """A symbol near the callout but NO leader must not bind (no nearest-snap)."""
    words, draw = _scene()
    draw = [d for d in draw if "lines" not in d]  # remove leader; symbol still present
    assert _run(words, draw).result == CALLOUT_LEADER_NOT_FOUND


def test_slice_consumes_start_anchor_bridge():
    doc = load_adjudication()
    l53 = next(r for r in doc["logs"] if r["log_id"] == "log53")
    start = l53["endpoint_anchors"]["start"]
    assert start["structure_class"] == "nextlink_hh"
    assert start["structure_label"] == "NEXTLINK HH"
    assert start["station"] == "21+63"
