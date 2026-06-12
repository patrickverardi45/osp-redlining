r"""M8.20 Law 1 -- SHARED_ALIGNMENT_MULTI_DROP (corpus-level, REVIEW-only).

A PURE decision law. It consumes per-bore extractions already produced by the
EXISTING per-bore gates (M8.17 uniqueness-mandatory printed chain, M8.18 single
design-path survivor, M8.19 path-length cross-sheet join, M8.20 retained walk
geometry) and decides whether N >= 2 bores legitimately share ONE origin
structure as a multi-drop terminal. It NEVER weakens those gates and NEVER
places: the only positive verdict is REVIEW (``SUGGESTION_NOT_PLACEMENT``).

By construction this law lives ABOVE the per-bore lane: ``resolve_bore`` is
per-bore (it cannot see another bore's claims), so collision detection is
corpus-level here. This module is imported by the M8.20 proof and tests only;
it is NOT wired into ``resolve_bore`` or the sweep (the per-bore lane stays
pure and the all-58 census is unchanged). Surfacing a REVIEW verdict into the
shipped reviewer payload is a separately authorized follow-up (see
``wiki/m8_20_adjudication.md`` Phase 3).

Encoded doctrine:
  * Law 1 -- the seven gates below; ALL must hold; output REVIEW, never AUTO.
  * Law 2 -- a single failed gate REJECTS every sharing bore (pairwise at the
    shared structure), typed, with the exact missing artifact NAMED. The
    shared-survivor fact alone neither proves nor rejects.
  * Law 3 -- intermediate stations (e.g. ``1+10`` vs ``1+30``) are used ONLY to
    confirm the printed chains are DISTINCT (gate 3). They are NEVER used to
    assign SEPARATE origins: the measured geometry is one drawn alignment, so
    the origin is shared. Inventing per-bore origins from intermediate stations
    is forbidden and this law never does it.

No tolerance is introduced or widened: gate 2 uses the structural
``JITTER_EQUIV_TOL`` (the weld-contact scale, the engine's "same drawn line"
band) verbatim.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Sequence, Tuple

from truelinev2.extract.design_path import JITTER_EQUIV_TOL, point_to_polyline

LAW_NAME = "SHARED_ALIGNMENT_MULTI_DROP"
MODE = "REVIEW_ONLY"          # structural: this law has no AUTO branch
SUGGESTION_LABEL = "SUGGESTION_NOT_PLACEMENT"

V_REVIEW = "SHARED_ALIGNMENT_MULTI_DROP_REVIEW"      # all gates hold: REVIEW only
V_REJECTED = "SHARED_ALIGNMENT_REJECTED"             # Law 2: typed pairwise reject
V_NOT_APPLICABLE = "SHARED_ALIGNMENT_NOT_APPLICABLE"  # < 2 bores share: law never enters

# The ordered gate names (for typed refusals + drift-proof tests).
GATE_PER_BORE = "per_bore_gates_unchanged"
GATE_DISTINCT_CHAINS = "distinct_printed_chains"
GATE_SHARED_ALIGNMENT = "measured_shared_alignment"
GATE_CONDUIT = "per_chain_conduit_evidence"
GATE_MULTIPORT = "multiport_origin_class"
GATE_BIJECTION = "claim_bijection"


@dataclass(frozen=True)
class BoreClaim:
    """One bore's already-extracted claim on the shared origin. Every field is
    a fact produced by an existing gate -- this law re-checks their JOINT
    consistency, it never re-derives or relaxes them."""
    bore_id: str
    survivor_id: str                                  # far-sheet structure label
    boundary_raw: str                                 # this run's matchline station
    chain_unique: bool                                # M8.17 CHAIN_UNIQUE
    join_proven: bool                                 # M8.19 join PROVEN
    chain_hops: Tuple[Tuple[str, str, float], ...]    # ((from,to,ft), ...)
    walk_points: Tuple[Tuple[float, float], ...]      # M8.20 retained stroke_points
    boundary_xy: Tuple[float, float]                  # drawn matchline boundary point
    conduit_count: int                                # # material-bound conduit statements
    origin_multiport: bool                            # printed multi-port origin class


def _max_cross_deviation(a: Sequence[Tuple[float, float]],
                         b: Sequence[Tuple[float, float]]) -> Optional[float]:
    """Symmetric max point-to-polyline deviation between two walks. Duplicates
    ``design_path._cross_deviation`` via the PUBLIC ``point_to_polyline`` (the
    private is not exported); a tripwire test pins the two equal so the match-
    layer law can never silently diverge from the engine's equivalence law."""
    if len(a) < 2 or len(b) < 2:
        return None
    return max(max(point_to_polyline(p, b) for p in a),
               max(point_to_polyline(p, a) for p in b))


def _reject(bores, shared, gate, missing) -> dict:
    """Law 2: a typed, named pairwise rejection of ALL sharing bores."""
    return {"verdict": V_REJECTED, "law": LAW_NAME, "mode": MODE,
            "shared_origin": shared, "bores": list(bores),
            "failed_gate": gate, "named_missing": missing,
            "review_only": True, "auto": False}


def _not_applicable(reason: str) -> dict:
    return {"verdict": V_NOT_APPLICABLE, "law": LAW_NAME, "mode": MODE,
            "reason": reason, "auto": False}


def shared_alignment_verdict(
        claims: Sequence[BoreClaim], *,
        origin_chain_boundaries: frozenset) -> dict:
    """Apply the seven Law-1 gates to the claims that share ONE survivor.

    ``origin_chain_boundaries`` is the set of boundary stations of EVERY
    uniqueness-mandatory printed chain that starts at the shared origin's start
    station and reaches a boundary on the shared matchline (extracted upstream).
    It is the bijection universe: gate 5 requires the claimed boundaries to be
    exactly this set, each once.
    """
    claims = list(claims)

    # Gate 6 / entry: corpus-level, >= 2 bores must share EXACTLY ONE survivor.
    if len(claims) < 2:
        return _not_applicable("fewer than two bores claim the structure "
                               "(one-bore inference can never invoke this law)")
    survivors = {c.survivor_id for c in claims}
    if len(survivors) != 1:
        return _not_applicable(f"claims span {len(survivors)} survivor "
                               f"structures, not one shared origin")
    shared = next(iter(survivors))
    bores = sorted(c.bore_id for c in claims)

    # Gate 1: existing per-bore gates remain unchanged (each independently
    # passed its M8.17 chain AND M8.19 join -- this law requires, never relaxes).
    bad = sorted(c.bore_id for c in claims
                 if not (c.chain_unique and c.join_proven))
    if bad:
        return _reject(bores, shared, GATE_PER_BORE,
                       f"{bad} did not independently pass the unchanged per-bore "
                       f"printed-chain + path-length-join gates")

    # Gate 3: N distinct closure-proven printed chains (pairwise-different hop
    # sets AND boundary stations). Computed before bijection. Law 3 lives here:
    # intermediate stations only PROVE distinctness, never split the origin.
    hop_sets = [tuple(c.chain_hops) for c in claims]
    boundaries = [c.boundary_raw for c in claims]
    if len(set(hop_sets)) != len(claims) or len(set(boundaries)) != len(claims):
        return _reject(bores, shared, GATE_DISTINCT_CHAINS,
                       "the claiming printed chains are not pairwise distinct "
                       "(a shared hop set or a shared boundary station)")

    # Gate 2: MEASURED pairwise jitter-equivalent walks AND coincident drawn
    # boundary points -- one drawn alignment, at the structural weld scale
    # (never loosened). A divergent pair is distinct drawn drops, not one origin.
    for i in range(len(claims)):
        for j in range(i + 1, len(claims)):
            a, b = claims[i], claims[j]
            dev = _max_cross_deviation(a.walk_points, b.walk_points)
            gap = math.dist(a.boundary_xy, b.boundary_xy)
            if dev is None or dev > JITTER_EQUIV_TOL or gap > JITTER_EQUIV_TOL:
                return _reject(
                    bores, shared, GATE_SHARED_ALIGNMENT,
                    f"{a.bore_id}/{b.bore_id} walks are not jitter-equivalent "
                    f"(max deviation {dev}, boundary gap {round(gap, 2)} pt vs "
                    f"JITTER_EQUIV_TOL {JITTER_EQUIV_TOL}) -- distinct drawn "
                    f"drops are not one shared origin")

    # Gate 4: positive printed multi-run evidence. Per-chain MATERIAL-bound
    # conduit statement AND a printed multi-port-capable origin class. Absence
    # for ANY claimant -> reject all (loose count-size text is not evidence;
    # the Phase-1 grammar already rejects depth/cover ranges).
    no_conduit = sorted(c.bore_id for c in claims if c.conduit_count < 1)
    if no_conduit:
        return _reject(bores, shared, GATE_CONDUIT,
                       f"{no_conduit} carry no material-bound printed conduit "
                       f"statement on their chain")
    no_port = sorted(c.bore_id for c in claims if not c.origin_multiport)
    if no_port:
        return _reject(bores, shared, GATE_MULTIPORT,
                       f"{no_port} do not print a multi-port-capable origin "
                       f"class at the shared origin")

    # Gate 5: claim bijection. Every printed chain FROM the shared origin TO a
    # boundary on the matchline must be claimed exactly once. Shared-survivor
    # selection is necessary, not sufficient: an unclaimed or doubly-claimed
    # printed run abstains all (gate 3 already guaranteed claims are distinct,
    # so a count/set mismatch here is an unclaimed or extra printed run).
    claimed = sorted(boundaries)
    universe = sorted(origin_chain_boundaries)
    if claimed != universe:
        return _reject(bores, shared, GATE_BIJECTION,
                       f"printed origin chains {universe} != claimed boundaries "
                       f"{claimed} -- an unclaimed or doubly-claimed printed "
                       f"run forbids the multi-drop binding")

    # Gate 7: all gates hold -> REVIEW-only. Never AUTO, never a placement; the
    # reviewer confirms the multi-drop assignment of N runs to one origin.
    return {"verdict": V_REVIEW, "law": LAW_NAME, "mode": MODE,
            "shared_origin": shared, "bores": bores, "boundaries": claimed,
            "review_only": True, "auto": False, "label": SUGGESTION_LABEL,
            "detail": (f"{len(claims)} distinct closure-proven printed runs over "
                       f"one MEASURED drawn alignment from one multi-port origin "
                       f"{shared}; REVIEW required to confirm the multi-drop "
                       f"assignment -- not a placement")}
