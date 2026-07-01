"""Read-only SOURCE-COMPLETENESS / REVIEW-REDLINE-READINESS classifier — the intake traffic controller.

Name-free. Pure stdlib. Draws NOTHING, places NOTHING, promotes NOTHING; touches no renderer / placement /
``_cap_review`` / AUTO / product runtime / recognized-corpus proof / fixtures / coordinates / named detectors.
It only READS the (already-computed) read-only Track B stage evidence for an uploaded package and routes it.

WHY THIS EXISTS (the product rule):
  The product can draw a redline only from a COMPLETE source package, and it must REFUSE an incomplete one. A
  plan-only package is NOT enough when no source file confirms the bore/span START and END stations. This module
  is the read-only traffic controller that, given the Track B stage evidence for a package, reports WHY the
  package is or is not ready for REVIEW-redline generation — and names the single next productive step. It is the
  gate that prepares the pipeline for automatic source-span extraction and future REVIEW redlines once complete
  packages arrive. It is deliberately NOT another "we can't do anything" diagnostic: every non-ready verdict
  carries an actionable ``recommended_next_input``.

THE PIPELINE IT CONTROLS (this module performs NONE of these steps — it reads their evidence and routes only):
    uploaded files
      -> identify whether a bore/span source exists             (SPAN_SOURCE stage)
      -> extract source-confirmed span rows when present         (a FUTURE extractor plugs in at the SEAM below)
      -> bind start / end stations to drawn anchors              (ANCHOR stage; G-a' evidence)
      -> verify the route between the two anchors                (ROUTE stage; G-b / G-b''' evidence)
      -> mark REVIEW readiness                                   (READY)

STATUS LADDER (evaluated in strict precedence; the FIRST match wins):
  1. PACKAGE_RECOGNIZED_CONTROL     -- a named dialect / the recognized-corpus registry already handles the
                                       plan: the deterministic control lane, NOT the cold REVIEW pipeline. This
                                       is a control result, not a failure.
  2. PACKAGE_UNUSABLE_OCR_REQUIRED  -- no extractable text layer: OCR / raster ingestion is required first.
  3. KEEP_BLOCKED                   -- an owner / adversarial TERMINAL reclassification of this package (e.g. two
                                       independent structural blockers): do not spend another gate on it.
  4. MISSING_BORE_SPAN_SOURCE       -- no bore-span source FILE (bore log / bore schedule) is present and the
                                       plan alone confirms no span: plan-only is not enough.
  5. NO_SOURCE_CONFIRMED_SPAN       -- a span source WAS inspected but no span could be source-confirmed (no two
                                       stations tied together as ONE bore with a start and an end).
  6. SPAN_SOURCE_FOUND              -- a source-confirmed span exists; downstream binding not yet fully verified.
  7. ANCHOR_BLOCKED                 -- span found but a start / end station does not bind to a UNIQUE drawn anchor.
  8. ROUTE_BLOCKED                  -- span found + anchors bound, but the route between them is not verifiable.
  9. READY_FOR_REVIEW_REDLINE       -- span found + both endpoints anchored + route verified: ready to GENERATE a
                                       REVIEW redline. (This gate still draws nothing.)

DOCTRINE (ALL-REDLINES + DO-NOT-WIDEN): KEEP_BLOCKED is an owner/adversarial decision, never an autonomous "give
up". The classifier computes a ``double_structural_block`` advisory (a package blocked INDEPENDENTLY at both the
anchor and route stages) that *justifies* an owner KEEP_BLOCKED reclassification, but it never promotes a package
to KEEP_BLOCKED by itself. Abstention is an interim state whose named target is the ``recommended_next_input``.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Sequence, Tuple

# --- readiness statuses (the 9-value traffic-controller vocabulary) ------------------------------------- #
READY_FOR_REVIEW_REDLINE = "READY_FOR_REVIEW_REDLINE"
SPAN_SOURCE_FOUND = "SPAN_SOURCE_FOUND"
NO_SOURCE_CONFIRMED_SPAN = "NO_SOURCE_CONFIRMED_SPAN"
MISSING_BORE_SPAN_SOURCE = "MISSING_BORE_SPAN_SOURCE"
ANCHOR_BLOCKED = "ANCHOR_BLOCKED"
ROUTE_BLOCKED = "ROUTE_BLOCKED"
PACKAGE_RECOGNIZED_CONTROL = "PACKAGE_RECOGNIZED_CONTROL"
PACKAGE_UNUSABLE_OCR_REQUIRED = "PACKAGE_UNUSABLE_OCR_REQUIRED"
KEEP_BLOCKED = "KEEP_BLOCKED"

ALL_STATUSES = (
    READY_FOR_REVIEW_REDLINE, SPAN_SOURCE_FOUND, NO_SOURCE_CONFIRMED_SPAN, MISSING_BORE_SPAN_SOURCE,
    ANCHOR_BLOCKED, ROUTE_BLOCKED, PACKAGE_RECOGNIZED_CONTROL, PACKAGE_UNUSABLE_OCR_REQUIRED, KEEP_BLOCKED,
)

# --- pipeline stage at which the ladder stopped (for reporting) ----------------------------------------- #
STAGE_RECOGNITION = "RECOGNITION"
STAGE_READABILITY = "READABILITY"
STAGE_KEEP_BLOCKED = "KEEP_BLOCKED"
STAGE_SPAN_SOURCE = "SPAN_SOURCE"
STAGE_ANCHOR = "ANCHOR"
STAGE_ROUTE = "ROUTE"
STAGE_READY = "READY"

# --- known PASS status strings of the read-only Track B observers (test-locked against the real observers
#     in tests/test_review_readiness.py so this set can never silently drift). These are plain strings; this
#     module imports NONE of the observers, staying decoupled + pure stdlib. ------------------------------- #
ANCHOR_PASS_STATUSES = frozenset({
    "ANCHOR_RESOLVED_TO_SYMBOL",        # plan_view_anchor_resolver (G-a')
    "ANCHOR_RESOLVED_TO_LEADER_TIP",
    "ANCHOR_RESOLVED_TO_ROUTE_ENDPOINT",
})
ROUTE_PASS_STATUSES = frozenset({
    "MAIN_ROUTE_DISCRIMINATED",         # route_main_run (G-b''')
    "PLAN_VIEW_RUN_CONNECTED",          # plan_view_run_observer (G-b)
})

# --- the actionable next step per non-ready status (a NAMED target, never a vague limitation) ----------- #
NEXT_INPUT_SPAN_SOURCE_FILE = "BORE_LOG_OR_BORE_SCHEDULE_NAMING_ONE_SPAN"   # sheet + start_ft + end_ft
NEXT_INPUT_OCR = "OCR_OR_RASTER_INGESTION"
NEXT_INPUT_ANCHOR_BINDER = "OFF_ROUTE_LABEL_BINDER_OR_ROUTE_ATTACHED_ANCHORS"
NEXT_INPUT_ROUTE_GATE = "ROUTE_CONTINUITY_GATE"
NEXT_INPUT_RUN_DOWNSTREAM = "RUN_ANCHOR_AND_ROUTE_GATES"
NEXT_INPUT_NEW_PACKAGE = "NEW_PACKAGE_OR_OWNER_GATE_APPROVAL"

_NEXT_INPUT = {
    PACKAGE_UNUSABLE_OCR_REQUIRED: NEXT_INPUT_OCR,
    MISSING_BORE_SPAN_SOURCE: NEXT_INPUT_SPAN_SOURCE_FILE,
    NO_SOURCE_CONFIRMED_SPAN: NEXT_INPUT_SPAN_SOURCE_FILE,
    SPAN_SOURCE_FOUND: NEXT_INPUT_RUN_DOWNSTREAM,
    ANCHOR_BLOCKED: NEXT_INPUT_ANCHOR_BINDER,
    ROUTE_BLOCKED: NEXT_INPUT_ROUTE_GATE,
    KEEP_BLOCKED: NEXT_INPUT_NEW_PACKAGE,
    # PACKAGE_RECOGNIZED_CONTROL + READY_FOR_REVIEW_REDLINE need no cold-lane input -> None
}

_NO_DRAW_NOTE = ("read-only readiness classification only — no stroke, no REVIEW candidate, no placement, no "
                 "promotion, no AUTO; the source-span extractor / anchor / route gates run downstream")


# ======================================================================================================== #
# Evidence inputs (a FUTURE adapter fills these from the read-only Track B observers; a bore/span source
# extractor plugs in at the SPAN_SOURCE seam). Every field is opaque data — no name, no coordinate, no draw.
# ======================================================================================================== #
@dataclass(frozen=True)
class SpanSourceEvidence:
    """What the source-span inspection found for a package.

    A *source-confirmed span* means TWO stations are tied together as ONE bore by independent printed/source
    proof (a bore-log / bore-schedule row carrying ``sheet`` + ``start_ft`` + ``end_ft``, or a printed
    ``Sta X to Y`` span callout, or a matchline-boundary continuation). Bare stationing ticks and resolved
    anchors ALONE are NOT a source-confirmed span.

    SEAM: a future automatic bore/span source extractor populates ``source_confirmed_span_count`` (and the
    per-span detail) from these inputs; this classifier only reads the count.
    """
    bore_span_source_files: Tuple[str, ...]   # span-carrying source FILES present (generic kinds, e.g.
                                              # "BORE_LOG", "BORE_SCHEDULE"); empty => no span-source file
    plan_span_layer_inspected: bool           # a printed-span scan actually ran over the plan text layer
    source_confirmed_span_count: int          # spans source-confirmed from those sources (>= 1 => found)
    detail: Dict[str, Any] = field(default_factory=dict)

    @property
    def any_source_inspected(self) -> bool:
        """True iff at least one candidate span source (a file or the plan's printed-span layer) was inspected."""
        return bool(self.bore_span_source_files) or self.plan_span_layer_inspected

    @property
    def has_source_file(self) -> bool:
        return bool(self.bore_span_source_files)

    @property
    def confirmed(self) -> bool:
        return self.source_confirmed_span_count >= 1


@dataclass(frozen=True)
class AnchorEvidence:
    """Per-endpoint anchor-resolution status strings from the read-only G-a' anchor resolver. Both endpoints
    must carry a PASS status for the span's endpoints to be considered bound."""
    start_status: str
    end_status: str
    detail: Dict[str, Any] = field(default_factory=dict)

    @property
    def both_resolved(self) -> bool:
        return anchor_resolved(self.start_status) and anchor_resolved(self.end_status)


@dataclass(frozen=True)
class RouteEvidence:
    """The route-verification status string from the read-only G-b / G-b''' observers. ``independently_blocked``
    is True only when a route observer was actually RUN and returned a reject (not merely 'not evaluated')."""
    status: str
    detail: Dict[str, Any] = field(default_factory=dict)

    @property
    def verified(self) -> bool:
        return route_verified(self.status)

    @property
    def independently_blocked(self) -> bool:
        return bool(self.status) and not route_verified(self.status)


@dataclass(frozen=True)
class ReviewReadinessEvidence:
    """The read-only evidence bundle a caller assembles for one uploaded/source package. ``anchor`` / ``route``
    are ``None`` when that stage was not evaluated (e.g. no span to anchor, or anchors unresolved so the route
    could not be verified). No field carries a name, a coordinate, or a drawn stroke."""
    package_id: str                             # runtime data id (no default -> never a hardcoded name)
    plan_readable: bool                         # the plan has an extractable text layer (False => OCR needed)
    recognized: bool                            # a named dialect or the recognized-corpus registry matches
    keep_blocked: bool = False                  # owner / adversarial TERMINAL reclassification of this package
    keep_blocked_reason: str = ""
    span: Optional[SpanSourceEvidence] = None
    anchor: Optional[AnchorEvidence] = None
    route: Optional[RouteEvidence] = None
    detail: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ReviewReadinessReport:
    """Read-only readiness verdict for one package. ``draws_anything`` / ``performs_placement`` are ALWAYS
    False. ``is_control`` marks the recognized deterministic lane (out of cold scope, not a failure)."""
    package_id: str
    status: str                                 # one of ALL_STATUSES
    stage: str                                  # the stage at which the ladder stopped
    ready: bool                                 # status == READY_FOR_REVIEW_REDLINE
    is_control: bool                            # status == PACKAGE_RECOGNIZED_CONTROL
    reason: str
    contributing_reasons: Tuple[str, ...]
    double_structural_block: bool               # blocked INDEPENDENTLY at both anchor AND route stages
    keep_blocked_candidate: bool                # advisory: an owner MAY reclassify this to KEEP_BLOCKED
    recommended_next_input: Optional[str]       # the NAMED next productive step (None when ready/control)
    draws_anything: bool                        # ALWAYS False
    performs_placement: bool                    # ALWAYS False
    note: str
    detail: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "package_id": self.package_id,
            "status": self.status,
            "stage": self.stage,
            "ready": self.ready,
            "is_control": self.is_control,
            "reason": self.reason,
            "contributing_reasons": list(self.contributing_reasons),
            "double_structural_block": self.double_structural_block,
            "keep_blocked_candidate": self.keep_blocked_candidate,
            "recommended_next_input": self.recommended_next_input,
            "draws_anything": self.draws_anything,
            "performs_placement": self.performs_placement,
            "note": self.note,
            "detail": dict(self.detail),
        }


# --- helper predicates (a future adapter maps observer status strings to booleans through these) -------- #
def anchor_resolved(status: Optional[str]) -> bool:
    """True iff a G-a' anchor status is one of the source-backed PASS resolutions."""
    return status in ANCHOR_PASS_STATUSES


def route_verified(status: Optional[str]) -> bool:
    """True iff a G-b / G-b''' route status is a clean verified run."""
    return status in ROUTE_PASS_STATUSES


def _report(evidence: ReviewReadinessEvidence, status: str, stage: str, reason: str, *,
            contributing: Sequence[str] = (), double_structural_block: bool = False,
            keep_blocked_candidate: bool = False, extra_detail: Optional[Dict[str, Any]] = None
            ) -> ReviewReadinessReport:
    detail: Dict[str, Any] = dict(evidence.detail)
    if extra_detail:
        detail.update(extra_detail)
    return ReviewReadinessReport(
        package_id=evidence.package_id,
        status=status,
        stage=stage,
        ready=(status == READY_FOR_REVIEW_REDLINE),
        is_control=(status == PACKAGE_RECOGNIZED_CONTROL),
        reason=reason,
        contributing_reasons=tuple(contributing),
        double_structural_block=double_structural_block,
        keep_blocked_candidate=keep_blocked_candidate,
        recommended_next_input=_NEXT_INPUT.get(status),
        draws_anything=False,
        performs_placement=False,
        note=_NO_DRAW_NOTE,
        detail=detail,
    )


def classify_review_readiness(evidence: ReviewReadinessEvidence) -> ReviewReadinessReport:
    """Route one package's read-only Track B evidence to a single readiness status. Draws / places / promotes
    NOTHING. The FIRST matching rung of the precedence ladder wins."""
    # 1. recognition control lane -- handled by the deterministic engine, out of the cold REVIEW pipeline.
    if evidence.recognized:
        return _report(evidence, PACKAGE_RECOGNIZED_CONTROL, STAGE_RECOGNITION,
                       "plan recognized by a named dialect or the recognized-corpus registry — deterministic "
                       "control lane, not the cold REVIEW pipeline (out of scope, not a failure)")

    # 2. readability -- cannot read any source text; OCR / raster ingestion required first.
    if not evidence.plan_readable:
        return _report(evidence, PACKAGE_UNUSABLE_OCR_REQUIRED, STAGE_READABILITY,
                       "no extractable text layer — OCR / raster ingestion required before source-span extraction")

    # 3. owner / adversarial TERMINAL reclassification -- do not spend another gate on this package.
    if evidence.keep_blocked:
        return _report(evidence, KEEP_BLOCKED, STAGE_KEEP_BLOCKED,
                       evidence.keep_blocked_reason or
                       "owner / adversarial reclassification — not solvable from this package's current source")

    # 4./5. span source -- is there a bore/span that a source FILE (or the plan) actually confirms?
    span = evidence.span
    if span is None or not span.confirmed:
        contributing = []
        no_source_file = (span is None) or (not span.has_source_file)
        inspected = (span is not None) and span.any_source_inspected
        if no_source_file:
            contributing.append(MISSING_BORE_SPAN_SOURCE)
        if inspected:
            contributing.append(NO_SOURCE_CONFIRMED_SPAN)
        if not contributing:                          # nothing was even inspected -> plan-only, no source
            contributing.append(MISSING_BORE_SPAN_SOURCE)
        # precedence: a missing source FILE is the actionable, dominant verdict (plan-only is not enough);
        # otherwise a source was inspected but confirmed no span.
        primary = MISSING_BORE_SPAN_SOURCE if MISSING_BORE_SPAN_SOURCE in contributing else NO_SOURCE_CONFIRMED_SPAN
        reason = ("no bore-span source file present and the plan alone confirms no span — plan-only is not "
                  "enough" if primary == MISSING_BORE_SPAN_SOURCE else
                  "a span source was inspected but no span could be source-confirmed (no two stations tied as "
                  "one bore with a start and an end)")
        return _report(evidence, primary, STAGE_SPAN_SOURCE, reason, contributing=tuple(contributing),
                       extra_detail=_span_detail(evidence))

    # span is source-confirmed -> baseline SPAN_SOURCE_FOUND; now bind anchors, then verify the route.
    anchor = evidence.anchor
    route = evidence.route
    anchor_blocked = (anchor is not None) and (not anchor.both_resolved)
    route_blocked = (route is not None) and route.independently_blocked
    # a package blocked INDEPENDENTLY at BOTH stages is a candidate for an OWNER KEEP_BLOCKED reclassification
    # (this is the pattern behind the 011-family strategic call); it is advisory only, never auto-terminal.
    double = anchor_blocked and route_blocked

    if anchor is None:                                # span found; anchors not yet evaluated
        return _report(evidence, SPAN_SOURCE_FOUND, STAGE_SPAN_SOURCE,
                       "source-confirmed span found; endpoint anchor binding not yet evaluated")

    if anchor_blocked:
        return _report(evidence, ANCHOR_BLOCKED, STAGE_ANCHOR,
                       "source-confirmed span found, but a start / end station does not bind to a unique drawn "
                       "anchor (%s / %s)" % (anchor.start_status, anchor.end_status),
                       double_structural_block=double, keep_blocked_candidate=double,
                       extra_detail={"anchor_start": anchor.start_status, "anchor_end": anchor.end_status})

    # anchors resolved
    if route is None:                                 # span + anchors OK; route not yet evaluated
        return _report(evidence, SPAN_SOURCE_FOUND, STAGE_ANCHOR,
                       "source-confirmed span found and both endpoints anchored; route verification not yet "
                       "evaluated")

    if route_blocked:
        return _report(evidence, ROUTE_BLOCKED, STAGE_ROUTE,
                       "span found and endpoints anchored, but the route between them is not verifiable (%s)"
                       % route.status, double_structural_block=double,
                       extra_detail={"route_status": route.status})

    # span + anchors + route all clear -> ready to GENERATE a REVIEW redline downstream (this gate draws nothing)
    return _report(evidence, READY_FOR_REVIEW_REDLINE, STAGE_READY,
                   "source-confirmed span + both endpoints anchored + route verified — ready to generate a "
                   "REVIEW redline (this gate draws nothing)",
                   extra_detail={"anchor_start": anchor.start_status, "anchor_end": anchor.end_status,
                                 "route_status": route.status})


def _span_detail(evidence: ReviewReadinessEvidence) -> Dict[str, Any]:
    """Carry forward the anchor evidence (if any) at a span-stage stop, so a report can state e.g. 'anchors
    would resolve; the blocker is upstream at the span source, not the anchors'."""
    out: Dict[str, Any] = {}
    if evidence.anchor is not None:
        out["anchor_start"] = evidence.anchor.start_status
        out["anchor_end"] = evidence.anchor.end_status
        out["anchors_would_resolve"] = evidence.anchor.both_resolved
    return out


def format_report(report: ReviewReadinessReport) -> str:
    return json.dumps(report.to_dict(), indent=2, sort_keys=True)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Harness-only diagnostic CLI: read a JSON evidence file and print the readiness report. Performs no
    placement and writes nothing.

    The JSON mirrors ``ReviewReadinessEvidence`` (``span`` / ``anchor`` / ``route`` optional nested objects):
      ``python -m truelinev2.harness.review_readiness <evidence.json>``
    """
    import sys
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        sys.stderr.write("usage: review_readiness <evidence.json>\n")
        return 2
    try:
        raw = json.loads(open(args[0], encoding="utf-8").read())
    except (OSError, ValueError) as exc:
        sys.stderr.write("could not read evidence json: %s\n" % exc)
        return 2
    span = raw.get("span")
    anchor = raw.get("anchor")
    route = raw.get("route")
    evidence = ReviewReadinessEvidence(
        package_id=str(raw.get("package_id") or "package"),
        plan_readable=bool(raw.get("plan_readable", True)),
        recognized=bool(raw.get("recognized", False)),
        keep_blocked=bool(raw.get("keep_blocked", False)),
        keep_blocked_reason=str(raw.get("keep_blocked_reason", "")),
        span=SpanSourceEvidence(
            bore_span_source_files=tuple(span.get("bore_span_source_files", ())),
            plan_span_layer_inspected=bool(span.get("plan_span_layer_inspected", False)),
            source_confirmed_span_count=int(span.get("source_confirmed_span_count", 0)),
            detail=dict(span.get("detail", {}))) if isinstance(span, dict) else None,
        anchor=AnchorEvidence(
            start_status=str(anchor.get("start_status", "")),
            end_status=str(anchor.get("end_status", "")),
            detail=dict(anchor.get("detail", {}))) if isinstance(anchor, dict) else None,
        route=RouteEvidence(
            status=str(route.get("status", "")),
            detail=dict(route.get("detail", {}))) if isinstance(route, dict) else None,
        detail=dict(raw.get("detail", {})))
    print(format_report(classify_review_readiness(evidence)))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
