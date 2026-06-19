"""Phase-2E published-bundle contract tests (tiny temp fixtures; no 50 MB real artifacts).

Builds minimal schema-valid bundles in tmp_path with a few-byte fake PNG and proves:
valid bundles pass; tampered sha256 / wrong bytes / missing file / unsafe path (absolute, ``..``,
backslash, data/outputs) / drawn-without-artifact / covered-with-artifact / not-published all fail;
the path-safety predicate and the bundle index behave. No engine, no render, no real artifacts.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from truelinev2.contracts.published_bundle import (
    MANIFEST_FILENAME,
    build_bundle_index,
    is_safe_relative_path,
    validate_bundle,
)


def _log(lid, status, provenance, drawn=False, covered=False, blocked=False, artifacts=None):
    return {
        "log_id": lid, "parent_id": "bore_" + lid, "entry_role": "standalone",
        "status": status, "provenance": provenance,
        "drawn": drawn, "covered": covered, "blocked": blocked,
        "drawn_lane": "NEW_TARGETS" if drawn else None,
        "source_sheets": [1],
        "span": {"start_station": "0+00", "end_station": "1+00", "label": "0+00->1+00"},
        "closure": None,
        "coverage": {"covered_by": "log10"} if covered else None,
        "blocker": {"category": "OWNER_LOCKED", "name": "x", "unlock_requirement": "owner lifts"} if blocked else None,
        "artifacts": artifacts or [],
        "evidence": [{"kind": "ACCOUNTABILITY_LEDGER", "ref": "ref"}],
        "warnings": [],
    }


def _artifact(path, sha256, nbytes, published=True, placeholder=False):
    return {"kind": "FINAL_REDLINE_PNG", "path": path, "sha256": sha256,
            "bytes": nbytes, "published": published, "example_placeholder": placeholder}


def build_bundle(tmp_path, *, mutate=None):
    """Create a minimal valid published bundle; `mutate(manifest, bundle_root)` can break it."""
    root = tmp_path / "brenham_test_bundle"
    art_dir = root / "artifacts" / "logA"
    art_dir.mkdir(parents=True)
    data = b"FAKE-PNG-BYTES-logA"
    (art_dir / "logA_s1_redline_stroke.png").write_bytes(data)
    sha = hashlib.sha256(data).hexdigest()
    rel = "artifacts/logA/logA_s1_redline_stroke.png"

    manifest = {
        "schema_version": "1.0.0", "mock_example": False, "disclaimer": "test bundle",
        "project_id": "t", "project_name": "Test",
        "engine": {"branch": "b", "engine_head": "head1", "render_commit": "rc1",
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
        "logs": [
            _log("logA", "DRAWN_REDLINE", "DETERMINISTIC_AUTO", drawn=True,
                 artifacts=[_artifact(rel, sha, len(data))]),
            _log("log14", "COVERED_BY_EXISTING_REDLINE", "COVERED_BY_EXISTING_REDLINE", covered=True),
            _log("logZ", "OWNER_LOCKED_ABSTAIN", "BLOCKED_OWNER_LOCKED", blocked=True),
        ],
    }
    if mutate:
        mutate(manifest, root)
    (root / MANIFEST_FILENAME).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return root


# --------------------------------------------------------------------------- #
def test_valid_bundle_passes(tmp_path):
    rep = validate_bundle(build_bundle(tmp_path))
    assert rep["valid"] is True, rep
    assert rep["artifact_count"] == 1
    assert rep["total_bytes"] == len(b"FAKE-PNG-BYTES-logA")
    assert rep["static_serving_safe"] is True
    assert rep["checksum_mismatches"] == [] and rep["missing_files"] == [] and rep["unsafe_paths"] == []
    assert len(rep["manifest_sha256"]) == 64


def test_index_reflects_manifest_and_validation(tmp_path):
    root = build_bundle(tmp_path)
    rep = validate_bundle(root)
    idx = build_bundle_index(root, rep, generated_at="2026-06-19T00:00:00Z")
    assert idx["run_label"] == "brenham_test_bundle"
    assert idx["project_id"] == "t" and idx["schema_version"] == "1.0.0"
    assert idx["engine_head"] == "head1" and idx["render_commit"] == "rc1"
    assert idx["manifest_sha256"] == rep["manifest_sha256"]
    assert idx["artifact_count"] == 1 and idx["total_bytes"] == len(b"FAKE-PNG-BYTES-logA")
    assert idx["validation"]["valid"] is True and idx["validation"]["static_serving_safe"] is True
    assert idx["generated_at"] == "2026-06-19T00:00:00Z"


def test_tampered_sha256_fails(tmp_path):
    def mut(m, root):
        m["logs"][0]["artifacts"][0]["sha256"] = "0" * 64
    rep = validate_bundle(build_bundle(tmp_path, mutate=mut))
    assert rep["valid"] is False and rep["checksum_mismatches"]


def test_wrong_bytes_fails(tmp_path):
    def mut(m, root):
        m["logs"][0]["artifacts"][0]["bytes"] = 99999
    rep = validate_bundle(build_bundle(tmp_path, mutate=mut))
    assert rep["valid"] is False and rep["checksum_mismatches"]


def test_missing_file_fails(tmp_path):
    def mut(m, root):
        (root / "artifacts" / "logA" / "logA_s1_redline_stroke.png").unlink()
    rep = validate_bundle(build_bundle(tmp_path, mutate=mut))
    assert rep["valid"] is False and rep["missing_files"]


def test_absolute_path_is_unsafe(tmp_path):
    def mut(m, root):
        m["logs"][0]["artifacts"][0]["path"] = "C:/evil/x.png"
    rep = validate_bundle(build_bundle(tmp_path, mutate=mut))
    assert rep["valid"] is False and rep["unsafe_paths"] and rep["static_serving_safe"] is False


def test_traversal_and_backslash_and_dataoutputs_unsafe(tmp_path):
    for bad in ("../escape.png", "artifacts\\logA\\x.png", "data/outputs/x.png", "/abs/x.png"):
        def mut(m, root, bad=bad):
            m["logs"][0]["artifacts"][0]["path"] = bad
        rep = validate_bundle(build_bundle(tmp_path / bad.replace("/", "_").replace("\\", "_"), mutate=mut))
        assert rep["valid"] is False and rep["unsafe_paths"], bad


def test_not_published_or_placeholder_fails(tmp_path):
    def mut(m, root):
        m["logs"][0]["artifacts"][0]["published"] = False
        m["logs"][0]["artifacts"][0]["example_placeholder"] = True
    rep = validate_bundle(build_bundle(tmp_path, mutate=mut))
    assert rep["valid"] is False and rep["structure_errors"]


def test_drawn_without_artifact_and_covered_with_artifact_fail(tmp_path):
    def mut1(m, root):
        m["logs"][0]["artifacts"] = []  # drawn but no artifact
    assert validate_bundle(build_bundle(tmp_path / "a", mutate=mut1))["valid"] is False

    def mut2(m, root):
        m["logs"][1]["artifacts"] = [_artifact("artifacts/log14/x.png", "0" * 64, 1)]  # covered w/ artifact
    rep = validate_bundle(build_bundle(tmp_path / "b", mutate=mut2))
    assert rep["valid"] is False and any("covered/blocked" in e for e in rep["structure_errors"])


def test_missing_manifest_fails(tmp_path):
    root = tmp_path / "empty_bundle"
    root.mkdir()
    rep = validate_bundle(root)
    assert rep["valid"] is False and rep["manifest_present"] is False


def test_path_safety_predicate():
    assert is_safe_relative_path("artifacts/logA/logA_s1_redline_stroke.png")
    for bad in ("", "/abs", "C:/x", "a\\b", "../x", "a/../b", "data/outputs/x", "a//b", "./x"):
        assert not is_safe_relative_path(bad), bad
