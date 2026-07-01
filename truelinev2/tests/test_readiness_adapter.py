"""Proof for the end-to-end read-only package readiness runner (truelinev2/harness/readiness_adapter.py +
readiness_source.py).

It proves the adapter turns a package SOURCE (a folder carrying a manifest + recorded read-only Track B observer
findings) into the same readiness classification the hand-fed classifier produces — end to end through all four
seams (discovery -> normalization -> classification -> serialization). Specifically:

  1. the four canonical public cold-package classifications reproduce end-to-end from folders;
  2. public-cold-009 stays blocked UPSTREAM of the anchors (its span source is missing) even though its anchors
     would resolve;
  3. public-cold-011 becomes KEEP_BLOCKED ONLY via the explicit owner/adversarial marker, never autonomously;
  4. the adapter modules import nothing from renderer / placement / backend / web / product runtime;
  5. the new module / test / doc paths are name-free.

No PDF is opened here: the recorded ``observer_findings.json`` is the "observer outputs where already available"
path. The live-observer seam is exercised only for its guard behavior (no plan -> None).
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

from truelinev2.harness.readiness_adapter import (
    evidence_from_findings,
    evidence_from_live_observers,
    run_readiness,
    run_readiness_for_case,
    run_readiness_for_folder,
    format_readiness,
)
from truelinev2.harness.readiness_source import (
    OBSERVER_FINDINGS_FILENAME,
    SOURCE_PACKAGE_FOLDER,
    discover_package,
    parse_observer_findings,
)
from truelinev2.harness.review_readiness import (
    ANCHOR_BLOCKED,
    KEEP_BLOCKED,
    MISSING_BORE_SPAN_SOURCE,
    NO_SOURCE_CONFIRMED_SPAN,
    PACKAGE_RECOGNIZED_CONTROL,
)

_HARNESS = Path(__file__).resolve().parents[1] / "harness"
_ADAPTER_MODULES = [_HARNESS / "readiness_source.py", _HARNESS / "readiness_adapter.py"]


# ----------------------------------------------------------------------------------------------------------- #
# The four public cold-package findings, recorded as name-free observer_findings.json in a package folder.
# ----------------------------------------------------------------------------------------------------------- #
_FINDINGS = {
    "public-cold-001": {                                   # recognized -> control lane
        "recognized": True, "plan_readable": True,
    },
    "public-cold-002": {                                   # span present, route-attached anchors unresolved
        "recognized": False, "plan_readable": True,
        "span_source_files": ["BORE_LOG"], "plan_span_layer_inspected": True,
        "source_confirmed_span_count": 1,
        "anchor_start_status": "AMBIGUOUS_ANCHOR", "anchor_end_status": "AMBIGUOUS_ANCHOR",
        "route_status": None,
    },
    "public-cold-009": {                                   # plan-only; anchors WOULD resolve; no source span
        "recognized": False, "plan_readable": True,
        "span_source_files": [], "plan_span_layer_inspected": True,
        "source_confirmed_span_count": 0,
        "anchor_start_status": "ANCHOR_RESOLVED_TO_SYMBOL",
        "anchor_end_status": "ANCHOR_RESOLVED_TO_ROUTE_ENDPOINT",
        "route_status": None,
    },
    "public-cold-011": {                                   # source-confirmed printed span, but two independent
        "recognized": False, "plan_readable": True,        # structural blockers downstream + an owner marker
        "keep_blocked": True,
        "keep_blocked_reason": "two independent structural blockers: fragmented route + off-route labels",
        "span_source_files": [], "plan_span_layer_inspected": True,
        "source_confirmed_span_count": 1,                  # bound a printed 'Sta X to Y' span (PRINTED_STA_CALLOUT)
        "anchor_start_status": "NO_SUPPORTED_ANCHOR", "anchor_end_status": "NO_SUPPORTED_ANCHOR",
        "route_status": "NO_MAIN_ROUTE",
    },
}

_EXPECTED = {
    "public-cold-001": PACKAGE_RECOGNIZED_CONTROL,
    "public-cold-002": ANCHOR_BLOCKED,
    "public-cold-009": MISSING_BORE_SPAN_SOURCE,
    "public-cold-011": KEEP_BLOCKED,
}


def _make_case(root: Path, case_id: str, findings: dict, *, with_manifest: bool = True) -> Path:
    d = root / case_id
    (d / "uploads").mkdir(parents=True)
    if with_manifest:
        (d / "package.json").write_text(json.dumps({
            "package_id": case_id, "provenance_class": "FRESH_NONRECOGNIZED",
            "uploads": [{"kind": "PLAN_PDF", "filename": "plan.pdf"}],
            "bores": [{"bore_label": "bore-1", "sheet": 1, "start_ft": 0.0, "end_ft": 100.0}],
        }), encoding="utf-8")
    (d / OBSERVER_FINDINGS_FILENAME).write_text(json.dumps(findings), encoding="utf-8")
    return d


# ----------------------------------------------------------------------------------------------------------- #
# (1) end-to-end canonical classifications.
# ----------------------------------------------------------------------------------------------------------- #
def test_four_canonical_classifications_end_to_end(tmp_path):
    for case_id, findings in _FINDINGS.items():
        d = _make_case(tmp_path, case_id, findings)
        report = run_readiness_for_folder(d)
        assert report is not None, case_id
        assert report.package_id == case_id
        assert report.status == _EXPECTED[case_id], "%s -> %s (expected %s)" % (
            case_id, report.status, _EXPECTED[case_id])
        assert report.draws_anything is False and report.performs_placement is False
        assert report.detail.get("findings_origin") == "recorded"


def test_case_reference_resolution_reproduces_classifications(tmp_path):
    """A case reference (id + injected cold-packages root) resolves to the same end-to-end classification."""
    for case_id, findings in _FINDINGS.items():
        _make_case(tmp_path, case_id, findings)
    for case_id in _FINDINGS:
        report = run_readiness_for_case(case_id, tmp_path)
        assert report is not None and report.status == _EXPECTED[case_id]


# ----------------------------------------------------------------------------------------------------------- #
# (2) 009 stays blocked UPSTREAM of the anchors.
# ----------------------------------------------------------------------------------------------------------- #
def test_009_blocked_upstream_of_anchors_despite_resolvable_anchors(tmp_path):
    d = _make_case(tmp_path, "public-cold-009", _FINDINGS["public-cold-009"])
    report = run_readiness_for_folder(d)
    assert report.status == MISSING_BORE_SPAN_SOURCE
    assert NO_SOURCE_CONFIRMED_SPAN in report.contributing_reasons
    assert report.stage == "SPAN_SOURCE"                       # stopped at the span stage, before anchors
    assert report.detail.get("anchors_would_resolve") is True  # anchors would bind; the blocker is the span
    assert report.recommended_next_input == "BORE_LOG_OR_BORE_SCHEDULE_NAMING_ONE_SPAN"


# ----------------------------------------------------------------------------------------------------------- #
# (3) 011 is KEEP_BLOCKED only via the owner marker, never autonomously.
# ----------------------------------------------------------------------------------------------------------- #
def test_011_not_keep_blocked_without_owner_marker(tmp_path):
    findings = dict(_FINDINGS["public-cold-011"])
    findings["keep_blocked"] = False                            # remove the owner/adversarial reclassification
    findings["keep_blocked_reason"] = ""
    d = _make_case(tmp_path, "public-cold-011-nomarker", findings)
    report = run_readiness_for_folder(d)
    assert report.status != KEEP_BLOCKED                        # the classifier never self-promotes to terminal
    assert report.status == ANCHOR_BLOCKED                      # classifies by stage (anchor first)
    assert report.double_structural_block is True              # both stages blocked -> advisory only
    assert report.keep_blocked_candidate is True


def test_011_keep_blocked_with_owner_marker(tmp_path):
    d = _make_case(tmp_path, "public-cold-011", _FINDINGS["public-cold-011"])
    report = run_readiness_for_folder(d)
    assert report.status == KEEP_BLOCKED


# ----------------------------------------------------------------------------------------------------------- #
# (4) the adapter imports nothing from renderer / placement / backend / web / product runtime.
# ----------------------------------------------------------------------------------------------------------- #
_FORBIDDEN_IMPORT_SEGMENTS = {
    "render", "renderer", "placement", "cap_review", "_cap_review",
    "api", "store", "web", "contracts", "match",
}


def _imported_modules(src: str):
    mods = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            for a in node.names:
                mods.add(a.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                mods.add(node.module)
    return mods


def test_adapter_imports_no_forbidden_modules():
    for mod_path in _ADAPTER_MODULES:
        mods = _imported_modules(mod_path.read_text(encoding="utf-8"))
        for m in mods:
            segments = set(m.split("."))
            leaked = segments & _FORBIDDEN_IMPORT_SEGMENTS
            assert not leaked, "%s imports forbidden module %r (%s)" % (mod_path.name, m, leaked)


# (5) The new module / doc / test paths are covered by the name-free guard
#     (test_no_specific_names_in_cold_package_harness.py): the two harness modules are in HARNESS_MODULES
#     (active structural check + env NAME_TOKENS), and the new doc + this test file are in its
#     EXTRA_NAME_FREE_TEXT_PATHS (env NAME_TOKENS). This test file embeds no real names itself.


# ----------------------------------------------------------------------------------------------------------- #
# Discovery + read-only + live-seam guard.
# ----------------------------------------------------------------------------------------------------------- #
def test_discover_package_reads_manifest_and_findings(tmp_path):
    d = _make_case(tmp_path, "public-cold-002", _FINDINGS["public-cold-002"])
    src = discover_package(d)
    assert src.kind == SOURCE_PACKAGE_FOLDER
    assert src.package_id == "public-cold-002"
    assert src.findings is not None and src.findings.source_confirmed_span_count == 1
    assert src.plan_path is None                    # no real plan bytes written -> uploads/plan.pdf absent


def test_adapter_is_read_only(tmp_path):
    d = _make_case(tmp_path, "public-cold-009", _FINDINGS["public-cold-009"])
    before = sorted(p.name for p in d.iterdir())
    run_readiness_for_folder(d)
    after = sorted(p.name for p in d.iterdir())
    assert before == after                          # created / removed nothing


def test_missing_source_returns_none(tmp_path):
    assert run_readiness_for_folder(tmp_path / "does-not-exist") is None


def test_live_seam_returns_none_without_a_plan(tmp_path):
    """The live-observer normalization degrades gracefully (no plan -> None) and needs no PDF to prove it."""
    src = discover_package(_make_case(tmp_path, "public-cold-009", _FINDINGS["public-cold-009"]))
    assert src.plan_path is None
    assert evidence_from_live_observers(src) is None


def test_recorded_evidence_normalization_is_pure():
    findings = parse_observer_findings(_FINDINGS["public-cold-009"])
    ev = evidence_from_findings("public-cold-009", findings)
    assert ev.span is not None and ev.span.source_confirmed_span_count == 0
    assert ev.anchor is not None and ev.anchor.both_resolved is True   # anchors would resolve
    assert ev.route is None                                            # route not evaluated
    assert ev.detail["findings_origin"] == "recorded"


def test_report_serialization_roundtrip(tmp_path):
    d = _make_case(tmp_path, "public-cold-001", _FINDINGS["public-cold-001"])
    report = run_readiness_for_folder(d)
    text = format_readiness(report)
    assert '"status"' in text and '"PACKAGE_RECOGNIZED_CONTROL"' in text


def test_run_readiness_without_findings_and_no_live_returns_none(tmp_path):
    d = tmp_path / "manifest-only"
    (d / "uploads").mkdir(parents=True)
    (d / "package.json").write_text(json.dumps({
        "package_id": "manifest-only", "provenance_class": "FRESH_NONRECOGNIZED",
        "uploads": [{"kind": "PLAN_PDF", "filename": "plan.pdf"}], "bores": []}), encoding="utf-8")
    src = discover_package(d)
    assert src.findings is None
    assert run_readiness(src, allow_live=False) is None      # no recorded findings, live disabled
