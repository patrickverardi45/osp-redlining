"""SOURCE-BACKED ROUTE VERIFICATION — the ROUTE stage after anchor-ready (read-only, name-free, harness-only).

Takes the source-backed, BOUND start/end anchors produced by the ANCHOR stage
(``endpoint_binding.EndpointBinding``) and asks one read-only question per span: does a UNIQUE drawn route/run
connect the two bound anchors? It answers with the EXISTING read-only Track B route observers verbatim, composed
in the established order ``isolate -> bridge -> discriminate``:

  * G-b'  ``plan_view_route_isolator.observe_route_isolation``   -> isolate route-like linework from grid/border/
           annotation between the two anchors (its internal G-b run status is carried through as the run status).
  * G-b'''' ``route_gap_bridge.bridge_route_gaps``               -> reconnect colinear route fragments across small
           dash gaps in the isolated linework (a continuity HYPOTHESIS between real drawn endpoints, never a stroke).
  * G-b''' ``route_main_run.discriminate_main_run``              -> separate the MAIN run from short laterals and
           confirm one unique backbone whose ENDS are the two anchors.

The route is considered VERIFIED only when BOTH the tight isolation gate G-b′ (``ROUTE_LINEWORK_ISOLATED`` —
reach_tol 12pt, so the bound anchors are the ENDS of a unique simple isolated run) AND the discriminator G-b‴
(``MAIN_ROUTE_DISCRIMINATED``) pass. Requiring isolation closes a radius asymmetry: G-b‴ alone (anchor_radius 50pt)
would accept a bound anchor sitting 13-49pt OFF the drawn route (as leader-tip / symbol anchors do) that isolation
rejects. ``MAIN_ROUTE_DISCRIMINATED`` is the sole verdict the readiness classifier accepts as a clean run
(``review_readiness.ROUTE_PASS_STATUSES``); every other observer outcome is an honest, NAMED refusal
(``ROUTE_BLOCKED`` downstream). It feeds the bound anchor
coordinate straight through (never invents a station / endpoint / coordinate / route geometry), draws nothing,
places nothing, verifies no ``_cap_review``, and promotes no AUTO. ``class_verified`` on every observer stays
False, so a verified run is REVIEW evidence — NOT a placement, a drawn redline, or the G-e REVIEW stroke (a
separate, later, owner-approved gate).

Route verification ONLY. Its output feeds the ``ReviewReadinessEvidence.route`` seam so a package can move from
``SPAN_SOURCE_FOUND`` at the ANCHOR stage to either route-ready (``READY_FOR_REVIEW_REDLINE``) or ``ROUTE_BLOCKED``;
with no bound anchor it leaves the route unevaluated (the ANCHOR stage already reports ``ANCHOR_BLOCKED``). It
imports nothing from render / placement / api / store / contracts / match / web / product runtime; the fitz-backed
plan reader + route observers are lazy-imported.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from truelinev2.harness.endpoint_binding import EndpointBinding, EndpointBindingReport
from truelinev2.harness.review_readiness import ReviewReadinessReport, RouteEvidence
from truelinev2.harness.span_extractor import SpanExtraction

# --- known route verdicts of the read-only observers (test-locked against the real constants) ----------- #
MAIN_ROUTE_DISCRIMINATED = "MAIN_ROUTE_DISCRIMINATED"    # route_main_run (G-b''') — the only route-ready verdict
PLAN_VIEW_RUN_CONNECTED = "PLAN_VIEW_RUN_CONNECTED"      # plan_view_run_observer (G-b) — a clean run (classifier PASS)
ROUTE_LINEWORK_ISOLATED = "ROUTE_LINEWORK_ISOLATED"      # plan_view_route_isolator (G-b') — clean isolation (enrichment)
# the route statuses the readiness classifier accepts as a verified run (== review_readiness.ROUTE_PASS_STATUSES):
ROUTE_PASS_STATUSES = frozenset({MAIN_ROUTE_DISCRIMINATED, PLAN_VIEW_RUN_CONNECTED})

# --- route-verification refusals (this stage's own reasons, distinct from the observers' reject statuses) - #
ANCHOR_NOT_BOUND = "ANCHOR_NOT_BOUND"          # the span's endpoints are not bound -> the route stage is not run
NO_PLAN_FOR_ROUTE = "NO_PLAN_FOR_ROUTE"        # bound, but no plan / no anchor coordinate to verify against
UNREADABLE_PLAN_ROUTE = "UNREADABLE_PLAN_ROUTE"  # opening / reading the plan (or an observer) raised


def route_status_verified(status: Optional[str]) -> bool:
    """True iff a canonical route status is a clean verified run (mirrors review_readiness.route_verified)."""
    return status in ROUTE_PASS_STATUSES


# ======================================================================================================== #
# Seam 3 — the route-verification contract.
# ======================================================================================================== #
@dataclass(frozen=True)
class RouteVerification:
    """Per-span read-only route-verification result over the BOUND start/end anchors.

    ``route_observer_status`` is the canonical verdict fed to the classifier (``MAIN_ROUTE_DISCRIMINATED`` when
    ready; otherwise the failing gate's status — the isolation reject, else the discriminator reject);
    ``route_isolation_status`` / ``route_run_status`` / ``main_run_status`` / ``gap_bridge_status`` are the
    per-observer breakdown (``None`` when that observer did not run). ``route_ready`` is True ONLY when BOTH the
    isolation gate (``ROUTE_LINEWORK_ISOLATED``) AND the discriminator (``MAIN_ROUTE_DISCRIMINATED``) pass.
    ``evaluated`` is True only when the route observers were
    actually RUN (bound anchors + a readable plan) — never merely 'not reached'. Nothing here is a stroke; the
    anchor summaries carry the observer-exposed coordinate, never an invented one."""
    span_id: str
    start_station: str
    end_station: str
    start_anchor_summary: Optional[Dict[str, Any]]
    end_anchor_summary: Optional[Dict[str, Any]]
    route_observer_status: Optional[str]
    route_isolation_status: Optional[str]
    route_run_status: Optional[str]
    main_run_status: Optional[str]
    gap_bridge_status: Optional[str]
    route_ready: bool
    evaluated: bool
    refusal: Optional[str]
    detail: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = dict(self.__dict__)
        d["start_anchor_summary"] = dict(self.start_anchor_summary) if self.start_anchor_summary else None
        d["end_anchor_summary"] = dict(self.end_anchor_summary) if self.end_anchor_summary else None
        d["detail"] = dict(self.detail)
        return d


@dataclass(frozen=True)
class RouteVerificationReport:
    verifications: Tuple[RouteVerification, ...]
    plan_present: bool
    sheet: int
    detail: Dict[str, Any] = field(default_factory=dict)

    @property
    def any_route_ready(self) -> bool:
        return any(v.route_ready for v in self.verifications)

    @property
    def any_evaluated(self) -> bool:
        return any(v.evaluated for v in self.verifications)

    def to_dict(self) -> dict:
        return {"verifications": [v.to_dict() for v in self.verifications], "plan_present": self.plan_present,
                "sheet": self.sheet, "any_route_ready": self.any_route_ready,
                "any_evaluated": self.any_evaluated, "detail": dict(self.detail)}


def _anchor_summary(status: Optional[str], method: Optional[str],
                    xy: Optional[Tuple[float, float]]) -> Optional[Dict[str, Any]]:
    """A compact, coordinate-carrying summary of one bound anchor (the observer-exposed xy, never invented)."""
    if status is None and method is None and xy is None:
        return None
    return {"status": status, "method": method, "xy": (list(xy) if xy is not None else None)}


# ======================================================================================================== #
# Seams 1-2 — bound-span selection + route-observer invocation / normalization.
# ======================================================================================================== #
def _verify_bound(binding: EndpointBinding, line_items, words, page_bounds) -> RouteVerification:
    """Run the isolate -> bridge -> discriminate observer chain over one BOUND binding's anchors. Read-only.
    Lazy-imports the route observers. Never draws / places / promotes."""
    from truelinev2.extract.plan_view_route_isolator import observe_route_isolation
    from truelinev2.extract.route_gap_bridge import bridge_route_gaps
    from truelinev2.extract.route_main_run import discriminate_main_run

    start_xy = binding.start_anchor_xy
    end_xy = binding.end_anchor_xy
    common = _common(binding)
    if start_xy is None or end_xy is None:                 # defensive: a bound binding always exposes both xy
        return RouteVerification(**common, route_observer_status=None, route_isolation_status=None,
                                 route_run_status=None, main_run_status=None, gap_bridge_status=None,
                                 route_ready=False, evaluated=False, refusal=NO_PLAN_FOR_ROUTE,
                                 detail={"reason": "bound binding is missing an anchor coordinate"})

    iso = observe_route_isolation(line_items, tuple(start_xy), tuple(end_xy), page_bounds=page_bounds, words=words)
    brg = bridge_route_gaps(list(iso.route_segments))
    main = discriminate_main_run(list(brg.bridged_segments), tuple(start_xy), tuple(end_xy))

    # ZERO-FALSE gate: the route is verified ONLY when the TIGHT isolation gate (G-b', reach_tol 12pt — the anchors
    # are the ENDS of a unique simple isolated run) AND the discriminator (G-b''') BOTH pass. Requiring isolation
    # closes the radius asymmetry: G-b''' alone (anchor_radius 50pt) would accept a bound anchor sitting 13-49pt OFF
    # the drawn route (as leader-tip / symbol anchors do) that isolation rejects. A route the isolation gate
    # rejected can NEVER be route-ready; the bridge / discriminate outputs only enrich the report + confirm.
    route_ready = iso.status == ROUTE_LINEWORK_ISOLATED and main.status == MAIN_ROUTE_DISCRIMINATED
    if route_ready:
        canonical = MAIN_ROUTE_DISCRIMINATED
    elif iso.status != ROUTE_LINEWORK_ISOLATED:
        canonical = iso.status                             # the tight isolation gate is the primary blocker
    else:
        canonical = main.status                            # isolated, but the discriminator refused
    return RouteVerification(
        **common,
        route_observer_status=canonical,
        route_isolation_status=iso.status,
        route_run_status=iso.run_status,
        main_run_status=main.status,
        gap_bridge_status=brg.status,
        route_ready=route_ready,
        evaluated=True,
        refusal=(None if route_ready else canonical),
        detail={"start_anchor_xy": list(start_xy), "end_anchor_xy": list(end_xy),
                "isolation": iso.to_dict(), "gap_bridge": brg.to_dict(), "main_run": main.to_dict(),
                "class_verified": False})


def _common(binding: EndpointBinding) -> Dict[str, Any]:
    return dict(
        span_id=binding.span_id, start_station=binding.start_station, end_station=binding.end_station,
        start_anchor_summary=_anchor_summary(binding.start_anchor_status, binding.start_anchor_method,
                                             binding.start_anchor_xy),
        end_anchor_summary=_anchor_summary(binding.end_anchor_status, binding.end_anchor_method,
                                           binding.end_anchor_xy))


def _unbound(binding: EndpointBinding) -> RouteVerification:
    """The route stage does NOT run for an unbound binding (the ANCHOR stage already reports ANCHOR_BLOCKED)."""
    return RouteVerification(**_common(binding), route_observer_status=None, route_isolation_status=None,
                             route_run_status=None, main_run_status=None, gap_bridge_status=None,
                             route_ready=False, evaluated=False, refusal=ANCHOR_NOT_BOUND,
                             detail={"reason": "endpoints not bound; route verification not run"})


def _plan_error(binding: EndpointBinding, error: str) -> RouteVerification:
    return RouteVerification(**_common(binding), route_observer_status=None, route_isolation_status=None,
                             route_run_status=None, main_run_status=None, gap_bridge_status=None,
                             route_ready=False, evaluated=False, refusal=UNREADABLE_PLAN_ROUTE,
                             detail={"error": error})


def verify_span_route(plan_path: Optional[str], binding: EndpointBinding, *, sheet: int = 1,
                      offset: int = 0) -> RouteVerification:
    """Verify one span's route between its BOUND anchors. Opens + closes the plan itself. An unbound binding is
    NOT run (returns ANCHOR_NOT_BOUND); with no plan it returns NO_PLAN_FOR_ROUTE. Read-only; never draws."""
    if not binding.bound:
        return _unbound(binding)
    if not plan_path:
        return RouteVerification(**_common(binding), route_observer_status=None, route_isolation_status=None,
                                 route_run_status=None, main_run_status=None, gap_bridge_status=None,
                                 route_ready=False, evaluated=False, refusal=NO_PLAN_FOR_ROUTE,
                                 detail={"reason": "bound binding but no plan to verify against"})
    from truelinev2.ingest.pdf import PlanPdf
    plan = None
    try:
        plan = PlanPdf(str(plan_path))
        line_items = plan.line_items(int(sheet), int(offset))
        words = plan.words(int(sheet), int(offset))
        page_bounds = plan.page_bounds_display(int(sheet), int(offset))
        return _verify_bound(binding, line_items, words, page_bounds)
    except Exception as exc:                               # noqa: BLE001 — an unreadable plan is a NAMED refusal
        return _plan_error(binding, str(exc))
    finally:
        if plan is not None:
            try:
                plan.close()
            except Exception:                              # noqa: BLE001
                pass


def verify_extraction_routes(plan_path: Optional[str], report: EndpointBindingReport, *, sheet: int = 1,
                             offset: int = 0) -> RouteVerificationReport:
    """Verify the route for every binding in an ``EndpointBindingReport``. Opens the plan ONCE (only when there is
    at least one bound binding to verify) and reuses its linework across spans. Read-only; never draws."""
    bindings = report.bindings
    plan_present = bool(plan_path)
    need_plan = plan_present and any(b.bound for b in bindings)

    verifications: List[RouteVerification]
    if not need_plan:
        verifications = [(_unbound(b) if not b.bound else
                          RouteVerification(**_common(b), route_observer_status=None, route_isolation_status=None,
                                            route_run_status=None, main_run_status=None, gap_bridge_status=None,
                                            route_ready=False, evaluated=False, refusal=NO_PLAN_FOR_ROUTE,
                                            detail={"reason": "bound binding but no plan to verify against"}))
                         for b in bindings]
        return RouteVerificationReport(tuple(verifications), plan_present=plan_present, sheet=sheet,
                                       detail={"span_count": len(bindings), "plan_opened": False})

    from truelinev2.ingest.pdf import PlanPdf
    plan = None
    try:
        plan = PlanPdf(str(plan_path))
        line_items = plan.line_items(int(sheet), int(offset))
        words = plan.words(int(sheet), int(offset))
        page_bounds = plan.page_bounds_display(int(sheet), int(offset))
        verifications = [(_verify_bound(b, line_items, words, page_bounds) if b.bound else _unbound(b))
                         for b in bindings]
    except Exception as exc:                               # noqa: BLE001 — unreadable plan -> NAMED refusal per bound span
        verifications = [(_plan_error(b, str(exc)) if b.bound else _unbound(b)) for b in bindings]
    finally:
        if plan is not None:
            try:
                plan.close()
            except Exception:                              # noqa: BLE001
                pass
    return RouteVerificationReport(tuple(verifications), plan_present=plan_present, sheet=sheet,
                                   detail={"span_count": len(bindings), "plan_opened": True})


def route_evidence_for_package(report: RouteVerificationReport) -> Optional[RouteEvidence]:
    """Reduce per-span route verifications to the package-level ``RouteEvidence`` seam. Returns None (route NOT
    evaluated -> the classifier stays at the ANCHOR stage, honoring the anchor verdict) when no plan is present,
    no bindings exist, or no BOUND span was route-evaluated. A route-ready span -> the verified status
    (MAIN_ROUTE_DISCRIMINATED); otherwise a bound-but-blocked span -> its reject status (-> ROUTE_BLOCKED). Never
    invents a status."""
    if not report.plan_present or not report.verifications:
        return None
    ready = next((v for v in report.verifications if v.route_ready), None)
    if ready is not None:
        return RouteEvidence(status=ready.route_observer_status or MAIN_ROUTE_DISCRIMINATED,
                             detail={"span_id": ready.span_id, "isolation": ready.route_isolation_status,
                                     "gap_bridge": ready.gap_bridge_status})
    blocked = next((v for v in report.verifications if v.evaluated), None)
    if blocked is not None:
        return RouteEvidence(status=(blocked.route_observer_status or blocked.refusal or "UNMEASURABLE"),
                             detail={"span_id": blocked.span_id, "isolation": blocked.route_isolation_status,
                                     "gap_bridge": blocked.gap_bridge_status, "refusal": blocked.refusal})
    return None                                            # bindings exist but none was route-evaluated


# ======================================================================================================== #
# Seams 4-5 — the readiness-adapter bridge + the end-to-end ROUTE-stage runner.
# ======================================================================================================== #
@dataclass(frozen=True)
class PackageRouteReadiness:
    report: ReviewReadinessReport
    extraction: SpanExtraction
    bindings: EndpointBindingReport
    routes: RouteVerificationReport

    def to_dict(self) -> dict:
        return {"report": self.report.to_dict(), "extraction": self.extraction.to_dict(),
                "bindings": self.bindings.to_dict(), "routes": self.routes.to_dict()}


def run_package_route_readiness(package_dir, *, plan_sheet: int = 1,
                                allow_live: bool = False) -> Optional[PackageRouteReadiness]:
    """End-to-end ROUTE stage: discover the package, run the source-span extractor, bind each span's endpoints
    (ANCHOR stage), verify the drawn route between the bound anchors (this stage), feed the resulting AnchorEvidence
    + RouteEvidence into the readiness adapter, and classify. Read-only; draws nothing."""
    from truelinev2.harness.endpoint_binding import anchor_evidence_for_package, bind_extraction_endpoints
    from truelinev2.harness.readiness_adapter import run_readiness_with_spans
    from truelinev2.harness.readiness_source import discover_package
    from truelinev2.harness.span_extractor import extract_spans_from_folder

    source = discover_package(package_dir)
    extraction = extract_spans_from_folder(str(package_dir))
    binding_report = bind_extraction_endpoints(source.plan_path, extraction, sheet=plan_sheet)
    anchor = anchor_evidence_for_package(binding_report)
    route_report = verify_extraction_routes(source.plan_path, binding_report, sheet=plan_sheet)
    route = route_evidence_for_package(route_report)
    pr = run_readiness_with_spans(package_dir, allow_live=allow_live, anchor=anchor, route=route)
    if pr is None:
        return None
    return PackageRouteReadiness(report=pr.report, extraction=pr.extraction, bindings=binding_report,
                                 routes=route_report)
