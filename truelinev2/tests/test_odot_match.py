from truelinev2.match.overlap import decide_by_containment
from truelinev2.schema.models import Callout
from truelinev2.stations import feet_to_station


def _anchor(sta_ft, sheet=10):
    s = feet_to_station(sta_ft)
    return Callout(sheet=sheet, page=sheet, from_sta=s, to_sta=s, from_ft=sta_ft, to_ft=sta_ft,
                   footage=0.0, text=f"PROPOSED DIRECTIONAL BORE @ ~{s}",
                   bbox=[0, 0, 1, 1], dialect="odot")


def test_single_in_span_reviews():
    d = decide_by_containment([_anchor(1450)], 1420, 1538, 118)
    assert d["status"] == "REVIEW" and d["reason"] == "POINT_ANCHOR_WITHIN_SPAN"
    assert d["winner"][0].from_ft == 1450


def test_none_in_span_abstains():
    d = decide_by_containment([_anchor(5000)], 1420, 1538, 118)
    assert d["status"] == "ABSTAIN" and d["reason"] == "NO_ANCHOR_IN_SPAN"


def test_begin_end_same_bore_across_sheets_reviews():
    d = decide_by_containment([_anchor(1422, 10), _anchor(1536, 11)], 1420, 1538, 118)
    assert d["status"] == "REVIEW"


def test_picks_anchor_nearest_midpoint():
    d = decide_by_containment([_anchor(1425), _anchor(1479)], 1420, 1538, 118)
    assert d["winner"][0].from_ft == 1479  # midpoint is 1479
