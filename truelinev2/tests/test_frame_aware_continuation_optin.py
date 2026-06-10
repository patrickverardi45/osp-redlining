"""M8.4 -- tests for the default-OFF frame-aware continuation retry (no PDF).

Locks: flag defaults OFF; OFF/None is byte-identical; the retry fires ONLY where the
default would abstain without ambiguity; translated chains place REVIEW-capped (never
AUTO, even with exact deltas); raw chains are untouched by the graph (additive
superset); ambiguity is never overridden; strict (M8.2d blanket) semantics unchanged;
unscoreable cross-frame chains never place.
"""
from __future__ import annotations

import dataclasses

from truelinev2.config import Settings
from truelinev2.match.chains import build_chains, chain_uses_translated_link
from truelinev2.match.engine import run_match
from truelinev2.match.frames import build_frame_edges, build_frame_graph, frame_for_sheet, parse_frame_equations
from truelinev2.match.score import score_chain
from truelinev2.schema.models import Bore, Callout, PlacementStatus
from truelinev2.stations import feet_to_station


def _c(sheet, f0, f1):
    return Callout(sheet=sheet, page=sheet, from_sta=feet_to_station(f0), to_sta=feet_to_station(f1),
                   from_ft=f0, to_ft=f1, footage=round(f1 - f0, 2), text="x", dialect="test")


def _bore(s, e, sheets):
    return Bore(bore_id="logT", source_file="logT.xlsx", sheet_refs=list(sheets),
                station_start=feet_to_station(s), station_end=feet_to_station(e),
                station_start_ft=s, station_end_ft=e, span_ft=round(e - s, 2))


class _StubDialect:
    name = "test"
    match_mode = "footage"

    def __init__(self, callouts):
        self._c = callouts

    def extract_callouts(self, plan, sheet, offset):
        return [c for c in self._c if c.sheet == sheet]


# A safe HIGH edge: sheet 1 STA 3+00 == sheet 2 STA 1+00 (offset 200).
_GRAPH = build_frame_graph(build_frame_edges(
    parse_frame_equations("MATCH LINE STA 3+00 / 1+00 - SEE SHEET 2"), frame_for_sheet(1)))
# A bore 0..500 whose only valid chain needs the translation: s1[0->300] + s2[1+00->3+00]
_TRANSLATED = [_c(1, 0, 300), _c(2, 100, 300)]


def test_flag_defaults_off():
    assert Settings.for_proof().frame_continuation_optin is False
    on = dataclasses.replace(Settings.for_proof(), frame_continuation_optin=True)
    assert on.frame_continuation_optin is True


def test_off_none_graph_abstains_exactly_as_before():
    pl = run_match(_bore(0, 500, [1, 2]), None, _StubDialect(_TRANSLATED), 0)
    assert pl.status is PlacementStatus.ABSTAIN  # frame-blind: 0+69-style link refused


def test_translated_retry_places_review_capped_never_auto():
    # exact deltas (start 0, end 0, foot 0) would be AUTO on the primary path --
    # the translated retry must cap at REVIEW with the caveat.
    pl = run_match(_bore(0, 500, [1, 2]), None, _StubDialect(_TRANSLATED), 0,
                   continuation_graph=_GRAPH)
    assert pl.status is PlacementStatus.REVIEW
    assert pl.reason == "FRAME_TRANSLATED_CONTINUATION"
    assert "FRAME_TRANSLATED_CONTINUATION" in pl.caveats
    assert pl.footage_delta == 0.0 and pl.end_delta == 0.0


def test_raw_chains_untouched_with_graph_present():
    # genuinely-continuous cross-sheet run: places AUTO on the primary path; the
    # graph must not change it (the M8.2d blanket regression class, fixed).
    raw = [_c(1, 0, 300), _c(2, 300, 500)]
    off = run_match(_bore(0, 500, [1, 2]), None, _StubDialect(raw), 0)
    on = run_match(_bore(0, 500, [1, 2]), None, _StubDialect(raw), 0, continuation_graph=_GRAPH)
    assert off.status is PlacementStatus.AUTO_SELECT
    assert on == off  # byte-identical: retry never reached


def test_ambiguity_is_never_overridden():
    # two coequal near-exact candidates with DIFFERENT station signatures (decide()
    # treats identical-station chains as one candidate) -> primary abstains on
    # ambiguity; the retry must NOT fire even though a translated chain exists.
    tie = [_c(1, 0, 500), _c(3, 2, 502)]
    pl = run_match(_bore(0, 500, [1, 2, 3]), None, _StubDialect(tie + _TRANSLATED), 0,
                   continuation_graph=_GRAPH)
    assert pl.status is PlacementStatus.ABSTAIN
    assert pl.reason == "GE_2_COEQUAL_CANDIDATES_NO_TIEBREAKER"


def test_no_start_anchor_still_abstains():
    # the log9/15/16 class: no callout near the bore start -> no chains either way.
    far = [_c(1, 4000, 4300), _c(2, 100, 300)]
    pl = run_match(_bore(0, 500, [1, 2]), None, _StubDialect(far), 0, continuation_graph=_GRAPH)
    assert pl.status is PlacementStatus.ABSTAIN


def test_additive_chains_are_a_superset_of_raw():
    raw_chains = build_chains(_TRANSLATED, 0, 500)
    add_chains = build_chains(_TRANSLATED, 0, 500, frame_graph=_GRAPH, additive=True)
    raw_sigs = {tuple(id(c) for c in ch) for ch in raw_chains}
    add_sigs = {tuple(id(c) for c in ch) for ch in add_chains}
    assert raw_sigs <= add_sigs and len(add_sigs) > len(raw_sigs)


def test_strict_blanket_semantics_unchanged():
    # M8.2d's strict mode: a raw-continuous cross-sheet link with NO safe edge for the
    # pair is REFUSED (that is what made blanket NOT_SAFE) -- must stay that way.
    raw = [_c(5, 0, 300), _c(6, 300, 500)]  # no edge between 5 and 6 in _GRAPH
    strict = build_chains(raw, 0, 500, frame_graph=_GRAPH)  # additive defaults False
    assert all(len(ch) == 1 for ch in strict)  # the cross-sheet link is refused


def test_additive_score_translates_chain_end():
    sc = score_chain(_TRANSLATED, 0, 500, 500, frame_graph=_GRAPH, additive=True)
    assert sc["end_delta"] == 0.0 and sc["foot_delta"] == 0.0  # end 300+200 = 500
    # raw scoring of the same chain (no graph) sees end 300 -> delta 200
    sc_raw = score_chain(_TRANSLATED, 0, 500, 500)
    assert sc_raw["end_delta"] == 200.0


def test_unscoreable_translated_chain_never_places():
    # a chain whose non-raw link has no safe edge is unscoreable -> huge delta -> reject
    chain = [_c(5, 0, 300), _c(6, 100, 300)]  # gap 200, no 5-6 edge
    sc = score_chain(chain, 0, 500, 500, frame_graph=_GRAPH, additive=True)
    assert sc["end_delta"] > 1e8


def test_chain_uses_translated_link_detector():
    assert chain_uses_translated_link(_TRANSLATED) is True
    assert chain_uses_translated_link([_c(1, 0, 300), _c(2, 300, 500)]) is False
    assert chain_uses_translated_link([_c(1, 0, 300)]) is False


# --- adversarial-review fixes (pinned) ---------------------------------------------

def _graph_from(*texts_with_sheets):
    edges = []
    for text, sheet in texts_with_sheets:
        edges.extend(build_frame_edges(parse_frame_equations(text), frame_for_sheet(sheet)))
    return build_frame_graph(edges)


def test_sheet_distinct_translated_rivals_abstain():
    # Finding 3: two coequal translated continuations with IDENTICAL station text on
    # DIFFERENT sheets (reset frames reuse low numbers). decide()'s text-keyed rivals
    # would merge them; the retry's sheet-aware re-check must abstain, never pick one.
    graph = _graph_from(("MATCH LINE STA 3+00 / 1+00 - SEE SHEET 2", 1),
                        ("MATCH LINE STA 3+00 / 1+00 - SEE SHEET 3", 1))
    callouts = [_c(1, 0, 300), _c(2, 100, 300), _c(3, 100, 300)]
    pl = run_match(_bore(0, 500, [1, 2, 3]), None, _StubDialect(callouts), 0,
                   continuation_graph=graph)
    assert pl.status is PlacementStatus.ABSTAIN


def test_sliver_link_cannot_evade_review_cap_or_scoring():
    # Finding 4: raw gap <= 2.0 but NON-monotonic -> the link only exists via
    # translation; the detector and the additive scorer must both treat it as
    # translated (shared raw_link_ok predicate).
    graph = _graph_from(("MATCH LINE STA 3+03 / 3+00 - SEE SHEET 2", 1),)
    chain = [_c(1, 0, 300), _c(2, 298.5, 300)]
    assert chain_uses_translated_link(chain) is True
    sc = score_chain(chain, 0, 303, 303, frame_graph=graph, additive=True)
    assert sc["end_delta"] == 0.0  # end scored through the translation (300 + 3)
    # Engine-level: bore 309 -> the lone 300' box is unacceptable (end_delta 9 > 8);
    # a far decoy makes the footage fallback ambiguous; the retry's winner is the
    # sliver-linked chain -> it must be flagged translated and REVIEW-capped.
    decoy = _c(9, 5000, 5309)
    pl = run_match(_bore(0, 309, [1, 2, 9]), None, _StubDialect(chain + [decoy]), 0,
                   continuation_graph=graph)
    assert pl.status is PlacementStatus.REVIEW  # capped, not silently dropped/AUTO
    assert "FRAME_TRANSLATED_CONTINUATION" in pl.caveats
    assert pl.footage == 301.5 and pl.end_delta == 6.0


def test_retry_placement_passes_through_collision_gate():
    # Finding 5: the retry placement must be gated like any other. A graded
    # abstain_required collision on the retry chain demotes REVIEW -> ABSTAIN.
    from truelinev2.match.collision_gate import CollisionGate
    gate_eqs = {1: tuple(parse_frame_equations(
        "MATCHLINE STA 3+00/1+00 - SEE SHEET 2 ................ "
        "MATCHLINE STA 3+00/1+05 - SEE SHEET 2")), 2: ()}
    gate = CollisionGate(equations_by_sheet=gate_eqs,
                         human_grades={"logT": "abstain_required"})
    pl = run_match(_bore(0, 500, [1, 2]), None, _StubDialect(_TRANSLATED), 0,
                   continuation_graph=_GRAPH, collision_gate=gate)
    assert pl.status is PlacementStatus.ABSTAIN
    assert "RESET_COLLISION_GATE" in pl.caveats


def test_multi_hop_additive_chain_scores_coherently():
    graph = _graph_from(("MATCH LINE STA 3+00 / 1+00 - SEE SHEET 2", 1),
                        ("MATCH LINE STA 3+00 / 1+00 - SEE SHEET 3", 2))
    chain = [_c(1, 0, 300), _c(2, 100, 300), _c(3, 100, 300)]
    sc = score_chain(chain, 0, 700, 700, frame_graph=graph, additive=True)
    assert sc["end_delta"] == 0.0 and sc["foot_delta"] == 0.0  # 300 + 200 + 200
    pl = run_match(_bore(0, 700, [1, 2, 3]), None, _StubDialect(chain), 0,
                   continuation_graph=graph)
    assert pl.status is PlacementStatus.REVIEW


def test_env_flag_parsing(monkeypatch):
    monkeypatch.setenv("TL2_FRAME_AWARE_CONTINUATION_OPTIN", "1")
    assert Settings.from_env().frame_continuation_optin is True
    monkeypatch.setenv("TL2_FRAME_AWARE_CONTINUATION_OPTIN", "0")
    assert Settings.from_env().frame_continuation_optin is False
    monkeypatch.delenv("TL2_FRAME_AWARE_CONTINUATION_OPTIN")
    assert Settings.from_env().frame_continuation_optin is False
