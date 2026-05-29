"""Engineering-plan upload session-binding resolver — unit tests.

Locks the fix for the session-binding bug where an engineering-plan PDF was
orphaned onto a freshly minted session (active workspace showed
engineering_plans=0). The resolver MUST:

- prefer the multipart form `session_id`,
- fall back to the URL query `session_id` (survives the direct-to-Render
  multipart path where the form field can be dropped),
- return None when neither is present (caller returns a clear error; NEVER mints).
"""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("TRUELINE_JWT_SECRET", "test-eng-plan-binding")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

from backend.main import _resolve_engineering_plan_session_id  # noqa: E402


class TestEngineeringPlanSessionBinding(unittest.TestCase):
    def test_form_session_id_wins(self):
        self.assertEqual(
            _resolve_engineering_plan_session_id("dfd4aa94", "other"), "dfd4aa94"
        )

    def test_form_blank_falls_back_to_query(self):
        self.assertEqual(
            _resolve_engineering_plan_session_id("", "dfd4aa94"), "dfd4aa94"
        )
        self.assertEqual(
            _resolve_engineering_plan_session_id(None, "dfd4aa94"), "dfd4aa94"
        )

    def test_both_blank_returns_none_never_mints(self):
        self.assertIsNone(_resolve_engineering_plan_session_id(None, None))
        self.assertIsNone(_resolve_engineering_plan_session_id("", ""))
        self.assertIsNone(_resolve_engineering_plan_session_id("   ", "  "))

    def test_whitespace_is_stripped(self):
        self.assertEqual(
            _resolve_engineering_plan_session_id("  dfd4aa94  ", None), "dfd4aa94"
        )
        self.assertEqual(
            _resolve_engineering_plan_session_id("  ", "  dfd4aa94 "), "dfd4aa94"
        )

    def test_returns_deterministic_not_random(self):
        # Unlike _resolve_session_id (which mints uuid4 on blank), this never
        # invents an id — two blank calls both return None.
        self.assertEqual(
            _resolve_engineering_plan_session_id(None, None),
            _resolve_engineering_plan_session_id(None, None),
        )


if __name__ == "__main__":
    unittest.main()
