"""Read-only COLD-PACKAGE eligibility + validation INTAKE path (the bridge from synthetic proof to a real
package). Name-free.

The Track B observer stack (terminus evidence, branch-uniqueness, station-x tightness, 2-D endpoint tightness,
leader-traced provenance) is proven only against synthetic/adversarial harnesses. The missing blocker is REAL /
FRESH cold-package validation. This module determines whether a candidate package is eligible to serve as cold
proof, runs the read-only observer stack if it is (or if it is synthetic — exercised but NEVER counted as real
validation), and refuses honestly otherwise — producing a read-only report. It performs NO placement, NO
promotion, NO store/job work; it opens files read-only and runs the geometry observers.

What a REAL eligible package must include (the intake contract):
  * a ``package.json`` manifest with ``provenance_class`` (advisory only — overridden by source evidence),
    ``uploads`` (>=1 ``PLAN_PDF`` + >=1 ``BORE_LOG``; ``GIS_ROUTE`` optional), and ``bores`` (each
    ``{bore_label, sheet, start_ft, end_ft}``), plus the upload bytes under ``uploads/``;
  * the plan must be GENUINELY non-recognized — ``select_dialect(plan) is None`` AND not in the recognized
    registry (a recognized plan is the work corpus, ineligible as cold proof, no matter what the manifest says);
  * printed terminus evidence on the plan (so the binders can source-bind endpoints).

ELIGIBILITY PRECEDENCE (source evidence overrides the declared class):
  not-found/unreadable -> incomplete -> RECOGNIZED (select_dialect or registry) -> declared ACTIVE_FIELD
  -> SYNTHETIC (declared or under a synthetic root) -> declared work -> declared fresh+complete+non-recognized
  -> unknown class. SYNTHETIC packages may exercise the report path but ``real_validation`` is False — they are
  NEVER counted as real-world generalization.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from truelinev2.extract.registry import select_dialect
from truelinev2.extract.run_geometry_observer import (
    BRANCH_FORKED,
    BRANCH_NO_SPANNING_RUN,
    BRANCH_RIVAL_RUNS,
)
from truelinev2.extract.terminus_coordinate_observer import (
    AMBIGUOUS_DRAWN_COORDINATE,
    DRAWN_COORDINATE_BOUND,
    NO_DRAWN_COORDINATE,
)
from truelinev2.extract.terminus_extractor import extract_termini
from truelinev2.extract.terminus_coordinate_observer import observe_package_terminus_geometry
from truelinev2.harness.fixtures import UPLOAD_KINDS
from truelinev2.ingest.pdf import PlanPdf

# --- declared provenance classes (manifest, ADVISORY — source evidence overrides) ---------------------- #
PROV_FRESH = "FRESH_NONRECOGNIZED"
PROV_WORK = "RECOGNIZED_WORK"
PROV_ACTIVE_FIELD = "ACTIVE_FIELD"      # a reserved active-field user's corpus (name-free); ineligible as proof
PROV_SYNTHETIC = "SYNTHETIC"
_DECLARED_CLASSES = (PROV_FRESH, PROV_WORK, PROV_ACTIVE_FIELD, PROV_SYNTHETIC)

# --- eligibility verdicts ------------------------------------------------------------------------------- #
ELIGIBLE_FRESH_NONRECOGNIZED = "ELIGIBLE_FRESH_NONRECOGNIZED"
SYNTHETIC_TEST_ONLY = "SYNTHETIC_TEST_ONLY"
INELIGIBLE_RECOGNIZED_WORK_CORPUS = "INELIGIBLE_RECOGNIZED_WORK_CORPUS"
INELIGIBLE_ACTIVE_FIELD_CORPUS = "INELIGIBLE_ACTIVE_FIELD_CORPUS"
INCOMPLETE_UPLOAD = "INCOMPLETE_UPLOAD"
UNKNOWN_PROVENANCE_CLASS = "UNKNOWN_PROVENANCE_CLASS"
PACKAGE_NOT_FOUND = "PACKAGE_NOT_FOUND"
PACKAGE_UNREADABLE = "PACKAGE_UNREADABLE"

# --- aggregated AUTO blockers (all non-promoting) ------------------------------------------------------- #
CLASS_VERIFICATION_MISSING = "CLASS_VERIFICATION_MISSING"
REAL_FRESH_PACKAGE_VALIDATION_PENDING = "REAL_FRESH_PACKAGE_VALIDATION_PENDING"
INSUFFICIENT_TERMINUS_EVIDENCE = "INSUFFICIENT_TERMINUS_EVIDENCE"
NO_DRAWN_COORDINATE_EVIDENCE = "NO_DRAWN_COORDINATE_EVIDENCE"
AMBIGUOUS_EVIDENCE = "AMBIGUOUS_EVIDENCE"
CROSS_SHEET_UNRESOLVED = "CROSS_SHEET_UNRESOLVED"

_REQUIRED_KINDS = ("PLAN_PDF", "BORE_LOG")
_OBSERVER_RAN = (ELIGIBLE_FRESH_NONRECOGNIZED, SYNTHETIC_TEST_ONLY)


@dataclass(frozen=True)
class CandidateObservation:
    """Read-only observer diagnostics for one bore. ``None`` fields mean the stack could not run (e.g. no
    trustworthy station axis). Carries no placement and confers no status."""
    bore_label: str
    sheet: int
    start_ft: float
    end_ft: float
    start_source_bound: bool
    end_source_bound: bool
    start_source_type: Optional[str]
    end_source_type: Optional[str]
    start_blocker: Optional[str]
    end_blocker: Optional[str]
    branch_uniqueness: Optional[str]
    endpoint_to_run_x_tightness: Optional[str]
    start_2d: Optional[str]
    end_2d: Optional[str]
    start_provenance: Optional[str]      # LEADER_TRACED_SYMBOL / COMPACT_SYMBOL_AT_STATION / a refusal result
    end_provenance: Optional[str]
    class_verified: bool
    would_reject: Optional[bool]
    two_d_verified: Optional[bool]
    detail: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PackageValidationReport:
    """Read-only verdict + observer evidence for a candidate package. ``placement_performed`` is ALWAYS False;
    ``real_validation`` is True ONLY for an eligible fresh non-recognized package (never for synthetic)."""
    package_id: str
    eligibility: str
    eligibility_reason: str
    corpus_class: str                    # FRESH_NONRECOGNIZED / RECOGNIZED_WORK / ACTIVE_FIELD / SYNTHETIC / UNKNOWN
    recognized: bool                     # a named dialect or the registry recognizes the plan
    real_validation: bool                # eligible fresh non-recognized only -> never synthetic
    source_files_present: Tuple[str, ...]
    source_files_missing: Tuple[str, ...]
    candidates: Tuple[CandidateObservation, ...]
    auto_blockers: Tuple[str, ...]
    placement_performed: bool            # always False
    note: str                            # the explicit "no placement/promotion performed" statement
    notes: Tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "package_id": self.package_id,
            "eligibility": self.eligibility,
            "eligibility_reason": self.eligibility_reason,
            "corpus_class": self.corpus_class,
            "recognized": self.recognized,
            "real_validation": self.real_validation,
            "source_files_present": list(self.source_files_present),
            "source_files_missing": list(self.source_files_missing),
            "candidates": [c.__dict__ for c in self.candidates],
            "auto_blockers": list(self.auto_blockers),
            "placement_performed": self.placement_performed,
            "note": self.note,
            "notes": list(self.notes),
        }


_NO_PLACEMENT_NOTE = "no placement/promotion performed — read-only eligibility + observer evidence only"
_NOTES = (
    "provenance_class in the manifest is ADVISORY; source evidence overrides it (a recognized plan is the work "
    "corpus regardless of the declared class)",
    "SYNTHETIC packages exercise the observer report path but real_validation is False — never counted as "
    "real-world generalization",
    "class verification is still missing (no generic CAD layer/class table) so class_verified is always False; "
    "G4 AUTO stays blocked",
)


def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _under_any(path: Path, roots: Sequence) -> bool:
    rp = path.resolve()
    for r in roots:
        try:
            rp.relative_to(Path(r).resolve())
            return True
        except ValueError:
            continue
    return False


def _report(package_id, eligibility, reason, corpus_class, recognized, real_validation,
            present, missing, candidates, auto_blockers, notes=()):
    return PackageValidationReport(
        package_id=package_id, eligibility=eligibility, eligibility_reason=reason,
        corpus_class=corpus_class, recognized=recognized, real_validation=real_validation,
        source_files_present=tuple(present), source_files_missing=tuple(missing),
        candidates=tuple(candidates), auto_blockers=tuple(sorted(set(auto_blockers))),
        placement_performed=False, note=_NO_PLACEMENT_NOTE, notes=tuple(notes) + _NOTES)


def _provenance_summary(coord) -> str:
    """A single provenance string per endpoint: the ladder rung when bound, else the refusal result."""
    if coord.result == DRAWN_COORDINATE_BOUND and coord.provenance:
        return coord.provenance                      # LEADER_TRACED_SYMBOL / COMPACT_SYMBOL_AT_STATION
    return coord.result                              # NO_DRAWN_COORDINATE / AMBIGUOUS_DRAWN_COORDINATE / NOT_SOURCE_BOUND


def _candidate(bore: dict, ev, obs) -> CandidateObservation:
    s, e = ev.start, ev.end
    if obs is None:                                  # no trustworthy station axis -> observer could not run
        return CandidateObservation(
            bore_label=str(bore.get("bore_label", "")), sheet=int(bore["sheet"]),
            start_ft=float(bore["start_ft"]), end_ft=float(bore["end_ft"]),
            start_source_bound=bool(s.source_bound), end_source_bound=bool(e.source_bound),
            start_source_type=s.source_type, end_source_type=e.source_type,
            start_blocker=s.blocker, end_blocker=e.blocker,
            branch_uniqueness=None, endpoint_to_run_x_tightness=None, start_2d=None, end_2d=None,
            start_provenance=None, end_provenance=None, class_verified=False,
            would_reject=None, two_d_verified=None, detail={"observer": "NO_STATION_AXIS"})
    return CandidateObservation(
        bore_label=str(bore.get("bore_label", "")), sheet=int(bore["sheet"]),
        start_ft=float(bore["start_ft"]), end_ft=float(bore["end_ft"]),
        start_source_bound=bool(s.source_bound), end_source_bound=bool(e.source_bound),
        start_source_type=s.source_type, end_source_type=e.source_type,
        start_blocker=s.blocker, end_blocker=e.blocker,
        branch_uniqueness=obs.branch_uniqueness, endpoint_to_run_x_tightness=obs.endpoint_to_run_x_tightness,
        start_2d=obs.start_2d.verdict, end_2d=obs.end_2d.verdict,
        start_provenance=_provenance_summary(obs.start_coordinate),
        end_provenance=_provenance_summary(obs.end_coordinate),
        class_verified=bool(obs.start_coordinate.class_verified and obs.end_coordinate.class_verified),
        would_reject=obs.would_reject, two_d_verified=obs.two_d_verified,
        detail={"reject_signals": list(obs.reject_signals),
                "start_coordinate_result": obs.start_coordinate.result,
                "end_coordinate_result": obs.end_coordinate.result,
                "start_leader_trace": obs.start_coordinate.leader_trace,
                "end_leader_trace": obs.end_coordinate.leader_trace})


def _candidate_blockers(c: CandidateObservation) -> List[str]:
    out: List[str] = []
    if not (c.start_source_bound and c.end_source_bound):
        out.append(INSUFFICIENT_TERMINUS_EVIDENCE)
    if NO_DRAWN_COORDINATE in (c.detail.get("start_coordinate_result"), c.detail.get("end_coordinate_result")):
        out.append(NO_DRAWN_COORDINATE_EVIDENCE)
    if (c.branch_uniqueness in (BRANCH_FORKED, BRANCH_RIVAL_RUNS)
            or AMBIGUOUS_DRAWN_COORDINATE in (c.detail.get("start_coordinate_result"),
                                              c.detail.get("end_coordinate_result"))):
        out.append(AMBIGUOUS_EVIDENCE)
    if c.branch_uniqueness == BRANCH_NO_SPANNING_RUN:
        out.append(NO_DRAWN_COORDINATE_EVIDENCE)
    return out


def run_observer_stack(plan_path, borelog_path, bores: Sequence[dict]) -> List[CandidateObservation]:
    """Per-bore read-only observer stack: derive terminus source-binding (``extract_termini``) then run the
    geometry + 2-D + provenance observer (``observe_package_terminus_geometry``). No placement, no store."""
    ev = extract_termini(plan_path, borelog_path)
    out: List[CandidateObservation] = []
    for bore in bores:
        obs = observe_package_terminus_geometry(
            str(plan_path), int(bore["sheet"]), float(bore["start_ft"]), float(bore["end_ft"]),
            start_source_bound=bool(ev.start.source_bound), end_source_bound=bool(ev.end.source_bound))
        out.append(_candidate(bore, ev, obs))
    return out


def load_package_manifest(package_dir) -> Optional[dict]:
    """Read ``package.json`` (no engine work). Returns the parsed dict, or None if missing/unreadable."""
    p = Path(package_dir) / "package.json"
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None


def _present_missing(package_dir: Path, uploads: Sequence[dict]):
    present, missing = [], []
    kinds = {}
    for u in uploads:
        k = u.get("kind")
        if k not in UPLOAD_KINDS:
            continue
        fp = package_dir / "uploads" / str(u.get("filename", ""))
        (present if fp.is_file() else missing).append(k)
        if fp.is_file():
            kinds[k] = fp
    for req in _REQUIRED_KINDS:
        if req not in kinds:
            if req not in missing:
                missing.append(req)
    return present, missing, kinds


def validate_package(package_dir, *, recognized_registry: Optional[Dict[str, Any]] = None,
                     synthetic_roots: Sequence = ()) -> PackageValidationReport:
    """Read-only eligibility + observer report for a candidate package. ``recognized_registry`` (optional
    sha256->any map) and ``synthetic_roots`` (dirs whose contents are synthetic) let a caller inject the
    recognized-corpus registry and the synthetic fixtures root. Never writes; never places; never promotes."""
    package_dir = Path(package_dir)
    pid = package_dir.name or "package"

    if not package_dir.is_dir():
        return _report(pid, PACKAGE_NOT_FOUND, "no package directory at %s" % package_dir,
                       "UNKNOWN", False, False, (), (), (), (REAL_FRESH_PACKAGE_VALIDATION_PENDING,))
    manifest = load_package_manifest(package_dir)
    if manifest is None:
        return _report(pid, PACKAGE_UNREADABLE, "missing or unreadable package.json",
                       "UNKNOWN", False, False, (), (), (), (REAL_FRESH_PACKAGE_VALIDATION_PENDING,))

    pid = str(manifest.get("package_id") or pid)
    declared = manifest.get("provenance_class")
    uploads = manifest.get("uploads") or []
    bores = manifest.get("bores") or []
    present, missing, kinds = _present_missing(package_dir, uploads)

    # (1) completeness — required files + at least one fully-specified bore
    bore_ok = [b for b in bores if all(k in b for k in ("sheet", "start_ft", "end_ft"))]
    if missing or not bore_ok:
        why = []
        if missing:
            why.append("missing required upload(s): %s" % ", ".join(sorted(set(missing))))
        if not bore_ok:
            why.append("no bore with sheet+start_ft+end_ft")
        return _report(pid, INCOMPLETE_UPLOAD, "; ".join(why), "UNKNOWN", False, False,
                       present, missing, (), (REAL_FRESH_PACKAGE_VALIDATION_PENDING,))

    plan_path, borelog_path = kinds["PLAN_PDF"], kinds["BORE_LOG"]

    # (2) recognition — SOURCE EVIDENCE overrides the declared class
    try:
        plan_bytes = plan_path.read_bytes()
        recognized = bool(select_dialect(PlanPdf(str(plan_path))) is not None)
    except Exception as exc:  # malformed / unreadable plan
        return _report(pid, PACKAGE_UNREADABLE, "plan unreadable: %s" % exc, "UNKNOWN", False, False,
                       present, missing, (), (REAL_FRESH_PACKAGE_VALIDATION_PENDING,))
    in_registry = bool(recognized_registry and _sha256(plan_bytes) in recognized_registry)
    if recognized or in_registry:
        reason = ("plan recognized by a named dialect" if recognized else
                  "plan is in the recognized-corpus registry")
        return _report(pid, INELIGIBLE_RECOGNIZED_WORK_CORPUS,
                       "%s -> work corpus, ineligible as cold proof (declared %r)" % (reason, declared),
                       "RECOGNIZED_WORK", True, False, present, missing, (),
                       (REAL_FRESH_PACKAGE_VALIDATION_PENDING,))

    # (3) declared ACTIVE_FIELD (a reserved active-field corpus) — ineligible as proof
    if declared == PROV_ACTIVE_FIELD:
        return _report(pid, INELIGIBLE_ACTIVE_FIELD_CORPUS,
                       "declared an active-field user's reserved corpus — ineligible as cold proof",
                       "ACTIVE_FIELD", False, False, present, missing, (),
                       (REAL_FRESH_PACKAGE_VALIDATION_PENDING,))

    # (4) synthetic (declared OR under a synthetic root) — exercise the report path, NOT real validation
    is_synth = (declared == PROV_SYNTHETIC) or _under_any(package_dir, synthetic_roots)
    # (5) declared work (without recognition firing) — still ineligible as proof
    if not is_synth and declared == PROV_WORK:
        return _report(pid, INELIGIBLE_RECOGNIZED_WORK_CORPUS,
                       "declared work corpus — ineligible as cold proof", "RECOGNIZED_WORK", False, False,
                       present, missing, (), (REAL_FRESH_PACKAGE_VALIDATION_PENDING,))
    # (6) eligible fresh — declared fresh, non-recognized, complete
    if not is_synth and declared != PROV_FRESH:
        return _report(pid, UNKNOWN_PROVENANCE_CLASS,
                       "provenance_class %r is not one of %s" % (declared, list(_DECLARED_CLASSES)),
                       "UNKNOWN", False, False, present, missing, (), (REAL_FRESH_PACKAGE_VALIDATION_PENDING,))

    eligibility = SYNTHETIC_TEST_ONLY if is_synth else ELIGIBLE_FRESH_NONRECOGNIZED
    corpus_class = PROV_SYNTHETIC if is_synth else PROV_FRESH
    real_validation = (eligibility == ELIGIBLE_FRESH_NONRECOGNIZED)

    # observer stack (read-only) for eligible-fresh and synthetic alike
    try:
        candidates = run_observer_stack(plan_path, borelog_path, bore_ok)
    except Exception as exc:
        return _report(pid, PACKAGE_UNREADABLE, "observer stack could not read the package: %s" % exc,
                       corpus_class, False, False, present, missing, (), (REAL_FRESH_PACKAGE_VALIDATION_PENDING,))

    blockers: List[str] = [CLASS_VERIFICATION_MISSING]
    if not real_validation:
        blockers.append(REAL_FRESH_PACKAGE_VALIDATION_PENDING)
    for c in candidates:
        blockers.extend(_candidate_blockers(c))
    reason = ("synthetic package — observer path exercised, NOT counted as real generalization" if is_synth
              else "fresh non-recognized package, complete + plan not recognized — eligible for cold proof")
    return _report(pid, eligibility, reason, corpus_class, False, real_validation,
                   present, missing, candidates, blockers)


def format_report(report: PackageValidationReport) -> str:
    return json.dumps(report.to_dict(), indent=2, sort_keys=True)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Harness-only diagnostic CLI: ``python -m truelinev2.harness.package_validation <package_dir>`` prints the
    read-only validation report as JSON. Performs no placement and writes nothing."""
    import sys
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        sys.stderr.write("usage: package_validation <package_dir>\n")
        return 2
    print(format_report(validate_package(args[0])))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
