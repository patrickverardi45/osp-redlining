"""OWNER-PACKET-2 next eligibility-growth scout -- offline tests.

Locks the scout's pure logic: it classifies exactly the 19 pending no-anchor logs (reusing the
CANONICAL cohort classifier, not a new one); the existing eligible set stays exactly log53/log64/
log71 and the seam contract refuses every pending log (no promotion); the honest verdict is
NO_SAFE_NEXT_ELIGIBILITY_CANDIDATE because every recorded-sheet modeled-terminus log is multi-sheet
(cross-sheet) and every clean single-area structure-to-structure log with named endpoints has no
recorded sheet; and -- the key NEGATIVE CONTROL -- is_eligibility_ready returns True for a synthetic
single-sheet structure-to-structure log, so the NO_SAFE verdict is a real finding, not a function
that can never say yes. No PDF parse here.
"""
from pathlib import Path

from truelinev2.ingest.manual_adjudication import load_adjudication
from truelinev2.proof.run_log53_primitives_cohort_replay import (
    PARTIAL_SOURCE_BINDABLE,
    REPRESENTATIVE_ROUTE_CANDIDATE,
    classify_record,
)
from truelinev2.proof.run_next_eligibility_growth_scout import (
    ALLOWED,
    CAT_NO_SHEET,
    R_NONE,
    R_SELECTED,
    blocker_categories,
    is_eligibility_ready,
    pending_logs,
)
from truelinev2.seam import ELIGIBLE_EXEMPLARS, build_seam_payload

DOC = load_adjudication()
REC = {r["log_id"]: r for r in DOC["logs"]}
PENDING = pending_logs(DOC)


def test_result_enum():
    assert ALLOWED == {
        "NEXT_ELIGIBILITY_GROWTH_SCOUT_PASS",
        "NO_SAFE_NEXT_ELIGIBILITY_CANDIDATE",
        "BLOCKED_NEXT_ELIGIBILITY_INVARIANT_VIOLATED",
    }
    assert R_SELECTED == "NEXT_ELIGIBILITY_GROWTH_SCOUT_PASS"
    assert R_NONE == "NO_SAFE_NEXT_ELIGIBILITY_CANDIDATE"


def test_pending_is_eighteen_no_anchor_logs():
    # 19 minus log59 (its source-recovered endpoint-anchor bridge moved it to SOURCE_BINDABLE_NOW)
    assert len(PENDING) == 18
    assert "log59" not in {r["log_id"] for r in PENDING}
    for r in PENDING:
        assert not r.get("endpoint_anchors")
        assert not r.get("must_remain_abstained")
        assert not r.get("needs_source_verification")


def test_no_safe_candidate_over_real_data():
    # every pending log fails at least one of the eight criteria -> NO_SAFE
    assert not any(is_eligibility_ready(r, DOC) for r in PENDING)


def test_eligible_set_unchanged_and_seam_refuses_pending():
    source_bindable_now = sorted(c["log_id"] for c in (classify_record(r) for r in DOC["logs"])
                                 if c["classification"] == "SOURCE_BINDABLE_NOW")
    # cohort SOURCE_BINDABLE_NOW grew by log59's bridge; the SEAM eligible set stays frozen at 3
    assert source_bindable_now == ["log53", "log59", "log64", "log71"]
    assert tuple(ELIGIBLE_EXEMPLARS) == ("log53", "log64", "log71")
    # the seam contract refuses every pending log -> no code promotion
    for r in PENDING:
        try:
            build_seam_payload(r["log_id"], r)
            assert False, f"{r['log_id']} must not be seam-eligible"
        except ValueError:
            pass


def test_recorded_sheet_modeled_candidates_are_all_multi_sheet():
    # every PARTIAL_SOURCE_BINDABLE (modeled terminus + recorded sheet) is multi-sheet -> cross-sheet
    partials = [classify_record(r) for r in PENDING
                if classify_record(r)["classification"] == PARTIAL_SOURCE_BINDABLE]
    assert partials, "expected the 8 PARTIAL_SOURCE_BINDABLE logs"
    assert all(c["signals"]["n_sheets"] >= 2 for c in partials)


def test_near_misses_are_named_endpoints_missing_only_a_sheet():
    near = [r["log_id"] for r in PENDING
            if classify_record(r)["classification"] == REPRESENTATIVE_ROUTE_CANDIDATE
            and CAT_NO_SHEET in blocker_categories(r, classify_record(r), DOC)]
    # log59 left the trio (its bridge moved it to SOURCE_BINDABLE_NOW); log66/log36 remain
    assert set(near) == {"log66", "log36"}
    for lid in near:
        sig = classify_record(REC[lid])["signals"]
        assert sig["modeled_terminus_classes"]          # endpoints are modeled/named
        assert sig["n_sheets"] == 0                      # but no recorded sheet to bind on


def test_every_pending_has_a_named_blocker_category():
    for r in PENDING:
        cats = blocker_categories(r, classify_record(r), DOC)
        assert cats, f"{r['log_id']} must carry >= 1 named blocker category"


def test_is_eligibility_ready_negative_control_accepts_a_qualifying_log():
    # NEGATIVE CONTROL: a synthetic single-sheet structure-to-structure log with both endpoints named
    # and no OCR/parent/sibling/review MUST be accepted -- proving NO_SAFE is a real finding, not a
    # function that can never return True.
    synthetic = {
        "log_id": "logSYN", "parent": None, "shared_print_child": False, "status": "RECOVERED",
        "correction_types": ["DIRECT_BORE_CALLOUT", "LEADER_LINE_TO_STRUCTURE"],
        "corrected_start": "2+76", "corrected_end": "4+46", "corrected_sheets": [21], "span_ft": 170.0,
        "evidence_notes": "Start at STA 2+76 INSTALLER HH; end at STA 4+46 FLOWER POT; direct bore.",
        "allowed_to_draw": True, "must_remain_abstained": False, "needs_review": False,
        "needs_source_verification": False, "endpoint_anchors": None,
    }
    assert is_eligibility_ready(synthetic, DOC) is True
    # the same log made MULTI-SHEET is rejected (cross-sheet); made SHEETLESS is rejected (no sheet)
    assert is_eligibility_ready({**synthetic, "corrected_sheets": [21, 22],
                                 "correction_types": [*synthetic["correction_types"], "MATCHLINE_CHAIN"]},
                                DOC) is False
    assert is_eligibility_ready({**synthetic, "corrected_sheets": []}, DOC) is False


def test_scout_reuses_canonical_classifier_no_new_one():
    src = (Path(__file__).resolve().parent.parent / "proof" / "run_next_eligibility_growth_scout.py").read_text(encoding="utf-8")
    assert "from truelinev2.proof.run_log53_primitives_cohort_replay import" in src
    assert "def classify_record" not in src      # must not re-declare the canonical classifier
    assert "def derive_signals" not in src
