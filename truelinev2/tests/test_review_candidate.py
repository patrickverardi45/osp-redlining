"""Proof for the SOURCE-BACKED REVIEW CANDIDATE MVP — the first drawing-capable slice, gated on
READY_FOR_REVIEW_REDLINE.

It generates a human-reviewable REVIEW candidate (with a RED overlay from observer-exposed geometry) ONLY when the
completed readiness spine returns READY_FOR_REVIEW_REDLINE, and generates ZERO candidates / NO artifact for every
refusal. It is NOT AUTO, NOT final placement, and NOT a status promotion. Fixtures are the generic complete-package
QA harness (product QA, not cold validation); artifacts are written into tmp and never committed.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

from truelinev2.harness.complete_package_qa import SCENARIOS, build_complete_package
from truelinev2.harness.review_candidate import (
    REVIEW_CANDIDATE_READY,
    REVIEW_CANDIDATE_REFUSED,
    REVIEW_STROKE_RGB,
    run_candidate_for_package,
)

_HARNESS = Path(__file__).resolve().parents[1] / "harness"
_REFUSAL_STATUS = {
    "plan_only": "MISSING_BORE_SPAN_SOURCE",
    "source_no_confirmed_span": "NO_SOURCE_CONFIRMED_SPAN",
    "span_labels_missing": "ANCHOR_BLOCKED",
    "span_anchors_off_route": "ANCHOR_BLOCKED",
    "span_anchors_route_blocked": "ROUTE_BLOCKED",
    "span_anchors_route_broken": "ROUTE_BLOCKED",
}


def _pkg_for(tmp_path, key):
    sc = next(s for s in SCENARIOS if s.key == key)
    return build_complete_package(tmp_path, name="rc-%s" % key, labels=sc.labels, route_shape=sc.route_shape,
                                  bore_csv=sc.bore_csv)


def _count_red(png_path):
    """Count solid RED pixels in a rendered PNG (the REVIEW stroke). Read-only raster scan via fitz."""
    import fitz
    pix = fitz.Pixmap(str(png_path))
    data, n = pix.samples, pix.n
    count = 0
    for i in range(0, len(data) - n + 1, n):
        if data[i] > 180 and data[i + 1] < 90 and data[i + 2] < 90:
            count += 1
    return count


def _red_centroid(png_path):
    """Return the (px, py) centroid of the RED pixels in a rendered PNG, or None. Read-only via fitz."""
    import fitz
    pix = fitz.Pixmap(str(png_path))
    data, n, w = pix.samples, pix.n, pix.width
    sx = sy = cnt = 0
    for i in range(0, len(data) - n + 1, n):
        if data[i] > 180 and data[i + 1] < 90 and data[i + 2] < 90:
            idx = i // n
            sx += idx % w
            sy += idx // w
            cnt += 1
    return (sx / cnt, sy / cnt) if cnt else None


# ----------------------------------------------------------------------------------------------------------- #
# (1) the complete package produces exactly ONE REVIEW candidate.
# ----------------------------------------------------------------------------------------------------------- #
def test_complete_ready_produces_exactly_one_candidate(tmp_path):
    rep = run_candidate_for_package(_pkg_for(tmp_path, "complete_ready"))
    assert rep.readiness_status == "READY_FOR_REVIEW_REDLINE"
    assert rep.candidate_status == REVIEW_CANDIDATE_READY
    assert rep.candidate_count == 1


# ----------------------------------------------------------------------------------------------------------- #
# (2) the candidate is source-backed by span row + bound anchors + verified route.
# ----------------------------------------------------------------------------------------------------------- #
def test_candidate_is_source_backed(tmp_path):
    c = run_candidate_for_package(_pkg_for(tmp_path, "complete_ready")).candidates[0]
    assert c.start_station == "11+75" and c.end_station == "13+25"
    assert c.source_file and c.source_citation                              # extracted span source
    assert c.start_anchor_summary and c.start_anchor_summary["xy"] and c.start_anchor_summary["method"]
    assert c.end_anchor_summary and c.end_anchor_summary["xy"]              # bound anchors (observer-exposed xy)
    assert c.route_summary["route_ready"] is True
    assert c.route_summary["main_run_status"] == "MAIN_ROUTE_DISCRIMINATED"
    assert len(c.route_geometry) >= 1                                       # observer-exposed verified backbone
    joined = " || ".join(c.evidence_chain)                                  # the evidence chain explains WHY
    assert "READY_FOR_REVIEW_REDLINE" in joined and "route verified" in joined and "NOT AUTO" in joined


# ----------------------------------------------------------------------------------------------------------- #
# (3) every refusal scenario produces ZERO candidates and NO artifact.
# ----------------------------------------------------------------------------------------------------------- #
def test_all_refusals_produce_zero_candidates_and_no_artifact(tmp_path):
    for key, expected_status in _REFUSAL_STATUS.items():
        art = tmp_path / ("art-%s" % key)
        rep = run_candidate_for_package(_pkg_for(tmp_path, key), artifact_dir=art)
        assert rep.readiness_status == expected_status, key                # the exact non-READY status
        assert rep.candidate_status == REVIEW_CANDIDATE_REFUSED, key
        assert rep.candidate_count == 0 and rep.generated_visual is False, key
        assert rep.refusal_reason, key                                      # a named refusal reason
        assert not art.exists() or not any(art.iterdir()), key             # no redline artifact written


# ----------------------------------------------------------------------------------------------------------- #
# (4) candidate output includes the metadata a later clickable UI needs.
# ----------------------------------------------------------------------------------------------------------- #
def test_candidate_metadata_for_clickable_ui(tmp_path):
    c = run_candidate_for_package(_pkg_for(tmp_path, "complete_ready")).candidates[0].to_dict()
    for k in ("span_id", "start_station", "end_station", "source_file", "source_citation",
              "start_anchor_summary", "end_anchor_summary", "route_summary"):
        assert k in c and c[k] is not None, k
    assert c["route_summary"]["route_observer_status"] == "MAIN_ROUTE_DISCRIMINATED"


# ----------------------------------------------------------------------------------------------------------- #
# (5) no AUTO, no placement, no promotion; the readiness classifier is untouched (still draws nothing).
# ----------------------------------------------------------------------------------------------------------- #
def test_no_auto_no_placement_no_promotion(tmp_path):
    pkg = _pkg_for(tmp_path, "complete_ready")
    rep = run_candidate_for_package(pkg, artifact_dir=tmp_path / "art")
    assert rep.performs_auto is False and rep.performs_placement is False and rep.promotes_status is False
    c = rep.candidates[0]
    assert c.is_auto is False and c.is_final_placement is False and c.is_promotion is False
    from truelinev2.harness.route_verification import run_package_route_readiness
    pr = run_package_route_readiness(pkg)
    assert pr.report.draws_anything is False and pr.report.performs_placement is False


# ----------------------------------------------------------------------------------------------------------- #
# Visual: before + after PNGs are generated and the RED REVIEW stroke is actually drawn.
# ----------------------------------------------------------------------------------------------------------- #
def test_visual_before_after_and_red_stroke_drawn(tmp_path):
    rep = run_candidate_for_package(_pkg_for(tmp_path, "complete_ready"), artifact_dir=tmp_path / "art")
    c = rep.candidates[0]
    assert rep.generated_visual is True and c.artifact_before and c.artifact_after
    before, after = Path(c.artifact_before), Path(c.artifact_after)
    assert before.is_file() and after.is_file()
    assert before.stat().st_size > 0 and after.stat().st_size > 0
    assert before.read_bytes() != after.read_bytes()                       # the overlay changed the image
    assert _count_red(before) == 0 and _count_red(after) > 0               # the RED REVIEW stroke was drawn


def test_review_stroke_is_the_canonical_red():
    from truelinev2.render.crop import REDLINE_STROKE_RGB                    # test may read render; the module may not
    assert REVIEW_STROKE_RGB == REDLINE_STROKE_RGB == (220, 25, 25)         # Red Stroke Law, test-locked


def test_overlay_display_to_raw_mapping_survives_page_rotation(tmp_path):
    """Lock the display->raw inverse-rotation mapping in render_review_candidate_overlay: the SAME display-space
    geometry must render its RED stroke at the SAME display-pixel location on a rotated page as on a flat one."""
    import fitz

    from truelinev2.harness.review_candidate import render_review_candidate_overlay

    geom = ({"a": (40.0, 150.0), "b": (160.0, 150.0)},)                     # horizontal in DISPLAY space
    centroids = {}
    for tag, rot in (("flat", 0), ("rot90", 90)):
        plan = tmp_path / ("%s.pdf" % tag)
        doc = fitz.open()
        page = doc.new_page(width=300, height=200)
        if rot:
            page.set_rotation(rot)
        doc.save(str(plan))
        doc.close()
        before, after = tmp_path / ("%s_b.png" % tag), tmp_path / ("%s_a.png" % tag)
        render_review_candidate_overlay(str(plan), 1, geom, out_before=before, out_after=after)
        assert _count_red(before) == 0 and _count_red(after) > 0, tag      # stroke drawn on-page for both
        centroids[tag] = _red_centroid(after)
    # display-space input -> same display-pixel output regardless of rotation (inverse rotation compensates)
    (fx, fy), (rx, ry) = centroids["flat"], centroids["rot90"]
    assert abs(fx - rx) <= 20 and abs(fy - ry) <= 20, centroids


# ----------------------------------------------------------------------------------------------------------- #
# (6)/(7) no forbidden imports; JSON-serializable; name-free coverage via the cold-package harness guard.
# ----------------------------------------------------------------------------------------------------------- #
_FORBIDDEN_IMPORT_SEGMENTS = {"render", "renderer", "placement", "cap_review", "_cap_review",
                              "api", "store", "web", "staging", "backend", "contracts", "match"}


def _imported_modules(src):
    mods = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            for a in node.names:
                mods.add(a.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module)
    return mods


def test_review_candidate_imports_no_forbidden_modules():
    src = (_HARNESS / "review_candidate.py").read_text(encoding="utf-8")
    for m in _imported_modules(src):
        leaked = set(m.split(".")) & _FORBIDDEN_IMPORT_SEGMENTS
        assert not leaked, "review_candidate imports forbidden module %r (%s)" % (m, leaked)


def test_report_is_json_serializable(tmp_path):
    rep = run_candidate_for_package(_pkg_for(tmp_path, "complete_ready"), artifact_dir=tmp_path / "art")
    text = json.dumps(rep.to_dict(), sort_keys=True)
    assert '"candidates"' in text and '"evidence_chain"' in text and '"route_geometry"' in text
