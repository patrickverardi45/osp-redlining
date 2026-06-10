"""M8.3a -- PURE helpers for the run-identity tiebreaker proof (coequal ties).

What the log48 probe established (and these helpers formalize):

  * A coequal tie often contains NEAR-DUPLICATE candidates -- the same physical
    boxes read twice with small station spreads (1+90 vs 1+91, 3+50 vs 3+55 --
    the log57 extraction-precision class). Collapsing candidates whose every box
    matches a counterpart within the precision band yields the set of PHYSICALLY
    DISTINCT routes. This collapse is deterministic and evidence-based.
  * Identity PROFILES (conduit thread, corridor/street tokens, end-structure
    labels, hop classifications) describe each surviving route for a human or a
    future rule. Profiles are EVIDENCE, not a scoring knob: this module never
    picks a "best-looking" route.

The ONLY auto-resolution these helpers permit is: after near-duplicate collapse,
EXACTLY ONE physical route remains. >=2 survivors -> not ready (human pick-card /
geo lane); zero identity evidence -> missing-evidence. No tolerance is widened;
no candidate is dropped for being "worse"; decide() is not touched.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

# The banked extraction-precision band (M8.2h / collision gate): two station
# readings within this many feet are one physical value read twice.
PRECISION_BAND_FT = 10.0

# Generic street-suffix tokens (English plan-annotation suffixes; convention-free).
STREET_SUFFIXES = ("ST", "LN", "WAY", "AVE", "DR", "RD", "CT", "PKWY", "BLVD", "HWY", "CIR")
# Generic access/structure tokens (same family the M8.2h pass used).
STRUCTURE_TOKENS = ("HH", "HANDHOLE", "FLOWER", "POT", "VAULT", "PEDESTAL",
                    "SPLICE", "TERMINAL", "DROP", "AP-")

VERDICT_READY = "TIEBREAKER_PROOF_READY_FOR_OPT_IN"
VERDICT_NOT_READY = "TIEBREAKER_NOT_READY"
VERDICT_MISSING = "MISSING_IDENTITY_EVIDENCE"


@dataclass(frozen=True)
class BoxRead:
    """One callout reading inside a candidate chain (pure data for the helpers)."""
    sheet: int
    from_ft: float
    to_ft: float
    conduit: Optional[str] = None
    vacant: bool = False
    text: str = ""


@dataclass
class RouteProfile:
    """The identity evidence for ONE physically-distinct candidate route."""
    signature: Tuple[Tuple[int, int, int], ...]
    readings: int = 1                      # how many raw candidates collapsed into it
    boxes: List[BoxRead] = field(default_factory=list)
    conduit_thread: List[str] = field(default_factory=list)
    conduit_uniform_type: bool = True      # same conduit size/type family end-to-end
    corridors: List[str] = field(default_factory=list)
    end_structures: List[str] = field(default_factory=list)
    hop_classes: List[str] = field(default_factory=list)
    deltas: Optional[Tuple[float, float, float]] = None  # start/end/foot (report-only)


def _boxes_match(a: BoxRead, b: BoxRead, band: float = PRECISION_BAND_FT) -> bool:
    """Two readings of the SAME physical box: same sheet, endpoints within the band."""
    return (a.sheet == b.sheet
            and abs(a.from_ft - b.from_ft) <= band
            and abs(a.to_ft - b.to_ft) <= band)


def chains_equivalent(a: Sequence[BoxRead], b: Sequence[BoxRead],
                      band: float = PRECISION_BAND_FT) -> bool:
    """Two candidate chains are the same PHYSICAL route iff they have the same
    length and every positional box pair is a near-duplicate reading."""
    if len(a) != len(b):
        return False
    return all(_boxes_match(x, y, band) for x, y in zip(a, b))


def collapse_near_duplicates(chains: Sequence[Sequence[BoxRead]],
                             band: float = PRECISION_BAND_FT) -> List[List[int]]:
    """Group candidate indices into physically-distinct routes (single-link over
    ``chains_equivalent``). Deterministic; order-independent membership."""
    groups: List[List[int]] = []
    for i, ch in enumerate(chains):
        placed = False
        for g in groups:
            if chains_equivalent(chains[g[0]], ch, band):
                g.append(i)
                placed = True
                break
        if not placed:
            groups.append([i])
    return groups


def _signature(chain: Sequence[BoxRead], band: float = PRECISION_BAND_FT
               ) -> Tuple[Tuple[int, int, int], ...]:
    return tuple((b.sheet, int(round(b.from_ft / band)), int(round(b.to_ft / band)))
                 for b in chain)


def _conduit_type(conduit: Optional[str]) -> str:
    """The conduit's size/type family with VACANT-ness stripped: '1-1.25\" VACANT
    HDPE' and '1-1.25\" HDPE' are the same physical conduit family (an occupied
    vs vacant section of one run is not an identity break)."""
    return " ".join(w for w in (conduit or "").upper().split() if w != "VACANT")


def conduit_uniform(chain: Sequence[BoxRead]) -> bool:
    types = {_conduit_type(b.conduit) for b in chain if (b.conduit or "").strip()}
    return len(types) <= 1


def street_tokens(words: Sequence[str]) -> List[str]:
    """Corridor names from a nearby-word list: a street suffix plus up to two
    preceding alphabetic words (e.g. ['E','TOM','GREEN','ST'] -> 'TOM GREEN ST')."""
    out: List[str] = []
    up = [str(w).upper().strip(".,") for w in words]
    for i, w in enumerate(up):
        if w in STREET_SUFFIXES:
            name = [t for t in up[max(0, i - 2):i] if t.isalpha() and len(t) > 1]
            if name:
                out.append(" ".join(name + [w]))
    return sorted(set(out))


def structure_tokens(words: Sequence[str]) -> List[str]:
    up = {str(w).upper().strip(".,") for w in words}
    found = [t for t in STRUCTURE_TOKENS if any(u.startswith(t) for u in up)]
    # FLOWER + POT collapse into one label when both present
    if "FLOWER" in found and "POT" in found:
        found = [t for t in found if t not in ("FLOWER", "POT")] + ["FLOWER POT"]
    return sorted(set(found))


def decide_tiebreak(profiles: Sequence[RouteProfile]) -> Dict[str, Any]:
    """The ONLY auto-resolution rule this proof validates: exactly one physical
    route after near-duplicate collapse. >=2 survivors are NEVER auto-picked --
    identity profiles route them to a human pick-card (or the geo lane). The
    recovery, when ready, is REVIEW-gated: a tie resolved by a new rule is never
    AUTO regardless of deltas."""
    if not profiles:
        return {"verdict": VERDICT_MISSING, "survivor": None,
                "recovery": None,
                "reason": "no candidate routes with identity evidence"}
    if len(profiles) == 1:
        return {"verdict": VERDICT_READY, "survivor": 0,
                "recovery": "REVIEW",
                "reason": ("all coequal candidates are near-duplicate readings of ONE "
                           "physical route; the tie is extraction precision, not real "
                           "ambiguity (REVIEW-gated; never AUTO via a new rule)")}
    distinct_corridors = len({tuple(p.corridors) for p in profiles}) > 1
    return {"verdict": VERDICT_NOT_READY, "survivor": None,
            "recovery": "HUMAN_PICK_CARD" if distinct_corridors else "MORE_EVIDENCE",
            "reason": (f"{len(profiles)} physically-distinct routes survive collapse; "
                       + ("corridor identities differ -- the missing relationship is the "
                          "bore<->corridor binding (not in the bore log); a human pick-card "
                          "or geo/structure anchor is required"
                          if distinct_corridors else
                          "identity profiles do not separate them; more evidence needed"))}
