"""Phase-2I durable-store contract tests (tiny temp fixtures; no 50 MB real bundle, no render).

Proves: a valid bundle stores into an immutable content-keyed layout with metadata + latest pointer;
storing is idempotent and historical bundles are retained immutably; invalid bundles (missing
artifact, checksum mismatch, mock_example:true, count drift) are REJECTED; validate_store catches a
corrupted stored bundle + a latest pointer to an invalid bundle; an immutable id with drifted content
is refused; and the website read contract holds. Pure stdlib + temp dirs.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from truelinev2.contracts.published_bundle import MANIFEST_FILENAME
from truelinev2.contracts.published_bundle_store import (
    BUNDLES_SUBDIR,
    WEBSITE_READ_CONTRACT,
    BundleImmutableError,
    BundleRejectedError,
    compute_bundle_id,
    load_store_index,
    store_bundle,
    validate_store,
    website_read_errors,
)

CREATED = "2026-06-19T00:00:00Z"


def _log(lid, status, prov, drawn=False, covered=False, blocked=False, artifacts=None):
    return {"log_id": lid, "parent_id": "b_" + lid, "entry_role": "standalone",
            "status": status, "provenance": prov, "drawn": drawn, "covered": covered,
            "blocked": blocked, "drawn_lane": "NEW_TARGETS" if drawn else None,
            "source_sheets": [1],
            "span": {"start_station": "0+00", "end_station": "1+00", "label": "0+00->1+00"},
            "closure": None, "coverage": {"covered_by": "log10"} if covered else None,
            "blocker": {"category": "OWNER_LOCKED", "name": "n", "unlock_requirement": "owner lifts"} if blocked else None,
            "artifacts": artifacts or [],
            "evidence": [{"kind": "ACCOUNTABILITY_LEDGER", "ref": "r"}], "warnings": []}


def build_bundle(root, *, mock_example=False, content_tag=b"A", mutate=None):
    root = Path(root)
    art_dir = root / "artifacts" / "logA"
    art_dir.mkdir(parents=True)
    data = b"FAKE-PNG-" + content_tag
    (art_dir / "logA_s1_redline_stroke.png").write_bytes(data)
    sha = hashlib.sha256(data).hexdigest()
    rel = "artifacts/logA/logA_s1_redline_stroke.png"
    art = {"kind": "FINAL_REDLINE_PNG", "path": rel, "sha256": sha, "bytes": len(data),
           "published": True, "example_placeholder": False}
    manifest = {
        "schema_version": "1.0.0", "mock_example": mock_example, "disclaimer": "t",
        "project_id": "brenham", "project_name": "Brenham",
        "engine": {"branch": "feat/truelinev2", "engine_head": "h", "render_commit": "c19b565",
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
                 _log("log14", "COVERED_BY_EXISTING_REDLINE", "COVERED_BY_EXISTING_REDLINE", covered=True),
                 _log("logZ", "OWNER_LOCKED_ABSTAIN", "BLOCKED_OWNER_LOCKED", blocked=True)],
    }
    if mutate:
        mutate(manifest, root)
    (root / MANIFEST_FILENAME).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return root


# --------------------------------------------------------------------------- #
def test_store_valid_bundle(tmp_path):
    src = build_bundle(tmp_path / "src")
    store = tmp_path / "store"
    res = store_bundle(src, store, created_at=CREATED)
    assert res["action"] == "stored"
    assert res["bundle_id"].startswith("brenham-c19b565-")
    dest = store / BUNDLES_SUBDIR / res["bundle_id"]
    assert (dest / MANIFEST_FILENAME).is_file()
    assert (dest / "_store_bundle_meta.json").is_file()
    m = res["meta"]
    assert m["render_commit"] == "c19b565" and len(m["manifest_sha256"]) == 64
    assert m["artifact_count"] == 1 and m["total_bytes"] > 0 and m["created_at"] == CREATED
    assert m["summary"] == {"total_logs": 3, "drawn": 1, "covered": 1, "blocked": 1}
    assert m["manifest_entrypoint"] == MANIFEST_FILENAME
    idx = load_store_index(store)
    assert idx["latest_valid"] == res["bundle_id"]
    assert idx["bundles"][res["bundle_id"]]["manifest_entrypoint"] == \
        "%s/%s/%s" % (BUNDLES_SUBDIR, res["bundle_id"], MANIFEST_FILENAME)
    assert validate_store(store)["valid"] is True


def test_store_is_idempotent(tmp_path):
    src = build_bundle(tmp_path / "src")
    store = tmp_path / "store"
    a = store_bundle(src, store, created_at=CREATED)
    b = store_bundle(src, store, created_at="2099-01-01T00:00:00Z")  # same content
    assert a["bundle_id"] == b["bundle_id"]
    assert b["action"] == "already_stored"
    # immutable: meta unchanged (original created_at retained, not the new one)
    meta = json.loads((store / BUNDLES_SUBDIR / a["bundle_id"] / "_store_bundle_meta.json").read_text())
    assert meta["created_at"] == CREATED


def test_store_retains_history_and_repoints_latest(tmp_path):
    store = tmp_path / "store"
    a = store_bundle(build_bundle(tmp_path / "a", content_tag=b"A"), store, created_at=CREATED)
    b = store_bundle(build_bundle(tmp_path / "b", content_tag=b"B"), store, created_at=CREATED)
    assert a["bundle_id"] != b["bundle_id"]
    # both immutable historical bundles retained; latest repointed to b
    assert (store / BUNDLES_SUBDIR / a["bundle_id"] / MANIFEST_FILENAME).is_file()
    assert (store / BUNDLES_SUBDIR / b["bundle_id"] / MANIFEST_FILENAME).is_file()
    idx = load_store_index(store)
    assert idx["latest_valid"] == b["bundle_id"]
    assert set(idx["bundles"]) == {a["bundle_id"], b["bundle_id"]}
    assert validate_store(store)["valid"] is True


def test_store_rejects_invalid_bundles(tmp_path):
    store = tmp_path / "store"
    # missing artifact
    src = build_bundle(tmp_path / "miss")
    (src / "artifacts" / "logA" / "logA_s1_redline_stroke.png").unlink()
    with pytest.raises(BundleRejectedError):
        store_bundle(src, store, created_at=CREATED)
    # checksum mismatch
    def bad_sha(m, root):
        m["logs"][0]["artifacts"][0]["sha256"] = "0" * 64
    with pytest.raises(BundleRejectedError):
        store_bundle(build_bundle(tmp_path / "cs", mutate=bad_sha), store, created_at=CREATED)
    # mock_example true
    with pytest.raises(BundleRejectedError):
        store_bundle(build_bundle(tmp_path / "mock", mock_example=True), store, created_at=CREATED)
    # count drift (status_counts disagree with logs)
    def drift(m, root):
        m["status_counts"]["DRAWN_REDLINE"] = 9
    with pytest.raises(BundleRejectedError):
        store_bundle(build_bundle(tmp_path / "drift", mutate=drift), store, created_at=CREATED)


def test_validate_store_catches_corruption_and_bad_latest(tmp_path):
    store = tmp_path / "store"
    res = store_bundle(build_bundle(tmp_path / "src"), store, created_at=CREATED)
    # corrupt the stored (immutable) artifact -> store no longer valid; latest pointer now bad
    (store / BUNDLES_SUBDIR / res["bundle_id"] / "artifacts" / "logA" /
     "logA_s1_redline_stroke.png").write_bytes(b"TAMPERED")
    rep = validate_store(store)
    assert rep["valid"] is False
    assert rep["invalid_bundles"] and rep["latest_pointer_ok"] is False


def test_immutable_overwrite_guard(tmp_path):
    store = tmp_path / "store"
    src = build_bundle(tmp_path / "src")
    res = store_bundle(src, store, created_at=CREATED)
    # tamper the stored manifest so its content no longer matches the id's content key
    (store / BUNDLES_SUBDIR / res["bundle_id"] / MANIFEST_FILENAME).write_text("{}", encoding="utf-8")
    with pytest.raises(BundleImmutableError):
        store_bundle(src, store, created_at=CREATED)


def test_website_read_contract(tmp_path):
    assert website_read_errors(build_bundle(tmp_path / "ok")) == []
    assert website_read_errors(build_bundle(tmp_path / "mock", mock_example=True))  # mock rejected

    def covered_with_artifact(m, root):
        m["logs"][1]["artifacts"] = [{"kind": "FINAL_REDLINE_PNG", "path": "artifacts/log14/x.png",
                                      "sha256": "0" * 64, "bytes": 1, "published": True,
                                      "example_placeholder": False}]
    assert website_read_errors(build_bundle(tmp_path / "cov", mutate=covered_with_artifact))
    blob = " ".join(WEBSITE_READ_CONTRACT).lower()
    assert "mock_example" in blob and "validated bundle" in blob and "never infer status" in blob


def test_bundle_id_is_content_keyed():
    manifest = {"project_id": "brenham", "engine": {"render_commit": "c19b565"}}
    assert compute_bundle_id(manifest, "a" * 64) == "brenham-c19b565-" + "a" * 12
    assert compute_bundle_id(manifest, "b" * 64) != compute_bundle_id(manifest, "a" * 64)
