from truelinev2.extract.odot import is_bore_layer
from truelinev2.match.overlap import decide_by_extent
from truelinev2.schema.models import Callout
from truelinev2.stations import feet_to_station


def _seg(f0, f1, sheet=11):
    return Callout(sheet=sheet, page=sheet, from_sta=feet_to_station(f0), to_sta=feet_to_station(f1),
                   from_ft=f0, to_ft=f1, footage=f1 - f0, text="DRAWN DIRECTIONAL BORE",
                   bbox=[0, 0, 1, 1], dialect="odot")


def test_is_bore_layer_pattern():
    assert is_bore_layer("P-PROPOSED DIRECTIONAL BORE")
    assert is_bore_layer("E-PROPOSED-DB")
    assert not is_bore_layer("E-PROPOSED UG")
    assert not is_bore_layer("E-UTIL-GAS")
    assert not is_bore_layer("E-ROW")
    assert not is_bore_layer("STATIONING-MAJOR")
    assert not is_bore_layer(None)


def test_continuous_run_covers_span_reviews():
    # M4 finding: one continuous drawn run (not segmented per bore) contains the
    # bore span -> REVIEW (location confirmed) but NEVER auto (endpoints not a
    # tight per-bore match); the run also exceeds the span -> surfaced as a caveat.
    d = decide_by_extent([_seg(1500, 2350)], 1976, 2047, 71)
    assert d["status"] == "REVIEW"
    assert d["reason"] == "DRAWN_EXTENT_COVERS_SPAN_NOT_TIGHT"
    assert "DRAWN_EXTENT_EXCEEDS_BORE_SPAN" in d["caveats"]


def test_tight_unique_extent_autos():
    d = decide_by_extent([_seg(1978, 2045)], 1976, 2047, 71)
    assert d["status"] == "AUTO_SELECT" and d["reason"] == "DRAWN_BORE_EXTENT_MATCHES_SPAN"


def test_no_drawn_geometry_abstains():
    d = decide_by_extent([_seg(3000, 3100)], 1976, 2047, 71)
    assert d["status"] == "ABSTAIN" and d["reason"] == "NO_DRAWN_BORE_OVER_SPAN"


def test_insufficient_coverage_abstains():
    d = decide_by_extent([_seg(1976, 1986)], 1976, 2047, 71, cover_min=0.6)
    assert d["status"] == "ABSTAIN" and d["reason"] == "INSUFFICIENT_DRAWN_COVERAGE"
