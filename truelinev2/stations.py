"""Station notation math. Pure, no I/O. ``A+BB`` == A*100 + BB feet."""
from __future__ import annotations

import re
from typing import Optional

_STA_RE = re.compile(r"^\s*(\d+)\s*\+\s*(\d+(?:\.\d+)?)\s*$")

# An optional leading station LABEL only: ``STA`` / ``STA.`` / ``STA:`` followed by
# whitespace and a digit. Used by ingest readers to normalize a label some sources
# (e.g. PDF digital-fill forms) keep in the station cell. Deliberately narrow: it
# strips ONLY this exact label and ONLY when a station number follows -- it performs
# no fuzzy OCR correction and leaves bare stations and non-station text untouched.
_STA_LABEL_RE = re.compile(r"^\s*STA[.:]?\s+(?=\d)", re.IGNORECASE)


def strip_station_label(value) -> str:
    """``'STA 3+50'`` / ``'STA. 3+50'`` / ``'STA: 3+50'`` -> ``'3+50'``; everything
    else (bare ``'3+50'``, ``'nope'``, ``'STATION 3+50'``) returned unchanged.
    Pure string normalization for the ingest seam; does not itself parse."""
    s = "" if value is None else str(value)
    return _STA_LABEL_RE.sub("", s, count=1)


def parse_station(value) -> Optional[float]:
    """``'12+22'`` -> ``1222.0``; None if unparseable."""
    if value is None:
        return None
    m = _STA_RE.match(str(value).strip())
    if not m:
        return None
    return int(m.group(1)) * 100.0 + float(m.group(2))


def feet_to_station(feet: float) -> str:
    feet = float(feet)
    sign = "-" if feet < 0 else ""
    feet = abs(feet)
    whole = int(feet // 100)
    rem = feet - whole * 100
    if abs(rem - round(rem)) < 1e-6:
        return f"{sign}{whole}+{int(round(rem)):02d}"
    return f"{sign}{whole}+{rem:05.2f}"
