"""Item 3 Slice A.2 — physical-anchor EVIDENCE plumbing (PDF-FREE).

Locks that the PDF-first resolver card surfaces physical_handhole_anchor WITHOUT changing the
drawn overlay/artifact:
  - _resolver_card projects mr['physical_anchor'] into geo (Gap 1 surfacing);
  - compute_physical_anchor_evidence resolves the connector anchors as evidence-only
    (applied=False, evidence_only=True) — the Gap 2 read-only computation core;
  - a station-frame/matchline card with evidence attached keeps render_artifact_ref on the
    station-frame overlay (NOT struct_connector) and gains the physical_handhole_anchor reason.

COMMAND (from repo root):
    python -m pytest backend/tests/test_physical_anchor_evidence_plumbing.py -v
"""
from __future__ import annotations

from app.core.redline_consult import consult
from app.core.match_review_queue import build_review_reason


def _path(layer, cx, cy, s=8.0):
    h = s / 2.0
    return {"layer": layer, "bbox_display": [cx - h, cy - h, cx + h, cy + h]}


# A log66-shaped single-sheet station-frame card: start (reset origin) + end (INSTALLER HH)
# overlays on sheet 10, a station-frame overlay image, and NO struct_connector (matchline draw).
def _log66_card_mr(physical_anchor=None):
    mr = {
        "geometry_status": "STATION_FRAME_RESOLVED",
        "status": "blocked",
        "group": "g66",
        "sheets": [10],
        "seam": None,
        "overlays": [
            {"role": "reset_origin", "sheet": 10, "bbox": [100.0, 95.0, 110.0, 105.0],
             "image": "bore_log66_s10_reset.png", "label": "NEXTLINK HH", "station": "45+33"},
            {"role": "end", "sheet": 10, "bbox": [300.0, 95.0, 310.0, 105.0],
             "image": "bore_log66_s10_evidence_overlay.png", "label": "INSTALLER HH", "station": "0+55"},
        ],
        "struct_connector": None,
    }
    if physical_anchor is not None:
        mr["physical_anchor"] = physical_anchor
    return mr


_RES = {"class": "single_sheet_hh", "hh_hh_ft": 55.0, "boc_ft": 10.0,
        "anchors": [{"role": "reset_origin", "label": "NEXTLINK HH", "station": "45+33"},
                    {"role": "end", "label": "INSTALLER HH", "station": "0+55"}]}
_REC = {"print": "print10"}


# 1. Gap-1 projection: _resolver_card copies mr['physical_anchor'] into geo.
def test_resolver_card_projects_physical_anchor_into_geo():
    pa = {"resolved": True, "start": {"resolved": True, "reason": "unique_structure_blob"},
          "end": {"resolved": True, "reason": "unique_structure_blob"},
          "applied": False, "evidence_only": True}
    card = consult._resolver_card("bore_log66", _log66_card_mr(pa), _REC, _RES)
    assert card["geo"]["physical_anchor"] == pa


# 1b. Absent physical_anchor -> geo has no physical_anchor key (byte-identical to before).
def test_resolver_card_omits_physical_anchor_when_absent():
    card = consult._resolver_card("bore_log66", _log66_card_mr(None), _REC, _RES)
    assert "physical_anchor" not in card["geo"]


# 2. Gap-2 compute core: resolves connector anchors as evidence (applied=False / evidence_only).
def test_compute_physical_anchor_evidence_is_read_only():
    # NEXTLINK HH blobs at the two overlay centroids (105,100) and (305,100); decoys on bad layers.
    paths = [_path("NEXTLINK", 105.0, 100.0), _path("NEXTLINK", 305.0, 100.0),
             _path("FLOWER POT", 120.0, 100.0), _path("TEL-HH", 290.0, 100.0)]
    pa = consult.compute_physical_anchor_evidence([100.0, 95.0, 110.0, 105.0],
                                                  [300.0, 95.0, 310.0, 105.0], paths)
    assert pa["resolved"] is True
    assert pa["applied"] is False and pa["evidence_only"] is True
    rej = ({r["layer"] for r in pa["start"]["rejected_candidates"]}
           | {r["layer"] for r in pa["end"]["rejected_candidates"]})
    assert {"FLOWER POT", "TEL-HH"} & rej  # decoys recorded, never the anchor


# 3. No-draw-change invariant: station-frame card keeps the station-frame artifact + slot.
def test_no_draw_change_station_frame_artifact_preserved():
    pa_present = {"resolved": True,
                  "start": {"resolved": True, "reason": "unique_structure_blob",
                            "rejected_candidates": [{"layer": "FLOWER POT", "reason": "layer_not_allowed"}]},
                  "end": {"resolved": True, "reason": "unique_structure_blob", "rejected_candidates": []},
                  "applied": False, "evidence_only": True}
    card_with = consult._resolver_card("bore_log66", _log66_card_mr(pa_present), _REC, _RES)
    card_without = consult._resolver_card("bore_log66", _log66_card_mr(None), _REC, _RES)
    # SAME drawn artifact + SAME overlay slot — evidence never switched the draw to struct_connector.
    assert card_with["render_artifact_ref"] == card_without["render_artifact_ref"]
    assert card_with["render_artifact_ref"] == "bore_log66_s10_evidence_overlay.png"
    assert "pdf_redline" in card_with["geo"] and "pdf_path_trace" not in card_with["geo"]
    assert card_with["geo"]["matchline_resolution"].get("redline_path") is None  # not structure_to_structure


# 4. End-to-end surfacing: the card's review_reason shows physical_handhole_anchor (+ preferred-over).
def test_review_reason_surfaces_physical_handhole_anchor_for_log66_card():
    pa = {"resolved": True,
          "start": {"resolved": True, "reason": "unique_structure_blob",
                    "rejected_candidates": [{"layer": "FLOWER POT", "reason": "layer_not_allowed"},
                                            {"layer": "TEL-HH", "reason": "layer_not_allowed"}]},
          "end": {"resolved": True, "reason": "unique_structure_blob", "rejected_candidates": []},
          "applied": False, "evidence_only": True}
    card = consult._resolver_card("bore_log66", _log66_card_mr(pa), _REC, _RES)
    rr = build_review_reason(card["geo"])
    assert rr is not None
    disc = next(d for d in rr["discriminators"] if d["name"] == "physical_handhole_anchor")
    assert disc["ok"] is True
    assert "anchored to authored structure symbol" in disc["detail"]
    assert "preferred over nearby" in disc["detail"] and "FLOWER POT" in disc["detail"]
