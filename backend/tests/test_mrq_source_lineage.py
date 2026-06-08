"""Slice 1a — source-lineage evidence: backend unit + wiring tests.

Locks the additive, EVIDENCE-ONLY source-lineage projection
(``source_lineage.source_lineage_evidence``) and its default-OFF wiring into the
Match Review queue (``match_review_queue._build_row`` + ``assemble_placement_proof``)
and the evidence cache key (``mrq_evidence_cache``).

Default-OFF => key absent => byte-identical payload. NEVER asserts any
draw / tiering / placement / closeout change — there is none. Imports via
``app.core`` so module identity matches what the cache's lazy import uses.
"""
from __future__ import annotations

import copy
import json

from app.core import match_review_queue as mrq
from app.core import mrq_evidence_cache as cache
from app.core import source_lineage as slmod
from app.core.source_lineage import (
    SOURCE_LINEAGE_FLAG,
    SOURCE_LINEAGE_SCHEMA_VERSION,
    load_lineage,
    source_lineage_evidence,
)

_INDEX = load_lineage()  # vendored owner-reviewed ledger


def _entry(sf):
    return {"source_file": sf, "group_id": (sf or "x") + ":g", "selected_route_id": "r1"}


# ── ledger loads + projects (pure helper) ────────────────────────────────────
def test_ledger_loads_32_children():
    assert len(_INDEX) == 32
    for cid in ("bore_log56", "bore_log58", "bore_log66", "bore_log67"):
        assert cid in _INDEX


def test_log56_daily_bundle_standalone_with_label():
    sl = source_lineage_evidence("bore_log56.xlsx", _INDEX)
    assert sl is not None
    assert sl["schema_version"] == SOURCE_LINEAGE_SCHEMA_VERSION
    assert sl["source_log_id"] == "bore_log22"
    assert sl["parent_kind"] == "daily_bundle"
    assert sl["review_status"] == "locked"
    assert sl["safe_standalone"] == "true"
    assert sl["closeout_scope"] == "child"
    assert sl["parent_ownership_label"] == "child segment of source log22"
    assert sl["segment_draw_scope"]["drawable"] is True


def test_log58_and_log66_continuous_run_legs_drawable():
    for cid, parent in (("bore_log58", "bore_log24"), ("bore_log66", "bore_log33")):
        sl = source_lineage_evidence(cid + ".xlsx", _INDEX)
        assert sl["source_log_id"] == parent
        assert sl["parent_kind"] == "continuous_run"
        assert sl["safe_standalone"] == "false"
        assert sl["closeout_scope"] == "parent_run"
        assert sl["segment_draw_scope"]["drawable"] is True  # geometry never hidden


def test_uncertain_family_log59_manual_review():
    # Uncertain/manual-review coverage moved off log67 (ratified daily_bundle, Family 34)
    # to Family 26's log59, which remains genuinely manual_review_pending.
    sl = source_lineage_evidence("bore_log59.xlsx", _INDEX)
    assert sl["source_log_id"] == "bore_log26"
    assert sl["parent_kind"] == "uncertain"
    assert sl["review_status"] == "manual_review_pending"
    assert sl["safe_standalone"] == "uncertain"
    assert sl["closeout_scope"] == "hold"


def test_log67_log68_daily_bundle_standalone():
    # Family 34 ratified daily_bundle 2026-06-07: Ellen St / Eledra St standalone child bores.
    for cid in ("bore_log67", "bore_log68"):
        sl = source_lineage_evidence(cid + ".xlsx", _INDEX)
        assert sl["source_log_id"] == "bore_log34"
        assert sl["parent_kind"] == "daily_bundle"
        assert sl["review_status"] == "locked"
        assert sl["safe_standalone"] == "true"
        assert sl["closeout_scope"] == "child"
        assert sl["parent_ownership_label"] == "child segment of source log34"
        assert sl["segment_draw_scope"]["drawable"] is True


def test_log71_log72_continuous_run_legs_with_run_order():
    # Family 40 ratified continuous_run 2026-06-07: one Lawndale run, legs 71 then 72.
    for cid in ("bore_log71", "bore_log72"):
        sl = source_lineage_evidence(cid + ".xlsx", _INDEX)
        assert sl["source_log_id"] == "bore_log40"
        assert sl["parent_kind"] == "continuous_run"
        assert sl["review_status"] == "locked"
        assert sl["safe_standalone"] == "false"
        assert sl["closeout_scope"] == "parent_run"
        assert sl["segment_draw_scope"]["drawable"] is True  # geometry never hidden
    # run_order is ledger-only (not projected); lock the owner-ratified order + preserved 55' gap.
    with open(slmod._DEFAULT_LINEAGE_PATH, encoding="utf-8") as fh:
        kids = {c["child_segment_id"]: c
                for c in json.load(fh)["source_logs"]["bore_log40"]["children"]}
    assert kids["bore_log71"]["run_order"] == 1
    assert kids["bore_log72"]["run_order"] == 2
    assert kids["bore_log71"]["corrected_station_span"] is None
    assert kids["bore_log72"]["corrected_station_span"] is None


def test_unknown_and_invalid_ledger_returns_none():
    assert source_lineage_evidence("bore_log999.xlsx", _INDEX) is None
    assert source_lineage_evidence(None, _INDEX) is None
    assert source_lineage_evidence("bore_log56.xlsx", {}) is None
    assert load_lineage(r"C:\__nope__\does_not_exist.json") == {}
    assert source_lineage_evidence("bore_log56.xlsx", load_lineage(r"C:\__nope__.json")) is None


def test_helper_is_pure_and_returns_a_copy():
    before = copy.deepcopy(_INDEX)
    out = source_lineage_evidence("bore_log56.xlsx", _INDEX)
    assert _INDEX == before  # index not mutated
    out["parent_kind"] = "MUTATED"
    assert _INDEX["bore_log56"]["parent_kind"] == "daily_bundle"  # cache uncorrupted


def test_block_has_no_draw_or_geometry_keys():
    sl = source_lineage_evidence("bore_log56.xlsx", _INDEX)
    for k in ("artifact_name", "drawn", "coords", "coordinates", "geometry",
              "segments", "polyline", "path_xy", "lat", "lon", "render"):
        assert k not in sl
    assert set(sl["segment_draw_scope"].keys()) <= {"drawable", "scope_note"}


# ── _build_row wiring: default-OFF parity / flag-ON additive-only ─────────────
def test_build_row_flag_off_no_key(monkeypatch):
    monkeypatch.delenv(SOURCE_LINEAGE_FLAG, raising=False)
    row = mrq._build_row(_entry("bore_log56.xlsx"), "abstained")
    assert "source_lineage" not in row


def test_build_row_flag_on_is_additive_only(monkeypatch):
    e = _entry("bore_log56.xlsx")
    monkeypatch.delenv(SOURCE_LINEAGE_FLAG, raising=False)
    off = mrq._build_row(e, "abstained")
    monkeypatch.setenv(SOURCE_LINEAGE_FLAG, "1")
    on = mrq._build_row(e, "abstained")
    assert "source_lineage" not in off
    assert on["source_lineage"]["source_log_id"] == "bore_log22"
    # every pre-existing row field byte-identical (no draw/tier/placement/closeout change)
    on_wo = {k: v for k, v in on.items() if k != "source_lineage"}
    assert on_wo == off


def test_build_row_flag_on_unknown_log_no_key(monkeypatch):
    monkeypatch.setenv(SOURCE_LINEAGE_FLAG, "1")
    row = mrq._build_row(_entry("bore_log999.xlsx"), "abstained")
    assert "source_lineage" not in row


def test_missing_ledger_index_no_attach(monkeypatch):
    # simulate a missing/empty vendored ledger -> behaves exactly like no evidence
    monkeypatch.setenv(SOURCE_LINEAGE_FLAG, "1")
    monkeypatch.setattr(mrq, "_SOURCE_LINEAGE_INDEX", {})
    row = mrq._build_row(_entry("bore_log56.xlsx"), "abstained")
    assert "source_lineage" not in row


# ── placement-proof wiring (reaches DRAWN cards like log56) ───────────────────
def test_placement_proof_flag_on_attaches_to_log56(monkeypatch):
    monkeypatch.setenv(SOURCE_LINEAGE_FLAG, "1")
    diag = [{"source_file": "bore_log56.xlsx", "group_id": "g"}]
    proof = mrq.assemble_placement_proof(diag)
    row = next(r for r in proof["rows"] if r.get("source_file") == "bore_log56.xlsx")
    assert row["source_lineage"]["parent_kind"] == "daily_bundle"
    assert row["source_lineage"]["parent_ownership_label"] == "child segment of source log22"


def test_placement_proof_flag_off_parity(monkeypatch):
    monkeypatch.delenv(SOURCE_LINEAGE_FLAG, raising=False)
    diag = [{"source_file": "bore_log56.xlsx", "group_id": "g"}]
    proof = mrq.assemble_placement_proof(diag)
    row = next(r for r in proof["rows"] if r.get("source_file") == "bore_log56.xlsx")
    assert "source_lineage" not in row


# ── evidence-cache key invalidation ──────────────────────────────────────────
def test_flag_is_registered_in_output_flags():
    assert SOURCE_LINEAGE_FLAG in cache._OUTPUT_FLAGS


def test_cache_key_changes_on_flag_flip(monkeypatch, tmp_path):
    pdf = str(tmp_path / "plan.pdf")
    open(pdf, "wb").close()
    rows = [{"source_file": "bore_log56.xlsx"}]
    monkeypatch.delenv(SOURCE_LINEAGE_FLAG, raising=False)
    k_off = cache.cache_key(rows, pdf)
    monkeypatch.setenv(SOURCE_LINEAGE_FLAG, "1")
    k_on = cache.cache_key(rows, pdf)
    assert k_off != k_on


def test_cache_key_changes_when_ledger_changes_while_on(monkeypatch, tmp_path):
    pdf = str(tmp_path / "plan.pdf")
    open(pdf, "wb").close()
    ledger = tmp_path / "lin.json"
    ledger.write_text('{"x": 1}', encoding="utf-8")
    monkeypatch.setattr(slmod, "_DEFAULT_LINEAGE_PATH", str(ledger))
    monkeypatch.setenv(SOURCE_LINEAGE_FLAG, "1")
    rows = [{"source_file": "bore_log56.xlsx"}]
    k1 = cache.cache_key(rows, pdf)
    ledger.write_text('{"x": 1, "y": 2, "z": 3}', encoding="utf-8")  # size changes
    k2 = cache.cache_key(rows, pdf)
    assert k1 != k2
