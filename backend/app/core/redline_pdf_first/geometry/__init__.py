"""AP/structure-anchored geometry (Slice B): deterministic identity binding.

Pure data — NO ``fitz``, NO KMZ parsing, NO network. Consumes the RESOLVED anchor
tables (anchors.json / sheet_station_model.json) and attaches a coord-free frame
plus EXACT-match geo_anchors to a selected segment's ``placement``.
"""
from .identity_binder import bind_segment, load_tables, normalize_identity  # noqa: F401

__all__ = ["bind_segment", "load_tables", "normalize_identity"]
