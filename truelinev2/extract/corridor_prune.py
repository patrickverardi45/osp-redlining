r"""M8.21 -- length-law corridor pruning for design-path walks (GENERAL;
no plan-set knowledge; proof-consumed only -- NOT wired into any lane).

``walk_design_path`` judges uniqueness over the piece universe it is GIVEN.
On a dense sheet the exhaustive DFS exhausts ``MAX_WALK_EXPANSIONS`` before
finishing, so every candidate dies ``DESIGN_PATH_SEARCH_EXHAUSTED`` and
uniqueness is uncertifiable (the banked log42 state). Raising the budget is
forbidden (a budget raise is not proof; a finished dense search lands in
``DESIGN_PATH_AMBIGUOUS`` and distinct geometry is never tiebroken). The
M8.20 adjudication named the missing capability: corridor-pruned /
junction-bounded unique tracing. This module is that corridor.

THE CORRIDOR IS THE EXISTING LENGTH LAW, NOT A NEW TOLERANCE. The M8.18
survivor gate already refuses any traced path whose length deviates more
than ``DESIGN_LENGTH_REL_TOL`` from ``footage * scale``. ``trim_to_anchors``
makes the walk anchors literal endpoints of the final path, so for every
vertex ``v`` retained in a final path, ``path_length >= d(start, v) +
d(v, end)`` (triangle inequality, zero slack). A piece whose vertices ALL
have ``d(start, v) + d(v, end) > bound`` therefore cannot contribute a
vertex to ANY final path the existing gate could accept -- removing it
removes only provably-gate-failing geometry. The keep rule is VERTEX
containment (a piece is kept iff at least one of its polyline vertices is
inside the bound), deliberately NOT geometric ellipse intersection: a path
through a piece contains the piece's vertices, so vertex containment is the
sound certificate.

Slack term (a structural derivation, not a tunable): vertices can leave a
final path only via the anchor trim (``TRIM_RADIUS``) or hairpin collapse
(``STITCH_SLACK``-gated, which cannot synthesize reach beyond the stitch
scale), and a piece enterable from an admissible-path vertex sits within one
``jump_cap`` hop of it. ``2 * (jump_cap + TRIM_RADIUS)`` covers both ends
with margin; the survivor's own final path must never need the slack (the
M8.21 probe gates that, pinned).

ONE-SIDED GUARANTEE (honest scope): pruning can only LOSE walk completions
(a hairpin variant whose direct sibling needs a jump exceeding ``jump_cap``
by up to the stitch scale can lose its only realization), never create
them. Lost completions convert to typed conservative abstains
(``NOT_CONNECTED`` / fewer paths) -- never a false survivor. Uniqueness
certified on a FINISHED pruned search means: unique among
LENGTH-ADMISSIBLE-CAPABLE geometry. That is a DIFFERENT certificate class
from a finished full-universe search (M8.18-class): a candidate that a
finished full search would kill ``DESIGN_PATH_AMBIGUOUS`` via a
length-INADMISSIBLE rival can survive in the corridor. Enumerated complete
paths are NEVER filtered by admissibility after the walk -- complete-but-
inadmissible in-corridor paths remain rivals and kill via ``AMBIGUOUS``.
Any consumer of corridor results must carry that provenance
(``UNIVERSE_LENGTH_CORRIDOR``) and any future wiring toward a placement
lane requires a fresh adversarial judgment of the semantics shift. The
shipped Law 1 (``SHARED_ALIGNMENT_MULTI_DROP``) gate 1 means FULL-UNIVERSE
survivorship and does not accept corridor-class survivors.

FRAME CAUTION (the M8.21 refutation lesson): the bound is parameterized by a
printed footage. On a sheet with more than one printed reset origin the
footage's FRAME must be proven (callout frame ownership) before any survivor
is read as an origin identity -- a structure can uniquely trace to the
boundary and still be an INTERIOR reset of the run (the banked log42 case:
the equation-bound installer HH at callout-frame 0+46 traces 224 ft, which
is footage - 46, not footage). This module prunes; it never adjudicates
identity.

No tolerance is introduced or widened: ``DESIGN_LENGTH_REL_TOL``,
``TRIM_RADIUS`` and the dash-gap cap are imported verbatim. There are no
numeric defaults beyond the imported constants and no fallback scale -- a
missing scale is a typed refusal, never a guess. Pure functions; nothing
rendered; no layer names, no company strings.
"""
from __future__ import annotations

import math
from typing import List, Sequence, Tuple

from truelinev2.extract.conduit_topology import MAX_DASH_GAP
from truelinev2.extract.design_path import (DESIGN_LENGTH_REL_TOL, TRIM_RADIUS,
                                            Piece)

Point = Tuple[float, float]

# Typed refusal: the corridor bound is derived from the coherent ladder
# scale; when no coherent scale exists the corridor must not exist either
# (a fallback scale would be a guess -- the banked probe posture).
SCALE_NOT_COHERENT = "LADDER_SCALE_NOT_COHERENT"

# Provenance tag every consumer must carry on corridor-certified results so
# they can never be mistaken for finished full-universe (M8.18-class)
# certificates.
UNIVERSE_LENGTH_CORRIDOR = "LENGTH_ADMISSIBLE_CORRIDOR"

# Typed pre-walk elimination: the straight chord already exceeds the bound,
# so every path fails the existing length gate without walking.
LENGTH_INFEASIBLE_CHORD = "LENGTH_INFEASIBLE_CHORD"


def _d(p: Point, q: Point) -> float:
    return math.hypot(p[0] - q[0], p[1] - q[1])


def corridor_bound(footage_ft: float, scale_pts_per_ft: float,
                   jump_cap: float = MAX_DASH_GAP) -> Tuple[float, float]:
    """``(expected_len_pts, bound_pts)`` for a printed footage at the coherent
    ladder scale. ``bound = exp * (1 + DESIGN_LENGTH_REL_TOL) +
    2 * (jump_cap + TRIM_RADIUS)``. ``jump_cap`` MUST be the same cap passed
    to ``walk_design_path`` (the slack argument is stated in units of the
    walk's own jump cap; a larger walk cap with a smaller bound cap would be
    unsound). Refuses (raises) on a missing/non-positive scale or footage --
    no fallback scale exists in law math."""
    if footage_ft is None or footage_ft <= 0:
        raise ValueError(f"corridor_bound: footage must be positive, "
                         f"got {footage_ft!r}")
    if scale_pts_per_ft is None or scale_pts_per_ft <= 0:
        raise ValueError(f"corridor_bound: {SCALE_NOT_COHERENT} "
                         f"(scale={scale_pts_per_ft!r}); a fallback scale "
                         f"would be a guess")
    exp = footage_ft * scale_pts_per_ft
    return exp, exp * (1.0 + DESIGN_LENGTH_REL_TOL) + 2.0 * (jump_cap
                                                             + TRIM_RADIUS)


def chord_infeasible(start_xy: Point, end_xy: Point, bound: float) -> bool:
    """True when the straight chord alone exceeds the bound: every final
    path measures at least the chord (anchors are literal path endpoints),
    so the existing length gate can never pass -- typed pre-walk kill."""
    return _d(start_xy, end_xy) > bound


def prune_pieces(pieces: Sequence[Piece], start_xy: Point, end_xy: Point,
                 bound: float) -> List[Piece]:
    """The corridor: keep a piece iff at least one of its polyline VERTICES
    ``v`` satisfies ``d(start, v) + d(v, end) <= bound`` (vertex containment,
    not geometric ellipse intersection -- see module docstring). Input MUST
    be ``conduit_pieces`` output (post twin-merge, post weld): pruning raw
    drawings could delete a junction's third leg and silently weld across a
    real branch point. Pure; the input is never mutated; relative order is
    preserved (the walk's tie-breaks see a stable sub-sequence)."""
    return [p for p in pieces
            if min(_d(start_xy, v) + _d(v, end_xy) for v in p.points)
            <= bound]
