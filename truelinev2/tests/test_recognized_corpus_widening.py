"""Phase 10 — recognized-corpus coverage widening (37 -> 50 via the committed all-50 union manifest).

The 13 ALREADY_DRAWN logs (no PNG in the callout-route-assembly sweep dir) are now reachable by resolving
their committed render from the all-50 union manifest, with each PNG's sha256 RE-VERIFIED against the
manifest before it is served. The 37 sweep-dir logs are untouched (sweep-glob-first). A single-PNG
cross-sheet render (log65) reports BOTH of its sheets (no silent drop).

The union-manifest checks skip when that render output is not present in this checkout (it is gitignored
machine-local render output, not committed source).
"""
from __future__ import annotations

from truelinev2.contracts import recognized_corpus_handoff as rch

_UNION = rch._DETERMINISTIC_UNION_MANIFEST


def test_sheets_from_name_handles_single_multi_and_odd_suffix():
    assert rch._sheets_from_name("log45_s10_redline_stroke") == (10,)
    assert rch._sheets_from_name("log7_s10_symbol_anchored_stroke") == (10,)
    assert rch._sheets_from_name("log25_design_path_s21_redline_stroke") == (21,)
    # the single-PNG cross-sheet render must yield BOTH sheets (never drop the second).
    assert rch._sheets_from_name("log65_s10_s9_cross_sheet_stroke") == (10, 9)
    assert rch._sheets_from_name("nothing_here") == (0,)


def test_already_drawn_logs_resolve_from_union_manifest():
    if not _UNION.is_file():
        import pytest
        pytest.skip("all-50 union manifest render output not present in this checkout")
    rch._union_cache.clear()
    thirteen = ["log7", "log25", "log45", "log50", "log51", "log52", "log53",
                "log59", "log64", "log65", "log66", "log69", "log71"]
    for lid in thirteen:
        arts = rch._deterministic_artifacts(lid)
        assert arts, "already-drawn %s should resolve from the union manifest" % lid
        for (mpath, src, sheets) in arts:
            assert mpath.startswith("artifacts/%s/" % lid)
            assert src.is_file()
            assert sheets and all(isinstance(s, int) for s in sheets)
    # log65's single cross-sheet PNG must carry BOTH sheets 9 and 10.
    sheets65 = sorted({s for (_p, _src, ss) in rch._deterministic_artifacts("log65") for s in ss})
    assert sheets65 == [9, 10]


def test_sweep_logs_take_precedence_over_union(monkeypatch, tmp_path):
    # A log present in the sweep dir is served from THERE (byte-identical), never the union fallback.
    png = b"\x89PNG\r\n\x1a\n"
    rdir = tmp_path / "sweep"
    rdir.mkdir()
    (rdir / "log9_s7_redline_stroke.png").write_bytes(png)
    (rdir / "log9_s14_redline_stroke.png").write_bytes(png)
    monkeypatch.setattr(rch, "_DETERMINISTIC_RENDER_DIR", rdir)
    arts = rch._deterministic_artifacts("log9")
    assert {a[1].parent for a in arts} == {rdir}                  # sourced from the sweep dir
    assert sorted({s for (_p, _src, ss) in arts for s in ss}) == [7, 14]
