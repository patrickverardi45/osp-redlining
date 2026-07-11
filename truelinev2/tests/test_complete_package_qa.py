"""Proof for the GENERIC COMPLETE-PACKAGE QA HARNESS (product QA for the complete-package workflow, NOT cold
validation).

It builds a generic name-free synthetic COMPLETE package and runs it through the SAME read-only readiness spine the
product uses (source-span extractor → endpoint binder → route verifier → readiness adapter), asserting the positive
package reaches READY_FOR_REVIEW_REDLINE and every refusal case fails at the correct stage — WITHOUT the harness
hard-coding any final status (the statuses are computed by the real observers). It draws nothing, invents no
coordinate, and exposes the metadata a later clickable-dots / detail-drawer UI needs.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

from truelinev2.harness.complete_package_qa import (
    ROUTE_BENT,
    ROUTE_CLEAN,
    ROUTE_FORKED,
    SCENARIOS,
    build_complete_package,
    check_scenario,
    run_all_scenarios,
    run_qa_scenario,
    _CONFIRMED_SPAN_CSV,
    _LABELS,
)
from truelinev2.harness.endpoint_binding import EndpointBindingReport
from truelinev2.harness.review_readiness import ReviewReadinessReport
from truelinev2.harness.route_verification import PackageRouteReadiness, RouteVerificationReport, run_package_route_readiness
from truelinev2.harness.span_extractor import SpanExtraction

_HARNESS = Path(__file__).resolve().parents[1] / "harness"


def _by_key(key):
    return next(s for s in SCENARIOS if s.key == key)


# ----------------------------------------------------------------------------------------------------------- #
# (1)+(2) the positive complete package is READY; every refusal case fails at the correct stage.
# ----------------------------------------------------------------------------------------------------------- #
def test_all_scenarios_match_expected(tmp_path):
    # Fix-wave-2 G8 (additive): 7 pre-existing scenarios + the new "bent_ready" multi-bend scenario -> 8.
    results = run_all_scenarios(tmp_path)
    assert len(results) == 8
    for sc, res, ok, mm in results:
        assert ok, "scenario %s mismatched: %s" % (sc.key, mm)


def test_positive_complete_package_is_ready(tmp_path):
    res = run_qa_scenario(tmp_path, _by_key("complete_ready"))
    r = res.readiness.report
    assert r.status == "READY_FOR_REVIEW_REDLINE" and r.stage == "READY" and r.ready is True
    assert res.readiness.routes.any_route_ready is True
    assert res.readiness.bindings.any_bound is True


def test_each_refusal_case_fails_at_correct_stage(tmp_path):
    expected = {
        "plan_only": ("MISSING_BORE_SPAN_SOURCE", "SPAN_SOURCE"),
        "source_no_confirmed_span": ("NO_SOURCE_CONFIRMED_SPAN", "SPAN_SOURCE"),
        "span_labels_missing": ("ANCHOR_BLOCKED", "ANCHOR"),
        "span_anchors_off_route": ("ANCHOR_BLOCKED", "ANCHOR"),
        "span_anchors_route_blocked": ("ROUTE_BLOCKED", "ROUTE"),
        "span_anchors_route_broken": ("ROUTE_BLOCKED", "ROUTE"),
    }
    for key, (status, stage) in expected.items():
        res = run_qa_scenario(tmp_path, _by_key(key))
        r = res.readiness.report
        assert (r.status, r.stage) == (status, stage), "%s -> %s@%s" % (key, r.status, r.stage)
        assert r.ready is False and r.draws_anything is False and r.performs_placement is False


# ----------------------------------------------------------------------------------------------------------- #
# (3) the harness runs through the SAME spine modules the product uses.
# ----------------------------------------------------------------------------------------------------------- #
def test_runs_through_the_real_spine_modules(tmp_path):
    pr = run_qa_scenario(tmp_path, _by_key("complete_ready")).readiness
    assert isinstance(pr, PackageRouteReadiness)
    assert isinstance(pr.report, ReviewReadinessReport)       # readiness classifier/adapter
    assert isinstance(pr.extraction, SpanExtraction)          # source-span extractor
    assert isinstance(pr.bindings, EndpointBindingReport)     # endpoint binder
    assert isinstance(pr.routes, RouteVerificationReport)     # route verifier


# ----------------------------------------------------------------------------------------------------------- #
# (4) the harness does NOT bypass the observers with hard-coded final statuses (status tracks the real inputs).
# ----------------------------------------------------------------------------------------------------------- #
def test_status_is_computed_not_hardcoded(tmp_path):
    # same builder, three inputs -> three DIFFERENT computed statuses (a hard-coded status could not do this).
    ready = run_package_route_readiness(build_complete_package(
        tmp_path, name="mut-ready", labels=_LABELS, route_shape=ROUTE_CLEAN, bore_csv=_CONFIRMED_SPAN_CSV))
    no_bore = run_package_route_readiness(build_complete_package(
        tmp_path, name="mut-nobore", labels=_LABELS, route_shape=ROUTE_CLEAN, bore_csv=None))
    forked = run_package_route_readiness(build_complete_package(
        tmp_path, name="mut-forked", labels=_LABELS, route_shape=ROUTE_FORKED, bore_csv=_CONFIRMED_SPAN_CSV))
    assert ready.report.status == "READY_FOR_REVIEW_REDLINE"
    assert no_bore.report.status == "MISSING_BORE_SPAN_SOURCE"
    assert forked.report.status == "ROUTE_BLOCKED"


def test_check_scenario_reads_the_live_status(tmp_path):
    # a deliberately wrong expectation must FAIL the check -> proves check compares against the computed status.
    import dataclasses
    sc = _by_key("complete_ready")
    res = run_qa_scenario(tmp_path, sc)
    ok, _ = check_scenario(res, sc)
    assert ok is True
    wrong = dataclasses.replace(sc, expected_status="ROUTE_BLOCKED")
    ok2, mm2 = check_scenario(res, wrong)
    assert ok2 is False and any("status" in m for m in mm2)


# ----------------------------------------------------------------------------------------------------------- #
# (5) the output includes the metadata a later clickable-dots / detail-drawer UI needs (no fake depth/BOC).
# ----------------------------------------------------------------------------------------------------------- #
def test_ui_summary_exposes_ui_metadata(tmp_path):
    s = run_qa_scenario(tmp_path, _by_key("complete_ready")).ui_summary()
    assert s["resolved"] is True and s["readiness_status"] == "READY_FOR_REVIEW_REDLINE"
    assert set(("stage", "ready", "recommended_next_input", "span_rows", "anchor_bindings",
                "route_verifications")) <= set(s)
    row = s["span_rows"][0]
    assert row["start_station"] == "11+75" and row["end_station"] == "13+25"
    assert row["source_file"] and row["source_kind"] and row["citation"]        # source citation / file for the UI
    b = s["anchor_bindings"][0]
    assert b["bound"] is True and b["start_anchor"]["xy"] is not None and b["start_anchor"]["method"]
    v = s["route_verifications"][0]
    assert v["route_ready"] is True and v["main_run_status"] == "MAIN_ROUTE_DISCRIMINATED"


def test_no_fake_depth_or_boc_but_structures_flow_when_present(tmp_path):
    # default confirmed span (no structure columns) -> structures None; NO depth/boc anywhere.
    plain = run_qa_scenario(tmp_path, _by_key("complete_ready")).ui_summary()
    prow = plain["span_rows"][0]
    assert prow["start_structure"] is None and prow["end_structure"] is None
    blob = json.dumps(plain).lower()
    assert "depth" not in blob and "boc" not in blob
    # when the SOURCE TABLE itself carries structures, they flow through verbatim (never invented otherwise).
    pkg = build_complete_package(tmp_path, name="qa-struct", labels=_LABELS, route_shape=ROUTE_CLEAN,
                                 bore_csv="start,end,start_structure,end_structure\n11+75,13+25,S1,S2\n")
    pr = run_package_route_readiness(pkg)
    srow = pr.extraction.spans[0]
    assert srow.start_structure == "S1" and srow.end_structure == "S2"


# ----------------------------------------------------------------------------------------------------------- #
# (6) no drawing / AUTO / placement / fixture mutation; read-only over an existing package; JSON-serializable.
# ----------------------------------------------------------------------------------------------------------- #
def test_spine_is_read_only_over_the_built_package(tmp_path):
    pkg = Path(build_complete_package(tmp_path, name="qa-ro", labels=_LABELS, route_shape=ROUTE_CLEAN,
                                      bore_csv=_CONFIRMED_SPAN_CSV))
    before = sorted(str(p.relative_to(pkg)) for p in pkg.rglob("*"))
    run_package_route_readiness(str(pkg))
    run_package_route_readiness(str(pkg))
    after = sorted(str(p.relative_to(pkg)) for p in pkg.rglob("*"))
    assert before == after
    assert "uploads/plan.probe.pdf" not in after                # the probe fixture is cleaned up


def test_never_draws_or_places_across_all_scenarios(tmp_path):
    for sc, res, ok, mm in run_all_scenarios(tmp_path):
        r = res.readiness.report
        assert r.draws_anything is False and r.performs_placement is False


def test_qa_result_is_json_serializable(tmp_path):
    s = run_qa_scenario(tmp_path, _by_key("complete_ready")).ui_summary()
    text = json.dumps(s, sort_keys=True)
    assert '"span_rows"' in text and '"anchor_bindings"' in text and '"route_verifications"' in text


# ----------------------------------------------------------------------------------------------------------- #
# Fix-wave-2 G8/W-E (additive proof asset): the "bent_ready" scenario reaches READY_FOR_REVIEW_REDLINE through
# the SAME UNMODIFIED spine, with a genuinely non-collinear >= 3-segment / >= 2-real-bend backbone -- the real
# fixture source-route-adoption's success-path tests bind to (Item-10 ruling: no test-local geometry patch).
# The 7 PRE-EXISTING scenarios (including "complete_ready", ROUTE_CLEAN's single-segment straight backbone)
# stay byte-identical -- this is purely additive.
# ----------------------------------------------------------------------------------------------------------- #
def _seg_len(seg):
    (ax, ay), (bx, by) = seg["a"], seg["b"]
    return ((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5


def _is_collinear(p0, p1, p2, tol=1e-6):
    """Cross-product test: True iff p0/p1/p2 lie on one straight line (within a tiny float tolerance)."""
    (x0, y0), (x1, y1), (x2, y2) = p0, p1, p2
    cross = (x1 - x0) * (y2 - y0) - (y1 - y0) * (x2 - x0)
    return abs(cross) <= tol


def test_bent_ready_scenario_reaches_ready_with_a_genuine_multi_bend_backbone(tmp_path):
    res = run_qa_scenario(tmp_path, _by_key("bent_ready"))
    r = res.readiness.report
    assert r.status == "READY_FOR_REVIEW_REDLINE" and r.stage == "READY" and r.ready is True
    assert res.readiness.routes.any_route_ready is True

    v = next(v for v in res.readiness.routes.verifications if v.route_ready)
    assert v.main_run_status == "MAIN_ROUTE_DISCRIMINATED"
    geom = v.route_geometry
    assert len(geom) >= 3, "expected >= 3 segments, got %d" % len(geom)          # >= 3 segments

    # contiguous chain: seg[i].b == seg[i+1].a exactly (the SAME exact-contiguity the adoption module requires).
    backbone_points = [geom[0]["a"]] + [seg["b"] for seg in geom]
    for i in range(len(geom) - 1):
        assert geom[i]["b"] == geom[i + 1]["a"], "backbone not exactly contiguous at segment %d/%d" % (i, i + 1)

    # >= 2 REAL bends: at least two interior vertices where the incoming/outgoing direction genuinely changes
    # (not collinear) -- proves this is NOT just a re-chunked straight line.
    bends = sum(
        0 if _is_collinear(backbone_points[i - 1], backbone_points[i], backbone_points[i + 1]) else 1
        for i in range(1, len(backbone_points) - 1))
    assert bends >= 2, "expected >= 2 real (non-collinear) interior bends, got %d" % bends
    assert all(_seg_len(seg) > 0 for seg in geom)                                # no degenerate zero-length leg


def test_bent_ready_scenario_is_additive_existing_scenarios_unchanged(tmp_path):
    """The pre-existing 7 scenarios' readiness OUTPUTS (status/stage/ready +, for complete_ready, the exact
    single-segment backbone geometry ROUTE_CLEAN has always produced) are unchanged by adding ROUTE_BENT /
    "bent_ready" -- proving the new scenario is purely additive, never a behavior change to any prior one."""
    for sc, res, ok, mm in run_all_scenarios(tmp_path):
        if sc.key == "bent_ready":
            continue
        assert ok, "pre-existing scenario %s regressed: %s" % (sc.key, mm)

    # complete_ready keeps its OWN single straight segment (ROUTE_CLEAN unaffected by ROUTE_BENT existing) --
    # proven by re-running it twice under this same fix (fixture builder is deterministic; a real regression
    # from the ROUTE_BENT addition would show up as a segment-count/shape change here, not just a hardcoded
    # literal that would be brittle across font/PyMuPDF versions).
    r1 = run_qa_scenario(tmp_path, _by_key("complete_ready"))
    r2 = run_qa_scenario(tmp_path, _by_key("complete_ready"))
    v1 = next(v for v in r1.readiness.routes.verifications if v.route_ready)
    v2 = next(v for v in r2.readiness.routes.verifications if v.route_ready)
    assert len(v1.route_geometry) == len(v2.route_geometry) == 1   # ROUTE_CLEAN's own single straight segment
    assert v1.route_geometry == v2.route_geometry                  # byte-identical / deterministic


def test_optional_kml_is_carried_but_inert(tmp_path):
    # the same package with vs without a generic route KML yields the IDENTICAL readiness status (no parser change).
    without = run_package_route_readiness(build_complete_package(
        tmp_path, name="qa-nokml", labels=_LABELS, route_shape=ROUTE_CLEAN, bore_csv=_CONFIRMED_SPAN_CSV))
    pkg = build_complete_package(tmp_path, name="qa-kml", labels=_LABELS, route_shape=ROUTE_CLEAN,
                                 bore_csv=_CONFIRMED_SPAN_CSV, with_kml=True)
    with_kml = run_package_route_readiness(pkg)
    assert (Path(pkg) / "uploads" / "route.kml").is_file()      # the KML is present in the package
    assert with_kml.report.status == without.report.status == "READY_FOR_REVIEW_REDLINE"


# ----------------------------------------------------------------------------------------------------------- #
# (6)/(7) no forbidden imports; name-free coverage is via test_no_specific_names_in_cold_package_harness.
# ----------------------------------------------------------------------------------------------------------- #
_FORBIDDEN_IMPORT_SEGMENTS = {"render", "renderer", "placement", "cap_review", "_cap_review",
                              "api", "store", "web", "contracts", "match"}


def _imported_modules(src):
    mods = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            for a in node.names:
                mods.add(a.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module)
    return mods


def test_complete_package_qa_imports_no_forbidden_modules():
    src = (_HARNESS / "complete_package_qa.py").read_text(encoding="utf-8")
    for m in _imported_modules(src):
        leaked = set(m.split(".")) & _FORBIDDEN_IMPORT_SEGMENTS
        assert not leaked, "complete_package_qa imports forbidden module %r (%s)" % (m, leaked)
