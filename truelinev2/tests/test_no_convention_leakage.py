"""Drift guard 1: convention/customer names must NOT leak into the
convention-agnostic core. They may live ONLY in extract/** and ingest/borelog_*
(the dialect/format homes) + registry/proof/tests. If the core ever needs an
``if odot:`` branch, that's the seam breaking — this test fails first.
"""
from __future__ import annotations

import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # truelinev2/
CORE_DIRS = ["match", "render", "store", "api", "schema", "security", "review"]
CORE_FILES = ["service.py", "config.py", "context.py", "stations.py", "__init__.py"]
FORBIDDEN = re.compile(r"(?i)\b(brenham|odot|tulsa|creek|nextlink|verofy)\b")


def _core_py_files():
    files = []
    for d in CORE_DIRS:
        for dp, _dn, fns in os.walk(os.path.join(ROOT, d)):
            if "__pycache__" in dp:
                continue
            files += [os.path.join(dp, fn) for fn in fns if fn.endswith(".py")]
    for f in CORE_FILES:
        p = os.path.join(ROOT, f)
        if os.path.isfile(p):
            files.append(p)
    return files


def test_no_convention_strings_in_core():
    offenders = []
    for f in _core_py_files():
        with open(f, encoding="utf-8") as fh:
            for i, line in enumerate(fh, 1):
                if FORBIDDEN.search(line):
                    offenders.append((os.path.relpath(f, ROOT), i, line.strip()[:80]))
    assert not offenders, "convention strings leaked into the core:\n" + "\n".join(map(str, offenders))
