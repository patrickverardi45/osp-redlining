"""OWNER-PACKET-2 near-miss sheet-locator scout -- offline tests.

Locks the scout's pure logic (the heavy read-only PDF recovery is verified by running the proof):
the result enum; the near-miss set is exactly the canonical NO_RECORDED_SHEET trio (log59/log66/
log36); the same-frame span<->footage consistency check; both endpoints of every near-miss are
owner-named modeled classes; the safety ranking puts log59 (the log64 shape) first; the eligible set
is unchanged and the seam contract refuses every near-miss; no endpoint_anchors are encoded and the
owner-review sheet stays blank; the reject-reason helper always names a category; and the scout
reuses the canonical classifier rather than defining a new one. No PDF parse here.
"""
from pathlib import Path

from truelinev2.ingest.manual_adjudication import load_adjudication
from truelinev2.proof.run_log53_primitives_cohort_replay import (
    NO_RECORDED_SHEET,
    REPRESENTATIVE_ROUTE_CANDIDATE,
    classify_record,
)
from truelinev2.proof.run_near_miss_sheet_locator_scout import (
    ALLOWED,
    NEAR_MISS_SIG,
    NEAR_MISSES,
    R_NONE,
    R_PASS,
    _reject_reason,
    _safety_rank,
    span_consistent,
)
from truelinev2.extract.structure_position import BRENHAM_STRUCTURE_LAYERS
from truelinev2.seam import ELIGIBLE_EXEMPLARS, build_seam_payload

DOC = load_adjudication()
REC = {r["log_id"]: r for r in DOC["logs"]}
MODELED = set(BRENHAM_STRUCTURE_LAYERS) | {"nextlink_hh"}


def test_result_enum():
    assert ALLOWED == {"SHEET_LOCATOR_SCOUT_PASS", "NO_SAFE_SHEET_LOCATOR_CANDIDATE",
                       "BLOCKED_SHEET_LOCATOR_INVARIANT_VIOLATED"}
    assert R_PASS == "SHEET_LOCATOR_SCOUT_PASS"
    assert R_NONE == "NO_SAFE_SHEET_LOCATOR_CANDIDATE"


def test_near_miss_set_is_the_remaining_no_recorded_sheet_logs():
    # log59 was bridged out (its source-recovered anchors moved it to SOURCE_BINDABLE_NOW); the
    # remaining NO_RECORDED_SHEET near-misses are log66/log36.
    canonical = sorted(
        r["log_id"] for r in DOC["logs"]
        if classify_record(r)["classification"] == REPRESENTATIVE_ROUTE_CANDIDATE
        and NO_RECORDED_SHEET in classify_record(r)["blockers"])
    assert canonical == sorted(NEAR_MISSES) == ["log36", "log66"]
    assert set(NEAR_MISS_SIG) == set(NEAR_MISSES)


def test_span_footage_consistency_check():
    # same-frame endpoints must be exactly <footage> apart (log59: 446-276=170; log36: 145-56=89)
    assert span_consistent(("2+76", "4+46"), 170) is True
    assert span_consistent(("0+56", "1+45"), 89) is True
    assert span_consistent(None, 55) is True                 # different reset frames -> no span check
    assert span_consistent(("2+76", "4+46"), 999) is False   # inconsistent span is rejected


def test_near_miss_endpoints_are_owner_named_modeled_classes():
    for lid in NEAR_MISSES:
        sig = NEAR_MISS_SIG[lid]
        assert sig["start"]["cls"] in MODELED
        assert sig["end"]["cls"] in MODELED
    # log66 (the next pick after log59 bridged out) is installer_hh <-> nextlink_hh
    assert (NEAR_MISS_SIG["log66"]["start"]["cls"], NEAR_MISS_SIG["log66"]["end"]["cls"]) == ("installer_hh", "nextlink_hh")


def test_safety_rank_prefers_log66_after_log59_bridged():
    ranked = sorted(NEAR_MISSES, key=lambda l: _safety_rank(l, REC))
    assert ranked[0] == "log66"                              # log59 bridged out; log66 is next (no reset collision)
    assert ranked == ["log66", "log36"]


def test_eligible_set_unchanged_and_seam_refuses_near_misses():
    source_bindable_now = sorted(c["log_id"] for c in (classify_record(r) for r in DOC["logs"])
                                 if c["classification"] == "SOURCE_BINDABLE_NOW")
    # cohort SOURCE_BINDABLE_NOW grew by log59's bridge; the SEAM eligible set stays at 3
    assert source_bindable_now == ["log53", "log59", "log64", "log71"]
    assert tuple(ELIGIBLE_EXEMPLARS) == ("log53", "log64", "log71")
    for lid in NEAR_MISSES:
        try:
            build_seam_payload(lid, REC[lid])
            assert False, f"{lid} must not be seam-eligible"
        except ValueError:
            pass


def test_no_anchors_and_owner_sheet_still_blank():
    for lid in NEAR_MISSES:
        assert not REC[lid].get("endpoint_anchors")
        assert not REC[lid].get("corrected_sheets")           # owner-review sheet stays blank (not encoded)


def test_reject_reason_always_names_a_category():
    # a recoverable-but-deferred near-miss
    r = _reject_reason("log66", {"uniquely_recovered": True, "recovered_sheet": 10}, REC["log66"])
    assert r["blocker_category"] == "recoverable_but_deferred_lower_priority_variant"
    # log36 deferred reason calls out the reset-station number collision
    r36 = _reject_reason("log36", {"uniquely_recovered": True, "recovered_sheet": 17}, REC["log36"])
    assert "collision" in r36["reason"]
    # a (hypothetical) non-recoverable near-miss -> named blocker category
    nr = _reject_reason("log36", {"uniquely_recovered": False, "recovered_sheet": None,
                                  "footage_sheets": [17], "both_bound_sheets": []}, REC["log36"])
    assert nr["blocker_category"] == "sheet_not_uniquely_recoverable"


def test_scout_reuses_canonical_classifier_no_new_one():
    src = (Path(__file__).resolve().parent.parent / "proof" / "run_near_miss_sheet_locator_scout.py").read_text(encoding="utf-8")
    assert "from truelinev2.proof.run_log53_primitives_cohort_replay import" in src
    assert "def classify_record" not in src
    assert "def derive_signals" not in src
