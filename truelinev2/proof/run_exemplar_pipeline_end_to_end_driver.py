r"""OWNER-PACKET-2 -- exemplar pipeline END-TO-END driver proof (PROOF ONLY; not product/runtime).

Proves the typed seam CONTRACT (truelinev2/seam/contract.py) + proof ADAPTER (truelinev2/seam/
proof_adapter.py) can DRIVE the existing named proof families end-to-end for EXACTLY the three
eligible exemplars -- log53, log64, log71 -- and that each named source-bind + render proof returns
PASS. It is a contained driver, NOT a general batch runner: it invokes proofs only for the three
fixed exemplars whose modules the adapter dispatch names; it adds no product wiring, no render queue,
no Match Review, no batch over the dataset, and expands no eligibility.

Each named proof is invoked in its OWN process exactly as it is normally run
(``python -m truelinev2.proof.<module>``); the process exit code IS the proof's PASS/FAIL. Render
proofs emit their PNG/JSON under gitignored data/outputs paths (never tracked). The driver's own
report is JSON only, also under the gitignored data/outputs path.

Proof-only.
Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_exemplar_pipeline_end_to_end_driver
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

from truelinev2.config import _REPO_ROOT
from truelinev2.ingest.manual_adjudication import (
    activation_summary,
    apply_adjudications,
    load_adjudication,
    parent_run_duplicate_check,
)
from truelinev2.seam import (
    ELIGIBLE_EXEMPLARS,
    PROOF_FAMILY,
    build_dispatch,
    build_seam_payload,
)

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "exemplar_pipeline_end_to_end_driver"
TRUTH = _REPO_ROOT / "data" / "outputs" / "final_engine_truth_table" / \
    "final_engine_truth_table.json"
FROZEN_BUCKETS = {"DRAWABLE_REVIEW": 31, "HUMAN_ADJUSTABLE_REVIEW": 6,
                  "OUT_OF_CLASS": 1, "PICK_CARD_REVIEW": 17, "SOURCE_OR_KMZ_REQUIRED": 3}
ABSTAIN_4 = ("log5", "log31", "log38", "log43")
REFUSAL_PROBES = ("log6", "log63", "log5", "log44")
PROOF_TIMEOUT_S = 600

R_PASS = "EXEMPLAR_PIPELINE_END_TO_END_DRIVER_PASS"
B_PROOF_FAIL = "BLOCKED_DRIVER_PROOF_FAMILY_FAILED"
B_ELIGIBILITY = "BLOCKED_DRIVER_ELIGIBILITY_DRIFT"
B_DOCTRINE = "BLOCKED_DRIVER_DOCTRINE_VIOLATED"
B_INVARIANT = "BLOCKED_DRIVER_INVARIANT_VIOLATED"
ALLOWED = {R_PASS, B_PROOF_FAIL, B_ELIGIBILITY, B_DOCTRINE, B_INVARIANT}


def drive_one(log_id: str, record: dict) -> dict:
    """Pure drive PLAN for one eligible exemplar: consume the canonical contract payload + adapter
    dispatch and collect the named existing source-bind/render proof modules + the preserved doctrine.
    No proof is executed here. Refuses any non-eligible log (inherited from the contract/adapter)."""
    payload = build_seam_payload(log_id, record)      # canonical seam contract
    dispatch = build_dispatch(log_id, record)         # canonical proof adapter (refuses non-eligible)
    source_bind_modules = tuple(sorted({m for leg in dispatch.legs
                                        for m in leg.expected_source_bind_proofs}))
    render_modules = sorted({leg.expected_render_proof for leg in dispatch.legs})
    if len(render_modules) != 1:
        raise ValueError(f"{log_id}: expected exactly one render proof family, got {render_modules}")
    matchline_leg = next((leg for leg in dispatch.legs if leg.route_context_role), None)
    return {
        "bore_id": log_id,
        "shape": dispatch.shape,
        "contract_shape": payload.shape.value,
        "source_bind_modules": source_bind_modules,
        "render_module": render_modules[0],
        "doctrine": {
            "matchline_role": matchline_leg.route_context_role if matchline_leg else None,
            "matchline_station": matchline_leg.matchline_station if matchline_leg else None,
            "render_modes": {leg.sheet: leg.render_mode for leg in dispatch.legs},
            "cross_sheet_join": dispatch.cross_sheet_join,
            "coordinate_reconciliation": dispatch.cross_sheet_coordinate_reconciliation,
        },
    }


def build_drive_plan(doc: dict) -> dict:
    """Drive plan for EXACTLY the three eligible exemplars (never any other log)."""
    rec = {r["log_id"]: r for r in doc["logs"]}
    return {lid: drive_one(lid, rec[lid]) for lid in ELIGIBLE_EXEMPLARS}


def invoke_proof_module(modname: str, timeout: int = PROOF_TIMEOUT_S) -> int:
    """Invoke a named proof in its OWN process (python -m <modname>) exactly as it is normally run;
    the exit code is the proof's PASS(0)/FAIL(non-zero). Side-effectful (the proof may emit artifacts
    under gitignored data/outputs). Returns the exit code (or 124 on timeout)."""
    try:
        proc = subprocess.run(
            [sys.executable, "-m", modname],
            cwd=str(_REPO_ROOT),
            env={**os.environ, "PYTHONPATH": str(_REPO_ROOT)},
            capture_output=True, text=True, timeout=timeout)
        return proc.returncode
    except subprocess.TimeoutExpired:
        return 124


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


def _refuses(log_id: str, rec: dict) -> bool:
    try:
        drive_one(log_id, rec.get(log_id, {}))
        return False
    except ValueError:
        return True


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for stale in OUT_DIR.glob("*.png"):
        stale.unlink()

    doc = load_adjudication()
    rec = {r["log_id"]: r for r in doc["logs"]}
    gates = []

    gates.append(("G0 engine census frozen (OFF 31/6/1/17/3, ON 22/1/4, log44+abstains held)",
                  _census_frozen(doc), None))

    plan = build_drive_plan(doc)

    # G1: driver consumes the canonical CONTRACT (per-bore shape equals the contract payload's shape)
    g1 = all(plan[lid]["shape"] == plan[lid]["contract_shape"] == build_seam_payload(lid, rec[lid]).shape.value
             for lid in ELIGIBLE_EXEMPLARS)
    gates.append(("G1 driver consumes canonical seam contract payloads (shape sourced from contract)", g1, None))

    # G2: driver consumes the canonical ADAPTER dispatch (the modules it will run ARE the adapter's
    # registry for each exemplar -- not an independent hardcoded list)
    g2 = all(set(plan[lid]["source_bind_modules"]) == set(PROOF_FAMILY[lid]["source_bind_proofs"])
             and plan[lid]["render_module"] == PROOF_FAMILY[lid]["render_proof"]
             for lid in ELIGIBLE_EXEMPLARS)
    gates.append(("G2 driver consumes canonical adapter dispatch (modules == adapter registry)", g2, None))

    gates.append(("G3 driver runs EXACTLY log53/log64/log71",
                  tuple(plan) == ELIGIBLE_EXEMPLARS == ("log53", "log64", "log71"), sorted(plan)))

    refusals = {lid: _refuses(lid, rec) for lid in REFUSAL_PROBES}
    refusals["log999_unknown"] = _refuses("log999", rec)
    gates.append(("G4 driver refuses all non-eligible logs (no silent promotion)",
                  all(refusals.values()), refusals))

    # G5/G6: correct source-bind + render families per exemplar (names match the expected mapping)
    expected = {
        "log53": {"src": {"truelinev2.proof.run_log53_matchline_boundary_slice",
                          "truelinev2.proof.run_log53_nextlink_hh_bindability_slice"},
                  "render": "truelinev2.proof.run_log53_render_artifact_slice"},
        "log64": {"src": {"truelinev2.proof.run_log64_sheet21_source_bind_slice"},
                  "render": "truelinev2.proof.run_log64_render_artifact_slice"},
        "log71": {"src": {"truelinev2.proof.run_log71_two_leg_source_bind_slice"},
                  "render": "truelinev2.proof.run_log71_render_artifact_slice"},
    }
    g5 = all(set(plan[lid]["source_bind_modules"]) == expected[lid]["src"] for lid in ELIGIBLE_EXEMPLARS)
    g6 = all(plan[lid]["render_module"] == expected[lid]["render"]
             and plan[lid]["render_module"].endswith("_render_artifact_slice") for lid in ELIGIBLE_EXEMPLARS)
    gates.append(("G5 correct source-bind proof family per exemplar", g5, None))
    gates.append(("G6 correct render proof family per exemplar (render-named)", g6, None))

    # ---- INVOKE every named proof in its own process; exit code == PASS/FAIL ----
    results = {}
    for lid in ELIGIBLE_EXEMPLARS:
        for mod in (*plan[lid]["source_bind_modules"], plan[lid]["render_module"]):
            if mod not in results:
                results[mod] = invoke_proof_module(mod)
    all_pass = all(rc == 0 for rc in results.values())
    gates.append(("G7 every invoked source-bind + render proof returns PASS (exit 0)",
                  all_pass, {m: rc for m, rc in sorted(results.items())}))

    # ---- doctrine preserved through the driver ---------------------------------
    d53, d64, d71 = plan["log53"]["doctrine"], plan["log64"]["doctrine"], plan["log71"]["doctrine"]
    gates.append(("G8 log53 matchline-endpoint doctrine preserved (STA 24+11 modeled endpoint)",
                  plan["log53"]["shape"] == "two_sheet_matchline_endpoint"
                  and d53["matchline_role"] == "modeled_matchline_endpoint"
                  and d53["matchline_station"] == "24+11", d53["matchline_station"]))
    gates.append(("G9 log71 route-context doctrine preserved (STA 5+45 route context, not endpoint)",
                  plan["log71"]["shape"] == "two_sheet_structure_to_structure_route_context"
                  and d71["matchline_role"] == "between_leg_crossing_route_context"
                  and d71["matchline_station"] == "5+45", d71["matchline_station"]))
    gates.append(("G10 log71 sheet 24 = ordered_chain_path; sheet 23 = continuous_corridor",
                  d71["render_modes"].get(24) == "ordered_chain_path"
                  and d71["render_modes"].get(23) == "continuous_corridor", d71["render_modes"]))
    gates.append(("G11 cross-sheet join deferred (two-sheet) / None (single-sheet)",
                  d53["cross_sheet_join"] == "deferred" and d71["cross_sheet_join"] == "deferred"
                  and d64["cross_sheet_join"] is None, None))
    gates.append(("G12 cross-sheet coordinate reconciliation false for every exemplar",
                  all(plan[lid]["doctrine"]["coordinate_reconciliation"] is False for lid in ELIGIBLE_EXEMPLARS),
                  None))
    gates.append(("G13 no new eligibility introduced (driver set == frozen 3; non-eligible refused)",
                  set(plan) == set(ELIGIBLE_EXEMPLARS) and all(refusals.values()), None))

    pngs = sorted(p.name for p in OUT_DIR.glob("*.png"))
    gates.append(("G14 driver emits no artifact of its own (JSON report only; zero PNG in its dir)",
                  len(pngs) == 0, pngs))

    result = (R_PASS if all(x for _, x, _ in gates)
              else B_INVARIANT if not gates[0][1]
              else B_ELIGIBILITY if not (gates[5][1] and refusals and all(refusals.values()))
              else B_PROOF_FAIL if not all_pass else B_DOCTRINE)
    return _emit(gates, result, plan, results)


def _emit(gates, result, plan, results) -> int:
    gates.append(("G15 result in allowed enum", result in ALLOWED, result))
    all_pass = all(x for _, x, _ in gates)
    driver_result = [
        {"bore_id": lid, "shape": plan[lid]["shape"],
         "source_bind_proofs": [{"module": m, "result": "PASS" if results.get(m) == 0 else f"FAIL({results.get(m)})"}
                                for m in plan[lid]["source_bind_modules"]],
         "render_proofs": [{"module": plan[lid]["render_module"],
                            "result": "PASS" if results.get(plan[lid]["render_module"]) == 0
                            else f"FAIL({results.get(plan[lid]['render_module'])})"}],
         "doctrine_checks": plan[lid]["doctrine"]}
        for lid in ELIGIBLE_EXEMPLARS]
    report = {
        "milestone": "OWNER-PACKET-2 -- exemplar pipeline end-to-end driver (proof; seam contract+adapter drive proven proofs)",
        "verdict": "PASS" if all_pass else "FAIL",
        "result": result if all_pass else "BLOCKED",
        "driver": "truelinev2/proof/run_exemplar_pipeline_end_to_end_driver.py",
        "eligible_exemplars": list(ELIGIBLE_EXEMPLARS),
        "driver_result": driver_result,
        "invoked_proofs": {m: ("PASS" if rc == 0 else f"FAIL({rc})") for m, rc in sorted(results.items())},
        "doctrine": {
            "log53_matchline": "modeled matchline endpoint (24+11)",
            "log71_matchline": "route context only (5+45); never a third endpoint",
            "log71_sheet24_render_mode": "ordered_chain_path (not downgraded)",
            "cross_sheet_join": "deferred (two-sheet) / none (single-sheet); reconciliation = false",
            "eligibility": "frozen to the three exemplars; driver refuses any other log",
        },
        "scope_guard": {"product_wiring": False, "broad_renderer": False, "render_queue": False,
                        "match_review_wiring": False, "batch_over_dataset": False,
                        "eligibility_expansion": False, "cross_sheet_join": False,
                        "cross_sheet_frame_solving": False, "representative_route_resolver": False,
                        "parent_child_aggregation": False, "new_log_promotion": False,
                        "fixed_exemplars_only": list(ELIGIBLE_EXEMPLARS)},
        "next_slice": ("if accepted, GROW eligibility by exactly one log: encode the next owner-confirmed "
                       "endpoint_anchors bridge from the 19 pending logs, then add it to the contract's "
                       "eligible set + adapter registry + this driver -- still no product wiring / no "
                       "batch over the dataset / no cross-sheet join."),
        "gates": [{"name": n, "pass": bool(x), "detail": d} for n, x, d in gates],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "exemplar_pipeline_end_to_end_driver.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"[e2e-driver] result: {report['result']}")
    for lid in ELIGIBLE_EXEMPLARS:
        print(f"[e2e-driver]   {lid}: shape={plan[lid]['shape']} "
              f"source_bind={[results.get(m) for m in plan[lid]['source_bind_modules']]} "
              f"render={results.get(plan[lid]['render_module'])} (0=PASS)")
    for n, x, _ in gates:
        print(f"[e2e-driver] {'PASS' if x else 'FAIL'}  {n}")
    print(f"[e2e-driver] VERDICT: {'PASS' if all_pass else 'FAIL'}  (report: {OUT_DIR})")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
