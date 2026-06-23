"""Phase 10 — downloadable closeout export bundle (.zip) tests.

A recognized deterministic job's export bundle is a REAL, structurally-valid zip assembled from EXISTING
trusted output: the redline manifest, the sha256-verified FINAL_REDLINE_PNG bytes, the closeout / export /
KMZ status JSON, the reviewed-bore-log metadata, and a README. Nothing is rendered or faked; a pixel-only
KMZ is reported honestly as BLOCKED inside the bundle (and no .kmz member is written). Self-contained +
name-free (mirrors test_recognized_corpus_handoff: render dir monkeypatched, registry injected).
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import zipfile

import pytest

from truelinev2.contracts.customer_project import create_customer_project
from truelinev2.contracts.processing_job import create_job
from truelinev2.contracts.upload_pipeline import accept_upload
from truelinev2.contracts.extracted_row import CONFIRMED, MANUAL_ENTRY, new_extracted_row
from truelinev2.contracts.reviewed_bore_log import (
    GROUPING_CONFIRMED, SEPARATE_BORE, add_extracted_rows, create_reviewed_bore_log,
    define_segment_group, review_row_in_log, set_grouping_status,
)
from truelinev2.contracts import recognized_corpus_handoff as rch
from truelinev2.contracts import product_workflow as pw
from truelinev2.contracts.export_bundle import NoRedlineBundleError, build_export_zip

AT, BY, CP, JOB, RBL = "2026-06-23T00:00:00Z", "op-1", "cp-0001", "job-0001", "rbl-1"

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


def _recognized_job(tmp, monkeypatch):
    rdir = tmp / "render"
    rdir.mkdir()
    (rdir / "log8_s18_redline_stroke.png").write_bytes(_PNG)
    (rdir / "log8_s22_redline_stroke.png").write_bytes(_PNG)
    monkeypatch.setattr(rch, "_DETERMINISTIC_RENDER_DIR", rdir)
    reg = {"corpora": [{"corpus_id": "recognized-corpus-001", "display_name": "Test Corpus",
                        "plan_sha256": [hashlib.sha256(_PDF).hexdigest()],
                        "bore_log_sha256_to_log": {hashlib.sha256(_BORE).hexdigest(): "log8"},
                        "log_facts": {}}], "configured": True}
    create_customer_project(tmp, CP, "Label", AT)
    create_job(tmp, CP, JOB, AT, BY)
    accept_upload(tmp, CP, JOB, kind="PLAN_PDF", filename="plan.pdf", content=_PDF, stored_at=AT)
    bore = accept_upload(tmp, CP, JOB, kind="BORE_LOG", filename="bore_log8.xlsx", content=_BORE, stored_at=AT)
    create_reviewed_bore_log(tmp, CP, JOB, bore["upload_id"], RBL, at=AT, by=BY)
    row = new_extracted_row("row-1", bore["upload_id"], raw={"s": "0+00"}, normalized={"s": "0+00"},
                            extraction_method=MANUAL_ENTRY, at=AT, by=BY)
    add_extracted_rows(tmp, CP, JOB, RBL, [row], at=AT, by=BY)
    review_row_in_log(tmp, CP, JOB, RBL, "row-1", CONFIRMED, at=AT, by=BY)
    define_segment_group(tmp, CP, JOB, RBL, "g-1", ["row-1"], SEPARATE_BORE, at=AT, by=BY)
    set_grouping_status(tmp, CP, JOB, RBL, "g-1", GROUPING_CONFIRMED, at=AT, by=BY)
    pw.run_product_redline(tmp, CP, JOB, registry=reg, at=AT, by=BY)          # renders + sets the bundle slot
    pw.assemble_closeout_package(tmp, CP, JOB, at=AT, by=BY)                  # closeout + export descriptor


def test_export_zip_is_valid_and_complete(tmp_path, monkeypatch):
    _recognized_job(tmp_path, monkeypatch)
    data, filename = build_export_zip(tmp_path, CP, JOB)
    assert filename == "redline_export_%s.zip" % JOB
    zf = zipfile.ZipFile(io.BytesIO(data))
    assert zf.testzip() is None
    names = set(zf.namelist())
    assert "redline_manifest.json" in names
    assert "README.txt" in names
    assert "status/closeout_review.json" in names
    assert "status/export_package.json" in names
    assert "status/kmz_export.json" in names
    assert "status/reviewed_bore_logs.json" in names
    pngs = [n for n in names if n.endswith(".png")]
    assert pngs and all(zf.read(n)[:8] == b"\x89PNG\r\n\x1a\n" for n in pngs)   # real PNG bytes
    manifest = json.loads(zf.read("redline_manifest.json"))
    assert manifest["bundle_origin"] == "DETERMINISTIC_RECOGNIZED_CORPUS"
    # The pixel-only KMZ is reported honestly + no .kmz member is written (never faked).
    kmz = json.loads(zf.read("status/kmz_export.json"))
    assert kmz["status"] == "BLOCKED" and kmz["geometry_basis"] == "UNSUPPORTED_PIXEL_ONLY"
    assert not any(n.endswith(".kmz") for n in names)
    assert "refuses to fake" in zf.read("README.txt").decode("utf-8")


def test_export_zip_is_deterministic(tmp_path, monkeypatch):
    _recognized_job(tmp_path, monkeypatch)
    a, _ = build_export_zip(tmp_path, CP, JOB)
    b, _ = build_export_zip(tmp_path, CP, JOB)
    assert hashlib.sha256(a).hexdigest() == hashlib.sha256(b).hexdigest()       # byte-stable


def test_export_zip_blocks_when_no_redline_bundle(tmp_path):
    create_customer_project(tmp_path, CP, "Label", AT)
    create_job(tmp_path, CP, JOB, AT, BY)
    with pytest.raises(NoRedlineBundleError):
        build_export_zip(tmp_path, CP, JOB)
