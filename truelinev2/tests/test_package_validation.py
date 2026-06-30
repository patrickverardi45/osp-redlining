"""Proof for the read-only cold-package eligibility + validation intake path.

It must make a FUTURE real/fresh package pluggable (drop a package.json + files -> honest observer report) while
NEVER pretending synthetic fixtures prove real-world generalization. provenance_class is advisory; source
evidence overrides it. No placement, no promotion, no store/job work. No eligible real/fresh package exists in
the repo today (only synthetic), so the eligible-fresh branch is exercised with a manufactured plan to test the
CLASSIFICATION + observer wiring — not to claim generalization.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from truelinev2.extract.run_geometry_observer import BRANCH_FORKED
from truelinev2.harness.package_validation import (
    AMBIGUOUS_EVIDENCE,
    CLASS_VERIFICATION_MISSING,
    ELIGIBLE_FRESH_NONRECOGNIZED,
    INCOMPLETE_UPLOAD,
    INELIGIBLE_ACTIVE_FIELD_CORPUS,
    INELIGIBLE_RECOGNIZED_WORK_CORPUS,
    NO_DRAWN_COORDINATE_EVIDENCE,
    PACKAGE_NOT_FOUND,
    PACKAGE_UNREADABLE,
    PROV_ACTIVE_FIELD,
    PROV_FRESH,
    PROV_SYNTHETIC,
    REAL_FRESH_PACKAGE_VALIDATION_PENDING,
    SYNTHETIC_TEST_ONLY,
    validate_package,
)
from truelinev2.harness.synth import (
    borelog_xlsx,
    plan_clean_bore_with_notes,
    plan_forked_run_with_notes,
    plan_leader_traced_with_notes,
)
from truelinev2.extract.leader_symbol_trace import LEADER_TRACED_SYMBOL

_BORE = {"bore_label": "bore-1", "sheet": 1, "start_ft": 1175.0, "end_ft": 1325.0}


def _make_pkg(tmp_path, name, plan_bytes, *, provenance_class, bores=(_BORE,), with_borelog=True):
    d = tmp_path / name
    (d / "uploads").mkdir(parents=True)
    uploads = [{"kind": "PLAN_PDF", "filename": "plan.pdf"}]
    (d / "uploads" / "plan.pdf").write_bytes(plan_bytes)
    if with_borelog:
        uploads.append({"kind": "BORE_LOG", "filename": "bore.xlsx"})
        (d / "uploads" / "bore.xlsx").write_bytes(borelog_xlsx())
    (d / "package.json").write_text(json.dumps({
        "package_id": name, "provenance_class": provenance_class,
        "uploads": uploads, "bores": list(bores)}), encoding="utf-8")
    return d


# ----------------------------------------------------------------------------------------------------------- #
# Eligibility classification (source evidence overrides the declared class).
# ----------------------------------------------------------------------------------------------------------- #
def test_eligible_fresh_branch_runs_the_observer(tmp_path):
    """Exercises the branch a FUTURE real package takes (manufactured plan declared FRESH, non-recognized,
    complete) — tests the classification + observer wiring, NOT real generalization."""
    d = _make_pkg(tmp_path, "fresh", plan_leader_traced_with_notes(), provenance_class=PROV_FRESH)
    r = validate_package(d)
    assert r.eligibility == ELIGIBLE_FRESH_NONRECOGNIZED
    assert r.corpus_class == PROV_FRESH and r.recognized is False and r.real_validation is True
    assert r.candidates and r.candidates[0].start_provenance == LEADER_TRACED_SYMBOL
    assert r.candidates[0].two_d_verified is True
    assert r.placement_performed is False and "no placement" in r.note


def test_synthetic_declared_flows_through_but_is_not_real_validation(tmp_path):
    d = _make_pkg(tmp_path, "synth", plan_leader_traced_with_notes(), provenance_class=PROV_SYNTHETIC)
    r = validate_package(d)
    assert r.eligibility == SYNTHETIC_TEST_ONLY
    assert r.real_validation is False                       # NEVER counted as real generalization
    assert r.candidates                                     # observer path still exercised
    assert REAL_FRESH_PACKAGE_VALIDATION_PENDING in r.auto_blockers
    assert r.placement_performed is False


def test_synthetic_root_overrides_a_fresh_claim(tmp_path):
    """A package declared FRESH but located under a synthetic root is SYNTHETIC_TEST_ONLY — synthetic location
    overrides the declared class, so a synth fixture can never be counted as real validation."""
    d = _make_pkg(tmp_path, "rooted", plan_leader_traced_with_notes(), provenance_class=PROV_FRESH)
    r = validate_package(d, synthetic_roots=[tmp_path])
    assert r.eligibility == SYNTHETIC_TEST_ONLY and r.real_validation is False


def test_recognized_registry_overrides_a_fresh_claim(tmp_path):
    """Declared FRESH, but the plan's sha256 is in the recognized-corpus registry -> work corpus, ineligible."""
    plan = plan_leader_traced_with_notes()
    d = _make_pkg(tmp_path, "reg", plan, provenance_class=PROV_FRESH)
    registry = {hashlib.sha256(plan).hexdigest(): {"render": "..."}}
    r = validate_package(d, recognized_registry=registry)
    assert r.eligibility == INELIGIBLE_RECOGNIZED_WORK_CORPUS
    assert r.recognized is True and r.real_validation is False
    assert not r.candidates                                 # not run as proof


def test_declared_active_field_corpus_is_rejected(tmp_path):
    d = _make_pkg(tmp_path, "field", plan_leader_traced_with_notes(), provenance_class=PROV_ACTIVE_FIELD)
    r = validate_package(d)
    assert r.eligibility == INELIGIBLE_ACTIVE_FIELD_CORPUS and r.real_validation is False


def test_incomplete_upload_names_the_missing_inputs(tmp_path):
    d = _make_pkg(tmp_path, "incomplete", plan_leader_traced_with_notes(),
                  provenance_class=PROV_FRESH, with_borelog=False)
    r = validate_package(d)
    assert r.eligibility == INCOMPLETE_UPLOAD
    assert "BORE_LOG" in r.source_files_missing
    assert "PLAN_PDF" in r.source_files_present


def test_incomplete_when_no_bore_spans(tmp_path):
    d = _make_pkg(tmp_path, "nobore", plan_leader_traced_with_notes(), provenance_class=PROV_FRESH, bores=())
    r = validate_package(d)
    assert r.eligibility == INCOMPLETE_UPLOAD and "bore" in r.eligibility_reason


def test_ambiguous_branch_evidence_is_non_promoting(tmp_path):
    d = _make_pkg(tmp_path, "fork", plan_forked_run_with_notes(), provenance_class=PROV_FRESH)
    r = validate_package(d)
    assert r.eligibility == ELIGIBLE_FRESH_NONRECOGNIZED   # eligible by class, but the evidence refuses
    c = r.candidates[0]
    assert c.branch_uniqueness == BRANCH_FORKED and c.would_reject is True
    assert c.two_d_verified is False
    assert AMBIGUOUS_EVIDENCE in r.auto_blockers


def test_missing_drawn_coordinate_is_non_promoting(tmp_path):
    d = _make_pkg(tmp_path, "nosym", plan_clean_bore_with_notes(), provenance_class=PROV_FRESH)
    r = validate_package(d)
    c = r.candidates[0]
    assert c.two_d_verified is False
    assert NO_DRAWN_COORDINATE_EVIDENCE in r.auto_blockers


def test_class_verification_always_a_blocker(tmp_path):
    d = _make_pkg(tmp_path, "cv", plan_leader_traced_with_notes(), provenance_class=PROV_FRESH)
    r = validate_package(d)
    assert CLASS_VERIFICATION_MISSING in r.auto_blockers     # generic class verification still missing
    assert r.candidates[0].class_verified is False


def test_package_not_found(tmp_path):
    r = validate_package(tmp_path / "does-not-exist")
    assert r.eligibility == PACKAGE_NOT_FOUND and r.real_validation is False


def test_package_unreadable_without_manifest(tmp_path):
    d = tmp_path / "no-manifest"
    (d / "uploads").mkdir(parents=True)
    r = validate_package(d)
    assert r.eligibility == PACKAGE_UNREADABLE


def test_validation_is_read_only(tmp_path):
    d = _make_pkg(tmp_path, "ro", plan_leader_traced_with_notes(), provenance_class=PROV_FRESH)
    before = sorted(p.name for p in (d / "uploads").iterdir()) + ["package.json"]
    validate_package(d)
    after = sorted(p.name for p in (d / "uploads").iterdir()) + ["package.json"]
    assert before == after                                  # no files created/removed; read-only


def test_no_eligible_real_fresh_package_among_synthetic_fixtures(tmp_path):
    """The repo's only cold packages are synthetic; presented honestly (declared synthetic OR under the
    synthetic root) they are SYNTHETIC_TEST_ONLY, never real validation. No eligible real/fresh package exists."""
    a = _make_pkg(tmp_path / "root", "p1", plan_leader_traced_with_notes(), provenance_class=PROV_SYNTHETIC)
    b = _make_pkg(tmp_path / "root", "p2", plan_clean_bore_with_notes(), provenance_class=PROV_FRESH)
    reps = [validate_package(a, synthetic_roots=[tmp_path / "root"]),
            validate_package(b, synthetic_roots=[tmp_path / "root"])]
    assert all(rep.real_validation is False for rep in reps)
    assert all(rep.eligibility == SYNTHETIC_TEST_ONLY for rep in reps)
