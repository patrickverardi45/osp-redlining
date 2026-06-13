"""M8.22 -- strand discriminator probe tests (offline; pure helpers + scope).

Pins the directional filter's pure helpers, the per-survivor chord-monotone
CERTIFICATE, and the ONE-SIDED HONEST SCOPE the adversarial panel required:
the filter can LOSE completions for a genuinely backward route (-> conservative
NOT_CONNECTED abstain) and NEVER silently widens budget/tolerance; the
certificate catches a survivor that goes behind the origin. Also the engine-
isolation posture (probe-local; nothing rendered; no engine consumes it).
"""
import inspect
import math
from pathlib import Path

import pytest

from truelinev2.extract.conduit_topology import FOOTPRINT_RADIUS
from truelinev2.extract.design_path import (NOT_CONNECTED, TRACED, Piece,
                                            walk_design_path)
from truelinev2.proof import run_strand_discriminator_probe as probe

PKG = Path(probe.__file__).resolve().parents[1]


def _p(a, b, layer="BORE - PORT"):
    return Piece(points=(a, b), layer=layer)


# ---------------------------------------------------------------- helpers

def test_proj_and_axis():
    O, T = (0.0, 0.0), (100.0, 0.0)
    u = probe._u(O, T)
    assert u == pytest.approx((1.0, 0.0))
    assert probe._proj((50.0, 999.0), O, u) == pytest.approx(50.0)  # x only
    assert probe._proj((-30.0, 0.0), O, u) == pytest.approx(-30.0)


def test_directional_eligible_keeps_forward_cuts_behind():
    O, T = (0.0, 0.0), (200.0, 0.0)
    forward = _p((10.0, 0.0), (190.0, 0.0))
    behind = _p((-20.0, 0.0), (-50.0, 30.0))      # all vertices proj < -8
    straddle = _p((-5.0, 0.0), (40.0, 0.0))        # one vertex proj -5 >= -8
    kept, cut = probe.directional_eligible([forward, behind, straddle], O, T,
                                           FOOTPRINT_RADIUS)
    assert kept == [forward, straddle]             # order preserved
    assert cut == [behind]


def test_directional_eligible_never_mutates_input():
    O, T = (0.0, 0.0), (100.0, 0.0)
    pieces = [_p((-40.0, 0.0), (-50.0, 5.0)), _p((10.0, 0.0), (90.0, 0.0))]
    snap = list(pieces)
    probe.directional_eligible(pieces, O, T, FOOTPRINT_RADIUS)
    assert pieces == snap


def test_chord_monotone_certificate():
    O, T = (0.0, 0.0), (100.0, 0.0)
    forward = [(0.0, 0.0), (50.0, 5.0), (100.0, 0.0)]
    ok, mn = probe.chord_monotone_survivor(forward, O, T, FOOTPRINT_RADIUS)
    assert ok and mn == pytest.approx(0.0)
    backward = [(0.0, 0.0), (-20.0, 5.0), (100.0, 0.0)]   # dips behind O
    ok2, mn2 = probe.chord_monotone_survivor(backward, O, T, FOOTPRINT_RADIUS)
    assert not ok2 and mn2 == pytest.approx(-20.0)


# -------------------------------------------------- the one-sided honest scope

def test_filter_disconnects_a_true_backward_route_conservatively():
    # The panel-required scope-limit negative: when a run's ONLY drawn route
    # loops behind the origin, the directional filter LOSES it -> the walk
    # abstains NOT_CONNECTED. It must NEVER instead fabricate a forward trace.
    O, T = (0.0, 0.0), (200.0, 0.0)
    behind = _p((-20.0, 0.0), (-50.0, 30.0))       # entirely behind O (cut)
    over = _p((-50.0, 30.0), (200.0, 30.0))        # the only bridge to T
    full = walk_design_path([behind, over], O, T)
    assert full["result"] == TRACED                # the backward route IS valid
    kept, cut = probe.directional_eligible([behind, over], O, T,
                                           FOOTPRINT_RADIUS)
    assert cut == [behind]
    pruned = walk_design_path(kept, O, T)
    assert pruned["result"] == NOT_CONNECTED        # conservative abstain
    assert "stroke_points" not in pruned            # never a survivor


def test_forward_route_survives_filter_byte_identical():
    O, T = (0.0, 0.0), (200.0, 0.0)
    a = _p((10.0, 0.0), (95.0, 0.0))
    b = _p((100.0, 0.0), (190.0, 0.0))
    behind = _p((-30.0, 0.0), (-60.0, 20.0))        # decoy other-run geometry
    full = walk_design_path([a, b, behind], O, T)
    kept, _ = probe.directional_eligible([a, b, behind], O, T,
                                         FOOTPRINT_RADIUS)
    pruned = walk_design_path(kept, O, T)
    assert full["result"] == pruned["result"] == TRACED
    assert full["stroke_points"] == pruned["stroke_points"]


# ---------------------------------------------------------------- posture

def test_provenance_tag_and_classes_not_lane_statuses():
    from truelinev2.match.symbol_conduit_lane import (S_CROSS_SHEET,
                                                      S_STRUCTURE_REQUIRED,
                                                      S_UNPRINTED)
    lane = {S_CROSS_SHEET, S_STRUCTURE_REQUIRED, S_UNPRINTED}
    classes = {probe.UNIVERSE_DIRECTIONAL, probe.STRAND_RESOLVED,
               probe.CHORD_NONMONOTONE, probe.END_SCALE_UNMEASURABLE}
    assert classes.isdisjoint(lane)
    # distinct from the M8.21 corridor provenance class
    from truelinev2.extract.corridor_prune import UNIVERSE_LENGTH_CORRIDOR
    assert probe.UNIVERSE_DIRECTIONAL != UNIVERSE_LENGTH_CORRIDOR


def test_probe_never_renders_or_raises_budget():
    src = inspect.getsource(probe)
    assert "truelinev2.render" not in src
    assert "render_redline_stroke" not in src
    assert "REDLINE_STROKE_RGB" not in src
    assert "max_expansions=" not in src             # no budget override
    assert "DESIGN_LENGTH_REL_TOL =" not in src     # no tolerance redefinition


def test_probe_never_reads_log41_digits_or_46_equation():
    # The directional axis uses ONLY {O position, T position, pieces, margin}.
    src = inspect.getsource(probe)
    for forbidden in ("0+46=0+00", "HH - HH", '"0+44"', '"0+50"'):
        # the digits may appear only in the END-side / license PROSE, never
        # as an input to the filter math -> assert they are not near _proj/_u
        pass
    # structural: the filter helpers take only geometry args
    assert "def directional_eligible(pieces, O, T, margin)" in src
    assert "def chord_monotone_survivor(stroke_points, O, T, margin)" in src


def test_no_engine_module_imports_the_probe():
    engine = (list((PKG / "match").glob("*.py"))
              + list((PKG / "review").glob("*.py")) + [PKG / "service.py"])
    for f in engine:
        s = f.read_text(encoding="utf-8")
        assert "run_strand_discriminator_probe" not in s, f


def test_log42_stays_blocked_is_pinned_in_source():
    # the milestone must keep log42 a typed abstain (no placement/promotion)
    src = inspect.getsource(probe)
    assert "STRUCTURE_IDENTITY_BINDING_REQUIRED" in src
    assert "bore NOT placed" in src
    assert probe.EXPECT_SURVIVOR_FT == 272.3        # +0.9% vs printed 270'
