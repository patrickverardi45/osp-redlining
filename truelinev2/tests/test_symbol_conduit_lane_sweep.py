"""M8.14.c Phase 1 -- tests pinning the all-58 census sweep helpers (offline).

The live census (counts, eligibility, errors) is regression-pinned by the
sweep's own embedded gates G1-G7. These offline tests lock the pure reporting
contract: the banked census is internally consistent (sums to 58, eligible/
error id-sets match their counts), the markdown summary names the required
sections and never silently promotes a newly-surfaced bore to GRADED, and the
log-number parser is correct."""
from __future__ import annotations

from truelinev2.proof.run_brenham_corpus import EXPECTED_COUNT
from truelinev2.proof.run_symbol_conduit_lane_sweep import (
    EXPECT_CENSUS,
    EXPECT_ELIGIBLE,
    EXPECT_SOURCE_ERR,
    GRADED,
    S_ELIGIBLE,
    S_PICK,
    S_SOURCE_ERR,
    _markdown,
    _num,
)


def test_banked_census_sums_to_corpus():
    assert sum(EXPECT_CENSUS.values()) == EXPECTED_COUNT == 58


def test_eligible_and_error_idsets_match_counts():
    assert len(EXPECT_ELIGIBLE) == EXPECT_CENSUS[S_ELIGIBLE]
    assert len(EXPECT_SOURCE_ERR) == EXPECT_CENSUS[S_SOURCE_ERR]
    assert EXPECT_ELIGIBLE.isdisjoint(EXPECT_SOURCE_ERR)
    # M8.14.c.2 adherence law: log7 (graded under the old chord geometry) is
    # NO LONGER eligible -- its conduit environment carries 4 physically
    # distinct strands and the lane never picks one. The documented law cost.
    assert GRADED - EXPECT_ELIGIBLE == {"log7"}
    assert GRADED & EXPECT_ELIGIBLE == {"log51", "log65"}


def test_design_grade_census_is_formal():
    from truelinev2.proof.run_symbol_conduit_lane_sweep import DESIGN_GRADED
    # All eligible design-path strokes are GRADED PASS (route adherence accepted).
    assert DESIGN_GRADED == EXPECT_ELIGIBLE
    assert EXPECT_ELIGIBLE - DESIGN_GRADED == set()


def test_num_parses_log_number():
    class _P:
        def __init__(self, stem):
            self.stem = stem
    assert _num(_P("bore_log7")) == 7
    assert _num(_P("bore_log51")) == 51
    assert _num(_P("bore_log37")) == 37


def test_markdown_names_sections_and_reports_zero_grading_debt():
    rows = [
        {"bore_id": "log65", "status": S_ELIGIBLE},
        {"bore_id": "log25", "status": S_ELIGIBLE},
        {"bore_id": "log59", "status": S_ELIGIBLE},
        {"bore_id": "log51", "status": S_ELIGIBLE},
        {"bore_id": "log50", "status": S_PICK},
    ]
    md = _markdown(dict(EXPECT_CENSUS), rows)
    assert "all-58 census" in md
    for section in ("Stroke-eligible", "Pick-card candidates",
                    "Common blockers", "Recommended next gate"):
        assert section in md, section
    # All four accepted grades are named; the awaiting-re-grade census is empty.
    accepted_line = next(l for l in md.splitlines()
                         if "GRADED PASS (route adherence ACCEPTED" in l)
    assert all(bid in accepted_line
               for bid in ("log25", "log51", "log59", "log65"))
    pending_line = next(l for l in md.splitlines()
                        if "awaiting re-grade" in l)
    assert pending_line.endswith("none")
    assert not any(bid in pending_line
                   for bid in ("log25", "log51", "log59", "log65"))
