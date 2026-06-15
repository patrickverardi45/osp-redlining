r"""OWNER-PACKET-2 -- seam-eligible BLANKET proof (PROOF ONLY; not product/runtime).

The first "blanket lane" proof: it shows the v2 seam can blanket-process EVERY currently seam-eligible
log -- and ONLY currently eligible logs -- in one contained pass, WITHOUT becoming product/runtime
wiring. The blanket covers EXACTLY the four proven exemplars:

  log53  log64  log71  log59

For each eligible log it builds the canonical coordinate-free seam payload (truelinev2/seam/contract.py)
and the proof-dispatch (truelinev2/seam/proof_adapter.py), then invokes that log's named source-bind +
render proof families in their OWN processes (reusing the end-to-end driver's invoke_proof_module) and
checks each returns PASS. Every NON-eligible cohort log is refused by BOTH the contract and the adapter
with a named reason (from the honest seam classifier) -- nothing is silently promoted.

IMPORTANT DOCTRINE: this blanket covers ONLY seam-eligible logs. It is NOT a claim that all production
logs can draw -- the other cohort logs stay refused/review (abstain / needs-source-verification / no
owner-reviewed endpoint_anchors bridge). It adds NO product wiring, NO render queue, NO Match Review,
NO runtime batch over the dataset, and grows NO eligibility. Render proofs emit their PNG/JSON under
their OWN gitignored data/outputs paths (never tracked); this blanket proof draws nothing of its own.

Proof-only; the JSON report is written under the gitignored data/outputs path.
Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_seam_eligible_blanket_proof
"""
from __future__ import annotations

import importlib.util
import json

from truelinev2.config import _REPO_ROOT
from truelinev2.ingest.manual_adjudication import (
    activation_summary,
    apply_adjudications,
    load_adjudication,
    parent_run_duplicate_check,
)
from truelinev2.proof.run_exemplar_pipeline_end_to_end_driver import invoke_proof_module
from truelinev2.proof.run_exemplar_pipeline_seam_scout import classify_record as seam_classify
from truelinev2.seam import ELIGIBLE_EXEMPLARS, build_dispatch, build_seam_payload

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "seam_eligible_blanket_proof"
TRUTH = _REPO_ROOT / "data" / "outputs" / "final_engine_truth_table" / \
    "final_engine_truth_table.json"
FROZEN_BUCKETS = {"DRAWABLE_REVIEW": 31, "HUMAN_ADJUSTABLE_REVIEW": 6,
                  "OUT_OF_CLASS": 1, "PICK_CARD_REVIEW": 17, "SOURCE_OR_KMZ_REQUIRED": 3}
ABSTAIN_4 = ("log5", "log31", "log38", "log43")
EXPECTED_ELIGIBLE = ("log53", "log64", "log71", "log59")
UNKNOWN_PROBE = "log999_unknown"

R_PASS = "SEAM_ELIGIBLE_BLANKET_PASS"
B_ELIGIBILITY = "BLOCKED_BLANKET_ELIGIBILITY_DRIFT"
B_BUILD = "BLOCKED_BLANKET_BUILD_FAILED"
B_PROOF_FAIL = "BLOCKED_BLANKET_PROOF_FAMILY_FAILED"
B_REFUSAL = "BLOCKED_BLANKET_NON_ELIGIBLE_NOT_REFUSED"
B_INVARIANT = "BLOCKED_BLANKET_INVARIANT_VIOLATED"
ALLOWED = {R_PASS, B_ELIGIBILITY, B_BUILD, B_PROOF_FAIL, B_REFUSAL, B_INVARIANT}


def _refuses_payload(log_id: str, rec: dict) -> bool:
    try:
        build_seam_payload(log_id, rec.get(log_id, {}))
        return False
    except ValueError:
        return True


def _refuses_dispatch(log_id: str, rec: dict) -> bool:
    try:
        build_dispatch(log_id, rec.get(log_id, {}))
        return False
    except ValueError:
        return True


def _module_exists(modname: str) -> bool:
    """Read-only existence check (locates the module; does NOT import or execute it)."""
    try:
        return importlib.util.find_spec(modname) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def build_blanket_plan(doc: dict) -> dict:
    """Pure blanket PLAN over EXACTLY the seam-eligible set (no invocation). Per eligible log: its
    canonical seam payload (shape + render mode) + adapter dispatch (source-bind/render proof families).
    Per non-eligible cohort log: the honest refusal reason + that BOTH contract and adapter refuse it.
    Refuses any log outside ELIGIBLE_EXEMPLARS (inherited from the contract/adapter) -- no promotion."""
    rec = {r["log_id"]: r for r in doc["logs"]}
    eligible = []
    for lid in ELIGIBLE_EXEMPLARS:
        payload = build_seam_payload(lid, rec[lid])     # canonical seam contract
        dispatch = build_dispatch(lid, rec[lid])        # canonical proof adapter
        source_bind = tuple(sorted({m for leg in dispatch.legs
                                    for m in leg.expected_source_bind_proofs}))
        render = tuple(sorted({leg.expected_render_proof for leg in dispatch.legs}))
        eligible.append({
            "bore_id": lid,
            "seam_shape": payload.shape.value,
            "render_mode": sorted({leg.render_mode.value for leg in payload.legs}),
            "source_bind_proofs": source_bind,
            "render_proofs": render,
            "proof_family": dispatch.legs[0].expected_proof_family,
        })
    refused = []
    for r in doc["logs"]:
        lid = r["log_id"]
        if lid in ELIGIBLE_EXEMPLARS:
            continue
        ok, reason, cats = seam_classify(r)
        refused.append({
            "bore_id": lid, "reason": reason, "categories": cats,
            "contract_refuses": _refuses_payload(lid, rec),
            "adapter_refuses": _refuses_dispatch(lid, rec),
        })
    return {"eligible": eligible, "refused": refused}


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

    gates.append(("G1 seam eligible set is EXACTLY log53/log64/log71/log59",
                  tuple(ELIGIBLE_EXEMPLARS) == EXPECTED_ELIGIBLE, list(ELIGIBLE_EXEMPLARS)))

    plan = build_blanket_plan(doc)
    eligible = plan["eligible"]
    refused = plan["refused"]

    gates.append(("G2 blanket builds a seam payload for EVERY eligible log (4/4; with seam shape)",
                  tuple(e["bore_id"] for e in eligible) == EXPECTED_ELIGIBLE
                  and all(e["seam_shape"] for e in eligible), [e["bore_id"] for e in eligible]))

    gates.append(("G3 blanket builds an adapter dispatch for EVERY eligible log (4/4; proof family mapped)",
                  all(e["proof_family"] and e["source_bind_proofs"] and e["render_proofs"]
                      for e in eligible), {e["bore_id"]: e["proof_family"] for e in eligible}))

    # G4/G5: each eligible log's named source-bind + render proof modules resolve (read-only find_spec)
    src_resolved = all(_module_exists(m) for e in eligible for m in e["source_bind_proofs"])
    render_resolved = all(_module_exists(m) for e in eligible for m in e["render_proofs"])
    gates.append(("G4 each eligible log's source-bind proof family is named + resolves",
                  src_resolved, None))
    gates.append(("G5 each eligible log's render proof family is named + resolves (render-named)",
                  render_resolved and all(m.endswith("_render_artifact_slice")
                                          for e in eligible for m in e["render_proofs"]), None))

    # ---- INVOKE every eligible log's source-bind + render proof in its own process ----
    results = {}
    for e in eligible:
        for mod in (*e["source_bind_proofs"], *e["render_proofs"]):
            if mod not in results:
                results[mod] = invoke_proof_module(mod)
    for e in eligible:
        e["result"] = ("PASS" if all(results[m] == 0
                                     for m in (*e["source_bind_proofs"], *e["render_proofs"]))
                       else "FAIL")
    all_pass = all(rc == 0 for rc in results.values())
    gates.append(("G6 every invoked source-bind + render proof returns PASS (exit 0)",
                  all_pass and all(e["result"] == "PASS" for e in eligible),
                  {m: rc for m, rc in sorted(results.items())}))

    # G7: every NON-eligible cohort log refused by BOTH contract + adapter, each with a named reason;
    #     an unknown id is also refused (no silent promotion of anything outside the eligible set).
    non_elig_refused = all(r["contract_refuses"] and r["adapter_refuses"] and r["reason"]
                           for r in refused)
    unknown_refused = (_refuses_payload(UNKNOWN_PROBE, rec) and _refuses_dispatch(UNKNOWN_PROBE, rec))
    gates.append(("G7 every NON-eligible cohort log refused by contract + adapter (named reason); unknown id refused",
                  non_elig_refused and unknown_refused,
                  {"non_eligible": len(refused), "all_named": non_elig_refused, "unknown_refused": unknown_refused}))

    # G8: ONLY eligible logs process -- the contract-eligible set == the seam-classifier-eligible set ==
    #     the frozen ELIGIBLE_EXEMPLARS; no dataset-wide auto-promotion (doc unchanged).
    contract_eligible = {r["log_id"] for r in doc["logs"] if not _refuses_payload(r["log_id"], rec)}
    classifier_eligible = {r["log_id"] for r in doc["logs"] if seam_classify(r)[0]}
    gates.append(("G8 only eligible logs process: contract-eligible == classifier-eligible == ELIGIBLE_EXEMPLARS (no auto-promotion)",
                  contract_eligible == classifier_eligible == set(ELIGIBLE_EXEMPLARS), sorted(contract_eligible)))

    pngs = sorted(p.name for p in OUT_DIR.glob("*.png"))
    gates.append(("G9 blanket proof emits NO render artifact of its own (zero PNG in its dir)",
                  len(pngs) == 0, pngs))

    result = (R_PASS if all(x for _, x, _ in gates)
              else B_INVARIANT if not gates[0][1]
              else B_ELIGIBILITY if not (gates[1][1] and gates[8][1])
              else B_BUILD if not (gates[2][1] and gates[3][1])
              else B_REFUSAL if not gates[7][1]
              else B_PROOF_FAIL)
    return _emit(gates, result, eligible, refused, results)


def _emit(gates, result, eligible, refused, results) -> int:
    gates.append(("G10 result in allowed enum", result in ALLOWED, result))
    all_pass = all(x for _, x, _ in gates)
    pass_count = sum(1 for e in eligible if e.get("result") == "PASS")
    blanket_result = {
        "eligible_logs": [
            {"bore_id": e["bore_id"], "seam_shape": e["seam_shape"], "render_mode": e["render_mode"],
             "source_bind_proofs": list(e["source_bind_proofs"]), "render_proofs": list(e["render_proofs"]),
             "result": e.get("result")}
            for e in eligible],
        "refused_logs": [{"bore_id": r["bore_id"], "reason": r["reason"]} for r in refused],
        "totals": {"eligible_count": len(eligible), "pass_count": pass_count,
                   "refused_count": len(refused)},
    }
    report = {
        "milestone": "OWNER-PACKET-2 -- seam-eligible blanket proof (proof only; blanket over the eligible set)",
        "verdict": "PASS" if all_pass else "FAIL",
        "result": result if all_pass else "BLOCKED",
        "proof": "truelinev2/proof/run_seam_eligible_blanket_proof.py",
        "eligible_exemplars": list(ELIGIBLE_EXEMPLARS),
        "blanket_result": blanket_result,
        "invoked_proofs": {m: ("PASS" if rc == 0 else f"FAIL({rc})") for m, rc in sorted(results.items())},
        "doctrine": {
            "blanket_covers_only_seam_eligible": True,
            "not_a_claim_all_production_logs_can_draw": True,
            "non_eligible_stay_refused_or_review": True,
            "eligibility_frozen_to": list(ELIGIBLE_EXEMPLARS),
        },
        "scope_guard": {"product_wiring": False, "broad_renderer": False, "render_queue": False,
                        "match_review_wiring": False, "runtime_batch_placement_or_rendering": False,
                        "dataset_wide_auto_promotion": False, "eligibility_growth": False,
                        "cross_sheet_join": False, "cross_sheet_frame_solving": False,
                        "representative_route_resolver": False, "parent_child_aggregation": False,
                        "new_log_promotion": False, "generated_artifacts_committed": False,
                        "own_render_artifacts": False},
        "next_slice": ("grow eligibility by exactly one more owner-confirmed endpoint-anchor bridge "
                       "(the near-miss / next-eligibility scouts' candidates), then re-run this blanket; "
                       "still no product wiring / no batch over the dataset / no cross-sheet join."),
        "gates": [{"name": n, "pass": bool(x), "detail": d} for n, x, d in gates],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "seam_eligible_blanket_proof.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"[blanket] result: {report['result']}")
    for e in eligible:
        print(f"[blanket]   {e['bore_id']:>6} | shape={e['seam_shape']:<48} | "
              f"render={','.join(e['render_mode'])} | result={e.get('result')}")
    print(f"[blanket]   eligible={len(eligible)} pass={sum(1 for e in eligible if e.get('result') == 'PASS')} "
          f"refused(non-eligible)={len(refused)}")
    for n, x, _ in gates:
        print(f"[blanket] {'PASS' if x else 'FAIL'}  {n}")
    print(f"[blanket] VERDICT: {'PASS' if all_pass else 'FAIL'}  (report: {OUT_DIR})")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
