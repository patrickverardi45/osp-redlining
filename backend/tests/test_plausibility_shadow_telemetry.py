"""PT.ACT R3.g — plausibility shadow telemetry tests.

Tests for ``_append_plausibility_shadow_row`` (engineering-side activation
readiness telemetry).  Verifies emission gate, schema stability, retention
cap, error containment, and the critical invariant that the helper NEVER
invokes compute / ranking / selection / scoring / route-evaluator helpers.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pytest

# Make ``backend`` importable when pytest is invoked from the repo root.
_BACKEND_PARENT = Path(__file__).resolve().parents[2]
if str(_BACKEND_PARENT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_PARENT))

# Required for backend.main import (mirrors existing PT.ACT test prelude).
os.environ.setdefault("TRUELINE_JWT_SECRET", "r3g-test-secret")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "r3g-test-auth-secret")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

from backend import main as bm  # noqa: E402


_EXPECTED_ROW_KEYS = {
    "schema_version",
    "decided_at",
    "envelope_emit_id",
    "session_id_hint",
    "input_sha256",
    "group_id",
    "envelope_schema_version",
    "generated_at_step",
    "layers_present",
    "modes_by_layer",
    "shadow_layers",
    "selection_impact_shadow_stack",
    "total_shadow_boost_delta_by_route_id",
    "max_total_shadow_delta",
    "cross_layer_top1_agreement",
    "any_layer_shadow_error",
    "any_would_have_changed_top1",
    "any_shadow_layer_would_have_applied",
    "per_layer_shadow_meta",
}


@pytest.fixture
def shadow_path(tmp_path, monkeypatch):
    """Redirect PLAUSIBILITY_SHADOW_PATH into an isolated tmp path."""
    p = tmp_path / "plausibility_shadow.jsonl"
    monkeypatch.setattr(bm, "PLAUSIBILITY_SHADOW_PATH", p)
    return p


def _make_envelope(
    *,
    shadow_layers: List[str],
    **overrides: Any,
) -> Dict[str, Any]:
    env: Dict[str, Any] = {
        "schema_version": "plausibility-cumulative-2",
        "generated_at_step": "post_ranking_boosts",
        "layers_present": ["PT.1", "PT.2.0"],
        "modes_by_layer": {"PT.1": "off", "PT.2.0": "off"},
        "shadow_layers": list(shadow_layers),
        "selection_impact_shadow_stack": [],
        "total_shadow_boost_delta_by_route_id": {},
        "max_total_shadow_delta": 0.0,
        "cross_layer_top1_agreement": None,
        "any_layer_shadow_error": False,
        "any_would_have_changed_top1": False,
        "any_shadow_layer_would_have_applied": False,
    }
    env.update(overrides)
    return env


def _make_layer_metas(
    *names: str,
    error: Any = None,
) -> List[Tuple[str, Dict[str, Any]]]:
    return [
        (
            n,
            {
                "mode": "shadow",
                "schema_version": "plan-bias-1",
                "shadow": {
                    "computed": True,
                    "would_have_applied": False,
                    "would_have_reordered": False,
                    "top1_unchanged_vs_actual": True,
                    "would_have_top1_route_id": "",
                    "error": error,
                },
            },
        )
        for n in names
    ]


def _read_rows(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


# ─── 1. Emission gate ───────────────────────────────────────────────────────

def test_no_write_when_no_shadow_layers(shadow_path):
    env = _make_envelope(shadow_layers=[])
    bm._append_plausibility_shadow_row(env, [], group_id="g1")
    assert not shadow_path.exists()


def test_no_write_under_live_mode(shadow_path):
    # LIVE never populates shadow_layers; emission must be skipped.
    env = _make_envelope(
        shadow_layers=[],
        modes_by_layer={"PT.1": "live", "PT.2.0": "live"},
    )
    bm._append_plausibility_shadow_row(env, [], group_id="g1")
    assert not shadow_path.exists()


def test_write_pt1_shadow_only(shadow_path):
    env = _make_envelope(shadow_layers=["PT.1"])
    bm._append_plausibility_shadow_row(env, _make_layer_metas("PT.1"), group_id="g1")
    rows = _read_rows(shadow_path)
    assert len(rows) == 1
    assert rows[0]["schema_version"] == "plausibility-shadow-1"
    assert rows[0]["shadow_layers"] == ["PT.1"]
    assert len(rows[0]["per_layer_shadow_meta"]) == 1
    assert rows[0]["per_layer_shadow_meta"][0]["layer"] == "PT.1"


def test_write_pt20_shadow_only(shadow_path):
    env = _make_envelope(shadow_layers=["PT.2.0"])
    bm._append_plausibility_shadow_row(env, _make_layer_metas("PT.2.0"), group_id="g1")
    rows = _read_rows(shadow_path)
    assert len(rows) == 1
    assert rows[0]["shadow_layers"] == ["PT.2.0"]
    assert rows[0]["per_layer_shadow_meta"][0]["layer"] == "PT.2.0"


def test_write_both_layers_shadow(shadow_path):
    env = _make_envelope(shadow_layers=["PT.1", "PT.2.0"])
    bm._append_plausibility_shadow_row(
        env, _make_layer_metas("PT.1", "PT.2.0"), group_id="g1"
    )
    rows = _read_rows(shadow_path)
    assert len(rows) == 1
    assert rows[0]["shadow_layers"] == ["PT.1", "PT.2.0"]
    assert len(rows[0]["per_layer_shadow_meta"]) == 2
    assert {p["layer"] for p in rows[0]["per_layer_shadow_meta"]} == {"PT.1", "PT.2.0"}


# ─── 2. Containment / robustness ────────────────────────────────────────────

def test_helper_never_raises_on_open_failure(shadow_path, monkeypatch):
    """Even if every ``open`` raises, the helper must return silently."""

    def _bad_open(*args, **kwargs):
        raise OSError("disk full simulation")

    monkeypatch.setattr("builtins.open", _bad_open)
    env = _make_envelope(shadow_layers=["PT.1"])
    # No assertion required — pytest fails if this raises.
    bm._append_plausibility_shadow_row(env, _make_layer_metas("PT.1"))


def test_helper_never_raises_on_non_dict_envelope(shadow_path):
    bm._append_plausibility_shadow_row("not-a-dict", _make_layer_metas("PT.1"))  # type: ignore[arg-type]
    bm._append_plausibility_shadow_row(None, _make_layer_metas("PT.1"))  # type: ignore[arg-type]
    assert not shadow_path.exists()


def test_no_envelope_mutation(shadow_path):
    env = _make_envelope(
        shadow_layers=["PT.1", "PT.2.0"],
        total_shadow_boost_delta_by_route_id={"r1": 0.01, "r2": 0.02},
        selection_impact_shadow_stack=[
            {"layer": "PT.1", "pre_layer_top1": "rA", "post_layer_top1": "rB"}
        ],
    )
    snap = json.dumps(env, sort_keys=True, default=str)
    metas = _make_layer_metas("PT.1", "PT.2.0")
    metas_snap = json.dumps(metas, sort_keys=True, default=str)
    bm._append_plausibility_shadow_row(env, metas, group_id="g1")
    assert json.dumps(env, sort_keys=True, default=str) == snap
    assert json.dumps(metas, sort_keys=True, default=str) == metas_snap


# ─── 3. Retention via size-trigger trimming ─────────────────────────────────

def test_retention_cap_triggers_only_when_oversize(shadow_path, monkeypatch):
    monkeypatch.setattr(bm, "PLAUSIBILITY_SHADOW_TRIM_TRIGGER_BYTES", 100)
    monkeypatch.setattr(bm, "PLAUSIBILITY_SHADOW_MAX_ROWS", 3)

    # Pre-seed with 6 dummy rows — file > 100 bytes immediately.
    with open(shadow_path, "w", encoding="utf-8") as fh:
        for i in range(6):
            fh.write(json.dumps({"seed_row": i, "pad": "x" * 32}) + "\n")
    assert os.path.getsize(shadow_path) > 100

    env = _make_envelope(shadow_layers=["PT.1"])
    bm._append_plausibility_shadow_row(env, _make_layer_metas("PT.1"))

    with open(shadow_path, "r", encoding="utf-8") as fh:
        lines = fh.readlines()
    assert len(lines) == 3
    last = json.loads(lines[-1])
    assert last["schema_version"] == "plausibility-shadow-1"


def test_no_trim_when_under_threshold(shadow_path, monkeypatch):
    """When the file is small, the helper must not rewrite (no churn)."""
    monkeypatch.setattr(bm, "PLAUSIBILITY_SHADOW_TRIM_TRIGGER_BYTES", 10 * 1024 * 1024)
    monkeypatch.setattr(bm, "PLAUSIBILITY_SHADOW_MAX_ROWS", 2)

    # Pre-seed 5 rows. File is small, well below the 10MB trigger.
    with open(shadow_path, "w", encoding="utf-8") as fh:
        for i in range(5):
            fh.write(json.dumps({"seed_row": i}) + "\n")
    size_before = os.path.getsize(shadow_path)

    env = _make_envelope(shadow_layers=["PT.1"])
    bm._append_plausibility_shadow_row(env, _make_layer_metas("PT.1"))

    with open(shadow_path, "r", encoding="utf-8") as fh:
        lines = fh.readlines()
    # No trim should have happened — 5 seed rows + 1 new row = 6 lines.
    assert len(lines) == 6
    assert os.path.getsize(shadow_path) > size_before


# ─── 4. Schema stability ────────────────────────────────────────────────────

def test_schema_keys_stable(shadow_path):
    env = _make_envelope(shadow_layers=["PT.1"])
    bm._append_plausibility_shadow_row(env, _make_layer_metas("PT.1"))
    rows = _read_rows(shadow_path)
    assert set(rows[0].keys()) == _EXPECTED_ROW_KEYS


@pytest.mark.parametrize("step", ["post_ranking_boosts", "post_ranking_boosts_fallback"])
def test_both_step_values(shadow_path, step):
    env = _make_envelope(shadow_layers=["PT.1"], generated_at_step=step)
    bm._append_plausibility_shadow_row(env, _make_layer_metas("PT.1"))
    rows = _read_rows(shadow_path)
    assert rows[0]["generated_at_step"] == step


# ─── 5. Identifiers ─────────────────────────────────────────────────────────

def test_identifiers_serialized_when_set(shadow_path, monkeypatch):
    monkeypatch.setitem(bm.STATE, "_session_id_hint", "sess-abc")
    monkeypatch.setitem(bm.STATE, "last_kmz_input_sha256", "sha-123")
    env = _make_envelope(shadow_layers=["PT.1"])
    bm._append_plausibility_shadow_row(
        env, _make_layer_metas("PT.1"), group_id="grp-xyz"
    )
    rows = _read_rows(shadow_path)
    assert rows[0]["session_id_hint"] == "sess-abc"
    assert rows[0]["input_sha256"] == "sha-123"
    assert rows[0]["group_id"] == "grp-xyz"


def test_identifiers_null_when_unset(shadow_path, monkeypatch):
    monkeypatch.setitem(bm.STATE, "_session_id_hint", None)
    monkeypatch.setitem(bm.STATE, "last_kmz_input_sha256", None)
    env = _make_envelope(shadow_layers=["PT.1"])
    bm._append_plausibility_shadow_row(env, _make_layer_metas("PT.1"))
    rows = _read_rows(shadow_path)
    assert rows[0]["session_id_hint"] is None
    assert rows[0]["input_sha256"] is None
    assert rows[0]["group_id"] is None


# ─── 6. Bounded fields ──────────────────────────────────────────────────────

def test_per_layer_error_truncated_to_200(shadow_path):
    long_err = "X" * 5000
    metas = _make_layer_metas("PT.1", error=long_err)
    env = _make_envelope(shadow_layers=["PT.1"])
    bm._append_plausibility_shadow_row(env, metas)
    rows = _read_rows(shadow_path)
    written_err = rows[0]["per_layer_shadow_meta"][0]["error"]
    assert isinstance(written_err, str)
    assert len(written_err) == 200
    assert written_err == "X" * 200


def test_bounded_delta_map_top_32_by_abs_value(shadow_path):
    deltas = {f"r{i}": float(i) for i in range(100)}
    env = _make_envelope(
        shadow_layers=["PT.1"],
        total_shadow_boost_delta_by_route_id=deltas,
    )
    bm._append_plausibility_shadow_row(env, _make_layer_metas("PT.1"))
    rows = _read_rows(shadow_path)
    out = rows[0]["total_shadow_boost_delta_by_route_id"]
    assert len(out) == 32
    # Top 32 by |delta| from {0..99} is {68..99}.
    assert min(float(v) for v in out.values()) == 68.0
    assert max(float(v) for v in out.values()) == 99.0


# ─── 7. INVARIANT: no recomputation ─────────────────────────────────────────

def test_helper_does_not_invoke_compute_or_scoring_helpers(shadow_path, monkeypatch):
    """R3.g critical invariant.

    The telemetry helper MUST be a strict transcriber of finalized observation
    state.  It must never call:
      - compute helpers (PT.1 / PT.2.0 live/shadow computers)
      - ranking helpers
      - selection helpers
      - route evaluators
      - scorers
      - the envelope builder (we are emitting an already-built envelope)

    Strategy: replace each suspect helper with a sentinel that records its
    name when called.  After ``_append_plausibility_shadow_row`` returns,
    the recorder must be empty.
    """
    invoked: List[str] = []

    def _sentinel(name: str):
        def _f(*args: Any, **kwargs: Any) -> Any:
            invoked.append(name)
            return None
        return _f

    forbidden_helpers = [
        # Live compute / apply helpers
        "_apply_print_to_sheet_plausibility_boost",
        "_apply_sheet_adjacency_plausibility_boost",
        "_plan_aware_ranking_boost",
        # Shadow compute helpers (R3.b/c/d/e)
        "_compute_print_to_sheet_shadow",
        "_compute_sheet_adjacency_shadow",
        "_compute_print_to_sheet_boost_live",
        "_compute_sheet_adjacency_boost_live",
        # Envelope builder (already invoked upstream)
        "_build_plausibility_cumulative_meta",
        # Ranking / selection / scoring / route evaluation
        "_find_route_by_id",
        "_anchor_route_subsection",
        "_fallback_rankings_geometry_only",
        "_rank_routes_by_score",
        "_score_route_against_group",
        "_score_route_match",
        "_route_sheet_sequence",
        "_is_ambiguous_print_group",
    ]
    for fname in forbidden_helpers:
        if hasattr(bm, fname):
            monkeypatch.setattr(bm, fname, _sentinel(fname))

    env = _make_envelope(
        shadow_layers=["PT.1", "PT.2.0"],
        total_shadow_boost_delta_by_route_id={"r1": 0.01, "r2": 0.02},
        max_total_shadow_delta=0.02,
        any_shadow_layer_would_have_applied=True,
        selection_impact_shadow_stack=[
            {"layer": "PT.1", "pre_layer_top1": "rA", "post_layer_top1": "rB",
             "changed": True, "would_have_applied": True, "would_have_reordered": True},
            {"layer": "PT.2.0", "pre_layer_top1": "rA", "post_layer_top1": "rA",
             "changed": False, "would_have_applied": False, "would_have_reordered": False},
        ],
    )
    bm._append_plausibility_shadow_row(
        env,
        _make_layer_metas("PT.1", "PT.2.0"),
        group_id="g1",
    )

    assert invoked == [], f"R3.g helper invoked forbidden functions: {invoked}"

    # And verify the row was still written correctly.
    rows = _read_rows(shadow_path)
    assert len(rows) == 1
    assert rows[0]["any_shadow_layer_would_have_applied"] is True


# ─── 8. Canonical-truth deduplication ───────────────────────────────────────

def test_no_actual_top1_route_id_field(shadow_path):
    """R3.g review removed ``actual_top1_route_id`` — canonical top1 truth
    lives in selection_impact_shadow_stack[*].pre_layer_top1.  Do not
    duplicate it as a top-level field on the row.
    """
    env = _make_envelope(shadow_layers=["PT.1"])
    bm._append_plausibility_shadow_row(env, _make_layer_metas("PT.1"))
    rows = _read_rows(shadow_path)
    assert "actual_top1_route_id" not in rows[0]
