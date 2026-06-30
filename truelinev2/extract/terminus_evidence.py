"""Source-backed per-bore TERMINUS EVIDENCE model (G1 schema — observer-only, no placement impact).

A bore has a START and an END. To eventually promote a cold-package placement from REVIEW toward AUTO, each
endpoint must be bound to SOURCE evidence (printed structure label / printed station callout / bilateral
matchline equation / a reviewed bore-log row), NEVER inferred from geometry. This module is the read-only
DATA model the terminus extractor (G2) emits; it changes no engine state and is not wired into placement.

Honesty rules baked into the model:
  * ``source_bound`` is True ONLY when a printed/source endpoint PROOF was found. A station value that is known
    only from the uploaded bore-log file (provenance BORE_LOG_ROW_PARSED) is NOT source-bound for AUTO — it
    carries a named ``blocker`` saying which printed proof is missing.
  * an endpoint inferred from the drawn run geometry is INFERRED_FROM_GEOMETRY, never presented as printed.
  * ``station_ft`` is always read from source (bore-log row or printed text), never computed from geometry.

Name-free: no customer/project/location/operator literal lives here.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Optional

# --- terminus source types (where an endpoint's proof comes from) ----------------------------------------- #
PRINTED_STRUCTURE_LABEL = "PRINTED_STRUCTURE_LABEL"      # printed "STA <n> <structure>" note at the endpoint
PRINTED_STA_CALLOUT = "PRINTED_STA_CALLOUT"             # printed run callout bracketing the bore span
MATCHLINE_BOUNDARY_STATION = "MATCHLINE_BOUNDARY_STATION"  # bilateral printed matchline boundary equation
BORE_LOG_ROW = "BORE_LOG_ROW"                          # station value from the uploaded bore-log row only
KMZ_ROUTE_VERTEX = "KMZ_ROUTE_VERTEX"                  # GIS route endpoint (future; requires calibration)
INFERRED_FROM_GEOMETRY = "INFERRED_FROM_GEOMETRY"      # drawn-run endpoint inference (never source-bound)
ABSENT = "ABSENT"                                     # no terminus value at all

SOURCE_TYPES = (PRINTED_STRUCTURE_LABEL, PRINTED_STA_CALLOUT, MATCHLINE_BOUNDARY_STATION,
                BORE_LOG_ROW, KMZ_ROUTE_VERTEX, INFERRED_FROM_GEOMETRY, ABSENT)

# Source types that constitute an INDEPENDENT printed/source endpoint proof (the AUTO-eligible set, gated
# later in G4). BORE_LOG_ROW is deliberately NOT here: the log gives the value, not per-bore printed identity.
SOURCE_BOUND_TYPES = (PRINTED_STRUCTURE_LABEL, PRINTED_STA_CALLOUT, MATCHLINE_BOUNDARY_STATION)

# --- provenance (audit trail of where the value was read) ------------------------------------------------- #
PRINTED_PLAN_TEXT = "PRINTED_PLAN_TEXT"
BORE_LOG_ROW_PARSED = "BORE_LOG_ROW_PARSED"
KMZ_GEOMETRY = "KMZ_GEOMETRY"
GENERIC_INFERRED = "GENERIC_INFERRED"

# --- terminus missing-evidence blockers (named; same convention as the generic-lane codes) ---------------- #
NO_PRINTED_START_STRUCTURE = "NO_PRINTED_START_STRUCTURE"
NO_PRINTED_END_STRUCTURE = "NO_PRINTED_END_STRUCTURE"
AMBIGUOUS_START_STRUCTURE = "AMBIGUOUS_START_STRUCTURE"
AMBIGUOUS_END_STRUCTURE = "AMBIGUOUS_END_STRUCTURE"
NO_BORE_LOG_STATION = "NO_BORE_LOG_STATION"
# Two PRINTED source readings disagree about an endpoint (e.g. a printed structure note binds the endpoint
# while a printed span callout brackets the bore to a DIFFERENT station). Never silently preferred / chosen.
CONFLICTING_START_TERMINUS = "CONFLICTING_START_TERMINUS"
CONFLICTING_END_TERMINUS = "CONFLICTING_END_TERMINUS"


@dataclass(frozen=True)
class TerminusEvidence:
    """Evidence for ONE bore endpoint. Read-only; emitted by the extractor, consumed by tests/reports."""
    which: str                          # "START" | "END"
    source_type: str                    # one of SOURCE_TYPES
    source_bound: bool                  # True iff a printed/source endpoint proof was found (never inferred)
    station_ft: Optional[float] = None  # source-read station (bore-log row or printed text), never geometry
    station_str: Optional[str] = None   # human station label, e.g. "13+25"
    sheet: Optional[int] = None         # construction sheet the endpoint sits on (from bore.sheet_refs)
    pdf_page: Optional[int] = None       # resolved PDF page (optional; sheet-label resolver)
    source_text: Optional[str] = None   # verbatim printed note line, if any
    structure_label: Optional[str] = None  # the printed structure keyword(s), if any
    provenance: str = GENERIC_INFERRED  # one of the provenance constants
    confidence: Optional[float] = None  # None unless a printed proof was bound
    blocker: Optional[str] = None       # named missing-evidence code when not source-bound
    pedigree: str = ""                  # human-readable evidence trail

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class BoreTerminusEvidence:
    """Both endpoints of one bore."""
    bore_label: Optional[str]           # opaque runtime label (never a hardcoded identity default)
    start: TerminusEvidence
    end: TerminusEvidence

    @property
    def both_source_bound(self) -> bool:
        return self.start.source_bound and self.end.source_bound

    @property
    def missing_blockers(self) -> tuple:
        return tuple(b for b in (self.start.blocker, self.end.blocker) if b)

    def as_dict(self) -> dict:
        return {"bore_label": self.bore_label,
                "start": self.start.as_dict(), "end": self.end.as_dict(),
                "both_source_bound": self.both_source_bound,
                "missing_blockers": list(self.missing_blockers)}
