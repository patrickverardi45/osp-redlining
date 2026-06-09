from truelinev2.extract.brenham import pair_from_lines


def test_pair_bundled_line():
    lines = ["STA 0+00 TO STA 2+99 DIR. BORE (299') 1.25\" VACANT HDPE FOR FIBER DROP"]
    out = pair_from_lines(lines)
    assert len(out) == 1
    c = out[0]
    assert c["from_ft"] == 0.0 and c["to_ft"] == 299.0 and c["footage"] == 299.0
    assert c["footage_verified"] is True
    assert c["vacant"] is True


def test_pair_split_lines():
    out = pair_from_lines(["STA 1+00 TO STA 4+00", "DIR. BORE (300') 2\" HDPE"])
    assert len(out) == 1
    assert out[0]["footage"] == 300.0 and out[0]["footage_verified"] is True


def test_odot_style_yields_nothing_in_m1():
    # ODOT convention ("DB-01" + "PROPOSED DIRECTIONAL BORE") is NOT the Brenham
    # grammar -> 0 callouts in M1 (deferred to the M2 ODOT dialect).
    assert pair_from_lines(["PROPOSED DIRECTIONAL BORE", "VIA DIRECTIONAL BORE - MINIMUM 36\" DEPTH"]) == []
