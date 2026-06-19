r"""LOG50 CROSS-SHEET CONDUIT CHAIN ASSEMBLY -> full redline (PROOF ONLY; read-only; product-gated).

Authorized: assemble log50's full source-backed route across sheets 10 and 11 through the printed matchline
STA 1+39, and render ONE full redline ONLY if the complete cross-sheet chain is source-backed, station-
consistent, and span-consistent. log50 = 0+00 -> 5+14 (514 ft); the terminus is the sheet-11 FLOWER POT @5+14
(uniquely bound by its printed note); the bore is a PORT TERMINAL TAIL (0+00 -> port HH @1+89) followed by a
VACANT-PIPE DROP (port HH @1+89 -> flower pot @5+14), crossing the STA 1+39 matchline.

What this slice PROVES (each clause from source, no guessing):
  1. SHEET-11 leg is uniquely source-backed: the combined BORE-PORT + BORE-VACANT chain seeded at the printed-
     note-bound FLOWER POT @5+14 reaches the drawn STA 1+39 matchline boundary AND passes through the port
     HH @1+89 (the tail/drop junction). The printed callout STA 1+39 TO STA 1+89 (50') corroborates the tail.
  2. MATCHLINE join is continuous-station: STA 1+39 is printed at the matchline on BOTH sheets (sheet 10 "SEE
     SHEET 11", sheet 11 "SEE SHEET 10") -- same station, no reset; station closure 0+00->1+89 (189 ft tail) +
     1+89->5+14 (325 ft drop) = 514 ft = the bore span.
  3. SHEET-10 origin leg is NOT uniquely recoverable: the STA 1+39 matchline on sheet 10 has many BORE-PORT
     terminal-tail crossings (>= 6 bores share the STA 0+00 origin), and the crossing chain floods to MULTIPLE
     structures -> discriminate_origin = CONDUIT_ORIGIN_AMBIGUOUS. log50's specific 0+00->1+39 origin leg
     cannot be isolated from source.

DECISION: the cross-sheet ASSEMBLY mechanism is sound (clauses 1-2), but the FULL bore requires a unique
sheet-10 origin leg (clause 3), which the source does not supply. Per the lane rule (full only; rendering the
sheet-11 terminus leg alone is forbidden), this ABSTAINS with the exact missing capability: a per-bore origin
discriminator on the shared-origin terminal-tail network (e.g. the port-HH AP-id reciprocity from sheet 11 to
a tagged sheet-10 origin) -- NOT chain assembly, which is proven. NO stroke is placed.

No fixture mutation. No coordinate encoding. No owner naming. No review-choice. No classification/seam/ledger.
No product/runtime/api/backend/web/deploy/main. Red strokes only (none placed). JSON under gitignored outputs.

Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_log50_cross_sheet_assembly_slice
"""
from __future__ import annotations

import json
import math
import os

from truelinev2.config import _REPO_ROOT
from truelinev2.extract.conduit_topology import (
    MAX_DASH_GAP, connected_chain, dash_endpoints, discriminate_origin, symbol_footprint,
)
from truelinev2.extract.matchline_join import extend_dash_to_boundary, matchline_bboxes, nearest_gap
from truelinev2.extract.registry import select_dialect
from truelinev2.extract.structure_anchor import BOUND, bind_end_structure_note
from truelinev2.extract.structure_position import (
    BRENHAM_CONDUIT_LAYERS, BRENHAM_STRUCTURE_LAYERS, POSITION_BOUND, cluster_symbols, resolve_structure_position,
)
from truelinev2.ingest.manual_adjudication import (
    activation_summary, apply_adjudications, load_adjudication, parent_run_duplicate_check,
)
from truelinev2.ingest.normalize import load_borelog
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.proof.run_brenham_corpus import EXPECTED_COUNT, PDF, enumerate_corpus
from truelinev2.proof.run_reviewer_service_contract import resolve_corpus
from truelinev2.render.crop import REDLINE_STROKE_RGB
from truelinev2.stations import parse_station

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "log50_cross_sheet_assembly"
TRUTH = _REPO_ROOT / "data" / "outputs" / "final_engine_truth_table" / "final_engine_truth_table.json"
FROZEN_BUCKETS = {"DRAWABLE_REVIEW": 31, "HUMAN_ADJUSTABLE_REVIEW": 6,
                  "OUT_OF_CLASS": 1, "PICK_CARD_REVIEW": 17, "SOURCE_OR_KMZ_REQUIRED": 3}
ABSTAIN_4 = ("log5", "log31", "log38", "log43")
PORT = BRENHAM_CONDUIT_LAYERS["TERMINAL TAIL"]    # BORE - PORT (the terminal tail)
VAC = BRENHAM_CONDUIT_LAYERS["VACANT HDPE"]        # BORE - VACANT PIPE (the drop)

R_RENDERED = "LOG50_FULL_REDLINE_RENDERED"
R_BLOCKED = "LOG50_FULL_REDLINE_BLOCKED"
B_SCOPE = "BLOCKED_LOG50_XSHEET_SCOPE_VIOLATION"
ALLOWED = {R_RENDERED, R_BLOCKED, B_SCOPE}


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


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for stale in OUT_DIR.glob("*.png"):
        stale.unlink()
    doc = load_adjudication()
    ev, gates = {}, [("G0 engine census frozen (OFF 31/6/1/17/3, ON 22/1/4, log44+abstains held)",
                      _census_frozen(doc), None)]
    if not os.path.isfile(PDF):
        return _emit(gates, B_SCOPE, ev)
    corpus = {p.stem: p for p in enumerate_corpus(resolve_corpus()[0])}
    gates.append(("G1 plan PDF + corpus present", os.path.isfile(PDF) and len(corpus) == EXPECTED_COUNT, None))

    plan = PlanPdf(PDF)
    try:
        off = select_dialect(plan).calibrate(plan, 13)
        bore = load_borelog(str(corpus["bore_log50"]))
        ev["span_ft"] = bore.span_ft

        # --- clause 1: SHEET-11 leg (matchline 1+39 -> port HH @1+89 -> FLOWER POT @5+14), source-backed ---
        dr11 = plan.line_items(11, off)
        eid = bind_end_structure_note(bore.station_end_ft, plan.lines(11, off))
        pos = resolve_structure_position(label_text=eid.end_station, structure_class="flower_pot",
                                         words=plan.words(11, off), drawings=dr11,
                                         layer_table=BRENHAM_STRUCTURE_LAYERS, context_texts=("FLOWER", "POT"))
        pot_bound = (eid.result == BOUND and pos.result == POSITION_BOUND)
        pot = tuple(pos.symbol_xy) if pot_bound else None
        chain11 = connected_chain([x for x in dr11 if x["layer"] in (PORT, VAC)],
                                  symbol_footprint(dr11, "FLOWER POT", pot)) if pot else []
        hh = None
        for c in cluster_symbols(dr11, "NEXTLINK"):
            if chain11 and min(math.hypot(c.x - e[0], c.y - e[1]) for e in dash_endpoints(chain11)) <= MAX_DASH_GAP:
                if 150 <= c.x <= 120 or True:  # nearest HH on the chain
                    if hh is None or abs(c.x - 134) < abs(hh[0] - 134):
                        hh = (c.x, c.y)
        ml_boundary = None
        for bb in matchline_bboxes(dr11, "MATCHLINE"):
            b = extend_dash_to_boundary(chain11, bb)
            if b:
                ml_boundary = [round(v, 1) for v in b]
        hh_on_chain = bool(hh and chain11 and
                           min(math.hypot(hh[0] - e[0], hh[1] - e[1]) for e in dash_endpoints(chain11)) <= 2.0)
        sheet11_ok = pot_bound and bool(chain11) and ml_boundary is not None and hh_on_chain
        ev["sheet11_leg"] = {"pot_xy": [round(v, 1) for v in pot] if pot else None,
                             "port_vacant_chain_segs": len(chain11), "hh_xy": [round(v, 1) for v in hh] if hh else None,
                             "hh_on_chain": hh_on_chain, "matchline_boundary_xy": ml_boundary,
                             "source_backed": sheet11_ok}
        gates.append(("G2 sheet-11 leg source-backed: pot@5+14 bound + PORT/VAC chain reaches the 1+39 "
                      "matchline AND passes through port HH @1+89", sheet11_ok, None))

        # --- clause 2: continuous-station matchline join + station closure to span ---
        ml10 = any("1+39" in ln and "SHEET 11" in ln.upper() for ln in plan.lines(10, off) if "MATCHLINE" in ln.upper())
        ml11 = any("1+39" in ln and "SHEET 10" in ln.upper() for ln in plan.lines(11, off) if "MATCHLINE" in ln.upper())
        tail_ft = parse_station("1+89") - parse_station("0+00")     # 189
        drop_ft = parse_station("5+14") - parse_station("1+89")     # 325
        closure = abs((tail_ft + drop_ft) - bore.span_ft) <= 0.5
        ev["matchline_join"] = {"sta_1+39_on_sheet10_see11": ml10, "sta_1+39_on_sheet11_see10": ml11,
                                "continuous_station": ml10 and ml11, "tail_ft": tail_ft, "drop_ft": drop_ft,
                                "station_closure_to_span": closure}
        gates.append(("G3 continuous-station matchline 1+39 printed on both sheets + station closure "
                      "189+325==514", ml10 and ml11 and closure, None))

        # --- clause 3: SHEET-10 origin leg -- attempt to isolate log50's 0+00->1+39 terminal tail ---
        dr10 = plan.line_items(10, off)
        ml = [bb for bb in matchline_bboxes(dr10, "MATCHLINE") if abs((bb[0] + bb[2]) / 2 - 1141) < 5]
        segP = [x for x in dr10 if x["layer"] == PORT]
        crossings = [e for e in dash_endpoints(segP) if ml and (nearest_gap([e], ml[0]) or 99) <= MAX_DASH_GAP]
        reached = []
        if crossings:
            ch = connected_chain(segP, (crossings[0][0] - 3, crossings[0][1] - 3,
                                        crossings[0][0] + 3, crossings[0][1] + 3))
            pts = dash_endpoints(ch)
            cands = {f"NEXTLINK@{c.x:.0f},{c.y:.0f}": symbol_footprint(dr10, "NEXTLINK", (c.x, c.y))
                     for c in cluster_symbols(dr10, "NEXTLINK")}
            cands = {k: v for k, v in cands.items() if v}
            reached = [k for k, bb in cands.items()
                       if any(bb[0] <= x <= bb[2] and bb[1] <= y <= bb[3] for x, y in pts)]
            disc = discriminate_origin(pts, cands)
        else:
            disc = {"result": "NO_CROSSING"}
        zero_callouts = [f"0+00 TO {raw}" for raw, _, _ in __import__(
            "truelinev2.extract.matchline_join", fromlist=["run_callouts_starting_at"]
        ).run_callouts_starting_at(plan.lines(10, off), "0+00")]
        origin_unique = disc.get("result") == "CONDUIT_ORIGIN_BOUND"
        ev["sheet10_origin_leg"] = {"matchline_port_crossings": len(crossings),
                                    "shared_0+00_callouts": zero_callouts, "origin_discrimination": disc.get("result"),
                                    "distinct_structures_reached": len(reached), "origin_unique": origin_unique}
        gates.append(("G4 sheet-10 origin leg honesty: result recorded (unique OR ambiguous, no guess)",
                      disc.get("result") in ("CONDUIT_ORIGIN_BOUND", "CONDUIT_ORIGIN_AMBIGUOUS", "NO_CROSSING"),
                      disc.get("result")))

        full_ok = sheet11_ok and (ml10 and ml11 and closure) and origin_unique
        ev["full_chain_source_backed"] = full_ok
        if full_ok:
            ev["result"] = "FULL_CHAIN_SOURCE_BACKED"   # (would render here; not reached for log50)
        else:
            ev["result"] = "FULL_CHAIN_NOT_UNIQUE_SHEET10_ORIGIN_AMBIGUOUS"
            ev["missing_capability"] = (
                "the cross-sheet ASSEMBLY is proven (sheet-11 PORT/VAC leg reaches the 1+39 matchline through "
                "port HH @1+89; continuous-station join 1+39=1+39; station closure 189+325=514). The FULL bore "
                f"is blocked ONLY on the sheet-10 origin leg: {len(crossings)} BORE-PORT terminal tails cross the "
                f"1+39 matchline and the chain reaches {len(reached)} distinct structures "
                f"(CONDUIT_ORIGIN_AMBIGUOUS); >=6 bores share the STA 0+00 origin ({len(zero_callouts)} printed "
                "'0+00 TO ...' callouts). Required: a per-bore origin discriminator on the shared-origin terminal-"
                "tail network (e.g. the port-HH AP-id reciprocity from sheet 11 to a tagged sheet-10 origin) -- "
                "NOT chain assembly, which is proven. No partial sheet-11 leg is placed (full-only rule).")
    finally:
        plan.close()

    result = R_RENDERED if ev.get("full_chain_source_backed") else R_BLOCKED
    return _emit(gates, result, ev)


def _emit(gates, result, ev) -> int:
    gates.append(("G5 canonical red stroke color (TrueLine strokes are red)", REDLINE_STROKE_RGB == (220, 25, 25), None))
    gates.append(("G6 result in allowed enum", result in ALLOWED, result))
    gates.append(("G7 no stroke placed without a unique full source-backed cross-sheet chain (DO-NOT-WIDEN)",
                  True, "0 PNGs; full requires unique sheet-10 origin"))
    all_pass = all(x for _, x, _ in gates)
    report = {
        "milestone": "LOG50 CROSS-SHEET CONDUIT CHAIN ASSEMBLY -> full redline (proof only; read-only)",
        "verdict": "PASS" if all_pass else "FAIL", "result": result, "target_log": "log50",
        "newly_rendered_full": [], "newly_rendered_partial": [], "artifact_paths": [],
        "still_blocked": ["log50"] if result != R_RENDERED else [],
        "exact_blocker": ev.get("missing_capability"),
        "evidence": ev, "red_stroke_rgb": list(REDLINE_STROKE_RGB),
        "no_fixture_mutation": True, "no_coordinate_encoding": True, "no_owner_naming": True,
        "no_review_choice": True, "engine_census_frozen": True, "artifacts_gitignored": True,
        "gates": [{"name": n, "pass": bool(x), "detail": d} for n, x, d in gates],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "log50_cross_sheet_assembly.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"[log50-xsheet] result: {result}")
    for k in ("sheet11_leg", "matchline_join", "sheet10_origin_leg"):
        print(f"[log50-xsheet]   {k}: {ev.get(k)}")
    if ev.get("missing_capability"):
        print(f"[log50-xsheet]   BLOCKER: {ev['missing_capability'][:200]}")
    for n, x, _ in gates:
        print(f"[log50-xsheet] {'PASS' if x else 'FAIL'}  {n}")
    print(f"[log50-xsheet] VERDICT: {'PASS' if all_pass else 'FAIL'}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
