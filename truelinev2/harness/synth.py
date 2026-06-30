"""Synthetic, name-free cold-package fixture generators.

Builds self-contained PDF + xlsx inputs (the same fitz/openpyxl pattern the product proof seed uses) that
exercise distinct engine decisions WITHOUT any real customer/project/location content. These plans carry NO
named-dialect text ('STA <a> TO STA <b>' / 'DIR(ECTIONAL) BORE') so select_dialect returns None and the
engine routes through the name-free generic-geometry lane (or abstains) — exactly the cold-package path.

Coordinate scheme (shared): station ticks at x=120..720 map to stations 1000..1600 (station_at(x) ~= x+880),
so the bore-log span 11+75..13+25 sits at x 295..445. A tight red run over that x-range is the bore; a
full-sheet line is a survey baseline the bore-aware selector must NOT mistake for the bore.

These generators write fixture directories under a gitignored fixtures root; they are pure data builders and
run no engine.
"""
from __future__ import annotations

import io
import json
import shutil
from pathlib import Path

import fitz
import openpyxl

from truelinev2.harness.fixtures import STATUS_ABSTAIN, STATUS_REVIEW

# Shared bore-log span (feet) used by the fixtures whose plan geometry is calibrated to it.
_BORE_START = "11+75"
_BORE_END = "13+25"


def _new_plan():
    doc = fitz.open()
    page = doc.new_page(width=792, height=612)            # landscape, plan-like
    return doc, page


def _draw_axis(page) -> None:
    """Station ticks + labels (x=120..720 -> 10+00..16+00). No named-dialect text."""
    for ft in range(1000, 1601, 100):
        x = 120 + (ft - 1000) / 100 * 100
        page.draw_line((x, 400), (x, 412), color=(0, 0, 0), width=0.8)
        page.insert_text((x - 12, 426), "%d+%02d" % (ft // 100, ft % 100), fontsize=8)


def _save(doc) -> bytes:
    out = io.BytesIO()
    doc.save(out)
    doc.close()
    return out.getvalue()


def plan_tight_red_run() -> bytes:
    """Axis + survey baseline + two existing utilities + a single PROPOSED bore drawn red, tightly spanning
    the bore-log range. The bore-aware generic selector should pick the red run and clip to the span ->
    REVIEW (capped; generic never AUTO)."""
    doc, page = _new_plan()
    page.insert_text((60, 60), "PLAN & PROFILE  -  ALIGNMENT 10+00 thru 16+00", fontsize=11)
    for gx in range(120, 721, 50):
        page.draw_line((gx, 300), (gx, 360), color=(0.8, 0.8, 0.8), width=0.4)
    _draw_axis(page)
    page.draw_line((120, 400), (720, 400), color=(0, 0, 0), width=0.7)            # full-sheet baseline
    page.draw_line((120, 372), (720, 372), color=(0.2, 0.5, 0.9), width=0.8)      # blue utility
    page.draw_line((120, 388), (720, 388), color=(0.1, 0.6, 0.2), width=0.8)      # green utility
    page.draw_line((295, 384), (445, 384), color=(1, 0, 0), width=1.8)            # the PROPOSED bore (red)
    return _save(doc)


def plan_ambiguous_runs() -> bytes:
    """Several co-linear runs over the SAME span (no single line is clearly the bore). The honest generic
    lane should still place a candidate but flag LOW / correction-recommended -> REVIEW path (never a
    confident AUTO)."""
    doc, page = _new_plan()
    page.insert_text((60, 60), "PLAN & PROFILE  -  ALIGNMENT 10+00 thru 16+00 (ambiguous)", fontsize=11)
    _draw_axis(page)
    page.draw_line((120, 400), (720, 400), color=(0, 0, 0), width=0.7)            # full-sheet baseline
    page.draw_line((295, 378), (445, 378), color=(0, 0, 0), width=1.4)            # rival A
    page.draw_line((295, 392), (445, 392), color=(1, 0, 0), width=1.6)            # rival B (red)
    page.draw_line((310, 406), (445, 406), color=(0, 0, 0), width=1.4)            # rival C
    return _save(doc)


def plan_axis_no_runs() -> bytes:
    """Axis ticks present but NO drawn run anywhere over the span (no bore line). The generic lane finds no
    drawable bore run -> ABSTAIN (honest 'nothing to place')."""
    doc, page = _new_plan()
    page.insert_text((60, 60), "PLAN & PROFILE  -  ALIGNMENT 10+00 thru 16+00 (no proposed work)", fontsize=11)
    for gx in range(120, 721, 50):
        page.draw_line((gx, 300), (gx, 360), color=(0.8, 0.8, 0.8), width=0.4)
    _draw_axis(page)
    return _save(doc)


def plan_blank() -> bytes:
    """A page with text only — no station ticks, no drawn geometry. No dialect, no axis -> ABSTAIN."""
    doc, page = _new_plan()
    page.insert_text((60, 60), "GENERAL NOTES SHEET", fontsize=12)
    page.insert_text((60, 90), "1. ALL WORK PER APPLICABLE STANDARDS.", fontsize=9)
    page.insert_text((60, 110), "2. CONTRACTOR TO VERIFY EXISTING CONDITIONS.", fontsize=9)
    return _save(doc)


def plan_partial_run(width_pt) -> bytes:
    """Axis + baseline + a red run covering only PART of the 150-pt bore span (x 295..295+width_pt). Below the
    ~50% coverage gate the generic lane should not place (ABSTAIN); 50-85% places only as a partial / low
    REVIEW."""
    doc, page = _new_plan()
    page.insert_text((60, 60), "PLAN & PROFILE  -  ALIGNMENT 10+00 thru 16+00 (partial run)", fontsize=11)
    _draw_axis(page)
    page.draw_line((120, 400), (720, 400), color=(0, 0, 0), width=0.7)
    page.draw_line((295, 384), (295 + width_pt, 384), color=(1, 0, 0), width=1.8)
    return _save(doc)


def plan_weak_axis() -> bytes:
    """Only TWO station ticks (below the 3-tick minimum to trust the axis) over a red run. The axis cannot be
    trusted -> ABSTAIN."""
    doc, page = _new_plan()
    page.insert_text((60, 60), "PLAN & PROFILE  -  (sparse stationing)", fontsize=11)
    for ft in (1000, 1600):
        x = 120 + (ft - 1000) / 100 * 100
        page.draw_line((x, 400), (x, 412), color=(0, 0, 0), width=0.8)
        page.insert_text((x - 12, 426), "%d+%02d" % (ft // 100, ft % 100), fontsize=8)
    page.draw_line((295, 384), (445, 384), color=(1, 0, 0), width=1.8)
    return _save(doc)


def plan_baseline_only() -> bytes:
    """Full axis but ONLY a full-sheet survey baseline (no tight proposed bore drawn). The honest answer is
    ABSTAIN: there is no bore to place, and the full-sheet baseline must NOT be mistaken for the bore. This is
    the over-placement probe (a placement on the baseline would be a FAIL)."""
    doc, page = _new_plan()
    page.insert_text((60, 60), "PLAN & PROFILE  -  (existing survey only)", fontsize=11)
    _draw_axis(page)
    page.draw_line((120, 400), (720, 400), color=(0, 0, 0), width=0.7)            # full-sheet baseline only
    return _save(doc)


def plan_speckle_no_run() -> bytes:
    """Axis + only short, widely-spaced red specks over the span (each below the minimum run length, gaps too
    wide to weld). No weldable run -> ABSTAIN."""
    doc, page = _new_plan()
    page.insert_text((60, 60), "PLAN & PROFILE  -  (no continuous proposed run)", fontsize=11)
    _draw_axis(page)
    for x in range(300, 441, 40):
        page.draw_line((x, 384), (x + 8, 384), color=(1, 0, 0), width=1.8)
    return _save(doc)


def plan_multi_sheet() -> bytes:
    """A TWO-page plan: each page carries the station axis + a red run over the span. The generic lane places a
    single clipped stroke on one sheet (it does not assemble cross-sheet legs yet) -> REVIEW. Probes multi-page
    handling."""
    doc = fitz.open()
    for label in ("SHEET 1", "SHEET 2"):
        page = doc.new_page(width=792, height=612)
        page.insert_text((60, 60), "PLAN & PROFILE  -  ALIGNMENT 10+00 thru 16+00 (%s)" % label, fontsize=11)
        _draw_axis(page)
        page.draw_line((120, 400), (720, 400), color=(0, 0, 0), width=0.7)
        page.draw_line((295, 384), (445, 384), color=(1, 0, 0), width=1.8)
    return _save(doc)


def borelog_xlsx(start=_BORE_START, end=_BORE_END) -> bytes:
    """A flat bore-log: a single bore span on plan sheet 1 (station/depth/print)."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["station", "depth", "print", "notes"])
    ws.append([start, 5.0, "1", "bore start"])
    ws.append([end, 5.0, "1", "bore end"])
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


# Fixture catalog: (id, description, plan-bytes builder, expected_status, expected_blockers, n_reviewed_rows).
# expected_blockers is set only where it is already OBSERVED and stable (an honest abstain with the right named
# code is the goal); where left empty the matrix simply REPORTS the observed codes for later tightening.
# n_reviewed_rows = 0 means the bore-log review gate is intentionally left unsatisfied (no engine-ready RBL).
_CATALOG = (
    # --- placeable: the generic lane reconstructs a run and holds it for review (never auto) -------------- #
    ("pkg-001-tight-red-run",
     "Single tight red proposed bore over the bore-log span; axis + baseline + two utilities as rivals.",
     plan_tight_red_run, STATUS_REVIEW, (), 1),
    ("pkg-002-ambiguous-runs",
     "Several co-linear runs over the same span; no single line is clearly the bore.",
     plan_ambiguous_runs, STATUS_REVIEW, (), 1),
    ("pkg-007-partial-mid",
     "Red run covers ~70% of the bore span (partial coverage, above the placement floor).",
     lambda: plan_partial_run(105), STATUS_REVIEW, (), 1),
    ("pkg-009-multi-sheet",
     "Two-page plan; station axis + a red run over the span on each page.",
     plan_multi_sheet, STATUS_REVIEW, (), 1),
    # --- honest abstains: no placeable evidence -> ABSTAIN with a named reason --------------------------- #
    ("pkg-003-axis-no-runs",
     "Axis ticks present but no proposed bore drawn anywhere over the span.",
     plan_axis_no_runs, STATUS_ABSTAIN, ("NO_PLAN_DIALECT_RECOGNIZED",), 1),
    ("pkg-004-blank-plan",
     "Notes-only sheet: no station axis and no drawn geometry.",
     plan_blank, STATUS_ABSTAIN, ("NO_PLAN_DIALECT_RECOGNIZED",), 1),
    ("pkg-005-weak-axis-2-ticks",
     "Only two station ticks (below the 3-tick minimum to trust the axis) over a red run.",
     plan_weak_axis, STATUS_ABSTAIN, (), 1),
    ("pkg-006-partial-below-min",
     "Red run covers <50% of the bore span (below the placement floor).",
     lambda: plan_partial_run(60), STATUS_ABSTAIN, (), 1),
    ("pkg-008-over-placement-baseline",
     "Full axis but only a full-sheet survey baseline; no proposed bore drawn (over-placement probe).",
     plan_baseline_only, STATUS_ABSTAIN, (), 1),
    ("pkg-010-speckle-no-run",
     "Axis + short widely-spaced specks over the span; no weldable continuous run.",
     plan_speckle_no_run, STATUS_ABSTAIN, (), 1),
    # --- gate-state abstain: geometry is fine but the human review gate is not satisfied ----------------- #
    ("pkg-011-no-engine-ready-borelog",
     "A good red run, but the bore-log review gate is not satisfied (no reviewed rows).",
     plan_tight_red_run, STATUS_ABSTAIN, ("NO_ENGINE_READY_REVIEWED_BORE_LOG",), 0),
)


def build_synthetic_fixtures(fixtures_root) -> list:
    """(Re)generate the synthetic fixture set under ``fixtures_root`` (idempotent: wipes + rebuilds). Returns
    the list of fixture ids written. Each fixture gets a PLAN_PDF + a BORE_LOG; ``n_reviewed_rows`` confirmed
    rows are declared (0 leaves the review gate intentionally unsatisfied)."""
    root = Path(fixtures_root)
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
    written = []
    for fixture_id, desc, plan_builder, status, blockers, n_rows in _CATALOG:
        fdir = root / fixture_id
        udir = fdir / "uploads"
        udir.mkdir(parents=True, exist_ok=True)
        (udir / "project_plan.pdf").write_bytes(plan_builder())
        (udir / "bore_log.xlsx").write_bytes(borelog_xlsx())
        bore_rows = [{"row_id": "row-%d" % (i + 1),
                      "raw": {"src": "bore_log.xlsx"},
                      "normalized": {"src": "bore_log.xlsx"}}
                     for i in range(n_rows)]
        spec = {
            "fixture_id": fixture_id,
            "description": desc,
            "uploads": [
                {"kind": "PLAN_PDF", "filename": "project_plan.pdf"},
                {"kind": "BORE_LOG", "filename": "bore_log.xlsx"},
            ],
            "bore_rows": bore_rows,
            "expected": {"status": status, "blockers": list(blockers)},
        }
        (fdir / "fixture.json").write_text(json.dumps(spec, indent=2), encoding="utf-8")
        written.append(fixture_id)
    return written

