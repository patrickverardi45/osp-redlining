"""Proof for the read-only SOURCE-BACKED ENDPOINT BINDING MVP (the ANCHOR stage after SPAN_SOURCE_FOUND).

It binds an extracted source-confirmed span row's start/end stations to plan anchors using the existing read-only
G-a (printed-station locator) + G-a' (anchor resolver) machinery verbatim, and feeds the resulting AnchorEvidence
into the readiness adapter. It draws nothing, verifies no route, invents no coordinate.

Synthetic plans are built with fitz: labels via insert_text, and (for positive binds) a route line whose endpoints
sit exactly on the label word-centers — discovered by reading PlanPdf.words on a probe, so the fixture never
guesses font metrics. All fixtures are generic and built in tmp_path (never committed).
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import fitz

from truelinev2.extract.plan_view_anchor_resolver import (
    AMBIGUOUS_ANCHOR,
    ANCHOR_RESOLVED_TO_LEADER_TIP,
    ANCHOR_RESOLVED_TO_ROUTE_ENDPOINT,
    ANCHOR_RESOLVED_TO_SYMBOL,
    LABEL_ONLY_NO_ANCHOR,
    NO_SUPPORTED_ANCHOR,
)
from truelinev2.extract.printed_station_locator import STATION_LABEL_LOCATED as GA_STATION_LABEL_LOCATED
from truelinev2.harness.endpoint_binding import (
    ANCHOR_NOT_RESOLVED,
    ANCHOR_PASS_STATUSES,
    EndpointBindingReport,
    LABEL_NOT_LOCATED,
    NO_PLAN_FOR_BINDING,
    STATION_LABEL_LOCATED,
    anchor_evidence_for_package,
    anchor_resolved,
    bind_span_endpoints,
    label_located,
    run_package_anchor_readiness,
)
from truelinev2.harness.review_readiness import (
    ANCHOR_BLOCKED,
    KEEP_BLOCKED,
    MISSING_BORE_SPAN_SOURCE,
    SPAN_SOURCE_FOUND,
)
from truelinev2.harness.span_extractor import SpanRow
from truelinev2.ingest.pdf import PlanPdf

_HARNESS = Path(__file__).resolve().parents[1] / "harness"


# ----------------------------------------------------------------------------------------------------------- #
# Synthetic plan fixtures (fitz): labels + optional route linework at the real word-centers.
# ----------------------------------------------------------------------------------------------------------- #
def _labels_pdf(path, labels):
    doc = fitz.open()
    page = doc.new_page(width=300, height=200)
    for text, x, y in labels:
        page.insert_text((x, y), text, fontsize=8)
    doc.save(str(path))
    doc.close()


def _word_centers(pdf_path):
    plan = PlanPdf(str(pdf_path))
    words = plan.words(1, 0)
    plan.close()
    return {w["text"]: (float(w["xc"]), float(w["yc"])) for w in words}


def _build_plan(tmp_path, out_path, labels, *, route=None):
    """Build a plan with the labels; if route == 'endpoints' draw a route line terminating at each label's word
    center; if route == 'passing' draw a line that passes near but ends far from the labels."""
    probe = tmp_path / "_probe.pdf"
    _labels_pdf(probe, labels)
    centers = _word_centers(probe)
    doc = fitz.open()
    page = doc.new_page(width=300, height=200)
    for text, x, y in labels:
        page.insert_text((x, y), text, fontsize=8)
    pts = [centers[t] for t, _, _ in labels if t in centers]
    if route in ("endpoints", "passing") and len(pts) >= 2:
        # page.draw_line yields a clean single segment (degree-1 termini); Shape.finish would double the path.
        if route == "endpoints":
            page.draw_line(fitz.Point(*pts[0]), fitz.Point(*pts[1]), color=(0, 0, 0), width=1)   # terminus at each label
        else:
            (ax, ay), (bx, by) = pts[0], pts[1]
            page.draw_line(fitz.Point(ax - 90, ay + 15), fitz.Point(bx + 90, by + 15),
                           color=(0, 0, 0), width=1)                     # passes 15pt below, no terminus near
    doc.save(str(out_path))
    doc.close()


def _pkg(tmp_path, name, *, labels=None, route="endpoints", bore_csv=None, findings=None):
    d = tmp_path / name
    (d / "uploads").mkdir(parents=True)
    uploads = []
    if labels is not None:
        _build_plan(tmp_path, d / "uploads" / "plan.pdf", labels, route=route)
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


def _row(start, end, span_id="span-001"):
    return SpanRow(span_id=span_id, source_file="b.csv", source_page=None, source_kind="CSV_TABLE",
                   start_station=start, end_station=end, footage=None, start_structure=None, end_structure=None,
                   status="SPAN_ROW_CONFIRMED", confidence="HIGH", citation="", bbox=None, detail={})


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
# (1) a span row can request binding for its exact start/end stations.
# ----------------------------------------------------------------------------------------------------------- #
def test_span_row_binds_its_exact_stations(tmp_path):
    out = tmp_path / "plan.pdf"
    _build_plan(tmp_path, out, [("11+75", 60, 100), ("13+25", 180, 100)], route="endpoints")
    b = bind_span_endpoints(str(out), _row("11+75", "13+25"), sheet=1)
    assert b.span_id == "span-001" and b.start_station == "11+75" and b.end_station == "13+25"
    assert b.start_label_status == STATION_LABEL_LOCATED and b.end_label_status == STATION_LABEL_LOCATED
    assert b.start_anchor_status == ANCHOR_RESOLVED_TO_ROUTE_ENDPOINT
    assert b.end_anchor_status == ANCHOR_RESOLVED_TO_ROUTE_ENDPOINT
    assert b.bound is True and b.refusal is None
    assert b.start_anchor_xy is not None and b.end_anchor_xy is not None     # observer-exposed coordinate
    assert b.detail["class_verified"] is False                              # never AUTO-verified


# ----------------------------------------------------------------------------------------------------------- #
# (2) labels + anchors resolve -> anchor-ready (SPAN_SOURCE_FOUND at the ANCHOR stage).
# ----------------------------------------------------------------------------------------------------------- #
def test_labels_and_anchors_resolve_is_anchor_ready(tmp_path):
    d = _pkg(tmp_path, "pkg-anchor-ready", labels=[("11+75", 60, 100), ("13+25", 180, 100)],
             route="endpoints", bore_csv="start,end\n11+75,13+25\n")
    par = run_package_anchor_readiness(str(d))
    assert par.report.status == SPAN_SOURCE_FOUND and par.report.stage == "ANCHOR"   # route pending
    assert par.bindings.any_bound is True
    assert par.report.draws_anything is False and par.report.performs_placement is False


# ----------------------------------------------------------------------------------------------------------- #
# (3) span rows exist but labels missing -> ANCHOR_BLOCKED (not route-ready).
# ----------------------------------------------------------------------------------------------------------- #
def test_labels_missing_is_anchor_blocked(tmp_path):
    # the plan carries DIFFERENT station labels, so the bore span's stations do not locate
    d = _pkg(tmp_path, "pkg-nolabels", labels=[("40+00", 60, 100), ("50+00", 180, 100)],
             route="endpoints", bore_csv="start,end\n11+75,13+25\n")
    par = run_package_anchor_readiness(str(d))
    assert par.report.status == ANCHOR_BLOCKED
    assert par.bindings.bindings[0].refusal == LABEL_NOT_LOCATED
    assert par.report.draws_anything is False


# ----------------------------------------------------------------------------------------------------------- #
# (4) labels present but anchors off-route/ambiguous -> ANCHOR_BLOCKED.
# ----------------------------------------------------------------------------------------------------------- #
def test_labels_present_but_anchors_off_route_is_anchor_blocked(tmp_path):
    d = _pkg(tmp_path, "pkg-offroute", labels=[("11+75", 60, 100), ("13+25", 180, 100)],
             route="passing", bore_csv="start,end\n11+75,13+25\n")
    par = run_package_anchor_readiness(str(d))
    assert par.report.status == ANCHOR_BLOCKED
    b = par.bindings.bindings[0]
    assert b.start_label_status == STATION_LABEL_LOCATED                     # labels DO locate
    assert not anchor_resolved(b.start_anchor_status)                       # but the anchor does not resolve
    assert b.refusal == ANCHOR_NOT_RESOLVED


# ----------------------------------------------------------------------------------------------------------- #
# (5) public-cold-009 with vs without an added source span.
# ----------------------------------------------------------------------------------------------------------- #
def test_009_without_source_file_stays_missing(tmp_path):
    d = _pkg(tmp_path, "public-cold-009", findings=_FINDINGS_009)           # recorded, no plan, no bore log
    par = run_package_anchor_readiness(str(d))
    assert par.report.status == MISSING_BORE_SPAN_SOURCE


def test_009_with_added_source_span_reaches_anchor_stage(tmp_path):
    d = _pkg(tmp_path, "public-cold-009", labels=[("7+62", 60, 100), ("8+00", 180, 100)],
             route="endpoints", bore_csv="start,end\n7+62,8+00\n", findings=_FINDINGS_009)
    par = run_package_anchor_readiness(str(d))
    assert par.report.status == SPAN_SOURCE_FOUND and par.report.stage == "ANCHOR"   # anchors resolve
    assert par.bindings.any_bound is True


# ----------------------------------------------------------------------------------------------------------- #
# (6) public-cold-011 remains blocked and never becomes draw-ready.
# ----------------------------------------------------------------------------------------------------------- #
def test_011_remains_keep_blocked_not_draw_ready(tmp_path):
    d = _pkg(tmp_path, "public-cold-011", labels=[("11+75", 60, 100), ("13+25", 180, 100)],
             route="endpoints", bore_csv="start,end\n11+75,13+25\n", findings=_FINDINGS_011)
    par = run_package_anchor_readiness(str(d))
    assert par.report.status == KEEP_BLOCKED                                # owner marker short-circuits


# ----------------------------------------------------------------------------------------------------------- #
# no plan -> anchor unevaluated (stays SPAN_SOURCE_FOUND, needs a plan).
# ----------------------------------------------------------------------------------------------------------- #
def test_no_plan_leaves_anchor_unevaluated(tmp_path):
    d = _pkg(tmp_path, "pkg-noplan", bore_csv="start,end\n11+75,13+25\n")   # bore log, no plan
    par = run_package_anchor_readiness(str(d))
    assert par.report.status == SPAN_SOURCE_FOUND
    assert par.bindings.plan_present is False
    assert par.bindings.bindings[0].refusal == NO_PLAN_FOR_BINDING


def test_anchor_evidence_none_when_no_plan_or_no_span():
    assert anchor_evidence_for_package(EndpointBindingReport((), plan_present=False, sheet=1)) is None


# ----------------------------------------------------------------------------------------------------------- #
# (7) no forbidden imports + read-only + serialization + (8) anti-drift.
# ----------------------------------------------------------------------------------------------------------- #
_FORBIDDEN_IMPORT_SEGMENTS = {
    "render", "renderer", "placement", "cap_review", "_cap_review",
    "api", "store", "web", "contracts", "match",
}


def _imported_modules(src):
    mods = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            for a in node.names:
                mods.add(a.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module)
    return mods


def test_endpoint_binding_imports_no_forbidden_modules():
    src = (_HARNESS / "endpoint_binding.py").read_text(encoding="utf-8")
    for m in _imported_modules(src):
        leaked = set(m.split(".")) & _FORBIDDEN_IMPORT_SEGMENTS
        assert not leaked, "endpoint_binding imports forbidden module %r (%s)" % (m, leaked)


def test_binding_is_read_only(tmp_path):
    d = _pkg(tmp_path, "pkg-ro", labels=[("11+75", 60, 100), ("13+25", 180, 100)],
             route="endpoints", bore_csv="start,end\n11+75,13+25\n")
    before = sorted(str(p.relative_to(d)) for p in d.rglob("*"))
    run_package_anchor_readiness(str(d))
    after = sorted(str(p.relative_to(d)) for p in d.rglob("*"))
    assert before == after


def test_package_anchor_readiness_is_json_serializable(tmp_path):
    d = _pkg(tmp_path, "pkg-json", labels=[("11+75", 60, 100), ("13+25", 180, 100)],
             route="endpoints", bore_csv="start,end\n11+75,13+25\n")
    par = run_package_anchor_readiness(str(d))
    text = json.dumps(par.to_dict(), sort_keys=True)
    assert '"bindings"' in text and '"any_bound"' in text and '"report"' in text


def test_pass_status_sets_match_the_real_observers():
    assert STATION_LABEL_LOCATED == GA_STATION_LABEL_LOCATED
    assert ANCHOR_PASS_STATUSES == {
        ANCHOR_RESOLVED_TO_ROUTE_ENDPOINT, ANCHOR_RESOLVED_TO_SYMBOL, ANCHOR_RESOLVED_TO_LEADER_TIP}
    for reject in (AMBIGUOUS_ANCHOR, NO_SUPPORTED_ANCHOR, LABEL_ONLY_NO_ANCHOR):
        assert not anchor_resolved(reject)
    assert label_located(GA_STATION_LABEL_LOCATED) and not label_located("NO_PRINTED_STATION_LABEL")
