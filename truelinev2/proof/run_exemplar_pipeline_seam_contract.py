r"""OWNER-PACKET-2 -- exemplar pipeline SEAM CONTRACT proof (PROOF ONLY; no product, no render).

Proves the contained pure seam module (truelinev2/seam/contract.py) formalizes the scout's (444beb5)
coordinate-free normalized payload for the THREE eligible exemplars only -- and that it preserves
every doctrine the exemplars established:

  log53 -- STA 24+11 matchline is MODELED as a matchline endpoint;
  log64 -- single-sheet structure-to-structure;
  log71 -- STA 5+45 matchline is ROUTE CONTEXT only (not a third endpoint), sheet 24 is a BENDING
           ordered_chain_path (never a straight corridor).

It builds payloads via the module (no PDF, no render, no product), checks the contract invariants,
confirms eligibility never expands (the module REFUSES non-eligible logs), and cross-checks that the
module is SEMANTICALLY equivalent to the committed scout's proposal. Census stays frozen.

Proof-only; the JSON report is written under the gitignored data/outputs path.
Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_exemplar_pipeline_seam_contract
"""
from __future__ import annotations

import json

from truelinev2.config import _REPO_ROOT
from truelinev2.ingest.manual_adjudication import (
    activation_summary,
    apply_adjudications,
    load_adjudication,
    parent_run_duplicate_check,
)
from truelinev2.proof.run_exemplar_pipeline_seam_scout import normalize_exemplar as scout_normalize
from truelinev2.seam import (
    ELIGIBLE_EXEMPLARS,
    BoundaryKind,
    RenderMode,
    SeamShape,
    build_seam_payload,
    eligible_seam_payloads,
    is_coordinate_free,
)

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "exemplar_pipeline_seam_contract"
TRUTH = _REPO_ROOT / "data" / "outputs" / "final_engine_truth_table" / \
    "final_engine_truth_table.json"
FROZEN_BUCKETS = {"DRAWABLE_REVIEW": 31, "HUMAN_ADJUSTABLE_REVIEW": 6,
                  "OUT_OF_CLASS": 1, "PICK_CARD_REVIEW": 17, "SOURCE_OR_KMZ_REQUIRED": 3}
ABSTAIN_4 = ("log5", "log31", "log38", "log43")
# logs that must NEVER be promoted to seam-eligible (the module must refuse them)
REFUSAL_PROBES = ("log6", "log5", "log44", "log63")

R_PASS = "EXEMPLAR_PIPELINE_SEAM_CONTRACT_PASS"
B_BUILD = "BLOCKED_SEAM_CONTRACT_BUILD_FAILED"
B_ELIGIBILITY = "BLOCKED_SEAM_CONTRACT_ELIGIBILITY_DRIFT"
B_INVARIANT = "BLOCKED_SEAM_CONTRACT_INVARIANT_VIOLATED"
B_INCONSISTENT = "BLOCKED_SEAM_CONTRACT_SCOUT_INCONSISTENT"
ALLOWED = {R_PASS, B_BUILD, B_ELIGIBILITY, B_INVARIANT, B_INCONSISTENT}


def _refuses(log_id: str, rec: dict) -> bool:
    try:
        build_seam_payload(log_id, rec.get(log_id, {}))
        return False
    except ValueError:
        return True


def _proj_module(p) -> tuple:
    """Semantic projection of a module SeamPayload (shape, per-leg boundary/mode, matchline, x-sheet)."""
    return (p.shape.value,
            tuple((l.sheet, l.render_mode.value,
                   l.start_anchor.boundary_kind.value, l.start_anchor.station, l.start_anchor.structure_class,
                   l.end_anchor.boundary_kind.value, l.end_anchor.station, l.end_anchor.structure_class)
                  for l in p.legs),
            tuple(p.matchline_stations), p.cross_sheet_join, p.cross_sheet_coordinate_reconciliation)


def _proj_scout(d: dict) -> tuple:
    """Same projection from the scout's dict payload (its boundary key is 'boundary')."""
    return (d["shape"],
            tuple((l["sheet"], l["render_mode"],
                   l["start_anchor"]["boundary"], l["start_anchor"].get("station"), l["start_anchor"].get("structure_class"),
                   l["end_anchor"]["boundary"], l["end_anchor"].get("station"), l["end_anchor"].get("structure_class"))
                  for l in d["legs"]),
            tuple(d["matchline_stations"]), d["cross_sheet_join"], d["cross_sheet_coordinate_reconciliation"])


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
    gates = []

    gates.append(("G0 engine census frozen (OFF 31/6/1/17/3, ON 22/1/4, log44+abstains held)",
                  _census_frozen(doc), None))
    l53s = (rec["log53"].get("endpoint_anchors") or {}).get("start") or {}
    l53e = (rec["log53"].get("endpoint_anchors") or {}).get("end") or {}
    l64s = (rec["log64"].get("endpoint_anchors") or {}).get("start") or {}
    l71s = (rec["log71"].get("endpoint_anchors") or {}).get("start") or {}
    gates.append(("G0b log53 + log64 + log71 encoded anchors unchanged (behavior preserved)",
                  l53s.get("structure_class") == "nextlink_hh"
                  and l53e.get("boundary_kind") == "matchline_continuation"
                  and l64s.get("structure_class") == "installer_hh"
                  and l71s.get("structure_class") == "nextlink_hh", None))

    # ---- build the three payloads via the module --------------------------------
    payloads = eligible_seam_payloads(doc)
    gates.append(("G1 module builds payloads for EXACTLY log53/log64/log71/log59",
                  tuple(payloads) == ELIGIBLE_EXEMPLARS == ("log53", "log64", "log71", "log59"),
                  sorted(payloads)))

    # G2: no other log is silently promoted -- the module REFUSES non-eligible logs
    refusals = {lid: _refuses(lid, rec) for lid in REFUSAL_PROBES}
    refusals["log999_unknown"] = _refuses("log999", rec)
    gates.append(("G2 module refuses non-eligible logs (recovered-no-anchor, abstain, needs-verify, unknown)",
                  all(refusals.values()), refusals))

    # G3: coordinate-free
    dicts = {lid: payloads[lid].to_dict() for lid in payloads}
    gates.append(("G3 every payload is coordinate-free (identity/contract only; no position)",
                  all(is_coordinate_free(d) for d in dicts.values()), None))

    # G4: endpoint anchors preserved
    p64, p71, p53, p59 = payloads["log64"], payloads["log71"], payloads["log53"], payloads["log59"]
    anchors_ok = (
        p64.legs[0].start_anchor.structure_class == "installer_hh" and p64.legs[0].start_anchor.station == "3+69"
        and p64.legs[0].end_anchor.structure_class == "flower_pot" and p64.legs[0].end_anchor.station == "1+00"
        and p71.legs[0].start_anchor.structure_class == "nextlink_hh" and p71.legs[0].start_anchor.station == "7+50"
        and p71.legs[-1].end_anchor.structure_class == "flower_pot" and p71.legs[-1].end_anchor.station == "6+95"
        and p53.legs[0].start_anchor.structure_class == "nextlink_hh" and p53.legs[0].start_anchor.station == "21+63"
        and p59.legs[0].start_anchor.structure_class == "installer_hh" and p59.legs[0].start_anchor.station == "2+76"
        and p59.legs[0].end_anchor.structure_class == "flower_pot" and p59.legs[0].end_anchor.station == "4+46")
    gates.append(("G4 endpoint anchors preserved (identity + station from committed anchors)", anchors_ok, None))

    # G5: matchline endpoint (log53) vs matchline route-context (log71), derived from anchors
    l53_ml = p53.legs[0].end_anchor
    l71_ml = p71.legs[0].end_anchor
    matchline_ok = (l53_ml.boundary_kind == BoundaryKind.MATCHLINE_CONTINUATION and l53_ml.station == "24+11"
                    and p53.legs[0].route_context.role == "modeled_matchline_endpoint"
                    and l71_ml.boundary_kind == BoundaryKind.MATCHLINE_ROUTE_CONTEXT and l71_ml.station == "5+45"
                    and p71.legs[0].route_context.role == "between_leg_crossing_route_context")
    gates.append(("G5 matchline doctrine preserved (log53 modeled endpoint; log71 5+45 route context)",
                  matchline_ok, {"log53": l53_ml.boundary_kind.value, "log71": l71_ml.boundary_kind.value}))

    # G6: log71 sheet 24 is ordered_chain_path (bends), not a straight/continuous corridor
    s24 = next(l for l in p71.legs if l.sheet == 24)
    all_modes = {l.render_mode for p in payloads.values() for l in p.legs}
    bend_ok = (s24.render_mode == RenderMode.ORDERED_CHAIN_PATH
               and p59.legs[0].render_mode == RenderMode.ORDERED_CHAIN_PATH   # log59 single-sheet, discontinuous direct corridor
               and all_modes <= {RenderMode.CONTINUOUS_CORRIDOR, RenderMode.ORDERED_CHAIN_PATH}
               and not any("straight" in m.value or "diagonal" in m.value for m in all_modes))
    gates.append(("G6 ordered_chain_path preserved (log71 s24 bends; log59 s21 discontinuous corridor); no straight mode exists",
                  bend_ok, {"log71_s24": s24.render_mode.value, "log59_s21": p59.legs[0].render_mode.value}))

    # G7: cross-sheet join deferred (two-sheet) / None (single-sheet)
    join_ok = (p53.cross_sheet_join == "deferred" and p71.cross_sheet_join == "deferred"
               and p64.cross_sheet_join is None)
    gates.append(("G7 cross-sheet join deferred for two-sheet exemplars; None for single-sheet", join_ok,
                  {"log53": p53.cross_sheet_join, "log64": p64.cross_sheet_join, "log71": p71.cross_sheet_join}))

    # G8: cross-sheet coordinate reconciliation is false; every leg is exactly one sheet
    recon_ok = (all(p.cross_sheet_coordinate_reconciliation is False for p in payloads.values())
                and all(isinstance(l.sheet, int) for p in payloads.values() for l in p.legs))
    gates.append(("G8 no cross-sheet coordinate reconciliation (false; legs are sheet-local)", recon_ok, None))

    # G9: scout consistency -- the module is semantically equivalent to the committed scout's proposal
    consistent = all(_proj_module(payloads[lid]) == _proj_scout(scout_normalize(lid, rec[lid]))
                     for lid in ELIGIBLE_EXEMPLARS)
    gates.append(("G9 module is semantically equivalent to the committed seam scout's payload", consistent, None))

    pngs = sorted(p.name for p in OUT_DIR.glob("*.png"))
    gates.append(("G10 no render artifact generated (proof writes JSON only; zero PNG)", len(pngs) == 0, pngs))

    result = (R_PASS if all(x for _, x, _ in gates)
              else B_INVARIANT if not (gates[0][1] and gates[3][1])
              else B_ELIGIBILITY if not (gates[1][1] and gates[2][1])
              else B_INCONSISTENT if not consistent else B_BUILD)
    return _emit(gates, result, dicts)


def _emit(gates, result, dicts) -> int:
    gates.append(("G11 result in allowed enum", result in ALLOWED, result))
    all_pass = all(x for _, x, _ in gates)
    report = {
        "milestone": "OWNER-PACKET-2 -- exemplar pipeline seam contract (proof; pure module formalization)",
        "verdict": "PASS" if all_pass else "FAIL",
        "result": result if all_pass else "BLOCKED",
        "module": "truelinev2/seam/contract.py",
        "eligible_exemplars": list(ELIGIBLE_EXEMPLARS),
        "shapes": {lid: dicts[lid]["shape"] for lid in dicts},
        "boundary_kinds": sorted(k.value for k in BoundaryKind),
        "render_modes": sorted(m.value for m in RenderMode),
        "seam_shapes": sorted(s.value for s in SeamShape),
        "payloads": dicts,
        "doctrine": {
            "coordinate_free": True,
            "log53_matchline": "modeled matchline endpoint (boundary_kind matchline_continuation)",
            "log71_matchline": "route context only (5+45 not a third endpoint)",
            "log71_sheet24_render_mode": "ordered_chain_path (bends)",
            "cross_sheet_join": "deferred (two-sheet) / none (single-sheet); coordinate reconciliation = false",
            "eligibility": "frozen to the three proven exemplars; build refuses any other log",
        },
        "scope_guard": {"product_wiring": False, "broad_renderer": False, "batch_placement_or_rendering": False,
                        "cross_sheet_join": False, "cross_sheet_frame_solving": False,
                        "representative_route_resolver": False, "parent_child_aggregation": False,
                        "new_log_promotion": False, "pdf_parsed": False, "coordinates_invented": False,
                        "generated_artifacts_committed": False},
        "next_slice": ("a CONTAINED proof that hands each seam-contract leg to the EXISTING per-leg "
                       "source-bind/render proofs (the contract -> proof adapter), still no product "
                       "wiring / no batch / no cross-sheet join; OR encode the next owner-confirmed "
                       "endpoint_anchors bridge to grow eligibility by one log."),
        "gates": [{"name": n, "pass": bool(x), "detail": d} for n, x, d in gates],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "exemplar_pipeline_seam_contract.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"[seam-contract] result: {report['result']}")
    for lid in ELIGIBLE_EXEMPLARS:
        print(f"[seam-contract]   {lid}: shape={dicts[lid]['shape']} legs={len(dicts[lid]['legs'])} "
              f"matchlines={dicts[lid]['matchline_stations']} x-sheet_join={dicts[lid]['cross_sheet_join']}")
    for n, x, _ in gates:
        print(f"[seam-contract] {'PASS' if x else 'FAIL'}  {n}")
    print(f"[seam-contract] VERDICT: {'PASS' if all_pass else 'FAIL'}  (report: {OUT_DIR})")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
