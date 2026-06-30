"""Adversarial proof for the read-only TERMINUS-COORDINATE + 2-D endpoint-tightness observer.

Closes the continued-89 residual AGAINST THE ADVERSARIAL HARNESS only: a source-bound terminus's drawn (x, y)
is derived from existing drawn geometry (a compact drawn symbol at the bound station), and 2-D tightness then
rejects a run that reaches the right station-x at the WRONG y — which station-x tightness cannot see. It does
NOT prove real generalization: no eligible fresh non-recognized package exists in the repo (only the recognized
work corpus + synthetic fixtures), so this validates the signals on the synthetic harness; the read-only
``observe_package_terminus_geometry`` PATH is what a future real package would run through. No AUTO, no
_cap_review, no placement/status/render change.
"""
from __future__ import annotations

import ast
import copy
import math
import os
import re
from pathlib import Path

from truelinev2.extract.generic_geometry import GenericGeometryDialect
from truelinev2.extract.run_geometry_observer import (
    BRANCH_FORKED,
    BRANCH_UNIQUE,
    TIGHTNESS_TIGHT,
)
from truelinev2.extract.terminus_coordinate_observer import (
    AMBIGUOUS_DRAWN_COORDINATE,
    COMPACT_SYMBOL_AT_STATION,
    DRAWN_COORDINATE_BOUND,
    ENDPOINT_TO_TERMINUS_2D_TIGHTNESS,
    NO_DRAWN_COORDINATE,
    NOT_SOURCE_BOUND,
    TERMINUS_DRAWN_COORDINATE,
    TIGHTNESS_2D_LOOSE,
    TIGHTNESS_2D_TIGHT,
    TIGHTNESS_2D_UNMEASURABLE,
    derive_terminus_drawn_coordinate,
    endpoint_2d_tightness,
    observe_package_terminus_geometry,
    observe_terminus_coordinates,
    observe_terminus_coordinates_core,
)
from truelinev2.harness.synth import (
    plan_clean_bore_with_notes,
    plan_forked_run_with_notes,
    plan_symbol_clean_with_notes,
    plan_symbol_y_misaligned_with_notes,
)
from truelinev2.ingest.pdf import PlanPdf

_OBS = Path(__file__).resolve().parents[1] / "extract" / "terminus_coordinate_observer.py"
_START_FT, _END_FT = 1175.0, 1325.0


def _shape(x0, y0, x1, y1):
    return {"x0": float(x0), "y0": float(y0), "x1": float(x1), "y1": float(y1),
            "xc": (x0 + x1) / 2.0, "yc": (y0 + y1) / 2.0}


def _seg(ax, ay, bx, by):
    return {"a": (float(ax), float(ay)), "b": (float(bx), float(by))}


def _box_segs(cx, cy, half=5.0):
    """The 4 edges of a symbol box (as band-segments would carry them)."""
    x0, y0, x1, y1 = cx - half, cy - half, cx + half, cy + half
    return [_seg(x0, y0, x1, y0), _seg(x1, y0, x1, y1), _seg(x1, y1, x0, y1), _seg(x0, y1, x0, y0)]


# --------------------------------------------------------------------------------------------------------- #
# Unit layer: TERMINUS_DRAWN_COORDINATE derivation + 2-D tightness on plain data (no PDF).
# --------------------------------------------------------------------------------------------------------- #
def test_derive_binds_a_unique_compact_symbol_at_the_station():
    shapes = [_shape(440, 379, 450, 389)]                  # a compact symbol box centered (445,384)
    c = derive_terminus_drawn_coordinate(shapes, 445.0, source_bound=True)
    assert c.result == DRAWN_COORDINATE_BOUND
    assert c.provenance == COMPACT_SYMBOL_AT_STATION
    assert abs(c.xy[0] - 445) < 0.1 and abs(c.xy[1] - 384) < 0.1


def test_derive_ignores_long_run_lines_and_reports_no_coordinate():
    shapes = [_shape(295, 383, 445, 385)]                  # a long thin run line (not a compact symbol)
    c = derive_terminus_drawn_coordinate(shapes, 445.0, source_bound=True)
    assert c.result == NO_DRAWN_COORDINATE                 # the run line is not a structure symbol


def test_derive_refuses_when_two_symbols_sit_at_the_station():
    shapes = [_shape(440, 379, 450, 389), _shape(441, 360, 451, 370)]   # two compact shapes near x=445
    c = derive_terminus_drawn_coordinate(shapes, 445.0, source_bound=True)
    assert c.result == AMBIGUOUS_DRAWN_COORDINATE          # uniqueness-mandatory; never chosen between
    assert c.xy is None


def test_derive_reports_not_source_bound_without_printed_identity():
    shapes = [_shape(440, 379, 450, 389)]
    c = derive_terminus_drawn_coordinate(shapes, 445.0, source_bound=False)
    assert c.result == NOT_SOURCE_BOUND
    assert c.xy is None                                    # no printed identity -> no coordinate to seek


def test_2d_tightness_tight_loose_and_unmeasurable():
    assert endpoint_2d_tightness((445, 384), (445, 384)).verdict == TIGHTNESS_2D_TIGHT
    loose = endpoint_2d_tightness((445, 360), (445, 384))  # 24 pt off in y
    assert loose.verdict == TIGHTNESS_2D_LOOSE and loose.gap > 15
    assert endpoint_2d_tightness((445, 360), None).verdict == TIGHTNESS_2D_UNMEASURABLE
    assert endpoint_2d_tightness(None, (445, 384)).verdict == TIGHTNESS_2D_UNMEASURABLE


def test_core_clean_symbol_is_two_d_verified():
    segs = [_seg(295, 384, 445, 384)]
    shapes = [_shape(290, 379, 300, 389), _shape(440, 379, 450, 389)]
    o = observe_terminus_coordinates_core(shapes, segs, 295.0, 445.0,
                                          start_source_bound=True, end_source_bound=True)
    assert o.branch_uniqueness == BRANCH_UNIQUE
    assert o.endpoint_to_run_x_tightness == TIGHTNESS_TIGHT
    assert o.start_2d.verdict == TIGHTNESS_2D_TIGHT and o.end_2d.verdict == TIGHTNESS_2D_TIGHT
    assert o.two_d_verified is True and o.would_reject is False


def test_core_y_misaligned_rejects_only_via_2d_tightness():
    """Run reaches the right station-x at each end (station-x TIGHT) but ~24 pt off the drawn structures in y:
    ONLY ENDPOINT_TO_TERMINUS_2D_TIGHTNESS rejects it."""
    segs = [_seg(295, 360, 445, 360)]
    shapes = [_shape(290, 379, 300, 389), _shape(440, 379, 450, 389)]   # structures on the true band (y=384)
    o = observe_terminus_coordinates_core(shapes, segs, 295.0, 445.0,
                                          start_source_bound=True, end_source_bound=True)
    assert o.branch_uniqueness == BRANCH_UNIQUE             # the run is a clean chain
    assert o.endpoint_to_run_x_tightness == TIGHTNESS_TIGHT  # station-x looks tight
    assert o.start_2d.verdict == TIGHTNESS_2D_LOOSE and o.end_2d.verdict == TIGHTNESS_2D_LOOSE
    assert o.would_reject is True
    assert o.reject_signals == (ENDPOINT_TO_TERMINUS_2D_TIGHTNESS,)
    assert o.two_d_verified is False


def test_core_missing_coordinate_is_unmeasurable_and_not_promoted():
    segs = [_seg(295, 384, 445, 384)]                      # a clean run, but NO drawn symbol anywhere
    o = observe_terminus_coordinates_core([], segs, 295.0, 445.0,
                                          start_source_bound=True, end_source_bound=True)
    assert o.start_coordinate.result == NO_DRAWN_COORDINATE
    assert o.start_2d.verdict == TIGHTNESS_2D_UNMEASURABLE and o.end_2d.verdict == TIGHTNESS_2D_UNMEASURABLE
    assert o.two_d_verified is False                       # unmeasurable never promotes
    assert o.would_reject is False                         # ...but is not a rejection either


def test_core_excludes_symbol_segments_from_the_run_graph():
    """The 2-D observer removes detected symbol segments from the run graph (the run is linework MINUS markers),
    so a drawn symbol's edges cannot weld into the run and perturb branch-uniqueness. A larger/closer symbol than
    this would weld at the endpoint and read as a FORK in the raw graph; excluding it keeps the run a clean chain."""
    run_plus_box = [_seg(295, 384, 445, 384)] + _box_segs(445, 384)          # run line + a 4-edge symbol box
    o = observe_terminus_coordinates_core([_shape(440, 379, 450, 389)], run_plus_box, 295.0, 445.0,
                                          start_source_bound=True, end_source_bound=True)
    assert o.detail["run_segments_used"] == 1                                # the 4 box edges removed; run kept
    assert o.branch_uniqueness == BRANCH_UNIQUE


def test_core_fork_still_rejected_by_branch_uniqueness():
    fork = [_seg(295, 384, 370, 384), _seg(370, 384, 445, 376), _seg(370, 384, 445, 392)]
    o = observe_terminus_coordinates_core([], fork, 295.0, 445.0,
                                          start_source_bound=True, end_source_bound=True)
    assert o.branch_uniqueness == BRANCH_FORKED
    assert o.would_reject is True


# --------------------------------------------------------------------------------------------------------- #
# Integration layer: the observer over REAL synthetic PDFs through the generic dialect (read-only).
# --------------------------------------------------------------------------------------------------------- #
def _observe(plan_bytes, tmp_path, name, *, start_bound=True, end_bound=True):
    p = tmp_path / ("%s.pdf" % name)
    p.write_bytes(plan_bytes)
    plan = PlanPdf(str(p))
    dialect = GenericGeometryDialect()
    dialect.extract_callouts(plan, 1, 0)
    obs = observe_terminus_coordinates(plan, dialect, 1, _START_FT, _END_FT,
                                       start_source_bound=start_bound, end_source_bound=end_bound)
    return plan, dialect, obs


def test_pdf_clean_symbol_passes_2d_tightness(tmp_path):
    _p, _d, o = _observe(plan_symbol_clean_with_notes(), tmp_path, "clean_symbol")
    assert o is not None
    assert o.start_coordinate.result == DRAWN_COORDINATE_BOUND
    assert o.end_coordinate.result == DRAWN_COORDINATE_BOUND
    assert o.branch_uniqueness == BRANCH_UNIQUE
    assert o.start_2d.verdict == TIGHTNESS_2D_TIGHT and o.end_2d.verdict == TIGHTNESS_2D_TIGHT
    assert o.two_d_verified is True and o.would_reject is False


def test_pdf_y_misaligned_rejected_by_2d_even_though_station_x_is_tight(tmp_path):
    _p, _d, o = _observe(plan_symbol_y_misaligned_with_notes(), tmp_path, "y_misaligned")
    assert o is not None
    assert o.endpoint_to_run_x_tightness == TIGHTNESS_TIGHT      # station-x is fooled
    assert o.start_coordinate.result == DRAWN_COORDINATE_BOUND
    assert TIGHTNESS_2D_LOOSE in (o.start_2d.verdict, o.end_2d.verdict)
    assert o.would_reject is True
    assert ENDPOINT_TO_TERMINUS_2D_TIGHTNESS in o.reject_signals
    assert o.two_d_verified is False


def test_pdf_no_symbol_is_unmeasurable_not_promoted(tmp_path):
    _p, _d, o = _observe(plan_clean_bore_with_notes(), tmp_path, "no_symbol")
    assert o is not None
    assert o.start_coordinate.result == NO_DRAWN_COORDINATE
    assert o.start_2d.verdict == TIGHTNESS_2D_UNMEASURABLE
    assert o.two_d_verified is False                            # honest: cannot 2-D verify -> not promoted
    assert o.would_reject is False                              # ...and not rejected


def test_pdf_fork_still_rejected_by_branch_uniqueness(tmp_path):
    _p, _d, o = _observe(plan_forked_run_with_notes(), tmp_path, "fork")
    assert o is not None
    assert o.branch_uniqueness == BRANCH_FORKED
    assert o.would_reject is True


def test_pdf_unbound_endpoint_reports_not_source_bound(tmp_path):
    _p, _d, o = _observe(plan_symbol_clean_with_notes(), tmp_path, "unbound", start_bound=False)
    assert o is not None
    assert o.start_coordinate.result == NOT_SOURCE_BOUND        # no printed identity -> no coordinate sought
    assert o.start_2d.verdict == TIGHTNESS_2D_UNMEASURABLE


def test_validation_harness_path_runs_on_a_package(tmp_path):
    """The read-only validation PATH a future real/fresh package would run through. Exercised here on a
    synthetic package only (no eligible fresh non-recognized package exists in the repo)."""
    p = tmp_path / "pkg_plan.pdf"
    p.write_bytes(plan_symbol_clean_with_notes())
    o = observe_package_terminus_geometry(str(p), 1, _START_FT, _END_FT,
                                          start_source_bound=True, end_source_bound=True)
    assert o is not None and o.two_d_verified is True


# --------------------------------------------------------------------------------------------------------- #
# Guardrails: read-only, no placement/render imports, name-free.
# --------------------------------------------------------------------------------------------------------- #
def test_observer_does_not_mutate_the_dialect(tmp_path):
    plan, dialect, _o = _observe(plan_symbol_clean_with_notes(), tmp_path, "ro")
    before_band = copy.deepcopy(dialect._band_segs)
    before_axis = {k: (v.a, v.b, v.n, v.residual_ft) for k, v in dialect._axis.items()}
    observe_terminus_coordinates(plan, dialect, 1, _START_FT, _END_FT,
                                 start_source_bound=True, end_source_bound=True)
    assert dialect._band_segs == before_band
    assert {k: (v.a, v.b, v.n, v.residual_ft) for k, v in dialect._axis.items()} == before_axis


def test_observer_module_imports_no_placement_or_render_code():
    tree = ast.parse(_OBS.read_text(encoding="utf-8"), filename=_OBS.name)
    forbidden = ("truelinev2.contracts", "truelinev2.match", "truelinev2.render",
                 "truelinev2.api", "truelinev2.store", "truelinev2.review")
    mods = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.append(node.module)
    leaks = [m for m in mods if any(m == f or m.startswith(f + ".") for f in forbidden)]
    assert not leaks, "observer must not import placement/render code: %r" % leaks


def test_observer_module_is_name_free():
    src = _OBS.read_text(encoding="utf-8")
    raw = os.environ.get("NAME_TOKENS", "").strip()
    if raw:
        tokens = [t for t in re.split(r"[|,\s]+", raw) if t]
        hits = sorted({t for t in tokens if re.search(r"\b" + re.escape(t.lower()) + r"\b", src.lower())})
        assert not hits, "NAME_TOKENS leaked into the observer module: %r" % hits
    assert TERMINUS_DRAWN_COORDINATE == "TERMINUS_DRAWN_COORDINATE"
    assert ENDPOINT_TO_TERMINUS_2D_TIGHTNESS == "ENDPOINT_TO_TERMINUS_2D_TIGHTNESS"
