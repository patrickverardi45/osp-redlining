"""PT.ACT R3.a — golden LIVE-output fixtures for PT.1 and PT.2.0.

Locks down the current HEAD (`de058f3`) LIVE behavior of
`_apply_print_to_sheet_plausibility_boost` and
`_apply_sheet_adjacency_plausibility_boost` by capturing the full
`(rankings_out, meta)` state for a small set of canonical scenarios.

After the R3 refactor (planned R3.b/R3.c) lifts each function body into
an `_compute_*_internal` helper, these tests must still pass — proving
byte-identical LIVE behavior across the refactor.

Capture (regenerate JSON from current code behavior — RUN BEFORE REFACTOR):

    cd backend/.. && python -c "from backend.tests.test_r3_golden_fixtures import capture_all; capture_all()"

Verify (default pytest run, must remain green across the refactor):

    python -m pytest backend/tests/test_r3_golden_fixtures.py -q

Doctrine:
  - Scenarios are deterministic — seam + sequence helpers are mocked,
    LIVE flag is set/restored under a try/finally guard.
  - Three scenarios per layer (reorder-fire-flip, gate-blocked-by-gap,
    and one mid-state per layer). Kept small for reviewability.
  - JSON written with `sort_keys=True, indent=2` for stable diffs.
  - Each scenario's `rankings_in`, `group`, mock inputs, and resulting
    `rankings_out` + `meta` are all serialized for full auditability.
"""

from __future__ import annotations

import copy
import json
import os
import sys
import unittest
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import patch

# Required for backend.main import (matches existing test prelude).
os.environ.setdefault("TRUELINE_JWT_SECRET", "r3-golden-secret")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "r3-golden-auth-secret")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

from backend import main as M

FIXTURE_DIR: Path = Path(__file__).parent / "fixtures"
PT1_FIXTURE: Path = FIXTURE_DIR / "r3_live_golden_pt1.json"
PT2_FIXTURE: Path = FIXTURE_DIR / "r3_live_golden_pt2.json"


# ---------------------------------------------------------------------------
# Synthetic input helpers — same shape as existing PT.1/PT.2.0 test files
# ---------------------------------------------------------------------------


def _ranking(rid: str, score: float, *, name: str = "") -> Dict[str, Any]:
    return {
        "route_id":        rid,
        "route_name":      name or f"name_{rid}",
        "score":           float(score),
        "combined_score":  float(score),
        "route_score":     0.0,
        "route_length_ft": 1000.0,
    }


def _group(tokens: List[Any]) -> Dict[str, Any]:
    return {
        "group_idx":   0,
        "source_file": "golden.csv",
        "print_tokens": list(tokens),
    }


# ---------------------------------------------------------------------------
# PT.1 scenarios — LIVE mode
# ---------------------------------------------------------------------------


PT1_SCENARIOS: List[Dict[str, Any]] = [
    {
        "name":            "reorder_fires_and_flips",
        "description":     "Gap 0.01; 3 tokens map to route_B (3*0.01 = cap); 0.59+0.03=0.62 > 0.60 -> reorder flips order.",
        "rankings_in":     [_ranking("route_A", 0.60), _ranking("route_B", 0.59)],
        "group":           _group(["7", "8", "9"]),
        "seam_map":        {"7": [42], "8": [43], "9": [44]},
        "sheet_to_routes": {42: ["route_B"], 43: ["route_B"], 44: ["route_B"]},
    },
    {
        "name":            "reorder_attempted_no_flip",
        "description":     "Gap 0.05; top-1 receives the 0.01 boost; gate fires but order unchanged (route_A stays).",
        "rankings_in":     [_ranking("route_A", 0.60), _ranking("route_B", 0.55)],
        "group":           _group(["7"]),
        "seam_map":        {"7": [42]},
        "sheet_to_routes": {42: ["route_A"]},
    },
    {
        "name":            "gap_above_threshold",
        "description":     "Gap 0.30 (>0.10); boost applies to route_A; reorder gate blocked, gap_above_threshold.",
        "rankings_in":     [_ranking("route_A", 0.85), _ranking("route_B", 0.55)],
        "group":           _group(["7"]),
        "seam_map":        {"7": [42]},
        "sheet_to_routes": {42: ["route_A"]},
    },
]


# ---------------------------------------------------------------------------
# PT.2.0 scenarios — LIVE mode
# ---------------------------------------------------------------------------


PT2_SCENARIOS: List[Dict[str, Any]] = [
    {
        "name":            "full_contiguous_match_flips",
        "description":     "Gap 0.01; route_B has full coverage (delta=cap); 0.59+0.03=0.62 -> reorder flips.",
        "rankings_in":     [_ranking("route_A", 0.60), _ranking("route_B", 0.59)],
        "group":           _group(["7"]),
        "seam_map":        {"7": [101, 102]},
        "route_sequences": {"route_A": [201], "route_B": [101, 102]},
    },
    {
        "name":            "partial_non_contiguous_run",
        "description":     "Gap 0.05; route_A's contiguous run is 2/3 (delta=0.02); no flip; gate fires.",
        "rankings_in":     [_ranking("route_A", 0.60), _ranking("route_B", 0.55)],
        "group":           _group(["7"]),
        "seam_map":        {"7": [101, 102, 103]},
        "route_sequences": {"route_A": [101, 999, 102, 103], "route_B": [201]},
    },
    {
        "name":            "gap_above_threshold",
        "description":     "Gap 0.30 (>0.10); route_A has full coverage; reorder gate blocked.",
        "rankings_in":     [_ranking("route_A", 0.85), _ranking("route_B", 0.55)],
        "group":           _group(["7"]),
        "seam_map":        {"7": [101, 102]},
        "route_sequences": {"route_A": [101, 102], "route_B": [201]},
    },
]


# ---------------------------------------------------------------------------
# Scenario runners (LIVE mode, deterministic, env restored on exit)
# ---------------------------------------------------------------------------


def _set_flag(name: str, value: str) -> Any:
    sentinel = object()
    prior: Any = os.environ.get(name, sentinel)
    os.environ[name] = value
    return prior


def _restore_flag(name: str, prior: Any) -> None:
    sentinel = object()
    # Detect "not present originally" by checking type explicitly.
    if prior is None or (prior is not None and not isinstance(prior, str)):
        # Conservative: pop, then re-set if prior was a real string.
        os.environ.pop(name, None)
        if isinstance(prior, str):
            os.environ[name] = prior
    else:
        os.environ[name] = prior


def _run_pt1_scenario(scenario: Dict[str, Any]) -> Dict[str, Any]:
    rankings_in = copy.deepcopy(scenario["rankings_in"])
    group = copy.deepcopy(scenario["group"])
    seam_map = scenario["seam_map"]
    # JSON loads with str keys; preserve int keys for sheet_to_routes.
    sheet_to_routes = {int(k): list(v) for k, v in scenario["sheet_to_routes"].items()}

    prior = os.environ.get(M._PRINT_TO_SHEET_BOOST_FLAG_ENV)
    os.environ[M._PRINT_TO_SHEET_BOOST_FLAG_ENV] = "1"
    try:
        with patch.object(M, "_print_to_sheets_from_packet_index", return_value=seam_map), \
                patch.object(M, "_sheet_to_route_ids_from_packet_index",
                             return_value=sheet_to_routes):
            rankings_out, meta = M._apply_print_to_sheet_plausibility_boost(rankings_in, group)
    finally:
        if prior is None:
            os.environ.pop(M._PRINT_TO_SHEET_BOOST_FLAG_ENV, None)
        else:
            os.environ[M._PRINT_TO_SHEET_BOOST_FLAG_ENV] = prior
    return {"rankings_out": rankings_out, "meta": meta}


def _run_pt2_scenario(scenario: Dict[str, Any]) -> Dict[str, Any]:
    rankings_in = copy.deepcopy(scenario["rankings_in"])
    group = copy.deepcopy(scenario["group"])
    seam_map = scenario["seam_map"]
    route_sequences = {k: list(v) for k, v in scenario["route_sequences"].items()}

    prior = os.environ.get(M._SHEET_ADJACENCY_BOOST_FLAG_ENV)
    os.environ[M._SHEET_ADJACENCY_BOOST_FLAG_ENV] = "1"
    try:
        with patch.object(M, "_print_to_sheets_from_packet_index", return_value=seam_map), \
                patch.object(M, "_route_sheet_sequence",
                             side_effect=lambda rid: route_sequences.get(rid, [])):
            rankings_out, meta = M._apply_sheet_adjacency_plausibility_boost(rankings_in, group)
    finally:
        if prior is None:
            os.environ.pop(M._SHEET_ADJACENCY_BOOST_FLAG_ENV, None)
        else:
            os.environ[M._SHEET_ADJACENCY_BOOST_FLAG_ENV] = prior
    return {"rankings_out": rankings_out, "meta": meta}


# ---------------------------------------------------------------------------
# JSON-safe coercion (defensive; all current shapes are basic types already)
# ---------------------------------------------------------------------------


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(v) for v in value]
    if isinstance(value, bool) or isinstance(value, (str, int, float)) or value is None:
        return value
    return str(value)


# ---------------------------------------------------------------------------
# Capture — regenerate fixtures from current behavior
# ---------------------------------------------------------------------------


def capture_all() -> None:
    """Run every scenario through the current LIVE code path and write
    JSON fixtures. Intended to be invoked ONCE before the R3 refactor
    lands, then never again unless explicitly approved."""
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)

    pt1_records: List[Dict[str, Any]] = []
    for s in PT1_SCENARIOS:
        out = _run_pt1_scenario(s)
        pt1_records.append({
            "name":             s["name"],
            "description":      s["description"],
            "rankings_in":      _to_jsonable(s["rankings_in"]),
            "group":            _to_jsonable(s["group"]),
            "seam_map":         _to_jsonable(s["seam_map"]),
            "sheet_to_routes":  _to_jsonable(s["sheet_to_routes"]),
            "rankings_out":     _to_jsonable(out["rankings_out"]),
            "meta":             _to_jsonable(out["meta"]),
        })
    PT1_FIXTURE.write_text(
        json.dumps(pt1_records, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    pt2_records: List[Dict[str, Any]] = []
    for s in PT2_SCENARIOS:
        out = _run_pt2_scenario(s)
        pt2_records.append({
            "name":             s["name"],
            "description":      s["description"],
            "rankings_in":      _to_jsonable(s["rankings_in"]),
            "group":            _to_jsonable(s["group"]),
            "seam_map":         _to_jsonable(s["seam_map"]),
            "route_sequences":  _to_jsonable(s["route_sequences"]),
            "rankings_out":     _to_jsonable(out["rankings_out"]),
            "meta":             _to_jsonable(out["meta"]),
        })
    PT2_FIXTURE.write_text(
        json.dumps(pt2_records, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(f"[R3.a] Captured {len(pt1_records)} PT.1 scenarios -> {PT1_FIXTURE}")
    print(f"[R3.a] Captured {len(pt2_records)} PT.2.0 scenarios -> {PT2_FIXTURE}")


# ---------------------------------------------------------------------------
# Verify tests — fail if current output drifts from golden JSON
# ---------------------------------------------------------------------------


class TestPT1GoldenLive(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not PT1_FIXTURE.exists():
            raise AssertionError(
                f"Missing fixture {PT1_FIXTURE}. Run:\n"
                f"  python -c 'from backend.tests.test_r3_golden_fixtures import capture_all; capture_all()'"
            )
        cls.golden = {r["name"]: r
                      for r in json.loads(PT1_FIXTURE.read_text(encoding="utf-8"))}

    def test_all_scenarios_match_golden_output(self) -> None:
        self.assertEqual(set(self.golden.keys()), {s["name"] for s in PT1_SCENARIOS})
        for s in PT1_SCENARIOS:
            with self.subTest(scenario=s["name"]):
                expected = self.golden[s["name"]]
                actual = _run_pt1_scenario(s)
                self.assertEqual(
                    _to_jsonable(actual["rankings_out"]),
                    expected["rankings_out"],
                    msg=f"PT.1 rankings_out drift in scenario '{s['name']}'",
                )
                self.assertEqual(
                    _to_jsonable(actual["meta"]),
                    expected["meta"],
                    msg=f"PT.1 meta drift in scenario '{s['name']}'",
                )


class TestPT2GoldenLive(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not PT2_FIXTURE.exists():
            raise AssertionError(
                f"Missing fixture {PT2_FIXTURE}. Run:\n"
                f"  python -c 'from backend.tests.test_r3_golden_fixtures import capture_all; capture_all()'"
            )
        cls.golden = {r["name"]: r
                      for r in json.loads(PT2_FIXTURE.read_text(encoding="utf-8"))}

    def test_all_scenarios_match_golden_output(self) -> None:
        self.assertEqual(set(self.golden.keys()), {s["name"] for s in PT2_SCENARIOS})
        for s in PT2_SCENARIOS:
            with self.subTest(scenario=s["name"]):
                expected = self.golden[s["name"]]
                actual = _run_pt2_scenario(s)
                self.assertEqual(
                    _to_jsonable(actual["rankings_out"]),
                    expected["rankings_out"],
                    msg=f"PT.2.0 rankings_out drift in scenario '{s['name']}'",
                )
                self.assertEqual(
                    _to_jsonable(actual["meta"]),
                    expected["meta"],
                    msg=f"PT.2.0 meta drift in scenario '{s['name']}'",
                )


if __name__ == "__main__":
    if "--capture" in sys.argv:
        capture_all()
    else:
        unittest.main()
