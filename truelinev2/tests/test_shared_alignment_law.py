"""Offline tests for the M8.20 Law 1 pure decision (SHARED_ALIGNMENT_MULTI_DROP).

The law is corpus-level and REVIEW-only. These tests pin every gate, Law 2
(typed pairwise rejection), Law 3 (intermediate stations never split the
origin), the structural-tolerance reuse (a consistency tripwire against the
engine's own equivalence formula), and the no-wiring posture (the per-bore
lane, the sweep, and the reviewer service never import this corpus-level law;
the law never imports a proof module).
"""
from __future__ import annotations

import dataclasses
import inspect
from pathlib import Path

from truelinev2.extract.design_path import JITTER_EQUIV_TOL
from truelinev2.match.shared_alignment import (
    GATE_BIJECTION,
    GATE_CONDUIT,
    GATE_DISTINCT_CHAINS,
    GATE_MULTIPORT,
    GATE_PER_BORE,
    GATE_SHARED_ALIGNMENT,
    MODE,
    SUGGESTION_LABEL,
    V_NOT_APPLICABLE,
    V_REJECTED,
    V_REVIEW,
    BoreClaim,
    _max_cross_deviation,
    shared_alignment_verdict,
)

LINE = ((0.0, 0.0), (50.0, 0.0), (100.0, 0.0))
H8 = (("0+00", "1+10", 110.0), ("1+10", "1+76", 66.0))
H32 = (("0+00", "1+30", 130.0), ("1+30", "1+77", 47.0))
UNIV = frozenset({"1+76", "1+77"})


def _claim(bid: str, boundary: str, hops, **kw) -> BoreClaim:
    base = dict(survivor_id="NEXTLINK@1,1", boundary_raw=boundary,
                chain_unique=True, join_proven=True, chain_hops=hops,
                walk_points=LINE, boundary_xy=(100.0, 0.0),
                conduit_count=2, origin_multiport=True)
    base.update(kw)
    return BoreClaim(bore_id=bid, **base)


def _pair(**overrides_for_log8):
    c8 = dataclasses.replace(_claim("log8", "1+76", H8), **overrides_for_log8)
    return [c8, _claim("log32", "1+77", H32)]


def test_all_gates_hold_yields_review_only():
    v = shared_alignment_verdict(_pair(), origin_chain_boundaries=UNIV)
    assert v["verdict"] == V_REVIEW
    assert v["review_only"] is True and v["auto"] is False
    assert v["mode"] == MODE == "REVIEW_ONLY"
    assert v["label"] == SUGGESTION_LABEL
    assert sorted(v["boundaries"]) == ["1+76", "1+77"]
    assert v["bores"] == ["log32", "log8"]


def test_fewer_than_two_or_split_survivors_not_applicable():
    one = shared_alignment_verdict([_claim("log8", "1+76", H8)],
                                   origin_chain_boundaries=UNIV)
    assert one["verdict"] == V_NOT_APPLICABLE and one["auto"] is False
    split = shared_alignment_verdict(
        [_claim("log8", "1+76", H8),
         _claim("log32", "1+77", H32, survivor_id="OTHER@9,9")],
        origin_chain_boundaries=UNIV)
    assert split["verdict"] == V_NOT_APPLICABLE


def test_per_bore_gate_rejects_when_chain_or_join_missing():
    for kw in ({"chain_unique": False}, {"join_proven": False}):
        v = shared_alignment_verdict(_pair(**kw), origin_chain_boundaries=UNIV)
        assert v["verdict"] == V_REJECTED and v["failed_gate"] == GATE_PER_BORE
        assert v["bores"] == ["log32", "log8"] and v["named_missing"]


def test_distinct_chains_gate_rejects_shared_boundary_or_hops():
    # Same boundary station OR same hop set -> not two distinct printed runs.
    same_b = shared_alignment_verdict(
        [_claim("log8", "1+76", H8), _claim("log32", "1+76", H32)],
        origin_chain_boundaries=UNIV)
    assert same_b["failed_gate"] == GATE_DISTINCT_CHAINS
    same_h = shared_alignment_verdict(
        [_claim("log8", "1+76", H8), _claim("log32", "1+77", H8)],
        origin_chain_boundaries=UNIV)
    assert same_h["failed_gate"] == GATE_DISTINCT_CHAINS


def test_shared_alignment_gate_rejects_divergent_walk_or_boundary_gap():
    far = tuple((x, y + JITTER_EQUIV_TOL + 5.0) for x, y in LINE)
    div = shared_alignment_verdict(_pair(walk_points=far),
                                   origin_chain_boundaries=UNIV)
    assert div["failed_gate"] == GATE_SHARED_ALIGNMENT
    gap = shared_alignment_verdict(
        _pair(boundary_xy=(100.0, JITTER_EQUIV_TOL + 5.0)),
        origin_chain_boundaries=UNIV)
    assert gap["failed_gate"] == GATE_SHARED_ALIGNMENT


def test_jitter_equivalent_within_tol_still_reviews():
    near = tuple((x, y + JITTER_EQUIV_TOL - 0.5) for x, y in LINE)
    v = shared_alignment_verdict(
        _pair(walk_points=near, boundary_xy=(100.0, JITTER_EQUIV_TOL - 0.5)),
        origin_chain_boundaries=UNIV)
    assert v["verdict"] == V_REVIEW


def test_conduit_and_multiport_gates_reject_missing_evidence():
    no_conduit = shared_alignment_verdict(_pair(conduit_count=0),
                                          origin_chain_boundaries=UNIV)
    assert no_conduit["failed_gate"] == GATE_CONDUIT
    no_port = shared_alignment_verdict(_pair(origin_multiport=False),
                                       origin_chain_boundaries=UNIV)
    assert no_port["failed_gate"] == GATE_MULTIPORT


def test_bijection_gate_rejects_unclaimed_or_doubly_claimed_run():
    extra = shared_alignment_verdict(
        _pair(), origin_chain_boundaries=frozenset(UNIV | {"9+99"}))
    assert extra["failed_gate"] == GATE_BIJECTION   # an unclaimed printed run
    short = shared_alignment_verdict(
        _pair(), origin_chain_boundaries=frozenset({"1+76"}))
    assert short["failed_gate"] == GATE_BIJECTION


def test_law3_intermediate_stations_never_split_a_shared_origin():
    # Two runs whose ONLY chain difference is the intermediate station still
    # share the origin (gate 3 confirms distinctness; the origin stays shared,
    # never split into two fake origins). All other gates holding -> REVIEW.
    h8 = (("0+00", "1+10", 110.0), ("1+10", "1+76", 66.0))
    h32 = (("0+00", "1+30", 130.0), ("1+30", "1+77", 47.0))
    v = shared_alignment_verdict(
        [_claim("log8", "1+76", h8), _claim("log32", "1+77", h32)],
        origin_chain_boundaries=UNIV)
    assert v["verdict"] == V_REVIEW and v["shared_origin"] == "NEXTLINK@1,1"


def test_law_has_no_auto_path_anywhere():
    # No AUTO placement status token exists in the law, and EVERY reachable
    # verdict (REVIEW / REJECTED / NOT_APPLICABLE) reports auto=False with the
    # structural REVIEW_ONLY mode -- there is no AUTO branch by construction.
    import truelinev2.match.shared_alignment as law

    assert "AUTO_SELECT" not in inspect.getsource(law)
    verdicts = [
        shared_alignment_verdict(_pair(), origin_chain_boundaries=UNIV),
        shared_alignment_verdict(_pair(conduit_count=0),
                                 origin_chain_boundaries=UNIV),
        shared_alignment_verdict([_claim("log8", "1+76", H8)],
                                 origin_chain_boundaries=UNIV),
    ]
    assert {v["verdict"] for v in verdicts} == {
        V_REVIEW, V_REJECTED, V_NOT_APPLICABLE}
    for v in verdicts:
        assert v.get("auto") is False
        assert v.get("mode") == MODE


def test_max_cross_deviation_matches_engine_equivalence_formula():
    from truelinev2.extract.design_path import _cross_deviation
    a = [(0.0, 0.0), (40.0, 5.0), (90.0, -3.0)]
    b = [(2.0, 7.0), (45.0, -6.0), (95.0, 9.0)]
    assert _max_cross_deviation(a, b) == _cross_deviation(a, b)


def test_corpus_law_not_wired_into_per_bore_lane_or_pipeline():
    pkg = Path(__file__).resolve().parents[1]
    # The corpus-level law must not be imported by the per-bore lane, the
    # sweep, or the reviewer service (no shipped wiring -> census unchanged).
    for rel in ("match/symbol_conduit_lane.py",
                "proof/run_symbol_conduit_lane_sweep.py",
                "review/reviewer_service.py"):
        src = (pkg / rel).read_text(encoding="utf-8")
        assert "shared_alignment" not in src, rel
    # The law itself must stay pure: never import a proof module.
    law_src = (pkg / "match" / "shared_alignment.py").read_text(encoding="utf-8")
    assert "truelinev2.proof" not in law_src
    assert ".proof." not in law_src
