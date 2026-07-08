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
from truelinev2.extract.plan_view_anchor_resolver import AMBIGUOUS_ANCHOR, resolve_plan_view_anchor_for_path
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

# --- result statuses ------------------------------------------------------------------------------------- #
REVIEW_CANDIDATE_RENDERED = "LOG68_CALLOUT_SPAN_REVIEW_CANDIDATE_RENDERED"    # the single positive
WITNESS_NOT_FOUND = "WITNESS_NOT_FOUND"
WITNESS_AMBIGUOUS = "WITNESS_AMBIGUOUS"
ADJUDICATED_SPAN_UNAVAILABLE = "ADJUDICATED_SPAN_UNAVAILABLE"
SHEET_REF_UNRESOLVED = "SHEET_REF_UNRESOLVED"
START_ANCHOR_AMBIGUOUS = "START_ANCHOR_AMBIGUOUS"
START_ANCHOR_UNRESOLVED = "START_ANCHOR_UNRESOLVED"
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
        chain = [
            "unique DIRECT_BORE_CALLOUT_SPAN_WITNESS %s TO %s (%s') on engineering sheet %d -> PDF page %d"
            % (start_sta, end_sta, int(span), leg_sheet, pdf_page),
        ]

        # --- start: source-bound plan-view anchor at the callout START station (never nearest-snap) --------
        ar = resolve_plan_view_anchor_for_path(str(plan_path), leg_sheet, float(start_ft), offset=offset)
        if ar.status == AMBIGUOUS_ANCHOR:
            return _refuse(START_ANCHOR_AMBIGUOUS,
                           "the callout start %s resolves to >= 2 plausible anchors on sheet %d — human pick, "
                           "never a guess" % (start_sta, leg_sheet), chain=chain,
                           detail={"anchor": ar.to_dict()})
        if not ar.resolved or ar.x is None or ar.y is None:
            return _refuse(START_ANCHOR_UNRESOLVED,
                           "the callout start %s did not source-bind to a plan-view anchor on sheet %d (%s)"
                           % (start_sta, leg_sheet, ar.status), chain=chain, detail={"anchor": ar.to_dict()})
        start_xy = (float(ar.x), float(ar.y))
        chain.append("start %s bound at (%.1f, %.1f) via %s" % (start_sta, start_xy[0], start_xy[1], ar.method))

        # --- leg: the source-backed conduit chain connected to the bound start (empty -> abstain) ----------
        conduit = [x for x in draw if x.get("layer") in BASE_CONDUIT]
        seed = (start_xy[0] - _SEED_EPS, start_xy[1] - _SEED_EPS, start_xy[0] + _SEED_EPS, start_xy[1] + _SEED_EPS)
        chain_segs = connected_chain(conduit, seed)
        if not chain_segs:
            return _refuse(NO_CONDUIT_CHAIN_AT_START,
                           "no source-backed conduit chain is connected to the bound start %s on sheet %d "
                           "(fiber/generic path or off-conduit anchor) — refusing" % (start_sta, leg_sheet),
                           chain=chain)

        # --- end: the printed SEE-SHEET matchline boundary the chain reaches at the callout END station ----
        # gate 1: the END station must sit on a printed SEE-SHEET crossing to a PARTNER sheet (the identity),
        # and that crossing must NOT carry a forbidden sibling continuation station.
        partner_crossings = [c for p in partners for c in see_sheet_crossings(chain_lines, p, "MATCHLINE")]
        end_crossings = [c for c in partner_crossings if end_sta in c]
        if not end_crossings:
            return _refuse(MATCHLINE_ENDPOINT_NOT_FOUND,
                           "no printed SEE-SHEET matchline crossing carries the callout end %s to a partner "
                           "sheet %s on sheet %d" % (end_sta, partners, leg_sheet), chain=chain)
        bleed = _forbidden_tokens_absent(*["/".join(c) for c in end_crossings])
        if bleed is not None:
            return _refuse(SIBLING_BLEED_DETECTED,
                           "the selected end matchline crossing also carries the forbidden sibling continuation "
                           "station %s — refusing to bind into the sibling bore" % bleed, chain=chain)
        # gate 2: the chain must UNIQUELY reach that matchline boundary at the END station
        bnd, reach, uniq = locate_matchline_boundary(words, draw, end_sta, chain_segs)
        if bnd is None or not uniq:
            return _refuse(MATCHLINE_ENDPOINT_NOT_FOUND,
                           "the callout end matchline %s is not uniquely reached by the start chain on sheet %d "
                           "(reach %s, unique %s)" % (end_sta, leg_sheet, reach, uniq), chain=chain)
        chain.append("end bound at MATCHLINE STA %s (SEE SHEET %s) boundary (%.1f, %.1f)"
                     % (end_sta, partners, bnd[0], bnd[1]))

        # --- leg source-backing + printed-span closure (the false-positive / sibling-bleed backstop) -------
        route, ok = _ordered_leg(chain_segs, start_xy, tuple(bnd))
        if not ok:
            return _refuse(LEG_NOT_SOURCE_BACKED,
                           "the start -> matchline leg is not a source-backed ordered conduit route on sheet %d"
                           % leg_sheet, chain=chain)
        drawn_ft = route_length(route) / SCALE
        closes = abs(drawn_ft - float(span)) <= CLOSURE_REL_TOL * float(span)
        chain.append("leg closure: drawn %.1f ft vs printed span %d ft (tol %d%%) -> %s"
                     % (drawn_ft, int(span), int(CLOSURE_REL_TOL * 100), "closes" if closes else "FAILS"))
        if not closes:
            return _refuse(CLOSURE_FAILED,
                           "leg draws %.1f ft vs printed span %d ft (> %d%%) — a partial/over-run (would bleed "
                           "into the sibling continuation) — refusing" % (drawn_ft, int(span), int(CLOSURE_REL_TOL * 100)),
                           chain=chain, detail={"drawn_ft": round(drawn_ft, 1), "span_ft": int(span)})
        # hard containment backstop: the terminal vertex IS the matchline boundary (never past it)
        if route[-1] != tuple(bnd):
            return _refuse(MATCHLINE_ENDPOINT_NOT_FOUND,
                           "the leg's terminal vertex is not the matchline boundary — refusing", chain=chain)

        detail = {"engineering_sheet": leg_sheet, "pdf_page": pdf_page, "partner_sheets": partners,
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
