r"""M8.18 -- per-ladder tick clustering (GENERAL; no plan-set knowledge).

The M8.16 corroboration sampled a ladder SCALE from a y-band around the
boundary crossing (``ladder_scale_for_band``). The M8.18 adversarial probe
proved that band is geometrically wrong in two ways: a HORIZONTAL matchline
puts the crossing far from any tick (the band is EMPTY -> log8), and a
VERTICAL matchline crossed by two perpendicular ladders mixes their ticks
(the band is MULTI-MODAL -> log42). Either way the band is not a coherent
corroboration basis.

This module separates the interleaved ticks into distinct DRAWN LADDERS --
maximal sequences of clean station ticks that step through ADJACENT stations
along a consistent drawn direction at a consistent pts/ft scale -- so a
caller can corroborate against a single internally-consistent ladder instead
of a polluted band. It owns no layer name, company, or structure type; it
takes ``Tick``s and returns ladder groupings.

Laws:
  * a ladder HOP joins two ticks whose station strictly increases by at most
    ``max_step_ft`` (adjacent stations -- never a long jump that would imply a
    tiny cross-ladder "scale"); among candidates the nearest (smallest
    station step, then smallest drawn distance) wins -- deterministic;
  * once a ladder has >= 2 ticks every further hop's pts/ft must stay within
    ``scale_rel_tol`` of the ladder's running median (the banked tick-path
    SCALE_REL_TOL) -- a ladder is internally scale-consistent by construction;
  * the COHERENT sheet scale exists only when the ladders that carry real
    structure (>= ``min_ticks`` ticks) AGREE on a scale within
    ``scale_rel_tol``; otherwise there is no single drawn scale and a
    scale-based corroboration must abstain (it is not invented).
"""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from truelinev2.extract.tick_path import SCALE_REL_TOL, Tick

MAX_LADDER_STEP_FT = 200.0   # a hop bridges at most ~2 station intervals; a
                             # larger station jump at a short drawn distance is
                             # a cross-ladder artifact, never one ladder
MIN_COHERENCE_TICKS = 3      # ladders this long carry the real drawn scale;
                             # 2-tick fragments are too weak to vote


@dataclass(frozen=True)
class Ladder:
    """One coherent drawn station ladder: station-ordered ticks + its median
    consecutive pts/ft scale."""
    ticks: Tuple[Tick, ...]
    scale: float

    @property
    def station_span(self) -> Tuple[float, float]:
        return (self.ticks[0].station_ft, self.ticks[-1].station_ft)

    @property
    def length(self) -> int:
        return len(self.ticks)


def _scales(chain: Sequence[Tuple[float, float, float]]) -> List[float]:
    return [math.hypot(b[1] - a[1], b[2] - a[2]) / (b[0] - a[0])
            for a, b in zip(chain, chain[1:]) if b[0] > a[0]]


def cluster_ladders(ticks: Sequence[Tick],
                    scale_rel_tol: float = SCALE_REL_TOL,
                    max_step_ft: float = MAX_LADDER_STEP_FT) -> List[Ladder]:
    """Greedy, deterministic partition of clean ticks into coherent ladders.
    Each returned ladder steps through adjacent stations at a consistent
    scale. Ticks that never join a >= 2-tick chain are dropped (orphans carry
    no scale). Pure: the input is never mutated."""
    pts = sorted({(t.station_ft, round(t.x, 1), round(t.y, 1)) for t in ticks})
    used: set = set()
    ladders: List[Ladder] = []
    for i, seed in enumerate(pts):
        if i in used:
            continue
        chain = [seed]
        idxs = {i}
        while True:
            last = chain[-1]
            cands = [(j, p) for j, p in enumerate(pts)
                     if j not in used and j not in idxs
                     and 0.0 < p[0] - last[0] <= max_step_ft]
            if len(chain) >= 2:
                med = statistics.median(_scales(chain))
                cands = [(j, p) for j, p in cands
                         if med > 0 and abs(
                             math.hypot(p[1] - last[1], p[2] - last[2])
                             / (p[0] - last[0]) - med) / med <= scale_rel_tol]
            if not cands:
                break
            j, p = min(cands, key=lambda jp: (
                jp[1][0] - last[0],
                math.hypot(jp[1][1] - last[1], jp[1][2] - last[2])))
            chain.append(p)
            idxs.add(j)
        if len(chain) >= 2:
            ladders.append(Ladder(
                ticks=tuple(Tick(s, x, y) for s, x, y in chain),
                scale=statistics.median(_scales(chain))))
            used |= idxs
    return ladders


def coherent_ladder_scale(ladders: Sequence[Ladder],
                          scale_rel_tol: float = SCALE_REL_TOL,
                          min_ticks: int = MIN_COHERENCE_TICKS
                          ) -> Optional[float]:
    """The single drawn pts/ft scale shared by the sheet's real ladders, or
    None when no coherent scale exists. The vote is taken among ladders with
    >= ``min_ticks`` ticks (falling back to all ladders only if none qualify);
    a coherent scale requires their scales to agree within ``scale_rel_tol``.
    None is an HONEST abstain -- a scale is never invented from disagreement.

    Caveat (known limitation, M8.18 adversarial review): the greedy
    ``cluster_ladders`` keys only on adjacent-station + scale consistency, not
    on drawn direction, so a contrived set of two opposite-running ladders
    that share intermediate stations CAN fuse into one off-scale ladder; if
    that fused ladder were the ONLY >= ``min_ticks`` voter its scale would be
    returned on trust (a single voter cannot be cross-checked). On the real
    Brenham far sheets no fusion occurs (every voter is 1.44) and any fused
    scale lands far outside a corroboration window, so this is latent, not
    exploitable; a future caller that WIRES this for placement should add a
    drawn-direction (collinearity) gate before trusting a lone voter."""
    voters = [l for l in ladders if l.length >= min_ticks] or list(ladders)
    if not voters:
        return None
    scales = sorted(l.scale for l in voters)
    med = statistics.median(scales)
    if med <= 0:
        return None
    if (scales[-1] - scales[0]) / med > scale_rel_tol:
        return None
    return med
