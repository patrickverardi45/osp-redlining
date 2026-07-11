"""Contract tests: render a job's VALIDATED human-confirmed source anchors into a real published bundle.

Drives the render adapter end-to-end on a fresh tmp store with a REAL minimal blank PDF (the test never
imports fitz; it ships the bytes). Asserts: a real dashed REVIEW PNG is produced with real sha256/bytes;
the bundle is mock_example:false + bundle_origin HUMAN_CONFIRMED_SOURCE_ANCHOR + provenance
OWNER_CONFIRMED_HUMAN_ADJUSTABLE (never DETERMINISTIC_AUTO); the job's redline_manifest + artifact_bundle
slots are set; unvalidated/stale anchors are refused; all validated anchors render into one bundle; idempotent
re-render; the committed deterministic 50/58 example is untouched; and the adapter imports no
solver/match/dialect/endpoint path. Generic ids only.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from truelinev2.contracts.customer_project import create_customer_project
from truelinev2.contracts.processing_job import JobNotFoundError, create_job, job_dir, load_job
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
    SourceAnchorStateError,
    build_source_anchor_manifest,
    create_source_anchor,
    load_source_anchor,
)
from truelinev2.render.source_anchor_render import render_job_source_anchors

AT = "2026-06-22T00:00:00Z"
BY = "operator-1"
CP = "cp-0001"
JOB = "job-0001"
RBL = "rbl-1"
BOUNDS = (0.0, 0.0, 612.0, 792.0)
TWO_PTS = [{"x": 100.0, "y": 120.0}, {"x": 300.0, "y": 340.0}]

# Minimal valid blank PDF (1 page, 612x792, rotation 0) generated once by PyMuPDF; the test never imports
# fitz — it ships these bytes so the adapter's real PlanPdf render runs.
_PDF = base64.b64decode(
    "JVBERi0xLjcKJcK1wrYKJSBXcml0dGVuIGJ5IE11UERGIDEuMjcuMgoKMSAwIG9iago8PC9UeXBlL0NhdGFsb2cvUGFnZXMg"
    "MiAwIFIvSW5mbzw8L1Byb2R1Y2VyKE11UERGIDEuMjcuMik+Pj4+CmVuZG9iagoKMiAwIG9iago8PC9UeXBlL1BhZ2VzL0Nv"
    "dW50IDEvS2lkc1s0IDAgUl0+PgplbmRvYmoKCjMgMCBvYmoKPDw+PgplbmRvYmoKCjQgMCBvYmoKPDwvVHlwZS9QYWdlL01l"
    "ZGlhQm94WzAgMCA2MTIgNzkyXS9Sb3RhdGUgMC9SZXNvdXJjZXMgMyAwIFIvUGFyZW50IDIgMCBSPj4KZW5kb2JqCgp4cmVm"
    "CjAgNQowMDAwMDAwMDAwIDY1NTM1IGYgCjAwMDAwMDAwNDIgMDAwMDAgbiAKMDAwMDAwMDEyMCAwMDAwMCBuIAowMDAwMDAw"
    "MTcyIDAwMDAwIG4gCjAwMDAwMDAxOTMgMDAwMDAgbiAKCnRyYWlsZXIKPDwvU2l6ZSA1L1Jvb3QgMSAwIFIvSURbPDI1QzNB"
    "MjRFNEVDMjgwQzJBQzY1QzM4NEMzQTJDMjg1PjwxQjAyRUMzMkUxRDMwNUYzNDJBRjZFMjI2MkYzNTZDND5dPj4Kc3RhcnR4"
    "cmVmCjI4NAolJUVPRgo=")


def _ready_job(tmp_path, *, cp=CP, job=JOB, row_raw=None):
    create_customer_project(tmp_path, cp, "Label", AT)
    create_job(tmp_path, cp, job, AT, BY)
    plan = accept_upload(tmp_path, cp, job, kind="PLAN_PDF", filename="plan.pdf", content=_PDF, stored_at=AT)
    bore = accept_upload(tmp_path, cp, job, kind="BORE_LOG", filename="b.csv", content=b"row\n", stored_at=AT)
    create_reviewed_bore_log(tmp_path, cp, job, bore["upload_id"], RBL, at=AT, by=BY)
    raw = row_raw if row_raw is not None else {"s": "0+00"}
    row = new_extracted_row("row-1", bore["upload_id"], raw=raw, normalized={"s": "0+00"},
                            extraction_method=MANUAL_ENTRY, at=AT, by=BY)
    add_extracted_rows(tmp_path, cp, job, RBL, [row], at=AT, by=BY)
    review_row_in_log(tmp_path, cp, job, RBL, "row-1", CONFIRMED, at=AT, by=BY)
    define_segment_group(tmp_path, cp, job, RBL, "g-1", ["row-1"], SEPARATE_BORE, at=AT, by=BY)
    set_grouping_status(tmp_path, cp, job, RBL, "g-1", GROUPING_CONFIRMED, at=AT, by=BY)
    return plan["upload_id"]


def _anchor(tmp_path, plan_upload_id, *, sa_id="sa-1", points=None, cp=CP, job=JOB):
    return create_source_anchor(
        tmp_path, cp, job, source_anchor_id=sa_id, plan_upload_id=plan_upload_id,
        reviewed_bore_log_id=RBL, page_number=1, control_points=points or TWO_PTS, group_id=None,
        at=AT, by=BY, page_bounds=BOUNDS,
        start_identity={"station": "0+00", "structure_label": "HH"}, end_identity={"station": "2+99"})


def _render(tmp_path, sa_id="sa-1", *, cp=CP, job=JOB):
    return render_job_source_anchors(tmp_path, cp, job, sa_id, at=AT, by=BY)


def _bundle_manifest(tmp_path, bundle_id, *, cp=CP, job=JOB):
    path = (job_dir(tmp_path, cp, job) / "bundle_store" / "bundles" / bundle_id / "redline_manifest.json")
    return json.loads(path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# Pure manifest builder.
# --------------------------------------------------------------------------- #
def test_build_manifest_reconciles_and_is_schema_valid():
    from truelinev2.contracts.redline_manifest_publisher import (
        load_schema, reconciliation_errors, validate_manifest)
    entries = [
        {"source_anchor": {"source_anchor_id": "sa-1", "reviewed_bore_log_id": "rbl-1", "page_number": 1,
                           "start_identity": {"station": "0+00"}, "end_identity": {"station": "2+99"}},
         "artifact_path": "artifacts/sa-1/sa-1_s1_redline_stroke.png", "sheet": 1},
        {"source_anchor": {"source_anchor_id": "sa-2", "reviewed_bore_log_id": "rbl-1", "page_number": 2,
                           "start_identity": {}, "end_identity": {}},
         "artifact_path": "artifacts/sa-2/sa-2_s2_redline_stroke.png", "sheet": 2},
    ]
    m = build_source_anchor_manifest(entries, project_id="cp-x", project_name="cp-x",
                                     engine_head="human-confirmed-source-anchor",
                                     render_commit="human-confirmed-source-anchor", disclaimer="d")
    assert m["mock_example"] is False
    assert m["bundle_origin"] == "HUMAN_CONFIRMED_SOURCE_ANCHOR"
    assert m["summary"] == {"total_logs": 2, "drawn_count": 2, "covered_count": 0, "blocked_count": 0,
                            "frontier": "2/2"}
    assert m["provenance_counts"]["OWNER_CONFIRMED_HUMAN_ADJUSTABLE"] == 2
    assert m["provenance_counts"]["DETERMINISTIC_AUTO"] == 0
    assert m["logs"][0]["status"] == "DRAWN_REDLINE" and m["logs"][0]["closure"] is None
    assert validate_manifest(m, load_schema()) == []
    assert reconciliation_errors(m) == []


# --------------------------------------------------------------------------- #
# Render adapter.
# --------------------------------------------------------------------------- #
def test_render_produces_real_human_confirmed_bundle(tmp_path):
    plan = _ready_job(tmp_path)
    _anchor(tmp_path, plan)
    summary = _render(tmp_path)
    assert summary["status"] == "SUCCEEDED" and summary["bundle_id"]
    assert summary["bundle_origin"] == "HUMAN_CONFIRMED_SOURCE_ANCHOR"
    assert summary["artifact_count"] == 1 and summary["source_anchor_ids"] == ["sa-1"]
    art = summary["artifacts"][0]
    assert art["kind"] == "FINAL_REDLINE_PNG" and len(art["sha256"]) == 64 and art["bytes"] > 0
    # job output slots set through the handoff
    job = load_job(tmp_path, CP, JOB)
    assert job["slots"]["redline_manifest"] is not None
    assert job["slots"]["artifact_bundle"] is not None
    # real PNG on disk in the durable bundle
    png = job_dir(tmp_path, CP, JOB) / "bundle_store" / "bundles" / summary["bundle_id"] / art["path"]
    assert png.is_file() and png.read_bytes()[:4] == b"\x89PNG" and png.stat().st_size > 0


def test_render_bundle_is_not_deterministic(tmp_path):
    plan = _ready_job(tmp_path)
    _anchor(tmp_path, plan)
    summary = _render(tmp_path)
    manifest = _bundle_manifest(tmp_path, summary["bundle_id"])
    assert manifest["mock_example"] is False
    assert manifest["bundle_origin"] == "HUMAN_CONFIRMED_SOURCE_ANCHOR"
    assert manifest["provenance_counts"]["DETERMINISTIC_AUTO"] == 0
    assert all(lg["provenance"] == "OWNER_CONFIRMED_HUMAN_ADJUSTABLE" for lg in manifest["logs"])
    assert manifest["summary"]["frontier"] == "1/1"          # job-local, NOT the deterministic 50/58


def test_render_rejects_unvalidated_anchor(tmp_path):
    plan = _ready_job(tmp_path)
    _anchor(tmp_path, plan, sa_id="sa-bad", points=[{"x": 10.0, "y": 10.0}])   # 1 point -> REJECTED
    with pytest.raises(SourceAnchorStateError):
        _render(tmp_path, "sa-bad")
    assert all(v is None for v in load_job(tmp_path, CP, JOB)["slots"].values())


def test_render_rejects_stale_rbl(tmp_path):
    plan = _ready_job(tmp_path)
    _anchor(tmp_path, plan)
    # rbl no longer engine-ready: append an UNREVIEWED row
    bore = next(u["upload_id"] for u in load_job(tmp_path, CP, JOB)["uploads"] if u["kind"] == "BORE_LOG")
    add_extracted_rows(tmp_path, CP, JOB, RBL,
                       [new_extracted_row("row-2", bore, raw={}, normalized={},
                                          extraction_method=MANUAL_ENTRY, at=AT, by=BY)], at=AT, by=BY)
    with pytest.raises(SourceAnchorStateError):
        _render(tmp_path)
    assert all(v is None for v in load_job(tmp_path, CP, JOB)["slots"].values())


def test_render_includes_all_validated_anchors(tmp_path):
    plan = _ready_job(tmp_path)
    _anchor(tmp_path, plan, sa_id="sa-1")
    _anchor(tmp_path, plan, sa_id="sa-2", points=[{"x": 50.0, "y": 60.0}, {"x": 70.0, "y": 80.0}])
    summary = _render(tmp_path, "sa-1")                       # trigger on sa-1
    assert summary["artifact_count"] == 2 and summary["source_anchor_ids"] == ["sa-1", "sa-2"]


def test_render_is_idempotent_for_identical_content(tmp_path):
    plan = _ready_job(tmp_path)
    _anchor(tmp_path, plan)
    first = _render(tmp_path)
    second = _render(tmp_path)                                # identical content -> same bundle
    assert first["bundle_id"] == second["bundle_id"] and second["status"] == "SUCCEEDED"


def test_render_tenant_isolation(tmp_path):
    plan = _ready_job(tmp_path)
    _anchor(tmp_path, plan)
    with pytest.raises(JobNotFoundError):                     # other tenant cannot render this job
        render_job_source_anchors(tmp_path, "cp-other", JOB, "sa-1", at=AT, by=BY)


def test_committed_deterministic_example_is_untouched():
    example = (Path(__file__).resolve().parents[1] / "contracts" / "examples"
               / "brenham_50_of_58_redline_manifest.example.json")
    manifest = json.loads(example.read_text(encoding="utf-8"))
    assert manifest["summary"]["frontier"] == "50/58"        # render lane never edits the deterministic set
    assert manifest["provenance_counts"]["DETERMINISTIC_AUTO"] == 49
    assert "bundle_origin" not in manifest                   # additive field is optional; example omits it


_FOOTAGE_ROW = {"Bore ID": "B-9", "Print #": "17", "Start Station": "5+03", "End Station": "6+79",
                "Footage": "176'", "Depth": "42", "BOC": "48", "Date": "2026-03-01", "Crew": "Night",
                "Notes": "vacant HDPE"}


def test_build_manifest_carries_station_dots_additively_and_validates():
    # LOCK UPDATE (Mission 8 addendum, owner's STATION-DOT CONTRACT, ``.foreman/scratch/m8/design-dots.md``;
    # CORRECTED by fix-wave F1): ``origin`` is an ADDITIVE, OPTIONAL schema property -- NOT schema-required
    # (a pre-addendum bundle without it must stay readable forever; see
    # test_pre_addendum_manifest_shape_still_publishes_and_reads_f1 for the read-compat regression lock).
    # This literal dot dict carries ``origin`` anyway because that is what the REAL builder always emits in
    # production (enforced below, at the builder level, not the schema).
    from truelinev2.contracts.redline_manifest_publisher import (
        load_schema, reconciliation_errors, validate_manifest)
    dots = [{"index": 0, "footage_along": 50.0, "station": "5+53", "xy_display": {"x": 1.0, "y": 2.0},
             "origin": "SOURCE_RECORDED",
             "depth": "42", "boc": "48", "date": "2026-03-01", "crew": "Night", "print": "17",
             "notes": "vacant HDPE", "bore_log_id": "B-9",
             "provenance": "HUMAN_CONFIRMED_CONTROL_POINTS"}]
    entries = [{"source_anchor": {"source_anchor_id": "sa-1", "reviewed_bore_log_id": "rbl-1",
                                  "page_number": 1, "start_identity": {"station": "5+03"},
                                  "end_identity": {"station": "6+79"}},
                "artifact_path": "artifacts/sa-1/x.png", "sheet": 1, "station_dots": dots,
                "station_marks_basis": "STATION_SERIES", "station_marks_warnings": []}]
    m = build_source_anchor_manifest(entries, project_id="cp-x", project_name="cp-x",
                                     engine_head="h", render_commit="h", disclaimer="d")
    assert validate_manifest(m, load_schema()) == [] and reconciliation_errors(m) == []
    assert m["logs"][0]["station_dots"] == dots
    # Builder-level guarantee (moved off the schema by F1): every dot the builder is GIVEN with an origin
    # carries it straight through, and the log-level basis/warnings the builder was given are present too.
    assert all("origin" in d for d in m["logs"][0]["station_dots"])
    assert m["logs"][0]["station_marks_basis"] == "STATION_SERIES"
    assert m["logs"][0]["station_marks_warnings"] == []


def test_manifest_without_station_dots_defaults_empty_and_validates():
    from truelinev2.contracts.redline_manifest_publisher import load_schema, validate_manifest
    entries = [{"source_anchor": {"source_anchor_id": "sa-1", "reviewed_bore_log_id": "rbl-1",
                                  "page_number": 1, "start_identity": {}, "end_identity": {}},
                "artifact_path": "artifacts/sa-1/x.png", "sheet": 1}]           # no station_dots key
    m = build_source_anchor_manifest(entries, project_id="cp-x", project_name="cp-x",
                                     engine_head="h", render_commit="h", disclaimer="d")
    assert m["logs"][0]["station_dots"] == []                                   # additive default
    assert validate_manifest(m, load_schema()) == []


def test_deterministic_example_manifest_still_validates_against_updated_schema():
    """The committed 50/58 example carries NO station_dots; the additive optional property leaves it valid."""
    from truelinev2.contracts.redline_manifest_publisher import load_schema, validate_manifest
    example = (Path(__file__).resolve().parents[1] / "contracts" / "examples"
               / "brenham_50_of_58_redline_manifest.example.json")
    m = json.loads(example.read_text(encoding="utf-8"))
    assert validate_manifest(m, load_schema()) == []
    assert all("station_dots" not in lg for lg in m["logs"])                    # byte-identical: never added


def test_render_places_station_dots_with_bore_info(tmp_path):
    # LOCK UPDATE (Mission 8 addendum, owner's STATION-DOT CONTRACT, ``.foreman/scratch/m8/design-dots.md``):
    # ``_FOOTAGE_ROW`` carries no ``station_readings`` series (start/end/footage only), so this is now the
    # SPAN_ENDPOINTS lane -- depth/BOC/notes are NOT per-station data on this row (they are NOT attached to
    # any mark) and every dot is tagged with its ``origin``. Bore-level date/crew/print/bore_log_id stay
    # attached to EVERY dot exactly as before; footage_along/station values are UNCHANGED (same recorded
    # span endpoints + same derived-interval arithmetic labels the pre-addendum ladder already produced).
    plan = _ready_job(tmp_path, row_raw=_FOOTAGE_ROW)
    _anchor(tmp_path, plan)
    summary = _render(tmp_path)
    assert summary["status"] == "SUCCEEDED"                                     # publish validated the dots
    manifest = _bundle_manifest(tmp_path, summary["bundle_id"])
    dots = manifest["logs"][0]["station_dots"]
    assert [d["footage_along"] for d in dots] == [0.0, 50.0, 100.0, 150.0, 176.0]   # start + 50' + endpoint
    assert [d["station"] for d in dots] == ["5+03", "5+53", "6+03", "6+53", "6+79"]  # start station clickable
    assert [d["origin"] for d in dots] == ["SOURCE_RECORDED", "DERIVED_INTERVAL", "DERIVED_INTERVAL",
                                           "DERIVED_INTERVAL", "SOURCE_RECORDED"]
    d0 = dots[0]
    assert d0["footage_along"] == 0.0 and d0["station"] == "5+03"               # the start point is in payload
    assert d0["crew"] == "Night" and d0["print"] == "17" and d0["date"] == "2026-03-01"
    assert d0["bore_log_id"] == "B-9"
    # depth/BOC/notes are the row's BORE-LEVEL values, never per-station data on a span-endpoints row --
    # honestly absent on every dot (never fabricated as if they were a station reading).
    assert all("depth" not in d and "boc" not in d and "notes" not in d for d in dots)
    assert all(d["provenance"] == "HUMAN_CONFIRMED_CONTROL_POINTS" for d in dots)
    assert manifest["logs"][0]["station_marks_basis"] == "SPAN_ENDPOINTS"
    assert manifest["logs"][0]["station_marks_warnings"] == []
    # provenance/frontier doctrine intact — dots are NEVER AUTO / never the deterministic frontier
    assert manifest["provenance_counts"]["DETERMINISTIC_AUTO"] == 0
    assert all(lg["provenance"] == "OWNER_CONFIRMED_HUMAN_ADJUSTABLE" for lg in manifest["logs"])
    assert manifest["summary"]["frontier"] == "1/1"
    # a real PNG is still produced (now with dot rings)
    art = summary["artifacts"][0]
    png = job_dir(tmp_path, CP, JOB) / "bundle_store" / "bundles" / summary["bundle_id"] / art["path"]
    assert png.is_file() and png.read_bytes()[:4] == b"\x89PNG"


def test_render_summary_surfaces_station_dots_for_the_web(tmp_path):
    """The render response (what the web consumes) carries the manifest's dots additively — idempotent
    re-render included — so the UI needs no second manifest fetch."""
    plan = _ready_job(tmp_path, row_raw=_FOOTAGE_ROW)
    _anchor(tmp_path, plan)
    for summary in (_render(tmp_path), _render(tmp_path)):        # fresh render + idempotent replay
        dots = summary["station_dots"]["sa-1"]
        assert [d["footage_along"] for d in dots] == [0.0, 50.0, 100.0, 150.0, 176.0]
        assert dots[0]["station"] == "5+03" and dots[-1]["station"] == "6+79"
        assert all(d["provenance"] == "HUMAN_CONFIRMED_CONTROL_POINTS" for d in dots)


def test_render_without_footage_row_still_renders_no_dots(tmp_path):
    plan = _ready_job(tmp_path)                                                 # default row: no footage
    _anchor(tmp_path, plan)
    summary = _render(tmp_path)
    assert summary["status"] == "SUCCEEDED"                                     # render is robust
    manifest = _bundle_manifest(tmp_path, summary["bundle_id"])
    assert manifest["logs"][0]["station_dots"] == []                           # no footage -> no dots, no crash


# --------------------------------------------------------------------------- #
# Station-dot contract addendum (Mission 8, owner's contract, ``.foreman/scratch/m8/design-dots.md``):
# render-integration coverage for the three ``build_station_marks`` bases, end to end through the real
# render adapter (not just the pure unit tests in test_station_marks.py).
# --------------------------------------------------------------------------- #
def _cell(value, verbatim=None, status="READ", confidence="MEDIUM"):
    return {"value": value, "verbatim": verbatim, "status": status, "confidence": confidence, "region": None}


def _reading(station, depth, boc, *, station_verbatim=None, row_index=0):
    return {"station": _cell(station, verbatim=station_verbatim or ("STA %s" % station)),
           "depth_ft": _cell(depth), "boc_ft": _cell(boc), "column_index": 0, "row_index": row_index}


_WP23_ROW = {
    "start_station": "3+50", "end_station": "4+08", "footage_ft": 58.0,
    "depth_ft": 5.0, "boc_ft": 8.0, "crew": "JS", "print_raw": "23", "date": "2026-03-01", "bore_id": "B-9",
    "station_readings": [
        _reading("3+50", 5.0, 8.0, station_verbatim="STA 3+50", row_index=0),
        _reading("4+08", 5.0, 8.0, station_verbatim="STA  4+08", row_index=1),
    ],
}


def test_render_wp23_shape_series_endpoints_with_derived_fill(tmp_path):
    """The exact WP23 persisted-row class (start/end/total + a 2-entry recorded series): [0(rec,5/8),
    50(derived,no depth/boc), 58(rec,5/8)], stations 3+50/4+00/4+08, tagged with origin."""
    plan = _ready_job(tmp_path, row_raw=_WP23_ROW)
    _anchor(tmp_path, plan)
    summary = _render(tmp_path)
    assert summary["status"] == "SUCCEEDED"
    manifest = _bundle_manifest(tmp_path, summary["bundle_id"])
    log = manifest["logs"][0]
    dots = log["station_dots"]
    assert [d["footage_along"] for d in dots] == [0.0, 50.0, 58.0]
    assert [d["station"] for d in dots] == ["3+50", "4+00", "4+08"]
    assert [d["origin"] for d in dots] == ["SOURCE_RECORDED", "DERIVED_INTERVAL", "SOURCE_RECORDED"]
    assert dots[0]["depth"] == "5.0" and dots[0]["boc"] == "8.0"
    assert dots[2]["depth"] == "5.0" and dots[2]["boc"] == "8.0"
    assert "depth" not in dots[1] and "boc" not in dots[1]
    assert dots[0]["station_evidence"]["verbatim"] == "STA 3+50"
    assert "station_evidence" not in dots[1]
    assert log["station_marks_basis"] == "SERIES_ENDPOINTS_WITH_DERIVED_FILL"
    assert log["station_marks_warnings"] == []
    from truelinev2.contracts.redline_manifest_publisher import load_schema, validate_manifest
    assert validate_manifest(manifest, load_schema()) == []


_IRREGULAR_ROW = {
    "start_station": "10+00", "end_station": "11+22", "footage_ft": 122.0,
    "crew": "JS", "print_raw": "9",
    "station_readings": [
        _reading("10+00", 4.0, 6.0, row_index=0),
        _reading("10+50", 4.5, 6.5, row_index=1),
        _reading("10+95", 5.0, 7.0, row_index=2),
        _reading("11+22", 4.5, 6.0, row_index=3),          # final interval 27 ft (< 50)
    ],
}


def test_render_multi_reading_irregular_series_no_fill_exact_final_interval(tmp_path):
    """>= 4 recorded readings with irregular gaps + a short final interval -> the EXACT recorded sequence,
    never a 50-ft fill (owner clause 5)."""
    plan = _ready_job(tmp_path, row_raw=_IRREGULAR_ROW)
    _anchor(tmp_path, plan)
    summary = _render(tmp_path)
    manifest = _bundle_manifest(tmp_path, summary["bundle_id"])
    log = manifest["logs"][0]
    dots = log["station_dots"]
    assert [d["footage_along"] for d in dots] == [0.0, 50.0, 95.0, 122.0]
    assert [d["station"] for d in dots] == ["10+00", "10+50", "10+95", "11+22"]
    assert all(d["origin"] == "SOURCE_RECORDED" for d in dots)
    assert [d["depth"] for d in dots] == ["4.0", "4.5", "5.0", "4.5"]
    assert log["station_marks_basis"] == "STATION_SERIES"
    assert log["station_marks_warnings"] == []


def test_render_footage_only_dot_positions_unchanged_by_addendum(tmp_path):
    """POSITION-EQUALITY LOCK (Mission 8 addendum): a footage-only row (no station_readings) still lands
    its dots at EXACTLY the positions the pre-addendum generic 50' ladder (``dot_marks``) would have used
    -- the addendum changes TAGS/metadata, never where an untagged row's dots actually sit."""
    from truelinev2.render.station_dots import _arclen_dots, dot_marks

    plan = _ready_job(tmp_path, row_raw=_FOOTAGE_ROW)
    _anchor(tmp_path, plan)
    summary = _render(tmp_path)
    manifest = _bundle_manifest(tmp_path, summary["bundle_id"])
    dots = manifest["logs"][0]["station_dots"]

    expected_marks = dot_marks(176.0)                              # the OLD/pre-addendum ladder, independently
    assert [d["footage_along"] for d in dots] == expected_marks
    expected_xy = [(round(x, 2), round(y, 2)) for _fa, _pt, (x, y) in _arclen_dots(TWO_PTS, 176.0, 50.0)]
    actual_xy = [(d["xy_display"]["x"], d["xy_display"]["y"]) for d in dots]
    assert actual_xy == expected_xy


def test_two_point_anchor_renders_a_straight_stroke(tmp_path, monkeypatch):
    """PRODUCT RULE (locked at the RENDER seam): a two-click HUMAN_CONFIRMED anchor hands the renderer a
    STRAIGHT stroke — every vertex collinear with the two clicks (zero perpendicular deviation), endpoints
    exactly the clicks, no route-following/conduit vertex ever inserted. Dots ride ON that segment."""
    import math
    import truelinev2.render.source_anchor_render as R
    plan = _ready_job(tmp_path, row_raw=_FOOTAGE_ROW)
    _anchor(tmp_path, plan)                                        # TWO_PTS: exactly two clicked points
    captured = {}
    orig = R.render_redline_stroke
    def spy(p, bore_id, sheet, offset, stroke_points, **kw):
        captured["pts"] = [tuple(q) for q in stroke_points]
        return orig(p, bore_id, sheet, offset, stroke_points, **kw)
    monkeypatch.setattr(R, "render_redline_stroke", spy)
    assert _render(tmp_path)["status"] == "SUCCEEDED"
    pts = captured["pts"]
    a, b = (TWO_PTS[0]["x"], TWO_PTS[0]["y"]), (TWO_PTS[1]["x"], TWO_PTS[1]["y"])
    assert pts[0] == a and pts[-1] == b and len(pts) >= 2
    L = math.hypot(b[0] - a[0], b[1] - a[1])
    for (x, y) in pts:
        dev = abs((b[0] - a[0]) * (a[1] - y) - (a[0] - x) * (b[1] - a[1])) / L
        assert dev < 1e-9, "renderer received a non-collinear vertex %r (dev %.3g)" % ((x, y), dev)


def test_render_adapter_imports_no_engine_path():
    import ast
    src = (Path(__file__).resolve().parents[1] / "render" / "source_anchor_render.py").read_text(
        encoding="utf-8")
    mods = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                mods.add(alias.name)
    forbidden = ("truelinev2.match", "truelinev2.extract", "truelinev2.ingest.manual_adjudication")
    for m in mods:
        assert not any(m == f or m.startswith(f + ".") for f in forbidden), \
            "render adapter must not import engine/solver module %r" % m
    # positive: it renders via the renderer + publishes via the contracts (no engine placement path)
    assert "truelinev2.render.crop" in mods
    assert "truelinev2.contracts.redline_manifest_publisher" in mods
