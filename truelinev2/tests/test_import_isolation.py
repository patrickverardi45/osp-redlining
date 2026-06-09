"""Drift guard 2: zero imports of old-app code (app/main/redline_pdf_first/
tl_core/backend) anywhere in truelinev2 — enforced under pytest, not just the
standalone proof."""
from __future__ import annotations

from truelinev2.proof.import_isolation import ROOT, scan_violations


def test_zero_old_app_imports():
    violations = scan_violations(ROOT)
    assert violations == [], "old-app imports / syntax errors found:\n" + "\n".join(map(str, violations))
