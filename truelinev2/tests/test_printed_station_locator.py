"""Proof for the read-only plan-view printed-station locator.

It resolves a source-bound endpoint station to its 2-D position by the PRINTED LABEL, with no linear axis --
the plan-view analog of ``StationAxis.x_at`` that unblocks meandering OSP/fiber routes where a linear
``station = a*x + b`` axis does not exist. Name-free synth plans; strict refusal; no placement; class_verified
always False (never unblocks AUTO).
"""
from __future__ import annotations

import fitz

from truelinev2.extract.printed_station_locator import (
    AMBIGUOUS_STATION_LABEL,
    NO_PRINTED_STATION_LABEL,
    NOT_SOURCE_BOUND,
    PLAN_VIEW_ENDPOINTS_INCOMPLETE,
    PLAN_VIEW_ENDPOINTS_LOCATED,
    STATION_LABEL_LOCATED,
    _word_station,
    locate_printed_station,
    observe_plan_view_endpoints,
    observe_plan_view_endpoints_for_path,
)
from truelinev2.ingest.pdf import PlanPdf

# A non-collinear plan-view layout: 172+53 sits at high-x / low-station, so the three stations do NOT lie on
# any linear station=a*x+b axis (mirrors a real meandering county-fiber sheet -> NO_STATION_AXIS for the
# axis projector, but each station's position is carried by its printed label).
_LABELS = [("177+01", 92, 263), ("178+56", 135, 263), ("172+53", 481, 316)]


def _make_plan(tmp_path, labels=_LABELS, name="plan.pdf"):
    doc = fitz.open()
    page = doc.new_page(width=792, height=612)
    for text, x, y in labels:
        page.insert_text((x, y), text, fontsize=8)
    p = tmp_path / name
    doc.save(str(p))
    doc.close()
    return str(p)


def _words(path):
    plan = PlanPdf(path)
    try:
        return plan.words(1, 0)
    finally:
        plan.close()


def test_locates_printed_station_label_without_an_axis(tmp_path):
    words = _words(_make_plan(tmp_path))
    a = locate_printed_station(words, 17701.0)
    assert a.status == STATION_LABEL_LOCATED and a.text == "177+01" and a.located
    w = next(w for w in words if w["text"] == "177+01")          # the anchor IS the printed word's own centre
    assert abs(a.x - w["xc"]) < 0.01 and abs(a.y - w["yc"]) < 0.01
    b = locate_printed_station(words, 17856.0)
    assert b.status == STATION_LABEL_LOCATED and b.text == "178+56"
    assert a.x != b.x                                            # distinct printed positions


def test_locator_works_where_a_linear_axis_does_not(tmp_path):
    from truelinev2.extract.station_axis import fit_axis
    words = _words(_make_plan(tmp_path))
    pts = [(w["xc"], _word_station(w["text"])) for w in words if _word_station(w["text"]) is not None]
    axis = fit_axis(pts)
    # the three stations are non-collinear -> a linear axis is meaningless (no fit, or a large residual).
    assert axis is None or axis.residual_ft > 10.0
    # the locator does not depend on an axis: it locates by the printed label directly.
    assert locate_printed_station(words, 17253.0).status == STATION_LABEL_LOCATED


def test_missing_station_is_refused(tmp_path):
    r = locate_printed_station(_words(_make_plan(tmp_path)), 99999.0)
    assert r.status == NO_PRINTED_STATION_LABEL and r.x is None and not r.located


def test_duplicate_station_is_ambiguous(tmp_path):
    path = _make_plan(tmp_path, _LABELS + [("177+01", 400, 500)])
    r = locate_printed_station(_words(path), 17701.0)
    assert r.status == AMBIGUOUS_STATION_LABEL and r.match_count == 2 and r.x is None


def test_word_station_strips_optional_sta_prefix():
    assert _word_station("12+00") == 1200.0
    assert _word_station("STA 12+00") == 1200.0
    assert _word_station("STA. 3+50") == 350.0
    assert _word_station("nope") is None
    assert _word_station("100") is None          # no '+' -> not a station token


def test_observe_both_endpoints_located(tmp_path):
    plan = PlanPdf(_make_plan(tmp_path))
    try:
        obs = observe_plan_view_endpoints(plan, 1, 17701.0, 17856.0,
                                          start_source_bound=True, end_source_bound=True)
    finally:
        plan.close()
    assert obs.status == PLAN_VIEW_ENDPOINTS_LOCATED
    assert obs.start.located and obs.end.located
    assert obs.label_separation is not None and obs.label_separation > 0
    assert obs.class_verified is False


def test_observe_unbound_endpoint_not_searched(tmp_path):
    plan = PlanPdf(_make_plan(tmp_path))
    try:
        obs = observe_plan_view_endpoints(plan, 1, 17701.0, 17856.0,
                                          start_source_bound=False, end_source_bound=True)
    finally:
        plan.close()
    assert obs.start.status == NOT_SOURCE_BOUND
    assert obs.end.located
    assert obs.status == PLAN_VIEW_ENDPOINTS_INCOMPLETE and obs.label_separation is None


def test_observe_missing_endpoint_incomplete(tmp_path):
    obs = observe_plan_view_endpoints_for_path(_make_plan(tmp_path), 1, 17701.0, 88888.0,
                                               start_source_bound=True, end_source_bound=True)
    assert obs.start.located and obs.end.status == NO_PRINTED_STATION_LABEL
    assert obs.status == PLAN_VIEW_ENDPOINTS_INCOMPLETE


def test_class_verified_always_false(tmp_path):
    obs = observe_plan_view_endpoints_for_path(_make_plan(tmp_path), 1, 17701.0, 17856.0,
                                               start_source_bound=True, end_source_bound=True)
    assert obs.class_verified is False           # locating a label never unblocks AUTO
