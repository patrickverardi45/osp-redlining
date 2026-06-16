"""CROSS-SHEET endpoint-anchor bridge (log52 + log58) -- offline tests.

Locks the bridge's pure facts: log52 (flower_pot @0+98 -> flower_pot @4+57) and log58 (installer_hh @39+79
-> installer_hh @2+36) carry schema-valid, identity-only, two-leg both-termini endpoint_anchors (the log71
schema; no matchline_continuation anchor, no coordinates); corrected_sheets stay the owner sets [8,7] /
[10,13]; the cohort classifier moves both PARTIAL_SOURCE_BINDABLE -> SOURCE_BINDABLE_NOW; both are HELD BACK
(anchored but NOT seam-promoted -- ELIGIBLE_EXEMPLARS unchanged; seam refuses them); the held-back set is
{log36, log52, log58}; and log11 + log47 stay un-anchored (held with named blockers). No PDF parse here.
"""
from pathlib import Path

import pytest

from truelinev2.ingest.manual_adjudication import load_adjudication, validate_endpoint_anchors
from truelinev2.proof.run_log53_primitives_cohort_replay import SOURCE_BINDABLE_NOW, classify_record
from truelinev2.proof.run_cross_sheet_endpoint_anchor_bridge_slice import (
    ALLOWED,
    EXPECTED_ANCHOR_LOGS,
    HELD_BACK_BRIDGED,
    HELD_NAMED_BLOCKER,
    R_ENCODED,
)
from truelinev2.seam import ELIGIBLE_EXEMPLARS, build_seam_payload

DOC = load_adjudication()
REC = {r["log_id"]: r for r in DOC["logs"]}


def test_result_enum():
    assert R_ENCODED == "CROSS_SHEET_ENDPOINT_ANCHORS_ENCODED"
    assert R_ENCODED in ALLOWED


def test_log52_two_leg_flower_to_flower():
    ea = REC["log52"]["endpoint_anchors"]
    assert validate_endpoint_anchors(REC["log52"]) == []
    s, e = ea["start"], ea["end"]
    assert (s["structure_class"], s["station"], s["boundary_kind"]) == ("flower_pot", "0+98", "structure_terminus")
    assert (e["structure_class"], e["station"], e["boundary_kind"]) == ("flower_pot", "4+57", "structure_terminus")
    assert s["structure_label"] == e["structure_label"] == "FLOWER POT"
    assert REC["log52"]["corrected_sheets"] == [8, 7]            # owner set UNCHANGED


def test_log58_two_leg_installer_to_installer():
    ea = REC["log58"]["endpoint_anchors"]
    assert validate_endpoint_anchors(REC["log58"]) == []
    s, e = ea["start"], ea["end"]
    assert (s["structure_class"], s["station"], s["boundary_kind"]) == ("installer_hh", "39+79", "structure_terminus")
    assert (e["structure_class"], e["station"], e["boundary_kind"]) == ("installer_hh", "2+36", "structure_terminus")
    assert s["structure_label"] == e["structure_label"] == "INSTALLER HH"
    assert REC["log58"]["corrected_sheets"] == [10, 13]          # owner set UNCHANGED


def test_anchors_are_identity_only_no_coordinates():
    coord_keys = {"x", "y", "xy", "symbol_xy", "coord", "coords", "point", "points", "geometry"}
    for lid in ("log52", "log58"):
        for side in ("start", "end"):
            a = REC[lid]["endpoint_anchors"][side]
            assert not (set(a) & coord_keys)
            assert a["boundary_kind"] == "structure_terminus"   # two-leg, no matchline_continuation anchor


def test_cohort_delta_log52_log58_source_bindable_now():
    for lid in ("log52", "log58"):
        assert classify_record(REC[lid])["classification"] == SOURCE_BINDABLE_NOW


def test_held_back_not_promoted():
    # seam unchanged at 5; both bridged logs are anchored-but-held-back (seam refuses them)
    assert tuple(ELIGIBLE_EXEMPLARS) == ("log53", "log64", "log71", "log59", "log66")
    for lid in ("log52", "log58"):
        with pytest.raises(ValueError):
            build_seam_payload(lid, REC[lid])
    # the held-back set is the 8 bridged logs (incl. the owner-corrected log11/47/67/69/70, 2026-06-16)
    assert HELD_BACK_BRIDGED == ("log11", "log36", "log47", "log52", "log58", "log67", "log69", "log70")
    with_anchors = {r["log_id"] for r in DOC["logs"] if r.get("endpoint_anchors")}
    assert with_anchors == set(EXPECTED_ANCHOR_LOGS) == {
        "log11", "log36", "log47", "log52", "log53", "log58", "log59",
        "log64", "log66", "log67", "log69", "log70", "log71"}


def test_log11_log47_since_bridged_no_named_blocker_remains():
    # log11 (shared log53 NEXTLINK HH start) + log47 (STA 4+94 INSTALLER HH end) have SINCE been
    # owner-confirmed + bridged (2026-06-16); no source-backed cross-sheet log is held un-anchored
    assert HELD_NAMED_BLOCKER == ()
    assert REC["log11"].get("endpoint_anchors") and REC["log47"].get("endpoint_anchors")


def test_bridge_proof_has_no_render_lane():
    src = Path(__file__).resolve().parent.parent / "proof" / "run_cross_sheet_endpoint_anchor_bridge_slice.py"
    text = src.read_text(encoding="utf-8")
    assert "from truelinev2.render" not in text
    assert "render_redline_stroke" not in text
