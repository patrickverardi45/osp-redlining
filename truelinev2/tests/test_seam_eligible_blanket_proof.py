"""OWNER-PACKET-2 seam-eligible blanket proof -- offline tests.

Locks the blanket's PURE plan (the heavy proof invocation is verified by running the proof itself, not
here): the result enum; the blanket covers EXACTLY the four seam-eligible exemplars (log53/log64/log71/
log59) and no more; each eligible log carries its seam shape, render mode(s), and the source-bind +
render proof families (log59 maps to its OWN family + modules); every NON-eligible cohort log is refused
by BOTH the contract and the adapter with a named reason; the blanket is the eligible set ONLY -- NOT a
claim that all production logs can draw (the rest stay refused/review); and the proof is contained (no
product/render/runtime imports). No PDF parse / no subprocess here -- build_blanket_plan is pure.
"""
from pathlib import Path

from truelinev2.ingest.manual_adjudication import load_adjudication
from truelinev2.proof.run_seam_eligible_blanket_proof import (
    ALLOWED,
    EXPECTED_ELIGIBLE,
    OUT_DIR,
    R_PASS,
    build_blanket_plan,
)
from truelinev2.seam import ELIGIBLE_EXEMPLARS

DOC = load_adjudication()
PLAN = build_blanket_plan(DOC)
ELIG = PLAN["eligible"]
REF = PLAN["refused"]


def test_result_enum():
    assert ALLOWED == {
        "SEAM_ELIGIBLE_BLANKET_PASS", "BLOCKED_BLANKET_ELIGIBILITY_DRIFT",
        "BLOCKED_BLANKET_BUILD_FAILED", "BLOCKED_BLANKET_PROOF_FAMILY_FAILED",
        "BLOCKED_BLANKET_NON_ELIGIBLE_NOT_REFUSED", "BLOCKED_BLANKET_INVARIANT_VIOLATED",
    }
    assert R_PASS == "SEAM_ELIGIBLE_BLANKET_PASS"


def test_blanket_covers_exactly_the_four_eligible():
    assert EXPECTED_ELIGIBLE == ("log53", "log64", "log71", "log59")
    assert tuple(ELIGIBLE_EXEMPLARS) == EXPECTED_ELIGIBLE
    assert tuple(e["bore_id"] for e in ELIG) == EXPECTED_ELIGIBLE   # exactly the 4, in order


def test_each_eligible_has_shape_render_mode_and_proof_families():
    by_id = {e["bore_id"]: e for e in ELIG}
    assert by_id["log64"]["seam_shape"] == "single_sheet_structure_to_structure"
    assert by_id["log59"]["seam_shape"] == "single_sheet_structure_to_structure"
    assert by_id["log53"]["seam_shape"] == "two_sheet_matchline_endpoint"
    assert by_id["log71"]["seam_shape"] == "two_sheet_structure_to_structure_route_context"
    # log59 is single-sheet but ordered_chain_path (discontinuous corridor); log64 is continuous
    assert by_id["log59"]["render_mode"] == ["ordered_chain_path"]
    assert by_id["log64"]["render_mode"] == ["continuous_corridor"]
    assert by_id["log71"]["render_mode"] == ["continuous_corridor", "ordered_chain_path"]
    for e in ELIG:
        assert e["source_bind_proofs"]                                       # >= 1 source-bind module
        assert all(m.startswith("truelinev2.proof.run_") for m in e["source_bind_proofs"])
        assert len(e["render_proofs"]) == 1
        assert e["render_proofs"][0].endswith("_render_artifact_slice")


def test_log59_maps_to_its_own_proof_family_and_modules():
    e = next(x for x in ELIG if x["bore_id"] == "log59")
    assert e["proof_family"] == "log59_single_sheet_structure_to_structure"
    assert e["source_bind_proofs"] == ("truelinev2.proof.run_log59_sheet21_source_bind_slice",)
    assert e["render_proofs"] == ("truelinev2.proof.run_log59_render_artifact_slice",)


def test_non_eligible_logs_refused_with_named_reason():
    assert REF                                                              # there ARE non-eligible cohort logs
    for r in REF:
        assert r["bore_id"] not in ELIGIBLE_EXEMPLARS
        assert r["contract_refuses"] is True and r["adapter_refuses"] is True
        assert r["reason"]                                                  # named reason
        assert r["categories"]                                             # >= 1 category


def test_blanket_is_eligible_only_not_all_production():
    # the cohort partitions cleanly into eligible (4) + refused (the rest); NOT "all logs can draw"
    eligible_ids = {e["bore_id"] for e in ELIG}
    refused_ids = {r["bore_id"] for r in REF}
    assert eligible_ids == set(ELIGIBLE_EXEMPLARS)
    assert eligible_ids.isdisjoint(refused_ids)
    assert eligible_ids | refused_ids == {r["log_id"] for r in DOC["logs"]}
    assert len(ELIG) == 4 and len(REF) == len(DOC["logs"]) - 4


def test_output_dir_is_gitignored_data_outputs():
    p = str(OUT_DIR).replace("\\", "/")
    assert "/data/outputs/seam_eligible_blanket_proof" in p


def test_proof_is_contained_no_product_render_runtime_imports():
    src = Path(__file__).resolve().parent.parent / "proof" / "run_seam_eligible_blanket_proof.py"
    import_lines = "\n".join(ln for ln in src.read_text(encoding="utf-8").splitlines()
                             if ln.strip().startswith(("import ", "from ")))
    for forbidden in ("truelinev2.api", "truelinev2.service", "truelinev2.render", "truelinev2.match",
                      "truelinev2.ingest.pdf", "PlanPdf", "render_redline_stroke"):
        assert forbidden not in import_lines, f"blanket proof must stay contained (no {forbidden})"
