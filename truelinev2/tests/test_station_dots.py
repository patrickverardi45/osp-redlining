"""Station/footage-dot math for the human-confirmed redline lane (pure; no fixture, no engine/PDF).
This test embeds NO real customer/person/place names (generic stations + free-form column keys only).
"""
from __future__ import annotations

import math

from truelinev2.render import station_dots as SD

# a straight horizontal control-point polyline of arbitrary display length (300 pt)
_LINE = [{"x": 100.0, "y": 200.0}, {"x": 400.0, "y": 200.0}]


def _marks(dots):
    return [d["footage_along"] for d in dots]


def test_176_footage_dots_at_start_50_100_150_176():
    dots = SD.compute_station_dots(_LINE, footage=176.0)
    assert _marks(dots) == [0.0, 50.0, 100.0, 150.0, 176.0]        # start + 50' marks + final endpoint
    assert [d["index"] for d in dots] == [0, 1, 2, 3, 4]


def test_exact_multiple_includes_start_and_endpoint_once_not_duplicated():
    assert _marks(SD.compute_station_dots(_LINE, footage=150.0)) == [0.0, 50.0, 100.0, 150.0]
    assert _marks(SD.compute_station_dots(_LINE, footage=50.0)) == [0.0, 50.0]
    assert _marks(SD.compute_station_dots(_LINE, footage=200.0)) == [0.0, 50.0, 100.0, 150.0, 200.0]


def test_short_footage_under_50_is_start_plus_endpoint():
    assert _marks(SD.compute_station_dots(_LINE, footage=30.0)) == [0.0, 30.0]


def test_degenerate_and_zero_length_return_no_dots_safely():
    assert SD.compute_station_dots([{"x": 1, "y": 1}], footage=176.0) == []          # < 2 points
    assert SD.compute_station_dots([{"x": 1, "y": 1}, {"x": 1, "y": 1}], footage=176.0) == []  # zero length
    assert SD.compute_station_dots(_LINE, footage=0) == []                            # non-positive footage
    assert SD.compute_station_dots(_LINE, footage=-5) == []
    assert SD.compute_station_dots([], footage=176.0) == []


def test_multi_segment_polyline_places_dots_by_arc_length():
    # an L-shape: 300 right then 100 down (total 400 pt). Footage 400 -> a dot per 100 ft of arc length.
    poly = [{"x": 0.0, "y": 0.0}, {"x": 300.0, "y": 0.0}, {"x": 300.0, "y": 100.0}]
    dots = SD.compute_station_dots(poly, footage=400.0, interval_ft=100.0)
    assert _marks(dots) == [0.0, 100.0, 200.0, 300.0, 400.0]
    assert dots[0]["xy_display"] == {"x": 0.0, "y": 0.0}          # start
    assert dots[1]["xy_display"] == {"x": 100.0, "y": 0.0}        # 100 ft = 100 pt on the horizontal leg
    assert dots[-1]["xy_display"] == {"x": 300.0, "y": 100.0}     # 400 ft -> the endpoint
    # a dot past the bend (350 pt of 400) lands on the vertical leg (index 1 = start-then-this mark)
    d350 = SD.compute_station_dots(poly, footage=400.0, interval_ft=350.0)[1]
    assert d350["xy_display"]["x"] == 300.0 and 0.0 < d350["xy_display"]["y"] <= 100.0


def test_station_label_arithmetic_when_parseable():
    dots = SD.compute_station_dots(_LINE, footage=176.0, start_station="5+03")
    assert [d["station"] for d in dots] == ["5+03", "5+53", "6+03", "6+53", "6+79"]   # start station first


def test_station_null_safe_when_not_parseable():
    dots = SD.compute_station_dots(_LINE, footage=176.0, start_station="not-a-station")
    assert all(d["station"] is None for d in dots)
    assert _marks(dots) == [0.0, 50.0, 100.0, 150.0, 176.0]           # footage still present
    dots2 = SD.compute_station_dots(_LINE, footage=100.0, start_station=None)
    assert all(d["station"] is None for d in dots2)


def test_self_calibrated_scale_independent_of_drawn_length():
    # same footage, DIFFERENT drawn lengths -> same footage marks, x5 dot spacing scales with drawn length
    short = SD.compute_station_dots([{"x": 0, "y": 0}, {"x": 100, "y": 0}], footage=200.0)
    long = SD.compute_station_dots([{"x": 0, "y": 0}, {"x": 1000, "y": 0}], footage=200.0)
    assert _marks(short) == _marks(long) == [0.0, 50.0, 100.0, 150.0, 200.0]
    # the 50' mark (index 1) sits at 50/200 of the drawn length, scaling with it
    assert short[1]["xy_display"]["x"] == 25.0 and long[1]["xy_display"]["x"] == 250.0


def test_provenance_is_human_and_matches_source_anchor_contract():
    from truelinev2.contracts.source_anchor import PROVENANCE
    assert SD.PROVENANCE_HUMAN == PROVENANCE == "HUMAN_CONFIRMED_CONTROL_POINTS"
    assert all(d["provenance"] == "HUMAN_CONFIRMED_CONTROL_POINTS"
               for d in SD.compute_station_dots(_LINE, footage=100.0))


def test_dot_carries_bore_log_info():
    info = {"depth": "42", "boc": "48", "date": "2026-03-01", "crew": "A-1", "print": "17",
            "notes": "vacant", "bore_log_id": "rbl-9"}
    d = SD.compute_station_dots(_LINE, footage=100.0, info=info)[0]
    for k, v in info.items():
        assert d[k] == v


def test_stroke_polyline_with_dots_merges_and_dedups_endpoint():
    aug = SD.stroke_polyline_with_dots(_LINE, footage=176.0)
    assert aug[0] == (100.0, 200.0) and aug[-1] == (400.0, 200.0)     # endpoints preserved, not duplicated
    assert len(aug) == 5                    # start(0==ctrl0) + 50/100/150 + end(176==ctrl1); coincident deduped
    xs = [p[0] for p in aug]
    assert xs == sorted(xs)                                          # arc-length ordered


def test_two_point_anchor_stroke_is_exactly_collinear():
    """PRODUCT RULE (locked): a two-click HUMAN_CONFIRMED anchor renders a STRAIGHT segment — the dot
    vertices are linear interpolations ON that segment (never route-followed, smoothed, bent, snapped, or
    conduit-derived). Every stroke vertex must have ~zero perpendicular deviation from the click-to-click
    line and lie BETWEEN the clicks; the first/last vertices are exactly the clicks."""
    a, b = (150.0, 300.0), (460.0, 380.0)
    pts = SD.stroke_polyline_with_dots([{"x": a[0], "y": a[1]}, {"x": b[0], "y": b[1]}], footage=176.0)
    assert pts[0] == a and pts[-1] == b
    L = math.hypot(b[0] - a[0], b[1] - a[1])
    for (x, y) in pts:
        dev = abs((b[0] - a[0]) * (a[1] - y) - (a[0] - x) * (b[1] - a[1])) / L
        assert dev < 1e-9, "stroke vertex off the straight segment: %r (dev %.3g)" % ((x, y), dev)
        t = ((x - a[0]) * (b[0] - a[0]) + (y - a[1]) * (b[1] - a[1])) / (L * L)
        assert -1e-9 <= t <= 1 + 1e-9, "stroke vertex outside the segment"
    # ... and the same for a steep/reversed segment (no axis assumption)
    pts2 = SD.stroke_polyline_with_dots([{"x": 400.0, "y": 50.0}, {"x": 380.0, "y": 700.0}], footage=100.0)
    (a2, b2) = pts2[0], pts2[-1]
    L2 = math.hypot(b2[0] - a2[0], b2[1] - a2[1])
    assert all(abs((b2[0] - a2[0]) * (a2[1] - y) - (a2[0] - x) * (b2[1] - a2[1])) / L2 < 1e-9 for x, y in pts2)


def test_two_point_anchor_dots_lie_on_the_straight_segment():
    a, b = (150.0, 300.0), (460.0, 380.0)
    dots = SD.compute_station_dots([{"x": a[0], "y": a[1]}, {"x": b[0], "y": b[1]}],
                                   footage=176.0, start_station="5+03")
    assert [d["footage_along"] for d in dots] == [0.0, 50.0, 100.0, 150.0, 176.0]
    L = math.hypot(b[0] - a[0], b[1] - a[1])
    for d in dots:
        x, y = d["xy_display"]["x"], d["xy_display"]["y"]
        dev = abs((b[0] - a[0]) * (a[1] - y) - (a[0] - x) * (b[1] - a[1])) / L
        assert dev < 0.02, "dot off the straight segment: %r" % (d,)   # 0.01-rounding of the payload only


def test_dot_xys_extracts_positions():
    dots = SD.compute_station_dots(_LINE, footage=100.0)
    assert SD.dot_xys(dots) == [(d["xy_display"]["x"], d["xy_display"]["y"]) for d in dots]


# --- reviewed-row field resolution (free-form columns; corrected > normalized > raw) ----------------------

def test_resolve_bore_fields_free_form_columns():
    row = {"raw": {"Footage": "176'", "Start Station": "5+03", "Depth": "42", "BOC": "48",
                   "Crew": "Night", "Print #": "17", "Notes": "vacant"},
           "normalized": {}, "review": {"corrected_values": None}}
    f = SD.resolve_bore_fields(row)
    assert f["footage"] == 176.0 and f["start_station"] == "5+03"
    assert f["info"]["depth"] == "42" and f["info"]["boc"] == "48" and f["info"]["crew"] == "Night"
    assert f["info"]["print"] == "17" and f["info"]["notes"] == "vacant"


def test_resolve_bore_fields_corrected_wins_over_normalized_and_raw():
    row = {"raw": {"footage": "100"}, "normalized": {"footage": "150"},
           "review": {"corrected_values": {"footage": "176"}}}
    assert SD.resolve_bore_fields(row)["footage"] == 176.0


def test_resolve_bore_fields_sparse_row_is_none_safe():
    f = SD.resolve_bore_fields({})
    assert f["footage"] is None and f["start_station"] is None
    assert all(v is None for v in f["info"].values())
    assert SD.resolve_bore_fields(None)["footage"] is None


def test_resolve_bore_fields_generic_extractor_keys():
    """Rows produced by the PRODUCT's generic span extractor use footage_ft / print_raw keys — they must
    resolve (verification-exposed integration truth, not a synthetic column set)."""
    row = {"raw": {"start_station": "5+03", "end_station": "6+79", "footage_ft": 176.0, "print_raw": "17",
                   "sheet_refs": [17]}, "normalized": {"start_station": "5+03"}}
    f = SD.resolve_bore_fields(row)
    assert f["footage"] == 176.0 and f["start_station"] == "5+03" and f["info"]["print"] == "17"


def test_resolve_bore_fields_depth_boc_min_ft_aliases():
    """The strict-reader + generic-extractor lanes both write depth_min_ft/boc_min_ft (borelog_rows.py) —
    these must resolve onto the SAME dot info keys ("depth"/"boc") a manually-typed row uses, so the dot
    payload is identical regardless of which lane produced the row."""
    row = {"raw": {"start_station": "5+03", "end_station": "6+79", "footage_ft": 176.0,
                   "depth_min_ft": 42.0, "boc_min_ft": 48.0}}
    f = SD.resolve_bore_fields(row)
    assert f["info"]["depth"] == "42.0" and f["info"]["boc"] == "48.0"


def test_resolve_bore_fields_depth_boc_ft_aliases():
    """The Phase-1 handwritten-extraction tier's SpanProposal-derived rows write depth_ft/boc_ft
    (contracts/handwritten_extraction.py) for the SAME depth/BOC concept — these must resolve onto the dot
    info payload identically to every other lane (station-dot info card parity: Footage/Station/Date/Print/
    BoreLog already worked; Depth/BOC must too)."""
    row = {"raw": {"start_station": "3+50", "end_station": "4+08", "footage_ft": 58.0,
                   "depth_ft": 5.0, "boc_ft": 8.0, "crew": "JS", "notes": "Job name: Test Loop"}}
    f = SD.resolve_bore_fields(row)
    assert f["info"]["depth"] == "5.0" and f["info"]["boc"] == "8.0"
    # crew/notes are plain-key aliases already (unchanged by this fix) -- confirmed still resolving
    # alongside the newly-aliased depth/boc on the SAME handwritten-lane row shape.
    assert f["info"]["crew"] == "JS" and f["info"]["notes"] == "Job name: Test Loop"


def test_resolve_bore_fields_depth_boc_ft_alias_yields_to_existing_keys():
    """Existing keys take precedence over the newly-added depth_ft/boc_ft aliases on a row that somehow
    carries both spellings (never a behavior change for any row already resolving today)."""
    row = {"raw": {"depth_min_ft": 42.0, "depth_ft": 5.0, "boc": 48.0, "boc_ft": 8.0}}
    f = SD.resolve_bore_fields(row)
    assert f["info"]["depth"] == "42.0" and f["info"]["boc"] == "48.0"


def test_resolve_bore_fields_depth_boc_absent_stays_none():
    """No depth/boc column at all -> both info keys stay honestly None (never a fabricated zero)."""
    row = {"raw": {"start_station": "5+03", "end_station": "6+79", "footage_ft": 176.0}}
    f = SD.resolve_bore_fields(row)
    assert f["info"]["depth"] is None and f["info"]["boc"] is None


def test_footage_coercion_handles_units_and_numbers():
    assert SD.resolve_bore_fields({"raw": {"footage": 176}})["footage"] == 176.0
    assert SD.resolve_bore_fields({"raw": {"length": "176 ft"}})["footage"] == 176.0
    assert SD.resolve_bore_fields({"raw": {"footage": "n/a"}})["footage"] is None


def test_no_engine_dialect_match_imports():
    import pathlib
    src = pathlib.Path(SD.__file__).read_text(encoding="utf-8")
    for forbidden in ("truelinev2.match", "truelinev2.extract", "run_match", "select_dialect",
                      "run_callout_route_assembly_sweep", "PlanPdf", "import fitz"):
        assert forbidden not in src, "station_dots must stay pure geometry: %r" % forbidden


# --------------------------------------------------------------------------- #
# ADDENDUM (Mission 8, owner's STATION-DOT CONTRACT, ``.foreman/scratch/m8/design-dots.md``, BINDING):
# ``marks`` is an ADDITIVE optional parameter on ``compute_station_dots``/``stroke_polyline_with_dots``.
# ``marks=None`` is LOCKED to be byte-identical to the pre-addendum contract -- this is the identity lock
# the addendum's design doc requires.
# --------------------------------------------------------------------------- #
def test_compute_station_dots_marks_none_is_byte_identical_to_pre_addendum_contract():
    """LOCKED: the exact payload shape/values production emitted before this addendum, reproduced with
    ``marks`` defaulted (never passed) -- proves the default path is untouched."""
    info = {"depth": "42", "boc": "48", "date": "2026-03-01", "crew": "A-1", "print": "17",
           "notes": "vacant", "bore_log_id": "rbl-9"}
    dots = SD.compute_station_dots(_LINE, footage=176.0, start_station="5+03", info=info)
    assert dots == [
        {"index": 0, "footage_along": 0.0, "station": "5+03",
         "xy_display": {"x": 100.0, "y": 200.0}, "depth": "42", "boc": "48", "date": "2026-03-01",
         "crew": "A-1", "print": "17", "notes": "vacant", "bore_log_id": "rbl-9",
         "provenance": "HUMAN_CONFIRMED_CONTROL_POINTS"},
        {"index": 1, "footage_along": 50.0, "station": "5+53",
         "xy_display": {"x": round(100 + 300 * 50 / 176, 2), "y": 200.0}, "depth": "42", "boc": "48",
         "date": "2026-03-01", "crew": "A-1", "print": "17", "notes": "vacant", "bore_log_id": "rbl-9",
         "provenance": "HUMAN_CONFIRMED_CONTROL_POINTS"},
        {"index": 2, "footage_along": 100.0, "station": "6+03",
         "xy_display": {"x": round(100 + 300 * 100 / 176, 2), "y": 200.0}, "depth": "42", "boc": "48",
         "date": "2026-03-01", "crew": "A-1", "print": "17", "notes": "vacant", "bore_log_id": "rbl-9",
         "provenance": "HUMAN_CONFIRMED_CONTROL_POINTS"},
        {"index": 3, "footage_along": 150.0, "station": "6+53",
         "xy_display": {"x": round(100 + 300 * 150 / 176, 2), "y": 200.0}, "depth": "42", "boc": "48",
         "date": "2026-03-01", "crew": "A-1", "print": "17", "notes": "vacant", "bore_log_id": "rbl-9",
         "provenance": "HUMAN_CONFIRMED_CONTROL_POINTS"},
        {"index": 4, "footage_along": 176.0, "station": "6+79",
         "xy_display": {"x": 400.0, "y": 200.0}, "depth": "42", "boc": "48", "date": "2026-03-01",
         "crew": "A-1", "print": "17", "notes": "vacant", "bore_log_id": "rbl-9",
         "provenance": "HUMAN_CONFIRMED_CONTROL_POINTS"},
    ]
    assert "origin" not in dots[0] and "station_evidence" not in dots[0]     # additive keys ABSENT by default
    # explicit marks=None (never omitted) must match the omitted-kwarg call bit-for-bit.
    assert SD.compute_station_dots(_LINE, footage=176.0, start_station="5+03", info=info, marks=None) == dots


def test_stroke_polyline_with_dots_marks_none_is_byte_identical():
    assert (SD.stroke_polyline_with_dots(_LINE, footage=176.0)
           == SD.stroke_polyline_with_dots(_LINE, footage=176.0, marks=None))


_WP23_MARKS = [
    {"footage_along": 0.0, "origin": "SOURCE_RECORDED", "station": "3+50", "depth": "5.0", "boc": "8.0",
     "notes": None, "station_evidence": {"verbatim": "STA 3+50", "status": "READ", "confidence": "MEDIUM"}},
    {"footage_along": 50.0, "origin": "DERIVED_INTERVAL", "station": "4+00", "depth": None, "boc": None,
     "notes": None, "station_evidence": None},
    {"footage_along": 58.0, "origin": "SOURCE_RECORDED", "station": "4+08", "depth": "5.0", "boc": "8.0",
     "notes": None, "station_evidence": {"verbatim": "STA  4+08", "status": "READ", "confidence": "MEDIUM"}},
]


def test_compute_station_dots_marks_path_places_dots_at_mark_footages_and_carries_tags():
    info = {"depth": None, "boc": None, "date": "2026-03-01", "crew": "JS", "print": "23", "notes": None,
           "bore_log_id": "B-9"}
    dots = SD.compute_station_dots(_LINE, footage=58.0, info=info, marks=_WP23_MARKS)
    assert [d["footage_along"] for d in dots] == [0.0, 50.0, 58.0]
    assert [d["origin"] for d in dots] == ["SOURCE_RECORDED", "DERIVED_INTERVAL", "SOURCE_RECORDED"]
    assert [d["station"] for d in dots] == ["3+50", "4+00", "4+08"]
    # bore-level facts attached to EVERY dot regardless of origin.
    assert all(d["crew"] == "JS" and d["print"] == "23" and d["date"] == "2026-03-01" for d in dots)
    assert all(d["bore_log_id"] == "B-9" for d in dots)
    # depth/boc/station_evidence present ONLY on the marks that carry them.
    assert dots[0]["depth"] == "5.0" and dots[0]["boc"] == "8.0"
    assert dots[0]["station_evidence"]["verbatim"] == "STA 3+50"
    assert "depth" not in dots[1] and "boc" not in dots[1] and "station_evidence" not in dots[1]
    assert dots[2]["depth"] == "5.0" and dots[2]["boc"] == "8.0"
    # positions: arc-length interpolation at the mark's OWN footage_along (self-calibrated), 2dp-rounded.
    assert dots[0]["xy_display"] == {"x": 100.0, "y": 200.0}
    assert dots[1]["xy_display"] == {"x": round(100 + 300 * 50 / 58, 2), "y": 200.0}
    assert dots[2]["xy_display"] == {"x": 400.0, "y": 200.0}
    assert all(d["provenance"] == "HUMAN_CONFIRMED_CONTROL_POINTS" for d in dots)


def test_compute_station_dots_marks_path_degenerate_input_returns_empty_safely():
    assert SD.compute_station_dots([{"x": 1, "y": 1}], footage=58.0, marks=_WP23_MARKS) == []
    assert SD.compute_station_dots([], footage=58.0, marks=_WP23_MARKS) == []


def test_stroke_polyline_with_dots_marks_path_vertices_align_with_mark_positions():
    aug = SD.stroke_polyline_with_dots(_LINE, footage=58.0, marks=_WP23_MARKS)
    xs = [p[0] for p in aug]
    assert xs == sorted(xs)
    assert aug[0] == (100.0, 200.0) and aug[-1] == (400.0, 200.0)
    assert (round(100 + 300 * 50 / 58, 2), 200.0) in [(round(x, 2), y) for x, y in aug]
