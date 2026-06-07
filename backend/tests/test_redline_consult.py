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


# ── D25: bore_log66 paused from the standalone struct-connector draw (run-wrong child of log33) ──
def test_struct_connector_pauses_log66_run_wrong(tmp_path):
    """D25: log66 is a run-wrong segment child of bore_log33's 650' run; even with an OTHERWISE
    drawable single-sheet start->end frame it must NOT draw a structure-to-structure connector.
    The guard fires BEFORE any PDF access (returns None with doc=None), so log66 falls through to
    evidence-card behavior like log58. (The positive draw for a non-paused single-sheet frame is
    covered by the live end-to-end run — this file is PDF-free by design.)"""
    valid_single_sheet = {
        "seam": None,
        "overlays": [{"role": "start", "sheet": 10, "bbox": [100.0, 95.0, 110.0, 105.0]},
                     {"role": "end", "sheet": 10, "bbox": [300.0, 95.0, 310.0, 105.0]}],
    }
    assert consult._render_struct_connector(
        valid_single_sheet, {"bore_id": "bore_log66"}, None, 13, str(tmp_path)) is None


def test_struct_connector_pause_scope_is_narrow():
    """The D25 pause is bore_log66 ONLY — it cannot affect the proven cross-sheet wins (log56/58,
    contained via the seam path) or any other log, so no other draw can change."""
    assert "bore_log66" in consult._STRUCT_CONNECTOR_PAUSED
    for other in ("bore_log56", "bore_log58", "bore_log54", "bore_logZZ", "x"):
        assert other not in consult._STRUCT_CONNECTOR_PAUSED


# ── D25: with the draw paused, log66's evidence-card still carries ALL the evidence ──────────────
_LOG66_RES = {"class": "single_sheet_hh", "hh_hh_ft": 55.0, "boc_ft": 10.0,
              "anchors": [{"role": "reset_origin", "label": "NEXTLINK HH", "station": "45+33"},
                          {"role": "end", "sheet": 10, "station": "0+55=0+00"}]}


def _contained_log66_mr():
    """The mr apply_resolver yields for log66 once the D25 guard suppresses the connector draw:
    NO struct_connector, but the read-only physical-anchor + BOC evidence still attach (they run
    independently of the draw), plus the station-frame proof overlays."""
    return {
        "geometry_status": "STATION_FRAME_RESOLVED", "status": "blocked", "group": "g66",
        "sheets": [10], "seam": None, "struct_connector": None,
        "overlays": [
            {"role": "reset_origin", "sheet": 10, "bbox": [100.0, 95.0, 110.0, 105.0],
             "image": "bore_log66_s10_reset.png", "label": "NEXTLINK HH", "station": "45+33"},
            {"role": "end", "sheet": 10, "bbox": [300.0, 95.0, 310.0, 105.0],
             "image": "bore_log66_s10_evidence_overlay.png", "label": "INSTALLER HH", "station": "0+55"},
        ],
        "physical_anchor": {"resolved": True, "applied": False, "evidence_only": True,
                            "start": {"resolved": True, "reason": "unique_structure_blob"},
                            "end": {"resolved": True, "reason": "unique_structure_blob"}},
        "boc_corroboration": {"verdict": "corroborated", "corroborated": True, "boc_ft": 10,
                              "boc_token": "10'", "endpoint_sheet": 10, "endpoint_station": "0+55",
                              "structure": "INSTALLER HH", "evidence_only": True},
    }


def test_log66_contained_card_is_evidence_only_but_keeps_all_evidence():
    card = consult._resolver_card("bore_log66", _contained_log66_mr(), {"print": "print10"}, _LOG66_RES)
    # evidence-card, NOT a standalone drawn redline (no structure_to_structure artifact)
    assert card["render_target"] == "evidence_card"
    assert card["render_artifact_ref"] == "bore_log66_s10_evidence_overlay.png"
    assert not str(card["render_artifact_ref"]).endswith("_structure_to_structure.png")
    assert "pdf_redline" in card["geo"] and "pdf_path_trace" not in card["geo"]
    assert card["geo"]["matchline_resolution"].get("redline_path") is None
    # evidence preserved: BOC 10', physical anchor (evidence-only), station-frame proof overlays
    assert card["geo"]["boc_corroboration"]["boc_ft"] == 10
    assert card["geo"]["boc_corroboration"]["verdict"] == "corroborated"
    assert card["geo"]["physical_anchor"]["applied"] is False
    assert card["geo"]["physical_anchor"]["evidence_only"] is True
    assert [o["artifact_name"] for o in card["geo"]["matchline_resolution"]["overlays"]] == \
        ["bore_log66_s10_reset.png", "bore_log66_s10_evidence_overlay.png"]


def test_log66_contained_card_review_reason_keeps_discriminators():
    """review_reason/evidence is preserved after containment: the BOC + physical-handhole
    discriminators still surface from the paused card's geo."""
    from app.core.match_review_queue import build_review_reason
    card = consult._resolver_card("bore_log66", _contained_log66_mr(), {"print": "print10"}, _LOG66_RES)
    rr = build_review_reason(card["geo"])
    assert rr is not None
    names = {d["name"] for d in rr["discriminators"]}
    assert "boc_corroboration" in names and "physical_handhole_anchor" in names
    assert rr["evidence"]["boc_ft"] == 10
