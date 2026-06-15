"""OWNER-PACKET-2 log53 primitive cohort replay -- offline tests.

Locks: the classification + typed-blocker enums; the five-primitive applicability rules
(never forced); the deterministic per-class decisions on synthetic + real records; the headline
cohort census counts; consistency with the existing placement_geometry_readiness seam; and the
structural no-render guarantee. No PDF parse, no truth table needed (the proof's census-safety
gates run the real truth table when executed).
"""
from pathlib import Path

from truelinev2.extract.structure_position import BRENHAM_STRUCTURE_LAYERS
from truelinev2.ingest.manual_adjudication import (
    PLACE_BLOCKED_ENGINE_LAW,
    PLACE_BLOCKED_SOURCE_VERIFY,
    load_adjudication,
)
from truelinev2.proof.run_log53_primitives_cohort_replay import (
    ALL_PRIMITIVES,
    ALLOWED_BLOCKERS,
    CLASSIFICATIONS,
    ENDPOINT_IDENTITY_NOT_ENCODED,
    ENDPOINT_IDENTITY_NOT_MODELED,
    FRAME_CONTESTED,
    HUMAN_REVIEW_REQUIRED,
    MODELED_TERMINUS_CLASSES,
    NO_RECORDED_SHEET,
    OWNER_HELD_ABSTAIN,
    PARTIAL_SOURCE_BINDABLE,
    PRIM_BORE_LATERAL,
    PRIM_STRUCT_ENDPOINT,
    REPRESENTATIVE_ROUTE_CANDIDATE,
    REVIEW_FLAG_HELD,
    SOURCE_BINDABLE_NOW,
    SOURCE_VERIFICATION_REQUIRED,
    STILL_BLOCKED,
    _consistent,
    classify_cohort,
    classify_record,
)


def _clean(**kw):
    """A clean RECOVERED + allowed-to-draw record; override fields per test."""
    base = {
        "log_id": "synth", "status": "RECOVERED", "allowed_to_draw": True,
        "must_remain_abstained": False, "needs_review": False,
        "needs_source_verification": False, "correction_types": [],
        "corrected_sheets": [], "corrected_start": "1+00", "corrected_end": "2+00",
        "evidence_notes": "",
    }
    base.update(kw)
    return base


# ---- enums ------------------------------------------------------------------------

def test_classification_enum_exact():
    assert CLASSIFICATIONS == {
        "SOURCE_BINDABLE_NOW", "PARTIAL_SOURCE_BINDABLE", "REPRESENTATIVE_ROUTE_CANDIDATE",
        "HUMAN_REVIEW_REQUIRED", "STILL_BLOCKED", "NOT_APPLICABLE",
    }


def test_blocker_enum_carries_task_vocabulary():
    # the task-named typed reasons must all be representable
    for tok in ("CALLOUT_NOT_FOUND", "CALLOUT_NOT_UNIQUE", "LEADER_NOT_FOUND",
                "SYMBOL_NOT_FOUND", "CONDUIT_SEED_NOT_FOUND", "MATCHLINE_TERMINATION_NOT_FOUND",
                "MID_CALLOUT_CONTAINMENT", "MULTIPLE_REVERSE_PATHS", "OCR_REQUIRED",
                "FRAME_CONTESTED", "OWNER_HELD_ABSTAIN", "SOURCE_VERIFICATION_REQUIRED"):
        assert tok in ALLOWED_BLOCKERS


def test_five_primitives_locked():
    assert ALL_PRIMITIVES == (
        "start_callout_leader_symbol_binding", "existing_structure_endpoint_binding",
        "bore_lateral_conduit_seed", "matchline_boundary_termination",
        "sheet_local_continuation_station_identity",
    )


def test_modeled_terminus_classes_grounded_in_dialect():
    # the bindable identities are exactly the dialect's structure layers + the nextlink callout
    assert MODELED_TERMINUS_CLASSES == set(BRENHAM_STRUCTURE_LAYERS) | {"nextlink_hh"}
    assert MODELED_TERMINUS_CLASSES == {"installer_hh", "terminal_port_hh", "flower_pot", "nextlink_hh"}


# ---- per-class decisions (synthetic) ----------------------------------------------

def test_abstain_is_still_blocked():
    r = classify_record(_clean(must_remain_abstained=True, allowed_to_draw=False,
                               status="ABSTAIN_NO_SAFE_SOURCE"))
    assert r["classification"] == STILL_BLOCKED
    assert r["blockers"] == [OWNER_HELD_ABSTAIN]


def test_source_verification_is_human_review():
    r = classify_record(_clean(allowed_to_draw=False, needs_source_verification=True,
                               status="NEEDS_SOURCE_VERIFICATION"))
    assert r["classification"] == HUMAN_REVIEW_REQUIRED
    assert r["blockers"] == [SOURCE_VERIFICATION_REQUIRED]


def test_needs_review_is_human_review():
    r = classify_record(_clean(needs_review=True))
    assert r["classification"] == HUMAN_REVIEW_REQUIRED
    assert r["blockers"] == [REVIEW_FLAG_HELD]


def test_single_sheet_modeled_terminus_is_partial_encode_only():
    r = classify_record(_clean(evidence_notes="ends at STA 2+00 FLOWER POT",
                               corrected_sheets=[5]))
    assert r["classification"] == PARTIAL_SOURCE_BINDABLE
    assert r["blockers"] == [ENDPOINT_IDENTITY_NOT_ENCODED]  # no cross-sheet gap
    assert PRIM_STRUCT_ENDPOINT in r["primitives_that_helped"]


def test_multi_sheet_partial_is_frame_contested():
    r = classify_record(_clean(evidence_notes="STA 2+00 FLOWER POT",
                               correction_types=["MATCHLINE_CHAIN"], corrected_sheets=[5, 6]))
    assert r["classification"] == PARTIAL_SOURCE_BINDABLE
    assert FRAME_CONTESTED in r["blockers"]


def test_modeled_terminus_without_sheet_is_representative():
    r = classify_record(_clean(evidence_notes="INSTALLER HH to FLOWER POT",
                               correction_types=["HH_HH_ANNOTATION"], corrected_sheets=[]))
    assert r["classification"] == REPRESENTATIVE_ROUTE_CANDIDATE
    assert NO_RECORDED_SHEET in r["blockers"]
    assert PRIM_BORE_LATERAL in r["primitives_that_helped"]


def test_unmodeled_terminus_is_representative():
    r = classify_record(_clean(evidence_notes="ends at the endpoint structure",
                               corrected_sheets=[5]))
    assert r["classification"] == REPRESENTATIVE_ROUTE_CANDIDATE
    assert ENDPOINT_IDENTITY_NOT_MODELED in r["blockers"]


def test_bare_hh_is_not_a_modeled_terminus():
    # "HH - HH = 56" names no specific modeled class -> not a structure-resolver terminus
    r = classify_record(_clean(evidence_notes="HH - HH = 56",
                               correction_types=["HH_HH_ANNOTATION"], corrected_sheets=[5]))
    assert r["classification"] == REPRESENTATIVE_ROUTE_CANDIDATE
    assert PRIM_STRUCT_ENDPOINT not in r["primitives_that_helped"]


def test_primitives_never_forced():
    r = classify_record(_clean())  # no signals at all
    assert r["primitives_that_helped"] == []


# ---- real cohort ------------------------------------------------------------------

def test_log53_is_source_bindable_now():
    doc = load_adjudication()
    l53 = next(r for r in doc["logs"] if r["log_id"] == "log53")
    r = classify_record(l53)
    assert r["classification"] == SOURCE_BINDABLE_NOW
    assert r["blockers"] == []


def test_full_cohort_census_counts():
    """The headline census is deterministic against the reviewed artifact. Intentional gated
    delta: encoding log64's endpoint-anchor bridge moved it PARTIAL -> SOURCE_BINDABLE_NOW
    (see test_log64_endpoint_anchor_bridge_slice), so SOURCE_BINDABLE_NOW=2 / PARTIAL=9."""
    rows = classify_cohort(load_adjudication())
    assert len(rows) == 27
    counts = {}
    for r in rows:
        counts[r["classification"]] = counts.get(r["classification"], 0) + 1
    assert counts == {
        SOURCE_BINDABLE_NOW: 2,          # log53 (rendered) + log64 (identity bridge encoded)
        PARTIAL_SOURCE_BINDABLE: 9,
        REPRESENTATIVE_ROUTE_CANDIDATE: 9,
        HUMAN_REVIEW_REQUIRED: 3,
        STILL_BLOCKED: 4,
    }


def test_largest_repeated_blocker_is_cross_sheet_frame():
    rows = classify_cohort(load_adjudication())
    blocker_counts = {}
    for r in rows:
        for b in r["blockers"]:
            blocker_counts[b] = blocker_counts.get(b, 0) + 1
    top = max(blocker_counts.items(), key=lambda kv: kv[1])
    assert top == (FRAME_CONTESTED, 12)


def test_real_cohort_enums_and_consistency():
    rows = classify_cohort(load_adjudication())
    for r in rows:
        assert r["classification"] in CLASSIFICATIONS
        for b in r["blockers"]:
            assert b in ALLOWED_BLOCKERS
        # every classification agrees with the existing placement-readiness seam
        assert _consistent(r["classification"], r["placement_readiness"])


def test_owner_abstains_and_log44_held():
    rows = {r["log_id"]: r for r in classify_cohort(load_adjudication())}
    for l in ("log5", "log31", "log38", "log43"):
        assert rows[l]["classification"] == STILL_BLOCKED
        assert rows[l]["placement_readiness"] == PLACE_BLOCKED_ENGINE_LAW
    assert rows["log44"]["classification"] == HUMAN_REVIEW_REQUIRED
    assert rows["log44"]["placement_readiness"] == PLACE_BLOCKED_SOURCE_VERIFY


# ---- structural no-render guarantee -----------------------------------------------

def test_proof_imports_no_render_or_pdf_lane():
    src = Path(
        __file__).resolve().parent.parent / "proof" / "run_log53_primitives_cohort_replay.py"
    text = src.read_text(encoding="utf-8")
    assert "from truelinev2.render" not in text
    assert "import truelinev2.render" not in text
    assert "ingest.pdf" not in text
    assert "render_redline_stroke" not in text
