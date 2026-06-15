"""OWNER-PACKET-2 exemplar pipeline end-to-end driver -- offline tests.

Locks the driver's PURE drive plan (the heavy proof invocation is verified by running the proof
itself, not here): it builds a plan for EXACTLY the three eligible exemplars and REFUSES every other
log; the modules it will invoke ARE the canonical adapter registry (not an independent hardcoded
list); the correct source-bind/render families map per exemplar; and the doctrine is preserved
(log53 STA 24+11 modeled matchline endpoint; log71 STA 5+45 route context; log71 sheet 24
ordered_chain_path / sheet 23 continuous_corridor; cross-sheet join deferred; reconciliation false).
Also confirms the driver does not statically import product/render/match code (it invokes the render
proofs out-of-process). No PDF parse here.
"""
from pathlib import Path

import pytest

from truelinev2.ingest.manual_adjudication import load_adjudication
from truelinev2.proof.run_exemplar_pipeline_end_to_end_driver import (
    build_drive_plan,
    drive_one,
    invoke_proof_module,
)
from truelinev2.seam import ELIGIBLE_EXEMPLARS, PROOF_FAMILY

DOC = load_adjudication()
REC = {r["log_id"]: r for r in DOC["logs"]}
PLAN = build_drive_plan(DOC)


def test_drive_plan_for_exactly_three():
    assert tuple(PLAN) == ELIGIBLE_EXEMPLARS == ("log53", "log64", "log71")
    assert PLAN["log53"]["shape"] == "two_sheet_matchline_endpoint"
    assert PLAN["log64"]["shape"] == "single_sheet_structure_to_structure"
    assert PLAN["log71"]["shape"] == "two_sheet_structure_to_structure_route_context"


def test_drive_one_refuses_non_eligible():
    for log_id in ("log6", "log63", "log5", "log44"):
        with pytest.raises(ValueError):
            drive_one(log_id, REC[log_id])
    with pytest.raises(ValueError):
        drive_one("log999", {"log_id": "log999"})


def test_plan_modules_equal_adapter_registry():
    # the driver invokes EXACTLY the adapter registry's modules -- not an independent hardcoded list
    for lid in ELIGIBLE_EXEMPLARS:
        assert set(PLAN[lid]["source_bind_modules"]) == set(PROOF_FAMILY[lid]["source_bind_proofs"])
        assert PLAN[lid]["render_module"] == PROOF_FAMILY[lid]["render_proof"]


def test_correct_source_bind_and_render_families():
    assert set(PLAN["log53"]["source_bind_modules"]) == {
        "truelinev2.proof.run_log53_matchline_boundary_slice",
        "truelinev2.proof.run_log53_nextlink_hh_bindability_slice"}
    assert PLAN["log53"]["render_module"] == "truelinev2.proof.run_log53_render_artifact_slice"
    assert set(PLAN["log64"]["source_bind_modules"]) == {"truelinev2.proof.run_log64_sheet21_source_bind_slice"}
    assert PLAN["log64"]["render_module"] == "truelinev2.proof.run_log64_render_artifact_slice"
    assert set(PLAN["log71"]["source_bind_modules"]) == {"truelinev2.proof.run_log71_two_leg_source_bind_slice"}
    assert PLAN["log71"]["render_module"] == "truelinev2.proof.run_log71_render_artifact_slice"
    for lid in ELIGIBLE_EXEMPLARS:
        assert PLAN[lid]["render_module"].endswith("_render_artifact_slice")


def test_log53_matchline_endpoint_doctrine_preserved():
    d = PLAN["log53"]["doctrine"]
    assert d["matchline_role"] == "modeled_matchline_endpoint"
    assert d["matchline_station"] == "24+11"


def test_log71_route_context_doctrine_preserved():
    d = PLAN["log71"]["doctrine"]
    assert d["matchline_role"] == "between_leg_crossing_route_context"
    assert d["matchline_station"] == "5+45"


def test_log71_render_modes_preserved():
    modes = PLAN["log71"]["doctrine"]["render_modes"]
    assert modes[24] == "ordered_chain_path"
    assert modes[23] == "continuous_corridor"


def test_cross_sheet_join_and_reconciliation():
    assert PLAN["log64"]["doctrine"]["cross_sheet_join"] is None
    assert PLAN["log53"]["doctrine"]["cross_sheet_join"] == "deferred"
    assert PLAN["log71"]["doctrine"]["cross_sheet_join"] == "deferred"
    for lid in ELIGIBLE_EXEMPLARS:
        assert PLAN[lid]["doctrine"]["coordinate_reconciliation"] is False


def test_invoke_proof_module_is_callable_out_of_process():
    # the invoker exists and runs a module out-of-process (proven against a trivially-passing module);
    # the real proof-family invocations + their PASS results are verified by running the driver proof.
    assert callable(invoke_proof_module)
    assert invoke_proof_module("truelinev2.proof.import_isolation") == 0


def test_driver_does_not_statically_import_product_or_render():
    # the driver invokes render proofs OUT-OF-PROCESS (subprocess); its own namespace must not pull in
    # product/render/match/PDF code.
    src = (Path(__file__).resolve().parent.parent / "proof" / "run_exemplar_pipeline_end_to_end_driver.py")
    import_lines = "\n".join(ln for ln in src.read_text(encoding="utf-8").splitlines()
                             if ln.strip().startswith(("import ", "from ")))
    for forbidden in ("truelinev2.api", "truelinev2.service", "truelinev2.render", "truelinev2.match",
                      "truelinev2.ingest.pdf", "PlanPdf", "render_redline_stroke"):
        assert forbidden not in import_lines, f"driver must not statically import {forbidden}"
