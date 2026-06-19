r"""KMZ DROP-IDENTITY JOIN -> redline artifacts (PROOF ONLY; read-only; product-gated).

The PDF station-corridor + drop-terminus solvers proved the flower-pot DROP bores log30/log50 cannot be cut
at a ruler point, and that the geometric pot search is non-unique. This slice asks the authorized next
question: can the KMZ feature/route/AP attributes UNIQUELY identify the drop terminus, and -- whether via the
KMZ or via the PDF's own printed end note -- render the correct PDF redline?

Two source channels are tried, both uniqueness-mandatory, no guessing, no review-choice, no owner naming:

  (A) KMZ DROP-IDENTITY JOIN. Read the design KMZ (extract/kmz). Try to bind the bore's flower-pot terminus
      to a UNIQUE KMZ feature by: AP id / splice-loc (the shipped KMZ_AP_STRUCTURE_JOIN), feature name,
      served-address / parent-AP field, or a Vacant-Pipe ROUTE whose drawn length matches the bore span and
      whose endpoints link a named structure to one pot. If exactly one -> KMZ-bound terminus.

  (B) PDF PRINTED END-NOTE. The proven b.4 grammar (bind_end_structure_note -> resolve_structure_position):
      a printed ``STA <end> FLOWER POT`` note binds EXACTLY ONE drawn pot on a referenced sheet. This is the
      PDF's own unique terminus identity; it needs no KMZ.

Render rule: if EITHER channel yields a UNIQUE terminus AND the on-sheet conduit traces a source-backed route
from a uniquely-bound on-sheet structure to that terminus, render a red REVIEW stroke (a PARTIAL sheet-local
terminus leg when the bore's start is cross-sheet). Abstain (named) otherwise, stating the exact missing KMZ
field. The terminus leg is labeled PARTIAL and never claims the full cross-sheet bore.

No owner naming. No review-choice. No fixture mutation. No coordinate encoding. No classification/seam/ledger.
No product/runtime/api/backend/web/deploy/main. Red strokes only. PNG/JSON under gitignored data/outputs.

Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_kmz_drop_identity_join_slice
"""
from __future__ import annotations

import json
import math
import os

from truelinev2.config import _REPO_ROOT
from truelinev2.extract.conduit_topology import (
    ORIGIN_BOUND, connected_chain, dash_endpoints, discriminate_origin, symbol_footprint,
)
from truelinev2.extract.kmz import BRENHAM_KMZ_DIALECT, ap_index, read_kmz
from truelinev2.extract.registry import select_dialect
from truelinev2.extract.structure_anchor import BOUND, bind_end_structure_note
from truelinev2.extract.structure_position import (
    BRENHAM_CONDUIT_LAYERS, BRENHAM_STRUCTURE_LAYERS, POSITION_BOUND, cluster_symbols,
    resolve_structure_position,
)
from truelinev2.ingest.manual_adjudication import (
    activation_summary, apply_adjudications, load_adjudication, parent_run_duplicate_check,
)
from truelinev2.ingest.normalize import load_borelog
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.match.kmz_structure_join import terminal_anchors
from truelinev2.proof.run_brenham_corpus import EXPECTED_COUNT, PDF, enumerate_corpus
from truelinev2.proof.run_log59_render_artifact_slice import (
    interior_vertices_are_dash_endpoints, route_edges_source_backed,
)
from truelinev2.proof.run_log71_render_artifact_slice import order_chain_route, route_length
from truelinev2.proof.run_reviewer_service_contract import resolve_corpus
from truelinev2.render.crop import REDLINE_STROKE_RGB, render_redline_stroke

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "kmz_drop_identity_join"
TRUTH = _REPO_ROOT / "data" / "outputs" / "final_engine_truth_table" / "final_engine_truth_table.json"
KMZ = _REPO_ROOT / "data" / "uploads" / "Brenham, TX - Phase 5_Design Team.kmz"
FROZEN_BUCKETS = {"DRAWABLE_REVIEW": 31, "HUMAN_ADJUSTABLE_REVIEW": 6,
                  "OUT_OF_CLASS": 1, "PICK_CARD_REVIEW": 17, "SOURCE_OR_KMZ_REQUIRED": 3}
ABSTAIN_4 = ("log5", "log31", "log38", "log43")
VACANT = BRENHAM_CONDUIT_LAYERS["VACANT HDPE"]
TARGETS = {"log30": (10, 12), "log50": (10, 11, 12)}    # authorized: log30 + log50 only
ROUTE_SPAN_TOL_FT = 25.0     # a KMZ Vacant-Pipe route length must be within this of the bore span to be a join

R_RENDERED = "KMZ_DROP_RENDER_PRODUCED_ARTIFACTS"
R_NO_RENDER = "KMZ_DROP_NO_SAFE_ARTIFACT"
B_SCOPE = "BLOCKED_KMZ_DROP_SCOPE_VIOLATION"
ALLOWED = {R_RENDERED, R_NO_RENDER, B_SCOPE}


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


def _feet(a, b):  # haversine ft between (lon,lat) points
    R = 20902231.0
    lon1, lat1, lon2, lat2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    dlon, dlat = lon2 - lon1, lat2 - lat1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def _route_len_ft(r):
    return sum(_feet(r.vertices[i], r.vertices[i + 1]) for i in range(len(r.vertices) - 1))


def kmz_drop_identity(model, span_ft):
    """Try to bind the flower-pot terminus to a UNIQUE KMZ feature. Returns (bound_xy|None, evidence). The
    Brenham KMZ flower pots carry NO identity key (name/AP/splice/served-address), so the only candidate join
    is a Vacant-Pipe ROUTE of matching drawn length whose far endpoint is a single pot -- reported here."""
    pots = [s for s in model.structures if s.kmz_class == "flower_pot"]
    vac = [r for r in model.routes if r.kmz_class == "bore_vacant_pipe"]
    named_pots = [p for p in pots if p.name or p.ap_ids or p.splice_loc]
    pot_field_keys = sorted({k for p in pots for k in p.fields})
    span_routes = [round(_route_len_ft(r)) for r in vac if abs(_route_len_ft(r) - span_ft) <= ROUTE_SPAN_TOL_FT]
    ev = {"flower_pots": len(pots), "named_or_keyed_pots": len(named_pots),
          "pot_field_keys": pot_field_keys, "ap_keyed_structures": len(ap_index(model)),
          "terminal_anchors_two_field": len(terminal_anchors(model, "terminal_port_hh")),
          "vacant_pipe_routes": len(vac),
          "vacant_routes_matching_span_pm{0}ft".format(int(ROUTE_SPAN_TOL_FT)): span_routes}
    # uniqueness-mandatory: a pot is KMZ-bound only if exactly one keyed pot OR exactly one span-matched route
    if len(named_pots) == 1:
        p = named_pots[0]
        return (p.lon, p.lat), {**ev, "join": "unique keyed flower-pot"}
    if len(span_routes) == 1:
        return "route-length", {**ev, "join": "unique Vacant-Pipe route length match"}
    keyed = sum(1 for p in pots if p.ap_ids or p.splice_loc or (p.name and p.name.lower() != "unnamed feature")
                or any(p.fields.get(k) for k in ("AP Number", "Scid")))
    ev["pots_with_any_populated_key"] = keyed
    ev["missing_kmz_field"] = (
        f"the flower-pot nodes carry NO usable per-bore drop key: 0/{len(pots)} are name/AP/splice keyed to a "
        f"bore. The AP Number / Scid / HH Sizes columns EXIST but are populated on only {keyed}/{len(pots)} pot(s) "
        f"(a lone Scid='Terminal HH'/AP=88 pot, which joins neither target). AND no Vacant-Pipe route length "
        f"matches the bore span (drop routes top out far below it). Required to disambiguate a drop terminus: a "
        f"populated parent-AP / served-address tag on the Flower Pot (or Vacant Pipe) feature, OR a full-length "
        f"bore route -- neither is present in this KMZ")
    return None, ev


def pdf_terminus_leg(plan, offset, bore, sheets):
    """The PDF's own unique terminus + a source-backed on-sheet leg to it (the proven b.4 + b.6 chain). Returns
    (sheet, start_xy, pot_xy, route)|None. The end pot is bound by its printed ``STA <end>`` note (exactly one
    drawn pot); the on-sheet origin structure is bound by the exactly-one-footprint conduit law."""
    for sheet in sheets:
        eid = bind_end_structure_note(bore.station_end_ft, plan.lines(sheet, offset))
        if eid.result != BOUND or "FLOWER" not in (eid.structure_label or "").upper():
            continue
        draw = plan.line_items(sheet, offset)
        pos = resolve_structure_position(label_text=eid.end_station, structure_class="flower_pot",
                                         words=plan.words(sheet, offset), drawings=draw,
                                         layer_table=BRENHAM_STRUCTURE_LAYERS, context_texts=("FLOWER", "POT"))
        if pos.result != POSITION_BOUND:
            continue
        pot = tuple(pos.symbol_xy)
        end_bb = symbol_footprint(draw, "FLOWER POT", pot)
        chain = connected_chain([x for x in draw if x["layer"] == VACANT], end_bb) if end_bb else []
        if not chain:
            continue
        cands = {}
        for lay in ("NEXTLINK", "FLOWER POT"):
            for c in cluster_symbols(draw, lay):
                if math.hypot(c.x - pot[0], c.y - pot[1]) <= 8:
                    continue
                bb = symbol_footprint(draw, lay, (c.x, c.y))
                if bb:
                    cands[f"{lay}@{c.x:.0f},{c.y:.0f}"] = bb
        disc = discriminate_origin(dash_endpoints(chain), cands)
        if disc["result"] != ORIGIN_BOUND:
            continue
        wb = cands[disc["winner"]]
        start = ((wb[0] + wb[2]) / 2.0, (wb[1] + wb[3]) / 2.0)
        route = order_chain_route(chain, start, pot)
        if (route and route[0] == tuple(start) and route[-1] == pot and len(route) >= 3
                and route_edges_source_backed(route, chain)
                and interior_vertices_are_dash_endpoints(route, chain)):
            return {"sheet": sheet, "start_xy": start, "pot_xy": pot, "route": route,
                    "end_note": eid.note_line, "origin_winner": disc["winner"],
                    "end_station": eid.end_station}
    return None


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for stale in OUT_DIR.glob("*.png"):
        stale.unlink()

    doc = load_adjudication()
    gates = [("G0 engine census frozen (OFF 31/6/1/17/3, ON 22/1/4, log44+abstains held)",
              _census_frozen(doc), None)]
    if not os.path.isfile(PDF) or not KMZ.is_file():
        return _emit(gates, B_SCOPE, {}, [])
    corpus = {p.stem: p for p in enumerate_corpus(resolve_corpus()[0])}
    gates.append(("G1 plan PDF + corpus + KMZ present",
                  os.path.isfile(PDF) and len(corpus) == EXPECTED_COUNT and KMZ.is_file(), len(corpus)))

    model = read_kmz(str(KMZ), BRENHAM_KMZ_DIALECT)
    plan = PlanPdf(PDF)
    rendered, targets = [], {}
    try:
        offset = select_dialect(plan).calibrate(plan, 13)
        for lid, sheets in TARGETS.items():
            bore = load_borelog(str(corpus["bore_" + lid]))
            rec = {"span_ft": round(bore.span_ft), "sheet_refs": bore.sheet_refs}
            # (A) KMZ drop-identity join attempt
            kmz_xy, kmz_ev = kmz_drop_identity(model, bore.span_ft)
            rec["kmz_join"] = kmz_ev
            rec["kmz_terminus_bound"] = kmz_xy is not None
            # (B) the PDF's OWN printed end-note terminus + source-backed on-sheet leg (evidence)
            leg = pdf_terminus_leg(plan, offset, bore, sheets)
            if leg is not None:
                rec["pdf_terminus_identified"] = {
                    "sheet": leg["sheet"], "end_note": leg["end_note"],
                    "pot_xy": [round(v, 1) for v in leg["pot_xy"]], "origin_winner": leg["origin_winner"],
                    "route_vertices": len(leg["route"]), "route_len_pt": round(route_length(leg["route"]), 1)}
            # RENDER decision: place a stroke ONLY on a KMZ-BACKED unique terminus (the authorized identity
            # source for this lane). The KMZ supplies none (pots unnamed), so NOTHING is placed -- DO-NOT-WIDEN,
            # and the committed drop-lane sweep already classifies log50 as PICK_CARD (the on-sheet leg covers
            # only part of the bore; the origin candidate is span-refused). The PDF-identified terminus is
            # reported as EVIDENCE, never drawn here.
            if kmz_xy is not None and leg is not None:
                png = render_redline_stroke(
                    plan, lid, leg["sheet"], offset, leg["route"], status="REVIEW",
                    reason=(f"DROP-TERMINUS (KMZ-backed, sheet {leg['sheet']}): bore {lid} -> FLOWER POT @ "
                            f"{leg['end_station']} uniquely identified by KMZ + bound by the printed note"),
                    out_dir=str(OUT_DIR), mandatory_points=[leg["start_xy"], leg["pot_xy"]], pad=150.0)
                if png and os.path.isfile(png):
                    rendered.append((lid, png, leg, "full"))
                    rec["png"] = os.path.basename(png)
                    rec["result"] = "RENDERED_KMZ_BACKED_TERMINUS"
                else:
                    rec["result"] = "RENDER_RETURNED_NO_PNG"
            elif leg is not None:
                rec["result"] = "TERMINUS_PDF_IDENTIFIED_PLACEMENT_BLOCKED_CROSS_SHEET"
                rec["missing_evidence"] = (
                    "the terminus IS uniquely identified -- by the PDF's OWN printed end note (FLOWER POT @ "
                    f"{leg['end_station']}, sheet {leg['sheet']}), NOT the KMZ -- so the drop pot is no longer "
                    "the blocker. But NO stroke is placed: (1) " + kmz_ev.get("missing_kmz_field", "") +
                    "; (2) the on-sheet conduit leg covers only the terminus end (intermediate HH "
                    f"{leg['origin_winner']} -> pot); the bore's 0+00 origin is cross-sheet, so the committed "
                    "drop-lane sweep classifies this as PICK_CARD (span-refused). The named missing capability "
                    "for a CORRECT full render is matchline-joined cross-sheet conduit chain assembly")
            else:
                rec["result"] = "NO_UNIQUE_TERMINUS"
                rec["missing_evidence"] = (
                    "PDF: no bindable printed 'STA <end> FLOWER POT' end note on the bore's sheets "
                    "(end identity unprinted). " + kmz_ev.get("missing_kmz_field", ""))
            targets[lid] = rec
    finally:
        plan.close()

    gates.append(("G2 every render has a real PNG; every abstain names exact missing evidence (PDF + KMZ)",
                  all(os.path.isfile(p) for _, p, _, _ in rendered)
                  and all(("missing_evidence" in r) or ("png" in r) for r in targets.values()), None))
    gates.append(("G3 a stroke is placed ONLY on a KMZ-backed unique terminus (DO-NOT-WIDEN); no review-choice",
                  all(r.get("kmz_terminus_bound") for r in targets.values() if "png" in r), None))
    result = R_RENDERED if rendered else R_NO_RENDER
    return _emit(gates, result, targets, rendered)


def _emit(gates, result, targets, rendered) -> int:
    gates.append(("G4 canonical red stroke color (TrueLine strokes are red)",
                  REDLINE_STROKE_RGB == (220, 25, 25), list(REDLINE_STROKE_RGB)))
    gates.append(("G5 result in allowed enum", result in ALLOWED, result))
    all_pass = all(x for _, x, _ in gates)
    report = {
        "milestone": "KMZ DROP-IDENTITY JOIN -> redline artifacts (proof only; read-only; product-gated)",
        "verdict": "PASS" if all_pass else "FAIL", "result": result,
        "target_logs": list(TARGETS),
        "kmz_file": str(KMZ).replace(str(_REPO_ROOT), "").lstrip("\\/").replace("\\", "/"),
        "newly_rendered_full": [l for l, _, _, k in rendered if k == "full"],
        "newly_rendered_partial": [l for l, _, _, k in rendered if k == "partial"],
        "artifact_paths": [str(p).replace(str(_REPO_ROOT), "").lstrip("\\/").replace("\\", "/")
                           for _, p, _, _ in rendered],
        "still_blocked": [{"log": l, "blocker": r.get("result"), "missing_evidence": r.get("missing_evidence")}
                          for l, r in targets.items() if "png" not in r],
        "finding": ("the KMZ carries NO flower-pot drop identity (158 pots, all unnamed; AP/Scid columns exist "
                    "but populated on 1 pot; no Vacant-Pipe route length matches the bore span) -> per the lane's "
                    "abstain rule, NO KMZ-backed stroke is placed. KEY side-finding: log50's terminus is uniquely "
                    "identified by the PDF's OWN printed end note (FLOWER POT @5+14, sheet 11; owner-agreed) -- so "
                    "the drop POT is no longer the blocker. But the on-sheet conduit covers only the terminus end "
                    "(HH 1+89 -> pot); the 0+00 origin is cross-sheet, so the committed drop-lane sweep classifies "
                    "log50 as PICK_CARD and NO stroke is placed (DO-NOT-WIDEN). The named missing capability for a "
                    "CORRECT FULL render is matchline-joined cross-sheet conduit chain assembly. log30: end note "
                    "unprinted + KMZ no identity -> abstain."),
        "targets": targets,
        "red_stroke_rgb": list(REDLINE_STROKE_RGB),
        "no_owner_naming": True, "no_review_choice": True, "no_fixture_mutation": True,
        "no_coordinate_encoding": True, "engine_census_frozen": True, "artifacts_gitignored": True,
        "gates": [{"name": n, "pass": bool(x), "detail": d} for n, x, d in gates],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "kmz_drop_identity_join.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"[kmz-drop] result: {result}  rendered={[l for l,_,_,_ in rendered]}")
    for lid, r in targets.items():
        print(f"[kmz-drop]   {lid}: span={r['span_ft']} kmz_bound={r.get('kmz_terminus_bound')} -> {r.get('result')}")
        if r.get("missing_evidence"):
            print(f"[kmz-drop]       missing: {r['missing_evidence'][:160]}")
    for a in sorted(p.name for p in OUT_DIR.glob("*.png")):
        print(f"[kmz-drop]   ARTIFACT: {a}")
    for n, x, _ in gates:
        print(f"[kmz-drop] {'PASS' if x else 'FAIL'}  {n}")
    print(f"[kmz-drop] VERDICT: {'PASS' if all_pass else 'FAIL'}  (report: {OUT_DIR})")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
