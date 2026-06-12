"""Offline tests for the M8.20 shared-origin adjudication probe seam.

The probe EXTRACTS (never infers) the facts the log8/log32/log42 start-origin
adjudication needs: walk-vs-walk geometry comparison against the structural
JITTER_EQUIV_TOL, printed conduit tokens from chain notes, and a per-candidate
elimination taxonomy. These tests pin the pure helpers and the no-wiring /
no-rendering safety posture; the plan-dependent gates live in the probe run.
"""
from __future__ import annotations

import inspect
from pathlib import Path

from truelinev2.extract.design_path import JITTER_EQUIV_TOL
from truelinev2.proof.run_shared_origin_adjudication_probe import (
    COMPARISON_NOT_AVAILABLE,
    DIVERGENT_PATHS,
    SHARED_ALIGNMENT,
    compare_design_walks,
    conduit_tokens,
)

LINE = [(0.0, 0.0), (50.0, 0.0), (100.0, 0.0), (150.0, 0.0)]


def _offset(pts, dy):
    return [(x, y + dy) for x, y in pts]


def test_identical_walks_are_shared_alignment():
    out = compare_design_walks(LINE, frozenset({1, 2, 3}),
                               list(LINE), frozenset({1, 2, 3}))
    assert out["verdict"] == SHARED_ALIGNMENT
    assert out["max_deviation_pt"] == 0.0
    assert out["piece_jaccard"] == 1.0
    assert out["shared_pieces"] == 3


def test_jitter_equivalent_walks_are_shared_alignment():
    # Entry-order permutations at a welded contact displace the path by at
    # most the weld-contact scale -- the M8.14.c equivalence band, reused
    # verbatim (never redefined here).
    out = compare_design_walks(LINE, frozenset({1, 2}),
                               _offset(LINE, JITTER_EQUIV_TOL - 1.0),
                               frozenset({1, 2}))
    assert out["verdict"] == SHARED_ALIGNMENT


def test_divergent_walks_are_physically_distinct():
    out = compare_design_walks(LINE, frozenset({1, 2}),
                               _offset(LINE, JITTER_EQUIV_TOL + 6.0),
                               frozenset({4, 5}))
    assert out["verdict"] == DIVERGENT_PATHS
    assert out["max_deviation_pt"] == JITTER_EQUIV_TOL + 6.0
    assert out["piece_jaccard"] == 0.0
    assert out["shared_pieces"] == 0


def test_short_walk_yields_no_comparison():
    out = compare_design_walks([(0.0, 0.0)], frozenset(), LINE, frozenset({1}))
    assert out["verdict"] == COMPARISON_NOT_AVAILABLE
    assert out["max_deviation_pt"] is None


def test_conduit_tokens_extracts_run_conduits_not_depth_ranges():
    notes = [
        'STA 0+00 TO STA 1+10 E/W PORT TERMINAL TAIL @ 24-36" MIN. DEPTH '
        'DIR. BORE (110\') 1-1.25" HDPE',
        'STA 1+10 TO STA 1+76 DIR. BORE (66\') 1-1.25" VACANT HDPE FOR '
        'FIBER DROP @ 24-36" MIN. DEPTH',
    ]
    assert conduit_tokens(notes) == ["1-1.25", "1-1.25"]


def test_conduit_tokens_empty_and_tokenless():
    assert conduit_tokens([]) == []
    assert conduit_tokens(["DIR. BORE (45') HDPE", ""]) == []
    assert conduit_tokens(['2-2" HDPE JOINT TRENCH']) == ["2-2"]


def test_probe_never_renders_and_engine_never_consumes_probe():
    """No-stroke / no-wiring posture, source-locked: the probe must not touch
    the render seam, and NO engine module (match/, review/, service) may
    import or reference the probe's verdict classes (suggestions/findings can
    never become engine placements through this seam)."""
    import truelinev2.proof.run_shared_origin_adjudication_probe as probe

    src = inspect.getsource(probe)
    assert "truelinev2.render" not in src
    assert "REDLINE_STROKE_RGB" not in src
    assert "render_redline_stroke" not in src

    pkg = Path(__file__).resolve().parents[1]
    engine_files = (sorted((pkg / "match").glob("*.py"))
                    + sorted((pkg / "review").glob("*.py"))
                    + [pkg / "service.py"])
    assert engine_files
    for path in engine_files:
        engine_src = path.read_text(encoding="utf-8")
        assert "shared_origin" not in engine_src, path.name
        assert "SHARED_ALIGNMENT" not in engine_src, path.name
        assert "run_shared_origin_adjudication_probe" not in engine_src, path.name


def test_deviation_formula_matches_design_path_equivalence_law():
    """Tripwire: the probe's duplicated deviation formula must stay equivalent
    to design_path._cross_deviation -- if the M8.14.c equivalence law ever
    evolves, this fails loud instead of letting the probe's SHARED/DIVERGENT
    verdict silently diverge from the engine's notion of 'same drawn line'."""
    from truelinev2.extract.design_path import _cross_deviation

    a = [(0.0, 0.0), (40.0, 5.0), (90.0, -3.0), (140.0, 12.0)]
    b = [(2.0, 7.0), (45.0, -6.0), (95.0, 9.0), (133.0, -4.0)]
    out = compare_design_walks(a, frozenset({1}), b, frozenset({2}))
    assert out["max_deviation_pt"] == round(_cross_deviation(a, b), 2)


def test_probe_verdict_classes_are_not_lane_statuses():
    from truelinev2.match import symbol_conduit_lane as lane

    lane_statuses = {
        getattr(lane, name) for name in dir(lane)
        if name.startswith("S_") and isinstance(getattr(lane, name), str)
    }
    assert SHARED_ALIGNMENT not in lane_statuses
    assert DIVERGENT_PATHS not in lane_statuses
    assert COMPARISON_NOT_AVAILABLE not in lane_statuses
