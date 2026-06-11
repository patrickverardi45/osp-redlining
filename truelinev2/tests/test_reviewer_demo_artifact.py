"""M8.13.a -- tests pinning the static reviewer demo harness (no PDF).

Locks: the sidecar carries both modes and preserves canonical bundle dumps
VERBATIM (never mutates them); demo_data.js has the window.TL2_DEMO shape; the
no-numeric-confidence walker rejects every smell; visual references must
resolve; PLACED_REVIEW bores without crops fail loudly by name; pick-card
candidates keep the frozen SUGGESTION_NOT_PLACEMENT label; the committed
viewer is a self-contained single file that reads demo_data.js, displays the
suggestion label, and labels evidence honestly. Pure/offline -- the corpus
run lives in the M8.13.a proof runner."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from truelinev2.match.symbol_conduit_lane import (
    ComponentReport,
    LaneOutcome,
    S_ELIGIBLE,
    S_PICK,
    StrokeSegment,
)
from truelinev2.proof.run_reviewer_demo_artifact import (
    VIEWER_SRC,
    assert_design_cards_verbatim,
    assert_design_geometry_integrity,
    assert_no_numeric_confidence,
    assert_placed_have_crops,
    assert_suggestion_labels,
    assert_visual_refs_resolve,
    build_demo_sidecar,
    build_design_card_section,
    demo_data_js,
)
from truelinev2.review.design_stroke_cards import build_card_packet
from truelinev2.review.reviewer_payloads import SUGGESTION_LABEL


def _bundles():
    return {
        "default_baseline": {
            "run_mode": "default_baseline",
            "payloads": [{"bore_id": "log1", "lane": "PLACED_REVIEW",
                          "confidence_class": "AUTO_EXACT_MATCH", "candidates": []}],
        },
        "fullest_safe_review": {
            "run_mode": "fullest_safe_review",
            "payloads": [
                {"bore_id": "log1", "lane": "PLACED_REVIEW",
                 "confidence_class": "REVIEW_OPTIN_SOLVER", "candidates": []},
                {"bore_id": "log2", "lane": "PICK_CARD_ROUTE_SUGGESTION",
                 "candidates": [{"candidate_id": "log2-0", "label": SUGGESTION_LABEL}]},
            ],
        },
    }


def _visuals():
    return {"log1": {"evidence_crops": ["visuals/crops/log1_s10.png"],
                     "sheet_context": [], "callout_bboxes": []}}


# --- sidecar -------------------------------------------------------------------------

def test_sidecar_contains_both_modes_and_preserves_bundles_verbatim():
    bundles = _bundles()
    frozen = copy.deepcopy(bundles)
    sc = build_demo_sidecar(bundles, _visuals(), {"10": "visuals/sheets/sheet_10.png"},
                            {"milestone": "test"})
    assert set(sc["bundles"]) == {"default_baseline", "fullest_safe_review"}
    assert sc["bundles"] == frozen          # verbatim pass-through
    assert bundles == frozen                # inputs not mutated
    sc["bundles"]["default_baseline"]["payloads"].clear()
    assert bundles == frozen                # sidecar holds a copy, not aliases


def test_demo_data_js_shape_roundtrips():
    sc = build_demo_sidecar(_bundles(), _visuals(), {}, {"m": 1})
    js = demo_data_js(sc)
    assert js.startswith("window.TL2_DEMO = ")
    assert js.rstrip().endswith(";")
    parsed = json.loads(js[len("window.TL2_DEMO = "):].rstrip().rstrip(";"))
    assert parsed == sc


# --- M8.15 design-stroke card section (additive) -------------------------------------

def _design_packet_dump():
    """A real 1-stroke + 1-pick packet dump (built by the actual M8.15 builder,
    so the synthetic shape can never drift from the contract)."""
    seg = StrokeSegment(sheet=21, start_ft=0.0, end_ft=100.0,
                        stroke_points=((10.0, 20.0), (30.0, 40.0)))
    stroke = LaneOutcome(bore_id="log25", status=S_ELIGIBLE, segments=(seg,),
                         evidence=(ComponentReport("tick_path", "READY", "ok"),
                                   ComponentReport("design_path", "TRACED", "t")))
    pick = LaneOutcome(bore_id="log50", status=S_PICK,
                       evidence=(ComponentReport("conduit_origin", "REFUSED", "s"),),
                       named_missing="span corroboration refused the candidate",
                       detail={"candidate": "SYM@1,2", "candidate_xy": [1.0, 2.0],
                               "end_anchor": [3.0, 4.0]})
    packet, _ = build_card_packet([stroke, pick], {"log25": "PASS"})
    return packet.model_dump(mode="json")


def _stroke_visuals():
    return {"log25": {"stroke_pngs": ["visuals/strokes/log25_lane_s21_redline_stroke.png"]}}


def test_design_section_is_additive_and_verbatim():
    pk = _design_packet_dump()
    frozen = copy.deepcopy(pk)
    section = build_design_card_section(pk, _stroke_visuals(), {"grades_source": "x"})
    # the canonical packet is carried byte-for-byte and the input is not mutated
    assert section["packet"] == frozen
    section["packet"]["cards"].clear()
    assert pk == frozen
    # the sidecar key is present ONLY when supplied
    plain = build_demo_sidecar(_bundles(), _visuals(), {}, {})
    assert "design_cards" not in plain
    withdc = build_demo_sidecar(_bundles(), _visuals(), {}, {},
                                design_cards=build_design_card_section(
                                    _design_packet_dump(), _stroke_visuals(), {}))
    assert withdc["bundles"] == plain["bundles"]      # pinned bundles untouched
    assert withdc["design_cards"]["packet"]["kind_counts"] == {
        "DESIGN_STROKE_REVIEW": 1, "DESIGN_PICK_CARD": 1}


def test_design_packet_carried_verbatim_in_sidecar():
    pk = _design_packet_dump()
    sc = build_demo_sidecar(_bundles(), _visuals(), {}, {},
                            design_cards=build_design_card_section(
                                pk, _stroke_visuals(), {}))
    assert_design_cards_verbatim(sc, pk)
    sc["design_cards"]["packet"]["mode"] = "TAMPERED"
    with pytest.raises(ValueError, match="mutated the canonical design-card"):
        assert_design_cards_verbatim(sc, pk)


def test_design_geometry_integrity_passes_and_fails_by_name():
    pk = _design_packet_dump()
    assert_design_geometry_integrity(pk, _stroke_visuals())
    # one rendered stroke per segment is mandatory
    with pytest.raises(ValueError, match="log25"):
        assert_design_geometry_integrity(pk, {"log25": {"stroke_pngs": []}})
    # a pick card must never carry a stroke artifact (masquerade guard)
    with pytest.raises(ValueError, match="log50"):
        assert_design_geometry_integrity(
            pk, {**_stroke_visuals(),
                 "log50": {"stroke_pngs": ["visuals/strokes/log50_x.png"]}})


def test_design_stroke_pngs_must_resolve(tmp_path):
    (tmp_path / "visuals" / "strokes").mkdir(parents=True)
    (tmp_path / "visuals" / "strokes" / "log25_lane_s21_redline_stroke.png").write_bytes(b"png")
    sc = build_demo_sidecar(_bundles(), {}, {}, {},
                            design_cards=build_design_card_section(
                                _design_packet_dump(), _stroke_visuals(), {}))
    assert_visual_refs_resolve(sc, tmp_path)          # design pngs resolve
    sc["design_cards"]["visuals"]["log25"]["stroke_pngs"].append("visuals/strokes/gone.png")
    with pytest.raises(ValueError, match="gone.png"):
        assert_visual_refs_resolve(sc, tmp_path)


def test_no_numeric_confidence_walker_accepts_design_cards():
    # design cards carry geometry (coords) + closed grade classes, never a
    # numeric confidence — the walker must pass over the whole section
    sc = build_demo_sidecar(_bundles(), _visuals(), {}, {},
                            design_cards=build_design_card_section(
                                _design_packet_dump(), _stroke_visuals(), {}))
    assert_no_numeric_confidence(sc)


# --- honesty gates -------------------------------------------------------------------

def test_no_numeric_confidence_walker():
    assert_no_numeric_confidence({"confidence_class": "AUTO_EXACT_MATCH"})
    with pytest.raises(ValueError, match="forbidden"):
        assert_no_numeric_confidence({"payloads": [{"confidence_score": 0.9}]})
    with pytest.raises(ValueError, match="forbidden"):
        assert_no_numeric_confidence({"probability": 1})
    with pytest.raises(ValueError, match="forbidden"):
        assert_no_numeric_confidence({"match_percent": 95})
    with pytest.raises(ValueError, match="numeric confidence"):
        assert_no_numeric_confidence({"confidence": 0.5})


def test_suggestion_labels_frozen():
    assert_suggestion_labels(_bundles()["fullest_safe_review"])
    bad = _bundles()["fullest_safe_review"]
    bad["payloads"][1]["candidates"][0]["label"] = "PLACEMENT"
    with pytest.raises(ValueError, match="label drift"):
        assert_suggestion_labels(bad)


def test_placed_without_crops_fails_loudly_by_name():
    assert_placed_have_crops(_bundles()["fullest_safe_review"], _visuals())
    with pytest.raises(ValueError, match="log1"):
        assert_placed_have_crops(_bundles()["fullest_safe_review"], {})
    with pytest.raises(ValueError, match="log1"):
        assert_placed_have_crops(_bundles()["fullest_safe_review"],
                                 {"log1": {"evidence_crops": []}})


def test_visual_refs_must_resolve(tmp_path):
    (tmp_path / "visuals" / "crops").mkdir(parents=True)
    (tmp_path / "visuals" / "crops" / "log1_s10.png").write_bytes(b"png")
    sc = build_demo_sidecar(_bundles(), _visuals(), {}, {})
    assert_visual_refs_resolve(sc, tmp_path)
    sc["visuals"]["log1"]["evidence_crops"].append("visuals/crops/missing.png")
    with pytest.raises(ValueError, match="missing.png"):
        assert_visual_refs_resolve(sc, tmp_path)


# --- the committed viewer -------------------------------------------------------------

def test_viewer_is_committed_single_file_reading_demo_data():
    assert VIEWER_SRC.is_file(), "committed viewer missing"
    html = VIEWER_SRC.read_text(encoding="utf-8")
    assert 'src="demo_data.js"' in html          # reads the generated sidecar
    assert "window.TL2_DEMO" in html
    assert "SUGGESTION" in html                  # suggestion framing rendered
    assert "not" in html.lower() and "stroke" in html.lower()  # evidence honesty label
    assert "textContent" in html                 # data lands XSS-safe, never innerHTML
    assert ".innerHTML" not in html
    # self-contained: no external/network references, no build chain, no React
    low = html.lower()
    assert "https://" not in low and "http://" not in low
    assert "react" not in low and "node_modules" not in low


def test_viewer_displays_confidence_classes_not_numbers():
    html = VIEWER_SRC.read_text(encoding="utf-8")
    assert "confidence_class" in html
    assert "confidence_score" not in html and "probability" not in html


def test_viewer_renders_design_cards_section_lazily():
    html = VIEWER_SRC.read_text(encoding="utf-8")
    # the design-stroke section is wired in and tab-routed
    assert "design_cards" in html
    assert "renderDesign" in html and "DESIGN_KEY" in html
    assert "DESIGN_STROKE_REVIEW" in html and "DESIGN_PICK_CARD" in html
    # stroke images load on demand (only when the <details> is opened)
    assert "toggle" in html and "loads on demand" in html
    # still XSS-safe + self-contained after the extension
    assert ".innerHTML" not in html
    low = html.lower()
    assert "https://" not in low and "http://" not in low
    assert "react" not in low and "node_modules" not in low
