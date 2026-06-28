"""Contract tests: recognized-corpus auto-handoff bridge.

A POSITIVELY-recognized uploaded plan (exact sha256, per the injected deployment REGISTRY) + an engine-ready
reviewed_bore_log whose source BORE_LOG sha256 maps to a DRAWN deterministic log → publishes the EXISTING
deterministic render PNG(s) for that log as a job-local FINAL_REDLINE_PNG bundle (bundle_origin
DETERMINISTIC_RECOGNIZED_CORPUS, per-log provenance DETERMINISTIC_AUTO — engine-derived, NOT human-clicked).
Unknown / unmapped uploads stay BLOCKED with named blockers. Self-contained + name-free: the registry is a
test fixture (no real corpus names baked in), and the deterministic render dir is monkeypatched, so the test
ships its own small PDF/PNG bytes and never depends on the committed corpus.
"""
from __future__ import annotations

import base64
import hashlib
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
from truelinev2.contracts import recognized_corpus_handoff as rch

AT = "2026-06-22T00:00:00Z"
BY = "op-1"
CP = "cp-0001"
JOB = "job-0001"
RBL = "rbl-1"

# Minimal valid 1-page PDF (ships the bytes; never imports fitz).
_PDF = base64.b64decode(
    "JVBERi0xLjcKJcK1wrYKJSBXcml0dGVuIGJ5IE11UERGIDEuMjcuMgoKMSAwIG9iago8PC9UeXBlL0NhdGFsb2cvUGFnZXMg"
    "MiAwIFIvSW5mbzw8L1Byb2R1Y2VyKE11UERGIDEuMjcuMik+Pj4+CmVuZG9iagoKMiAwIG9iago8PC9UeXBlL1BhZ2VzL0Nv"
    "dW50IDEvS2lkc1s0IDAgUl0+PgplbmRvYmoKCjMgMCBvYmoKPDw+PgplbmRvYmoKCjQgMCBvYmoKPDwvVHlwZS9QYWdlL01l"
    "ZGlhQm94WzAgMCA2MTIgNzkyXS9Sb3RhdGUgMC9SZXNvdXJjZXMgMyAwIFIvUGFyZW50IDIgMCBSPj4KZW5kb2JqCgp4cmVm"
    "CjAgNQowMDAwMDAwMDAwIDY1NTM1IGYgCjAwMDAwMDAwNDIgMDAwMDAgbiAKMDAwMDAwMDEyMCAwMDAwMCBuIAowMDAwMDAw"
    "MTcyIDAwMDAwIG4gCjAwMDAwMDAxOTMgMDAwMDAgbiAKCnRyYWlsZXIKPDwvU2l6ZSA1L1Jvb3QgMSAwIFIvSURbPDI1QzNB"
    "MjRFNEVDMjgwQzJBQzY1QzM4NEMzQTJDMjg1PjwxQjAyRUMzMkUxRDMwNUYzNDJBRjZFMjI2MkYzNTZDND5dPj4Kc3RhcnR4"
    "cmVmCjI4NAolJUVPRgo=")
# Minimal valid 1x1 PNG (stands in for a committed deterministic redline-stroke render).
_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")

_BORE = b"bore-log-8 content"


def _job(tmp, plan_bytes, bore_bytes):
    create_customer_project(tmp, CP, "Label", AT)
    create_job(tmp, CP, JOB, AT, BY)
    accept_upload(tmp, CP, JOB, kind="PLAN_PDF", filename="plan.pdf", content=plan_bytes, stored_at=AT)
    bore = accept_upload(tmp, CP, JOB, kind="BORE_LOG", filename="bore_log8.xlsx", content=bore_bytes, stored_at=AT)
    create_reviewed_bore_log(tmp, CP, JOB, bore["upload_id"], RBL, at=AT, by=BY)
    row = new_extracted_row("row-1", bore["upload_id"], raw={"s": "0+00"}, normalized={"s": "0+00"},
                            extraction_method=MANUAL_ENTRY, at=AT, by=BY)
    add_extracted_rows(tmp, CP, JOB, RBL, [row], at=AT, by=BY)
    review_row_in_log(tmp, CP, JOB, RBL, "row-1", CONFIRMED, at=AT, by=BY)
    define_segment_group(tmp, CP, JOB, RBL, "g-1", ["row-1"], SEPARATE_BORE, at=AT, by=BY)
    set_grouping_status(tmp, CP, JOB, RBL, "g-1", GROUPING_CONFIRMED, at=AT, by=BY)


def _registry(tmp_path, monkeypatch, *, plan_bytes, bore_bytes, recognize_plan, map_bore_to):
    """Patch the committed render dir to a tmp dir with two log8 PNGs and build an injectable registry."""
    rdir = tmp_path / "render"
    rdir.mkdir()
    (rdir / "log8_s18_redline_stroke.png").write_bytes(_PNG)
    (rdir / "log8_s22_redline_stroke.png").write_bytes(_PNG)
    monkeypatch.setattr(rch, "_DETERMINISTIC_RENDER_DIR", rdir)
    corpora = []
    if recognize_plan:
        corpora.append({
            "corpus_id": "recognized-corpus-001",
            "display_name": "Test Corpus",
            "plan_sha256": [hashlib.sha256(plan_bytes).hexdigest()],
            "bore_log_sha256_to_log": ({hashlib.sha256(bore_bytes).hexdigest(): map_bore_to}
                                       if map_bore_to else {}),
            "log_facts": {"log8": {"parent_id": "bore_log8",
                                   "span": {"start_station": "0+00", "end_station": "3+90",
                                            "label": "0+00->3+90"}}},
        })
    return {"corpora": corpora, "configured": True}


def test_registry_path_loading_reports_configured_state(tmp_path):
    # Unset / missing / unreadable => NOT configured (an OPERATIONAL gap, distinct from "plan not in registry").
    assert rch.load_registry(None) == {"corpora": [], "configured": False}
    assert rch.load_registry("C:/no/such/registry.json") == {"corpora": [], "configured": False}
    # A real readable registry file => configured, even when it holds zero corpora.
    empty = tmp_path / "empty_registry.json"
    empty.write_text(json.dumps({"corpora": []}), encoding="utf-8")
    assert rch.load_registry(empty) == {"corpora": [], "configured": True}


def test_recognized_corpus_runnable_renders_deterministic_bundle(tmp_path, monkeypatch):
    reg = _registry(tmp_path, monkeypatch, plan_bytes=_PDF, bore_bytes=_BORE,
                    recognize_plan=True, map_bore_to="log8")
    _job(tmp_path, _PDF, _BORE)

    ev = rch.evaluate_recognized_corpus_handoff(tmp_path, CP, JOB, registry=reg)
    assert ev["status"] == "RUNNABLE" and ev["runnable"] is True
    assert ev["recognized_corpus_id"] == "recognized-corpus-001"          # generic id, NOT the display_name
    assert ev["recognized_package_label"] == "Recognized uploaded project package"
    assert "recognized_corpus" not in ev                                   # the display_name field is gone
    assert ev["deterministic_log_id"] == "log8"
    assert sorted(ev["render_sheets"]) == [18, 22]

    summary = rch.render_recognized_corpus_handoff(tmp_path, CP, JOB, registry=reg, at=AT, by=BY)
    assert summary["status"] == "SUCCEEDED"
    assert summary["bundle_origin"] == "DETERMINISTIC_RECOGNIZED_CORPUS"
    assert summary["recognized_corpus_id"] == "recognized-corpus-001"
    assert summary["recognized_package_label"] == "Recognized uploaded project package"
    assert summary["artifact_count"] == 2
    assert summary["artifacts"] and all(a["kind"] == "FINAL_REDLINE_PNG" for a in summary["artifacts"])
    assert all(a["sha256"] and a["bytes"] for a in summary["artifacts"])

    job = load_job(tmp_path, CP, JOB)
    assert job["slots"]["artifact_bundle"] is not None
    assert job["slots"]["redline_manifest"] is not None

    bundle_id = summary["bundle_id"]
    mpath = job_dir(tmp_path, CP, JOB) / "bundle_store" / "bundles" / bundle_id / "redline_manifest.json"
    m = json.loads(mpath.read_text(encoding="utf-8"))
    assert m["mock_example"] is False
    assert m["bundle_origin"] == "DETERMINISTIC_RECOGNIZED_CORPUS"
    assert m["logs"][0]["log_id"] == "log8"
    assert m["logs"][0]["provenance"] == "DETERMINISTIC_AUTO"
    assert m["logs"][0]["status"] == "DRAWN_REDLINE"
    assert "HUMAN_CONFIRMED" not in json.dumps(m)
    assert "source_anchor" not in json.dumps(m).lower()
    assert "Test Corpus" not in json.dumps(m)                              # display_name never reaches the bundle

    again = rch.render_recognized_corpus_handoff(tmp_path, CP, JOB, registry=reg, at=AT, by=BY)
    assert again["bundle_id"] == summary["bundle_id"]


def test_recognized_multi_bore_publishes_all_logs(tmp_path, monkeypatch):
    # Two engine-ready bore-logs mapping to two DRAWN logs -> ONE job-local multi-log bundle (scales to N);
    # the per-bore recognized_logs list drives the step-through. A single-bore job still yields one log.
    rdir = tmp_path / "render"
    rdir.mkdir()
    for n in ("log8_s18", "log8_s22", "log9_s7"):
        (rdir / ("%s_redline_stroke.png" % n)).write_bytes(_PNG)
    monkeypatch.setattr(rch, "_DETERMINISTIC_RENDER_DIR", rdir)
    bore8, bore9 = b"bore-eight", b"bore-nine"
    reg = {"corpora": [{
        "corpus_id": "recognized-corpus-001", "display_name": "Test Corpus",
        "plan_sha256": [hashlib.sha256(_PDF).hexdigest()],
        "bore_log_sha256_to_log": {hashlib.sha256(bore8).hexdigest(): "log8",
                                   hashlib.sha256(bore9).hexdigest(): "log9"},
    }], "configured": True}

    create_customer_project(tmp_path, CP, "Label", AT)
    create_job(tmp_path, CP, JOB, AT, BY)
    accept_upload(tmp_path, CP, JOB, kind="PLAN_PDF", filename="plan.pdf", content=_PDF, stored_at=AT)
    for i, (bore, _lg) in enumerate([(bore8, "log8"), (bore9, "log9")], start=1):
        up = accept_upload(tmp_path, CP, JOB, kind="BORE_LOG", filename="bore%d.xlsx" % i,
                           content=bore, stored_at=AT)
        rbl = "rbl-%d" % i
        create_reviewed_bore_log(tmp_path, CP, JOB, up["upload_id"], rbl, at=AT, by=BY)
        row = new_extracted_row("row-%d" % i, up["upload_id"], raw={"s": "0+00"}, normalized={"s": "0+00"},
                                extraction_method=MANUAL_ENTRY, at=AT, by=BY)
        add_extracted_rows(tmp_path, CP, JOB, rbl, [row], at=AT, by=BY)
        review_row_in_log(tmp_path, CP, JOB, rbl, "row-%d" % i, CONFIRMED, at=AT, by=BY)
        define_segment_group(tmp_path, CP, JOB, rbl, "g-%d" % i, ["row-%d" % i], SEPARATE_BORE, at=AT, by=BY)
        set_grouping_status(tmp_path, CP, JOB, rbl, "g-%d" % i, GROUPING_CONFIRMED, at=AT, by=BY)

    ev = rch.evaluate_recognized_corpus_handoff(tmp_path, CP, JOB, registry=reg)
    assert ev["runnable"] is True
    assert {r["log_id"] for r in ev["recognized_logs"]} == {"log8", "log9"}
    assert all("render_sheets" in r and "reviewed_bore_log_id" in r for r in ev["recognized_logs"])

    summary = rch.render_recognized_corpus_handoff(tmp_path, CP, JOB, registry=reg, at=AT, by=BY)
    assert summary["status"] == "SUCCEEDED"
    assert {a["log_id"] for a in summary["artifacts"]} == {"log8", "log9"}
    assert summary["artifact_count"] == 3                      # log8 s18+s22 + log9 s7

    bundle_id = summary["bundle_id"]
    mpath = job_dir(tmp_path, CP, JOB) / "bundle_store" / "bundles" / bundle_id / "redline_manifest.json"
    m = json.loads(mpath.read_text(encoding="utf-8"))
    assert {lg["log_id"] for lg in m["logs"]} == {"log8", "log9"}
    assert m["summary"]["frontier"] == "2/2"
    assert m["provenance_counts"]["DETERMINISTIC_AUTO"] == 2
    assert "Test Corpus" not in json.dumps(m)                  # display_name never reaches the bundle


def test_unknown_plan_blocked(tmp_path, monkeypatch):
    reg = _registry(tmp_path, monkeypatch, plan_bytes=_PDF, bore_bytes=_BORE,
                    recognize_plan=False, map_bore_to="log8")
    _job(tmp_path, _PDF, _BORE)
    ev = rch.evaluate_recognized_corpus_handoff(tmp_path, CP, JOB, registry=reg)
    assert ev["status"] == "BLOCKED" and ev["runnable"] is False
    assert ev["recognized_corpus_id"] is None
    codes = {b["code"] for b in ev["blockers"]}
    assert "UPLOADED_CORPUS_NOT_RECOGNIZED" in codes
    assert "UPLOADED_CORPUS_AUTO_HANDOFF_NOT_IMPLEMENTED" in codes
    assert "RECOGNIZED_CORPUS_REGISTRY_NOT_CONFIGURED" not in codes   # registry IS configured, plan just unknown
    with pytest.raises(rch.RecognizedCorpusError):
        rch.render_recognized_corpus_handoff(tmp_path, CP, JOB, registry=reg, at=AT, by=BY)


def test_registry_not_configured_is_distinct_blocker(tmp_path):
    # The exact public-staging failure: a genuinely-registered plan + bore-log, but the serving process has
    # NO registry loaded (TL2_RECOGNIZED_CORPUS_REGISTRY unset). The honest blocker is
    # RECOGNIZED_CORPUS_REGISTRY_NOT_CONFIGURED — NOT the misleading "your plan is not a recognized corpus".
    _job(tmp_path, _PDF, _BORE)
    ev = rch.evaluate_recognized_corpus_handoff(tmp_path, CP, JOB, registry=rch.load_registry(None))
    assert ev["status"] == "BLOCKED" and ev["runnable"] is False
    assert ev["recognized_corpus_id"] is None
    codes = {b["code"] for b in ev["blockers"]}
    assert "RECOGNIZED_CORPUS_REGISTRY_NOT_CONFIGURED" in codes
    assert "UPLOADED_CORPUS_NOT_RECOGNIZED" not in codes
    with pytest.raises(rch.RecognizedCorpusError):
        rch.render_recognized_corpus_handoff(tmp_path, CP, JOB, registry=rch.load_registry(None), at=AT, by=BY)


def test_recognized_plan_but_unmapped_bore_log_blocked(tmp_path, monkeypatch):
    reg = _registry(tmp_path, monkeypatch, plan_bytes=_PDF, bore_bytes=_BORE,
                    recognize_plan=True, map_bore_to=None)
    _job(tmp_path, _PDF, _BORE)
    ev = rch.evaluate_recognized_corpus_handoff(tmp_path, CP, JOB, registry=reg)
    assert ev["status"] == "BLOCKED" and ev["runnable"] is False
    assert ev["recognized_corpus_id"] == "recognized-corpus-001"   # plan recognized (generic id)...
    assert ev["deterministic_log_id"] is None                       # ...but bore-log not mapped
    codes = {b["code"] for b in ev["blockers"]}
    assert "BORE_LOG_NOT_MAPPED_TO_DETERMINISTIC_LOG" in codes
    with pytest.raises(rch.RecognizedCorpusError):
        rch.render_recognized_corpus_handoff(tmp_path, CP, JOB, registry=reg, at=AT, by=BY)
