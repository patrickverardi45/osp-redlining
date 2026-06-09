"""Drift guard 3: no global mutable state (the old monolith's process-global
``STATE`` is the anti-pattern). Asserts: (a) no ``global`` statements in product
code; (b) no module-level binding to a mutable container literal for a
non-constant name (allowlist: the dialect registry + UPPER_CASE constants).
Scope: product code only (excludes tests/ and proof/).
"""
from __future__ import annotations

import ast
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # truelinev2/
EXCLUDE_DIRS = {"tests", "proof", "__pycache__"}
ALLOW_MUTABLE_NAMES = {"_DIALECTS"}  # the dialect registry: built once, read-only


def _is_const_name(name: str) -> bool:
    return name.lstrip("_").isupper()


def _product_py_files():
    files = []
    for dp, dn, fns in os.walk(ROOT):
        dn[:] = [d for d in dn if d not in EXCLUDE_DIRS]
        files += [os.path.join(dp, fn) for fn in fns if fn.endswith(".py")]
    return files


def _module_level_mutable_assigns(tree: ast.Module):
    out = []
    for node in tree.body:  # module level only
        if not isinstance(node, ast.Assign):
            continue
        v = node.value
        is_mut = isinstance(v, (ast.List, ast.Dict, ast.Set)) or (
            isinstance(v, ast.Call) and isinstance(v.func, ast.Name)
            and v.func.id in {"list", "dict", "set"})
        if not is_mut:
            continue
        for t in node.targets:
            if (isinstance(t, ast.Name) and not _is_const_name(t.id)
                    and not (t.id.startswith("__") and t.id.endswith("__"))  # module dunders
                    and t.id not in ALLOW_MUTABLE_NAMES):
                out.append(t.id)
    return out


def test_no_global_keyword_and_no_module_mutable_state():
    bad_global, bad_mut = [], []
    for f in _product_py_files():
        with open(f, encoding="utf-8") as fh:
            tree = ast.parse(fh.read(), filename=f)
        rel = os.path.relpath(f, ROOT)
        for node in ast.walk(tree):
            if isinstance(node, ast.Global):
                bad_global.append(rel)
        for name in _module_level_mutable_assigns(tree):
            bad_mut.append((rel, name))
    assert not bad_global, "global statements (forbidden): " + str(sorted(set(bad_global)))
    assert not bad_mut, "module-level mutable state (use injected/scoped state instead): " + str(bad_mut)
