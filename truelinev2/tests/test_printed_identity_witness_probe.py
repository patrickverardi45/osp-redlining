"""Printed-identity witness probe: pure matcher truths + honest-skip + read-only wiring guards.
No fixture required (matchers are tested on synthetic lines); the real-plan run is proof-only.
This test embeds NO real customer/person/place names.
"""
from __future__ import annotations

from pathlib import Path

from truelinev2.proof import run_printed_identity_witness_probe as w


def test_found_reset_equation_witness():
    lines = ["ROUTE CONTEXT", "STA 44+08 = 0+00", "MORE TEXT"]
    hits = w.match_reset_equation(lines, "44+08", "0+00")
    res = w.witness_result(w.RESET_EQUATION_TERMINUS_WITNESS, hits)
    assert res["status"] == w.FOUND and res["refusal"] is None
    assert res["hits"][0]["line_index"] == 1


def test_found_reset_equation_split_across_two_lines():
    lines = ["STA 44+08 =", "0+00"]
    res = w.witness_result(w.RESET_EQUATION_TERMINUS_WITNESS, w.match_reset_equation(lines, "44+08"))
    assert res["status"] == w.FOUND and res["hits"][0].get("joined_pair") is True


def test_found_direct_bore_callout_witness():
    lines = ["STA 5+03 TO STA 6+79 DIR. BORE (176')"]
    hits = w.match_direct_bore_callout(lines, "5+03", "6+79")
    res = w.witness_result(w.DIRECT_BORE_CALLOUT_SPAN_WITNESS, hits)
    assert res["status"] == w.FOUND and res["refusal"] is None


def test_found_direct_bore_callout_with_bore_token_on_next_block_line():
    lines = ["STA 5+03 TO STA 6+79", "DIR. BORE (176') 1-1.25\" VACANT HDPE"]
    res = w.witness_result(w.DIRECT_BORE_CALLOUT_SPAN_WITNESS, w.match_direct_bore_callout(lines, "5+03", "6+79"))
    assert res["status"] == w.FOUND and "BORE" in res["hits"][0]["line"]


def test_bare_station_pair_without_bore_token_is_not_a_callout_witness():
    assert w.match_direct_bore_callout(["STA 5+03 TO STA 6+79"], "5+03", "6+79") == []
    assert w.match_direct_bore_callout(["STA 5+03 TO STA 6+79", "PLOWED ROUTE"], "5+03", "6+79") == []


def test_ambiguous_witness_refuses():
    lines = ["STA 44+08 = 0+00", "NOTE", "STA 44+08 = 0+00"]
    res = w.witness_result(w.RESET_EQUATION_TERMINUS_WITNESS, w.match_reset_equation(lines, "44+08"))
    assert res["status"] == w.AMBIGUOUS and res["refusal"] == w.AMBIGUOUS_PRINTED_WITNESS


def test_not_found_witness_refuses():
    res = w.witness_result(w.RESET_EQUATION_TERMINUS_WITNESS, w.match_reset_equation(["NOTHING HERE"], "44+08"))
    assert res["status"] == w.NOT_FOUND and res["refusal"] == w.PRINTED_WITNESS_NOT_FOUND and res["hits"] == []


def test_no_fixture_honest_skip_writes_nothing(tmp_path):
    out = tmp_path / "witness_probe.json"
    report = w.run_probe(plan_path=str(tmp_path / "absent-plan.pdf"), out_path=str(out))
    assert report.get("skipped") is True
    assert not out.exists()


def test_probe_spec_covers_exactly_the_two_gap_bores():
    assert [p["log_id"] for p in w.PROBES] == ["log46", "log68"]
    assert {p["witness_kind"] for p in w.PROBES} == {w.RESET_EQUATION_TERMINUS_WITNESS,
                                                     w.DIRECT_BORE_CALLOUT_SPAN_WITNESS}


def test_read_only_no_product_render_engine_wiring():
    """The module must stay a pure text-scan proof: no render/match/api/contracts/store import, no PNG."""
    src = (Path(w.__file__)).read_text(encoding="utf-8")
    for forbidden in ("truelinev2.render", "truelinev2.match", "truelinev2.api", "truelinev2.contracts",
                      "product_store", "run_match", ".png", ".PNG"):
        assert forbidden not in src, "forbidden wiring token in probe module: %r" % forbidden
    assert "REVIEW_CANDIDATE" not in src.replace("no_review_candidate", "")


def test_guarantee_flags_and_status_vocabulary():
    assert set(w.ALL_STATUSES) == {"FOUND", "NOT_FOUND", "AMBIGUOUS"}
    res = w.witness_result(w.RESET_EQUATION_TERMINUS_WITNESS, [])
    assert res["status"] in w.ALL_STATUSES
