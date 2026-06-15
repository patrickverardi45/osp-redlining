r"""OWNER-PACKET-2 -- log71 TWO sheet-local-leg SOURCE BIND slice (PROOF ONLY; no render).

After 9825910 encoded log71's owner-reviewed endpoint-anchor IDENTITY (start NEXTLINK HH @ STA 7+50
on sheet 24 -- owner-confirmed 2026-06-15; end FLOWER POT @ STA 6+95 on sheet 23 -- owner-named),
this binds that identity to REAL sheet 24 + sheet 23 PDF/CAD source as TWO sheet-local legs joined
at the 'STA 5+45 - SEE SHEET 24' matchline -- the same primitives log53/log64 used (printed label ->
label box -> leader -> modeled symbol for the termini; the nextlink-callout locator for the reset
start; modeled conduit chain; chain-reach matchline disambiguation). It renders nothing, draws no
stroke, writes no PNG, and solves no cross-sheet frame.

The two legs (oriented start -> end, as a future render would draw them):

  sheet 24 (START leg):  NEXTLINK HH start (STA 7+50 = 0+00)  ->  STA 5+45 matchline
  sheet 23 (END leg):    STA 5+45 matchline                   ->  FLOWER POT end (STA 6+95)

The 5+45 matchline is NOT an endpoint: log71 has exactly two true structure termini (start NEXTLINK
HH, end FLOWER POT). 5+45 is the between-leg crossing -- intermediate route context the bind resolves
by CHAIN REACH (the matchline the leg's conduit chain physically terminates at, uniquely; '5+45' is
not sheet-unique and sheet 23 also carries a 6+00 matchline, so the strict unique-label law does not
apply). It is located independently ON EACH SHEET, in that sheet's OWN coordinate frame; the two
matchline points are NEVER reconciled to each other -- cross-sheet coordinate translation stays
deferred (a separately-authorized step).

What it proves (single sheet per leg; no cross-sheet solving):
  END leg  (sheet 23): STA 6+95 FLOWER POT binds; the flower-pot-seeded base conduit chain reaches a
                       uniquely chain-located 5+45 matchline boundary -> the leg is source-backed.
  START leg (sheet 24): the Lawndale reset STA 7+50 = 0+00 binds as a NEXTLINK HH via the committed
                       locator; the nextlink-HH-seeded base conduit chain reaches a uniquely
                       chain-located 5+45 matchline boundary -> the leg is source-backed. (The scout
                       at 07aad25 proved the END-leg matchline + that both legs carry a chain; the
                       NEW substantive proof here is the START-leg 5+45 matchline on sheet 24 and the
                       per-leg corridor continuity.)

Direct-corridor continuity (the log64 corridor_is_continuous law, generalized to either leg axis) is
reported per leg as render-readiness -- a continuous direct band is immediately strokeable; a bending
leg is still source-backed but needs the ordered route at render time. All coordinates come from the
EXISTING extractor; this slice synthesizes none. Census stays frozen (no artifact change; flag-OFF
31/6/1/17/3, flag-ON 22/1/4). A render is the separately-authorized next step, NOT done here.

Proof-only; the JSON report is written under the gitignored data/outputs path.
Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_log71_two_leg_source_bind_slice
"""
from __future__ import annotations

import json
import os

from truelinev2.config import _REPO_ROOT
from truelinev2.extract.conduit_topology import (
    MAX_DASH_GAP,
    connected_chain,
    dash_endpoints,
    symbol_footprint,
)
from truelinev2.extract.registry import select_dialect
from truelinev2.extract.structure_position import (
    BRENHAM_CONDUIT_LAYERS,
    BRENHAM_STRUCTURE_LAYERS,
    POSITION_BOUND,
    resolve_nextlink_hh_callout,
    resolve_structure_position,
)
from truelinev2.ingest.manual_adjudication import (
    activation_summary,
    apply_adjudications,
    load_adjudication,
    parent_run_duplicate_check,
    validate_endpoint_anchors,
)
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.proof.run_brenham_corpus import EXPECTED_COUNT, PDF, enumerate_corpus
from truelinev2.proof.run_log53_primitives_cohort_replay import MODELED_TERMINUS_CLASSES
from truelinev2.proof.run_log64_sheet21_source_bind_slice import CORRIDOR_HALF, corridor_is_continuous
from truelinev2.proof.run_log71_sheet_local_bind_scout import (
    END_FP_LABEL,
    INSTALLER_SYMBOL_LAYER,
    MATCHLINE_STA,
    SHEET_END,
    SHEET_START,
    START_STA,
    locate_matchline_boundary,
)
from truelinev2.proof.run_reviewer_service_contract import resolve_corpus

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "log71_two_leg_source_bind_slice"
TRUTH = _REPO_ROOT / "data" / "outputs" / "final_engine_truth_table" / \
    "final_engine_truth_table.json"
BASE_CONDUIT = set(BRENHAM_CONDUIT_LAYERS.values())   # BORE - VACANT PIPE / BORE - PORT
FROZEN_BUCKETS = {"DRAWABLE_REVIEW": 31, "HUMAN_ADJUSTABLE_REVIEW": 6,
                  "OUT_OF_CLASS": 1, "PICK_CARD_REVIEW": 17, "SOURCE_OR_KMZ_REQUIRED": 3}
ABSTAIN_4 = ("log5", "log31", "log38", "log43")

R_CONFIRMED = "LOG71_TWO_LEG_SOURCE_BIND_CONFIRMED"
B_ANCHORS = "BLOCKED_LOG71_ENCODED_ANCHORS_MISSING"
B_END_BIND = "BLOCKED_LOG71_END_FLOWER_POT_BIND_FAILED"
B_END_MATCHLINE = "BLOCKED_LOG71_END_LEG_MATCHLINE_NOT_LOCATED"
B_START_BIND = "BLOCKED_LOG71_START_NEXTLINK_HH_BIND_FAILED"
B_START_MATCHLINE = "BLOCKED_LOG71_START_LEG_MATCHLINE_NOT_LOCATED"
B_ROUTE = "BLOCKED_LOG71_ROUTE_NOT_SOURCE_BACKED"
ALLOWED = {R_CONFIRMED, B_ANCHORS, B_END_BIND, B_END_MATCHLINE, B_START_BIND,
           B_START_MATCHLINE, B_ROUTE}


def start_label_text(start_anchor: dict) -> str:
    """The bindable START label is the owner reset token '<station>=0+00' (log71's start is a
    STATION_RESET_SEGMENT_BOUNDARY at the NEXTLINK HH; owner_note_text records 'STA 7+50 = 0+00').
    Derived from the encoded anchor -- never invented. Same shape as log64's start label."""
    return f"{start_anchor.get('station')}=0+00"


def leg_corridor_band(chain_eps, term_xy, matchline_xy, half: float = CORRIDOR_HALF):
    """Sorted unique dash-endpoint positions along a leg's DOMINANT axis that lie inside the direct
    terminus->matchline corridor band (cross-axis within ``half`` of the centerline; main-axis between
    the endpoints). Orientation-aware generalization of log64's vertical ``corridor_band``: a log71
    leg may run either way (the END leg is vertical, the START leg's axis is whatever the source
    draws). Invents nothing -- only real conduit dash endpoints are banded. Pure.
    Returns ``(band, lo, hi, axis)`` where ``axis`` is 'y' (vertical leg) or 'x' (horizontal leg)."""
    vertical = abs(matchline_xy[1] - term_xy[1]) >= abs(matchline_xy[0] - term_xy[0])
    main, cross = (1, 0) if vertical else (0, 1)
    cc = (term_xy[cross] + matchline_xy[cross]) / 2.0
    lo, hi = min(term_xy[main], matchline_xy[main]), max(term_xy[main], matchline_xy[main])
    band = sorted({round(p[main], 2) for p in chain_eps
                   if abs(p[cross] - cc) <= half and (lo - 5) <= p[main] <= (hi + 5)})
    return band, lo, hi, ("y" if vertical else "x")


def bind_leg(*, role, sheet, terminus_xy, terminus_class, terminus_station, seed_layer,
             matchline_sta, words, draw):
    """Source-bind one sheet-local leg: seed a base conduit chain at the bound terminus symbol,
    locate the ``matchline_sta`` matchline this leg's chain terminates at (chain-reach; route
    context, NOT an endpoint), and compute the direct terminus->matchline corridor continuity
    (render-readiness). Returns a leg dict (or one with ``matchline_xy``=None if no chain / no
    uniquely-located matchline). Coordinates are all extractor-derived. Pure given inputs."""
    fp = symbol_footprint(draw, seed_layer, terminus_xy)
    chain = connected_chain([x for x in draw if x.get("layer") in BASE_CONDUIT], fp) if fp else []
    leg = {
        "role": role, "sheet": sheet,
        "structure_terminus": {
            "structure_class": terminus_class, "station": terminus_station,
            "xy": [round(c, 2) for c in terminus_xy]},
        "matchline_join": {"station": matchline_sta, "kind": "route_context", "xy": None},
        "corridor": {"chain_segs": len(chain), "reach_to_matchline_pt": None,
                     "band_points": None, "direct_corridor_continuous": None, "axis": None},
        "source_backed": False,
    }
    if not chain:
        return leg
    bnd, reach, uniq = locate_matchline_boundary(words, draw, matchline_sta, chain)
    leg["corridor"]["reach_to_matchline_pt"] = round(reach, 2) if reach is not None else None
    if bnd is None or not uniq:
        return leg
    leg["matchline_join"]["xy"] = [round(c, 2) for c in bnd]
    band, lo, hi, axis = leg_corridor_band(dash_endpoints(chain), terminus_xy, tuple(bnd))
    leg["corridor"]["band_points"] = len(band)
    leg["corridor"]["axis"] = axis
    leg["corridor"]["direct_corridor_continuous"] = corridor_is_continuous(band, lo, hi)
    leg["source_backed"] = True   # terminus bound + chain reaches a uniquely-located matchline
    return leg


def _census_frozen(doc) -> bool:
    if not TRUTH.is_file():
        return False
    truth = json.loads(TRUTH.read_text(encoding="utf-8"))
    baseline = {r["bore_id"]: dict(r) for r in truth["rows"]}
    off_rows = apply_adjudications(baseline, enabled=False)
    on_rows = apply_adjudications(baseline, enabled=True, doc=doc)
    summ = activation_summary(on_rows)
    buckets = {}
    for r in off_rows.values():
        buckets[r["completion_bucket"]] = buckets.get(r["completion_bucket"], 0) + 1
    return (off_rows is baseline and buckets == FROZEN_BUCKETS
            and summ["manual_review_drawable"] == 22 and summ["manual_source_verification"] == 1
            and summ["manual_abstain"] == 4
            and on_rows["log44"]["adjudication"]["drawable_status"] == "non_drawable"
            and all(on_rows[l]["adjudication"]["drawable_status"] == "abstain" for l in ABSTAIN_4)
            and not parent_run_duplicate_check(doc))


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for stale in OUT_DIR.glob("*.png"):
        stale.unlink()  # no render/stroke lane: a PNG must never exist

    doc = load_adjudication()
    rec = {r["log_id"]: r for r in doc["logs"]}
    l71 = rec.get("log71") or {}
    ea = l71.get("endpoint_anchors") or {}
    start_a, end_a = ea.get("start") or {}, ea.get("end") or {}
    end_note_up = str(end_a.get("owner_note_text") or "").upper()
    gates, ev = [], {"sheet_start": SHEET_START, "sheet_end": SHEET_END,
                     "start_leg": None, "end_leg": None}

    # ---- frozen ENGINE census (this slice changes no artifact) --------------------
    gates.append(("G0 engine census frozen (OFF 31/6/1/17/3, ON 22/1/4, log44+abstains held)",
                  _census_frozen(doc), None))
    # preserve behavior: log53 + log64 anchors untouched
    l53s = (rec["log53"].get("endpoint_anchors") or {}).get("start") or {}
    l64s = (rec["log64"].get("endpoint_anchors") or {}).get("start") or {}
    l64e = (rec["log64"].get("endpoint_anchors") or {}).get("end") or {}
    gates.append(("G0b log53 + log64 encoded anchors unchanged (behavior preserved)",
                  l53s.get("structure_class") == "nextlink_hh"
                  and l64s.get("structure_class") == "installer_hh" and l64s.get("station") == "3+69"
                  and l64e.get("structure_class") == "flower_pot" and l64e.get("station") == "1+00", None))

    # ---- consume the encoded log71 identity (9825910) -----------------------------
    anchors_ok = (validate_endpoint_anchors(l71) == []
                  and start_a.get("structure_class") == "nextlink_hh" and start_a.get("station") == START_STA
                  and end_a.get("structure_class") == "flower_pot" and end_a.get("station") == END_FP_LABEL)
    gates.append(("G1 log71 encoded anchors consumed (nextlink_hh @7+50 s24 -> flower_pot @6+95 s23)",
                  anchors_ok, {"start": start_a.get("station"), "end": end_a.get("station")}))
    # the 5+45 matchline is route context, NOT a third endpoint anchor (schema = start/end termini)
    matchline_is_context = (set(ea) <= {"start", "end"}
                            and MATCHLINE_STA in end_note_up
                            and start_a.get("station") != MATCHLINE_STA
                            and end_a.get("station") != MATCHLINE_STA)
    gates.append(("G2 5+45 matchline = route context not endpoint (no 3rd anchor; preserved in end note)",
                  matchline_is_context, {"anchor_keys": sorted(ea), "matchline": MATCHLINE_STA}))
    gates.append(("G3 both termini are MODELED structure classes (nextlink_hh + flower_pot)",
                  start_a.get("structure_class") in MODELED_TERMINUS_CLASSES
                  and end_a.get("structure_class") in MODELED_TERMINUS_CLASSES, None))
    if not anchors_ok:
        return _emit(gates, B_ANCHORS, ev)

    if not os.path.isfile(PDF):
        gates.append(("G4 plan PDF present", False, f"missing {PDF}"))
        return _emit(gates, B_ROUTE, ev)
    corpus_dir, _ = resolve_corpus()
    corpus = {p.stem: p for p in enumerate_corpus(corpus_dir)} if os.path.isdir(corpus_dir) else {}
    gates.append(("G4 plan PDF + corpus present",
                  os.path.isfile(PDF) and len(corpus) == EXPECTED_COUNT,
                  {"pdf": os.path.isfile(PDF), "corpus": len(corpus)}))

    plan = PlanPdf(PDF)
    result = B_ROUTE
    try:
        dialect = select_dialect(plan)
        offset = dialect.calibrate(plan, 13)

        # ---- END leg (sheet 23): 5+45 matchline -> FLOWER POT 6+95 --------------
        we, de = plan.words(SHEET_END, offset), plan.line_items(SHEET_END, offset)
        pv = resolve_structure_position(label_text=END_FP_LABEL, structure_class="flower_pot",
                                        words=we, drawings=de, layer_table=BRENHAM_STRUCTURE_LAYERS,
                                        context_texts=("FLOWER", "POT"))
        gates.append(("G5 END flower_pot STA 6+95 binds on sheet 23 (label+context -> leader -> symbol)",
                      pv.result == POSITION_BOUND and bool(pv.symbol_xy), pv.result))
        if pv.result != POSITION_BOUND or not pv.symbol_xy:
            return _emit(gates, B_END_BIND, ev)
        end_leg = bind_leg(role="end", sheet=SHEET_END, terminus_xy=tuple(pv.symbol_xy),
                           terminus_class="flower_pot", terminus_station=END_FP_LABEL,
                           seed_layer="FLOWER POT", matchline_sta=MATCHLINE_STA, words=we, draw=de)
        ev["end_leg"] = end_leg
        gates.append(("G6 END leg source-backed: flower-pot chain reaches a unique 5+45 matchline on s23",
                      end_leg["source_backed"], {"reach": end_leg["corridor"]["reach_to_matchline_pt"],
                                                 "matchline_xy": end_leg["matchline_join"]["xy"]}))
        if not end_leg["source_backed"]:
            return _emit(gates, B_END_MATCHLINE, ev)

        # ---- START leg (sheet 24): NEXTLINK HH 7+50=0+00 -> 5+45 matchline -------
        ws, ds = plan.words(SHEET_START, offset), plan.line_items(SHEET_START, offset)
        nv = resolve_nextlink_hh_callout(station_sta=START_STA, words=ws, drawings=ds,
                                         callout_layer="ANNOTATION", symbol_layer="NEXTLINK")
        gates.append(("G7 START nextlink_hh STA 7+50=0+00 binds on sheet 24 (committed callout locator)",
                      nv.result == POSITION_BOUND and bool(nv.symbol_xy), nv.result))
        if nv.result != POSITION_BOUND or not nv.symbol_xy:
            return _emit(gates, B_START_BIND, ev)
        start_leg = bind_leg(role="start", sheet=SHEET_START, terminus_xy=tuple(nv.symbol_xy),
                             terminus_class="nextlink_hh", terminus_station=START_STA,
                             seed_layer=INSTALLER_SYMBOL_LAYER, matchline_sta=MATCHLINE_STA,
                             words=ws, draw=ds)
        ev["start_leg"] = start_leg
        gates.append(("G8 START leg source-backed: nextlink-HH chain reaches a unique 5+45 matchline on s24",
                      start_leg["source_backed"], {"reach": start_leg["corridor"]["reach_to_matchline_pt"],
                                                   "matchline_xy": start_leg["matchline_join"]["xy"]}))
        if not start_leg["source_backed"]:
            return _emit(gates, B_START_MATCHLINE, ev)

        # ---- join semantics + no cross-sheet translation ------------------------
        # The two legs share ONE matchline IDENTITY (STA 5+45) but each leg's matchline point is
        # located in its OWN sheet frame; the points are NOT equal and are NEVER reconciled.
        s_ml, e_ml = start_leg["matchline_join"]["xy"], end_leg["matchline_join"]["xy"]
        ev["start_leg_matchline_xy"] = s_ml
        ev["end_leg_matchline_xy"] = e_ml
        no_cross_sheet = s_ml != e_ml and start_leg["sheet"] != end_leg["sheet"]
        gates.append(("G9 two legs joined by 5+45 IDENTITY only; per-sheet frames NOT reconciled (no x-sheet)",
                      no_cross_sheet, {"s24_matchline_xy": s_ml, "s23_matchline_xy": e_ml}))

        result = R_CONFIRMED
    finally:
        plan.close()

    return _emit(gates, result, ev)


def _emit(gates, result, ev) -> int:
    gates.append(("G10 result in allowed enum", result in ALLOWED, result))
    pngs = sorted(p.name for p in OUT_DIR.glob("*.png"))
    gates.append(("G11 zero PNG / zero stroke (no render lane)", len(pngs) == 0, {"pngs": pngs}))
    confirmed = result == R_CONFIRMED
    all_pass = all(x for _, x, _ in gates) and confirmed

    start_leg, end_leg = ev.get("start_leg"), ev.get("end_leg")
    # render-ready-ish source-bind payload (start -> end, as a future render would draw); NO render
    payload = {
        "target": "log71",
        "legs": [leg for leg in (start_leg, end_leg) if leg is not None],
        "join": {
            "matchline_station": MATCHLINE_STA, "kind": "route_context_between_two_termini",
            "frames": f"per-sheet (sheet {SHEET_START} START + sheet {SHEET_END} END); NOT reconciled",
            "cross_sheet_translation": "deferred",
        },
        "render_ready_ish": confirmed, "rendered": False,
    } if confirmed else None
    report = {
        "milestone": "OWNER-PACKET-2 -- log71 two sheet-local-leg source bind slice (proof only; no render)",
        "verdict": "PASS" if all_pass else "FAIL",
        "result": result, "target": "log71", "sheets": [SHEET_START, SHEET_END],
        "question": ("does log71's encoded identity bind to real sheet 24 + sheet 23 source as TWO "
                     "sheet-local legs -- NEXTLINK HH start (s24), FLOWER POT end (s23), each leg's "
                     "conduit chain reaching a uniquely chain-located 5+45 matchline -- WITHOUT any "
                     "cross-sheet coordinate translation?"),
        "source_bind_payload": payload,
        "matchline_5_45": "route context (between-leg crossing located per-sheet by chain-reach; not an endpoint identity)",
        "future_render_ready": confirmed,
        "no_render": True, "no_invented_coordinates": True, "no_screenshot_pixels": True,
        "no_cross_sheet": True, "coords_are_extractor_derived": True,
        "next_slice": ("contained log71 RENDER artifact: ONE red REVIEW stroke per leg (s24 nextlink HH "
                       "-> 5+45 matchline; s23 5+45 matchline -> flower pot), endpoints re-derived from "
                       "source and gated to these binds, route following the proven corridor; cross-sheet "
                       "frame join remains a later separately-authorized step."),
        "evidence": ev,
        "gates": [{"name": n, "pass": bool(x), "detail": d} for n, x, d in gates],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "log71_two_leg_source_bind_slice.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"[log71-2leg] result: {result}")
    for role in ("start_leg", "end_leg"):
        leg = ev.get(role)
        if leg:
            c = leg["corridor"]
            print(f"[log71-2leg]   {role} (sheet {leg['sheet']}): terminus={leg['structure_terminus']['xy']} "
                  f"matchline={leg['matchline_join']['xy']} reach={c['reach_to_matchline_pt']} "
                  f"axis={c['axis']} band={c['band_points']} direct_continuous={c['direct_corridor_continuous']} "
                  f"source_backed={leg['source_backed']}")
    for n, x, _ in gates:
        print(f"[log71-2leg] {'PASS' if x else 'FAIL'}  {n}")
    print(f"[log71-2leg] VERDICT: {'PASS' if all_pass else 'FAIL'}  (report: {OUT_DIR})")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
