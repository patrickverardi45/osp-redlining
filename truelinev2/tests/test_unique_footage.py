"""M7 — translation-invariant unique-footage matching (generic core fallback).

Asserts: unique footage candidate -> REVIEW (never AUTO); 0 -> abstain; >=2 -> abstain;
existing absolute-start placements unchanged (primary path, fallback not reached);
ambiguity (tied chains) is NOT overridden by the fallback. No convention names appear
(the no-convention-leakage guard enforces the core stays clean).
"""
from __future__ import annotations

from truelinev2.match.engine import run_match
from truelinev2.match.overlap import decide_by_unique_footage
from truelinev2.schema.models import Bore, Callout, PlacementStatus
from truelinev2.stations import feet_to_station


def _c(sheet: int, f0: float, f1: float) -> Callout:
    return Callout(sheet=sheet, page=sheet, from_sta=feet_to_station(f0), to_sta=feet_to_station(f1),
                   from_ft=f0, to_ft=f1, footage=round(f1 - f0, 2), text="x", dialect="test")


def _bore(start_ft: float, end_ft: float, sheets) -> Bore:
    return Bore(bore_id="logT", source_file="logT.xlsx", sheet_refs=list(sheets),
                station_start=feet_to_station(start_ft), station_end=feet_to_station(end_ft),
                station_start_ft=start_ft, station_end_ft=end_ft, span_ft=round(end_ft - start_ft, 2))


class _StubDialect:
    """Minimal footage dialect for engine integration tests (no PDF needed)."""
    name = "test"
    match_mode = "footage"

    def __init__(self, callouts):
        self._c = callouts

    def extract_callouts(self, plan, sheet, offset):
        return [c for c in self._c if c.sheet == sheet]


# --- decider unit tests ---

def test_unique_footage_candidate_reviews():
    d = decide_by_unique_footage([_c(7, 4000, 4416)], 416.0)
    assert d["status"] == "REVIEW" and d["reason"] == "FOOTAGE_UNIQUE_FRAME_UNCONFIRMED"
    assert d["winner"][0].sheet == 7
    assert "ABSOLUTE_FRAME_UNCONFIRMED" in d["caveats"]


def test_zero_candidates_abstain():
    d = decide_by_unique_footage([_c(7, 4000, 4100)], 416.0)  # footage 100, far from 416
    assert d["status"] == "ABSTAIN" and d["reason"] == "NO_FOOTAGE_UNIQUE_CANDIDATE"
    assert d["winner"] is None


def test_two_candidates_abstain():
    d = decide_by_unique_footage([_c(7, 4000, 4416), _c(8, 5000, 5416)], 416.0)  # both footage 416
    assert d["status"] == "ABSTAIN" and d["reason"] == "AMBIGUOUS_FOOTAGE_CANDIDATES"
    assert d["winner"] is None


# --- engine integration ---

def test_engine_fallback_reviews_local_frame_unique():
    # bore logged 0..416 (local frame); only callout is absolute 4000..4416 (footage 416).
    # No chain starts (4000 not within 8 ft of 0) -> fallback -> REVIEW.
    pl = run_match(_bore(0, 416, [7]), None, _StubDialect([_c(7, 4000, 4416)]), 0)
    assert pl.status == PlacementStatus.REVIEW
    assert pl.reason == "FOOTAGE_UNIQUE_FRAME_UNCONFIRMED"
    assert pl.sheets == [7] and pl.footage == 416.0


def test_engine_two_footage_candidates_abstains():
    pl = run_match(_bore(0, 416, [7, 8]),
                   None, _StubDialect([_c(7, 4000, 4416), _c(8, 5000, 5416)]), 0)
    assert pl.status == PlacementStatus.ABSTAIN


def test_engine_absolute_start_still_uses_primary_unchanged():
    # callout at the bore's ABSOLUTE start with exact footage+endpoints -> primary AUTO,
    # the fallback is never reached (proves existing placements are unchanged).
    pl = run_match(_bore(0, 299, [8]), None, _StubDialect([_c(8, 0, 299)]), 0)
    assert pl.status == PlacementStatus.AUTO_SELECT
