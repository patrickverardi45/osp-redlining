"""M8.24 -- origin-identity abstain probe tests (offline; posture + premises).

The milestone is a SAFE ABSTAIN + reframe (no promotion, census frozen). These
pin: the typed findings are not lane statuses / not placement signals; the
no-promotion / no-render / no-AUTO posture; that the named next capability is
explicitly NOT the existing identity-agnostic M8.5 reverse_anchor; and the
dialect fill discriminators the 'origin unidentified by fill' claim rests on.
"""
import inspect
from pathlib import Path

from truelinev2.extract.structure_position import BRENHAM_LANE_DIALECT
from truelinev2.proof import run_origin_identity_abstain_probe as probe

PKG = Path(probe.__file__).resolve().parents[1]


def test_typed_findings_are_not_lane_statuses():
    from truelinev2.match.symbol_conduit_lane import (S_CROSS_SHEET,
                                                      S_STRUCTURE_REQUIRED,
                                                      S_UNPRINTED)
    lane = {S_CROSS_SHEET, S_STRUCTURE_REQUIRED, S_UNPRINTED}
    findings = {probe.ORIGIN_PRINTED_UNIDENTIFIED,
                probe.TERMINAL_IS_THE_BOUND_STRUCTURE,
                probe.ORIGIN_SYMBOL_IDENTITY_BINDER_REQUIRED}
    assert findings.isdisjoint(lane)


def test_no_promotion_no_auto_no_render():
    src = inspect.getsource(probe)
    assert '"start_origin_identity_bound": False' in src
    assert '"is_review_candidate": False' in src
    assert "AUTO_" not in src
    assert "truelinev2.render" not in src
    assert "render_redline_stroke" not in src
    assert "max_expansions=" not in src              # no budget knob
    assert 'OUT_DIR.glob("*.png")' in src            # G7 asserts zero PNGs


def test_next_capability_excludes_identity_agnostic_reverse_anchor():
    # the named next capability must NOT be mistaken for the shipped M8.5
    # reverse_anchor (a footage START-POSITION solver, identity-agnostic).
    src = inspect.getsource(probe)
    assert "ORIGIN-SYMBOL-IDENTITY binder" in src
    assert "reverse_anchor" in src and "identity-agnostic" in src
    assert "station_axis" in src and "directional filter" in src


def test_origin_fill_discriminators_are_the_dialect_class_fills():
    # the 'origin unidentified by fill' claim rests on these dialect fills.
    sl = BRENHAM_LANE_DIALECT.structure_layers
    assert sl["installer_hh"][2] == probe.INSTALLER_RED
    assert sl["terminal_port_hh"][2] == probe.TERMINAL_BLUE
    assert probe.INSTALLER_RED != probe.TERMINAL_BLUE


def test_no_engine_module_imports_the_probe():
    engine = (list((PKG / "match").glob("*.py"))
              + list((PKG / "review").glob("*.py")) + [PKG / "service.py"])
    for f in engine:
        assert "run_origin_identity_abstain_probe" not in f.read_text(
            encoding="utf-8"), f


def test_segment_b_answer_pinned_from_span_not_log41_digit():
    src = inspect.getsource(probe)
    assert "callout-frame ORIGIN" in src
    assert "270+17" in src
    assert "NOT from the log41" in src or "not from the log41" in src.lower()
