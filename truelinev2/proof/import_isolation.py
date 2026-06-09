"""Prove v2 is not a wrapper: AST-scan every truelinev2 module and assert ZERO
imports of old-app code (``app`` / ``main`` / ``redline_pdf_first`` / ``tl_core``
/ ``backend``). Relative imports are intra-package and allowed.

``scan_violations`` is reused by the pytest guard (tests/test_import_isolation.py).
Run standalone: python -m truelinev2.proof.import_isolation
"""
from __future__ import annotations

import ast
import os
from typing import List, Set, Tuple

FORBIDDEN = {"app", "main", "redline_pdf_first", "tl_core", "backend"}
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # truelinev2/


def _import_roots(node: ast.AST) -> Set[str]:
    out: Set[str] = set()
    if isinstance(node, ast.Import):
        for n in node.names:
            out.add(n.name.split(".")[0])
    elif isinstance(node, ast.ImportFrom):
        if node.level and node.level > 0:
            return out  # relative import — intra-package, fine
        if node.module:
            out.add(node.module.split(".")[0])
    return out


def scan_violations(root: str = ROOT) -> List[Tuple[str, str]]:
    """Return [(relpath, reason)] for any forbidden import or syntax error."""
    files = []
    for dp, _dn, fns in os.walk(root):
        for fn in fns:
            if fn.endswith(".py"):
                files.append(os.path.join(dp, fn))
    violations: List[Tuple[str, str]] = []
    for f in files:
        try:
            with open(f, encoding="utf-8") as fh:
                tree = ast.parse(fh.read(), filename=f)
        except SyntaxError as exc:
            violations.append((os.path.relpath(f, root), f"SYNTAX: {exc}"))
            continue
        for node in ast.walk(tree):
            for r in _import_roots(node):
                if r in FORBIDDEN:
                    violations.append((os.path.relpath(f, root), f"imports {r!r}"))
    return violations


def main() -> int:
    violations = scan_violations(ROOT)
    print(f"[import-isolation] forbidden roots: {sorted(FORBIDDEN)}")
    if violations:
        for f, why in violations:
            print(f"  VIOLATION: {f}: {why}")
        print("[import-isolation] FAIL")
        return 1
    print("[import-isolation] PASS - zero old-app imports")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
