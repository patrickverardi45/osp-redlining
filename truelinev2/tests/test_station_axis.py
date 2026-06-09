from truelinev2.extract.station_axis import fit_axis, parse_tick


def test_parse_tick():
    assert parse_tick("14+00") == 1400
    assert parse_tick("9+50") == 950
    assert parse_tick("nope") is None
    assert parse_tick("STA 14+00") is None  # bare ticks only


def test_fit_and_project():
    axis = fit_axis([(100, 1400), (200, 1500), (300, 1600), (400, 1700)])
    assert axis is not None
    assert abs(axis.station_at(250) - 1550) < 1e-6


def test_fit_trims_outlier():
    axis = fit_axis([(100, 1400), (200, 1500), (300, 1600), (400, 1700), (250, 9999)])
    assert abs(axis.station_at(250) - 1550) < 5.0


def test_too_few_points():
    assert fit_axis([(1, 2)]) is None
    assert fit_axis([(5, 100), (5, 200)]) is None  # no x spread
