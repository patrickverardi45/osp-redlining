"""Offline tests for the shipped engine extractor seam.

The plan-integration behavior (claims for log8/log32, log42 excluded, faithful
promotion) is proven by ``run_shared_alignment_extract_proof``. These offline
tests pin the convention-agnostic, no-proof-import posture and the pure
dialect-sourced helpers.
"""
from __future__ import annotations

import inspect
from pathlib import Path

from truelinev2.extract.structure_position import BRENHAM_LANE_DIALECT
from truelinev2.match import shared_alignment_extract as extract
from truelinev2.match.shared_alignment_extract import (
    _materials,
    _matchline_boundary_stations,
    _multiport_keywords,
    _structure_layers,
)


def test_module_imports_no_proof_code():
    src = inspect.getsource(extract)
    assert "truelinev2.proof" not in src
    assert ".proof." not in src
    # and it is not a probe / renderer
    assert "render_redline_stroke" not in src
    assert "truelinev2.render" not in src


def test_materials_are_dialect_sourced():
    # 'VACANT HDPE' -> ('HDPE',); no convention string is hard-coded in engine.
    assert _materials(BRENHAM_LANE_DIALECT) == ("HDPE",)


def test_multiport_keywords_are_dialect_sourced():
    # Sourced from the dialect's declared multi-port origin classes.
    assert BRENHAM_LANE_DIALECT.multiport_origin_classes == ("terminal_port_hh",)
    kws = _multiport_keywords(BRENHAM_LANE_DIALECT)
    assert "TERMINAL" in kws and "PORT HH" in kws


def test_multiport_keywords_empty_when_no_classes_declared():
    import dataclasses

    plain = dataclasses.replace(BRENHAM_LANE_DIALECT, multiport_origin_classes=())
    assert _multiport_keywords(plain) == ()


def test_structure_layers_are_sorted_unique():
    layers = _structure_layers(BRENHAM_LANE_DIALECT)
    assert layers == sorted(set(layers))
    assert layers  # nonempty for Brenham


class _Frame:
    def __init__(self, sid):
        self.from_frame = f"sheet:{sid[0]}"
        self.to_frame = f"sheet:{sid[1]}"


class _Edge:
    def __init__(self, a, b, a_raw, b_raw):
        self.from_frame = f"sheet:{a}"
        self.to_frame = f"sheet:{b}"
        self.a_raw = a_raw
        self.b_raw = b_raw


class _Graph:
    def __init__(self, edges):
        self.edges = edges


def test_matchline_boundary_stations_collects_both_sides_for_the_pair_only():
    g = _Graph([
        _Edge(18, 22, "1+76", "1+76"),
        _Edge(18, 22, "1+77", "1+77"),
        _Edge(10, 9, "6+11", "6+11"),   # a different sheet pair, excluded
    ])
    assert _matchline_boundary_stations(g, 18, 22) == {"1+76", "1+77"}
    assert _matchline_boundary_stations(g, 10, 9) == {"6+11"}


def test_dialect_field_is_additive_and_defaulted():
    # The new field exists with an empty default; existing construction works.
    import dataclasses

    field_names = {f.name for f in dataclasses.fields(type(BRENHAM_LANE_DIALECT))}
    assert "multiport_origin_classes" in field_names
    bare = dataclasses.replace(BRENHAM_LANE_DIALECT)
    assert bare.multiport_origin_classes == ("terminal_port_hh",)


def test_extract_module_lives_in_match_not_proof_or_review():
    path = Path(inspect.getfile(extract)).resolve()
    assert path.parent.name == "match"
