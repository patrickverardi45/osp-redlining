"""Item 5 Slice A.1 — authored-path SELECTION evidence (PDF-FREE).

Locks (all additive, evidence-only, default-OFF behind TRUELINE_PATH_SELECTION_EVIDENCE):
  - build_review_reason attaches evidence['path_selection'] ONLY when the flag is on;
  - OFF => no path_selection key, and the rest of the review_reason is byte-identical;
  - the builder surfaces the fusion discriminators (run_color / station_monotonic /
    named_matchline / boc_corridor) that already live in geo.cross_sheet_seam_stitch (log56);
  - it is SPAN-LEVEL (scope_note present) and never promotes a run-wrong child (log66/log58);
  - it carries NO candidates[] / n_acceptable / tiebreaker (deferred to Slice A.2);
  - it COMPOSES with station_roles (run-scope risk stays a separate, un-contradicted key);
  - flipping the flag invalidates the MRQ evidence cache key.

COMMAND (from repo root):
    PYTHONPATH=backend python -m pytest backend/tests/test_path_selection_evidence.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

# match_review_queue imports vendored top-level packages -> needs backend/app/core on path.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "core"))

from app.core import mrq_evidence_cache
from app.core.match_review_queue import (
    PATH_SELECTION_FLAG,
    PATH_SELECTION_SCHEMA_VERSION,
    build_review_reason,
    path_selection_evidence,
)

_SCOPE = "does not prove standalone run completeness"


# ── geo fixtures (synthetic; PDF-free) ───────────────────────────────────────────────
def _log56_geo():
    """log56-shaped cross-sheet seam fusion win: the authored_path_selector discriminators
    are stashed on the s17 segment (the data A.1 surfaces); s21 abstains."""
    return {
        "geometry_status": "MATCHLINE_FRAME_RESOLVED",
        "frame": {"multi_sheet": True},
        "matchline_resolution": {
            "status": "MATCHLINE_FRAME_RESOLVED", "class": "cross_sheet_equation_reset",
            "sheets": [17, 21], "canonical_span": "0+00->2+76", "boc_ft": 11,
            "seam": {"home_sta": "1+61", "neighbor_sta": "1+59", "neighbor_sheet": 21},
        },
        "cross_sheet_seam_stitch": {
            "resolved": True, "run_id": "bore_log56",
            "reason": "cross_sheet_seam_path_partial_s17_only",
            "segments": [
                {"sheet": 17, "status": "drawn", "reason": None,
                 "discriminators": {"named_matchline_bound": True, "run_color": [0.9, 0.0, 0.9],
                                    "candidate_vertices": 6, "station_monotonic": True,
                                    "boc_corridor_ft": 11},
                 "evidence": {"run_color": [0.9, 0.0, 0.9], "named_seam_sta": "1+61",
                              "path_vertices": 6, "boc_ft": 11}},
                {"sheet": 21, "status": "abstained_requires_path_evidence",
                 "reason": "s21_vectors_disconnected_no_authored_path"},
            ],
        },
    }


def _log66_geo():
    """log66-shaped single-sheet station-frame card: NOT fusion-selected (no run_color /
    station_monotonic). Run-scope risk is owned separately by station_roles."""
    return {
        "geometry_status": "STATION_FRAME_RESOLVED",
        "frame": {"multi_sheet": False},
        "matchline_resolution": {"status": "STATION_FRAME_RESOLVED", "class": "STATION_EQUATION_RESET",
                                 "sheets": [10], "canonical_span": "0+00->0+55", "boc_ft": 10},
    }


# ── flag gating / parity ─────────────────────────────────────────────────────────────
def test_off_no_path_selection_key(monkeypatch):
    monkeypatch.delenv(PATH_SELECTION_FLAG, raising=False)
    monkeypatch.delenv("TRUELINE_STATION_ROLE_EVIDENCE", raising=False)
    rr = build_review_reason(_log56_geo())
    assert rr is not None and "path_selection" not in rr["evidence"]


def test_off_on_parity_except_added_key(monkeypatch):
    monkeypatch.delenv("TRUELINE_STATION_ROLE_EVIDENCE", raising=False)
    geo = _log56_geo()
    monkeypatch.delenv(PATH_SELECTION_FLAG, raising=False)
    off = build_review_reason(geo)
    monkeypatch.setenv(PATH_SELECTION_FLAG, "1")
    on = build_review_reason(geo)
    assert "path_selection" not in off["evidence"]
    assert "path_selection" in on["evidence"]
    # everything else byte-identical: no draw/abstain/discriminator/code/missing change.
    assert off["code"] == on["code"]
    assert off["missing"] == on["missing"]
    assert off["discriminators"] == on["discriminators"]
    assert {k: v for k, v in on["evidence"].items() if k != "path_selection"} == off["evidence"]


# ── ON: schema + scope_note + fusion discriminators ──────────────────────────────────
def test_on_schema_and_scope_note(monkeypatch):
    monkeypatch.setenv(PATH_SELECTION_FLAG, "1")
    ps = build_review_reason(_log56_geo())["evidence"]["path_selection"]
    assert ps["schema_version"] == PATH_SELECTION_SCHEMA_VERSION
    assert _SCOPE in ps["scope_note"]


def test_on_log56_surfaces_run_color_and_station_monotonic(monkeypatch):
    monkeypatch.setenv(PATH_SELECTION_FLAG, "1")
    ps = build_review_reason(_log56_geo())["evidence"]["path_selection"]
    assert ps["discriminators"]["run_color"] == [0.9, 0.0, 0.9]
    assert ps["discriminators"]["station_monotonic"] is True
    assert ps["discriminators"]["named_matchline"] is True
    assert ps["discriminators"]["boc_corridor_ft"] == 11
    assert ps["winner"]["sheets"] == [17, 21]
    assert ps["winner"]["station_signature"] == "0+00->2+76"
    assert "sheet 21" in ps["abstain_reason"]
    # NOT surfaced in A.1 (deferred to A.2)
    assert "candidates" not in ps and "n_acceptable" not in ps and "tiebreaker" not in ps


# ── log66/log58: span-level, no promotion, run-scope risk stays separate ──────────────
def test_log66_span_level_no_fusion_no_promotion(monkeypatch):
    monkeypatch.setenv(PATH_SELECTION_FLAG, "1")
    ps = build_review_reason(_log66_geo())["evidence"]["path_selection"]
    assert ps["discriminators"]["run_color"] is None          # not fusion-selected
    assert ps["discriminators"]["station_monotonic"] is None
    assert ps["discriminators"]["named_matchline"] is True     # from matchline_resolution status
    assert _SCOPE in ps["scope_note"]
    # carries NO draw/promotion fields — pure evidence keys only.
    assert set(ps) <= {"schema_version", "winner", "discriminators",
                       "decision_reason", "abstain_reason", "scope_note"}


def test_log66_path_selection_composes_with_station_roles(monkeypatch):
    # both evidence flags ON: path_selection + station_roles are SEPARATE, independent keys;
    # the run-scope risk is owned by station_roles and NOT contradicted by path_selection.
    monkeypatch.setenv(PATH_SELECTION_FLAG, "1")
    monkeypatch.setenv("TRUELINE_STATION_ROLE_EVIDENCE", "1")
    geo = _log66_geo()
    geo["frame"] = {"multi_sheet": False, "chainage_start_ft": 0.0, "chainage_end_ft": 55.0,
                    "eqs_used": ["45+33=0+00"]}
    ev = build_review_reason(geo)["evidence"]
    assert "path_selection" in ev and "station_roles" in ev
    assert ev["station_roles"]["local_reset_continuation_risk"] is True
    assert _SCOPE in ev["path_selection"]["scope_note"]


# ── builder unit ─────────────────────────────────────────────────────────────────────
def test_builder_none_safe():
    assert path_selection_evidence(None) is None
    assert path_selection_evidence({}) is None
    assert path_selection_evidence({"frame": {}}) is None


def test_builder_matchline_only():
    ps = path_selection_evidence(_log66_geo())
    assert ps is not None
    assert ps["winner"]["station_signature"] == "0+00->0+55"
    assert ps["discriminators"]["named_matchline"] is True
    assert ps["discriminators"]["run_color"] is None


# ── cache key invalidation (the _OUTPUT_FLAGS addition) ──────────────────────────────
def test_cache_key_changes_on_flag_flip(monkeypatch, tmp_path):
    assert PATH_SELECTION_FLAG in mrq_evidence_cache._OUTPUT_FLAGS
    rows = [{"station": "0+00", "source_file": "x.xlsx"}]
    pdf = str(tmp_path / "plan.pdf")
    Path(pdf).write_bytes(b"%PDF-1.4\n")
    monkeypatch.setenv(PATH_SELECTION_FLAG, "0")
    k_off = mrq_evidence_cache.cache_key(rows, pdf)
    monkeypatch.setenv(PATH_SELECTION_FLAG, "1")
    k_on = mrq_evidence_cache.cache_key(rows, pdf)
    assert k_off != k_on
