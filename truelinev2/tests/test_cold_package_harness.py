"""Cold-package evaluation harness: baseline behavior + scorer logic.

Drives the synthetic baseline fixtures through the REAL product redline decision (empty registry -> cold
path) in an isolated tmp store, and asserts the engine's current cold-package behavior:
  * a tight single proposed bore over the span -> UPLOADED_REVIEW (generic lane places, capped REVIEW);
  * several co-linear runs over the span     -> UPLOADED_REVIEW (placed, honestly low/correction);
  * axis-only / blank plans                  -> ABSTAIN with the named engine blocker.
A correct ABSTAIN (the expected named blocker) is a PASS — an honest abstain is evidence of a real, named
missing capability, never a failure.
"""
from __future__ import annotations

from truelinev2.harness.fixtures import Fixture, load_fixtures
from truelinev2.harness.runner import provision_and_run
from truelinev2.harness.scorer import score
from truelinev2.harness.synth import build_synthetic_fixtures


def test_baseline_matrix(tmp_path):
    fx_root = tmp_path / "fixtures"
    store = tmp_path / "store"
    store.mkdir(parents=True)
    build_synthetic_fixtures(fx_root)

    fixtures = load_fixtures(fx_root)
    assert {f.fixture_id for f in fixtures} == {
        "pkg-001-tight-red-run", "pkg-002-ambiguous-runs", "pkg-003-axis-no-runs", "pkg-004-blank-plan"}

    results = {}
    for f in fixtures:
        results[f.fixture_id] = score(provision_and_run(store, f), f)

    # Every fixture matches its expected status (and expected named blockers) -> 4/4 PASS.
    assert all(r.passed for r in results.values()), {k: r.detail for k, r in results.items()}

    # The two placeable plans reach REVIEW (never auto-promoted; generic lane is capped to REVIEW).
    assert results["pkg-001-tight-red-run"].observed_status == "UPLOADED_REVIEW"
    assert results["pkg-002-ambiguous-runs"].observed_status == "UPLOADED_REVIEW"

    # The two un-placeable plans abstain with the engine's named reason (honest, specific — not a bare abstain).
    for fid in ("pkg-003-axis-no-runs", "pkg-004-blank-plan"):
        assert results[fid].observed_status == "ABSTAIN"
        assert any("NO_PLAN_DIALECT_RECOGNIZED" in b for b in results[fid].observed_blockers)


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


def test_review_fixture_has_no_blockers():
    fx = Fixture("pkg-y", "", (), (), "UPLOADED_REVIEW", ())
    review = {"path": "UPLOADED_REVIEW", "blockers": []}
    r = score(review, fx)
    assert r.passed
    assert r.observed_blockers == ()
