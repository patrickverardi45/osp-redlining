"""Synthetic regression coverage for the P5.3 diagnostic-only emission layer.

Covers the main.py helpers added by P5.3:
  - _trueline_plan_pdf_parse_enabled()
  - _resolve_engineering_plan_pdf_paths(session_id)
  - _build_plan_topology_for_session(session_id)
  - _print_to_sheets_from_packet_index()
  - _evaluate_footage_range_for_group_safe(group, sheet_origins)

These tests verify diagnostic-only guarantees in isolation. Full-rebuild
integration is guarded by the P0 lockdown harness elsewhere.

COMMAND
-------
    python -m pytest backend/tests/test_p53_diagnostic_emission.py -v
"""

from __future__ import annotations

import copy
import os
import sys
import unittest
from pathlib import Path
from typing import Any, Dict, List

_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

os.environ.setdefault("TRUELINE_JWT_SECRET", "p53-test-secret")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "p53-test-auth-secret")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

import main  # noqa: E402
from app.services import engineering_plan_parser as pp  # noqa: E402

_FLAG_VAR = "TRUELINE_PLAN_PDF_PARSE"


class _EnvSaver:
    """Save and restore a single environment variable across a test."""

    def __init__(self, name: str) -> None:
        self.name = name
        self._was_set = False
        self._prev: str = ""

    def __enter__(self):
        self._was_set = self.name in os.environ
        self._prev = os.environ.get(self.name, "")
        return self

    def __exit__(self, *args):
        if self._was_set:
            os.environ[self.name] = self._prev
        else:
            os.environ.pop(self.name, None)


def _origin(length_ft: int, confidence: str = "high",
            has_reset: bool = False) -> Dict[str, Any]:
    return {
        "origin_ft": 0,
        "end_ft": int(length_ft),
        "length_ft": int(length_ft),
        "method": "matchline_chain",
        "confidence": confidence,
        "chain_anchor_sheets": [],
        "has_reset_boundary": bool(has_reset),
        "matchline_count": 2,
        "callout_count": 0,
        "notes": [],
    }


def _group(span_ft: int, print_tokens: List[Any]) -> Dict[str, Any]:
    return {"span_ft": span_ft, "print_tokens": list(print_tokens)}


# ---------------------------------------------------------------------------
# Flag resolution
# ---------------------------------------------------------------------------

class FlagResolution(unittest.TestCase):
    def test_unset_is_off(self) -> None:
        with _EnvSaver(_FLAG_VAR):
            os.environ.pop(_FLAG_VAR, None)
            self.assertFalse(main._trueline_plan_pdf_parse_enabled())

    def test_empty_is_off(self) -> None:
        with _EnvSaver(_FLAG_VAR):
            os.environ[_FLAG_VAR] = ""
            self.assertFalse(main._trueline_plan_pdf_parse_enabled())

    def test_zero_is_off(self) -> None:
        with _EnvSaver(_FLAG_VAR):
            os.environ[_FLAG_VAR] = "0"
            self.assertFalse(main._trueline_plan_pdf_parse_enabled())

    def test_false_string_is_off(self) -> None:
        with _EnvSaver(_FLAG_VAR):
            for val in ("false", "False", "FALSE", "no", "off"):
                with self.subTest(val=val):
                    os.environ[_FLAG_VAR] = val
                    self.assertFalse(main._trueline_plan_pdf_parse_enabled())

    def test_truthy_values_are_on(self) -> None:
        with _EnvSaver(_FLAG_VAR):
            for val in ("1", "true", "True", "TRUE", "yes", "YES", "on", "ON"):
                with self.subTest(val=val):
                    os.environ[_FLAG_VAR] = val
                    self.assertTrue(main._trueline_plan_pdf_parse_enabled())

    def test_garbage_is_off(self) -> None:
        with _EnvSaver(_FLAG_VAR):
            for val in ("2", "maybe", "okay", "enable", "y", "t", " 1 "):
                with self.subTest(val=val):
                    os.environ[_FLAG_VAR] = val
                    # Only the documented truthy set is accepted.
                    # " 1 " gets stripped to "1" and SHOULD match.
                    if val.strip().lower() in {"1", "true", "yes", "on"}:
                        self.assertTrue(main._trueline_plan_pdf_parse_enabled())
                    else:
                        self.assertFalse(main._trueline_plan_pdf_parse_enabled())

    def test_flag_read_at_runtime_not_import(self) -> None:
        # Toggle the flag back and forth in the same test; the function
        # must reflect the latest value without any reset/restart.
        with _EnvSaver(_FLAG_VAR):
            os.environ[_FLAG_VAR] = "0"
            self.assertFalse(main._trueline_plan_pdf_parse_enabled())
            os.environ[_FLAG_VAR] = "1"
            self.assertTrue(main._trueline_plan_pdf_parse_enabled())
            os.environ[_FLAG_VAR] = "0"
            self.assertFalse(main._trueline_plan_pdf_parse_enabled())


# ---------------------------------------------------------------------------
# Wrapper behavior
# ---------------------------------------------------------------------------

class WrapperBehavior(unittest.TestCase):
    def test_empty_topology_returns_no_emit_with_reason(self) -> None:
        out = main._evaluate_footage_range_for_group_safe(
            _group(span_ft=900, print_tokens=[4]),
            {},
        )
        self.assertEqual(out, {"emitted": False, "reason": "no_topology_available"})

    def test_none_topology_returns_no_emit_with_reason(self) -> None:
        out = main._evaluate_footage_range_for_group_safe(
            _group(span_ft=900, print_tokens=[4]),
            None,  # type: ignore[arg-type]
        )
        self.assertEqual(out, {"emitted": False, "reason": "no_topology_available"})

    def test_valid_topology_emits_full_evaluation(self) -> None:
        out = main._evaluate_footage_range_for_group_safe(
            _group(span_ft=900, print_tokens=[4]),
            {4: _origin(length_ft=900)},
        )
        self.assertTrue(out["emitted"])
        # All evaluate_footage_range_containment keys are merged.
        for key in (
            "classification", "confidence", "group_span_ft",
            "expected_plan_span_ft", "consistency_ratio",
            "referenced_sheets", "missing_sheets", "covered_sheets",
            "sheet_confidence_levels", "sheet_methods",
            "has_reset_boundary", "ambiguity_flags", "reasons",
            "would_boost",
        ):
            self.assertIn(key, out)

    def test_wrapper_never_emits_route_id(self) -> None:
        out = main._evaluate_footage_range_for_group_safe(
            _group(span_ft=900, print_tokens=[4]),
            {4: _origin(length_ft=900)},
        )
        for forbidden in (
            "route_id", "selected_route_id", "matched_route",
            "matched_route_id", "route_choice", "selected_route",
        ):
            self.assertNotIn(forbidden, out)

    def test_wrapper_safe_failures_on_garbage_group(self) -> None:
        # Garbage group with valid topology — wrapper must not raise.
        for bad_group in (None, "string", 42, [], object()):
            with self.subTest(group=bad_group):
                try:
                    out = main._evaluate_footage_range_for_group_safe(
                        bad_group,  # type: ignore[arg-type]
                        {4: _origin(length_ft=900)},
                    )
                except Exception as exc:
                    self.fail(f"wrapper raised on group={bad_group!r}: {exc!r}")
                # When the underlying helper returns no_data, the wrapper
                # still flags emitted=True with classification=no_data.
                self.assertIn("emitted", out)

    def test_wrapper_propagates_classification(self) -> None:
        out_contained = main._evaluate_footage_range_for_group_safe(
            _group(span_ft=900, print_tokens=[4]),
            {4: _origin(length_ft=900)},
        )
        self.assertEqual(out_contained["classification"], "contained_consistent")

        out_oor = main._evaluate_footage_range_for_group_safe(
            _group(span_ft=100, print_tokens=[4]),
            {4: _origin(length_ft=1000)},
        )
        self.assertEqual(out_oor["classification"], "out_of_range")


# ---------------------------------------------------------------------------
# print_to_sheets builder
# ---------------------------------------------------------------------------

class PrintToSheetsBuilder(unittest.TestCase):
    def test_brenham_packet_index_translates_to_string_keys(self) -> None:
        out = main._print_to_sheets_from_packet_index()
        # Sample of Brenham mappings — token "1" should resolve to [1].
        # These keys are stable across the Brenham fixture.
        self.assertIn("1", out)
        self.assertEqual(out["1"], [1])
        self.assertIn("18", out)
        self.assertEqual(out["18"], [18])

    def test_keys_are_all_strings(self) -> None:
        out = main._print_to_sheets_from_packet_index()
        for k in out.keys():
            self.assertIsInstance(k, str)

    def test_values_are_lists_of_ints(self) -> None:
        out = main._print_to_sheets_from_packet_index()
        for v in out.values():
            self.assertIsInstance(v, list)
            for item in v:
                self.assertIsInstance(item, int)

    def test_helper_never_raises(self) -> None:
        # Even if CURRENT_PACKET_PRINT_SHEET_INDEX is mutated in flight,
        # the helper must not raise. We do not mutate it here — just call.
        try:
            main._print_to_sheets_from_packet_index()
        except Exception as exc:
            self.fail(f"print_to_sheets builder raised: {exc!r}")


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

class PathResolution(unittest.TestCase):
    def test_empty_session_id_returns_empty_list(self) -> None:
        self.assertEqual(main._resolve_engineering_plan_pdf_paths(""), [])

    def test_unknown_session_id_returns_empty_list(self) -> None:
        # Random session id never seen by the system -> empty plans index.
        self.assertEqual(
            main._resolve_engineering_plan_pdf_paths(
                "nonexistent-session-id-for-test-only"
            ),
            [],
        )

    def test_helper_never_raises_on_arbitrary_input(self) -> None:
        for bad in (None, 0, [], {}, object()):
            with self.subTest(arg=bad):
                try:
                    out = main._resolve_engineering_plan_pdf_paths(bad)  # type: ignore[arg-type]
                except Exception as exc:
                    self.fail(f"path resolver raised on {bad!r}: {exc!r}")
                self.assertEqual(out, [])


# ---------------------------------------------------------------------------
# build_plan_topology safety
# ---------------------------------------------------------------------------

class BuildTopologySafety(unittest.TestCase):
    def test_unknown_session_returns_empty_dict(self) -> None:
        self.assertEqual(
            main._build_plan_topology_for_session(
                "nonexistent-session-id-for-test-only"
            ),
            {},
        )

    def test_empty_session_id_returns_empty_dict(self) -> None:
        self.assertEqual(main._build_plan_topology_for_session(""), {})

    def test_helper_never_raises_on_arbitrary_input(self) -> None:
        for bad in (None, 0, [], {}, object()):
            with self.subTest(arg=bad):
                try:
                    out = main._build_plan_topology_for_session(bad)  # type: ignore[arg-type]
                except Exception as exc:
                    self.fail(f"topology builder raised on {bad!r}: {exc!r}")
                self.assertEqual(out, {})


# ---------------------------------------------------------------------------
# Idempotence and input immutability
# ---------------------------------------------------------------------------

class Idempotence(unittest.TestCase):
    def test_repeated_wrapper_calls_produce_identical_output(self) -> None:
        group = _group(span_ft=900, print_tokens=[4])
        origins = {4: _origin(length_ft=900)}
        a = main._evaluate_footage_range_for_group_safe(group, origins)
        b = main._evaluate_footage_range_for_group_safe(group, origins)
        self.assertEqual(a, b)

    def test_wrapper_does_not_mutate_group(self) -> None:
        group = _group(span_ft=900, print_tokens=[4])
        snapshot = copy.deepcopy(group)
        main._evaluate_footage_range_for_group_safe(group, {4: _origin(length_ft=900)})
        self.assertEqual(group, snapshot)

    def test_wrapper_does_not_mutate_topology(self) -> None:
        origins = {4: _origin(length_ft=900)}
        snapshot = copy.deepcopy(origins)
        main._evaluate_footage_range_for_group_safe(_group(span_ft=900, print_tokens=[4]),
                                                    origins)
        self.assertEqual(origins, snapshot)

    def test_two_back_to_back_calls_return_independent_dicts(self) -> None:
        group = _group(span_ft=900, print_tokens=[4])
        origins = {4: _origin(length_ft=900)}
        a = main._evaluate_footage_range_for_group_safe(group, origins)
        b = main._evaluate_footage_range_for_group_safe(group, origins)
        a["referenced_sheets"].append(999)
        self.assertNotIn(999, b["referenced_sheets"])


# ---------------------------------------------------------------------------
# Diagnostic-only guarantees (cross-checks main.py for unintended consumers)
# ---------------------------------------------------------------------------

class DiagnosticOnlyGuarantees(unittest.TestCase):
    def test_footage_range_check_has_no_readers_in_main(self) -> None:
        """The diagnostic field must not be consumed by any scoring,
        validation, render, or selection logic. Comment-style references
        in the section header are allowed; rvalue / .get() reads are not.
        """
        main_py = Path(main.__file__).read_text(encoding="utf-8")

        # Exactly one assignment of the diagnostic key (the P5.3 writer).
        writes = main_py.count('_diag["footage_range_check"] =')
        self.assertEqual(
            writes, 1,
            f"expected exactly one writer of _diag['footage_range_check']; "
            f"found {writes}",
        )

        # No read-style consumption anywhere.
        forbidden_read_patterns = [
            '.get("footage_range_check"',
            ".get('footage_range_check'",
            '= _diag["footage_range_check"]',
            "= _diag['footage_range_check']",
            '= entry["footage_range_check"]',
            "= entry['footage_range_check']",
            '"footage_range_check" in ',
            "'footage_range_check' in ",
            'if _diag["footage_range_check"]',
            "if _diag['footage_range_check']",
        ]
        for pat in forbidden_read_patterns:
            self.assertNotIn(
                pat, main_py,
                f"footage_range_check must not be consumed by main.py "
                f"(found reader pattern: {pat!r})",
            )

    def test_p53_helpers_exist_at_module_level(self) -> None:
        for name in (
            "_trueline_plan_pdf_parse_enabled",
            "_resolve_engineering_plan_pdf_paths",
            "_build_plan_topology_for_session",
            "_print_to_sheets_from_packet_index",
            "_evaluate_footage_range_for_group_safe",
        ):
            self.assertTrue(hasattr(main, name),
                            f"main.py missing {name}")

    def test_parser_module_is_importable_from_main(self) -> None:
        self.assertIs(main._engineering_plan_parser, pp)

    def test_no_new_state_keys_written_outside_rebuild(self) -> None:
        """Verify that no top-level main.py function writes
        engineering_plan_sheet_origins or engineering_plan_parser_outputs
        into STATE. P5.3 keeps topology in a local variable.
        """
        main_py = Path(main.__file__).read_text(encoding="utf-8")
        for forbidden_state_key in (
            'STATE["engineering_plan_sheet_origins"]',
            'STATE["engineering_plan_parser_outputs"]',
            "STATE['engineering_plan_sheet_origins']",
            "STATE['engineering_plan_parser_outputs']",
        ):
            self.assertNotIn(
                forbidden_state_key, main_py,
                f"P5.3 must not persist topology in STATE: "
                f"{forbidden_state_key!r} found"
            )


# ---------------------------------------------------------------------------
# Flag-gated emission shape contract
# ---------------------------------------------------------------------------

class EmissionShape(unittest.TestCase):
    def test_no_emit_path_emits_minimal_two_key_dict(self) -> None:
        out = main._evaluate_footage_range_for_group_safe(
            _group(span_ft=900, print_tokens=[4]),
            {},
        )
        # Exactly two keys: emitted, reason.
        self.assertEqual(set(out.keys()), {"emitted", "reason"})

    def test_emit_path_emits_emitted_plus_evaluation_keys(self) -> None:
        out = main._evaluate_footage_range_for_group_safe(
            _group(span_ft=900, print_tokens=[4]),
            {4: _origin(length_ft=900)},
        )
        self.assertIn("emitted", out)
        self.assertTrue(out["emitted"])
        # All evaluation keys are present (cross-checks merge).
        for key in pp.evaluate_footage_range_containment(
            _group(span_ft=900, print_tokens=[4]),
            {4: _origin(length_ft=900)},
        ).keys():
            self.assertIn(key, out)


if __name__ == "__main__":
    unittest.main()
