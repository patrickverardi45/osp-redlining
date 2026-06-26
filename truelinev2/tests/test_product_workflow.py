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
from truelinev2.contracts.source_anchor import create_source_anchor
from truelinev2.render.source_anchor_render import render_job_source_anchors
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
    # SUPERSEDED is IGNORED — a human source-anchor correction replaced the engine candidate, so it is the
    # authoritative placed redline now and never gates closeout.
    ok, status, code = pw._review_gate([{"status": ra.STATUS_REVIEW_SUPERSEDED}])
    assert ok and code is None
    # but a SUPERSEDED candidate next to a still-pending sibling REVIEW still blocks on the pending one.
    ok, status, code = pw._review_gate([{"status": ra.STATUS_REVIEW_SUPERSEDED},
                                        {"status": ra.STATUS_REVIEW_CANDIDATE}])
    assert not ok and code == pw.REVIEW_NOT_ACCEPTED


def test_failed_job_cannot_advance(tmp_path):
    create_customer_project(tmp_path, CP, "Label", AT)
    create_job(tmp_path, CP, JOB, AT, BY)
    from truelinev2.contracts.processing_job import transition
    transition(tmp_path, CP, JOB, "FAILED", at=AT, by=BY, reason="test")
    with pytest.raises(pw.ProductWorkflowError):
        pw._advance_to(tmp_path, CP, JOB, PLACED, at=AT, by=BY, reason="x")


# --------------------------------------------------------------------------- #
# B(2). Uploaded REVIEW — accept then RE-RUN: the owner-reported state-sync bug. After a REVIEW candidate is
#       accepted (in ANY panel), the workflow must report it ACCEPTED + ready to assemble, never re-gate the
#       user behind a fresh acceptance and never mint a duplicate candidate.
# --------------------------------------------------------------------------- #
def _generic_review_job(tmp):
    """A job whose uploaded plan matches NO named dialect (so the generic-geometry fallback places a REVIEW
    candidate from its OWN drawn geometry) + an engine-ready reviewed bore-log. Self-contained: a station-tick
    row + ONE drawn run over the bore span, built in-process (no real CAD plan / customer corpus)."""
    import io
    import fitz
    import openpyxl
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    for ft in range(1000, 1401, 100):                          # ticks 10+00..14+00 (axis station_at(x)~=x+900)
        x = 100 + (ft - 1000) / 100 * 100
        page.draw_line((x, 400), (x, 412), color=(0, 0, 0), width=0.8)
        page.insert_text((x - 12, 426), "%d+%02d" % (ft // 100, ft % 100), fontsize=8)
    page.draw_line((250, 392), (350, 392), color=(1, 0, 0), width=1.8)   # the proposed bore ~11+50..12+50
    pbytes = io.BytesIO(); doc.save(pbytes); doc.close()
    wb = openpyxl.Workbook(); ws = wb.active
    ws.append(["station", "depth", "print"]); ws.append(["11+50", 5.0, "1"]); ws.append(["12+50", 5.0, "1"])
    bbytes = io.BytesIO(); wb.save(bbytes)

    create_customer_project(tmp, CP, "Label", AT)
    create_job(tmp, CP, JOB, AT, BY)
    accept_upload(tmp, CP, JOB, kind="PLAN_PDF", filename="plan.pdf", content=pbytes.getvalue(), stored_at=AT)
    bore = accept_upload(tmp, CP, JOB, kind="BORE_LOG", filename="bore.xlsx", content=bbytes.getvalue(),
                         stored_at=AT)
    create_reviewed_bore_log(tmp, CP, JOB, bore["upload_id"], RBL, at=AT, by=BY)
    row = new_extracted_row("row-1", bore["upload_id"], raw={"s": "x"}, normalized={"s": "x"},
                            extraction_method=MANUAL_ENTRY, at=AT, by=BY)
    add_extracted_rows(tmp, CP, JOB, RBL, [row], at=AT, by=BY)
    review_row_in_log(tmp, CP, JOB, RBL, "row-1", CONFIRMED, at=AT, by=BY)
    define_segment_group(tmp, CP, JOB, RBL, "g-1", ["row-1"], SEPARATE_BORE, at=AT, by=BY)
    set_grouping_status(tmp, CP, JOB, RBL, "g-1", GROUPING_CONFIRMED, at=AT, by=BY)


def test_uploaded_review_after_accept_is_ready_to_package(tmp_path):
    _generic_review_job(tmp_path)
    reg = {"corpora": [], "configured": True}

    first = pw.run_product_redline(tmp_path, CP, JOB, registry=reg, at=AT, by=BY)
    assert first["path"] == pw.PATH_UPLOADED_REVIEW
    assert first["requires_acceptance"] is True and first["review_accepted"] is False
    cid = first["candidate_id"]
    assert cid

    ra.accept_review_candidate(tmp_path, CP, JOB, cid, at=AT, by=BY)

    # Re-running the redline path (e.g. the owner lands on Redlines after accepting in Review) must now report
    # the SAME candidate as ACCEPTED + ready to assemble — no duplicate, no fresh acceptance gate.
    again = pw.run_product_redline(tmp_path, CP, JOB, registry=reg, at=AT, by=BY)
    assert again["candidate_id"] == cid                        # no duplicate candidate
    assert again["review_accepted"] is True and again["review_status"] == ra.STATUS_REVIEW_ACCEPTED
    assert again["requires_acceptance"] is False               # ready to assemble — user not stranded

    pkg = pw.assemble_closeout_package(tmp_path, CP, JOB, at=AT, by=BY)
    assert pkg["assembled"] is True and pkg["blocker"] is None
    assert pkg["export_status"] == "READY"


# --------------------------------------------------------------------------- #
# F. Correction lane — a LOW/wrong engine REVIEW candidate, CORRECTED by a human source-anchor render,
#    becomes packageable WITHOUT falsely "accepting" the engine's geometry (the core mission fix). The
#    correction SUPERSEDES the candidate (it never gates again) and fills the job's redline slot.
# --------------------------------------------------------------------------- #
def test_source_anchor_correction_supersedes_review_and_unblocks_closeout(tmp_path):
    _generic_review_job(tmp_path)
    reg = {"corpora": [], "configured": True}

    first = pw.run_product_redline(tmp_path, CP, JOB, registry=reg, at=AT, by=BY)
    assert first["path"] == pw.PATH_UPLOADED_REVIEW
    cid = first["candidate_id"]

    # Before correction a pending REVIEW blocks closeout — the dead-end this fix removes.
    blocked = pw.assemble_closeout_package(tmp_path, CP, JOB, at=AT, by=BY)
    assert blocked["assembled"] is False and blocked["blocker"] == pw.REVIEW_NOT_ACCEPTED

    # Human correction: capture + validate a source anchor, then render it (the customer "Correct redline
    # placement" action). This fills the job's redline slot with the human-confirmed bundle.
    plan_upload = next(u["upload_id"] for u in load_job(tmp_path, CP, JOB)["uploads"]
                       if u["kind"] == "PLAN_PDF")
    create_source_anchor(
        tmp_path, CP, JOB, source_anchor_id="sa-1", plan_upload_id=plan_upload,
        reviewed_bore_log_id=RBL, page_number=1,
        control_points=[{"x": 250.0, "y": 392.0}, {"x": 350.0, "y": 392.0}], group_id=None,
        at=AT, by=BY, page_bounds=(0.0, 0.0, 612.0, 792.0),
        start_identity={"station": "11+50"}, end_identity={"station": "12+50"})
    summary = render_job_source_anchors(tmp_path, CP, JOB, "sa-1", at=AT, by=BY)
    assert summary["status"] == "SUCCEEDED"
    assert summary["bundle_origin"] == "HUMAN_CONFIRMED_SOURCE_ANCHOR"

    # The engine candidate is now SUPERSEDED — NOT accepted (the human replaced it, never approving the
    # engine's wrong/low geometry).
    rec = ra.load_review_candidate(tmp_path, CP, JOB, cid)
    assert rec["status"] == ra.STATUS_REVIEW_SUPERSEDED
    assert rec["provenance"] == ra.SUPERSEDED_PROVENANCE

    # Re-running the redline path (the workspace lands here on rehydrate) reports placed + ready, no re-accept.
    again = pw.run_product_redline(tmp_path, CP, JOB, registry=reg, at=AT, by=BY)
    assert again["requires_acceptance"] is False and again.get("review_superseded") is True

    # Closeout/export now assembles from the human-confirmed redline — the user is no longer stranded.
    pkg = pw.assemble_closeout_package(tmp_path, CP, JOB, at=AT, by=BY)
    assert pkg["assembled"] is True and pkg["blocker"] is None
    assert pkg["export_status"] == "READY"


def test_export_gate_blocks_unaccepted_download_but_passes_resolved(tmp_path):
    # The ZIP/PDF download routes share this gate, so a pending/rejected REVIEW is never downloadable while
    # recognized/AUTO (no candidate), an accepted REVIEW, a corrected SUPERSEDED candidate, and a stale
    # ABSTAINED record all pass.
    create_customer_project(tmp_path, CP, "Label", AT)
    create_job(tmp_path, CP, JOB, AT, BY)
    ok, code = pw.export_gate(tmp_path, CP, JOB)          # no candidate (recognized/AUTO) -> packageable
    assert ok and code is None

    _inject_review_candidate(tmp_path, ra.STATUS_REVIEW_CANDIDATE)
    ok, code = pw.export_gate(tmp_path, CP, JOB)          # pending REVIEW -> blocked
    assert not ok and code == pw.REVIEW_NOT_ACCEPTED

    rec = ra.load_review_candidate(tmp_path, CP, JOB, "rc-%s" % RBL)
    rec["status"] = ra.STATUS_REVIEW_SUPERSEDED           # human-corrected -> packageable again
    ra._write(tmp_path, rec)
    ok, code = pw.export_gate(tmp_path, CP, JOB)
    assert ok and code is None
