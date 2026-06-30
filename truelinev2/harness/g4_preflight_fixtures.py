"""G4 PREFLIGHT fixtures — the name-free synthetic proof-bed a future cold-package AUTO gate must pass BEFORE
any AUTO code lands (see truelinev2/docs/G4_TERMINUS_AUTO_DESIGN.md).

Each fixture pairs a both-/one-endpoint terminus situation with a SPECIFIC placement-geometry condition, so the
design's geometry + sheet + review gates can be exercised against real observed evidence. EVERYTHING here is
read-only and changes NO placement/status today: every fixture is REVIEW (or ABSTAIN) under the current engine.
The ``future_auto`` label records ONLY how the *proposed* (unbuilt) gate would classify the case — it is data,
not behavior.

Exactly ONE fixture is a future POSITIVE candidate (both endpoints printed-bound + near-perfect, rival-free
geometry on the placement sheet); the rest are NEGATIVE shapes the future gate must reject (ambiguous geometry,
low coverage, sheet mismatch, conflicting/ambiguous endpoint identity, a false-positive nearby note, and an
unreviewed bore-log row blocked by the existing engine-ready gate).
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
    PRINTED_STRUCTURE_LABEL,
)
from truelinev2.harness.synth import (
    borelog_xlsx,
    plan_ambiguous_end_notes,
    plan_ambiguous_runs_with_notes,
    plan_clean_bore_with_notes,
    plan_offset_end_note,
    plan_partial_run_with_notes,
    plan_run_sheet1_notes_sheet2,
)

# future_auto classifications (DATA ONLY — never affects today's placement/status).
POSITIVE_CANDIDATE = "POSITIVE_CANDIDATE"
NEGATIVE_AMBIGUOUS_GEOMETRY = "NEGATIVE_AMBIGUOUS_GEOMETRY"
NEGATIVE_LOW_CONFIDENCE_GEOMETRY = "NEGATIVE_LOW_CONFIDENCE_GEOMETRY"
NEGATIVE_SHEET_MISMATCH = "NEGATIVE_SHEET_MISMATCH"
NEGATIVE_CONFLICTING_ENDPOINT = "NEGATIVE_CONFLICTING_ENDPOINT"
NEGATIVE_FALSE_POSITIVE_ENDPOINT = "NEGATIVE_FALSE_POSITIVE_ENDPOINT"
NEGATIVE_UNREVIEWED_ROW = "NEGATIVE_UNREVIEWED_ROW"

_BOUND = {"source_bound": True, "source_type": PRINTED_STRUCTURE_LABEL, "blocker": None}
_AMBIG_END = {"source_bound": False, "source_type": BORE_LOG_ROW, "blocker": AMBIGUOUS_END_STRUCTURE}
_MISS_END = {"source_bound": False, "source_type": BORE_LOG_ROW, "blocker": NO_PRINTED_END_STRUCTURE}


@dataclass(frozen=True)
class G4PreflightFixture:
    fixture_id: str
    description: str
    plan_path: Path
    borelog_path: Path
    expected_start: dict        # file-level terminus evidence (source_bound / source_type / blocker)
    expected_end: dict
    expected_path: str          # cold decision path TODAY ("UPLOADED_REVIEW" | "ABSTAIN")
    future_auto: str            # the PROPOSED gate's classification (data only)
    reviewed: bool              # stand up the engine-ready reviewed bore-log? (False -> unreviewed -> ABSTAIN)


# (id, description, plan_builder, borelog_builder, exp_start, exp_end, expected_path, future_auto, reviewed)
_SEED = (
    ("g4-01-lone-positive-candidate",
     "Both endpoints printed-bound + a single tight rival-free bore run on the placement sheet.",
     plan_clean_bore_with_notes, borelog_xlsx, _BOUND, _BOUND,
     "UPLOADED_REVIEW", POSITIVE_CANDIDATE, True),
    ("g4-02-both-bound-uncertain-geometry",
     "Both endpoints printed-bound BUT several co-linear runs over the span (ambiguous geometry).",
     plan_ambiguous_runs_with_notes, borelog_xlsx, _BOUND, _BOUND,
     "UPLOADED_REVIEW", NEGATIVE_AMBIGUOUS_GEOMETRY, True),
    ("g4-03-both-bound-low-confidence-geometry",
     "Both endpoints printed-bound BUT the drawn run covers only part of the span (low confidence).",
     lambda: plan_partial_run_with_notes(80), borelog_xlsx, _BOUND, _BOUND,
     "UPLOADED_REVIEW", NEGATIVE_LOW_CONFIDENCE_GEOMETRY, True),
    ("g4-04-both-bound-sheet-mismatch",
     "Both endpoints printed-bound on sheet 2 but the run/placement is on sheet 1 (sheet mismatch).",
     plan_run_sheet1_notes_sheet2, lambda: borelog_xlsx(print_val="1,2"), _BOUND, _BOUND,
     "UPLOADED_REVIEW", NEGATIVE_SHEET_MISMATCH, True),
    ("g4-05-conflicting-end-identity",
     "Start printed-bound; the END has two rival structure notes at the same station (conflicting identity).",
     plan_ambiguous_end_notes, borelog_xlsx, _BOUND, _AMBIG_END,
     "UPLOADED_REVIEW", NEGATIVE_CONFLICTING_ENDPOINT, True),
    ("g4-06-false-positive-nearby-text",
     "Start printed-bound; an END-area note belongs to ANOTHER station, so the end stays unbound.",
     plan_offset_end_note, borelog_xlsx, _BOUND, _MISS_END,
     "UPLOADED_REVIEW", NEGATIVE_FALSE_POSITIVE_ENDPOINT, True),
    ("g4-07-unreviewed-bore-log-row",
     "Same clean both-bound plan, but the bore-log row is NOT reviewed -> blocked by the engine-ready gate.",
     plan_clean_bore_with_notes, borelog_xlsx, _BOUND, _BOUND,
     "ABSTAIN", NEGATIVE_UNREVIEWED_ROW, False),
)


def build_g4_preflight_fixtures(root) -> list:
    """(Re)generate the G4 preflight fixtures under ``root`` (idempotent: wipes + rebuilds). Returns ids."""
    root = Path(root)
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
    written = []
    for fid, desc, plan_builder, borelog_builder, exp_s, exp_e, path, fa, reviewed in _SEED:
        udir = root / fid / "uploads"
        udir.mkdir(parents=True, exist_ok=True)
        (udir / "project_plan.pdf").write_bytes(plan_builder())
        (udir / "bore_log.xlsx").write_bytes(borelog_builder())
        spec = {"fixture_id": fid, "description": desc,
                "uploads": [{"kind": "PLAN_PDF", "filename": "project_plan.pdf"},
                            {"kind": "BORE_LOG", "filename": "bore_log.xlsx"}],
                "expected": {"start": exp_s, "end": exp_e},
                "expected_path": path, "future_auto": fa, "reviewed": reviewed}
        (root / fid / "expected.json").write_text(json.dumps(spec, indent=2), encoding="utf-8")
        written.append(fid)
    return written


def load_g4_preflight_fixtures(root) -> list:
    """Load every G4 preflight fixture directory under ``root`` (sorted by id)."""
    root = Path(root)
    out = []
    if not root.is_dir():
        return out
    for child in sorted(p for p in root.iterdir() if p.is_dir()):
        spec_path = child / "expected.json"
        if not spec_path.is_file():
            continue
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        out.append(G4PreflightFixture(
            fixture_id=spec["fixture_id"], description=spec.get("description", ""),
            plan_path=child / "uploads" / "project_plan.pdf",
            borelog_path=child / "uploads" / "bore_log.xlsx",
            expected_start=spec["expected"]["start"], expected_end=spec["expected"]["end"],
            expected_path=spec["expected_path"], future_auto=spec["future_auto"],
            reviewed=spec["reviewed"]))
    return out
