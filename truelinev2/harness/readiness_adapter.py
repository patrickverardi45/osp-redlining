"""End-to-end READ-ONLY package readiness runner: the thin adapter that turns the hand-fed classifier into a
package -> readiness report pipeline. Name-free, harness-only.

Seams (kept cleanly separated; this module owns 2 and the composition, and reuses 3 + 4):
  1. package discovery / input loading   -> ``readiness_source.discover_package`` / ``resolve_case_dir``
  2. observer evidence normalization      -> ``evidence_from_findings`` (recorded) / ``evidence_from_live_observers``
  3. readiness classification             -> ``review_readiness.classify_review_readiness``
  4. report serialization                 -> ``review_readiness.format_report``

It draws nothing, places nothing, promotes nothing, and imports NOTHING from render / placement / api / store /
contracts / product runtime. The live-observer normalization lazily imports only the read-only dialect selector +
plan reader; the classifier's KEEP_BLOCKED is only ever produced from an explicit owner/adversarial marker carried
in the recorded findings — never derived autonomously here.
"""
from __future__ import annotations

import json
from typing import Any, Dict, Optional, Sequence

from truelinev2.harness.readiness_source import (
    ObserverFindings,
    PackageSource,
    SOURCE_NOT_FOUND,
    discover_package,
    resolve_case_dir,
)
from truelinev2.harness.review_readiness import (
    AnchorEvidence,
    ReviewReadinessEvidence,
    ReviewReadinessReport,
    RouteEvidence,
    SpanSourceEvidence,
    classify_review_readiness,
    format_report,
)

FINDINGS_ORIGIN_RECORDED = "recorded"
FINDINGS_ORIGIN_LIVE = "live"


# ======================================================================================================== #
# Seam 2 — observer evidence normalization.
# ======================================================================================================== #
def evidence_from_findings(package_id, findings: ObserverFindings) -> ReviewReadinessEvidence:
    """Pure transform: recorded ``ObserverFindings`` -> ``ReviewReadinessEvidence``. Anchor / route stages stay
    unevaluated (None) when their status strings are absent, so the classifier stops honestly upstream."""
    span = SpanSourceEvidence(
        bore_span_source_files=tuple(findings.span_source_files),
        plan_span_layer_inspected=findings.plan_span_layer_inspected,
        source_confirmed_span_count=findings.source_confirmed_span_count)
    anchor = (AnchorEvidence(start_status=findings.anchor_start_status, end_status=findings.anchor_end_status)
              if (findings.anchor_start_status and findings.anchor_end_status) else None)
    route = RouteEvidence(status=findings.route_status) if findings.route_status else None
    detail = dict(findings.detail)
    detail["findings_origin"] = FINDINGS_ORIGIN_RECORDED
    return ReviewReadinessEvidence(
        package_id=package_id, plan_readable=findings.plan_readable, recognized=findings.recognized,
        keep_blocked=findings.keep_blocked, keep_blocked_reason=findings.keep_blocked_reason,
        span=span, anchor=anchor, route=route, detail=detail)


def evidence_from_live_observers(source: PackageSource) -> Optional[ReviewReadinessEvidence]:
    """Fresh-package seam: read the signals a plan yields directly today — recognition (``select_dialect``) and
    readability (a text-layer probe) — leaving span / anchor / route unevaluated so the classifier returns the
    honest current verdict (no confirmed span yet). Lazily imports ONLY the read-only dialect selector + plan
    reader; imports nothing from render / placement / api / store / contracts. Returns None when there is no
    readable plan. Richer live span / anchor / route normalization is wired here as real complete packages arrive.
    """
    if not source.plan_path:
        return None
    from truelinev2.extract.registry import select_dialect     # read-only dialect detection
    from truelinev2.ingest.pdf import PlanPdf                   # read-only plan reader
    plan = None
    try:
        plan = PlanPdf(str(source.plan_path))
        recognized = select_dialect(plan) is not None
        plan_readable = _plan_has_text(plan)
    except Exception:
        return None
    finally:
        try:
            if plan is not None:
                plan.close()
        except Exception:
            pass
    return ReviewReadinessEvidence(
        package_id=source.package_id, plan_readable=plan_readable, recognized=recognized,
        span=SpanSourceEvidence(bore_span_source_files=(), plan_span_layer_inspected=False,
                                source_confirmed_span_count=0),
        detail={"findings_origin": FINDINGS_ORIGIN_LIVE,
                "live_span_anchor_route": "pending_real_package_validation",
                "borelog_present": source.borelog_present})


def _plan_has_text(plan) -> bool:
    """True iff any page of the plan yields extractable text (a text-layer probe; else OCR is required)."""
    try:
        for idx in range(int(plan.page_count)):
            if plan.text_by_index(idx).strip():
                return True
    except Exception:
        return False
    return False


# ======================================================================================================== #
# Composition — seams 1 -> 2 -> 3 (classify). Seam 4 is format_report / to_dict.
# ======================================================================================================== #
def run_readiness(source: PackageSource, *, allow_live: bool = False) -> Optional[ReviewReadinessReport]:
    """Route a resolved ``PackageSource`` to a readiness report. Prefers recorded findings ("observer outputs
    where already available"); falls back to live normalization only when ``allow_live`` is set. Returns None
    when neither is available."""
    if source.findings is not None:
        evidence: Optional[ReviewReadinessEvidence] = evidence_from_findings(source.package_id, source.findings)
    elif allow_live:
        evidence = evidence_from_live_observers(source)
    else:
        evidence = None
    if evidence is None:
        return None
    return classify_review_readiness(evidence)


def run_readiness_for_folder(package_dir, *, allow_live: bool = False) -> Optional[ReviewReadinessReport]:
    """Discover a package folder (seam 1) and route it to a readiness report."""
    source = discover_package(package_dir)
    if source.kind == SOURCE_NOT_FOUND and source.findings is None:
        return None
    return run_readiness(source, allow_live=allow_live)


def run_readiness_for_case(case_id, cold_packages_root, *, allow_live: bool = False
                           ) -> Optional[ReviewReadinessReport]:
    """Resolve a case reference under an INJECTED cold-packages root and route it to a readiness report."""
    return run_readiness_for_folder(resolve_case_dir(case_id, cold_packages_root), allow_live=allow_live)


def format_readiness(report: ReviewReadinessReport) -> str:
    """Seam 4 — concise JSON serialization (delegates to the classifier's formatter)."""
    return format_report(report)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Harness-only diagnostic CLI: ``python -m truelinev2.harness.readiness_adapter <package_dir> [--live]``.
    Discovers the package, routes it through the classifier, prints the JSON report. Writes nothing, draws
    nothing."""
    import sys
    args = list(sys.argv[1:] if argv is None else argv)
    allow_live = "--live" in args
    positional = [a for a in args if not a.startswith("--")]
    if not positional:
        sys.stderr.write("usage: readiness_adapter <package_dir> [--live]\n")
        return 2
    report = run_readiness_for_folder(positional[0], allow_live=allow_live)
    if report is None:
        print(json.dumps({"status": "SOURCE_UNRESOLVED",
                          "note": "no recorded observer_findings.json and live normalization not enabled "
                                  "(pass --live with a readable plan)"}, indent=2, sort_keys=True))
        return 0
    print(format_readiness(report))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
