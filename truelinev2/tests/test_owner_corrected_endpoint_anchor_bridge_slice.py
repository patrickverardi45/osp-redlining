"""OWNER-CORRECTED endpoint-anchor bridge slice (log67/69/70/47/11) -- offline tests.

Locks the bridge consequences of the 2026-06-16 owner corrections: the result enum; the 5 logs carry
schema-valid, identity-only (no coordinate), two-structure-terminus bridges with the owner-corrected
classes/stations; each classifies SOURCE_BINDABLE_NOW; log69 is single-sheet [17] while log67/70/47/11 stay
cross-sheet; all 5 are seam-REFUSED (held back, nothing promoted); the held-back set is the 8 and the
anchored set is 13; and the closure ledger is CROSS_SHEET 1 / HELD_BACK 8. The census-frozen + ledger run
is verified by executing the proof.
"""
import json

from truelinev2.config import _REPO_ROOT
from truelinev2.ingest.manual_adjudication import load_adjudication, validate_endpoint_anchors
from truelinev2.proof.run_log53_primitives_cohort_replay import (
    MODELED_TERMINUS_CLASSES,
    SOURCE_BINDABLE_NOW,
    classify_record,
)
from truelinev2.seam import ELIGIBLE_EXEMPLARS, build_seam_payload
from truelinev2.proof.run_owner_corrected_endpoint_anchor_bridge_slice import (
    ALLOWED,
    ANCHORED_13,
    CORRECTED,
    HELD_BACK_8,
    R_ENCODED,
    SINGLE_SHEET,
    _has_coord_keys,
    main,
)

DOC = load_adjudication()
REC = {r["log_id"]: r for r in DOC["logs"]}
OUT = _REPO_ROOT / "data" / "outputs" / "owner_corrected_endpoint_anchor_bridge_slice"


def test_result_enum_exact():
    assert ALLOWED == {
        "OWNER_CORRECTED_ENDPOINT_ANCHORS_ENCODED",
        "BLOCKED_OWNER_CORRECTED_SCHEMA_GAP",
        "BLOCKED_OWNER_CORRECTED_COHORT_DRIFT",
        "BLOCKED_OWNER_CORRECTED_SILENTLY_PROMOTED",
        "BLOCKED_OWNER_CORRECTED_CENSUS_DRIFT",
    }
    assert R_ENCODED in ALLOWED


def test_corrected_set_and_single_sheet():
    assert set(CORRECTED) == {"log67", "log69", "log70", "log47", "log11"}
    assert SINGLE_SHEET == ("log69",)
    assert HELD_BACK_8 == ("log11", "log36", "log47", "log52", "log58", "log67", "log69", "log70")
    assert len(ANCHORED_13) == 13


def test_the_five_carry_schema_valid_identity_only_bridges():
    for lid, exp in CORRECTED.items():
        ea = REC[lid].get("endpoint_anchors") or {}
        assert validate_endpoint_anchors(REC[lid]) == []
        assert set(ea) == {"start", "end"}
        for side, (cls, sta) in (("start", exp["start"]), ("end", exp["end"])):
            a = ea[side]
            assert a["boundary_kind"] == "structure_terminus"
            assert (a["structure_class"], a["station"]) == (cls, sta)
            assert a["structure_class"] in MODELED_TERMINUS_CLASSES
            assert not _has_coord_keys(a)          # identity-only, no coordinates
        assert REC[lid]["corrected_sheets"] == exp["sheets"]


def test_all_five_source_bindable_now():
    for lid in CORRECTED:
        assert classify_record(REC[lid])["classification"] == SOURCE_BINDABLE_NOW


def test_log69_single_sheet_others_cross_sheet():
    assert REC["log69"]["corrected_sheets"] == [17]
    for lid in ("log67", "log70", "log47", "log11"):
        assert len(REC[lid]["corrected_sheets"]) >= 2


def test_all_five_seam_refused_nothing_promoted():
    assert tuple(ELIGIBLE_EXEMPLARS) == ("log53", "log64", "log71", "log59", "log66")
    for lid in CORRECTED:
        try:
            build_seam_payload(lid, REC[lid])
            assert False, f"{lid} (held back) must not be seam-eligible"
        except ValueError:
            pass


def test_no_render_lane_in_proof():
    from pathlib import Path
    src = (Path(__file__).resolve().parent.parent / "proof"
           / "run_owner_corrected_endpoint_anchor_bridge_slice.py").read_text(encoding="utf-8")
    assert "from truelinev2.render" not in src and "render_redline_stroke" not in src


def test_end_to_end_bridge_proof_passes():
    rc = main()
    assert rc == 0
    data = json.loads((OUT / "owner_corrected_endpoint_anchor_bridge_slice.json").read_text(encoding="utf-8"))
    assert data["verdict"] == "PASS" and data["result"] == R_ENCODED
    assert sorted(data["held_back_set"]) == sorted(HELD_BACK_8)
    assert sorted(data["anchored_set"]) == sorted(ANCHORED_13)
    assert all(v == SOURCE_BINDABLE_NOW for v in data["cohort_now"].values())
