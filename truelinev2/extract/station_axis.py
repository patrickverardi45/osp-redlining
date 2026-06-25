"""Station axis: fit ``station_ft = a*x + b`` from a sheet's station-tick labels.

Theil-Sen estimator (median of pairwise slopes) — robust to stray non-tick
numbers without tuning a residual threshold. Pure Python (no numpy). Reusable
infrastructure for any positional plan dialect, not ODOT-specific.
"""
from __future__ import annotations

import re
from typing import List, Optional, Sequence, Tuple

_TICK = re.compile(r"^\d{1,3}\+\d{2}$")


def parse_tick(text: str) -> Optional[int]:
    """A bare station tick ``'14+00'`` -> 1400 ft; None if not a tick token."""
    s = (text or "").strip()
    if not _TICK.match(s):
        return None
    a, b = s.split("+")
    return int(a) * 100 + int(b)


def _median(xs: Sequence[float]) -> Optional[float]:
    xs = sorted(xs)
    n = len(xs)
    if n == 0:
        return None
    m = n // 2
    return xs[m] if n % 2 else (xs[m - 1] + xs[m]) / 2.0


class StationAxis:
    def __init__(self, a: float, b: float, n: int, residual_ft: float):
        self.a = a
        self.b = b
        self.n = n
        self.residual_ft = residual_ft

    def station_at(self, x: float) -> float:
        return self.a * x + self.b

    def x_at(self, station_ft: float) -> Optional[float]:
        """Inverse of ``station_at``: the display-space x for a station (ft), or None if degenerate.
        Lets a caller clip a drawn run to a bore-log station span."""
        if not self.a:
            return None
        return (float(station_ft) - self.b) / self.a


def fit_axis(points: List[Tuple[float, float]]) -> Optional[StationAxis]:
    """points: (x, station_ft). Theil-Sen fit; None if < 2 distinct x."""
    pts = [(float(x), float(s)) for x, s in points if x is not None and s is not None]
    if len({p[0] for p in pts}) < 2:
        return None
    slopes: List[float] = []
    for i in range(len(pts)):
        for j in range(i + 1, len(pts)):
            if pts[j][0] != pts[i][0]:
                slopes.append((pts[j][1] - pts[i][1]) / (pts[j][0] - pts[i][0]))
    a = _median(slopes)
    if a is None or a == 0:
        return None
    b = _median([s - a * x for x, s in pts])
    resid = sum(abs(a * x + b - s) for x, s in pts) / len(pts)
    return StationAxis(a, b, len(pts), round(resid, 2))
