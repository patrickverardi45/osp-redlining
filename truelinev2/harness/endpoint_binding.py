"""SOURCE-BACKED ENDPOINT BINDING — the ANCHOR stage after SPAN_SOURCE_FOUND (read-only, name-free, harness-only).

Takes the extracted source-confirmed span rows and attempts to bind each span's start/end STATION to a drawn
anchor on the plan, using the EXISTING read-only Track B machinery verbatim: G-a
(`printed_station_locator.observe_plan_view_endpoints_for_path`) for the printed station-label status, and G-a'
(`plan_view_anchor_resolver.resolve_plan_view_anchor_for_path`) for the source-backed anchor (route terminus /
structure symbol / leader tip / proximity symbol). It never draws, never places, never verifies the route, never
promotes AUTO. It invents no coordinate — any (x, y) on a binding is exactly what the anchor observer exposed.

Endpoint binding ONLY — NOT route validation and NOT the G-e REVIEW stroke. Its output feeds the
``ReviewReadinessEvidence.anchor`` seam so a package can move from ``SPAN_SOURCE_FOUND`` to either anchors-resolved
(still ``SPAN_SOURCE_FOUND`` at the ANCHOR stage, route pending) or ``ANCHOR_BLOCKED``; with no plan it simply
leaves the anchor unevaluated (stays ``SPAN_SOURCE_FOUND``, needs a plan). It imports nothing from render /
placement / api / store / contracts / web / product runtime; the fitz-backed observers are lazy-imported.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

from truelinev2.harness.review_readiness import AnchorEvidence, ReviewReadinessReport
from truelinev2.harness.span_extractor import SpanExtraction, SpanRow
from truelinev2.stations import parse_station

# --- known PASS statuses of the read-only observers (test-locked against the real constants) ------------ #
STATION_LABEL_LOCATED = "STATION_LABEL_LOCATED"          # printed_station_locator (G-a)
ANCHOR_PASS_STATUSES = frozenset({                      # plan_view_anchor_resolver (G-a')
    "ANCHOR_RESOLVED_TO_SYMBOL",
    "ANCHOR_RESOLVED_TO_LEADER_TIP",
    "ANCHOR_RESOLVED_TO_ROUTE_ENDPOINT",
})

# --- binding refusals ----------------------------------------------------------------------------------- #
NO_PLAN_FOR_BINDING = "NO_PLAN_FOR_BINDING"
STATION_UNPARSEABLE = "STATION_UNPARSEABLE"
LABEL_NOT_LOCATED = "LABEL_NOT_LOCATED"
ANCHOR_NOT_RESOLVED = "ANCHOR_NOT_RESOLVED"
UNREADABLE_PLAN = "UNREADABLE_PLAN"


def label_located(status: Optional[str]) -> bool:
    return status == STATION_LABEL_LOCATED


def anchor_resolved(status: Optional[str]) -> bool:
    return status in ANCHOR_PASS_STATUSES


# ======================================================================================================== #
# Seam 4 — the endpoint-binding contract.
# ======================================================================================================== #
@dataclass(frozen=True)
class EndpointBinding:
    """Per-span endpoint-binding result. ``*_anchor_xy`` is the observer-exposed anchor coordinate (never
    invented) or None; ``*_anchor_method`` is the evidence type (ROUTE_TERMINUS / LEADER_TRACED_SYMBOL /
    PROXIMITY_SYMBOL / LEADER_TIP). ``bound`` is True only when BOTH endpoints resolved to a source-backed
    anchor."""
    span_id: str
    start_station: str
    end_station: str
    start_label_status: Optional[str]
    end_label_status: Optional[str]
    start_anchor_status: Optional[str]
    end_anchor_status: Optional[str]
    start_anchor_method: Optional[str]
    end_anchor_method: Optional[str]
    start_anchor_xy: Optional[Tuple[float, float]]
    end_anchor_xy: Optional[Tuple[float, float]]
    bound: bool
    refusal: Optional[str]
    detail: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = dict(self.__dict__)
        d["start_anchor_xy"] = list(self.start_anchor_xy) if self.start_anchor_xy else None
        d["end_anchor_xy"] = list(self.end_anchor_xy) if self.end_anchor_xy else None
        d["detail"] = dict(self.detail)
        return d


@dataclass(frozen=True)
class EndpointBindingReport:
    bindings: Tuple[EndpointBinding, ...]
    plan_present: bool
    sheet: int
    detail: Dict[str, Any] = field(default_factory=dict)

    @property
    def any_bound(self) -> bool:
        return any(b.bound for b in self.bindings)

    def to_dict(self) -> dict:
        return {"bindings": [b.to_dict() for b in self.bindings], "plan_present": self.plan_present,
                "sheet": self.sheet, "any_bound": self.any_bound, "detail": dict(self.detail)}


# ======================================================================================================== #
# Seams 1-3 — span-row selection, station-label lookup, anchor-resolver normalization.
# ======================================================================================================== #
def bind_span_endpoints(plan_path: Optional[str], span_row: SpanRow, *, sheet: int = 1,
                        offset: int = 0) -> EndpointBinding:
    """Attempt to bind one span row's start/end stations to plan anchors via the read-only G-a + G-a' path
    drivers. Lazy-imports the observers. Never draws / places / verifies a route."""
    start_ft, end_ft = parse_station(span_row.start_station), parse_station(span_row.end_station)

    def _refuse(reason: str, **extra) -> EndpointBinding:
        return EndpointBinding(
            span_id=span_row.span_id, start_station=span_row.start_station, end_station=span_row.end_station,
            start_label_status=extra.get("sl"), end_label_status=extra.get("el"),
            start_anchor_status=extra.get("sa"), end_anchor_status=extra.get("ea"),
            start_anchor_method=None, end_anchor_method=None, start_anchor_xy=None, end_anchor_xy=None,
            bound=False, refusal=reason, detail={"sheet": sheet, **extra.get("detail", {})})

    if start_ft is None or end_ft is None:
        return _refuse(STATION_UNPARSEABLE)
    if not plan_path:
        return _refuse(NO_PLAN_FOR_BINDING)

    from truelinev2.extract.printed_station_locator import observe_plan_view_endpoints_for_path
    from truelinev2.extract.plan_view_anchor_resolver import resolve_plan_view_anchor_for_path
    try:
        obs = observe_plan_view_endpoints_for_path(
            plan_path, sheet, start_ft, end_ft, start_source_bound=True, end_source_bound=True, offset=offset)
        sa = resolve_plan_view_anchor_for_path(plan_path, sheet, start_ft, offset=offset)
        ea = resolve_plan_view_anchor_for_path(plan_path, sheet, end_ft, offset=offset)
    except Exception as exc:
        return _refuse(UNREADABLE_PLAN, detail={"error": str(exc)})

    bound = anchor_resolved(sa.status) and anchor_resolved(ea.status)
    refusal = None
    if not bound:
        refusal = (LABEL_NOT_LOCATED
                   if not (label_located(obs.start.status) and label_located(obs.end.status))
                   else ANCHOR_NOT_RESOLVED)
    return EndpointBinding(
        span_id=span_row.span_id, start_station=span_row.start_station, end_station=span_row.end_station,
        start_label_status=obs.start.status, end_label_status=obs.end.status,
        start_anchor_status=sa.status, end_anchor_status=ea.status,
        start_anchor_method=sa.method, end_anchor_method=ea.method,
        start_anchor_xy=((sa.x, sa.y) if sa.x is not None and sa.y is not None else None),
        end_anchor_xy=((ea.x, ea.y) if ea.x is not None and ea.y is not None else None),
        bound=bound, refusal=refusal,
        detail={"sheet": sheet, "label_separation": obs.label_separation,
                "class_verified": bool(sa.class_verified and ea.class_verified)})


def bind_extraction_endpoints(plan_path: Optional[str], extraction: SpanExtraction, *, sheet: int = 1,
                              offset: int = 0) -> EndpointBindingReport:
    """Bind every source-confirmed span row in an extraction. Read-only."""
    bindings = tuple(bind_span_endpoints(plan_path, s, sheet=sheet, offset=offset) for s in extraction.spans)
    return EndpointBindingReport(bindings=bindings, plan_present=bool(plan_path), sheet=sheet,
                                 detail={"span_count": len(bindings)})


def anchor_evidence_for_package(report: EndpointBindingReport) -> Optional[AnchorEvidence]:
    """Reduce per-span bindings to the package-level ``AnchorEvidence`` seam. Returns None (anchor NOT evaluated
    -> package stays SPAN_SOURCE_FOUND) when there is no plan or no span to bind; a resolved binding -> pass
    statuses (anchors resolved); otherwise the first binding's blocking statuses -> ANCHOR_BLOCKED. Never
    invents a status."""
    if not report.plan_present or not report.bindings:
        return None
    bound = next((b for b in report.bindings if b.bound), None)
    if bound is not None:
        return AnchorEvidence(start_status=bound.start_anchor_status, end_status=bound.end_anchor_status,
                              detail={"span_id": bound.span_id, "start_method": bound.start_anchor_method,
                                      "end_method": bound.end_anchor_method})
    b = report.bindings[0]
    return AnchorEvidence(start_status=(b.start_anchor_status or "UNMEASURABLE"),
                          end_status=(b.end_anchor_status or "UNMEASURABLE"),
                          detail={"span_id": b.span_id, "refusal": b.refusal})


# ======================================================================================================== #
# Seam 5 — the readiness adapter bridge.
# ======================================================================================================== #
@dataclass(frozen=True)
class PackageAnchorReadiness:
    report: ReviewReadinessReport
    extraction: SpanExtraction
    bindings: EndpointBindingReport

    def to_dict(self) -> dict:
        return {"report": self.report.to_dict(), "extraction": self.extraction.to_dict(),
                "bindings": self.bindings.to_dict()}


def run_package_anchor_readiness(package_dir, *, plan_sheet: int = 1,
                                 allow_live: bool = False) -> Optional[PackageAnchorReadiness]:
    """End-to-end ANCHOR stage: discover the package, run the source-span extractor, bind each span's endpoints
    against the plan via G-a/G-a', feed the resulting AnchorEvidence into the readiness adapter, and classify.
    Read-only; draws nothing."""
    from truelinev2.harness.readiness_adapter import run_readiness_with_spans
    from truelinev2.harness.readiness_source import discover_package
    from truelinev2.harness.span_extractor import extract_spans_from_folder

    source = discover_package(package_dir)
    extraction = extract_spans_from_folder(str(package_dir))
    binding_report = bind_extraction_endpoints(source.plan_path, extraction, sheet=plan_sheet)
    anchor = anchor_evidence_for_package(binding_report)
    pr = run_readiness_with_spans(package_dir, allow_live=allow_live, anchor=anchor)
    if pr is None:
        return None
    return PackageAnchorReadiness(report=pr.report, extraction=pr.extraction, bindings=binding_report)
