"""Item 4 Slice A — BOC/offset corroboration as additive review evidence (PDF-FREE).

Locks:
  - consult._boc_verdict_label maps prove_candidate verdicts -> reviewable labels;
  - consult._resolver_card projects mr['boc_corroboration'] into geo (absent -> omitted);
  - build_review_reason emits a boc_corroboration discriminator and KEEPS boc_ft;
  - no-draw-change: render_artifact_ref / overlay slot identical with vs without the evidence;
  - mismatch is DISPLAY-ONLY (never flips a drawn card to abstained);
  - compute core: boc_offset.prove_candidate verdicts (corroborated / mismatch / structure_only /
    blocked) via mocked text extraction (no real PDF).

COMMAND (from repo root):
    python -m pytest backend/tests/test_boc_corroboration.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

# boc_offset imports the vendored top-level ``redline_pdf_first`` -> needs backend/app/core on path.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "core"))

from app.core.redline_consult import boc_offset, consult
from app.core.match_review_queue import build_review_reason


# ── helpers: a log66-shaped single-sheet station-frame card ──────────────────────────
def _mr(boc_corroboration=None):
    mr = {
        "geometry_status": "STATION_FRAME_RESOLVED", "status": "blocked", "group": "g66",
        "sheets": [10], "seam": None, "struct_connector": None,
        "overlays": [
            {"role": "reset_origin", "sheet": 10, "bbox": [100.0, 95.0, 110.0, 105.0],
             "image": "bore_log66_s10_reset.png", "label": "NEXTLINK HH", "station": "45+33"},
            {"role": "end", "sheet": 10, "bbox": [300.0, 95.0, 310.0, 105.0],
             "image": "bore_log66_s10_evidence_overlay.png", "label": "INSTALLER HH", "station": "0+55"},
        ],
    }
    if boc_corroboration is not None:
        mr["boc_corroboration"] = boc_corroboration
    return mr


_RES = {"class": "single_sheet_hh", "hh_hh_ft": 55.0, "boc_ft": 10.0,
        "anchors": [{"role": "reset_origin", "label": "NEXTLINK HH", "station": "45+33"},
                    {"role": "end", "sheet": 10, "station": "0+55=0+00"}]}
_REC = {"print": "print10"}

_CORROBORATED = {"verdict": "corroborated", "corroborated": True, "boc_ft": 10, "boc_token": "10'",
                 "endpoint_sheet": 10, "endpoint_station": "0+55", "structure": "INSTALLER HH",
                 "nearby_offsets": [{"text": "10'", "ft": 10, "dist": 91.0}], "evidence_only": True}


# 1. verdict -> label mapping
def test_verdict_label_mapping():
    assert consult._boc_verdict_label("BOC_CONTEXT_CORROBORATED") == "corroborated"
    assert consult._boc_verdict_label("DOWNGRADE_BOC_OFFSET_MISMATCH") == "mismatch"
    assert consult._boc_verdict_label("DOWNGRADE_STRUCTURE_ONLY_NO_BOC_CALLOUT") == "structure_only"
    assert consult._boc_verdict_label("BLOCKED_NO_AUTHORED_ENDPOINT_STRUCTURE") == "blocked"
    assert consult._boc_verdict_label("anything else") == "unknown"


# 2. projection
def test_resolver_card_projects_boc_corroboration_into_geo():
    card = consult._resolver_card("bore_log66", _mr(_CORROBORATED), _REC, _RES)
    assert card["geo"]["boc_corroboration"] == _CORROBORATED


def test_resolver_card_omits_boc_corroboration_when_absent():
    card = consult._resolver_card("bore_log66", _mr(None), _REC, _RES)
    assert "boc_corroboration" not in card["geo"]


# 3. no-draw-change invariant
def test_no_draw_change_artifact_identical_with_and_without_boc():
    a = consult._resolver_card("bore_log66", _mr(_CORROBORATED), _REC, _RES)
    b = consult._resolver_card("bore_log66", _mr(None), _REC, _RES)
    assert a["render_artifact_ref"] == b["render_artifact_ref"] == "bore_log66_s10_evidence_overlay.png"
    assert "pdf_redline" in a["geo"] and "pdf_path_trace" not in a["geo"]
    assert a["geo"]["matchline_resolution"].get("redline_path") is None


# 4. review_reason surfaces a boc_corroboration discriminator + KEEPS boc_ft
def test_review_reason_surfaces_boc_corroboration_and_keeps_boc_ft():
    geo = {"geometry_status": "STATION_FRAME_RESOLVED",
           "matchline_resolution": {"status": "STATION_FRAME_RESOLVED", "sheets": [10], "boc_ft": 10},
           "boc_corroboration": _CORROBORATED}
    rr = build_review_reason(geo)
    disc = next(d for d in rr["discriminators"] if d["name"] == "boc_corroboration")
    assert disc["ok"] is True and "matches 10'" in disc["detail"]
    assert rr["evidence"]["boc_ft"] == 10.0                                  # existing BOC text kept
    assert rr["evidence"]["boc_corroboration"]["verdict"] == "corroborated"  # new evidence


def test_review_reason_boc_mismatch_is_display_only_no_abstain():
    geo = {"geometry_status": "STATION_FRAME_RESOLVED",
           "matchline_resolution": {"status": "STATION_FRAME_RESOLVED", "sheets": [13], "boc_ft": 8},
           "pdf_path_trace": {"artifact_name": "bore_log58_overlay.png"},  # it DREW
           "boc_corroboration": {"verdict": "mismatch", "boc_ft": 8, "boc_token": "8'",
                                 "endpoint_sheet": 13, "nearby_offsets": [{"text": "7'", "ft": 7}]}}
    rr = build_review_reason(geo)
    disc = next(d for d in rr["discriminators"] if d["name"] == "boc_corroboration")
    assert disc["ok"] is False and "7'" in disc["detail"] and "8'" in disc["detail"]
    assert rr["code"] != "abstained"  # mismatch is display-only; the drawn card is unaffected


def test_review_reason_no_boc_key_when_absent():
    geo = {"geometry_status": "STATION_FRAME_RESOLVED",
           "matchline_resolution": {"status": "STATION_FRAME_RESOLVED", "sheets": [10], "boc_ft": 10}}
    rr = build_review_reason(geo)
    assert not any(d["name"] == "boc_corroboration" for d in rr["discriminators"])
    assert "boc_corroboration" not in rr["evidence"]


# 5. compute core — prove_candidate verdicts via mocked text extraction (no real PDF)
def _blocks(*texts):
    return [{"text": t, "bbox_display": [140.0, 100.0, 200.0, 110.0]} for t in texts]


def _words(*pairs):
    return [{"text": t, "bbox_display": [float(x), 100.0, float(x) + 10.0, 110.0]} for t, x in pairs]


def _mock_tx(monkeypatch, blocks, words):
    monkeypatch.setattr(boc_offset.tx, "extract_blocks", lambda page: blocks)
    monkeypatch.setattr(boc_offset.tx, "extract_words", lambda page: words)
    monkeypatch.setattr(boc_offset.tx, "search_callout",
                        lambda page, q: [{"bbox_display": [150.0, 100.0, 160.0, 110.0]}])


def test_compute_corroborated(monkeypatch):
    _mock_tx(monkeypatch, _blocks("STA 0+55 INSTALLER HH"), _words(("10'", 145)))
    pv = boc_offset.prove_candidate(object(), "0+55", 10, "INSTALLER HH")
    assert pv["verdict"] == "BOC_CONTEXT_CORROBORATED" and pv["corroborated"] is True


def test_compute_mismatch(monkeypatch):
    _mock_tx(monkeypatch, _blocks("STA 0+55 INSTALLER HH"), _words(("7'", 145)))
    pv = boc_offset.prove_candidate(object(), "0+55", 10, "INSTALLER HH")
    assert pv["verdict"] == "DOWNGRADE_BOC_OFFSET_MISMATCH" and pv["corroborated"] is False


def test_compute_structure_only(monkeypatch):
    _mock_tx(monkeypatch, _blocks("STA 0+55 INSTALLER HH"), _words())
    pv = boc_offset.prove_candidate(object(), "0+55", 10, "INSTALLER HH")
    assert pv["verdict"] == "DOWNGRADE_STRUCTURE_ONLY_NO_BOC_CALLOUT" and pv["corroborated"] is False


def test_compute_blocked(monkeypatch):
    _mock_tx(monkeypatch, _blocks("UNRELATED TEXT"), _words(("10'", 145)))
    pv = boc_offset.prove_candidate(object(), "0+55", 10, "INSTALLER HH")
    assert pv["verdict"] == "BLOCKED_NO_AUTHORED_ENDPOINT_STRUCTURE" and pv["corroborated"] is False
