"""M8.23 -- END-continuity abstain probe tests (offline; posture + the one
sound gate's structural premises).

The milestone is a SAFE ABSTAIN (no REVIEW promotion, census frozen). These
pin: the dialect layer/class separation the FLOWER POT exclusion rests on;
that the probe's typed findings are not lane statuses and not placement
signals; the no-promotion / no-render / no-budget posture; and that the
honest verdict (NOT a REVIEW candidate; START identity is the blocker) is
stated in source.
"""
import inspect
from pathlib import Path

from truelinev2.extract.structure_position import BRENHAM_LANE_DIALECT
from truelinev2.proof import run_end_continuity_abstain_probe as probe

PKG = Path(probe.__file__).resolve().parents[1]


def test_terminal_port_hh_and_flower_pot_are_distinct_layers():
    # the FLOWER POT exclusion rests on a PRINTED-CLASS / CAD-layer separation,
    # never on distance -- pin that the two classes live on different layers.
    sl = BRENHAM_LANE_DIALECT.structure_layers
    assert sl["terminal_port_hh"][1] == "NEXTLINK"
    assert sl["flower_pot"][1] == "FLOWER POT"
    assert sl["terminal_port_hh"][1] != sl["flower_pot"][1]


def test_typed_findings_are_not_lane_statuses():
    from truelinev2.match.symbol_conduit_lane import (S_CROSS_SHEET,
                                                      S_STRUCTURE_REQUIRED,
                                                      S_UNPRINTED)
    lane = {S_CROSS_SHEET, S_STRUCTURE_REQUIRED, S_UNPRINTED}
    findings = {probe.BLOCKER_IS_START_IDENTITY,
                probe.END_CLASS_BOUND_NONPROMOTING,
                probe.END_SCALE_UNMEASURABLE,
                probe.FLOWER_POT_CLASS_EXCLUDED}
    assert findings.isdisjoint(lane)


def test_probe_makes_no_review_promotion_and_no_auto():
    src = inspect.getsource(probe)
    # the verdict is an ABSTAIN: log42 stays blocked, not a REVIEW candidate
    assert '"is_review_candidate": False' in src
    assert "NOT a REVIEW candidate" in src
    # no AUTO, no stroke geometry, no tolerance/budget knobs
    assert "AUTO_" not in src
    assert "max_expansions=" not in src
    assert "REDLINE_STROKE_RGB" not in src
    assert "render_redline_stroke" not in src


def test_probe_names_start_identity_as_the_blocker():
    src = inspect.getsource(probe)
    assert "START_STRUCTURE_IDENTITY_UNBOUND" in src
    assert "NEXTLINK@819,351" in src           # the named origin
    assert "extract_group_claims" in src       # measures the SHIPPED join (0 survivors)


def test_no_engine_module_imports_the_probe():
    engine = (list((PKG / "match").glob("*.py"))
              + list((PKG / "review").glob("*.py")) + [PKG / "service.py"])
    for f in engine:
        assert "run_end_continuity_abstain_probe" not in f.read_text(
            encoding="utf-8"), f


def test_probe_renders_nothing():
    src = inspect.getsource(probe)
    assert "truelinev2.render" not in src       # no render import
    assert "OUT_DIR.glob(\"*.png\")" in src      # G7 asserts zero PNGs on disk
