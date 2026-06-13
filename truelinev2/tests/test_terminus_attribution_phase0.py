"""M9.3 -- START/END terminus-attribution Phase-0 tests (offline; pure + posture).

Pin the pure in-frame pair parser, the owning-station frame map, the class-aware
drop phrase, the DIRECTION-aware attribution (terminal at END = ENDPOINT_ATTRIBUTED,
terminal at START = JUNCTION_ORIGIN), the per-bore disposition tree, an end-to-end
attribution over a FAKE plan, banked constants, and read-only/UNWIRED posture. The
LIVE drift-guarded facts (all-58 census, controls binding, log10 positive, log68
sheet-neighbour rejection, the 3 junctions, log46 PDF<->KMZ contradiction, log44
gating, uniqueness invariant, no drift) are gated INSIDE the runner (G1-G11).
"""
import inspect
from pathlib import Path

from truelinev2.proof import run_terminus_attribution_phase0 as p0

PKG = Path(p0.__file__).resolve().parents[1]


# ---- pure: in-frame pair parser --------------------------------------------

def test_pair_from_label_full_partial_multi():
    assert p0._pair_from_label("TERMINAL 6 PORT HH AP-163 SPLICE LOC 46") == (
        163, "SPLICE LOC 46", "FULL_PAIR")
    assert p0._pair_from_label("FLOWER POT") == (None, None, "NO_ID")
    assert p0._pair_from_label("AP-163 only")[2] == "AP_ONLY"
    assert p0._pair_from_label("SPLICE LOC 46 only")[2] == "SPLICE_ONLY"
    assert p0._pair_from_label(
        "AP-163 SPLICE LOC 46 AP-164 SPLICE LOC 47")[2] == "MULTI_AMBIGUOUS"


# ---- pure: owning-station frame map ----------------------------------------

def test_ap_owning_stations_frame_and_reset():
    lines = [
        "STA 4+51",
        "TERMINAL 6 PORT HH AP-163 SPLICE LOC 46",       # owned by 4+51
        "STA 0+00 TO STA 4+51 DIR. BORE (451')",          # run callout -> reset
        "AP-999 SPLICE LOC 99",                           # orphan (None)
        "STA 1+40",
        "TERMINAL 6 PORT HH AP-165 SPLICE LOC 12",        # owned by 1+40
    ]
    owning = p0._ap_owning_stations(lines)
    assert owning[163] == "4+51" and owning[165] == "1+40" and owning[999] is None


# ---- pure: class-aware drop phrase -----------------------------------------

def test_drop_phrase_class_aware():
    assert "drop structure" in p0._drop_phrase("flower_pot", "FLOWER POT")
    assert "drop structure" in p0._drop_phrase("installer_hh", "INSTALLER HH")
    # class None (e.g. a NEXTLINK / backbone splice HH) is NOT called a drop structure
    none_phrase = p0._drop_phrase(None, "EXIST. NEXTLINK HH PROP. SPLICE POINT 13")
    assert "drop structure" not in none_phrase and "splice HH" in none_phrase


# ---- pure: per-bore disposition tree ---------------------------------------

_ATTR = {"result": p0.A_ATTRIB, "ap": 163, "splice": "SPLICE LOC 46"}
_JUNC = {"result": p0.A_JUNCTION, "ap": 163, "splice": "SPLICE LOC 46"}
_CONTRA = {"result": p0.A_KMZ_CONTRA, "ap": 161, "splice": "SPLICE LOC 35"}
_NONOTE = {"result": p0.A_NO_NOTE, "ap": None, "splice": None}
_NOPAIR = {"result": p0.A_NO_PAIR, "ap": None, "splice": None}


def test_disposition_priority():
    # banked source contradiction overrides everything
    assert p0._bore_disposition("log44", _ATTR, _ATTR, []) == p0.B_SOURCE_CONTRA
    # PDF<->KMZ contradiction beats a clean attribution headline
    assert p0._bore_disposition("logX", _NONOTE, _CONTRA, []) == p0.A_KMZ_CONTRA
    # clean END attribution
    assert p0._bore_disposition("logX", _NONOTE, _ATTR, []) == p0.A_ATTRIB
    # START junction (END not attributed)
    assert p0._bore_disposition("logX", _JUNC, _NOPAIR, []) == p0.A_JUNCTION
    # no attribution but a flat AP rejected
    assert p0._bore_disposition(
        "logX", _NONOTE, _NOPAIR, [{"ap": 148, "owning_station": "20+71"}]) == \
        p0.B_SHEET_NEIGHBOR
    assert p0._bore_disposition("logX", _NONOTE, _NONOTE, []) == p0.A_NO_NOTE


# ---- end-to-end attribution over a FAKE plan (no PDF/corpus) ---------------

class _FakePlan:
    def __init__(self, lines):
        self._lines = lines

    def lines(self, sheet, offset):
        return self._lines


def test_attribute_end_terminal_is_attributed():
    plan = _FakePlan(["STA 4+51", "TERMINAL 6 PORT HH AP-163 SPLICE LOC 46"])
    a = p0._attribute_endpoint(plan, [10], 0, 451.0, "END")
    assert a["result"] == p0.A_ATTRIB and a["ap"] == 163
    assert a["structure_class"] == p0.TERMINAL_CLASS


def test_attribute_start_terminal_is_junction_origin_not_attributed():
    # DIRECTION rule: a terminal at a START is the prior feed's terminus.
    plan = _FakePlan(["STA 4+51", "TERMINAL 6 PORT HH AP-163 SPLICE LOC 46"])
    a = p0._attribute_endpoint(plan, [10], 0, 451.0, "START")
    assert a["result"] == p0.A_JUNCTION and a["ap"] == 163


def test_attribute_flower_pot_is_no_pair():
    plan = _FakePlan(['STA 2+99', '11"X11"X12" FLOWER POT'])
    a = p0._attribute_endpoint(plan, [8], 0, 299.0, "END")
    assert a["result"] == p0.A_NO_PAIR and a["structure_class"] == "flower_pot"


def test_attribute_absent_note_is_no_note():
    plan = _FakePlan(["STA 9+99 TERMINAL 6 PORT HH AP-1 SPLICE LOC 1"])
    a = p0._attribute_endpoint(plan, [10], 0, 451.0, "END")
    assert a["result"] == p0.A_NO_NOTE


# ---- banked constants -------------------------------------------------------

def test_banked_constants():
    assert set(p0.TARGETS) == {"log10", "log68", "log7", "log42", "log44"}
    assert p0.TERMINAL_CLASS == "terminal_port_hh"
    assert p0.SOURCE_CONTRADICTION == {"log44"}
    assert p0.M91_CONTROL_AP == {"log7": 163, "log42": 105}
    assert sum(p0.BANKED_FULLEST_LANES.values()) == 58
    # the join results that REFUTE an attributed pair
    assert "KMZ_TERMINAL_JOIN_AP_ONLY_REJECTED" in p0._CONTRA_JOINS
    assert "KMZ_TERMINAL_JOIN_BOUND" not in p0._CONTRA_JOINS


# ---- read-only posture + UNWIRED -------------------------------------------

def test_read_only_posture_no_render_no_placement():
    src = inspect.getsource(p0)
    assert "truelinev2.render" not in src and "render_redline_stroke" not in src
    assert 'OUT_DIR.glob("*.png")' in src
    assert "Status.AUTO" not in src and "place_bore" not in src


def test_proof_not_imported_by_engine_and_join_unwired():
    engine = (list((PKG / "match").glob("*.py"))
              + list((PKG / "review").glob("*.py")) + [PKG / "service.py"])
    for f in engine:
        src = f.read_text(encoding="utf-8")
        assert "run_terminus_attribution_phase0" not in src, f
        assert "kmz_structure_join" not in src, f
