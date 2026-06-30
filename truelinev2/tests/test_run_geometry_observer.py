"""Adversarial proof for the read-only run-geometry OBSERVER (the two signals G4 named as missing).

This closes the G4 geometry gate's documented blind spot AGAINST THE ADVERSARIAL HARNESS only: it proves the
observer computes ``BRANCH_PATH_UNIQUENESS`` + ``ENDPOINT_TO_RUN_COORDINATE_TIGHTNESS`` and that, with them,
the wrong-branch FORK (which the current-data oracle in ``test_g4_geometry_validation.py`` passes as a
documented false positive) is REJECTED, while the clean positive still passes and every other negative stays
rejected. It does NOT prove real cold-package generalization — that needs real/fresh packages + a real
source-bound endpoint COORDINATE (termini are station-only today); see the observer module's honest-scope
notes. Nothing here promotes anything: no AUTO, no _cap_review, no placement/status/render change.
"""
from __future__ import annotations

import ast
import copy
import os
import re
from pathlib import Path

from truelinev2.extract.generic_geometry import GenericGeometryDialect
from truelinev2.extract.run_geometry_observer import (
    BRANCH_FORKED,
    BRANCH_NO_SPANNING_RUN,
    BRANCH_PATH_UNIQUENESS,
    BRANCH_RIVAL_RUNS,
    BRANCH_UNIQUE,
    ENDPOINT_TO_RUN_COORDINATE_TIGHTNESS,
    TIGHTNESS_LOOSE,
    TIGHTNESS_TIGHT,
    TIGHTNESS_UNMEASURABLE,
    observe_dialect_run,
    observe_run_geometry,
)
from truelinev2.harness.g4_geometry_fixtures import build_g4_geometry_fixtures, load_g4_geometry_fixtures
from truelinev2.harness.synth import plan_offset_run_with_notes
from truelinev2.ingest.pdf import PlanPdf

_OBSERVER = Path(__file__).resolve().parents[1] / "extract" / "run_geometry_observer.py"
_BORE_START_FT, _BORE_END_FT = 1175.0, 1325.0     # 11+75 .. 13+25 (the synthetic bore span)


# ----------------------------------------------------------------------------------------------------------- #
# Unit layer: the observer's verdicts on plain segment lists (no PDF) — the algorithm locked directly.
# ----------------------------------------------------------------------------------------------------------- #
def _seg(ax, ay, bx, by):
    return {"a": (float(ax), float(ay)), "b": (float(bx), float(by))}


def test_clean_chain_is_unique_and_tight():
    o = observe_run_geometry([_seg(295, 384, 445, 384)], 295.0, 445.0)
    assert o.branch_uniqueness == BRANCH_UNIQUE
    assert o.endpoint_tightness == TIGHTNESS_TIGHT
    assert o.would_reject is False
    assert o.reject_signals == ()


def test_fork_is_rejected_by_branch_uniqueness_only():
    """A degree-3 junction -> FORKED. Tightness is fine (both branch ends sit at the bound stations), so ONLY
    BRANCH_PATH_UNIQUENESS rejects it — exactly the signal nothing else had."""
    fork = [_seg(295, 384, 370, 384), _seg(370, 384, 445, 376), _seg(370, 384, 445, 392)]
    o = observe_run_geometry(fork, 295.0, 445.0)
    assert o.branch_uniqueness == BRANCH_FORKED
    assert o.endpoint_tightness == TIGHTNESS_TIGHT
    assert o.detail["junction_count"] == 1
    assert o.would_reject is True
    assert o.reject_signals == (BRANCH_PATH_UNIQUENESS,)


def test_parallel_runs_are_rival_runs():
    o = observe_run_geometry([_seg(295, 380, 445, 380), _seg(295, 392, 445, 392)], 295.0, 445.0)
    assert o.branch_uniqueness == BRANCH_RIVAL_RUNS
    assert o.detail["spanning_components"] == 2
    assert BRANCH_PATH_UNIQUENESS in o.reject_signals


def test_broken_specks_have_no_spanning_run():
    specks = [_seg(300, 384, 308, 384), _seg(360, 384, 368, 384), _seg(420, 384, 428, 384)]
    o = observe_run_geometry(specks, 295.0, 445.0)
    assert o.branch_uniqueness == BRANCH_NO_SPANNING_RUN
    assert o.would_reject is True


def test_overshoot_is_rejected_by_tightness_only():
    o = observe_run_geometry([_seg(200, 384, 540, 384)], 295.0, 445.0)
    assert o.branch_uniqueness == BRANCH_UNIQUE
    assert o.endpoint_tightness == TIGHTNESS_LOOSE
    assert o.reject_signals == (ENDPOINT_TO_RUN_COORDINATE_TIGHTNESS,)


def test_undershoot_is_loose():
    o = observe_run_geometry([_seg(325, 384, 415, 384)], 295.0, 445.0)
    assert o.branch_uniqueness == BRANCH_UNIQUE
    assert o.endpoint_tightness == TIGHTNESS_LOOSE
    assert o.detail["start_gap"] >= 15.0 and o.detail["end_gap"] >= 15.0


def test_offset_run_is_unique_but_loose():
    """A single clean run shifted off the bound endpoints: branch-uniqueness PASSES (one simple chain), so a
    branch-only gate would accept it — ONLY ENDPOINT_TO_RUN_COORDINATE_TIGHTNESS rejects it. Proves tightness
    is independently necessary, not redundant with branch-uniqueness."""
    o = observe_run_geometry([_seg(315, 384, 465, 384)], 295.0, 445.0)
    assert o.branch_uniqueness == BRANCH_UNIQUE
    assert o.endpoint_tightness == TIGHTNESS_LOOSE
    assert o.reject_signals == (ENDPOINT_TO_RUN_COORDINATE_TIGHTNESS,)


def test_unbound_endpoint_is_unmeasurable_not_guessed():
    o = observe_run_geometry([_seg(295, 384, 445, 384)], None, 445.0)
    assert o.endpoint_tightness == TIGHTNESS_UNMEASURABLE      # never invents a position for an unbound endpoint
    assert o.would_reject is True


def test_observer_is_deterministic():
    fork = [_seg(295, 384, 370, 384), _seg(370, 384, 445, 376), _seg(370, 384, 445, 392)]
    assert observe_run_geometry(fork, 295.0, 445.0) == observe_run_geometry(fork, 295.0, 445.0)


# ----------------------------------------------------------------------------------------------------------- #
# Integration layer: the observer over the REAL synthetic G4 plans (through the generic dialect's own
# read-only band-segment exposure). Same data the placement lane sees; no placement is run or changed.
# ----------------------------------------------------------------------------------------------------------- #
def _observe_plan(plan_path, *, sheet=1):
    plan = PlanPdf(str(plan_path))
    dialect = GenericGeometryDialect()
    dialect.extract_callouts(plan, sheet, 0)                  # read-only: populates axis + band segments
    return dialect, observe_dialect_run(dialect, sheet, _BORE_START_FT, _BORE_END_FT)


def _by_id(tmp_path):
    root = tmp_path / "g4geo"
    build_g4_geometry_fixtures(root)
    out = {}
    for fx in load_g4_geometry_fixtures(root):
        _d, obs = _observe_plan(fx.plan_path)
        out[fx.fixture_id] = (fx, obs)
    return out


def test_clean_positive_passes_the_observer(tmp_path):
    fx, obs = _by_id(tmp_path)["g4geo-01-perfect-line"]
    assert obs is not None
    assert obs.branch_uniqueness == BRANCH_UNIQUE
    assert obs.endpoint_tightness == TIGHTNESS_TIGHT
    assert obs.would_reject is False


def test_fork_flips_from_oracle_pass_to_observer_reject(tmp_path):
    """THE FLIP: g4geo-06 is recorded as a current-data oracle PASS (a documented false positive in
    test_g4_geometry_validation.py); the observer now REJECTS it via BRANCH_PATH_UNIQUENESS."""
    fx, obs = _by_id(tmp_path)["g4geo-06-wrong-branch-fork"]
    assert fx.oracle_would_pass is True                       # the current-data oracle passed it (the gap)
    assert obs.branch_uniqueness == BRANCH_FORKED
    assert obs.would_reject is True
    assert obs.reject_signals == (BRANCH_PATH_UNIQUENESS,)    # the previously-missing signal does the work


def test_every_geometry_negative_is_rejected_by_the_observer_or_an_existing_signal(tmp_path):
    """The fork + all single-sheet negatives are rejected by the observer; the cross-sheet negative stays
    rejected by the EXISTING cross-sheet signal (the observer is single-sheet by design and does not claim it
    clean). The clean positive is the only case the observer-augmented gate passes."""
    results = _by_id(tmp_path)
    observer_rejects = {
        "g4geo-02-parallel-rival": BRANCH_PATH_UNIQUENESS,
        "g4geo-03-broken-fragments": BRANCH_PATH_UNIQUENESS,
        "g4geo-04-line-overshoots": ENDPOINT_TO_RUN_COORDINATE_TIGHTNESS,
        "g4geo-05-line-undershoots": ENDPOINT_TO_RUN_COORDINATE_TIGHTNESS,
        "g4geo-06-wrong-branch-fork": BRANCH_PATH_UNIQUENESS,
        "g4geo-07-baseline-trap": ENDPOINT_TO_RUN_COORDINATE_TIGHTNESS,
    }
    for fid, signal in observer_rejects.items():
        fx, obs = results[fid]
        assert obs.would_reject is True, fid
        assert signal in obs.reject_signals, (fid, obs.reject_signals)

    # the multi-sheet negative: the observer sees only the (clean) single-sheet leg and does NOT reject it;
    # it stays out by the existing cross-sheet signal (recorded oracle_would_pass=False).
    ms_fx, ms_obs = results["g4geo-08-multisheet-cross-sheet-partial"]
    assert ms_obs.would_reject is False                      # observer is silent on a clean single sheet
    assert ms_fx.oracle_would_pass is False                 # existing cross-sheet signal already rejects it


def test_observer_augmented_gate_passes_only_the_true_positive(tmp_path):
    """The observer-augmented decision (current-data oracle AND the observer) passes ONLY the genuine clean
    positive. Every ground-truth NEGATIVE — including the fork the current data could not separate — is out."""
    results = _by_id(tmp_path)
    # augmented pass = the current-data oracle passed it AND the observer does not reject it
    augmented_pass = sorted(fid for fid, (fx, obs) in results.items()
                            if fx.oracle_would_pass and not obs.would_reject)
    assert augmented_pass == ["g4geo-01-perfect-line"]

    # and the fork specifically transitioned pass -> reject because of the observer (not the old oracle)
    fork_fx, fork_obs = results["g4geo-06-wrong-branch-fork"]
    assert fork_fx.oracle_would_pass and fork_obs.would_reject


def test_offset_run_is_caught_only_by_endpoint_tightness(tmp_path):
    """An end-to-end (real synthetic PDF) tightness-only negative: a single clean unforked run shifted off the
    bound endpoints. Branch-uniqueness is UNIQUE (a branch-only gate would accept it); the observer rejects it
    solely via ENDPOINT_TO_RUN_COORDINATE_TIGHTNESS."""
    p = tmp_path / "offset_plan.pdf"
    p.write_bytes(plan_offset_run_with_notes())
    _d, obs = _observe_plan(p)
    assert obs is not None
    assert obs.branch_uniqueness == BRANCH_UNIQUE
    assert obs.endpoint_tightness == TIGHTNESS_LOOSE
    assert obs.reject_signals == (ENDPOINT_TO_RUN_COORDINATE_TIGHTNESS,)


# ----------------------------------------------------------------------------------------------------------- #
# Guardrails: read-only, observer never reaches the placement path, name-free.
# ----------------------------------------------------------------------------------------------------------- #
def test_observer_does_not_mutate_the_dialect(tmp_path):
    p = tmp_path / "clean_plan.pdf"
    p.write_bytes(_clean_bytes(tmp_path))
    plan = PlanPdf(str(p))
    dialect = GenericGeometryDialect()
    dialect.extract_callouts(plan, 1, 0)
    before_polys = copy.deepcopy(dialect._polys)
    before_meta = copy.deepcopy(dialect._meta)
    before_band = copy.deepcopy(dialect._band_segs)
    before_axis_ids = {k: id(v) for k, v in dialect._axis.items()}            # same axis instances, none replaced
    before_axis_coef = {k: (v.a, v.b, v.n, v.residual_ft) for k, v in dialect._axis.items()}
    observe_dialect_run(dialect, 1, _BORE_START_FT, _BORE_END_FT)
    # the observer reads the dialect (axis_for / band_segments_for / x_at) and mutates nothing
    assert dialect._polys == before_polys
    assert dialect._meta == before_meta
    assert dialect._band_segs == before_band
    assert {k: id(v) for k, v in dialect._axis.items()} == before_axis_ids
    assert {k: (v.a, v.b, v.n, v.residual_ft) for k, v in dialect._axis.items()} == before_axis_coef


def test_observer_module_imports_no_placement_or_render_code():
    """Structural lock: the observer is pure geometry. It must not import contracts/match/render/api/store, so
    it can never participate in or alter a placement decision."""
    tree = ast.parse(_OBSERVER.read_text(encoding="utf-8"), filename=_OBSERVER.name)
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
    """(A) operator NAME_TOKENS absent from the observer module; (B) the two diagnostics are the documented
    name-free strings (no customer/person/place tokens)."""
    src = _OBSERVER.read_text(encoding="utf-8")
    raw = os.environ.get("NAME_TOKENS", "").strip()
    if raw:
        tokens = [t for t in re.split(r"[|,\s]+", raw) if t]
        hits = sorted({t for t in tokens if re.search(r"\b" + re.escape(t.lower()) + r"\b", src.lower())})
        assert not hits, "NAME_TOKENS leaked into the observer module: %r" % hits
    assert BRANCH_PATH_UNIQUENESS == "BRANCH_PATH_UNIQUENESS"
    assert ENDPOINT_TO_RUN_COORDINATE_TIGHTNESS == "ENDPOINT_TO_RUN_COORDINATE_TIGHTNESS"


# --- helpers for the read-only test (a clean both-bound fixture, built once) -------------------------------- #
def _build(tmp_path):
    root = tmp_path / "g4geo_ro"
    build_g4_geometry_fixtures(root)
    return root


def _clean_bytes(tmp_path):
    for fx in load_g4_geometry_fixtures(_build(tmp_path)):
        if fx.fixture_id == "g4geo-01-perfect-line":
            return fx.plan_path.read_bytes()
    raise AssertionError("clean fixture missing")
