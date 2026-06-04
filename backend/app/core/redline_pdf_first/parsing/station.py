"""Station parsing & math. Pure, no I/O, no Brenham-specific constants.

Convention: ``A+BB`` = A*100 + BB feet (e.g. ``12+22`` -> 1222.0 ft).
"""
from __future__ import annotations

import re
from typing import Dict, Optional

_STA_RE = re.compile(r"^\s*(\d+)\s*\+\s*(\d+(?:\.\d+)?)\s*$")


def parse_station(value) -> Optional[float]:
    """``'12+22'`` -> ``1222.0`` ft. Returns None if unparseable."""
    if value is None:
        return None
    m = _STA_RE.match(str(value).strip())
    if not m:
        return None
    return int(m.group(1)) * 100.0 + float(m.group(2))


def station_to_feet(value) -> Optional[float]:
    return parse_station(value)


def feet_to_station(feet: float) -> str:
    """``1222`` -> ``'12+22'`` (inverse of :func:`parse_station`)."""
    feet = float(feet)
    sign = "-" if feet < 0 else ""
    feet = abs(feet)
    whole = int(feet // 100)
    rem = feet - whole * 100
    if abs(rem - round(rem)) < 1e-6:
        return f"{sign}{whole}+{int(round(rem)):02d}"
    return f"{sign}{whole}+{rem:05.2f}"


def station_delta(a, b) -> Optional[float]:
    """Signed feet from station ``a`` to ``b`` (b - a)."""
    fa, fb = parse_station(a), parse_station(b)
    if fa is None or fb is None:
        return None
    return round(fb - fa, 2)


def footage_check(authored_ft: float, field_ft: float) -> Dict[str, float]:
    """Compare an authored box footage to a field (bore-log) span."""
    a, f = float(authored_ft), float(field_ft)
    return {"authored": round(a, 2), "bore_log": round(f, 2), "delta": round(abs(a - f), 2)}


def within_tol(a: float, b: float, tol: float) -> bool:
    return abs(float(a) - float(b)) <= float(tol)
