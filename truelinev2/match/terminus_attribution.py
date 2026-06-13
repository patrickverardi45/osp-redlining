r"""M9.3.1 -- TERMINUS_ATTRIBUTION: the shipped START/END terminus-attribution law.

Promotes the M9.3 Phase-0 station-note-frame attribution into convention-agnostic
engine code. It binds a printed terminus pair (an AP id + a splice-loc id) to a
SPECIFIC bore ENDPOINT -- the structure note printed AT that endpoint's station --
and refuses everything else with a typed reason. It places NOTHING, draws NOTHING,
emits no AUTO, moves no bore, changes no product bucket.

THE LAW (uniqueness-mandatory; END-of-feed direction; KMZ-cross-checked):
  An AP+splice pair is ENDPOINT_ATTRIBUTED to a bore's END iff the END station
  carries exactly one structure note (0 -> NO_ENDPOINT_NOTE, >=2 ->
  MULTIPLE_COMPETING_CALLOUTS), that note's class is the profile's terminal class
  (else NON_TERMINAL_ENDPOINT), exactly one (AP, splice) pair sits INSIDE that
  note's frame (else NO_AP_SPLICE_PAIR / MULTIPLE_COMPETING_CALLOUTS), and -- when
  a KMZ model is supplied -- the pair joins its unique terminal via the M9.1
  two-field join (a REJECTION -> PDF_KMZ_CONTRADICTION). A corpus check enforces
  that each terminal anchors AT MOST ONE bore END.

  DIRECTION (load-bearing): a terminal is END-OF-FEED -- it carries the ARRIVING
  bore's terminal tail. A terminal printed at a bore's START is the PRIOR feed's
  terminus; this bore DEPARTS the junction. So a terminal at a START is a
  JUNCTION_ORIGIN (a bore-to-bore junction -- useful for run assembly), NEVER the
  START bore's terminus identity. Terminal OWNERSHIP is END-direction only.

  NOT A FLAT SCAN: an AP printed somewhere on the bore's sheets but OWNED by a
  different station's note frame is a SHEET_NEIGHBOR and is rejected -- attribution
  is per-frame, not per-sheet. Proximity, AP-only, and splice-only never attribute.

UNIVERSAL CORE: this module holds ZERO plan-set literals (drift-guard-enforced).
Every convention -- the station / AP / splice grammars, the structure-note keyword
set, the structure-class keyword table, the terminal-class name, AND the AP id TYPE
(``ap_cast``: ``int`` for digit-AP plan sets, ``str``/a normaliser for zone/alpha-AP
plan sets, so an "A12" id is NEVER coerced to int) -- arrives via an injected PROFILE
(duck-typed; the reference profile lives in extract/, the convention seam). The AP
type must match the KMZ side (M9.1 doctrine: a consistent comparable type across both
sources). The KMZ cross-check delegates to the already-universal
match.kmz_structure_join.join_terminal. No reader / no PDF I/O here: the caller
passes neutral per-sheet text lines.

``source_contradiction`` is an INJECTED caller fact (e.g. banked PDF<->source
findings), NOT detected by this extractor; when set it short-circuits the bore to a
SOURCE_CONTRADICTION disposition.

UNWIRED (unconsumed): nothing in resolve_bore / the sweep / the reviewer service /
run_match consults this module (it has no opt-in flag -- it is simply not imported
by any consumer). It returns typed, evidence-carrying facts only; acting on them is
a future, separately-gated lane.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from truelinev2.match.kmz_structure_join import join_terminal

# per-endpoint typed outcomes
ENDPOINT_ATTRIBUTED = "ENDPOINT_ATTRIBUTED"
JUNCTION_ORIGIN = "JUNCTION_ORIGIN"
NO_ENDPOINT_NOTE = "NO_ENDPOINT_NOTE"
NO_AP_SPLICE_PAIR = "NO_AP_SPLICE_PAIR"
NON_TERMINAL_ENDPOINT = "NON_TERMINAL_ENDPOINT"
MULTIPLE_COMPETING_CALLOUTS = "MULTIPLE_COMPETING_CALLOUTS"
PDF_KMZ_CONTRADICTION = "PDF_KMZ_CONTRADICTION"
# bore-level disposition adds:
SHEET_NEIGHBOR_REJECTED = "SHEET_NEIGHBOR_REJECTED"
SOURCE_CONTRADICTION = "SOURCE_CONTRADICTION"
UNMODELED_RELATIONSHIP = "UNMODELED_RELATIONSHIP"

# M9.1 join results that REFUTE an attributed pair (AP present, ids disagree /
# ambiguous). JOIN_NONE = the AP is simply not in the KMZ -> NOT a contradiction
# (attribution is a PDF-side identity; the KMZ is corroboration, not a precondition).
_CONTRA_JOINS = ("KMZ_TERMINAL_JOIN_AP_ONLY_REJECTED",
                 "KMZ_TERMINAL_JOIN_SPLICE_ONLY_REJECTED",
                 "KMZ_TERMINAL_JOIN_AMBIGUOUS")
_JOIN_BOUND = "KMZ_TERMINAL_JOIN_BOUND"


@dataclass(frozen=True)
class EndpointNote:
    """A structure note detected at a station, parsed by the injected profile."""
    station: str
    sheet: object
    note_line: str
    label: str
    structure_class: Optional[str]
    ap: Optional[object]      # profile-typed AP id (int for digit-AP plan sets, str for zone/alpha)
    splice: Optional[str]
    pair_kind: str            # FULL_PAIR | AP_ONLY | SPLICE_ONLY | MULTI_AMBIGUOUS | NO_ID

    def to_dict(self) -> dict:
        return {"station": self.station, "sheet": self.sheet,
                "structure_class": self.structure_class, "ap": self.ap,
                "splice": self.splice, "pair_kind": self.pair_kind,
                "note_line": self.note_line}


@dataclass(frozen=True)
class EndpointAttribution:
    """Typed answer for ONE endpoint. ``ap``/``splice`` are non-None only when an
    AP+splice pair was read from the endpoint note frame."""
    side: str                 # "START" | "END"
    station: str
    result: str
    ap: Optional[object] = None       # profile-typed AP id (int / str), never coerced
    splice: Optional[str] = None
    structure_class: Optional[str] = None
    kmz_join: Optional[str] = None
    note_line: Optional[str] = None
    why: str = ""

    @property
    def attributed(self) -> bool:
        return self.result == ENDPOINT_ATTRIBUTED

    def to_dict(self) -> dict:
        return {"side": self.side, "station": self.station, "result": self.result,
                "ap": self.ap, "splice": self.splice,
                "structure_class": self.structure_class, "kmz_join": self.kmz_join,
                "note_line": self.note_line, "why": self.why}


@dataclass(frozen=True)
class SheetNeighbor:
    ap: object                # profile-typed AP id
    splice_loc: Optional[str]
    owning_station: Optional[str]

    def to_dict(self) -> dict:
        return {"ap": self.ap, "splice_loc": self.splice_loc,
                "owning_station": self.owning_station}


@dataclass(frozen=True)
class BoreTerminusResult:
    bore_id: str
    start_station: str
    end_station: str
    start: EndpointAttribution
    end: EndpointAttribution
    sheet_neighbors: Tuple[SheetNeighbor, ...] = ()
    source_contradiction: bool = False

    @property
    def disposition(self) -> str:
        if self.source_contradiction:
            return SOURCE_CONTRADICTION
        if PDF_KMZ_CONTRADICTION in (self.start.result, self.end.result):
            return PDF_KMZ_CONTRADICTION
        if self.end.result == ENDPOINT_ATTRIBUTED:
            return ENDPOINT_ATTRIBUTED
        if self.start.result == JUNCTION_ORIGIN:
            return JUNCTION_ORIGIN
        if self.sheet_neighbors:
            return SHEET_NEIGHBOR_REJECTED
        if MULTIPLE_COMPETING_CALLOUTS in (self.start.result, self.end.result):
            return MULTIPLE_COMPETING_CALLOUTS
        if self.start.result == NO_ENDPOINT_NOTE and self.end.result == NO_ENDPOINT_NOTE:
            return NO_ENDPOINT_NOTE
        if NON_TERMINAL_ENDPOINT in (self.start.result, self.end.result):
            return NON_TERMINAL_ENDPOINT
        if NO_AP_SPLICE_PAIR in (self.start.result, self.end.result):
            return NO_AP_SPLICE_PAIR
        return UNMODELED_RELATIONSHIP

    @property
    def attributed_aps(self) -> Tuple[int, ...]:
        return tuple(a.ap for a in (self.start, self.end)
                     if a.result in (ENDPOINT_ATTRIBUTED, JUNCTION_ORIGIN) and a.ap)

    def to_dict(self) -> dict:
        return {"bore_id": self.bore_id, "start_station": self.start_station,
                "end_station": self.end_station, "disposition": self.disposition,
                "start": self.start.to_dict(), "end": self.end.to_dict(),
                "sheet_neighbors": [n.to_dict() for n in self.sheet_neighbors],
                "source_contradiction": self.source_contradiction}


# ---- profile-driven detection (uses ONLY the injected profile) --------------

def _classify(label: Optional[str], class_keywords) -> Optional[str]:
    """First class whose keyword appears in the label (injected table). The
    universal mirror of the lane classifier -- holds no class literal."""
    up = (label or "").upper()
    for klass, keywords in class_keywords:
        if any(k in up for k in keywords):
            return klass
    return None


def _in_frame_pair(label: Optional[str], profile
                   ) -> Tuple[Optional[int], Optional[str], str]:
    """Exactly-one-AP + exactly-one-splice inside one note frame, via injected
    grammars. >1 of either -> MULTI_AMBIGUOUS (never first-matched). The splice is
    the whole matched token (zone/alpha-safe), normalised for the M9.1 join."""
    aps = sorted({profile.ap_cast(m)
                  for m in re.findall(profile.ap_token, label or "", re.I)},
                 key=repr)
    sps = sorted({" ".join(m.upper().split())
                  for m in re.findall(profile.splice_token, label or "", re.I)})
    if len(aps) == 1 and len(sps) == 1:
        return aps[0], sps[0], "FULL_PAIR"
    if aps and not sps:
        return (aps[0] if len(aps) == 1 else None), None, "AP_ONLY"
    if sps and not aps:
        return None, (sps[0] if len(sps) == 1 else None), "SPLICE_ONLY"
    if len(aps) > 1 or len(sps) > 1:
        return None, None, "MULTI_AMBIGUOUS"
    return None, None, "NO_ID"


def detect_endpoint_note(lines_by_sheet: Dict[object, Sequence[str]], station: str,
                         profile) -> Tuple[Optional[EndpointNote], int]:
    """The unique structure note at ``station`` across the bore's sheets, parsed by
    the injected profile. Per-sheet first-bound (a single sheet with >=2 qualifying
    notes -> competing). Returns (note | None, max competing count seen)."""
    sta_re = re.compile(profile.station_line_re)
    competing = 0
    for sheet, lines in lines_by_sheet.items():
        cands: List[Tuple[str, str]] = []
        for i, ln in enumerate(lines):
            s = ln.strip()
            m = sta_re.match(s)
            if not m or m.group(1) != station:
                continue
            if profile.run_callout_marker in s or profile.equation_marker in s:
                continue
            parts = [s[m.end():].strip()]
            for nxt in lines[i + 1:i + 1 + profile.note_window]:
                if sta_re.match(nxt.strip()):
                    break
                parts.append(nxt.strip())
            label = " ".join(p for p in parts if p)
            if any(k in label.upper() for k in profile.note_keywords):
                cands.append((s, label))
        if len(cands) == 1:
            note_line, label = cands[0]
            ap, sp, kind = _in_frame_pair(label, profile)
            return EndpointNote(station=station, sheet=sheet, note_line=note_line,
                                label=label,
                                structure_class=_classify(label, profile.class_keywords),
                                ap=ap, splice=sp, pair_kind=kind), competing
        competing = max(competing, len(cands))
    return None, competing


def owning_pairs(lines_by_sheet: Dict[object, Sequence[str]], profile
                 ) -> Dict[int, Tuple[Optional[str], Optional[str]]]:
    """Map each printed AP (from an AP+splice pair) to (splice_loc, owning station).
    A run-callout / equation line resets the frame to None (an orphan owns no note).
    The INDEPENDENT method behind sheet-neighbour rejection."""
    pair_re = re.compile(profile.pair_re, re.I)
    sta_re = re.compile(profile.station_line_re)
    out: Dict[int, Tuple[Optional[str], Optional[str]]] = {}
    for lines in lines_by_sheet.values():
        cur: Optional[str] = None
        for ln in lines:
            s = ln.strip()
            m = sta_re.match(s)
            if m:
                cur = None if (profile.run_callout_marker in s
                               or profile.equation_marker in s) else m.group(1)
            for pm in pair_re.finditer(ln):
                ap = profile.ap_cast(pm.group(1))   # profile-typed; NOT coerced to int
                if ap not in out:
                    # the splice id is the SECOND grammar group; stored as the raw
                    # matched token (no reconstructed vocabulary -> core stays literal-free)
                    out[ap] = (pm.group(2), cur)
    return out


# ---- the law ----------------------------------------------------------------

def attribute_endpoint(side: str, station: str, note: Optional[EndpointNote],
                       competing: int, *, terminal_class: str,
                       kmz_model=None) -> EndpointAttribution:
    """Apply the attribution law to ONE endpoint. END-direction enforced; a
    terminal at a START is a JUNCTION_ORIGIN, never attributed."""
    if note is None:
        if competing >= 2:
            return EndpointAttribution(side, station, MULTIPLE_COMPETING_CALLOUTS,
                                       why=f"{competing} structure notes share STA "
                                       f"{station}; never chosen between")
        return EndpointAttribution(side, station, NO_ENDPOINT_NOTE,
                                   why=f"no structure note at STA {station}")
    base = dict(side=side, station=station, structure_class=note.structure_class,
                note_line=note.note_line)
    if note.pair_kind == "MULTI_AMBIGUOUS":
        return EndpointAttribution(**base, result=MULTIPLE_COMPETING_CALLOUTS,
                                   why="the endpoint note frame carries >1 AP/splice token")
    if note.structure_class != terminal_class:
        return EndpointAttribution(**base, result=NON_TERMINAL_ENDPOINT,
                                   why=f"endpoint note class {note.structure_class!r} "
                                   f"is not the terminal class -- no AP+splice identity")
    if note.pair_kind != "FULL_PAIR":
        return EndpointAttribution(**base, result=NO_AP_SPLICE_PAIR,
                                   why=f"terminal note carries only a partial id "
                                   f"({note.pair_kind})")
    if side == "START":
        return EndpointAttribution(**base, result=JUNCTION_ORIGIN, ap=note.ap,
                                   splice=note.splice,
                                   why=f"START sits at terminal AP {note.ap}; a "
                                   f"terminal is END-OF-FEED, so this is the ARRIVING "
                                   f"bore's terminus -- a junction this bore departs")
    # side == END: a terminal tail terminates here.
    kmz_join = None
    if kmz_model is not None:
        kmz_join = join_terminal(kmz_model, terminal_class=terminal_class,
                                 pdf_ap=note.ap, pdf_splice_loc=note.splice).result
        if kmz_join in _CONTRA_JOINS:
            return EndpointAttribution(**base, result=PDF_KMZ_CONTRADICTION, ap=note.ap,
                                       splice=note.splice, kmz_join=kmz_join,
                                       why=f"PDF terminus AP {note.ap} {note.splice} "
                                       f"CONTRADICTS the KMZ terminal (join {kmz_join})")
    return EndpointAttribution(**base, result=ENDPOINT_ATTRIBUTED, ap=note.ap,
                               splice=note.splice, kmz_join=kmz_join,
                               why=f"AP {note.ap} + {note.splice} printed INSIDE the "
                               f"{station} terminal note frame -- the bore's END terminus")


def attribute_bore(bore_id: str, start_station: str, end_station: str,
                   lines_by_sheet: Dict[object, Sequence[str]], profile, *,
                   kmz_model=None, source_contradiction: bool = False
                   ) -> BoreTerminusResult:
    """Attribute both endpoints of a bore + reject sheet-neighbour APs. Pure;
    consumes neutral per-sheet text lines + the injected profile. ``source_contradiction``
    is an INJECTED caller fact (banked PDF<->source finding), not detected here; when
    True the bore disposition is SOURCE_CONTRADICTION."""
    start_note, sc = detect_endpoint_note(lines_by_sheet, start_station, profile)
    end_note, ec = detect_endpoint_note(lines_by_sheet, end_station, profile)
    start_a = attribute_endpoint("START", start_station, start_note, sc,
                                 terminal_class=profile.terminal_class, kmz_model=kmz_model)
    end_a = attribute_endpoint("END", end_station, end_note, ec,
                               terminal_class=profile.terminal_class, kmz_model=kmz_model)

    # an AP this bore OWNS at an endpoint (attributed / junction / contradicted) is
    # not a foreign neighbour -- PDF_KMZ_CONTRADICTION is included because a
    # contradicted AP still sits at this bore's endpoint frame.
    attributed = {a.ap for a in (start_a, end_a)
                  if a.result in (ENDPOINT_ATTRIBUTED, JUNCTION_ORIGIN, PDF_KMZ_CONTRADICTION)
                  and a.ap}
    neighbors = []
    for ap, (sp, owner) in sorted(owning_pairs(lines_by_sheet, profile).items()):
        if ap in attributed:
            continue
        if owner not in (start_station, end_station):
            neighbors.append(SheetNeighbor(ap=ap, splice_loc=sp, owning_station=owner))
    return BoreTerminusResult(bore_id=bore_id, start_station=start_station,
                              end_station=end_station, start=start_a, end=end_a,
                              sheet_neighbors=tuple(neighbors),
                              source_contradiction=source_contradiction)


# ---- corpus-level invariants ------------------------------------------------

def terminal_end_index(results: Sequence[BoreTerminusResult]) -> Dict[object, List[str]]:
    """terminal AP -> the bore(s) that ENDPOINT_ATTRIBUTED it as an END."""
    idx: Dict[object, List[str]] = {}
    for r in results:
        if r.end.result == ENDPOINT_ATTRIBUTED and r.end.ap is not None:
            idx.setdefault(r.end.ap, []).append(r.bore_id)
    return idx


def check_terminal_uniqueness(results: Sequence[BoreTerminusResult]
                              ) -> Dict[object, List[str]]:
    """Violations of the one-terminal-per-END invariant (a terminal anchoring >1
    bore END). Empty dict == invariant holds."""
    return {ap: bores for ap, bores in terminal_end_index(results).items()
            if len(bores) > 1}


def resolve_junctions(results: Sequence[BoreTerminusResult]) -> List[dict]:
    """Pair each JUNCTION_ORIGIN start to the bore whose END owns that terminal (a
    bore-to-bore junction for a future run-assembly lane)."""
    owner = {ap: bores[0] for ap, bores in terminal_end_index(results).items()
             if len(bores) == 1}
    out = []
    for r in results:
        if r.start.result == JUNCTION_ORIGIN and r.start.ap is not None:
            out.append({"start_bore": r.bore_id, "terminal_ap": r.start.ap,
                        "splice_loc": r.start.splice,
                        "end_bore_owner": owner.get(r.start.ap)})
    return out
