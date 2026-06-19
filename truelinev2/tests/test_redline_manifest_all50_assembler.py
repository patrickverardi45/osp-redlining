"""Phase-2D all-50 assembler unit tests (synthetic; no real artifacts, no publish, no render).

Locks the new assembler logic: merging the sweep `verdicts[*].artifacts` + the canonical
report into one {log: [paths]} map, deriving PARTIAL logs from the canonical report, and
rebuilding a publisher input that replaces drawn-log artifacts with real records, keeps
covered/blocked empty, flags PARTIAL logs, leaves status/counts untouched, and refuses a drawn
log with no real artifact. Pure functions on synthetic dicts -- no engine, no gitignored data.
"""
from __future__ import annotations

import pytest

from truelinev2.proof.run_redline_manifest_all50_publish import (
    FINAL_KIND,
    PARTIAL_WARNING,
    build_artifact_paths,
    build_publish_input,
    partial_logs_from_canonical,
)

SWEEP = {"verdicts": {
    "logA": {"artifacts": ["data/outputs/callout_route_assembly_sweep/logA_s1_redline_stroke.png",
                           "data/outputs/callout_route_assembly_sweep/logA_s2_redline_stroke.png"]},
    "logB": {"artifacts": ["data/outputs/callout_route_assembly_sweep/logB_s3_redline_stroke.png"]},
}}
CANON = {"render": [
    {"log_id": "logC", "render_status": "FULL",
     "artifacts": [{"rel": "logC/logC_s4_redline_stroke.png"}]},
    {"log_id": "logD", "render_status": "PARTIAL",
     "artifacts": [{"rel": "logD/logD_s5_symbol_anchored_stroke.png"}]},
]}
CROOT = "data/outputs/redline_manifest_publish/already_drawn13_canonical"


def _base():
    def lg(lid, drawn=False, covered=False, blocked=False):
        return {"log_id": lid, "drawn": drawn, "covered": covered, "blocked": blocked,
                "artifacts": ([{"kind": FINAL_KIND, "path": "PLACEHOLDER", "sha256": None,
                                "example_placeholder": True}] if drawn else []),
                "warnings": []}
    return {"mock_example": True, "logs": [
        lg("logA", drawn=True), lg("logD", drawn=True),
        lg("logC", covered=True), lg("logZ", blocked=True),
    ]}


def test_build_artifact_paths_merges_both_sources():
    paths = build_artifact_paths(SWEEP, CANON, CROOT)
    assert paths["logA"] == [
        "data/outputs/callout_route_assembly_sweep/logA_s1_redline_stroke.png",
        "data/outputs/callout_route_assembly_sweep/logA_s2_redline_stroke.png"]
    assert paths["logB"] == ["data/outputs/callout_route_assembly_sweep/logB_s3_redline_stroke.png"]
    assert paths["logC"] == [CROOT + "/logC/logC_s4_redline_stroke.png"]
    assert paths["logD"] == [CROOT + "/logD/logD_s5_symbol_anchored_stroke.png"]
    assert set(paths) == {"logA", "logB", "logC", "logD"}


def test_partial_logs_from_canonical():
    assert partial_logs_from_canonical(CANON) == {"logD"}


def test_build_publish_input_replaces_drawn_keeps_rest():
    base = _base()
    out = build_publish_input(base, {"logA": ["p1", "p2"], "logD": ["p3"]}, partial_logs={"logD"})
    by = {l["log_id"]: l for l in out["logs"]}
    assert [a["path"] for a in by["logA"]["artifacts"]] == ["p1", "p2"]
    assert all(a["kind"] == FINAL_KIND and a["example_placeholder"] is True and a["sha256"] is None
               for a in by["logA"]["artifacts"])
    assert [a["path"] for a in by["logD"]["artifacts"]] == ["p3"]
    assert any(PARTIAL_WARNING in w for w in by["logD"]["warnings"])
    assert by["logC"]["artifacts"] == [] and by["logZ"]["artifacts"] == []
    assert out["mock_example"] is True  # the publisher flips this, not the assembler
    assert base["logs"][0]["artifacts"][0]["path"] == "PLACEHOLDER"  # base not mutated


def test_build_publish_input_raises_on_missing_drawn_artifact():
    with pytest.raises(ValueError):
        build_publish_input(_base(), {"logA": ["p1"]}, partial_logs=set())  # logD drawn, no paths


def test_non_partial_logs_get_no_partial_warning():
    out = build_publish_input(_base(), {"logA": ["p1"], "logD": ["p3"]}, partial_logs=set())
    by = {l["log_id"]: l for l in out["logs"]}
    assert not any(PARTIAL_WARNING in w for w in by["logA"]["warnings"])
    assert not any(PARTIAL_WARNING in w for w in by["logD"]["warnings"])
