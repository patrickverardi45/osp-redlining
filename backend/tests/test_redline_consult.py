"""Unit tests for the default-OFF redline consult (matchline/station-frame resolver +
row-fed source-station corrections + BOC) and its wiring into the PDF-first adapter.

PDF-FREE by design — exercises the pure port (row-fed corrections, status ``classify``,
ledger loads, flag gating, vendored-path repoint, and the no-resolution no-op) WITHOUT
importing fitz, so it runs anywhere (the PDF-verification path is covered by the live
end-to-end run against the Brenham plan). Mirrors the existing backend test layout
(``app.core`` import style; run with ``python -m pytest`` from the repo root).

COMMAND (from repo root):
    python -m pytest backend/tests/test_redline_consult.py -v
"""
from __future__ import annotations

import json
import os

import pytest

from app.core import pdf_first_adapter as adapter
from app.core.redline_consult import correction_lib, consult

DATA_DIR = adapter._DEFAULT_ANALYSIS_DIR


# ── vendored layout: engine package + owner-reviewed ledgers ─────────────────────────────────
def test_engine_vendored_under_adapter_dir():
    assert os.path.isdir(os.path.join(adapter._DEFAULT_ENGINE_ROOT, "redline_pdf_first"))
    assert DATA_DIR.endswith("_redline_data") and os.path.isdir(DATA_DIR)


def test_vendored_ledgers_present_and_shaped():
    fr = json.load(open(os.path.join(DATA_DIR, "_matchline", "frame_resolutions.json"),
                        encoding="utf-8"))
    by_id = {r["bore_id"]: r for r in fr["resolutions"]}
    # the three proven wins are present
    for log_id in ("bore_log56", "bore_log58", "bore_log66"):
        assert log_id in by_id, log_id
    # log58 = HH_HH_DISTANCE proof class; log56/58 cross-sheet (seam) -> C; log66 single-sheet -> B
    assert by_id["bore_log58"]["class"] == "HH_HH_DISTANCE"
    assert by_id["bore_log56"].get("matchline_seam") and by_id["bore_log58"].get("matchline_seam")
    assert by_id["bore_log66"].get("matchline_seam") is None
    # corrections ledger: the true source corrections must stay
    corr = consult._corrections(DATA_DIR)
    assert corr["bore_log56"]["station_map"]["2+96"] == "2+76"
    assert corr["bore_log58"]["station_map"]["2+56"] == "2+36"
    # BOC evidence ledger: the log56 false-A override case (global placement evidence)
    boc = consult._boc_evidence(DATA_DIR)
    assert boc["bore_log56"]["boc_ft"] == 11


# ── flag gating (default-OFF) ────────────────────────────────────────────────────────────────
def test_resolver_flag_default_off(monkeypatch):
    monkeypatch.delenv("TRUELINE_MATCHLINE_FRAME_RESOLVER", raising=False)
    assert adapter._matchline_frame_resolver_enabled() is False
    for on in ("1", "true", "YES", "On"):
        monkeypatch.setenv("TRUELINE_MATCHLINE_FRAME_RESOLVER", on)
        assert adapter._matchline_frame_resolver_enabled() is True
    monkeypatch.setenv("TRUELINE_MATCHLINE_FRAME_RESOLVER", "0")
    assert adapter._matchline_frame_resolver_enabled() is False


# ── row-fed corrections (the live port of corrected_copy) ────────────────────────────────────
def _rows(*stations):
    return [{"station": s, "print": "21", "boc_ft": 11, "station_ft": None,
             "source_file": "bore_log56.xlsx"} for s in stations]


def test_corrected_rows_remaps_endpoint_without_mutating_input():
    rows = _rows("0+00", "1+00", "2+96")
    new, changes = correction_lib.corrected_rows(rows, {"2+96": "2+76"})
    assert [r["station"] for r in new] == ["0+00", "1+00", "2+76"]
    assert changes == [{"row": 2, "original": "2+96", "corrected": "2+76"}]
    assert new[2]["station_ft"] == 276  # recomputed on the COPY
    # STATE rows must never be mutated (original .xlsx is likewise never altered)
    assert [r["station"] for r in rows] == ["0+00", "1+00", "2+96"]
    assert rows[2]["station_ft"] is None


def test_corrected_rows_normalizes_sta_prefix():
    new, changes = correction_lib.corrected_rows(_rows("STA 2+96"), {"2+96": "2+76"})
    assert new[0]["station"] == "2+76" and len(changes) == 1


def test_corrected_rows_drop_excludes_whole_row():
    rows = _rows("40+00", "43+86", "59+19")
    new, _ = correction_lib.corrected_rows(
        rows, {"45+86": "43+86"}, drop_stations=["59+19"], strict=False)
    assert [r["station"] for r in new] == ["40+00", "43+86"]  # contaminant row dropped


def test_corrected_rows_strict_refuses_stale_key():
    with pytest.raises(ValueError):
        correction_lib.corrected_rows(_rows("0+00", "1+00"), {"2+96": "2+76"})


def test_apply_corrections_uses_vendored_ledger():
    rows = [{"station": s, "source_file": "bore_log58.xlsx"} for s in ("0+00", "1+00", "2+56")]
    new, changes, rec = consult.apply_corrections("bore_log58", rows, DATA_DIR)
    assert [r["station"] for r in new][-1] == "2+36"
    assert rec["cells_changed"] == 1 and "correction_error" not in rec


def test_apply_corrections_no_correction_is_noop():
    rows = [{"station": "0+00", "source_file": "bore_logZZ.xlsx"}]
    new, changes, rec = consult.apply_corrections("bore_logZZ", rows, DATA_DIR)
    assert new is rows and changes == [] and rec is None


# ── classify: the status detection the consult keys on (verbatim port) ───────────────────────
def _env(placements=None, review=None, fail_safe=None, status="OK"):
    return {"status": status, "placements": placements or [], "review_items": review or [],
            "fail_safe": fail_safe or [], "warnings": []}


def test_classify_fail_safe_and_blocked():
    assert consult.classify(_env(fail_safe=[{"log_ids": ["x"], "reason": "GE_2_COEQUAL_OVERLAP"}])
                            )["status"] == "fail_safe"
    assert consult.classify(_env())["status"] == "blocked"
    assert consult.classify(_env(status="ERROR"))["status"] == "blocked"


def test_classify_path_trace_vs_matchline():
    base = {"log_ids": ["x"], "surface": "placement", "sheets": [2]}
    single = dict(base, geo={"geometry_status": "AP_ANCHORED", "frame": {"multi_sheet": False},
                             "pdf_path_trace": {"artifact_name": "x.png"}})
    multi = dict(base, geo={"geometry_status": "AP_ANCHORED", "frame": {"multi_sheet": True},
                            "pdf_path_trace": {"artifact_name": "x.png"}})
    assert consult.classify(_env(placements=[single]))["status"] == "path_trace_drawn"
    assert consult.classify(_env(placements=[multi]))["status"] == "matchline"


def test_classify_evidence_overlay():
    c = {"log_ids": ["x"], "surface": "review",
         "geo": {"geometry_status": "AP_ANCHORED", "frame": {},
                 "pdf_redline": {"artifact_name": "r.png"}}}
    assert consult.classify(_env(review=[c]))["status"] == "evidence_overlay"


# ── apply_resolver is a no-op when there is no owner-reviewed resolution (PDF-free path) ──────
def test_apply_resolver_noop_without_resolution():
    env = _env(placements=[{"log_ids": ["bore_logZZ"], "surface": "placement"}])
    before = json.dumps(env, sort_keys=True, default=str)
    out = consult.apply_resolver("bore_logZZ", env, doc=None, sheet_offset=13,
                                 out_dir=os.path.join(DATA_DIR, "_nope"), data_dir=DATA_DIR)
    assert json.dumps(out, sort_keys=True, default=str) == before  # envelope untouched


# ── Step A: structure-to-structure connector (log66) is default-OFF + bounded ────────────────
def test_struct_connector_flag_default_off(monkeypatch):
    monkeypatch.delenv("TRUELINE_REDLINE_STRUCT_CONNECTOR", raising=False)
    assert consult._struct_connector_enabled() is False
    monkeypatch.setenv("TRUELINE_REDLINE_STRUCT_CONNECTOR", "1")
    assert consult._struct_connector_enabled() is True


def test_struct_connector_excludes_cross_sheet_and_incomplete(tmp_path):
    out = str(tmp_path)
    # cross-sheet (matchline seam) -> NEVER a straight connector (log56/58 excluded); returns
    # None BEFORE touching the PDF, so doc=None is safe.
    assert consult._render_struct_connector(
        {"seam": {"home_sta": "1+60"}, "overlays": [{"role": "start", "sheet": 10, "bbox": [0, 0, 1, 1]},
                                                    {"role": "end", "sheet": 13, "bbox": [0, 0, 1, 1]}]},
        {"bore_id": "x"}, None, 13, out) is None
    # single-sheet but no proven END anchor (e.g. host-only frame) -> None
    assert consult._render_struct_connector(
        {"seam": None, "overlays": [{"role": "start", "sheet": 10, "bbox": [0, 0, 1, 1]}]},
        {"bore_id": "x"}, None, 13, out) is None
    # start + end on DIFFERENT sheets -> None (single-sheet crossing only)
    assert consult._render_struct_connector(
        {"seam": None, "overlays": [{"role": "start", "sheet": 10, "bbox": [0, 0, 1, 1]},
                                    {"role": "end", "sheet": 11, "bbox": [0, 0, 1, 1]}]},
        {"bore_id": "x"}, None, 13, out) is None
