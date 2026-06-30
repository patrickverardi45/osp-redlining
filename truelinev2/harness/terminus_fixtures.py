"""Seed terminus fixtures (G1) — name-free synthetic cold packages + their EXPECTED terminus evidence.

A terminus fixture is a directory:

    <root>/<fixture_id>/
        uploads/project_plan.pdf      # cold plan (no named-dialect trigger), optional printed structure notes
        uploads/bore_log.xlsx         # bore-log row -> source station values
        expected_termini.json         # expected start/end {source_bound, source_type, blocker}
        fixture.md                    # optional human-authored companion (see TERMINUS_FIXTURE_GUIDE.md)

The fixture format accepts PLAIN NOTES + screenshots (no Excel needed to AUTHOR a real case): the canonical
``expected_termini.json`` is hand-editable text, and a real bore-log input may be any accepted upload kind.

These name-free synthetic seeds exercise the realistic terminus EVIDENCE classes the AUTO gate will eventually
need to reason over — each is read-only observer evidence only and changes no placement/status:

  * both endpoints printed-bound, one bound + one missing, neither bound (the base source-bound vs missing
    distinction);
  * the SYMMETRIC one-bound case (start bound / end missing);
  * an AMBIGUOUS endpoint (two rival structure notes share the station — never coin-flipped);
  * a bare station CALLOUT with no structure keyword (not upgraded to a structure proof);
  * a nearby structure note that belongs to ANOTHER station (no proximity over-binding — the negative case);
  * a MULTI-SHEET bore whose end note sits on the second referenced sheet;
  * a bore-log carrying DEPTH + BOC metadata (carried only — must not change endpoint binding);
  * route geometry drawn but NO source-backed termini (a placeable run with no printed endpoint identity).
"""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from truelinev2.extract.terminus_evidence import (
    AMBIGUOUS_END_STRUCTURE,
    BORE_LOG_ROW,
    NO_PRINTED_END_STRUCTURE,
    NO_PRINTED_START_STRUCTURE,
    PRINTED_STRUCTURE_LABEL,
)
from truelinev2.harness.synth import (
    borelog_xlsx,
    plan_ambiguous_end_notes,
    plan_bare_station_callouts,
    plan_multi_sheet_end_note,
    plan_offset_end_note,
    plan_tight_red_run,
    plan_with_structure_notes,
)


@dataclass(frozen=True)
class TerminusFixture:
    fixture_id: str
    description: str
    plan_path: Path
    borelog_path: Path
    expected: dict          # {"start": {...}, "end": {...}}


# Reusable expected-endpoint shorthands (source_bound, source_type, blocker).
_BOUND = {"source_bound": True, "source_type": PRINTED_STRUCTURE_LABEL, "blocker": None}
_MISS_START = {"source_bound": False, "source_type": BORE_LOG_ROW, "blocker": NO_PRINTED_START_STRUCTURE}
_MISS_END = {"source_bound": False, "source_type": BORE_LOG_ROW, "blocker": NO_PRINTED_END_STRUCTURE}
_AMBIG_END = {"source_bound": False, "source_type": BORE_LOG_ROW, "blocker": AMBIGUOUS_END_STRUCTURE}

# (id, description, plan_builder, borelog_builder, expected-start, expected-end)
_SEED = (
    ("term-001-both-bound",
     "Cold plan with printed structure notes at BOTH bore endpoints.",
     lambda: plan_with_structure_notes(True, True), borelog_xlsx, _BOUND, _BOUND),
    ("term-002-end-bound-start-missing",
     "Cold plan with a printed END structure note but NO printed START note.",
     lambda: plan_with_structure_notes(False, True), borelog_xlsx, _MISS_START, _BOUND),
    ("term-003-none-bound",
     "Cold plan with NO printed structure notes; only the bore-log row gives the station values.",
     lambda: plan_with_structure_notes(False, False), borelog_xlsx, _MISS_START, _MISS_END),
    ("term-004-start-bound-end-missing",
     "Cold plan with a printed START structure note but NO printed END note (symmetric one-bound case).",
     lambda: plan_with_structure_notes(True, False), borelog_xlsx, _BOUND, _MISS_END),
    ("term-005-ambiguous-end",
     "Cold plan with a single START note but TWO rival structure notes at the END station (ambiguous).",
     plan_ambiguous_end_notes, borelog_xlsx, _BOUND, _AMBIG_END),
    ("term-006-bare-station-callout",
     "Cold plan with bare station callouts ('STA n') and NO structure keyword at either endpoint.",
     plan_bare_station_callouts, borelog_xlsx, _MISS_START, _MISS_END),
    ("term-007-offset-note-other-station",
     "Cold plan: a correct START note, but the END-area note belongs to a DIFFERENT station (negative).",
     plan_offset_end_note, borelog_xlsx, _BOUND, _MISS_END),
    ("term-008-multi-sheet-end-on-sheet-2",
     "Two-sheet bore: START note on sheet 1, END note on sheet 2 (bore-log references both sheets).",
     plan_multi_sheet_end_note, lambda: borelog_xlsx(print_val="1,2"), _BOUND, _BOUND),
    ("term-009-depth-boc-carried-metadata",
     "Both endpoints printed-bound; the bore-log also carries DEPTH + BOC (carried only, never used).",
     lambda: plan_with_structure_notes(True, True), lambda: borelog_xlsx(depth=7.5, boc=3.0), _BOUND, _BOUND),
    ("term-010-route-geometry-no-termini",
     "A drawn red bore run over the span but NO printed structure notes (route geometry, no source termini).",
     plan_tight_red_run, borelog_xlsx, _MISS_START, _MISS_END),
)


def build_terminus_fixtures(root) -> list:
    """(Re)generate the seed terminus fixtures under ``root`` (idempotent: wipes + rebuilds). Returns ids."""
    root = Path(root)
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
    written = []
    for fixture_id, desc, plan_builder, borelog_builder, exp_start, exp_end in _SEED:
        udir = root / fixture_id / "uploads"
        udir.mkdir(parents=True, exist_ok=True)
        (udir / "project_plan.pdf").write_bytes(plan_builder())
        (udir / "bore_log.xlsx").write_bytes(borelog_builder())
        spec = {"fixture_id": fixture_id, "description": desc,
                "uploads": [{"kind": "PLAN_PDF", "filename": "project_plan.pdf"},
                            {"kind": "BORE_LOG", "filename": "bore_log.xlsx"}],
                "expected": {"start": exp_start, "end": exp_end}}
        (root / fixture_id / "expected_termini.json").write_text(json.dumps(spec, indent=2), encoding="utf-8")
        written.append(fixture_id)
    return written


def load_terminus_fixtures(root) -> list:
    """Load every terminus fixture directory under ``root`` (sorted by id)."""
    root = Path(root)
    out = []
    if not root.is_dir():
        return out
    for child in sorted(p for p in root.iterdir() if p.is_dir()):
        spec_path = child / "expected_termini.json"
        if not spec_path.is_file():
            continue
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        out.append(TerminusFixture(
            fixture_id=spec["fixture_id"], description=spec.get("description", ""),
            plan_path=child / "uploads" / "project_plan.pdf",
            borelog_path=child / "uploads" / "bore_log.xlsx",
            expected=spec["expected"]))
    return out
