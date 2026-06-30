"""Printed STATION-CALLOUT terminus fixtures (PRINTED_STA_CALLOUT) — name-free synthetic, observer-only.

Each fixture exercises the read-only callout binder (truelinev2/extract/callout_anchor.py) through the terminus
extractor and changes NO placement/status. The callout grammar is deliberately cold-lane safe (no 'STA a TO
STA b', no 'DIR(ECTIONAL) BORE'), so select_dialect stays None and these never become recognized-corpus
fixtures.

Cases: a clear span callout (both endpoints bind), a partial callout (one endpoint, other missing), two rival
callouts (ambiguous, never coin-flipped), a bare station (no span -> no bind), an unrelated callout (different
range -> no bind), and a callout that CONFLICTS with a printed structure label (surfaced as a conflict, never
silently preferred).
"""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from truelinev2.extract.terminus_evidence import (
    AMBIGUOUS_END_STRUCTURE,
    AMBIGUOUS_START_STRUCTURE,
    BORE_LOG_ROW,
    CONFLICTING_END_TERMINUS,
    NO_PRINTED_END_STRUCTURE,
    NO_PRINTED_START_STRUCTURE,
    PRINTED_STA_CALLOUT,
    PRINTED_STRUCTURE_LABEL,
)
from truelinev2.harness.synth import (
    borelog_xlsx,
    plan_bare_station_callouts,
    plan_callout_ambiguous,
    plan_callout_conflicts_structure,
    plan_callout_span_both,
    plan_callout_start_only,
    plan_callout_unrelated,
)

_CALLOUT = {"source_bound": True, "source_type": PRINTED_STA_CALLOUT, "blocker": None}
_STRUCT = {"source_bound": True, "source_type": PRINTED_STRUCTURE_LABEL, "blocker": None}
_MISS_START = {"source_bound": False, "source_type": BORE_LOG_ROW, "blocker": NO_PRINTED_START_STRUCTURE}
_MISS_END = {"source_bound": False, "source_type": BORE_LOG_ROW, "blocker": NO_PRINTED_END_STRUCTURE}
_AMBIG_START = {"source_bound": False, "source_type": BORE_LOG_ROW, "blocker": AMBIGUOUS_START_STRUCTURE}
_AMBIG_END = {"source_bound": False, "source_type": BORE_LOG_ROW, "blocker": AMBIGUOUS_END_STRUCTURE}
_CONFLICT_END = {"source_bound": False, "source_type": BORE_LOG_ROW, "blocker": CONFLICTING_END_TERMINUS}


@dataclass(frozen=True)
class CalloutFixture:
    fixture_id: str
    description: str
    plan_path: Path
    borelog_path: Path
    expected: dict          # {"start": {...}, "end": {...}}


# (id, description, plan_builder, borelog_builder, expected-start, expected-end)
_SEED = (
    ("callout-001-span-both-bound",
     "A printed station-range callout brackets the bore span exactly -> both endpoints bind.",
     plan_callout_span_both, borelog_xlsx, _CALLOUT, _CALLOUT),
    ("callout-002-start-only",
     "The callout brackets the START station only (its other end is not the bore end) -> partial bind.",
     plan_callout_start_only, borelog_xlsx, _CALLOUT, _MISS_END),
    ("callout-003-ambiguous",
     "Two rival span callouts both bracket the bore -> each endpoint is ambiguous (no coin-flip).",
     plan_callout_ambiguous, borelog_xlsx, _AMBIG_START, _AMBIG_END),
    ("callout-004-bare-station",
     "Bare station text ('STA n') carries no span/endpoint identity -> binds neither endpoint.",
     plan_bare_station_callouts, borelog_xlsx, _MISS_START, _MISS_END),
    ("callout-005-unrelated",
     "A span callout for a DIFFERENT range (neither station matches) -> binds neither endpoint.",
     plan_callout_unrelated, borelog_xlsx, _MISS_START, _MISS_END),
    ("callout-006-conflicts-structure",
     "A printed structure note binds the END while a callout brackets the bore to a different end -> conflict.",
     plan_callout_conflicts_structure, borelog_xlsx, _STRUCT, _CONFLICT_END),
)


def build_callout_fixtures(root) -> list:
    """(Re)generate the callout fixtures under ``root`` (idempotent: wipes + rebuilds). Returns ids."""
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


def load_callout_fixtures(root) -> list:
    """Load every callout fixture directory under ``root`` (sorted by id)."""
    root = Path(root)
    out = []
    if not root.is_dir():
        return out
    for child in sorted(p for p in root.iterdir() if p.is_dir()):
        spec_path = child / "expected_termini.json"
        if not spec_path.is_file():
            continue
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        out.append(CalloutFixture(
            fixture_id=spec["fixture_id"], description=spec.get("description", ""),
            plan_path=child / "uploads" / "project_plan.pdf",
            borelog_path=child / "uploads" / "bore_log.xlsx",
            expected=spec["expected"]))
    return out
