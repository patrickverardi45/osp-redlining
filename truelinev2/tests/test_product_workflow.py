"""Phase 9 contract tests — the product workflow orchestrator (3-path redline + closeout assembly).

Proves the seam that connects an uploaded product job to the PROVEN redline capability:
  * RECOGNIZED_DETERMINISTIC — a recognized package serves the EXISTING committed deterministic render (real
    FINAL_REDLINE_PNG, DETERMINISTIC_AUTO), advances the job to PLACED, then assembles a closeout/export
    package that reaches READY; KMZ is honestly BLOCKED (pixel-only) and OMITTED — never faked.
  * ABSTAIN — a package that is neither recognized nor placeable reports the SPECIFIC reasons from BOTH
    sources (recognition + engine), renders nothing, never advances the lifecycle, and cannot be accepted.
  * REVIEW acceptance gate — a REVIEW redline must be human-accepted before it is packaged.

Self-contained + name-free (mirrors test_recognized_corpus_handoff): the deterministic render dir is
monkeypatched and the registry is an injected fixture, so the test ships its own PDF/PNG bytes.
"""
from __future__ import annotations

import base64
import hashlib

import pytest

from truelinev2.contracts.customer_project import create_customer_project
from truelinev2.contracts.processing_job import (
    CLOSEOUT_REVIEW, CREATED, PLACED, create_job, load_job,
)
from truelinev2.contracts.upload_pipeline import accept_upload
from truelinev2.contracts.extracted_row import CONFIRMED, MANUAL_ENTRY, new_extracted_row
from truelinev2.contracts.reviewed_bore_log import (
    GROUPING_CONFIRMED, SEPARATE_BORE, add_extracted_rows, create_reviewed_bore_log,
    define_segment_group, review_row_in_log, set_grouping_status,
)
from truelinev2.contracts import recognized_corpus_handoff as rch
from truelinev2.contracts import review_acceptance as ra
from truelinev2.contracts import product_workflow as pw

AT = "2026-06-23T00:00:00Z"
BY = "op-1"
CP = "cp-0001"
JOB = "job-0001"
RBL = "rbl-1"

# Minimal valid 1-page PDF (no dialect text) + 1x1 PNG stand-in for a committed deterministic render.
_PDF = base64.b64decode(
    "JVBERi0xLjcKJcK1wrYKJSBXcml0dGVuIGJ5IE11UERGIDEuMjcuMgoKMSAwIG9iago8PC9UeXBlL0NhdGFsb2cvUGFnZXMg"
    "MiAwIFIvSW5mbzw8L1Byb2R1Y2VyKE11UERGIDEuMjcuMik+Pj4+CmVuZG9iagoKMiAwIG9iago8PC9UeXBlL1BhZ2VzL0Nv"
    "dW50IDEvS2lkc1s0IDAgUl0+PgplbmRvYmoKCjMgMCBvYmoKPDw+PgplbmRvYmoKCjQgMCBvYmoKPDwvVHlwZS9QYWdlL01l"
    "ZGlhQm94WzAgMCA2MTIgNzkyXS9Sb3RhdGUgMC9SZXNvdXJjZXMgMyAwIFIvUGFyZW50IDIgMCBSPj4KZW5kb2JqCgp4cmVm"
    "CjAgNQowMDAwMDAwMDAwIDY1NTM1IGYgCjAwMDAwMDAwNDIgMDAwMDAgbiAKMDAwMDAwMDEyMCAwMDAwMCBuIAowMDAwMDAw"
    "MTcyIDAwMDAwIG4gCjAwMDAwMDAxOTMgMDAwMDAgbiAKCnRyYWlsZXIKPDwvU2l6ZSA1L1Jvb3QgMSAwIFIvSURbPDI1QzNB"
    "MjRFNEVDMjgwQzJBQzY1QzM4NEMzQTJDMjg1PjwxQjAyRUMzMkUxRDMwNUYzNDJBRjZFMjI2MkYzNTZDND5dPj4Kc3RhcnR4"
    "cmVmCjI4NAolJUVPRgo=")
_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
_BORE = b"recognized-by-sha256-only"


def _engine_ready_job(tmp, *, with_rbl=True):
    """A job with a PLAN_PDF + a BORE_LOG; optionally an engine-ready reviewed_bore_log (sha-recognized)."""
    create_customer_project(tmp, CP, "Label", AT)
    create_job(tmp, CP, JOB, AT, BY)
    accept_upload(tmp, CP, JOB, kind="PLAN_PDF", filename="plan.pdf", content=_PDF, stored_at=AT)
    bore = accept_upload(tmp, CP, JOB, kind="BORE_LOG", filename="bore_log8.xlsx",
                         content=_BORE, stored_at=AT)
    if not with_rbl:
        return
    create_reviewed_bore_log(tmp, CP, JOB, bore["upload_id"], RBL, at=AT, by=BY)
    row = new_extracted_row("row-1", bore["upload_id"], raw={"s": "0+00"}, normalized={"s": "0+00"},
                            extraction_method=MANUAL_ENTRY, at=AT, by=BY)
    add_extracted_rows(tmp, CP, JOB, RBL, [row], at=AT, by=BY)
    review_row_in_log(tmp, CP, JOB, RBL, "row-1", CONFIRMED, at=AT, by=BY)
    define_segment_group(tmp, CP, JOB, RBL, "g-1", ["row-1"], SEPARATE_BORE, at=AT, by=BY)
    set_grouping_status(tmp, CP, JOB, RBL, "g-1", GROUPING_CONFIRMED, at=AT, by=BY)


def _registry(tmp_path, monkeypatch, *, recognize_plan, map_bore):
    """Patch the committed render dir to a tmp dir with two log8 PNGs + build an injectable registry."""
    rdir = tmp_path / "render"
    rdir.mkdir()
    (rdir / "log8_s18_redline_stroke.png").write_bytes(_PNG)
    (rdir / "log8_s22_redline_stroke.png").write_bytes(_PNG)
    monkeypatch.setattr(rch, "_DETERMINISTIC_RENDER_DIR", rdir)
    corpora = []
    if recognize_plan:
        corpora.append({
            "corpus_id": "recognized-corpus-001", "display_name": "Test Corpus",
            "plan_sha256": [hashlib.sha256(_PDF).hexdigest()],
            "bore_log_sha256_to_log": ({hashlib.sha256(_BORE).hexdigest(): "log8"} if map_bore else {}),
            "log_facts": {"log8": {"parent_id": "bore_log8",
                                   "span": {"start_station": "0+00", "end_station": "3+90",
                                            "label": "0+00->3+90"}}},
        })
    return {"corpora": corpora, "configured": True}


# --------------------------------------------------------------------------- #
# A. Recognized deterministic path — the Phase 8C fix: a recognized package serves the PROVEN render.
# --------------------------------------------------------------------------- #
def test_recognized_package_runs_deterministic_then_packages(tmp_path, monkeypatch):
    reg = _registry(tmp_path, monkeypatch, recognize_plan=True, map_bore=True)
    _engine_ready_job(tmp_path)

    out = pw.run_product_redline(tmp_path, CP, JOB, registry=reg, at=AT, by=BY)
    assert out["path"] == pw.PATH_RECOGNIZED
    assert out["runnable"] is True and out["rendered"] is True
    assert out["provenance"] == "DETERMINISTIC_AUTO"
    assert out["deterministic_log_id"] == "log8"
    assert out["render"]["artifact_count"] == 2
    assert all(a["kind"] == "FINAL_REDLINE_PNG" for a in out["render"]["artifacts"])
    # A successful render advances the job to PLACED (so the closeout/export chain is reachable).
    assert load_job(tmp_path, CP, JOB)["status"] == PLACED

    pkg = pw.assemble_closeout_package(tmp_path, CP, JOB, at=AT, by=BY)
    assert pkg["assembled"] is True and pkg["blocker"] is None
    assert pkg["closeout_status"] == "READY_FOR_APPROVAL"          # clean spine, no privileged approve needed
    assert pkg["export_status"] == "READY"                         # FINAL needs privileged approve (deferred)
    # The redline artifacts + manifest are referenced in the package descriptor.
    assert "REDLINE_ARTIFACTS" in pkg["export_view"]["included_sections"]
    assert "REDLINE_MANIFEST" in pkg["export_view"]["included_sections"]
    # KMZ is honestly blocked (pixel-only) and OMITTED — never faked.
    assert pkg["kmz_status"] == "BLOCKED"
    assert pkg["kmz_geometry_basis"] == "UNSUPPORTED_PIXEL_ONLY"
    assert "KMZ_EXPORT" in pkg["export_view"]["omitted_sections"]
    assert load_job(tmp_path, CP, JOB)["status"] == CLOSEOUT_REVIEW


def test_recognized_then_redline_is_idempotent(tmp_path, monkeypatch):
    reg = _registry(tmp_path, monkeypatch, recognize_plan=True, map_bore=True)
    _engine_ready_job(tmp_path)
    a = pw.run_product_redline(tmp_path, CP, JOB, registry=reg, at=AT, by=BY)
    b = pw.run_product_redline(tmp_path, CP, JOB, registry=reg, at=AT, by=BY)
    assert a["render"]["bundle_id"] == b["render"]["bundle_id"]    # same committed render, same bundle
    assert load_job(tmp_path, CP, JOB)["status"] == PLACED


# --------------------------------------------------------------------------- #
# C. Abstain path — specific reasons from BOTH sources; nothing rendered; lifecycle untouched.
# --------------------------------------------------------------------------- #
def test_unrecognized_unplaceable_abstains_with_specific_reasons(tmp_path, monkeypatch):
    reg = _registry(tmp_path, monkeypatch, recognize_plan=False, map_bore=False)
    _engine_ready_job(tmp_path, with_rbl=False)                    # no engine-ready reviewed bore-log

    out = pw.run_product_redline(tmp_path, CP, JOB, registry=reg, at=AT, by=BY)
    assert out["path"] == pw.PATH_ABSTAIN
    assert out["runnable"] is False and out["rendered"] is False
    sources = {b["source"] for b in out["blockers"]}
    assert sources == {"recognition", "engine"}                   # NOT a bare single ENGINE_ABSTAINED
    codes = {b["code"] for b in out["blockers"]}
    assert "UPLOADED_CORPUS_NOT_RECOGNIZED" in codes
    assert "NO_ENGINE_READY_REVIEWED_BORE_LOG" in codes
    # No render => no lifecycle advance (stays CREATED); no acceptable candidate.
    assert load_job(tmp_path, CP, JOB)["status"] == CREATED


# --------------------------------------------------------------------------- #
# B. REVIEW acceptance gate — a REVIEW redline must be accepted before it is packaged.
# --------------------------------------------------------------------------- #
def _inject_review_candidate(tmp, status):
    rec = ra._new_record(candidate_id="rc-%s" % RBL, customer_project_id=CP, job_id=JOB,
                         reviewed_bore_log_id=RBL, tier=ra.TIER_REVIEW, status=status,
                         provenance=ra.CANDIDATE_PROVENANCE, at=AT, by=BY)
    ra._write(tmp, rec)


def test_pending_review_blocks_closeout_until_accepted(tmp_path):
    create_customer_project(tmp_path, CP, "Label", AT)
    create_job(tmp_path, CP, JOB, AT, BY)
    _inject_review_candidate(tmp_path, ra.STATUS_REVIEW_CANDIDATE)

    blocked = pw.assemble_closeout_package(tmp_path, CP, JOB, at=AT, by=BY)
    assert blocked["assembled"] is False
    assert blocked["blocker"] == pw.REVIEW_NOT_ACCEPTED
    assert load_job(tmp_path, CP, JOB)["status"] == CREATED        # gate runs BEFORE any lifecycle advance

    ra.accept_review_candidate(tmp_path, CP, JOB, "rc-%s" % RBL, at=AT, by=BY)
    passed = pw.assemble_closeout_package(tmp_path, CP, JOB, at=AT, by=BY)
    assert passed["blocker"] is None                              # gate passed (downstream closeout may still block)


def test_rejected_review_cannot_be_packaged(tmp_path):
    create_customer_project(tmp_path, CP, "Label", AT)
    create_job(tmp_path, CP, JOB, AT, BY)
    _inject_review_candidate(tmp_path, ra.STATUS_REVIEW_REJECTED)
    out = pw.assemble_closeout_package(tmp_path, CP, JOB, at=AT, by=BY)
    assert out["assembled"] is False and out["blocker"] == pw.REVIEW_WAS_REJECTED


def test_recognized_render_not_blocked_by_stale_abstain(tmp_path, monkeypatch):
    # A job recognized as a deterministic package must NOT be blocked at closeout by a stale ABSTAINED record
    # from a prior REVIEW attempt (the Phase 8C job-jsy03x case). The deterministic render is authoritative.
    reg = _registry(tmp_path, monkeypatch, recognize_plan=True, map_bore=True)
    _engine_ready_job(tmp_path)
    out = pw.run_product_redline(tmp_path, CP, JOB, registry=reg, at=AT, by=BY)
    assert out["path"] == pw.PATH_RECOGNIZED
    _inject_review_candidate(tmp_path, ra.STATUS_ABSTAINED)        # stale abstain from a prior attempt
    pkg = pw.assemble_closeout_package(tmp_path, CP, JOB, at=AT, by=BY)
    assert pkg["assembled"] is True and pkg["blocker"] is None     # not blocked by the stale abstain
    assert pkg["export_status"] == "READY"


def test_review_gate_pure_cases():
    ok, status, code = pw._review_gate([])
    assert ok and code is None
    ok, status, code = pw._review_gate([{"status": ra.STATUS_REVIEW_ACCEPTED}])
    assert ok and code is None and status == ra.STATUS_REVIEW_ACCEPTED
    ok, status, code = pw._review_gate([{"status": ra.STATUS_REVIEW_CANDIDATE}])
    assert not ok and code == pw.REVIEW_NOT_ACCEPTED
    ok, status, code = pw._review_gate([{"status": ra.STATUS_REVIEW_REJECTED}])
    assert not ok and code == pw.REVIEW_WAS_REJECTED
    # ABSTAINED is IGNORED — it never gates a later authoritative render.
    ok, status, code = pw._review_gate([{"status": ra.STATUS_ABSTAINED}])
    assert ok and code is None
    # a stale ABSTAINED alongside an accepted REVIEW still passes (abstain filtered out).
    ok, status, code = pw._review_gate([{"status": ra.STATUS_ABSTAINED},
                                        {"status": ra.STATUS_REVIEW_ACCEPTED}])
    assert ok and code is None


def test_failed_job_cannot_advance(tmp_path):
    create_customer_project(tmp_path, CP, "Label", AT)
    create_job(tmp_path, CP, JOB, AT, BY)
    from truelinev2.contracts.processing_job import transition
    transition(tmp_path, CP, JOB, "FAILED", at=AT, by=BY, reason="test")
    with pytest.raises(pw.ProductWorkflowError):
        pw._advance_to(tmp_path, CP, JOB, PLACED, at=AT, by=BY, reason="x")
