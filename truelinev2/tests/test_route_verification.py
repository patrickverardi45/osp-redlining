"""Proof for the read-only SOURCE-BACKED ROUTE VERIFICATION MVP (the ROUTE stage after anchor-ready).

It verifies whether a UNIQUE drawn route connects a span's two BOUND anchors, using the existing read-only route
observers verbatim (G-b' isolate -> G-b'''' bridge -> G-b''' discriminate) fed the source-backed bound-anchor
coordinate. It draws nothing, strokes nothing, places nothing, promotes no AUTO, and invents no coordinate.

Synthetic plans are built with fitz: labels via insert_text, and route linework whose endpoints sit exactly on the
label word-centers (discovered by reading PlanPdf.words on a probe, so the fixture never guesses font metrics).
Route shapes: 'clean' (one segment terminus-to-terminus -> a unique run), 'forked' (a long lateral off a midpoint
junction -> ambiguous), 'broken' (two colinear stubs with a wide central gap -> no single run). All fixtures are
generic and built in tmp_path (never committed).
"""
from __future__ import annotations

import ast
import json
import math
from pathlib import Path

import fitz

from truelinev2.extract.plan_view_route_isolator import ROUTE_LINEWORK_ISOLATED as GBPRIME_ISOLATED
from truelinev2.extract.plan_view_run_observer import PLAN_VIEW_RUN_CONNECTED as GB_RUN_CONNECTED
from truelinev2.extract.route_main_run import (
    MAIN_ROUTE_DISCRIMINATED as GBTRIPLE_DISCRIMINATED,
    NO_MAIN_ROUTE as GBTRIPLE_NO_MAIN_ROUTE,
)
from truelinev2.harness.endpoint_binding import EndpointBinding, EndpointBindingReport
from truelinev2.harness.review_readiness import (
    ANCHOR_BLOCKED,
    AnchorEvidence,
    KEEP_BLOCKED,
    MISSING_BORE_SPAN_SOURCE,
    READY_FOR_REVIEW_REDLINE,
    ROUTE_BLOCKED,
    ROUTE_PASS_STATUSES as RR_ROUTE_PASS_STATUSES,
    ReviewReadinessEvidence,
    RouteEvidence,
    SpanSourceEvidence,
    classify_review_readiness,
)
from truelinev2.harness.route_verification import (
    ANCHOR_NOT_BOUND,
    MAIN_ROUTE_DISCRIMINATED,
    NO_PLAN_FOR_ROUTE,
    PLAN_VIEW_RUN_CONNECTED,
    ROUTE_LINEWORK_ISOLATED,
    ROUTE_PASS_STATUSES,
    route_evidence_for_package,
    route_status_verified,
    run_package_route_readiness,
    verify_extraction_routes,
    verify_span_route,
)

_HARNESS = Path(__file__).resolve().parents[1] / "harness"


# ----------------------------------------------------------------------------------------------------------- #
# Synthetic plan fixtures (fitz): labels + route linework of a chosen shape at the real word-centers.
# ----------------------------------------------------------------------------------------------------------- #
def _labels_pdf(path, labels):
    doc = fitz.open()
    page = doc.new_page(width=300, height=200)
    for text, x, y in labels:
        page.insert_text((x, y), text, fontsize=8)
    doc.save(str(path))
    doc.close()


def _word_centers(pdf_path):
    from truelinev2.ingest.pdf import PlanPdf
    plan = PlanPdf(str(pdf_path))
    words = plan.words(1, 0)
    plan.close()
    return {w["text"]: (float(w["xc"]), float(w["yc"])) for w in words}


def _build_route_plan(tmp_path, out_path, labels, *, shape="clean"):
    """Build a plan with the labels and route linework of ``shape``. Returns the {label: (xc, yc)} centers so a
    caller can build a binding whose anchor xy sit exactly on the drawn termini."""
    probe = tmp_path / "_probe.pdf"
    _labels_pdf(probe, labels)
    centers = _word_centers(probe)
    doc = fitz.open()
    page = doc.new_page(width=300, height=200)
    for text, x, y in labels:
        page.insert_text((x, y), text, fontsize=8)
    pts = [centers[t] for t, _, _ in labels if t in centers]
    if len(pts) >= 2 and shape != "none":
        (ax, ay), (bx, by) = pts[0], pts[1]
        a, b = fitz.Point(ax, ay), fitz.Point(bx, by)
        if shape == "clean":
            page.draw_line(a, b, color=(0, 0, 0), width=1)                        # one terminus at each label
        elif shape == "forked":
            jx, jy = (ax + bx) / 2.0, (ay + by) / 2.0                             # junction at the midpoint
            page.draw_line(a, fitz.Point(jx, jy), color=(0, 0, 0), width=1)
            page.draw_line(fitz.Point(jx, jy), b, color=(0, 0, 0), width=1)
            page.draw_line(fitz.Point(jx, jy), fitz.Point(jx, jy + 70.0),
                           color=(0, 0, 0), width=1)                              # a LONG lateral (>= half backbone)
        elif shape == "broken":
            L = math.hypot(bx - ax, by - ay) or 1.0
            ux, uy = (bx - ax) / L, (by - ay) / L
            stub = 40.0                                                           # > leader max (30); wide central gap
            page.draw_line(a, fitz.Point(ax + ux * stub, ay + uy * stub), color=(0, 0, 0), width=1)
            page.draw_line(fitz.Point(bx - ux * stub, by - uy * stub), b, color=(0, 0, 0), width=1)
        elif shape == "offset":
            off = 25.0                                                            # a clean run 25pt OFF the anchors:
            page.draw_line(fitz.Point(ax, ay + off), fitz.Point(bx, by + off),   # > isolation reach_tol (12), <
                           color=(0, 0, 0), width=1)                             # discriminator radius (50)
    doc.save(str(out_path))
    doc.close()
    return centers


def _binding(centers, sa, sb, *, bound=True, span_id="span-001", start_station="11+75", end_station="13+25"):
    """Construct an EndpointBinding directly (decoupled from G-a'): a bound binding carries the observer-exposed
    anchor xy at the two label word-centers; an unbound one carries no coordinate."""
    return EndpointBinding(
        span_id=span_id, start_station=start_station, end_station=end_station,
        start_label_status="STATION_LABEL_LOCATED", end_label_status="STATION_LABEL_LOCATED",
        start_anchor_status=("ANCHOR_RESOLVED_TO_ROUTE_ENDPOINT" if bound else "NO_SUPPORTED_ANCHOR"),
        end_anchor_status=("ANCHOR_RESOLVED_TO_ROUTE_ENDPOINT" if bound else "NO_SUPPORTED_ANCHOR"),
        start_anchor_method=("ROUTE_TERMINUS" if bound else None),
        end_anchor_method=("ROUTE_TERMINUS" if bound else None),
        start_anchor_xy=(centers[sa] if bound else None),
        end_anchor_xy=(centers[sb] if bound else None),
        bound=bound, refusal=(None if bound else "ANCHOR_NOT_RESOLVED"), detail={})


def _report(binding, *, plan_present=True):
    return EndpointBindingReport(bindings=(binding,), plan_present=plan_present, sheet=1)


def _pkg(tmp_path, name, *, labels=None, shape="clean", bore_csv=None, findings=None):
    d = tmp_path / name
    (d / "uploads").mkdir(parents=True)
    uploads = []
    if labels is not None:
        _build_route_plan(tmp_path, d / "uploads" / "plan.pdf", labels, shape=shape)
        uploads.append({"kind": "PLAN_PDF", "filename": "plan.pdf"})
    if bore_csv is not None:
        (d / "uploads" / "bore-log.csv").write_text(bore_csv, encoding="utf-8")
        uploads.append({"kind": "BORE_LOG", "filename": "bore-log.csv"})
    (d / "package.json").write_text(json.dumps({
        "package_id": name, "provenance_class": "FRESH_NONRECOGNIZED", "uploads": uploads, "bores": []}),
        encoding="utf-8")
    if findings is not None:
        (d / "observer_findings.json").write_text(json.dumps(findings), encoding="utf-8")
    return d


_LABELS = [("11+75", 60, 100), ("13+25", 180, 100)]
_FINDINGS_009 = {"recognized": False, "plan_readable": True, "span_source_files": [],
                 "plan_span_layer_inspected": True, "source_confirmed_span_count": 0,
                 "anchor_start_status": "ANCHOR_RESOLVED_TO_SYMBOL",
                 "anchor_end_status": "ANCHOR_RESOLVED_TO_ROUTE_ENDPOINT"}
_FINDINGS_011 = {"recognized": False, "plan_readable": True, "keep_blocked": True,
                 "keep_blocked_reason": "two independent structural blockers",
                 "span_source_files": [], "plan_span_layer_inspected": True, "source_confirmed_span_count": 1,
                 "anchor_start_status": "NO_SUPPORTED_ANCHOR", "anchor_end_status": "NO_SUPPORTED_ANCHOR",
                 "route_status": "NO_MAIN_ROUTE"}


# ----------------------------------------------------------------------------------------------------------- #
# (1) an unbound binding does not run route verification.
# ----------------------------------------------------------------------------------------------------------- #
def test_unbound_binding_does_not_run_route(tmp_path):
    out = tmp_path / "plan.pdf"
    centers = _build_route_plan(tmp_path, out, _LABELS, shape="clean")
    v = verify_span_route(str(out), _binding(centers, "11+75", "13+25", bound=False))
    assert v.route_ready is False and v.evaluated is False
    assert v.refusal == ANCHOR_NOT_BOUND
    assert v.route_observer_status is None and v.route_isolation_status is None and v.main_run_status is None


def test_route_evidence_none_when_no_bound_span(tmp_path):
    """No bound span -> route NOT evaluated -> RouteEvidence None (the ANCHOR-stage verdict stands)."""
    out = tmp_path / "plan.pdf"
    centers = _build_route_plan(tmp_path, out, _LABELS, shape="clean")
    rr = verify_extraction_routes(str(out), _report(_binding(centers, "11+75", "13+25", bound=False)))
    assert rr.any_evaluated is False
    assert route_evidence_for_package(rr) is None


# ----------------------------------------------------------------------------------------------------------- #
# (3) bound anchors + a unique drawn route -> route-ready.
# ----------------------------------------------------------------------------------------------------------- #
def test_clean_route_between_bound_anchors_is_route_ready(tmp_path):
    out = tmp_path / "plan.pdf"
    centers = _build_route_plan(tmp_path, out, _LABELS, shape="clean")
    v = verify_span_route(str(out), _binding(centers, "11+75", "13+25"))
    assert v.route_ready is True and v.evaluated is True and v.refusal is None
    assert v.route_observer_status == MAIN_ROUTE_DISCRIMINATED
    assert v.main_run_status == MAIN_ROUTE_DISCRIMINATED
    assert v.route_isolation_status == ROUTE_LINEWORK_ISOLATED
    assert v.route_run_status == PLAN_VIEW_RUN_CONNECTED
    assert v.detail["class_verified"] is False                             # never AUTO-verified
    assert v.start_anchor_summary["xy"] is not None                        # observer-exposed coordinate carried


def test_route_evidence_verified_and_classifier_ready(tmp_path):
    out = tmp_path / "plan.pdf"
    centers = _build_route_plan(tmp_path, out, _LABELS, shape="clean")
    rr = verify_extraction_routes(str(out), _report(_binding(centers, "11+75", "13+25")))
    ev = route_evidence_for_package(rr)
    assert ev is not None and ev.verified is True and ev.status == MAIN_ROUTE_DISCRIMINATED
    report = classify_review_readiness(ReviewReadinessEvidence(
        package_id="pkg", plan_readable=True, recognized=False,
        span=SpanSourceEvidence(("BORE_LOG",), False, 1),
        anchor=AnchorEvidence("ANCHOR_RESOLVED_TO_ROUTE_ENDPOINT", "ANCHOR_RESOLVED_TO_ROUTE_ENDPOINT"),
        route=ev))
    assert report.status == READY_FOR_REVIEW_REDLINE and report.ready is True
    assert report.draws_anything is False and report.performs_placement is False


# ----------------------------------------------------------------------------------------------------------- #
# (2)/(4) bound anchors but no unique / ambiguous / broken route -> ROUTE_BLOCKED.
# ----------------------------------------------------------------------------------------------------------- #
def test_broken_route_is_not_route_ready(tmp_path):
    out = tmp_path / "plan.pdf"
    centers = _build_route_plan(tmp_path, out, _LABELS, shape="broken")
    v = verify_span_route(str(out), _binding(centers, "11+75", "13+25"))
    assert v.route_ready is False and v.evaluated is True
    assert v.main_run_status == GBTRIPLE_NO_MAIN_ROUTE
    assert not route_status_verified(v.route_observer_status)


def test_forked_route_refuses_safely(tmp_path):
    out = tmp_path / "plan.pdf"
    centers = _build_route_plan(tmp_path, out, _LABELS, shape="forked")
    v = verify_span_route(str(out), _binding(centers, "11+75", "13+25"))
    assert v.route_ready is False and v.evaluated is True and v.refusal is not None
    assert not route_status_verified(v.route_observer_status)


def test_route_evidence_blocked_and_classifier_route_blocked(tmp_path):
    out = tmp_path / "plan.pdf"
    centers = _build_route_plan(tmp_path, out, _LABELS, shape="forked")
    rr = verify_extraction_routes(str(out), _report(_binding(centers, "11+75", "13+25")))
    ev = route_evidence_for_package(rr)
    assert ev is not None and ev.verified is False and ev.independently_blocked is True
    report = classify_review_readiness(ReviewReadinessEvidence(
        package_id="pkg", plan_readable=True, recognized=False,
        span=SpanSourceEvidence(("BORE_LOG",), False, 1),
        anchor=AnchorEvidence("ANCHOR_RESOLVED_TO_ROUTE_ENDPOINT", "ANCHOR_RESOLVED_TO_ROUTE_ENDPOINT"),
        route=ev))
    assert report.status == ROUTE_BLOCKED and report.draws_anything is False


def test_offset_anchor_off_route_is_not_route_ready(tmp_path):
    """ZERO-FALSE regression: a bound anchor sitting 25pt OFF the drawn route (as a leader-tip / symbol anchor can)
    must NOT be route-ready. The isolation gate (reach_tol 12pt) rejects it even though the discriminator alone
    (anchor_radius 50pt) would have accepted it — proving route_ready needs BOTH gates."""
    out = tmp_path / "plan.pdf"
    centers = _build_route_plan(tmp_path, out, _LABELS, shape="offset")
    v = verify_span_route(str(out), _binding(centers, "11+75", "13+25"))         # anchor xy = label centres (on route? no — 25pt above)
    assert v.route_ready is False and v.evaluated is True
    assert v.route_isolation_status != ROUTE_LINEWORK_ISOLATED                   # isolation gate rejects (off-route)
    assert v.main_run_status == MAIN_ROUTE_DISCRIMINATED                         # the discriminator ALONE was fooled
    assert not route_status_verified(v.route_observer_status)


def test_no_plan_leaves_route_unevaluated(tmp_path):
    out = tmp_path / "plan.pdf"
    centers = _build_route_plan(tmp_path, out, _LABELS, shape="clean")
    v = verify_span_route(None, _binding(centers, "11+75", "13+25"))
    assert v.route_ready is False and v.evaluated is False and v.refusal == NO_PLAN_FOR_ROUTE


# ----------------------------------------------------------------------------------------------------------- #
# End-to-end (run_package_route_readiness): the full ladder.
# ----------------------------------------------------------------------------------------------------------- #
def test_e2e_clean_route_is_ready(tmp_path):
    d = _pkg(tmp_path, "pkg-route-ready", labels=_LABELS, shape="clean", bore_csv="start,end\n11+75,13+25\n")
    pr = run_package_route_readiness(str(d))
    assert pr.report.status == READY_FOR_REVIEW_REDLINE and pr.report.ready is True
    assert pr.routes.any_route_ready is True
    assert pr.report.draws_anything is False and pr.report.performs_placement is False


def test_e2e_anchor_blocked_does_not_run_route(tmp_path):
    # bore-span stations do not match the plan labels -> anchors don't bind -> route not evaluated
    d = _pkg(tmp_path, "pkg-anchorblock", labels=[("40+00", 60, 100), ("50+00", 180, 100)],
             shape="clean", bore_csv="start,end\n11+75,13+25\n")
    pr = run_package_route_readiness(str(d))
    assert pr.report.status == ANCHOR_BLOCKED
    assert pr.routes.any_evaluated is False                                # route stage not run for an unbound span


def test_e2e_bound_but_forked_route_is_route_blocked(tmp_path):
    d = _pkg(tmp_path, "pkg-routeblock", labels=_LABELS, shape="forked", bore_csv="start,end\n11+75,13+25\n")
    pr = run_package_route_readiness(str(d))
    assert pr.bindings.any_bound is True                                   # anchors DO bind (fork termini)
    assert pr.report.status == ROUTE_BLOCKED


# ----------------------------------------------------------------------------------------------------------- #
# (5)/(6) public-cold-009 with / without a source span; (7) public-cold-011.
# ----------------------------------------------------------------------------------------------------------- #
def test_009_without_source_file_stays_missing(tmp_path):
    d = _pkg(tmp_path, "public-cold-009", findings=_FINDINGS_009)          # recorded, no plan, no bore log
    pr = run_package_route_readiness(str(d))
    assert pr.report.status == MISSING_BORE_SPAN_SOURCE


def test_009_with_span_and_verified_route_becomes_ready(tmp_path):
    d = _pkg(tmp_path, "public-cold-009", labels=[("7+62", 60, 100), ("8+00", 180, 100)],
             shape="clean", bore_csv="start,end\n7+62,8+00\n", findings=_FINDINGS_009)
    pr = run_package_route_readiness(str(d))
    assert pr.report.status == READY_FOR_REVIEW_REDLINE                    # observers verify the run
    assert pr.routes.any_route_ready is True


def test_009_with_span_but_unverified_route_is_route_blocked(tmp_path):
    d = _pkg(tmp_path, "public-cold-009", labels=[("7+62", 60, 100), ("8+00", 180, 100)],
             shape="forked", bore_csv="start,end\n7+62,8+00\n", findings=_FINDINGS_009)
    pr = run_package_route_readiness(str(d))
    assert pr.bindings.any_bound is True
    assert pr.report.status == ROUTE_BLOCKED                               # anchors bind, but the run is not verified


def test_011_remains_keep_blocked_not_draw_ready(tmp_path):
    d = _pkg(tmp_path, "public-cold-011", labels=_LABELS, shape="clean",
             bore_csv="start,end\n11+75,13+25\n", findings=_FINDINGS_011)
    pr = run_package_route_readiness(str(d))
    assert pr.report.status == KEEP_BLOCKED and pr.report.ready is False   # owner marker short-circuits


# ----------------------------------------------------------------------------------------------------------- #
# (8) no forbidden imports + read-only + serialization; (9) anti-drift pass-set lock.
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


def test_route_verification_imports_no_forbidden_modules():
    src = (_HARNESS / "route_verification.py").read_text(encoding="utf-8")
    for m in _imported_modules(src):
        leaked = set(m.split(".")) & _FORBIDDEN_IMPORT_SEGMENTS
        assert not leaked, "route_verification imports forbidden module %r (%s)" % (m, leaked)


def test_route_verification_is_read_only(tmp_path):
    d = _pkg(tmp_path, "pkg-ro", labels=_LABELS, shape="clean", bore_csv="start,end\n11+75,13+25\n")
    before = sorted(str(p.relative_to(d)) for p in d.rglob("*"))
    run_package_route_readiness(str(d))
    after = sorted(str(p.relative_to(d)) for p in d.rglob("*"))
    assert before == after


def test_package_route_readiness_is_json_serializable(tmp_path):
    d = _pkg(tmp_path, "pkg-json", labels=_LABELS, shape="clean", bore_csv="start,end\n11+75,13+25\n")
    pr = run_package_route_readiness(str(d))
    text = json.dumps(pr.to_dict(), sort_keys=True)
    assert '"routes"' in text and '"verifications"' in text and '"report"' in text and '"bindings"' in text


def test_route_pass_statuses_match_the_real_observers():
    assert MAIN_ROUTE_DISCRIMINATED == GBTRIPLE_DISCRIMINATED
    assert PLAN_VIEW_RUN_CONNECTED == GB_RUN_CONNECTED
    assert ROUTE_LINEWORK_ISOLATED == GBPRIME_ISOLATED
    assert ROUTE_PASS_STATUSES == RR_ROUTE_PASS_STATUSES                   # test-locked to the classifier's pass set
    assert route_status_verified(MAIN_ROUTE_DISCRIMINATED)
    assert not route_status_verified(GBTRIPLE_NO_MAIN_ROUTE)
    assert not route_status_verified(ROUTE_LINEWORK_ISOLATED)              # isolation alone is NOT route-ready
