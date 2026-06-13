"""M9.4.1 -- RUN_ASSEMBLY core + review-card tests (offline; universal + posture).

Pin the SHIPPED core (match/run_assembly.py) on SYNTHETIC, non-Brenham facts +
grammar: the physical-departure enumerator (drop flag from an INJECTED marker, not a
baked literal), the STRONGER competing guard (an unclaimed lateral the JUNCTION_ORIGIN
count would miss -> COMPETING), the safety law (candidate / drop / self-junction /
start-as-ownership / contradiction / terminal-mismatch / no-kmz / none-owner), the
M8.20-style review card contract, the zero-literal core guard, and the UNWIRED
posture. The LIVE Brenham reproduction (2 candidates + 1 drop, 7 clean ENDs, the
injected drop on real log65, no drift) is gated INSIDE the extractor proof
(run_run_assembly_extract, G1-G11).
"""
import inspect
import re
from pathlib import Path

import pytest

from truelinev2.extract.terminus_profile import TerminusProfile
from truelinev2.match import run_assembly as RA
from truelinev2.match import terminus_attribution as TA
from truelinev2.review import run_assembly_review as RV

PKG = Path(RA.__file__).resolve().parents[1]
BOUND = "KMZ_TERMINAL_JOIN_BOUND"

# a totally non-Brenham profile: a DIFFERENT injected drop marker ("LATERAL TAP").
SYN = TerminusProfile(
    station_line_re=r"^STA\s+(\d{1,3}\+\d{2})\b",
    run_callout_marker="TO STA", equation_marker="=", note_window=4,
    note_keywords=("WIDGET TERMINUS",),
    class_keywords=(("widget_terminus", ("WIDGET TERMINUS",)),),
    terminal_class="widget_terminus",
    ap_token=r"NODE\s*-?\s*(\d+)", splice_token=r"PORT\s*LOC\s*\d+",
    pair_re=r"NODE-?\s?(\d+)\s+PORT\s*LOC\s*(\d+)",
    drop_markers=("LATERAL TAP",),
)


def _ep(side, result, ap=None, splice=None, kmz_join=None, station=None):
    return TA.EndpointAttribution(
        side=side, station=station or ("4+51" if side == "END" else "0+00"),
        result=result, ap=ap, splice=splice, kmz_join=kmz_join,
        note_line=f"note-{side}")


def _bore(bid, *, start_station="0+00", end_station="4+51",
          end_result=TA.NO_ENDPOINT_NOTE, end_ap=None, end_splice=None, end_join=None,
          start_result=TA.NO_ENDPOINT_NOTE, start_ap=None, start_splice=None):
    return TA.BoreTerminusResult(
        bore_id=bid, start_station=start_station, end_station=end_station,
        start=_ep("START", start_result, start_ap, start_splice, station=start_station),
        end=_ep("END", end_result, end_ap, end_splice, end_join, station=end_station),
        sheet_neighbors=())


def _clean(ap=152, splice="PORT LOC 3"):
    """A clean junction: `ender` owns terminal `ap` at its END; `starter` departs it."""
    ender = _bore("ender", start_station="0+00", end_station="4+51",
                  end_result=TA.ENDPOINT_ATTRIBUTED, end_ap=ap, end_splice=splice,
                  end_join=BOUND)
    starter = _bore("starter", start_station="4+51", end_station="9+99",
                    start_result=TA.JUNCTION_ORIGIN, start_ap=ap, start_splice=splice)
    j = {"start_bore": "starter", "terminal_ap": ap, "end_bore_owner": "ender",
         "splice_loc": splice}
    return j, {"ender": ender, "starter": starter}


# ---- physical-departure enumeration + injected drop grammar -----------------

def test_run_callout_departures_enumerates_and_dedups():
    # the SAME printed run on two sheets is ONE departure (deduped by callout text);
    # the injected marker flags the drop.
    lines = {1: ["STA 4+51 TO STA 6+11 RUN", "VACANT HDPE LATERAL TAP"],
             2: ["STA 4+51 TO STA 6+11 RUN", "VACANT HDPE LATERAL TAP"]}
    deps = RA.run_callout_departures(lines, "4+51", SYN)
    assert len(deps) == 1 and deps[0].is_drop is True
    trunk = {1: ["STA 9+00 TO STA 9+50 trunk run", "PLAIN CONTINUATION"]}
    assert RA.run_callout_departures(trunk, "9+00", SYN)[0].is_drop is False


def test_run_callout_departures_window_stops_at_next_sta_line():
    # a drop marker that belongs to a NEIGHBORING station's note must NOT leak into a
    # trunk run-callout's window (frame discipline, mirroring detect_endpoint_note).
    lines = {1: ["STA 4+51 TO STA 6+11 RUN", "STA 5+00 SOMETHING", "LATERAL TAP"]}
    deps = RA.run_callout_departures(lines, "4+51", SYN)
    assert len(deps) == 1 and deps[0].is_drop is False
    # the marker IS seen when it sits before any intervening STA line.
    own = {1: ["STA 4+51 TO STA 6+11 RUN", "LATERAL TAP", "STA 5+00 SOMETHING"]}
    assert RA.run_callout_departures(own, "4+51", SYN)[0].is_drop is True


def test_departure_run_class_uses_injected_marker_not_baked_literal():
    drop = {1: ["STA 4+51 TO STA 6+11 RUN", "LATERAL TAP HERE"]}
    trunk = {1: ["STA 4+51 TO STA 6+11 RUN", "PLAIN CONTINUATION"]}
    assert RA.departure_run_class(drop, "4+51", SYN) == RA.DEP_DROP
    assert RA.departure_run_class(trunk, "4+51", SYN) == RA.DEP_TRUNK
    assert RA.departure_run_class({1: []}, "4+51", SYN) == RA.DEP_UNKNOWN
    # the SAME drop line with no injected markers reads as a non-drop (no baked literal)
    import dataclasses
    nomark = dataclasses.replace(SYN, drop_markers=())
    assert RA.departure_run_class(drop, "4+51", nomark) == RA.DEP_TRUNK
    # a Brenham-style marker is NOT recognised by a profile that did not inject it
    bren = {1: ["STA 4+51 TO STA 6+11 RUN", "FOR FIBER DROP"]}
    assert RA.departure_run_class(bren, "4+51", SYN) == RA.DEP_TRUNK


def test_physical_departure_count_claims_candidate_own_callout():
    # the candidate's OWN node callout is claimed -> not an extra lateral (count 1).
    j, by_id = _clean()
    lines = {"starter": {1: ["STA 4+51 TO STA 6+11 RUN", "LATERAL TAP"]},
             "ender": {1: ["STA 4+51 TO STA 6+11 RUN", "LATERAL TAP"]}}  # same printed run
    count, extra = RA.physical_departure_count(152, "ender", ["starter"], by_id, lines, SYN)
    assert count == 1 and extra == []


def test_physical_departure_count_catches_unclaimed_lateral():
    # an EXTRA lateral at the node (different destination) the JUNCTION_ORIGIN count
    # would miss, printed in the END bore's OWN frame -> count 2 (the M9.4.1 stronger guard).
    j, by_id = _clean()
    lines = {"starter": {1: []},
             "ender": {1: ["STA 4+51 TO STA 9+99 RUN", "LATERAL TAP"]}}
    count, extra = RA.physical_departure_count(152, "ender", ["starter"], by_id, lines, SYN)
    assert count == 2 and len(extra) == 1


def test_physical_departure_count_cross_sheet_lateral_is_named_limitation():
    # NAMED LIMITATION (M9.4.1, pinned so it stays honest): the guard is frame-scoped to
    # the END bore's sheets. A matchline-adjacent lateral drawn SOLELY on a sheet outside
    # the END bore's frame (here under a non-participating bore key) is NOT enumerated ->
    # count stays 1. Associating a far-sheet callout with this node needs the M9.2 frame-
    # equation graph; a corpus-wide scan is unsafe (a station token is frame-local).
    j, by_id = _clean()
    lines = {"starter": {1: []},
             "ender": {1: ["STA 4+51 WIDGET TERMINUS NODE-152 PORT LOC 3"]},  # no run callout in END frame
             "faraway": {7: ["STA 4+51 TO STA 9+99 RUN", "LATERAL TAP"]}}      # lateral on a non-END sheet
    count, extra = RA.physical_departure_count(152, "ender", ["starter"], by_id, lines, SYN)
    assert count == 1 and extra == []      # cross-sheet lateral MISSED -> the named open target


# ---- the safety law ---------------------------------------------------------

def test_candidate_when_non_drop_and_uncontested():
    j, by_id = _clean()
    e = RA.assemble_junction(j, by_id, 1, {}, RA.DEP_UNKNOWN)
    assert e.disposition == RA.RUN_ASSEMBLY_REVIEW_CANDIDATE
    assert e.is_continuation_candidate and e.is_evidence
    assert e.relation == RA.RELATION_SHARED_TERMINAL
    assert e.review_only and e.evidence_only and not e.affects_product_disposition
    assert e.geometry is None and e.auto is False and e.terminal_is_end_of_feed
    assert e.end_ownership_clean_unique and e.same_terminal_fact and e.kmz_join_corroborated


def test_drop_departure_is_branch_not_continuation():
    j, by_id = _clean()
    e = RA.assemble_junction(j, by_id, 1, {}, RA.DEP_DROP)
    assert e.disposition == RA.JUNCTION_DROP_BRANCH
    assert e.is_drop_branch and not e.is_continuation_candidate
    assert "NOT the trunk" in e.why


def test_competing_physical_departure_refused():
    j, by_id = _clean()
    e = RA.assemble_junction(j, by_id, 2, {}, RA.DEP_UNKNOWN)
    assert e.disposition == RA.COMPETING_JUNCTION_CANDIDATES and not e.is_evidence


def test_self_junction_refused():
    j, by_id = _clean()
    j["end_bore_owner"] = "starter"
    e = RA.assemble_junction(j, by_id, 1, {}, RA.DEP_TRUNK)
    assert e.disposition == RA.SELF_JUNCTION_REFUSED


def test_start_as_ownership_refused():
    j, by_id = _clean()
    by_id["starter"] = _bore("starter", start_station="4+51",
                             start_result=TA.ENDPOINT_ATTRIBUTED, start_ap=152,
                             start_splice="PORT LOC 3")
    e = RA.assemble_junction(j, by_id, 1, {}, RA.DEP_TRUNK)
    assert e.disposition == RA.START_JUNCTION_NOT_OWNERSHIP


def test_contradiction_blocks():
    j, by_id = _clean()
    assert RA.assemble_junction(j, by_id, 1, {"starter": RA.SOURCE_CONTRADICTION},
                                RA.DEP_TRUNK).disposition == RA.SOURCE_CONTRADICTION
    assert RA.assemble_junction(j, by_id, 1, {"ender": RA.PDF_KMZ_CONTRADICTION},
                                RA.DEP_TRUNK).disposition == RA.PDF_KMZ_CONTRADICTION


def test_terminal_mismatch_and_no_kmz_are_unmodeled():
    j, by_id = _clean()
    by_id["starter"] = _bore("starter", start_station="4+51",
                             start_result=TA.JUNCTION_ORIGIN, start_ap=152,
                             start_splice="PORT LOC 99")
    assert RA.assemble_junction(j, by_id, 1, {}, RA.DEP_TRUNK).disposition \
        == RA.UNMODELED_RUN_RELATIONSHIP
    j2, by_id2 = _clean()
    by_id2["ender"] = _bore("ender", end_result=TA.ENDPOINT_ATTRIBUTED, end_ap=152,
                            end_splice="PORT LOC 3", end_join="KMZ_TERMINAL_JOIN_NONE")
    assert RA.assemble_junction(j2, by_id2, 1, {}, RA.DEP_TRUNK).disposition \
        == RA.UNMODELED_RUN_RELATIONSHIP


def test_none_owner_is_unmodeled():
    j, by_id = _clean()
    j["end_bore_owner"] = None
    e = RA.assemble_junction(j, by_id, 1, {}, RA.DEP_UNKNOWN)
    assert e.disposition == RA.UNMODELED_RUN_RELATIONSHIP and "no unique END owner" in e.why


# ---- end-to-end corpus entry point (synthetic) ------------------------------

def test_extract_run_assembly_end_to_end_synthetic():
    # ender owns terminal AP-9 at its END (KMZ-BOUND); starter departs it as a drop.
    j, by_id = _clean(ap=9, splice="PORT LOC 3")
    results = [by_id["ender"], by_id["starter"]]
    lines = {"ender": {1: ["STA 4+51 WIDGET TERMINUS NODE-9 PORT LOC 3"]},
             "starter": {1: ["STA 4+51 TO STA 6+00 RUN LATERAL TAP"]}}
    evs = RA.extract_run_assembly(results, lines, SYN)
    assert len(evs) == 1
    e = evs[0]
    assert (e.end_bore, e.start_bore) == ("ender", "starter")
    assert e.disposition == RA.JUNCTION_DROP_BRANCH          # printed LATERAL TAP at the node
    assert e.competing_departures == 1                       # the lateral is claimed by starter


# ---- the review card (M8.20-style) -----------------------------------------

def test_build_cards_only_for_evidence_dispositions():
    cand = RA.RunAssemblyEvidence(end_bore="e", start_bore="s", terminal_ap=9,
                                  splice_loc="PORT LOC 3",
                                  disposition=RA.RUN_ASSEMBLY_REVIEW_CANDIDATE,
                                  departure_run_class=RA.DEP_TRUNK)
    drop = RA.RunAssemblyEvidence(end_bore="e2", start_bore="s2", terminal_ap=10,
                                  splice_loc="PORT LOC 4",
                                  disposition=RA.JUNCTION_DROP_BRANCH,
                                  departure_run_class=RA.DEP_DROP)
    blocker = RA.RunAssemblyEvidence(end_bore="e3", start_bore="s3", terminal_ap=11,
                                     splice_loc=None,
                                     disposition=RA.COMPETING_JUNCTION_CANDIDATES)
    cards = RV.build_run_assembly_cards([cand, drop, blocker])
    assert len(cards) == 2
    by_class = {c.continuation_class: c for c in cards}
    assert by_class[RV.CONTINUATION_CANDIDATE].start_bore == "s"
    assert by_class[RV.DROP_BRANCH].start_bore == "s2"
    assert all(c.review_only and not c.auto and not c.has_geometry for c in cards)


def test_card_validator_forbids_geometry_and_auto_and_self_junction():
    base = dict(end_bore="e", start_bore="s", terminal_ap=9, splice_loc="PORT LOC 3",
                end_station="4+51", start_station="4+51",
                continuation_class=RV.CONTINUATION_CANDIDATE,
                departure_run_class=RA.DEP_TRUNK, competing_departures=1, detail="d")
    RV.RunAssemblyReviewCard(**base)                                  # valid
    with pytest.raises(ValueError):
        RV.RunAssemblyReviewCard(**{**base, "auto": True})
    with pytest.raises(ValueError):
        RV.RunAssemblyReviewCard(**{**base, "has_geometry": True})
    with pytest.raises(ValueError):
        RV.RunAssemblyReviewCard(**{**base, "label": "PLACED"})
    with pytest.raises(ValueError):
        RV.RunAssemblyReviewCard(**{**base, "start_bore": "e"})       # self-junction


def test_card_drop_branch_must_be_a_drop_and_candidate_must_not_be():
    base = dict(end_bore="e", start_bore="s", terminal_ap=9, splice_loc="PORT LOC 3",
                end_station="4+51", start_station="4+51", competing_departures=1, detail="d")
    with pytest.raises(ValueError):      # drop-branch card without a drop departure
        RV.RunAssemblyReviewCard(continuation_class=RV.DROP_BRANCH,
                                 departure_run_class=RA.DEP_TRUNK, **base)
    with pytest.raises(ValueError):      # candidate card with a drop departure
        RV.RunAssemblyReviewCard(continuation_class=RV.CONTINUATION_CANDIDATE,
                                 departure_run_class=RA.DEP_DROP, **base)


# ---- posture: zero-literal core, UNWIRED, module shipped --------------------

def test_core_holds_zero_plan_set_literal():
    src = inspect.getsource(RA)
    assert not re.search(r"(?i)\b(brenham|odot|tulsa|creek|nextlink|verofy)\b", src)
    for vocab in ("FOR FIBER DROP", "terminal_port_hh", "FLOWER POT", "SPLICE LOC",
                  "INSTALLER HH", "PORT HH"):
        assert vocab not in src, vocab
    assert ".lon" not in src and ".lat" not in src           # no coordinate in the law


def test_core_module_shipped():
    assert (PKG / "match" / "run_assembly.py").exists()
    assert (PKG / "review" / "run_assembly_review.py").exists()


def test_core_unwired_from_placement_path():
    for rel in ("match/engine.py", "match/symbol_conduit_lane.py",
                "review/reviewer_service.py", "service.py"):
        src = (PKG / rel).read_text(encoding="utf-8")
        assert "run_assembly" not in src, rel


def test_no_render_no_placement_in_core():
    src = inspect.getsource(RA)
    assert "render" not in src and "Status.AUTO" not in src and "place_bore" not in src
