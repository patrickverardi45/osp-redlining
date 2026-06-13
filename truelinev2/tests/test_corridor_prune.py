"""M8.21 -- corridor_prune law tests (offline, synthetic; no PDF/corpus).

Pins: bound arithmetic from imported banked constants (zero new tunables);
typed refusal on missing scale (no fallback); vertex-containment keep rule;
the one-sided guarantee (pruning loses completions conservatively, never
creates them); the deliberate semantics shift (corridor TRACED vs
full-universe AMBIGUOUS) so it can never drift silently; and that neither a
budget raise nor a tolerance widening rides along.
"""
import math

import pytest

from truelinev2.extract import corridor_prune as cp
from truelinev2.extract.conduit_topology import MAX_DASH_GAP
from truelinev2.extract.corridor_prune import (LENGTH_INFEASIBLE_CHORD,
                                               SCALE_NOT_COHERENT,
                                               UNIVERSE_LENGTH_CORRIDOR,
                                               chord_infeasible,
                                               corridor_bound, prune_pieces)
from truelinev2.extract.design_path import (AMBIGUOUS, DESIGN_LENGTH_REL_TOL,
                                            MAX_WALK_EXPANSIONS,
                                            NOT_CONNECTED, TRACED,
                                            TRIM_RADIUS, Piece,
                                            walk_design_path)


def _piece(a, b, layer="L"):
    return Piece(points=(a, b), layer=layer)


# ---------------------------------------------------------------- constants

def test_banked_constants_unchanged():
    # Tripwire: the corridor law is parameterized ONLY by these banked
    # values; a budget raise or tolerance widening must fail here first.
    assert DESIGN_LENGTH_REL_TOL == 0.25
    assert MAX_DASH_GAP == 35.0
    assert TRIM_RADIUS == 2.0
    assert MAX_WALK_EXPANSIONS == 20000


def test_bound_arithmetic_pinned():
    exp, bound = corridor_bound(270.0, 1.44)
    assert exp == pytest.approx(388.8)
    # 388.8 * 1.25 + 2 * (35 + 2) = 486.0 + 74.0
    assert bound == pytest.approx(560.0)


def test_bound_scales_with_jump_cap():
    # The slack is stated in units of the walk's own jump cap; a caller
    # using a larger cap must get a larger bound (never silently unsound).
    _, b1 = corridor_bound(100.0, 1.0)
    _, b2 = corridor_bound(100.0, 1.0, jump_cap=MAX_DASH_GAP * 2)
    assert b2 == pytest.approx(b1 + 2.0 * MAX_DASH_GAP)
    exp, b = corridor_bound(100.0, 1.0, jump_cap=50.0)
    assert b >= exp * (1.0 + DESIGN_LENGTH_REL_TOL) + 2.0 * (50.0
                                                             + TRIM_RADIUS)


def test_missing_scale_is_typed_refusal_never_fallback():
    with pytest.raises(ValueError, match=SCALE_NOT_COHERENT):
        corridor_bound(270.0, None)
    with pytest.raises(ValueError, match=SCALE_NOT_COHERENT):
        corridor_bound(270.0, 0.0)
    with pytest.raises(ValueError):
        corridor_bound(0.0, 1.44)
    with pytest.raises(ValueError):
        corridor_bound(None, 1.44)


def test_no_packet_literal_fallback_in_source():
    import inspect
    src = inspect.getsource(cp)
    assert "1.44" not in src          # no packet-specific scale literal
    assert "or 1.44" not in src       # the forbidden fallback pattern
    assert "max_expansions" not in src  # the law never touches the budget


# ---------------------------------------------------------------- keep rule

def test_prune_keeps_on_path_drops_far_vertex_containment():
    start, end = (0.0, 0.0), (100.0, 0.0)
    on_path = _piece((10.0, 0.0), (90.0, 0.0))
    far = _piece((50.0, 300.0), (60.0, 300.0))      # min-sum ~600
    kept = prune_pieces([on_path, far], start, end, bound=150.0)
    assert kept == [on_path]


def test_prune_boundary_is_inclusive_and_order_preserved():
    start, end = (0.0, 0.0), (100.0, 0.0)
    # vertex at (50, 0): min-sum exactly 100
    exact = _piece((50.0, 0.0), (55.0, 0.0))
    near = _piece((20.0, 0.0), (30.0, 0.0))
    pieces = [exact, near]
    kept = prune_pieces(pieces, start, end, bound=100.0)
    assert exact in kept
    assert kept.index(near) > kept.index(exact)     # relative order stable


def test_prune_never_mutates_input():
    start, end = (0.0, 0.0), (100.0, 0.0)
    pieces = [_piece((10.0, 0.0), (90.0, 0.0)),
              _piece((50.0, 300.0), (60.0, 300.0))]
    snapshot = list(pieces)
    prune_pieces(pieces, start, end, bound=150.0)
    assert pieces == snapshot


def test_chord_infeasible():
    assert chord_infeasible((0.0, 0.0), (200.0, 0.0), bound=150.0)
    assert not chord_infeasible((0.0, 0.0), (100.0, 0.0), bound=150.0)


# ------------------------------------------------- one-sided guarantee

def test_pruning_loses_completions_conservatively_never_creates():
    # The out-of-corridor piece is the ONLY bridge across a > jump_cap gap:
    # both the full and the pruned walk must refuse (NOT_CONNECTED) -- no
    # admissible path exists, and pruning cannot create one.
    start, end = (0.0, 0.0), (100.0, 0.0)
    stub = _piece((5.0, 0.0), (40.0, 0.0))
    far_bridge = _piece((40.0, 300.0), (100.0, 300.0))
    full = walk_design_path([stub, far_bridge], start, end)
    kept = prune_pieces([stub, far_bridge], start, end, bound=160.0)
    pruned = walk_design_path(kept, start, end)
    assert full["result"] == NOT_CONNECTED
    assert pruned["result"] == NOT_CONNECTED


def test_inadmissible_rival_inside_corridor_still_kills_ambiguous():
    # The asymmetry pin: complete paths are NEVER post-filtered by length --
    # two jitter-distinct complete paths INSIDE the corridor kill the
    # candidate via AMBIGUOUS even if one could never pass the length gate.
    start, end = (0.0, 0.0), (100.0, 0.0)
    direct = _piece((5.0, 0.0), (95.0, 0.0))
    rival = _piece((5.0, 20.0), (95.0, 20.0))       # distinct (dev 20 > 4)
    pieces = [direct, rival]
    kept = prune_pieces(pieces, start, end, bound=200.0)
    assert kept == pieces                            # both inside corridor
    walk = walk_design_path(kept, start, end)
    assert walk["result"] == AMBIGUOUS
    assert walk["path_groups"] == 2


def test_semantics_shift_is_real_and_deliberate():
    # The documented certificate-class difference: a long detour rival that
    # CANNOT satisfy the length law is outside the corridor, so the pruned
    # walk is TRACED where the full walk is AMBIGUOUS. Corridor uniqueness
    # is uniqueness among length-admissible-capable geometry ONLY -- any
    # consumer must carry UNIVERSE_LENGTH_CORRIDOR provenance.
    start, end = (0.0, 0.0), (100.0, 0.0)
    direct = _piece((5.0, 0.0), (95.0, 0.0))          # min-sum 100 per vertex
    detour_a = _piece((5.0, 30.0), (50.0, 60.0))      # min-sums 130 / 156
    detour_b = _piece((50.0, 60.0), (95.0, 30.0))
    pieces = [direct, detour_a, detour_b]
    full = walk_design_path(pieces, start, end)
    assert full["result"] == AMBIGUOUS               # full universe: 2 paths
    kept = prune_pieces(pieces, start, end, bound=120.0)
    assert kept == [direct]                          # detour cannot be 100ft
    pruned = walk_design_path(kept, start, end)
    assert pruned["result"] == TRACED
    assert pruned["path_groups"] == 1
    assert isinstance(UNIVERSE_LENGTH_CORRIDOR, str)


def test_survivor_preservation_on_straight_route():
    # A unique admissible route survives pruning byte-identically.
    start, end = (0.0, 0.0), (100.0, 0.0)
    a = _piece((5.0, 0.0), (45.0, 0.0))
    b = _piece((50.0, 0.0), (95.0, 0.0))
    far = _piece((50.0, 400.0), (60.0, 400.0))
    full = walk_design_path([a, b, far], start, end)
    kept = prune_pieces([a, b, far], start, end, bound=160.0)
    pruned = walk_design_path(kept, start, end)
    assert full["result"] == TRACED and pruned["result"] == TRACED
    assert full["stroke_points"] == pruned["stroke_points"]


def test_typed_strings_are_not_lane_statuses():
    from truelinev2.match.symbol_conduit_lane import (S_CROSS_SHEET,
                                                      S_STRUCTURE_REQUIRED,
                                                      S_UNPRINTED)
    lane = {S_CROSS_SHEET, S_STRUCTURE_REQUIRED, S_UNPRINTED}
    assert {LENGTH_INFEASIBLE_CHORD, SCALE_NOT_COHERENT,
            UNIVERSE_LENGTH_CORRIDOR}.isdisjoint(lane)
