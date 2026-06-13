"""M9.1 -- KMZ_AP_STRUCTURE_JOIN extractor tests.

The law is exercised on a SYNTHETIC, non-Brenham model (proving the core is
universal -- Brenham is only a profile/fixture) plus the tracked Brenham fixture
controls. Pins: two-field bind; AP-only / splice-only / missing / ambiguous /
cross-structure-mix / wrong-class refusals; zone/alpha splice ids never collapse
or cross-bind (the M9.1 audit fix); no coordinate in the binding law; universal
core (no customer literal); UNWIRED from the placement path.
"""
import inspect
import re
from pathlib import Path
from types import SimpleNamespace

from truelinev2.extract.kmz import (BRENHAM_KMZ_DIALECT, KmzStructure,
                                    read_kmz)
from truelinev2.match import kmz_structure_join as J
from truelinev2.match.kmz_structure_join import (join_terminal,
                                                 parse_terminus_pair,
                                                 terminal_anchors)

PKG = Path(J.__file__).resolve().parents[1]
FIXTURE = str(PKG.parent / "backend" / "tests" / "fixtures"
              / "brenham_phase5_source_truth.kmz")
TC = "widget_terminus"   # a generic (non-Brenham) terminal class for the model


def _struct(cls, name, aps, loc, lon=0.0, lat=0.0):
    return KmzStructure(kmz_class=cls, name=name, ap_ids=tuple(aps),
                        splice_loc=loc, lon=lon, lat=lat)


def _model(*structs):
    return SimpleNamespace(structures=tuple(structs))


def _j(model, ap, sp, tc=TC):
    return join_terminal(model, terminal_class=tc, pdf_ap=ap, pdf_splice_loc=sp)


# ---- universal law on a synthetic, non-Brenham model ------------------------

def test_two_field_bind_on_synthetic_model():
    m = _model(_struct(TC, "T1", [10], "Loc 5"),
               _struct(TC, "T2", [11], "Loc 6"))
    r = _j(m, 10, "Loc 5")
    assert r.bound and r.anchor.name == "T1" and r.anchor.kmz_class == TC
    assert r.evidence["proximity_used"] is False


def test_class_scoped_same_ids_wrong_class_not_bound():
    # a non-terminal structure carrying the SAME (ap, splice) is never a
    # candidate -- the join is class-scoped to the profile's terminal class.
    m = _model(_struct(TC, "T1", [10], "Loc 5"),
               _struct("splice", "SP", [10], "Loc 5"))
    r = _j(m, 10, "Loc 5")
    assert r.bound and r.anchor.name == "T1"
    assert len(terminal_anchors(m, TC)) == 1   # SP excluded from the index


def test_ap_only_and_splice_only_and_cross_mix_refused():
    m = _model(_struct(TC, "T1", [10], "Loc 5"),
               _struct(TC, "T2", [11], "Loc 6"))
    assert _j(m, 10, "Loc 999").result == J.JOIN_AP_ONLY_REJECTED
    assert _j(m, 999, "Loc 5").result == J.JOIN_SPLICE_ONLY_REJECTED
    assert _j(m, 10, "Loc 6").result == J.JOIN_AP_ONLY_REJECTED   # cross-mix t1/t2
    assert not _j(m, 10, "Loc 6").bound


def test_missing_ids_refused():
    m = _model(_struct(TC, "T1", [10], "Loc 5"))
    assert _j(m, 10, None).result == J.JOIN_SPLICE_MISSING
    assert _j(m, 10, "   ").result == J.JOIN_SPLICE_MISSING   # whitespace == missing
    assert _j(m, None, "Loc 5").result == J.JOIN_AP_MISSING
    assert _j(m, 10, "Loc 5", tc="").result == J.JOIN_NO_TERMINAL_CLASS


def test_ambiguous_refused():
    m = _model(_struct(TC, "A", [20], "Loc 8"),
               _struct(TC, "B", [20], "Loc 8"))
    r = _j(m, 20, "Loc 8")
    assert r.result == J.JOIN_AMBIGUOUS and r.anchor is None


def test_self_duplicated_ap_does_not_masquerade_as_ambiguous():
    # one structure listing the same AP twice is ONE candidate, not two.
    m = _model(_struct(TC, "T", [70, 70], "Loc 9"))
    r = _j(m, 70, "Loc 9")
    assert r.bound and r.anchor.name == "T"


def test_zone_and_alpha_splice_ids_are_universal():
    # the M9.1 fix: opaque-token comparison -> a zone/alpha id neither cross-binds
    # nor vanishes (a trailing-integer reduction would do both).
    m = _model(_struct(TC, "ZA", [70], "ZONE A-12"),
               _struct(TC, "ZB", [80], "ZONE B-12"),
               _struct(TC, "AL", [90], "Loc 5A"))
    assert _j(m, 70, "Zone A-12").anchor.name == "ZA"          # case-normalized bind
    assert _j(m, 80, "Zone A-12").result == J.JOIN_AP_ONLY_REJECTED  # no cross-zone
    assert _j(m, 90, "Loc 5A").bound                            # alpha id bindable


def test_no_match_is_typed_none():
    m = _model(_struct(TC, "T1", [10], "Loc 5"))
    assert _j(m, 777, "Loc 888").result == J.JOIN_NONE


def test_norm_token_and_parse_pair():
    assert J._norm_token("Splice Loc 46") == "SPLICE LOC 46"
    assert J._norm_token("  zone   a-12 ") == "ZONE A-12"   # collapse + upper
    assert J._norm_token(None) is None and J._norm_token("   ") is None
    ap, sp = parse_terminus_pair(
        "AP-163 SPLICE LOC 46", ap_re=BRENHAM_KMZ_DIALECT.ap_token,
        splice_re=BRENHAM_KMZ_DIALECT.splice_token)
    assert ap == 163 and sp == "SPLICE LOC 46"


# ---- controls on the tracked Brenham fixture (profile-injected) -------------

def test_controls_bind_on_fixture():
    m = read_kmz(FIXTURE, BRENHAM_KMZ_DIALECT)
    tc = BRENHAM_KMZ_DIALECT.terminal_class
    for ap, sp in ((163, "Splice Loc 46"), (105, "Splice Loc 25")):
        r = join_terminal(m, terminal_class=tc, pdf_ap=ap, pdf_splice_loc=sp)
        assert r.bound and r.anchor.ap_id == ap
        assert r.anchor.splice_loc == J._norm_token(sp)
        assert r.anchor.kmz_class == tc


# ---- posture: universal core, no coordinate in the law, UNWIRED -------------

def test_core_has_no_customer_literal_and_no_coordinate_in_law():
    src = inspect.getsource(J)
    assert not re.search(r"(?i)\b(brenham|odot|tulsa|nextlink|verofy)\b", src)
    # the BINDING law reads no coordinate (lon/lat only carried as metadata)
    jsrc = inspect.getsource(join_terminal)
    assert ".lon" not in jsrc and ".lat" not in jsrc


def test_join_extractor_unwired_from_placement_path():
    for rel in ("match/engine.py", "match/symbol_conduit_lane.py",
                "review/reviewer_service.py", "service.py"):
        src = (PKG / rel).read_text(encoding="utf-8")
        assert "kmz_structure_join" not in src, rel
