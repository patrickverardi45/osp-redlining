"""Deterministic contract test for the product-workflow seed (run_product_workflow_seed.seed_workflow).

Pure stdlib + tmp_path; no httpx/TestClient; generic ids only. Proves the full product spine end-to-end
on a synthetic-but-REAL (checksummed) single-drawn-log subset bundle, plus the safety invariants:
untrusted manual rows, the review+group gate, handoff rejection of a not-ready reviewed-bore-log / a
mock_example bundle / a tampered bundle, manifest-backed artifact reads with path guarding, KMZ
pixel-only block, non-privileged closeout, server-computed billing, descriptor-only export with no
generated files, gitignored seed output, and name-token absence.

The test never depends on the gitignored real render corpus: it publishes its own real PNG bytes through
the same publisher/store/handoff chain the harness uses.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

import pytest

from truelinev2.proof import run_product_workflow_seed as seed
from truelinev2.contracts.customer_project import create_customer_project
from truelinev2.contracts.processing_job import (
    AWAITING_REVIEW,
    EXTRACTING,
    PLACED,
    PLACING,
    UPLOADING,
    create_job,
    job_dir,
    load_job,
    transition,
)
from truelinev2.contracts.upload_pipeline import accept_upload
from truelinev2.contracts.extracted_row import (
    CONFIRMED,
    MANUAL_ENTRY,
    UNREVIEWED,
    new_extracted_row,
)
from truelinev2.contracts.reviewed_bore_log import (
    GROUPING_CONFIRMED,
    SEPARATE_BORE,
    add_extracted_rows,
    create_reviewed_bore_log,
    define_segment_group,
    is_engine_ready,
    load_reviewed_bore_log,
    review_row_in_log,
    set_grouping_status,
)
from truelinev2.contracts.manifest_handoff import (
    BUNDLE_STORE_SUBDIR,
    FAILED,
    REJECTED,
    SUCCEEDED,
    finalize_handoff,
    record_handoff_attempt,
)
from truelinev2.contracts.published_bundle_consumer import (
    ArtifactNotServableError,
    StaticBundleConsumer,
)
from truelinev2.contracts import kmz_export as kmz
from truelinev2.contracts import closeout_review as co
from truelinev2.contracts import billing_summary as bill
from truelinev2.contracts import export_package as exp

AT = "2026-06-21T00:00:00Z"
BY = "test-seed"
CP = "seed-cp-test"
JOB = "seed-job-test"
RBL = "seed-rbl-test"
GROUP = "seed-grp-test"
RUN = "seed-run-test"
ARTIFACT_PATH = "artifacts/log-a/log_a_s1_redline_stroke.png"

NEW_FILES = (Path(seed.__file__), Path(__file__))


# --------------------------------------------------------------------------- #
# Generic fixtures (no real names; deterministic).
# --------------------------------------------------------------------------- #
def _drawn_log_a(artifacts):
    return {
        "log_id": "log-a", "parent_id": "bore_log-a", "entry_role": "standalone",
        "status": "DRAWN_REDLINE", "provenance": "DETERMINISTIC_AUTO",
        "drawn": True, "covered": False, "blocked": False, "drawn_lane": "NEW_TARGETS",
        "source_sheets": [1],
        "span": {"start_station": "0+00", "end_station": "1+00", "label": "0+00->1+00"},
        "closure": {"drawn_ft": 100.0, "closes": True}, "coverage": None, "blocker": None,
        "artifacts": artifacts,
        "evidence": [{"kind": "ACCOUNTABILITY_LEDGER", "ref": "r"}], "warnings": [],
    }


def _publisher_input():
    """Publisher-input manifest: placeholder artifact the publisher resolves to a real file + checksums."""
    art = {"kind": "FINAL_REDLINE_PNG", "sheet": 1, "path": ARTIFACT_PATH,
           "sha256": None, "example_placeholder": True}
    return seed.build_subset_manifest_input(
        _drawn_log_a([art]), project_id="seed-proj-test", project_name="Seed test project",
        render_commit="rc-test", engine_head="h-test", disclaimer="internal seed subset (test)")


def _rules():
    return {"version": "test-rules-1", "currency": "USD", "minor_unit_digits": 2,
            "rules": [{"code": "BORE_FT", "kind": "BASE", "unit": "ft", "unit_cost": "2.50",
                       "label": "per foot"}]}


def _png(tmp_path):
    p = tmp_path / "src" / "log_a_s1_redline_stroke.png"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"\x89PNG\r\n\x1a\nseed-deterministic-bytes")
    return p


def _run_full(tmp_path):
    return seed.seed_workflow(
        tmp_path, customer_project_id=CP, job_id=JOB, reviewed_bore_log_id=RBL, engine_run_id=RUN,
        group_id=GROUP, manifest_input=_publisher_input(),
        artifact_map={ARTIFACT_PATH: str(_png(tmp_path))}, cost_rule_set=_rules(),
        upload_bytes=b"row_id,start_station,end_station\nr1,0+00,1+00\n",
        rows=[{"row_id": "r1", "raw": {"s": "0+00"}, "normalized": {"s": "0+00"}}], at=AT, by=BY)


def _manual_bundle(root, *, mock_example=False, tamper=False):
    """Build a ready-to-store published bundle directly (not via the publisher, which forces
    mock_example=false) so the mock/tamper rejection paths can be exercised."""
    root = Path(root)
    art_dir = root / "artifacts" / "log-a"
    art_dir.mkdir(parents=True)
    data = b"\x89PNG\r\n\x1a\nmanual-bundle"
    (art_dir / "log_a_s1_redline_stroke.png").write_bytes(data)
    art = {"kind": "FINAL_REDLINE_PNG", "path": ARTIFACT_PATH, "sha256": hashlib.sha256(data).hexdigest(),
           "bytes": len(data), "published": True, "example_placeholder": False}
    manifest = seed.build_subset_manifest_input(
        _drawn_log_a([art]), project_id="seed-proj-test", project_name="Seed test project",
        render_commit="rc-test", engine_head="h-test", disclaimer="manual bundle (test)")
    manifest["mock_example"] = mock_example
    (root / "redline_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    if tamper:
        (art_dir / "log_a_s1_redline_stroke.png").write_bytes(b"TAMPERED")
    return root


def _setup_job(store, *, ready):
    """project -> job -> BORE_LOG upload -> reviewed_bore_log + one MANUAL row [-> reviewed + grouped] ->
    PLACING. Returns the upload_id."""
    create_customer_project(store, CP, "Label", AT)
    create_job(store, CP, JOB, AT, BY)
    up = accept_upload(store, CP, JOB, kind="BORE_LOG", filename="b.csv", content=b"a,b", stored_at=AT)
    transition(store, CP, JOB, UPLOADING, at=AT, by=BY)
    transition(store, CP, JOB, EXTRACTING, at=AT, by=BY)
    transition(store, CP, JOB, AWAITING_REVIEW, at=AT, by=BY)
    create_reviewed_bore_log(store, CP, JOB, up["upload_id"], RBL, at=AT, by=BY)
    add_extracted_rows(store, CP, JOB, RBL, [new_extracted_row(
        "r1", up["upload_id"], raw={}, normalized={}, extraction_method=MANUAL_ENTRY, at=AT, by=BY)],
        at=AT, by=BY)
    if ready:
        review_row_in_log(store, CP, JOB, RBL, "r1", CONFIRMED, at=AT, by=BY)
        define_segment_group(store, CP, JOB, RBL, GROUP, ["r1"], SEPARATE_BORE, at=AT, by=BY)
        set_grouping_status(store, CP, JOB, RBL, GROUP, GROUPING_CONFIRMED, at=AT, by=BY)
    transition(store, CP, JOB, PLACING, at=AT, by=BY)
    return up["upload_id"]


# --------------------------------------------------------------------------- #
# Gate: manual rows are untrusted until reviewed + grouped.
# --------------------------------------------------------------------------- #
def test_manual_rows_start_untrusted_then_review_and_group_open_the_gate(tmp_path):
    _setup_job(tmp_path, ready=False)
    rbl = load_reviewed_bore_log(tmp_path, CP, JOB, RBL)
    assert rbl["rows"][0]["review"]["status"] == UNREVIEWED
    assert is_engine_ready(rbl) is False
    review_row_in_log(tmp_path, CP, JOB, RBL, "r1", CONFIRMED, at=AT, by=BY)
    define_segment_group(tmp_path, CP, JOB, RBL, GROUP, ["r1"], SEPARATE_BORE, at=AT, by=BY)
    set_grouping_status(tmp_path, CP, JOB, RBL, GROUP, GROUPING_CONFIRMED, at=AT, by=BY)
    assert is_engine_ready(load_reviewed_bore_log(tmp_path, CP, JOB, RBL)) is True


# --------------------------------------------------------------------------- #
# Handoff rejects: not-ready gate, mock_example bundle, tampered bundle (slots stay empty).
# --------------------------------------------------------------------------- #
def test_handoff_rejects_not_ready_reviewed_bore_log(tmp_path):
    _setup_job(tmp_path, ready=False)
    record_handoff_attempt(tmp_path, CP, JOB, RBL, RUN, engine_run_status="completed", at=AT, by=BY)
    bundle = _manual_bundle(tmp_path / "bundle_ok")
    h = finalize_handoff(tmp_path, CP, JOB, RUN, bundle, at=AT, by=BY)
    assert h["status"] == REJECTED
    job = load_job(tmp_path, CP, JOB)
    assert job["slots"]["redline_manifest"] is None and job["slots"]["artifact_bundle"] is None


def test_handoff_rejects_mock_example_bundle(tmp_path):
    _setup_job(tmp_path, ready=True)
    record_handoff_attempt(tmp_path, CP, JOB, RBL, RUN, engine_run_status="completed", at=AT, by=BY)
    bundle = _manual_bundle(tmp_path / "bundle_mock", mock_example=True)
    h = finalize_handoff(tmp_path, CP, JOB, RUN, bundle, at=AT, by=BY)
    assert h["status"] == FAILED
    assert load_job(tmp_path, CP, JOB)["slots"]["artifact_bundle"] is None


def test_handoff_rejects_tampered_bundle(tmp_path):
    _setup_job(tmp_path, ready=True)
    record_handoff_attempt(tmp_path, CP, JOB, RBL, RUN, engine_run_status="completed", at=AT, by=BY)
    bundle = _manual_bundle(tmp_path / "bundle_tamper", tamper=True)
    h = finalize_handoff(tmp_path, CP, JOB, RUN, bundle, at=AT, by=BY)
    assert h["status"] == FAILED
    assert load_job(tmp_path, CP, JOB)["slots"]["artifact_bundle"] is None


# --------------------------------------------------------------------------- #
# Full spine: a real subset bundle finalizes; downstream stages produce real state.
# --------------------------------------------------------------------------- #
def test_full_seed_spine_produces_real_state(tmp_path):
    r = _run_full(tmp_path)

    assert r["engine_ready"] is True
    assert r["handoff"]["status"] == SUCCEEDED

    job = load_job(tmp_path, CP, JOB)
    assert job["status"] == PLACED
    assert job["slots"]["redline_manifest"]["ref"]["validation_status"] == "VALIDATED"
    assert job["slots"]["artifact_bundle"]["ref"]["validation_status"] == "VALIDATED"

    # manifest-backed artifacts carry real sha256 + bytes
    assert r["artifacts"] and all(a["kind"] == "FINAL_REDLINE_PNG" for a in r["artifacts"])
    assert all(a["sha256"] and a["bytes"] for a in r["artifacts"])

    # KMZ pixel-only -> BLOCKED (never fabricates coordinates)
    assert r["kmz"]["status"] == kmz.BLOCKED

    # closeout evaluated, not blocked, and NOT approved (no privileged transition was used)
    assert r["closeout"]["status"] == co.READY_FOR_APPROVAL
    assert r["closeout_summary"]["is_blocked"] is False
    assert r["closeout"]["decision"] is None

    # billing computed server-side from the generic rules (100.0 ft * 2.50 = 250.00); not billable yet
    assert r["billing"]["status"] == bill.COMPUTED
    assert r["billing_view"]["final_total"] == "250.00"
    assert r["billing_view"]["is_billable"] is False

    # export is a descriptor of references; manifest in, KMZ omitted (pixel-only)
    assert r["export"]["status"] == exp.READY
    assert "REDLINE_MANIFEST" in r["export_view"]["included_sections"]
    assert "KMZ_EXPORT" in r["export_view"]["omitted_sections"]


def test_artifact_read_is_manifest_backed_and_path_guarded(tmp_path):
    r = _run_full(tmp_path)
    bundle_store = job_dir(tmp_path, CP, JOB) / BUNDLE_STORE_SUBDIR
    bundle = StaticBundleConsumer(bundle_store, enable=True).open_bundle(r["bundle_id"])
    desc = bundle.resolve_artifact(ARTIFACT_PATH, read_bytes=False)
    assert desc["path"] == ARTIFACT_PATH
    with pytest.raises(ArtifactNotServableError):
        bundle.resolve_artifact("artifacts/log-a/not_in_manifest.png", read_bytes=False)


def test_export_generates_no_files_only_a_descriptor(tmp_path):
    _run_full(tmp_path)
    doc_exts = {".pdf", ".html", ".htm", ".zip", ".kmz", ".kml", ".docx"}
    generated = [str(p) for p in job_dir(tmp_path, CP, JOB).rglob("*")
                 if p.suffix.lower() in doc_exts]
    assert generated == []


# --------------------------------------------------------------------------- #
# Internal/test-only guarantees.
# --------------------------------------------------------------------------- #
def test_seed_store_root_is_under_gitignored_outputs():
    parts = seed.SEED_STORE_ROOT.parts
    assert "data" in parts and "outputs" in parts
    assert seed.SEED_STORE_ROOT.name == "product_store_seed"


def test_new_files_have_no_operator_name_tokens():
    """Mechanism (A): if NAME_TOKENS is set, none may appear in the seed files. Embeds no real names."""
    raw = os.environ.get("NAME_TOKENS", "").strip()
    if not raw:
        return  # optional; CI/operator runs with the deployment's real tokens to enforce absence
    tokens = [t for t in re.split(r"[|,\s]+", raw) if t]
    blob = "\n".join(p.read_text(encoding="utf-8") for p in NEW_FILES).lower()
    hits = sorted({t for t in tokens if re.search(r"\b" + re.escape(t.lower()) + r"\b", blob)})
    assert not hits, "operator-supplied NAME_TOKENS leaked into seed files: %r" % hits
