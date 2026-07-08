"""Tests for the READ-ONLY structure-datum refusal census (proof harness). The classifier is a pure, total,
strict-precedence function; the real-corpus run skips honestly without the private fixtures (so CI runs these
without touching the corpus). No product store is written; nothing is placed or promoted.

Synthetic fixtures only (pure signal tuples + tmp dirs); no customer/person/place names.
"""
from __future__ import annotations

import json
from pathlib import Path

from truelinev2.harness import structure_datum_reasoning as sdr
from truelinev2.proof import run_structure_datum_census as census


def _bucket(**kw):
    base = dict(deterministic_placed=False, reasoner_status=sdr.STRUCTURE_DATUM_REVIEW_CANDIDATE,
                reasoner_ready=False, span_exceeds=False, far_endpoint_supported=False)
    base.update(kw)
    return census.classify_census_bucket(**base)


# --------------------------------------------------------------------------------------------------------- #
# (1) one synthetic signal-set per bucket -> the intended bucket (10 buckets, all reachable).
# --------------------------------------------------------------------------------------------------------- #
def test_one_fixture_per_bucket():
    assert _bucket(deterministic_placed=True) == census.CONTROL_DETERMINISTIC_PLACED
    assert _bucket(reasoner_ready=True) == census.CANDIDATE_PRODUCED
    assert _bucket(reasoner_status=sdr.AMBIGUOUS_STRUCTURE_DATUM,
                   far_endpoint_supported=True) == census.AMBIGUOUS_ONLY_FAR_SUPPORTED
    assert _bucket(reasoner_status=sdr.UNSUPPORTED_FAR_ENDPOINT) == census.UNSUPPORTED_FAR_ONLY
    assert _bucket(reasoner_status=sdr.AMBIGUOUS_STRUCTURE_DATUM,
                   far_endpoint_supported=False) == census.DOUBLE_BLOCKED
    assert _bucket(reasoner_status=sdr.NO_PRINTED_DATUM_WITNESS, span_exceeds=True) == census.SPAN_EXCEEDS_PRINTED_SHEET
    assert _bucket(reasoner_status=sdr.MULTI_SHEET_REFS_UNSUPPORTED) == census.MULTI_REF_PASS_THROUGH
    assert _bucket(reasoner_status=sdr.NO_PRINTED_DATUM_WITNESS) == census.NO_WITNESS
    assert _bucket(reasoner_status=sdr.NO_PRINT_SHEET_REF) == census.NO_PRINT_REF
    assert _bucket(reasoner_status=sdr.NO_CONFIRMED_SPAN) == census.OTHER_REFUSAL
    # every bucket name is reachable by this suite
    reached = {
        _bucket(deterministic_placed=True), _bucket(reasoner_ready=True),
        _bucket(reasoner_status=sdr.AMBIGUOUS_STRUCTURE_DATUM, far_endpoint_supported=True),
        _bucket(reasoner_status=sdr.UNSUPPORTED_FAR_ENDPOINT),
        _bucket(reasoner_status=sdr.AMBIGUOUS_STRUCTURE_DATUM, far_endpoint_supported=False),
        _bucket(reasoner_status=sdr.NO_PRINTED_DATUM_WITNESS, span_exceeds=True),
        _bucket(reasoner_status=sdr.MULTI_SHEET_REFS_UNSUPPORTED),
        _bucket(reasoner_status=sdr.NO_PRINTED_DATUM_WITNESS),
        _bucket(reasoner_status=sdr.NO_PRINT_SHEET_REF), _bucket(reasoner_status=sdr.SHEET_REF_UNRESOLVED),
    }
    assert reached == set(census.ALL_BUCKETS)


# --------------------------------------------------------------------------------------------------------- #
# (2) precedence / mutual exclusion: signal-sets that satisfy MULTIPLE conditions resolve to the higher rung.
# --------------------------------------------------------------------------------------------------------- #
def test_precedence_is_strict_and_mutually_exclusive():
    # CONTROL beats every reasoner signal (a placed bore is never re-bucketed by the cold reasoner)
    assert _bucket(deterministic_placed=True, reasoner_ready=True) == census.CONTROL_DETERMINISTIC_PLACED
    assert _bucket(deterministic_placed=True, reasoner_status=sdr.AMBIGUOUS_STRUCTURE_DATUM,
                   span_exceeds=True) == census.CONTROL_DETERMINISTIC_PLACED
    # SPAN_EXCEEDS beats the datum-refusal buckets (log43 shape: ambiguous on-sheet end but the far end off-sheet)
    assert _bucket(reasoner_status=sdr.AMBIGUOUS_STRUCTURE_DATUM, far_endpoint_supported=True,
                   span_exceeds=True) == census.SPAN_EXCEEDS_PRINTED_SHEET
    # a produced candidate outranks span_exceeds (a real candidate implies both ends on-sheet + supported)
    assert _bucket(reasoner_ready=True, span_exceeds=True) == census.CANDIDATE_PRODUCED
    # precondition refusals outrank the datum buckets
    assert _bucket(reasoner_status=sdr.NO_PRINT_SHEET_REF, span_exceeds=True) == census.NO_PRINT_REF
    # the classifier is total: an unforeseen status falls through to OTHER_REFUSAL (never crashes / never places)
    assert _bucket(reasoner_status="SOMETHING_NEW") == census.OTHER_REFUSAL


# --------------------------------------------------------------------------------------------------------- #
# (3) read-only guard: the census source performs no product-store / service / artifact writes.
# --------------------------------------------------------------------------------------------------------- #
def test_no_product_store_or_service_writes():
    src = Path(census.__file__).read_text(encoding="utf-8")
    for forbidden in ("ReviewStore", "ArtifactStore", "RedlineService", "product_store", "accept_upload",
                      "create_job", "save_bundle"):
        assert forbidden not in src, "census must not touch %s (read-only)" % forbidden
    # the only writer is run_census -> out_path; no other write/open-for-write appears
    assert src.count("write_text(") == 1


# --------------------------------------------------------------------------------------------------------- #
# (4) importable + runnable WITHOUT the real fixtures -> honest skip (no crash, no write anywhere).
# --------------------------------------------------------------------------------------------------------- #
def test_skips_honestly_without_real_corpus(tmp_path):
    out = tmp_path / "out" / "census.json"
    r = census.run_census(corpus_dir=str(tmp_path / "no_such_corpus"),
                          plan_path=str(tmp_path / "no_such_plan.pdf"), out_path=str(out))
    assert r["skipped"] is True and "rows" not in r
    assert not out.exists()                                    # skip writes NOTHING
    assert not (tmp_path / "out").exists()
    assert list(tmp_path.iterdir()) == []                      # tmp untouched -> no product-store dirs created


# --------------------------------------------------------------------------------------------------------- #
# (5) CONTROL labeling never promotes or refuses: a deterministically-placed bore is CONTROL regardless of the
# reasoner verdict, and the classifier emits only a LABEL (no placement / promotion state).
# --------------------------------------------------------------------------------------------------------- #
def test_control_labeling_does_not_promote_or_refuse():
    for rs, ready in ((sdr.STRUCTURE_DATUM_REVIEW_CANDIDATE, True), (sdr.AMBIGUOUS_STRUCTURE_DATUM, False),
                      (sdr.NO_PRINTED_DATUM_WITNESS, False), (sdr.UNSUPPORTED_FAR_ENDPOINT, False)):
        assert _bucket(deterministic_placed=True, reasoner_status=rs,
                       reasoner_ready=ready) == census.CONTROL_DETERMINISTIC_PLACED
    # the classifier returns a plain bucket string — it carries no draw/place/promote side effect
    assert isinstance(_bucket(deterministic_placed=True), str)


def test_report_shape_of_skip_is_json_serializable():
    r = census.run_census(corpus_dir="/no/corpus", plan_path="/no/plan.pdf")
    json.dumps(r)                                              # must be serializable + non-crashing
    assert r["skipped"] is True


# --------------------------------------------------------------------------------------------------------- #
# Authoritative-frontier reconciliation: the census records the closure/render LEDGER (not run_match) as the
# real "converted" signal, and maps every ledger category onto a reconciliation category.
# --------------------------------------------------------------------------------------------------------- #
def test_ledger_reconciliation_map_is_total_and_correct():
    import truelinev2.proof.run_all_redlines_closure_ledger as L
    assert census.reconcile_ledger_category(L.ENGINE_PLACED) == census.ALREADY_RENDER_FRONTIER_PLACED
    assert census.reconcile_ledger_category(L.SEAM_RENDER_PROVEN) == census.ALREADY_RENDER_FRONTIER_PLACED
    assert census.reconcile_ledger_category(L.HELD_BACK) == census.OWNER_PROMOTION_HOLD
    assert census.reconcile_ledger_category(L.STILL_BLOCKED_NAMED) == census.OWNER_LOCKED_ABSTAIN
    assert census.reconcile_ledger_category(L.UNMODELED_TERMINUS) == census.TERMINUS_OR_PARENT_CHILD_EVIDENCE_BLOCKER
    assert census.reconcile_ledger_category(L.PARENT_CHILD) == census.TERMINUS_OR_PARENT_CHILD_EVIDENCE_BLOCKER
    assert census.reconcile_ledger_category(L.SOURCE_OWNER) == census.SOURCE_OCR_OWNER_CONFIRMATION_NEEDED
    assert census.reconcile_ledger_category(L.CROSS_SHEET) == census.TRUE_CROSS_SHEET_FRAME_JOIN_GAP
    # total: every authoritative ledger category maps to a known reconciliation category
    for cat in L.ALL_CATEGORIES:
        assert census.reconcile_ledger_category(cat) in census.RECONCILIATION_CATEGORIES
    # unknown / absent -> OTHER (never crashes, never a run_match guess)
    assert census.reconcile_ledger_category("SOMETHING_NEW") == census.OTHER_LEDGER_REFUSAL
    assert census.reconcile_ledger_category(None) == census.OTHER_LEDGER_REFUSAL


def test_frontier_status_is_ledger_driven_not_run_match():
    import inspect
    import truelinev2.proof.run_all_redlines_closure_ledger as L
    # STRUCTURAL PROOF: frontier_status is a function of (ledger, bore_id) only — no run_match input, so the
    # authoritative frontier can never be controlled by the default-flag baseline.
    assert list(inspect.signature(census.frontier_status).parameters) == ["ledger", "bore_id"]
    ledger = {"log15": {"placed": True, "category": L.ENGINE_PLACED}}
    fs = census.frontier_status(ledger, "bore_log15")            # bore-log stem -> ledger key
    assert fs["in_render_ledger"] and fs["render_frontier_placed"] is True
    assert fs["ledger_reconciliation"] == census.ALREADY_RENDER_FRONTIER_PLACED
    # a bore absent from the ledger -> not-placed + OTHER (no fallback to run_match)
    absent = census.frontier_status(ledger, "bore_log99")
    assert absent["in_render_ledger"] is False and absent["render_frontier_placed"] is False
    assert absent["ledger_reconciliation"] == census.OTHER_LEDGER_REFUSAL


def test_frontier_loader_skips_honestly_without_truth_table(monkeypatch, tmp_path):
    # If the gitignored engine truth table is absent, the frontier is honestly EMPTY (never substituted by
    # run_match): _load_frontier_ledger returns {} rather than crashing or guessing.
    monkeypatch.setattr(census, "_REPO_ROOT", tmp_path)         # no truth table under this root
    assert census._load_frontier_ledger() == {}
