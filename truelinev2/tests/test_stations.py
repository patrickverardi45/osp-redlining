from truelinev2.stations import feet_to_station, parse_station


def test_parse_basic():
    assert parse_station("0+00") == 0.0
    assert parse_station("2+99") == 299.0
    assert parse_station("12+22") == 1222.0


def test_parse_bad():
    assert parse_station("nope") is None
    assert parse_station(None) is None


def test_roundtrip():
    assert feet_to_station(299.0) == "2+99"
    assert feet_to_station(0) == "0+00"
    assert feet_to_station(1222) == "12+22"
