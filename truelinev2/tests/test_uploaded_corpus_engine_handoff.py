"""Contract tests: uploaded-corpus engine handoff adapter.

The adapter runs the shipped placement ENGINE on a job's uploaded plan + an engine-ready reviewed bore-log
and, when the engine places a drawable candidate, renders the redline stroke along the DRAWN route and
publishes it as a job-local FINAL_REDLINE_PNG bundle (bundle_origin UPLOADED_CORPUS_ENGINE). ABSTAIN /
no-dialect / missing-input cases stay BLOCKED with named blockers and publish nothing.

Self-contained + name-free: a real CAD plan is NOT needed here — the heavy engine (`_run_engine`) and the
renderer (`render_redline_stroke`) are monkeypatched with synthetic results, so the publish/blocker logic is
exercised deterministically. The end-to-end engine render on real plan geometry lives in a separate
(non-CI) proof. No real customer/project/location/operator name appears anywhere.
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
from truelinev2.contracts import uploaded_corpus_engine_handoff as uce
from truelinev2.schema.models import Bore, Callout, Placement, PlacementStatus

AT = "2026-06-22T00:00:00Z"
BY = "op-1"
CP = "cp-0001"
JOB = "job-0001"
RBL = "rbl-1"

# A real minimal 1-page PDF: the render path opens PlanPdf(plan) for real (the renderer itself is
# monkeypatched), so the bytes must be a valid PDF. The engine (_run_engine) is monkeypatched.
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


def _job(tmp, *, with_plan=True, with_bore=True, ready=True):
    create_customer_project(tmp, CP, "Label", AT)
    create_job(tmp, CP, JOB, AT, BY)
    if with_plan:
        accept_upload(tmp, CP, JOB, kind="PLAN_PDF", filename="plan.pdf", content=_PDF, stored_at=AT)
    bore_id = None
    if with_bore:
        bore = accept_upload(tmp, CP, JOB, kind="BORE_LOG", filename="log.xlsx", content=_BORE, stored_at=AT)
        bore_id = bore["upload_id"]
        create_reviewed_bore_log(tmp, CP, JOB, bore_id, RBL, at=AT, by=BY)
        row = new_extracted_row("row-1", bore_id, raw={"s": "0+00"}, normalized={"s": "0+00"},
                                extraction_method=MANUAL_ENTRY, at=AT, by=BY)
        add_extracted_rows(tmp, CP, JOB, RBL, [row], at=AT, by=BY)
        if ready:
            review_row_in_log(tmp, CP, JOB, RBL, "row-1", CONFIRMED, at=AT, by=BY)
            define_segment_group(tmp, CP, JOB, RBL, "g-1", ["row-1"], SEPARATE_BORE, at=AT, by=BY)
            set_grouping_status(tmp, CP, JOB, RBL, "g-1", GROUPING_CONFIRMED, at=AT, by=BY)
    return bore_id


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


_NA_MATCHLINE = {"verdict": "N/A", "caveats": [], "evidence": []}


def _patch_engine(monkeypatch, *, placement, bore=None, extra_legs=(), matchline=None, dialect="generic"):
    b = bore if bore is not None else _bore()
    ml = matchline if matchline is not None else _NA_MATCHLINE
    # 7th value = the dialect OBJECT used (None here -> no traced centerline / no confidence signals,
    # so the stub renders the bbox-extent exactly as before; the string ``dialect`` stays the name label).
    monkeypatch.setattr(uce, "_run_engine",
                        lambda plan_path, borelog_path, rbl=None: (b, placement, 0, dialect, list(extra_legs), ml, None, None))


def _patch_render(monkeypatch, captions_seen=None):
    # Mirrors the real renderer's signature incl. the caption gate; ``captions_seen`` records the
    # caption kwarg per call so tests can assert the PRODUCT lane opts out (caption=False).
    def fake_render(plan, bore_id, sheet, offset, stroke_points, *, status, reason, out_dir,
                    caption=True):
        if captions_seen is not None:
            captions_seen.append(caption)
        import os
        os.makedirs(out_dir, exist_ok=True)
        p = os.path.join(out_dir, "%s_s%d_redline_stroke.png" % (bore_id, sheet))
        with open(p, "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n" + b"render(%s)" % status.encode())
        return p
    monkeypatch.setattr(uce, "render_redline_stroke", fake_render)


def test_review_candidate_renders_job_local_bundle(tmp_path, monkeypatch):
    _job(tmp_path)
    _patch_engine(monkeypatch, placement=_placement(PlacementStatus.REVIEW,
                                                    caveats=["DRAWN_EXTENT_EXCEEDS_BORE_SPAN"]))
    captions_seen = []
    _patch_render(monkeypatch, captions_seen)

    ev = uce.evaluate_uploaded_corpus_engine_handoff(tmp_path, CP, JOB)
    assert ev["status"] == "RUNNABLE" and ev["runnable"] is True
    assert ev["candidate"]["placement_status"] == "REVIEW"
    assert ev["candidate"]["render_tier"] == "dashed"
    assert "DRAWN_EXTENT_EXCEEDS_BORE_SPAN" in ev["candidate"]["caveats"]
    assert "CROSS_SHEET_CONTINUATION_REVIEW" not in ev["candidate"]["caveats"]   # single-sheet bore (71'-like)
    assert ev["candidate"]["referenced_sheets"] == [11]

    summary = uce.render_uploaded_corpus_engine_handoff(tmp_path, CP, JOB, at=AT, by=BY)
    assert summary["status"] == "SUCCEEDED"
    assert summary["bundle_origin"] == "UPLOADED_CORPUS_ENGINE"
    assert summary["placement_status"] == "REVIEW"              # no promotion: REVIEW stays REVIEW
    assert summary["artifact_count"] == 1
    assert summary["artifacts"] and all(a["kind"] == "FINAL_REDLINE_PNG" for a in summary["artifacts"])
    assert all(a["sha256"] and a["bytes"] for a in summary["artifacts"])
    # Strict-reader-success equivalence (F2): the reviewed-row adapter never ran on this path (no
    # bore_source stamped on the matchline), so the summary dict must carry NO "bore_source" key at all --
    # not even a ``None`` placeholder -- keeping this shape byte-identical to before the adapter existed.
    assert "bore_source" not in summary
    # PRODUCT artifacts are rendered caption-free: the render call opts out of the diagnostic band;
    # bore id / status / reason remain STRUCTURED manifest/summary fields (asserted above/below),
    # never burned into customer-facing pixels.
    assert captions_seen == [False]

    job = load_job(tmp_path, CP, JOB)
    assert job["slots"]["artifact_bundle"] is not None
    assert job["slots"]["redline_manifest"] is not None

    bundle_id = summary["bundle_id"]
    mpath = job_dir(tmp_path, CP, JOB) / "bundle_store" / "bundles" / bundle_id / "redline_manifest.json"
    m = json.loads(mpath.read_text(encoding="utf-8"))
    assert m["mock_example"] is False
    assert m["bundle_origin"] == "UPLOADED_CORPUS_ENGINE"
    assert m["logs"][0]["log_id"] == RBL                       # generic, name-free log id
    assert m["logs"][0]["status"] == "DRAWN_REDLINE"
    assert m["logs"][0]["provenance"] == "OWNER_CONFIRMED_HUMAN_ADJUSTABLE"   # REVIEW => human-adjustable

    # No manifest lies: each published sha256/bytes is computed from the ACTUAL (caption-free)
    # product artifact bytes on disk in the bundle.
    bdir = job_dir(tmp_path, CP, JOB) / "bundle_store" / "bundles" / bundle_id
    for a in summary["artifacts"]:
        blob = (bdir / a["path"]).read_bytes()
        assert hashlib.sha256(blob).hexdigest() == a["sha256"]
        assert len(blob) == a["bytes"]

    again = uce.render_uploaded_corpus_engine_handoff(tmp_path, CP, JOB, at=AT, by=BY)
    assert again["bundle_id"] == summary["bundle_id"]          # idempotent by content


def test_summary_stamps_bore_source_only_when_adapter_supplied_it(tmp_path, monkeypatch):
    # The other half of the F2 equivalence guard: when _run_engine DID stamp a bore_source (the reviewed-row
    # adapter path), the summary's "bore_source" key must be PRESENT with that value -- proving the key is
    # additive/conditional, not simply removed.
    _job(tmp_path)
    ml_with_source = {"verdict": "N/A", "caveats": [], "evidence": [], "bore_source": "REVIEWED_ROWS_ADAPTER"}
    _patch_engine(monkeypatch, placement=_placement(PlacementStatus.REVIEW,
                                                    caveats=["DRAWN_EXTENT_EXCEEDS_BORE_SPAN"]),
                  matchline=ml_with_source)
    _patch_render(monkeypatch)
    summary = uce.render_uploaded_corpus_engine_handoff(tmp_path, CP, JOB, at=AT, by=BY)
    assert summary["bore_source"] == "REVIEWED_ROWS_ADAPTER"


def test_auto_select_renders_deterministic_provenance(tmp_path, monkeypatch):
    _job(tmp_path)
    _patch_engine(monkeypatch, placement=_placement(PlacementStatus.AUTO_SELECT,
                                                    reason="DRAWN_BORE_EXTENT_MATCHES_SPAN"))
    _patch_render(monkeypatch)
    ev = uce.evaluate_uploaded_corpus_engine_handoff(tmp_path, CP, JOB)
    assert ev["candidate"]["render_tier"] == "solid"
    summary = uce.render_uploaded_corpus_engine_handoff(tmp_path, CP, JOB, at=AT, by=BY)
    bundle_id = summary["bundle_id"]
    mpath = job_dir(tmp_path, CP, JOB) / "bundle_store" / "bundles" / bundle_id / "redline_manifest.json"
    m = json.loads(mpath.read_text(encoding="utf-8"))
    assert m["logs"][0]["provenance"] == "DETERMINISTIC_AUTO"
    assert m["provenance_counts"]["DETERMINISTIC_AUTO"] == 1


def test_engine_abstain_blocks_and_renders_nothing(tmp_path, monkeypatch):
    _job(tmp_path)
    _patch_engine(monkeypatch, placement=_placement(PlacementStatus.ABSTAIN, with_callout=False,
                                                    reason="NO_DRAWN_BORE_OVER_SPAN"))
    ev = uce.evaluate_uploaded_corpus_engine_handoff(tmp_path, CP, JOB)
    assert ev["status"] == "BLOCKED" and ev["runnable"] is False
    assert "candidate" not in ev
    assert "ENGINE_ABSTAINED" in {b["code"] for b in ev["blockers"]}
    with pytest.raises(uce.UploadedCorpusEngineError):
        uce.render_uploaded_corpus_engine_handoff(tmp_path, CP, JOB, at=AT, by=BY)
    assert load_job(tmp_path, CP, JOB)["slots"]["artifact_bundle"] is None


def test_no_dialect_blocks(tmp_path, monkeypatch):
    _job(tmp_path)
    monkeypatch.setattr(uce, "_run_engine",
                        lambda plan_path, borelog_path, rbl=None: (_bore(), None, 0, None, [], _NA_MATCHLINE, None, None))
    ev = uce.evaluate_uploaded_corpus_engine_handoff(tmp_path, CP, JOB)
    assert ev["status"] == "BLOCKED"
    assert "NO_PLAN_DIALECT_RECOGNIZED" in {b["code"] for b in ev["blockers"]}


def test_unreadable_bore_log_blocks_named_never_crashes(tmp_path):
    # REGRESSION (staging generic-ready-demo 500): an engine-ready job whose BORE_LOG file the ENGINE's
    # ingest normalizer cannot read (the fixture's garbage-bytes .xlsx funnels to load_borelog's
    # unrecognized-format ValueError) must evaluate to a NAMED blocker — never an unhandled exception.
    # The REAL _run_engine runs here on purpose (no monkeypatch): the guard under test sits inside it.
    _job(tmp_path)
    ev = uce.evaluate_uploaded_corpus_engine_handoff(tmp_path, CP, JOB)
    assert ev["status"] == "BLOCKED" and ev["runnable"] is False
    blockers = {b["code"]: b["reason"] for b in ev["blockers"]}
    assert uce.BORE_LOG_FORMAT_UNRECOGNIZED in blockers
    # Plain-English, review-support copy: no traceback/exception text, no stored path leakage.
    reason = blockers[uce.BORE_LOG_FORMAT_UNRECOGNIZED]
    assert "could not read this bore log" in reason
    assert "ValueError" not in reason and "payload" not in reason and "\\" not in reason
    # The render path refuses with the lane's controlled error (route maps it to 409), never a crash.
    with pytest.raises(uce.UploadedCorpusEngineError) as exc:
        uce.render_uploaded_corpus_engine_handoff(tmp_path, CP, JOB, at=AT, by=BY)
    assert uce.BORE_LOG_FORMAT_UNRECOGNIZED in str(exc.value)


def test_missing_inputs_block_without_running_engine(tmp_path, monkeypatch):
    # No plan, and the reviewed bore-log never reaches engine-ready -> input blockers, engine NEVER invoked.
    _job(tmp_path, with_plan=False, ready=False)
    monkeypatch.setattr(uce, "_run_engine",
                        lambda *a, **k: pytest.fail("engine must not run when inputs are missing"))
    ev = uce.evaluate_uploaded_corpus_engine_handoff(tmp_path, CP, JOB)
    codes = {b["code"] for b in ev["blockers"]}
    assert ev["status"] == "BLOCKED"
    assert "NO_PLAN_PDF_UPLOAD" in codes
    assert "NO_ENGINE_READY_REVIEWED_BORE_LOG" in codes
    with pytest.raises(uce.UploadedCorpusEngineError):
        uce.render_uploaded_corpus_engine_handoff(tmp_path, CP, JOB, at=AT, by=BY)


def test_cross_sheet_both_legs_render_multiple_artifacts(tmp_path, monkeypatch):
    # Two-sheet bore ([10,11]): winner sheet 10 + a source-supported leg on sheet 11 -> TWO FINAL_REDLINE_PNG
    # artifacts (full cross-sheet REVIEW coverage). CROSS_SHEET_CONTINUATION_REVIEW present; NOT partial; the
    # winner's own sheet keeps its existing single-callout render.
    _job(tmp_path)
    bore = _bore(sheet_refs=(10, 11))
    placement = _placement(PlacementStatus.REVIEW, sheets=(10,), callout_sheet=10)
    extra = [{"sheet": 11, "stroke_points": [(110.0, 300.0), (260.0, 302.0)]}]
    _patch_engine(monkeypatch, placement=placement, bore=bore, extra_legs=extra)
    _patch_render(monkeypatch)

    ev = uce.evaluate_uploaded_corpus_engine_handoff(tmp_path, CP, JOB)
    assert ev["runnable"] is True
    assert ev["candidate"]["referenced_sheets"] == [10, 11]
    assert ev["candidate"]["render_sheets"] == [10, 11]
    assert ev["candidate"]["extra_leg_sheets"] == [11]
    assert "CROSS_SHEET_CONTINUATION_REVIEW" in ev["candidate"]["caveats"]
    assert "PARTIAL_CROSS_SHEET_REVIEW" not in ev["candidate"]["caveats"]   # both sheets render

    summary = uce.render_uploaded_corpus_engine_handoff(tmp_path, CP, JOB, at=AT, by=BY)
    assert summary["artifact_count"] == 2
    assert all(a["kind"] == "FINAL_REDLINE_PNG" for a in summary["artifacts"])
    mpath = (job_dir(tmp_path, CP, JOB) / "bundle_store" / "bundles"
             / summary["bundle_id"] / "redline_manifest.json")
    m = json.loads(mpath.read_text(encoding="utf-8"))
    assert sorted(m["logs"][0]["source_sheets"]) == [10, 11]
    assert len(m["logs"][0]["artifacts"]) == 2
    assert "CROSS_SHEET_CONTINUATION_REVIEW" in m["logs"][0]["warnings"]
    assert "PARTIAL_CROSS_SHEET_REVIEW" not in m["logs"][0]["warnings"]
    assert m["logs"][0]["provenance"] == "OWNER_CONFIRMED_HUMAN_ADJUSTABLE"   # AUTO not promoted


def test_partial_cross_sheet_review_labeled_honestly(tmp_path, monkeypatch):
    # Two-sheet bore ([10,11]) but only the winner sheet (10) has a source-supported leg (no leg on 11):
    # ONE artifact + CROSS_SHEET_CONTINUATION_REVIEW + PARTIAL_CROSS_SHEET_REVIEW (honest partial coverage).
    _job(tmp_path)
    bore = _bore(sheet_refs=(10, 11))
    placement = _placement(PlacementStatus.REVIEW, sheets=(10,), callout_sheet=10)
    _patch_engine(monkeypatch, placement=placement, bore=bore, extra_legs=[])   # no leg on sheet 11
    _patch_render(monkeypatch)

    ev = uce.evaluate_uploaded_corpus_engine_handoff(tmp_path, CP, JOB)
    assert ev["candidate"]["render_sheets"] == [10]
    caveats = ev["candidate"]["caveats"]
    assert "CROSS_SHEET_CONTINUATION_REVIEW" in caveats
    assert "PARTIAL_CROSS_SHEET_REVIEW" in caveats

    summary = uce.render_uploaded_corpus_engine_handoff(tmp_path, CP, JOB, at=AT, by=BY)
    assert summary["artifact_count"] == 1
    mpath = (job_dir(tmp_path, CP, JOB) / "bundle_store" / "bundles"
             / summary["bundle_id"] / "redline_manifest.json")
    m = json.loads(mpath.read_text(encoding="utf-8"))
    assert m["logs"][0]["source_sheets"] == [10]
    assert "PARTIAL_CROSS_SHEET_REVIEW" in m["logs"][0]["warnings"]


# --- Phase 5: matchline continuity (read-only printed-matchline validation) ----------------------------- #

class _FakePlan:
    """Minimal plan stub exposing only .lines(sheet, offset) for the matchline-continuity unit tests."""
    def __init__(self, by_sheet):
        self._by = by_sheet

    def lines(self, sheet, offset):
        return self._by.get(sheet, [])


def _two_sheet_bore(lo_ft, hi_ft):
    return Bore(bore_id="x", project=None, source_file="x", sheet_refs=[10, 11],
                station_start="14+20", station_end="15+38",
                station_start_ft=lo_ft, station_end_ft=hi_ft, span_ft=hi_ft - lo_ft)


def test_matchline_continuity_confirmed_with_boundary_station():
    # Both sheets print the SAME matchline boundary STATION inside the bore span -> CONFIRMED.
    plan = _FakePlan({10: ["MATCHLINE STA 15+00 - SEE SHEET 11"],
                      11: ["MATCHLINE STA 15+00 - SEE SHEET 10"]})
    r = uce._matchline_continuity(plan, 0, _two_sheet_bore(1420.0, 1538.0), [10, 11])
    assert r["verdict"] == "CONFIRMED"
    assert "MATCHLINE_CONTINUATION_CONFIRMED_REVIEW" in r["caveats"]
    assert r["evidence"][0]["shared_boundary_station_ft"] == 1500.0


def test_matchline_continuity_adjacency_only_is_unverified():
    # Mutual SEE-SHEET adjacency printed but NO boundary station (the real two-sheet, no-station case) ->
    # UNVERIFIED + adjacency confirmed; never faked-confirmed.
    plan = _FakePlan({10: ["MATCHLINE: SEE SHEET 11"], 11: ["MATCHLINE: SEE SHEET 10"]})
    r = uce._matchline_continuity(plan, 0, _two_sheet_bore(1420.0, 1538.0), [10, 11])
    assert r["verdict"] == "UNVERIFIED"
    assert "MATCHLINE_CONTINUATION_UNVERIFIED" in r["caveats"]
    assert "MATCHLINE_SHEET_ADJACENCY_CONFIRMED" in r["caveats"]
    assert "MATCHLINE_CONTINUATION_CONFIRMED_REVIEW" not in r["caveats"]


def test_matchline_continuity_no_evidence_unverified():
    # No matchline text at all -> UNVERIFIED, and NO adjacency claim (nothing printed to support it).
    plan = _FakePlan({10: ["EOP"], 11: ["ROW"]})
    r = uce._matchline_continuity(plan, 0, _two_sheet_bore(1420.0, 1538.0), [10, 11])
    assert r["verdict"] == "UNVERIFIED"
    assert "MATCHLINE_CONTINUATION_UNVERIFIED" in r["caveats"]
    assert "MATCHLINE_SHEET_ADJACENCY_CONFIRMED" not in r["caveats"]


def test_matchline_continuity_single_sheet_na():
    # Single rendered sheet -> not applicable (71'-like); no matchline caveat.
    plan = _FakePlan({11: ["MATCHLINE: SEE SHEET 10"]})
    r = uce._matchline_continuity(plan, 0, _bore(sheet_refs=(11,)), [11])
    assert r["verdict"] == "N/A" and r["caveats"] == []


def test_unverified_matchline_flows_to_report_and_manifest(tmp_path, monkeypatch):
    # The UNVERIFIED verdict (two-sheet, no-station shape) reaches evaluate + the manifest; CROSS_SHEET stays.
    _job(tmp_path)
    bore = _bore(sheet_refs=(10, 11))
    placement = _placement(PlacementStatus.REVIEW, sheets=(10,), callout_sheet=10)
    extra = [{"sheet": 11, "stroke_points": [(110.0, 300.0), (260.0, 302.0)]}]
    ml = {"verdict": "UNVERIFIED",
          "caveats": ["MATCHLINE_CONTINUATION_UNVERIFIED", "MATCHLINE_SHEET_ADJACENCY_CONFIRMED"],
          "evidence": [{"pair": [10, 11], "shared_boundary_station_ft": None}]}
    _patch_engine(monkeypatch, placement=placement, bore=bore, extra_legs=extra, matchline=ml)
    _patch_render(monkeypatch)

    ev = uce.evaluate_uploaded_corpus_engine_handoff(tmp_path, CP, JOB)
    assert ev["candidate"]["matchline_continuity"] == "UNVERIFIED"
    caveats = ev["candidate"]["caveats"]
    assert "MATCHLINE_CONTINUATION_UNVERIFIED" in caveats
    assert "MATCHLINE_SHEET_ADJACENCY_CONFIRMED" in caveats
    assert "CROSS_SHEET_CONTINUATION_REVIEW" in caveats              # kept (legs still separate per-sheet)
    assert "MATCHLINE_CONTINUATION_CONFIRMED_REVIEW" not in caveats

    summary = uce.render_uploaded_corpus_engine_handoff(tmp_path, CP, JOB, at=AT, by=BY)
    m = json.loads((job_dir(tmp_path, CP, JOB) / "bundle_store" / "bundles"
                    / summary["bundle_id"] / "redline_manifest.json").read_text(encoding="utf-8"))
    assert "MATCHLINE_CONTINUATION_UNVERIFIED" in m["logs"][0]["warnings"]
    assert m["logs"][0]["provenance"] == "OWNER_CONFIRMED_HUMAN_ADJUSTABLE"   # AUTO not promoted


def test_confirmed_matchline_stays_review_not_auto(tmp_path, monkeypatch):
    # A CONFIRMED continuity adds the confirmed caveat but stays REVIEW (dashed) — never promoted to AUTO.
    _job(tmp_path)
    bore = _bore(sheet_refs=(10, 11))
    placement = _placement(PlacementStatus.REVIEW, sheets=(10,), callout_sheet=10)
    extra = [{"sheet": 11, "stroke_points": [(110.0, 300.0), (260.0, 302.0)]}]
    ml = {"verdict": "CONFIRMED", "caveats": ["MATCHLINE_CONTINUATION_CONFIRMED_REVIEW"],
          "evidence": [{"pair": [10, 11], "shared_boundary_station_ft": 1500.0}]}
    _patch_engine(monkeypatch, placement=placement, bore=bore, extra_legs=extra, matchline=ml)
    _patch_render(monkeypatch)

    ev = uce.evaluate_uploaded_corpus_engine_handoff(tmp_path, CP, JOB)
    assert ev["candidate"]["matchline_continuity"] == "CONFIRMED"
    assert "MATCHLINE_CONTINUATION_CONFIRMED_REVIEW" in ev["candidate"]["caveats"]
    assert ev["candidate"]["placement_status"] == "REVIEW" and ev["candidate"]["render_tier"] == "dashed"
