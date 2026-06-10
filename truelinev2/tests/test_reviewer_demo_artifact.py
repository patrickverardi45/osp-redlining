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

from truelinev2.proof.run_reviewer_demo_artifact import (
    VIEWER_SRC,
    assert_no_numeric_confidence,
    assert_placed_have_crops,
    assert_suggestion_labels,
    assert_visual_refs_resolve,
    build_demo_sidecar,
    demo_data_js,
)
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
