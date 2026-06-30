r"""Cold-package evaluation harness CLI: (re)build the synthetic baseline fixtures, run each through the real
product redline decision (registry=None) in a fresh transient store, score, and print the failure matrix.

Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.harness

Fixtures + the transient run store live gitignored under data/outputs/truelinev2/cold_package_harness/.
This runs no engine of its own and renders nothing — it only drives the existing contracts read-only.
"""
from __future__ import annotations

import shutil

from truelinev2.config import _REPO_ROOT
from truelinev2.harness.fixtures import load_fixtures
from truelinev2.harness.report import blocker_histogram, format_matrix
from truelinev2.harness.runner import provision_and_run
from truelinev2.harness.scorer import score
from truelinev2.harness.synth import build_synthetic_fixtures

_HARNESS_ROOT = _REPO_ROOT / "data" / "outputs" / "truelinev2" / "cold_package_harness"
_FIXTURES_ROOT = _HARNESS_ROOT / "fixtures"
_STORE_ROOT = _HARNESS_ROOT / "run_store"


def main() -> int:
    ids = build_synthetic_fixtures(_FIXTURES_ROOT)
    print("[harness] built %d synthetic fixtures: %s" % (len(ids), ", ".join(ids)))

    fixtures = load_fixtures(_FIXTURES_ROOT)
    if _STORE_ROOT.exists():
        shutil.rmtree(_STORE_ROOT)
    _STORE_ROOT.mkdir(parents=True, exist_ok=True)

    results = []
    for fx in fixtures:
        try:
            decision = provision_and_run(_STORE_ROOT, fx)
        except Exception as exc:                       # a harness/provision error is a fixture-level failure
            from truelinev2.harness.scorer import ScoreResult
            results.append(ScoreResult(fx.fixture_id, fx.expected_status, "ERROR", (), fx.expected_blockers,
                                       False, "provision/run raised: %r" % exc))
            continue
        results.append(score(decision, fx))

    print()
    print(format_matrix(results))
    print()
    print(blocker_histogram(results))
    return 0 if all(r.passed for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
