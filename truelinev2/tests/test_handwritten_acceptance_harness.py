"""Offline tests for the handwritten-corpus acceptance harness
(``truelinev2/qa/run_handwritten_corpus_acceptance.py``): a keyless run over a synthetic mini-corpus, a
deterministic fake-provider run, and two ADVERSARIAL scenarios that prove the harness's own hard checks
(no-fabrication scan, reconciliation) fire independently of the extraction seam's own validation -- by
monkeypatching ``extract_handwritten`` to return a hand-built, already-poisoned/tampered result the real
seam would never itself produce. No real corpus file, network call, or product-store write anywhere here.
"""
from __future__ import annotations

import hashlib
import io
import json

from truelinev2.contracts.handwritten_extraction import PAGE_RECORD_FORMAT
from truelinev2.extract.handwritten_borelog import (
    HANDWRITTEN_VISION_PROVIDER_NOT_CONFIGURED,
    extract_handwritten as real_extract_handwritten,
)
from truelinev2.tests.test_handwritten_borelog_extract import (
    HEADER_LINES,
    _blank_cell,
    _cell,
    _pdf_bytes,
    _reading,
)

import truelinev2.qa.run_handwritten_corpus_acceptance as harness_mod
from truelinev2.qa.run_handwritten_corpus_acceptance import main, run

_FAKE_PROVIDER_MODULE = "truelinev2.extract.vision_providers.fake"


def _png_bytes() -> bytes:
    from PIL import Image

    img = Image.new("RGB", (12, 12), color=(10, 20, 30))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _report(out_dir) -> dict:
    return json.loads((out_dir / "report.json").read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# (a) keyless run -- works today with no provider configured.
# --------------------------------------------------------------------------- #
def test_keyless_run_over_mini_corpus_refuses_image_page_and_exits_clean(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "log1.pdf").write_bytes(
        _pdf_bytes([HEADER_LINES + ["STA 0+00 3.5 5'", "STA 0+50 3.5 5'"]]))
    (corpus / "log2.pdf").write_bytes(
        _pdf_bytes([HEADER_LINES + ["STA 0+00 3.5 5'", "STA 1+00 3.5 5'", "STA 2+00 3.5 5'"]]))
    (corpus / "photo.png").write_bytes(_png_bytes())
    out_dir = tmp_path / "out"

    exit_code = run(corpus_dir=corpus, out_dir=out_dir, provider_name=None, fixtures_dir=None)

    assert exit_code == 0
    report = _report(out_dir)
    assert report["corpus_file_count"] == 3
    assert report["verdict"] == "CLEAN"
    assert report["reconciliation_failures"] == []
    assert report["fabrication_failures"] == []
    assert report["stats"]["files_by_type"] == {".pdf": 2, ".png": 1}
    assert report["stats"]["pages_by_outcome"][HANDWRITTEN_VISION_PROVIDER_NOT_CONFIGURED] == 1
    assert report["stats"]["pages_by_outcome"]["EXTRACTED"] == 2
    assert (out_dir / "report.md").is_file()
    md = (out_dir / "report.md").read_text(encoding="utf-8")
    assert "HANDWRITTEN_VISION_PROVIDER_NOT_CONFIGURED" in md
    assert "RECONCILIATION: PASS" in md
    assert "NO-FABRICATION SCAN: PASS" in md
    # No absolute path (this test's own tmp_path) leaks into the report content.
    assert str(tmp_path) not in json.dumps(report)
    assert str(tmp_path) not in md


# --------------------------------------------------------------------------- #
# (b) deterministic fake-provider run -- VISION_OCR proposals counted.
# --------------------------------------------------------------------------- #
def test_fake_provider_run_produces_counted_vision_ocr_proposal(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    png_bytes = _png_bytes()
    (corpus / "photo.png").write_bytes(png_bytes)
    fixtures_dir = tmp_path / "fixtures"
    fixtures_dir.mkdir()
    sha = hashlib.sha256(png_bytes).hexdigest()
    fixture_record = {
        "record_format": PAGE_RECORD_FORMAT,
        "header": {"date": _blank_cell(), "crew": _blank_cell(),
                  "job_name": _blank_cell(), "print_raw": _blank_cell()},
        "readings": [_reading("0+00", 3.5, 5.0, row_index=0), _reading("0+50", 3.5, 5.0, row_index=1)],
        "page_status": "EXTRACTED", "refusal": None, "warnings": [], "audit": [],
    }
    (fixtures_dir / ("%s-p0.json" % sha)).write_text(json.dumps(fixture_record), encoding="utf-8")
    out_dir = tmp_path / "out"

    exit_code = run(corpus_dir=corpus, out_dir=out_dir, provider_name=_FAKE_PROVIDER_MODULE,
                    fixtures_dir=fixtures_dir)

    assert exit_code == 0
    report = _report(out_dir)
    assert report["verdict"] == "CLEAN"
    assert report["stats"]["pages_by_outcome"].get("EXTRACTED") == 1
    assert report["stats"]["proposals_by_method"].get("VISION_OCR") == 1
    assert report["files"][0]["proposal_count"] == 1


# --------------------------------------------------------------------------- #
# HARD CHECK -- no-fabrication scan fires on a poisoned extraction result, independent of the seam's own
# validate_page_extraction (bypassed here by monkeypatching extract_handwritten directly).
# --------------------------------------------------------------------------- #
def test_poisoned_extraction_result_triggers_fabrication_failure(tmp_path, monkeypatch):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "log.pdf").write_bytes(_pdf_bytes([HEADER_LINES + ["STA 0+00 3.5 5'"]]))
    out_dir = tmp_path / "out"

    poisoned_cell = _cell(value="9+99", status="UNREADABLE", verbatim="9+99", confidence=None)

    def _poisoned(data, file_name, *, upload_id, provider_name=None, timeout_s=90.0, providers=None):
        source = {"upload_id": upload_id, "sha256": "a" * 64, "file_name": file_name,
                 "page_index": 0, "page_count": 1}
        page = {
            "record_format": PAGE_RECORD_FORMAT, "source": source, "method": "TEXT_LAYER",
            "extractor": "poisoned-test-double",
            "header": {"date": _blank_cell(), "crew": _blank_cell(),
                      "job_name": _blank_cell(), "print_raw": _blank_cell()},
            "readings": [{"station": poisoned_cell, "depth_ft": _blank_cell(), "boc_ft": _blank_cell(),
                        "column_index": 0, "row_index": 0}],
            "page_status": "EXTRACTED", "refusal": None, "warnings": [], "audit": [],
        }
        return {"pages": [page], "proposals": [],
               "page_ledger": [{"page_index": 0, "status": "NO_USABLE_STATION_RUN", "refusal": None,
                                "warnings": [], "proposal_count": 0, "runs_skipped": []}]}

    monkeypatch.setattr(harness_mod, "extract_handwritten", _poisoned)

    exit_code = run(corpus_dir=corpus, out_dir=out_dir, provider_name=None, fixtures_dir=None)

    assert exit_code == 2
    report = _report(out_dir)
    assert report["verdict"] == "FAILED"
    assert report["reconciliation_failures"] == []
    assert report["fabrication_failures"], "expected at least one fabrication failure"
    assert any("readings[0].station" in f["field"] for f in report["fabrication_failures"])
    assert any("UNREADABLE" in f["detail"] for f in report["fabrication_failures"])


# --------------------------------------------------------------------------- #
# HARD CHECK -- reconciliation fires when a page vanishes from the ledger (simulated ledger tamper).
# --------------------------------------------------------------------------- #
def test_ledger_missing_a_page_triggers_reconciliation_failure(tmp_path, monkeypatch):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "log.pdf").write_bytes(_pdf_bytes([
        HEADER_LINES + ["STA 0+00 3.5 5'", "STA 0+50 3.5 5'"],
        HEADER_LINES + ["STA 0+00 3.4 4'", "STA 0+30 3.4 4'"],
    ]))
    out_dir = tmp_path / "out"

    def _tampered(data, file_name, *, upload_id, provider_name=None, timeout_s=90.0, providers=None):
        result = real_extract_handwritten(data, file_name, upload_id=upload_id,
                                          provider_name=provider_name, timeout_s=timeout_s)
        result = dict(result)
        result["page_ledger"] = result["page_ledger"][:1]     # drop page 1's ledger entry
        return result

    monkeypatch.setattr(harness_mod, "extract_handwritten", _tampered)

    exit_code = run(corpus_dir=corpus, out_dir=out_dir, provider_name=None, fixtures_dir=None)

    assert exit_code == 2
    report = _report(out_dir)
    assert report["verdict"] == "FAILED"
    assert report["fabrication_failures"] == []
    assert report["reconciliation_failures"]
    failure = report["reconciliation_failures"][0]
    assert failure["expected_page_count"] == 2
    assert failure["ledger_page_indices"] == [0]


# --------------------------------------------------------------------------- #
# CLI wiring + harness-level error mapping (exit 1, never a fake 0/2).
# --------------------------------------------------------------------------- #
def test_main_cli_happy_path_matches_run(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "log.pdf").write_bytes(_pdf_bytes([HEADER_LINES + ["STA 0+00 3.5 5'", "STA 0+50 3.5 5'"]]))
    out_dir = tmp_path / "out"

    exit_code = main(["--corpus", str(corpus), "--out", str(out_dir)])

    assert exit_code == 0
    assert (out_dir / "report.json").is_file()
    assert (out_dir / "report.md").is_file()


def test_main_cli_missing_corpus_dir_exits_one(tmp_path):
    exit_code = main(["--corpus", str(tmp_path / "does-not-exist"), "--out", str(tmp_path / "out")])
    assert exit_code == 1
