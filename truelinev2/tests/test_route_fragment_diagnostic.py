"""Proof for the read-only route fragmentation diagnostic (investigation helper).

It measures WHY isolated route linework is fragmented (component breakdown, gap taxonomy, over-exclusion,
curvature, vector density, reachability) and recommends the next code gate from evidence -- it reclassifies
nothing, bridges nothing, draws nothing. Name-free synthetic geometry; class_verified always False.
"""
from __future__ import annotations

from truelinev2.extract.route_fragment_diagnostic import (
    REC_CURVE_AWARE_BRIDGE,
    REC_GB_PRIME_EXCLUSION_TUNING,
    REC_READY_FOR_DISCRIMINATION,
    REC_UNMEASURABLE,
    diagnose_route_fragmentation,
)


def _chain(pts):
    return {"lines": [(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1]) for i in range(len(pts) - 1)]}


def _word(x0, y0, x1, y1, text="x"):
    return {"text": text, "x0": x0, "y0": y0, "x1": x1, "y1": y1,
            "xc": (x0 + x1) / 2.0, "yc": (y0 + y1) / 2.0, "block": 0}


# --- component breakdown counts fragments -------------------------------------------------------------- #
def test_component_breakdown():
    items = [_chain([(10, 10), (20, 10)]), _chain([(40, 10), (50, 10)]), _chain([(70, 10), (80, 10)])]
    d = diagnose_route_fragmentation(items, (10.0, 25.0), (80.0, 25.0))
    assert d.components == 3 and d.route_segments == 3 and d.class_verified is False
    assert len(d.component_summary) == 3


# --- colinear small gaps are bridgeable -> ready for discrimination ------------------------------------- #
def test_ready_for_discrimination():
    items = [_chain([(10, 10), (20, 10)]), _chain([(30, 10), (40, 10)]), _chain([(50, 10), (60, 10)])]
    d = diagnose_route_fragmentation(items, (10.0, 25.0), (60.0, 25.0))
    assert d.gap_taxonomy["close_colinear"] >= 2
    assert d.reachable_after_safe_bridge is True
    assert d.recommendation == REC_READY_FOR_DISCRIMINATION


# --- an excluded word-attached connector in a route gap -> exclusion tuning ----------------------------- #
def test_over_exclusion_recommends_gb_prime_tuning():
    # two long route dashes (>_LEADER_MAX so they survive) + a SHORT word-attached connector G-b' drops as a leader
    dash1 = _chain([(0, 0), (35, 0)])
    dash2 = _chain([(55, 0), (90, 0)])
    connector = _chain([(35, 0), (55, 0)])          # 20 pt, endpoint by a word -> dropped by G-b'
    words = [_word(33, -3, 45, 5, "s")]             # a printed word straddling (35,0)
    d = diagnose_route_fragmentation([dash1, dash2, connector], (0.0, 15.0), (90.0, 15.0), words=words)
    assert d.over_exclusion_gaps >= 1 and d.over_exclusion_word_attached >= 1
    assert d.recommendation == REC_GB_PRIME_EXCLUSION_TUNING


# --- gentle-turn gaps (close + curved) -> curve-aware bridge -------------------------------------------- #
def test_curvature_recommends_curve_aware_bridge():
    # three fragments forming a gentle arc; each gap turns ~30 deg (toward but not aligned) and is not a dropped seg
    items = [_chain([(0, 0), (20, 0)]),
             _chain([(28, 6), (44, 18)]),
             _chain([(50, 30), (60, 50)])]
    d = diagnose_route_fragmentation(items, (0.0, -10.0), (60.0, 60.0))
    assert d.gap_taxonomy["close_curved"] >= 2
    assert d.recommendation == REC_CURVE_AWARE_BRIDGE


# --- unmeasurable when a label is missing -------------------------------------------------------------- #
def test_unmeasurable_when_label_missing():
    d = diagnose_route_fragmentation([_chain([(0, 0), (10, 0)])], None, (10.0, 0.0))
    assert d.recommendation == REC_UNMEASURABLE and d.class_verified is False
    assert d.components == 0


# --- to_dict is JSON-friendly and carries the evidence ------------------------------------------------- #
def test_to_dict_shape():
    items = [_chain([(10, 10), (20, 10)]), _chain([(40, 10), (50, 10)])]
    d = diagnose_route_fragmentation(items, (10.0, 25.0), (50.0, 25.0))
    js = d.to_dict()
    for k in ("components", "gap_taxonomy", "over_exclusion_gaps", "all_vector_segments",
              "reachable_after_safe_bridge", "recommendation", "reasons", "class_verified"):
        assert k in js
    assert js["class_verified"] is False
