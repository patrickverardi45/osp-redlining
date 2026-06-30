"""Cold-package evaluation harness: behavior matrix + scorer logic.

Drives the synthetic fixtures through the REAL product redline decision (empty registry -> cold path) in an
isolated tmp store, and pins the engine's CURRENT cold-package behavior:

  * a clear single bore-shaped run over the span -> UPLOADED_REVIEW, MEDIUM confidence;
  * ambiguous / partial-coverage runs            -> UPLOADED_REVIEW, LOW confidence, correction-recommended;
  * no usable geometry (no run / blank / weak axis / speckle) -> ABSTAIN (currently the coarse
    NO_PLAN_DIALECT_RECOGNIZED for several distinct causes);
  * the review gate unsatisfied                  -> ABSTAIN, NO_ENGINE_READY_REVIEWED_BORE_LOG.

A correct ABSTAIN with the expected named blocker is a PASS. The two over-placement probes are PINNED as
KNOWN divergences (the engine currently places a LOW, correction-recommended candidate on the full-sheet
alignment line where the oracle wants an ABSTAIN); if a future abstain-policy change flips them, these
assertions fail on purpose and force a deliberate review (never a silent regression).
"""
from __future__ import annotations

from truelinev2.harness.fixtures import Fixture, load_fixtures
from truelinev2.harness.runner import provision_and_run
from truelinev2.harness.scorer import score
from truelinev2.harness.synth import build_synthetic_fixtures

# Fixtures whose observed outcome matches the desired oracle today.
ALIGNED = {
    "pkg-001-tight-red-run", "pkg-002-ambiguous-runs", "pkg-007-partial-mid", "pkg-009-multi-sheet",
    "pkg-003-axis-no-runs", "pkg-004-blank-plan", "pkg-005-weak-axis-2-ticks", "pkg-010-speckle-no-run",
    "pkg-011-no-engine-ready-borelog",
}
# Over-placement probes: the oracle says ABSTAIN (no clear bore drawn), but the engine currently places a
# LOW, correction-recommended candidate on the full-sheet alignment line. Pinned (see module docstring).
KNOWN_OVERPLACEMENT = {"pkg-006-partial-below-min", "pkg-008-over-placement-baseline"}


def test_matrix(tmp_path):
    fx_root = tmp_path / "fixtures"
    store = tmp_path / "store"
    store.mkdir(parents=True)
    build_synthetic_fixtures(fx_root)

    fixtures = load_fixtures(fx_root)
    assert {f.fixture_id for f in fixtures} == ALIGNED | KNOWN_OVERPLACEMENT

    results = {f.fixture_id: score(provision_and_run(store, f), f) for f in fixtures}

    # Every aligned fixture matches its desired oracle (status + named blockers).
    for fid in ALIGNED:
        assert results[fid].passed, results[fid].detail

    # A clear bore-shaped run is a confident (MEDIUM) review; never auto-promoted.
    assert results["pkg-001-tight-red-run"].observed_status == "UPLOADED_REVIEW"
    assert results["pkg-001-tight-red-run"].observed_band == "MEDIUM"

    # Un-placeable geometry abstains with the engine's (currently coarse) named dialect reason.
    for fid in ("pkg-003-axis-no-runs", "pkg-005-weak-axis-2-ticks", "pkg-010-speckle-no-run"):
        assert results[fid].observed_status == "ABSTAIN"
        assert any("NO_PLAN_DIALECT_RECOGNIZED" in b for b in results[fid].observed_blockers)

    # The gate-state abstain names its SPECIFIC cause (distinct from the coarse dialect blocker).
    assert any("NO_ENGINE_READY_REVIEWED_BORE_LOG" in b
               for b in results["pkg-011-no-engine-ready-borelog"].observed_blockers)

    # FINDING (pinned): the over-placement probes place a LOW correction-recommended candidate on the
    # alignment instead of abstaining.
    for fid in KNOWN_OVERPLACEMENT:
        r = results[fid]
        assert not r.passed
        assert r.observed_status == "UPLOADED_REVIEW"
        assert r.observed_band == "LOW"
        assert r.observed_correction is True


def test_scorer_path_and_blocker_logic():
    fx = Fixture("pkg-x", "", (), (), "ABSTAIN", ("NO_PLAN_DIALECT_RECOGNIZED",))

    # correct abstain with the expected named blocker -> PASS
    good = {"path": "ABSTAIN", "blockers": [{"source": "engine", "code": "NO_PLAN_DIALECT_RECOGNIZED"}]}
    assert score(good, fx).passed

    # path mismatch (placed where abstain was expected = over-placement) -> FAIL
    placed = {"path": "UPLOADED_REVIEW", "blockers": []}
    assert not score(placed, fx).passed

    # right path but the expected named blocker is missing -> FAIL
    wrong_reason = {"path": "ABSTAIN", "blockers": [{"source": "engine", "code": "SOMETHING_ELSE"}]}
    assert not score(wrong_reason, fx).passed


def test_scorer_captures_confidence():
    fx = Fixture("pkg-y", "", (), (), "UPLOADED_REVIEW", ())
    decision = {
        "path": "UPLOADED_REVIEW", "blockers": [],
        "review": {"record": {"confidence": {"band": "LOW", "score": 0.35, "correction_recommended": True}}},
    }
    r = score(decision, fx)
    assert r.passed
    assert r.observed_band == "LOW"
    assert r.observed_score == 0.35
    assert r.observed_correction is True
