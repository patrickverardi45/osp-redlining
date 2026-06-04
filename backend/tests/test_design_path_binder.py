"""Contract tests for the pure design_path_binder (no production wiring, no rendering).

Proves the deterministic contract: bore_truth + resolver_proof + design_refs ->
BoundDesignPath (BOUND) or ABSTAIN.

  * bore_log7 positive control -> BOUND, route_469, within tolerance (faithful fixture: the
    KMZ route_catalog + AP-163 anchor live in live STATE, not in _redline_data, so they are
    supplied as inputs — the binder is pure and consumes design_refs).
  * log66 -> ABSTAIN (real frame_resolutions entry + real vendored anchor tables): the proven
    HH/station endpoints carry no AP/SPLICE identity, so no station-indexed design geometry
    binds them.
  * log58 -> ABSTAIN cross_sheet_stitch_not_implemented (real matchline seam).

Run from repo root:  python -m pytest backend/tests/test_design_path_binder.py -v
"""
from __future__ import annotations

import json
import os

from app.core import pdf_first_adapter as adapter
from app.core.redline_pdf_first.geometry import design_path_binder as B
from app.core.redline_pdf_first.geometry import identity_binder

DATA = adapter._DEFAULT_ANALYSIS_DIR


def _resolution(bore_id):
    fr = json.load(open(os.path.join(DATA, "_matchline", "frame_resolutions.json"), encoding="utf-8"))
    return next(r for r in fr["resolutions"] if r["bore_id"] == bore_id)


# ── 1) bore_log7 positive control -> BOUND, route_469, within tolerance ───────────────────────
def test_bore_log7_positive_control_bound_route469():
    bore = {"bore_log_id": "bore_log7", "source_file": "bore_log7.xlsx",
            "footage_ft": 451.0, "boc_ft": None}
    proof = {"proof_class": "AP_ANCHORED", "home_sheet": 10, "seam": None, "anchors": [
        {"role": "start", "label": "SPLICE LOC 46", "sheet": 10},
        {"role": "end", "label": "STA 4+51 TERMINAL PORT HH AP-163", "sheet": 10}]}
    refs = {
        "anchor_tables": {"anchors": {
            ("AP", "163", 10): [{"kind": "AP", "id": "163", "sheet": 10, "sta": 451.0,
                                 "coord": [-96.38598520, 30.15819527]}],
            ("SPLICE", "LOC46", 10): [{"kind": "SPLICE", "id": "LOC46", "sheet": 10, "sta": 0.0,
                                       "coord": [-96.38630000, 30.15710000]}],
        }, "station_model": {}},
        "route_catalog": [{"route_id": "route_469", "terminus": {"kind": "AP", "id": "163"},
                           "length_ft": 459.0,
                           "coords": [[-96.38630000, 30.15710000], [-96.38598520, 30.15819527]]}],
    }
    out = B.bind_design_path(bore, proof, refs)
    assert out["status"] == B.STATUS_BOUND, out
    assert out["map_path"]["route_id"] == "route_469"
    assert out["binding"]["geometry_source"] == "kmz_route:route_469"
    assert out["binding"]["end"]["identity"] == {"kind": "AP", "id": "163"}
    assert out["binding"]["start"]["identity"] == {"kind": "SPLICE_LOC", "id": "LOC46"}
    assert out["validation"]["within_tol"] is True
    assert 0.95 <= out["validation"]["ratio"] <= 1.0       # 451/459 = 0.982
    assert out["field_truth"] == B.FIELD_TRUTH_CONFIRMED
    assert out["billable"] is True
    assert out["draw_decision"] == B.DRAW_GEOMETRY_BOUND
    assert out["pdf_path"] is None                          # page model deferred (documented)
    assert out["abstain_reason"] is None


# ── 2) log66 -> ABSTAIN endpoint-not-anchored (real resolution + real vendored anchors) ───────
def test_log66_abstains_no_anchor_bind():
    bore = {"bore_log_id": "bore_log66", "source_file": "bore_log66.xlsx",
            "footage_ft": 55.0, "hh_hh_ft": 55, "boc_ft": 10}
    proof = _resolution("bore_log66")                       # real: equation start + station end (HH); NO seam, NO AP
    refs = {"anchor_tables": identity_binder.load_tables(DATA)}   # real vendored anchors; NO route_catalog
    out = B.bind_design_path(bore, proof, refs)
    assert out["status"] == B.STATUS_ABSTAIN, out
    assert out["abstain_reason"] == B.ABSTAIN_ENDPOINT_NOT_ANCHORED, out
    assert out["binding"]["end"]["identity"] is None        # HH/station endpoints carry no AP/SPLICE id
    assert out["binding"]["start"]["identity"] is None
    assert "no station-indexed design geometry" in out["abstain_detail"]["note"]
    # PRODUCT CORRECTION: ABSTAIN means "do not auto-draw", NOT "this bore does not count".
    assert out["field_truth"] == B.FIELD_TRUTH_CONFIRMED    # the 55' HH-HH bore is real/billable
    assert out["billable"] is True
    assert out["draw_decision"] == B.DRAW_NEEDS_REVIEW       # surfaces for review; never erased


# ── 3) log58 -> ABSTAIN cross_sheet_stitch_not_implemented (real matchline seam) ──────────────
def test_log58_abstains_cross_sheet():
    bore = {"bore_log_id": "bore_log58", "source_file": "bore_log58.xlsx", "footage_ft": 236.0}
    proof = _resolution("bore_log58")                       # real: has matchline_seam
    out = B.bind_design_path(bore, proof, {"anchor_tables": identity_binder.load_tables(DATA)})
    assert out["status"] == B.STATUS_ABSTAIN
    assert out["abstain_reason"] == B.ABSTAIN_CROSS_SHEET, out
    assert out["field_truth"] == B.FIELD_TRUTH_CONFIRMED    # field truth preserved across the seam
    assert out["draw_decision"] == B.DRAW_NEEDS_REVIEW


# ── 4) both endpoints bound but NO route geometry -> ABSTAIN no_design_geometry ───────────────
def test_endpoints_bound_but_no_route_abstains():
    bore = {"bore_log_id": "x", "source_file": "x.xlsx", "footage_ft": 451.0}
    proof = {"home_sheet": 10, "seam": None, "anchors": [
        {"role": "start", "label": "AP-161", "sheet": 10},
        {"role": "end", "label": "AP-163", "sheet": 10}]}
    refs = {"anchor_tables": {"anchors": {
        ("AP", "163", 10): [{"coord": [-96.3, 30.1], "sta": 451.0}],
        ("AP", "161", 10): [{"coord": [-96.31, 30.09], "sta": 0.0}]}}}   # no route_catalog
    out = B.bind_design_path(bore, proof, refs)
    assert out["status"] == B.STATUS_ABSTAIN
    assert out["abstain_reason"] == B.ABSTAIN_NO_DESIGN_GEOMETRY, out


# ── 5) as-built footage diverges from design length -> ABSTAIN length_mismatch ────────────────
def test_length_mismatch_abstains():
    bore = {"bore_log_id": "x", "source_file": "x.xlsx", "footage_ft": 100.0}   # 100 vs 459
    proof = {"home_sheet": 10, "seam": None, "anchors": [
        {"role": "start", "label": "AP-161", "sheet": 10},
        {"role": "end", "label": "AP-163", "sheet": 10}]}
    refs = {"anchor_tables": {"anchors": {
                ("AP", "163", 10): [{"coord": [-96.3, 30.1], "sta": 451.0}],
                ("AP", "161", 10): [{"coord": [-96.31, 30.09], "sta": 0.0}]}},
            "route_catalog": [{"route_id": "route_469", "terminus": {"kind": "AP", "id": "163"},
                               "length_ft": 459.0, "coords": []}]}
    out = B.bind_design_path(bore, proof, refs)
    assert out["status"] == B.STATUS_ABSTAIN
    assert out["abstain_reason"] == B.ABSTAIN_LENGTH_MISMATCH, out


# ── 6) ambiguous anchor (two distinct coords for one identity) is rejected -> ABSTAIN ─────────
def test_ambiguous_anchor_rejected():
    bore = {"bore_log_id": "x", "source_file": "x.xlsx", "footage_ft": 451.0}
    proof = {"home_sheet": 10, "seam": None, "anchors": [
        {"role": "start", "label": "AP-161", "sheet": 10},
        {"role": "end", "label": "AP-163", "sheet": 10}]}
    refs = {"anchor_tables": {"anchors": {
        ("AP", "163", 10): [{"coord": [-96.3, 30.1], "sta": 451.0},
                            {"coord": [-96.9, 30.9], "sta": 451.0}],   # two distinct coords -> ambiguous
        ("AP", "161", 10): [{"coord": [-96.31, 30.09], "sta": 0.0}]}}}
    out = B.bind_design_path(bore, proof, refs)
    assert out["status"] == B.STATUS_ABSTAIN
    assert out["abstain_reason"] == B.ABSTAIN_ENDPOINT_NOT_ANCHORED, out


# ── 7) schema shape + no-endpoints abstain ───────────────────────────────────────────────────
def test_schema_shape_and_empty():
    out = B.bind_design_path({}, {}, {})
    assert out["schema_version"] == "design-path-binder-1"
    assert out["status"] == B.STATUS_ABSTAIN
    assert out["abstain_reason"] == B.ABSTAIN_NO_ENDPOINTS
    assert out["field_truth"] == B.FIELD_TRUTH_ABSENT       # no real bore in {} -> not billable
    assert out["billable"] is False
    assert out["draw_decision"] == B.DRAW_ABSTAIN           # nothing to bill/review -> hard abstain
    for k in ("field_truth", "billable", "draw_decision",
              "binding", "pdf_path", "map_path", "validation", "evidence", "abstain_reason"):
        assert k in out


# ── 8) product invariant: abstaining from auto-draw NEVER erases a confirmed field bore ───────
def test_field_truth_preserved_when_auto_draw_abstains():
    bore = {"bore_log_id": "bore_log66", "source_file": "bore_log66.xlsx",
            "footage_ft": 55.0, "boc_ft": 10}
    out = B.bind_design_path(bore, _resolution("bore_log66"),
                             {"anchor_tables": identity_binder.load_tables(DATA)})
    # real/billable field truth is preserved...
    assert out["billable"] is True
    assert out["field_truth"] == B.FIELD_TRUTH_CONFIRMED
    # ...auto-draw is withheld (no guessed line) but the bore is surfaced for review...
    assert out["draw_decision"] == B.DRAW_NEEDS_REVIEW
    assert out["draw_decision"] != B.DRAW_GEOMETRY_BOUND
    # ...with a clear reason + an explicit "not erased" note (so it does not disappear / unbill).
    assert out["abstain_reason"]
    assert out["evidence"]["field_truth_note"].startswith("bore log is a confirmed billable")
