"""Phase-2A artifact publisher tests (temp fake artifacts; no engine, no render).

Proves the publisher copies final redline artifacts to a stable publish dir, computes
correct sha256 + bytes, flips placeholders to published refs, emits mock_example:false,
keeps the output schema-valid, requires final artifacts for drawn logs (failing loudly
when one is missing), never fakes artifacts for covered/blocked logs, preserves
log3/log14/blocked semantics + warnings, and uses no forbidden sources. All artifacts
are temporary fakes created under tmp_path — real render outputs are never required.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from truelinev2.contracts.redline_manifest_publisher import (
    ContractViolationError,
    MissingArtifactError,
    load_schema,
    publish_manifest,
    reconciliation_errors,
    validate_manifest,
)

CONTRACTS = Path(__file__).resolve().parents[1] / "contracts"
EXAMPLE = CONTRACTS / "examples" / "brenham_50_of_58_redline_manifest.example.json"
PUBLISHER_SRC = CONTRACTS / "redline_manifest_publisher.py"

EX = json.loads(EXAMPLE.read_text(encoding="utf-8"))
SCHEMA = load_schema()
DRAWN_ART_PATHS = [a["path"] for lg in EX["logs"] if lg["drawn"] for a in lg["artifacts"]]
LOG2_ART = [a["path"] for lg in EX["logs"] if lg["log_id"] == "log2" for a in lg["artifacts"]][0]
BLOCKED7 = {"log5", "log15", "log16", "log31", "log38", "log43", "log57"}


def make_sources(tmp_path, omit=()):
    """Create a temp fake source file for each drawn-log final artifact.

    Returns (source_root, artifact_map, content_by_manifest_path).
    """
    src_root = tmp_path / "src"
    src_root.mkdir(parents=True, exist_ok=True)
    amap = {}
    content = {}
    for path in DRAWN_ART_PATHS:
        if path in omit:
            continue
        data = ("FAKE-PNG::" + path).encode("utf-8")
        f = src_root / Path(path).name  # basenames are unique across the example
        f.write_bytes(data)
        amap[path] = str(f)
        content[path] = data
    return src_root, amap, content


def by_id(manifest):
    return {lg["log_id"]: lg for lg in manifest["logs"]}


# --------------------------------------------------------------------------- #
def test_publishes_real_manifest_mock_example_false(tmp_path):
    src_root, amap, _ = make_sources(tmp_path)
    res = publish_manifest(EXAMPLE, src_root, tmp_path / "pub", "run-001", artifact_map=amap)
    m = res["manifest"]
    pub_dir = Path(res["publish_dir"])

    assert m["mock_example"] is False
    assert Path(res["manifest_path"]).is_file()
    assert validate_manifest(m, SCHEMA) == []
    assert reconciliation_errors(m) == []

    total = 0
    for lg in m["logs"]:
        if lg["drawn"]:
            assert lg["artifacts"], lg["log_id"]
            for a in lg["artifacts"]:
                assert a["published"] is True
                assert a["example_placeholder"] is False
                assert isinstance(a["sha256"], str) and len(a["sha256"]) == 64
                assert a["bytes"] > 0
                assert a["path"].startswith("artifacts/%s/" % lg["log_id"])
                assert (pub_dir / a["path"]).is_file()
                total += 1
        else:
            assert lg["artifacts"] == []
    assert total == res["published_count"] == len(DRAWN_ART_PATHS)


def test_sha256_and_bytes_match_published_file(tmp_path):
    src_root, amap, content = make_sources(tmp_path)
    res = publish_manifest(EXAMPLE, src_root, tmp_path / "pub", "run-001", artifact_map=amap)
    pub_dir = Path(res["publish_dir"])

    # Internal consistency: every record's sha256/bytes match its published file.
    for lg in res["manifest"]["logs"]:
        for a in lg["artifacts"]:
            raw = (pub_dir / a["path"]).read_bytes()
            assert a["sha256"] == hashlib.sha256(raw).hexdigest()
            assert a["bytes"] == len(raw)

    # Copy fidelity: log2's published bytes equal the exact source bytes we wrote.
    log2 = by_id(res["manifest"])["log2"]
    expected = content[LOG2_ART]
    published = (pub_dir / log2["artifacts"][0]["path"]).read_bytes()
    assert published == expected
    assert log2["artifacts"][0]["sha256"] == hashlib.sha256(expected).hexdigest()
    assert log2["artifacts"][0]["bytes"] == len(expected)


def test_resolves_via_source_root_without_explicit_map(tmp_path):
    # No artifact_map: the publisher finds sources by basename under source-root.
    src_root, _amap, _ = make_sources(tmp_path)
    res = publish_manifest(EXAMPLE, src_root, tmp_path / "pub", "run-002")
    assert res["published_count"] == len(DRAWN_ART_PATHS)
    assert res["manifest"]["mock_example"] is False


def test_missing_drawn_artifact_fails_loudly(tmp_path):
    src_root, amap, _ = make_sources(tmp_path, omit={LOG2_ART})
    with pytest.raises(MissingArtifactError) as ei:
        publish_manifest(EXAMPLE, src_root, tmp_path / "pub", "run-003", artifact_map=amap)
    msg = str(ei.value)
    assert "log2" in msg and "missing" in msg.lower()


def test_covered_and_blocked_not_required_or_faked(tmp_path):
    src_root, amap, _ = make_sources(tmp_path)
    res = publish_manifest(EXAMPLE, src_root, tmp_path / "pub", "run-004", artifact_map=amap)
    m = by_id(res["manifest"])
    pub_dir = Path(res["publish_dir"])

    assert m["log14"]["artifacts"] == []  # covered: no duplicate artifact
    for k in BLOCKED7:
        assert m[k]["artifacts"] == []     # blocked: no fabricated artifact
    for k in ("log14", "log5", "log57"):
        assert not (pub_dir / "artifacts" / k).exists()


def test_blocked_log_with_artifact_raises_contract_violation(tmp_path):
    modified = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    for lg in modified["logs"]:
        if lg["log_id"] == "log5":
            lg["artifacts"] = [{
                "kind": "FINAL_REDLINE_PNG", "path": "bogus.png",
                "sha256": None, "example_placeholder": True,
            }]
    p = tmp_path / "modified.json"
    p.write_text(json.dumps(modified), encoding="utf-8")
    src_root, amap, _ = make_sources(tmp_path)
    with pytest.raises(ContractViolationError) as ei:
        publish_manifest(p, src_root, tmp_path / "pub", "run-005", artifact_map=amap)
    assert "log5" in str(ei.value)


def test_log3_log14_blocked_semantics_preserved(tmp_path):
    src_root, amap, _ = make_sources(tmp_path)
    res = publish_manifest(EXAMPLE, src_root, tmp_path / "pub", "run-006", artifact_map=amap)
    m = by_id(res["manifest"])

    # log3 stays owner-confirmed geometry (NOT deterministic auto), still drawn + published.
    assert m["log3"]["provenance"] == "OWNER_CONFIRMED_HUMAN_ADJUSTABLE"
    assert m["log3"]["status"] == "DRAWN_REDLINE"
    assert all(a["published"] for a in m["log3"]["artifacts"])

    # log14 stays covered, no duplicate artifact.
    assert m["log14"]["status"] == "COVERED_BY_EXISTING_REDLINE"
    assert m["log14"]["coverage"]["covered_by"] == "log10"
    assert m["log14"]["artifacts"] == []

    # blocked logs stay blocked with their unlock requirements.
    for k in BLOCKED7:
        assert m[k]["blocked"] is True
        assert m[k]["blocker"]["unlock_requirement"].strip()
        assert m[k]["artifacts"] == []

    # Stored-anchor-debt warnings are carried through, not converted to placement truth.
    assert any("B-DATA-LOG48-ADJ-1" in w for w in m["log48"]["warnings"])
    assert any("B-DATA-LOG48-ADJ-1" in w for w in m["log70"]["warnings"])

    # Accounting is unchanged by publishing.
    assert res["manifest"]["status_counts"] == EX["status_counts"]
    assert res["manifest"]["provenance_counts"] == EX["provenance_counts"]


def test_output_schema_and_backward_compat(tmp_path):
    src_root, amap, _ = make_sources(tmp_path)
    res = publish_manifest(EXAMPLE, src_root, tmp_path / "pub", "run-007", artifact_map=amap)

    # Published manifest (with bytes/published) validates.
    assert validate_manifest(res["manifest"], SCHEMA) == []
    # Backward compat: the untouched placeholder example still validates under the schema.
    assert validate_manifest(EX, SCHEMA) == []
    # Published artifacts carry the full real-metadata field set.
    a = next(a for lg in res["manifest"]["logs"] if lg["drawn"] for a in lg["artifacts"])
    assert {"kind", "path", "sha256", "bytes", "published", "example_placeholder"} <= set(a)


def test_output_validates_under_jsonschema_if_present(tmp_path):
    jsonschema = pytest.importorskip("jsonschema")
    src_root, amap, _ = make_sources(tmp_path)
    res = publish_manifest(EXAMPLE, src_root, tmp_path / "pub", "run-008", artifact_map=amap)
    jsonschema.validate(instance=res["manifest"], schema=SCHEMA)


def test_validator_is_not_vacuous():
    bad = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    bad["logs"][0]["artifacts"][0]["published"] = "yes"  # boolean expected
    assert validate_manifest(bad, SCHEMA)
    bad2 = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    bad2["logs"][0]["artifacts"][0]["bytes"] = -1  # minimum 0
    assert validate_manifest(bad2, SCHEMA)


def test_publish_is_deterministic(tmp_path):
    src_root, amap, _ = make_sources(tmp_path)
    r1 = publish_manifest(EXAMPLE, src_root, tmp_path / "p", "run-det", artifact_map=amap)
    r2 = publish_manifest(EXAMPLE, src_root, tmp_path / "p", "run-det", artifact_map=amap)
    # Same inputs + same target -> byte-identical manifest (no timestamps / nondeterminism).
    assert json.dumps(r1["manifest"], sort_keys=True) == json.dumps(r2["manifest"], sort_keys=True)


def test_no_forbidden_sources_in_publisher():
    src = PUBLISHER_SRC.read_text(encoding="utf-8").lower()
    for token in ("parent_source_model", "placement_status",
                  "data/outputs/callout_route_assembly_sweep"):
        assert token not in src, token
    # No renderer / engine-solve coupling.
    assert "truelinev2.render" not in src
    assert "match.engine" not in src
    assert "solve_log" not in src
