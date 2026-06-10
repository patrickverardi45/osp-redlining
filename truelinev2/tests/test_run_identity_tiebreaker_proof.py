"""M8.3a -- pure tests for the run-identity tiebreaker helpers (no PDF, no engine).

Locks: near-duplicate collapse groups precision-spread readings of one physical
route (the log48 shape: 5 candidates -> 2 routes); exactly-one-survivor is the ONLY
auto-resolution and is REVIEW-gated; >=2 distinct routes are NEVER auto-picked
(human pick-card when corridors differ); conduit VACANT-ness is not an identity
break; street/structure token extraction is deterministic.
"""
from __future__ import annotations

from truelinev2.proof.run_identity_tiebreaker import (
    PRECISION_BAND_FT,
    BoxRead,
    RouteProfile,
    chains_equivalent,
    collapse_near_duplicates,
    conduit_uniform,
    decide_tiebreak,
    street_tokens,
    structure_tokens,
)


def _b(sheet, f0, f1, conduit='1-1.25" HDPE'):
    return BoxRead(sheet=sheet, from_ft=f0, to_ft=f1, conduit=conduit)


# The log48 shape: 5 raw candidates = 2 physical routes (3 readings + 2 readings)
_R10A = _b(10, 0, 190)
_R10B = _b(10, 0, 191)
_S12_A = [_R10A, _b(12, 191, 355), _b(12, 355, 510, '1-1.25" VACANT HDPE')]
_S12_B = [_R10B, _b(12, 190, 350), _b(12, 350, 507, '1-1.25" VACANT HDPE')]
_S12_C = [_R10A, _b(12, 190, 350), _b(12, 350, 507, '1-1.25" VACANT HDPE')]
_S11_A = [_R10A, _b(11, 189, 514, '1-1.25" VACANT HDPE')]
_S11_B = [_R10B, _b(11, 189, 514, '1-1.25" VACANT HDPE')]


def test_log48_shape_collapses_five_to_two():
    groups = collapse_near_duplicates([_S12_A, _S12_B, _S12_C, _S11_A, _S11_B])
    assert len(groups) == 2
    assert sorted(len(g) for g in groups) == [2, 3]


def test_chains_equivalent_within_band_only():
    assert chains_equivalent(_S12_A, _S12_B) is True          # 1-5 ft spreads
    assert chains_equivalent(_S12_A, _S11_A) is False         # different sheets/shape
    far = [_R10A, _b(12, 191, 355), _b(12, 355, 510 + PRECISION_BAND_FT + 1,
                                       '1-1.25" VACANT HDPE')]
    assert chains_equivalent(_S12_A, far) is False            # beyond the band


def test_collapse_to_single_route_when_only_readings_differ():
    groups = collapse_near_duplicates([_S12_A, _S12_B, _S12_C])
    assert len(groups) == 1 and len(groups[0]) == 3


def test_vacant_is_not_an_identity_break():
    assert conduit_uniform(_S12_A) is True   # HDPE -> HDPE -> VACANT HDPE = one family
    mixed = [_b(1, 0, 100, '1-1.25" HDPE'), _b(1, 100, 200, '2-1.25" HDPE')]
    assert conduit_uniform(mixed) is False   # size change IS an identity break


def test_street_tokens_extraction():
    assert street_tokens(["E", "TOM", "GREEN", "ST"]) == ["TOM GREEN ST"]
    assert street_tokens(["MAE", "WAY", "POTHOLE"]) == ["MAE WAY"]
    assert street_tokens(["DEPTH", "BORE", "VACANT"]) == []


def test_structure_tokens_extraction():
    toks = structure_tokens(["FLOWER", "POT", "VACANT", "AP-164", "TERMINAL"])
    assert "FLOWER POT" in toks and "AP-" in toks and "TERMINAL" in toks
    assert structure_tokens(["DEPTH", "ROW"]) == []


def _profile(corridors):
    return RouteProfile(signature=((1, 0, 1),), corridors=corridors)


def test_single_survivor_is_ready_and_review_gated():
    v = decide_tiebreak([_profile(["A ST"])])
    assert v["verdict"] == "TIEBREAKER_PROOF_READY_FOR_OPT_IN"
    assert v["recovery"] == "REVIEW"  # never AUTO via a new rule


def test_two_distinct_routes_never_auto_picked():
    v = decide_tiebreak([_profile(["LEDBETTER ST"]), _profile(["TOM GREEN ST"])])
    assert v["verdict"] == "TIEBREAKER_NOT_READY"
    assert v["survivor"] is None
    assert v["recovery"] == "HUMAN_PICK_CARD"


def test_two_routes_same_corridor_needs_more_evidence():
    v = decide_tiebreak([_profile(["A ST"]), _profile(["A ST"])])
    assert v["verdict"] == "TIEBREAKER_NOT_READY" and v["recovery"] == "MORE_EVIDENCE"


def test_no_profiles_is_missing_evidence():
    assert decide_tiebreak([])["verdict"] == "MISSING_IDENTITY_EVIDENCE"
