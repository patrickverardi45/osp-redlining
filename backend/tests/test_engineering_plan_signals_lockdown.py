"""Engineering-plan signal regression lock-down (P0 / CP-1).

PURPOSE
-------
Captures the CURRENT deterministic output of the three engineering-plan
signal functions as a golden snapshot. This test exists to detect drift —
NOT to validate correctness. Whatever main.py produces today is the baseline
the Engineering-Plan PDF Signal Expansion Sprint must preserve when the
dimension-aggregator refactor (P1) ships.

LOCKED FUNCTIONS
----------------
- main._extract_engineering_plan_signals   (main.py:7418)
- main._plan_aware_ranking_boost           (main.py:7775)
- main._classify_group_ambiguity           (main.py:7589)

FIXTURE INPUTS
--------------
- backend/tests/fixtures/engineering_plans/brenham/plan_inputs.json
- backend/tests/fixtures/engineering_plans/brenham/normalized_groups.json
- backend/tests/fixtures/engineering_plans/brenham/rankings_input.json
- backend/tests/fixtures/engineering_plans/brenham/ambiguity_scenarios.json

GOLDEN OUTPUTS
--------------
- backend/tests/fixtures/engineering_plans/brenham/golden/extracted_signals.json
- backend/tests/fixtures/engineering_plans/brenham/golden/plan_aware_boost.json
- backend/tests/fixtures/engineering_plans/brenham/golden/ambiguity_classification.json

COMMAND
-------
    # Normal run (asserts against golden):
    python -m pytest backend/tests/test_engineering_plan_signals_lockdown.py -v

    # Regenerate golden after an intentional behavior change:
    LOCKDOWN_UPDATE=1 python -m pytest backend/tests/test_engineering_plan_signals_lockdown.py -v

    # PowerShell:
    $env:LOCKDOWN_UPDATE="1"; python -m pytest backend/tests/test_engineering_plan_signals_lockdown.py -v

IF A TEST FAILS
---------------
A failure means one of the three locked functions changed output for an
input the fixture covers. Either:
  (a) the change is intentional — regenerate golden with LOCKDOWN_UPDATE=1
      and commit the diff, OR
  (b) the change is unintentional — investigate before regenerating.
NEVER regenerate-to-green without understanding why the snapshot drifted.
"""

from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from typing import Any, Dict, List

_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

# Required env vars for main.py import — match the defaults used by every
# other backend test. Real secrets are never required for this lock-down
# because the locked functions are pure (no JWT decode, no DB access).
os.environ.setdefault("TRUELINE_JWT_SECRET", "lockdown-test-secret")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "lockdown-test-auth-secret")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

import main  # noqa: E402

_FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "engineering_plans" / "brenham"
_GOLDEN_ROOT = _FIXTURE_ROOT / "golden"

_UPDATE_GOLDEN = os.environ.get("LOCKDOWN_UPDATE", "").strip() == "1"


def _load_json(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as fp:
        return json.load(fp)


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, indent=2, sort_keys=True) + "\n"
    with open(path, "w", encoding="utf-8", newline="\n") as fp:
        fp.write(text)


def _assert_or_update(test: unittest.TestCase, actual: Any, golden_path: Path, label: str) -> None:
    if _UPDATE_GOLDEN or not golden_path.is_file():
        _write_json(golden_path, actual)
        action = "regenerated" if _UPDATE_GOLDEN else "created"
        print(f"[LOCKDOWN] {action} {label} golden -> {golden_path}")
        return
    expected = _load_json(golden_path)
    test.assertEqual(
        actual,
        expected,
        msg=(
            f"\n\n{label} drift detected against {golden_path}.\n"
            f"If this change is intentional, regenerate with LOCKDOWN_UPDATE=1 and commit the diff.\n"
            f"If this change is UNINTENTIONAL, investigate before regenerating."
        ),
    )


def _load_plans() -> List[Dict[str, Any]]:
    return _load_json(_FIXTURE_ROOT / "plan_inputs.json")["plans"]


def _load_groups_by_id() -> Dict[str, Dict[str, Any]]:
    groups = _load_json(_FIXTURE_ROOT / "normalized_groups.json")["groups"]
    return {g["group_id"]: g for g in groups}


def _build_plan_signals() -> List[Dict[str, Any]]:
    """Run extraction once; reused by the boost + classify tests so they
    exercise the exact same signal payloads the rebuild pipeline would."""
    return [main._extract_engineering_plan_signals(p) for p in _load_plans()]


# ---------------------------------------------------------------------------
# Locked function 1 — _extract_engineering_plan_signals
# ---------------------------------------------------------------------------

class TestExtractEngineeringPlanSignals(unittest.TestCase):
    def test_brenham_plan_signal_extraction_matches_golden(self) -> None:
        plans = _load_plans()
        actual = {
            plan["plan_id"]: main._extract_engineering_plan_signals(plan)
            for plan in plans
        }
        _assert_or_update(
            self,
            actual,
            _GOLDEN_ROOT / "extracted_signals.json",
            label="_extract_engineering_plan_signals",
        )


# ---------------------------------------------------------------------------
# Locked function 2 — _plan_aware_ranking_boost
# ---------------------------------------------------------------------------

class TestPlanAwareRankingBoost(unittest.TestCase):
    def test_brenham_plan_aware_boost_matches_golden(self) -> None:
        plan_signals = _build_plan_signals()
        groups_by_id = _load_groups_by_id()
        scenarios = _load_json(_FIXTURE_ROOT / "rankings_input.json")["scenarios"]

        actual: Dict[str, Any] = {}
        for scenario in scenarios:
            group_id = scenario["group_id"]
            group = groups_by_id[group_id]
            rankings_in = scenario["rankings"]
            boosted, meta = main._plan_aware_ranking_boost(rankings_in, group, plan_signals)
            actual[group_id] = {
                "boosted_rankings": boosted,
                "plan_bias_meta": meta,
            }

        _assert_or_update(
            self,
            actual,
            _GOLDEN_ROOT / "plan_aware_boost.json",
            label="_plan_aware_ranking_boost",
        )


# ---------------------------------------------------------------------------
# Locked function 3 — _classify_group_ambiguity
# ---------------------------------------------------------------------------

class TestClassifyGroupAmbiguity(unittest.TestCase):
    def test_brenham_ambiguity_classification_matches_golden(self) -> None:
        plan_signals = _build_plan_signals()
        groups_by_id = _load_groups_by_id()
        scenarios = _load_json(_FIXTURE_ROOT / "ambiguity_scenarios.json")["scenarios"]

        actual: Dict[str, Any] = {}
        for scenario in scenarios:
            scenario_id = scenario["scenario_id"]
            group = groups_by_id[scenario["group_ref"]]
            status, meta = main._classify_group_ambiguity(
                scenario["render_block_reasons"],
                group,
                scenario["validation"],
                scenario["matched_route"],
                plan_signals,
            )
            actual[scenario_id] = {"status": status, "meta": meta}

        _assert_or_update(
            self,
            actual,
            _GOLDEN_ROOT / "ambiguity_classification.json",
            label="_classify_group_ambiguity",
        )


if __name__ == "__main__":
    unittest.main()
