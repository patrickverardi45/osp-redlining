"""SOURCE-BACKED REVIEW CANDIDATE — the first drawing-capable slice, gated on READY_FOR_REVIEW_REDLINE
(read-only readiness spine + a REVIEW-candidate overlay; name-free; harness-only).

Generates a human-reviewable REVIEW CANDIDATE redline artifact ONLY when the completed readiness spine returns
exactly ``READY_FOR_REVIEW_REDLINE`` (source-confirmed span + both endpoints source-anchored + route verified). It
is **NOT AUTO, NOT final placement, and NOT a status promotion** — it is a candidate plus its source evidence
chain, for a human to review. Every visual element is drawn from OBSERVER-EXPOSED geometry (the bound anchor
coordinates + the G-b‴ verified main-run backbone); it invents no station / bore row / anchor / endpoint / route
geometry / source relationship. The RED stroke follows the Red Stroke Law (``REVIEW_STROKE_RGB``, test-locked to
the canonical render constant); the source PDF is never recolored.

Every non-READY readiness status — ``MISSING_BORE_SPAN_SOURCE`` / ``NO_SOURCE_CONFIRMED_SPAN`` / ``ANCHOR_BLOCKED``
/ ``ROUTE_BLOCKED`` (and any other) — generates ZERO candidates and NO artifact.

It draws a REVIEW candidate but touches NO product placement / status / ``_cap_review`` / AUTO / renderer / web /
staging / backend runtime: the overlay is a self-contained ``fitz`` raster written into a caller-supplied directory
(never committed). It imports nothing from render / placement / api / store / contracts / match / web; ``fitz`` +
the readiness spine are lazy-imported.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from truelinev2.harness.review_readiness import READY_FOR_REVIEW_REDLINE

# --- candidate statuses --------------------------------------------------------------------------------- #
REVIEW_CANDIDATE_READY = "REVIEW_CANDIDATE_READY"        # exactly one source-backed candidate produced
REVIEW_CANDIDATE_REFUSED = "REVIEW_CANDIDATE_REFUSED"    # not READY -> zero candidates, no artifact

# --- Red Stroke Law: ALL drawn redline overlays are RED. Test-locked to render.crop.REDLINE_STROKE_RGB. -- #
REVIEW_STROKE_RGB = (220, 25, 25)
_STROKE_WIDTH_PT = 2.5
_RENDER_ZOOM = 2.0

# --- per non-READY readiness status: why no candidate was drawn ----------------------------------------- #
_REFUSAL_REASONS = {
    "MISSING_BORE_SPAN_SOURCE": "no source-confirmed bore span — nothing to draw",
    "NO_SOURCE_CONFIRMED_SPAN": "a span source was inspected but confirmed no span — nothing to draw",
    "ANCHOR_BLOCKED": "a start/end station does not bind to a unique drawn anchor — no verified endpoints",
    "ROUTE_BLOCKED": "endpoints anchored but the route between them is not verifiable — no verified run",
    "SPAN_SOURCE_FOUND": "downstream anchor/route not yet verified",
    "PACKAGE_RECOGNIZED_CONTROL": "recognized deterministic control lane — out of the cold REVIEW pipeline",
    "PACKAGE_UNUSABLE_OCR_REQUIRED": "no extractable text layer — OCR / raster ingestion required first",
    "KEEP_BLOCKED": "owner / adversarial terminal reclassification",
}


# ======================================================================================================== #
# Seam 2 — the REVIEW-candidate evidence contract.
# ======================================================================================================== #
@dataclass(frozen=True)
class ReviewCandidate:
    """A single human-reviewable REVIEW candidate + its source evidence. ``route_geometry`` is the
    observer-exposed verified backbone (never invented). ``is_auto`` / ``is_final_placement`` / ``is_promotion``
    are ALWAYS False — a candidate is REVIEW evidence, not a placement / AUTO / status change."""
    span_id: str
    start_station: str
    end_station: str
    source_file: str
    source_citation: str
    source_kind: str
    confidence: str
    start_anchor_summary: Optional[Dict[str, Any]]
    end_anchor_summary: Optional[Dict[str, Any]]
    route_summary: Dict[str, Any]
    route_geometry: Tuple[Dict[str, Any], ...]
    candidate_status: str
    artifact_before: Optional[str]
    artifact_after: Optional[str]
    stroke_rgb: Tuple[int, int, int]
    evidence_chain: Tuple[str, ...]
    is_auto: bool = False
    is_final_placement: bool = False
    is_promotion: bool = False

    def to_dict(self) -> dict:
        return {
            "span_id": self.span_id, "start_station": self.start_station, "end_station": self.end_station,
            "source_file": self.source_file, "source_citation": self.source_citation,
            "source_kind": self.source_kind, "confidence": self.confidence,
            "start_anchor_summary": dict(self.start_anchor_summary) if self.start_anchor_summary else None,
            "end_anchor_summary": dict(self.end_anchor_summary) if self.end_anchor_summary else None,
            "route_summary": dict(self.route_summary),
            "route_geometry": [{"a": list(s["a"]), "b": list(s["b"])} for s in self.route_geometry],
            "candidate_status": self.candidate_status,
            "artifact_before": self.artifact_before, "artifact_after": self.artifact_after,
            "stroke_rgb": list(self.stroke_rgb), "evidence_chain": list(self.evidence_chain),
            "is_auto": self.is_auto, "is_final_placement": self.is_final_placement,
            "is_promotion": self.is_promotion,
        }


@dataclass(frozen=True)
class ReviewCandidateReport:
    """The outcome of a candidate attempt. Exactly one candidate when READY; zero on any refusal.
    ``performs_auto`` / ``performs_placement`` / ``promotes_status`` are ALWAYS False."""
    readiness_status: str
    candidate_status: str
    candidates: Tuple[ReviewCandidate, ...]
    refusal_reason: Optional[str]
    generated_visual: bool
    is_review_candidate: bool = True
    performs_auto: bool = False
    performs_placement: bool = False
    promotes_status: bool = False
    detail: Dict[str, Any] = field(default_factory=dict)

    @property
    def candidate_count(self) -> int:
        return len(self.candidates)

    def to_dict(self) -> dict:
        return {
            "readiness_status": self.readiness_status, "candidate_status": self.candidate_status,
            "candidate_count": self.candidate_count, "candidates": [c.to_dict() for c in self.candidates],
            "refusal_reason": self.refusal_reason, "generated_visual": self.generated_visual,
            "is_review_candidate": self.is_review_candidate, "performs_auto": self.performs_auto,
            "performs_placement": self.performs_placement, "promotes_status": self.promotes_status,
            "detail": dict(self.detail),
        }


# ======================================================================================================== #
# Seam 3 — visual artifact generation (self-contained fitz raster; NOT the product renderer).
# ======================================================================================================== #
def render_review_candidate_overlay(plan_path, sheet: int, route_geometry: Tuple[Dict[str, Any], ...], *,
                                    out_before, out_after, offset: int = 0) -> None:
    """Render the plan-as-is (``out_before``) + the plan with a RED REVIEW stroke along the observer-exposed
    verified backbone (``out_after``) as PNGs. Draws in DISPLAY space via the page's inverse rotation so the
    stroke lines up with the observer coordinates. Writes ONLY the two given paths; opens + closes its own fitz
    doc; changes nothing in the product / no `_cap_review` / no placement. The RED follows the Red Stroke Law;
    the source PDF is not recolored (the stroke is an overlay)."""
    import fitz

    doc = fitz.open(str(plan_path))
    try:
        page = doc[int(sheet) + int(offset) - 1]           # matches PlanPdf.page_index (sheet + offset - 1)
        matrix = fitz.Matrix(_RENDER_ZOOM, _RENDER_ZOOM)
        page.get_pixmap(matrix=matrix, colorspace=fitz.csRGB, alpha=False).save(str(out_before))
        inv = ~page.rotation_matrix                        # display-space coords -> raw draw space
        red = (REVIEW_STROKE_RGB[0] / 255.0, REVIEW_STROKE_RGB[1] / 255.0, REVIEW_STROKE_RGB[2] / 255.0)
        for seg in route_geometry:
            a = fitz.Point(float(seg["a"][0]), float(seg["a"][1])) * inv
            b = fitz.Point(float(seg["b"][0]), float(seg["b"][1])) * inv
            page.draw_line(a, b, color=red, width=_STROKE_WIDTH_PT)
        page.get_pixmap(matrix=matrix, colorspace=fitz.csRGB, alpha=False).save(str(out_after))
    finally:
        doc.close()


# ======================================================================================================== #
# Seams 1 + 4 — route-ready candidate selection + refusal handling + report assembly.
# ======================================================================================================== #
def _fmt_xy(xy) -> str:
    return ("(%.1f, %.1f)" % (float(xy[0]), float(xy[1]))) if xy else "n/a"


def _refused(status: str, *, extra: Optional[str] = None) -> ReviewCandidateReport:
    reason = _REFUSAL_REASONS.get(status, "readiness is %s — not READY_FOR_REVIEW_REDLINE" % status)
    if extra:
        reason = "%s (%s)" % (reason, extra)
    return ReviewCandidateReport(readiness_status=status, candidate_status=REVIEW_CANDIDATE_REFUSED,
                                 candidates=(), refusal_reason=reason, generated_visual=False,
                                 detail={"gated_on": READY_FOR_REVIEW_REDLINE})


def _evidence_chain(status, span, binding, verification, geometry, generated: bool) -> Tuple[str, ...]:
    chain = [
        "readiness == %s (source-confirmed span + both endpoints anchored + route verified)" % status,
        "source span %s from %s: %r (kind %s, confidence %s)"
        % (span.span_id, span.source_file, span.citation, span.source_kind, span.confidence),
        "start %s -> %s via %s at %s"
        % (binding.start_station, binding.start_anchor_status, binding.start_anchor_method,
           _fmt_xy(binding.start_anchor_xy)),
        "end %s -> %s via %s at %s"
        % (binding.end_station, binding.end_anchor_status, binding.end_anchor_method,
           _fmt_xy(binding.end_anchor_xy)),
        "route verified: %s (isolation %s, run %s, main_run %s, bridge %s)"
        % (verification.route_observer_status, verification.route_isolation_status, verification.route_run_status,
           verification.main_run_status, verification.gap_bridge_status),
        "geometry: %d observer-exposed verified-backbone segment(s); RED %s REVIEW stroke; source PDF not recolored"
        % (len(geometry), REVIEW_STROKE_RGB),
        "REVIEW CANDIDATE — human-reviewable; NOT AUTO, NOT final placement, NOT a status promotion; "
        "class_verified=False",
    ]
    if generated:
        chain.append("visual overlay rendered (before = plan as-is, after = plan + RED REVIEW stroke)")
    return tuple(chain)


def build_review_candidate(readiness, *, plan_path=None, artifact_dir=None) -> ReviewCandidateReport:
    """Build a REVIEW candidate from a completed ``PackageRouteReadiness`` — ONLY when its readiness status is
    exactly ``READY_FOR_REVIEW_REDLINE``. Otherwise refuse with zero candidates + no artifact. When
    ``artifact_dir`` + ``plan_path`` are supplied and the verified geometry is present, render the before/after
    REVIEW overlay PNGs on the SAME page the geometry was verified on (``readiness.routes.sheet``, so the render
    page can never diverge from the observer geometry's page). Read-only wrt the product; no AUTO / placement /
    status change / ``_cap_review``."""
    status = readiness.report.status
    if status != READY_FOR_REVIEW_REDLINE:
        return _refused(status)

    verification = next((v for v in readiness.routes.verifications if v.route_ready), None)
    if verification is None:                               # defensive — READY implies a route-ready span
        return _refused(status, extra="READY without a route-ready verification")
    span = next((s for s in readiness.extraction.spans if s.span_id == verification.span_id), None)
    binding = next((b for b in readiness.bindings.bindings
                    if b.span_id == verification.span_id and b.bound), None)
    if span is None or binding is None:                    # defensive — READY implies both exist
        return _refused(status, extra="READY without a matching source span / bound anchor")

    geometry = tuple(verification.route_geometry)
    # The page the geometry was verified on (never diverges): sheet = the ENGINEERING sheet, sheet_offset =
    # the report's own page resolution (Slice 3; 0 = raw-page semantics) -> PDF page = sheet + sheet_offset.
    sheet = readiness.routes.sheet
    sheet_offset = int(getattr(readiness.routes, "sheet_offset", 0) or 0)
    before = after = None
    generated = False
    if artifact_dir is not None and plan_path and geometry:
        out_dir = Path(artifact_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        before = str(out_dir / ("review_candidate_%s_before.png" % verification.span_id))
        after = str(out_dir / ("review_candidate_%s_after.png" % verification.span_id))
        render_review_candidate_overlay(plan_path, sheet, geometry, out_before=before, out_after=after,
                                        offset=sheet_offset)
        generated = True

    route_summary = {
        "route_ready": verification.route_ready, "route_observer_status": verification.route_observer_status,
        "route_isolation_status": verification.route_isolation_status,
        "route_run_status": verification.route_run_status, "main_run_status": verification.main_run_status,
        "gap_bridge_status": verification.gap_bridge_status, "segment_count": len(geometry),
    }
    candidate = ReviewCandidate(
        span_id=verification.span_id, start_station=span.start_station, end_station=span.end_station,
        source_file=span.source_file, source_citation=span.citation, source_kind=span.source_kind,
        confidence=span.confidence,
        start_anchor_summary=verification.start_anchor_summary,
        end_anchor_summary=verification.end_anchor_summary,
        route_summary=route_summary, route_geometry=geometry, candidate_status=REVIEW_CANDIDATE_READY,
        artifact_before=before, artifact_after=after, stroke_rgb=REVIEW_STROKE_RGB,
        evidence_chain=_evidence_chain(status, span, binding, verification, geometry, generated))
    return ReviewCandidateReport(readiness_status=status, candidate_status=REVIEW_CANDIDATE_READY,
                                 candidates=(candidate,), refusal_reason=None, generated_visual=generated,
                                 detail={"gated_on": READY_FOR_REVIEW_REDLINE})


# ======================================================================================================== #
# Seam 5 — the end-to-end runner (readiness spine -> candidate) + harness CLI.
# ======================================================================================================== #
def run_candidate_for_package(package_dir, *, plan_sheet: int = 1,
                              artifact_dir=None) -> ReviewCandidateReport:
    """End-to-end: discover the package, run the read-only readiness spine, then build a REVIEW candidate ONLY
    when it returns READY_FOR_REVIEW_REDLINE. Read-only wrt the product; draws only the REVIEW candidate overlay
    (when ``artifact_dir`` is given), never a placement / AUTO / status change."""
    from truelinev2.harness.readiness_source import discover_package
    from truelinev2.harness.route_verification import run_package_route_readiness

    source = discover_package(package_dir)
    readiness = run_package_route_readiness(package_dir, plan_sheet=plan_sheet)
    if readiness is None:
        return _refused("SOURCE_UNRESOLVED", extra="no package readiness resolved")
    return build_review_candidate(readiness, plan_path=source.plan_path, artifact_dir=artifact_dir)


def main(argv: Optional[list] = None) -> int:
    """``python -m truelinev2.harness.review_candidate <package_dir> [<artifact_dir>]`` — run the readiness spine
    over a package and (only when READY) build a REVIEW candidate, writing before/after overlay PNGs into
    ``artifact_dir`` when given. Prints the JSON report. Draws only the REVIEW candidate overlay; no AUTO /
    placement / status change."""
    import json
    import sys
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        sys.stderr.write("usage: review_candidate <package_dir> [<artifact_dir>]\n")
        return 2
    artifact_dir = args[1] if len(args) > 1 else None
    report = run_candidate_for_package(args[0], artifact_dir=artifact_dir)
    print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
