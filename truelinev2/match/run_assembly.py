r"""M9.4.1 -- RUN_ASSEMBLY: the shipped convention-agnostic run-assembly core.

Promotes the M9.4 Phase-0 run-assembly safety law (proof/run_run_assembly_phase0)
into engine code over the M9.3.1 typed terminus facts (match/terminus_attribution).
It binds a bore-to-bore JUNCTION into a typed SHARED-TERMINAL-NODE evidence item --
or refuses it with a typed blocker. It places NOTHING, draws NOTHING, emits no AUTO,
moves no bore, changes no product bucket. The evidence is a NEW review item (a future
group card, M8.20-style); it is NOT a stationing or geometric continuation.

THE BASE FACT (directional END -> START):
  An END bore TERMINATES at terminal T (END-of-feed ownership, M9.3.1) and a DIFFERENT
  bore's START sits at the same T (a JUNCTION_ORIGIN -- it DEPARTS the junction). The
  relation is a SHARED TERMINAL NODE. What departs T may be the trunk continuing OR a
  fiber-drop LATERAL: the DEPARTING bore's printed run class types the item -- a non-
  drop departure is a RUN_ASSEMBLY_REVIEW_CANDIDATE; a positively-detected drop
  departure is a JUNCTION_DROP_BRANCH (a branch off the terminus, NOT the trunk). A
  reviewer -- never this core -- commits a run.

THE SAFETY LAW (all must hold before the departure is classified):
  0. bore-to-bore only (start_bore != end_bore -- a self-junction is refused);
  1. END ownership is clean + unique (END is ENDPOINT_ATTRIBUTED; one terminal -> one
     END bore, the M9.3.1 invariant);
  2. the START side is JUNCTION_ORIGIN, never ownership (END-direction law);
  3. both sides carry the SAME normalized terminal fact (same AP + same splice token);
  4. the M9.1 two-field join corroborates the terminal (END kmz_join == BOUND);
  5. neither bore carries a PDF<->KMZ or source contradiction;
  6. NO competing physical departure at the terminal (see below);
  7. EVIDENCE-only -- it changes no product disposition.

THE COMPETING GUARD (M9.4.1 -- the named Phase-0 gap closed for the same-frame case):
  Phase-0 counted only JUNCTION_ORIGIN departures (terminal-class start notes). This
  core enumerates the physical departures printed WITHIN THE TERMINAL'S OWN FRAME -- the
  END bore's sheets, where the terminal note sits: every run callout printed AT the
  terminal's station, PLUS every JUNCTION_ORIGIN start, deduped so a JUNCTION_ORIGIN
  bore's OWN run callout is not double-counted. If MORE THAN ONE distinct physical run
  departs the node, the continuation branches -> COMPETING_JUNCTION_CANDIDATES (never
  chosen between). So a fiber-drop lateral that lacks a terminal-class start note can no
  longer hide from the guard -- WHEN it is drawn on the terminal's own sheet.

  KNOWN LIMITATION (named, still-open evidence target -- mirrors the Phase-0 block):
  the scan is frame-scoped to the END bore's sheets, NOT corpus-wide, because a station
  token (e.g. "4+51") is frame-local and recurs in every sheet's stationing -- a corpus-
  wide scan would FALSE-POSITIVE on unrelated frames (the M9.2 matchline trap), breaking
  zero-false. So a matchline-adjacent lateral drawn SOLELY on a sheet outside the END
  bore's frame is not yet enumerated. Associating a far-sheet callout with this node
  requires the cross-sheet frame-equation graph (the M9.2 matchline track) -- a separate,
  justified capability, never a silent widen here.

UNIVERSAL CORE: this module holds ZERO plan-set literals (drift-guard-enforced). The
station / run-callout grammar AND the drop-marker grammar arrive via the injected
PROFILE (duck-typed; the reference profile lives in extract/terminus_profile.py). No
reader / no PDF I/O: the caller passes neutral per-sheet text lines (the SAME the
M9.3.1 attribution consumed) and the typed BoreTerminusResult facts.

COMPOSES (read-only): match.terminus_attribution (the M9.3.1 typed facts + the
junction resolver) -- exactly as terminus_attribution composes the M9.1 join. It is
NOT on the placement path.

UNWIRED (unconsumed): nothing in resolve_bore / the sweep / the reviewer service /
the engine / run_match consults this module (it has no opt-in flag -- it is simply
not imported by any consumer). It returns typed, evidence-carrying facts only; acting
on them is a future, separately-gated reviewer-service step.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from truelinev2.match import terminus_attribution as TA

# ---- typed dispositions -----------------------------------------------------
# the two SHARED-TERMINAL evidence facts (a reviewer classifies/commits):
RUN_ASSEMBLY_REVIEW_CANDIDATE = "RUN_ASSEMBLY_REVIEW_CANDIDATE"   # non-drop departure; candidate continuation
JUNCTION_DROP_BRANCH = "JUNCTION_DROP_BRANCH"                     # positively-detected drop lateral
# typed blockers (no evidence item; never a placement):
SELF_JUNCTION_REFUSED = "SELF_JUNCTION_REFUSED"
START_JUNCTION_NOT_OWNERSHIP = "START_JUNCTION_NOT_OWNERSHIP"
COMPETING_JUNCTION_CANDIDATES = "COMPETING_JUNCTION_CANDIDATES"
PDF_KMZ_CONTRADICTION = TA.PDF_KMZ_CONTRADICTION
SOURCE_CONTRADICTION = TA.SOURCE_CONTRADICTION
UNMODELED_RUN_RELATIONSHIP = "UNMODELED_RUN_RELATIONSHIP"

# the relation/evidence every item carries (the FACT, not a committed run)
RELATION_SHARED_TERMINAL = "END_START_SHARED_TERMINAL"
EVIDENCE_SHARED_TERMINAL = "JUNCTION_SHARED_TERMINAL_EVIDENCE"

# departing-bore printed run classes
DEP_DROP = "drop"
DEP_TRUNK = "trunk"
DEP_UNKNOWN = "unknown"

# the dispositions that carry a shared-terminal FACT (vs a typed blocker)
EVIDENCE_DISPOSITIONS = (RUN_ASSEMBLY_REVIEW_CANDIDATE, JUNCTION_DROP_BRANCH)

_JOIN_BOUND = TA._JOIN_BOUND   # "KMZ_TERMINAL_JOIN_BOUND"


def _norm(s) -> Optional[str]:
    return " ".join(str(s).upper().split()) if s else None


@dataclass(frozen=True)
class Departure:
    """A physical run-callout departure printed at a node station. ``is_drop`` is
    True iff the callout window carries one of the injected ``profile.drop_markers``
    (the core invents no drop literal). The ``key`` is the normalized callout text,
    so the SAME printed run on two sheets is ONE departure, and a JUNCTION_ORIGIN
    bore's own run callout is not double-counted against the node enumeration."""
    origin_station: str
    is_drop: bool
    line: str

    @property
    def key(self) -> str:
        return " ".join(self.line.upper().split())

    def to_dict(self) -> dict:
        return {"origin_station": self.origin_station, "is_drop": self.is_drop,
                "line": self.line}


@dataclass(frozen=True)
class RunAssemblyEvidence:
    """Typed answer for ONE junction. For an evidence disposition it carries the
    shared-terminal FACT; for a blocker it carries the typed reason. NEVER a
    placement: ``geometry`` is always None, ``auto`` always False, and the item
    asserts it changes no product disposition."""
    end_bore: str
    start_bore: str
    terminal_ap: object
    splice_loc: Optional[str]
    disposition: str
    relation: str = RELATION_SHARED_TERMINAL
    evidence_class: str = EVIDENCE_SHARED_TERMINAL
    departure_run_class: str = DEP_UNKNOWN
    competing_departures: int = 1
    end_station: Optional[str] = None
    start_station: Optional[str] = None
    end_note: Optional[str] = None
    start_note: Optional[str] = None
    end_ownership_clean_unique: bool = False
    start_is_junction_origin_not_ownership: bool = False
    same_terminal_fact: bool = False
    kmz_join_corroborated: bool = False
    why: str = ""
    # posture invariants (asserted, never computed True for a placement)
    review_only: bool = True
    evidence_only: bool = True
    affects_product_disposition: bool = False
    auto: bool = False
    geometry: None = None
    terminal_is_end_of_feed: bool = True

    @property
    def is_evidence(self) -> bool:
        return self.disposition in EVIDENCE_DISPOSITIONS

    @property
    def is_continuation_candidate(self) -> bool:
        return self.disposition == RUN_ASSEMBLY_REVIEW_CANDIDATE

    @property
    def is_drop_branch(self) -> bool:
        return self.disposition == JUNCTION_DROP_BRANCH

    def to_dict(self) -> dict:
        return {"end_bore": self.end_bore, "start_bore": self.start_bore,
                "terminal_ap": self.terminal_ap, "splice_loc": self.splice_loc,
                "disposition": self.disposition, "relation": self.relation,
                "evidence_class": self.evidence_class,
                "departure_run_class": self.departure_run_class,
                "competing_departures": self.competing_departures,
                "end_station": self.end_station, "start_station": self.start_station,
                "end_note": self.end_note, "start_note": self.start_note,
                "end_ownership_clean_unique": self.end_ownership_clean_unique,
                "start_is_junction_origin_not_ownership":
                    self.start_is_junction_origin_not_ownership,
                "same_terminal_fact": self.same_terminal_fact,
                "kmz_join_corroborated": self.kmz_join_corroborated,
                "review_only": self.review_only, "evidence_only": self.evidence_only,
                "affects_product_disposition": self.affects_product_disposition,
                "auto": self.auto, "geometry": self.geometry,
                "terminal_is_end_of_feed": self.terminal_is_end_of_feed,
                "why": self.why}


# ---- profile-driven physical-departure enumeration --------------------------

def run_callout_departures(lines_by_sheet: Dict[object, Sequence[str]], station: str,
                           profile) -> Tuple[Departure, ...]:
    """Every physical run-callout departure printed AT ``station`` -- a
    ``STA <station> ... <run_callout_marker> ...`` line -- typed with its drop flag
    (the callout window carries an injected ``profile.drop_markers`` token).
    Deduped by normalized callout text. Convention-clean: the station grammar, the
    run-callout marker, the note window, AND the drop markers are all injected."""
    if not station:
        return ()
    sta_re = re.compile(profile.station_line_re)
    markers = tuple(m.upper() for m in getattr(profile, "drop_markers", ()) or ())
    window_n = profile.note_window
    seen: Dict[str, Departure] = {}
    for lines in lines_by_sheet.values():
        for i, ln in enumerate(lines):
            s = ln.strip()
            m = sta_re.match(s)
            if not m or m.group(1) != station:
                continue
            if profile.run_callout_marker not in s:
                continue
            # frame discipline (mirror detect_endpoint_note): stop the window at the
            # next STA line so a NEIGHBORING station's note cannot leak its drop marker
            # into this callout's window.
            parts = [s]
            for nxt in lines[i + 1:i + 1 + window_n]:
                if sta_re.match(nxt.strip()):
                    break
                parts.append(nxt.strip())
            window = " ".join(parts)
            up = window.upper()
            d = Departure(origin_station=station,
                          is_drop=any(mk in up for mk in markers),
                          line=window.strip())
            seen.setdefault(d.key, d)
    return tuple(seen.values())


def departure_run_class(lines_by_sheet: Dict[object, Sequence[str]],
                        start_station: str, profile) -> str:
    """The printed run class of the bore DEPARTING a terminal, read at its START
    station: DEP_DROP if any of its run callouts carries an injected drop marker,
    DEP_TRUNK if a departing run callout exists without one, else DEP_UNKNOWN.
    (Absence of a drop marker is NOT proof of trunk -- a non-drop departure stays a
    review CANDIDATE, never an asserted continuation.)"""
    deps = run_callout_departures(lines_by_sheet, start_station, profile)
    if not deps:
        return DEP_UNKNOWN
    return DEP_DROP if any(d.is_drop for d in deps) else DEP_TRUNK


def physical_departure_count(terminal_ap, end_bore: str,
                             junction_origin_bores: Sequence[str],
                             by_id: Dict[str, "TA.BoreTerminusResult"],
                             lines_by_id: Dict[str, Dict[object, Sequence[str]]],
                             profile) -> Tuple[int, List[Departure]]:
    """The distinct physical departures at the terminal node, enumerated WITHIN THE
    TERMINAL'S OWN FRAME (the END bore's sheets) -- the M9.4.1 stronger guard. Returns
    (count, unclaimed_node_laterals). The count is the number of JUNCTION_ORIGIN
    departing bores PLUS the run callouts printed at the terminal's station (on the END
    bore's sheets) that are NOT one of those bores' own (claimed) callouts. > 1 == the
    continuation branches. SCOPE (named limitation): a matchline-adjacent lateral drawn
    SOLELY on a sheet outside the END bore's frame is not enumerated here (a station
    token is frame-local; a corpus-wide scan would false-positive -- the M9.2 trap); the
    cross-sheet case needs the M9.2 frame-equation graph (a separate, justified step)."""
    claimed = set()
    for b in junction_origin_bores:
        br = by_id.get(b)
        if br is None:
            continue
        for d in run_callout_departures(lines_by_id.get(b, {}), br.start_station, profile):
            claimed.add(d.key)
    end_r = by_id.get(end_bore)
    node_station = end_r.end_station if end_r else ""
    node = run_callout_departures(lines_by_id.get(end_bore, {}), node_station, profile)
    extra = [d for d in node if d.key not in claimed]
    return len(set(junction_origin_bores)) + len(extra), extra


# ---- the safety law ---------------------------------------------------------

def assemble_junction(junction: dict, by_id: Dict[str, "TA.BoreTerminusResult"],
                      competing_departures: int, contradiction: Dict[str, str],
                      dep_class: str) -> RunAssemblyEvidence:
    """The run-assembly safety law over ONE junction fact. Pure; emits a typed
    SHARED-TERMINAL evidence item or a typed blocker. EVIDENCE-only -- never a
    placement/bucket. The departure run class (trunk/drop) types an evidence item."""
    start_bore = junction["start_bore"]
    ap = junction["terminal_ap"]
    end_bore = junction["end_bore_owner"]
    splice = junction.get("splice_loc")
    end_r = by_id.get(end_bore) if end_bore is not None else None
    start_r = by_id.get(start_bore)

    def make(disp: str, why: str, **extra) -> RunAssemblyEvidence:
        return RunAssemblyEvidence(
            end_bore=end_bore, start_bore=start_bore, terminal_ap=ap, splice_loc=splice,
            disposition=disp, departure_run_class=dep_class,
            competing_departures=competing_departures,
            end_station=end_r.end.station if end_r else None,
            start_station=start_r.start.station if start_r else None,
            end_note=end_r.end.note_line if end_r else None,
            start_note=start_r.start.note_line if start_r else None,
            why=why, **extra)

    # (0) bore-to-bore only -- a self-junction is degenerate.
    if end_bore is not None and start_bore == end_bore:
        return make(SELF_JUNCTION_REFUSED,
                    f"{start_bore} START and END both sit at terminal AP {ap} -- a "
                    f"self-junction is not a bore-to-bore relation; refused")
    if end_bore is None:
        return make(UNMODELED_RUN_RELATIONSHIP,
                    f"terminal AP {ap} has no unique END owner -- no bore-to-bore junction")
    if end_r is None or start_r is None:
        return make(UNMODELED_RUN_RELATIONSHIP,
                    "a junction bore is absent from the extractor results")

    # (1) END ownership clean + unique
    owners = TA.terminal_end_index(list(by_id.values())).get(ap, [])
    if (end_r.end.result != TA.ENDPOINT_ATTRIBUTED or end_r.end.ap != ap
            or owners != [end_bore]):
        return make(UNMODELED_RUN_RELATIONSHIP,
                    f"END ownership of AP {ap} is not clean+unique to {end_bore} "
                    f"(owners={owners})")
    # (2) START is JUNCTION_ORIGIN, never ownership
    if start_r.start.result != TA.JUNCTION_ORIGIN or start_r.start.ap != ap:
        return make(START_JUNCTION_NOT_OWNERSHIP,
                    f"{start_bore} START is not a JUNCTION_ORIGIN for AP {ap} "
                    f"(result={start_r.start.result}) -- refused as ownership")
    # (3) same normalized terminal fact
    if not (end_r.end.ap == start_r.start.ap
            and _norm(end_r.end.splice) == _norm(start_r.start.splice)):
        return make(UNMODELED_RUN_RELATIONSHIP,
                    f"END/START do not share one terminal fact "
                    f"({end_r.end.ap}/{end_r.end.splice} vs "
                    f"{start_r.start.ap}/{start_r.start.splice})")
    # (4) KMZ join corroborates
    if end_r.end.kmz_join != _JOIN_BOUND:
        return make(UNMODELED_RUN_RELATIONSHIP,
                    f"terminal AP {ap} is not KMZ-join corroborated "
                    f"(join={end_r.end.kmz_join})")
    # (5) contradiction blocks
    for b in (end_bore, start_bore):
        if b in contradiction:
            return make(contradiction[b],
                        f"{b} carries a {contradiction[b]} -- blocked until owner/source reread")
    # (6) competing PHYSICAL departure (M9.4.1: all departures, not only JUNCTION_ORIGIN)
    if competing_departures > 1:
        return make(COMPETING_JUNCTION_CANDIDATES,
                    f"{competing_departures} physical runs depart terminal AP {ap} -- "
                    f"the continuation branches; never chosen between")

    # (7) classify by the departing bore's printed run class
    clean = dict(end_ownership_clean_unique=True,
                 start_is_junction_origin_not_ownership=True,
                 same_terminal_fact=True, kmz_join_corroborated=True)
    if dep_class == DEP_DROP:
        return make(JUNCTION_DROP_BRANCH,
                    f"{start_bore} departs terminal AP {ap} as a fiber-drop lateral "
                    f"(a printed drop marker) -- a branch off {end_bore}'s end-of-feed "
                    f"terminus, NOT the trunk continuing", **clean)
    return make(RUN_ASSEMBLY_REVIEW_CANDIDATE,
                f"{end_bore} END terminates at terminal AP {ap} ({splice}); "
                f"{start_bore} departs the SAME terminal (departure run class: "
                f"{dep_class}) -- a SHARED-TERMINAL-NODE review candidate; the reviewer "
                f"classifies the continuation (shared-terminal FACT only, not a "
                f"committed run, no drop marker positively detected)", **clean)


# ---- corpus entry point -----------------------------------------------------

def extract_run_assembly(results: Sequence["TA.BoreTerminusResult"],
                         lines_by_id: Dict[str, Dict[object, Sequence[str]]],
                         profile) -> List[RunAssemblyEvidence]:
    """The shipped run-assembly extractor over M9.3.1 typed terminus facts.

    ``results``: the M9.3.1 BoreTerminusResult list. ``lines_by_id``: per-bore
    neutral lines_by_sheet (the SAME the attribution consumed). ``profile``: the
    injected TerminusProfile (station/run/drop grammar). Pure read; emits one typed
    RunAssemblyEvidence per bore-to-bore junction. No placement, no geometry, no AUTO,
    zero bores moved. The contradictions are derived from the typed facts themselves
    (a bore whose disposition is a PDF<->KMZ or source contradiction)."""
    by_id = {r.bore_id: r for r in results}
    junctions = TA.resolve_junctions(results)
    contradiction = {r.bore_id: r.disposition for r in results
                     if r.disposition in (PDF_KMZ_CONTRADICTION, SOURCE_CONTRADICTION)}
    jo_by_ap: Dict[object, List[str]] = {}
    for r in results:
        if r.start.result == TA.JUNCTION_ORIGIN and r.start.ap is not None:
            jo_by_ap.setdefault(r.start.ap, []).append(r.bore_id)

    out: List[RunAssemblyEvidence] = []
    for j in junctions:
        ap = j["terminal_ap"]
        end_bore = j["end_bore_owner"]
        start_bore = j["start_bore"]
        dep = departure_run_class(lines_by_id.get(start_bore, {}),
                                  by_id[start_bore].start_station, profile) \
            if start_bore in by_id else DEP_UNKNOWN
        count, _extra = physical_departure_count(
            ap, end_bore, jo_by_ap.get(ap, []), by_id, lines_by_id, profile) \
            if end_bore is not None else (len(jo_by_ap.get(ap, [])), [])
        out.append(assemble_junction(j, by_id, count, contradiction, dep))
    return out
