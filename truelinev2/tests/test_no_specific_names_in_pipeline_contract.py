"""Naming guard for the permanent pipeline contract modules: real customer/project/person/location
tokens must never live in reusable code. This test embeds NO real names itself.

Two name-free mechanisms:
  (A) Operator-supplied denylist via the ``NAME_TOKENS`` env var (the docs/probe_v1_inventory.sh
      pattern; pipe/comma/space separated, case-insensitive). Operators/CI run with their deployment's
      real tokens to enforce absence; the repo stores none. Unset -> this part is a documented no-op.
  (B) Structural invariant (always on, no names needed): identity is INJECTED, never baked. No public
      function parameter that carries identity (a name ending in ``_id``, or ``display_name``) may have a
      default value — so a real name can never be hardcoded as a parameter default.
"""
from __future__ import annotations

import ast
import os
import re
from pathlib import Path

CONTRACTS = Path(__file__).resolve().parents[1] / "contracts"
PIPELINE_MODULES = [
    CONTRACTS / "customer_project.py",
    CONTRACTS / "processing_job.py",
    CONTRACTS / "upload_pipeline.py",
    CONTRACTS / "extracted_row.py",
    CONTRACTS / "reviewed_bore_log.py",
    CONTRACTS / "manifest_handoff.py",
    CONTRACTS / "kmz_export.py",
    CONTRACTS / "closeout_review.py",
]


def _sources():
    return {p.name: p.read_text(encoding="utf-8") for p in PIPELINE_MODULES}


def _is_identity_param(name: str) -> bool:
    return name.endswith("_id") or name == "display_name"


def test_modules_exist():
    for p in PIPELINE_MODULES:
        assert p.is_file(), "missing pipeline module: %s" % p


def test_operator_supplied_name_tokens_absent():
    """(A) If NAME_TOKENS is set, none of those tokens may appear in the pipeline modules."""
    raw = os.environ.get("NAME_TOKENS", "").strip()
    if not raw:
        return  # optional; set NAME_TOKENS='token_a|token_b' to enforce a deployment's real names
    tokens = [t for t in re.split(r"[|,\s]+", raw) if t]
    blob = "\n".join(_sources().values()).lower()
    # whole-word match so a short token can't false-positive on a substring (e.g. "pot" in "idempotent")
    hits = sorted({t for t in tokens
                   if re.search(r"\b" + re.escape(t.lower()) + r"\b", blob)})
    assert not hits, "operator-supplied NAME_TOKENS leaked into pipeline modules: %r" % hits


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
