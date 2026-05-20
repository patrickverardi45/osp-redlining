"""RI.1 — rebuild scope seam tests.

Verifies that the RebuildScope enum exists with the documented values
and that _rebuild_field_data_outputs accepts the kwarg without behavioral
deviation from the no-kwarg call.

RI.1 acceptance gate. Behavioral parity for production paths is verified
by the existing R3.a golden-fixture suite; this file covers only the new
seam itself.

COMMAND
-------
    python -m pytest backend/tests/test_rebuild_scope_seam.py -v
"""

from __future__ import annotations

import copy
import os
import unittest
from typing import Any, Dict

# Required for backend.main import (matches existing test prelude).
os.environ.setdefault("TRUELINE_JWT_SECRET", "ri1-test-secret")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "ri1-test-auth-secret")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

from backend import main as M
from backend.app.core.rebuild_scope import RebuildScope


class TestRebuildScopeSeam(unittest.TestCase):
    """RI.1 seam — enum vocabulary + kwarg threading parity."""

    def setUp(self) -> None:
        # Snapshot whatever STATE the test runner left behind; restore it
        # on teardown so this file cannot pollute downstream tests.
        self._saved_state = copy.deepcopy(dict(M.STATE))

    def tearDown(self) -> None:
        M.STATE.clear()
        M.STATE.update(self._saved_state)

    def _reset_to_minimal(self) -> None:
        """Minimal STATE: no rows, no routes, no session hint.

        Drives _rebuild_field_data_outputs through the empty-input path
        with the eng-plans branch skipped (empty session hint) and the
        per-group loop never entering (empty rows -> empty groups).
        """
        M.STATE.clear()
        M.STATE.update({
            "committed_rows": [],
            "route_catalog": [],
            "_session_id_hint": "",
        })

    def _snapshot(self) -> Dict[str, Any]:
        return copy.deepcopy(dict(M.STATE))

    # ----- enum surface --------------------------------------------------

    def test_01_enum_values_match_spec(self) -> None:
        """RebuildScope value strings are locked against accidental rename."""
        self.assertEqual(RebuildScope.FULL.value, "full")
        self.assertEqual(RebuildScope.ROWS_ONLY.value, "rows_only")
        self.assertEqual(RebuildScope.METADATA_ONLY.value, "metadata_only")
        self.assertEqual(RebuildScope.RESET.value, "reset")

    def test_02_enum_is_str_subclass(self) -> None:
        """str-Enum base preserved for downstream JSON serialization (RI.5)."""
        self.assertIsInstance(RebuildScope.FULL, str)
        self.assertIsInstance(RebuildScope.ROWS_ONLY, str)

    # ----- function seam parity ------------------------------------------

    def test_03_default_full_parity_with_no_kwarg(self) -> None:
        """No-kwarg call and scope=FULL call must produce identical STATE."""
        self._reset_to_minimal()
        M._rebuild_field_data_outputs()
        snapshot_no_kwarg = self._snapshot()

        self._reset_to_minimal()
        M._rebuild_field_data_outputs(scope=RebuildScope.FULL)
        snapshot_full = self._snapshot()

        self.assertEqual(snapshot_no_kwarg, snapshot_full)

    def test_04_rows_only_does_not_branch_in_ri1(self) -> None:
        """RI.1 ignores scope — ROWS_ONLY must produce identical output to FULL.

        This locks the no-behavior-change invariant. RI.4 will introduce
        the branching; until then, every scope value must produce the
        FULL-scope output.
        """
        self._reset_to_minimal()
        M._rebuild_field_data_outputs(scope=RebuildScope.FULL)
        snapshot_full = self._snapshot()

        self._reset_to_minimal()
        M._rebuild_field_data_outputs(scope=RebuildScope.ROWS_ONLY)
        snapshot_rows_only = self._snapshot()

        self.assertEqual(snapshot_full, snapshot_rows_only)

    def test_05_all_scope_values_accepted_without_raise(self) -> None:
        """Every documented scope value is accepted as kwarg without raising."""
        for scope in (
            RebuildScope.FULL,
            RebuildScope.ROWS_ONLY,
            RebuildScope.METADATA_ONLY,
            RebuildScope.RESET,
        ):
            with self.subTest(scope=scope):
                self._reset_to_minimal()
                try:
                    M._rebuild_field_data_outputs(scope=scope)
                except Exception as exc:
                    self.fail(f"Unexpected exception for scope={scope}: {exc!r}")


if __name__ == "__main__":
    unittest.main()
