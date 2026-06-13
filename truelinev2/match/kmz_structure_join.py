r"""M9.1 -- KMZ_AP_STRUCTURE_JOIN: the shipped cross-source terminal-join law.

Promotes the M9.0 audited primitive from proof into convention-agnostic engine
code. The law binds a PDF terminus callout to a KMZ structure ONLY when TWO
independent printed ids agree -- the AP id AND the splice-loc id -- and exactly
one terminal-class structure carries both. This is the zero-false cross-source
anchor: AP alone is not safe (the same-AP splice twin is a DIFFERENT structure
tens-to-hundreds of metres away); proximity is not used at all (no coordinate is
read to BIND -- geometry is carried only as resolved metadata).

UNIVERSAL CORE: this module holds zero plan-set literals (drift-guard-enforced).
Everything customer-specific arrives via parameters/profile:
  * ``terminal_class`` -- which ``KmzStructure.kmz_class`` is the bore terminus
    (from the KMZ profile/dialect, e.g. the dialect's ``terminal_class``);
  * ``ap_re`` / ``splice_re`` -- the PDF-callout grammars (the dialect's tokens)
    used only by the optional ``parse_terminus_pair`` helper.
The KMZ feature model is produced by the universal KMZ reader (extract/kmz.py)
and passed IN as a parameter; this module never imports the reader.

COMPARISON SEMANTICS (M9.1 audit fix): the splice-loc is compared as a WHOLE
NORMALIZED TOKEN -- never reduced to a trailing integer -- so a zone/alpha id
(``A-12`` vs ``B-12``, ``Loc 5A``) neither cross-binds nor vanishes. The AP id is
compared by value-equality. The law itself imposes no integer assumption. How a
raw string becomes an AP id / splice token is the PROFILE's GRAMMAR: the shipped
reference profile parses integer AP ids + ``SPLICE LOC`` tokens; a plan set whose
ids carry discriminating prefixes/suffixes supplies a grammar that preserves them
(and must produce AP keys of a consistent comparable type across both sources).
The law is sound for any profile whose grammar does not itself discard
discriminating id characters.

DEFAULT-OFF / UNWIRED: nothing in ``resolve_bore`` / the sweep / the reviewer
service / ``run_match`` consults this module. It places nothing, draws nothing,
emits no AUTO, no stroke/segment/PNG, and changes no product bucket. It only
reports a typed, evidence-carrying terminal anchor (or a typed refusal).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

# typed outcomes (the join is uniqueness-mandatory and two-field-mandatory)
JOIN_BOUND = "KMZ_TERMINAL_JOIN_BOUND"
JOIN_NONE = "KMZ_TERMINAL_JOIN_NONE"
JOIN_AMBIGUOUS = "KMZ_TERMINAL_JOIN_AMBIGUOUS"
JOIN_AP_MISSING = "KMZ_TERMINAL_JOIN_AP_MISSING"
JOIN_SPLICE_MISSING = "KMZ_TERMINAL_JOIN_SPLICE_MISSING"
JOIN_AP_ONLY_REJECTED = "KMZ_TERMINAL_JOIN_AP_ONLY_REJECTED"
JOIN_SPLICE_ONLY_REJECTED = "KMZ_TERMINAL_JOIN_SPLICE_ONLY_REJECTED"
JOIN_NO_TERMINAL_CLASS = "KMZ_TERMINAL_JOIN_NO_TERMINAL_CLASS"


@dataclass(frozen=True)
class TerminalAnchor:
    """A resolved bore-terminus structure. ``splice_loc`` is an OPAQUE normalized
    TOKEN (not an int) so a zone/alpha id (``A-12`` vs ``B-12``) stays distinct.
    ``lon``/``lat`` are carried as METADATA only -- the join never reads them."""
    ap_id: int
    splice_loc: str
    kmz_class: str
    name: str
    lon: float
    lat: float

    def to_dict(self) -> dict:
        return {"ap_id": self.ap_id, "splice_loc": self.splice_loc,
                "kmz_class": self.kmz_class, "name": self.name,
                "lon": round(self.lon, 6), "lat": round(self.lat, 6)}


@dataclass(frozen=True)
class TerminalJoin:
    """Typed answer. ``anchor`` is non-None ONLY for JOIN_BOUND."""
    result: str
    anchor: Optional[TerminalAnchor] = None
    named_missing: Optional[str] = None
    evidence: dict = field(default_factory=dict)

    @property
    def bound(self) -> bool:
        return self.result == JOIN_BOUND

    def to_dict(self) -> dict:
        return {"result": self.result,
                "anchor": self.anchor.to_dict() if self.anchor else None,
                "named_missing": self.named_missing, "evidence": self.evidence}


def _norm_token(text: Optional[str]) -> Optional[str]:
    """Normalized comparison token for an id string: uppercased, whitespace-
    collapsed, stripped. PRESERVES every discriminating character (zone letters,
    alpha suffixes). A trailing-integer reduction would erase a 'SPLICE A-12' vs
    'SPLICE B-12' distinction and risk binding the WRONG closure on a non-integer
    plan set -- so the join compares whole opaque tokens, never a parsed int.
    Empty / whitespace-only -> None."""
    if not text:
        return None
    t = " ".join(str(text).upper().split())
    return t or None


def terminal_anchors(model, terminal_class: str) -> Tuple[TerminalAnchor, ...]:
    """Every terminal-class structure carrying BOTH an AP id and a splice-loc
    token, expanded to one anchor per (ap_id, splice_loc). AP ids are de-
    duplicated per structure so a self-duplicated id can never masquerade as two
    candidates. A structure missing either id contributes no anchor."""
    out: List[TerminalAnchor] = []
    for s in getattr(model, "structures", ()):
        if s.kmz_class != terminal_class:
            continue
        sp = _norm_token(s.splice_loc)
        if sp is None:
            continue
        for ap in sorted(set(s.ap_ids)):
            out.append(TerminalAnchor(ap_id=ap, splice_loc=sp,
                                      kmz_class=s.kmz_class, name=s.name,
                                      lon=s.lon, lat=s.lat))
    return tuple(out)


def join_terminal(model, *, terminal_class: str,
                  pdf_ap: Optional[int],
                  pdf_splice_loc: Optional[str]) -> TerminalJoin:
    """Bind a PDF terminus (AP id + splice-loc token) to EXACTLY ONE terminal-
    class KMZ structure carrying BOTH ids. The splice-loc is compared as a whole
    normalized TOKEN (zone/alpha-safe), never a parsed int. Every non-bind is a
    typed refusal. No proximity, no AP-only, no splice-only, no guess."""
    if not terminal_class:
        return TerminalJoin(JOIN_NO_TERMINAL_CLASS,
                            named_missing="the KMZ profile declares no "
                            "terminal_class for the bore-terminus join")
    if pdf_ap is None:
        return TerminalJoin(JOIN_AP_MISSING,
                            named_missing="no printed AP id on the PDF terminus "
                            "callout -- the join requires both an AP id and a "
                            "splice-loc id")
    sp_key = _norm_token(pdf_splice_loc)
    if sp_key is None:
        return TerminalJoin(
            JOIN_SPLICE_MISSING,
            named_missing="no printed SPLICE-LOC id on the PDF terminus callout "
            "-- AP alone is not a safe anchor (the same-AP splice twin is a "
            "different structure); the splice-loc id is mandatory",
            evidence={"pdf_ap": pdf_ap})

    anchors = terminal_anchors(model, terminal_class)
    both = [a for a in anchors
            if a.ap_id == pdf_ap and a.splice_loc == sp_key]
    if len(both) == 1:
        a = both[0]
        return TerminalJoin(
            JOIN_BOUND, anchor=a,
            evidence={"join": "two-field (AP id + splice-loc token) agreement",
                      "pdf_ap": pdf_ap, "pdf_splice_loc": sp_key,
                      "kmz_terminal": a.name, "kmz_class": a.kmz_class,
                      "proximity_used": False})
    if len(both) > 1:
        return TerminalJoin(
            JOIN_AMBIGUOUS,
            named_missing=f"{len(both)} {terminal_class} structures carry BOTH "
            f"AP {pdf_ap} and {sp_key!r} -- the terminus is not uniquely "
            f"printed; never chosen between",
            evidence={"pdf_ap": pdf_ap, "pdf_splice_loc": sp_key,
                      "candidates": [a.name for a in both]})

    # zero two-field matches -> diagnose WHY (and prove AP-only / splice-only
    # are REFUSED, never silently downgraded to a one-field bind).
    ap_hits = [a for a in anchors if a.ap_id == pdf_ap]
    splice_hits = [a for a in anchors if a.splice_loc == sp_key]
    if ap_hits:
        return TerminalJoin(
            JOIN_AP_ONLY_REJECTED,
            named_missing=f"AP {pdf_ap} matches a {terminal_class} but its "
            f"splice-loc(s) {sorted({a.splice_loc for a in ap_hits})} != "
            f"{sp_key!r} -- AP-only is not a safe anchor; refused",
            evidence={"pdf_ap": pdf_ap, "pdf_splice_loc": sp_key,
                      "ap_match_splice_locs": sorted({a.splice_loc
                                                      for a in ap_hits})})
    if splice_hits:
        return TerminalJoin(
            JOIN_SPLICE_ONLY_REJECTED,
            named_missing=f"splice-loc {sp_key!r} matches a {terminal_class} but "
            f"its AP id(s) {sorted({a.ap_id for a in splice_hits})} != PDF AP "
            f"{pdf_ap} -- splice-only is not a safe anchor; refused",
            evidence={"pdf_ap": pdf_ap, "pdf_splice_loc": sp_key,
                      "splice_match_aps": sorted({a.ap_id for a in splice_hits})})
    return TerminalJoin(
        JOIN_NONE,
        named_missing=f"no {terminal_class} carries AP {pdf_ap} with splice-loc "
        f"{sp_key!r} -- no cross-source terminus anchor exists",
        evidence={"pdf_ap": pdf_ap, "pdf_splice_loc": sp_key})


def parse_terminus_pair(line: str, *, ap_re: str, splice_re: str
                        ) -> Tuple[Optional[int], Optional[str]]:
    """Optional helper: extract (ap_id, splice_loc_token) from ONE printed
    terminus callout line, using the INJECTED grammars (the dialect's ap/splice
    tokens). Universal -- holds no literal vocabulary. The splice-loc is returned
    as a normalized opaque token (zone/alpha-safe); the AP id is an int per a
    digit-AP grammar; a field absent -> None so the caller can feed
    the pair straight to join_terminal. ASSUMES exactly one terminus per line --
    do not feed multi-callout or line-wrapped OCR text (it would take the first AP
    and first splice token, which may belong to different structures)."""
    ap = None
    m = re.search(ap_re, line or "", re.I)
    if m:
        g = m.group(1) if m.groups() else m.group(0)
        d = re.search(r"\d+", g or "")
        ap = int(d.group(0)) if d else None
    sp = None
    ms = re.search(splice_re, line or "", re.I)
    if ms:
        sp = _norm_token(ms.group(0))
    return ap, sp
