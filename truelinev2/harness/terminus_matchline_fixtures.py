"""Printed MATCHLINE boundary-station terminus fixtures (MATCHLINE_BOUNDARY_STATION) — name-free, observer-only.

Each fixture exercises the read-only matchline binder (truelinev2/extract/matchline_anchor.py) through the
terminus extractor and changes NO placement/status. The matchline grammar ('MATCH... STA <n> - SEE SHEET <m>')
carries no 'STA a TO STA b' / 'DIR(ECTIONAL) BORE', so select_dialect stays None and these stay cold/generic.

Cases: a clean bilateral END crossing (binds), both endpoints on bilateral crossings (binds), a unilateral
crossing (one-sided -> refused), two rival crossings (ambiguous -> no coin-flip), a matchline that conflicts
with a span callout (conflict surfaced), a crossing to an unreferenced sheet (sheet mismatch -> refused), and
a nearby-but-inexact crossing (proximity -> refused).
"""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from truelinev2.extract.terminus_evidence import (
    AMBIGUOUS_END_STRUCTURE,
    BORE_LOG_ROW,
    CONFLICTING_END_TERMINUS,
    MATCHLINE_BOUNDARY_STATION,
    NO_PRINTED_END_STRUCTURE,
    PRINTED_STRUCTURE_LABEL,
)
from truelinev2.harness.synth import (
    borelog_xlsx,
    plan_matchline_ambiguous,
    plan_matchline_bilateral,
    plan_matchline_both_bound,
    plan_matchline_conflicts_callout,
    plan_matchline_sheet_mismatch,
    plan_matchline_unilateral,
    plan_matchline_unrelated,
)

_STRUCT = {"source_bound": True, "source_type": PRINTED_STRUCTURE_LABEL, "blocker": None}
_MATCHLINE = {"source_bound": True, "source_type": MATCHLINE_BOUNDARY_STATION, "blocker": None}
_MISS_END = {"source_bound": False, "source_type": BORE_LOG_ROW, "blocker": NO_PRINTED_END_STRUCTURE}
_AMBIG_END = {"source_bound": False, "source_type": BORE_LOG_ROW, "blocker": AMBIGUOUS_END_STRUCTURE}
_CONFLICT_END = {"source_bound": False, "source_type": BORE_LOG_ROW, "blocker": CONFLICTING_END_TERMINUS}


def _log(print_val):
    return lambda: borelog_xlsx(print_val=print_val)


@dataclass(frozen=True)
class MatchlineFixture:
    fixture_id: str
    description: str
    plan_path: Path
    borelog_path: Path
    expected: dict          # {"start": {...}, "end": {...}}


# (id, description, plan_builder, borelog_builder, expected-start, expected-end)
_SEED = (
    ("matchline-001-bilateral-end",
     "The END lands on a BILATERAL matchline crossing (both sheets print it); START via a structure note.",
     plan_matchline_bilateral, _log("1,2"), _STRUCT, _MATCHLINE),
    ("matchline-002-both-bound",
     "BOTH endpoints land on bilateral matchline crossings (start sheets 1-2, end sheets 2-3).",
     plan_matchline_both_bound, _log("1,2,3"), _MATCHLINE, _MATCHLINE),
    ("matchline-003-unilateral",
     "Only one sheet prints the crossing (unilateral) -> the END does not bind (CONFIRMED tier needs both).",
     plan_matchline_unilateral, _log("1,2"), _STRUCT, _MISS_END),
    ("matchline-004-ambiguous",
     "Two rival bilateral crossings claim the same END station -> ambiguous (never coin-flipped).",
     plan_matchline_ambiguous, _log("1,2,3"), _STRUCT, _AMBIG_END),
    ("matchline-005-conflicts-callout",
     "The END is matchline-bound but a span callout brackets the bore to a different end -> conflict.",
     plan_matchline_conflicts_callout, _log("1,2"), _STRUCT, _CONFLICT_END),
    ("matchline-006-sheet-mismatch",
     "The crossing references an UNREFERENCED sheet (3) -> no bilateral boundary on the bore's sheets.",
     plan_matchline_sheet_mismatch, _log("1,2"), _STRUCT, _MISS_END),
    ("matchline-007-unrelated",
     "A bilateral crossing at 13+20 (not the bore end 13+25) -> binds neither endpoint (exact only).",
     plan_matchline_unrelated, _log("1,2"), _STRUCT, _MISS_END),
)


def build_matchline_fixtures(root) -> list:
    """(Re)generate the matchline fixtures under ``root`` (idempotent: wipes + rebuilds). Returns ids."""
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


def load_matchline_fixtures(root) -> list:
    """Load every matchline fixture directory under ``root`` (sorted by id)."""
    root = Path(root)
    out = []
    if not root.is_dir():
        return out
    for child in sorted(p for p in root.iterdir() if p.is_dir()):
        spec_path = child / "expected_termini.json"
        if not spec_path.is_file():
            continue
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        out.append(MatchlineFixture(
            fixture_id=spec["fixture_id"], description=spec.get("description", ""),
            plan_path=child / "uploads" / "project_plan.pdf",
            borelog_path=child / "uploads" / "bore_log.xlsx",
            expected=spec["expected"]))
    return out
