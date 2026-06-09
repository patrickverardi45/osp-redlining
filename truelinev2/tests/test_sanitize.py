from truelinev2.security.sanitize import escape_html


def test_script_neutralized():
    out = escape_html("<script>alert('x')</script>")
    assert "<script>" not in out and "&lt;script&gt;" in out


def test_all_chars():
    assert escape_html("a&b\"c'd<e>f") == "a&amp;b&quot;c&#39;d&lt;e&gt;f"


def test_none():
    assert escape_html(None) == ""
