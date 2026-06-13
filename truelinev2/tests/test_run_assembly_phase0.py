"""M9.4 -- gated REVIEW-only run-assembly Phase-0 tests (offline; pure law + posture).

Pin the run-assembly safety law (evaluate_junction) over SYNTHETIC M9.3.1 facts:
the shared-terminal-node review candidate, the fiber-drop branch (departure run
class = drop), the self-junction refusal, and every typed blocker. The LIVE Brenham
facts (2 candidates + 1 drop, 7 clean ENDs, no drift) are gated INSIDE the proof
(run_run_assembly_phase0, G1-G10).
"""
import inspect

from truelinev2.match import terminus_attribution as TA
from truelinev2.proof import run_run_assembly_phase0 as p0

BOUND = "KMZ_TERMINAL_JOIN_BOUND"


def _ep(side, result, ap=None, splice=None, kmz_join=None):
    return TA.EndpointAttribution(side=side, station=("4+51" if side == "END" else "0+00"),
                                  result=result, ap=ap, splice=splice, kmz_join=kmz_join)


def _bore(bid, *, end_result=TA.NO_ENDPOINT_NOTE, end_ap=None, end_splice=None,
          end_join=None, start_result=TA.NO_ENDPOINT_NOTE, start_ap=None,
          start_splice=None):
    return TA.BoreTerminusResult(
        bore_id=bid, start_station="0+00", end_station="4+51",
        start=_ep("START", start_result, start_ap, start_splice),
        end=_ep("END", end_result, end_ap, end_splice, end_join),
        sheet_neighbors=())


def _by_id(*results):
    return {r.bore_id: r for r in results}


def _clean():
    ender = _bore("ender", end_result=TA.ENDPOINT_ATTRIBUTED, end_ap=152,
                  end_splice="SPLICE LOC 35", end_join=BOUND)
    starter = _bore("starter", start_result=TA.JUNCTION_ORIGIN, start_ap=152,
                    start_splice="SPLICE LOC 35")
    j = {"start_bore": "starter", "terminal_ap": 152, "end_bore_owner": "ender",
         "splice_loc": "SPLICE LOC 35"}
    return j, _by_id(ender, starter)


def test_shared_terminal_node_review_candidate():
    j, by_id = _clean()
    r = p0.evaluate_junction(j, by_id, {152: 1}, {}, dep_class="unknown")
    assert r["disposition"] == p0.RUN_ASSEMBLY_REVIEW_CANDIDATE
    assert r["relation"] == p0.RELATION_SHARED_TERMINAL
    assert r["review_only"] and r["evidence_only"]
    assert r["affects_product_disposition"] is False
    assert r["geometry"] is None and r["auto"] is False
    assert r["terminal_is_end_of_feed"] is True
    assert r["departure_run_class"] == "unknown"


def test_fiber_drop_departure_is_branch_not_continuation():
    j, by_id = _clean()
    r = p0.evaluate_junction(j, by_id, {152: 1}, {}, dep_class="drop")
    assert r["disposition"] == p0.JUNCTION_DROP_BRANCH
    assert "DROP" in r["why"].upper() and "NOT the trunk" in r["why"]


def test_self_junction_refused():
    # a bore whose START and END both sit at the same terminal is not bore-to-bore.
    loop = _bore("loop", end_result=TA.ENDPOINT_ATTRIBUTED, end_ap=152,
                 end_splice="SPLICE LOC 35", end_join=BOUND,
                 start_result=TA.JUNCTION_ORIGIN, start_ap=152, start_splice="SPLICE LOC 35")
    j = {"start_bore": "loop", "terminal_ap": 152, "end_bore_owner": "loop",
         "splice_loc": "SPLICE LOC 35"}
    r = p0.evaluate_junction(j, _by_id(loop), {152: 1}, {}, dep_class="trunk")
    assert r["disposition"] == p0.SELF_JUNCTION_REFUSED


def test_start_as_ownership_refused():
    j, by_id = _clean()
    by_id["starter"] = _bore("starter", start_result=TA.ENDPOINT_ATTRIBUTED,
                             start_ap=152, start_splice="SPLICE LOC 35")
    r = p0.evaluate_junction(j, by_id, {152: 1}, {}, dep_class="trunk")
    assert r["disposition"] == p0.START_JUNCTION_NOT_OWNERSHIP


def test_contradiction_blocks():
    j, by_id = _clean()
    assert p0.evaluate_junction(j, by_id, {152: 1}, {"starter": p0.SOURCE_CONTRADICTION},
                                dep_class="trunk")["disposition"] == p0.SOURCE_CONTRADICTION
    assert p0.evaluate_junction(j, by_id, {152: 1}, {"ender": p0.PDF_KMZ_CONTRADICTION},
                                dep_class="trunk")["disposition"] == p0.PDF_KMZ_CONTRADICTION


def test_competing_junction_branch():
    j, by_id = _clean()
    r = p0.evaluate_junction(j, by_id, {152: 2}, {}, dep_class="trunk")
    assert r["disposition"] == p0.COMPETING_JUNCTION_CANDIDATES


def test_terminal_fact_mismatch_and_no_kmz_are_unmodeled():
    j, by_id = _clean()
    by_id["starter"] = _bore("starter", start_result=TA.JUNCTION_ORIGIN, start_ap=152,
                             start_splice="SPLICE LOC 99")
    assert p0.evaluate_junction(j, by_id, {152: 1}, {}, dep_class="trunk")["disposition"] \
        == p0.UNMODELED_RUN_RELATIONSHIP
    j2, by_id2 = _clean()
    by_id2["ender"] = _bore("ender", end_result=TA.ENDPOINT_ATTRIBUTED, end_ap=152,
                            end_splice="SPLICE LOC 35", end_join="KMZ_TERMINAL_JOIN_NONE")
    assert p0.evaluate_junction(j2, by_id2, {152: 1}, {}, dep_class="trunk")["disposition"] \
        == p0.UNMODELED_RUN_RELATIONSHIP


def test_none_owner_is_typed_no_unique_owner():
    j = {"start_bore": "starter", "terminal_ap": 152, "end_bore_owner": None,
         "splice_loc": "SPLICE LOC 35"}
    starter = _bore("starter", start_result=TA.JUNCTION_ORIGIN, start_ap=152,
                    start_splice="SPLICE LOC 35")
    r = p0.evaluate_junction(j, _by_id(starter), {152: 1}, {}, dep_class="unknown")
    assert r["disposition"] == p0.UNMODELED_RUN_RELATIONSHIP
    assert "no unique END owner" in r["why"]


# ---- banked constants -------------------------------------------------------

def test_banked_constants():
    assert p0.EXPECT_JUNCTIONS == {("log27", 152, "log10"), ("log39", 117, "log72"),
                                   ("log65", 163, "log7")}
    assert p0.EXPECT_CLEAN_END["log10"] == 152 and len(p0.EXPECT_CLEAN_END) == 7
    assert p0.M92_NO_EQUATION == {"log14", "log61", "log62", "log67", "log68", "log70"}
    assert p0.SOURCE_CONTRADICTION_BORES == {"log44"}
    assert p0.DROP_MARKER == "FOR FIBER DROP"


def test_norm_helper():
    assert p0._norm("Splice Loc 35") == "SPLICE LOC 35"
    assert p0._norm(None) is None


# ---- read-only / evidence-only posture -------------------------------------

def test_proof_is_read_only_evidence_only():
    src = inspect.getsource(p0)
    assert "truelinev2.render" not in src and "render_redline_stroke" not in src
    assert "Status.AUTO" not in src and "place_bore" not in src
    assert "REDLINE_STROKE" not in src
    assert "TA.attribute_bore" in src and "TA.resolve_junctions" in src


def test_run_assembly_core_module_shipped_in_m941():
    # Phase 0 named the core as the next milestone; M9.4.1 ships it. The core stays
    # UNWIRED from the placement path (guarded in test_run_assembly.py).
    from pathlib import Path
    pkg = Path(p0.__file__).resolve().parents[1]
    assert (pkg / "match" / "run_assembly.py").exists()
    assert (pkg / "review" / "run_assembly_review.py").exists()
