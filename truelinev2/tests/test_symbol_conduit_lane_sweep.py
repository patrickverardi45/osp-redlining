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
    # every graded bore is in the eligible set (graded => eligible, not reverse)
    assert GRADED <= EXPECT_ELIGIBLE


def test_newly_surfaced_are_eligible_minus_graded():
    new = EXPECT_ELIGIBLE - GRADED
    assert new == {"log25", "log59"}  # the bores needing Patrick's grade


def test_num_parses_log_number():
    class _P:
        def __init__(self, stem):
            self.stem = stem
    assert _num(_P("bore_log7")) == 7
    assert _num(_P("bore_log51")) == 51
    assert _num(_P("bore_log37")) == 37


def test_markdown_names_sections_and_separates_graded_from_new():
    rows = [
        {"bore_id": "log7", "status": S_ELIGIBLE},
        {"bore_id": "log65", "status": S_ELIGIBLE},
        {"bore_id": "log25", "status": S_ELIGIBLE},   # newly surfaced
        {"bore_id": "log59", "status": S_ELIGIBLE},   # newly surfaced
        {"bore_id": "log51", "status": S_ELIGIBLE},
        {"bore_id": "log50", "status": S_PICK},
    ]
    md = _markdown(dict(EXPECT_CENSUS), rows)
    assert "all-58 census" in md
    for section in ("Stroke-eligible", "Pick-card candidates",
                    "Common blockers", "Recommended next gate"):
        assert section in md, section
    # newly-surfaced bores are flagged, never folded into GRADED
    assert "log25" in md and "log59" in md
    graded_line = next(l for l in md.splitlines() if "GRADED PASS" in l)
    assert "log25" not in graded_line and "log59" not in graded_line
    new_line = next(l for l in md.splitlines() if "NEWLY SURFACED" in l)
    assert "log25" in new_line and "log59" in new_line
