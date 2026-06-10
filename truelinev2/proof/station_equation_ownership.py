r"""M8.6 -- station-equation OWNERSHIP / frame-origin binding (pure proof helpers).

Doctrine (Patrick, 2026-06-10): ``STA 2+72=0+00`` means ONE physical point carries
TWO station identities -- parent/plan station 2+72 (272 ft) AND local-frame origin
0+00. Two annotations ``STA 2+72=0+00`` and ``STA 2+22=0+00`` are TWO different
physical structures/origins, never the same zero: ``0+00`` is a local origin marker
and is NOT globally unique. A nearby ``HH - HH = 50'`` note corroborates the pair
(272 - 222 = 50), and a bore interval ``2+22 TO 2+72`` (50 ft) is the matching
footage math. An endpoint may also be the startpoint of another segment: shared
stations/structures can be INTERIOR run boundaries, not final termini.

These helpers model that ownership: one ``StructureOrigin`` PER reset equation,
identity keyed by (sheet, parent station) -- never by the 0+00 side -- with the
nearby structure label bound by text adjacency (the terminus tail-lines pattern)
and HH-HH distance notes as corroborating evidence. No placement decision, no
engine wiring, no tolerance: corroboration deltas are reported exactly, with the
existing chains link tolerance (2.0 ft) cited only as a descriptive band.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from truelinev2.stations import feet_to_station, parse_station

# A reset annotation: parent station = local 0+00 (either side may be written first).
_STA = r"\d+\+\d+(?:\.\d+)?"
_RESET_FWD = re.compile(rf"(?:STA\s*)?({_STA})\s*=\s*0?0\+00\b", re.I)
_RESET_REV = re.compile(rf"(?:STA\s*)?0?0\+00\s*=\s*({_STA})", re.I)
# An HH-to-HH structure-distance note, e.g. ``HH - HH = 50'``.
_HH_DIST = re.compile(r"HH\s*-\s*HH\s*=\s*(\d+(?:\.\d+)?)\s*'", re.I)
# Structure labels, specific -> generic (first match wins). Proof-local grammar;
# no monolith import.
_STRUCTURE_PATTERNS: Tuple[Tuple[str, re.Pattern], ...] = (
    ("installer_hh", re.compile(r"INSTALLER\s+HH", re.I)),
    ("flower_pot", re.compile(r"FLOWER\s*POT", re.I)),
    ("terminal_port_hh", re.compile(r"(?:TERMINAL\s+)?\d*\s*PORT\s+HH|TERMINAL\s+PORT", re.I)),
    ("splice", re.compile(r"SPLICE", re.I)),
    ("handhole", re.compile(r"\bHH\b", re.I)),
)
_SIZE = re.compile(r"\d+\"X\d+\"X\d+\"", re.I)
# How many following text lines to scan for the structure label (stop at the next
# STA line) -- the M8.3b callout_tail_lines adjacency pattern.
_ADJACENT_LINES = 3
_STA_LINE = re.compile(rf"(?:STA\s*){_STA}", re.I)


@dataclass(frozen=True)
class StructureOrigin:
    """ONE reset annotation = one physical structure point with TWO identities:
    the parent/plan station and the local-frame origin 0+00. ``origin_id`` is
    keyed by (sheet, parent station) -- NEVER by the 0+00 side."""
    sheet: int
    parent_station_raw: str
    parent_station_ft: float
    local_origin_ft: float = 0.0
    structure_type: Optional[str] = None
    structure_label: Optional[str] = None   # raw adjacent label text (size + type)
    source_line: str = ""

    @property
    def origin_id(self) -> str:
        return f"sheet:{self.sheet}/reset@{self.parent_station_raw}"

    def to_dict(self) -> dict:
        return {"origin_id": self.origin_id, "sheet": self.sheet,
                "parent_station": self.parent_station_raw,
                "parent_station_ft": self.parent_station_ft,
                "local_origin_ft": self.local_origin_ft,
                "structure_type": self.structure_type,
                "structure_label": self.structure_label,
                "source_line": self.source_line}


def _structure_from_lines(lines: Sequence[str]) -> Tuple[Optional[str], Optional[str]]:
    """(structure_type, raw label) from the adjacent lines following a reset
    annotation: scan up to _ADJACENT_LINES, stopping at the next STA line."""
    label_parts: List[str] = []
    stype: Optional[str] = None
    for ln in lines[:_ADJACENT_LINES]:
        if _STA_LINE.search(ln):
            break
        if _SIZE.search(ln):
            label_parts.append(ln.strip())
            continue
        for name, pat in _STRUCTURE_PATTERNS:
            if pat.search(ln):
                stype = stype or name
                label_parts.append(ln.strip())
                break
    return stype, (" ".join(label_parts) or None)


def extract_reset_origins(lines: Sequence[str], sheet: int) -> List[StructureOrigin]:
    """One StructureOrigin PER reset annotation on this sheet's text lines.
    Distinct parent stations are distinct origins BY CONSTRUCTION; duplicates of
    the same (sheet, parent) collapse to one (the same physical annotation read
    twice), but two origins NEVER collapse on the shared ``0+00`` side."""
    seen: Dict[str, StructureOrigin] = {}
    for i, ln in enumerate(lines):
        for m in list(_RESET_FWD.finditer(ln)) + list(_RESET_REV.finditer(ln)):
            raw = m.group(1)
            ft = parse_station(raw)
            if ft is None or ft == 0.0:
                continue  # a literal 0+00 parent is not an origin annotation
            stype, label = _structure_from_lines(lines[i + 1:])
            o = StructureOrigin(sheet=sheet, parent_station_raw=raw,
                                parent_station_ft=ft, structure_type=stype,
                                structure_label=label, source_line=ln.strip())
            seen.setdefault(o.origin_id, o)
    return list(seen.values())


def parse_hh_distances(text: str) -> List[float]:
    """Every ``HH - HH = N'`` structure-distance note in the text (feet)."""
    return [float(x) for x in _HH_DIST.findall(text or "")]


def corroborate_pairs(origins: Sequence[StructureOrigin],
                      hh_notes: Sequence[float]) -> List[dict]:
    """For every same-sheet origin pair: the parent-station delta (pure footage
    math, ``A+B == A*100+B``) and whether an HH-HH note matches it EXACTLY.
    Evidence only -- no tolerance is consulted to 'accept' anything."""
    out: List[dict] = []
    by_sheet: Dict[int, List[StructureOrigin]] = {}
    for o in origins:
        by_sheet.setdefault(o.sheet, []).append(o)
    for sheet, group in sorted(by_sheet.items()):
        group = sorted(group, key=lambda o: o.parent_station_ft)
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                delta = round(b.parent_station_ft - a.parent_station_ft, 2)
                out.append({
                    "sheet": sheet,
                    "pair": (a.origin_id, b.origin_id),
                    "parent_delta_ft": delta,
                    "hh_note_exact_match": delta in hh_notes,
                })
    return out


def prove_no_collapse(origins: Sequence[StructureOrigin]) -> dict:
    """The M8.6 core assertion: every reset annotation is its OWN origin. Distinct
    parent stations -> distinct origin_ids -> distinct physical structures; the
    shared local ``0+00`` side never merges them."""
    ids = [o.origin_id for o in origins]
    parents = [(o.sheet, o.parent_station_ft) for o in origins]
    return {
        "origin_count": len(origins),
        "distinct_origin_ids": len(set(ids)),
        "distinct_parent_points": len(set(parents)),
        "all_local_origins_are_zero": all(o.local_origin_ft == 0.0 for o in origins),
        "no_collapse": len(set(ids)) == len(origins) == len(set(parents)),
    }


def bore_interval_footage(start_sta: str, end_sta: str) -> Optional[float]:
    """``2+22 TO 2+72`` -> 50.0 ft (the station-notation footage math)."""
    a, b = parse_station(start_sta), parse_station(end_sta)
    if a is None or b is None:
        return None
    return round(b - a, 2)


def origins_bounding_interval(origins: Sequence[StructureOrigin], start_ft: float,
                              end_ft: float) -> List[Tuple[StructureOrigin, StructureOrigin]]:
    """Same-sheet origin pairs whose parent stations EXACTLY bound a bore interval
    (start at one structure, end at the other) -- the screenshot pattern: bore
    ``2+22 TO 2+72`` bounded by the two installer-HH origins. A bounding origin is
    evidence the endpoint is a structure boundary (possibly INTERIOR to a larger
    run), not proof of a final terminus."""
    out = []
    by_sheet: Dict[int, List[StructureOrigin]] = {}
    for o in origins:
        by_sheet.setdefault(o.sheet, []).append(o)
    for group in by_sheet.values():
        starts = [o for o in group if o.parent_station_ft == start_ft]
        ends = [o for o in group if o.parent_station_ft == end_ft]
        out.extend((s, e) for s in starts for e in ends)
    return out
