"""G4 GEOMETRY-vs-ENDPOINT validation fixtures — the read-only proof bed for the hardest AUTO risk.

Every fixture has BOTH endpoints source-bound (printed structure notes / a matchline crossing), so the
endpoint STATIONS are proven. They differ only in the GEOMETRY between the endpoints — the open question a
future AUTO gate must answer: is the selected drawn run actually the bore? Everything here is REVIEW/ABSTAIN
under the current engine (no AUTO, no placement change); ``ground_truth`` + ``oracle_would_pass`` are DATA used
only by the validation test to expose where the current signals are sufficient and where they are NOT.

The decisive case is the WRONG-BRANCH fork: its endpoints are correct and the current generic-lane signals
look exactly like the clean positive (MEDIUM, no rival/partial/extent warning), yet the selected path could
follow the wrong branch. The current data cannot separate it from the true positive — so the future gate is
NOT safely implementable from current data (a real package + a branch-uniqueness signal are still required).
"""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from truelinev2.extract.terminus_evidence import MATCHLINE_BOUNDARY_STATION, PRINTED_STRUCTURE_LABEL
from truelinev2.harness.synth import (
    borelog_xlsx,
    plan_baseline_trap_with_notes,
    plan_broken_fragments_with_notes,
    plan_clean_bore_with_notes,
    plan_forked_run_with_notes,
    plan_matchline_bilateral,
    plan_overshoot_run_with_notes,
    plan_parallel_rivals_with_notes,
    plan_undershoot_run_with_notes,
)

_STRUCT = {"source_bound": True, "source_type": PRINTED_STRUCTURE_LABEL, "blocker": None}
_MATCHLINE = {"source_bound": True, "source_type": MATCHLINE_BOUNDARY_STATION, "blocker": None}

POSITIVE = "POSITIVE"        # a true future AUTO candidate (the selected run really is the bore)
NEGATIVE = "NEGATIVE"        # the selected run is NOT proven to be the bore -> must never AUTO


def _log(print_val):
    return lambda: borelog_xlsx(print_val=print_val)


@dataclass(frozen=True)
class G4GeometryFixture:
    fixture_id: str
    description: str
    plan_path: Path
    borelog_path: Path
    expected_start: dict          # terminus evidence (both endpoints are source-bound by design)
    expected_end: dict
    expected_path: str            # cold decision path TODAY
    ground_truth: str             # POSITIVE | NEGATIVE  (what a SAFE gate SHOULD do)
    oracle_would_pass: bool       # what the CURRENT-DATA oracle does (True even for the fork -> the gap)
    note: str                     # why it is rejected / why current data can or cannot tell


# (id, description, plan_builder, borelog_builder, exp_start, exp_end, path, ground_truth, oracle_would_pass, note)
_SEED = (
    ("g4geo-01-perfect-line",
     "Both endpoints source-bound + a single clean rival-free run between them.",
     plan_clean_bore_with_notes, _log("1"), _STRUCT, _STRUCT, "UPLOADED_REVIEW",
     POSITIVE, True, "clean: passes every available signal (the true positive)"),
    ("g4geo-02-parallel-rival",
     "Both endpoints source-bound, but two parallel runs span the same stations.",
     plan_parallel_rivals_with_notes, _log("1"), _STRUCT, _STRUCT, "UPLOADED_REVIEW",
     NEGATIVE, False, "rejected by MULTIPLE_PLAUSIBLE_RUNS / COMPETING_RUNS_NEAR_SCORE"),
    ("g4geo-03-broken-fragments",
     "Both endpoints source-bound, but only short specks span the range (no weldable run).",
     plan_broken_fragments_with_notes, _log("1"), _STRUCT, _STRUCT, "ABSTAIN",
     NEGATIVE, False, "rejected: the engine ABSTAINS (NO_WELDABLE_RUN)"),
    ("g4geo-04-line-overshoots",
     "Both endpoints source-bound, but the selected run extends materially beyond the termini.",
     plan_overshoot_run_with_notes, _log("1"), _STRUCT, _STRUCT, "UPLOADED_REVIEW",
     NEGATIVE, False, "rejected by DRAWN_EXTENT_EXCEEDS_BORE_SPAN / RUN_LENGTH_UNLIKE_BORE_SPAN"),
    ("g4geo-05-line-undershoots",
     "Both endpoints source-bound, but the run reaches neither terminus (partial coverage).",
     plan_undershoot_run_with_notes, _log("1"), _STRUCT, _STRUCT, "UPLOADED_REVIEW",
     NEGATIVE, False, "rejected by LOW band + PARTIAL_SPAN_COVERAGE + correction-recommended"),
    ("g4geo-06-wrong-branch-fork",
     "Both endpoints source-bound, but the run forks and the path can follow the wrong branch.",
     plan_forked_run_with_notes, _log("1"), _STRUCT, _STRUCT, "UPLOADED_REVIEW",
     NEGATIVE, True, "FALSE POSITIVE: current signals look identical to the clean positive — no "
                     "branch-uniqueness signal exists, so the gate cannot reject it from current data"),
    ("g4geo-07-baseline-trap",
     "Both endpoints source-bound, but only a full-sheet baseline spans the stations.",
     plan_baseline_trap_with_notes, _log("1"), _STRUCT, _STRUCT, "ABSTAIN",
     NEGATIVE, False, "rejected: the over-placement guard ABSTAINS (NO_DRAWN_RUN_OVER_SPAN)"),
    ("g4geo-08-multisheet-cross-sheet-partial",
     "Source-bound matchline END + run on one sheet only -> cross-sheet continuation unvalidated.",
     plan_matchline_bilateral, _log("1,2"), _STRUCT, _MATCHLINE, "UPLOADED_REVIEW",
     NEGATIVE, False, "rejected by CROSS_SHEET_CONTINUATION_REVIEW / PARTIAL_CROSS_SHEET_REVIEW (a fully "
                      "clean multi-sheet positive needs rendered legs on every referenced sheet)"),
)


def build_g4_geometry_fixtures(root) -> list:
    """(Re)generate the G4 geometry fixtures under ``root`` (idempotent: wipes + rebuilds). Returns ids."""
    root = Path(root)
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
    written = []
    for (fid, desc, plan_b, log_b, exp_s, exp_e, path, gt, op, note) in _SEED:
        udir = root / fid / "uploads"
        udir.mkdir(parents=True, exist_ok=True)
        (udir / "project_plan.pdf").write_bytes(plan_b())
        (udir / "bore_log.xlsx").write_bytes(log_b())
        spec = {"fixture_id": fid, "description": desc,
                "uploads": [{"kind": "PLAN_PDF", "filename": "project_plan.pdf"},
                            {"kind": "BORE_LOG", "filename": "bore_log.xlsx"}],
                "expected": {"start": exp_s, "end": exp_e}, "expected_path": path,
                "ground_truth": gt, "oracle_would_pass": op, "note": note}
        (root / fid / "expected.json").write_text(json.dumps(spec, indent=2), encoding="utf-8")
        written.append(fid)
    return written


def load_g4_geometry_fixtures(root) -> list:
    """Load every G4 geometry fixture directory under ``root`` (sorted by id)."""
    root = Path(root)
    out = []
    if not root.is_dir():
        return out
    for child in sorted(p for p in root.iterdir() if p.is_dir()):
        spec_path = child / "expected.json"
        if not spec_path.is_file():
            continue
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        out.append(G4GeometryFixture(
            fixture_id=spec["fixture_id"], description=spec.get("description", ""),
            plan_path=child / "uploads" / "project_plan.pdf",
            borelog_path=child / "uploads" / "bore_log.xlsx",
            expected_start=spec["expected"]["start"], expected_end=spec["expected"]["end"],
            expected_path=spec["expected_path"], ground_truth=spec["ground_truth"],
            oracle_would_pass=spec["oracle_would_pass"], note=spec["note"]))
    return out
