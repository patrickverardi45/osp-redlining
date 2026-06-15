"""OWNER-PACKET-2 near-miss sheet-locator scout -- offline tests.

Locks the scout's pure logic (the heavy read-only PDF recovery is verified by running the proof):
the result enum; the near-miss set is now EMPTY (log59/log66 promoted, log36 bridged-but-held-back ->
every NO_RECORDED_SHEET near-miss is bridged out); the same-frame span<->footage consistency check;
the safety ranking over the empty near-miss set is empty; the cohort SOURCE_BINDABLE_NOW set (6) is a
superset of the seam eligible set (5) with log36 the held-back gap; log36 now carries an endpoint-anchor
bridge but corrected_sheets stays [] (held back); the reject-reason helper always names a category; and
the scout reuses the canonical classifier rather than defining a new one. No PDF parse here.
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


def test_near_miss_set_is_empty_all_bridged_out():
    # log59 + log66 (promoted) + log36 (bridged-but-held-back) all moved to SOURCE_BINDABLE_NOW;
    # no NO_RECORDED_SHEET REPRESENTATIVE_ROUTE_CANDIDATE near-miss remains.
    canonical = sorted(
        r["log_id"] for r in DOC["logs"]
        if classify_record(r)["classification"] == REPRESENTATIVE_ROUTE_CANDIDATE
        and NO_RECORDED_SHEET in classify_record(r)["blockers"])
    assert canonical == sorted(NEAR_MISSES) == []
    assert set(NEAR_MISS_SIG) == set(NEAR_MISSES) == set()


def test_span_footage_consistency_check():
    # same-frame endpoints must be exactly <footage> apart (log59: 446-276=170; log36: 145-56=89)
    assert span_consistent(("2+76", "4+46"), 170) is True
    assert span_consistent(("0+56", "1+45"), 89) is True
    assert span_consistent(None, 55) is True                 # different reset frames -> no span check
    assert span_consistent(("2+76", "4+46"), 999) is False   # inconsistent span is rejected


def test_near_miss_sigs_when_present_are_owner_named_modeled_classes():
    # NEAR_MISS_SIG is empty now (all near-misses bridged); the loop locks the invariant for any
    # FUTURE near-miss sig: both endpoints must be owner-named modeled classes.
    assert NEAR_MISS_SIG == {}
    for lid in NEAR_MISSES:
        sig = NEAR_MISS_SIG[lid]
        assert sig["start"]["cls"] in MODELED and sig["end"]["cls"] in MODELED


def test_safety_rank_over_empty_near_miss_set_is_empty():
    ranked = sorted(NEAR_MISSES, key=lambda l: _safety_rank(l, REC))
    assert ranked == []                                      # all near-misses bridged out -> nothing to rank


def test_cohort_superset_of_seam_and_held_back_log36_refused():
    source_bindable_now = sorted(c["log_id"] for c in (classify_record(r) for r in DOC["logs"])
                                 if c["classification"] == "SOURCE_BINDABLE_NOW")
    # log36 bridged-but-held-back: cohort SOURCE_BINDABLE_NOW (6) > seam eligible (5); log36 is the gap
    assert source_bindable_now == ["log36", "log53", "log59", "log64", "log66", "log71"]
    assert tuple(ELIGIBLE_EXEMPLARS) == ("log53", "log64", "log71", "log59", "log66")
    # the held-back log36 (anchored, corrected_sheets []) is still seam-REFUSED
    try:
        build_seam_payload("log36", REC["log36"])
        assert False, "log36 (held back) must not be seam-eligible"
    except ValueError:
        pass


def test_log36_bridged_but_owner_sheet_still_blank():
    # log36 now carries an endpoint-anchor bridge (anchored) but the owner-review sheet stays blank
    # (corrected_sheets [], NOT owner-confirmed) -> held back, still seam-refused
    assert REC["log36"].get("endpoint_anchors")
    assert REC["log36"].get("corrected_sheets") == []


def test_reject_reason_always_names_a_category():
    # log36 recoverable-but-deferred reason names the category + calls out the reset-station collision
    r36 = _reject_reason("log36", {"uniquely_recovered": True, "recovered_sheet": 17}, REC["log36"])
    assert r36["blocker_category"] == "recoverable_but_deferred_lower_priority_variant"
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
