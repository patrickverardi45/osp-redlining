"""Output encoding — the fix for the monolith's unescaped document.write sink
(Stream-6 2a, confirmed stored-XSS)."""
from __future__ import annotations

from tl_core.security.sanitize import escape_html


def test_script_tag_is_neutralized():
    out = escape_html("<script>alert('x')</script>")
    assert "<script>" not in out
    assert "&lt;script&gt;" in out
    assert "&#39;" in out


def test_all_dangerous_chars_escaped():
    assert escape_html('a&b"c\'d<e>f') == "a&amp;b&quot;c&#39;d&lt;e&gt;f"


def test_none_becomes_empty():
    assert escape_html(None) == ""


def test_plain_text_unchanged():
    assert escape_html("bore_log51 sheet 8") == "bore_log51 sheet 8"
