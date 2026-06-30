"""Seed terminus fixtures (G1) — name-free synthetic cold packages + their EXPECTED terminus evidence.

A terminus fixture is a directory:

    <root>/<fixture_id>/
        uploads/project_plan.pdf      # cold plan (no named-dialect trigger), optional printed structure notes
        uploads/bore_log.xlsx         # bore-log row -> source station values
        expected_termini.json         # expected start/end {source_bound, source_type, blocker}
        fixture.md                    # optional human-authored companion (see TERMINUS_FIXTURE_GUIDE.md)

The fixture format accepts PLAIN NOTES + screenshots (no Excel needed to AUTHOR a real case): the canonical
``expected_termini.json`` is hand-editable text, and a real bore-log input may be any accepted upload kind.
These three synthetic seeds exercise: both endpoints printed-bound, one bound + one missing, and neither
bound (bore-log value only) — proving the source-bound vs missing/blocker distinction.
"""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from truelinev2.extract.terminus_evidence import (
    BORE_LOG_ROW,
    NO_PRINTED_END_STRUCTURE,
    NO_PRINTED_START_STRUCTURE,
    PRINTED_STRUCTURE_LABEL,
)
from truelinev2.harness.synth import borelog_xlsx, plan_with_structure_notes


@dataclass(frozen=True)
class TerminusFixture:
    fixture_id: str
    description: str
    plan_path: Path
    borelog_path: Path
    expected: dict          # {"start": {...}, "end": {...}}


# (id, description, start_note?, end_note?, expected-start, expected-end)
_SEED = (
    ("term-001-both-bound",
     "Cold plan with printed structure notes at BOTH bore endpoints.",
     True, True,
     {"source_bound": True, "source_type": PRINTED_STRUCTURE_LABEL, "blocker": None},
     {"source_bound": True, "source_type": PRINTED_STRUCTURE_LABEL, "blocker": None}),
    ("term-002-end-bound-start-missing",
     "Cold plan with a printed END structure note but NO printed START note.",
     False, True,
     {"source_bound": False, "source_type": BORE_LOG_ROW, "blocker": NO_PRINTED_START_STRUCTURE},
     {"source_bound": True, "source_type": PRINTED_STRUCTURE_LABEL, "blocker": None}),
    ("term-003-none-bound",
     "Cold plan with NO printed structure notes; only the bore-log row gives the station values.",
     False, False,
     {"source_bound": False, "source_type": BORE_LOG_ROW, "blocker": NO_PRINTED_START_STRUCTURE},
     {"source_bound": False, "source_type": BORE_LOG_ROW, "blocker": NO_PRINTED_END_STRUCTURE}),
)


def build_terminus_fixtures(root) -> list:
    """(Re)generate the seed terminus fixtures under ``root`` (idempotent: wipes + rebuilds). Returns ids."""
    root = Path(root)
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
    written = []
    for fixture_id, desc, start_note, end_note, exp_start, exp_end in _SEED:
        udir = root / fixture_id / "uploads"
        udir.mkdir(parents=True, exist_ok=True)
        (udir / "project_plan.pdf").write_bytes(plan_with_structure_notes(start_note, end_note))
        (udir / "bore_log.xlsx").write_bytes(borelog_xlsx())
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
