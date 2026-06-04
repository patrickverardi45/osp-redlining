"""Day-1 STUB selector.

Returns a contract-valid ``EngineResult`` for one PROVEN Path-12 log (log51) to
validate the pipeline end-to-end. This is NOT the real selector — it parses no
PDF and no bore log; it hard-codes the proven log51 AUTO_SELECT result.

Guarantees:
  * never raises to the caller — any failure becomes a FAIL_SAFE / ERROR result;
  * no ``fitz`` import (only pdf/ touches fitz);
  * no coordinate-snapping / route scoring.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from ..contracts import (
    Callout,
    EngineResult,
    Evidence,
    FailSafeItem,
    SelectedSegment,
    StationSpan,
    ENGINE_VERSION,
    RENDER_TARGET_EVIDENCE_CARD,
    STATUS_FAIL_SAFE_GLOBAL,
    STATUS_OK,
    TIER_AUTO_SELECT,
    TIER_FAIL_SAFE,
    error_result,
)

SHEET_OFFSET = 13  # page = sheet + 13

# Proven Path-12 AUTO_SELECT log used as the Day-1 pipeline fixture.
_LOG51 = {
    "print": "Jersey Ln",
    "sheet": 8,
    "span": ("0+00", "2+99"),
    "footage": 299.0,
    "conduit": '1-1.25" HDPE',
    "end_structures": ["Jersey Ln"],
    "callout_text": "STA 0+00 TO STA 2+99 DIR. BORE (299')",
}


def _build_log51_segment() -> SelectedSegment:
    span = StationSpan(start=_LOG51["span"][0], end=_LOG51["span"][1])
    callout = Callout(
        text=_LOG51["callout_text"],
        kind="DIR_BORE",
        sheet=_LOG51["sheet"],
        page=_LOG51["sheet"] + SHEET_OFFSET,
        station_span=span,
        footage=_LOG51["footage"],
        conduit=_LOG51["conduit"],
        bbox_display=None,  # Day-1 stub: real de-rotated bbox arrives via pdf/text_extract (Day 2+)
        visually_verified=True,
    )
    evidence = Evidence(
        funnel_path=["print", "sheet", "station_band", "dir_bore", "end_structure"],
        matched_on=["Print", "Station", "Structure"],
        footage_check={"authored": 299.0, "bore_log": 299.0, "delta": 0.0},
        tiebreaker=None,
        callout_ids=["0"],
        notes="Day-1 stub fixture (Path-12 proven AUTO_SELECT). NOT produced by the real selector.",
    )
    return SelectedSegment(
        segment_id="log51",
        log_ids=["log51"],
        tier=TIER_AUTO_SELECT,
        print=_LOG51["print"],
        sheets=[_LOG51["sheet"]],
        station_span=span,
        footage=_LOG51["footage"],
        end_structures=list(_LOG51["end_structures"]),
        conduit=_LOG51["conduit"],
        callouts=[callout],
        evidence=evidence,
        render_target=RENDER_TARGET_EVIDENCE_CARD,
        caveat=None,
        requires_approval=False,
    )


def run_stub(log_id: str = "log51",
             source: Optional[Dict[str, Any]] = None) -> EngineResult:
    """Return a contract-valid EngineResult for the requested stub log."""
    job_id = f"stub-{log_id}"
    try:
        if log_id != "log51":
            # Honest FAIL_SAFE — no fabricated placement for an unknown stub target.
            return EngineResult(
                job_id=job_id,
                status=STATUS_FAIL_SAFE_GLOBAL,
                source=source or {"stub": True, "log_id": log_id},
                fail_safe_items=[FailSafeItem(
                    log_ids=[log_id],
                    reason="NO_STUB_FIXTURE_FOR_LOG",
                    candidates=[],
                )],
                evidence={"stub": True, "note": f"no Day-1 stub fixture for {log_id!r}"},
                warnings=[f"no stub fixture for {log_id!r}"],
            )
        return EngineResult(
            job_id=job_id,
            status=STATUS_OK,
            engine_version=ENGINE_VERSION,
            source=source or {
                "stub": True,
                "log_id": log_id,
                "note": "Day-1 stub; no PDF/bore-log parsed",
            },
            selected_segments=[_build_log51_segment()],
            review_items=[],
            fail_safe_items=[],
            evidence={"stub": True, "pipeline": "day1", "proven_log": "log51"},
        )
    except Exception as exc:  # never crash the caller
        return error_result(job_id, f"{type(exc).__name__}: {exc}", source)
