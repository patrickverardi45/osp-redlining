"""OWNER-PACKET-2 exemplar -> pipeline seam scout -- offline tests.

Locks the seam's pure laws: the result enum; the normalized payload represents all three exemplar
shapes (single-sheet S2S, two-sheet matchline-endpoint, two-sheet S2S + route context); the payload
is COORDINATE-FREE and preserves endpoint-anchor identity; a matchline is route context UNLESS an
anchor models it as a matchline endpoint (derived from committed anchors, never hardcoded); a bending
leg is render_mode ordered_chain_path with no straight-shortcut mode; no cross-sheet reconciliation;
and the cohort eligibility classification is HONEST (only the 3 anchor-encoded exemplars are eligible;
abstains + needs-verification stay blocked; nothing is silently upgraded). No PDF parse here.
"""
from pathlib import Path

from truelinev2.ingest.manual_adjudication import load_adjudication
from truelinev2.proof.run_exemplar_pipeline_seam_scout import (
    ALLOWED,
    EXEMPLARS,
    R_PASS,
    RENDER_MODES,
    classify_record,
    has_coord_keys,
    normalize_exemplar,
)

DOC = load_adjudication()
REC = {r["log_id"]: r for r in DOC["logs"]}


def _payload(log_id):
    return normalize_exemplar(log_id, REC[log_id])


def test_result_enum_exact():
    assert ALLOWED == {
        "EXEMPLAR_PIPELINE_SEAM_SCOUT_PASS",
        "BLOCKED_SEAM_PAYLOAD_CANNOT_REPRESENT_EXEMPLAR",
        "BLOCKED_SEAM_INVARIANT_VIOLATED",
        "BLOCKED_SEAM_CLASSIFICATION_DISHONEST",
        "BLOCKED_SEAM_CONTRADICTED_BY_PROOF_OUTPUT",
    }
    assert R_PASS == "EXEMPLAR_PIPELINE_SEAM_SCOUT_PASS"
    assert EXEMPLARS == ("log53", "log64", "log71", "log59", "log66")


def test_payload_represents_all_three_shapes():
    shapes = {_payload(lid)["shape"] for lid in EXEMPLARS}
    assert len(shapes) == 3
    assert len(_payload("log64")["legs"]) == 1          # single-sheet structure-to-structure
    assert len(_payload("log53")["legs"]) == 2          # two-sheet matchline endpoint
    assert len(_payload("log71")["legs"]) == 2          # two-sheet S2S + route context


def test_has_coord_keys_detects_planted_coordinate():
    # the guard must actually fire on a coordinate-style key (defense for the coordinate-free law)
    assert has_coord_keys({"legs": [{"start_anchor": {"xy": [1.0, 2.0]}}]}) is True
    assert has_coord_keys({"legs": [{"sheet": 24, "render_mode": "ordered_chain_path"}]}) is False


def test_payloads_are_coordinate_free():
    for lid in EXEMPLARS:
        assert has_coord_keys(_payload(lid)) is False


def test_payload_preserves_anchor_identity():
    p64 = _payload("log64")["legs"][0]
    assert (p64["start_anchor"]["structure_class"], p64["start_anchor"]["station"]) == ("installer_hh", "3+69")
    assert (p64["end_anchor"]["structure_class"], p64["end_anchor"]["station"]) == ("flower_pot", "1+00")
    p71 = _payload("log71")
    assert p71["legs"][0]["start_anchor"]["structure_class"] == "nextlink_hh"
    assert p71["legs"][0]["start_anchor"]["station"] == "7+50"
    assert p71["legs"][-1]["end_anchor"]["structure_class"] == "flower_pot"
    assert p71["legs"][-1]["end_anchor"]["station"] == "6+95"


def test_matchline_endpoint_vs_route_context_from_anchors():
    # log53: the matchline IS a modeled endpoint (end anchor boundary_kind == matchline_continuation)
    l53_ml = _payload("log53")["legs"][0]["end_anchor"]
    assert l53_ml["boundary"] == "matchline_continuation"
    assert l53_ml["modeled_endpoint"] is True
    # log71: the 5+45 matchline is intermediate ROUTE CONTEXT, never an endpoint (not carried as an anchor)
    l71_ml = _payload("log71")["legs"][0]["end_anchor"]
    assert l71_ml["boundary"] == "matchline_route_context"
    assert l71_ml["modeled_endpoint"] is False
    assert l71_ml["station"] == "5+45"


def test_bending_route_is_ordered_chain_path_no_shortcut():
    assert _payload("log71")["legs"][0]["render_mode"] == "ordered_chain_path"   # sheet 24 bends
    assert _payload("log71")["legs"][1]["render_mode"] == "continuous_corridor"  # sheet 23 vertical
    all_modes = {leg["render_mode"] for lid in EXEMPLARS for leg in _payload(lid)["legs"]}
    assert all_modes <= RENDER_MODES
    assert not any("straight" in m or "diagonal" in m for m in all_modes)


def test_no_cross_sheet_reconciliation():
    for lid in EXEMPLARS:
        p = _payload(lid)
        assert p["cross_sheet_coordinate_reconciliation"] is False
        for leg in p["legs"]:
            assert isinstance(leg["sheet"], int)        # each leg is exactly one sheet
    assert _payload("log64")["cross_sheet_join"] is None          # single sheet
    assert _payload("log53")["cross_sheet_join"] == "deferred"    # two sheets, not solved
    assert _payload("log71")["cross_sheet_join"] == "deferred"


def test_classification_is_honest_no_silent_upgrade():
    eligible = {r["log_id"] for r in DOC["logs"] if classify_record(r)[0]}
    # log66 has since been owner-confirmed (sheet 10) + source-bound + rendered + PROMOTED, so it is now
    # a seam exemplar -- anchor-eligible == the seam exemplar set exactly (nothing silently upgraded)
    assert set(EXEMPLARS) <= eligible
    assert eligible - set(EXEMPLARS) == set()                      # every anchor-eligible log is a seam exemplar
    # abstains stay blocked
    for lid in ("log5", "log31", "log38", "log43"):
        ok, _, cats = classify_record(REC[lid])
        assert ok is False and "owner_abstain" in cats
    # needs-source-verification stays blocked
    ok, _, cats = classify_record(REC["log44"])
    assert ok is False and "needs_source_verification" in cats
    # a recovered log without anchors is blocked pending its owner-reviewed bridge (not upgraded)
    ok, _, cats = classify_record(REC["log6"])
    assert ok is False and "no_endpoint_anchors_pending_owner_bridge" in cats
    # every cohort log is classified and every block carries a named category
    blocked = [r for r in DOC["logs"] if not classify_record(r)[0]]
    assert len(eligible) + len(blocked) == len(DOC["logs"])
    assert all(classify_record(r)[2] for r in blocked)


def test_scout_has_no_product_or_render_imports():
    # the scout NAMES render/source-bind primitives in its descriptive analysis strings, but must
    # never IMPORT product/render/PDF code -- so scan import statements only (not data/docstrings).
    src = Path(__file__).resolve().parent.parent / "proof" / "run_exemplar_pipeline_seam_scout.py"
    import_lines = "\n".join(ln for ln in src.read_text(encoding="utf-8").splitlines()
                             if ln.strip().startswith(("import ", "from ")))
    for forbidden in ("truelinev2.api", "truelinev2.service", "truelinev2.match",
                      "truelinev2.render", "truelinev2.ingest.pdf", "PlanPdf",
                      "render_redline_stroke"):
        assert forbidden not in import_lines, f"scout must not import {forbidden}"
