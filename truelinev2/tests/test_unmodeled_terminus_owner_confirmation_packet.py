"""UNMODELED_TERMINUS owner-confirmation packet (FULL candidates) -- offline tests.

Locks the packet's pure laws: the result enum; the scope is EXACTLY the scout's FULL set {log46, log54};
the PROPOSED two-leg structure_terminus encoding is schema-valid, identity-only (no coordinate field), and
modeled-class; each proposed station/sheet is owner-grounded (printed in evidence_notes / within
corrected_sheets); the fixture is NOT mutated (the candidates carry no endpoint_anchors and stay UNMODELED);
and the proof ENCODES NOTHING (the proposed anchors are dry-run only). The packet proof is artifact-driven
(no PDF parse); the end-to-end PASS is verified TRUTH-gated.
"""
import json
import os
from pathlib import Path

import pytest

from truelinev2.config import _REPO_ROOT
from truelinev2.ingest.manual_adjudication import load_adjudication, validate_endpoint_anchors
from truelinev2.proof.run_log53_primitives_cohort_replay import (
    ENDPOINT_IDENTITY_NOT_MODELED,
    MODELED_TERMINUS_CLASSES,
    classify_record,
)
from truelinev2.proof.run_unmodeled_terminus_class_scout import FULL, PARTITION
from truelinev2.seam import ELIGIBLE_EXEMPLARS
from truelinev2.proof.run_unmodeled_terminus_owner_confirmation_packet import (
    ALLOWED,
    CANDIDATE,
    FULL_CANDIDATES,
    R_READY,
    STRUCTURE_LABEL,
    _has_coord_keys,
    main,
    proposed_anchor,
)

DOC = load_adjudication()
REC = {r["log_id"]: r for r in DOC["logs"]}
TRUTH = _REPO_ROOT / "data" / "outputs" / "final_engine_truth_table" / "final_engine_truth_table.json"
PROOF = Path(__file__).resolve().parent.parent / "proof" / "run_unmodeled_terminus_owner_confirmation_packet.py"
OUT = _REPO_ROOT / "data" / "outputs" / "unmodeled_terminus_owner_confirmation_packet"


def test_result_enum_exact():
    assert ALLOWED == {
        "OWNER_CONFIRMATION_PACKET_READY",
        "BLOCKED_PACKET_FULL_SET_DRIFTED",
        "BLOCKED_PACKET_PROPOSED_ENCODING_INVALID",
        "BLOCKED_PACKET_PROVENANCE_MISSING",
        "BLOCKED_PACKET_FIXTURE_MUTATED",
        "BLOCKED_PACKET_SOURCE_RECOVERY_DRIFTED",
    }
    assert R_READY in ALLOWED


def test_scope_is_exactly_the_scout_full_set():
    full_in_scout = tuple(sorted((l for l, p in PARTITION.items() if p == FULL), key=lambda s: int(s[3:])))
    assert FULL_CANDIDATES == ("log46", "log54") == full_in_scout
    assert set(CANDIDATE) == set(FULL_CANDIDATES)


def test_candidates_still_unmodeled_root_gate():
    # the packet exists precisely because the owner has NOT named a modeled terminus class yet
    for lid in FULL_CANDIDATES:
        c = classify_record(REC[lid])
        assert ENDPOINT_IDENTITY_NOT_MODELED in c["blockers"]
        assert c["signals"]["has_modeled_terminus"] is False


def test_proposed_encoding_is_schema_valid_identity_only_modeled():
    for lid in FULL_CANDIDATES:
        ea = {"start": proposed_anchor(lid, "start"), "end": proposed_anchor(lid, "end")}
        assert validate_endpoint_anchors({"log_id": lid, "endpoint_anchors": ea}) == []
        for side in ("start", "end"):
            a = ea[side]
            assert a["boundary_kind"] == "structure_terminus"
            assert a["structure_class"] in MODELED_TERMINUS_CLASSES
            assert a["structure_label"] == STRUCTURE_LABEL[a["structure_class"]]
            assert not _has_coord_keys(a)                       # identity-only, no coordinates
            assert "UNCONFIRMED" in a["owner_note_text"]        # self-documents as a candidate


def test_proposed_matches_candidate_classes_and_stations():
    expect = {
        "log46": (("nextlink_hh", "44+08"), ("terminal_port_hh", "5+34")),
        "log54": (("nextlink_hh", "3+91"), ("terminal_port_hh", "3+14")),
    }
    for lid, ((sc, sl), (ec, el)) in expect.items():
        assert (CANDIDATE[lid]["start"]["class"], CANDIDATE[lid]["start"]["station"]) == (sc, sl)
        assert (CANDIDATE[lid]["end"]["class"], CANDIDATE[lid]["end"]["station"]) == (ec, el)


def test_provenance_is_owner_grounded():
    # every proposed station is printed in the owner evidence_notes; every sheet within corrected_sheets
    for lid in FULL_CANDIDATES:
        notes = str(REC[lid].get("evidence_notes") or "")
        sheets = set(REC[lid].get("corrected_sheets") or [])
        for role in ("start", "end"):
            assert CANDIDATE[lid][role]["station"] in notes
            assert CANDIDATE[lid][role]["sheet"] in sheets


def test_fixture_unmodified_nothing_encoded():
    # the candidates carry NO endpoint_anchors -- the proposed encoding is dry-run only
    fresh = {r["log_id"]: r for r in load_adjudication()["logs"]}
    for lid in FULL_CANDIDATES:
        assert fresh[lid].get("endpoint_anchors") is None
    # the proof never writes endpoint_anchors into a record
    src = PROOF.read_text(encoding="utf-8")
    assert "endpoint_anchors\"] =" not in src and "endpoint_anchors'] =" not in src
    assert "from truelinev2.render" not in src and "render_redline_stroke" not in src


def test_seam_unchanged():
    assert tuple(ELIGIBLE_EXEMPLARS) == ("log53", "log64", "log71", "log59", "log66")


@pytest.mark.skipif(not os.path.isfile(TRUTH), reason="engine truth table not present")
def test_end_to_end_packet_ready():
    rc = main()
    assert rc == 0
    data = json.loads((OUT / "unmodeled_terminus_owner_confirmation_packet.json").read_text(encoding="utf-8"))
    assert data["verdict"] == "PASS" and data["result"] == R_READY
    assert set(data["confirmation_packet"]) == set(FULL_CANDIDATES)
    for lid in FULL_CANDIDATES:
        p = data["confirmation_packet"][lid]
        assert "UNCONFIRMED" in p["status"]
        assert p["proposed_start_terminus"]["structure_class"] == CANDIDATE[lid]["start"]["class"]
        assert p["proposed_end_terminus"]["structure_class"] == CANDIDATE[lid]["end"]["class"]
        assert validate_endpoint_anchors({"log_id": lid, "endpoint_anchors": p["what_would_be_encoded_if_confirmed"]}) == []
    assert data["scope_guard"]["endpoint_anchors_encoded"] is False
