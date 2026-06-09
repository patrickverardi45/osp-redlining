"""Output encoding for any user-/OCR-/filename-derived string surfaced as HTML.
Escape at the sink (the lesson from the old app's unescaped print path)."""
from __future__ import annotations

_ESC = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}


def escape_html(value: object) -> str:
    s = "" if value is None else str(value)
    return "".join(_ESC.get(ch, ch) for ch in s)
