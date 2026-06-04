"""Contract / invariant tests for the PDF-first evidence payload (closeout + bridge prep).

NON-VISUAL / PDF-FREE / no engine run. Two kinds of check:

  * BEHAVIORAL (drives real code): the log56 evidence-fusion selector ABSTAINS with a
    machine-readable reason and NO path (no fake diagonal) when its discriminators do not bind.
    This exercises app.core.redline_consult.authored_path_selector directly (pure, no PDF).

  * SHAPE CONTRACT (synthetic fixtures mirroring the VERIFIED canonical builder output in
    pdf_first_adapter.py + redline_consult/consult.py): the envelope/card carry the durable
    fields closeout needs, abstained seam segments never carry a drawn artifact, and the log66
    structure connector evidence is present. Binding these to a live engine fixture is a
    visual-capable follow-up; today they pin the shape the consultant/bridge can code against.

COMMAND (from repo root):
    python -m pytest backend/tests/test_pdf_first_evidence_contract.py -v
"""
from __future__ import annotations

from app.core.redline_consult import authored_path_selector as APS

# Machine-readable abstain reasons documented by the selector (D13 safety doctrine).
ABSTAIN_REASONS = {
    "named_matchline_not_bound",
    "color_did_not_isolate_single_run",
    "endpoint_structure_not_bound",
    "multiple_candidate_paths_after_evidence_fusion",
    "station_callouts_insufficient_to_orient",
    "path_not_station_monotonic",
    "boc_corridor_ambiguous",
}

# Durable fields a downstream consumer (closeout + Hero-map bridge) relies on.
REQUIRED_ENVELOPE_FIELDS = (
    "schema_version", "status", "render_target", "source", "counts_by_tier",
    "counts_by_surface", "placements", "review_items", "fail_safe", "groups", "warnings",
)
REQUIRED_CARD_FIELDS = ("log_ids", "tier", "surface", "render_target", "station_range")


def _missing(obj, required):
    return [f for f in required if f not in obj]


# ── BEHAVIORAL: real selector abstain (no fake diagonal) ──────────────────────
def test_selector_abstains_with_reason_and_no_path():
    res = APS.select_authored_s17_path(
        segments=[], matchline_paths=[], start_xy=(0.0, 0.0),
        home_sta="1+61", neighbor_sta="1+59",
        station_callouts=[], matchline_callouts=[], offset_callouts=[], boc_ft=11,
    )
    assert res["resolved"] is False
    assert res["path_xy"] is None                       # abstain draws NOTHING (no fake diagonal)
    assert isinstance(res["reason"], str) and res["reason"] in ABSTAIN_REASONS
    assert isinstance(res["discriminators"], dict)      # machine-readable evidence trail present


# ── SHAPE CONTRACT fixtures (mirror the verified canonical payload) ───────────
def _seam_stitch_block():
    """Mirror redline_consult/consult.py `_render_cross_sheet_seam_stitch` output for log56."""
    return {
        "resolved": False, "run_id": "bore_log56",
        "reason": "cross_sheet_seam_abstain_pending_evidence_fusion",
        "machine_resolved_anchors": 3, "owner_verified_anchors": 1,
        "anchors": {
            "sheet17_start_hh": {"source": "machine", "resolved": True, "xy": [100.0, 200.0], "reason": None},
            "sheet17_seam_crossing": {"source": "machine", "resolved": True, "xy": [140.0, 60.0], "reason": None},
        },
        "segments": [
            {"sheet": 17, "status": "abstained_pending_evidence_fusion",
             "reason": "named_matchline_not_bound", "discriminators": {}, "artifact_name": None},
            {"sheet": 21, "status": "abstained_requires_path_evidence",
             "reason": "s21_vectors_disconnected_no_authored_path", "artifact_name": None},
        ],
    }


def _sample_envelope():
    """A representative pdf_first_evidence envelope (canonical shape) with a log56 seam-stitch
    review card and a log66 structure-connector card."""
    log56_card = {
        "log_ids": ["bore_log56"], "tier": "MATCHLINE_FRAME_RESOLVER", "surface": "review",
        "render_target": "evidence_card", "station_range": {"start": "0+00", "end": "2+76"},
        "end_structures": ["INSTALLER HH"], "evidence": ["eq 4+57=0+00 (s17)", "BOC 11'"],
        "geo": {"geometry_status": "RESOLVED", "frame": {"multi_sheet": True, "page": 17},
                "cross_sheet_seam_stitch": _seam_stitch_block()},
    }
    log66_card = {
        "log_ids": ["bore_log66"], "tier": "STRUCT_CONNECTOR", "surface": "review",
        "render_target": "evidence_card", "station_range": {"start": "0+00", "end": "0+55"},
        "end_structures": ["NEXTLINK HH", "INSTALLER HH"], "evidence": ["55' HH-HH", "BOC 10'"],
        "geo": {"geometry_status": "RESOLVED", "frame": {"multi_sheet": False, "page": 10},
                "struct_connector": {"resolved": True, "anchor": [320.0, 410.0],
                                     "source": "physical_anchor", "artifact_name": "bore_log66_connector_s10.png"}},
    }
    return {
        "schema_version": "pdf-first-evidence-1", "status": "OK",
        "render_target": "evidence_card",
        "source": {"plan_pdf": "Brenham.pdf", "input": "committed_rows",
                   "logs": ["bore_log56", "bore_log66"]},
        "counts_by_tier": {"MATCHLINE_FRAME_RESOLVER": 1, "STRUCT_CONNECTOR": 1},
        "counts_by_surface": {"placements": 0, "review_items": 2, "fail_safe": 0},
        "placements": [], "review_items": [log56_card, log66_card], "fail_safe": [],
        "groups": [], "warnings": [],
        "resolver": {"flag": "TRUELINE_MATCHLINE_FRAME_RESOLVER", "consult_active": True,
                     "resolved_count": 2, "corrections_applied": []},
    }


def _card_for(env, log_id):
    for card in env["placements"] + env["review_items"]:
        if log_id in (card.get("log_ids") or []):
            return card
    raise AssertionError("no card for %s" % log_id)


def test_envelope_required_fields_present():
    assert _missing(_sample_envelope(), REQUIRED_ENVELOPE_FIELDS) == []


def test_review_cards_carry_required_fields():
    env = _sample_envelope()
    for card in env["review_items"]:
        assert _missing(card, REQUIRED_CARD_FIELDS) == [], card.get("log_ids")


def test_abstained_seam_segments_never_carry_a_drawn_artifact():
    """log56 s21 (and any abstained seam segment) must carry a reason and NO artifact."""
    css = _card_for(_sample_envelope(), "bore_log56")["geo"]["cross_sheet_seam_stitch"]
    s21 = next(s for s in css["segments"] if s["sheet"] == 21)
    assert s21["status"].startswith("abstained")
    assert s21.get("artifact_name") is None         # nothing drawn -> no fake diagonal
    assert s21.get("reason")                          # machine-readable reason present
    # General invariant across every segment.
    for seg in css["segments"]:
        if str(seg.get("status", "")).startswith("abstained"):
            assert seg.get("artifact_name") is None, seg
            assert seg.get("reason"), seg


def test_seam_s17_abstain_surfaces_discriminators():
    """Canonical payload carries the D13 discriminators (the typed frontend mirror drops them)."""
    css = _card_for(_sample_envelope(), "bore_log56")["geo"]["cross_sheet_seam_stitch"]
    s17 = next(s for s in css["segments"] if s["sheet"] == 17)
    assert "discriminators" in s17 and isinstance(s17["discriminators"], dict)


def test_log66_connector_evidence_payload_exists():
    sc = _card_for(_sample_envelope(), "bore_log66")["geo"]["struct_connector"]
    assert sc["resolved"] is True
    assert "anchor" in sc and isinstance(sc["anchor"], list)
    assert sc.get("artifact_name")                   # connector was drawn for log66
