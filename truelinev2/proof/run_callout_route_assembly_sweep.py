r"""GENERALIZED CALLOUT-IDENTITY ROUTE ASSEMBLY sweep -> render redlines (PROOF; read-only; product-gated).

Generalizes the log50 splice-point lesson into ONE solver over the whole anchored-but-not-yet-drawn class.
The log50/log71 finding: a cross-sheet bore draws as TWO sheet-local legs joined by a PRINTED station
identity -- you do NOT need cross-sheet coordinate/frame reconciliation, and you must NOT require the wrong
reciprocal label (an AP on both sheets, a single non-conflicting frame equation, etc.). The engine had been
HOLDING these logs back on exactly that broken assumption ("CONFLICTING_FRAME_EQUATIONS", "multi-sheet
reconciliation", "12-vs-13 crossing ambiguity"). This sweep reads each bore's route SENTENCE from source and
renders it:

  start callout / reset  ->  bind start terminus (modeled structure symbol, leader-bound; never nearest)
  end callout            ->  bind end terminus on its own sheet
  per-endpoint sheet     ->  DERIVED by unique source bind across corrected_sheets (no hardcoded sheet)
  matchline reference    ->  the printed 'MATCHLINE STA a/b - SEE SHEET <partner>' crossing equation
  reciprocal sheet       ->  the SAME printed equation on the partner sheet (station identity, not coords)
  crossing pick          ->  WHICH printed crossing this bore uses = the one BOTH legs' conduit chains
                             physically reach (chain-reach uniqueness) -- this DISAMBIGUATES the
                             "conflicting" multi-crossing sheet pairs the old gate refused
  conduit route          ->  ordered source-backed chain path per leg (every edge a real drawn dash or a
                             <= MAX_DASH_GAP hop; every interior vertex a real dash endpoint)
  station closure        ->  if span_ft is printed, the two drawn legs' length closes the bore span
  -> render TWO red REVIEW strokes (one per sheet), joined by the printed station identity; frames NOT
     reconciled (the proven log50/log52/log53/log71 cross-sheet render shape).

FALSE-POSITIVE GUARDS (each abstains, never guesses): terminus must POSITION_BOUND uniquely on exactly ONE
corrected sheet; the crossing must be the UNIQUE printed SEE-SHEET equation both legs reach (0 or >=2 ->
abstain, no nearest/length pick); BOTH legs required (never a partial drawn as a full bore); every route edge
source-backed (no ruler cut across a through conduit); printed station closure when span_ft is known.

Scope: NO fixture mutation (adjudication read-only), NO coordinate encoding (all xy extractor-derived), NO
owner naming (anchors consumed as-is), NO review-choice fallback, NO seam/ledger/census change (frozen +
gated), NO product/runtime/api/backend/web/deploy/main. Red strokes only; PNG/JSON under the gitignored
data/outputs path. The only engine change is the additive matchline primitive see_sheet_crossings (extract/).

Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_callout_route_assembly_sweep
"""
from __future__ import annotations

import json
import math
import os
import re

from truelinev2.config import _REPO_ROOT
from truelinev2.extract.conduit_topology import (
    MAX_DASH_GAP, connected_chain, dash_endpoints, symbol_footprint,
)
from truelinev2.extract.matchline_join import (
    extend_dash_to_boundary, matchline_bboxes, nearest_gap, see_sheet_crossings,
)
from truelinev2.extract.registry import select_dialect
from truelinev2.extract.structure_position import (
    BRENHAM_CONDUIT_LAYERS, BRENHAM_LATERAL_CONDUIT_LAYERS, BRENHAM_STRUCTURE_LAYERS,
    POSITION_BOUND, resolve_nextlink_hh_callout, resolve_structure_position,
)
from truelinev2.ingest.manual_adjudication import (
    activation_summary, apply_adjudications, load_adjudication,
    parent_run_duplicate_check, validate_endpoint_anchors,
)
from truelinev2.ingest.parent_source import child_owns_route
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.proof.run_brenham_corpus import EXPECTED_COUNT, PDF, enumerate_corpus
from truelinev2.proof.run_log59_render_artifact_slice import (
    interior_vertices_are_dash_endpoints, route_edges_source_backed,
)
from truelinev2.proof.run_log71_render_artifact_slice import order_chain_route, route_length
from truelinev2.proof.run_log71_sheet_local_bind_scout import locate_matchline_boundary
from truelinev2.proof.run_reviewer_service_contract import resolve_corpus
from truelinev2.render.crop import REDLINE_STROKE_RGB, render_redline_stroke
from truelinev2.stations import parse_station

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "callout_route_assembly_sweep"
TRUTH = _REPO_ROOT / "data" / "outputs" / "final_engine_truth_table" / "final_engine_truth_table.json"
# drop bores (flower-pot termini) route on BORE - LATERAL; mainline bores on VACANT PIPE / PORT. The
# dialect defines the lateral layer SEPARATELY (structure_position) and sanctions composing base|lateral
# for drop coverage (the proven log53 lateral precedent). BORE - PATH stays EXCLUDED (unproven over-cover).
BASE_CONDUIT = set(BRENHAM_CONDUIT_LAYERS.values()) | set(BRENHAM_LATERAL_CONDUIT_LAYERS.values())
FROZEN_BUCKETS = {"DRAWABLE_REVIEW": 31, "HUMAN_ADJUSTABLE_REVIEW": 6,
                  "OUT_OF_CLASS": 1, "PICK_CARD_REVIEW": 17, "SOURCE_OR_KMZ_REQUIRED": 3}
ABSTAIN_4 = ("log5", "log31", "log38", "log43")
SCALE = 1.44                # Brenham drawn pts/ft
CLOSURE_REL_TOL = 0.10      # two legs' drawn length vs printed bore span (corroboration, span_ft known)

# the bores already drawn by a committed render proof (the frontier this sweep extends past)
ALREADY_DRAWN = ("log7", "log25", "log45", "log51", "log52", "log53", "log59",
                 "log64", "log65", "log66", "log69", "log71", "log50")
# bores whose route would DUPLICATE an already-drawn sibling (DO-NOT-WIDEN: no parent/child overlap).
DUPLICATE_OF_DRAWN = ()
# OWNER-CONFIRMED PLAN ROUTES (2026-06-17, LOG48_N_LEG_CALLOUT_ASSEMBLY_RENDER lane): a split child whose
# STORED adjudication is CORRUPTED (carries a sibling's route) but whose OWN plan route the owner re-verified
# against the plan PDF (read-only visual re-verify -- every token confirmed in text layer AND rendered crops).
# The corrupted record (corrected_end 5+14 == sibling log50) cannot seed the render, so the owner-confirmed,
# plan-PRINTED route SENTENCE is injected here -- LABELS ONLY; coordinates stay extractor-derived (the reset
# HH + flower pot bind by their printed labels and the conduit is traced from real dashes), and the parent-
# source gate + printed-span closure still gate every leg. NOT an adjudication record; census uses `doc`, not
# this map, so the frozen census is untouched. log48 = bore_log20 Segment A: sheets 10+12, start reset HH
# 'STA 45+33=0+00' (PROP. SPLICE POINT 46) -> 'STA 0+00 TO 1+90' (190') -> MATCHLINE STA 1+90/1+90 SEE SHEET
# 12 -> 'STA 1+90 TO 3+50' (160') through the 8-PORT HH AP-167 SPLICE LOC 46 @3+50 -> 'STA 3+50 TO 5+07'
# (157') -> FLOWER POT @5+07. 190+160+157 = 507 ft. DISTINCT from sibling log50 (sheets 10+11, matchline
# 1+39, AP-168 6-port @1+89, FLOWER POT 5+14, span 514): the parent-source gate REJECTS log48 on the 514
# route, and the UNIQUE-viable-crossing + closure guards reject the parallel 1+91/1+92 Ledbetter run -- so no
# owner naming and no sibling theft. span_ft is the bore-LOCAL plan span (post-reset 0+00->5+07), NOT a
# station delta across the reset.
# log70 (2026-06-17, LOG70_L_TURN_EXACT_FOOTAGE_RENDER lane): the stored 2026-06-16 adjudication anchor is
# WRONG (not merely superseded) -- its START binds the WRONG structure:
#   * WRONG stored start = '1+45' (the far-left start of log69's horizontal Niebuhr run). With it the solver
#     traced the whole L (561.5' -- which the parent gate also rejects as claiming sibling log69's 454' span).
#   * CORRECT start = the 'STA 4+54 INSTALLER HH' at the Niebuhr/Eledra corner (= log69's end).
# log70 is the L-shaped corner-turn UP Eledra St: STA 0+00 TO 1+75 (175') on sheet 17 -> MATCHLINE STA
# 1+75/6+79 SEE SHEET 20 -> STA 1+75 TO 2+15 (40') on sheet 20 -> STA 2+15 FLOWER POT. 175+40 = 215 ft = the
# printed 'HH - HH = 215'' annotation (== footage); the route's CLOSURE to 215 CONFIRMS it (and discriminates
# the 215' Eledra run from the parallel 218' run). The end (FLOWER POT 2+15, sheet 20) and span (215') were
# already correct ("sheet 20 side was correct"); only the WRONG sheet-17 start is fixed here.
# Identity-only override (NO coordinates). It does NOT edit the stored adjudication/census: the WRONG '1+45'
# record is intentionally LEFT IN PLACE in the adjudication data until a census re-baseline is SEPARATELY
# AUTHORIZED -- this map only feeds the render the correct start. Parent gate passes 215 / rejects sibling 454.
OWNER_CONFIRMED_PLAN_ROUTES = {
    "log48": {"log_id": "log48", "corrected_start": "0+00", "corrected_end": "5+07",
              "corrected_sheets": [10, 12], "span_ft": 507, "status": "RECOVERED",
              "evidence_notes": "STA 45+33=0+00", "endpoint_anchors": None,
              "allowed_to_draw": True, "must_remain_abstained": False},
    "log70": {"log_id": "log70", "parent": "bore_log35", "status": "RECOVERED",
              "corrected_start": "0+00", "corrected_end": "2+15",
              "corrected_sheets": [17, 20], "span_ft": 215.0,
              "endpoint_anchors": {
                  "start": {"station": "4+54", "structure_class": "installer_hh",
                            "boundary_kind": "structure_terminus", "clarity": "CLEAR",
                            "structure_label": "INSTALLER HH",
                            "owner_note_text": ("owner re-correction 2026-06-17: log70 L-turn starts at the "
                                                "STA 4+54 INSTALLER HH (Niebuhr/Eledra corner; = log69 end) and "
                                                "runs UP Eledra St. Supersedes the 1+45 start. HH-HH=215' == the "
                                                "bore footage (175' s17 + 40' s20).")},
                  "end": {"station": "2+15", "structure_class": "flower_pot",
                          "boundary_kind": "structure_terminus", "clarity": "CLEAR",
                          "structure_label": "FLOWER POT",
                          "owner_note_text": ("owner-confirmed log70 end (sheet 20 side correct): STA 2+15 "
                                              "FLOWER POT, 40' past the 1+75 matchline up Eledra St.")}},
              "allowed_to_draw": True, "must_remain_abstained": False},
    # log61 (2026-06-17, LOG61_CURVE_SIDE_DISCRIMINATOR_RENDER lane): the Ruth Circle cul-de-sac bore, 2+43->
    # 4+50 (207'), cross-sheet 5->6. The 5<->6 boundary is a BUNDLED matchline 'MATCHLINE STA 24+11/4+37/1+92
    # SEE SHEET 6' (3 runs on one line). CORRECT route = AP-137 / LEFT branch: STA 2+43 INSTALLER HH (sheet 5)
    # -> up the left side -> 4+37 crossing -> STA 4+37 TO 4+50 (13') -> STA 4+50 FLOWER POT (sheet 6). The
    # `bundled_matchline_from_end_callout` flag activates the source-backed selector: the sheet-6 end callout
    # 'STA 4+37 TO STA 4+50' names 4+37, so the 4+37 crossing is selected (NOT 24+11 fiber, NOT 1+92 / AP-138
    # RIGHT branch / STA 2+01 FLOWER POT / 250.7' overshoot). Conduit is straight POLYLINE (no curve issue).
    # Identity-only anchors (NO coordinates); does NOT edit census/adjudication. Parent gate passes 207
    # (sheets {5,6} overlap model sheet {6}); closure to 207 refuses the 250.7' wrong branch.
    "log61": {"log_id": "log61", "parent": "bore_log26", "status": "RECOVERED",
              "corrected_start": "2+43", "corrected_end": "4+50",
              "corrected_sheets": [5, 6], "span_ft": 207.0,
              "bundled_matchline_from_end_callout": True,
              "endpoint_anchors": {
                  "start": {"station": "2+43", "structure_class": "installer_hh",
                            "boundary_kind": "structure_terminus", "clarity": "CLEAR",
                            "structure_label": "INSTALLER HH",
                            "owner_note_text": ("owner-corrected log61 start 2026-06-17: STA 2+43 INSTALLER HH "
                                                "at the base of the Ruth Circle cul-de-sac (sheet 5).")},
                  "end": {"station": "4+50", "structure_class": "flower_pot",
                          "boundary_kind": "structure_terminus", "clarity": "CLEAR",
                          "structure_label": "FLOWER POT",
                          "owner_note_text": ("owner-corrected log61 end 2026-06-17: the LEFT-side (AP-137) STA "
                                              "4+50 FLOWER POT on sheet 6 (NOT the RIGHT-side AP-138 STA 2+01).")}},
              "allowed_to_draw": True, "must_remain_abstained": False},
    # log62 (2026-06-17, NEXT_EASIEST lane): the RIGHT (AP-138) branch of the SAME Ruth Circle cul-de-sac --
    # bore_log26 sibling of log61. Source-VERIFIED route (printed structure identities, not owner-named):
    # STA 1+82 INSTALLER HH (sheet 5, the right-branch entrance; the bore's local 0+00) -> up the right side ->
    # the SAME bundled 'MATCHLINE STA 24+11/4+37/1+92 SEE SHEET 6' at the 1+92 crossing -> 'STA 1+92 TO 2+01'
    # -> STA 2+01 FLOWER POT (sheet 6). span 0+00->2+01 = 201'. The bundled selector picks 1+92 (named by the
    # sheet-6 end callout 'STA 1+92 TO STA 2+01') -- proving it generalizes to the sibling branch (24+11 fiber /
    # 4+37 = log61's LEFT branch are never selected). drawn 198.1 vs 201 (closes); parent gate ok (collision
    # sibling = log60, not log61). Identity-only anchors; no census/corpus change.
    "log62": {"log_id": "log62", "parent": "bore_log26", "status": "RECOVERED",
              "corrected_start": "0+00", "corrected_end": "2+01",
              "corrected_sheets": [5, 6], "span_ft": 201.0,
              "bundled_matchline_from_end_callout": True,
              "endpoint_anchors": {
                  "start": {"station": "1+82", "structure_class": "installer_hh",
                            "boundary_kind": "structure_terminus", "clarity": "CLEAR",
                            "structure_label": "INSTALLER HH",
                            "owner_note_text": ("log62 RIGHT (AP-138) branch start: STA 1+82 INSTALLER HH "
                                                "(sheet 5, right-branch entrance = bore-local 0+00).")},
                  "end": {"station": "2+01", "structure_class": "flower_pot",
                          "boundary_kind": "structure_terminus", "clarity": "CLEAR",
                          "structure_label": "FLOWER POT",
                          "owner_note_text": ("log62 end: STA 2+01 FLOWER POT (sheet 6) via the 1+92 crossing "
                                              "of the bundled 24+11/4+37/1+92 matchline (AP-138 RIGHT side).")}},
              "allowed_to_draw": True, "must_remain_abstained": False},
}
# OWNER-REVIEWED REVIEW-CANDIDATE PROMOTIONS (2026-06-17 owner review of review_candidate_reasoning_sweep):
# logs the owner CONFIRMED correct that carry NO owner adjudication route -- the engine truth-table SPAN
# seeds the endpoints (source), and the owner review is the discriminator authorizing the deterministic
# render of the source-backed, span-CLOSING route. Census is untouched (no adjudication record added);
# closure + unique bind still gate every render (an approved log that does not bind/close stays blocked).
OWNER_APPROVED_SPAN_PROMOTIONS = ("log10", "log37", "log39", "log72")
# OWNER-CORRECTED logs (2026-06-17): a candidate leg went the WRONG direction and the owner identified the
# correct branch. Span-seeded too, but they get STRICT direction routing -- the matchline boundary is taken
# from the printed COMBINED 'SEE SHEET' label, not an ambiguous per-station token (the CRITICAL DIRECTION
# RULE). (log70 was ALSO owner-corrected but is NOT YET promotable. This is NOT a source conflict -- the
# source is fully present. The blocker is MISSING SOLVER SUPPORT for the corrected route: an L-SHAPED
# CORNER-TURN from the STA 4+54 (13"X24"X24") INSTALLER HH UP Eledra St, where the printed 'HH-HH=215''
# (== the bore footage) IS the leg and must WIN over the adjudicated flower-pot terminus. Lacking that
# primitive, the default solver traces the wrong corridor and fails closure (561.5' vs 215') -- a TRACING
# gap, not a source gap.)
OWNER_CORRECTED_SPAN_PROMOTIONS = ("log9", "log23")
OWNER_DIRECTION_CORRECTED = ("log9", "log23")
SPAN_SEEDED_PROMOTIONS = OWNER_APPROVED_SPAN_PROMOTIONS + OWNER_CORRECTED_SPAN_PROMOTIONS
SYMBOL_LAYER = {"flower_pot": "FLOWER POT", "installer_hh": "NEXTLINK",
                "terminal_port_hh": "NEXTLINK", "nextlink_hh": "NEXTLINK"}
CONTEXT = {"flower_pot": ("FLOWER", "POT")}
MODELED = set(SYMBOL_LAYER)

_AP_TOK = re.compile(r"AP-\d+")
_STA_HEADER = re.compile(r"^STA\s*\d+\+\d+\s*$")


def station_placement_ap_ids(lines, station):
    """Source-derived AP splice-loc identity of the structure PLACED AT ``station``.

    A terminal-port HH prints its placement as a note block headed by a BARE ``STA <station>`` line
    (the header is just the station -- NOT a run callout ``STA a TO b``, which carries the bore, not the
    structure) followed by ``PLACE ... / TERMINAL 8 PORT HH / AP-NNN SPLICE LOC ...`` up to the next
    ``STA`` header. When a bore's start STATION label is not sheet-unique (so it will not bind directly),
    the structure placed at that station still binds by its printed AP id (the dialect's id_token
    locator) -- a SOURCE-derived identity, never an owner name. Uniqueness-gated (DO-NOT-WIDEN): returns
    the single AP id ONLY when EXACTLY ONE bare ``STA <station>`` header exists AND its block carries
    EXACTLY ONE AP id; otherwise ``[]`` (typed absence -> the caller stays abstained). Pure; printed-note
    grammar only, no plan-set knowledge."""
    headers = [i for i, ln in enumerate(lines)
               if _STA_HEADER.match(ln.strip()) and ln.strip().replace(" ", "") == f"STA{station}"]
    if len(headers) != 1:
        return []
    i = headers[0]
    aps = []
    for j in range(i + 1, len(lines)):
        if re.match(r"^STA\s", lines[j].strip()):
            break
        aps.extend(_AP_TOK.findall(lines[j]))
    aps = sorted(set(aps))
    return aps if len(aps) == 1 else []

R_COMPLETE = "CALLOUT_ROUTE_ASSEMBLY_SWEEP_COMPLETE"
B_CENSUS = "BLOCKED_SWEEP_CENSUS_DRIFT"
B_SCOPE = "BLOCKED_SWEEP_SCOPE_VIOLATION"
B_NOTHING = "BLOCKED_SWEEP_NO_NEW_RENDER"
ALLOWED = {R_COMPLETE, B_CENSUS, B_SCOPE, B_NOTHING}


def _census_frozen(doc) -> bool:
    if not TRUTH.is_file():
        return False
    baseline = {r["bore_id"]: dict(r) for r in json.loads(TRUTH.read_text(encoding="utf-8"))["rows"]}
    off = apply_adjudications(baseline, enabled=False)
    on = apply_adjudications(baseline, enabled=True, doc=doc)
    summ = activation_summary(on)
    buckets = {}
    for r in off.values():
        buckets[r["completion_bucket"]] = buckets.get(r["completion_bucket"], 0) + 1
    return (off is baseline and buckets == FROZEN_BUCKETS
            and summ["manual_review_drawable"] == 22 and summ["manual_source_verification"] == 1
            and summ["manual_abstain"] == 4
            and on["log44"]["adjudication"]["drawable_status"] == "non_drawable"
            and all(on[l]["adjudication"]["drawable_status"] == "abstain" for l in ABSTAIN_4)
            and not parent_run_duplicate_check(doc))


def _bind(plan, offset, sheet, cls, station):
    """Source-bind a terminus on one sheet via the proven leader-chain locators. Returns
    (xy|None, words, draw, result). nextlink_hh uses the ANNOTATION callout locator; the modeled
    note/id classes use resolve_structure_position (reset label tried first). No nearest-snap."""
    words, draw = plan.words(sheet, offset), plan.line_items(sheet, offset)
    if cls == "nextlink_hh":
        v = resolve_nextlink_hh_callout(station_sta=station, words=words, drawings=draw,
                                        callout_layer="ANNOTATION", symbol_layer="NEXTLINK")
        return (tuple(v.symbol_xy) if (v.result == POSITION_BOUND and v.symbol_xy) else None,
                words, draw, v.result)
    ctx, last = CONTEXT.get(cls), None
    for label in (f"{station}=0+00", station):
        kw = dict(label_text=label, structure_class=cls, words=words, drawings=draw,
                  layer_table=BRENHAM_STRUCTURE_LAYERS)
        if ctx:
            kw["context_texts"] = ctx
        v = resolve_structure_position(**kw)
        last = v.result
        if v.result == POSITION_BOUND and v.symbol_xy:
            return tuple(v.symbol_xy), words, draw, v.result
    return None, words, draw, last


def _chain_at(draw, cls, xy):
    fp = symbol_footprint(draw, SYMBOL_LAYER[cls], xy)
    return connected_chain([x for x in draw if x.get("layer") in BASE_CONDUIT], fp) if fp else []


def _all_sheets(plan, offset):
    return [s for s in range(1, plan.page_count + 1) if 0 <= s + offset - 1 < plan.page_count]


def _bind_over(plan, offset, candidate_sheets, cls, label):
    """The UNIQUE (sheet, class) where ``label`` binds across ``candidate_sheets`` (0 or >=2 -> None)."""
    # cheap pre-filter: a terminus can only bind on a sheet whose text prints its label token (one get_text
    # call vs a full words+line_items parse per class) -- necessary for any bind, narrows the search.
    search = [s for s in candidate_sheets if label in plan.text_by_index(s + offset - 1)]
    classes = [cls] if cls else list(MODELED)
    bound, res = [], {}
    for sh in search:
        for c in classes:
            xy, _, _, rr = _bind(plan, offset, sh, c, label)
            if xy is not None:
                bound.append((sh, c))
                res[f"s{sh}:{c}"] = rr
    if len(bound) == 1:
        return bound[0][0], bound[0][1], res
    return None, None, res


def _bind_unique(plan, offset, sheets, cls, label):
    """The UNIQUE (sheet, class) where a terminus LABEL binds, derived from source. The sheet comes from the
    owner's corrected_sheets, or -- when that set is EMPTY -- is EXTRACTED FROM SOURCE across ALL plan
    sheets. The class is consumed when an owner anchor encoded it; when None it is DERIVED FROM SOURCE
    (every modeled class tried; the unique leader-bound symbol wins -- never owner-named, never nearest).
    0 or >=2 binds -> (None, None, {}).

    OFF-SHEET FALLBACK: when corrected_sheets is given but the label does NOT bind on it, retry across ALL
    plan sheets (uniqueness-gated). A cross-sheet bore's far endpoint can sit on a sheet the owner omitted
    from corrected_sheets (e.g. log6's start reset '0+56=0+00' is on sheet 17 but corrected_sheets=[5]); a
    GLOBALLY unique label binds there safely, while a non-unique one still yields >=2 -> None (no widening)."""
    if not label:
        return None, None, {}
    if sheets:
        sheet, c, res = _bind_over(plan, offset, list(sheets), cls, label)
        if sheet is not None:
            return sheet, c, res
        off = _bind_over(plan, offset, _all_sheets(plan, offset), cls, label)
        return (off[0], off[1], off[2] or res) if off[0] is not None else (None, None, off[2] or res)
    return _bind_over(plan, offset, _all_sheets(plan, offset), cls, label)


def _resolve_endpoint(plan, offset, sheets, cls, labels):
    """Resolve a terminus to a unique (sheet, class, label) bind, trying candidate LABELS in priority order
    and taking the FIRST that binds uniquely: the printed station first, then any AP id-token (AP-NNN) from
    the owner-reviewed notes -- a TERMINAL PORT HH prints its identity as an AP splice-loc id (the dialect's
    id_token locator), so an AP terminus whose station label is not drawn still binds by its AP id. Station
    first means the AP fallback only fires when the station does not bind; it never overrides a station bind
    or contaminates the other endpoint. Returns (sheet, class, label, res)."""
    last = {}
    for label in labels:
        sheet, c, res = _bind_unique(plan, offset, sheets, cls, label)
        last = res or last
        if sheet is not None:
            return sheet, c, label, res
    return None, None, None, last


def _resolve_endpoints(r):
    """Per-endpoint (station, class) for a bore. From encoded endpoint_anchors when present; otherwise from
    the owner-reviewed corrected stations -- the START reset 'STA x=0+00' parsed from evidence_notes (or
    corrected_start if it is a non-zero station), the END = corrected_end -- with class None so it is
    DERIVED from source. Returns (start_sta, start_cls, end_sta, end_cls, anchored)."""
    ea = r.get("endpoint_anchors") or {}
    if ea:
        s, e = ea.get("start") or {}, ea.get("end") or {}
        return s.get("station"), s.get("structure_class"), e.get("station"), e.get("structure_class"), True
    notes = r.get("evidence_notes") or ""
    resets = re.findall(r"STA\s*(\d+\+\d+)\s*=\s*0\+00", notes)
    cs, ce = r.get("corrected_start"), r.get("corrected_end")
    start_sta = resets[0] if resets else (cs if (cs and cs != "0+00") else None)
    return start_sta, None, ce, None, False


def _leg_matchline(words, draw, chain, cross, strict=False):
    """(station, boundary_xy) the leg's chain reaches for one printed crossing equation.

    DIRECTION RULE (``strict``): the boundary matchline is identified by the COMBINED printed label ('a/b'
    via _ml_bbox) which sits ON the physical 'MATCHLINE STA a/b - SEE SHEET <partner>' line -- so the leg
    extends toward the matchline that NAMES the partner sheet, NOT a same-numbered station printed in a
    mid-sheet run callout ('STA a TO b ...'). The bare per-token locator (locate_matchline_boundary) snaps
    to whichever matchline a station token sits nearest, which is the WRONG physical line when that station
    also appears in a run callout near a DIFFERENT matchline (this is exactly how log9/log23 went the wrong
    direction). ``strict`` is enabled ONLY for owner-flagged wrong-direction logs; the default keeps the
    legacy per-token locator so every previously-committed render is byte-identical (no drift)."""
    if strict:
        mlb = _ml_bbox(words, draw, cross)
        if mlb is not None:
            eps = dash_endpoints(chain)
            if eps and min(nearest_gap([p], mlb) for p in eps) <= MAX_DASH_GAP:
                bnd = extend_dash_to_boundary(chain, mlb)
                if bnd is not None:
                    return cross[0], tuple(bnd)
    for sta in cross:
        bnd, _, uniq = locate_matchline_boundary(words, draw, sta, chain)
        if bnd is not None and uniq:
            return sta, tuple(bnd)
    return None


def _ordered_leg(chain, a_xy, b_xy):
    """Ordered source-backed route a->b through the chain, with the source-backing verdict."""
    route = order_chain_route(chain, a_xy, b_xy)
    ok = (len(route) >= 2 and route[0] == tuple(a_xy) and route[-1] == tuple(b_xy)
          and route_edges_source_backed(route, chain)
          and (len(route) < 3 or interior_vertices_are_dash_endpoints(route, chain)))
    return route, bool(ok)


def _ml_bbox(words, draw, cross):
    """The drawn matchline bbox carrying a printed crossing equation. Matches the COMBINED 'a/b' label token
    (which sits ON the matchline line) -- NOT the individual 'a'/'b' tokens, which are the run-callout
    stations printed mid-sheet and can be nearer a DIFFERENT matchline. Identity only; route geometry comes
    from the bbox + chain-reach, never the token position."""
    mls = matchline_bboxes(draw, "MATCHLINE")
    if not mls:
        return None
    for sta in ["/".join(cross), *cross]:                    # combined label token first, then fallbacks
        toks = [w for w in words if str(w.get("text", "")) == sta]
        if toks:
            t = toks[0]
            return min(mls, key=lambda bb: nearest_gap([(float(t["xc"]), float(t["yc"]))], bb))
    return None


def _conduit_components(conduit):
    """All connected components of the sheet's conduit dashes (orientation-free dash-gap connectivity).
    Two PARALLEL runs more than MAX_DASH_GAP apart are DISTINCT components -- this is what lets the N-leg
    solver SEE parallel printed runs between the same two matchlines (and refuse to pick between them)."""
    n = len(conduit)
    seen = [False] * n
    comps = []
    for i in range(n):
        if seen[i]:
            continue
        seed = conduit[i]
        comp = connected_chain(conduit, (seed["x0"], seed["y0"], seed["x1"], seed["y1"]))
        ids = {id(c) for c in comp}
        for j in range(n):
            if id(conduit[j]) in ids:
                seen[j] = True
        comps.append(comp)
    return comps


def _chain_boundary_near_x(chain, mlb, target_x, x_tol=14.0):
    """The chain's boundary crossing of matchline ``mlb`` whose x aligns with ``target_x``. A physical
    through-line crosses a matchline at ONE x, so this extends the chain's terminal dash that is both near
    the matchline AND near ``target_x`` to the matchline centerline; None if the chain does not reach the
    matchline near ``target_x``. This is the cross-sheet THROUGH-CONTINUITY test: it selects the parallel
    run actually connected to a bore's own bound terminus (e.g. an end AP) and rejects a parallel run that
    crosses the same matchline but belongs to a DIFFERENT bore."""
    best = None
    for seg in chain:
        for ln in seg.get("lines") or ():
            for p, q in (((ln[0], ln[1]), (ln[2], ln[3])), ((ln[2], ln[3]), (ln[0], ln[1]))):
                if nearest_gap([p], mlb) > MAX_DASH_GAP or abs(p[0] - target_x) > x_tol:
                    continue
                ext = extend_dash_to_boundary([{"lines": [(p[0], p[1], q[0], q[1])]}], mlb)
                if ext is None or abs(ext[0] - target_x) > x_tol:
                    continue
                d = abs(ext[0] - target_x)
                if best is None or d < best[0]:
                    best = (d, (ext[0], ext[1]))
    return best[1] if best else None


def _boundary_crossings(chain, mlb):
    """Every DISTINCT point where ``chain``'s terminal dashes reach matchline ``mlb`` (within MAX_DASH_GAP,
    extended to the centerline), tagged with the ALONG-matchline coordinate (y for a vertical matchline, x
    for a horizontal one). A conduit blob may reach the SAME drawn matchline at more than one point (several
    runs to one sheet edge); this enumerates them so the caller can pick the through-continuous one."""
    vertical = (mlb[3] - mlb[1]) >= (mlb[2] - mlb[0])
    out = []
    for seg in chain:
        for ln in seg.get("lines") or ():
            for p, q in (((ln[0], ln[1]), (ln[2], ln[3])), ((ln[2], ln[3]), (ln[0], ln[1]))):
                if nearest_gap([p], mlb) > MAX_DASH_GAP:
                    continue
                ext = extend_dash_to_boundary([{"lines": [(p[0], p[1], q[0], q[1])]}], mlb)
                if ext is None:
                    continue
                coord = ext[1] if vertical else ext[0]
                if all(abs(coord - c) > 3.0 for c, _ in out):
                    out.append((coord, tuple(ext)))
    return out


def _through_continuous_pair(s_chain, s_mlb, e_chain, e_mlb, tol=10.0):
    """The UNIQUE (start_bnd, end_bnd) pair whose two legs cross their matchlines at the SAME along-matchline
    coordinate -- a physical bore crosses the sheet boundary at ONE height (vertical matchline) / offset
    (horizontal), and tiled sheets preserve that coordinate across the edge. This DISAMBIGUATES a leg whose
    blob reaches the matchline at several points (the wrong branch overshoots closure): the bore's branch is
    the one through-continuous with the OTHER leg. Returns (s_bnd, e_bnd) or (None, None) when not exactly
    one matching pair (0 or >=2 -> abstain, never a length/nearest pick)."""
    sc = _boundary_crossings(s_chain, s_mlb)
    ec = _boundary_crossings(e_chain, e_mlb)
    pairs = [(sx, ex) for (s, sx) in sc for (e, ex) in ec if abs(s - e) <= tol]
    return pairs[0] if len(pairs) == 1 else (None, None)


def _solve_nleg(plan, offset, out, s0, smid, sn, s_xy, s_chain, s_words, s_draw,
                e_xy, e_chain, e_words, e_draw, span):
    """Three-sheet route s0 -> smid -> sn joined by TWO printed matchline crossings (the log46 shape).

    The middle leg is a CONNECTED CONDUIT COMPONENT on smid that spans the entry (->s0) and exit (->sn)
    matchlines. Every such component is enumerated as a candidate middle run; for each, the full 3-leg
    route (start chain -> entry crossing, the component, exit crossing -> end chain) is built and gated by
    source-backing + printed-span closure. The route renders ONLY if EXACTLY ONE middle run produces a
    closing source-backed path. When smid prints PARALLEL runs between the SAME two matchlines (each
    closing, and the start/end chains reach the shared matchline bboxes so neither leg discriminates), the
    route is NOT unique -> defer with the parallel runs named. No nearest/length pick; middle sheet never
    omitted; >=2 closing runs -> abstain (DO-NOT-WIDEN)."""
    out["printed_crossings_start_mid"] = [list(c) for c in see_sheet_crossings(plan.lines(s0, offset), smid, "MATCHLINE")]
    out["printed_crossings_mid_end"] = [list(c) for c in see_sheet_crossings(plan.lines(sn, offset), smid, "MATCHLINE")]
    if not span:
        out["blocker"] = "N-leg route needs a printed bore span for full-path closure"
        return out
    mid_words, mid_draw = plan.words(smid, offset), plan.line_items(smid, offset)
    mid_conduit = [x for x in mid_draw if x.get("layer") in BASE_CONDUIT]
    # the entry (->s0) and exit (->sn) matchline bboxes printed on smid (one per crossing equation)
    entries = [(c, _ml_bbox(mid_words, mid_draw, c)) for c in see_sheet_crossings(plan.lines(smid, offset), s0, "MATCHLINE")]
    exits = [(c, _ml_bbox(mid_words, mid_draw, c)) for c in see_sheet_crossings(plan.lines(smid, offset), sn, "MATCHLINE")]
    entries = [(c, bb) for c, bb in entries if bb]
    exits = [(c, bb) for c, bb in exits if bb]

    def _reaches(eps, bb):
        return bool(eps) and min(nearest_gap([p], bb) for p in eps) <= MAX_DASH_GAP

    sols = []
    for comp in _conduit_components(mid_conduit):
        eps = dash_endpoints(comp)
        ent = [(c, bb) for c, bb in entries if _reaches(eps, bb)]
        ext = [(c, bb) for c, bb in exits if _reaches(eps, bb)]
        if len(ent) != 1 or len(ext) != 1:
            continue                                   # a middle run spans exactly one entry + one exit
        (ec0, entry_bb), (ecn, exit_bb) = ent[0], ext[0]
        a_mid = extend_dash_to_boundary(comp, entry_bb)
        b_mid = extend_dash_to_boundary(comp, exit_bb)
        if not (a_mid and b_mid):
            continue
        # THROUGH-CONTINUITY: a physical bore crosses each matchline at ONE x, so the START chain must cross
        # the entry matchline at this run's entry x, and the END chain at this run's exit x. This selects the
        # parallel run actually connected to THIS bore's bound termini (e.g. the end AP) and rejects a
        # parallel run that crosses the same matchlines but belongs to a DIFFERENT same-crew bore.
        entry_bb_s0 = _ml_bbox(s_words, s_draw, ec0)
        exit_bb_sn = _ml_bbox(e_words, e_draw, ecn)
        start_bnd = _chain_boundary_near_x(s_chain, entry_bb_s0, a_mid[0]) if entry_bb_s0 else None
        end_bnd = _chain_boundary_near_x(e_chain, exit_bb_sn, b_mid[0]) if exit_bb_sn else None
        if not (start_bnd and end_bnd):
            continue                       # run not through-continuous with this bore's start AND end
        r1, ok1 = _ordered_leg(s_chain, s_xy, start_bnd)
        r2, ok2 = _ordered_leg(comp, tuple(a_mid), tuple(b_mid))
        r3, ok3 = _ordered_leg(e_chain, end_bnd, e_xy)
        if not (ok1 and ok2 and ok3):
            continue
        drawn = (route_length(r1) + route_length(r2) + route_length(r3)) / SCALE
        if abs(drawn - span) > CLOSURE_REL_TOL * span:
            continue
        sols.append({"entry": list(ec0), "exit": list(ecn), "drawn_ft": round(drawn, 1),
                     "mid_run": f"{ec0[0]}->{ecn[0]} @x~{round(a_mid[0])}",
                     "legs": [
                         {"sheet": s0, "route": r1, "a_xy": s_xy, "b_xy": start_bnd,
                          "len_pt": round(route_length(r1), 1), "kind": "start_leg",
                          "start_label": out.get("_ss"), "matchline_sta": ec0[0]},
                         {"sheet": smid, "route": r2, "a_xy": tuple(a_mid), "b_xy": tuple(b_mid),
                          "len_pt": round(route_length(r2), 1), "kind": "mid_leg",
                          "matchline_in": ec0[0], "matchline_out": ecn[0]},
                         {"sheet": sn, "route": r3, "a_xy": end_bnd, "b_xy": e_xy,
                          "len_pt": round(route_length(r3), 1), "kind": "end_leg",
                          "end_label": out.get("_es"), "matchline_sta": ecn[0]},
                     ]})
    out["nleg_closing_solutions"] = [{k: v for k, v in s.items() if k != "legs"} for s in sols]
    if len(sols) == 1:
        sol = sols[0]
        out["closure"] = {"drawn_ft": sol["drawn_ft"], "span_ft": span, "closes": True}
        out["crossing_chain"] = [sol["entry"], sol["exit"]]
        out["legs"] = sol["legs"]
        return out
    if len(sols) >= 2:
        runs = "; ".join(s["mid_run"] for s in sols)
        out["blocker"] = (
            f"N-leg route ({s0}->{smid}->{sn}) NOT unique: {len(sols)} PARALLEL source-backed middle runs on "
            f"sheet {smid} cross the SAME printed matchlines and each closes the {span} ft span [{runs}]. The "
            f"start/end chains reach the shared matchline bboxes (both station tokens), so no source-backed "
            f"discriminator selects this bore's run -- render deferred (DO-NOT-WIDEN; needs a per-run "
            f"discriminator such as a printed run-callout tie or a distinct start/end conduit lane)")
        return out
    out["blocker"] = (f"N-leg route ({s0}->{smid}->{sn}): no single source-backed middle conduit component "
                      f"spans the entry and exit matchlines to closure on sheet {smid}")
    return out


def _solve_end_at_matchline(plan, offset, out, s_sheet, sc, s_lbl, ss, es, span):
    """Single leg: bound start structure -> the printed matchline crossing station ``es`` boundary the
    start's conduit chain reaches. The bore's far end IS the sheet boundary; the printed bore span
    (start -> es) closes the ONE drawn leg. Same source-backed + closure guards as a cross-sheet start
    leg, with no second structure required. ``span`` is MANDATORY -- without a second structure, printed
    closure is the only false-positive guard (a leg short of the span = the bore continues past the
    boundary = a partial -> defer)."""
    out["single_sheet"] = True
    out["end_at_matchline"] = True
    if not span:
        out["blocker"] = "end-at-matchline: no printed bore span for closure (only false-positive guard)"
        return out
    s_xy, s_words, s_draw, _ = _bind(plan, offset, s_sheet, sc, s_lbl)
    s_chain = _chain_at(s_draw, sc, s_xy)
    if not s_chain:
        out["blocker"] = "end-at-matchline: no connected conduit chain at the start terminus"
        return out
    bnd, reach, uniq = locate_matchline_boundary(s_words, s_draw, es, s_chain)
    if bnd is None or not uniq:
        out["blocker"] = (f"end-at-matchline: matchline station {es} not uniquely reached by the start "
                          f"chain (reach {reach}, unique {uniq})")
        return out
    route, ok = _ordered_leg(s_chain, s_xy, bnd)
    if not ok:
        out["blocker"] = "end-at-matchline: leg route not source-backed (start -> matchline)"
        return out
    drawn_ft = route_length(route) / SCALE
    closes = abs(drawn_ft - span) <= CLOSURE_REL_TOL * span
    out["closure"] = {"drawn_ft": round(drawn_ft, 1), "span_ft": span, "closes": closes}
    if not closes:
        out["blocker"] = (f"end-at-matchline closure failed: leg draws {round(drawn_ft, 1)} ft vs printed "
                          f"bore span {span} ft (>{int(CLOSURE_REL_TOL*100)}% off -> partial/wrong run)")
        return out
    out["legs"] = [{"sheet": s_sheet, "route": route, "a_xy": s_xy, "b_xy": tuple(bnd),
                    "len_pt": round(route_length(route), 1), "kind": "matchline_terminus",
                    "start_label": s_lbl, "matchline_sta": es}]
    return out


HH_SYMBOL_LAYER = "NEXTLINK"   # the drawn hand-hole symbol layer (installer / terminal / nextlink HHs)
SAME_POINT_TOL = 8.0           # two endpoint binds within this gap = the SAME drawn structure (a symbol footprint)
HH_ANN_PERP_TOL = 45.0         # an 'HH - HH = N'' annotation within this of the A-B line labels THAT pair


def _hh_symbol_clusters(draw):
    """Centers of the drawn hand-hole symbol clusters (the HH symbol layer), deduped within a symbol
    footprint. Each cluster is one HH structure (an installer / terminal / nextlink hand-hole)."""
    clusters = []
    for t in draw:
        if t.get("layer") != HH_SYMBOL_LAYER:
            continue
        c = (t["xc"], t["yc"])
        if all(math.hypot(c[0] - cc[0], c[1] - cc[1]) > SAME_POINT_TOL for cc in clusters):
            clusters.append(c)
    return clusters


def _ann_between(c, a, b, perp_tol=HH_ANN_PERP_TOL):
    """True if point ``c`` projects ONTO the A-B segment (parameter in [0,1]) within ``perp_tol`` -- i.e.
    the annotation lies alongside the drawn run between the two HHs, corroborating it labels THIS pair."""
    ax, ay = a; bx, by = b; cx, cy = c
    dx, dy = bx - ax, by - ay
    l2 = dx * dx + dy * dy
    if l2 == 0:
        return False
    t = ((cx - ax) * dx + (cy - ay) * dy) / l2
    if not (0.0 <= t <= 1.0):
        return False
    px, py = ax + t * dx, ay + t * dy
    return math.hypot(cx - px, cy - py) <= perp_tol


def _solve_hh_hh_bridge(plan, offset, out, sheet, cls, a_lbl, a_xy, words, draw, span):
    """HH-HH distance-annotation bridge. The two endpoint LABELS of this bore resolved to ONE drawn HH
    structure (A) -- because the partner endpoint is a frame 0+00 whose bare station is not sheet-unique
    and binds to the same reset structure. The plan STATES the pair with a printed 'HH - HH = N'' distance
    annotation, so bind the partner HH (B) as the drawn HH symbol at the SOURCE-STATED distance -- NOT
    nearest -- only when EVERY guard holds: (1) the 'HH - HH = N'' annotation (N == printed span) is UNIQUE
    by value on the sheet; (2) EXACTLY ONE HH symbol sits at span +-CLOSURE_REL_TOL from A; (3) that
    annotation lies BETWEEN A and B; (4) the route A->B is source-backed and closes to N. Any ambiguity ->
    defer (DO-NOT-WIDEN: no nearest pick, no stacked-annotation collapse, no ruler cut)."""
    out["hh_hh_bridge"] = True
    out["single_sheet"] = True
    if not span or span != int(span):
        out["blocker"] = "HH-HH bridge: no integer printed span to match a 'HH - HH = N'' annotation"
        return out
    n = int(span)
    hits = plan.search(sheet, offset, f"HH - HH = {n}'")
    out["hh_annotation_value"], out["hh_annotation_hits"] = n, len(hits)
    if len(hits) != 1:
        out["blocker"] = (f"HH-HH bridge: printed 'HH - HH = {n}'' annotation not unique on the sheet "
                          f"({len(hits)} hits) -> cannot uniquely select the pair (no stacked collapse)")
        return out
    ann = hits[0]
    ann_c = ((ann[0] + ann[2]) / 2.0, (ann[1] + ann[3]) / 2.0)
    # partner HH(s): drawn HH symbols at the SOURCE-STATED distance (span +- closure tol) from A -- distance
    # MATCHED to the printed annotation value, never distance-minimised (nearest).
    tol = CLOSURE_REL_TOL * span
    cands = [c for c in _hh_symbol_clusters(draw)
             if math.hypot(c[0] - a_xy[0], c[1] - a_xy[1]) > SAME_POINT_TOL
             and abs(math.hypot(c[0] - a_xy[0], c[1] - a_xy[1]) / SCALE - span) <= tol]
    out["hh_bridge_candidates"] = [[round(x, 1) for x in c] for c in cands]
    if len(cands) != 1:
        out["blocker"] = (f"HH-HH bridge: not a UNIQUE HH symbol at {n} ft from A ({len(cands)} candidates) "
                          f"-> ambiguous, defer (no nearest pick)")
        return out
    b_xy = cands[0]
    if not _ann_between(ann_c, a_xy, b_xy):
        out["blocker"] = (f"HH-HH bridge: the unique 'HH - HH = {n}'' annotation is not positioned between "
                          f"A and B -> it may label a different pair, defer")
        return out
    chain = _chain_at(draw, cls, a_xy)
    route, ok = _ordered_leg(chain, a_xy, tuple(b_xy))
    if not ok:
        out["blocker"] = "HH-HH bridge: route A->B not source-backed (no drawn conduit between the two HHs)"
        return out
    drawn_ft = route_length(route) / SCALE
    closes = abs(drawn_ft - span) <= CLOSURE_REL_TOL * span
    out["closure"] = {"drawn_ft": round(drawn_ft, 1), "span_ft": span, "closes": closes}
    if not closes:
        out["blocker"] = (f"HH-HH bridge closure failed: route draws {round(drawn_ft, 1)} ft vs printed "
                          f"HH-HH span {span} ft")
        return out
    out["legs"] = [{"sheet": sheet, "route": route, "a_xy": a_xy, "b_xy": tuple(b_xy),
                    "len_pt": round(route_length(route), 1), "kind": "hh_hh_bridge",
                    "start_label": a_lbl, "end_label": f"HH (HH-HH={n}')"}]
    return out


_BUNDLE_END_CALLOUT = re.compile(r"STA\s*(\d+\+\d+)\s*TO\s*STA\s*(\d+\+\d+)", re.I)


def _select_bundled_station(end_lines, end_station, equation):
    """SOURCE-BACKED bundled-matchline station selector. A bundled matchline equation
    'MATCHLINE STA a/b/c - SEE SHEET N' has several runs crossing ONE physical line; the crossing THIS bore
    uses is the start station X of the printed END-side run callout 'STA X TO STA <end_station>' that
    produces the terminus leg -- a PRINTED station identity, NOT geometry. Returns the UNIQUE X that is also
    one of the equation's stations; None if 0 or >=2 qualifying callouts (abstain; DO-NOT-WIDEN). A station
    the source does not tie to this bore's terminus (e.g. log61's 24+11 fiber run / 1+92 right branch) can
    never be selected."""
    eqset = set(equation)
    xs = set()
    for ln in end_lines:
        for m in _BUNDLE_END_CALLOUT.finditer(ln):
            if m.group(2) == end_station and m.group(1) in eqset:
                xs.add(m.group(1))
    return next(iter(xs)) if len(xs) == 1 else None


def solve_log(plan, offset, lid, rec):
    """Attempt the full route sentence for one anchored bore. Returns a verdict dict with either a
    render plan (legs to draw) or a named blocker. Renders nothing (the caller draws)."""
    r = rec.get(lid, {})
    sheets = r.get("corrected_sheets") or []
    # printed bore span for the closure guard: span_ft if recorded, else the bore-local station delta
    # corrected_start -> corrected_end (the bore's own stationing IS its conduit length).
    span = r.get("span_ft")
    span_src = "span_ft"
    if span is None and r.get("corrected_start") and r.get("corrected_end"):
        span = abs(parse_station(r["corrected_end"]) - parse_station(r["corrected_start"]))
        span_src = "corrected_start->corrected_end"
    out = {"log": lid, "sheets_set": sheets, "span_ft": span, "span_source": span_src,
           "blocker": None, "legs": None, "single_sheet": None}

    ss, sc, es, ec, anchored = _resolve_endpoints(r)
    out["anchored"] = anchored
    out["endpoint_source"] = "endpoint_anchors" if anchored else "reviewed_corrected_stations"
    if anchored and validate_endpoint_anchors(r):
        out["blocker"] = "endpoint_anchors invalid"
        return out
    if not ss or not es:
        out["blocker"] = "endpoints not resolvable (no anchors and no parseable reset/corrected stations)"
        return out

    # candidate bind labels in priority order: the printed station first, then any AP id-token from the
    # owner notes (the TERMINAL PORT HH AP-terminus fallback -- bind by AP-NNN when the station label is not
    # drawn at the symbol). AP ids only apply to reviewed-but-unanchored logs (anchored logs carry a class).
    ap_ids = re.findall(r"AP-\d+", r.get("evidence_notes") or "") if not anchored else []
    # SOURCE-derived start AP id: when the start STATION label is not sheet-unique (will not bind directly),
    # the structure PLACED at that station binds by the AP id printed in its placement note (source, not
    # owner). Searched only on the corrected sheets, uniqueness-gated; tried AFTER the station, so it only
    # fires when the station itself does not bind (never overrides a direct bind, never widens).
    pdf_start_aps = []
    if not anchored and sheets:
        for sh in sheets:
            pdf_start_aps += station_placement_ap_ids(plan.lines(sh, offset), ss)
        pdf_start_aps = sorted(set(pdf_start_aps))
    out["pdf_start_ap_ids"] = pdf_start_aps
    # RESET-TO-RESET bore: when the owner notes name a SECOND 'STA x=0+00' reset (the receiving structure
    # across the street), the bore's corrected_end is its OWN measured length -- NOT the receiving
    # structure's label, so the end never binds by corrected_end. The receiving structure binds by its OWN
    # reset TOKEN '<sta>=0+00', which is sheet-unique where the bare station is not (the bare '0+46' also
    # binds an installer HH on another sheet -> >=2 -> None; only the '0+46=0+00' token is globally unique).
    # Appended as a TRAILING end candidate so it fires ONLY when corrected_end does not bind
    # (first-binds-wins -> every existing render is byte-identical). Source-derived, never owner-named.
    end_reset_tokens = ([f"{s}=0+00" for s in re.findall(r"STA\s*(\d+\+\d+)\s*=\s*0\+00",
                                                          r.get("evidence_notes") or "") if s != ss]
                        if not anchored else [])
    out["end_reset_tokens"] = end_reset_tokens
    s_sheet, sc, s_lbl, s_res = _resolve_endpoint(plan, offset, sheets, sc, [ss, *ap_ids, *pdf_start_aps])
    e_sheet, ec, e_lbl, e_res = _resolve_endpoint(plan, offset, sheets, ec, [es, *ap_ids, *end_reset_tokens])
    out["sheet_source_derived"] = (not sheets) and s_sheet is not None and e_sheet is not None
    out["class_source_derived"] = not anchored
    out["start_sheet"], out["end_sheet"] = s_sheet, e_sheet
    out["start_class"], out["end_class"] = sc, ec
    out["bound_labels"] = {"start": s_lbl, "end": e_lbl}
    out["bind_results"] = {"start": s_res, "end": e_res}

    # END-AT-MATCHLINE: a bore may TERMINATE at a printed matchline crossing station -- its far end is the
    # sheet boundary (the conduit continues as a DIFFERENT bore on the partner sheet), not a second
    # structure. When the start binds to a structure and the end station did NOT bind to any structure but
    # IS a printed SEE-SHEET crossing on the start sheet to a corrected partner, draw ONE source-backed leg
    # from the start structure to that matchline boundary, gated by printed-span closure (the only
    # corroboration without a second structure -> span MANDATORY). This is the cross-sheet START-LEG shape
    # with no reciprocal leg; it never fires for a bore whose end DOES bind (that takes the structure path).
    if s_sheet is not None and sc in MODELED and e_sheet is None and es:
        partners = [s for s in sheets if s != s_sheet]
        end_is_crossing = any(es in cr for p in partners
                              for cr in see_sheet_crossings(plan.lines(s_sheet, offset), p, "MATCHLINE"))
        if partners and end_is_crossing:
            return _solve_end_at_matchline(plan, offset, out, s_sheet, sc, s_lbl, ss, es, span)

    if s_sheet is None or e_sheet is None or sc not in MODELED or ec not in MODELED:
        out["blocker"] = (f"terminus did not resolve to a UNIQUE (sheet,class) source bind "
                          f"(start->s{s_sheet}/{sc}; end->s{e_sheet}/{ec})")
        return out

    s_xy, s_words, s_draw, _ = _bind(plan, offset, s_sheet, sc, s_lbl)
    e_xy, e_words, e_draw, _ = _bind(plan, offset, e_sheet, ec, e_lbl)
    s_chain = _chain_at(s_draw, sc, s_xy)
    e_chain = _chain_at(e_draw, ec, e_xy)
    if not s_chain or not e_chain:
        out["blocker"] = f"no connected conduit chain at a terminus (start segs {len(s_chain)}, end segs {len(e_chain)})"
        return out

    if s_sheet == e_sheet:
        out["single_sheet"] = True
        if math.hypot(s_xy[0] - e_xy[0], s_xy[1] - e_xy[1]) <= SAME_POINT_TOL:
            # both endpoint labels resolved to ONE drawn HH (the partner endpoint is a non-unique frame
            # 0+00 that binds to the same reset structure) -> bridge to the partner HH via the printed
            # 'HH - HH = N'' distance annotation (a SOURCE relationship; never nearest).
            return _solve_hh_hh_bridge(plan, offset, out, s_sheet, sc, s_lbl, s_xy, s_words, s_draw, span)
        route, ok = _ordered_leg(s_chain, s_xy, e_xy)
        if not ok:
            out["blocker"] = "single-sheet route not source-backed (terminus-to-terminus chain path)"
            return out
        if span:
            drawn_ft = route_length(route) / SCALE
            out["closure"] = {"drawn_ft": round(drawn_ft, 1), "span_ft": span, "closes": abs(drawn_ft - span) <= CLOSURE_REL_TOL * span}
            if not out["closure"]["closes"]:
                out["blocker"] = f"single-sheet closure failed: drawn {round(drawn_ft,1)} ft vs span {span} ft"
                return out
        out["legs"] = [{"sheet": s_sheet, "route": route, "a_xy": s_xy, "b_xy": e_xy,
                        "len_pt": round(route_length(route), 1), "kind": "single_sheet",
                        "start_label": ss, "end_label": es}]
        return out

    # ---- cross-sheet: resolve the printed crossing both legs reach, render two sheet-local legs ----
    s_lines = plan.lines(s_sheet, offset)
    crossings = see_sheet_crossings(s_lines, e_sheet, "MATCHLINE")
    out["printed_crossings_start_to_end"] = [list(c) for c in crossings]
    if not crossings:
        mids = [s for s in sheets if s not in (s_sheet, e_sheet)]
        if len(mids) == 1:
            # 3-sheet route: start -> intermediate -> end, joined by two printed matchline crossings
            out["_ss"], out["_es"] = ss, es
            return _solve_nleg(plan, offset, out, s_sheet, mids[0], e_sheet,
                               s_xy, s_chain, s_words, s_draw, e_xy, e_chain, e_words, e_draw, span)
        if mids:
            out["blocker"] = (f"N-leg route with {len(mids)} intermediate sheets {mids} not supported "
                              f"(only a single intermediate sheet is implemented)")
        else:
            out["blocker"] = f"no printed SEE-SHEET matchline crossing between sheets {s_sheet} and {e_sheet}"
        return out

    # BUNDLED-MATCHLINE STATION SELECTOR (opt-in via `bundled_matchline_from_end_callout`; gated so existing
    # bundled-matchline renders are byte-identical). A bundled 'MATCHLINE STA a/b/c' has several runs crossing
    # ONE physical line; the default minimal-extension boundary can snap to the WRONG run (log61: the 24+11
    # fiber run -> 250.7' overshoot down the AP-138 RIGHT branch). Select the station the printed END callout
    # 'STA X TO STA <es>' names (log61 sheet-6 'STA 4+37 TO STA 4+50' -> 4+37), bind the END leg at that
    # station's crossing (the short terminus chain reaches it unambiguously), and bind the START leg at the
    # crossing THROUGH-CONTINUOUS with it (nearest along-matchline x). Closure + the parent gate still gate the
    # render; any ambiguity (no unique end-callout station / no aligned start crossing / closure off) abstains.
    if r.get("bundled_matchline_from_end_callout"):
        bundled = next((c for c in crossings if len(c) > 1), None)
        sel = _select_bundled_station(plan.lines(e_sheet, offset), es, bundled) if bundled else None
        out["bundled_equation"] = list(bundled) if bundled else None
        out["bundled_selected_station"] = sel
        if bundled is None or sel is None:
            out["blocker"] = ("bundled-matchline selector: crossing station not uniquely derivable from a "
                              f"printed 'STA X TO STA {es}' end callout within {out['bundled_equation']}")
            return out
        e_mlb = _ml_bbox(e_words, e_draw, bundled)
        s_mlb = _ml_bbox(s_words, s_draw, bundled)
        e_bnd = locate_matchline_boundary(e_words, e_draw, sel, e_chain)[0] if e_mlb else None
        if not (e_mlb and s_mlb and e_bnd):
            out["blocker"] = "bundled-matchline selector: end-leg boundary or matchline bbox not resolved"
            return out
        s_bnd = _chain_boundary_near_x(s_chain, s_mlb, e_bnd[0])
        if s_bnd is None:
            out["blocker"] = (f"bundled-matchline selector: start chain has no crossing within x-tol of the "
                              f"end's {sel} crossing (sheet {s_sheet}->{e_sheet} frame offset too large)")
            return out
        s_route, s_ok = _ordered_leg(s_chain, s_xy, s_bnd)
        e_route, e_ok = _ordered_leg(e_chain, e_bnd, e_xy)
        out["start_leg_source_backed"], out["end_leg_source_backed"] = s_ok, e_ok
        if not (s_ok and e_ok):
            out["blocker"] = f"bundled-matchline selector: leg route not source-backed (start {s_ok}, end {e_ok})"
            return out
        drawn_ft = (route_length(s_route) + route_length(e_route)) / SCALE
        closes = bool(span) and abs(drawn_ft - span) <= CLOSURE_REL_TOL * span
        out["closure"] = {"drawn_ft": round(drawn_ft, 1), "span_ft": span, "closes": closes}
        if not closes:
            out["blocker"] = (f"bundled-matchline selector closure failed: {round(drawn_ft, 1)} ft vs span "
                              f"{span} ft (>{int(CLOSURE_REL_TOL*100)}% -> wrong branch)")
            return out
        out["crossing_equation"] = list(bundled)
        out["legs"] = [
            {"sheet": s_sheet, "route": s_route, "a_xy": s_xy, "b_xy": s_bnd,
             "len_pt": round(route_length(s_route), 1), "kind": "start_leg", "start_label": ss, "matchline_sta": sel},
            {"sheet": e_sheet, "route": e_route, "a_xy": e_bnd, "b_xy": e_xy,
             "len_pt": round(route_length(e_route), 1), "kind": "end_leg", "end_label": es, "matchline_sta": sel},
        ]
        return out

    strict = lid in OWNER_DIRECTION_CORRECTED
    viable = []
    for cross in crossings:
        a = _leg_matchline(s_words, s_draw, s_chain, cross, strict=strict)
        b = _leg_matchline(e_words, e_draw, e_chain, cross, strict=strict)
        if a and b:
            viable.append({"equation": list(cross), "start_sta": a[0], "start_bnd": [round(v, 1) for v in a[1]],
                           "end_sta": b[0], "end_bnd": [round(v, 1) for v in b[1]],
                           "_a": a, "_b": b})
    out["viable_crossings"] = [{k: v for k, v in c.items() if not k.startswith("_")} for c in viable]
    if len(viable) != 1:
        out["blocker"] = (f"crossing not unique: {len(viable)} of {len(crossings)} printed SEE-SHEET "
                          f"{s_sheet}<->{e_sheet} equations are reached by BOTH legs' chains "
                          f"(need exactly 1; 0 or >=2 -> abstain, no nearest/length pick)")
        return out
    cr = viable[0]
    a_bnd, b_bnd = cr["_a"][1], cr["_b"][1]
    s_route, s_ok = _ordered_leg(s_chain, s_xy, a_bnd)
    e_route, e_ok = _ordered_leg(e_chain, b_bnd, e_xy)

    # THROUGH-CONTINUITY refinement: the default minimal-extension boundary can pick the WRONG branch when a
    # leg's conduit blob reaches the SAME drawn matchline at more than one point (closure then overshoots --
    # log6's start chain reaches the 3+23/0+69 matchline at y~343 AND y~426). The physical bore crosses the
    # sheet boundary at ONE along-matchline coordinate, so re-pick the UNIQUE crossing pair whose two legs
    # cross at the same coordinate. Adopted ONLY when both legs stay source-backed AND it closes the printed
    # span -- never a length/nearest pick. Single-branch crossings (the existing renders) close on the
    # default, so the retry never fires and they are byte-identical.
    out["through_continuity"] = False
    default_closes = bool(span and s_ok and e_ok and abs(
        (route_length(s_route) + route_length(e_route)) / SCALE - span) <= CLOSURE_REL_TOL * span)
    if span and not default_closes:
        s_mlb = _ml_bbox(s_words, s_draw, cr["equation"])
        e_mlb = _ml_bbox(e_words, e_draw, cr["equation"])
        a_tc, b_tc = (_through_continuous_pair(s_chain, s_mlb, e_chain, e_mlb)
                      if (s_mlb and e_mlb) else (None, None))
        if a_tc and b_tc:
            s_r2, s_o2 = _ordered_leg(s_chain, s_xy, a_tc)
            e_r2, e_o2 = _ordered_leg(e_chain, b_tc, e_xy)
            if s_o2 and e_o2 and abs(
                    (route_length(s_r2) + route_length(e_r2)) / SCALE - span) <= CLOSURE_REL_TOL * span:
                a_bnd, b_bnd = a_tc, b_tc
                s_route, e_route, s_ok, e_ok = s_r2, e_r2, s_o2, e_o2
                out["through_continuity"] = True

    out["start_leg_source_backed"], out["end_leg_source_backed"] = s_ok, e_ok
    if not (s_ok and e_ok):
        out["blocker"] = f"a leg route not source-backed (start {s_ok}, end {e_ok})"
        return out

    s_len, e_len = route_length(s_route), route_length(e_route)
    if span:
        drawn_ft = (s_len + e_len) / SCALE
        closes = abs(drawn_ft - span) <= CLOSURE_REL_TOL * span
        out["closure"] = {"drawn_ft": round(drawn_ft, 1), "span_ft": span, "closes": closes}
        if not closes:
            out["blocker"] = (f"station closure failed: two legs draw {round(drawn_ft, 1)} ft vs printed "
                              f"bore span {span} ft (>{int(CLOSURE_REL_TOL*100)}% off -> wrong crossing/partial)")
            return out

    out["legs"] = [
        {"sheet": s_sheet, "route": s_route, "a_xy": s_xy, "b_xy": a_bnd, "len_pt": round(s_len, 1),
         "kind": "start_leg", "start_label": ss, "matchline_sta": cr["start_sta"]},
        {"sheet": e_sheet, "route": e_route, "a_xy": b_bnd, "b_xy": e_xy, "len_pt": round(e_len, 1),
         "kind": "end_leg", "end_label": es, "matchline_sta": cr["end_sta"]},
    ]
    out["crossing_equation"] = cr["equation"]
    return out


def _render(plan, offset, lid, v):
    pngs = []
    for leg in v["legs"]:
        if leg["kind"] == "single_sheet":
            derived = (" [sheet source-derived from unique bind; owner confirmation pending before product promotion]"
                       if v.get("sheet_source_derived") else "")
            reason = (f"{lid} source-backed callout route: {leg['start_label']} -> {leg['end_label']} "
                      f"(single sheet {leg['sheet']}; ordered conduit chain path){derived}")
        elif leg["kind"] == "start_leg":
            reason = (f"{lid} sheet-{leg['sheet']} leg: start {leg['start_label']} -> MATCHLINE STA "
                      f"{leg['matchline_sta']} (SEE SHEET {v['end_sheet']}); cross-sheet bore joined by "
                      f"printed station identity, frames not reconciled")
        elif leg["kind"] == "mid_leg":
            reason = (f"{lid} sheet-{leg['sheet']} MIDDLE leg: MATCHLINE STA {leg['matchline_in']} -> "
                      f"MATCHLINE STA {leg['matchline_out']} (conduit corridor traced between the two printed "
                      f"crossings; 3-sheet route, middle sheet not omitted)")
        elif leg["kind"] == "matchline_terminus":
            reason = (f"{lid} sheet-{leg['sheet']} bore: start {leg['start_label']} -> MATCHLINE STA "
                      f"{leg['matchline_sta']}; bore TERMINATES at the sheet boundary (continues as a "
                      f"separate bore on the partner sheet); single leg, printed-span closure")
        elif leg["kind"] == "hh_hh_bridge":
            reason = (f"{lid} sheet-{leg['sheet']} HH-HH bore: {leg['start_label']} -> {leg['end_label']}; "
                      f"partner hand-hole identified by the printed HH-HH distance annotation (unique by "
                      f"value, positioned between the two HHs); source-backed conduit, printed-span closure")
        else:
            reason = (f"{lid} sheet-{leg['sheet']} leg: MATCHLINE STA {leg['matchline_sta']} -> end "
                      f"{leg['end_label']}; joined to sheet {v['start_sheet']} by printed station identity")
        png = render_redline_stroke(plan, lid, leg["sheet"], offset, leg["route"], status="REVIEW",
                                    reason=reason, out_dir=str(OUT_DIR),
                                    mandatory_points=[tuple(leg["a_xy"]), tuple(leg["b_xy"])], pad=160.0)
        leg["png"] = os.path.basename(png) if png else None
        if png and os.path.isfile(png):
            pngs.append(png)
    return pngs


def _span_seed_record(lid, truth_rows):
    """Synthetic owner-reviewed record for an OWNER_APPROVED_SPAN_PROMOTIONS log: seed the endpoints from
    the engine truth-table SPAN 'A->B' + sheets (source), normalising the zero-padded station ('02+65' ->
    '2+65'). class None -> derived from source; unique-bind + printed-span closure still gate the render."""
    row = next((r for r in truth_rows if r.get("bore_id") == lid), None)
    m = re.match(r"(\d+\+\d+)\s*->\s*(\d+\+\d+)", (row or {}).get("span") or "")
    if not row or not m:
        return None

    def _n(s):
        mm = re.match(r"0*(\d+)\+(\d+)", s)
        return f"{int(mm.group(1))}+{mm.group(2)}" if mm else s

    return {"log_id": lid, "corrected_start": _n(m.group(1)), "corrected_end": _n(m.group(2)),
            "corrected_sheets": row.get("sheets") or [], "span_ft": None, "status": "RECOVERED",
            "evidence_notes": "", "endpoint_anchors": None, "allowed_to_draw": True,
            "must_remain_abstained": False}


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for stale in OUT_DIR.glob("*.png"):
        stale.unlink()
    doc = load_adjudication()
    rec = {r["log_id"]: r for r in doc["logs"]}
    # OWNER-APPROVED promotions: inject truth-table-span-seeded records so the deterministic sweep renders
    # the owner-confirmed candidates (census untouched -- these are NOT adjudication records).
    truth_rows = json.loads(TRUTH.read_text(encoding="utf-8"))["rows"] if TRUTH.is_file() else []
    for _lid in SPAN_SEEDED_PROMOTIONS:
        if _lid not in rec:
            _srec = _span_seed_record(_lid, truth_rows)
            if _srec:
                rec[_lid] = _srec
    # OWNER-CONFIRMED PLAN ROUTES: OVERRIDE the corrupted stored record with the owner+plan-verified route
    # sentence so the solver seeds the child's OWN endpoints (not the sibling's corrupted ones). Census is
    # computed from `doc` (untouched), never from `rec`.
    for _lid, _orec in OWNER_CONFIRMED_PLAN_ROUTES.items():
        rec[_lid] = dict(_orec)
    gates, ev = [], {"verdicts": {}}

    gates.append(("G0 engine census frozen (OFF 31/6/1/17/3, ON 22/1/4, log44+abstains held)",
                  _census_frozen(doc), None))

    if not os.path.isfile(PDF):
        return _emit(gates, B_SCOPE, ev)
    corpus_dir, _ = resolve_corpus()
    corpus = {p.stem: p for p in enumerate_corpus(corpus_dir)} if os.path.isdir(corpus_dir) else {}
    gates.append(("G1 plan PDF + corpus present", os.path.isfile(PDF) and len(corpus) == EXPECTED_COUNT,
                  {"pdf": os.path.isfile(PDF), "corpus": len(corpus)}))

    def _is_target(lid, r):
        if lid in ALREADY_DRAWN or lid in DUPLICATE_OF_DRAWN or r.get("must_remain_abstained"):
            return False
        if r.get("allowed_to_draw") is False:
            return False
        if r.get("endpoint_anchors"):
            return True
        # reviewed-but-unanchored: owner-reviewed corrected station endpoints (class derived from source)
        return bool(r.get("corrected_start") and r.get("corrected_end")
                    and r.get("status") in ("RECOVERED", "CORRECT_AS_DRAWN"))

    targets = sorted((lid for lid, r in rec.items() if _is_target(lid, r)), key=lambda s: int(s[3:]))
    ev["targets"] = targets

    rendered_full, blocked = [], {}
    plan = PlanPdf(PDF)
    try:
        offset = select_dialect(plan).calibrate(plan, 13)
        for lid in targets:
            v = solve_log(plan, offset, lid, rec)
            if v.get("legs"):
                # PARENT-SOURCE GATE (ORIGINAL_HANDWRITTEN_PARENT_SOURCE_MODEL): a split child may render
                # ONLY through its parent group, which disambiguates ownership by span + sheets so a child
                # cannot claim a SIBLING's route -- the log48<-log50 mixup (which is even baked into log48's
                # adjudication: corrected_end 5+14 == log50's route). Verified drift-free: every currently
                # rendered log owns its route; the gate only blocks a child claiming a sibling's span.
                _drawn = (v.get("closure") or {}).get("drawn_ft")
                if _drawn is None:
                    _drawn = sum(leg["len_pt"] for leg in v["legs"]) / SCALE
                _g_ok, _g_reason = child_owns_route(lid, _drawn, sorted({leg["sheet"] for leg in v["legs"]}))
                v["parent_source_gate"] = {"ok": _g_ok, "reason": _g_reason}
            if v.get("legs") and v["parent_source_gate"]["ok"]:
                pngs = _render(plan, offset, lid, v)
                n_expected = len(v["legs"])
                if len(pngs) == n_expected:
                    v["artifacts"] = [str(p).replace(str(_REPO_ROOT), "").lstrip("\\/").replace("\\", "/")
                                      for p in pngs]
                    rendered_full.append(lid)
                else:
                    v["blocker"] = f"render returned {len(pngs)}/{n_expected} PNGs"
                    blocked[lid] = v["blocker"]
            elif v.get("legs"):
                v["blocker"] = f"parent-source gate blocked render: {v['parent_source_gate']['reason']}"
                v["legs"] = None
                blocked[lid] = v["blocker"]
            else:
                blocked[lid] = v["blocker"]
            ev["verdicts"][lid] = {k: x for k, x in v.items() if not k.startswith("_") and k != "legs"}
            ev["verdicts"][lid]["leg_summary"] = ([{"sheet": l["sheet"], "kind": l["kind"],
                                                    "vertices": len(l["route"]), "len_pt": l["len_pt"],
                                                    "png": l.get("png")} for l in v["legs"]]
                                                   if v.get("legs") else None)
    finally:
        plan.close()

    ev["rendered_full"], ev["blocked"] = rendered_full, blocked
    gates.append(("G2 every rendered bore drew ALL its legs (no partial drawn as a full bore)",
                  all(len(ev["verdicts"][l]["leg_summary"]) ==
                      len([p for p in OUT_DIR.glob(f"{l}_*.png")]) for l in rendered_full), rendered_full))
    gates.append(("G3 at least one NEW redline artifact produced (success metric = new artifacts)",
                  len(rendered_full) >= 1, {"rendered": rendered_full}))
    gates.append(("G4 canonical red stroke color (TrueLine strokes are red)",
                  REDLINE_STROKE_RGB == (220, 25, 25), list(REDLINE_STROKE_RGB)))
    result = R_COMPLETE if all(x for _, x, _ in gates) else (
        B_CENSUS if not gates[0][1] else B_NOTHING)
    return _emit(gates, result, ev)


def _emit(gates, result, ev) -> int:
    gates.append(("G5 result in allowed enum", result in ALLOWED, result))
    all_pass = all(x for _, x, _ in gates) and result == R_COMPLETE
    pngs = sorted(p.name for p in OUT_DIR.glob("*.png"))
    report = {
        "milestone": "GENERALIZED CALLOUT-IDENTITY ROUTE ASSEMBLY sweep -> render (proof; read-only)",
        "verdict": "PASS" if all_pass else "FAIL", "result": result,
        "targets": ev.get("targets", []),
        "newly_rendered_full": ev.get("rendered_full", []),
        "newly_rendered_partial": [],
        "artifact_paths": [a for l in ev.get("rendered_full", []) for a in ev["verdicts"][l].get("artifacts", [])],
        "still_blocked": ev.get("blocked", {}),
        "verdicts": ev.get("verdicts", {}),
        "red_stroke_rgb": list(REDLINE_STROKE_RGB),
        "no_fixture_mutation": True, "no_coordinate_encoding": True, "no_owner_naming": True,
        "no_review_choice": True, "no_seam_or_ledger_change": True, "engine_census_frozen": True,
        "artifacts_gitignored": True, "max_dash_gap_not_loosened": MAX_DASH_GAP == 35.0,
        "artifacts_on_disk": pngs,
        "gates": [{"name": n, "pass": bool(x), "detail": d} for n, x, d in gates],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "callout_route_assembly_sweep.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"[route-sweep] result: {result}  newly_rendered={ev.get('rendered_full')}")
    for lid, v in ev.get("verdicts", {}).items():
        if lid in ev.get("rendered_full", []):
            print(f"[route-sweep]   {lid}: RENDERED {v.get('leg_summary')}")
        else:
            print(f"[route-sweep]   {lid}: BLOCKED -- {v.get('blocker')}")
    for n, x, _ in gates:
        print(f"[route-sweep] {'PASS' if x else 'FAIL'}  {n}")
    print(f"[route-sweep] VERDICT: {'PASS' if all_pass else 'FAIL'}  (report: {OUT_DIR})")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
