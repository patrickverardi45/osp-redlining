r"""OWNER-PACKET-2 -- contract -> PROOF adapter proof (PROOF ONLY; no product, no render execution).

Proves the contained pure adapter (truelinev2/seam/proof_adapter.py) hands the typed coordinate-free
seam contract off to the EXISTING proven per-leg source-bind/render proof families for the three
eligible exemplars -- without product wiring, without a batch runner, without executing the proofs,
and without expanding eligibility. It builds dispatch descriptors from the CANONICAL contract module,
checks the doctrine is preserved verbatim (log53 matchline endpoint; log71 5+45 route context; log71
sheet 24 ordered_chain_path not downgraded), confirms the named existing proof modules EXIST
(read-only find_spec; never imported/run here), and confirms eligibility never expands. Census frozen.

Proof-only; the JSON report is written under the gitignored data/outputs path.
Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_exemplar_pipeline_contract_adapter
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

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
    dispatch_is_coordinate_free,
    eligible_dispatches,
    is_coordinate_free,
)

SOURCE_BIND_SUFFIXES = ("_source_bind_slice", "_bindability_slice", "_boundary_slice")

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "exemplar_pipeline_contract_adapter"
TRUTH = _REPO_ROOT / "data" / "outputs" / "final_engine_truth_table" / \
    "final_engine_truth_table.json"
ADAPTER_SRC = _REPO_ROOT / "truelinev2" / "seam" / "proof_adapter.py"
FROZEN_BUCKETS = {"DRAWABLE_REVIEW": 31, "HUMAN_ADJUSTABLE_REVIEW": 6,
                  "OUT_OF_CLASS": 1, "PICK_CARD_REVIEW": 17, "SOURCE_OR_KMZ_REQUIRED": 3}
ABSTAIN_4 = ("log5", "log31", "log38", "log43")
REFUSAL_PROBES = ("log6", "log63", "log5", "log44")
# Per-EXEMPLAR proof family (NOT shape-keyed): log59 and log64 share the single_sheet shape but each
# hands off to its OWN source-bind/render proofs (log59 renders ordered_chain_path, log64 continuous),
# so the expected family is keyed by exemplar, not by shape.
EXEMPLAR_FAMILY = {
    "log53": "log53_two_sheet_matchline_endpoint",
    "log64": "log64_single_sheet_structure_to_structure",
    "log71": "log71_two_sheet_structure_to_structure_route_context",
    "log59": "log59_single_sheet_structure_to_structure",
}

R_PASS = "EXEMPLAR_PIPELINE_CONTRACT_ADAPTER_PASS"
B_ELIGIBILITY = "BLOCKED_ADAPTER_ELIGIBILITY_DRIFT"
B_DOCTRINE = "BLOCKED_ADAPTER_DOCTRINE_VIOLATED"
B_MAPPING = "BLOCKED_ADAPTER_PROOF_FAMILY_MAPPING_INVALID"
B_INVARIANT = "BLOCKED_ADAPTER_INVARIANT_VIOLATED"
ALLOWED = {R_PASS, B_ELIGIBILITY, B_DOCTRINE, B_MAPPING, B_INVARIANT}


def _module_exists(modname: str) -> bool:
    """Read-only existence check (locates the module; does NOT import or execute it)."""
    try:
        return importlib.util.find_spec(modname) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def _refuses(log_id: str, rec: dict) -> bool:
    try:
        build_dispatch(log_id, rec.get(log_id, {}))
        return False
    except ValueError:
        return True


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

    # ---- build dispatches via the CANONICAL contract module --------------------
    dispatches = eligible_dispatches(doc)
    adapter_text = ADAPTER_SRC.read_text(encoding="utf-8")
    # G1: adapter consumes the canonical contract (imports from it; owns NO duplicate exemplar
    # topology) and its eligibility + per-bore shape are SOURCED from the contract (the dispatch
    # shape equals the contract payload's shape; the registry keys are the contract's eligible set).
    sourced_from_contract = (
        "from truelinev2.seam.contract import" in adapter_text
        and "EXEMPLAR_TOPOLOGY" not in adapter_text
        and tuple(PROOF_FAMILY) == ELIGIBLE_EXEMPLARS
        and all(dispatches[lid].shape == build_seam_payload(lid, rec[lid]).shape.value
                for lid in ELIGIBLE_EXEMPLARS))
    gates.append(("G1 adapter consumes canonical seam contract (no duplicate topology; eligibility+shape sourced from it)",
                  sourced_from_contract, None))

    gates.append(("G2 adapter accepts EXACTLY log53/log64/log71/log59",
                  tuple(dispatches) == ELIGIBLE_EXEMPLARS == ("log53", "log64", "log71", "log59"),
                  sorted(dispatches)))

    refusals = {lid: _refuses(lid, rec) for lid in REFUSAL_PROBES}
    refusals["log999_unknown"] = _refuses("log999", rec)
    gates.append(("G3 adapter refuses all non-eligible logs (recovered-no-anchor, abstain, needs-verify, unknown)",
                  all(refusals.values()), refusals))

    coord_free = all(dispatch_is_coordinate_free(d) for d in dispatches.values())
    # negative control: the guard must FAIL when a coordinate key is injected into a dispatch copy
    poisoned = json.loads(json.dumps(dispatches["log71"].to_dict()))
    poisoned["legs"][0]["symbol_xy"] = [1.0, 2.0]
    neg_control = is_coordinate_free(poisoned) is False
    gates.append(("G4 dispatch handoff is coordinate-free (and the guard bites on an injected coord)",
                  coord_free and neg_control, {"coord_free": coord_free, "neg_control": neg_control}))

    # G5: boundary kinds preserved verbatim from the contract payload
    boundary_ok = True
    for lid in ELIGIBLE_EXEMPLARS:
        payload = build_seam_payload(lid, rec[lid])
        disp = dispatches[lid]
        for leg, dleg in zip(payload.legs, disp.legs):
            if (dleg.start_boundary_kind != leg.start_anchor.boundary_kind.value
                    or dleg.end_boundary_kind != leg.end_anchor.boundary_kind.value):
                boundary_ok = False
    gates.append(("G5 endpoint anchors + boundary kinds preserved verbatim from the contract", boundary_ok, None))

    d53, d64, d71 = dispatches["log53"], dispatches["log64"], dispatches["log71"]
    gates.append(("G6 log53 matchline-endpoint doctrine preserved (STA 24+11 modeled matchline endpoint)",
                  d53.shape == "two_sheet_matchline_endpoint"
                  and d53.legs[0].end_boundary_kind == "matchline_continuation"
                  and d53.legs[0].route_context_role == "modeled_matchline_endpoint"
                  and d53.legs[0].matchline_station == "24+11", d53.legs[0].matchline_station))
    gates.append(("G7 log71 route-context doctrine preserved (STA 5+45 route context, not endpoint)",
                  d71.shape == "two_sheet_structure_to_structure_route_context"
                  and d71.legs[0].end_boundary_kind == "matchline_route_context"
                  and d71.legs[0].route_context_role == "between_leg_crossing_route_context"
                  and d71.legs[0].matchline_station == "5+45", d71.legs[0].matchline_station))

    s24 = next(l for l in d71.legs if l.sheet == 24)
    s23 = next(l for l in d71.legs if l.sheet == 23)
    all_modes = {l.render_mode for d in dispatches.values() for l in d.legs}
    gates.append(("G8 log71 sheet 24 = ordered_chain_path (not downgraded); s23 continuous; modes are the two known",
                  s24.render_mode == "ordered_chain_path" and s23.render_mode == "continuous_corridor"
                  and all_modes <= {"continuous_corridor", "ordered_chain_path"}, sorted(all_modes)))

    # G9: each leg maps to the correct proof family (matches its shape); the named EXISTING proof
    # modules exist (read-only find_spec); and each is named by its ROLE (render vs source-bind), so a
    # swapped registry entry is caught. The adapter never imports/executes them.
    family_ok, modules_ok, role_ok, missing = True, True, True, []
    for lid in ELIGIBLE_EXEMPLARS:
        for leg in dispatches[lid].legs:
            if leg.expected_proof_family != EXEMPLAR_FAMILY[lid]:
                family_ok = False
            if not leg.expected_render_proof.endswith("_render_artifact_slice"):
                role_ok = False
            if not all(m.endswith(SOURCE_BIND_SUFFIXES) for m in leg.expected_source_bind_proofs):
                role_ok = False
            for mod in (*leg.expected_source_bind_proofs, leg.expected_render_proof):
                if not _module_exists(mod):
                    modules_ok = False
                    missing.append(mod)
    gates.append(("G9 each leg maps to the correct proof family; named source-bind/render proofs exist + role-named",
                  family_ok and modules_ok and role_ok,
                  {"family_ok": family_ok, "role_ok": role_ok, "missing_modules": sorted(set(missing))}))

    gates.append(("G10 cross-sheet join deferred (two-sheet) / None (single-sheet)",
                  d53.cross_sheet_join == "deferred" and d71.cross_sheet_join == "deferred"
                  and d64.cross_sheet_join is None, None))
    gates.append(("G11 cross-sheet coordinate reconciliation false; every leg sheet-local",
                  all(d.cross_sheet_coordinate_reconciliation is False for d in dispatches.values())
                  and all(isinstance(l.sheet, int) for d in dispatches.values() for l in d.legs), None))

    # G12: the adapter imports NO renderer / product / PDF, and never imports the proof modules it names
    import_lines = "\n".join(ln for ln in adapter_text.splitlines()
                             if ln.strip().startswith(("import ", "from ")))
    purity_ok = not any(bad in import_lines for bad in (
        "truelinev2.api", "truelinev2.service", "truelinev2.render", "truelinev2.ingest",
        "truelinev2.extract", "truelinev2.match", "truelinev2.proof", "PlanPdf",
        "render_redline_stroke"))
    gates.append(("G12 adapter imports no broad renderer / product / PDF / proof modules (pure)", purity_ok, None))

    result = (R_PASS if all(x for _, x, _ in gates)
              else B_INVARIANT if not gates[0][1]
              else B_ELIGIBILITY if not (gates[2][1] and gates[3][1])
              else B_MAPPING if not (family_ok and modules_ok and role_ok)
              else B_DOCTRINE)
    return _emit(gates, result, dispatches)


def _emit(gates, result, dispatches) -> int:
    pngs = sorted(p.name for p in OUT_DIR.glob("*.png"))
    gates.append(("G13 no render artifact generated by this proof (JSON only; zero PNG)", len(pngs) == 0, pngs))
    gates.append(("G14 result in allowed enum", result in ALLOWED, result))
    all_pass = all(x for _, x, _ in gates)
    dicts = {lid: dispatches[lid].to_dict() for lid in dispatches}
    report = {
        "milestone": "OWNER-PACKET-2 -- contract -> proof adapter (proof; pure handoff to proven proof families)",
        "verdict": "PASS" if all_pass else "FAIL",
        "result": result if all_pass else "BLOCKED",
        "adapter": "truelinev2/seam/proof_adapter.py",
        "eligible_exemplars": list(ELIGIBLE_EXEMPLARS),
        "proof_families": {lid: {"family": PROOF_FAMILY[lid]["family"].value,
                                 "source_bind_proofs": list(PROOF_FAMILY[lid]["source_bind_proofs"]),
                                 "render_proof": PROOF_FAMILY[lid]["render_proof"]}
                           for lid in ELIGIBLE_EXEMPLARS},
        "dispatches": dicts,
        "doctrine": {
            "coordinate_free_handoff": True,
            "log53_matchline": "modeled matchline endpoint (24+11) preserved through the adapter",
            "log71_matchline": "route context only (5+45); never a third endpoint",
            "log71_sheet24_render_mode": "ordered_chain_path (not downgraded to continuous/straight)",
            "cross_sheet_join": "deferred (two-sheet) / none (single-sheet); reconciliation = false",
            "eligibility": "frozen to the three exemplars; adapter refuses any other log",
            "execution": "names existing proof modules only; never imports or runs them",
        },
        "scope_guard": {"product_wiring": False, "broad_renderer": False, "batch_placement_or_rendering": False,
                        "eligibility_expansion": False, "cross_sheet_join": False,
                        "cross_sheet_frame_solving": False, "representative_route_resolver": False,
                        "parent_child_aggregation": False, "proof_modules_executed": False,
                        "coordinates_invented": False, "generated_artifacts_committed": False},
        "next_slice": ("if accepted, a CONTAINED end-to-end driver proof that uses this dispatch to "
                       "actually invoke each named proof family for the three exemplars (still no "
                       "product wiring / no batch / no cross-sheet join); OR grow eligibility by one "
                       "log by encoding the next owner-confirmed endpoint_anchors bridge."),
        "gates": [{"name": n, "pass": bool(x), "detail": d} for n, x, d in gates],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "exemplar_pipeline_contract_adapter.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"[adapter] result: {report['result']}")
    for lid in ELIGIBLE_EXEMPLARS:
        d = dicts[lid]
        print(f"[adapter]   {lid}: shape={d['shape']} legs={len(d['legs'])} "
              f"family={d['legs'][0]['expected_proof_family']} x-sheet_join={d['cross_sheet_join']}")
    for n, x, _ in gates:
        print(f"[adapter] {'PASS' if x else 'FAIL'}  {n}")
    print(f"[adapter] VERDICT: {'PASS' if all_pass else 'FAIL'}  (report: {OUT_DIR})")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
