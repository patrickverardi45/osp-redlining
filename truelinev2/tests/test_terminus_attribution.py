"""M9.3.1 -- TERMINUS_ATTRIBUTION extractor tests (offline; universal + posture).

Pin the convention-agnostic CORE on a SYNTHETIC NON-Brenham profile (proving zero
Brenham coupling), the END-direction rule, in-frame uniqueness, sheet-neighbour
rejection, AP-only/splice-only refusal, the M9.1 KMZ cross-check + PDF_KMZ_
CONTRADICTION, the one-terminal-per-END uniqueness invariant, junction resolution,
the zero-literal core guard, and the UNWIRED posture. The LIVE Brenham controls (7
clean END attributions, log68 rejection, 3 junctions, log46 contradiction, no drift)
are gated INSIDE the extractor proof (run_terminus_attribution_extract, G1-G12).
"""
import inspect
import re
from pathlib import Path
from types import SimpleNamespace

from truelinev2.extract.kmz import KmzStructure
from truelinev2.extract.terminus_profile import TerminusProfile
from truelinev2.match import terminus_attribution as TA

PKG = Path(TA.__file__).resolve().parents[1]

# A TOTALLY non-Brenham synthetic profile: different terminal class, different AP /
# splice / note vocabulary. If the core binds correctly here, it is convention-clean.
SYN = TerminusProfile(
    station_line_re=r"^STA\s+(\d{1,3}\+\d{2})\b",
    run_callout_marker="TO STA",
    equation_marker="=",
    note_window=4,
    note_keywords=("WIDGET TERMINUS", "WIDGET POT"),
    class_keywords=(("widget_terminus", ("WIDGET TERMINUS",)),
                    ("widget_pot", ("WIDGET POT",))),
    terminal_class="widget_terminus",
    ap_token=r"NODE\s*-?\s*(\d+)",
    splice_token=r"PORT\s*LOC\s*\d+",
    pair_re=r"NODE-?\s?(\d+)\s+PORT\s*LOC\s*(\d+)",
)

_TERM = "STA 4+51 WIDGET TERMINUS NODE-9 PORT LOC 3"


def _model(*structs):
    return SimpleNamespace(structures=tuple(structs))


# ---- universality: the core works on a synthetic non-Brenham profile -------

def test_end_terminal_attributes_on_synthetic_profile():
    r = TA.attribute_bore("synA", "0+00", "4+51",
                          {1: ["STA 0+00 WIDGET POT", _TERM]}, SYN)
    assert r.end.result == TA.ENDPOINT_ATTRIBUTED and r.end.ap == 9
    assert r.end.splice == "PORT LOC 3" and r.end.structure_class == "widget_terminus"
    assert r.disposition == TA.ENDPOINT_ATTRIBUTED
    # the START is a non-terminal class -> not attributed, typed
    assert r.start.result == TA.NON_TERMINAL_ENDPOINT


# a zone/alpha-AP plan set: AP ids like "A12" must NOT be coerced to int (the M9.1
# join compares by value-equality; the core must too). ap_cast=str preserves the token.
ALPHA = TerminusProfile(
    station_line_re=r"^STA\s+(\d{1,3}\+\d{2})\b",
    run_callout_marker="TO STA", equation_marker="=", note_window=4,
    note_keywords=("ZONE TERMINUS",),
    class_keywords=(("zone_terminus", ("ZONE TERMINUS",)),),
    terminal_class="zone_terminus",
    ap_token=r"BOX\s*-?\s*([A-Z]\d+)",
    splice_token=r"PORT\s*LOC\s*\d+",
    pair_re=r"BOX-?\s?([A-Z]\d+)\s+PORT\s*LOC\s*(\d+)",
    ap_cast=str,
)


def test_alpha_zone_ap_id_binds_not_crashes():
    # the M9.1-audit-class case: an "A12" AP must bind cleanly, never raise ValueError.
    model = _model(KmzStructure("zone_terminus", "TA12", ("A12",), "Port Loc 3", 0.0, 0.0))
    lines = {1: ["STA 4+51 ZONE TERMINUS BOX-A12 PORT LOC 3"]}
    r = TA.attribute_bore("alpha", "0+00", "4+51", lines, ALPHA, kmz_model=model)
    assert r.end.result == TA.ENDPOINT_ATTRIBUTED
    assert r.end.ap == "A12"                              # opaque token, NOT coerced to int
    assert r.end.kmz_join == "KMZ_TERMINAL_JOIN_BOUND"
    # the sheet-neighbour / owning-map path must also tolerate alpha ids
    assert "A12" in TA.owning_pairs(lines, ALPHA)


def test_alpha_zone_ids_stay_distinct_no_int_collapse():
    # A12 and B12 must NOT collide (the bug an int-coercion would reintroduce).
    lines = {1: ["STA 4+51 ZONE TERMINUS BOX-A12 PORT LOC 3 BOX-B12 PORT LOC 4"]}
    r = TA.attribute_bore("alpha2", "0+00", "4+51", lines, ALPHA)
    assert r.end.result == TA.MULTIPLE_COMPETING_CALLOUTS   # two distinct ids in frame


def test_start_terminal_is_junction_origin_not_ownership():
    r = TA.attribute_bore("synB", "1+00", "5+00", {1: ["STA 1+00 WIDGET TERMINUS NODE-9 PORT LOC 3"]}, SYN)
    assert r.start.result == TA.JUNCTION_ORIGIN and r.start.ap == 9
    assert r.end.result == TA.NO_ENDPOINT_NOTE
    assert r.disposition == TA.JUNCTION_ORIGIN


def test_partial_id_is_no_pair():
    r = TA.attribute_bore("synC", "0+00", "4+51", {1: ["STA 4+51 WIDGET TERMINUS NODE-9"]}, SYN)
    assert r.end.result == TA.NO_AP_SPLICE_PAIR          # AP-only in frame
    r2 = TA.attribute_bore("synD", "0+00", "4+51", {1: ["STA 4+51 WIDGET TERMINUS PORT LOC 3"]}, SYN)
    assert r2.end.result == TA.NO_AP_SPLICE_PAIR         # splice-only in frame


def test_multi_pair_in_frame_is_competing():
    r = TA.attribute_bore("synE", "0+00", "4+51",
                          {1: ["STA 4+51 WIDGET TERMINUS NODE-9 PORT LOC 3 NODE-10 PORT LOC 4"]}, SYN)
    assert r.end.result == TA.MULTIPLE_COMPETING_CALLOUTS


def test_no_note_and_competing_notes():
    assert TA.attribute_bore("synF", "0+00", "9+99", {1: ["STA 4+51 WIDGET TERMINUS NODE-9 PORT LOC 3"]},
                             SYN).end.result == TA.NO_ENDPOINT_NOTE
    r = TA.attribute_bore("synG", "0+00", "4+51",
                          {1: ["STA 4+51 WIDGET TERMINUS NODE-9 PORT LOC 3",
                               "STA 4+51 WIDGET TERMINUS NODE-10 PORT LOC 4"]}, SYN)
    assert r.end.result == TA.MULTIPLE_COMPETING_CALLOUTS


def test_sheet_neighbor_rejected_not_flat_scan():
    # NODE-50 prints on the bore's sheet but is OWNED by STA 8+00, not an endpoint.
    lines = {1: ["STA 2+00 WIDGET POT",
                 "STA 8+00 WIDGET TERMINUS NODE-50 PORT LOC 7",
                 "STA 3+00 PLAIN LABEL"]}
    r = TA.attribute_bore("synH", "2+00", "3+00", lines, SYN)
    assert any(n.ap == 50 and n.owning_station == "8+00" for n in r.sheet_neighbors)
    assert r.disposition == TA.SHEET_NEIGHBOR_REJECTED
    assert 50 not in r.attributed_aps


def test_run_callout_resets_frame_so_pair_is_orphan_not_owned():
    lines = {1: ["STA 0+00 TO STA 4+51 RUN", "NODE-77 PORT LOC 1"]}
    owning = TA.owning_pairs(lines, SYN)
    assert owning[77][1] is None                          # owned by no note frame


# ---- KMZ cross-check (M9.1) + PDF<->KMZ contradiction ----------------------

def test_kmz_cross_check_bound_keeps_attribution():
    model = _model(KmzStructure("widget_terminus", "T9", (9,), "Port Loc 3", 0.0, 0.0))
    r = TA.attribute_bore("synI", "0+00", "4+51", {1: [_TERM]}, SYN, kmz_model=model)
    assert r.end.result == TA.ENDPOINT_ATTRIBUTED
    assert r.end.kmz_join == "KMZ_TERMINAL_JOIN_BOUND"


def test_kmz_splice_mismatch_is_pdf_kmz_contradiction():
    # KMZ NODE-9 carries Port Loc 99, PDF says Port Loc 3 -> the join refutes it.
    model = _model(KmzStructure("widget_terminus", "T9", (9,), "Port Loc 99", 0.0, 0.0))
    r = TA.attribute_bore("synJ", "0+00", "4+51", {1: [_TERM]}, SYN, kmz_model=model)
    assert r.end.result == TA.PDF_KMZ_CONTRADICTION
    assert r.end.kmz_join in TA._CONTRA_JOINS
    assert r.disposition == TA.PDF_KMZ_CONTRADICTION


def test_source_contradiction_override():
    r = TA.attribute_bore("synK", "0+00", "4+51", {1: [_TERM]}, SYN,
                          source_contradiction=True)
    assert r.disposition == TA.SOURCE_CONTRADICTION


# ---- corpus invariants ------------------------------------------------------

def test_one_terminal_per_end_uniqueness_violation_detected():
    ra = TA.attribute_bore("a", "0+00", "4+51", {1: [_TERM]}, SYN)
    rb = TA.attribute_bore("b", "0+00", "9+99",
                           {1: ["STA 9+99 WIDGET TERMINUS NODE-9 PORT LOC 3"]}, SYN)
    viol = TA.check_terminal_uniqueness([ra, rb])
    assert 9 in viol and set(viol[9]) == {"a", "b"}


def test_resolve_junctions_pairs_start_to_end_owner():
    ender = TA.attribute_bore("ender", "0+00", "4+51", {1: [_TERM]}, SYN)
    starter = TA.attribute_bore("starter", "4+51", "9+99", {1: [_TERM]}, SYN)
    jns = {(j["start_bore"], j["terminal_ap"], j["end_bore_owner"])
           for j in TA.resolve_junctions([ender, starter])}
    assert jns == {("starter", 9, "ender")}


# ---- zero-literal core guard + UNWIRED posture -----------------------------

def test_core_holds_zero_plan_set_literal():
    src = inspect.getsource(TA)
    assert not re.search(r"(?i)\b(brenham|odot|tulsa|creek|nextlink|verofy)\b", src)
    for vocab in ("terminal_port_hh", "FLOWER POT", "INSTALLER HH", "PORT HH",
                  "SPLICE LOC", "NEXTLINK"):
        assert vocab not in src, vocab
    # no coordinate read in the law (attribution is identity, never proximity)
    assert ".lon" not in src and ".lat" not in src


def test_extractor_unwired_from_placement_path():
    engine = (list((PKG / "match").glob("*.py"))
              + list((PKG / "review").glob("*.py")) + [PKG / "service.py"])
    for f in engine:
        if f.name == "terminus_attribution.py":
            continue
        assert "terminus_attribution" not in f.read_text(encoding="utf-8"), f


def test_no_render_no_placement_in_core():
    src = inspect.getsource(TA)
    assert "render" not in src and "Status.AUTO" not in src and "place_bore" not in src
