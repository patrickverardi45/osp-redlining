"""Contract tests: Phase 6 REVIEW acceptance lane.

The engine generates a SOURCE-SUPPORTED REVIEW redline candidate (rendered, real FINAL_REDLINE_PNG); a
human ACCEPTS or REJECTS it WITHOUT drawing geometry. REVIEW is a first-class product output, never AUTO.

Self-contained + name-free (mirrors test_uploaded_corpus_engine_handoff): the heavy engine (`_run_engine`)
and the renderer (`render_redline_stroke`) are monkeypatched with synthetic results so the accept/reject
state machine + provenance + job-local-bundle facts are exercised deterministically. No real
customer/project/location/operator name appears anywhere.
"""
from __future__ import annotations

import base64
import json

import pytest

from truelinev2.contracts.customer_project import create_customer_project
from truelinev2.contracts.processing_job import create_job, job_dir, load_job
from truelinev2.contracts.upload_pipeline import accept_upload
from truelinev2.contracts.extracted_row import CONFIRMED, MANUAL_ENTRY, new_extracted_row
from truelinev2.contracts.reviewed_bore_log import (
    GROUPING_CONFIRMED, SEPARATE_BORE, add_extracted_rows, create_reviewed_bore_log,
    define_segment_group, review_row_in_log, set_grouping_status,
)
from truelinev2.contracts import uploaded_corpus_engine_handoff as uce
from truelinev2.contracts import review_acceptance as ra
from truelinev2.schema.models import Bore, Callout, Placement, PlacementStatus

AT = "2026-06-22T00:00:00Z"
BY = "op-1"
CP = "cp-0001"
JOB = "job-0001"
RBL = "rbl-1"
CID = "rc-rbl-1"                      # _candidate_id(RBL)

# A real minimal 1-page PDF (the render path opens PlanPdf for real; the renderer is monkeypatched).
_PDF = base64.b64decode(
    "JVBERi0xLjcKJcK1wrYKJSBXcml0dGVuIGJ5IE11UERGIDEuMjcuMgoKMSAwIG9iago8PC9UeXBlL0NhdGFsb2cvUGFnZXMg"
    "MiAwIFIvSW5mbzw8L1Byb2R1Y2VyKE11UERGIDEuMjcuMik+Pj4+CmVuZG9iagoKMiAwIG9iago8PC9UeXBlL1BhZ2VzL0Nv"
    "dW50IDEvS2lkc1s0IDAgUl0+PgplbmRvYmoKCjMgMCBvYmoKPDw+PgplbmRvYmoKCjQgMCBvYmoKPDwvVHlwZS9QYWdlL01l"
    "ZGlhQm94WzAgMCA2MTIgNzkyXS9Sb3RhdGUgMC9SZXNvdXJjZXMgMyAwIFIvUGFyZW50IDIgMCBSPj4KZW5kb2JqCgp4cmVm"
    "CjAgNQowMDAwMDAwMDAwIDY1NTM1IGYgCjAwMDAwMDAwNDIgMDAwMDAgbiAKMDAwMDAwMDEyMCAwMDAwMCBuIAowMDAwMDAw"
    "MTcyIDAwMDAwIG4gCjAwMDAwMDAxOTMgMDAwMDAgbiAKCnRyYWlsZXIKPDwvU2l6ZSA1L1Jvb3QgMSAwIFIvSURbPDI1QzNB"
    "MjRFNEVDMjgwQzJBQzY1QzM4NEMzQTJDMjg1PjwxQjAyRUMzMkUxRDMwNUYzNDJBRjZFMjI2MkYzNTZDND5dPj4Kc3RhcnR4"
    "cmVmCjI4NAolJUVPRgo=")
_BORE = b"bore-log content"
_NA_MATCHLINE = {"verdict": "N/A", "caveats": [], "evidence": []}


def _job(tmp, *, with_plan=True, with_bore=True, ready=True):
    create_customer_project(tmp, CP, "Label", AT)
    create_job(tmp, CP, JOB, AT, BY)
    if with_plan:
        accept_upload(tmp, CP, JOB, kind="PLAN_PDF", filename="plan.pdf", content=_PDF, stored_at=AT)
    if with_bore:
        bore = accept_upload(tmp, CP, JOB, kind="BORE_LOG", filename="log.xlsx", content=_BORE, stored_at=AT)
        create_reviewed_bore_log(tmp, CP, JOB, bore["upload_id"], RBL, at=AT, by=BY)
        row = new_extracted_row("row-1", bore["upload_id"], raw={"s": "0+00"}, normalized={"s": "0+00"},
                                extraction_method=MANUAL_ENTRY, at=AT, by=BY)
        add_extracted_rows(tmp, CP, JOB, RBL, [row], at=AT, by=BY)
        if ready:
            review_row_in_log(tmp, CP, JOB, RBL, "row-1", CONFIRMED, at=AT, by=BY)
            define_segment_group(tmp, CP, JOB, RBL, "g-1", ["row-1"], SEPARATE_BORE, at=AT, by=BY)
            set_grouping_status(tmp, CP, JOB, RBL, "g-1", GROUPING_CONFIRMED, at=AT, by=BY)


def _bore(sheet_refs=(11,)):
    return Bore(bore_id="log.xlsx", project=None, source_file="log.xlsx", sheet_refs=list(sheet_refs),
                station_start="19+76", station_end="20+47", station_start_ft=1976.0,
                station_end_ft=2047.0, span_ft=71.0)


def _placement(status, *, with_callout=True, reason="DRAWN_EXTENT_COVERS_SPAN_NOT_TIGHT", caveats=(),
               sheets=(11,), callout_sheet=11):
    callouts = []
    if with_callout:
        callouts = [Callout(sheet=callout_sheet, page=callout_sheet, from_sta="19+84", to_sta="20+24",
                            from_ft=1984.0, to_ft=2024.0, footage=40.0,
                            text="DRAWN DIRECTIONAL BORE 19+84->20+24",
                            bbox=[100.0, 200.0, 300.0, 205.0], dialect="generic")]
    return Placement(bore_id="log.xlsx", status=status, tier="t", reason=reason,
                     sheets=list(sheets), caveats=list(caveats),
                     abstain_reason=("no drawn bore over span" if status == PlacementStatus.ABSTAIN else None),
                     matched_callouts=callouts)


def _patch_engine(monkeypatch, *, placement, bore=None, extra_legs=(), matchline=None, dialect="generic"):
    b = bore if bore is not None else _bore()
    ml = matchline if matchline is not None else _NA_MATCHLINE
    monkeypatch.setattr(uce, "_run_engine",
                        lambda plan_path, borelog_path: (b, placement, 0, dialect, list(extra_legs), ml))


def _patch_render(monkeypatch):
    def fake_render(plan, bore_id, sheet, offset, stroke_points, *, status, reason, out_dir):
        import os
        os.makedirs(out_dir, exist_ok=True)
        p = os.path.join(out_dir, "%s_s%d_redline_stroke.png" % (bore_id, sheet))
        with open(p, "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n" + b"render(%s)" % status.encode())
        return p
    monkeypatch.setattr(uce, "render_redline_stroke", fake_render)


def _published_manifest(tmp, bundle_id):
    mpath = job_dir(tmp, CP, JOB) / "bundle_store" / "bundles" / bundle_id / "redline_manifest.json"
    return json.loads(mpath.read_text(encoding="utf-8"))


def _review_job(tmp, monkeypatch, **pl):
    _job(tmp)
    _patch_engine(monkeypatch, placement=_placement(PlacementStatus.REVIEW, **pl))
    _patch_render(monkeypatch)


# --------------------------------------------------------------------------- #
# Generate -> REVIEW_CANDIDATE
# --------------------------------------------------------------------------- #
def test_generate_creates_review_candidate_with_rendered_bundle(tmp_path, monkeypatch):
    _review_job(tmp_path, monkeypatch, caveats=["DRAWN_EXTENT_EXCEEDS_BORE_SPAN"])
    report = ra.generate_review_candidate(tmp_path, CP, JOB, at=AT, by=BY)

    assert report["tier"] == ra.TIER_REVIEW and report["runnable"] is True
    rec = report["record"]
    assert rec["status"] == ra.STATUS_REVIEW_CANDIDATE
    assert rec["candidate_id"] == CID
    assert rec["provenance"] == ra.CANDIDATE_PROVENANCE
    assert rec["candidate_origin"] == "ENGINE_GENERATED"
    assert rec["no_manual_geometry"] is True
    assert rec["placement_status"] == "REVIEW"
    # Real rendered FINAL_REDLINE_PNG bundle (job-local).
    bundle = rec["bundle"]
    assert bundle["bundle_origin"] == "UPLOADED_CORPUS_ENGINE"
    assert bundle["artifact_count"] == 1
    assert bundle["artifacts"] and all(a["kind"] == "FINAL_REDLINE_PNG" for a in bundle["artifacts"])
    assert all(a["sha256"] and a["bytes"] for a in bundle["artifacts"])
    # Why REVIEW and not AUTO is explained honestly (never an AUTO claim).
    assert rec["why_not_auto"]["auto_blocked"] is True
    assert ra.NO_PER_BORE_TERMINI in rec["why_not_auto"]["blockers"]


def test_generated_candidate_is_listable_and_loadable(tmp_path, monkeypatch):
    _review_job(tmp_path, monkeypatch)
    ra.generate_review_candidate(tmp_path, CP, JOB, at=AT, by=BY)
    listed = ra.list_review_candidates(tmp_path, CP, JOB)
    assert [r["candidate_id"] for r in listed] == [CID]
    loaded = ra.load_review_candidate(tmp_path, CP, JOB, CID)
    assert loaded["status"] == ra.STATUS_REVIEW_CANDIDATE


# --------------------------------------------------------------------------- #
# Accept
# --------------------------------------------------------------------------- #
def test_accept_transitions_to_accepted_with_human_accepted_provenance(tmp_path, monkeypatch):
    _review_job(tmp_path, monkeypatch)
    ra.generate_review_candidate(tmp_path, CP, JOB, at=AT, by=BY)

    accepted = ra.accept_review_candidate(tmp_path, CP, JOB, CID, at="2026-06-22T01:00:00Z", by="owner-1")
    assert accepted["status"] == ra.STATUS_REVIEW_ACCEPTED
    assert accepted["provenance"] == ra.ACCEPTED_PROVENANCE
    assert accepted["accepted_by"] == "owner-1" and accepted["accepted_at"] == "2026-06-22T01:00:00Z"
    assert accepted["no_manual_geometry"] is True
    # Persisted.
    assert ra.load_review_candidate(tmp_path, CP, JOB, CID)["status"] == ra.STATUS_REVIEW_ACCEPTED


def test_accepted_review_does_not_become_auto(tmp_path, monkeypatch):
    _review_job(tmp_path, monkeypatch)
    report = ra.generate_review_candidate(tmp_path, CP, JOB, at=AT, by=BY)
    bundle_id = report["record"]["bundle"]["bundle_id"]
    accepted = ra.accept_review_candidate(tmp_path, CP, JOB, CID, at=AT, by=BY)

    # The acceptance record is human-accepted REVIEW, NEVER deterministic AUTO.
    assert accepted["tier"] == ra.TIER_REVIEW
    assert accepted["placement_status"] == "REVIEW"
    assert accepted["provenance"] != "DETERMINISTIC_AUTO"
    # The published manifest stays human-adjustable REVIEW, not AUTO.
    m = _published_manifest(tmp_path, bundle_id)
    assert m["logs"][0]["provenance"] == "OWNER_CONFIRMED_HUMAN_ADJUSTABLE"
    assert m["provenance_counts"]["DETERMINISTIC_AUTO"] == 0


def test_accept_is_idempotent(tmp_path, monkeypatch):
    _review_job(tmp_path, monkeypatch)
    ra.generate_review_candidate(tmp_path, CP, JOB, at=AT, by=BY)
    a1 = ra.accept_review_candidate(tmp_path, CP, JOB, CID, at=AT, by=BY)
    a2 = ra.accept_review_candidate(tmp_path, CP, JOB, CID, at="2026-06-22T02:00:00Z", by="x")
    assert a2["status"] == ra.STATUS_REVIEW_ACCEPTED
    assert a2["accepted_at"] == a1["accepted_at"]            # not re-stamped


# --------------------------------------------------------------------------- #
# Reject
# --------------------------------------------------------------------------- #
def test_reject_transitions_with_reason(tmp_path, monkeypatch):
    _review_job(tmp_path, monkeypatch)
    ra.generate_review_candidate(tmp_path, CP, JOB, at=AT, by=BY)
    rejected = ra.reject_review_candidate(tmp_path, CP, JOB, CID, reason="route looks off near the vault",
                                          at=AT, by="owner-1")
    assert rejected["status"] == ra.STATUS_REVIEW_REJECTED
    assert rejected["rejection_reason"] == "route looks off near the vault"
    assert rejected["rejected_by"] == "owner-1"


def test_reject_requires_a_reason(tmp_path, monkeypatch):
    _review_job(tmp_path, monkeypatch)
    ra.generate_review_candidate(tmp_path, CP, JOB, at=AT, by=BY)
    for bad in ("", "   "):
        with pytest.raises(ra.ReviewAcceptanceError):
            ra.reject_review_candidate(tmp_path, CP, JOB, CID, reason=bad, at=AT, by=BY)
    assert ra.load_review_candidate(tmp_path, CP, JOB, CID)["status"] == ra.STATUS_REVIEW_CANDIDATE


def test_rejected_review_remains_rejected_and_cannot_be_accepted(tmp_path, monkeypatch):
    _review_job(tmp_path, monkeypatch)
    ra.generate_review_candidate(tmp_path, CP, JOB, at=AT, by=BY)
    ra.reject_review_candidate(tmp_path, CP, JOB, CID, reason="needs correction", at=AT, by=BY)
    with pytest.raises(ra.ReviewAcceptanceStateError):
        ra.accept_review_candidate(tmp_path, CP, JOB, CID, at=AT, by=BY)
    assert ra.load_review_candidate(tmp_path, CP, JOB, CID)["status"] == ra.STATUS_REVIEW_REJECTED


def test_accepted_review_cannot_be_rejected(tmp_path, monkeypatch):
    _review_job(tmp_path, monkeypatch)
    ra.generate_review_candidate(tmp_path, CP, JOB, at=AT, by=BY)
    ra.accept_review_candidate(tmp_path, CP, JOB, CID, at=AT, by=BY)
    with pytest.raises(ra.ReviewAcceptanceStateError):
        ra.reject_review_candidate(tmp_path, CP, JOB, CID, reason="changed my mind", at=AT, by=BY)


# --------------------------------------------------------------------------- #
# Provenance + caveats preserved (two-sheet, matchline UNVERIFIED)
# --------------------------------------------------------------------------- #
def test_caveats_and_blockers_preserved_for_cross_sheet_unverified(tmp_path, monkeypatch):
    _job(tmp_path)
    bore = _bore(sheet_refs=(10, 11))
    placement = _placement(PlacementStatus.REVIEW, sheets=(10,), callout_sheet=10)
    extra = [{"sheet": 11, "stroke_points": [(110.0, 300.0), (260.0, 302.0)]}]
    matchline = {"verdict": "UNVERIFIED",
                 "caveats": [uce.MATCHLINE_CONTINUATION_UNVERIFIED, uce.MATCHLINE_SHEET_ADJACENCY_CONFIRMED],
                 "evidence": [{"pair": [10, 11], "see_sheet_a_to_b": True, "see_sheet_b_to_a": True,
                               "shared_boundary_station_ft": None}]}
    _patch_engine(monkeypatch, placement=placement, bore=bore, extra_legs=extra, matchline=matchline)
    _patch_render(monkeypatch)

    rec = ra.generate_review_candidate(tmp_path, CP, JOB, at=AT, by=BY)["record"]
    assert rec["matchline_continuity"] == "UNVERIFIED"
    assert "CROSS_SHEET_CONTINUATION_REVIEW" in rec["caveats"]
    assert uce.MATCHLINE_CONTINUATION_UNVERIFIED in rec["caveats"]
    # Caveats survive acceptance unchanged (and never relabel to AUTO).
    accepted = ra.accept_review_candidate(tmp_path, CP, JOB, CID, at=AT, by=BY)
    assert "CROSS_SHEET_CONTINUATION_REVIEW" in accepted["caveats"]
    assert uce.MATCHLINE_CONTINUATION_UNVERIFIED in accepted["why_not_auto"]["blockers"]
    assert ra.NO_PER_BORE_TERMINI in accepted["why_not_auto"]["blockers"]


# --------------------------------------------------------------------------- #
# Abstain + missing inputs
# --------------------------------------------------------------------------- #
def test_engine_abstain_records_abstained_and_blocks_accept(tmp_path, monkeypatch):
    _job(tmp_path)
    _patch_engine(monkeypatch, placement=_placement(PlacementStatus.ABSTAIN, with_callout=False,
                                                    reason="NO_DRAWN_BORE_OVER_SPAN"))
    report = ra.generate_review_candidate(tmp_path, CP, JOB, at=AT, by=BY)
    assert report["tier"] == ra.TIER_ABSTAIN and report["runnable"] is False
    rec = report["record"]
    assert rec["status"] == ra.STATUS_ABSTAINED
    assert rec["bundle"] is None
    assert "ENGINE_ABSTAINED" in {b["code"] for b in rec["blockers"]}
    with pytest.raises(ra.ReviewAcceptanceStateError):
        ra.accept_review_candidate(tmp_path, CP, JOB, CID, at=AT, by=BY)


def test_missing_inputs_make_no_record(tmp_path, monkeypatch):
    _job(tmp_path, with_plan=False, ready=False)
    monkeypatch.setattr(uce, "_run_engine",
                        lambda *a, **k: pytest.fail("engine must not run when inputs are missing"))
    report = ra.generate_review_candidate(tmp_path, CP, JOB, at=AT, by=BY)
    assert report["tier"] is None and report["runnable"] is False
    assert report["record"] is None
    assert "NO_PLAN_PDF_UPLOAD" in {b["code"] for b in report["blockers"]}
    assert ra.list_review_candidates(tmp_path, CP, JOB) == []


# --------------------------------------------------------------------------- #
# Idempotent generate preserves a prior decision
# --------------------------------------------------------------------------- #
def test_regenerate_preserves_prior_decision(tmp_path, monkeypatch):
    _review_job(tmp_path, monkeypatch)
    ra.generate_review_candidate(tmp_path, CP, JOB, at=AT, by=BY)
    ra.accept_review_candidate(tmp_path, CP, JOB, CID, at=AT, by="owner-1")
    again = ra.generate_review_candidate(tmp_path, CP, JOB, at="2026-06-22T05:00:00Z", by="other")
    assert again["record"]["status"] == ra.STATUS_REVIEW_ACCEPTED       # decision not reset
    assert again["record"]["accepted_by"] == "owner-1"


# --------------------------------------------------------------------------- #
# Frontier isolation — the candidate bundle is job-local, never the deterministic 50/58
# --------------------------------------------------------------------------- #
def test_candidate_bundle_is_job_local_not_deterministic_frontier(tmp_path, monkeypatch):
    _review_job(tmp_path, monkeypatch)
    report = ra.generate_review_candidate(tmp_path, CP, JOB, at=AT, by=BY)
    m = _published_manifest(tmp_path, report["record"]["bundle"]["bundle_id"])
    assert m["mock_example"] is False
    assert m["bundle_origin"] == "UPLOADED_CORPUS_ENGINE"
    assert m["summary"]["frontier"] == "1/1"                            # job-local single-log, not 50/58
    # The job's output slots point at the engine candidate bundle (accepted FINAL_REDLINE_PNG is retrievable).
    job = load_job(tmp_path, CP, JOB)
    assert job["slots"]["redline_manifest"] is not None
    assert job["slots"]["artifact_bundle"] is not None
