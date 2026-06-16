"""OWNER-PACKET-2 manual adjudication ACTIVATION -- offline tests.

Exercises the default-OFF resolution overlay with a SYNTHETIC baseline (no dependency
on the gitignored truth table; the proof covers the real rows). No engine re-run, no
geometry, no corpus.
"""
import copy

import pytest

from truelinev2.config import Settings
from truelinev2.ingest.manual_adjudication import (
    ADJ_BUCKET_ABSTAIN,
    ADJ_BUCKET_REVIEW_DRAWABLE,
    ADJ_BUCKET_SOURCE_VERIFY,
    AdjudicationError,
    activation_summary,
    apply_adjudications,
    flag_on_disposition,
    load_adjudication,
)

ABSTAIN_4 = {"log5", "log31", "log38", "log43"}
SHARED_PRINT_11 = {
    "log6", "log46", "log47", "log52", "log53", "log58", "log63", "log64", "log67",
    "log70", "log71",
}


@pytest.fixture(scope="module")
def doc():
    return load_adjudication()


@pytest.fixture(scope="module")
def baseline(doc):
    """Synthetic baseline: the 27 problem logs (non-drawable) + 2 already-drawable rows."""
    rows = {}
    for r in doc["logs"]:
        rows[r["log_id"]] = {
            "bore_id": r["log_id"],
            "completion_bucket": "PICK_CARD_REVIEW",
            "source_family": r.get("parent") or r["log_id"],
            "can_draw_now": False,
        }
    for d in ("logD1", "logD2"):
        rows[d] = {"bore_id": d, "completion_bucket": "DRAWABLE_REVIEW",
                   "source_family": d, "can_draw_now": True}
    return rows


# --- flag default + env ---------------------------------------------------------
def test_flag_defaults_off(monkeypatch):
    monkeypatch.delenv("TRUELINE_MANUAL_ADJUDICATIONS", raising=False)
    assert Settings.from_env().manual_adjudications_optin is False


def test_flag_env_on(monkeypatch):
    monkeypatch.setenv("TRUELINE_MANUAL_ADJUDICATIONS", "1")
    assert Settings.from_env().manual_adjudications_optin is True


# --- flag OFF is inert / byte-identical -----------------------------------------
def test_off_returns_unchanged(baseline):
    out = apply_adjudications(baseline, enabled=False)
    assert out is baseline
    assert not any("adjudication" in r for r in out.values())


# --- flag ON overlays only the artifact logs ------------------------------------
def test_on_overlays_only_27(baseline, doc):
    out = apply_adjudications(baseline, enabled=True, doc=doc)
    overlaid = {b for b, r in out.items() if r.get("adjudication")}
    assert overlaid == {r["log_id"] for r in doc["logs"]}
    # the 2 already-drawable rows are untouched
    assert out["logD1"] == baseline["logD1"]
    assert out["logD2"] == baseline["logD2"]


def test_on_does_not_mutate_input(baseline, doc):
    before = copy.deepcopy(baseline)
    apply_adjudications(baseline, enabled=True, doc=doc)
    assert baseline == before  # overlay returns a new dict; input untouched


# --- the 4 abstains stay hard-abstained -----------------------------------------
@pytest.mark.parametrize("lid", sorted(ABSTAIN_4))
def test_on_abstain_hard(baseline, doc, lid):
    out = apply_adjudications(baseline, enabled=True, doc=doc)
    a = out[lid]["adjudication"]
    assert a["drawable_status"] == "abstain"
    assert out[lid]["completion_bucket"] == ADJ_BUCKET_ABSTAIN
    assert out[lid]["can_draw_now"] is False


# --- log44 stays source-verification / non-drawable -----------------------------
def test_on_log44_source_verification(baseline, doc):
    out = apply_adjudications(baseline, enabled=True, doc=doc)
    a = out["log44"]["adjudication"]
    assert a["drawable_status"] == "non_drawable"
    assert out["log44"]["completion_bucket"] == ADJ_BUCKET_SOURCE_VERIFY
    assert a["needs_source_verification"] is True
    assert out["log44"]["can_draw_now"] is False


# --- the 11 shared-print children become review-drawable ------------------------
@pytest.mark.parametrize("lid", sorted(SHARED_PRINT_11))
def test_on_shared_print_review_drawable(baseline, doc, lid):
    out = apply_adjudications(baseline, enabled=True, doc=doc)
    assert out[lid]["completion_bucket"] == ADJ_BUCKET_REVIEW_DRAWABLE
    assert out[lid]["adjudication"]["drawable_status"] == "review_drawable"


# --- log68/log69 separation + corrected print -----------------------------------
def test_on_log68_log69_not_mixed(baseline, doc):
    out = apply_adjudications(baseline, enabled=True, doc=doc)
    a68, a69 = out["log68"]["adjudication"], out["log69"]["adjudication"]
    assert (a68["corrected_start"], a68["corrected_end"]) == ("5+03", "6+79")
    assert "4+54" not in (a68["corrected_start"], a68["corrected_end"])
    # owner correction 2026-06-16: log69 start is the 1+45=0+00 reset (bore-frame 0+00), end 4+54 INSTALLER HH
    assert (a69["corrected_start"], a69["corrected_end"]) == ("0+00", "4+54")


@pytest.mark.parametrize("lid", ["log67", "log68", "log70"])
def test_on_print_17_20(baseline, doc, lid):
    out = apply_adjudications(baseline, enabled=True, doc=doc)
    assert out[lid]["adjudication"]["corrected_prints"] == [17, 20]


def test_on_log69_single_print_17(baseline, doc):
    # owner correction 2026-06-16: log69 is single-sheet on print 17
    out = apply_adjudications(baseline, enabled=True, doc=doc)
    assert out["log69"]["adjudication"]["corrected_prints"] == [17]


# --- movement summary computed from actual output -------------------------------
def test_activation_summary_counts(baseline, doc):
    out = apply_adjudications(baseline, enabled=True, doc=doc)
    s = activation_summary(out)
    assert s["manual_review_drawable"] == 22
    assert s["manual_source_verification"] == 1
    assert s["manual_abstain"] == 4
    assert s["moved_count"] == 27
    assert s["engine_drawable_unchanged"] == 2  # the 2 synthetic drawable rows


# --- fail-closed --------------------------------------------------------------
def test_on_fail_closed_on_invalid_artifact(baseline, doc):
    bad = copy.deepcopy(doc)
    a = next(r for r in bad["logs"] if r["log_id"] == "log5")
    a["allowed_to_draw"] = True  # tamper an abstain
    with pytest.raises(AdjudicationError):
        apply_adjudications(baseline, enabled=True, doc=bad)


def test_disposition_carries_only_reviewed_facts(doc):
    rec = next(r for r in doc["logs"] if r["log_id"] == "log53")
    d = flag_on_disposition(rec)
    assert d["corrected_start"] == rec["corrected_start"]
    assert d["corrected_end"] == rec["corrected_end"]
    assert d["corrected_sheets"] == (rec["corrected_sheets"] or [])


def test_disposition_abstain_never_drawable(doc):
    rec = next(r for r in doc["logs"] if r["log_id"] == "log38")
    d = flag_on_disposition(rec)
    assert d["drawable_status"] == "abstain"
    assert d["bucket"] == ADJ_BUCKET_ABSTAIN
