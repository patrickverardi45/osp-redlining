"""Endpoint wiring tests for the default-OFF `pdf_redline_bridge_candidates` MRQ block.

Drives `match_review_queue_endpoint` in backend/main.py with the heavy engine/session bits patched
(mirrors test_pdf_first_artifact_endpoint.py: env defaults before import, patch internals). Proves:
  * flag OFF                      -> bridge key ABSENT (byte-compatible with current behavior)
  * flag ON + pdf_first_evidence  -> bridge key PRESENT + composed; NO world-coordinate keys
  * flag ON but no pdf_first_evidence -> bridge key ABSENT (it requires the evidence)

COMMAND (from repo root):
    python -m pytest backend/tests/test_mrq_bridge_candidates_endpoint.py -v
"""
from __future__ import annotations

import contextlib
import json
import os
from unittest.mock import patch

os.environ.setdefault("TRUELINE_JWT_SECRET", "bridge-mrq-test-secret")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "bridge-mrq-auth-test-secret")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

from backend import main as M           # noqa: E402 — after env defaults
from app.core import pdf_first_adapter  # noqa: E402

SID = "sess-bridge-itest"

_EVIDENCE = {
    "schema_version": "pdf-first-evidence-1", "status": "OK",
    "source": {"plan_pdf": "Brenham.pdf"},
    "placements": [], "fail_safe": [],
    "review_items": [{
        "log_ids": ["bore_log56"], "tier": "MATCHLINE_FRAME_RESOLVER", "surface": "review",
        "sheets": [17], "station_range": {"start": "0+00", "end": "2+76"},
        "geo": {"frame": {"page": 17},
                "geo_anchors": [{"kind": "AP", "id": "AP-120", "coord": [254.0, 424.0]}]},
    }],
}
_RENDER = {"points": [{"feature_id": "TX-AP120_pt", "name": "AP-120",
                       "classification": "terminal_port_handhole"}], "lines": [], "polygons": []}
_MRQ = {"schema_version": "mrq", "row_count": 1,
        "rows": [{"source_file": "bore_log56.xlsx", "selected_route_id": "route_123",
                  "selected_route_name": "Main St", "group_id": "G1"}]}
_STATE = {
    "pipeline_diag": [],
    "committed_rows": [{"source_file": "bore_log56.xlsx", "station": "0+00"}],
    "kmz_semantic": {"features": [{"feature_id": "X"}]},   # presence only; render is patched
}


def _body(resp):
    return json.loads(resp.body)


@contextlib.contextmanager
def _harness():
    """Patch session scope + STATE + queue + plan resolver + heavy builders (engine/render)."""
    with patch.object(M, "_session_scope", lambda _sid: contextlib.nullcontext()), \
         patch.object(M, "STATE", dict(_STATE)), \
         patch.object(M, "_assemble_match_review_queue", lambda *a, **k: dict(_MRQ)), \
         patch.object(M, "_resolve_engineering_plan_pdf_paths", lambda _sid: ["/fake/plan.pdf"]), \
         patch.object(M, "_build_kmz_render_payload", lambda _sem: dict(_RENDER)), \
         patch.object(pdf_first_adapter, "build_session_evidence_from_committed_rows",
                      lambda *a, **k: dict(_EVIDENCE)):
        yield


def test_flag_off_no_bridge_key(monkeypatch):
    monkeypatch.delenv("TRUELINE_PDF_KMZ_BRIDGE_BUILDER", raising=False)
    monkeypatch.delenv("TRUELINE_PDF_FIRST_ENGINE", raising=False)
    with _harness():
        body = _body(M.match_review_queue_endpoint(session_id=SID))
    assert body.get("success") is True
    assert "pdf_redline_bridge_candidates" not in body     # byte-compat: absent when OFF


def test_flag_on_bridge_key_present(monkeypatch):
    monkeypatch.setenv("TRUELINE_PDF_FIRST_ENGINE", "1")
    monkeypatch.setenv("TRUELINE_PDF_KMZ_BRIDGE_BUILDER", "1")
    monkeypatch.delenv("TRUELINE_MRQ_EVIDENCE_CACHE", raising=False)
    with _harness():
        body = _body(M.match_review_queue_endpoint(session_id=SID))
    assert "pdf_first_evidence" in body
    block = body.get("pdf_redline_bridge_candidates")
    assert block and block["schema_version"] == "pdf-redline-bridge-candidates-1"
    assert block["identity_index"]["source"] == "render_only"
    cands = block["candidates"]
    assert len(cands) == 1 and cands[0]["status"] == "candidate"
    assert cands[0]["kmz_candidate_feature_id"] == "TX-AP120_pt"
    assert cands[0]["map_candidate_route_id"] == "route_123"
    for c in cands:
        for k in ("lat", "lon", "lonlat", "coord", "coords", "geometry", "segments", "polyline"):
            assert k not in c


def test_flag_on_but_no_pdf_first_evidence_no_bridge_key(monkeypatch):
    # The bridge block requires pdf_first_evidence; with the PDF-first engine OFF there is none.
    monkeypatch.delenv("TRUELINE_PDF_FIRST_ENGINE", raising=False)
    monkeypatch.setenv("TRUELINE_PDF_KMZ_BRIDGE_BUILDER", "1")
    with _harness():
        body = _body(M.match_review_queue_endpoint(session_id=SID))
    assert "pdf_redline_bridge_candidates" not in body
