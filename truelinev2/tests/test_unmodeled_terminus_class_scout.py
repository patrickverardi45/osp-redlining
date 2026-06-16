"""UNMODELED_TERMINUS_CLASS scout -- offline + PDF-gated tests.

Locks the scout's pure laws: the result/blocker enum; the scouted set is EXACTLY the closure ledger's
UNMODELED_TERMINUS class (6 logs); every member carries the ROOT gate ENDPOINT_IDENTITY_NOT_MODELED with
no owner-named modeled terminus; the deterministic owner-review partition (2 full / 2 partial / 2
representative); the NO-GUESS law (recovered only when exactly one class binds); and the structural guard
that the scout reuses the SHIPPED resolvers + canonical classifier and ENCODES NOTHING (defines no new
resolver, writes no endpoint_anchors, draws nothing). The heavy read-only resolver recovery is verified
PDF-gated by running the scout.
"""
import json
import os
from collections import Counter
from pathlib import Path

import pytest

from truelinev2.config import _REPO_ROOT
from truelinev2.ingest.manual_adjudication import load_adjudication
from truelinev2.proof.run_all_redlines_closure_ledger import UNMODELED_TERMINUS, build_ledger
from truelinev2.proof.run_brenham_corpus import PDF
from truelinev2.proof.run_log53_primitives_cohort_replay import (
    ENDPOINT_IDENTITY_NOT_MODELED,
    REPRESENTATIVE_ROUTE_CANDIDATE,
    classify_record,
)
from truelinev2.seam import ELIGIBLE_EXEMPLARS
from truelinev2.proof.run_unmodeled_terminus_class_scout import (
    ALLOWED,
    EXPECTED_UNMODELED,
    FULL,
    PARTIAL,
    PARTITION,
    REPRESENTATIVE,
    R_COMPLETE,
    TERMINI,
    NEXT_ACTION,
    main,
)

DOC = load_adjudication()
REC = {r["log_id"]: r for r in DOC["logs"]}
TRUTH = _REPO_ROOT / "data" / "outputs" / "final_engine_truth_table" / "final_engine_truth_table.json"
PROOF = Path(__file__).resolve().parent.parent / "proof" / "run_unmodeled_terminus_class_scout.py"
OUT = _REPO_ROOT / "data" / "outputs" / "unmodeled_terminus_class_scout"


def test_result_enum_exact():
    assert ALLOWED == {
        "UNMODELED_TERMINUS_CLASS_SCOUT_COMPLETE",
        "BLOCKED_UNMODELED_TRUTH_MISSING",
        "BLOCKED_UNMODELED_PDF_MISSING",
        "BLOCKED_UNMODELED_COHORT_MISMATCH",
        "BLOCKED_UNMODELED_AMBIGUOUS_NOT_HELD",
        "BLOCKED_UNMODELED_SILENTLY_ENCODED",
    }
    assert R_COMPLETE in ALLOWED


def test_scouted_set_is_the_ledger_unmodeled_class():
    rows = json.loads(TRUTH.read_text(encoding="utf-8"))["rows"]
    ledger = build_ledger(rows, DOC)
    ledger_unmod = tuple(sorted((b for b, v in ledger.items() if v["category"] == UNMODELED_TERMINUS),
                                key=lambda s: int(s[3:])))
    assert ledger_unmod == EXPECTED_UNMODELED == ("log6", "log41", "log46", "log54", "log63", "log68")
    assert set(TERMINI) == set(EXPECTED_UNMODELED)


def test_every_member_is_unmodeled_root_gate():
    for lid in EXPECTED_UNMODELED:
        c = classify_record(REC[lid])
        assert c["classification"] == REPRESENTATIVE_ROUTE_CANDIDATE
        assert ENDPOINT_IDENTITY_NOT_MODELED in c["blockers"]
        assert c["signals"]["has_modeled_terminus"] is False


def test_partition_constant_is_exact_and_total():
    assert PARTITION == {
        "log46": FULL, "log54": FULL,
        "log6": PARTIAL, "log63": PARTIAL,
        "log41": REPRESENTATIVE, "log68": REPRESENTATIVE,
    }
    assert set(PARTITION) == set(EXPECTED_UNMODELED)        # every member partitioned exactly once
    counts = Counter(PARTITION.values())
    assert counts[FULL] == 2 and counts[PARTIAL] == 2 and counts[REPRESENTATIVE] == 2
    assert set(NEXT_ACTION) == {FULL, PARTIAL, REPRESENTATIVE}


def test_termini_are_owner_authoritative_per_log():
    # each member has a start + end terminus with a sheet drawn from its owner-confirmed corrected_sheets
    for lid in EXPECTED_UNMODELED:
        assert set(TERMINI[lid]) == {"start", "end"}
        sheets = set(REC[lid].get("corrected_sheets") or [])
        for role in ("start", "end"):
            sheet, station, reset = TERMINI[lid][role]
            assert sheet in sheets and isinstance(station, str) and isinstance(reset, bool)


def test_reuses_shipped_resolvers_encodes_nothing():
    # the scout reuses the SHIPPED resolvers + classifier; defines no new resolver; writes no endpoint_anchors
    src = PROOF.read_text(encoding="utf-8")
    assert "from truelinev2.extract.structure_position import" in src
    assert "from truelinev2.proof.run_log53_primitives_cohort_replay import" in src
    top_defs = {ln.split("(")[0].strip() for ln in src.splitlines() if ln.startswith("def ")}
    for forbidden in ("def resolve_structure_position", "def resolve_nextlink_hh_callout",
                      "def classify_record", "def derive_signals"):
        assert forbidden not in top_defs
    assert "from truelinev2.render" not in src and "render_redline_stroke" not in src
    # encodes nothing: no write of endpoint_anchors into the artifact
    assert "endpoint_anchors\"] =" not in src and "endpoint_anchors'] =" not in src


def test_the_six_carry_no_endpoint_anchors_in_artifact():
    # the class stays UNMODELED in the reviewed artifact -- recovered classes are candidates, not encoded
    for lid in EXPECTED_UNMODELED:
        assert not REC[lid].get("endpoint_anchors")


def test_seam_unchanged():
    assert tuple(ELIGIBLE_EXEMPLARS) == ("log53", "log64", "log71", "log59", "log66")


@pytest.mark.skipif(not os.path.isfile(PDF), reason="Brenham plan PDF not present")
def test_end_to_end_resolver_recovery():
    rc = main()
    assert rc == 0
    data = json.loads((OUT / "unmodeled_terminus_class_scout.json").read_text(encoding="utf-8"))
    assert data["verdict"] == "PASS" and data["result"] == R_COMPLETE
    assert data["partition_counts"] == {FULL: 2, PARTIAL: 2, REPRESENTATIVE: 2}
    per = data["per_log"]
    # FULL: both termini recovered to a modeled class, each on-route; nextlink->port pattern
    for lid in ("log46", "log54"):
        assert per[lid]["partition"] == FULL and per[lid]["n_recovered"] == 2
        for role in ("start", "end"):
            t = per[lid]["termini"][role]
            assert t["recovered_class"] in ("nextlink_hh", "terminal_port_hh", "installer_hh", "flower_pot")
            assert t["on_route"] is True and len(t["classes_bound"]) == 1   # NO-GUESS: unique bind
    # PARTIAL: exactly one terminus recovered (installer_hh), one bare
    for lid in ("log6", "log63"):
        assert per[lid]["partition"] == PARTIAL and per[lid]["n_recovered"] == 1
    # REPRESENTATIVE: neither terminus binds a structure
    for lid in ("log41", "log68"):
        assert per[lid]["partition"] == REPRESENTATIVE and per[lid]["n_recovered"] == 0
        for role in ("start", "end"):
            assert per[lid]["termini"][role]["recovered_class"] is None
    # encodes nothing
    assert data["doctrine"]["encodes_nothing"] is True and data["doctrine"]["no_new_resolver"] is True
