r"""Contract -> PROOF adapter (PURE; no PDF / render / product / proof-execution imports).

Proves the typed coordinate-free seam contract (truelinev2/seam/contract.py) can HAND OFF each
eligible exemplar to the EXISTING proven per-leg source-bind/render proof families -- without wiring
anything into product/runtime, without a batch runner, and without executing the proofs. It consumes
the CANONICAL seam payload (it does NOT duplicate the contract's topology) and emits a coordinate-free
proof-DISPATCH descriptor naming, per leg, the proof family + the existing source-bind/render proof
MODULES that would derive coordinates downstream.

  log53 -> log53_two_sheet_matchline_endpoint            (STA 24+11 modeled matchline endpoint)
  log64 -> log64_single_sheet_structure_to_structure
  log71 -> log71_two_sheet_structure_to_structure_route_context  (STA 5+45 route context; s24 bends)
  log59 -> log59_single_sheet_structure_to_structure     (log64's shape but its OWN ordered_chain_path proofs)

Eligibility never expands here: the dispatch is frozen to the three proven exemplars and inherits the
contract's refusal of any other log (no silent promotion). The descriptor stays coordinate-free; only
the referenced existing proofs derive coordinates from PDF primitives. This module imports NO renderer,
NO PDF, NO product code, and never imports/executes the proof modules it names (it carries their
import paths as strings; existence is checked read-only by the adapter proof).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Dict, Optional, Tuple

from truelinev2.seam.contract import (
    ELIGIBLE_EXEMPLARS,
    SeamPayload,
    build_seam_payload,
    is_coordinate_free,
)


class ProofFamily(str, Enum):
    LOG53_TWO_SHEET_MATCHLINE_ENDPOINT = "log53_two_sheet_matchline_endpoint"
    LOG64_SINGLE_SHEET_STRUCTURE_TO_STRUCTURE = "log64_single_sheet_structure_to_structure"
    LOG71_TWO_SHEET_STRUCTURE_TO_STRUCTURE_ROUTE_CONTEXT = "log71_two_sheet_structure_to_structure_route_context"
    LOG59_SINGLE_SHEET_STRUCTURE_TO_STRUCTURE = "log59_single_sheet_structure_to_structure"


# canonical proof-family registry: the EXISTING proven modules each eligible exemplar hands off to.
# These are dispatch TARGETS (import-path strings); the adapter never imports or executes them.
PROOF_FAMILY: Dict[str, dict] = {
    "log53": {"family": ProofFamily.LOG53_TWO_SHEET_MATCHLINE_ENDPOINT,
              "source_bind_proofs": ("truelinev2.proof.run_log53_matchline_boundary_slice",
                                     "truelinev2.proof.run_log53_nextlink_hh_bindability_slice"),
              "render_proof": "truelinev2.proof.run_log53_render_artifact_slice"},
    "log64": {"family": ProofFamily.LOG64_SINGLE_SHEET_STRUCTURE_TO_STRUCTURE,
              "source_bind_proofs": ("truelinev2.proof.run_log64_sheet21_source_bind_slice",),
              "render_proof": "truelinev2.proof.run_log64_render_artifact_slice"},
    "log71": {"family": ProofFamily.LOG71_TWO_SHEET_STRUCTURE_TO_STRUCTURE_ROUTE_CONTEXT,
              "source_bind_proofs": ("truelinev2.proof.run_log71_two_leg_source_bind_slice",),
              "render_proof": "truelinev2.proof.run_log71_render_artifact_slice"},
    "log59": {"family": ProofFamily.LOG59_SINGLE_SHEET_STRUCTURE_TO_STRUCTURE,
              "source_bind_proofs": ("truelinev2.proof.run_log59_sheet21_source_bind_slice",),
              "render_proof": "truelinev2.proof.run_log59_render_artifact_slice"},
}


@dataclass(frozen=True)
class LegDispatch:
    """How ONE seam leg hands off to the proven proofs. Coordinate-free: it names boundary kinds,
    route mode, and proof targets -- never a position (the named proofs derive those downstream)."""
    sheet: int
    start_boundary_kind: str
    end_boundary_kind: str
    route_context_role: Optional[str]
    matchline_station: Optional[str]          # the route-context/endpoint matchline STATION label (not a coordinate)
    render_mode: str
    expected_proof_family: str
    expected_source_bind_proofs: Tuple[str, ...]
    expected_render_proof: str


@dataclass(frozen=True)
class ProofDispatch:
    bore_id: str
    shape: str
    legs: Tuple[LegDispatch, ...]
    cross_sheet_join: Optional[str]
    cross_sheet_coordinate_reconciliation: bool

    def to_dict(self) -> dict:
        return asdict(self)


def dispatch_for(payload: SeamPayload) -> ProofDispatch:
    """Map a CANONICAL seam-contract payload to a coordinate-free proof-dispatch descriptor. The
    boundary kinds, route-context role, and render mode are copied VERBATIM from the contract leg
    (never downgraded -- log71 sheet 24 stays ordered_chain_path); the proof family + existing
    source-bind/render proof modules are looked up from the registry. Refuses any bore not in the
    frozen registry (no silent promotion)."""
    fam = PROOF_FAMILY.get(payload.bore_id)
    if fam is None:
        raise ValueError(f"no proof family for {payload.bore_id!r}; adapter is eligibility-frozen "
                         f"to {tuple(PROOF_FAMILY)}")
    legs = tuple(
        LegDispatch(
            sheet=leg.sheet,
            start_boundary_kind=leg.start_anchor.boundary_kind.value,
            end_boundary_kind=leg.end_anchor.boundary_kind.value,
            route_context_role=(leg.route_context.role if leg.route_context else None),
            matchline_station=(leg.route_context.matchline_station if leg.route_context else None),
            render_mode=leg.render_mode.value,
            expected_proof_family=fam["family"].value,
            expected_source_bind_proofs=fam["source_bind_proofs"],
            expected_render_proof=fam["render_proof"])
        for leg in payload.legs)
    return ProofDispatch(
        bore_id=payload.bore_id, shape=payload.shape.value, legs=legs,
        cross_sheet_join=payload.cross_sheet_join,
        cross_sheet_coordinate_reconciliation=payload.cross_sheet_coordinate_reconciliation)


def build_dispatch(log_id: str, record: dict) -> ProofDispatch:
    """Build the proof-dispatch for ONE eligible exemplar straight from committed data, via the
    CANONICAL contract (build_seam_payload refuses any non-eligible log -- the adapter inherits that
    refusal; no duplicate topology lives here)."""
    return dispatch_for(build_seam_payload(log_id, record))


def eligible_dispatches(doc: dict) -> Dict[str, ProofDispatch]:
    """Proof-dispatch for exactly the three eligible exemplars, keyed by bore_id. Never promotes
    another log."""
    rec = {r["log_id"]: r for r in doc["logs"]}
    return {lid: build_dispatch(lid, rec[lid]) for lid in ELIGIBLE_EXEMPLARS}


def dispatch_is_coordinate_free(dispatch: ProofDispatch) -> bool:
    """The handoff descriptor stays coordinate-free until the named existing proofs derive coords."""
    return is_coordinate_free(dispatch.to_dict())
