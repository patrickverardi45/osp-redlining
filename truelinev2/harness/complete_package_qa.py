"""GENERIC COMPLETE-PACKAGE QA HARNESS — product QA for the complete-package workflow (read-only, name-free).

This is **product QA, NOT cold validation.** It builds a permanent, generic, name-free SYNTHETIC "complete package"
— shaped like the kind of complete package a real operator will eventually upload — and runs it through the SAME
read-only FieldRoute readiness spine the product uses, end to end:

    uploaded / source package
      → source-span extractor      (``span_extractor.extract_spans_from_folder``)   finds span rows
      → endpoint binder            (``endpoint_binding.bind_extraction_endpoints``)  binds start/end stations
      → route verifier             (``route_verification.verify_extraction_routes``) verifies / refuses the run
      → readiness adapter          (``readiness_adapter.run_readiness_with_spans``)  reports the readiness status

It composes the real modules VERBATIM via ``route_verification.run_package_route_readiness`` — it does NOT
re-implement or hard-code any final status; every status is COMPUTED by the observers. It draws nothing, strokes
nothing, places nothing, promotes no AUTO, verifies no ``_cap_review``, and invents no station / bore row /
endpoint / coordinate / route geometry / source relationship. The synthetic plan / bore-log fixtures are built in a
caller-supplied directory (a temp dir in tests) and are never committed. It imports nothing from render / placement
/ api / store / contracts / match / web / product runtime; fitz + the plan reader are lazy-imported.

Modular seams:
  1. generic package FIXTURE BUILDER          — ``build_complete_package`` (+ ``build_plan_pdf`` / bore-log / KML)
  2. expected source/span + readiness MANIFEST — ``QAScenario`` + ``SCENARIOS`` (the expected outputs per scenario)
  3. readiness pipeline RUNNER                 — ``run_qa_scenario`` (drives the real spine)
  4. scenario ASSERTIONS                       — ``check_scenario`` (actual vs expected, structured mismatches)
  5. documentation                             — ``truelinev2/docs/COMPLETE_PACKAGE_QA_HARNESS.md``

There is NO fake depth / BOC: the readiness spine models neither, so the UI summary carries only the span rows'
own fields (start/end structure appear ONLY when the synthetic source table itself provides them).
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from truelinev2.harness.route_verification import PackageRouteReadiness, run_package_route_readiness

# --- route linework shapes for the synthetic plan ------------------------------------------------------- #
ROUTE_CLEAN = "clean"          # one segment terminus-to-terminus at the two labels -> a unique run
ROUTE_PASSING = "passing"      # a line that passes near but ENDS far from the labels -> no route terminus anchor
ROUTE_FORKED = "forked"        # a long lateral off a midpoint junction -> ambiguous run
ROUTE_BROKEN = "broken"        # two colinear stubs with a wide central gap -> no single run
ROUTE_NONE = "none"            # labels only, no route linework
# Fix-wave-2 G8/W-E (additive; existing shapes above UNCHANGED): a genuinely NON-COLLINEAR, >= 3-segment,
# >= 2-real-bend zigzag terminus-to-terminus (unlike ROUTE_CLEAN's single straight segment) -- still one
# contiguous, unbranched, ungapped run between the two anchors, so it isolates/discriminates through the
# SAME UNMODIFIED observer chain exactly like ROUTE_CLEAN, but its observer-exposed ``route_geometry`` carries
# real interior bend vertices a source-route-adoption proposal can preserve (proving a genuine multi-segment
# backbone reaches READY_FOR_REVIEW_REDLINE, never a test-local synthetic geometry patch).
ROUTE_BENT = "bent"

_PLAN_KIND = "PLAN_PDF"
_BORELOG_KIND = "BORE_LOG"
_GIS_KIND = "GIS_ROUTE"


# ======================================================================================================== #
# Seam 1 — generic package fixture builder (name-free; deterministic; built in a caller-supplied dir).
# ======================================================================================================== #
def _word_centers(pdf_path: str) -> Dict[str, Tuple[float, float]]:
    from truelinev2.ingest.pdf import PlanPdf
    plan = PlanPdf(str(pdf_path))
    try:
        words = plan.words(1, 0)
    finally:
        plan.close()
    return {w["text"]: (float(w["xc"]), float(w["yc"])) for w in words}


def build_plan_pdf(plan_path, labels: List[Tuple[str, float, float]], *, route_shape: str = ROUTE_CLEAN) -> str:
    """Build a generic single-page plan PDF: the station labels via insert_text, and route linework of
    ``route_shape`` whose endpoints sit exactly on the label word-centres (read from a probe so font metrics are
    never guessed). Deterministic; draws only black linework; invents no station. Returns the path."""
    import fitz

    plan_path = Path(plan_path)
    probe = plan_path.with_suffix(".probe.pdf")

    def _emit(target, draw: bool):
        doc = fitz.open()
        page = doc.new_page(width=300, height=200)
        for text, x, y in labels:
            page.insert_text((x, y), text, fontsize=8)
        if draw:
            centers = _word_centers(str(probe))
            pts = [centers[t] for t, _, _ in labels if t in centers]
            if len(pts) >= 2 and route_shape != ROUTE_NONE:
                (ax, ay), (bx, by) = pts[0], pts[1]
                a, b = fitz.Point(ax, ay), fitz.Point(bx, by)
                if route_shape == ROUTE_CLEAN:
                    page.draw_line(a, b, color=(0, 0, 0), width=1)
                elif route_shape == ROUTE_PASSING:
                    page.draw_line(fitz.Point(ax - 90, ay + 15), fitz.Point(bx + 90, by + 15),
                                   color=(0, 0, 0), width=1)                       # passes 15pt below, no terminus
                elif route_shape == ROUTE_FORKED:
                    jx, jy = (ax + bx) / 2.0, (ay + by) / 2.0
                    page.draw_line(a, fitz.Point(jx, jy), color=(0, 0, 0), width=1)
                    page.draw_line(fitz.Point(jx, jy), b, color=(0, 0, 0), width=1)
                    page.draw_line(fitz.Point(jx, jy), fitz.Point(jx, jy + 70.0), color=(0, 0, 0), width=1)
                elif route_shape == ROUTE_BROKEN:
                    L = math.hypot(bx - ax, by - ay) or 1.0
                    ux, uy = (bx - ax) / L, (by - ay) / L
                    stub = 40.0
                    page.draw_line(a, fitz.Point(ax + ux * stub, ay + uy * stub), color=(0, 0, 0), width=1)
                    page.draw_line(fitz.Point(bx - ux * stub, by - uy * stub), b, color=(0, 0, 0), width=1)
                elif route_shape == ROUTE_BENT:
                    # a genuine multi-bend run: THREE contiguous segments (no gap, no branch) -- one unique
                    # isolatable/discriminable run, exactly like ROUTE_CLEAN, but with two real preserved
                    # interior bends. The FIRST leg stays exactly COLLINEAR with the straight a-b line (same y
                    # as the start label) so its own bounding box never satisfies the anchor resolver's
                    # unrelated "drawn label-frame" floor (extract/leader_symbol_trace.py._BOX_MIN_H) the way
                    # a segment leaving the label at an angle would -- an anchor-resolution quirk of a from-the-
                    # label-outward angled first leg, NOT a route-isolation concern, and not a fence file this
                    # ticket may touch. The two REAL bends live at the two interior vertices (j1 -> down-and-
                    # across to j2 -> back up into b), non-collinear with the base line and with each other.
                    j1x, j1y = ax + (bx - ax) / 3.0, ay
                    j2x, j2y = ax + 2.0 * (bx - ax) / 3.0, ay + 30.0
                    j1, j2 = fitz.Point(j1x, j1y), fitz.Point(j2x, j2y)
                    page.draw_line(a, j1, color=(0, 0, 0), width=1)
                    page.draw_line(j1, j2, color=(0, 0, 0), width=1)
                    page.draw_line(j2, b, color=(0, 0, 0), width=1)
        doc.save(str(target))
        doc.close()

    _emit(probe, draw=False)                              # probe: labels only, to read real word-centres
    _emit(plan_path, draw=(route_shape != ROUTE_NONE))
    try:
        os.remove(probe)
    except OSError:
        pass
    return str(plan_path)


_GENERIC_KML = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>route</name><Placemark>'
    '<LineString><coordinates>-97.000,31.000,0 -97.001,31.001,0</coordinates></LineString>'
    '</Placemark></Document></kml>\n'
)


def build_complete_package(package_dir, *, name: str, labels: Optional[List[Tuple[str, float, float]]] = None,
                           route_shape: str = ROUTE_CLEAN, bore_csv: Optional[str] = None,
                           with_kml: bool = False, provenance_class: str = "SYNTHETIC") -> str:
    """Assemble a generic COMPLETE package folder under ``package_dir``: an optional plan PDF (labels + route
    linework), an optional bore-log CSV (a span source), an optional inert generic route KML, and a name-free
    ``package.json`` manifest. ``name`` is runtime data (folder id), never a hardcoded person/place. Read-only wrt
    the product; writes only into the given dir. Returns the package folder path.

    The KML is a documented OPTIONAL context file: it is a ``GIS_ROUTE`` upload with a ``.kml`` extension, so the
    read-only readiness spine (span discovery / package discovery) provably IGNORES it — no parser / render change.
    """
    d = Path(package_dir) / name
    (d / "uploads").mkdir(parents=True, exist_ok=True)
    uploads: List[Dict[str, str]] = []
    if labels is not None:
        build_plan_pdf(d / "uploads" / "plan.pdf", labels, route_shape=route_shape)
        uploads.append({"kind": _PLAN_KIND, "filename": "plan.pdf"})
    if bore_csv is not None:
        (d / "uploads" / "bore-log.csv").write_text(bore_csv, encoding="utf-8")
        uploads.append({"kind": _BORELOG_KIND, "filename": "bore-log.csv"})
    if with_kml:
        (d / "uploads" / "route.kml").write_text(_GENERIC_KML, encoding="utf-8")
        uploads.append({"kind": _GIS_KIND, "filename": "route.kml"})
    (d / "package.json").write_text(json.dumps({
        "package_id": name, "provenance_class": provenance_class, "uploads": uploads, "bores": []}),
        encoding="utf-8")
    return str(d)


# ======================================================================================================== #
# Seam 2 — the expected source/span + readiness manifest (per scenario; the "expected outputs").
# ======================================================================================================== #
@dataclass(frozen=True)
class QAScenario:
    """One complete-package QA scenario = a build spec + the EXPECTED readiness outputs. Optional expected fields
    are only checked when set (not None)."""
    key: str
    description: str
    labels: Optional[List[Tuple[str, float, float]]]
    route_shape: str
    bore_csv: Optional[str]
    expected_status: str
    expected_stage: str
    expected_ready: bool
    with_kml: bool = False
    expected_span_confirmed: Optional[bool] = None
    expected_any_bound: Optional[bool] = None
    expected_any_route_ready: Optional[bool] = None


# Generic name-free station labels + a source-confirmed span (start,end columns) tying two stations as one bore.
_LABELS = [("11+75", 60, 100), ("13+25", 180, 100)]
_MISMATCHED_LABELS = [("40+00", 60, 100), ("50+00", 180, 100)]
_CONFIRMED_SPAN_CSV = "start,end\n11+75,13+25\n"
_STANDALONE_STATIONS_CSV = "station\n10+00\n20+00\n30+00\n"      # a bare ruler: stations, but none tied as a bore

SCENARIOS: Tuple[QAScenario, ...] = (
    QAScenario(
        key="complete_ready",
        description="Complete package: one source-confirmed span, bound anchors, unique drawn route.",
        labels=_LABELS, route_shape=ROUTE_CLEAN, bore_csv=_CONFIRMED_SPAN_CSV,
        expected_status="READY_FOR_REVIEW_REDLINE", expected_stage="READY", expected_ready=True,
        expected_span_confirmed=True, expected_any_bound=True, expected_any_route_ready=True),
    QAScenario(
        key="plan_only",
        description="Plan only — no bore-log / span source file present.",
        labels=_LABELS, route_shape=ROUTE_CLEAN, bore_csv=None,
        expected_status="MISSING_BORE_SPAN_SOURCE", expected_stage="SPAN_SOURCE", expected_ready=False,
        expected_span_confirmed=False),
    QAScenario(
        key="source_no_confirmed_span",
        description="A span-source FILE is present but its table has only a station column — standalone stations, "
                    "no start/end columns, no bore tie (extractor refusal NO_TABLE_SPAN_COLUMNS).",
        labels=_LABELS, route_shape=ROUTE_CLEAN, bore_csv=_STANDALONE_STATIONS_CSV,
        expected_status="NO_SOURCE_CONFIRMED_SPAN", expected_stage="SPAN_SOURCE", expected_ready=False,
        expected_span_confirmed=False),
    QAScenario(
        key="span_labels_missing",
        description="Source span confirmed, but the plan's station labels do not match the span's stations.",
        labels=_MISMATCHED_LABELS, route_shape=ROUTE_CLEAN, bore_csv=_CONFIRMED_SPAN_CSV,
        expected_status="ANCHOR_BLOCKED", expected_stage="ANCHOR", expected_ready=False,
        expected_span_confirmed=True, expected_any_bound=False),
    QAScenario(
        key="span_anchors_off_route",
        description="Source span + labels present, but the route linework has no terminus at the labels (off-route).",
        labels=_LABELS, route_shape=ROUTE_PASSING, bore_csv=_CONFIRMED_SPAN_CSV,
        expected_status="ANCHOR_BLOCKED", expected_stage="ANCHOR", expected_ready=False,
        expected_span_confirmed=True, expected_any_bound=False),
    QAScenario(
        key="span_anchors_route_blocked",
        description="Source span + bound anchors, but the drawn route between them is forked / not unique.",
        labels=_LABELS, route_shape=ROUTE_FORKED, bore_csv=_CONFIRMED_SPAN_CSV,
        expected_status="ROUTE_BLOCKED", expected_stage="ROUTE", expected_ready=False,
        expected_span_confirmed=True, expected_any_bound=True, expected_any_route_ready=False),
    QAScenario(
        key="span_anchors_route_broken",
        description="Source span + bound anchors, but the drawn route is BROKEN (a wide central gap) — no single "
                    "run bridges the anchors (a structurally distinct ROUTE_BLOCKED from the forked case).",
        labels=_LABELS, route_shape=ROUTE_BROKEN, bore_csv=_CONFIRMED_SPAN_CSV,
        expected_status="ROUTE_BLOCKED", expected_stage="ROUTE", expected_ready=False,
        expected_span_confirmed=True, expected_any_bound=True, expected_any_route_ready=False),
    # Fix-wave-2 G8/W-E (ADDITIVE — every scenario above is UNCHANGED): the SAME complete-ready shape as
    # "complete_ready" (identical labels/span/footage), except the drawn route is a genuine non-collinear
    # >= 3-segment zigzag (ROUTE_BENT) instead of one straight segment — proves a real multi-bend backbone
    # reaches READY_FOR_REVIEW_REDLINE through the UNMODIFIED spine (source-route-adoption's success-path
    # tests bind to THIS scenario, never a test-local synthetic geometry patch).
    QAScenario(
        key="bent_ready",
        description="Complete package: one source-confirmed span, bound anchors, unique drawn route with a "
                    "genuine multi-segment BEND (non-collinear backbone) between the two anchors.",
        labels=_LABELS, route_shape=ROUTE_BENT, bore_csv=_CONFIRMED_SPAN_CSV,
        expected_status="READY_FOR_REVIEW_REDLINE", expected_stage="READY", expected_ready=True,
        expected_span_confirmed=True, expected_any_bound=True, expected_any_route_ready=True),
)


# ======================================================================================================== #
# Seam 3 — the readiness pipeline runner (drives the REAL spine; computes nothing itself).
# ======================================================================================================== #
@dataclass(frozen=True)
class QAResult:
    """The outcome of running one scenario's package through the real readiness spine, plus a UI-facing summary."""
    scenario_key: str
    package_dir: str
    readiness: Optional[PackageRouteReadiness]

    def ui_summary(self) -> dict:
        """The read-only metadata a later clickable-dots / detail-drawer UI needs: extracted span rows (station
        start/end + source citation/file), per-span anchor + route verification summaries, and the readiness
        status. No depth / BOC is fabricated — the spine models neither; start/end structure appear only when the
        source table provided them."""
        pr = self.readiness
        if pr is None:
            return {"scenario": self.scenario_key, "resolved": False,
                    "note": "no package manifest / source resolved"}
        spans = [{"span_id": s.span_id, "start_station": s.start_station, "end_station": s.end_station,
                  "footage": s.footage, "start_structure": s.start_structure, "end_structure": s.end_structure,
                  "source_file": s.source_file, "source_page": s.source_page, "source_kind": s.source_kind,
                  "confidence": s.confidence, "citation": s.citation} for s in pr.extraction.spans]
        bindings = [{"span_id": b.span_id, "start_station": b.start_station, "end_station": b.end_station,
                     "bound": b.bound, "refusal": b.refusal,
                     "start_anchor": {"status": b.start_anchor_status, "method": b.start_anchor_method,
                                      "xy": (list(b.start_anchor_xy) if b.start_anchor_xy else None)},
                     "end_anchor": {"status": b.end_anchor_status, "method": b.end_anchor_method,
                                    "xy": (list(b.end_anchor_xy) if b.end_anchor_xy else None)}}
                    for b in pr.bindings.bindings]
        routes = [{"span_id": v.span_id, "route_ready": v.route_ready, "evaluated": v.evaluated,
                   "refusal": v.refusal, "route_observer_status": v.route_observer_status,
                   "route_isolation_status": v.route_isolation_status, "route_run_status": v.route_run_status,
                   "main_run_status": v.main_run_status, "gap_bridge_status": v.gap_bridge_status}
                  for v in pr.routes.verifications]
        return {
            "scenario": self.scenario_key,
            "resolved": True,
            "readiness_status": pr.report.status,
            "stage": pr.report.stage,
            "ready": pr.report.ready,
            "recommended_next_input": pr.report.recommended_next_input,
            "draws_anything": pr.report.draws_anything,
            "performs_placement": pr.report.performs_placement,
            "span_rows": spans,
            "anchor_bindings": bindings,
            "route_verifications": routes,
        }


def run_qa_scenario(package_dir, scenario: QAScenario) -> QAResult:
    """Build the scenario's complete package and run it through the REAL readiness spine
    (``run_package_route_readiness``). Read-only; draws nothing; hard-codes no status."""
    pkg = build_complete_package(package_dir, name="qa-%s" % scenario.key, labels=scenario.labels,
                                 route_shape=scenario.route_shape, bore_csv=scenario.bore_csv,
                                 with_kml=scenario.with_kml)
    pr = run_package_route_readiness(pkg)
    return QAResult(scenario_key=scenario.key, package_dir=pkg, readiness=pr)


# ======================================================================================================== #
# Seam 4 — scenario assertions (actual vs expected; structured mismatches, reusable outside pytest).
# ======================================================================================================== #
def check_scenario(result: QAResult, scenario: QAScenario) -> Tuple[bool, List[str]]:
    """Compare a QAResult against a scenario's expected outputs. Returns (ok, mismatches). Only checks the
    optional expected fields that are set."""
    mismatches: List[str] = []
    pr = result.readiness
    if pr is None:
        return False, ["package did not resolve through the readiness spine"]

    def _eq(label: str, actual: Any, expected: Any) -> None:
        if actual != expected:
            mismatches.append("%s: expected %r, got %r" % (label, expected, actual))

    _eq("status", pr.report.status, scenario.expected_status)
    _eq("stage", pr.report.stage, scenario.expected_stage)
    _eq("ready", pr.report.ready, scenario.expected_ready)
    _eq("draws_anything", pr.report.draws_anything, False)
    _eq("performs_placement", pr.report.performs_placement, False)
    if scenario.expected_span_confirmed is not None:
        _eq("span_confirmed", pr.extraction.has_source_confirmed_span, scenario.expected_span_confirmed)
    if scenario.expected_any_bound is not None:
        _eq("any_bound", pr.bindings.any_bound, scenario.expected_any_bound)
    if scenario.expected_any_route_ready is not None:
        _eq("any_route_ready", pr.routes.any_route_ready, scenario.expected_any_route_ready)
    return (not mismatches), mismatches


def run_all_scenarios(root) -> List[Tuple[QAScenario, QAResult, bool, List[str]]]:
    """Run every canonical scenario under ``root`` and check each. Read-only; draws nothing. Returns per-scenario
    (scenario, result, ok, mismatches)."""
    out: List[Tuple[QAScenario, QAResult, bool, List[str]]] = []
    for sc in SCENARIOS:
        res = run_qa_scenario(root, sc)
        ok, mm = check_scenario(res, sc)
        out.append((sc, res, ok, mm))
    return out


# ======================================================================================================== #
# Seam 5 — harness-only diagnostic CLI (writes fixtures into a caller-supplied dir; draws nothing).
# ======================================================================================================== #
def main(argv: Optional[List[str]] = None) -> int:
    """``python -m truelinev2.harness.complete_package_qa <scratch_dir>`` — build + run every scenario under the
    given scratch directory, print each scenario's readiness status + pass/fail + UI summary. Writes only fixtures
    into the scratch dir; draws nothing, places nothing."""
    import sys
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        sys.stderr.write("usage: complete_package_qa <scratch_dir>\n")
        return 2
    root = args[0]
    Path(root).mkdir(parents=True, exist_ok=True)
    all_ok = True
    report = []
    for sc, res, ok, mm in run_all_scenarios(root):
        all_ok = all_ok and ok
        report.append({"scenario": sc.key, "description": sc.description, "ok": ok, "mismatches": mm,
                       "ui_summary": res.ui_summary()})
    print(json.dumps({"all_ok": all_ok, "scenarios": report}, indent=2, sort_keys=True))
    return 0 if all_ok else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
