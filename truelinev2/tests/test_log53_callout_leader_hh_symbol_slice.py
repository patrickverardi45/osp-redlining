"""OWNER-PACKET-2 log53 callout-leader / HH-HH conduit source-coverage -- offline tests.

Locks the proof's pure laws: the typed result enum, the callout-token locator and the
box-enclosure rule (a framing callout box must enclose ALL tokens, so map-geometry
polygons that merely overlap are rejected), and the modeled-layer sets the dialect-gap
classification depends on. No PDF parse here (the proof runs the real sheet-5 check).
"""
from truelinev2.extract.structure_position import BRENHAM_CONDUIT_LAYERS, BRENHAM_STRUCTURE_LAYERS
from truelinev2.ingest.manual_adjudication import load_adjudication
from truelinev2.proof.run_log53_callout_leader_hh_symbol_slice import (
    ALLOWED,
    MODELED_CONDUIT_LAYERS,
    MODELED_STRUCT_TEXT_LAYERS,
    R_BINDS,
    R_DIALECT_GAP,
    _callout_box_layer,
    _callout_centroid,
)


def _w(text, xc, yc):
    return {"text": text, "xc": xc, "yc": yc}


def _box(layer, x0, y0, x1, y1, typ="fs"):
    return {"layer": layer, "type": typ, "x0": x0, "y0": y0, "x1": x1, "y1": y1,
            "xc": (x0 + x1) / 2, "yc": (y0 + y1) / 2}


def test_allowed_result_enum_exact():
    assert ALLOWED == {
        "CALLOUT_LEADER_BINDS_HH_SYMBOL",
        "CALLOUT_LEADER_REACHES_HH_SYMBOL_BUT_CONDUIT_LAYER_UNMODELED",
        "CALLOUT_TEXT_FOUND_LEADER_NOT_FOUND",
        "CALLOUT_AND_SYMBOL_FOUND_BUT_NOT_UNIQUE",
        "HH_HH_CONDUIT_LAYER_FOUND_BUT_NOT_CONNECTED",
        "SOURCE_FEATURE_PRESENT_DIALECT_GAP_CONFIRMED",
        "SOURCE_FEATURE_NOT_MACHINE_RECOVERABLE",
    }


def test_callout_centroid_isolates_local_note():
    # all five tokens within the 40 pt window of the reset anchor
    words = [_w("21+63=0+00", 738, 474), _w("NEXTLINK", 760, 480), _w("HH", 770, 480),
             _w("SPLICE", 738, 492), _w("32", 752, 492),
             _w("SPLICE", 841, 209)]  # a DIFFERENT note far away -> excluded
    centroid, near = _callout_centroid(words)
    assert centroid is not None
    assert len(near) == 5  # the far SPLICE is not included
    assert (841, 209) not in near
    assert 730 < centroid[0] < 790 and 470 < centroid[1] < 495


def test_callout_box_must_enclose_all_tokens():
    near = [(738, 474), (775, 480), (793, 480), (738, 492), (768, 492)]
    draw = [
        _box("HOUSES", 716, 462, 771, 535, "s"),   # overlaps text but stops before x=793 -> rejected
        _box("ANNOTATION", 709, 467, 800, 500),    # encloses ALL tokens -> selected
    ]
    layer, box = _callout_box_layer(draw, near)
    assert layer == "ANNOTATION"
    assert box == (709, 467, 800, 500)


def test_callout_box_none_when_no_full_enclosure():
    near = [(738, 474), (793, 480)]
    draw = [_box("HOUSES", 716, 462, 771, 535, "s")]  # never encloses x=793
    assert _callout_box_layer(draw, near) == (None, None)


def test_modeled_layer_sets_exclude_the_log53_layers():
    # the dialect-gap classification hinges on these: ANNOTATION is not a modeled
    # structure-text layer, and BORE - LATERAL is not a modeled conduit layer
    assert "ANNOTATION" not in MODELED_STRUCT_TEXT_LAYERS
    assert MODELED_STRUCT_TEXT_LAYERS == {v[0] for v in BRENHAM_STRUCTURE_LAYERS.values()}
    assert "BORE - LATERAL" not in MODELED_CONDUIT_LAYERS
    assert "BORE - PATH" not in MODELED_CONDUIT_LAYERS
    assert MODELED_CONDUIT_LAYERS == set(BRENHAM_CONDUIT_LAYERS.values())


def test_success_and_gap_results_are_in_enum():
    assert R_BINDS in ALLOWED and R_DIALECT_GAP in ALLOWED


def test_slice_consumes_start_anchor_bridge():
    doc = load_adjudication()
    l53 = next(r for r in doc["logs"] if r["log_id"] == "log53")
    start = l53["endpoint_anchors"]["start"]
    assert start["structure_class"] == "nextlink_hh"
    assert start["structure_label"] == "NEXTLINK HH"
