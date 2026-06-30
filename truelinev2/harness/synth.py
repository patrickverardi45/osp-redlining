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


# Fixture catalog: (id, description, plan-bytes builder, expected_status, expected_blockers).
# expected_blockers is left empty for the first baseline (the matrix REPORTS the observed codes; they are
# tightened into expectations once observed — an honest abstain with the right code is the goal, not a guess).
_CATALOG = (
    ("pkg-001-tight-red-run",
     "Single tight red proposed bore over the bore-log span; axis + baseline + two utilities as rivals.",
     plan_tight_red_run, STATUS_REVIEW, ()),
    ("pkg-002-ambiguous-runs",
     "Several co-linear runs over the same span; no single line is clearly the bore.",
     plan_ambiguous_runs, STATUS_REVIEW, ()),
    ("pkg-003-axis-no-runs",
     "Axis ticks present but no proposed bore drawn anywhere over the span.",
     plan_axis_no_runs, STATUS_ABSTAIN, ("NO_PLAN_DIALECT_RECOGNIZED",)),
    ("pkg-004-blank-plan",
     "Notes-only sheet: no station axis and no drawn geometry.",
     plan_blank, STATUS_ABSTAIN, ("NO_PLAN_DIALECT_RECOGNIZED",)),
)


def build_synthetic_fixtures(fixtures_root) -> list:
    """(Re)generate the synthetic baseline fixture set under ``fixtures_root`` (idempotent: wipes + rebuilds).
    Returns the list of fixture ids written. Each fixture gets a PLAN_PDF + a BORE_LOG + one confirmed row."""
    root = Path(fixtures_root)
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
    written = []
    for fixture_id, desc, plan_builder, status, blockers in _CATALOG:
        fdir = root / fixture_id
        udir = fdir / "uploads"
        udir.mkdir(parents=True, exist_ok=True)
        (udir / "project_plan.pdf").write_bytes(plan_builder())
        (udir / "bore_log.xlsx").write_bytes(borelog_xlsx())
        spec = {
            "fixture_id": fixture_id,
            "description": desc,
            "uploads": [
                {"kind": "PLAN_PDF", "filename": "project_plan.pdf"},
                {"kind": "BORE_LOG", "filename": "bore_log.xlsx"},
            ],
            "bore_rows": [
                {"row_id": "row-1",
                 "raw": {"src": "bore_log.xlsx"},
                 "normalized": {"src": "bore_log.xlsx"}},
            ],
            "expected": {"status": status, "blockers": list(blockers)},
        }
        (fdir / "fixture.json").write_text(json.dumps(spec, indent=2), encoding="utf-8")
        written.append(fixture_id)
    return written
