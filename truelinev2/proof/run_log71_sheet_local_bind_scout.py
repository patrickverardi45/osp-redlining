r"""OWNER-PACKET-2 -- log71 sheet-local SOURCE-BIND scout (PROOF ONLY; identity resolution).

log71 was selected by the next-candidate scout as the safest remaining PARTIAL, with ONE open
blocker: the START is "Lawndale, reset STA 7+50 = 0+00" -- no structure class was owner-named. This
scout resolves that identity against REAL sheet source (same primitives as log53/log64; never
screenshot pixels, never invented coordinates) and confirms whether log71 can enter the controlled
pipeline as a log53-style two sheet-local legs joined by station identity at the 5+45 matchline.

It encodes NO endpoint_anchors, draws NO stroke, renders NO PNG, and solves NO cross-sheet frame.

Findings it proves on real source (single-sheet per leg; cross-sheet translation deferred):
  END leg  (sheet 23): STA 6+95 FLOWER POT binds via resolve_structure_position(flower_pot,
                       label "6+95" + ("FLOWER","POT")); a base conduit chain reaches the
                       "MATCHLINE STA 5+45 - SEE SHEET 24" boundary (the 5+45 token uniquely ON a
                       MATCHLINE bbox -- the other 5+45 is a route-ladder tick).
  START leg (sheet 24): the Lawndale reset STA 7+50 = 0+00 RESOLVES as a NEXTLINK HH via the
                       COMMITTED resolve_nextlink_hh_callout locator (the same ANNOTATION-callout
                       pattern proven for log53's start) -> start class is MODELED (nextlink_hh),
                       not unmodeled / label-only / ambiguous; a base conduit chain is connected.

Census stays frozen (no artifact change). A render is NOT done; encoding endpoint_anchors is the
recommended NEXT slice now that the start identity is source-resolved.

Proof-only; the JSON report is written under the gitignored data/outputs path.
Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_log71_sheet_local_bind_scout
"""
from __future__ import annotations

import json
import os
import re

from truelinev2.config import _REPO_ROOT
from truelinev2.extract.conduit_topology import (
    MAX_DASH_GAP,
    connected_chain,
    dash_endpoints,
    symbol_footprint,
)
from truelinev2.extract.matchline_join import extend_dash_to_boundary, matchline_bboxes, nearest_gap
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
from truelinev2.proof.run_brenham_corpus import EXPECTED_COUNT, PDF, enumerate_corpus
from truelinev2.proof.run_log53_primitives_cohort_replay import MODELED_TOKENS
from truelinev2.proof.run_reviewer_service_contract import resolve_corpus

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "log71_sheet_local_bind_scout"
TRUTH = _REPO_ROOT / "data" / "outputs" / "final_engine_truth_table" / \
    "final_engine_truth_table.json"
SHEET_END, SHEET_START = 23, 24
END_FP_LABEL, START_STA, MATCHLINE_STA = "6+95", "7+50", "5+45"
INSTALLER_SYMBOL_LAYER = "NEXTLINK"
MATCHLINE_REACH_SEP = 10.0   # the chosen matchline's chain-reach must beat rivals by this (pt)
FROZEN_BUCKETS = {"DRAWABLE_REVIEW": 31, "HUMAN_ADJUSTABLE_REVIEW": 6,
                  "OUT_OF_CLASS": 1, "PICK_CARD_REVIEW": 17, "SOURCE_OR_KMZ_REQUIRED": 3}
ABSTAIN_4 = ("log5", "log31", "log38", "log43")
_BASE_CONDUIT = set(BRENHAM_CONDUIT_LAYERS.values())

R_COMPLETE = "LOG71_SHEET_LOCAL_BIND_SCOUT_COMPLETE"
R_START_RESOLVED = "LOG71_START_IDENTITY_RESOLVED"
R_PARTIAL = "LOG71_PARTIAL_BIND_CONFIRMED"
B_START_AMBIG = "BLOCKED_LOG71_START_IDENTITY_AMBIGUOUS"
B_START_UNMODELED = "BLOCKED_LOG71_START_CLASS_UNMODELED"
B_END = "BLOCKED_LOG71_END_BIND_FAILED"
B_MATCHLINE = "BLOCKED_LOG71_MATCHLINE_BOUNDARY_FAILED"
B_ROUTE = "BLOCKED_LOG71_ROUTE_NOT_SOURCE_BACKED"
B_AMBIG = "BLOCKED_LOG71_SOURCE_AMBIGUOUS"
ALLOWED = {R_COMPLETE, R_START_RESOLVED, R_PARTIAL, B_START_AMBIG, B_START_UNMODELED, B_END,
           B_MATCHLINE, B_ROUTE, B_AMBIG}


def owner_named_classes(evidence_notes: str) -> set:
    """The modeled structure classes the OWNER explicitly NAMED in the reviewed evidence_notes
    (authoritative). A class the extractor can bind but the owner did NOT name is source-resolved,
    NOT owner-named -- the bridge holds owner identity, so encoding such a class needs owner
    confirmation first. Pure."""
    up = str(evidence_notes or "").upper()
    return {cls for tok, cls in MODELED_TOKENS if tok in up}


def select_matchline_by_chain_reach(sorted_reaches, sep: float = MATCHLINE_REACH_SEP) -> bool:
    """The conduit chain physically TERMINATES at exactly one matchline. Given the per-candidate
    chain-to-matchline reach gaps (ascending), the boundary is uniquely the closest IFF that reach
    is within MAX_DASH_GAP AND clearly beats the next candidate by ``sep`` -- so a same-numbered
    route-ladder tick near a DIFFERENT matchline is not mistaken for this leg's boundary. This
    chain-anchored rule is needed because '5+45' is NOT sheet-unique on sheet 23 (and sheet 23
    carries a second matchline at 6+00); the strict unique-label law does not apply. Pure."""
    if not sorted_reaches:
        return False
    if sorted_reaches[0] > MAX_DASH_GAP:
        return False
    return len(sorted_reaches) == 1 or (sorted_reaches[1] - sorted_reaches[0]) >= sep


def locate_matchline_boundary(words, draw, sta, chain):
    """Resolve the ``sta`` matchline boundary point the conduit ``chain`` terminates at. The bare
    ``sta`` label is not sheet-unique, so candidates are disambiguated by CHAIN REACH (the matchline
    the chain actually reaches, uniquely). Returns (boundary_xy, reach_gap, unique) or
    (None, reach_or_None, unique). No invented coordinate."""
    toks = [w for w in words if re.match(rf"^{re.escape(sta)}", str(w.get("text", "")))]
    mls = matchline_bboxes(draw, "MATCHLINE")
    eps = dash_endpoints(chain)
    if not toks or not mls or not eps:
        return None, None, False
    cands = []
    for t in toks:
        mlb = min(mls, key=lambda bb: nearest_gap([(t["xc"], t["yc"])], bb))
        reach = min(nearest_gap([p], mlb) for p in eps)
        cands.append((reach, mlb))
    cands.sort(key=lambda c: c[0])
    unique = select_matchline_by_chain_reach([r for r, _ in cands])
    if not unique:
        return None, (cands[0][0] if cands else None), False
    reach, mlb = cands[0]
    bnd = extend_dash_to_boundary(chain, mlb)
    return (tuple(bnd) if bnd else None), reach, True


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
        stale.unlink()

    doc = load_adjudication()
    rec = {r["log_id"]: r for r in doc["logs"]}
    gates, ev = [], {"sheet_end": SHEET_END, "sheet_start": SHEET_START}

    gates.append(("G0 engine census frozen (OFF 31/6/1/17/3, ON 22/1/4, log44+abstains held)",
                  _census_frozen(doc), None))
    l53s = (rec["log53"].get("endpoint_anchors") or {}).get("start") or {}
    l64s = (rec["log64"].get("endpoint_anchors") or {}).get("start") or {}
    gates.append(("G0b log53 + log64 prior behavior preserved; log71 has NO anchors yet",
                  l53s.get("structure_class") == "nextlink_hh"
                  and l64s.get("structure_class") == "installer_hh"
                  and "endpoint_anchors" not in rec["log71"], None))

    if not os.path.isfile(PDF):
        gates.append(("G1 plan PDF present", False, f"missing {PDF}"))
        return _emit(gates, B_ROUTE, ev)
    corpus_dir, _ = resolve_corpus()
    corpus = {p.stem: p for p in enumerate_corpus(corpus_dir)} if os.path.isdir(corpus_dir) else {}
    gates.append(("G1 plan PDF + corpus present",
                  os.path.isfile(PDF) and len(corpus) == EXPECTED_COUNT, len(corpus)))

    plan = PlanPdf(PDF)
    result = B_ROUTE
    try:
        dialect = select_dialect(plan)
        offset = dialect.calibrate(plan, 13)

        # ---- END leg (sheet 23): 6+95 flower pot + 5+45 matchline boundary ------
        we, de = plan.words(SHEET_END, offset), plan.line_items(SHEET_END, offset)
        pv = resolve_structure_position(label_text=END_FP_LABEL, structure_class="flower_pot",
                                        words=we, drawings=de, layer_table=BRENHAM_STRUCTURE_LAYERS,
                                        context_texts=("FLOWER", "POT"))
        ev["end_bind_result"] = pv.result
        ev["end_flower_pot_xy"] = [round(c, 2) for c in pv.symbol_xy] if pv.symbol_xy else None
        gates.append(("G2 END flower_pot STA 6+95 binds on sheet 23 (label+context -> symbol)",
                      pv.result == POSITION_BOUND and bool(pv.symbol_xy), pv.result))
        if pv.result != POSITION_BOUND or not pv.symbol_xy:
            return _emit(gates, B_END, ev)
        e_xy = tuple(pv.symbol_xy)
        fp = symbol_footprint(de, "FLOWER POT", e_xy)
        end_chain = connected_chain([x for x in de if x.get("layer") in _BASE_CONDUIT], fp) if fp else []
        ev["end_chain_segs"] = len(end_chain)
        if not end_chain:
            return _emit(gates, B_ROUTE, ev)

        bnd, reach, uniq = locate_matchline_boundary(we, de, MATCHLINE_STA, end_chain)
        ev["end_matchline_reach_pt"] = round(reach, 2) if reach is not None else None
        ev["end_matchline_boundary_xy"] = [round(c, 2) for c in bnd] if bnd else None
        ev["matchline_disambiguation"] = "chain-reach (5+45 label not sheet-unique; sheet 23 also carries a 6+00 matchline)"
        gates.append(("G3 5+45 matchline boundary uniquely located via chain-reach on sheet 23",
                      bnd is not None and uniq, {"unique": uniq, "bnd": ev["end_matchline_boundary_xy"]}))
        if bnd is None:
            return _emit(gates, B_MATCHLINE, ev)

        # ---- START leg (sheet 24): resolve the Lawndale reset identity ----------
        ws, ds = plan.words(SHEET_START, offset), plan.line_items(SHEET_START, offset)
        nv = resolve_nextlink_hh_callout(station_sta=START_STA, words=ws, drawings=ds,
                                         callout_layer="ANNOTATION", symbol_layer="NEXTLINK")
        ev["start_nextlink_callout_result"] = nv.result
        ev["start_symbol_xy"] = [round(c, 2) for c in nv.symbol_xy] if nv.symbol_xy else None
        start_class = None
        if nv.result == POSITION_BOUND and nv.symbol_xy:
            start_class = "nextlink_hh"
        else:
            # is it some OTHER modeled class, or unmodeled? (probe the modeled structure binder)
            other = [c for c in ("installer_hh", "flower_pot", "terminal_port_hh")
                     if resolve_structure_position(
                         label_text=f"{START_STA}=0+00", structure_class=c, words=ws, drawings=ds,
                         layer_table=BRENHAM_STRUCTURE_LAYERS).result == POSITION_BOUND]
            ev["start_other_modeled_binds"] = other
            if len(other) == 1:
                start_class = other[0]
            elif len(other) > 1:
                return _emit(gates, B_START_AMBIG, ev)
            else:
                return _emit(gates, B_START_UNMODELED, ev)
        ev["start_structure_class"] = start_class
        # DOCTRINE: the source bind RESOLVES the class, but the bridge holds OWNER identity. The
        # owner's notes name the END ("FLOWER POT") but NOT the START class ("Lawndale reset") --
        # so the start class is source-resolved, NOT owner-named, and must be owner-confirmed
        # before it is encoded into endpoint_anchors.
        named = owner_named_classes(rec["log71"].get("evidence_notes"))
        ev["owner_named_classes"] = sorted(named)
        ev["start_class_owner_named"] = start_class in named
        ev["end_class_owner_named"] = "flower_pot" in named
        gates.append(("G4 Lawndale START STA 7+50=0+00 SOURCE-resolves to a MODELED class (nextlink_hh)",
                      start_class == "nextlink_hh", start_class))
        gates.append(("G4b honesty: start class is source-resolved but NOT owner-named (end FP is)",
                      ev["start_class_owner_named"] is False and ev["end_class_owner_named"] is True,
                      {"named": sorted(named)}))

        s_xy = tuple(nv.symbol_xy)
        sfp = symbol_footprint(ds, INSTALLER_SYMBOL_LAYER, s_xy)
        start_chain = connected_chain([x for x in ds if x.get("layer") in _BASE_CONDUIT], sfp) if sfp else []
        ev["start_chain_segs"] = len(start_chain)
        gates.append(("G5 both legs carry a source conduit chain (start s24 + end s23)",
                      len(start_chain) > 0 and len(end_chain) > 0,
                      {"start_segs": len(start_chain), "end_segs": len(end_chain)}))
        if not start_chain:
            return _emit(gates, B_ROUTE, ev)

        result = R_COMPLETE
    finally:
        plan.close()

    return _emit(gates, result, ev)


def _emit(gates, result, ev) -> int:
    gates.append(("G6 result in allowed enum", result in ALLOWED, result))
    pngs = sorted(p.name for p in OUT_DIR.glob("*.png"))
    gates.append(("G7 zero PNG / zero stroke (no render lane)", len(pngs) == 0, {"pngs": pngs}))
    complete = result in (R_COMPLETE, R_START_RESOLVED, R_PARTIAL)
    all_pass = all(x for _, x, _ in gates) and complete
    # the start class is source-resolved but NOT owner-named -> NOT safe to auto-encode; owner
    # confirmation of the start structure class is required first (doctrine: owner identity).
    start_owner_named = ev.get("start_class_owner_named") is True
    encodable = result == R_COMPLETE and start_owner_named
    report = {
        "milestone": "OWNER-PACKET-2 -- log71 sheet-local source-bind scout (proof only; identity resolution)",
        "verdict": "PASS" if all_pass else "FAIL",
        "result": result, "target": "log71",
        "start_identity_source_resolved": bool(ev.get("start_structure_class")),
        "start_structure_class": ev.get("start_structure_class"),
        "start_class_owner_named": ev.get("start_class_owner_named"),
        "end_class_owner_named": ev.get("end_class_owner_named"),
        "endpoint_anchors_encodable_next": encodable,
        "next_slice": (
            "OWNER-CONFIRM the log71 START class first: STA 7+50=0+00 SOURCE-resolves as a NEXTLINK "
            "HH via the committed locator (same primitive as log53), but the owner's notes name only "
            "the END ('STA 6+95 FLOWER POT') -- not the start class ('Lawndale reset'). Present this "
            "source bind for owner confirmation; ONLY after the owner confirms the start is a NEXTLINK "
            "HH, encode endpoint_anchors (start nextlink_hh @ s24; end flower_pot @ s23; "
            "matchline_continuation @ STA 5+45) and run the log53-style TWO sheet-local-leg source-bind "
            "proof (chain-reach 5+45 disambiguation; cross-sheet translation deferred)."
            if result == R_COMPLETE else "resolve the reported blocker before encoding"),
        "evidence": ev,
        "no_render": True, "no_invented_coordinates": True, "no_screenshot_pixels": True,
        "no_cross_sheet": True, "no_anchor_encoding": True, "coords_are_extractor_derived": True,
        "gates": [{"name": n, "pass": bool(x), "detail": d} for n, x, d in gates],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "log71_sheet_local_bind_scout.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"[log71-scout] result: {result}  start_class: {ev.get('start_structure_class')}")
    for k in ("end_bind_result", "end_flower_pot_xy", "end_chain_segs", "end_matchline_reach_pt",
              "end_matchline_boundary_xy", "start_nextlink_callout_result", "start_symbol_xy",
              "start_structure_class", "start_class_owner_named", "end_class_owner_named",
              "start_chain_segs"):
        if k in ev:
            print(f"[log71-scout]   {k}: {ev[k]}")
    print(f"[log71-scout]   endpoint_anchors_encodable_next: {report['endpoint_anchors_encodable_next']}")
    for n, x, _ in gates:
        print(f"[log71-scout] {'PASS' if x else 'FAIL'}  {n}")
    print(f"[log71-scout] VERDICT: {'PASS' if all_pass else 'FAIL'}  (report: {OUT_DIR})")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
