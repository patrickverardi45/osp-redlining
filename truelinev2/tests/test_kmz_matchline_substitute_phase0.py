"""M9.2 -- KMZ_MATCHLINE_SUBSTITUTE Phase-0 feasibility tests (offline; pure + posture).

Pin the pure endpoint-pair parser, the disposition decision tree (the FIRST-unmet-
condition logic + the accurate per-bore blocker prose), the banked candidate-scope
constants, and the read-only/UNWIRED posture. The LIVE drift-guarded facts (KMZ
taxonomy, the live candidate-class re-derivation, the M9.1 controls binding, 0/6
TWO_ENDPOINTS_BOUND, no contract drift) are gated INSIDE the runner (G1-G7), as
with the other v2 corpus probes.
"""
import inspect
from pathlib import Path
from types import SimpleNamespace

from truelinev2.proof import run_kmz_matchline_substitute_phase0 as p0

PKG = Path(p0.__file__).resolve().parents[1]


# ---- pure: endpoint-pair parser --------------------------------------------

def test_pair_from_label_clean_full_pair():
    ap, sp, kind = p0._pair_from_label("STA 7+21 TERMINAL 6 PORT HH AP-148 SPLICE LOC 34")
    assert (ap, sp, kind) == (148, "SPLICE LOC 34", "FULL_PAIR")


def test_pair_from_label_no_id_and_partials():
    assert p0._pair_from_label('11"X11"X12" FLOWER POT') == (None, None, "NO_ID")
    assert p0._pair_from_label("AP-148 only")[2] == "AP_ONLY"
    assert p0._pair_from_label("SPLICE LOC 34 only")[2] == "SPLICE_ONLY"
    assert p0._pair_from_label(None) == (None, None, "NO_ID")


def test_pair_from_label_multiple_tokens_is_ambiguous_never_first_match():
    # two distinct APs / splices in one block must NOT be silently first-matched.
    ap, sp, kind = p0._pair_from_label("AP-137 SPLICE LOC 33 ... AP-138 SPLICE LOC 35")
    assert kind == "MULTI_AMBIGUOUS" and ap is None and sp is None


# ---- pure: disposition decision tree ---------------------------------------

class _Anchor:
    def __init__(self, name):
        self.name = name


class _Join:
    """Minimal stand-in for TerminalJoin (only .bound + .anchor are read)."""
    def __init__(self, bound, name=None):
        self.bound = bound
        self.anchor = _Anchor(name) if name else None


_NO = {"identity_bound": False, "pair_kind": "NO_STRUCTURE_NOTE", "label": None}
_FLOWER = {"identity_bound": True, "pair_kind": "NO_ID", "label": "FLOWER POT"}


def test_disposition_pair_missing_is_the_strict_class_outcome():
    disp, why = p0._disposition(
        True, True, _NO, _FLOWER, _Join(False), _Join(False), False, False)
    assert disp == p0.D_PAIR_MISSING
    # accurate per-bore prose: names the printed flower-pot END, not a blanket claim
    assert "FLOWER POT" in why and "no key" in why


def test_disposition_one_endpoint_only():
    disp, why = p0._disposition(
        True, True, _NO, _FLOWER, _Join(False), _Join(True, "T1"), False, False)
    assert disp == p0.D_ONE_ONLY and "END" in why


def test_disposition_two_bound_needs_admissible_route():
    s, e = _Join(True, "A"), _Join(True, "B")
    # both bound + distinct, but route linkage inadmissible -> NO_KMZ_ROUTE_SUPPORT
    assert p0._disposition(True, True, _FLOWER, _FLOWER, s, e, False, False)[0] == \
        p0.D_NO_ROUTE
    # both bound + admissible route + no contradiction -> TWO_ENDPOINTS_BOUND
    assert p0._disposition(True, True, _FLOWER, _FLOWER, s, e, True, False)[0] == \
        p0.D_TWO_BOUND
    # contradiction wins over an otherwise-complete bind
    assert p0._disposition(True, True, _FLOWER, _FLOWER, s, e, True, True)[0] == \
        p0.D_PDF_CONTRA


def test_disposition_not_in_class_and_source_only():
    assert p0._disposition(False, True, _NO, _NO, _Join(False), _Join(False),
                           False, False)[0] == p0.D_NOT_IN_CLASS
    assert p0._disposition(True, False, _NO, _NO, _Join(False), _Join(False),
                           False, False)[0] == p0.D_SOURCE_ONLY


def test_disposition_distinct_anchor_required_for_two_bound():
    # same anchor name at both ends is NOT distinct -> not TWO_ENDPOINTS_BOUND.
    same = _Join(True, "SAME")
    disp, _ = p0._disposition(True, True, _FLOWER, _FLOWER, same, _Join(True, "SAME"),
                              True, False)
    assert disp != p0.D_TWO_BOUND


# ---- banked candidate scope -------------------------------------------------

def test_named_scope_is_strict_class_plus_log10():
    assert set(p0.NAMED_SCOPE) == p0.STRICT_NO_EQUATION | {"log10"}
    assert "log10" not in p0.STRICT_NO_EQUATION
    assert len(p0.STRICT_NO_EQUATION) == 6 and len(p0.NAMED_SCOPE) == 7


def test_banked_controls_and_lanes():
    assert p0.CONTROLS == {"log7": (163, "SPLICE LOC 46"),
                           "log42": (105, "SPLICE LOC 25")}
    assert sum(p0.BANKED_FULLEST_LANES.values()) == 58
    assert p0.BANKED_FULLEST_LANES["PLACED_REVIEW"] == 30


# ---- read-only posture + UNWIRED -------------------------------------------

def test_read_only_posture_no_render_no_placement():
    src = inspect.getsource(p0)
    assert "truelinev2.render" not in src and "render_redline_stroke" not in src
    assert 'OUT_DIR.glob("*.png")' in src              # G6 asserts zero PNGs
    # consumes the shipped join READ-ONLY; never assigns a placement Status/AUTO.
    assert "join_terminal" in src
    assert "Status.AUTO" not in src and "place_bore" not in src


def test_join_and_reader_stay_unwired_from_engine():
    # the join + reader stay UNWIRED from the PLACEMENT PATH. (The shipped M9.3.1
    # extractor match/terminus_attribution.py legitimately composes the M9.1 join;
    # the contract is no-placement-path-consumption, matching the authoritative
    # test_kmz_structure_join unwired test -- not "no match/ file ever imports it".)
    placement = [PKG / "match" / "engine.py",
                 PKG / "match" / "symbol_conduit_lane.py",
                 PKG / "review" / "reviewer_service.py", PKG / "service.py"]
    for f in placement:
        src = f.read_text(encoding="utf-8")
        assert "kmz_structure_join" not in src, f
        assert "extract.kmz" not in src and "extract import kmz" not in src, f


def test_no_engine_module_imports_this_proof():
    engine = (list((PKG / "match").glob("*.py"))
              + list((PKG / "review").glob("*.py")) + [PKG / "service.py"])
    for f in engine:
        assert "run_kmz_matchline_substitute_phase0" not in f.read_text(
            encoding="utf-8"), f


def test_no_pdf_contradiction_banked_for_class():
    # condition 4 is a banked input (this class has no source-vs-plan contradiction).
    assert set(p0.PDF_CONTRADICTION) == set(p0.NAMED_SCOPE)
    assert not any(p0.PDF_CONTRADICTION.values())
