"""Slice 1a.1 — source_lineage attached onto pdf_first_evidence cards: backend tests.

Locks the additive, EVIDENCE-ONLY card-level attach (`source_lineage.attach_card_lineage`
+ `source_lineage_for_log_id`) and its default-OFF wiring into
`pdf_first_adapter._envelope_from_result`. Imports via `app.core` so module identity
matches the adapter's local import (the flag-gating spy relies on this). NEVER asserts
any draw / tier / status / render_target / geo change — there is none.
"""
from __future__ import annotations

import copy
import sys
import types

import pytest

from app.core import pdf_first_adapter
from app.core import source_lineage as slmod
from app.core.source_lineage import (
    SOURCE_LINEAGE_FLAG,
    SOURCE_LINEAGE_SCHEMA_VERSION,
    attach_card_lineage,
    index,
    source_lineage_for_log_id,
)

_IDX = index()  # cached vendored ledger index


# ── mapping log56 -> bore_log56 (and edge cases) ─────────────────────────────
def test_index_loads_32_and_maps():
    assert len(_IDX) == 32
    assert source_lineage_for_log_id(["log56"], _IDX)["source_log_id"] == "bore_log22"
    assert source_lineage_for_log_id(["bore_log56"], _IDX)["source_log_id"] == "bore_log22"  # tolerate bore_
    assert source_lineage_for_log_id(["log56", "log56"], _IDX)["source_log_id"] == "bore_log22"  # dup same child
    assert source_lineage_for_log_id(["log999"], _IDX) is None    # unknown
    assert source_lineage_for_log_id([], _IDX) is None
    assert source_lineage_for_log_id(None, _IDX) is None
    assert source_lineage_for_log_id(["log56", "log58"], _IDX) is None  # ambiguous multi-child group
    assert source_lineage_for_log_id(["log56"], {}) is None       # empty index


def _envelope():
    # synthetic pdf_first_evidence envelope with non-lineage fields present, to prove parity
    return {
        "schema_version": "pdf-first-evidence-1",
        "render_target": "evidence_card",
        "status": "OK",
        "counts_by_surface": {"placements": 1, "review_items": 2, "fail_safe": 1},
        "placements": [
            {"log_ids": ["log56"], "tier": "AUTO_SELECT",
             "station_range": {"start": "0+00", "end": "2+76"},
             "render_artifact_ref": "bore_log56_s2.png",
             "geo": {"geometry_status": "AP_ANCHORED"}},
        ],
        "review_items": [
            {"log_ids": ["log58"], "tier": "SHARED_SEGMENT_REVIEW", "render_artifact_ref": "x.png"},
            {"log_ids": ["log66"], "tier": "SHARED_SEGMENT_REVIEW"},
        ],
        "fail_safe": [
            {"log_ids": ["log67"], "tier": "FAIL_SAFE"},
        ],
    }


# ── attach_card_lineage: card-content assertions ─────────────────────────────
def test_attach_log56_daily_bundle_standalone_with_label():
    env = _envelope()
    attach_card_lineage(env, _IDX)
    sl = env["placements"][0]["source_lineage"]
    assert sl["schema_version"] == SOURCE_LINEAGE_SCHEMA_VERSION
    assert sl["source_log_id"] == "bore_log22"
    assert sl["parent_kind"] == "daily_bundle"
    assert sl["safe_standalone"] == "true"
    assert sl["closeout_scope"] == "child"
    assert sl["parent_ownership_label"] == "child segment of source log22"


def test_attach_log58_log66_continuous_run_drawable():
    env = _envelope()
    attach_card_lineage(env, _IDX)
    by = {c["log_ids"][0]: c["source_lineage"] for c in env["review_items"]}
    for lid, parent in (("log58", "bore_log24"), ("log66", "bore_log33")):
        assert by[lid]["source_log_id"] == parent
        assert by[lid]["parent_kind"] == "continuous_run"
        assert by[lid]["safe_standalone"] == "false"
        assert by[lid]["closeout_scope"] == "parent_run"
        assert by[lid]["segment_draw_scope"]["drawable"] is True  # geometry never hidden


def test_attach_log67_uncertain_manual_review():
    env = _envelope()
    attach_card_lineage(env, _IDX)
    sl = env["fail_safe"][0]["source_lineage"]
    assert sl["parent_kind"] == "uncertain"
    assert sl["review_status"] == "manual_review_pending"
    assert sl["closeout_scope"] == "hold"


def test_attach_is_additive_only_no_other_card_field_changes():
    base = _envelope()
    after = copy.deepcopy(base)
    attach_card_lineage(after, _IDX)
    # every pre-existing card field byte-identical; ONLY source_lineage added
    for sect in ("placements", "review_items", "fail_safe"):
        for b, a in zip(base[sect], after[sect]):
            a_wo = {k: v for k, v in a.items() if k != "source_lineage"}
            assert a_wo == b  # tier / station_range / render_artifact_ref / geo unchanged
    # top-level non-card fields untouched
    for k in ("schema_version", "render_target", "status", "counts_by_surface"):
        assert after[k] == base[k]


def test_attach_does_not_mutate_index_records():
    env = _envelope()
    before = copy.deepcopy(_IDX)
    attach_card_lineage(env, _IDX)
    env["placements"][0]["source_lineage"]["parent_kind"] = "MUTATED"
    assert _IDX == before  # cached index uncorrupted
    assert _IDX["bore_log56"]["parent_kind"] == "daily_bundle"


def test_attach_unknown_card_gets_no_key():
    env = {"placements": [{"log_ids": ["log999"], "tier": "AUTO_SELECT"}],
           "review_items": [], "fail_safe": []}
    attach_card_lineage(env, _IDX)
    assert "source_lineage" not in env["placements"][0]


# ── _envelope_from_result flag-gating (adapter wiring) ───────────────────────
class _FakeResult:
    selected_segments: list = []
    review_items: list = []
    fail_safe_items: list = []
    render_artifacts: list = []


@pytest.fixture
def _stub_engine(monkeypatch):
    """Stub the scratch-tree engine import so `_envelope_from_result` runs in the test
    venv (`redline_pdf_first` isn't installed here; with empty result lists its card
    builders are never actually called — only the top-of-function import must resolve)."""
    ec = types.ModuleType("redline_pdf_first.render.evidence_card")
    ec.build_failsafe_card = lambda fs: {}
    ec.build_segment_card = lambda seg: {}
    render = types.ModuleType("redline_pdf_first.render")
    render.evidence_card = ec
    root = types.ModuleType("redline_pdf_first")
    root.render = render
    monkeypatch.setitem(sys.modules, "redline_pdf_first", root)
    monkeypatch.setitem(sys.modules, "redline_pdf_first.render", render)
    monkeypatch.setitem(sys.modules, "redline_pdf_first.render.evidence_card", ec)


def test_envelope_from_result_flag_off_does_not_attach(monkeypatch, _stub_engine):
    calls = []
    monkeypatch.setattr(slmod, "attach_card_lineage", lambda env, idx: calls.append(1) or env)
    monkeypatch.delenv(SOURCE_LINEAGE_FLAG, raising=False)
    env = pdf_first_adapter._envelope_from_result(_FakeResult())
    assert calls == []                      # OFF: helper never invoked
    assert "source_lineage" not in env
    assert env["placements"] == [] and env["review_items"] == [] and env["fail_safe"] == []


def test_envelope_from_result_flag_on_calls_attach(monkeypatch, _stub_engine):
    calls = []
    monkeypatch.setattr(slmod, "attach_card_lineage", lambda env, idx: calls.append(1) or env)
    monkeypatch.setenv(SOURCE_LINEAGE_FLAG, "1")
    pdf_first_adapter._envelope_from_result(_FakeResult())
    assert calls == [1]                     # ON: helper invoked exactly once


# ── cache: flag registered so a flip invalidates the pdf_first_evidence cache ─
def test_flag_registered_in_output_flags():
    from app.core import mrq_evidence_cache as cache
    assert SOURCE_LINEAGE_FLAG in cache._OUTPUT_FLAGS
