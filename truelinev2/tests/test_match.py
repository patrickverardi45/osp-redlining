from truelinev2.match.chains import build_chains
from truelinev2.match.decide import decide
from truelinev2.match.score import score_chain
from truelinev2.schema.models import Callout


def _c(fs, ts, ff, tf, foot, sheet=8, vacant=False):
    return Callout(sheet=sheet, page=sheet + 13, from_sta=fs, to_sta=ts,
                   from_ft=ff, to_ft=tf, footage=foot, vacant=vacant, text="")


def _decide(callouts, start, end):
    chains = build_chains(callouts, start, end)
    scored = [(ch, score_chain(ch, start, end, end - start)) for ch in chains]
    return decide(scored, end - start)


def test_auto_select_exact():
    d = _decide([_c("0+00", "2+99", 0, 299, 299)], 0, 299)
    assert d["status"] == "AUTO_SELECT"
    assert d["reason"] == "EXACT_BOX_FOOTAGE_AND_ENDPOINTS"
    assert d["winner"][0].from_sta == "0+00"


def test_abstain_no_match():
    d = _decide([_c("50+00", "52+00", 5000, 5200, 200)], 0, 299)
    assert d["status"] == "ABSTAIN"
    assert d["reason"] == "NO_AUTHORED_BOX_MATCH_FOR_BORE_SPAN"


def test_abstain_on_coequal_rivals():
    # two genuinely different segments both ~matching the span -> abstain (no guess)
    d = _decide([_c("0+00", "1+00", 0, 100, 100), _c("0+02", "1+02", 2, 102, 100, sheet=9)], 0, 100)
    assert d["status"] == "ABSTAIN"
    assert d["reason"] == "GE_2_COEQUAL_CANDIDATES_NO_TIEBREAKER"
