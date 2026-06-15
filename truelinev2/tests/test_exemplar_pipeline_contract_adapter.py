"""OWNER-PACKET-2 contract -> proof adapter -- offline tests.

Locks the pure adapter (truelinev2/seam/proof_adapter.py): it consumes the CANONICAL seam contract
(no duplicate topology); builds dispatch for EXACTLY the three eligible exemplars and REFUSES every
other log; the handoff descriptor is coordinate-free and preserves boundary kinds verbatim; the
matchline doctrine holds (log53 STA 24+11 modeled endpoint; log71 STA 5+45 route context); log71
sheet 24 stays ordered_chain_path (not downgraded); each leg maps to the correct proof family and the
named existing source-bind/render proof modules exist; the cross-sheet join is deferred and
reconciliation is false; and the adapter imports no renderer/product/PDF/proof code. No PDF parse.
"""
import importlib.util
from pathlib import Path

import pytest

from truelinev2.ingest.manual_adjudication import load_adjudication
from truelinev2.seam import (
    ELIGIBLE_EXEMPLARS,
    PROOF_FAMILY,
    ProofDispatch,
    ProofFamily,
    build_dispatch,
    dispatch_is_coordinate_free,
    eligible_dispatches,
    is_coordinate_free,
)

DOC = load_adjudication()
REC = {r["log_id"]: r for r in DOC["logs"]}


def _d(log_id):
    return build_dispatch(log_id, REC[log_id])


def test_proof_family_registry_is_frozen_to_three():
    assert tuple(PROOF_FAMILY) == ELIGIBLE_EXEMPLARS == ("log53", "log64", "log71")
    assert {f.value for f in ProofFamily} == {
        "log53_two_sheet_matchline_endpoint",
        "log64_single_sheet_structure_to_structure",
        "log71_two_sheet_structure_to_structure_route_context"}


def test_builds_dispatch_for_exactly_three():
    dispatches = eligible_dispatches(DOC)
    assert tuple(dispatches) == ELIGIBLE_EXEMPLARS
    assert all(isinstance(d, ProofDispatch) for d in dispatches.values())
    assert len(_d("log64").legs) == 1
    assert len(_d("log53").legs) == 2
    assert len(_d("log71").legs) == 2


def test_refuses_non_eligible_no_silent_promotion():
    for log_id in ("log6", "log63", "log5", "log44"):
        with pytest.raises(ValueError):
            build_dispatch(log_id, REC[log_id])
    with pytest.raises(ValueError):
        build_dispatch("log999", {"log_id": "log999"})


def test_dispatch_is_coordinate_free():
    for lid in ELIGIBLE_EXEMPLARS:
        assert dispatch_is_coordinate_free(_d(lid)) is True
    # negative control: the guard bites when a coordinate key is injected into a dispatch copy
    poisoned = _d("log71").to_dict()
    poisoned["legs"][0]["symbol_xy"] = [1.0, 2.0]
    assert is_coordinate_free(poisoned) is False


def test_log53_matchline_endpoint_doctrine_preserved():
    d = _d("log53")
    assert d.shape == "two_sheet_matchline_endpoint"
    assert d.legs[0].end_boundary_kind == "matchline_continuation"
    assert d.legs[0].route_context_role == "modeled_matchline_endpoint"
    assert d.legs[0].matchline_station == "24+11"          # the named station is carried + locked


def test_log71_route_context_doctrine_preserved():
    d = _d("log71")
    assert d.shape == "two_sheet_structure_to_structure_route_context"
    assert d.legs[0].end_boundary_kind == "matchline_route_context"
    assert d.legs[0].route_context_role == "between_leg_crossing_route_context"
    assert d.legs[0].matchline_station == "5+45"           # 5+45 carried as route context, not endpoint


def test_log71_sheet24_ordered_chain_path_not_downgraded():
    d = _d("log71")
    s24 = next(l for l in d.legs if l.sheet == 24)
    s23 = next(l for l in d.legs if l.sheet == 23)
    assert s24.render_mode == "ordered_chain_path"
    assert s23.render_mode == "continuous_corridor"
    all_modes = {l.render_mode for lid in ELIGIBLE_EXEMPLARS for l in _d(lid).legs}
    assert not any("straight" in m or "diagonal" in m for m in all_modes)


def test_each_leg_maps_to_correct_family_and_existing_proofs():
    shape_family = {
        "single_sheet_structure_to_structure": "log64_single_sheet_structure_to_structure",
        "two_sheet_matchline_endpoint": "log53_two_sheet_matchline_endpoint",
        "two_sheet_structure_to_structure_route_context": "log71_two_sheet_structure_to_structure_route_context",
    }
    bind_suffixes = ("_source_bind_slice", "_bindability_slice", "_boundary_slice")
    for lid in ELIGIBLE_EXEMPLARS:
        d = _d(lid)
        for leg in d.legs:
            assert leg.expected_proof_family == shape_family[d.shape]
            # role-named so a swapped registry entry is caught: render vs source-bind
            assert leg.expected_render_proof.endswith("_render_artifact_slice")
            assert all(m.endswith(bind_suffixes) for m in leg.expected_source_bind_proofs)
            # the named existing proof modules resolve (read-only; not imported/executed)
            for mod in (*leg.expected_source_bind_proofs, leg.expected_render_proof):
                assert mod.startswith("truelinev2.proof.run_")
                assert importlib.util.find_spec(mod) is not None


def test_cross_sheet_join_deferred_and_no_reconciliation():
    assert _d("log64").cross_sheet_join is None
    assert _d("log53").cross_sheet_join == "deferred"
    assert _d("log71").cross_sheet_join == "deferred"
    for lid in ELIGIBLE_EXEMPLARS:
        d = _d(lid)
        assert d.cross_sheet_coordinate_reconciliation is False
        for leg in d.legs:
            assert isinstance(leg.sheet, int)


def test_adapter_uses_canonical_contract_no_duplicate_topology():
    src = (Path(__file__).resolve().parent.parent / "seam" / "proof_adapter.py").read_text(encoding="utf-8")
    assert "from truelinev2.seam.contract import" in src
    assert "EXEMPLAR_TOPOLOGY" not in src      # must not re-declare the contract's topology


def test_adapter_is_pure_no_render_product_pdf_proof_imports():
    src = (Path(__file__).resolve().parent.parent / "seam" / "proof_adapter.py").read_text(encoding="utf-8")
    import_lines = "\n".join(ln for ln in src.splitlines() if ln.strip().startswith(("import ", "from ")))
    for forbidden in ("truelinev2.api", "truelinev2.service", "truelinev2.render", "truelinev2.ingest",
                      "truelinev2.extract", "truelinev2.match", "truelinev2.proof", "PlanPdf",
                      "render_redline_stroke"):
        assert forbidden not in import_lines, f"adapter must stay pure (no {forbidden})"
