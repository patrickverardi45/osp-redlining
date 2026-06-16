r"""UNMODELED_TERMINUS_CLASS scout (PROOF/REPORT ONLY; read-only; reuses the SHIPPED resolvers).

The all-redlines closure ledger names UNMODELED_TERMINUS_CLASS_NEEDED a non-placed class of 6 logs
(log6/41/46/54/63/68): each is classify_record REPRESENTATIVE_ROUTE_CANDIDATE carrying the ROOT gate
ENDPOINT_IDENTITY_NOT_MODELED -- the OWNER review never named a modeled terminus CLASS (no FLOWER POT /
INSTALLER HH / NEXTLINK HH / PORT HH token), so has_modeled_terminus is False and there is no exact
endpoint to place. The authorized question: is there a safe, smallest COMMON primitive across the class?

Finding (this scout): NO new resolver/primitive is needed. Running the SHIPPED structure resolvers
(resolve_structure_position over BRENHAM_STRUCTURE_LAYERS + the committed resolve_nextlink_hh_callout)
READ-ONLY over each log's owner-stated terminus stations deterministically partitions the class:

  FULL_SOURCE_RECOVERED (both termini) -- the existing resolver UNIQUELY binds a modeled class at BOTH
    termini, each ON the bore conduit chain (on-route). The terminus identity is SOURCE-RECOVERED, not
    owner-confirmed -> an UNCONFIRMED OWNER-REVIEW CANDIDATE (present for confirmation, then the existing
    endpoint-anchor bridge + sheet-local bind -- the proven log36 recover->confirm->bridge lane):
      log46  nextlink_hh @ STA 44+08 (s10)  ->  terminal_port_hh @ STA 5+34 (s14)
      log54  nextlink_hh @ STA 3+91 (s17)   ->  terminal_port_hh @ STA 3+14 (s21)
  PARTIAL_SOURCE_RECOVERED (one terminus) -- one terminus uniquely binds on-route (owner-confirm
    candidate); the other is a BARE station with no structure symbol (recover/representative):
      log6   end installer_hh @ STA 2+43 (s5);  start 'structure where column 2 ends' bare (shared-print
             column split; the bore log table is handwritten -- owner column->structure recovery)
      log63  end installer_hh @ STA 0+56 (s17);  start 0+00 bare (HH-HH=56: owner notes a start HH but no
             station-located symbol). NB the recovered end IS log36's start structure (shared print) -- a
             cross-log corroboration, NOT an encode.
  NO_TERMINUS_STRUCTURE (neither terminus) -- NO modeled structure binds at EITHER station: a bare
    station / road crossing / directional bore. No exact endpoint structure exists -> REPRESENTATIVE-
    ROUTE-ONLY (the human-review pick-card lane), not a terminus-class to model:
      log41  across-street resets (review-approved as drawn); bore 0+00 -> 0+44
      log68  'STA 5+03 TO STA 6+79 DIR. BORE' callout between stations (multi-sheet, OCR-corrected)

NO-GUESS LAW: a terminus is RECOVERED only when EXACTLY ONE modeled class binds (unique). Zero -> bare;
two-or-more -> AMBIGUOUS and HELD (never picked). The recovered classes are SOURCE-RECOVERED CANDIDATES,
explicitly UNCONFIRMED -- OCR/source output stays untrusted until owner-reviewed; this scout ENCODES no
endpoint_anchors (the 6 stay UNMODELED in the artifact), defines NO new resolver/classifier, parses NO
coordinate into a placement, draws NO stroke, writes NO PNG, and promotes NOTHING. Census stays frozen.

Proof-only; the JSON report is written under the gitignored data/outputs path.
Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_unmodeled_terminus_class_scout
"""
from __future__ import annotations

import json
import math
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
)
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.proof.run_all_redlines_closure_ledger import UNMODELED_TERMINUS, build_ledger
from truelinev2.proof.run_brenham_corpus import EXPECTED_COUNT, PDF, enumerate_corpus
from truelinev2.proof.run_log53_primitives_cohort_replay import (
    ENDPOINT_IDENTITY_NOT_MODELED,
    REPRESENTATIVE_ROUTE_CANDIDATE,
    classify_record,
)
from truelinev2.proof.run_reviewer_service_contract import resolve_corpus
from truelinev2.seam import ELIGIBLE_EXEMPLARS

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "unmodeled_terminus_class_scout"
TRUTH = _REPO_ROOT / "data" / "outputs" / "final_engine_truth_table" / \
    "final_engine_truth_table.json"
BASE_CONDUIT = set(BRENHAM_CONDUIT_LAYERS.values())
FROZEN_BUCKETS = {"DRAWABLE_REVIEW": 31, "HUMAN_ADJUSTABLE_REVIEW": 6,
                  "OUT_OF_CLASS": 1, "PICK_CARD_REVIEW": 17, "SOURCE_OR_KMZ_REQUIRED": 3}
ABSTAIN_4 = ("log5", "log31", "log38", "log43")
SEAM_ELIGIBLE = ("log53", "log64", "log71", "log59", "log66")   # this scout promotes nothing

EXPECTED_UNMODELED = ("log6", "log41", "log46", "log54", "log63", "log68")
# structure classes the dialect resolver can deterministically bind (the same probe set per terminus);
# nextlink_hh has no BRENHAM_STRUCTURE_LAYERS row -> the committed callout locator.
PROBE_STRUCT_CLASSES = ("installer_hh", "terminal_port_hh", "flower_pot")
SEED_LAYER = {"installer_hh": "NEXTLINK", "terminal_port_hh": "NEXTLINK",
              "nextlink_hh": "NEXTLINK", "flower_pot": "FLOWER POT"}

# owner-stated termini per UNMODELED log (sheet, station, reset_token); owner-authoritative stations
# read from the reviewed evidence_notes -- nothing invented.
TERMINI = {
    "log6":  {"start": (5, "0+56", True), "end": (5, "2+43", False)},
    "log41": {"start": (1, "7+40", True), "end": (1, "0+46", True)},
    "log46": {"start": (10, "44+08", True), "end": (14, "5+34", False)},
    "log54": {"start": (17, "3+91", True), "end": (21, "3+14", True)},
    "log63": {"start": (17, "0+00", True), "end": (17, "0+56", True)},
    "log68": {"start": (17, "5+03", False), "end": (20, "6+79", False)},
}

# deterministic partition categories + the exact owner-review target / blocker for each
FULL = "FULL_SOURCE_RECOVERED_OWNER_CONFIRM"          # both termini recovered on-route
PARTIAL = "PARTIAL_SOURCE_RECOVERED_OWNER_CONFIRM"     # one terminus recovered, other bare
REPRESENTATIVE = "NO_TERMINUS_STRUCTURE_REPRESENTATIVE_ONLY"   # neither terminus has a structure
PARTITION = {
    "log46": FULL, "log54": FULL,
    "log6": PARTIAL, "log63": PARTIAL,
    "log41": REPRESENTATIVE, "log68": REPRESENTATIVE,
}
NEXT_ACTION = {
    FULL: ("BOTH termini source-recovered on-route (UNCONFIRMED candidates) -> present to owner for "
           "endpoint-identity confirmation, then the existing endpoint-anchor bridge + sheet-local bind "
           "(the log52/log58 lane); cross-sheet frame join where multi-sheet"),
    PARTIAL: ("ONE terminus source-recovered on-route (UNCONFIRMED) -> owner-confirm it; the bare terminus "
              "needs column->structure / start-symbol recovery before an exact second endpoint exists"),
    REPRESENTATIVE: ("NEITHER terminus binds a modeled structure -> no exact endpoint exists; "
                     "representative-route-only (human-review pick-card lane), not a terminus-class to model"),
}

R_COMPLETE = "UNMODELED_TERMINUS_CLASS_SCOUT_COMPLETE"
B_TRUTH = "BLOCKED_UNMODELED_TRUTH_MISSING"
B_PDF = "BLOCKED_UNMODELED_PDF_MISSING"
B_COHORT = "BLOCKED_UNMODELED_COHORT_MISMATCH"
B_GUESS = "BLOCKED_UNMODELED_AMBIGUOUS_NOT_HELD"   # a terminus where >=2 classes bind was not held
B_ENCODED = "BLOCKED_UNMODELED_SILENTLY_ENCODED"
ALLOWED = {R_COMPLETE, B_TRUTH, B_PDF, B_COHORT, B_GUESS, B_ENCODED}


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


def _on_route(draw, seed_layer, xy) -> tuple:
    """Does the bound symbol connect to a modeled base conduit chain (on the bore route)?
    Returns (connected, chain_segs, reach_pt). Read-only; reuses the shipped topology primitive."""
    fp = symbol_footprint(draw, seed_layer, xy)
    chain = connected_chain([x for x in draw if x.get("layer") in BASE_CONDUIT], fp) if fp else []
    eps = dash_endpoints(chain)
    reach = min((math.hypot(p[0] - xy[0], p[1] - xy[1]) for p in eps), default=None)
    return (reach is not None and reach <= MAX_DASH_GAP), len(chain), (round(reach, 2) if reach is not None else None)


def resolve_terminus(plan, offset, sheet, station, reset) -> dict:
    """Run the SHIPPED resolvers for EVERY modeled class at one terminus. Returns the unique recovered
    class (on-route checked) or marks it bare / ambiguous. No class is ever invented or picked when >=2
    bind. Coordinates are extractor-derived."""
    words = plan.words(sheet, offset)
    draw = plan.line_items(sheet, offset)
    labels = [f"{station}=0+00", station] if reset else [station, f"{station}=0+00"]
    bound = {}
    for cls in PROBE_STRUCT_CLASSES:
        for label in labels:
            kw = dict(label_text=label, structure_class=cls, words=words, drawings=draw,
                      layer_table=BRENHAM_STRUCTURE_LAYERS)
            if cls == "flower_pot":
                kw["context_texts"] = ("FLOWER", "POT")
            v = resolve_structure_position(**kw)
            if v.result == POSITION_BOUND and v.symbol_xy:
                bound[cls] = tuple(v.symbol_xy)
                break
    nv = resolve_nextlink_hh_callout(station_sta=station, words=words, drawings=draw,
                                     callout_layer="ANNOTATION", symbol_layer="NEXTLINK")
    if nv.result == POSITION_BOUND and nv.symbol_xy:
        bound["nextlink_hh"] = tuple(nv.symbol_xy)
    out = {"sheet": sheet, "station": station, "classes_bound": sorted(bound),
           "recovered_class": None, "xy": None, "on_route": None, "chain_segs": None,
           "reach_pt": None, "state": "bare"}
    if len(bound) == 1:
        cls, xy = next(iter(bound.items()))
        conn, segs, reach = _on_route(draw, SEED_LAYER[cls], xy)
        out.update(recovered_class=cls, xy=[round(c, 2) for c in xy], on_route=conn,
                   chain_segs=segs, reach_pt=reach, state="recovered")
    elif len(bound) >= 2:
        out["state"] = "ambiguous"   # NO-GUESS: never pick one
    return out


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for stale in OUT_DIR.glob("*.png"):
        stale.unlink()

    doc = load_adjudication()
    rec = {r["log_id"]: r for r in doc["logs"]}
    gates = []
    result = B_COHORT

    if not TRUTH.is_file():
        gates.append(("G0 final engine truth table present", False, str(TRUTH)))
        return _emit(gates, B_TRUTH, {}, rec)
    truth_rows = json.loads(TRUTH.read_text(encoding="utf-8"))["rows"]

    gates.append(("G0 engine census frozen (OFF 31/6/1/17/3, ON 22/1/4, log44+abstains held)",
                  _census_frozen(doc), None))

    # G1 the scouted set is EXACTLY the closure ledger's UNMODELED_TERMINUS class, verified from the ledger
    ledger = build_ledger(truth_rows, doc)
    ledger_unmod = tuple(sorted((b for b, v in ledger.items() if v["category"] == UNMODELED_TERMINUS),
                                key=lambda s: int(s[3:])))
    gates.append(("G1 scouted set == ledger UNMODELED_TERMINUS_CLASS_NEEDED (6 logs), verified from the ledger",
                  ledger_unmod == EXPECTED_UNMODELED and set(TERMINI) == set(EXPECTED_UNMODELED),
                  list(ledger_unmod)))

    # G2 every member carries the ROOT gate ENDPOINT_IDENTITY_NOT_MODELED with NO owner-named modeled class
    every_unmodeled = all(
        classify_record(rec[l])["classification"] == REPRESENTATIVE_ROUTE_CANDIDATE
        and ENDPOINT_IDENTITY_NOT_MODELED in classify_record(rec[l])["blockers"]
        and not classify_record(rec[l])["signals"]["has_modeled_terminus"]
        for l in EXPECTED_UNMODELED)
    gates.append(("G2 every member is ENDPOINT_IDENTITY_NOT_MODELED (no owner-named modeled terminus class)",
                  every_unmodeled, None))

    # G3 reuses the SHIPPED resolvers + canonical classifier; defines NO new resolver/classifier here
    gates.append(("G3 reuses shipped resolve_structure_position / resolve_nextlink_hh_callout / classify_record (no new primitive)",
                  resolve_structure_position.__module__ == "truelinev2.extract.structure_position"
                  and resolve_nextlink_hh_callout.__module__ == "truelinev2.extract.structure_position"
                  and classify_record.__module__ == "truelinev2.proof.run_log53_primitives_cohort_replay", None))

    if not os.path.isfile(PDF):
        gates.append(("G4 plan PDF present (read-only, to run the resolvers)", False, PDF))
        return _emit(gates, B_PDF, {}, rec)
    corpus_dir, _ = resolve_corpus()
    corpus = {p.stem: p for p in enumerate_corpus(corpus_dir)} if os.path.isdir(corpus_dir) else {}
    gates.append(("G4 plan PDF + corpus present", os.path.isfile(PDF) and len(corpus) == EXPECTED_COUNT,
                  {"pdf": os.path.isfile(PDF), "corpus": len(corpus)}))

    plan = PlanPdf(PDF)
    scout = {}
    try:
        offset = select_dialect(plan).calibrate(plan, 13)
        for lid in EXPECTED_UNMODELED:
            t = {role: resolve_terminus(plan, offset, *TERMINI[lid][role]) for role in ("start", "end")}
            n_rec = sum(1 for r in t.values() if r["state"] == "recovered")
            n_amb = sum(1 for r in t.values() if r["state"] == "ambiguous")
            partition = (FULL if n_rec == 2 else PARTIAL if n_rec == 1 else REPRESENTATIVE)
            scout[lid] = {"termini": t, "n_recovered": n_rec, "n_ambiguous": n_amb,
                          "partition": partition, "next_action": NEXT_ACTION[partition]}
    finally:
        plan.close()

    # G5 NO-GUESS: no terminus was AMBIGUOUS-but-picked; recovered termini are uniquely bound AND on-route
    no_guess = all(
        all(r["state"] != "ambiguous" or r["recovered_class"] is None for r in s["termini"].values())
        and all(r["recovered_class"] is None or (len(r["classes_bound"]) == 1 and r["on_route"])
                for r in s["termini"].values())
        for s in scout.values())
    gates.append(("G5 NO-GUESS: recovered termini are UNIQUE single-class binds, on-route; no ambiguous pick",
                  no_guess, None))

    # G6 deterministic partition matches the source-recovered reality (2 full / 2 partial / 2 representative)
    got = {lid: s["partition"] for lid, s in scout.items()}
    gates.append(("G6 partition: FULL=log46/log54 (2); PARTIAL=log6/log63 (2); REPRESENTATIVE=log41/log68 (2)",
                  got == PARTITION,
                  {"full": [l for l in scout if got[l] == FULL],
                   "partial": [l for l in scout if got[l] == PARTIAL],
                   "representative": [l for l in scout if got[l] == REPRESENTATIVE]}))

    # G7 ENCODES NOTHING: the 6 carry NO endpoint_anchors; classify_cohort over them is UNCHANGED (still
    #    UNMODELED); recovered classes are flagged UNCONFIRMED candidates, never written to the artifact.
    no_encode = (all(not rec[l].get("endpoint_anchors") for l in EXPECTED_UNMODELED)
                 and all(ledger[l]["category"] == UNMODELED_TERMINUS for l in EXPECTED_UNMODELED))
    gates.append(("G7 ENCODES NOTHING: the 6 carry no endpoint_anchors; still UNMODELED in the artifact (candidates UNCONFIRMED)",
                  no_encode, None))

    if all(x for _, x, _ in gates):
        result = R_COMPLETE
    elif not gates[1][1]:
        result = B_COHORT
    elif not gates[5][1]:
        result = B_GUESS
    elif not gates[6][1]:
        result = B_ENCODED
    else:
        result = B_COHORT
    return _emit(gates, result, rec, scout=scout, ledger_unmod=ledger_unmod)


def _emit(gates, result, rec, scout=None, ledger_unmod=()) -> int:
    pngs = sorted(p.name for p in OUT_DIR.glob("*.png"))
    gates.append(("G8 no render / zero PNG / seam unchanged (nothing promoted)",
                  len(pngs) == 0 and tuple(ELIGIBLE_EXEMPLARS) == SEAM_ELIGIBLE, {"pngs": pngs}))
    gates.append(("G9 result in allowed enum", result in ALLOWED, result))
    all_pass = all(x for _, x, _ in gates)
    scout = scout or {}
    report = {
        "milestone": "UNMODELED_TERMINUS_CLASS scout (proof/report only; read-only resolver recovery)",
        "verdict": "PASS" if all_pass else "FAIL",
        "result": result if all_pass else "BLOCKED",
        "class": "UNMODELED_TERMINUS_CLASS_NEEDED",
        "scouted_set": list(ledger_unmod) or list(EXPECTED_UNMODELED),
        "finding": ("NO new resolver/primitive needed: the SHIPPED resolvers, run read-only per terminus, "
                    "partition the class into source-recoverable owner-confirmation candidates (existing "
                    "bridge lane) vs representative-route-only (no terminus structure)."),
        "partition_counts": {
            FULL: sum(1 for s in scout.values() if s["partition"] == FULL),
            PARTIAL: sum(1 for s in scout.values() if s["partition"] == PARTIAL),
            REPRESENTATIVE: sum(1 for s in scout.values() if s["partition"] == REPRESENTATIVE)},
        "safe_subset_owner_confirm_candidates": {
            lid: {role: {"recovered_class": t["recovered_class"], "station": t["station"],
                         "sheet": t["sheet"], "on_route": t["on_route"], "xy": t["xy"]}
                  for role, t in s["termini"].items() if t["recovered_class"]}
            for lid, s in scout.items() if s["partition"] in (FULL, PARTIAL)},
        "held_representative_route_only": [lid for lid, s in scout.items()
                                           if s["partition"] == REPRESENTATIVE],
        "per_log": {lid: {"partition": s["partition"], "n_recovered": s["n_recovered"],
                          "termini": s["termini"], "next_action": s["next_action"]}
                    for lid, s in scout.items()},
        "doctrine": {
            "no_guess_law": "a terminus is RECOVERED only when EXACTLY ONE modeled class binds (unique); >=2 -> held",
            "candidates_unconfirmed": "recovered classes are SOURCE-RECOVERED, OWNER-CONFIRMATION REQUIRED (untrusted until reviewed)",
            "encodes_nothing": True, "no_new_resolver": True, "no_pdf_placement": True,
            "no_render": True, "no_seam_promotion": True, "engine_census_frozen": True,
        },
        "scope_guard": {"product_wiring": False, "broad_renderer": False, "match_review_wiring": False,
                        "runtime_batch": False, "deploy": False, "coordinates_invented": False},
        "next_slice": ("present the FULL candidates (log46, log54) for owner endpoint-identity confirmation, "
                       "then the existing endpoint-anchor bridge + sheet-local bind (+ cross-sheet frame "
                       "join). For PARTIAL (log6, log63): owner-confirm the recovered end + recover the bare "
                       "start (column->structure). For REPRESENTATIVE (log41, log68): the human-review "
                       "representative-route pick-card lane. Each separately authorized; nothing encoded here."),
        "gates": [{"name": n, "pass": bool(x), "detail": d} for n, x, d in gates],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "unmodeled_terminus_class_scout.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"[unmodeled] result: {report['result']}")
    for lid in EXPECTED_UNMODELED:
        s = scout.get(lid)
        if s:
            st, en = s["termini"]["start"], s["termini"]["end"]
            print(f"[unmodeled]   {lid:>6} {s['partition']:<42} "
                  f"start={st['recovered_class'] or st['state']} end={en['recovered_class'] or en['state']}")
    for n, x, _ in gates:
        print(f"[unmodeled] {'PASS' if x else 'FAIL'}  {n}")
    print(f"[unmodeled] VERDICT: {'PASS' if all_pass else 'FAIL'}  (report: {OUT_DIR})")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
