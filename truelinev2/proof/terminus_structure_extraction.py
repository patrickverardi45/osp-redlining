"""M8.3b -- PURE terminus/access-structure extraction from callout text (proof helpers).

The Fable synthesis finding: the DIR. BORE callout's textual TAIL (the lines after
the footage inside the callout box, and the words around it) names what the run
terminates at -- TERMINAL PORT HH AP-163, FLOWER POT, FIBER DROP, SPLICE LOC 46,
INSTALLER HH -- and v2 currently ignores everything after the footage.

These helpers classify that text into generic structure classes. PURE: no PDF, no
engine imports, no placement logic, no convention/customer names. Classification is
EVIDENCE extraction only -- nothing here picks a route or changes a disposition.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Sequence

# Generic plan-annotation vocabulary -> structure classes. Order matters only for
# reporting; classes are a SET (a tail can name several: TERMINAL + HH + AP).
_AP_RE = re.compile(r"\bAP[-\s]?0*(\d{1,4})\b", re.I)
_SPLICE_LOC_RE = re.compile(r"\bSPLICE\s+LOC\.?\s*0*(\d{1,4})\b", re.I)

# (class, regex) -- word-boundary, case-insensitive, multi-word aware.
_CLASS_PATTERNS = (
    ("handhole", re.compile(r"\b(HANDHOLE|HAND\s+HOLE|HH)\b", re.I)),
    ("installer_handhole", re.compile(r"\bINSTALLER\s+HH\b|\bINSTALLER\s+HANDHOLE\b", re.I)),
    ("flower_pot", re.compile(r"\bFLOWER\s*POT\b", re.I)),
    ("access_point", re.compile(r"\bAP[-\s]?\d{1,4}\b|\bACCESS\s+POINT\b", re.I)),
    ("terminal", re.compile(r"\bTERMINAL\b", re.I)),
    ("splice", re.compile(r"\bSPLICE\b", re.I)),
    ("drop_context", re.compile(r"\b(FIBER|HOUSE)\s+DROP\b|\bFOR\s+(FIBER\s+)?DROP\b|\bDROP\b", re.I)),
    ("vacant_context", re.compile(r"\bVACANT\b", re.I)),
    ("pedestal", re.compile(r"\bPED(ESTAL)?\b", re.I)),
    ("vault", re.compile(r"\bVAULT\b", re.I)),
)

# Tokens that are dig/annotation noise, never structures (kept for honesty in tests).
NON_STRUCTURE_NOISE = ("POTHOLE", "DEPTH", "MIN", "ROW", "D/W", "HDPE", "CABLE", "CT")


@dataclass
class TerminusEvidence:
    """Structure evidence extracted from one callout's textual tail/context."""
    classes: List[str] = field(default_factory=list)   # generic structure classes found
    ap_ids: List[str] = field(default_factory=list)     # numeric AP identities (e.g. '164')
    splice_locs: List[str] = field(default_factory=list)
    hits: List[str] = field(default_factory=list)       # the literal matched snippets
    source: str = ""                                    # 'tail_lines' | 'nearby_words' | 'both'

    @property
    def has_structure(self) -> bool:
        return bool(self.classes)

    @property
    def has_identity(self) -> bool:
        """True iff a NAMED identity was found (the PROVEN/BLOCKED discriminator):
        an AP number or a splice-loc number. A bare class (e.g. flower_pot) is a
        terminus TYPE, not an identity."""
        return bool(self.ap_ids or self.splice_locs)

    def to_dict(self) -> dict:
        return {"classes": self.classes, "ap_ids": self.ap_ids,
                "splice_locs": self.splice_locs, "hits": self.hits,
                "has_identity": self.has_identity, "source": self.source}


def classify_structure_text(text: str, *, source: str = "") -> TerminusEvidence:
    """Classify a text blob (a callout tail / nearby-word join) into structure
    classes + named identities. Pure and deterministic."""
    blob = " ".join((text or "").split())
    ev = TerminusEvidence(source=source)
    for klass, rx in _CLASS_PATTERNS:
        m = rx.search(blob)
        if m:
            ev.classes.append(klass)
            ev.hits.append(m.group(0).strip())
    ev.ap_ids = sorted({m.group(1) for m in _AP_RE.finditer(blob)})
    ev.splice_locs = sorted({m.group(1) for m in _SPLICE_LOC_RE.finditer(blob)})
    return ev


def merge_evidence(a: TerminusEvidence, b: TerminusEvidence) -> TerminusEvidence:
    """Union of two evidence sources (tail lines + nearby words)."""
    out = TerminusEvidence(source="both" if (a.source and b.source and a.source != b.source)
                           else (a.source or b.source))
    out.classes = sorted(set(a.classes) | set(b.classes))
    out.ap_ids = sorted(set(a.ap_ids) | set(b.ap_ids))
    out.splice_locs = sorted(set(a.splice_locs) | set(b.splice_locs))
    out.hits = sorted(set(a.hits) | set(b.hits))
    return out


_STA_LINE_RE = re.compile(r"STA\s+\d+\+\d+(?:\.\d+)?\s+TO\s+STA\s+\d+\+\d+", re.I)


def callout_tail_lines(page_lines: Sequence[str], from_sta: str, to_sta: str,
                       max_lines: int = 4) -> List[str]:
    """The textual TAIL of one callout box: the lines following its ``STA a TO STA
    b`` line, up to the next STA line or ``max_lines``. Pure over a page's lines."""
    needle = re.compile(rf"STA\s+{re.escape(from_sta)}\s+TO\s+STA\s+{re.escape(to_sta)}\b", re.I)
    out: List[str] = []
    grab = 0
    for i, ln in enumerate(page_lines):
        if needle.search(ln):
            for nxt in page_lines[i + 1: i + 1 + max_lines]:
                if _STA_LINE_RE.search(nxt):
                    break
                out.append(nxt.strip())
            grab += 1
    return out


def extract_from_tail(page_lines: Sequence[str], from_sta: str, to_sta: str,
                      max_lines: int = 4) -> TerminusEvidence:
    tail = " ".join(callout_tail_lines(page_lines, from_sta, to_sta, max_lines))
    return classify_structure_text(tail, source="tail_lines")
