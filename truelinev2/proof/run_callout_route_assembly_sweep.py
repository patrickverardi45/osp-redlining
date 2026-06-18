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
    POSITION_BOUND, cluster_symbols, resolve_nextlink_hh_callout, resolve_structure_position,
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
    # log30 (2026-06-18, LOG30_LEDBETTER_PARALLEL_RUN render lane): standalone bore_log30, corpus 0+00->5+00
    # sheets [10,12]. It IS the parallel '1+91/1+92 Ledbetter run' log48's note records the Woodson solver
    # rejecting -- a DISTINCT bore from the already-drawn log48 (Woodson, 1+90/1+90 -> 5+07): the two routes
    # run 219-258 ft apart on s10/s12 (read-only visual + numeric re-verify, data/outputs/log30_visual_verify).
    # Source-derived bind (no owner naming): start reset 'STA 2+22=0+00' (s10 HH) selected by PER-LEG closure
    # (start leg 190.1' = local 1+91; the parallel 2+72 reset's 226' start leg FAILS per-leg closure though its
    # total is in-tol); end '5+10' FLOWER POT (s12, Ledbetter); the 1+91/1+92 crossing chosen by both-legs
    # chain-reach (NOT log48's 1+90). span_ft = corpus 500. LABELS ONLY -- coords extractor-derived; census
    # uses `doc`, not this map (frozen). Parent gate: bore_log30 standalone (no sibling overlap).
    "log30": {"log_id": "log30", "corrected_start": "0+00", "corrected_end": "5+10",
              "corrected_sheets": [10, 12], "span_ft": 500, "status": "RECOVERED",
              "evidence_notes": "STA 2+22=0+00", "endpoint_anchors": None,
              "cross_sheet_drop_terminus": True, "parallel_crossing_by_chain_reach": True,
              "allowed_to_draw": True, "must_remain_abstained": False},
    # log4 (2026-06-18, FIBER_CORRIDOR_SPRINT render lane): standalone bore_log4, a 2-1.25" fiber MAIN on
    # Chappell Hill, 15+13->21+63 (650'), sheets 3->4->5 (N-leg). BOTH endpoints are printed NEXTLINK HHs
    # (reset 15+13=0+00 on s3; 21+63=0+00 on s5). The fiber conduit is on the generic BORE-PATH layer (outside
    # BASE_CONDUIT) AND the s3/s4 frames are x-offset, so two gated, narrow opt-ins are needed: (1)
    # `fiber_conduit_candidate_set` adds BORE-PATH to THIS log's conduit set only (global BASE_CONDUIT
    # untouched -> census + all other renders byte-identical); (2) `nleg_matchline_identity_join` joins the 3
    # legs by SEE-SHEET matchline identity (16+25, 20+18) in the UNAMBIGUOUS single-middle-run case (exactly 1
    # component + 1 entry + 1 exit), the proven cross-sheet 2-leg shape. drawn 647.6' closes 650' (0.4%).
    # Distinct corpus parent from the (undrawn) log3 that geographically contains it. span_ft = corpus 650.
    "log4": {"log_id": "log4", "corrected_start": "0+00", "corrected_end": "21+63",
             "corrected_sheets": [3, 4, 5], "span_ft": 650, "status": "RECOVERED",
             "evidence_notes": "STA 15+13=0+00", "endpoint_anchors": None,
             "fiber_conduit_candidate_set": True, "nleg_matchline_identity_join": True,
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
    # log60 (2026-06-17, RAW_CORPUS_FAST_PICK lane): a clean SINGLE-SHEET drop on sheet 15 -- the easiest
    # remaining raw corpus log. Source-VERIFIED (printed structures): STA 6+32 INSTALLER HH (the drop's local
    # 0+00) -> STA 1+13 FLOWER POT, 'STA 0+00 TO STA 1+13' (113'). Both termini bind by clean station labels
    # (6+32 / 1+13); the existing single-sheet solver traces the ordered conduit path and closes (drawn 111.3
    # vs 113). No matchline, no parallel branch. Parent gate ok (bore_log26; own 0+00->1+13 vs colliding
    # sibling log62's 201 -> owns its own). Identity-only anchors; no census/corpus change.
    "log60": {"log_id": "log60", "parent": "bore_log26", "status": "RECOVERED",
              "corrected_start": "0+00", "corrected_end": "1+13",
              "corrected_sheets": [15], "span_ft": 113.0,
              "endpoint_anchors": {
                  "start": {"station": "6+32", "structure_class": "installer_hh",
                            "boundary_kind": "structure_terminus", "clarity": "CLEAR",
                            "structure_label": "INSTALLER HH",
                            "owner_note_text": ("log60 single-sheet drop start: STA 6+32 INSTALLER HH "
                                                "(sheet 15; the drop's local 0+00).")},
                  "end": {"station": "1+13", "structure_class": "flower_pot",
                          "boundary_kind": "structure_terminus", "clarity": "CLEAR",
                          "structure_label": "FLOWER POT",
                          "owner_note_text": "log60 end: STA 1+13 FLOWER POT (sheet 15)."}},
              "allowed_to_draw": True, "must_remain_abstained": False},
    # log32 (2026-06-17, owner-supplied PRINTED-DISTANCE discriminator): cross-sheet drop 18->22, 0+00->2+13
    # (213'). Sheet 18 prints TWO reset HHs that both produce a closing route (STA 12+22=0+00 NEXTLINK HH /
    # SPLICE POINT 34 -> 207.2'; STA 12+93=0+00 INSTALLER HH -> 210.5'), so closure alone is ambiguous. The
    # OWNER-CONFIRMED source discriminator is the printed HH-HH decomposition: HH-HH=130' on sheet 18 (the leg
    # to the matchline) + HH-HH=83' on sheet 22 = 213 = the bore span -> the origin is STA 12+22=0+00 (NOT
    # 12+93). Anchor the start to the 12+22 NEXTLINK HH; the end is STA 2+13 FLOWER POT on sheet 22 via the
    # 1+77/1+76 matchline. The existing cross-sheet 2-leg solver traces it (drawn 207.2 vs 213, closes).
    # Identity-only anchors; no census/corpus change. Parent gate ok (standalone bore_log32).
    "log32": {"log_id": "log32", "parent": "bore_log32", "status": "RECOVERED",
              "corrected_start": "0+00", "corrected_end": "2+13",
              "corrected_sheets": [18, 22], "span_ft": 213.0,
              "endpoint_anchors": {
                  "start": {"station": "12+22", "structure_class": "nextlink_hh",
                            "boundary_kind": "structure_terminus", "clarity": "CLEAR",
                            "structure_label": "NEXTLINK HH",
                            "owner_note_text": ("owner-confirmed log32 origin 2026-06-17: STA 12+22=0+00 NEXTLINK "
                                                "HH (PROP. SPLICE POINT 34, sheet 18). Printed HH-HH decomposition "
                                                "130' (s18) + 83' (s22) = 213 = bore span SELECTS 12+22, REJECTS "
                                                "the STA 12+93=0+00 INSTALLER HH origin.")},
                  "end": {"station": "2+13", "structure_class": "flower_pot",
                          "boundary_kind": "structure_terminus", "clarity": "CLEAR",
                          "structure_label": "FLOWER POT",
                          "owner_note_text": ("log32 end: STA 2+13 FLOWER POT (sheet 22), reached from the 12+22 "
                                              "origin down Hickory Ln across the 1+77/1+76 matchline.")}},
              "allowed_to_draw": True, "must_remain_abstained": False},
    # log27 (2026-06-17, owner-confirmed CROSS-SHEET TYPO + END-SYMBOL bind): mainline run sheets 15->16,
    # 7+30->13+55 (625', E Mansfield St). Start = STA 7+30 TERMINAL 6-PORT HH (AP-152 SPLICE LOC 35) on sheet
    # 15. The 15<->16 join is the printed MATCHLINE STA 11+66, but sheet 15 mislabels it 'SEE SHEET 14' (owner-
    # confirmed plan TYPO; should be SEE SHEET 16) while sheet 16 correctly prints the reciprocal 'SEE SHEET
    # 15' at 11+66 -- so the join is still confirmed BOTH ways, only the start-sheet number is corrected (opt-
    # in `matchline_see_sheet_typo`, gated to log27). End = STA 13+55 NEXTLINK HH (PROP. SPLICE POINT 36) on
    # sheet 16; its drawn symbol sits ~107pt from its non-unique '13+55' label so the standard callout locator
    # fails -> owner-confirmed `end_hh_symbol_bind` binds the UNIQUE NEXTLINK symbol near the 13+55 label. The
    # existing cross-sheet 2-leg solver then traces it (s15 leg 435.6' + s16 leg 188.8' = 624.4 vs 625 span,
    # closes). Parent gate ok (standalone bore_log27). Identity-only; no census/corpus change.
    "log27": {"log_id": "log27", "parent": "bore_log27", "status": "RECOVERED",
              "corrected_start": "7+30", "corrected_end": "13+55",
              "corrected_sheets": [15, 16], "span_ft": 625.0,
              "matchline_see_sheet_typo": {"start_sheet": 15, "end_sheet": 16, "station": "11+66",
                                           "printed_sheet": 14},
              "end_hh_symbol_bind": True,
              "endpoint_anchors": {
                  "start": {"station": "7+30", "structure_class": "terminal_port_hh",
                            "boundary_kind": "structure_terminus", "clarity": "CLEAR",
                            "structure_label": "TERMINAL PORT HH",
                            "owner_note_text": ("log27 start: STA 7+30 TERMINAL 6-PORT HH AP-152 SPLICE LOC 35 "
                                                "(sheet 15, E Mansfield St).")},
                  "end": {"station": "13+55", "structure_class": "nextlink_hh",
                          "boundary_kind": "structure_terminus", "clarity": "CLEAR",
                          "structure_label": "NEXTLINK HH",
                          "owner_note_text": ("log27 end: STA 13+55 NEXTLINK HH PROP. SPLICE POINT 36 (sheet "
                                              "16), across the owner-corrected 11+66 matchline join.")}},
              "allowed_to_draw": True, "must_remain_abstained": False},
    # log2 (2026-06-18, Gate #2 ENDPOINT_IDENTITY_OWNER_REVIEW -- owner-confirmed end): cross-sheet mainline
    # sheets 18->19, span 849'. START = STA 12+22 NEXTLINK HH / PROP. SPLICE POINT 34 (sheet 18) -- the bore
    # log NAMES 12+22 directly (no 0+00 collision; same origin owner-confirmed for log32). END = STA 20+71
    # TERMINAL 6-PORT HH / AP-148 SPLICE LOC 34 (sheet 19, Niebuhr St) -- owner-confirmed 2026-06-18; bare
    # '20+71' prints 3x so `end_hh_symbol_bind` binds the UNIQUE terminal HH symbol near a 20+71 label
    # (AP-148 is globally unique, 1/43 pages). PRINTED leg footages corroborate: 616' (s18 12+22->18+38) +
    # 233' (s19 18+38->20+71) = 849 = span. The 18+38 join is reciprocal ('SEE SHEET 19' on s18, 'SEE SHEET
    # 18' on s19), but '18+38' also prints in the mid-sheet run callout 'STA 12+22 TO STA 18+38' next to the
    # SEE-SHEET-22 line, so the per-token boundary locator snaps WRONG (215' partial) -> `crossing_by_partner
    # _sheet` selects each leg's boundary by the SEE-SHEET-<partner> matchline identity (drawn 848.0 vs 849,
    # closes). Identity-only anchors; no census/corpus change. Parent gate ok (standalone bore_log2; distinct
    # from log32's 213'/[18,22]/flower-pot drop off the SAME splice point).
    "log2": {"log_id": "log2", "parent": "bore_log2", "status": "RECOVERED",
             "corrected_start": "12+22", "corrected_end": "20+71",
             "corrected_sheets": [18, 19], "span_ft": 849.0,
             "end_hh_symbol_bind": True, "crossing_by_partner_sheet": True,
             "endpoint_anchors": {
                 "start": {"station": "12+22", "structure_class": "nextlink_hh",
                           "boundary_kind": "structure_terminus", "clarity": "CLEAR",
                           "structure_label": "NEXTLINK HH",
                           "owner_note_text": ("log2 start: STA 12+22=0+00 NEXTLINK HH PROP. SPLICE POINT 34 "
                                               "(sheet 18); bore log names 12+22 directly. Same origin "
                                               "owner-confirmed for log32.")},
                 "end": {"station": "20+71", "structure_class": "terminal_port_hh",
                         "boundary_kind": "structure_terminus", "clarity": "CLEAR",
                         "structure_label": "TERMINAL 6 PORT HH",
                         "owner_note_text": ("owner-confirmed log2 end 2026-06-18: STA 20+71 TERMINAL 6-PORT "
                                             "HH AP-148 SPLICE LOC 34 (sheet 19, Niebuhr St). Legs 616'+233'="
                                             "849 across the reciprocal 18+38 / SEE SHEET 19 matchline.")}},
             "allowed_to_draw": True, "must_remain_abstained": False},
    # log8 (2026-06-18, Gate #2 endpoint-identity review -- owner-confirmed start via plan screenshots): cross-
    # sheet drop 18->22, span 390', down Hickory Ln. Owner confirmed the START is STA 12+93=0+00 13"X24"X24"
    # INSTALLER HH (NOT the 12+22 NEXTLINK HH = log32's origin, which closes only loosely at 426'). Printed
    # chain: STA 0+00 TO 1+10 (110') -> STA 1+10 TO 1+76 (66') on sheet 18 -> MATCHLINE STA 1+77/1+76 SEE SHEET
    # 22 -> STA 1+76 TO 3+90 (214') on sheet 22 -> STA 3+90 11"X11"X12" FLOWER POT (Hickory cul-de-sac);
    # 110+66+214 = 390. The existing cross-sheet 2-leg solver traces it with NO special hook (both termini bind
    # by their own labels: 12+93 installer_hh reset, 3+90 flower_pot), drawn 384.6 vs 390 (closes). DISTINCT
    # from log32 (12+22 NEXTLINK -> 2+13 FLOWER POT, 213') and log2 (12+22 -> 20+71, 849', sheets 18->19):
    # different start + end + span. Parent gate ok (standalone bore_log8). Identity-only; no census/corpus change.
    "log8": {"log_id": "log8", "parent": "bore_log8", "status": "RECOVERED",
             "corrected_start": "12+93", "corrected_end": "3+90",
             "corrected_sheets": [18, 22], "span_ft": 390.0,
             "endpoint_anchors": {
                 "start": {"station": "12+93", "structure_class": "installer_hh",
                           "boundary_kind": "structure_terminus", "clarity": "CLEAR",
                           "structure_label": "INSTALLER HH",
                           "owner_note_text": ("owner-confirmed log8 start 2026-06-18 (plan screenshots): STA "
                                               "12+93=0+00 13\"X24\"X24\" INSTALLER HH (sheet 18, Hickory Ln); "
                                               "NOT the 12+22 NEXTLINK HH (= log32 origin, loose 426' close).")},
                 "end": {"station": "3+90", "structure_class": "flower_pot",
                         "boundary_kind": "structure_terminus", "clarity": "CLEAR",
                         "structure_label": "FLOWER POT",
                         "owner_note_text": ("log8 end: STA 3+90 11\"X11\"X12\" FLOWER POT (sheet 22, Hickory Ln "
                                             "cul-de-sac), 214' past the 1+76 matchline. Chain 110+66+214 = 390.")}},
             "allowed_to_draw": True, "must_remain_abstained": False},
    # log56 (2026-06-18, DROP_TERMINUS_SYMBOL_BIND lane -- owner-confirmed): single-sheet drop on sheet 2
    # (Stone St). START = STA 0+46=0+00 INSTALLER HH (owner-confirmed; the co-located origin of the printed
    # 'STA 0+00 TO 2+70 (270') 1-1.25" PORT TERMINAL TAIL' drop). END = a SYMBOL-ONLY flower pot with NO
    # bindable station label (the 2+70/2+76 labels do not bind a flower_pot; nearest is 2+52, 37pt off), so the
    # new opt-in `drop_terminus_symbol_bind` walks the start's BASE_CONDUIT drop chain to the UNIQUE flower-pot
    # symbol at the printed span (267.3 vs 270, closes). The bore-log end 2+76 is owner-accepted OCR/handwriting
    # drift from the printed 2+70 (same class as log48 5+09 vs printed 5+07). Single-sheet, no matchline. The
    # gate REJECTS fiber/generic BORE chains (log42 has 0 BASE_CONDUIT segs there) and >=2 reachable pots.
    # CLOSURE SPAN = the bore-log's own 276' (0+00->2+76, the full drop TO THE POT), NOT the 270' conduit-run
    # callout (STA 0+00 TO 2+70, which stops ~6' short of the pot): two flower pots sit near 270' (a 245.4'
    # decoy on the Stone St row + the real 273.6' pot), and the 276' bore span uniquely selects the 273.6' one
    # (the 245.4' decoy fails closure at 11%). Identity-only anchors; coordinates extractor-derived; no
    # census/corpus change. Parent gate ok: log56 owns this 0+00->2+76 / sheet-2 route through parent bore_log22.
    "log56": {"log_id": "log56", "parent": "bore_log22", "status": "RECOVERED",
              "corrected_start": "0+46", "corrected_end": "2+70",
              "corrected_sheets": [2], "span_ft": 276.0,
              "drop_terminus_symbol_bind": True,
              "endpoint_anchors": {
                  "start": {"station": "0+46", "structure_class": "installer_hh",
                            "boundary_kind": "structure_terminus", "clarity": "CLEAR",
                            "structure_label": "INSTALLER HH",
                            "owner_note_text": ("owner-confirmed log56 start 2026-06-18: STA 0+46=0+00 INSTALLER "
                                                "HH (sheet 2, Stone St) -- the '0+00 TO 2+70' PORT TERMINAL TAIL "
                                                "drop origin (NOT the 7+40 NEXTLINK splice).")},
                  "end": {"station": "2+70", "structure_class": "flower_pot",
                          "boundary_kind": "structure_terminus", "clarity": "CLEAR",
                          "structure_label": "FLOWER POT",
                          "owner_note_text": ("owner-confirmed log56 end 2026-06-18: the UNIQUE flower-pot symbol "
                                              "at the end of the traceable 270' 1-1.25\" drop (symbol-only -- no "
                                              "bindable station label; bore-log 2+76 = OCR drift from printed 2+70).")}},
              "allowed_to_draw": True, "must_remain_abstained": False},
    # log55 (2026-06-18, Gate #1 DROP_TERMINUS_SYMBOL_BIND -- owner-confirmed start): single-sheet drop on
    # sheet 17, the sibling of log56 under parent bore_log22. START = STA 4+57=0+00 INSTALLER HH -- owner-
    # confirmed 2026-06-18. Sheet 17 prints FIVE reset HHs that each reset to 0+00 (2+05/1+45/4+57/3+91/0+56),
    # so the bare 0+00 is 5-way ambiguous; but ONLY the 4+57=0+00 reset's BASE_CONDUIT drop chain reaches a
    # UNIQUE flower-pot symbol that closes the bore span (the other four bind no closing terminus) -- so the
    # source uniquely indicates 4+57, and the owner confirmed it. END = a SYMBOL-ONLY flower pot with NO
    # bindable station label (same shape as log56), so the opt-in `drop_terminus_symbol_bind` walks the 4+57
    # chain to the UNIQUE end-class symbol at the printed span (drawn 173.8' vs span 169', closes). CLOSURE
    # SPAN = the bore-log's own 169' (truth_span 0+00->1+69). Single-sheet, no matchline. The gate REJECTS
    # fiber/generic BORE chains and >=2 reachable pots. Identity-only anchors; coordinates extractor-derived;
    # no census/corpus change. Parent gate ok: log55 owns this 0+00->1+69 / sheet-17 route through parent
    # bore_log22 -- DISTINCT from sibling log56 (0+00->2+76 / sheet 2): different sheet AND span, no sibling
    # route theft (log55 span_collision_with_sibling is empty).
    "log55": {"log_id": "log55", "parent": "bore_log22", "status": "RECOVERED",
              "corrected_start": "4+57", "corrected_end": "1+69",
              "corrected_sheets": [17], "span_ft": 169.0,
              "drop_terminus_symbol_bind": True,
              "endpoint_anchors": {
                  "start": {"station": "4+57", "structure_class": "installer_hh",
                            "boundary_kind": "structure_terminus", "clarity": "CLEAR",
                            "structure_label": "INSTALLER HH",
                            "owner_note_text": ("owner-confirmed log55 start 2026-06-18: STA 4+57=0+00 INSTALLER "
                                                "HH (sheet 17) -- the ONLY one of five 0+00 resets "
                                                "(2+05/1+45/4+57/3+91/0+56) whose drop chain reaches a unique "
                                                "flower-pot terminus that closes the 169' span.")},
                  "end": {"station": "1+69", "structure_class": "flower_pot",
                          "boundary_kind": "structure_terminus", "clarity": "CLEAR",
                          "structure_label": "FLOWER POT",
                          "owner_note_text": ("owner-confirmed log55 end 2026-06-18: the UNIQUE flower-pot symbol "
                                              "at the end of the traceable 1-1.25\" drop (symbol-only -- no "
                                              "bindable station label); bore-log span 0+00->1+69 = 169'.")}},
              "allowed_to_draw": True, "must_remain_abstained": False},
    # log19 (2026-06-18, Gate #2 CROSS_SHEET_DROP_TERMINUS_EXTENSION -- owner-confirmed terminus): a drop whose
    # start STA 4+94 INSTALLER HH binds on sheet 14 and continues PAST the BUNDLED 'MATCHLINE STA 10+44/9+53 -
    # SEE SHEET 7' to a FLOWER POT on sheet 7. The single-sheet drop_terminus_symbol_bind returns 0 candidates
    # (the pot is off-sheet); the NEW opt-in `cross_sheet_drop_terminus` assembles two sheet-local legs joined
    # by the reciprocal SEE-SHEET identity (s14 left-edge SEE SHEET 7 + s7 right-edge SEE SHEET 14), each leg's
    # boundary selected by the matchline IDENTITY -- the bundled '10+44' token also prints mid-sheet by a
    # DIFFERENT matchline, so the per-token locator snaps to a 320.9' partial; the partner-sheet selector gives
    # the full 459.2' start run. The 10+44/9+53 matchline is BUNDLED (carries TWO parallel bores), so TWO sheet-7
    # pots BOTH close the 656' span: STA 11+69 (via the 9+53 entry, 675.9') and STA 12+64 (via the 10+44 entry,
    # 679.3'). OWNER CONFIRMED 2026-06-18 the terminus is STA 11+69 -- the END of the printed 'STA 9+86 TO STA
    # 11+69' drop chain, via the 9+53 entry (NOT the 10+44 entry / STA 12+64). ACCOUNTING CORRECTION: the log
    # records both 11+19 and 11+50, where the 50' was accounted ADDITIVELY from 11+19 (11+19 + 50' = 11+69), so
    # 11+50 was never the absolute terminus -- the station chain is 11+00 -> 11+50 -> 11+69. 11+69 binds a
    # flower_pot by its printed label, so the >=2-pot bundled ambiguity is resolved by owner confirmation (NOT a
    # closer-closure/nearest pick). Drawn 675.9 vs span 656 (3%, closes). NOT the fiber
    # backbone -- both legs trace a 1-1.25" HDPE BASE_CONDUIT chain. Identity-only anchors; coordinates
    # extractor-derived; no census/corpus change. Parent gate ok: standalone bore_log19, owns 4+94->11+50 / s14.
    "log19": {"log_id": "log19", "parent": "bore_log19", "status": "RECOVERED",
              "corrected_start": "4+94", "corrected_end": "11+69",
              "corrected_sheets": [14, 7], "span_ft": 656.0,
              "cross_sheet_drop_terminus": True,
              "endpoint_anchors": {
                  "start": {"station": "4+94", "structure_class": "installer_hh",
                            "boundary_kind": "structure_terminus", "clarity": "CLEAR",
                            "structure_label": "INSTALLER HH",
                            "owner_note_text": ("log19 start: STA 4+94 INSTALLER HH (sheet 14); BASE_CONDUIT drop "
                                                "chain to the bundled 10+44/9+53 SEE-SHEET-7 matchline.")},
                  "end": {"station": "11+69", "structure_class": "flower_pot",
                          "boundary_kind": "structure_terminus", "clarity": "CLEAR",
                          "structure_label": "FLOWER POT",
                          "owner_note_text": ("owner-confirmed log19 terminus 2026-06-18: STA 11+69 FLOWER POT "
                                              "(sheet 7, 905 Carlee Dr), the end of the printed STA 9+86->11+69 "
                                              "drop chain via the 9+53 entry of the BUNDLED 10+44/9+53 matchline. "
                                              "Selected over the 10+44-entry STA 12+64 pot (both close 656'; owner "
                                              "confirmation resolves the bundled-matchline ambiguity). ACCOUNTING "
                                              "CORRECTION: recorded 11+50 was a documentation error -- the 50' was "
                                              "accounted additively from 11+19 (11+19 + 50' = 11+69), so 11+50 was "
                                              "never the absolute terminus.")}},
              "allowed_to_draw": True, "must_remain_abstained": False},
    # log49 (2026-06-18, owner-confirmed start coordinate + span): single-sheet installer->nextlink bore on
    # sheet 10, the Segment B (high-station 44+89->45+33) child of parent bore_log20 (siblings log48/log50).
    # START = STA 44+83 13"X24"X24" INSTALLER HH -- the bore-log records 44+89 (OCR/field drift, owner-accepted
    # 2026-06-18); '44+83' prints 3x (run-callout text) so the bare locator abstains LABEL_WORD_NOT_UNIQUE. The
    # NEW opt-in `start_label_context` binds the UNIQUE installer-HH symbol via the INSTALLER HH callout's own
    # context words ("INSTALLER","HH") -> label box -> leader -> symbol (914.6,420.2) == owner Candidate A;
    # Candidate B (861,354) carries NO INSTALLER HH callout -> rejected BY SOURCE, not preference. END = STA
    # 45+33=0+00 NEXTLINK HH / PROP. SPLICE POINT 46 (binds via the nextlink callout locator). The printed run
    # is STA 44+83 TO 45+33 DIR. BORE (50'); drawn 49.9' closes 50' (0.1%). The owner 44'->50' span correction
    # is recorded as the parent model's adj_corrected_span (source-confirmed by the printed callout; accepted --
    # log49 has no span-colliding sibling), so the parent-source gate passes. DISTINCT from siblings: 49.9' is
    # nowhere near log48 (507') or log50 (514'); span_collision empty.
    "log49": {"log_id": "log49", "parent": "bore_log20", "status": "RECOVERED",
              "corrected_start": "44+83", "corrected_end": "45+33",
              "corrected_sheets": [10], "span_ft": 50.0,
              "start_label_context": ["INSTALLER", "HH"],
              "endpoint_anchors": {
                  "start": {"station": "44+83", "structure_class": "installer_hh",
                            "boundary_kind": "structure_terminus", "clarity": "CLEAR",
                            "structure_label": "INSTALLER HH",
                            "owner_note_text": ("owner-confirmed log49 start 2026-06-18: STA 44+83 "
                                                "13\"X24\"X24\" INSTALLER HH (sheet 10); bore-log 44+89 = OCR/"
                                                "field drift (owner-accepted). Bound via the INSTALLER HH "
                                                "callout context+leader to the UNIQUE symbol (Candidate A); "
                                                "Candidate B has no such callout -> rejected by source.")},
                  "end": {"station": "45+33", "structure_class": "nextlink_hh",
                          "boundary_kind": "structure_terminus", "clarity": "CLEAR",
                          "structure_label": "NEXTLINK HH",
                          "owner_note_text": ("owner-confirmed log49 end 2026-06-18: STA 45+33=0+00 NEXTLINK "
                                              "HH / PROP. SPLICE POINT 46 (sheet 10).")}},
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


# the 2-1.25" fiber-MAIN path layer: a generic BORE layer OUTSIDE BASE_CONDUIT, so it is NEVER in the default
# conduit set (census + every non-fiber render stay byte-identical). Used ONLY by the gated per-log opt-in.
FIBER_CONDUIT_EXTRA = ("BORE - PATH",)


def _conduit_set_for(r):
    """The conduit layer set for THIS log's chain tracing. Default = BASE_CONDUIT. With the gated per-log
    opt-in `fiber_conduit_candidate_set`, ADD the generic fiber-main path layer FOR THIS LOG ONLY -- the
    global BASE_CONDUIT constant is NEVER mutated (census + all other renders byte-identical). Tracing stays
    BOUNDED by connected-component-from-endpoint; the exactly-one-route + closure + no-overlap gates prevent
    any sheet-wide generic-BORE widening."""
    return (BASE_CONDUIT | set(FIBER_CONDUIT_EXTRA)) if r.get("fiber_conduit_candidate_set") else BASE_CONDUIT


def _chain_at(draw, cls, xy, conduit_set=BASE_CONDUIT):
    fp = symbol_footprint(draw, SYMBOL_LAYER[cls], xy)
    return connected_chain([x for x in draw if x.get("layer") in conduit_set], fp) if fp else []


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


def _partner_matchline_bbox(words, draw, station, partner_sheet, tol=42.0):
    """The drawn matchline bbox carrying the printed 'MATCHLINE STA <station> ... SEE SHEET <partner_sheet>'
    line, identified by the PARTNER-SHEET number (the printed crossing IDENTITY) -- NOT the per-station
    token, which is non-unique when <station> also prints in a mid-sheet run callout printed next to a
    DIFFERENT matchline (log2: '18+38' is both 'STA 12+22 TO STA 18+38', sitting by the SEE-SHEET-22 line,
    AND the 'MATCHLINE STA 18+38 - SEE SHEET 19' label on the right-edge line). Among the sheet's matchline
    bboxes, the UNIQUE one whose nearby printed text (within ``tol`` pt of the drawn line) carries MATCHLINE
    + <station> + 'SHEET <partner_sheet>'. 0 or >=2 -> None (uniqueness-gated; never a nearest pick).
    Source-derived (printed matchline label + drawn line); no frame graph, no coordinate reconciliation."""
    matches = []
    for bb in matchline_bboxes(draw, "MATCHLINE"):
        near = " ".join(str(w.get("text", "")) for w in words
                        if nearest_gap([(float(w["xc"]), float(w["yc"]))], bb) <= tol).upper()
        if "MATCHLINE" in near and station in near and re.search(rf"SHEET\s*{partner_sheet}\b", near):
            matches.append(bb)
    return matches[0] if len(matches) == 1 else None


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
                e_xy, e_chain, e_words, e_draw, span, conduit_set=BASE_CONDUIT,
                matchline_identity_join=False):
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
    mid_conduit = [x for x in mid_draw if x.get("layer") in conduit_set]
    # the entry (->s0) and exit (->sn) matchline bboxes printed on smid (one per crossing equation)
    entries = [(c, _ml_bbox(mid_words, mid_draw, c)) for c in see_sheet_crossings(plan.lines(smid, offset), s0, "MATCHLINE")]
    exits = [(c, _ml_bbox(mid_words, mid_draw, c)) for c in see_sheet_crossings(plan.lines(smid, offset), sn, "MATCHLINE")]
    entries = [(c, bb) for c, bb in entries if bb]
    exits = [(c, bb) for c, bb in exits if bb]

    def _reaches(eps, bb):
        return bool(eps) and min(nearest_gap([p], bb) for p in eps) <= MAX_DASH_GAP

    sols = []
    comps = _conduit_components(mid_conduit)
    for comp in comps:
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
        # MATCHLINE-IDENTITY JOIN (opt-in `nleg_matchline_identity_join`; gated): when smid's frame is NOT
        # x-aligned with s0/sn (a fiber main drawn in offset sheet frames -- log4: s3 crosses 16+25 at x~772
        # but the s4 run enters at x~690, the SAME physical bore), the through-continuity x-match fails. Safe
        # ONLY in the unambiguous single-run case (exactly 1 middle component + 1 entry + 1 exit -> no parallel
        # run to confuse): join each leg to its OWN sheet's matchline IDENTITY (the proven cross-sheet 2-leg
        # join shape). Full-route printed-span closure remains the only-false-positive gate.
        if matchline_identity_join and len(comps) == 1 and len(entries) == 1 and len(exits) == 1:
            if start_bnd is None and entry_bb_s0:
                _sb = extend_dash_to_boundary(s_chain, entry_bb_s0)
                start_bnd = tuple(_sb) if _sb is not None else None
            if end_bnd is None and exit_bb_sn:
                _eb = extend_dash_to_boundary(e_chain, exit_bb_sn)
                end_bnd = tuple(_eb) if _eb is not None else None
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
DROP_TERMINUS_SYMBOL_TOL = 30.0  # a drop-terminus symbol must sit within this of the chain's terminal dash endpoint


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


def _terminus_symbol_candidates(chain, start_xy, symbols, span):
    """(endpoint, route, symbol) for each end-class symbol sitting within DROP_TERMINUS_SYMBOL_TOL of a dash
    endpoint of the START's BASE_CONDUIT chain AND whose source-backed ordered route from the start CLOSES the
    printed span. Near-identical endpoints are collapsed (SAME_POINT_TOL). PURE selector -- the caller renders
    ONLY when EXACTLY ONE survives (0 or >=2 -> abstain; never a nearest/length pick). No station, no coord."""
    eps = dash_endpoints(chain)
    if not eps or not span:
        return []
    out, seen = [], []
    for sym in symbols:
        ep = min(eps, key=lambda p: math.hypot(sym.x - p[0], sym.y - p[1]))
        if math.hypot(sym.x - ep[0], sym.y - ep[1]) > DROP_TERMINUS_SYMBOL_TOL:
            continue
        if any(math.hypot(ep[0] - q[0], ep[1] - q[1]) <= SAME_POINT_TOL for q in seen):
            continue
        route, ok = _ordered_leg(chain, start_xy, ep)
        if not ok:
            continue
        if abs(route_length(route) / SCALE - span) > CLOSURE_REL_TOL * span:
            continue
        seen.append(ep)
        out.append((ep, route, sym))
    return out


def _solve_drop_terminus(plan, offset, out, sheet, sc, s_lbl, ss, es, end_cls, span):
    """Single-sheet DROP to a SYMBOL-ONLY terminus (opt-in `drop_terminus_symbol_bind`): the terminus is a
    drawn flower-pot/drop symbol with NO bindable station label, so the standard station/AP locators abstain.
    Walk the bound start's BASE_CONDUIT chain to the UNIQUE end-class symbol at the printed span distance.
    Gates (all source-derived; DO-NOT-WIDEN): (1) a traceable BASE_CONDUIT chain at the start -- a fiber /
    generic-BORE route yields an EMPTY chain (those layers are outside BASE_CONDUIT) -> reject; (2) EXACTLY
    ONE end-class symbol reachable at span (0 or >=2 -> reject, no nearest pick); (3) the ordered leg is
    source-backed (the terminus is conduit-connected to the start); (4) printed-span closure is MANDATORY
    (no partial stub). Single-sheet only (no matchline). No station, no invented coordinate."""
    s_xy, s_words, s_draw, _ = _bind(plan, offset, sheet, sc, s_lbl)
    if not s_xy:
        out["blocker"] = "drop-terminus: start structure did not bind"
        return out
    chain = _chain_at(s_draw, sc, s_xy)
    if not chain:
        out["blocker"] = ("drop-terminus: no traceable BASE_CONDUIT chain at the start "
                          "(fiber / generic BORE only -> not a drop)")
        return out
    cands = _terminus_symbol_candidates(chain, s_xy, cluster_symbols(s_draw, SYMBOL_LAYER[end_cls]), span)
    out["drop_terminus_candidates"] = [{"xy": [round(c[0][0], 1), round(c[0][1], 1)],
                                        "drawn_ft": round(route_length(c[1]) / SCALE, 1)} for c in cands]
    if len(cands) != 1:
        out["blocker"] = (f"drop-terminus: {len(cands)} unique {end_cls} symbols reachable at span {span} ft "
                          f"(need exactly 1; 0 or >=2 -> abstain, no nearest/length pick)")
        return out
    ep, route, sym = cands[0]
    drawn_ft = route_length(route) / SCALE
    closes = bool(span) and abs(drawn_ft - span) <= CLOSURE_REL_TOL * span
    out["closure"] = {"drawn_ft": round(drawn_ft, 1), "span_ft": span, "closes": closes}
    if not closes:
        out["blocker"] = (f"drop-terminus closure failed: {round(drawn_ft, 1)} ft vs span {span} ft "
                          f"(>{int(CLOSURE_REL_TOL*100)}%)")
        return out
    out["start_sheet"], out["end_sheet"] = sheet, sheet
    out["start_class"], out["end_class"] = sc, end_cls
    out["bound_labels"] = {"start": ss, "end": es}
    out["single_sheet"] = True
    out["drop_terminus_bound"] = {"sheet": sheet, "symbol_xy": [round(sym.x, 1), round(sym.y, 1)],
                                  "endpoint_xy": [round(ep[0], 1), round(ep[1], 1)]}
    out["legs"] = [{"sheet": sheet, "route": route, "a_xy": list(s_xy), "b_xy": list(ep),
                    "len_pt": round(route_length(route), 1), "kind": "drop_terminus",
                    "start_label": ss, "end_label": es}]
    return out


def _solve_cross_sheet_drop_terminus(plan, offset, out, s_sheet, ss, e_sheet, es,
                                     s_xy, s_chain, s_words, s_draw,
                                     e_xy, e_chain, e_words, e_draw, crossings, span,
                                     parallel_by_chain_reach=False):
    """CROSS-SHEET DROP terminus (opt-in `cross_sheet_drop_terminus`): the cross-sheet extension of
    `drop_terminus_symbol_bind` -- a drop whose START binds on one sheet but whose TERMINUS is on a
    CONTINUATION sheet PAST the matchline, so the single-sheet `_solve_drop_terminus` finds 0 candidates
    (the pot is off-sheet). Assembles TWO sheet-local legs (start->matchline, matchline->terminus) joined by
    the printed RECIPROCAL SEE-SHEET station identity -- the proven cross-sheet 2-leg render shape (frames
    NOT reconciled) -- but tolerant of a BUNDLED matchline (`MATCHLINE STA a/b - SEE SHEET N` carrying >1
    parallel run): each leg's boundary is taken from the `SEE SHEET <partner>` matchline IDENTITY
    (`_partner_matchline_bbox`), NOT the per-token locator, which snaps to a stray same-numbered token by a
    DIFFERENT matchline (log19: the bare `10+44` token mid-sheet -> a 320.9' partial instead of the 459.2'
    run to the left-edge SEE-SHEET-7 line). The owner-confirmed terminus binds UNIQUELY by its printed label
    (a bundled matchline carries parallel bores whose pots BOTH close the span; that >=2-candidate ambiguity
    is resolved by OWNER CONFIRMATION of the terminus, the doctrine for a no-printed-discriminator case --
    NOT a closer-closure/nearest pick).

    Gates (all source-derived; DO-NOT-WIDEN): (1) opt-in flag + bound start + bound terminus (caller); (2)
    MANDATORY printed bore span (without a second free structure, full-route closure is the only false-positive
    guard); (3) a traceable BASE_CONDUIT chain on BOTH legs (fiber/generic BORE -> empty chain -> reject); (4)
    a printed RECIPROCAL SEE-SHEET crossing (this sheet->partner AND partner->this sheet, sharing stations);
    (5) a UNIQUE `SEE SHEET <partner>` matchline on EACH sheet that its OWN chain reaches (0/>=2 -> abstain);
    (6) both legs source-backed; (7) MANDATORY full-route closure -- a sheet-local PARTIAL (only the start leg)
    draws far short of the span and is rejected (never a partial drawn as a full bore)."""
    out["cross_sheet_drop_terminus"] = True
    if not span:
        out["blocker"] = "cross-sheet drop-terminus: no printed bore span (full-route closure is the only guard)"
        return out
    if not s_chain or not e_chain:
        out["blocker"] = (f"cross-sheet drop-terminus: a leg has no BASE_CONDUIT chain (start segs "
                          f"{len(s_chain)}, end segs {len(e_chain)}) -- fiber/generic BORE is not a drop")
        return out
    e_cross = see_sheet_crossings(plan.lines(e_sheet, offset), s_sheet, "MATCHLINE")
    shared = [c for c in crossings if any(set(c) & set(d) for d in e_cross)]
    out["printed_crossings_reciprocal"] = [list(c) for c in e_cross]
    if not crossings or not e_cross or not shared:
        out["blocker"] = (f"cross-sheet drop-terminus: no RECIPROCAL SEE-SHEET matchline between sheets "
                          f"{s_sheet} and {e_sheet} (start {crossings}, partner {e_cross})")
        return out
    stations = sorted({sta for c in shared for sta in c})
    # boundary on EACH leg by the SEE-SHEET-<partner> matchline IDENTITY (unique across the bundled stations)
    s_mlbs, e_mlbs = [], []
    for sta in stations:
        bb = _partner_matchline_bbox(s_words, s_draw, sta, e_sheet)
        if bb and bb not in s_mlbs:
            s_mlbs.append(bb)
        bb = _partner_matchline_bbox(e_words, e_draw, sta, s_sheet)
        if bb and bb not in e_mlbs:
            e_mlbs.append(bb)
    out["partner_matchline"] = {"stations": stations,
                                "start_bbox": [round(v, 1) for v in s_mlbs[0]] if len(s_mlbs) == 1 else None,
                                "end_bbox": [round(v, 1) for v in e_mlbs[0]] if len(e_mlbs) == 1 else None}

    # PARALLEL-CROSSING SELECTOR (opt-in `parallel_crossing_by_chain_reach`; gated so default renders stay
    # byte-identical -- fires ONLY when the SEE-SHEET-<partner> matchline is non-unique). Two parallel printed
    # crossings between the SAME sheet pair (log30's Ledbetter 1+91/1+92 vs the already-drawn log48's Woodson
    # 1+90/1+90) make _partner_matchline_bbox return >1 per leg. Disambiguate to the crossing BOTH legs' OWN
    # conduit chains physically REACH (extend_dash_to_boundary != None) -- the drawn dashes, a SOURCE
    # discriminator, never nearest. Require EXACTLY ONE (0/>=2 -> abstain, DO-NOT-WIDEN). The per-leg
    # station-delta closure gate (below) is the additional false-positive guard.
    sel = None
    if parallel_by_chain_reach and (len(s_mlbs) != 1 or len(e_mlbs) != 1):
        viable = []
        for c in shared:
            sb = eb = s_st = e_st = None
            for sta in c:
                cb = _partner_matchline_bbox(s_words, s_draw, sta, e_sheet)
                db = _partner_matchline_bbox(e_words, e_draw, sta, s_sheet)
                if sb is None and cb and extend_dash_to_boundary(s_chain, cb) is not None:
                    sb, s_st = cb, sta
                if eb is None and db and extend_dash_to_boundary(e_chain, db) is not None:
                    eb, e_st = db, sta
            if sb is not None and eb is not None:
                viable.append((list(c), sb, eb, s_st, e_st))
        out["parallel_crossings_reached_by_both"] = [v[0] for v in viable]
        if len(viable) != 1:
            out["blocker"] = (f"parallel-crossing selector: {len(viable)} crossings reached by BOTH legs' "
                              f"chains (need exactly 1) -- ambiguous, abstain (DO-NOT-WIDEN)")
            return out
        _c, sb, eb, s_st, e_st = viable[0]
        s_mlbs, e_mlbs = [sb], [eb]
        sel = {"crossing": _c, "start_sta": s_st, "end_sta": e_st}
        out["parallel_crossing_selected"] = sel

    if len(s_mlbs) != 1 or len(e_mlbs) != 1:
        out["blocker"] = (f"cross-sheet drop-terminus: SEE-SHEET-<partner> matchline not unique on a leg "
                          f"(start {len(s_mlbs)}, end {len(e_mlbs)}) -- cannot place the join boundary")
        return out
    s_bnd = extend_dash_to_boundary(s_chain, s_mlbs[0])
    e_bnd = extend_dash_to_boundary(e_chain, e_mlbs[0])
    if s_bnd is None or e_bnd is None:
        out["blocker"] = ("cross-sheet drop-terminus: a leg conduit chain does not reach its SEE-SHEET "
                          f"partner matchline (start {s_bnd is not None}, end {e_bnd is not None})")
        return out
    s_route, s_ok = _ordered_leg(s_chain, s_xy, tuple(s_bnd))
    e_route, e_ok = _ordered_leg(e_chain, tuple(e_bnd), e_xy)
    out["start_leg_source_backed"], out["end_leg_source_backed"] = s_ok, e_ok
    if not (s_ok and e_ok):
        out["blocker"] = f"cross-sheet drop-terminus: leg route not source-backed (start {s_ok}, end {e_ok})"
        return out
    drawn_ft = (route_length(s_route) + route_length(e_route)) / SCALE
    closes = abs(drawn_ft - span) <= CLOSURE_REL_TOL * span
    out["closure"] = {"drawn_ft": round(drawn_ft, 1), "span_ft": span, "closes": closes}
    if not closes:
        out["blocker"] = (f"cross-sheet drop-terminus closure failed: assembled legs draw {round(drawn_ft, 1)} "
                          f"ft vs printed bore span {span} ft (>{int(CLOSURE_REL_TOL*100)}% -> partial/wrong run)")
        return out

    # PER-LEG CLOSURE (parallel-crossing path only): each leg's drawn length must match its printed station
    # delta -- start leg = bore-local 0+00 -> the start-side crossing station; end leg = the end-side crossing
    # station -> corrected_end. Rejects a same-conduit-network start whose TOTAL happens to close but whose
    # split does NOT match the printed stations (log30's true 2+22 start: start leg 190'=1+91, end leg
    # 319'=5+10-1+91; the parallel 2+72 reset's 226' start leg fails this even though its total is in-tol).
    if sel is not None:
        s_ft, e_ft = route_length(s_route) / SCALE, route_length(e_route) / SCALE
        exp_s = abs(parse_station(sel["start_sta"]))
        exp_e = abs(parse_station(es) - parse_station(sel["end_sta"]))
        out["per_leg_closure"] = {"start_drawn": round(s_ft, 1), "start_expected": round(exp_s, 1),
                                  "end_drawn": round(e_ft, 1), "end_expected": round(exp_e, 1)}
        if (exp_s <= 0 or exp_e <= 0 or abs(s_ft - exp_s) > CLOSURE_REL_TOL * exp_s
                or abs(e_ft - exp_e) > CLOSURE_REL_TOL * exp_e):
            out["blocker"] = (f"parallel-crossing per-leg closure failed: start {round(s_ft,1)}/{round(exp_s,1)} "
                              f"end {round(e_ft,1)}/{round(exp_e,1)} ft (legs must match printed station deltas)")
            return out

    _xeq = sel["crossing"] if sel is not None else list(shared[0])
    _msta = sel["start_sta"] if sel is not None else shared[0][0]
    out["crossing_equation"] = _xeq
    out["legs"] = [
        {"sheet": s_sheet, "route": s_route, "a_xy": list(s_xy), "b_xy": list(s_bnd),
         "len_pt": round(route_length(s_route), 1), "kind": "start_leg", "start_label": ss,
         "matchline_sta": _msta},
        {"sheet": e_sheet, "route": e_route, "a_xy": list(e_bnd), "b_xy": list(e_xy),
         "len_pt": round(route_length(e_route), 1), "kind": "end_leg", "end_label": es,
         "matchline_sta": _msta},
    ]
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


def _bind_hh_symbol_near_label(draw, words, station, max_leader=130.0):
    """OWNER-CONFIRMED end bind: the UNIQUE hand-hole symbol (HH_SYMBOL_LAYER) whose nearest printed
    <station> label sits within max_leader pt. For an end HH whose drawn symbol is too far from its (often
    non-unique) station label for the standard callout locator's leader tolerance to bind. Source-derived
    (drawn symbol + printed station label); uniqueness-gated (0 or >=2 qualifying symbols -> None). Never an
    invented coordinate -- the returned xy is a real drawn HH symbol center."""
    labels = [(w["xc"], w["yc"]) for w in words if str(w.get("text", "")) == station]
    if not labels:
        return None
    near = [c for c in _hh_symbol_clusters(draw)
            if min(math.hypot(c[0] - lx, c[1] - ly) for lx, ly in labels) <= max_leader]
    return tuple(near[0]) if len(near) == 1 else None


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

    # OWNER-CONFIRMED START LABEL-CONTEXT BIND (opt-in `start_label_context`; gated): the start STATION label
    # is not sheet-unique (it also prints in run callouts) so the bare locator abstains LABEL_WORD_NOT_UNIQUE;
    # the owner confirms the start STRUCTURE CLASS and we bind the UNIQUE class symbol via the printed
    # structure callout's OWN context words (its label box must ALSO contain them) -> leader -> symbol -- the
    # standard word->box->leader->symbol->fill chain, never a coordinate (the START analogue of
    # end_hh_symbol_bind). Uniqueness across the candidate sheets is mandatory (0 or >=2 binds -> no override).
    s_xy_ov = None
    _start_cls = (r.get("endpoint_anchors") or {}).get("start", {}).get("structure_class")
    _start_ctx = r.get("start_label_context")
    if s_sheet is None and _start_ctx and _start_cls in MODELED and ss:
        sbinds = []
        for sh in (sheets or _all_sheets(plan, offset)):
            sv = resolve_structure_position(
                label_text=ss, structure_class=_start_cls, words=plan.words(sh, offset),
                drawings=plan.line_items(sh, offset), layer_table=BRENHAM_STRUCTURE_LAYERS,
                context_texts=tuple(_start_ctx))
            if sv.result == POSITION_BOUND and sv.symbol_xy:
                sbinds.append((sh, tuple(sv.symbol_xy)))
        if len(sbinds) == 1:
            s_sheet, sc, s_lbl, s_xy_ov = sbinds[0][0], _start_cls, ss, sbinds[0][1]
            out["start_sheet"], out["start_class"], out["bound_labels"]["start"] = s_sheet, sc, s_lbl
            out["start_context_bound"] = {"sheet": s_sheet, "station": ss,
                                          "context": list(_start_ctx),
                                          "xy": [round(v, 1) for v in s_xy_ov]}

    # OWNER-CONFIRMED END SYMBOL BIND (opt-in `end_hh_symbol_bind`; gated): when the end HH's drawn symbol
    # sits too far from its (non-unique) printed station label for the standard callout locator to bind, the
    # owner confirms the end structure and we bind to the UNIQUE end-class HH symbol nearest a printed end-
    # station label on a corrected sheet (source-derived; uniqueness-gated). Fires BEFORE the end-at-matchline
    # fallback so a real end structure is not mistaken for a boundary terminus.
    e_xy_ov = None
    _end_cls = (r.get("endpoint_anchors") or {}).get("end", {}).get("structure_class")
    if e_sheet is None and r.get("end_hh_symbol_bind") and _end_cls in MODELED and es:
        for sh in (sheets or [s_sheet]):
            xy = _bind_hh_symbol_near_label(plan.line_items(sh, offset), plan.words(sh, offset), es)
            if xy is not None:
                e_sheet, ec, e_lbl, e_xy_ov = sh, _end_cls, es, xy
                out["end_sheet"], out["end_class"], out["bound_labels"]["end"] = e_sheet, ec, e_lbl
                out["end_symbol_bound"] = {"sheet": sh, "station": es, "xy": [round(v, 1) for v in xy]}
                break

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

    # DROP-TERMINUS SYMBOL BIND (opt-in `drop_terminus_symbol_bind`; gated): single-sheet drop whose terminus
    # is a drawn flower-pot/drop symbol with NO bindable station label. Fires AFTER end-symbol-bind and
    # end-at-matchline (a labeled HH / a matchline-exit terminus wins first), only when the start bound and the
    # end did not. All gates are inside _solve_drop_terminus (traceable BASE_CONDUIT chain, unique symbol at
    # span, source-backed leg, mandatory closure). Self-contained -> returns the render plan or a named blocker.
    if (s_sheet is not None and sc in MODELED and e_sheet is None
            and r.get("drop_terminus_symbol_bind") and _end_cls in MODELED and es):
        return _solve_drop_terminus(plan, offset, out, s_sheet, sc, s_lbl, ss, es, _end_cls, span)

    if s_sheet is None or e_sheet is None or sc not in MODELED or ec not in MODELED:
        out["blocker"] = (f"terminus did not resolve to a UNIQUE (sheet,class) source bind "
                          f"(start->s{s_sheet}/{sc}; end->s{e_sheet}/{ec})")
        return out

    if s_xy_ov is not None:                       # owner-confirmed start context bind (standard locator failed)
        s_xy, s_words, s_draw = s_xy_ov, plan.words(s_sheet, offset), plan.line_items(s_sheet, offset)
    else:
        s_xy, s_words, s_draw, _ = _bind(plan, offset, s_sheet, sc, s_lbl)
    if e_xy_ov is not None:                       # owner-confirmed end symbol bind (standard locator failed)
        e_xy, e_words, e_draw = e_xy_ov, plan.words(e_sheet, offset), plan.line_items(e_sheet, offset)
    else:
        e_xy, e_words, e_draw, _ = _bind(plan, offset, e_sheet, ec, e_lbl)
    cset = _conduit_set_for(r)                     # default BASE_CONDUIT; fiber opt-in adds BORE-PATH (gated)
    s_chain = _chain_at(s_draw, sc, s_xy, cset)
    e_chain = _chain_at(e_draw, ec, e_xy, cset)
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
    # OWNER-CONFIRMED MATCHLINE SEE-SHEET TYPO (opt-in `matchline_see_sheet_typo`; tightly gated): the start
    # sheet prints the matchline at <station> as 'SEE SHEET <printed>' (a plan typo) instead of the real
    # partner <e_sheet>, so see_sheet_crossings can't find the join. Apply ONLY when (1) that exact wrong
    # crossing is UNIQUELY printed on the start sheet at <station>, AND (2) the partner sheet prints the
    # RECIPROCAL 'SEE SHEET <s_sheet>' at the SAME <station> -- so the physical join is still source-confirmed
    # from BOTH sheets; only the start-sheet's sheet NUMBER is corrected. Never a broad sheet-ref override.
    typo = r.get("matchline_see_sheet_typo")
    if not crossings and typo and typo.get("start_sheet") == s_sheet and typo.get("end_sheet") == e_sheet:
        sta = typo["station"]
        wrong = [c for c in see_sheet_crossings(s_lines, typo["printed_sheet"], "MATCHLINE") if sta in c]
        recip = [c for c in see_sheet_crossings(plan.lines(e_sheet, offset), s_sheet, "MATCHLINE") if sta in c]
        if len(wrong) == 1 and recip:
            crossings = wrong
            out["matchline_typo_applied"] = {"station": sta, "printed_see_sheet": typo["printed_sheet"],
                                             "corrected_to": e_sheet, "reciprocal_confirmed": True}
    out["printed_crossings_start_to_end"] = [list(c) for c in crossings]
    if not crossings:
        mids = [s for s in sheets if s not in (s_sheet, e_sheet)]
        if len(mids) == 1:
            # 3-sheet route: start -> intermediate -> end, joined by two printed matchline crossings
            out["_ss"], out["_es"] = ss, es
            return _solve_nleg(plan, offset, out, s_sheet, mids[0], e_sheet,
                               s_xy, s_chain, s_words, s_draw, e_xy, e_chain, e_words, e_draw, span,
                               conduit_set=cset,
                               matchline_identity_join=r.get("nleg_matchline_identity_join"))
        if mids:
            out["blocker"] = (f"N-leg route with {len(mids)} intermediate sheets {mids} not supported "
                              f"(only a single intermediate sheet is implemented)")
        else:
            out["blocker"] = f"no printed SEE-SHEET matchline crossing between sheets {s_sheet} and {e_sheet}"
        return out

    # CROSS-SHEET DROP TERMINUS (opt-in `cross_sheet_drop_terminus`; gated). A drop whose start binds on
    # s_sheet but whose terminus is on a continuation sheet PAST the matchline (the single-sheet
    # drop_terminus_symbol_bind returns 0 candidates). Self-contained -> selects each leg's boundary by the
    # SEE-SHEET-<partner> matchline identity (bundled-matchline tolerant) and joins two source-backed legs by
    # printed station identity, gated by full-route closure. Fires only when both termini already bound (the
    # owner-confirmed terminus binds by its printed label) and both legs have a BASE_CONDUIT chain.
    if r.get("cross_sheet_drop_terminus"):
        return _solve_cross_sheet_drop_terminus(plan, offset, out, s_sheet, ss, e_sheet, es,
                                                 s_xy, s_chain, s_words, s_draw,
                                                 e_xy, e_chain, e_words, e_draw, crossings, span,
                                                 parallel_by_chain_reach=r.get("parallel_crossing_by_chain_reach"))

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

    # PARTNER-SHEET BOUNDARY SELECTOR (opt-in `crossing_by_partner_sheet`; gated so existing renders are
    # byte-identical). Identify each leg's cross-sheet boundary by the matchline carrying the printed
    # 'MATCHLINE STA <sta> ... SEE SHEET <partner>' line (the reciprocal printed crossing IDENTITY), then
    # extend each leg's own conduit chain to its own partner matchline. Needed when the crossing station is
    # also printed in a mid-sheet run callout next to a DIFFERENT matchline, so the per-token locator (and
    # _ml_bbox's first-token pick) snap to the WRONG physical line (log2: the start chain's '18+38' token by
    # the SEE-SHEET-22 line -> a 215' partial instead of the 616' run to the right-edge SEE-SHEET-19 line).
    # Uniqueness + printed-span closure gate every leg; any non-unique matchline / unreached chain abstains.
    if r.get("crossing_by_partner_sheet"):
        sta = crossings[0][0] if (len(crossings) == 1 and len(crossings[0]) == 1) else None
        s_mlb = _partner_matchline_bbox(s_words, s_draw, sta, e_sheet) if sta else None
        e_mlb = _partner_matchline_bbox(e_words, e_draw, sta, s_sheet) if sta else None
        out["partner_matchline"] = {"station": sta,
                                    "start_bbox": [round(v, 1) for v in s_mlb] if s_mlb else None,
                                    "end_bbox": [round(v, 1) for v in e_mlb] if e_mlb else None}
        if not (s_mlb and e_mlb):
            out["blocker"] = ("partner-sheet selector: 'MATCHLINE STA <sta> - SEE SHEET <partner>' not "
                              f"uniquely identified (start s{s_sheet}->partner {e_sheet}, end s{e_sheet}->"
                              f"partner {s_sheet}; sta={sta})")
            return out
        s_bnd = extend_dash_to_boundary(s_chain, s_mlb)
        e_bnd = extend_dash_to_boundary(e_chain, e_mlb)
        if s_bnd is None or e_bnd is None:
            out["blocker"] = "partner-sheet selector: a leg conduit chain does not reach its partner matchline"
            return out
        s_route, s_ok = _ordered_leg(s_chain, s_xy, tuple(s_bnd))
        e_route, e_ok = _ordered_leg(e_chain, tuple(e_bnd), e_xy)
        out["start_leg_source_backed"], out["end_leg_source_backed"] = s_ok, e_ok
        if not (s_ok and e_ok):
            out["blocker"] = f"partner-sheet selector: leg route not source-backed (start {s_ok}, end {e_ok})"
            return out
        drawn_ft = (route_length(s_route) + route_length(e_route)) / SCALE
        closes = bool(span) and abs(drawn_ft - span) <= CLOSURE_REL_TOL * span
        out["closure"] = {"drawn_ft": round(drawn_ft, 1), "span_ft": span, "closes": closes}
        if not closes:
            out["blocker"] = (f"partner-sheet selector closure failed: {round(drawn_ft, 1)} ft vs span "
                              f"{span} ft (>{int(CLOSURE_REL_TOL*100)}% -> wrong crossing/partial)")
            return out
        out["crossing_equation"] = list(crossings[0])
        out["legs"] = [
            {"sheet": s_sheet, "route": s_route, "a_xy": s_xy, "b_xy": list(s_bnd),
             "len_pt": round(route_length(s_route), 1), "kind": "start_leg", "start_label": ss, "matchline_sta": sta},
            {"sheet": e_sheet, "route": e_route, "a_xy": list(e_bnd), "b_xy": e_xy,
             "len_pt": round(route_length(e_route), 1), "kind": "end_leg", "end_label": es, "matchline_sta": sta},
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
        elif leg["kind"] == "drop_terminus":
            reason = (f"{lid} sheet-{leg['sheet']} drop: {leg['start_label']} -> symbol-only "
                      f"{v.get('end_class')} terminus (single sheet; bound to the UNIQUE drop-terminus symbol "
                      f"at the printed span along the source-backed conduit chain -- no station label); "
                      f"printed-span closure")
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
