"""Match Review Queue endpoint — lean response (504 fix).

After a completed rebuild the session is ~18 MB; the /match-review panel was
504'ing. The endpoint now (a) uses a READ-ONLY session scope (no 18 MB re-persist
on a pure read) and (b) strips heavy, UI-unused internals (safety_net_log,
evidence_summary.evidence_resolver_tag, kmz_address_cluster_evidence) from rows
unless ?include_internals=1.

This locks: the DEFAULT response excludes those heavy internals and is far smaller
than the full one, while still carrying every field the panel renders; and
include_internals=True restores the full detail.

Drives the endpoint directly (no TestClient/auth). Run from repo root:
    python -m pytest backend/tests/test_mrq_lean_response.py -v
"""
from __future__ import annotations

import json
import os
import pathlib
import tempfile
import unittest

os.environ.setdefault("TRUELINE_JWT_SECRET", "mrq-lean-test")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "mrq-lean-auth")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")
os.environ["OSP_UPLOAD_DIR"] = tempfile.mkdtemp(prefix="mrq_lean_")

from backend import main as M  # noqa: E402 — after env defaults

# Hard-isolate the session DB regardless of import order.
_TMP = pathlib.Path(tempfile.mkdtemp(prefix="mrq_lean_iso_"))
M.SESSION_DB_PATH = _TMP / "session_store.db"
M._init_session_db()

_PAD = "x" * 5000  # makes the heavy internals measurably large


def _seed_session(sid):
    # One abstained group that exercises evidence_summary + safety_net_log,
    # padded so the heavy internals dominate the row size.
    entry = {
        "source_file": "bore_log38.xlsx",
        "group_id": "g38",
        "stopped_at": "abstained_location_evidence_mismatch",
        "render_allowed": False,
        "selected_route_id": "",
        "strict_top5": [{"route_id": "route_1", "score": 0.12, "route_name": "R1"}],
        "print_filter": {"print_tokens": ["38"], "applied": True},
        "strict_allowed_route_ids": ["route_1"],
        "location_evidence_mismatch": {"notes_streets": ["CHERI LN"], "pad": _PAD},
        "evidence_resolver": {"decision": "ABSTAIN_CONFLICT", "confidence": 0.13, "pad": _PAD},
        "location_mismatch_rescue_selected": {"rescued_route_id": "route_2", "pad": _PAD},
        "auto_candidate_expansion": {"pad": _PAD},
    }
    with M._session_scope(sid):
        M.STATE["pipeline_diag"] = [entry]


def _call(sid, include_internals):
    resp = M.match_review_queue_endpoint(session_id=sid, include_internals=include_internals)
    body = json.loads(bytes(resp.body).decode())
    return resp, body


class TestMrqLeanResponse(unittest.TestCase):
    def test_default_excludes_heavy_internals_but_keeps_ui_fields(self):
        sid = "mrq-lean-default"
        _seed_session(sid)
        resp, body = _call(sid, include_internals=False)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(body.get("success"))
        rows = body.get("rows") or []
        self.assertEqual(len(rows), 1)
        row = rows[0]
        # heavy internals stripped
        self.assertNotIn("safety_net_log", row)
        es = row.get("evidence_summary") or {}
        self.assertNotIn("evidence_resolver_tag", es)
        self.assertNotIn("kmz_address_cluster_evidence", es)
        # UI-rendered fields preserved
        self.assertEqual(row.get("status"), "abstained")
        self.assertEqual(row.get("priority"), "high")
        self.assertIn("top_3_alternates", row)
        self.assertEqual(es.get("print_tokens"), ["38"])
        self.assertEqual(es.get("allowed_route_ids"), ["route_1"])

    def test_include_internals_restores_heavy_fields(self):
        sid = "mrq-lean-full"
        _seed_session(sid)
        _, body = _call(sid, include_internals=True)
        row = (body.get("rows") or [])[0]
        self.assertIn("safety_net_log", row)
        self.assertTrue(len(row["safety_net_log"]) > 0)
        es = row.get("evidence_summary") or {}
        self.assertIn("evidence_resolver_tag", es)
        self.assertIn("kmz_address_cluster_evidence", es)

    def test_lean_response_is_much_smaller(self):
        sid = "mrq-lean-size"
        _seed_session(sid)
        _, lean = _call(sid, include_internals=False)
        _, full = _call(sid, include_internals=True)
        lean_bytes = len(json.dumps(lean))
        full_bytes = len(json.dumps(full))
        # The 4 padded internals (~20 KB) are gone from the lean response.
        self.assertLess(lean_bytes, full_bytes)
        self.assertLess(lean_bytes, full_bytes - 15000)


if __name__ == "__main__":
    unittest.main()
