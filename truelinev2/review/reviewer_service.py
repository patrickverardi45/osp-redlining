r"""M8.11 -- reviewer bundle service seam (service contract only).

The seam a future v2 API route / reviewer UI consumes: given a corpus of bore
logs and one plan PDF, produce the FULL M8.10 reviewer payload bundle -- every
bore in exactly one validated lane -- under an EXPLICIT run mode. No FastAPI
route, no UI, no DB/artifact writes, no env reads, no engine wiring.

Run modes are a CLOSED table (the only way solver flags compose here):

  default_baseline     -- all opt-in solvers OFF (the corrected-source default).
  fullest_safe_review  -- M8.5 reverse-endpoint + M8.8 station-axis ONLY (the
                          two zero-false REVIEW-only opt-ins). M8.2l collision
                          and M8.4 continuation are NOT composed; M8.2d blanket
                          frame translation has no flag here and never will.

The mode table is a LOCAL payload-generation choice: it never reads environment
flags, never mutates ``Settings``, and changes no production default. The
bundle records the exact flag state used, and its validator pins flag state to
the mode table so a bundle cannot claim one mode while built under another.

Contract rules (validated by pydantic, not documented-and-hoped):
  * every bore yields exactly one M8.10 ``ReviewerPayload``; a payload that
    fails validation RAISES -- no quiet skips, no force-green;
  * lane/status counts are recomputed inside the bundle validator and must
    match the declared counts;
  * suggestions stay ``SUGGESTION_NOT_PLACEMENT`` and confidence stays a
    closed CLASS (enforced by the M8.10 models this module builds on);
  * no geometry is invented -- evidence is the engine's and the M8.7/M8.9
    classifiers' text/station math, unchanged.

Lane routing for non-placed bores mirrors the banked M8.10 proof runner
(``proof/run_reviewer_payload_contract``) verbatim: M8.7 ``prove_interval_path``
routes in-class vs out-of-class; M8.9 ``classify_frame_ownership`` assigns the
product lane. Both are CLASSIFIERS (consulted in BOTH modes for lane routing,
never for placement). They currently live under ``proof/``; re-homing them is a
future named decision (as M8.8 re-homed the station-axis solver into match/).
"""
from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Dict, List, Sequence

from pydantic import BaseModel, ConfigDict, Field, model_validator

from truelinev2.extract.registry import select_dialect
from truelinev2.extract.station_axis import parse_tick
from truelinev2.ingest.normalize import load_borelog
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.match.collision_gate import collect_equations
from truelinev2.match.engine import run_match
from truelinev2.match.reverse_anchor import ReverseAnchorContext
from truelinev2.match.station_axis_interval import StationAxisContext, prove_interval_path
from truelinev2.match.transition_classifier import conflict_sheet_pairs
from truelinev2.proof.frame_ownership_candidates import classify_frame_ownership
from truelinev2.proof.station_equation_ownership import extract_reset_origins, parse_hh_distances
from truelinev2.review.reviewer_payloads import (
    SCHEMA_VERSION,
    ReviewerLane,
    ReviewerPayload,
    payload_from_frame_ownership,
    payload_from_placement,
    payload_out_of_class,
    payload_source_error,
)
from truelinev2.service import _build_plan_frame_graph

BUNDLE_SCHEMA_VERSION = "truelinev2-reviewer-bundle-1"

_STATUS_KEYS = ("AUTO_SELECT", "REVIEW", "ABSTAIN", "ERROR")

# the named next solver per M8.7 verdict, for OUT_OF_CLASS routing
# (verbatim from the banked M8.10 proof runner)
NEXT_SOLVER = {
    "END_STATION_NOT_FOUND": ("structure-identity binding at the bore end / "
                              "interval endpoint-rounding evidence"),
    "STATION_TICK_NOT_FOUND": ("vision/crop inspection of the drawn path or a "
                               "bore-frame binding datum"),
    "PATH_DISCONTINUITY": ("the missing sheet's ticks or a frame equation to "
                           "prove path continuity"),
    "FOOTAGE_MISMATCH": ("the missing authored interval or drawn-path geometry "
                         "(vector layer)"),
}


class ReviewRunMode(str, Enum):
    DEFAULT_BASELINE = "default_baseline"
    FULLEST_SAFE_REVIEW = "fullest_safe_review"


class GenerationFlagState(BaseModel):
    """Frozen record of the solver opt-ins a bundle was generated under.
    Field order mirrors ``config.Settings``; all fields are required so the
    mode table below spells out every flag explicitly."""
    model_config = ConfigDict(frozen=True)
    reset_collision_optin: bool
    frame_continuation_optin: bool
    reverse_endpoint_optin: bool
    station_axis_interval_optin: bool


# The closed mode table. fullest_safe_review composes EXACTLY the two
# zero-false REVIEW-only opt-ins (M8.5 + M8.8); collision (a demote gate) and
# continuation (corpus-inert) stay OFF in every mode pending owner activation.
MODE_FLAGS: Dict[ReviewRunMode, GenerationFlagState] = {
    ReviewRunMode.DEFAULT_BASELINE: GenerationFlagState(
        reset_collision_optin=False, frame_continuation_optin=False,
        reverse_endpoint_optin=False, station_axis_interval_optin=False),
    ReviewRunMode.FULLEST_SAFE_REVIEW: GenerationFlagState(
        reset_collision_optin=False, frame_continuation_optin=False,
        reverse_endpoint_optin=True, station_axis_interval_optin=True),
}


class CorpusSource(BaseModel):
    """Source metadata sufficient to debug a bundle: where every input came
    from, in enumeration order."""
    corpus_dir: str
    plan_pdf_path: str
    sheet_offset: int
    bore_log_count: int = Field(ge=0)
    bore_log_files: List[str]

    @model_validator(mode="after")
    def _count_matches(self) -> "CorpusSource":
        if self.bore_log_count != len(self.bore_log_files):
            raise ValueError("bore_log_count must equal len(bore_log_files)")
        return self


class ReviewerBundle(BaseModel):
    """The validated reviewer bundle. The validator recomputes every count
    from the payloads themselves -- a bundle whose declared counts drift from
    its contents fails construction loudly."""
    bundle_schema_version: str = BUNDLE_SCHEMA_VERSION
    payload_schema_version: str = SCHEMA_VERSION
    project_id: str
    run_mode: ReviewRunMode
    flag_state: GenerationFlagState
    status_counts: Dict[str, int]
    lane_counts: Dict[str, int]
    payloads: List[ReviewerPayload]
    source: CorpusSource

    @model_validator(mode="after")
    def _bundle_contract(self) -> "ReviewerBundle":
        if self.bundle_schema_version != BUNDLE_SCHEMA_VERSION:
            raise ValueError(f"bundle schema must be {BUNDLE_SCHEMA_VERSION}")
        if self.payload_schema_version != SCHEMA_VERSION:
            raise ValueError(f"payload schema must be {SCHEMA_VERSION}")
        bad = [p.bore_id for p in self.payloads
               if p.schema_version != self.payload_schema_version]
        if bad:
            raise ValueError(f"payload schema_version drift: {bad}")
        if self.flag_state != MODE_FLAGS[self.run_mode]:
            raise ValueError(
                f"flag_state does not match the closed table for {self.run_mode}")
        if len(self.payloads) != self.source.bore_log_count:
            raise ValueError(
                f"every bore must reach a lane: {len(self.payloads)} payloads "
                f"for {self.source.bore_log_count} bore logs")
        ids = [p.bore_id for p in self.payloads]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate bore_id in payloads")
        derived: Dict[str, int] = {}
        for p in self.payloads:
            derived[p.lane.value] = derived.get(p.lane.value, 0) + 1
        if derived != self.lane_counts:
            raise ValueError(
                f"lane_counts drift: declared {self.lane_counts} != derived {derived}")
        missing = [k for k in (*_STATUS_KEYS, "PLACED") if k not in self.status_counts]
        if missing:
            raise ValueError(f"status_counts missing keys: {missing}")
        placed = self.status_counts["AUTO_SELECT"] + self.status_counts["REVIEW"]
        if self.status_counts["PLACED"] != placed:
            raise ValueError("PLACED must equal AUTO_SELECT + REVIEW")
        if sum(self.status_counts[k] for k in _STATUS_KEYS) != self.source.bore_log_count:
            raise ValueError("status counts must sum to the bore log count")
        if self.lane_counts.get(ReviewerLane.PLACED_REVIEW.value, 0) != placed:
            raise ValueError("PLACED_REVIEW lane count must equal placed statuses")
        return self


class ReviewerBundleService:
    """Pure generation seam: paths in, validated ``ReviewerBundle`` out.

    Holds only immutable configuration (where the corpus and plan live); each
    ``generate`` call opens the plan, runs the corpus under the requested mode,
    and closes the plan. Nothing is cached, persisted, or rendered."""

    def __init__(self, *, corpus_dir: str, plan_pdf_path: str, project_id: str,
                 bore_log_paths: Sequence[Path], sheet_offset: int = 13):
        self._corpus_dir = corpus_dir
        self._plan_pdf_path = plan_pdf_path
        self._project_id = project_id
        self._bore_log_paths = [Path(p) for p in bore_log_paths]
        self._sheet_offset = sheet_offset

    def generate(self, mode: ReviewRunMode) -> ReviewerBundle:
        flags = MODE_FLAGS[mode]
        statuses: List[str] = []
        payloads: List[ReviewerPayload] = []
        plan = PlanPdf(self._plan_pdf_path)
        try:
            dialect = select_dialect(plan)
            if dialect is None:
                raise ValueError("no registered plan dialect recognized this plan")
            offset = dialect.calibrate(plan, self._sheet_offset)
            graph = conflicts = None
            if flags.reverse_endpoint_optin:
                graph = _build_plan_frame_graph(plan, offset)
                conflicts = conflict_sheet_pairs(graph)
            for p in self._bore_log_paths:
                try:
                    bore = load_borelog(str(p))
                except Exception as e:
                    statuses.append("ERROR")
                    payloads.append(payload_source_error(
                        p.stem.replace("bore_log", "log"),
                        f"{type(e).__name__}: {e}"))
                    continue
                axis_sheets = sorted({x for r in bore.sheet_refs
                                      for x in (r - 1, r, r + 1) if x >= 1})
                # Ticks + axis callouts (refs +-1) feed the M8.8 solver when its
                # flag is ON and the M8.7/M8.9 LANE ROUTING in both modes.
                # Computed lazily: in default mode a placed bore never needs them.
                axis_data = None

                def _axis(s=axis_sheets, b=bore):
                    nonlocal axis_data
                    if axis_data is None:
                        axis_data = (
                            {sh: tuple(t for t in (parse_tick(w["text"])
                                                   for w in plan.words(sh, offset))
                                       if t is not None) for sh in s},
                            tuple(c for sh in s
                                  for c in dialect.extract_callouts(plan, sh, offset)))
                    return axis_data

                rev_ctx = None
                if flags.reverse_endpoint_optin:
                    # per-bore sheet_refs equations: the construction the banked
                    # M8.5/M8.8 sweeps and the M8.10 lane proof all used
                    rev_ctx = ReverseAnchorContext(
                        graph=graph, conflicts=conflicts,
                        equations_by_sheet=collect_equations(plan, offset,
                                                             bore.sheet_refs))
                axis_ctx = None
                if flags.station_axis_interval_optin:
                    ticks, cals = _axis()
                    axis_ctx = StationAxisContext(ticks_by_sheet=ticks, callouts=cals)
                pl = run_match(bore, plan, dialect, offset,
                               reverse_anchor=rev_ctx, station_axis=axis_ctx)
                statuses.append(pl.status.value)
                if pl.status.value in ("AUTO_SELECT", "REVIEW"):
                    payloads.append(payload_from_placement(bore, pl))
                    continue
                ticks, cals = _axis()
                payloads.append(self._route_abstain(
                    plan, offset, bore, axis_sheets, ticks, cals))
        finally:
            plan.close()

        status_counts = {k: statuses.count(k) for k in _STATUS_KEYS}
        status_counts["PLACED"] = (status_counts["AUTO_SELECT"]
                                   + status_counts["REVIEW"])
        lane_counts: Dict[str, int] = {}
        for pay in payloads:
            lane_counts[pay.lane.value] = lane_counts.get(pay.lane.value, 0) + 1
        return ReviewerBundle(
            project_id=self._project_id, run_mode=mode, flag_state=flags,
            status_counts=status_counts, lane_counts=lane_counts,
            payloads=payloads,
            source=CorpusSource(
                corpus_dir=self._corpus_dir, plan_pdf_path=self._plan_pdf_path,
                sheet_offset=self._sheet_offset,
                bore_log_count=len(self._bore_log_paths),
                bore_log_files=[p.name for p in self._bore_log_paths]))

    @staticmethod
    def _route_abstain(plan: PlanPdf, offset: int, bore, axis_sheets: List[int],
                       ticks_by_sheet: Dict, callouts) -> ReviewerPayload:
        """Banked M8.10 routing: M8.7 verdict -> out-of-class, else the M8.9
        frame-ownership lane. Classification only -- never places."""
        m87 = prove_interval_path(
            bore_id=bore.bore_id, bore_start_ft=bore.station_start_ft,
            bore_end_ft=bore.station_end_ft, span_ft=bore.span_ft,
            ticks_by_sheet=dict(ticks_by_sheet), callouts=list(callouts),
            sheet_refs=list(bore.sheet_refs))
        if m87["result"] != "FRAME_OR_SHEET_CONFLICT":
            return payload_out_of_class(
                bore, m87["result"],
                NEXT_SOLVER.get(m87["result"], "named-solver triage"),
                named=m87.get("named_missing_relationship"))
        origins, hh_by_sheet = [], {}
        for s in axis_sheets:
            lines = plan.lines(s, offset)
            origins.extend(extract_reset_origins(lines, s))
            notes = parse_hh_distances(" ".join(lines))
            if notes:
                hh_by_sheet[s] = notes
        verdict = classify_frame_ownership(
            bore_id=bore.bore_id, bore_start_ft=bore.station_start_ft,
            bore_end_ft=bore.station_end_ft, span_ft=bore.span_ft,
            ticks_by_sheet=dict(ticks_by_sheet), callouts=list(callouts),
            origins=origins, hh_notes_by_sheet=hh_by_sheet,
            sheet_refs=list(bore.sheet_refs),
            equations_by_sheet=collect_equations(plan, offset, axis_sheets))
        return payload_from_frame_ownership(bore, verdict)
