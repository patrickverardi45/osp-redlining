r"""M8.14.c -- the symbol/conduit/matchline stroke LANE (default-OFF skeleton).

Promotes the proven b.2 -> b.10 chain into ONE named, modular resolver lane.
The lane is convention-agnostic: every layer name, class color, keyword, and
token format arrives via an injected ``LaneDialect`` (the extract seam owns
the tables); this module holds no plan-set knowledge (drift-guard-enforced).

Chain (each component a proven law; any missing artifact -> typed refusal):
  1. printed END identity (structure note at the end station)
  2. label box -> leader -> symbol-cluster POSITION binding (class-checked)
  3. printed START identity: reset equation OR structure note, any ref sheet
  4. conduit-origin topology when the start identity is unprinted
     (containment + span corroboration -- a span-refused candidate is a
     pick-card, never a placement)
  5. clean station-ladder tick path as the STATION CONSTRAINT, then the
     M8.14.c.2 DESIGN-PATH ADHERENCE law for geometry: the stroke FOLLOWS
     the drawn conduit route (welded-piece walk); ticks never define final
     geometry; a chord needs a positive straightness certificate; an
     untraceable design path is a typed abstain, never a chord
  6. matchline-joined cross-sheet continuation when start/end sheets differ
  7. symbol-anchored stroke segments (RED by the stroke-color law; rendering
     itself lives in render/, not here)
  8. typed abstain / pick-card when any proof artifact is missing

MODE: default-OFF (``TL2_SYMBOL_CONDUIT_LANE_OPTIN``; Phase 0 ships the lane
UNWIRED -- nothing in engine/service consults it). REVIEW-ONLY: no lane
outcome can ever be AUTO. ZERO-FALSE: every gate is a refusal gate.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from truelinev2.extract.conduit_topology import (
    ORIGIN_AMBIGUOUS,
    ORIGIN_BOUND,
    connected_chain,
    dash_endpoints,
    discriminate_origin,
    ladder_band_scales,
    ladder_scale_for_band,
    symbol_footprint,
)
from truelinev2.extract.design_path import (
    DESIGN_LENGTH_REL_TOL,
    NOT_CONNECTED as DP_NOT_CONNECTED,
    TRACED as DP_TRACED,
    chord_straightness_certificate,
    conduit_pieces,
    parallel_strand_guard,
    path_length,
    ticks_adhere,
    walk_design_path,
)
from truelinev2.extract.conduit_topology import FOOTPRINT_RADIUS
from truelinev2.extract.matchline_join import (
    cross_sheet_join_verdict,
    extend_dash_to_boundary,
    find_run_callout_from,
    find_run_callout_to,
    joined_segments_verdict,
    matchline_bboxes,
    nearest_gap,
    run_callouts_ending_at,
    run_callouts_starting_at,
)
from truelinev2.extract.stroke_anchor import (
    label_offset_safety,
    stroke_endpoint_fidelity,
)
from truelinev2.extract.structure_anchor import (
    BOUND,
    bind_end_structure_note,
    bind_origin_by_parent_station,
)
from truelinev2.extract.structure_position import (
    PAIR_SCALE_REL_TOL,
    POSITION_BOUND,
    LaneDialect,
    cluster_symbols,
    corroborate_pair_scale,
    resolve_structure_position,
)
from truelinev2.extract.tick_path import READY, Tick, route_ladder_ticks, solve_tick_path
from truelinev2.proof.station_equation_ownership import extract_reset_origins
from truelinev2.stations import feet_to_station, parse_station

LANE_NAME = "symbol_conduit_matchline"
LANE_MODE = "REVIEW_ONLY"   # no lane outcome can ever be AUTO (structural)

S_ELIGIBLE = "STROKE_ELIGIBLE_REVIEW"
S_PICK = "PICK_CARD_WITH_END_ANCHOR"
S_END_ONLY = "POSITION_BOUND_END_ONLY"
S_UNPRINTED = "END_IDENTITY_UNPRINTED"
S_END_POSITION = "END_POSITION_UNRESOLVED"
# Distinct abstains so the census names the REAL blocker (not one catch-all):
#   - structure-identity: >= 2 rival symbols claim the start -- at the on-sheet
#     conduit origin (the banked b.5 trap) OR among far-sheet structures the
#     M8.16 corroboration band cannot separate (the log42 class) -> needs the
#     identity discriminator, never a metric guess
#   - cross-sheet: the conduit run exits the sheet (0 on-sheet candidates) or a
#     cross-sheet matchline join cannot be proven -> needs the b.9 join evidence
S_STRUCTURE_REQUIRED = "STRUCTURE_IDENTITY_BINDING_REQUIRED"
S_CROSS_SHEET = "CROSS_SHEET_CONTINUATION_REQUIRED"
# M8.14.c.2 (Patrick's graded-FAIL correction): a redline must FOLLOW the
# drawn design line; when conduit is drawn but the path cannot be traced
# uniquely (or a chord lacks a straightness certificate), the stroke abstains
# -- a chord is never drawn across a drawn route.
S_DESIGN = "DESIGN_PATH_NOT_TRACEABLE"
STATUSES = (S_ELIGIBLE, S_PICK, S_END_ONLY, S_UNPRINTED, S_END_POSITION,
            S_STRUCTURE_REQUIRED, S_CROSS_SHEET, S_DESIGN)

BAND_HALFWIDTH = 30.0   # ladder-scale corridor around an anchor (b.8 constant)

# Per-component architecture record: core law / dialect facts / what another
# company configures. Static, lane-owned; emitted with every outcome.
COMPONENTS: Dict[str, Dict[str, str]] = {
    "end_identity": {
        "law": "a structure NOTE at the bore's end station binds end identity "
               "(grammar excludes run callouts and equations); uniqueness "
               "mandatory",
        "configured": "structure-note keywords per class (class_keywords)",
    },
    "structure_position": {
        "law": "identity word -> unique same-layer label box (context-"
               "disambiguated) -> unique same-layer leader -> unique symbol "
               "cluster at the tip -> class fill check; labels are never "
               "positions",
        "configured": "label/symbol layers + class fills (structure_layers); "
                      "locator strategy + context words + id/equation token "
                      "formats",
    },
    "start_identity": {
        "law": "exact reset-equation parent-station equality OR a structure "
               "note at the start station, scanned over the bore's referenced "
               "sheets; never metric",
        "configured": "equation token format; structure-note keywords",
    },
    "conduit_origin": {
        "law": "the bore's CORRIDOR conduit chain (graph-connected to the "
               "bound end footprint, restricted to the ladder-frame axis band "
               "the end anchor lives in -- off-corridor network legs are "
               "other runs) must terminate with dash endpoints inside EXACTLY "
               "ONE start-side structure footprint, and the symbol-pair span "
               "must corroborate the sheet ladder scale; a span-refused "
               "candidate is a pick-card, never a placement",
        "configured": "callout conduit text -> conduit layer (conduit_layers, "
                      "conduit_key)",
    },
    "tick_path": {
        "law": "clean all-tick-block ladder ticks + symbol anchor ticks "
               "through the uniqueness/scale/branch-safe solver; exactly one "
               "trimmed stroke; endpoints land ON the anchors; ticks CONSTRAIN "
               "progress -- they never define final geometry by themselves",
        "configured": "nothing (fully general)",
    },
    "design_path": {
        "law": "the stroke interior FOLLOWS the drawn conduit route: anchor-"
               "seeded exhaustive walk over conduit piece segments (sub-path "
               "long axes), nearest-hop with junction tie-branching, dead "
               "ends pruned, EXACTLY ONE complete path; length corroborates "
               "the ladder scale; in-span ticks lie ON the path; a chord is "
               "drawn ONLY with a positive straightness certificate (in-span "
               "ticks collinear with the anchor chord); anything else is a "
               "typed abstain -- never a chord across a drawn route",
        "configured": "drawn conduit-path layers (path_layers)",
    },
    "matchline_join": {
        "law": "printed frame equation typeset at both drawn matchlines + "
               "chains terminating at them + shared printed boundary station "
               "+ footage closure + agreeing implied scales; boundary anchors "
               "= terminal dash extended along its own direction, dash-gap "
               "capped",
        "configured": "matchline layer name; equation format (frame grammar)",
    },
    "cross_sheet_origin": {
        "law": "when the end-sheet corridor chain finds no on-sheet origin, "
               "the far sheet is DISCOVERED only from printed artifacts: a "
               "run callout ENDING at the bore end on the end sheet names the "
               "boundary station; EXACTLY ONE frame-graph equation edge "
               "carries that boundary raw on the end sheet; the bore log's "
               "own sheet references must name the far sheet; the far sheet "
               "prints the reciprocal callout STARTING at the bore start "
               "with the SAME boundary raw and closing footage; the run's "
               "conduit class comes from the printed notes via the dialect "
               "table; EXACTLY ONE far-sheet structure's conduit chain "
               "terminates at the shared matchline (rivals adjudicated only "
               "by the banked corroboration band against a CONSISTENT -- "
               "unimodal -- ladder band; corroboration refuses, never "
               "selects); the b.9 join law then re-proves the continuation",
        "configured": "nothing new (matchline layer, equation format, conduit/"
                      "structure layers already arrive via the lane dialect)",
    },
    "stroke_output": {
        "law": "segments only for fully-proven chains; REVIEW-only; the "
               "canonical red stroke color law governs all rendering",
        "configured": "nothing (color law is canonical)",
    },
    "abstain": {
        "law": "any missing proof artifact -> typed status + the exact named "
               "missing artifact; no guessing, no widening, no fallback",
        "configured": "nothing (fully general)",
    },
}


@dataclass(frozen=True)
class ComponentReport:
    component: str
    result: str
    detail: str = ""

    def to_dict(self) -> dict:
        return {"component": self.component, "result": self.result,
                "detail": self.detail,
                "law": COMPONENTS[self.component]["law"],
                "configured_by": COMPONENTS[self.component]["configured"]}


@dataclass(frozen=True)
class StrokeSegment:
    sheet: int
    start_ft: float
    end_ft: float
    stroke_points: Tuple[Tuple[float, float], ...]

    def to_dict(self) -> dict:
        return {"sheet": self.sheet, "start_ft": self.start_ft,
                "end_ft": self.end_ft,
                "stroke_points": [[round(x, 1), round(y, 1)]
                                  for x, y in self.stroke_points]}


@dataclass(frozen=True)
class LaneOutcome:
    bore_id: str
    status: str
    review_only: bool = True            # structural: the lane has no AUTO
    segments: Tuple[StrokeSegment, ...] = ()
    evidence: Tuple[ComponentReport, ...] = ()
    named_missing: Optional[str] = None
    detail: dict = field(default_factory=dict)

    @property
    def stroke_eligible(self) -> bool:
        return self.status == S_ELIGIBLE and bool(self.segments)

    def to_dict(self) -> dict:
        return {"bore_id": self.bore_id, "lane": LANE_NAME, "mode": LANE_MODE,
                "status": self.status, "review_only": self.review_only,
                "stroke_eligible": self.stroke_eligible,
                "segments": [s.to_dict() for s in self.segments],
                "evidence_chain": [e.to_dict() for e in self.evidence],
                "named_missing": self.named_missing, "detail": self.detail}


def corridor_filter(segments: Sequence[dict],
                    frame_points: Sequence[Tuple[float, float]],
                    halfwidth: float = BAND_HALFWIDTH) -> List[dict]:
    """Conduit segments within ``halfwidth`` of the route-corridor AXIS (the
    line through the outermost ladder-frame points). Orientation-free. The
    b.6 corridor construction stated as lane law: a bore whose interior is
    the corridor ladder cannot originate off-corridor; perpendicular network
    legs belong to OTHER runs. Fewer than two frame points -> no corridor is
    established and the segments pass through unfiltered (ambiguity then
    refuses honestly downstream)."""
    pts = list(frame_points)
    if len(pts) < 2:
        return list(segments)
    (x0, y0), (x1, y1) = pts[0], pts[-1]
    dx, dy = x1 - x0, y1 - y0
    den = math.hypot(dx, dy)
    if den == 0:
        return list(segments)
    out = []
    for s in segments:
        perp = abs((s["xc"] - x0) * dy - (s["yc"] - y0) * dx) / den
        if perp <= halfwidth:
            out.append(s)
    return out


CS_BOUND = "CROSS_SHEET_START_BOUND"
CS_REFUSED = "CROSS_SHEET_START_REFUSED"
CS_AMBIGUOUS = "CROSS_SHEET_START_AMBIGUOUS"


def _sheet_no(frame_id: str) -> Optional[int]:
    head, _, tail = str(frame_id).partition(":")
    return int(tail) if head == "sheet" and tail.isdigit() else None


def discover_cross_sheet_start(plan, bore, offset: int, dialect: LaneDialect,
                               frame_graph, *, end_sheet: int) -> dict:
    """The cross_sheet_origin DISCOVERY law (see COMPONENTS): printed-only
    far-sheet + start-structure binding for a bore whose corridor chain found
    no on-sheet origin. PURE READ; every missing clause is a typed refusal
    with the exact named artifact. The returned binding is a CANDIDATE only --
    the caller must re-prove the continuation through the full matchline-join
    law before any geometry exists."""
    end_raw = feet_to_station(bore.station_end_ft)
    start_raw = feet_to_station(bore.station_start_ft)
    span_ft = bore.station_end_ft - bore.station_start_ft

    def refuse(named: str, result: str = CS_REFUSED, **detail) -> dict:
        return {"result": result, "named_missing": named, "detail": detail}

    # 1. printed boundary: run callouts ENDING at the bore end on E ---------
    #    (uniqueness-mandatory: 0 or >= 2 distinct boundary statements refuse)
    ending = [(raw, f, note) for raw, f, note
              in run_callouts_ending_at(plan.lines(end_sheet, offset), end_raw)
              if f is not None]
    boundary_cands = sorted({(raw, f) for raw, f, _ in ending
                             if raw != start_raw})
    if not boundary_cands:
        if ending:
            return refuse(f"sheet {end_sheet}'s run callout ending at "
                          f"{end_raw} starts at the bore's own start station "
                          f"{start_raw} (a full-span callout) -- it names no "
                          f"crossing boundary, yet the drawn chain exits the "
                          f"sheet; the printed segment callouts are the "
                          f"named missing artifact")
        return refuse(f"a printed run callout ENDING at {end_raw} on sheet "
                      f"{end_sheet} (with its note footage) -- without the "
                      f"end sheet's printed segment statement no shared "
                      f"boundary station exists")
    if len(boundary_cands) > 1:
        return refuse(f"{len(boundary_cands)} distinct printed run callouts "
                      f"end at {end_raw} on sheet {end_sheet} "
                      f"({boundary_cands}) -- the boundary station is not "
                      f"uniquely printed")
    boundary_raw, seg_end_ft = boundary_cands[0]
    end_note = " | ".join(n for raw, f, n in ending
                          if (raw, f) == boundary_cands[0])

    # 2. EXACTLY ONE printed frame equation carries that boundary on E ------
    #    (either side of the equation -- the equation NAMES one physical
    #    boundary in two sheet frames; callouts print bore-local stationing,
    #    which may be either side: the log65 + log32 evidence)
    edges = []
    for e in (frame_graph.edges if frame_graph is not None else ()):
        a_sheet, b_sheet = _sheet_no(e.from_frame), _sheet_no(e.to_frame)
        if end_sheet == a_sheet and boundary_raw in (e.a_raw, e.b_raw):
            edges.append((e, b_sheet))
        elif end_sheet == b_sheet and boundary_raw in (e.a_raw, e.b_raw):
            edges.append((e, a_sheet))
    if not edges:
        return refuse(f"a printed matchline frame equation carrying boundary "
                      f"{boundary_raw} on one of sheet {end_sheet}'s drawn "
                      f"matchlines -- the sheet prints no equation at this "
                      f"boundary (the log50-class missing artifact); a join "
                      f"is never synthesized")
    if len(edges) > 1:
        return refuse(f"{len(edges)} printed frame equations claim boundary "
                      f"{boundary_raw} on sheet {end_sheet} -- the far sheet "
                      f"is not uniquely printed",
                      sources=[e.source for e, _ in edges])
    edge, far_sheet = edges[0]
    if far_sheet is None or far_sheet == end_sheet:
        return refuse(f"the frame equation {edge.source!r} does not name a "
                      f"distinct far sheet")
    refs = sorted(set(bore.sheet_refs))
    if far_sheet not in refs:
        # Every proven cross-sheet specimen (log65; log8/32/42 evidence)
        # references BOTH sheets in its own bore log. A discovered far sheet
        # the bore log never cites is uncorroborated by the bore's own
        # printed references -- refuse, never guess (the log12 class).
        return refuse(f"the bore log's own sheet references {refs} do not "
                      f"name the discovered far sheet {far_sheet} -- the "
                      f"printed continuation is uncorroborated by the bore's "
                      f"print references", far_sheet=far_sheet,
                      edge_source=edge.source)

    # 3. reciprocal printed callout on the far sheet + footage closure ------
    starting = [(raw, f, note) for raw, f, note
                in run_callouts_starting_at(plan.lines(far_sheet, offset),
                                            start_raw)
                if f is not None]
    recip = sorted({(raw, f) for raw, f, _ in starting
                    if raw == boundary_raw})
    if not recip:
        return refuse(f"a printed run callout on sheet {far_sheet} from "
                      f"{start_raw} to the shared boundary {boundary_raw} "
                      f"(the far sheet prints "
                      f"{[r for r, _, _ in starting] or 'none'} from "
                      f"{start_raw}) -- without the reciprocal segment "
                      f"statement the continuation is unproven",
                      far_sheet=far_sheet, edge_source=edge.source)
    if len(recip) > 1:
        return refuse(f"{len(recip)} distinct printed footages for the far "
                      f"segment {start_raw}->{boundary_raw} on sheet "
                      f"{far_sheet} ({recip})", far_sheet=far_sheet)
    seg_far_ft = recip[0][1]
    far_note = " | ".join(n for raw, f, n in starting
                          if (raw, f) == recip[0])
    if abs((seg_end_ft + seg_far_ft) - span_ft) > 0.5:
        return refuse(f"footage closure (printed {seg_far_ft}+{seg_end_ft} "
                      f"!= bore span {span_ft})", far_sheet=far_sheet)

    # 3b. the run's conduit CLASS, from the printed notes themselves --------
    #     (the dialect's promised seam: bore-callout conduit text -> conduit
    #     layer; BOTH reciprocal notes must name the SAME single mapped class)
    common_keys = sorted(k for k in dialect.conduit_layers
                         if k in end_note.upper() and k in far_note.upper())
    if not common_keys:
        return refuse(f"a mapped conduit class in the printed reciprocal "
                      f"callout notes (notes: {end_note[:90]!r} / "
                      f"{far_note[:90]!r}; mapped classes: "
                      f"{sorted(dialect.conduit_layers)}) -- extend the "
                      f"dialect conduit table, never guess a layer",
                      far_sheet=far_sheet)
    if len(common_keys) > 1:
        return refuse(f"the printed reciprocal notes name {len(common_keys)} "
                      f"mapped conduit classes ({common_keys}) -- the run's "
                      f"drawn layer is not uniquely printed",
                      far_sheet=far_sheet)
    conduit_layer = dialect.conduit_layers[common_keys[0]]

    # 4. EXACTLY ONE far-sheet structure chain terminates at the matchline --
    drawings = plan.line_items(far_sheet, offset)
    mls = matchline_bboxes(drawings, dialect.matchline_layer)
    eq_text = edge.source.split(None, 1)[-1]
    eq_xy = next(((w["xc"], w["yc"]) for w in plan.words(far_sheet, offset)
                  if w["text"] == eq_text), None)
    if eq_xy is None or not mls:
        return refuse(f"the equation text {eq_text!r} typeset at sheet "
                      f"{far_sheet}'s drawn matchline", far_sheet=far_sheet)
    ml = min(mls, key=lambda bb: nearest_gap([eq_xy], bb))
    conduit = [d for d in drawings if d["layer"] == conduit_layer]
    sym_layers = sorted({v[1] for v in dialect.structure_layers.values()})
    reaching: Dict[str, dict] = {}
    for lay in sym_layers:
        for c in cluster_symbols(drawings, lay):
            bb = symbol_footprint(drawings, lay, (c.x, c.y))
            if not bb:
                continue
            chain = connected_chain(conduit, bb)
            bnd = extend_dash_to_boundary(chain, ml) if chain else None
            if bnd is None:
                continue
            reaching[f"{lay}@{c.x:.0f},{c.y:.0f}"] = {
                "layer": lay,
                "xy": ((bb[0] + bb[2]) / 2.0, (bb[1] + bb[3]) / 2.0),
                "chain_segments": len(chain), "boundary_xy": bnd}
    if not reaching:
        return refuse(f"a sheet-{far_sheet} structure whose drawn conduit "
                      f"chain terminates at the shared matchline -- none "
                      f"found; the continuation may span further sheets "
                      f"(multi-hop continuation is a separate named "
                      f"capability)", far_sheet=far_sheet)
    if len(reaching) > 1:
        # A drawn conduit NETWORK blobs every on-network structure into
        # "reaching". The banked b.6 corroboration band (the SAME refusal
        # gate that holds log50 at pick-card) refuses every candidate whose
        # distance to its own chain's drawn boundary crossing does not
        # account for the PRINTED far-segment footage at the sheet's ladder
        # scale. The band itself must be a CONSISTENT corroboration basis:
        # a y-band holding ticks from MORE THAN ONE drawn ladder yields
        # multi-modal hop scales whose median is a cross-ladder artifact
        # (the log42 adversarial finding) -- such a band corroborates
        # NOTHING. Refusal-shaped throughout: survivors of 0 or >= 2 still
        # abstain -- corroboration never selects, it only refuses.
        ticks_f, _ = route_ladder_ticks(plan, far_sheet, offset)
        survivors = {}
        band_notes = []
        for label, cand in reaching.items():
            bxy = cand["boundary_xy"]
            scales = ladder_band_scales(
                ticks_f, bxy[1] - BAND_HALFWIDTH, bxy[1] + BAND_HALFWIDTH)
            med = sorted(scales)[len(scales) // 2] if scales else None
            unimodal = (med is not None and med > 0 and all(
                abs(s - med) / med <= PAIR_SCALE_REL_TOL for s in scales))
            if not unimodal:
                band_notes.append(
                    f"{label}: ladder band is "
                    + ("empty" if not scales else
                       f"multi-modal ({[round(s, 3) for s in scales]} pt/ft "
                       f"-- ticks from more than one drawn ladder)")
                    + "; no corroboration basis")
                continue
            corr = corroborate_pair_scale(cand["xy"], bxy, seg_far_ft, med)
            if corr["consistent"]:
                survivors[label] = {**cand, "corroboration": corr}
        if len(survivors) != 1:
            return {"result": CS_AMBIGUOUS,
                    "named_missing": (
                        f"{len(reaching)} sheet-{far_sheet} structures sit on "
                        f"the conduit network reaching the shared matchline "
                        f"and {len(survivors)} corroborate the printed far-"
                        f"segment footage ({seg_far_ft}') against a "
                        f"consistent ladder band "
                        f"(survivors: {sorted(survivors) or 'none'}"
                        + (f"; {'; '.join(sorted(set(band_notes)))}"
                           if band_notes else "")
                        + ") -- the start structure identity cannot be "
                        f"uniquely bound; guessing is forbidden"),
                    "detail": {"far_sheet": far_sheet,
                               "rivals": sorted(reaching),
                               "survivors": sorted(survivors),
                               "band_notes": sorted(set(band_notes))}}
        reaching = survivors
    label, cand = next(iter(reaching.items()))
    return {"result": CS_BOUND, "far_sheet": far_sheet,
            "start_xy": cand["xy"], "start_layer": cand["layer"],
            "conduit_layer": conduit_layer,
            "boundary_raw": boundary_raw, "seg_end_ft": seg_end_ft,
            "seg_far_ft": seg_far_ft, "edge_source": edge.source,
            "detail": (f"callouts {start_raw}->{boundary_raw} "
                       f"({seg_far_ft}') on sheet {far_sheet} + "
                       f"{boundary_raw}->{end_raw} ({seg_end_ft}') on sheet "
                       f"{end_sheet}; equation {edge.source!r}; printed "
                       f"conduit class {common_keys[0]!r} -> layer "
                       f"{conduit_layer!r}; unique reaching structure "
                       f"{label} ({cand['chain_segments']} chain segs)")}


def _classify_label(label: Optional[str],
                    dialect: LaneDialect) -> Optional[str]:
    up = (label or "").upper()
    for klass, keywords in dialect.class_keywords:
        if any(k in up for k in keywords):
            return klass
    return None


def _locate(plan, sheet: int, offset: int, dialect: LaneDialect, *,
            klass: str, station_raw: Optional[str] = None,
            note_label: Optional[str] = None,
            equation_line: Optional[str] = None):
    """Position binding for an identity, by the dialect's locator strategy.
    Equation-bound identities ALWAYS locate by the equation token (lane law)."""
    words = plan.words(sheet, offset)
    drawings = plan.line_items(sheet, offset)
    if equation_line is not None:
        m = re.search(dialect.equation_token, equation_line.replace(" ", ""))
        if not m:
            return None, "the origin source line carries no locatable equation token"
        return resolve_structure_position(
            label_text=m.group(0), structure_class=klass, words=words,
            drawings=drawings, layer_table=dialect.structure_layers), None
    strategy = dialect.locator.get(klass)
    if strategy == "station_context":
        return resolve_structure_position(
            label_text=station_raw, structure_class=klass, words=words,
            drawings=drawings, layer_table=dialect.structure_layers,
            context_texts=dialect.context_words.get(klass, ())), None
    if strategy == "id_token":
        m = re.search(dialect.id_token, note_label or "")
        if not m:
            return None, (f"the {klass} note label carries no printed id token "
                          f"-- the locator strategy cannot run")
        return resolve_structure_position(
            label_text=m.group(0), structure_class=klass, words=words,
            drawings=drawings, layer_table=dialect.structure_layers), None
    return None, (f"no locator strategy is configured for class {klass!r} -- "
                  f"a note-bound class without a locator is a typed refusal")


def _solve_segment(plan, offset: int, dialect: LaneDialect, *, bore_id: str,
                   sheet: int, start_ft: float, end_ft: float,
                   start_xy: Tuple[float, float], end_xy: Tuple[float, float]
                   ) -> Tuple[Optional[StrokeSegment], str, str, str]:
    """Returns (segment, refusal, abstain_status, design_note). The tick path
    remains the STATION CONSTRAINT (uniqueness/scale gates); the GEOMETRY must
    follow the drawn design path (M8.14.c.2) -- a chord is allowed only with a
    positive straightness certificate."""
    ticks, _counts = route_ladder_ticks(plan, sheet, offset)
    anchors = [Tick(start_ft, *start_xy), Tick(end_ft, *end_xy)]
    v = solve_tick_path(bore_id=bore_id, sheet=sheet, start_ft=start_ft,
                        end_ft=end_ft, ticks=list(ticks) + anchors)
    if v.result != READY or v.strokes_found != 1:
        return None, (f"anchored tick path on sheet {sheet} is {v.result} "
                      f"({v.named_missing_relationship or 'not unique'})"), \
            S_END_ONLY, ""
    if not stroke_endpoint_fidelity(v, start_xy, end_xy):
        return None, (f"the trimmed stroke on sheet {sheet} does not land ON "
                      f"the anchor symbols -- fidelity refused"), S_END_ONLY, ""

    inspan = [(t.x, t.y) for t in ticks if start_ft < t.station_ft < end_ft]
    med = sorted(v.hop_scales)[len(v.hop_scales) // 2] if v.hop_scales else 0.0
    span_ft = end_ft - start_ft
    pieces = conduit_pieces(plan.line_items(sheet, offset), dialect.path_layers)
    walk = walk_design_path(pieces, start_xy, end_xy)

    if walk["result"] == DP_TRACED:
        stroke = walk["stroke_points"]
        plen = path_length(stroke)
        scale_ok = (med > 0 and span_ft > 0
                    and abs(plen / span_ft - med) / med <= DESIGN_LENGTH_REL_TOL)
        adhere = ticks_adhere(stroke, inspan, BAND_HALFWIDTH)
        strands = parallel_strand_guard(
            pieces, walk["visited_pieces"], stroke,
            [start_xy, end_xy], BAND_HALFWIDTH, FOOTPRINT_RADIUS)
        if not strands["clear"]:
            return None, (f"an unvisited mapped-class conduit piece PARALLELS "
                          f"the traced path on sheet {sheet} ({strands}) -- a "
                          f"sibling drawn run the walk never saw complete; "
                          f"the strand discriminator is the named missing "
                          f"artifact; tracing one of parallel runs is "
                          f"forbidden"), S_DESIGN, ""
        if not scale_ok:
            return None, (f"the traced design path on sheet {sheet} fails "
                          f"length corroboration ({round(plen, 1)} pt / "
                          f"{span_ft} ft vs ladder {round(med, 3)} pt/ft) -- "
                          f"the drawn route does not account for the bore "
                          f"span; a chord is never substituted"), S_DESIGN, ""
        if not adhere["adheres"]:
            return None, (f"the traced design path on sheet {sheet} leaves "
                          f"the in-span tick band ({adhere}) -- ticks "
                          f"constrain progress; refused"), S_DESIGN, ""
        note = (f"design path TRACED: {len(stroke)} vertices over "
                f"{len(pieces)} pieces; length {round(plen, 1)} pt "
                f"corroborates {round(plen / span_ft, 3)} pt/ft; "
                f"tick adherence {adhere}")
        return StrokeSegment(sheet=sheet, start_ft=start_ft, end_ft=end_ft,
                             stroke_points=tuple(stroke)), "", "", note

    if walk["result"] == DP_NOT_CONNECTED:
        cert = chord_straightness_certificate(inspan, start_xy, end_xy,
                                              BAND_HALFWIDTH)
        if cert["straight"]:
            note = (f"no drawn conduit connects the anchors; chord permitted "
                    f"by straightness certificate {cert}")
            return StrokeSegment(sheet=sheet, start_ft=start_ft,
                                 end_ft=end_ft,
                                 stroke_points=tuple(v.stroke_points)), \
                "", "", note
        return None, (f"no drawn conduit path of the mapped classes connects "
                      f"the anchors on sheet {sheet} AND the straightness "
                      f"certificate fails ({cert}) -- a chord across a "
                      f"non-certified route is forbidden; the named missing "
                      f"artifact is the bore's drawn conduit class/layer "
                      f"mapping (extend path_layers) or a straight tick "
                      f"certificate"), S_DESIGN, ""

    return None, (f"the design-path walk on sheet {sheet} is "
                  f"{walk['result']} ({walk.get('named_missing', '')}) -- "
                  f"a chord is never drawn across a drawn route"), S_DESIGN, ""


def resolve_bore(plan, bore, offset: int, dialect: LaneDialect,
                 frame_graph=None) -> LaneOutcome:
    """The full lane chain for ONE bore. Pure orchestration of proven laws;
    every stop is a typed outcome with its component evidence trail."""
    ev: List[ComponentReport] = []
    sheets = sorted(set(bore.sheet_refs))
    bid = bore.bore_id

    # 1. END identity --------------------------------------------------------
    end_sheet = end_id = end_klass = None
    for sheet in sheets:
        eid = bind_end_structure_note(bore.station_end_ft,
                                      plan.lines(sheet, offset))
        if eid.result != BOUND:
            continue
        klass = _classify_label(eid.structure_label, dialect)
        if klass:
            end_sheet, end_id, end_klass = sheet, eid, klass
            break
    if end_id is None:
        named = (f"printed end-structure note at "
                 f"{feet_to_station(bore.station_end_ft)} on sheets {sheets} "
                 f"-- the end identity is unprinted; no end anchor can exist")
        ev.append(ComponentReport("end_identity", "REFUSED", named))
        return LaneOutcome(bore_id=bid, status=S_UNPRINTED,
                           evidence=tuple(ev), named_missing=named)
    ev.append(ComponentReport("end_identity", "BOUND",
                              f"sheet {end_sheet}: {end_id.note_line} -> "
                              f"{end_klass}"))

    # 2. END position --------------------------------------------------------
    end_pos, err = _locate(plan, end_sheet, offset, dialect, klass=end_klass,
                           station_raw=end_id.end_station,
                           note_label=end_id.structure_label)
    if err or end_pos.result != POSITION_BOUND:
        named = err or (f"end position unresolved: {end_pos.result} -- "
                        f"{end_pos.named_missing_relationship}")
        ev.append(ComponentReport("structure_position", "REFUSED", named))
        return LaneOutcome(bore_id=bid, status=S_END_POSITION,
                           evidence=tuple(ev), named_missing=named)
    ev.append(ComponentReport("structure_position", "BOUND",
                              f"end symbol @{[round(c, 1) for c in end_pos.symbol_xy]} "
                              f"sheet {end_sheet}"))

    # 3. START identity (printed: equation, then note; any referenced sheet) --
    start_sheet = start_xy = start_klass = start_layer = None
    start_word_xy = None
    cs_conduit_layer = None   # set only by cross-sheet origin discovery
    for sheet in sheets:
        lines = plan.lines(sheet, offset)
        ob = bind_origin_by_parent_station(
            bore.station_start_ft, extract_reset_origins(lines, sheet))
        if ob.result == BOUND and ob.origin.structure_type:
            pos, err = _locate(plan, sheet, offset, dialect,
                               klass=ob.origin.structure_type,
                               equation_line=ob.origin.source_line)
            if not err and pos.result == POSITION_BOUND:
                start_sheet, start_xy = sheet, tuple(pos.symbol_xy)
                start_klass = ob.origin.structure_type
                start_layer = dialect.structure_layers[start_klass][1]
                start_word_xy = pos.word_xy
                ev.append(ComponentReport(
                    "start_identity", "BOUND",
                    f"reset equation {ob.origin.source_line!r} sheet {sheet}"))
                break
        sid = bind_end_structure_note(bore.station_start_ft, lines)
        if sid.result == BOUND:
            klass = _classify_label(sid.structure_label, dialect)
            if klass:
                pos, err = _locate(plan, sheet, offset, dialect, klass=klass,
                                   station_raw=sid.end_station,
                                   note_label=sid.structure_label)
                if not err and pos.result == POSITION_BOUND:
                    start_sheet, start_xy = sheet, tuple(pos.symbol_xy)
                    start_klass = klass
                    start_layer = dialect.structure_layers[start_klass][1]
                    start_word_xy = pos.word_xy
                    ev.append(ComponentReport(
                        "start_identity", "BOUND",
                        f"structure note {sid.note_line!r} sheet {sheet}"))
                    break

    # 4. conduit-origin fallback (end sheet; only when nothing is printed) ---
    if start_xy is None:
        drawings = plan.line_items(end_sheet, offset)
        layer = dialect.conduit_layers[dialect.conduit_key]
        sym_layers = sorted({v[1] for v in dialect.structure_layers.values()})
        end_bb = symbol_footprint(
            drawings, dialect.structure_layers[end_klass][1],
            tuple(end_pos.symbol_xy))
        ticks_all, _ = route_ladder_ticks(plan, end_sheet, offset)
        band_pts = ([(t.x, t.y) for t in sorted(
            ticks_all, key=lambda t: t.station_ft)
            if abs(t.y - end_pos.symbol_xy[1]) <= BAND_HALFWIDTH]
            + [tuple(end_pos.symbol_xy)])
        corridor = corridor_filter(
            [d for d in drawings if d["layer"] == layer], band_pts)
        chain = connected_chain(corridor, end_bb)
        cands = {}
        for lay in sym_layers:
            for c in cluster_symbols(drawings, lay):
                if math.hypot(c.x - end_pos.symbol_xy[0],
                              c.y - end_pos.symbol_xy[1]) <= 8:
                    continue  # the end structure is never a start candidate
                bb = symbol_footprint(drawings, lay, (c.x, c.y))
                if bb:
                    cands[f"{lay}@{c.x:.0f},{c.y:.0f}"] = bb
        disc = discriminate_origin(dash_endpoints(chain), cands)
        if disc["result"] == ORIGIN_BOUND:
            bb = cands[disc["winner"]]
            cand_xy = ((bb[0] + bb[2]) / 2.0, (bb[1] + bb[3]) / 2.0)
            scale = ladder_scale_for_band(
                ticks_all, end_pos.symbol_xy[1] - BAND_HALFWIDTH,
                end_pos.symbol_xy[1] + BAND_HALFWIDTH)
            corr = (corroborate_pair_scale(
                cand_xy, tuple(end_pos.symbol_xy),
                bore.station_end_ft - bore.station_start_ft, scale)
                if scale else {"consistent": False, "reason": "no ladder band"})
            if corr["consistent"]:
                start_sheet, start_xy = end_sheet, cand_xy
                ev.append(ComponentReport(
                    "conduit_origin", "BOUND",
                    f"chain ({len(chain)} segs) -> {disc['winner']} "
                    f"span-corroborated {corr}"))
            else:
                named = (f"the conduit-connected candidate {disc['winner']} is "
                         f"REFUSED by span corroboration ({corr}); the bore "
                         f"extends beyond this sheet's drawn chain -- "
                         f"cross-sheet continuation or a reviewer pick is "
                         f"required")
                ev.append(ComponentReport("conduit_origin", "REFUSED", named))
                return LaneOutcome(bore_id=bid, status=S_PICK,
                                   evidence=tuple(ev), named_missing=named,
                                   detail={"candidate": disc["winner"],
                                           "candidate_xy": list(cand_xy),
                                           "end_anchor": list(end_pos.symbol_xy)})
        elif disc["result"] == ORIGIN_AMBIGUOUS:
            # >= 2 rival start-side symbols at the corridor origin ON this sheet
            # -- the start structure is present but not uniquely identifiable
            # (the banked b.5 log51 trap): identity binding, never a guess.
            named = (f"no printed start identity on sheets {sheets} and the "
                     f"corridor conduit chain reaches {disc['hit_counts']} -- "
                     f">= 2 rival start-side structures share the origin; the "
                     f"start structure identity cannot be uniquely bound "
                     f"without an identity discriminator (printed start "
                     f"structure note / equation); guessing is forbidden")
            ev.append(ComponentReport("conduit_origin", "REFUSED", named))
            return LaneOutcome(bore_id=bid, status=S_STRUCTURE_REQUIRED,
                               evidence=tuple(ev), named_missing=named,
                               detail={"end_anchor": list(end_pos.symbol_xy),
                                       "origin_hits": disc["hit_counts"]})
        else:
            # 0 on-sheet candidates -- the conduit run exits this sheet; the
            # start lives across a matchline (the log65 class). The
            # cross_sheet_origin DISCOVERY law now runs: printed-only far-
            # sheet + start binding, then the full b.9 join re-proof below.
            ev.append(ComponentReport(
                "conduit_origin", "REFUSED",
                f"no printed start identity on sheets {sheets}; the corridor "
                f"conduit chain finds NO start-side structure on the end "
                f"sheet ({disc['result']}) -- the run exits this sheet; "
                f"attempting printed cross-sheet origin discovery"))
            cs = discover_cross_sheet_start(plan, bore, offset, dialect,
                                            frame_graph, end_sheet=end_sheet)
            if cs["result"] == CS_BOUND:
                start_sheet = cs["far_sheet"]
                start_xy = tuple(cs["start_xy"])
                start_layer = cs["start_layer"]
                cs_conduit_layer = cs["conduit_layer"]
                ev.append(ComponentReport("cross_sheet_origin", "BOUND",
                                          cs["detail"]))
            elif cs["result"] == CS_AMBIGUOUS:
                ev.append(ComponentReport("cross_sheet_origin", "REFUSED",
                                          cs["named_missing"]))
                return LaneOutcome(
                    bore_id=bid, status=S_STRUCTURE_REQUIRED,
                    evidence=tuple(ev), named_missing=cs["named_missing"],
                    detail={"end_anchor": list(end_pos.symbol_xy),
                            **cs.get("detail", {})})
            else:
                named = (f"cross-sheet continuation evidence incomplete: "
                         f"{cs['named_missing']}")
                ev.append(ComponentReport("cross_sheet_origin", "REFUSED",
                                          named))
                return LaneOutcome(bore_id=bid, status=S_CROSS_SHEET,
                                   evidence=tuple(ev), named_missing=named,
                                   detail={"end_anchor": list(end_pos.symbol_xy),
                                           **cs.get("detail", {})})

    # 5/6/7. strokes: single-sheet or matchline-joined cross-sheet -----------
    if start_sheet == end_sheet:
        seg, err, abstain, note = _solve_segment(
            plan, offset, dialect, bore_id=bid, sheet=end_sheet,
            start_ft=bore.station_start_ft, end_ft=bore.station_end_ft,
            start_xy=start_xy, end_xy=tuple(end_pos.symbol_xy))
        if seg is None:
            comp = "design_path" if abstain == S_DESIGN else "tick_path"
            ev.append(ComponentReport(comp, "REFUSED", err))
            return LaneOutcome(bore_id=bid, status=abstain,
                               evidence=tuple(ev), named_missing=err)
        ev.append(ComponentReport("tick_path", "READY",
                                  "station constraint satisfied"))
        ev.append(ComponentReport("design_path", "TRACED", note))
        segs = (seg,)
    else:
        joined = _cross_sheet_segments(
            plan, offset, dialect, frame_graph, bid=bid, bore=bore,
            start_sheet=start_sheet, start_xy=start_xy,
            start_layer=start_layer,
            end_sheet=end_sheet, end_xy=tuple(end_pos.symbol_xy),
            end_layer=dialect.structure_layers[end_klass][1], ev=ev,
            conduit_layer=cs_conduit_layer)
        if isinstance(joined, LaneOutcome):
            return joined
        segs = joined

    ls = label_offset_safety(
        [segs[0].stroke_points[0], segs[-1].stroke_points[-1]],
        [start_word_xy, end_pos.word_xy])
    if not ls["safe"]:
        named = f"stroke endpoints sit at identity label words ({ls}) -- refused"
        ev.append(ComponentReport("stroke_output", "REFUSED", named))
        return LaneOutcome(bore_id=bid, status=S_END_ONLY,
                           evidence=tuple(ev), named_missing=named)
    ev.append(ComponentReport("stroke_output", "ELIGIBLE",
                              f"{len(segs)} REVIEW segment(s); red by the "
                              f"canonical stroke-color law"))
    return LaneOutcome(bore_id=bid, status=S_ELIGIBLE, segments=segs,
                       evidence=tuple(ev))


def _cross_sheet_segments(plan, offset, dialect: LaneDialect, frame_graph, *,
                          bid: str, bore, start_sheet: int,
                          start_xy: Tuple[float, float], start_layer: str,
                          end_sheet: int, end_xy: Tuple[float, float],
                          end_layer: str, ev: List[ComponentReport],
                          conduit_layer: Optional[str] = None):
    """Components 6+5 for the cross-sheet case; returns segments or a typed
    LaneOutcome refusal (cross-sheet by default -- the whole function is the
    matchline join; an unprovable join IS a cross-sheet-continuation gap).
    ``conduit_layer`` arrives ONLY from cross-sheet origin discovery (the
    printed callout notes' mapped class); the printed-identity path keeps the
    dialect's drop-bore default unchanged."""
    def refuse(named: str, status: str = S_CROSS_SHEET) -> LaneOutcome:
        ev.append(ComponentReport("matchline_join", "REFUSED", named))
        return LaneOutcome(bore_id=bid, status=status, evidence=tuple(ev),
                           named_missing=named,
                           detail={"end_anchor": list(end_xy)})

    start_raw = feet_to_station(bore.station_start_ft)
    end_raw = feet_to_station(bore.station_end_ft)
    co_from = find_run_callout_from(plan.lines(start_sheet, offset), start_raw)
    co_to = find_run_callout_to(plan.lines(end_sheet, offset), end_raw)
    if not co_from or not co_to or co_from[0] != co_to[0]:
        return refuse(f"printed run callouts sharing one boundary station "
                      f"between sheets {start_sheet} and {end_sheet} "
                      f"(found {co_from} / {co_to})")
    boundary_raw, seg_a_ft = co_from
    seg_b_ft = co_to[1]
    boundary_ft = parse_station(boundary_raw)

    edge = None
    if frame_graph is not None:
        for e in frame_graph.edges:
            if ({e.from_frame, e.to_frame}
                    == {f"sheet:{start_sheet}", f"sheet:{end_sheet}"}
                    and boundary_raw in (e.a_raw, e.b_raw)):
                edge = e
                break
    if edge is None:
        return refuse(f"a printed matchline frame equation joining sheets "
                      f"{start_sheet} and {end_sheet} at boundary "
                      f"{boundary_raw} (frame-graph edge)")
    eq_text = edge.source.split(None, 1)[-1]  # equation token sans keyword

    layer = conduit_layer or dialect.conduit_layers[dialect.conduit_key]
    sides = {}
    for sheet, anchor_xy, anchor_layer in (
            (start_sheet, start_xy, start_layer),
            (end_sheet, end_xy, end_layer)):
        drawings = plan.line_items(sheet, offset)
        eq_xy = next(((w["xc"], w["yc"]) for w in plan.words(sheet, offset)
                      if w["text"] == eq_text), None)
        mls = matchline_bboxes(drawings, dialect.matchline_layer)
        if eq_xy is None or not mls:
            return refuse(f"the equation text {eq_text!r} typeset at sheet "
                          f"{sheet}'s drawn matchline")
        ml = min(mls, key=lambda bb: nearest_gap([eq_xy], bb))
        fp = symbol_footprint(drawings, anchor_layer, anchor_xy)
        if fp is None:
            return refuse(f"the bound anchor's drawn footprint on sheet "
                          f"{sheet} ({anchor_layer!r} near {anchor_xy})")
        chain = connected_chain([d for d in drawings if d["layer"] == layer], fp)
        bnd = extend_dash_to_boundary(chain, ml)
        if bnd is None:
            return refuse(f"sheet {sheet}'s conduit chain terminating at its "
                          f"matchline (terminal-dash extension refused)")
        dist = nearest_gap([anchor_xy], ml)
        sides[sheet] = {"boundary": bnd, "dist": dist, "chain": len(chain)}

    scale_a = sides[start_sheet]["dist"] / seg_a_ft if seg_a_ft else None
    scale_b = sides[end_sheet]["dist"] / seg_b_ft if seg_b_ft else None
    join = cross_sheet_join_verdict(
        equation_edge=True, eq_at_matchline_a=True, eq_at_matchline_b=True,
        chain_a_reaches=True, chain_b_reaches=True,
        seg_a_ft=seg_a_ft, seg_b_ft=seg_b_ft,
        span_ft=bore.station_end_ft - bore.station_start_ft,
        scale_a=scale_a, scale_b=scale_b)
    if join["verdict"] != "CROSS_SHEET_CONTINUATION_PROVEN":
        return refuse(join["named_missing"])
    if not joined_segments_verdict(
            boundary_a_ft=boundary_ft, boundary_b_ft=boundary_ft,
            seg_a_ft=seg_a_ft, seg_b_ft=seg_b_ft,
            span_ft=bore.station_end_ft - bore.station_start_ft)["joined"]:
        return refuse("shared-boundary footage closure")
    ev.append(ComponentReport(
        "matchline_join", "PROVEN",
        f"boundary {boundary_raw} via {edge.source!r}; scales "
        f"{round(scale_a, 4)}/{round(scale_b, 4)}"))

    out = []
    notes = []
    for sheet, s_ft, e_ft, s_xy, e_xy in (
            (start_sheet, bore.station_start_ft, boundary_ft, start_xy,
             sides[start_sheet]["boundary"]),
            (end_sheet, boundary_ft, bore.station_end_ft,
             sides[end_sheet]["boundary"], end_xy)):
        seg, err, abstain, note = _solve_segment(
            plan, offset, dialect, bore_id=bid, sheet=sheet,
            start_ft=s_ft, end_ft=e_ft, start_xy=s_xy, end_xy=e_xy)
        if seg is None:
            if abstain == S_DESIGN:
                ev.append(ComponentReport("design_path", "REFUSED", err))
                return LaneOutcome(bore_id=bid, status=S_DESIGN,
                                   evidence=tuple(ev), named_missing=err)
            return refuse(err)
        notes.append(note)
        out.append(seg)
    ev.append(ComponentReport("tick_path", "READY",
                              f"{len(out)} cross-sheet segments "
                              f"(station constraints satisfied)"))
    ev.append(ComponentReport("design_path", "TRACED", " | ".join(notes)))
    return tuple(out)
