"""Contract tests: field segment-evidence packages (the mobile submit-to-review WRITE contract).

Locks the owner's field rules: a start station photo is REQUIRED to begin and an end station photo is
REQUIRED to complete/submit (the only default-required photos); every logged problem area requires at
least one bound problem photo; OPTIONAL_CONTEXT photos are never required; bore readings follow a
~50 ft NOMINAL cadence that is advisory only. A required photo counts ONLY when it binds to a real job
upload of kind PHOTO — claimed-but-unbacked photos satisfy nothing. Field evidence supports review and
NEVER creates a redline / AUTO / placement (doctrine flags locked; forbidden-import AST scan).
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from truelinev2.contracts import field_evidence as fe
from truelinev2.contracts.customer_project import create_customer_project
from truelinev2.contracts.processing_job import create_job, load_job
from truelinev2.contracts.upload_pipeline import accept_upload

AT, BY, CP, JOB, SEG = "2026-01-01T00:00:00+00:00", "field-1", "cp-aaa", "job-1", "seg-001"


def _store(tmp_path: Path) -> Path:
    store = tmp_path / "product_store"
    create_customer_project(store, CP, "Label", AT)
    create_job(store, CP, JOB, AT, BY)
    return store


def _photo(store: Path, name: str) -> str:
    up = accept_upload(store, CP, JOB, kind="PHOTO", filename=name,
                       content=("photo-bytes-%s" % name).encode(), stored_at=AT)
    return up["upload_id"]


def _photo_ref(evidence_id: str, kind: str, upload_id=None, **extra) -> dict:
    return {"evidence_id": evidence_id, "kind": kind, "upload_id": upload_id, **extra}


def _payload(**over) -> dict:
    base = {"start_station": "11+75", "end_station": "13+25",
            "photos": [], "problems": [], "readings": [], "notes": None}
    base.update(over)
    return base


def _save(store, payload) -> dict:
    return fe.save_field_evidence(store, CP, JOB, SEG, payload, at=AT, by=BY)


def _submit(store) -> dict:
    return fe.submit_field_evidence(store, CP, JOB, SEG, at=AT, by=BY)


def _complete_payload(store) -> dict:
    start, end = _photo(store, "start.jpg"), _photo(store, "end.jpg")
    return _payload(photos=[_photo_ref("ev-start", fe.START_STATION, start, station="11+75"),
                            _photo_ref("ev-end", fe.END_STATION, end, station="13+25")])


# --------------------------------------------------------------------------- #
# Save / load / upsert.
# --------------------------------------------------------------------------- #
def test_save_creates_draft_with_doctrine_flags(tmp_path):
    store = _store(tmp_path)
    rec = _save(store, _payload())
    assert rec["record_format"] == fe.FIELD_EVIDENCE_RECORD_FORMAT
    assert rec["status"] == fe.DRAFT
    assert rec["segment_id"] == SEG and rec["processing_job_id"] == JOB
    # Doctrine flags: field evidence never draws/places/promotes.
    assert rec["creates_redline"] is False and rec["performs_auto"] is False
    assert rec["performs_placement"] is False and rec["review_support_only"] is True
    assert rec["audit"][-1]["action"] == "field_evidence_saved"
    assert fe.load_field_evidence(store, CP, JOB, SEG)["segment_id"] == SEG
    assert [r["segment_id"] for r in fe.list_field_evidence(store, CP, JOB)] == [SEG]


def test_upsert_preserves_created_at_and_appends_audit(tmp_path):
    store = _store(tmp_path)
    _save(store, _payload())
    rec = fe.save_field_evidence(store, CP, JOB, SEG, _payload(notes="second pass"),
                                 at="2026-01-02T00:00:00+00:00", by=BY)
    assert rec["created_at"] == AT and rec["updated_at"] == "2026-01-02T00:00:00+00:00"
    assert len(rec["audit"]) == 2 and rec["notes"] == "second pass"


def test_invalid_segment_id_refused(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(fe.InvalidSegmentIdError):
        fe.save_field_evidence(store, CP, JOB, "../escape", _payload(), at=AT, by=BY)


def test_malformed_payloads_refused(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(fe.InvalidFieldEvidenceError):                     # unknown photo kind
        _save(store, _payload(photos=[_photo_ref("e1", "SELFIE")]))
    with pytest.raises(fe.InvalidFieldEvidenceError):                     # unknown problem type
        _save(store, _payload(problems=[{"problem_id": "p1", "type": "aliens", "photo_evidence_ids": []}]))
    with pytest.raises(fe.InvalidFieldEvidenceError):                     # duplicate photo evidence ids
        _save(store, _payload(photos=[_photo_ref("e1", fe.OPTIONAL_CONTEXT),
                                      _photo_ref("e1", fe.OPTIONAL_CONTEXT)]))
    with pytest.raises(fe.InvalidFieldEvidenceError):                     # problem references unknown photo
        _save(store, _payload(problems=[{"problem_id": "p1", "type": "obstruction",
                                         "photo_evidence_ids": ["ghost"]}]))
    with pytest.raises(fe.InvalidFieldEvidenceError):                     # problem photo must be PROBLEM_AREA
        _save(store, _payload(photos=[_photo_ref("e1", fe.OPTIONAL_CONTEXT)],
                              problems=[{"problem_id": "p1", "type": "damage",
                                         "photo_evidence_ids": ["e1"]}]))


# --------------------------------------------------------------------------- #
# Required-evidence rules.
# --------------------------------------------------------------------------- #
def test_missing_start_photo_blocks_submit(tmp_path):
    store = _store(tmp_path)
    end = _photo(store, "end.jpg")
    _save(store, _payload(photos=[_photo_ref("ev-end", fe.END_STATION, end)]))
    result = _submit(store)
    assert result["submitted"] is False and result["status"] == fe.DRAFT
    assert result["blocked"] == fe.BLOCKED_MISSING_REQUIRED_EVIDENCE
    assert [m["code"] for m in result["missing_evidence"]] == [fe.MISSING_START_STATION_PHOTO]
    assert fe.load_field_evidence(store, CP, JOB, SEG)["status"] == fe.DRAFT   # record untouched


def test_missing_end_photo_blocks_submit(tmp_path):
    store = _store(tmp_path)
    start = _photo(store, "start.jpg")
    _save(store, _payload(photos=[_photo_ref("ev-start", fe.START_STATION, start)]))
    result = _submit(store)
    assert result["submitted"] is False
    assert [m["code"] for m in result["missing_evidence"]] == [fe.MISSING_END_STATION_PHOTO]


def test_unbound_or_wrong_kind_uploads_satisfy_nothing(tmp_path):
    store = _store(tmp_path)
    # A claimed start photo with NO upload binding, an end photo bound to a NON-existent upload id, and
    # a "photo" bound to a BORE_LOG upload: none of them satisfies a required slot (evidence is real or
    # it does not count).
    borelog = accept_upload(store, CP, JOB, kind="BORE_LOG", filename="log.xlsx",
                            content=b"not-a-photo", stored_at=AT)
    _save(store, _payload(photos=[
        _photo_ref("ev-start", fe.START_STATION, None),
        _photo_ref("ev-end", fe.END_STATION, "up-000000000000"),
        _photo_ref("ev-x", fe.OPTIONAL_CONTEXT, borelog["upload_id"]),
    ]))
    result = _submit(store)
    codes = [m["code"] for m in result["missing_evidence"]]
    assert codes == [fe.MISSING_START_STATION_PHOTO, fe.MISSING_END_STATION_PHOTO]


def test_problem_without_bound_photo_blocks_submit(tmp_path):
    store = _store(tmp_path)
    payload = _complete_payload(store)
    payload["problems"] = [{"problem_id": "p1", "type": "utility_conflict", "station": "12+40",
                            "note": "unmarked line", "photo_evidence_ids": []}]
    _save(store, payload)
    result = _submit(store)
    assert result["submitted"] is False
    missing = result["missing_evidence"]
    assert [m["code"] for m in missing] == [fe.PROBLEM_PHOTO_REQUIRED]
    assert missing[0]["problem_id"] == "p1" and missing[0]["type"] == "utility_conflict"


def test_missing_reason_order_is_deterministic(tmp_path):
    store = _store(tmp_path)
    payload = _payload(
        photos=[_photo_ref("pp", fe.PROBLEM_AREA, None)],
        problems=[{"problem_id": "p1", "type": "obstruction", "photo_evidence_ids": ["pp"]},
                  {"problem_id": "p2", "type": "damage", "photo_evidence_ids": []}])
    _save(store, payload)
    first, second = _submit(store), _submit(store)
    codes = [m["code"] for m in first["missing_evidence"]]
    assert codes == [fe.MISSING_START_STATION_PHOTO, fe.MISSING_END_STATION_PHOTO,
                     fe.PROBLEM_PHOTO_REQUIRED, fe.PROBLEM_PHOTO_REQUIRED]
    assert [m["problem_id"] for m in first["missing_evidence"][2:]] == ["p1", "p2"]
    assert first["missing_evidence"] == second["missing_evidence"]        # deterministic


def test_optional_context_photos_never_required(tmp_path):
    store = _store(tmp_path)
    payload = _complete_payload(store)
    payload["photos"].append(_photo_ref("ev-ctx", fe.OPTIONAL_CONTEXT, None, note="extra context"))
    _save(store, payload)
    result = _submit(store)
    assert result["submitted"] is True and result["missing_evidence"] == []


def test_complete_package_submits_and_resubmit_is_idempotent(tmp_path):
    store = _store(tmp_path)
    _save(store, _complete_payload(store))
    result = _submit(store)
    assert result["submitted"] is True and result["status"] == fe.SUBMITTED_FOR_REVIEW
    rec = fe.load_field_evidence(store, CP, JOB, SEG)
    assert rec["status"] == fe.SUBMITTED_FOR_REVIEW
    assert rec["submitted_at"] == AT and rec["submitted_by"] == BY
    assert rec["audit"][-1]["action"] == "field_evidence_submitted"
    again = _submit(store)
    assert again["submitted"] is True and again["missing_evidence"] == []


def test_save_after_submit_is_locked(tmp_path):
    store = _store(tmp_path)
    _save(store, _complete_payload(store))
    assert _submit(store)["submitted"] is True
    with pytest.raises(fe.FieldEvidenceLockedError):
        _save(store, _payload(notes="late edit"))


# --------------------------------------------------------------------------- #
# Digital bore-log readings.
# --------------------------------------------------------------------------- #
def test_readings_accept_non_exact_cadence(tmp_path):
    store = _store(tmp_path)
    # ~50 ft nominal is ADVISORY: irregular real-world offsets are stored exactly as recorded.
    readings = [
        {"reading_id": "r0", "offset_ft": 0, "depth_ft": 4.2, "pitch_pct": -18,
         "method": "walkover_locator", "recorded_at": AT},
        {"reading_id": "r1", "offset_ft": 47, "depth_ft": 6.8},
        {"reading_id": "r2", "offset_ft": 103, "depth_ft": 7.4, "note": "under the ditch"},
        {"reading_id": "r3", "offset_ft": 160.5, "depth_ft": 6.1, "problem": True, "station": "STA 1+60"},
    ]
    rec = _save(store, _payload(readings=readings))
    assert [r["offset_ft"] for r in rec["readings"]] == [0.0, 47.0, 103.0, 160.5]
    assert rec["readings"][3]["problem"] is True
    assert fe.NOMINAL_READING_INTERVAL_FT == 50                           # advisory constant only


def test_reading_validation_refuses_bad_numbers(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(fe.InvalidFieldEvidenceError):                     # negative offset
        _save(store, _payload(readings=[{"reading_id": "r0", "offset_ft": -1, "depth_ft": 5}]))
    with pytest.raises(fe.InvalidFieldEvidenceError):                     # missing depth
        _save(store, _payload(readings=[{"reading_id": "r0", "offset_ft": 0}]))
    with pytest.raises(fe.InvalidFieldEvidenceError):                     # bad method
        _save(store, _payload(readings=[{"reading_id": "r0", "offset_ft": 0, "depth_ft": 5,
                                         "method": "divining-rod"}]))


# --------------------------------------------------------------------------- #
# Doctrine: never a redline / AUTO / placement; module imports nothing drawing-capable.
# --------------------------------------------------------------------------- #
def test_submit_changes_no_job_status_or_slots(tmp_path):
    store = _store(tmp_path)
    _save(store, _complete_payload(store))
    before = load_job(store, CP, JOB)
    _submit(store)
    after = load_job(store, CP, JOB)
    assert after["status"] == before["status"]
    assert after["slots"] == before["slots"]                              # no output slot, no promotion


def test_module_imports_no_placement_or_render_seam():
    src = (Path(fe.__file__)).read_text(encoding="utf-8")
    tree = ast.parse(src)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
    forbidden = ("truelinev2.extract", "truelinev2.render", "truelinev2.match", "truelinev2.harness",
                 "truelinev2.contracts.uploaded_corpus_engine_handoff",
                 "truelinev2.contracts.review_acceptance", "truelinev2.contracts.redline_manifest")
    hits = [m for m in imported for f in forbidden if m == f or m.startswith(f + ".")]
    assert not hits, "field_evidence must not import placement/render/engine seams: %r" % hits
