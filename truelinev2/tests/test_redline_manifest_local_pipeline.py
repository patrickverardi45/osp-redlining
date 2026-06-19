"""Phase-2F local pipeline tests (synthetic fixtures + temp dirs; no real artifacts, no render).

Covers the runner's new orchestration units without the 50 MB real artifacts or any render:
verify-artifacts-exist, semantic-preservation checks, and the publish-existing chain end-to-end
(assemble -> publish -> bundle-validate) on a tiny synthetic project, plus validate-existing run().
"""
from __future__ import annotations

import json
from pathlib import Path

from truelinev2.contracts.published_bundle import MANIFEST_FILENAME, validate_bundle
from truelinev2.proof.run_redline_manifest_local_pipeline import (
    assemble_and_publish,
    check_semantics,
    run,
    verify_artifacts_exist,
)


def test_verify_artifacts_exist(tmp_path):
    present = tmp_path / "a.png"
    present.write_bytes(b"x")
    count, missing = verify_artifacts_exist(
        {"logA": [str(present)], "logB": [str(tmp_path / "gone.png")]}, str(tmp_path))
    assert count == 2
    assert len(missing) == 1 and "logB" in missing[0]


def test_check_semantics_present_and_absent():
    def lg(lid, **kw):
        base = {"log_id": lid, "drawn": False, "covered": False, "blocked": False,
                "artifacts": [], "warnings": [], "status": "X", "provenance": "Y",
                "coverage": None, "blocker": None}
        base.update(kw)
        return base
    manifest = {"logs": [
        lg("log3", drawn=True, provenance="OWNER_CONFIRMED_HUMAN_ADJUSTABLE"),
        lg("log7", drawn=True, warnings=["... PARTIAL representative ..."]),
        lg("log14", covered=True, status="COVERED_BY_EXISTING_REDLINE",
           coverage={"covered_by": "log10"}),
    ] + [lg(b, blocked=True, blocker={"category": "OWNER_LOCKED", "name": "n",
                                      "unlock_requirement": "owner lifts"})
         for b in ("log5", "log31", "log38", "log43", "log15", "log16", "log57")]}
    sem = check_semantics(manifest)
    assert sem["blocked_preserved"] is True
    assert sem["covered_log14_preserved"] is True
    assert sem["log3_owner_confirmed"] is True
    assert sem["log7_partial_warning"] is True
    # tolerant: absent logs -> None
    assert check_semantics({"logs": []}) == {
        "blocked_preserved": None, "covered_log14_preserved": None,
        "log3_owner_confirmed": None, "log7_partial_warning": None}


# --- tiny synthetic project for the publish-existing chain --------------------
def _log(lid, status, prov, drawn=False, covered=False, blocked=False):
    return {"log_id": lid, "parent_id": "b_" + lid, "entry_role": "standalone",
            "status": status, "provenance": prov, "drawn": drawn, "covered": covered,
            "blocked": blocked, "drawn_lane": "NEW_TARGETS" if drawn else None,
            "source_sheets": [1],
            "span": {"start_station": "0+00", "end_station": "1+00", "label": "0+00->1+00"},
            "closure": None, "coverage": {"covered_by": "log10"} if covered else None,
            "blocker": {"category": "OWNER_LOCKED", "name": "n", "unlock_requirement": "owner lifts"} if blocked else None,
            "artifacts": ([{"kind": "FINAL_REDLINE_PNG", "path": "X", "sha256": None,
                            "example_placeholder": True}] if drawn else []),
            "evidence": [{"kind": "ACCOUNTABILITY_LEDGER", "ref": "r"}], "warnings": []}


def _base():
    return {"schema_version": "1.0.0", "mock_example": True, "disclaimer": "t",
            "project_id": "t", "project_name": "T",
            "engine": {"branch": "b", "engine_head": "h", "render_commit": "rc", "generated_from": "g"},
            "summary": {"total_logs": 3, "drawn_count": 2, "covered_count": 0, "blocked_count": 1,
                        "frontier": "2/3"},
            "status_counts": {"DRAWN_REDLINE": 2, "COVERED_BY_EXISTING_REDLINE": 0,
                              "OWNER_LOCKED_ABSTAIN": 1, "SOURCE_GAP_BLOCKED": 0,
                              "MISSING_SOURCE_SHEET_BLOCKED": 0},
            "provenance_counts": {"DETERMINISTIC_AUTO": 2, "OWNER_CONFIRMED_HUMAN_ADJUSTABLE": 0,
                                  "COVERED_BY_EXISTING_REDLINE": 0, "BLOCKED_OWNER_LOCKED": 1,
                                  "BLOCKED_SOURCE_GAP": 0, "BLOCKED_MISSING_SOURCE": 0},
            "consumption_rules": ["consume the manifest"],
            "logs": [_log("logNEW", "DRAWN_REDLINE", "DETERMINISTIC_AUTO", drawn=True),
                     _log("logALR", "DRAWN_REDLINE", "DETERMINISTIC_AUTO", drawn=True),
                     _log("logBLK", "OWNER_LOCKED_ABSTAIN", "BLOCKED_OWNER_LOCKED", blocked=True)]}


def _make_sources(tmp_path):
    sweep_dir = tmp_path / "sweep"
    sweep_dir.mkdir()
    (sweep_dir / "logNEW_s1_redline_stroke.png").write_bytes(b"NEW-bytes")
    canon_root = tmp_path / "canon"
    (canon_root / "logALR").mkdir(parents=True)
    (canon_root / "logALR" / "logALR_s1_redline_stroke.png").write_bytes(b"ALR-bytes")
    sweep = {"verdicts": {"logNEW": {"artifacts": [str(sweep_dir / "logNEW_s1_redline_stroke.png")]}}}
    canon = {"render": [{"log_id": "logALR", "render_status": "FULL",
                         "artifacts": [{"rel": "logALR/logALR_s1_redline_stroke.png"}]}]}
    return sweep, canon, canon_root


def test_publish_existing_chain_end_to_end(tmp_path):
    sweep, canon, canon_root = _make_sources(tmp_path)
    result = assemble_and_publish(_base(), sweep, canon, str(canon_root),
                                  str(tmp_path / "pub"), "tinyrun", str(tmp_path))
    m = result["manifest"]
    assert m["mock_example"] is False
    by = {l["log_id"]: l for l in m["logs"]}
    assert len(by["logNEW"]["artifacts"]) == 1 and by["logNEW"]["artifacts"][0]["published"] is True
    assert len(by["logALR"]["artifacts"]) == 1
    assert by["logBLK"]["artifacts"] == []
    rep = validate_bundle(result["publish_dir"])
    assert rep["valid"] is True and rep["artifact_count"] == 2 and rep["static_serving_safe"] is True


def test_run_validate_existing_on_tiny_bundle(tmp_path):
    sweep, canon, canon_root = _make_sources(tmp_path)
    result = assemble_and_publish(_base(), sweep, canon, str(canon_root),
                                  str(tmp_path / "pub"), "tinyrun", str(tmp_path))
    report, ok = run("validate-existing", "unused", result["publish_dir"])
    assert ok is True
    assert report["run_mode"] == "validate-existing"
    assert report["bundle_validation"] == "VALID"
    assert report["mock_example_false"] is True
    assert report["render_used"] is False
    assert report["artifact_count"] == 2
    assert Path(report["manifest_path"]).name == MANIFEST_FILENAME
