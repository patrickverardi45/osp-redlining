"""G1+G2 — terminus evidence schema + read-only extractor.

Proves the observer-only extractor emits source-backed terminus evidence and the honest source-bound vs
missing-evidence distinction, and that it is NOT wired into the engine placement path (so it cannot change
placement/status or the deterministic frontier).
"""
from __future__ import annotations

import ast
import os
import re
from pathlib import Path

from truelinev2.extract import terminus_evidence as te
from truelinev2.extract.terminus_extractor import extract_termini
from truelinev2.harness.terminus_fixtures import build_terminus_fixtures, load_terminus_fixtures

_EXTRACT = Path(te.__file__).resolve().parent
_TERMINUS_MODULES = [
    _EXTRACT / "terminus_evidence.py",
    _EXTRACT / "terminus_extractor.py",
    _EXTRACT.parents[0] / "harness" / "terminus_fixtures.py",
    _EXTRACT.parents[0] / "contracts" / "terminus_report.py",   # G3 read-only display report (observer)
]


def test_seed_fixtures_match_expected(tmp_path):
    root = tmp_path / "term_fixtures"
    build_terminus_fixtures(root)
    fixtures = load_terminus_fixtures(root)
    assert {f.fixture_id for f in fixtures} == {
        "term-001-both-bound", "term-002-end-bound-start-missing", "term-003-none-bound"}

    for fx in fixtures:
        ev = extract_termini(fx.plan_path, fx.borelog_path)
        for which, observed in (("start", ev.start), ("end", ev.end)):
            exp = fx.expected[which]
            assert observed.source_bound == exp["source_bound"], (fx.fixture_id, which, observed)
            assert observed.source_type == exp["source_type"], (fx.fixture_id, which, observed)
            assert observed.blocker == exp["blocker"], (fx.fixture_id, which, observed)


def test_bound_endpoint_carries_verbatim_printed_proof(tmp_path):
    root = tmp_path / "term_fixtures"
    build_terminus_fixtures(root)
    by = {f.fixture_id: f for f in load_terminus_fixtures(root)}

    ev = extract_termini(by["term-001-both-bound"].plan_path, by["term-001-both-bound"].borelog_path)
    assert ev.both_source_bound
    # a source-bound endpoint is PRINTED, carries the verbatim note + structure label + provenance, no blocker
    assert ev.start.source_type == te.PRINTED_STRUCTURE_LABEL
    assert ev.start.source_text and "INSTALLER HH" in ev.start.structure_label
    assert ev.start.provenance == te.PRINTED_PLAN_TEXT and ev.start.confidence == 1.0
    assert ev.start.blocker is None
    assert ev.start.station_str == "11+75" and ev.end.station_str == "13+25"


def test_missing_endpoint_is_borelog_value_not_inferred(tmp_path):
    root = tmp_path / "term_fixtures"
    build_terminus_fixtures(root)
    by = {f.fixture_id: f for f in load_terminus_fixtures(root)}

    ev = extract_termini(by["term-003-none-bound"].plan_path, by["term-003-none-bound"].borelog_path)
    assert not ev.both_source_bound
    # missing-proof endpoints carry the bore-log STATION VALUE (source-backed) but are NOT source-bound, and
    # are never relabeled as printed or inferred-as-source.
    for end, code in ((ev.start, te.NO_PRINTED_START_STRUCTURE), (ev.end, te.NO_PRINTED_END_STRUCTURE)):
        assert end.source_bound is False
        assert end.source_type == te.BORE_LOG_ROW
        assert end.provenance == te.BORE_LOG_ROW_PARSED
        assert end.blocker == code
        assert end.station_ft is not None          # value known from the bore-log row
        assert end.source_text is None             # nothing printed to quote
    assert set(ev.missing_blockers) == {te.NO_PRINTED_START_STRUCTURE, te.NO_PRINTED_END_STRUCTURE}


def test_extractor_is_not_wired_into_the_engine_placement_path():
    """Observer-only guarantee: the placement orchestrator + uploaded-corpus engine handoff must NOT import or
    call the terminus extractor, so it can never change a placement, its status, or the deterministic frontier."""
    contracts = _EXTRACT.parents[0] / "contracts"
    for name in ("product_workflow.py", "uploaded_corpus_engine_handoff.py"):
        src = (contracts / name).read_text(encoding="utf-8")
        assert "terminus_extractor" not in src, "%s must not wire in the terminus extractor" % name


def test_terminus_modules_are_name_free():
    """(A) optional NAME_TOKENS denylist absent; (B) identity params never defaulted in code."""
    raw = os.environ.get("NAME_TOKENS", "").strip()
    if raw:
        tokens = [t for t in re.split(r"[|,\s]+", raw) if t]
        blob = "\n".join(p.read_text(encoding="utf-8") for p in _TERMINUS_MODULES).lower()
        hits = sorted({t for t in tokens if re.search(r"\b" + re.escape(t.lower()) + r"\b", blob)})
        assert not hits, "NAME_TOKENS leaked into terminus modules: %r" % hits

    offenders = []
    for p in _TERMINUS_MODULES:
        tree = ast.parse(p.read_text(encoding="utf-8"), filename=p.name)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            a = node.args
            positional = list(a.posonlyargs) + list(a.args)
            pos_defaults = [None] * (len(positional) - len(a.defaults)) + list(a.defaults)
            for arg, default in list(zip(positional, pos_defaults)) + list(zip(a.kwonlyargs, a.kw_defaults)):
                if default is not None and (arg.arg.endswith("_id") or arg.arg == "display_name"):
                    offenders.append("%s:%s(%s=...)" % (p.name, node.name, arg.arg))
    assert not offenders, "identity params must not have defaults: %s" % offenders
