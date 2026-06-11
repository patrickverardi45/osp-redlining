"""M8.14.c -- tests pinning the symbol/conduit/matchline lane skeleton.

Locks: default-OFF flag + the lane UNWIRED from engine/service (structural);
REVIEW-only taxonomy (no AUTO status can exist); every component carries its
core-law / configured-by architecture record; the corridor filter is
orientation-free and never fabricates a corridor; the dialect contract is
complete for every class the lane can encounter; refusal text for unmodeled
locator classes."""
from __future__ import annotations

import inspect
import os

from truelinev2.config import Settings
from truelinev2.extract.structure_position import (
    BRENHAM_LANE_DIALECT,
    LaneDialect,
)
from truelinev2.match import symbol_conduit_lane as lane
from truelinev2.match.symbol_conduit_lane import (
    COMPONENTS,
    LANE_MODE,
    LANE_NAME,
    STATUSES,
    ComponentReport,
    LaneOutcome,
    corridor_filter,
)


def test_flag_default_off_and_env_controlled(monkeypatch):
    assert Settings.for_proof().symbol_conduit_lane_optin is False
    monkeypatch.delenv("TL2_SYMBOL_CONDUIT_LANE_OPTIN", raising=False)
    assert Settings.from_env().symbol_conduit_lane_optin is False
    monkeypatch.setenv("TL2_SYMBOL_CONDUIT_LANE_OPTIN", "1")
    assert Settings.from_env().symbol_conduit_lane_optin is True


def test_lane_is_unwired_from_engine_and_service():
    import truelinev2.match.engine as engine
    import truelinev2.service as service
    assert "symbol_conduit" not in inspect.getsource(engine)
    assert "symbol_conduit" not in inspect.getsource(service)


def test_review_only_taxonomy_has_no_auto():
    assert LANE_MODE == "REVIEW_ONLY"
    assert all("AUTO" not in s for s in STATUSES)
    out = LaneOutcome(bore_id="x", status=STATUSES[0])
    assert out.review_only is True


def test_distinct_abstain_statuses_exist():
    # the catch-all was split so the census names the REAL blocker
    assert lane.S_STRUCTURE_REQUIRED == "STRUCTURE_IDENTITY_BINDING_REQUIRED"
    assert lane.S_CROSS_SHEET == "CROSS_SHEET_CONTINUATION_REQUIRED"
    assert {lane.S_STRUCTURE_REQUIRED, lane.S_CROSS_SHEET} <= set(STATUSES)
    # all seven are distinct
    assert len(set(STATUSES)) == len(STATUSES) == 7


def test_every_component_reports_law_and_configuration():
    assert set(COMPONENTS) == {"end_identity", "structure_position",
                               "start_identity", "conduit_origin", "tick_path",
                               "matchline_join", "stroke_output", "abstain"}
    for name, meta in COMPONENTS.items():
        assert meta["law"] and meta["configured"], name
    d = ComponentReport("tick_path", "READY").to_dict()
    assert d["law"] and d["configured_by"]


def test_corridor_filter_is_orientation_free():
    horiz = [{"xc": x, "yc": 350.0} for x in (100, 300, 500)]
    off = [{"xc": 300.0, "yc": 250.0}]
    frame_h = [(100.0, 348.0), (500.0, 352.0)]
    kept = corridor_filter(horiz + off, frame_h)
    assert kept == horiz  # the perpendicular leg is excluded
    vert = [{"xc": 350.0, "yc": y} for y in (100, 300, 500)]
    off_v = [{"xc": 250.0, "yc": 300.0}]
    frame_v = [(348.0, 100.0), (352.0, 500.0)]
    assert corridor_filter(vert + off_v, frame_v) == vert


def test_corridor_filter_never_fabricates_a_corridor():
    segs = [{"xc": 1.0, "yc": 1.0}, {"xc": 999.0, "yc": 999.0}]
    assert corridor_filter(segs, []) == segs            # no frame -> no filter
    assert corridor_filter(segs, [(5.0, 5.0)]) == segs  # one point is no axis
    assert corridor_filter(segs, [(5.0, 5.0), (5.0, 5.0)]) == segs  # degenerate


def test_brenham_dialect_contract_is_complete():
    d = BRENHAM_LANE_DIALECT
    assert isinstance(d, LaneDialect)
    classes = {k for k, _ in d.class_keywords}
    assert set(d.structure_layers) >= classes
    # every station_context locator class has context words
    for klass, strategy in d.locator.items():
        assert klass in d.structure_layers
        if strategy == "station_context":
            assert d.context_words.get(klass)
    assert d.conduit_key in d.conduit_layers
    assert d.id_token and d.equation_token and d.matchline_layer


class _StubPlan:
    def words(self, sheet, offset):
        return []

    def line_items(self, sheet, offset):
        return []


def test_unmodeled_locator_class_refuses_typed():
    pos, refusal = lane._locate(_StubPlan(), 1, 0, BRENHAM_LANE_DIALECT,
                                klass="unknown_class")
    assert pos is None
    assert "no locator strategy" in refusal and "typed refusal" in refusal


def test_no_convention_strings_in_the_lane_module():
    src = inspect.getsource(lane)
    for forbidden in ("FLOWER", "NEXTLINK", "MATCHLINE", "AP-", "VACANT",
                      "Brenham", "BRENHAM"):
        # the orchestrator names no layer/class/token literal; everything
        # arrives via the injected LaneDialect (doctrine, beyond the guard)
        assert forbidden not in src, forbidden
