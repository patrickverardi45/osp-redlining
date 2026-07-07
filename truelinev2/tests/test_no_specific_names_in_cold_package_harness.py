"""Naming guard for the cold-package evaluation harness: real customer/project/person/location tokens must
never live in this reusable code. Mirrors test_no_specific_names_in_pipeline_contract.py (same two
mechanisms) for the truelinev2/harness package. This test embeds NO real names itself.
"""
from __future__ import annotations

import ast
import os
import re
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1] / "harness"
HARNESS_MODULES = [
    HARNESS / "__init__.py",
    HARNESS / "fixtures.py",
    HARNESS / "synth.py",
    HARNESS / "runner.py",
    HARNESS / "scorer.py",
    HARNESS / "report.py",
    HARNESS / "__main__.py",
    HARNESS / "package_validation.py",
    HARNESS / "review_readiness.py",
    HARNESS / "readiness_source.py",
    HARNESS / "readiness_adapter.py",
    HARNESS / "span_source.py",
    HARNESS / "span_extractor.py",
    HARNESS / "endpoint_binding.py",
    HARNESS / "route_verification.py",
    HARNESS / "complete_package_qa.py",
    HARNESS / "review_candidate.py",
    HARNESS / "product_readiness_bridge.py",
    HARNESS / "structure_datum_reasoning.py",
]

# Non-module text paths (docs + tests) that must also stay free of operator-supplied real names. Scanned by the
# same optional NAME_TOKENS mechanism; this list embeds no real names itself.
_ROOT = HARNESS.parent
EXTRA_NAME_FREE_TEXT_PATHS = [
    _ROOT / "docs" / "SOURCE_COMPLETENESS_REVIEW_READINESS.md",
    _ROOT / "docs" / "SOURCE_SPAN_EXTRACTOR.md",
    _ROOT / "docs" / "SOURCE_BACKED_ENDPOINT_BINDING.md",
    _ROOT / "docs" / "SOURCE_BACKED_ROUTE_VERIFICATION.md",
    _ROOT / "docs" / "COMPLETE_PACKAGE_QA_HARNESS.md",
    _ROOT / "docs" / "SOURCE_BACKED_REVIEW_CANDIDATE.md",
    _ROOT / "docs" / "STAGING_REVIEW_CANDIDATE_PRODUCT_WIRING.md",
    _ROOT / "tests" / "test_review_readiness.py",
    _ROOT / "tests" / "test_readiness_adapter.py",
    _ROOT / "tests" / "test_span_extractor.py",
    _ROOT / "tests" / "test_endpoint_binding.py",
    _ROOT / "tests" / "test_route_verification.py",
    _ROOT / "tests" / "test_complete_package_qa.py",
    _ROOT / "tests" / "test_review_candidate.py",
    _ROOT / "tests" / "test_product_readiness_wiring.py",
    _ROOT / "tests" / "test_structure_datum_reasoning.py",
    _ROOT / "proof" / "run_cold_package_readiness_census.py",
]


def _sources():
    return {p.name: p.read_text(encoding="utf-8") for p in HARNESS_MODULES}


def _is_identity_param(name: str) -> bool:
    return name.endswith("_id") or name == "display_name"


def test_modules_exist():
    for p in HARNESS_MODULES:
        assert p.is_file(), "missing harness module: %s" % p


def test_operator_supplied_name_tokens_absent():
    """(A) If NAME_TOKENS is set, none of those tokens may appear in the harness modules."""
    raw = os.environ.get("NAME_TOKENS", "").strip()
    if not raw:
        return  # optional; set NAME_TOKENS='token_a|token_b' to enforce a deployment's real names
    tokens = [t for t in re.split(r"[|,\s]+", raw) if t]
    blob = "\n".join(_sources().values()).lower()
    hits = sorted({t for t in tokens
                   if re.search(r"\b" + re.escape(t.lower()) + r"\b", blob)})
    assert not hits, "operator-supplied NAME_TOKENS leaked into harness modules: %r" % hits


def test_identity_parameters_have_no_defaults():
    """(B) Identity is injected at runtime, never defaulted in code (so a name cannot be hardcoded)."""
    offenders = []
    for name, src in _sources().items():
        tree = ast.parse(src, filename=name)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            a = node.args
            positional = list(a.posonlyargs) + list(a.args)
            pos_defaults = [None] * (len(positional) - len(a.defaults)) + list(a.defaults)
            pairs = list(zip(positional, pos_defaults)) + list(zip(a.kwonlyargs, a.kw_defaults))
            for arg, default in pairs:
                if default is not None and _is_identity_param(arg.arg):
                    offenders.append("%s:%s(%s=...)" % (name, node.name, arg.arg))
    assert not offenders, "identity params must not have defaults (inject at runtime): %s" % offenders


def test_extra_name_free_text_paths_exist():
    for p in EXTRA_NAME_FREE_TEXT_PATHS:
        assert p.is_file(), "missing name-free text path: %s" % p


def test_operator_supplied_name_tokens_absent_in_extra_paths():
    """(A) extended to docs + tests: if NAME_TOKENS is set, none of those tokens may appear there either."""
    raw = os.environ.get("NAME_TOKENS", "").strip()
    if not raw:
        return  # optional; set NAME_TOKENS='token_a|token_b' to enforce a deployment's real names
    tokens = [t for t in re.split(r"[|,\s]+", raw) if t]
    blob = "\n".join(p.read_text(encoding="utf-8") for p in EXTRA_NAME_FREE_TEXT_PATHS).lower()
    hits = sorted({t for t in tokens
                   if re.search(r"\b" + re.escape(t.lower()) + r"\b", blob)})
    assert not hits, "operator-supplied NAME_TOKENS leaked into docs/tests: %r" % hits
