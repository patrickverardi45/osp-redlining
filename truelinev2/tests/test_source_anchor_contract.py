"""Contract tests: human-confirmed source_anchor record + renderability validation.

Pure stdlib + tmp_path; NO engine, NO renderer, NO fitz, NO PDF opened (the page bounds are injected, as
the route does at the edge). Asserts: a valid human-confirmed anchor is VALIDATED with the
HUMAN_CONFIRMED_CONTROL_POINTS provenance; the named blockers fire (too-few / out-of-bounds /
page-not-resolvable / wrong-or-missing plan upload / rbl-not-engine-ready / group / row); tenant isolation;
list/get; no job-output mutation; coordinate discipline (identity is coordinate-free; the legacy
adjudication fixtures and the renderer are never touched). Generic ids only.
"""
from __future__ import annotations

from pathlib import Path

from truelinev2.contracts.customer_project import create_customer_project
from truelinev2.contracts.processing_job import create_job, job_dir, load_job
from truelinev2.contracts.upload_pipeline import accept_upload
from truelinev2.contracts.extracted_row import CONFIRMED, MANUAL_ENTRY, new_extracted_row
from truelinev2.contracts.reviewed_bore_log import (
    GROUPING_CONFIRMED,
    SEPARATE_BORE,
    add_extracted_rows,
    create_reviewed_bore_log,
    define_segment_group,
    review_row_in_log,
    set_grouping_status,
)
from truelinev2.contracts.source_anchor import (
    CONTROL_POINT_OUT_OF_BOUNDS,
    CONTROL_POINTS_TOO_FEW,
    COORDINATE_SPACE,
    GROUP_NOT_CONFIRMED_OR_ELIGIBLE,
    NO_PLAN_PDF_UPLOAD,
    PAGE_NOT_RESOLVABLE,
    PLAN_UPLOAD_NOT_FOUND,
    PLAN_UPLOAD_NOT_PLAN_PDF,
    PROVENANCE,
    REVIEWED_BORE_LOG_NOT_ENGINE_READY,
    REVIEWED_BORE_LOG_NOT_FOUND,
    ROW_NOT_ENGINE_ELIGIBLE,
    SourceAnchorError,
    SourceAnchorNotFoundError,
    create_source_anchor,
    list_source_anchors,
    load_source_anchor,
)

AT = "2026-06-22T00:00:00Z"
BY = "operator-1"
CP = "cp-0001"
JOB = "job-0001"
RBL = "rbl-1"
BOUNDS = (0.0, 0.0, 1000.0, 1000.0)
TWO_PTS = [{"x": 100.0, "y": 120.0}, {"x": 300.0, "y": 340.0}]


def _project_job(tmp_path, cp=CP, job=JOB):
    create_customer_project(tmp_path, cp, "Label", AT)
    create_job(tmp_path, cp, job, AT, BY)


def _plan_upload(tmp_path, cp=CP, job=JOB):
    # bytes are never opened in the contract layer (bounds are injected) -> any bytes are fine here
    return accept_upload(tmp_path, cp, job, kind="PLAN_PDF", filename="plan.pdf",
                         content=b"%PDF-1.4 not-opened-in-contract-tests", stored_at=AT)["upload_id"]


def _bore_upload(tmp_path, cp=CP, job=JOB):
    return accept_upload(tmp_path, cp, job, kind="BORE_LOG", filename="bores.csv",
                         content=b"row\n", stored_at=AT)["upload_id"]


def _engine_ready_rbl(tmp_path, bore_upload_id, cp=CP, job=JOB, rbl=RBL):
    create_reviewed_bore_log(tmp_path, cp, job, bore_upload_id, rbl, at=AT, by=BY)
    row = new_extracted_row("row-1", bore_upload_id, raw={"s": "0+00"}, normalized={"s": "0+00"},
                            extraction_method=MANUAL_ENTRY, at=AT, by=BY)
    add_extracted_rows(tmp_path, cp, job, rbl, [row], at=AT, by=BY)
    review_row_in_log(tmp_path, cp, job, rbl, "row-1", CONFIRMED, at=AT, by=BY)
    define_segment_group(tmp_path, cp, job, rbl, "g-1", ["row-1"], SEPARATE_BORE, at=AT, by=BY)
    set_grouping_status(tmp_path, cp, job, rbl, "g-1", GROUPING_CONFIRMED, at=AT, by=BY)


def _ready_job(tmp_path):
    """Project + job + PLAN_PDF + an engine-ready reviewed_bore_log. Returns the plan upload id."""
    _project_job(tmp_path)
    plan = _plan_upload(tmp_path)
    _engine_ready_rbl(tmp_path, _bore_upload(tmp_path))
    return plan


def _create(tmp_path, *, plan_upload_id, page_bounds=BOUNDS, control_points=None, sa_id="sa-1",
            reviewed_bore_log_id=RBL, page_number=1, group_id=None, **kw):
    return create_source_anchor(
        tmp_path, CP, JOB, source_anchor_id=sa_id, plan_upload_id=plan_upload_id,
        reviewed_bore_log_id=reviewed_bore_log_id, page_number=page_number,
        control_points=TWO_PTS if control_points is None else control_points,
        group_id=group_id, at=AT, by=BY, page_bounds=page_bounds, **kw)


def _codes(rec):
    return {b["code"] for b in rec["blockers"]}


def test_validated_when_all_inputs_good(tmp_path):
    plan = _ready_job(tmp_path)
    rec = _create(tmp_path, plan_upload_id=plan)
    assert rec["status"] == "VALIDATED" and rec["renderable"] is True and rec["blockers"] == []
    assert rec["provenance"] == PROVENANCE == "HUMAN_CONFIRMED_CONTROL_POINTS"
    assert rec["coordinate_space"] == COORDINATE_SPACE == "pdf_display_space"
    assert rec["control_points"] == TWO_PTS
    assert rec["checks"]["page_resolvable"] is True
    assert rec["checks"]["all_control_points_in_bounds"] is True


def test_too_few_points_rejected(tmp_path):
    plan = _ready_job(tmp_path)
    rec = _create(tmp_path, plan_upload_id=plan, control_points=[{"x": 10.0, "y": 10.0}])
    assert rec["status"] == "REJECTED" and rec["renderable"] is False
    assert CONTROL_POINTS_TOO_FEW in _codes(rec)


def test_out_of_bounds_point_rejected(tmp_path):
    plan = _ready_job(tmp_path)
    rec = _create(tmp_path, plan_upload_id=plan, page_bounds=(0.0, 0.0, 100.0, 100.0),
                  control_points=[{"x": 10.0, "y": 10.0}, {"x": 9999.0, "y": 5.0}])
    assert rec["renderable"] is False and CONTROL_POINT_OUT_OF_BOUNDS in _codes(rec)


def test_page_not_resolvable_when_bounds_none(tmp_path):
    plan = _ready_job(tmp_path)
    rec = _create(tmp_path, plan_upload_id=plan, page_bounds=None)
    assert rec["renderable"] is False and PAGE_NOT_RESOLVABLE in _codes(rec)


def test_plan_upload_not_found(tmp_path):
    _ready_job(tmp_path)                                     # a PLAN_PDF exists, but we name a missing id
    rec = _create(tmp_path, plan_upload_id="up-nope")
    assert PLAN_UPLOAD_NOT_FOUND in _codes(rec) and rec["renderable"] is False


def test_plan_upload_wrong_kind(tmp_path):
    _project_job(tmp_path)
    _plan_upload(tmp_path)                                   # satisfies has_plan_pdf
    bore = _bore_upload(tmp_path)
    _engine_ready_rbl(tmp_path, bore)
    rec = _create(tmp_path, plan_upload_id=bore)             # points at the BORE_LOG upload
    assert PLAN_UPLOAD_NOT_PLAN_PDF in _codes(rec)


def test_no_plan_pdf_upload_at_all(tmp_path):
    _project_job(tmp_path)
    bore = _bore_upload(tmp_path)
    _engine_ready_rbl(tmp_path, bore)                        # no PLAN_PDF uploaded
    rec = _create(tmp_path, plan_upload_id="up-nope", page_bounds=None)
    assert NO_PLAN_PDF_UPLOAD in _codes(rec)


def test_reviewed_bore_log_not_found(tmp_path):
    _project_job(tmp_path)
    plan = _plan_upload(tmp_path)
    rec = _create(tmp_path, plan_upload_id=plan, reviewed_bore_log_id="rbl-missing")
    assert REVIEWED_BORE_LOG_NOT_FOUND in _codes(rec)


def test_reviewed_bore_log_not_engine_ready(tmp_path):
    _project_job(tmp_path)
    plan = _plan_upload(tmp_path)
    bore = _bore_upload(tmp_path)
    create_reviewed_bore_log(tmp_path, CP, JOB, bore, RBL, at=AT, by=BY)
    row = new_extracted_row("row-1", bore, raw={}, normalized={}, extraction_method=MANUAL_ENTRY,
                            at=AT, by=BY)
    add_extracted_rows(tmp_path, CP, JOB, RBL, [row], at=AT, by=BY)   # UNREVIEWED -> not engine-ready
    rec = _create(tmp_path, plan_upload_id=plan)
    assert REVIEWED_BORE_LOG_NOT_ENGINE_READY in _codes(rec)


def test_group_not_eligible(tmp_path):
    plan = _ready_job(tmp_path)                              # has a CONFIRMED group g-1
    define_segment_group(tmp_path, CP, JOB, RBL, "g-pending", ["row-1"], SEPARATE_BORE, at=AT, by=BY)
    rec = _create(tmp_path, plan_upload_id=plan, group_id="g-pending")   # PENDING, not confirmed
    assert GROUP_NOT_CONFIRMED_OR_ELIGIBLE in _codes(rec)


def test_row_not_engine_eligible(tmp_path):
    plan = _ready_job(tmp_path)
    rec = _create(tmp_path, plan_upload_id=plan, row_ids=["row-does-not-exist"])
    assert ROW_NOT_ENGINE_ELIGIBLE in _codes(rec)


def test_tenant_isolation(tmp_path):
    plan = _ready_job(tmp_path)
    _create(tmp_path, plan_upload_id=plan)
    create_customer_project(tmp_path, "cp-0002", "Label", AT)
    create_job(tmp_path, "cp-0002", JOB, AT, BY)
    assert list_source_anchors(tmp_path, "cp-0002", JOB) == []          # other project sees none
    try:
        load_source_anchor(tmp_path, "cp-0002", JOB, "sa-1")
        assert False, "expected SourceAnchorNotFoundError"
    except SourceAnchorNotFoundError:
        pass


def test_list_and_get_and_missing(tmp_path):
    plan = _ready_job(tmp_path)
    _create(tmp_path, plan_upload_id=plan, sa_id="sa-1")
    _create(tmp_path, plan_upload_id=plan, sa_id="sa-2")
    ids = [r["source_anchor_id"] for r in list_source_anchors(tmp_path, CP, JOB)]
    assert ids == ["sa-1", "sa-2"]
    assert load_source_anchor(tmp_path, CP, JOB, "sa-1")["source_anchor_id"] == "sa-1"
    try:
        load_source_anchor(tmp_path, CP, JOB, "sa-nope")
        assert False, "expected SourceAnchorNotFoundError"
    except SourceAnchorNotFoundError:
        pass


def test_duplicate_id_raises(tmp_path):
    plan = _ready_job(tmp_path)
    _create(tmp_path, plan_upload_id=plan, sa_id="sa-1")
    try:
        _create(tmp_path, plan_upload_id=plan, sa_id="sa-1")
        assert False, "expected SourceAnchorError on duplicate"
    except SourceAnchorError:
        pass


def test_creates_no_output_slots_or_artifacts(tmp_path):
    plan = _ready_job(tmp_path)
    _create(tmp_path, plan_upload_id=plan)
    job = load_job(tmp_path, CP, JOB)
    assert all(v is None for v in job["slots"].values())               # no redline_manifest/bundle/export
    jd = job_dir(tmp_path, CP, JOB)
    assert not (jd / "bundle_store").exists() and not (jd / "handoffs").exists()
    assert list(jd.rglob("*.png")) == []                               # nothing rendered


def test_identity_is_coordinate_free(tmp_path):
    plan = _ready_job(tmp_path)
    rec = _create(tmp_path, plan_upload_id=plan,
                  start_identity={"station": "0+00", "structure_label": "HH",
                                  "note": "n", "x": 5.0, "y": 9.0})   # x/y must be dropped
    assert rec["start_identity"] == {"station": "0+00", "structure_label": "HH", "note": "n"}
    assert "x" not in rec["start_identity"] and "y" not in rec["start_identity"]


def test_module_never_touches_renderer_or_legacy_adjudication():
    src = (Path(__file__).resolve().parents[1] / "contracts" / "source_anchor.py").read_text(
        encoding="utf-8")
    for forbidden in ("manual_adjudication", "render_redline_stroke", "import fitz", "render.crop"):
        assert forbidden not in src, "source_anchor.py must not reference %r" % forbidden
