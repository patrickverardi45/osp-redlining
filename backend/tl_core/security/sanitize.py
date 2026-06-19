"""Output encoding for any user-/OCR-/filename-derived string surfaced to a UI.

The monolith's CloseoutPacket print path concatenated such strings into
``document.write()`` with no escaping (Stream-6 2a — confirmed stored-XSS via the
operator-supplied override ``reason``, uploaded filenames, and OCR text). tl_core
escapes at the sink. Mirrors the safe ``esc()`` already present at
``web/src/lib/office/sessionPacketHtml.ts``.
"""
from __future__ import annotations

_HTML_ESCAPES = {
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
}


def escape_html(value: object) -> str:
    """Entity-escape a value for safe inclusion in HTML text OR an attribute.

    Escaping both quote styles makes the result safe in single- and double-quoted
    attributes as well as element text.
    """
    s = "" if value is None else str(value)
    return "".join(_HTML_ESCAPES.get(ch, ch) for ch in s)
