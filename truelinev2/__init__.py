"""TrueLine v2 — an independent, clean PDF-first redline product.

This package is a clean-room reimplementation. The old TrueLine app
(``backend/main.py``, ``backend/app/**``, ``redline_pdf_first``, ``tl_core``) is
used ONLY as a behavioral specification — it is never imported here. v2 imports
only standard third-party infrastructure libraries (PyMuPDF, openpyxl, Pillow,
pydantic, FastAPI/uvicorn, sqlite, pytest).

Architectural thesis: only plan-evidence *extraction* is convention-specific (a
pluggable ``PlanDialect``); normalization, matching, scoring, tiering, rendering,
abstention, storage, and serving are convention-agnostic. Adding a new plan
convention (a different agency's plan format) is a new dialect, not an engine fork.
"""
from __future__ import annotations

__all__ = ["__version__"]
__version__ = "0.1.0"
