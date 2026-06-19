"""Engine adapter no-raise contract: a missing/broken engine must come back as a
contained ERROR result, never an exception into the caller."""
from __future__ import annotations

from tl_core.adapters.engine_pdf_first import PdfFirstEngine
from tl_core.domain.redline import RedlineResult


def test_run_never_raises_and_returns_result(tmp_path):
    eng = PdfFirstEngine(engine_root=tmp_path / "no-engine-here", render_crops=False)
    res = eng.run("/no/such/bore.xlsx", "/no/such/plan.pdf")
    assert isinstance(res, RedlineResult)
    assert res.status in ("OK", "FAIL_SAFE_GLOBAL", "ERROR")
    assert res.placements == [] or res.status == "OK"
