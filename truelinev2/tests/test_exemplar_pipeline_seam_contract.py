"""OWNER-PACKET-2 exemplar pipeline seam contract -- offline tests.

Locks the pure seam module (truelinev2/seam/contract.py): the enum values; that it builds payloads
for EXACTLY the three eligible exemplars and REFUSES every other log (no silent promotion); that the
payload is coordinate-free and preserves endpoint-anchor identity; that the matchline doctrine holds
(log53 STA 24+11 = modeled matchline endpoint; log71 STA 5+45 = route context only); that log71
sheet 24 is ordered_chain_path (never a straight corridor); that the cross-sheet join is deferred and
coordinate reconciliation is false; and that the module is a PURE contract (no product/render/PDF
imports) and is semantically equivalent to the committed seam scout. No PDF parse here.
"""
from pathlib import Path

import pytest

from truelinev2.ingest.manual_adjudication import load_adjudication
from truelinev2.proof.run_exemplar_pipeline_seam_scout import normalize_exemplar as scout_normalize
from truelinev2.seam import (
    ELIGIBLE_EXEMPLARS,
    BoundaryKind,
    RenderMode,
    SeamPayload,
    SeamShape,
    build_seam_payload,
    eligible_seam_payloads,
    is_coordinate_free,
)

DOC = load_adjudication()
REC = {r["log_id"]: r for r in DOC["logs"]}


def _p(log_id):
    return build_seam_payload(log_id, REC[log_id])


def test_enum_values():
    assert {k.value for k in BoundaryKind} == {
        "structure_terminus", "matchline_continuation", "matchline_route_context"}
    assert {m.value for m in RenderMode} == {"continuous_corridor", "ordered_chain_path"}
    assert {s.value for s in SeamShape} == {
        "single_sheet_structure_to_structure", "two_sheet_matchline_endpoint",
        "two_sheet_structure_to_structure_route_context"}
    assert ELIGIBLE_EXEMPLARS == ("log53", "log64", "log71", "log59", "log66")


def test_builds_exactly_five_eligible_exemplars():
    payloads = eligible_seam_payloads(DOC)
    assert tuple(payloads) == ELIGIBLE_EXEMPLARS
    assert _p("log64").shape == SeamShape.SINGLE_SHEET_STRUCTURE_TO_STRUCTURE and len(_p("log64").legs) == 1
    assert _p("log53").shape == SeamShape.TWO_SHEET_MATCHLINE_ENDPOINT and len(_p("log53").legs) == 2
    assert _p("log71").shape == SeamShape.TWO_SHEET_STRUCTURE_TO_STRUCTURE_ROUTE_CONTEXT and len(_p("log71").legs) == 2
    # log59 + log66 share log64's single-sheet shape but render ordered_chain_path (discontinuous corridor)
    assert _p("log59").shape == SeamShape.SINGLE_SHEET_STRUCTURE_TO_STRUCTURE and len(_p("log59").legs) == 1
    assert _p("log59").legs[0].render_mode == RenderMode.ORDERED_CHAIN_PATH
    assert _p("log66").shape == SeamShape.SINGLE_SHEET_STRUCTURE_TO_STRUCTURE and len(_p("log66").legs) == 1
    assert _p("log66").legs[0].render_mode == RenderMode.ORDERED_CHAIN_PATH


def test_refuses_non_eligible_logs_no_silent_promotion():
    # recovered-but-no-anchor, owner-abstain, needs-source-verification, and an unknown id all refuse
    for log_id in ("log6", "log63", "log5", "log44"):
        with pytest.raises(ValueError):
            build_seam_payload(log_id, REC[log_id])
    with pytest.raises(ValueError):
        build_seam_payload("log999", {"log_id": "log999"})
    # even an eligible id refuses if its endpoint_anchors are absent (eligibility requires them)
    with pytest.raises(ValueError):
        build_seam_payload("log71", {"log_id": "log71"})


def test_payload_is_coordinate_free():
    for lid in ELIGIBLE_EXEMPLARS:
        assert is_coordinate_free(_p(lid).to_dict()) is True
    # the guard actually fires on a planted coordinate key
    assert is_coordinate_free({"legs": [{"start_anchor": {"xy": [1.0, 2.0]}}]}) is False


def test_endpoint_anchors_preserved():
    p64 = _p("log64")
    assert (p64.legs[0].start_anchor.structure_class, p64.legs[0].start_anchor.station) == ("installer_hh", "3+69")
    assert (p64.legs[0].end_anchor.structure_class, p64.legs[0].end_anchor.station) == ("flower_pot", "1+00")
    p71 = _p("log71")
    assert (p71.legs[0].start_anchor.structure_class, p71.legs[0].start_anchor.station) == ("nextlink_hh", "7+50")
    assert (p71.legs[-1].end_anchor.structure_class, p71.legs[-1].end_anchor.station) == ("flower_pot", "6+95")
    assert _p("log53").legs[0].start_anchor.structure_class == "nextlink_hh"


def test_matchline_doctrine_endpoint_vs_route_context():
    l53 = _p("log53").legs[0].end_anchor
    assert l53.boundary_kind == BoundaryKind.MATCHLINE_CONTINUATION and l53.station == "24+11"
    assert _p("log53").legs[0].route_context.role == "modeled_matchline_endpoint"
    l71 = _p("log71").legs[0].end_anchor
    assert l71.boundary_kind == BoundaryKind.MATCHLINE_ROUTE_CONTEXT and l71.station == "5+45"
    assert _p("log71").legs[0].route_context.role == "between_leg_crossing_route_context"


def test_log71_sheet24_is_ordered_chain_path_not_straight():
    s24 = next(l for l in _p("log71").legs if l.sheet == 24)
    s23 = next(l for l in _p("log71").legs if l.sheet == 23)
    assert s24.render_mode == RenderMode.ORDERED_CHAIN_PATH
    assert s23.render_mode == RenderMode.CONTINUOUS_CORRIDOR
    all_modes = {l.render_mode.value for lid in ELIGIBLE_EXEMPLARS for l in _p(lid).legs}
    assert not any("straight" in m or "diagonal" in m for m in all_modes)


def test_cross_sheet_join_deferred_and_no_reconciliation():
    assert _p("log64").cross_sheet_join is None                 # single sheet
    assert _p("log53").cross_sheet_join == "deferred"           # two sheets, not solved
    assert _p("log71").cross_sheet_join == "deferred"
    for lid in ELIGIBLE_EXEMPLARS:
        p = _p(lid)
        assert p.cross_sheet_coordinate_reconciliation is False
        for leg in p.legs:
            assert isinstance(leg.sheet, int)                   # each leg is exactly one sheet


def test_to_dict_carries_required_contract_fields():
    d = _p("log71").to_dict()
    required = {"bore_id", "shape", "review_status", "eligible", "abstain_reason", "sheets", "legs",
                "matchline_stations", "cross_sheet_join", "cross_sheet_coordinate_reconciliation"}
    assert required <= set(d)
    leg_fields = {"sheet", "start_anchor", "end_anchor", "route_context", "render_mode", "source_evidence"}
    assert leg_fields <= set(d["legs"][0])


def test_payload_is_frozen_immutable():
    p = _p("log64")
    assert isinstance(p, SeamPayload)
    with pytest.raises(Exception):
        p.eligible = False           # frozen dataclass: attribute assignment is rejected


def test_module_is_semantically_equivalent_to_scout():
    def proj_mod(p):
        return (p.shape.value,
                tuple((l.sheet, l.render_mode.value, l.start_anchor.boundary_kind.value, l.start_anchor.station,
                       l.end_anchor.boundary_kind.value, l.end_anchor.station) for l in p.legs),
                tuple(p.matchline_stations), p.cross_sheet_join)

    def proj_scout(d):
        return (d["shape"],
                tuple((l["sheet"], l["render_mode"], l["start_anchor"]["boundary"], l["start_anchor"].get("station"),
                       l["end_anchor"]["boundary"], l["end_anchor"].get("station")) for l in d["legs"]),
                tuple(d["matchline_stations"]), d["cross_sheet_join"])

    for lid in ELIGIBLE_EXEMPLARS:
        assert proj_mod(_p(lid)) == proj_scout(scout_normalize(lid, REC[lid]))


def test_module_is_pure_no_product_render_pdf_imports():
    src = Path(__file__).resolve().parent.parent / "seam" / "contract.py"
    import_lines = "\n".join(ln for ln in src.read_text(encoding="utf-8").splitlines()
                             if ln.strip().startswith(("import ", "from ")))
    for forbidden in ("truelinev2.api", "truelinev2.service", "truelinev2.match", "truelinev2.render",
                      "truelinev2.ingest", "truelinev2.extract", "truelinev2.proof", "PlanPdf"):
        assert forbidden not in import_lines, f"seam contract must stay pure (no {forbidden})"
