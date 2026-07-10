"""Contract tests: default-OFF uploaded-corpus AUTO cap (owner-gated AUTO/final).

Policy: for a CUSTOMER-uploaded package, a raw engine AUTO_SELECT must NOT become a no-acceptance AUTO/final
placement by default. It is CAPPED to a high-confidence human-reviewable REVIEW candidate (requires
accept/reject); the engine's raw verdict/reason/evidence are preserved as metadata; closeout/export stays
blocked until a human accepts. The prior AUTO behavior is available ONLY behind
TL2_UPLOADED_CORPUS_AUTO_OPTIN (Settings.uploaded_corpus_auto_optin), default False.

Self-contained + name-free (mirrors test_review_acceptance_contract): the heavy engine (`_run_engine`) and
the renderer (`render_redline_stroke`) are monkeypatched with synthetic results so the cap + acceptance gate
are exercised deterministically. No engine/render/select_dialect/closeout code is modified by this policy.
"""
from __future__ import annotations

import base64

from truelinev2.contracts.customer_project import create_customer_project
from truelinev2.contracts.processing_job import create_job
from truelinev2.contracts.upload_pipeline import accept_upload
from truelinev2.contracts.extracted_row import CONFIRMED, MANUAL_ENTRY, new_extracted_row
from truelinev2.contracts.reviewed_bore_log import (
    GROUPING_CONFIRMED, SEPARATE_BORE, add_extracted_rows, create_reviewed_bore_log,
    define_segment_group, review_row_in_log, set_grouping_status,
)
from truelinev2.contracts import uploaded_corpus_engine_handoff as uce
from truelinev2.contracts import review_acceptance as ra
from truelinev2.contracts import product_workflow as pw
from truelinev2.schema.models import Bore, Callout, Placement, PlacementStatus

AT = "2026-06-22T00:00:00Z"
BY = "op-1"
CP = "cp-0001"
JOB = "job-0001"
RBL = "rbl-1"
CID = "rc-rbl-1"                      # _candidate_id(RBL)
AUTO_REASON = "EXACT_BOX_FOOTAGE_AND_ENDPOINTS"

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


def _job(tmp):
    create_customer_project(tmp, CP, "Label", AT)
    create_job(tmp, CP, JOB, AT, BY)
    accept_upload(tmp, CP, JOB, kind="PLAN_PDF", filename="plan.pdf", content=_PDF, stored_at=AT)
    bore = accept_upload(tmp, CP, JOB, kind="BORE_LOG", filename="log.xlsx", content=_BORE, stored_at=AT)
    create_reviewed_bore_log(tmp, CP, JOB, bore["upload_id"], RBL, at=AT, by=BY)
    row = new_extracted_row("row-1", bore["upload_id"], raw={"s": "0+00"}, normalized={"s": "0+00"},
                            extraction_method=MANUAL_ENTRY, at=AT, by=BY)
    add_extracted_rows(tmp, CP, JOB, RBL, [row], at=AT, by=BY)
    review_row_in_log(tmp, CP, JOB, RBL, "row-1", CONFIRMED, at=AT, by=BY)
    define_segment_group(tmp, CP, JOB, RBL, "g-1", ["row-1"], SEPARATE_BORE, at=AT, by=BY)
    set_grouping_status(tmp, CP, JOB, RBL, "g-1", GROUPING_CONFIRMED, at=AT, by=BY)


def _placement(status, *, reason):
    callout = Callout(sheet=10, page=23, from_sta="38+90", to_sta="44+08", from_ft=3890.0, to_ft=4408.0,
                      footage=518.0, text="STA 38+90 TO STA 44+08 DIR. BORE (518')",
                      bbox=[100.0, 200.0, 300.0, 205.0], dialect="brenham")
    return Placement(bore_id="log.xlsx", status=status, tier=status.value, reason=reason,
                     sheets=[10], matched_callouts=[callout])


def _patch(monkeypatch, *, status, reason):
    """Patch the engine to return the given placement + a synthetic renderer (writes a real PNG file)."""
    bore = Bore(bore_id="log.xlsx", source_file="log.xlsx", sheet_refs=[10], station_start="38+90",
                station_end="44+08", station_start_ft=3890.0, station_end_ft=4408.0, span_ft=518.0)
    placement = _placement(status, reason=reason)
    monkeypatch.setattr(uce, "_run_engine",
                        lambda plan_path, borelog_path, rbl=None: (bore, placement, 0, "brenham", [], _NA_MATCHLINE,
                                                                   None, None))

    def fake_render(plan, bore_id, sheet, offset, stroke_points, *, status, reason, out_dir, caption=True):
        import os
        os.makedirs(out_dir, exist_ok=True)
        p = os.path.join(out_dir, "%s_s%d_redline_stroke.png" % (bore_id, sheet))
        with open(p, "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n" + b"render(%s)" % status.encode())
        return p
    monkeypatch.setattr(uce, "render_redline_stroke", fake_render)


# --------------------------------------------------------------------------- #
# 1 + 2. Default OFF: engine AUTO_SELECT is CAPPED to a REVIEW candidate; raw verdict preserved.
# --------------------------------------------------------------------------- #
def test_uploaded_auto_capped_to_review_candidate_by_default(tmp_path, monkeypatch):
    _job(tmp_path)
    _patch(monkeypatch, status=PlacementStatus.AUTO_SELECT, reason=AUTO_REASON)

    gen = ra.generate_review_candidate(tmp_path, CP, JOB, at=AT, by=BY)   # default flag OFF

    assert gen["tier"] == ra.TIER_REVIEW                                  # NOT TIER_AUTO
    rec = gen["record"]
    assert rec is not None                                                # a REVIEW record was written
    assert rec["status"] == ra.STATUS_REVIEW_CANDIDATE
    assert rec["candidate_id"] == CID
    assert rec["provenance"] == ra.CANDIDATE_PROVENANCE
    assert rec["auto_capped_by_policy"] is True
    # Raw engine verdict/reason/evidence preserved in metadata.
    assert rec["placement_status"] == "AUTO_SELECT"
    assert rec["engine_reason"] == AUTO_REASON
    assert rec["bore_span"] == "38+90->44+08"
    assert rec["why_not_auto"]["blockers"] == [ra.UPLOADED_CORPUS_AUTO_OWNER_GATED]
    assert rec["why_not_auto"]["engine_tier"] == "AUTO_SELECT"
    assert rec["why_not_auto"]["engine_reason"] == AUTO_REASON


def test_run_product_redline_surfaces_capped_auto_as_uploaded_review(tmp_path, monkeypatch):
    _job(tmp_path)
    _patch(monkeypatch, status=PlacementStatus.AUTO_SELECT, reason=AUTO_REASON)

    out = pw.run_product_redline(tmp_path, CP, JOB, registry={"corpora": []}, at=AT, by=BY)  # flag OFF

    assert out["path"] == pw.PATH_UPLOADED_REVIEW                         # human-review lane, not AUTO
    assert out["path"] != pw.PATH_UPLOADED_AUTO
    assert out["provenance"] == pw.PROVENANCE_REVIEW_CANDIDATE
    assert out["requires_acceptance"] is True
    assert out["review_status"] == ra.STATUS_REVIEW_CANDIDATE


# --------------------------------------------------------------------------- #
# 3. Closeout / export is BLOCKED until the capped REVIEW candidate is accepted.
# --------------------------------------------------------------------------- #
def test_closeout_export_blocked_until_capped_review_accepted(tmp_path, monkeypatch):
    _job(tmp_path)
    _patch(monkeypatch, status=PlacementStatus.AUTO_SELECT, reason=AUTO_REASON)
    pw.run_product_redline(tmp_path, CP, JOB, registry={"corpora": []}, at=AT, by=BY)   # capped -> PLACED

    # Before acceptance: closeout assembly + export gate both BLOCK on REVIEW_NOT_ACCEPTED.
    co = pw.assemble_closeout_package(tmp_path, CP, JOB, at=AT, by=BY)
    assert co["assembled"] is False
    assert co["blocker"] == pw.REVIEW_NOT_ACCEPTED
    ok, code = pw.export_gate(tmp_path, CP, JOB)
    assert ok is False and code == pw.REVIEW_NOT_ACCEPTED

    # Human accepts the REVIEW candidate -> the gate opens.
    ra.accept_review_candidate(tmp_path, CP, JOB, CID, at=AT, by=BY)
    ok2, code2 = pw.export_gate(tmp_path, CP, JOB)
    assert ok2 is True and code2 is None


# --------------------------------------------------------------------------- #
# 4. Opt-in ON restores the prior AUTO behavior ONLY behind the explicit flag.
# --------------------------------------------------------------------------- #
def test_auto_optin_true_restores_auto_placement(tmp_path, monkeypatch):
    _job(tmp_path)
    _patch(monkeypatch, status=PlacementStatus.AUTO_SELECT, reason=AUTO_REASON)

    gen = ra.generate_review_candidate(tmp_path, CP, JOB, at=AT, by=BY, uploaded_corpus_auto_optin=True)
    assert gen["tier"] == ra.TIER_AUTO
    assert gen["record"] is None                                         # no acceptance record
    assert gen["requires_acceptance"] is False

    out = pw.run_product_redline(tmp_path, CP, JOB, registry={"corpora": []}, at=AT, by=BY,
                                 uploaded_corpus_auto_optin=True)
    assert out["path"] == pw.PATH_UPLOADED_AUTO
    assert out["provenance"] == pw.PROVENANCE_DETERMINISTIC_AUTO
    assert out["requires_acceptance"] is False


# --------------------------------------------------------------------------- #
# 5. Regression: a genuine engine REVIEW is UNCHANGED by the cap (no false auto_capped flag).
# --------------------------------------------------------------------------- #
def test_engine_review_is_unchanged_by_the_cap(tmp_path, monkeypatch):
    _job(tmp_path)
    _patch(monkeypatch, status=PlacementStatus.REVIEW, reason="DRAWN_EXTENT_COVERS_SPAN_NOT_TIGHT")

    gen = ra.generate_review_candidate(tmp_path, CP, JOB, at=AT, by=BY)   # flag OFF
    rec = gen["record"]
    assert gen["tier"] == ra.TIER_REVIEW
    assert rec["status"] == ra.STATUS_REVIEW_CANDIDATE
    assert rec["placement_status"] == "REVIEW"
    assert rec["auto_capped_by_policy"] is False
    # Existing REVIEW explanation is preserved (NOT the owner-gate policy blocker).
    assert ra.UPLOADED_CORPUS_AUTO_OWNER_GATED not in rec["why_not_auto"]["blockers"]
    assert ra.NO_PER_BORE_TERMINI in rec["why_not_auto"]["blockers"]
