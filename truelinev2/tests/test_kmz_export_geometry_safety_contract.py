"""Contract tests: the kmz_export geometry-safety contract. Pure stdlib + tmp_path; no engine/render/
wiring. Generic ids/values only. The PRIMARY proof: a real (sheet/station/pixel) v2 manifest is BLOCKED
(UNSUPPORTED_PIXEL_ONLY) — the system abstains rather than fake coordinates. Synthetic geospatial geometry
appears ONLY in pure-function / future-path fixtures (it never exists in a real v2 manifest today).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from truelinev2.contracts.customer_project import create_customer_project
from truelinev2.contracts.processing_job import create_job, load_job, set_output_slot
from truelinev2.contracts.upload_pipeline import accept_upload
from truelinev2.contracts.extracted_row import CONFIRMED, OCR, new_extracted_row
from truelinev2.contracts.reviewed_bore_log import (
    GROUPING_CONFIRMED, SEPARATE_BORE, add_extracted_rows, create_reviewed_bore_log,
    define_segment_group, review_row_in_log, set_grouping_status,
)
from truelinev2.contracts.manifest_handoff import finalize_handoff, record_handoff_attempt
from truelinev2.contracts.published_bundle import sha256_file
from truelinev2.contracts.kmz_export import (
    AMBIGUOUS_CRS,
    BLOCKED,
    COORDINATE_UNCERTAINTY,
    EXPORT_STROKE_KML_COLOR,
    EXPORTABLE,
    GEOREFERENCED_SHEET,
    GEOSPATIAL_COORDINATES,
    MISSING_MANIFEST_SLOT,
    MANIFEST_NOT_RESOLVABLE,
    SOURCE_CONFLICT,
    UNSUPPORTED_PIXEL_ONLY,
    UNTRUSTED_HANDOFF,
    build_kml,
    classify_geometry_basis,
    evaluate_export,
    extract_exportable_features,
)

AT = "2026-06-21T00:00:00Z"
BY = "operator-1"
CP = "cp-0001"
JOB = "job-0001"
RBL = "rbl-0001"
RUN = "run-0001"


def _codes(record):
    return {b["code"] for b in record["blockers"]}


# --------------------------------------------------------------------------- #
# Generic PIXEL-ONLY engine-output bundle (the real shape: stations/sheets/PNG, NO geometry).
# --------------------------------------------------------------------------- #
def _log(lid, status, prov, drawn=False, covered=False, blocked=False, artifacts=None):
    return {"log_id": lid, "parent_id": "b_" + lid, "entry_role": "standalone",
            "status": status, "provenance": prov, "drawn": drawn, "covered": covered,
            "blocked": blocked, "drawn_lane": "NEW_TARGETS" if drawn else None, "source_sheets": [1],
            "span": {"start_station": "0+00", "end_station": "1+00", "label": "0+00->1+00"},
            "closure": None, "coverage": {"covered_by": "logX"} if covered else None,
            "blocker": {"category": "OWNER_LOCKED", "name": "n", "unlock_requirement": "owner lifts"}
            if blocked else None,
            "artifacts": artifacts or [],
            "evidence": [{"kind": "ACCOUNTABILITY_LEDGER", "ref": "r"}], "warnings": []}


def _build_pixel_only_bundle(root):
    root = Path(root)
    art_dir = root / "artifacts" / "logA"
    art_dir.mkdir(parents=True)
    data = b"FAKE-PNG-A"
    (art_dir / "logA_s1_redline_stroke.png").write_bytes(data)
    art = {"kind": "FINAL_REDLINE_PNG", "path": "artifacts/logA/logA_s1_redline_stroke.png",
           "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data),
           "published": True, "example_placeholder": False}
    manifest = {
        "schema_version": "1.0.0", "mock_example": False, "disclaimer": "t",
        "project_id": "proj-a", "project_name": "Project A",
        "engine": {"branch": "feat/truelinev2", "engine_head": "h", "render_commit": "rc-0",
                   "generated_from": "test"},
        "summary": {"total_logs": 3, "drawn_count": 1, "covered_count": 1, "blocked_count": 1,
                    "frontier": "1/3"},
        "status_counts": {"DRAWN_REDLINE": 1, "COVERED_BY_EXISTING_REDLINE": 1,
                          "OWNER_LOCKED_ABSTAIN": 1, "SOURCE_GAP_BLOCKED": 0,
                          "MISSING_SOURCE_SHEET_BLOCKED": 0},
        "provenance_counts": {"DETERMINISTIC_AUTO": 1, "OWNER_CONFIRMED_HUMAN_ADJUSTABLE": 0,
                              "COVERED_BY_EXISTING_REDLINE": 1, "BLOCKED_OWNER_LOCKED": 1,
                              "BLOCKED_SOURCE_GAP": 0, "BLOCKED_MISSING_SOURCE": 0},
        "consumption_rules": ["consume the manifest"],
        "logs": [_log("logA", "DRAWN_REDLINE", "DETERMINISTIC_AUTO", drawn=True, artifacts=[art]),
                 _log("logC", "COVERED_BY_EXISTING_REDLINE", "COVERED_BY_EXISTING_REDLINE", covered=True),
                 _log("logB", "OWNER_LOCKED_ABSTAIN", "BLOCKED_OWNER_LOCKED", blocked=True)],
    }
    (root / "redline_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return root


def _spine_with_handoff(tmp_path):
    """Full core spine -> a job with VALIDATED redline_manifest + artifact_bundle slots (pixel-only)."""
    create_customer_project(tmp_path, CP, "Label", AT)
    create_job(tmp_path, CP, JOB, AT, BY)
    up = accept_upload(tmp_path, CP, JOB, kind="BORE_LOG", filename="log.csv", content=b"a,b", stored_at=AT)
    create_reviewed_bore_log(tmp_path, CP, JOB, up["upload_id"], RBL, at=AT, by=BY)
    add_extracted_rows(tmp_path, CP, JOB, RBL, [new_extracted_row(
        "row-1", up["upload_id"], raw={}, normalized={}, extraction_method=OCR, at=AT, by=BY)],
        at=AT, by=BY)
    review_row_in_log(tmp_path, CP, JOB, RBL, "row-1", CONFIRMED, at=AT, by=BY)
    define_segment_group(tmp_path, CP, JOB, RBL, "grp-1", ["row-1"], SEPARATE_BORE, at=AT, by=BY)
    set_grouping_status(tmp_path, CP, JOB, RBL, "grp-1", GROUPING_CONFIRMED, at=AT, by=BY)
    record_handoff_attempt(tmp_path, CP, JOB, RBL, RUN, engine_run_status="completed", at=AT, by=BY)
    finalize_handoff(tmp_path, CP, JOB, RUN, _build_pixel_only_bundle(tmp_path / "engine_out"), at=AT, by=BY)
    return up["upload_id"]


# --------------------------------------------------------------------------- #
# PRIMARY: real pixel-only manifests are BLOCKED (the system abstains, never fakes).
# --------------------------------------------------------------------------- #
def test_real_pixel_only_manifest_is_blocked(tmp_path):
    _spine_with_handoff(tmp_path)
    rec = evaluate_export(tmp_path, CP, JOB)
    assert rec["status"] == BLOCKED
    assert rec["geometry_basis"] == UNSUPPORTED_PIXEL_ONLY
    assert _codes(rec) == {UNSUPPORTED_PIXEL_ONLY}
    assert rec["kml"] is None and rec["kml_sha256"] is None and rec["kmz_package"] is None


def test_missing_manifest_slot_blocks(tmp_path):
    create_customer_project(tmp_path, CP, "Label", AT)
    create_job(tmp_path, CP, JOB, AT, BY)
    rec = evaluate_export(tmp_path, CP, JOB)
    assert rec["status"] == BLOCKED and MISSING_MANIFEST_SLOT in _codes(rec)


def test_untrusted_handoff_blocks(tmp_path):
    _spine_with_handoff(tmp_path)
    # tamper the stored job: mark the manifest slot ref un-validated
    jpath = (Path(tmp_path) / "customer_projects" / CP / "processing_jobs" / JOB / "_processing_job.json")
    job = json.loads(jpath.read_text())
    job["slots"]["redline_manifest"]["ref"]["validation_status"] = "UNVALIDATED"
    jpath.write_text(json.dumps(job, indent=2), encoding="utf-8")
    rec = evaluate_export(tmp_path, CP, JOB)
    assert rec["status"] == BLOCKED and UNTRUSTED_HANDOFF in _codes(rec)


def test_manifest_sha_drift_blocks(tmp_path):
    _spine_with_handoff(tmp_path)
    # tamper the durably stored manifest so its sha256 no longer matches the slot
    bid = load_job(tmp_path, CP, JOB)["slots"]["artifact_bundle"]["ref"]["bundle_id"]
    stored = (Path(tmp_path) / "customer_projects" / CP / "processing_jobs" / JOB
              / "bundle_store" / "bundles" / bid / "redline_manifest.json")
    stored.write_text(stored.read_text() + "\n ", encoding="utf-8")     # change bytes -> sha drift
    rec = evaluate_export(tmp_path, CP, JOB)
    assert rec["status"] == BLOCKED and MANIFEST_NOT_RESOLVABLE in _codes(rec)


def test_uploaded_gis_route_is_ignored(tmp_path):
    _spine_with_handoff(tmp_path)
    # an uploaded GIS_ROUTE (KMZ) must NEVER be treated as approved output / re-exported
    accept_upload(tmp_path, CP, JOB, kind="GIS_ROUTE", filename="route.kmz",
                  content=b"PK\x03\x04 fake-kmz", stored_at=AT)
    rec = evaluate_export(tmp_path, CP, JOB)
    assert rec["status"] == BLOCKED and rec["geometry_basis"] == UNSUPPORTED_PIXEL_ONLY
    assert "route.kmz" not in json.dumps(rec)                          # upload never referenced


# --------------------------------------------------------------------------- #
# Pure-function classifier: stations/sheets/pixels are NEVER geospatial.
# --------------------------------------------------------------------------- #
def _drawn(log_id, geometry=None, closure=None):
    return {"log_id": log_id, "drawn": True, "covered": False, "blocked": False,
            "status": "DRAWN_REDLINE", "span": {"start_station": "0+00", "end_station": "9+99", "label": "x"},
            "source_sheets": [1, 2, 3], "closure": closure, "geometry": geometry}


def _geom(coords=None, crs="EPSG:4326", source="ENGINE_REVIEWED", confidence="HIGH", kind="LineString"):
    return {"crs": crs, "datum": "WGS84", "units": "degrees", "kind": kind,
            "coordinates": coords or [[0.0, 0.0], [1.0, 1.0]], "source": source, "confidence": confidence}


def test_classify_stations_only_is_pixel_only():
    # rich span + source_sheets but NO geometry -> pixel-only (stations are not coordinates)
    assert classify_geometry_basis({"logs": [_drawn("logA"), _drawn("logB")]}) == UNSUPPORTED_PIXEL_ONLY


def test_classify_geospatial_and_georeferenced():
    assert classify_geometry_basis({"logs": [_drawn("logA", geometry=_geom())]}) == GEOSPATIAL_COORDINATES
    # a georeference transform without per-feature coords is recognized but unresolved
    assert classify_geometry_basis({"logs": [_drawn("logA")], "georeference": {"transform": "x"}}) \
        == GEOREFERENCED_SHEET


def test_extract_feature_blockers():
    m = {"logs": [
        _drawn("good", geometry=_geom()),
        _drawn("badcrs", geometry=_geom(crs="EPSG:3857")),
        _drawn("lowconf", geometry=_geom(confidence="LOW")),
        _drawn("badsrc", geometry=_geom(source="UPLOADED_KMZ")),
    ]}
    _feats, blockers = extract_exportable_features(m, source_manifest_id="m1", source_artifact_bundle_id="b1")
    codes = {b["code"] for b in blockers}
    assert codes == {AMBIGUOUS_CRS, COORDINATE_UNCERTAINTY, SOURCE_CONFLICT}


def test_build_kml_is_deterministic_and_red_and_traceable():
    feats, blockers = extract_exportable_features(
        {"logs": [_drawn("logA", geometry=_geom())]}, source_manifest_id="m1", source_artifact_bundle_id="b1")
    assert blockers == []
    k1 = build_kml(feats, source_manifest_id="m1", source_artifact_bundle_id="b1")
    k2 = build_kml(feats, source_manifest_id="m1", source_artifact_bundle_id="b1")
    assert k1 == k2                                                    # deterministic
    assert EXPORT_STROKE_KML_COLOR in k1 and "<LineString>" in k1     # red styling + geometry
    assert "source_manifest_id" in k1 and "feat-logA" in k1           # traceability


# --------------------------------------------------------------------------- #
# FUTURE export path through evaluate_export — synthetic geometry ONLY (rule 7: never implies real
# v2 manifests carry geometry; proves the wiring for when the engine emits verified coordinates).
# --------------------------------------------------------------------------- #
def test_evaluate_export_exportable_with_synthetic_future_geometry(tmp_path):
    create_customer_project(tmp_path, CP, "Label", AT)
    create_job(tmp_path, CP, JOB, AT, BY)
    bid = "proj-a-rc-0-feeddeadbeef"
    broot = (Path(tmp_path) / "customer_projects" / CP / "processing_jobs" / JOB
             / "bundle_store" / "bundles" / bid)
    broot.mkdir(parents=True)
    manifest = {"logs": [_drawn("logA", geometry=_geom(), closure={"drawn_ft": 247.0})]}  # synthetic future
    mpath = broot / "redline_manifest.json"
    mpath.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    msha = sha256_file(mpath)
    set_output_slot(tmp_path, CP, JOB, "redline_manifest",
                    {"manifest_id": msha, "manifest_sha256": msha, "bundle_id": bid,
                     "validation_status": "VALIDATED"}, at=AT, by=BY)
    set_output_slot(tmp_path, CP, JOB, "artifact_bundle",
                    {"bundle_id": bid, "manifest_sha256": msha, "validation_status": "VALIDATED"},
                    at=AT, by=BY)
    rec = evaluate_export(tmp_path, CP, JOB)
    assert rec["status"] == EXPORTABLE and rec["geometry_basis"] == GEOSPATIAL_COORDINATES
    assert rec["crs"]["crs"] == "EPSG:4326"
    assert rec["kml"] and EXPORT_STROKE_KML_COLOR in rec["kml"] and rec["kml_sha256"]
    assert rec["kmz_package"]["members"][0]["sha256"] == rec["kml_sha256"]   # interface descriptor only
    assert rec["features"][0]["length_ft"] == 247.0
    # export_package slot is NEVER touched by this lane; no binary KMZ written
    assert load_job(tmp_path, CP, JOB)["slots"]["export_package"] is None
    assert not any(p.suffix == ".kmz" for p in broot.rglob("*"))
