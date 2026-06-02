"""PDF subpackage — the ONLY place ``fitz`` (PyMuPDF) may be imported.

Enforced by ``tests/test_import_boundaries.py``. Everything here works in, or
converts to, *display* (post-rotation) coordinate space so downstream code
never has to know about page rotation.
"""
