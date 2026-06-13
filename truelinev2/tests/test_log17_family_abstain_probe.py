"""M8.25 -- bore_log17 family closure-abstain probe tests (offline; posture).

The milestone is a SAFE CLOSURE-ABSTAIN (no placement, census frozen). These
pin: the typed findings are not lane statuses; the no-promotion / no-render /
no-AUTO posture; that the accepted-grade set the 'log43 grade A' correction
rests on is {log25,51,59,65}; and that no engine module imports the probe.
"""
import inspect
from pathlib import Path

from truelinev2.proof import run_log17_family_abstain_probe as probe

PKG = Path(probe.__file__).resolve().parents[1]


def test_typed_findings_are_not_lane_statuses():
    from truelinev2.match.symbol_conduit_lane import (S_ELIGIBLE,
                                                      S_STRUCTURE_REQUIRED,
                                                      S_UNPRINTED)
    lane = {S_ELIGIBLE, S_STRUCTURE_REQUIRED, S_UNPRINTED}
    findings = {probe.FAMILY_CLOSED_BOTH_ABSTAIN,
                probe.FAMILY_RELATION_GROUPING_ONLY,
                probe.LOG43_SOURCE_QUALITY, probe.LOG44_SOURCE_PLAN_MISMATCH}
    assert findings.isdisjoint(lane)


def test_accepted_grades_exclude_the_family_and_grade_A_is_corrected():
    # the 'log43 resolved/grade A' premise correction rests on this set.
    assert probe.ACCEPTED_GRADES == {"log25", "log51", "log59", "log65"}
    assert "log43" not in probe.ACCEPTED_GRADES
    assert "log44" not in probe.ACCEPTED_GRADES


def test_placeable_siblings_prove_blocker_is_per_bore():
    # other-family split children that DO place -> blocker is per-bore, not
    # a family trait (so the family relation is grouping-only).
    assert probe.PLACEABLE_SIBLINGS == ("log51", "log59", "log65")


def test_no_promotion_no_auto_no_render():
    src = inspect.getsource(probe)
    assert '"verdict": "PASS" if ok else "FAILURE"' in src
    assert "AUTO" not in src.replace("no AUTO", "").replace("REVIEW/AUTO", "")
    assert "truelinev2.render" not in src
    assert "render_redline_stroke" not in src
    assert 'OUT_DIR.glob("*.png")' in src             # G7 asserts zero PNGs


def test_family_relation_is_grouping_only_pinned():
    src = inspect.getsource(probe)
    assert "GROUPING-ONLY" in src or "grouping-only" in src
    assert "no safe family/child law" in src.lower() or \
        "no_safe_family_law" in src


def test_no_engine_module_imports_the_probe():
    engine = (list((PKG / "match").glob("*.py"))
              + list((PKG / "review").glob("*.py")) + [PKG / "service.py"])
    for f in engine:
        assert "run_log17_family_abstain_probe" not in f.read_text(
            encoding="utf-8"), f
