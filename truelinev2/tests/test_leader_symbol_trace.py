"""Adversarial proof for the read-only LEADER-TRACED structure-coordinate provenance (cold packages).

Upgrades the continued-90 cold-lane coordinate: when a printed terminus label's own drawn LEADER points at a
unique drawn SYMBOL, the coordinate is bound with the stronger ``LEADER_TRACED_SYMBOL`` provenance; otherwise
it falls back to the weaker geometry-only ``COMPACT_SYMBOL_AT_STATION``, and ambiguous/label-only evidence
refuses (non-promoting). Layer-agnostic + name-free; NO class verification (still missing — needs a CAD
layer/class table the cold lane lacks); validated on the adversarial harness only (no eligible fresh package).
No AUTO, no _cap_review, no placement/status/render change.
"""
from __future__ import annotations

import ast
import copy
import os
import re
from pathlib import Path

from truelinev2.extract.generic_geometry import GenericGeometryDialect
from truelinev2.extract.leader_symbol_trace import (
    AMBIGUOUS_LEADER,
    AMBIGUOUS_SYMBOL,
    LABEL_ONLY_NO_SYMBOL,
    LEADER_TRACED_SYMBOL,
    NO_LEADER_EVIDENCE,
    trace_label_to_symbol,
)
from truelinev2.extract.run_geometry_observer import BRANCH_FORKED, BRANCH_UNIQUE
from truelinev2.extract.terminus_coordinate_observer import (
    AMBIGUOUS_DRAWN_COORDINATE,
    COMPACT_SYMBOL_AT_STATION,
    DRAWN_COORDINATE_BOUND,
    ENDPOINT_TO_TERMINUS_2D_TIGHTNESS,
    NO_DRAWN_COORDINATE,
    NOT_SOURCE_BOUND,
    TIGHTNESS_2D_LOOSE,
    TIGHTNESS_2D_UNMEASURABLE,
    derive_terminus_coordinate,
    observe_terminus_coordinates,
)
from truelinev2.harness.synth import (
    plan_ambiguous_leader_with_notes,
    plan_ambiguous_symbol_with_notes,
    plan_forked_run_with_notes,
    plan_label_only_no_symbol_with_notes,
    plan_leader_traced_with_notes,
    plan_symbol_clean_with_notes,
    plan_symbol_y_misaligned_with_notes,
)
from truelinev2.ingest.pdf import PlanPdf

_TRACE = Path(__file__).resolve().parents[1] / "extract" / "leader_symbol_trace.py"
_START_FT, _END_FT = 1175.0, 1325.0


def _word(text, xc, yc):
    return {"text": text, "xc": float(xc), "yc": float(yc)}


def _box_item(x0, y0, x1, y1):
    cs = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    lines = [(a[0], a[1], b[0], b[1]) for a, b in zip(cs, cs[1:] + cs[:1])]
    return {"x0": x0, "y0": y0, "x1": x1, "y1": y1, "lines": lines}


def _line_item(ax, ay, bx, by):
    return {"x0": min(ax, bx), "y0": min(ay, by), "x1": max(ax, bx), "y1": max(ay, by),
            "lines": [(ax, ay, bx, by)]}


def _shape(x0, y0, x1, y1):
    return {"x0": float(x0), "y0": float(y0), "x1": float(x1), "y1": float(y1),
            "xc": (x0 + x1) / 2.0, "yc": (y0 + y1) / 2.0}


def _sym_shape(cx, cy, half=5.0):
    return _shape(cx - half, cy - half, cx + half, cy + half)


# --------------------------------------------------------------------------------------------------------- #
# Unit layer: the resolver's hops on plain data (no PDF), uniqueness-mandatory.
# --------------------------------------------------------------------------------------------------------- #
_WORD = _word("11+75", 287, 357)
_BOX = _box_item(245, 351, 360, 365)
_LEADER = _line_item(300, 365, 297, 381)
_SYM = _sym_shape(295, 384)


def test_trace_resolves_label_box_leader_symbol():
    xy, sub, _d = trace_label_to_symbol([_WORD], [_BOX, _LEADER], [_SYM], label_tokens=["11+75"])
    assert sub == LEADER_TRACED_SYMBOL
    assert abs(xy[0] - 295) < 0.1 and abs(xy[1] - 384) < 0.1


def test_trace_no_label_word():
    xy, sub, _d = trace_label_to_symbol([], [_BOX, _LEADER], [_SYM], label_tokens=["11+75"])
    assert xy is None and sub == NO_LEADER_EVIDENCE


def test_trace_ambiguous_label_word():
    xy, sub, _d = trace_label_to_symbol([_WORD, _word("11+75", 600, 357)], [_BOX, _LEADER], [_SYM],
                                        label_tokens=["11+75"])
    assert xy is None and sub == AMBIGUOUS_LEADER


def test_trace_label_with_no_box_is_label_only():
    xy, sub, _d = trace_label_to_symbol([_WORD], [_LEADER], [_SYM], label_tokens=["11+75"])
    assert xy is None and sub == LABEL_ONLY_NO_SYMBOL      # no drawn frame to leader from


def test_trace_two_leaders_is_ambiguous():
    xy, sub, _d = trace_label_to_symbol([_WORD], [_BOX, _LEADER, _line_item(320, 365, 330, 381)], [_SYM],
                                        label_tokens=["11+75"])
    assert xy is None and sub == AMBIGUOUS_LEADER


def test_trace_leader_to_no_symbol_is_label_only():
    xy, sub, _d = trace_label_to_symbol([_WORD], [_BOX, _LEADER], [_sym_shape(600, 384)], label_tokens=["11+75"])
    assert xy is None and sub == LABEL_ONLY_NO_SYMBOL      # leader points at no drawn symbol


def test_trace_two_symbols_at_tip_is_ambiguous():
    xy, sub, _d = trace_label_to_symbol([_WORD], [_BOX, _LEADER], [_sym_shape(295, 384), _sym_shape(299, 382)],
                                        label_tokens=["11+75"])
    assert xy is None and sub == AMBIGUOUS_SYMBOL


def test_trace_leader_line_is_not_mistaken_for_its_own_symbol():
    """An elongated leader line must not count as the symbol at its own tip (aspect bound). With NO square
    symbol present, the trace is LABEL_ONLY_NO_SYMBOL, not a leader-traced bind to the leader itself."""
    leader_as_shape = _shape(297, 365, 300, 381)           # the leader's own bbox: 3x16, elongated
    xy, sub, _d = trace_label_to_symbol([_WORD], [_BOX, _LEADER], [leader_as_shape], label_tokens=["11+75"])
    assert xy is None and sub == LABEL_ONLY_NO_SYMBOL


# --------------------------------------------------------------------------------------------------------- #
# Unit layer: the coordinate ladder in derive_terminus_coordinate.
# --------------------------------------------------------------------------------------------------------- #
def test_derive_leader_traced_is_strongest_and_not_class_verified():
    c = derive_terminus_coordinate(source_bound=True, station_x=295.0, label_tokens=["11+75"],
                                   words=[_WORD], line_items=[_BOX, _LEADER], shapes=[_SYM])
    assert c.result == DRAWN_COORDINATE_BOUND
    assert c.provenance == LEADER_TRACED_SYMBOL
    assert c.leader_trace == LEADER_TRACED_SYMBOL
    assert c.class_verified is False                       # generic class verification is still missing


def test_derive_ambiguous_leader_refuses_without_downgrading():
    c = derive_terminus_coordinate(source_bound=True, station_x=295.0, label_tokens=["11+75"],
                                   words=[_WORD], line_items=[_BOX, _LEADER, _line_item(320, 365, 330, 381)],
                                   shapes=[_SYM])
    assert c.result == AMBIGUOUS_DRAWN_COORDINATE          # never downgraded to a weaker compact guess
    assert c.leader_trace == AMBIGUOUS_LEADER and c.xy is None


def test_derive_ambiguous_symbol_refuses():
    c = derive_terminus_coordinate(source_bound=True, station_x=295.0, label_tokens=["11+75"],
                                   words=[_WORD], line_items=[_BOX, _LEADER],
                                   shapes=[_sym_shape(295, 384), _sym_shape(299, 382)])
    assert c.result == AMBIGUOUS_DRAWN_COORDINATE
    assert c.leader_trace == AMBIGUOUS_SYMBOL and c.xy is None


def test_derive_falls_back_to_compact_when_no_leader():
    """No drawn frame/leader, but a compact symbol sits at the station -> the weaker COMPACT provenance."""
    c = derive_terminus_coordinate(source_bound=True, station_x=295.0, label_tokens=["11+75"],
                                   words=[_WORD], line_items=[], shapes=[_SYM])
    assert c.result == DRAWN_COORDINATE_BOUND
    assert c.provenance == COMPACT_SYMBOL_AT_STATION       # weaker than LEADER_TRACED_SYMBOL
    assert c.leader_trace == LABEL_ONLY_NO_SYMBOL


def test_derive_label_only_no_symbol_yields_no_coordinate():
    c = derive_terminus_coordinate(source_bound=True, station_x=295.0, label_tokens=["11+75"],
                                   words=[_WORD], line_items=[_BOX], shapes=[])
    assert c.result == NO_DRAWN_COORDINATE                 # label/text centroid is never a coordinate
    assert c.xy is None


def test_derive_not_source_bound():
    c = derive_terminus_coordinate(source_bound=False, station_x=295.0, label_tokens=["11+75"],
                                   words=[_WORD], line_items=[_BOX, _LEADER], shapes=[_SYM])
    assert c.result == NOT_SOURCE_BOUND and c.xy is None


# --------------------------------------------------------------------------------------------------------- #
# Integration layer: real synthetic PDFs through the dialect (read-only).
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


def test_pdf_leader_traced_is_stronger_than_compact(tmp_path):
    _p, _d, traced = _observe(plan_leader_traced_with_notes(), tmp_path, "leader")
    assert traced is not None
    assert traced.start_coordinate.result == DRAWN_COORDINATE_BOUND
    assert traced.start_coordinate.provenance == LEADER_TRACED_SYMBOL
    assert traced.end_coordinate.provenance == LEADER_TRACED_SYMBOL
    assert traced.start_coordinate.class_verified is False and traced.end_coordinate.class_verified is False
    assert traced.two_d_verified is True

    # the same clean drawn symbol WITHOUT a leader frame resolves only to the weaker compact provenance
    _p2, _d2, compact = _observe(plan_symbol_clean_with_notes(), tmp_path, "compact")
    assert compact.start_coordinate.provenance == COMPACT_SYMBOL_AT_STATION
    # LEADER_TRACED_SYMBOL is the stronger rung
    assert traced.start_coordinate.provenance != compact.start_coordinate.provenance


def test_pdf_label_only_produces_no_coordinate(tmp_path):
    _p, _d, o = _observe(plan_label_only_no_symbol_with_notes(), tmp_path, "label_only")
    assert o.start_coordinate.result == NO_DRAWN_COORDINATE
    assert o.start_2d.verdict == TIGHTNESS_2D_UNMEASURABLE
    assert o.two_d_verified is False


def test_pdf_ambiguous_leader_is_non_promoting(tmp_path):
    _p, _d, o = _observe(plan_ambiguous_leader_with_notes(), tmp_path, "amb_leader")
    assert o.start_coordinate.result == AMBIGUOUS_DRAWN_COORDINATE
    assert o.start_coordinate.leader_trace == AMBIGUOUS_LEADER
    assert o.start_2d.verdict == TIGHTNESS_2D_UNMEASURABLE
    assert o.two_d_verified is False                       # non-promoting


def test_pdf_ambiguous_symbol_is_non_promoting(tmp_path):
    _p, _d, o = _observe(plan_ambiguous_symbol_with_notes(), tmp_path, "amb_symbol")
    assert o.start_coordinate.result == AMBIGUOUS_DRAWN_COORDINATE
    assert o.start_coordinate.leader_trace == AMBIGUOUS_SYMBOL
    assert o.two_d_verified is False


def test_pdf_y_misaligned_still_rejected_by_2d(tmp_path):
    _p, _d, o = _observe(plan_symbol_y_misaligned_with_notes(), tmp_path, "ymis")
    assert o.would_reject is True
    assert ENDPOINT_TO_TERMINUS_2D_TIGHTNESS in o.reject_signals


def test_pdf_fork_still_rejected_by_branch_uniqueness(tmp_path):
    _p, _d, o = _observe(plan_forked_run_with_notes(), tmp_path, "fork")
    assert o.branch_uniqueness == BRANCH_FORKED
    assert o.would_reject is True


# --------------------------------------------------------------------------------------------------------- #
# Guardrails: read-only, no placement/render imports, name-free.
# --------------------------------------------------------------------------------------------------------- #
def test_observer_does_not_mutate_the_dialect(tmp_path):
    plan, dialect, _o = _observe(plan_leader_traced_with_notes(), tmp_path, "ro")
    before_band = copy.deepcopy(dialect._band_segs)
    before_axis = {k: (v.a, v.b, v.n, v.residual_ft) for k, v in dialect._axis.items()}
    observe_terminus_coordinates(plan, dialect, 1, _START_FT, _END_FT,
                                 start_source_bound=True, end_source_bound=True)
    assert dialect._band_segs == before_band
    assert {k: (v.a, v.b, v.n, v.residual_ft) for k, v in dialect._axis.items()} == before_axis


def test_trace_module_imports_no_placement_or_render_code():
    tree = ast.parse(_TRACE.read_text(encoding="utf-8"), filename=_TRACE.name)
    forbidden = ("truelinev2.contracts", "truelinev2.match", "truelinev2.render",
                 "truelinev2.api", "truelinev2.store", "truelinev2.review", "truelinev2.ingest")
    mods = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.append(node.module)
    leaks = [m for m in mods if any(m == f or m.startswith(f + ".") for f in forbidden)]
    assert not leaks, "leader-trace must be pure geometry (stdlib only): %r" % leaks


def test_trace_module_is_name_free():
    src = _TRACE.read_text(encoding="utf-8")
    raw = os.environ.get("NAME_TOKENS", "").strip()
    if raw:
        tokens = [t for t in re.split(r"[|,\s]+", raw) if t]
        hits = sorted({t for t in tokens if re.search(r"\b" + re.escape(t.lower()) + r"\b", src.lower())})
        assert not hits, "NAME_TOKENS leaked into the leader-trace module: %r" % hits
    assert LEADER_TRACED_SYMBOL == "LEADER_TRACED_SYMBOL"
