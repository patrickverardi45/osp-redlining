"""LOG68 CALLOUT-SPAN WITNESS BINDING SLICE (PROOF; read-only; product-gated; REVIEW-only).

A single, witness-gated proof slice for ONE bore whose endpoint identity is a printed DIRECT-BORE CALLOUT
SPAN rather than a modeled structure class (closure ledger ``UNMODELED_TERMINUS_CLASS_NEEDED``). The read-only
printed-identity probe proved a UNIQUE ``DIRECT_BORE_CALLOUT_SPAN_WITNESS`` for it — ``STA 5+03 TO STA 6+79
... 176'`` on the title-block-resolved sheet. This slice binds that witness to a single sheet-local drawn leg
and renders exactly ONE red REVIEW-candidate stroke, or ABSTAINS with a named reason. It can NEVER produce a
wrong redline: every precondition abstains rather than guesses, and printed-span closure is the false-positive
backstop (a stroke that bled into the sibling continuation would fail closure and abstain).

SHAPE (the proven single-sheet ``matchline_terminus`` render shape, reused — NOT rebuilt):
  start   the printed callout START station, source-bound via the read-only plan-view anchor resolver
          (ROUTE_TERMINUS / leader / symbol — never nearest-snap; ambiguous -> abstain)
  leg     the source-backed conduit chain connected to that anchor (``connected_chain``; empty -> abstain)
  end     the printed SEE-SHEET matchline boundary the chain reaches at the callout END station
          (``locate_matchline_boundary``; not uniquely reached -> abstain)
  closes  the drawn leg length closes against the printed span (``176'`` +- CLOSURE_REL_TOL; else abstain)
  -> ONE dashed red REVIEW stroke on the start sheet, terminating AT the matchline (never past it).

SIBLING CONTAINMENT (hard, tested): the bore's END is the callout ``6+79`` matchline; the sheet also prints a
SEPARATE continuation callout and a sibling start station that belong to OTHER bores. This slice references ONLY
the log's own start/end stations; it refuses if the selected crossing carries the sibling continuation station,
and printed-span closure rejects any leg that runs into the sibling segment. The sibling tokens are declared as
FORBIDDEN and asserted absent from every route-derivation input.

STRICT SCOPE — this module: composes only shipped read-only observers (anchor resolver, conduit topology,
matchline join) + the render primitive; imports the callout-route sweep's geometry helpers READ-ONLY (never
edits it); parses no new grammar; encodes no coordinate (all xy observer-derived); mutates NOTHING; edits no
adjudication artifact (the owner record is READ for the corrected span/sheets only); tunes no threshold; makes
no AUTO / final / promotion / frontier claim; touches no other bore. Output is ONE PNG + ONE JSON under a
DEDICATED ``data/outputs/`` subdir — NEVER the sweep's tripwire-tracked render dir. Honest skip (nothing
written) when the plan is absent.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from truelinev2.config import _REPO_ROOT
from truelinev2.extract.leader_symbol_trace import _BOX_MARGIN, _label_boxes, _leaders  # read-only reuse (never edited)
from truelinev2.extract.leader_symbol_trace import AMBIGUOUS_LEADER
from truelinev2.extract.plan_view_anchor_resolver import (
    AMBIGUOUS_ANCHOR,
    AnchorResolution,
    resolve_label_anchor,
    resolve_plan_view_anchor_for_path,
)
# Read-only reuse of the callout-route sweep's PROVEN geometry helpers + constants (identical semantics; the
# sweep is never edited). SCALE / CLOSURE_REL_TOL / BASE_CONDUIT / _ordered_leg / route_length /
# locate_matchline_boundary / connected_chain / see_sheet_crossings are the single source of render truth.
from truelinev2.proof.run_callout_route_assembly_sweep import (
    BASE_CONDUIT,
    CLOSURE_REL_TOL,
    SCALE,
    _ordered_leg,
    connected_chain,
    locate_matchline_boundary,
    route_length,
    see_sheet_crossings,
)
from truelinev2.proof.run_printed_identity_witness_probe import (
    DIRECT_BORE_CALLOUT_SPAN_WITNESS,
    FOUND,
    match_direct_bore_callout,
    witness_result,
)
from truelinev2.render.crop import REDLINE_STROKE_RGB, render_redline_stroke
from truelinev2.stations import feet_to_station, parse_station

# --- this slice's ONE target (a generic corpus log id; no customer/person/place tokens) ------------------- #
_LOG_ID = "log68"
# The bore's OWN stations (read from the owner adjudication at runtime; these literals are only the
# probe/adjudication-quoted callout identity, used to gate + as a runtime-vs-artifact consistency check).
_CALLOUT_START_STA = "5+03"
_CALLOUT_END_STA = "6+79"
# Sibling continuation / sibling-start stations that belong to OTHER bores on the same sheet — FORBIDDEN here.
_FORBIDDEN_SIBLING_STATIONS = ("7+21", "4+54")
_SEED_EPS = 1.0                     # a point-sized seed bbox around the bound start anchor (chain seeding)

# --- callout-box anchor FALLBACK (entered ONLY on a bare-station AMBIGUOUS_ANCHOR) ------------------------- #
# The bare token 5+03 prints in >= 2 callouts on the sheet (this bore's start AND a neighbor's end), so the
# station-token resolver honestly refuses. The FULL callout phrase, however, is UNIQUE (probe-proven), so the
# fallback anchors from the unique callout BOX + its own leader: phrase search -> exactly-1 bbox -> words
# FILTERED to that bbox (label identity confined to THIS callout instance; leader/symbol geometry stays
# whole-sheet) -> the existing resolve_label_anchor -> accept ONLY leader-backed evidence. A Tier-2 proximity
# symbol near the box could be a SIBLING's structure -> refused (zero-false beats coverage).
_CALLOUT_PHRASE = "STA %s TO STA %s" % (_CALLOUT_START_STA, _CALLOUT_END_STA)
_BOX_PAD = 6.0                      # pt: word-center containment pad around the searched callout bbox
_LEADER_METHODS = ("LEADER_TRACED_SYMBOL", "LEADER_TIP")   # the ONLY accepted anchor evidence in this mode

# --- chain-reach uniqueness (entered ONLY when the unique innermost row STILL has >= 2 leaders) ------------ #
# When the callout box is unique but N leaders leave it, we DO NOT pick by direction/proximity/length. Every
# leader tip is tested against the SAME physical predicate — seed the conduit chain at the tip, uniquely reach
# the 6+79 matchline, close to 176' — and accepted ONLY if EXACTLY ONE tip's leg closes (0 or >= 2 -> abstain).
# The survivor's provenance is physical (chain reach), not the tracer's leader-uniqueness, so it gets its OWN
# method name and NEVER claims LEADER_TRACED_SYMBOL. This is the sweep's committed chain-reach pattern, applied
# per-candidate — a binary source-backed predicate + exactly-one survivor, NOT a preference heuristic.
_CHAIN_REACH_METHOD = "CHAIN_REACH_LEADER_TIP"
_CHAIN_REACH_MODE = "CALLOUT_BOX_LEADER_CHAIN_REACH"

# --- result statuses ------------------------------------------------------------------------------------- #
REVIEW_CANDIDATE_RENDERED = "LOG68_CALLOUT_SPAN_REVIEW_CANDIDATE_RENDERED"    # the single positive
WITNESS_NOT_FOUND = "WITNESS_NOT_FOUND"
WITNESS_AMBIGUOUS = "WITNESS_AMBIGUOUS"
ADJUDICATED_SPAN_UNAVAILABLE = "ADJUDICATED_SPAN_UNAVAILABLE"
SHEET_REF_UNRESOLVED = "SHEET_REF_UNRESOLVED"
START_ANCHOR_AMBIGUOUS = "START_ANCHOR_AMBIGUOUS"
START_ANCHOR_UNRESOLVED = "START_ANCHOR_UNRESOLVED"
CALLOUT_BOX_NOT_FOUND = "CALLOUT_BOX_NOT_FOUND"
CALLOUT_BOX_AMBIGUOUS = "CALLOUT_BOX_AMBIGUOUS"
CALLOUT_LEADER_AMBIGUOUS = "CALLOUT_LEADER_AMBIGUOUS"
CALLOUT_ANCHOR_NOT_LEADER_BACKED = "CALLOUT_ANCHOR_NOT_LEADER_BACKED"
CALLOUT_ROW_BOX_NOT_PHRASE_CONTAINING = "CALLOUT_ROW_BOX_NOT_PHRASE_CONTAINING"
CALLOUT_ROW_BOX_NOT_NESTED = "CALLOUT_ROW_BOX_NOT_NESTED"
LEADER_CHAIN_REACH_NONE = "LEADER_CHAIN_REACH_NONE"                # 0 leader tips produce a closing leg
LEADER_CHAIN_REACH_NOT_UNIQUE = "LEADER_CHAIN_REACH_NOT_UNIQUE"    # >= 2 leader tips produce a closing leg
NO_CONDUIT_CHAIN_AT_START = "NO_CONDUIT_CHAIN_AT_START"
MATCHLINE_ENDPOINT_NOT_FOUND = "MATCHLINE_ENDPOINT_NOT_FOUND"
SIBLING_BLEED_DETECTED = "SIBLING_BLEED_DETECTED"
LEG_NOT_SOURCE_BACKED = "LEG_NOT_SOURCE_BACKED"
CLOSURE_FAILED = "CLOSURE_FAILED"
RENDER_PRODUCED_NO_STROKE = "RENDER_PRODUCED_NO_STROKE"

_OUT_DIR = _REPO_ROOT / "data" / "outputs" / "truelinev2" / "log68_callout_span_witness"


@dataclass(frozen=True)
class Log68SliceResult:
    """Outcome of the one binding attempt. ``rendered`` True with exactly one PNG, or a NAMED refusal.
    ``performs_auto`` / ``performs_promotion`` are ALWAYS False — REVIEW evidence only, no frontier change."""
    status: str
    rendered: bool
    reason: str
    png: Optional[str]
    evidence_chain: Tuple[str, ...]
    detail: Dict[str, Any] = field(default_factory=dict)
    is_review_candidate: bool = True
    performs_auto: bool = False
    performs_final_placement: bool = False
    performs_promotion: bool = False
    changes_frontier: bool = False

    def to_dict(self) -> dict:
        return {"log_id": _LOG_ID, "status": self.status, "rendered": self.rendered, "reason": self.reason,
                "png": self.png, "evidence_chain": list(self.evidence_chain), "detail": dict(self.detail),
                "is_review_candidate": self.is_review_candidate, "performs_auto": self.performs_auto,
                "performs_final_placement": self.performs_final_placement,
                "performs_promotion": self.performs_promotion, "changes_frontier": self.changes_frontier}


def _refuse(status: str, reason: str, chain=(), detail=None) -> Log68SliceResult:
    return Log68SliceResult(status=status, rendered=False, reason=reason, png=None,
                            evidence_chain=tuple(chain), detail=dict(detail or {}))


def _log68_record() -> Dict[str, Any]:
    """The owner adjudication record for this log (READ-ONLY; the artifact is never edited). {} if absent."""
    try:
        from truelinev2.ingest.manual_adjudication import load_adjudication
        for r in load_adjudication()["logs"]:
            if r.get("log_id") == _LOG_ID:
                return r
    except Exception:  # noqa: BLE001 - a missing/unreadable artifact -> a NAMED refusal upstream, never a guess
        pass
    return {}


def _forbidden_tokens_absent(*texts: str) -> Optional[str]:
    """The first FORBIDDEN sibling station appearing in any supplied text, else None. Used as a hard gate so a
    sibling continuation station can never be consumed by this bore's route derivation."""
    blob = " ".join(str(t) for t in texts)
    for tok in _FORBIDDEN_SIBLING_STATIONS:
        if re.search(r"\b" + re.escape(tok) + r"\b", blob):
            return tok
    return None


def _unique_callout_bbox(bboxes: Sequence[Sequence[float]]) -> Tuple[Optional[Tuple[float, ...]], Optional[str]]:
    """(bbox, None) for EXACTLY one phrase hit; else (None, named refusal). Pure — never picks among >= 2."""
    if not bboxes:
        return None, CALLOUT_BOX_NOT_FOUND
    if len(bboxes) > 1:
        return None, CALLOUT_BOX_AMBIGUOUS
    return tuple(float(v) for v in bboxes[0]), None


def _accept_leader_anchor(res: AnchorResolution) -> Tuple[Optional[Tuple[float, float]], Optional[str]]:
    """(xy, None) ONLY for a leader-backed resolution (LEADER_TRACED_SYMBOL / LEADER_TIP); else (None, named
    refusal). Ambiguity (the resolver's AMBIGUOUS_ANCHOR) -> CALLOUT_LEADER_AMBIGUOUS; anything unresolved or
    proximity/route-tier -> CALLOUT_ANCHOR_NOT_LEADER_BACKED (a nearby symbol may belong to a SIBLING). Pure."""
    if res.status == AMBIGUOUS_ANCHOR:
        return None, CALLOUT_LEADER_AMBIGUOUS
    if res.resolved and res.method in _LEADER_METHODS and res.x is not None and res.y is not None:
        return (float(res.x), float(res.y)), None
    return None, CALLOUT_ANCHOR_NOT_LEADER_BACKED


def _box_contains(outer: Dict[str, Any], x0: float, y0: float, x1: float, y1: float,
                  m: float = _BOX_MARGIN) -> bool:
    """True when rect (x0,y0,x1,y1) lies inside drawing ``outer``'s bbox within the tracer's own margin."""
    return (float(outer["x0"]) - m <= x0 and x1 <= float(outer["x1"]) + m
            and float(outer["y0"]) - m <= y0 and y1 <= float(outer["y1"]) + m)


def _same_frame(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    """MUTUAL containment within the tracer's own margin = COINCIDENT representations of ONE physical drawn
    frame (CAD exports emit the same callout box several times: fill + border + duplicates). This is identity
    recognition — the exact analogue of the codebase's SAME_POINT_TOL / symbol-footprint dedup — never a
    choice between different frames."""
    return (_box_contains(a, float(b["x0"]), float(b["y0"]), float(b["x1"]), float(b["y1"]))
            and _box_contains(b, float(a["x0"]), float(a["y0"]), float(a["x1"]), float(a["y1"])))


def _innermost_row_box(candidates: Sequence[Dict[str, Any]], phrase_bbox: Sequence[float]
                       ) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]], Optional[str]]:
    """The UNIQUE innermost callout ROW frame: of the label boxes framing the word, keep those that contain
    the FULL printed phrase bbox; group coincident duplicates into ONE physical frame (``_same_frame``); then
    require exactly one frame CLASS nested inside every other (the unique minimum of the containment partial
    order — strict geometry, no area score, no ranking between DIFFERENT frames). Returns (chosen | None,
    rejected_frames, refusal | None): ``chosen`` is the innermost class's deterministic representative (the
    smallest rect, coordinate-lexicographic tiebreak — coincident rects are geometrically interchangeable);
    ``rejected`` is EVERY other candidate drawing (other classes, sub-cell frames, AND the chosen class's
    duplicate exports), so a retry trace sees exactly ONE label box. 0 survivors / no unique innermost class
    -> named refusal (genuinely different non-nested frames are never chosen between)."""
    px0, py0, px1, py1 = (float(v) for v in phrase_bbox)
    survivors = [b for b in candidates if _box_contains(b, px0, py0, px1, py1)]
    if not survivors:
        return None, [], CALLOUT_ROW_BOX_NOT_PHRASE_CONTAINING
    # coincidence classes over the survivors (greedy by mutual containment — transitive at these tolerances)
    classes: List[List[Dict[str, Any]]] = []
    for b in survivors:
        for cls in classes:
            if _same_frame(b, cls[0]):
                cls.append(b)
                break
        else:
            classes.append([b])
    inner = [cls for cls in classes
             if all(cls is other or _box_contains(other[0], float(cls[0]["x0"]), float(cls[0]["y0"]),
                                                  float(cls[0]["x1"]), float(cls[0]["y1"]))
                    for other in classes)]
    if len(inner) != 1:
        return None, [], CALLOUT_ROW_BOX_NOT_NESTED
    chosen = min(inner[0], key=lambda d: ((float(d["x1"]) - float(d["x0"])) * (float(d["y1"]) - float(d["y0"])),
                                          float(d["x0"]), float(d["y0"]), float(d["x1"]), float(d["y1"])))
    return chosen, [b for b in candidates if b is not chosen], None


def _row_forbidden_token(words, chosen: Dict[str, Any]) -> Optional[str]:
    """The first FORBIDDEN sibling station printed INSIDE the chosen row frame (word-center containment,
    tracer margin), else None — the chosen row must belong to THIS bore's callout, never a sibling's."""
    row = [str(w.get("text", "")) for w in words
           if _box_contains(chosen, float(w.get("xc", 0)), float(w.get("yc", 0)),
                            float(w.get("xc", 0)), float(w.get("yc", 0)))]
    return _forbidden_tokens_absent(*row)


def _callout_box_anchor(plan, sheet: int, offset: int, words, draw, leg_predicate=None
                        ) -> Tuple[Optional[Tuple[float, float]], Optional[str], Dict[str, Any]]:
    """Anchor the start from the UNIQUE printed callout box + its own leader (the fallback for the ambiguous
    bare station token). Returns (xy | None, refusal | None, detail). Composes ONLY shipped observers:
    ``plan.search`` (phrase -> bbox), then ``resolve_label_anchor`` over the words INSIDE that bbox (the label
    identity is confined to THIS callout instance) with whole-sheet line_items/shapes for leader geometry.
    Accepts leader-backed evidence only; every other outcome is a NAMED refusal, never a guess."""
    detail: Dict[str, Any] = {"phrase": _CALLOUT_PHRASE, "mode": "CALLOUT_BOX_LEADER"}
    bbs = plan.search(sheet, offset, _CALLOUT_PHRASE)
    detail["phrase_bbox_hits"] = len(bbs)
    bbox, refusal = _unique_callout_bbox(bbs)
    if refusal is not None:
        return None, refusal, detail
    x0, y0, x1, y1 = bbox
    inside = [w for w in words
              if (x0 - _BOX_PAD) <= float(w.get("xc", 0)) <= (x1 + _BOX_PAD)
              and (y0 - _BOX_PAD) <= float(w.get("yc", 0)) <= (y1 + _BOX_PAD)]
    label_words = [w for w in inside if _CALLOUT_START_STA in str(w.get("text", ""))]
    detail["box_words"], detail["label_word_candidates"] = len(inside), len(label_words)
    if len(label_words) != 1:               # cannot isolate ONE label word inside the unique box -> refuse
        return None, CALLOUT_ANCHOR_NOT_LEADER_BACKED, detail
    lw = label_words[0]
    label_token, label_xy = str(lw["text"]), (float(lw["xc"]), float(lw["yc"]))
    shapes = plan.vector_segments(sheet, offset)
    res = resolve_label_anchor(inside, draw, shapes, label_token=label_token, label_xy=label_xy)
    detail["anchor"] = res.to_dict()
    xy, refusal = _accept_leader_anchor(res)
    if refusal != CALLOUT_LEADER_AMBIGUOUS or res.detail.get("leader_trace") != AMBIGUOUS_LEADER:
        return xy, refusal, detail          # accepted, or a refusal the row retry cannot help

    # --- innermost-row retry (entered ONLY after a first-pass AMBIGUOUS_LEADER) ---------------------------
    # The stacked callout table frames >= 2 label boxes around the word, so the uniqueness-mandatory tracer
    # refused. Select the UNIQUE innermost phrase-containing row frame by strict containment geometry, drop
    # the other frame drawings from line_items, and re-run the UNCHANGED shared tracer once — its own
    # leader/tip/symbol uniqueness gates stay authoritative. Words + whole-sheet shapes are untouched.
    candidates = _label_boxes(draw, label_xy)
    rr: Dict[str, Any] = {"label_box_candidates": len(candidates)}
    detail["row_retry"] = rr
    if len(candidates) <= 1:                # the ambiguity was NOT the box hop — the retry cannot help
        return None, CALLOUT_LEADER_AMBIGUOUS, detail
    chosen, rejected, row_refusal = _innermost_row_box(candidates, bbox)
    rr["phrase_containing"] = sum(1 for b in candidates
                                  if _box_contains(b, x0, y0, x1, y1))
    if row_refusal is not None:
        return None, row_refusal, detail
    rr["chosen_bbox"] = [round(float(chosen[k]), 1) for k in ("x0", "y0", "x1", "y1")]
    rr["rejected_frames"] = len(rejected)
    tok = _row_forbidden_token(words, chosen)
    if tok is not None:
        rr["forbidden_token"] = tok
        return None, SIBLING_BLEED_DETECTED, detail
    rej_ids = {id(b) for b in rejected}
    res2 = resolve_label_anchor(inside, [d for d in draw if id(d) not in rej_ids], shapes,
                                label_token=label_token, label_xy=label_xy)
    detail["first_pass_anchor"] = detail["anchor"]
    detail["anchor"] = res2.to_dict()
    rr["mode"] = "INNERMOST_ROW_BOX"
    xy2, refusal2 = _accept_leader_anchor(res2)
    if refusal2 != CALLOUT_LEADER_AMBIGUOUS or leg_predicate is None:
        return xy2, refusal2, detail          # accepted, a non-ambiguity refusal, or no predicate to test with

    # --- chain-reach uniqueness (entered ONLY when the unique innermost row STILL has >= 2 leaders) --------
    # The row box is unique but several leader segments leave it, so the tracer's leader hop stays ambiguous.
    # DO NOT pick by direction/proximity/length: test EACH leader tip against the SAME physical predicate (seed
    # chain -> unique 6+79 matchline -> 176' closure -> terminal = boundary) and accept ONLY a unique survivor.
    tips = _leaders([d for d in draw if id(d) not in rej_ids],
                    (float(chosen["x0"]), float(chosen["y0"]), float(chosen["x1"]), float(chosen["y1"])))
    cr: Dict[str, Any] = {"leader_tips": len(tips), "candidates": []}
    detail["chain_reach"] = cr
    survivors: List[Tuple[float, float]] = []
    for (_ax, _ay, tx, ty) in tips:                 # tip is the far endpoint (box end first; see _leaders)
        ok, why, dft = leg_predicate((float(tx), float(ty)))
        cr["candidates"].append({"tip": [round(float(tx), 1), round(float(ty), 1)], "passes": bool(ok),
                                 "eliminated_by": None if ok else why,
                                 "drawn_ft": round(float(dft), 1) if (ok and dft is not None) else None})
        if ok:
            survivors.append((float(tx), float(ty)))
    cr["survivor_count"] = len(survivors)
    if len(survivors) == 0:
        return None, LEADER_CHAIN_REACH_NONE, detail
    if len(survivors) > 1:
        return None, LEADER_CHAIN_REACH_NOT_UNIQUE, detail
    cr["survivor"] = [round(survivors[0][0], 1), round(survivors[0][1], 1)]
    detail["method"] = _CHAIN_REACH_METHOD               # physical provenance, NOT the tracer's leader-uniqueness
    detail["mode"] = _CHAIN_REACH_MODE
    return survivors[0], None, detail


@dataclass(frozen=True)
class _LegBind:
    """Outcome of binding ONE start_xy to the sheet-local leg (chain -> unique 6+79 matchline -> 176' closure
    -> terminal = boundary). ``ok`` True with route/bnd/drawn_ft; else a NAMED refusal + reason. ``sub_chain``
    carries the evidence-chain lines to splice into the caller. Read-only; renders NOTHING (this is also the
    chain-reach candidate predicate — it must never draw)."""
    ok: bool
    status: Optional[str]
    reason: str
    route: Optional[List[Any]] = None
    bnd: Optional[Tuple[float, float]] = None
    drawn_ft: Optional[float] = None
    sub_chain: Tuple[str, ...] = ()
    detail: Dict[str, Any] = field(default_factory=dict)


def _bind_leg_from_start(start_xy: Tuple[float, float], *, words, draw, conduit, chain_lines, partners,
                         end_sta: str, span, leg_sheet: int) -> _LegBind:
    """Bind the single sheet-local leg from ``start_xy``: seed the conduit chain, uniquely reach the printed
    ``end_sta`` SEE-SHEET matchline boundary, close against the printed span, and require the terminal vertex
    to BE the boundary (never past it). The SAME gates the main flow uses and the chain-reach predicate tests
    per candidate — one source of truth. Read-only; draws nothing."""
    sub: List[str] = []
    seed = (start_xy[0] - _SEED_EPS, start_xy[1] - _SEED_EPS, start_xy[0] + _SEED_EPS, start_xy[1] + _SEED_EPS)
    chain_segs = connected_chain(conduit, seed)
    if not chain_segs:
        return _LegBind(False, NO_CONDUIT_CHAIN_AT_START,
                        "no source-backed conduit chain is connected to the bound start on sheet %d "
                        "(fiber/generic path or off-conduit anchor) — refusing" % leg_sheet)
    partner_crossings = [c for p in partners for c in see_sheet_crossings(chain_lines, p, "MATCHLINE")]
    end_crossings = [c for c in partner_crossings if end_sta in c]
    if not end_crossings:
        return _LegBind(False, MATCHLINE_ENDPOINT_NOT_FOUND,
                        "no printed SEE-SHEET matchline crossing carries the callout end %s to a partner sheet "
                        "%s on sheet %d" % (end_sta, partners, leg_sheet))
    bleed = _forbidden_tokens_absent(*["/".join(c) for c in end_crossings])
    if bleed is not None:
        return _LegBind(False, SIBLING_BLEED_DETECTED,
                        "the selected end matchline crossing also carries the forbidden sibling continuation "
                        "station %s — refusing to bind into the sibling bore" % bleed)
    bnd, reach, uniq = locate_matchline_boundary(words, draw, end_sta, chain_segs)
    if bnd is None or not uniq:
        return _LegBind(False, MATCHLINE_ENDPOINT_NOT_FOUND,
                        "the callout end matchline %s is not uniquely reached by the start chain on sheet %d "
                        "(reach %s, unique %s)" % (end_sta, leg_sheet, reach, uniq))
    sub.append("end bound at MATCHLINE STA %s (SEE SHEET %s) boundary (%.1f, %.1f)"
               % (end_sta, partners, bnd[0], bnd[1]))
    route, ok = _ordered_leg(chain_segs, start_xy, tuple(bnd))
    if not ok:
        return _LegBind(False, LEG_NOT_SOURCE_BACKED,
                        "the start -> matchline leg is not a source-backed ordered conduit route on sheet %d"
                        % leg_sheet, sub_chain=tuple(sub))
    drawn_ft = route_length(route) / SCALE
    closes = abs(drawn_ft - float(span)) <= CLOSURE_REL_TOL * float(span)
    sub.append("leg closure: drawn %.1f ft vs printed span %d ft (tol %d%%) -> %s"
               % (drawn_ft, int(span), int(CLOSURE_REL_TOL * 100), "closes" if closes else "FAILS"))
    if not closes:
        return _LegBind(False, CLOSURE_FAILED,
                        "leg draws %.1f ft vs printed span %d ft (> %d%%) — a partial/over-run (would bleed into "
                        "the sibling continuation) — refusing"
                        % (drawn_ft, int(span), int(CLOSURE_REL_TOL * 100)), route=route, bnd=tuple(bnd),
                        drawn_ft=drawn_ft, sub_chain=tuple(sub),
                        detail={"drawn_ft": round(drawn_ft, 1), "span_ft": int(span)})
    if route[-1] != tuple(bnd):
        return _LegBind(False, MATCHLINE_ENDPOINT_NOT_FOUND,
                        "the leg's terminal vertex is not the matchline boundary — refusing", route=route,
                        bnd=tuple(bnd), sub_chain=tuple(sub))
    return _LegBind(True, None, "closes", route=route, bnd=tuple(bnd), drawn_ft=drawn_ft, sub_chain=tuple(sub))


def bind_and_render(plan_path: str, *, out_dir: Optional[str] = None, render: bool = True) -> Log68SliceResult:
    """Run the full witness-gated bind for log68 on the title-block-resolved sheet, rendering ONE REVIEW
    stroke or returning a NAMED refusal. Read-only except the ONE PNG/JSON written under ``out_dir``."""
    from truelinev2.ingest.pdf import PlanPdf
    from truelinev2.ingest.sheet_label_index import build_sheet_index

    out_dir = out_dir or str(_OUT_DIR)
    rec = _log68_record()
    span = rec.get("span_ft")
    start_sta = rec.get("corrected_start") or _CALLOUT_START_STA
    end_sta = rec.get("corrected_end") or _CALLOUT_END_STA
    sheets = [int(s) for s in (rec.get("corrected_sheets") or ())]
    if not span or not sheets:
        return _refuse(ADJUDICATED_SPAN_UNAVAILABLE,
                       "the owner adjudication record for this log is absent/incomplete (span + corrected "
                       "sheets required) — refusing rather than assuming a span/sheet")
    # runtime-vs-artifact consistency: the adjudicated callout stations must equal the probe-quoted identity
    if (start_sta, end_sta) != (_CALLOUT_START_STA, _CALLOUT_END_STA):
        return _refuse(ADJUDICATED_SPAN_UNAVAILABLE,
                       "adjudicated callout stations %s->%s disagree with the proven witness %s->%s — refusing"
                       % (start_sta, end_sta, _CALLOUT_START_STA, _CALLOUT_END_STA))
    bleed = _forbidden_tokens_absent(start_sta, end_sta)
    if bleed is not None:                  # the log's OWN stations must never be a sibling station
        return _refuse(SIBLING_BLEED_DETECTED,
                       "a forbidden sibling station %s appears in this log's own callout identity — refusing" % bleed)

    start_ft, end_ft = parse_station(start_sta), parse_station(end_sta)
    if start_ft is None or end_ft is None:
        return _refuse(ADJUDICATED_SPAN_UNAVAILABLE, "callout stations are not parseable")

    plan = PlanPdf(str(plan_path))
    try:
        idx = build_sheet_index(plan)
        # the leg sheet is the witness sheet; the OTHER corrected sheet is the partner (SEE-SHEET continuation)
        chain_out: Dict[str, Any] = {}
        for leg_sheet in sheets:
            resolved = idx.resolve_construction_sheet(leg_sheet)
            if resolved is None:
                continue
            offset = int(resolved) - leg_sheet
            lines = plan.lines(leg_sheet, offset)
            hits = match_direct_bore_callout(lines, start_sta, end_sta)
            wres = witness_result(DIRECT_BORE_CALLOUT_SPAN_WITNESS, hits)
            if wres["status"] == FOUND:
                partners = [s for s in sheets if s != leg_sheet]
                chain_out = {"leg_sheet": leg_sheet, "pdf_page": int(resolved), "offset": offset,
                             "witness": wres, "partner_sheets": partners}
                break
            chain_out.setdefault("witness_status", wres["status"])
        if not chain_out:
            st = chain_out.get("witness_status") if isinstance(chain_out, dict) else None
            status = WITNESS_AMBIGUOUS if st == "AMBIGUOUS" else WITNESS_NOT_FOUND
            return _refuse(status, "no unique printed direct-bore callout-span witness on the corrected sheet(s) "
                                   "%s for %s -> %s" % (sheets, start_sta, end_sta))

        leg_sheet = chain_out["leg_sheet"]
        pdf_page = chain_out["pdf_page"]
        offset = chain_out["offset"]
        partners = chain_out["partner_sheets"]
        words, draw = plan.words(leg_sheet, offset), plan.line_items(leg_sheet, offset)
        chain_lines = plan.lines(leg_sheet, offset)
        conduit = [x for x in draw if x.get("layer") in BASE_CONDUIT]
        chain = [
            "unique DIRECT_BORE_CALLOUT_SPAN_WITNESS %s TO %s (%s') on engineering sheet %d -> PDF page %d"
            % (start_sta, end_sta, int(span), leg_sheet, pdf_page),
        ]

        def _leg_predicate(tip_xy: Tuple[float, float]):
            """The physical chain-reach predicate for the callout-box fallback: does a chain seeded at ``tip_xy``
            reach the UNIQUE end matchline and CLOSE to the printed span? -> (ok, elimination_reason, drawn_ft).
            Renders NOTHING — candidate testing never draws."""
            lb = _bind_leg_from_start(tip_xy, words=words, draw=draw, conduit=conduit, chain_lines=chain_lines,
                                      partners=partners, end_sta=end_sta, span=span, leg_sheet=leg_sheet)
            return lb.ok, (lb.status or "closes"), lb.drawn_ft

        # --- start: source-bound plan-view anchor at the callout START station (never nearest-snap) --------
        ar = resolve_plan_view_anchor_for_path(str(plan_path), leg_sheet, float(start_ft), offset=offset)
        anchor_detail: Dict[str, Any] = {"bare_station_anchor": ar.to_dict()}
        if ar.status == AMBIGUOUS_ANCHOR:
            # FALLBACK (only entered here): the bare token is non-unique on the sheet, but the FULL callout
            # phrase is unique — anchor from the callout BOX + its own leader. Refusals stay named and carry
            # the original START_ANCHOR_AMBIGUOUS context; a clean bare-station resolve NEVER reaches this.
            xy, fb_refusal, fb_detail = _callout_box_anchor(plan, leg_sheet, offset, words, draw,
                                                            leg_predicate=_leg_predicate)
            anchor_detail["callout_box_fallback"] = fb_detail
            anchor_detail["original_start_anchor"] = START_ANCHOR_AMBIGUOUS
            if fb_refusal is not None:
                return _refuse(fb_refusal,
                               "bare start %s is ambiguous on sheet %d and the callout-box leader fallback "
                               "refused (%s) — human pick, never a guess" % (start_sta, leg_sheet, fb_refusal),
                               chain=chain, detail=anchor_detail)
            start_xy = xy
            method = fb_detail.get("method") or (fb_detail.get("anchor") or {}).get("method")
            anchor_detail["anchor_mode"] = fb_detail.get("mode", "CALLOUT_BOX_LEADER")
            chain.append("bare start %s ambiguous -> UNIQUE callout box '%s' -> %s anchor at "
                         "(%.1f, %.1f) via %s" % (start_sta, _CALLOUT_PHRASE, anchor_detail["anchor_mode"],
                                                  start_xy[0], start_xy[1], method))
        elif not ar.resolved or ar.x is None or ar.y is None:
            return _refuse(START_ANCHOR_UNRESOLVED,
                           "the callout start %s did not source-bind to a plan-view anchor on sheet %d (%s)"
                           % (start_sta, leg_sheet, ar.status), chain=chain, detail=anchor_detail)
        else:
            start_xy = (float(ar.x), float(ar.y))
            method = ar.method
            anchor_detail["anchor_mode"] = "BARE_STATION"
            chain.append("start %s bound at (%.1f, %.1f) via %s" % (start_sta, start_xy[0], start_xy[1], method))

        # --- leg + unique end matchline + printed-span closure + terminal-at-boundary, via the shared binder
        #     (the SAME gates the chain-reach predicate tested per candidate — one source of truth) ----------
        lb = _bind_leg_from_start(start_xy, words=words, draw=draw, conduit=conduit, chain_lines=chain_lines,
                                  partners=partners, end_sta=end_sta, span=span, leg_sheet=leg_sheet)
        chain.extend(lb.sub_chain)
        if not lb.ok:
            return _refuse(lb.status, lb.reason, chain=chain, detail=lb.detail)
        route, bnd, drawn_ft = lb.route, lb.bnd, lb.drawn_ft

        detail = {"engineering_sheet": leg_sheet, "pdf_page": pdf_page, "partner_sheets": partners,
                  "anchor_mode": anchor_detail.get("anchor_mode"), "anchor_method": method,
                  "anchor_evidence": anchor_detail,
                  "start_station": start_sta, "end_station": end_sta, "span_ft": int(span),
                  "drawn_ft": round(drawn_ft, 1), "start_xy": [round(start_xy[0], 1), round(start_xy[1], 1)],
                  "matchline_boundary_xy": [round(float(bnd[0]), 1), round(float(bnd[1]), 1)],
                  "route_vertices": len(route), "stroke_rgb": list(REDLINE_STROKE_RGB),
                  "forbidden_sibling_stations": list(_FORBIDDEN_SIBLING_STATIONS)}
        chain.append("REVIEW candidate — human-reviewable; NOT AUTO, NOT final placement, NOT a frontier promotion")

        if not render:
            return Log68SliceResult(status=REVIEW_CANDIDATE_RENDERED, rendered=False,
                                    reason="bind succeeded (render suppressed)", png=None,
                                    evidence_chain=tuple(chain), detail=detail)

        reason = ("%s sheet-%d bore: callout %s -> MATCHLINE STA %s (SEE SHEET %s); bore TERMINATES at the "
                  "sheet boundary (continues as a separate bore on the partner sheet); single leg, printed-span "
                  "closure %d'" % (_LOG_ID, leg_sheet, start_sta, end_sta, partners, int(span)))
        png = render_redline_stroke(plan, _LOG_ID, leg_sheet, offset, route, status="REVIEW", reason=reason,
                                    out_dir=out_dir, mandatory_points=[start_xy, tuple(bnd)], pad=160.0)
        if not png or not os.path.isfile(png):
            return _refuse(RENDER_PRODUCED_NO_STROKE, "the render primitive produced no stroke (< 2 route points)",
                           chain=chain, detail=detail)
        detail["png"] = os.path.basename(png)
        return Log68SliceResult(status=REVIEW_CANDIDATE_RENDERED, rendered=True,
                                reason="source-backed callout-span leg bound + closed; ONE red REVIEW stroke drawn",
                                png=png, evidence_chain=tuple(chain), detail=detail)
    finally:
        plan.close()


def run_slice(plan_path: Optional[str] = None, out_dir: Optional[str] = None,
              write_json: bool = True) -> Dict[str, Any]:
    """Run the slice and return (and optionally write) the JSON report. Honest skip (NOTHING written) when the
    plan is absent — CI-safe without the private fixture."""
    plan_path = plan_path or os.getenv("TL2_STRUCTURE_DATUM_PLAN") or os.getenv("TL2_PROOF_PDF") or ""
    if not plan_path or not Path(plan_path).is_file():
        return {"skipped": True, "reason": "plan PDF not present (proof-only; not run in CI)", "plan_path": plan_path}
    out_dir = out_dir or str(_OUT_DIR)
    result = bind_and_render(plan_path, out_dir=out_dir)
    report = {
        "milestone": "log68 direct-bore callout-span witness binding slice (read-only proof; REVIEW-only)",
        "plan_path": Path(plan_path).name,
        "result": result.to_dict(),
        "guarantees": {"read_only_except_one_png_json": True, "no_sweep_edit": True, "no_engine_edit": True,
                       "no_renderer_truth_edit": True, "no_classifier_ledger_census_edit": True,
                       "no_adjudication_edit": True, "no_store_wiring": True, "no_auto": True,
                       "no_final_placement": True, "no_promotion": True, "no_frontier_change": True,
                       "sibling_containment_enforced": True, "own_output_dir_not_sweep_tripwire_dir": True},
    }
    if write_json:
        op = Path(out_dir) / "log68_callout_span_witness.json"
        op.parent.mkdir(parents=True, exist_ok=True)
        op.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        report["written_to"] = str(op)
    return report


def main(argv: Optional[Sequence[str]] = None) -> int:  # pragma: no cover - CLI parity
    import sys
    args = list(sys.argv[1:] if argv is None else argv)
    plan = args[0] if args else None
    report = run_slice(plan_path=plan)
    print(json.dumps({k: v for k, v in report.items() if k != "result"}, indent=2, sort_keys=True))
    r = report.get("result")
    if r:
        print("[log68] %s  rendered=%s  %s" % (r["status"], r["rendered"], r["reason"]))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
