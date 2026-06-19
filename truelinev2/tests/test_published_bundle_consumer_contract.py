"""Phase-2J read-only static-bundle-consumer contract tests (tiny temp fixtures; no 50 MB real
bundle, no render).

Proves the website/backend READ side of the durable store:
  * a valid stored bundle loads end-to-end and `latest_valid` resolves;
  * an explicit immutable bundle_id resolves; latest repoints across stores;
  * a missing/invalid latest pointer fails; an unregistered id fails;
  * a mock/example bundle is rejected (even if forced into the store);
  * covered/blocked logs carrying artifacts are rejected;
  * stale source/model fields (`parent_source_model` / `placement_status`) are rejected;
  * artifact resolution is by manifest path only (no filename inference) and rejects traversal,
    unknown paths, and sha256/byte drift; only `FINAL_REDLINE_PNG` is exposed;
  * the gate is default-OFF (env / explicit enable);
  * the consumer never imports a render/engine/solver path ("no live render").

Pure stdlib + temp dirs; reuses the real store-write path (`store_bundle`) to build fixtures.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from truelinev2.contracts.published_bundle import MANIFEST_FILENAME
from truelinev2.contracts.published_bundle_store import (
    BUNDLES_SUBDIR,
    STORE_INDEX_FILENAME,
    store_bundle,
)
from truelinev2.contracts.published_bundle_consumer import (
    CONSUMER_OPTIN_ENV,
    ArtifactNotServableError,
    BundleNotReadableError,
    ConsumerDisabledError,
    StaticBundleConsumer,
    consumer_enabled,
    consumer_read_errors,
)

CREATED = "2026-06-19T00:00:00Z"
CONSUMER_MODULE = Path(__file__).resolve().parents[1] / "contracts" / "published_bundle_consumer.py"


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
    """A 3-log bundle (1 drawn + 1 covered + 1 blocked) with one real FINAL_REDLINE_PNG artifact."""
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


def stored(tmp_path, *, name="src", store_name="store", content_tag=b"A"):
    """Build a valid bundle and store it via the real store-write path; return (store_root, bundle_id)."""
    src = build_bundle(tmp_path / name, content_tag=content_tag)
    store = tmp_path / store_name
    res = store_bundle(src, store, created_at=CREATED)
    return store, res["bundle_id"]


def register_raw(store_root, bundle_id, src_bundle):
    """Force a (possibly INADMISSIBLE) bundle into the store layout + point latest_valid at it.

    Bypasses store_bundle's admission so we can prove the CONSUMER independently refuses a bad bundle
    (defense in depth: even if a non-conforming bundle reached the store, it must not be served)."""
    store_root = Path(store_root)
    dest = store_root / BUNDLES_SUBDIR / bundle_id
    shutil.copytree(src_bundle, dest)
    (store_root / STORE_INDEX_FILENAME).write_text(json.dumps({
        "store_format": "trueline-redline-bundle-store-1",
        "latest_valid": bundle_id,
        "bundles": {bundle_id: {"bundle_id": bundle_id}},
    }, indent=2), encoding="utf-8")
    return dest


# --------------------------------------------------------------------------- #
def test_valid_bundle_loads_and_latest_resolves(tmp_path):
    store, bid = stored(tmp_path)
    c = StaticBundleConsumer(store, enable=True)
    assert c.latest_valid_id() == bid
    rb = c.open_latest()
    assert rb.bundle_id == bid
    payload = rb.manifest_payload()
    assert payload["mock_example"] is False
    assert payload["summary"]["frontier"] == "1/3"
    assert len(rb.manifest_sha256) == 64
    # Only the drawn log contributes a FINAL_REDLINE_PNG; covered/blocked contribute none.
    finals = rb.final_artifacts()
    assert [lid for lid, _ in finals] == ["logA"]
    # End-to-end artifact read: resolved by manifest path, checksum-verified.
    desc = rb.resolve_artifact("artifacts/logA/logA_s1_redline_stroke.png")
    assert desc["content_type"] == "image/png"
    assert desc["log_id"] == "logA"
    assert desc["bytes"] == len(desc["data"])
    assert hashlib.sha256(desc["data"]).hexdigest() == desc["sha256"]


def test_open_explicit_bundle_id_and_latest_repoints(tmp_path):
    store, a = stored(tmp_path, name="a", content_tag=b"A")
    # store a second, different bundle into the SAME store -> latest repoints to b, a retained
    src_b = build_bundle(tmp_path / "b", content_tag=b"B")
    res_b = store_bundle(src_b, store, created_at=CREATED)
    b = res_b["bundle_id"]
    assert a != b
    c = StaticBundleConsumer(store, enable=True)
    assert c.latest_valid_id() == b
    assert c.open_latest().bundle_id == b
    # explicit immutable id still resolves the historical bundle
    assert c.open_bundle(a).bundle_id == a
    assert set(c.registered_ids()) == {a, b}


def test_missing_latest_pointer_fails(tmp_path):
    empty = tmp_path / "empty_store"
    empty.mkdir()
    c = StaticBundleConsumer(empty, enable=True)
    with pytest.raises(BundleNotReadableError):
        c.latest_valid_id()
    with pytest.raises(BundleNotReadableError):
        c.open_latest()


def test_unregistered_and_invalid_latest_fail(tmp_path):
    store, bid = stored(tmp_path)
    c = StaticBundleConsumer(store, enable=True)
    # unregistered id
    with pytest.raises(BundleNotReadableError):
        c.open_bundle("brenham-c19b565-deadbeefdead")
    # latest_valid points to a registered id whose bundle dir is gone
    shutil.rmtree(store / BUNDLES_SUBDIR / bid)
    c2 = StaticBundleConsumer(store, enable=True)
    with pytest.raises(BundleNotReadableError):
        c2.open_latest()


def test_mock_example_bundle_rejected(tmp_path):
    mock_src = build_bundle(tmp_path / "mock", mock_example=True)
    assert any("mock_example" in e for e in consumer_read_errors(mock_src))
    # even if forced into the store, the consumer refuses to serve it
    store = tmp_path / "store"
    register_raw(store, "brenham-c19b565-mockmockmock", mock_src)
    c = StaticBundleConsumer(store, enable=True)
    with pytest.raises(BundleNotReadableError):
        c.open_latest()


def test_covered_blocked_with_artifacts_rejected(tmp_path):
    def covered_with_artifact(m, root):
        m["logs"][1]["artifacts"] = [{"kind": "FINAL_REDLINE_PNG", "path": "artifacts/log14/x.png",
                                      "sha256": "0" * 64, "bytes": 1, "published": True,
                                      "example_placeholder": False}]
    bad = build_bundle(tmp_path / "cov", mutate=covered_with_artifact)
    assert consumer_read_errors(bad)  # non-empty
    store = tmp_path / "store"
    register_raw(store, "brenham-c19b565-coveredart1", bad)
    with pytest.raises(BundleNotReadableError):
        StaticBundleConsumer(store, enable=True).open_latest()


def test_stale_source_model_fields_rejected(tmp_path):
    def inject_stale(m, root):
        m["parent_source_model"] = {"do_not": "read"}      # top-level stale field
        m["logs"][0]["placement_status"] = "STALE"          # per-log stale field
    bad = build_bundle(tmp_path / "stale", mutate=inject_stale)
    errs = consumer_read_errors(bad)
    assert any("parent_source_model" in e for e in errs)
    assert any("placement_status" in e for e in errs)


def test_artifact_resolution_is_allowlisted_no_filename_inference(tmp_path):
    store, _ = stored(tmp_path)
    rb = StaticBundleConsumer(store, enable=True).open_latest()
    # traversal / absolute / unknown paths all refused
    for bad in ("../../etc/passwd", "artifacts/logA/../../../secret",
                "/abs/path.png", "artifacts/logA/not_listed.png", "redline_manifest.json"):
        with pytest.raises(ArtifactNotServableError):
            rb.resolve_artifact(bad)
    # a real on-disk PNG that is NOT in the manifest is still refused (no filename inference)
    stray = rb.bundle_root / "artifacts" / "logA" / "stray.png"
    stray.write_bytes(b"STRAY")
    with pytest.raises(ArtifactNotServableError):
        rb.resolve_artifact("artifacts/logA/stray.png")


def test_non_final_kind_not_exposed(tmp_path):
    def add_helper(m, root):
        hdir = root / "artifacts" / "logA"
        (hdir / "logA_helper.png").write_bytes(b"HELPER")
        h = b"HELPER"
        m["logs"][0]["artifacts"].append(
            {"kind": "PROOF_HELPER", "path": "artifacts/logA/logA_helper.png",
             "sha256": hashlib.sha256(h).hexdigest(), "bytes": len(h),
             "published": True, "example_placeholder": False})
    src = build_bundle(tmp_path / "helper", mutate=add_helper)
    store = tmp_path / "store"
    res = store_bundle(src, store, created_at=CREATED)
    rb = StaticBundleConsumer(store, enable=True).open_bundle(res["bundle_id"])
    # PROOF_HELPER is published+valid but NOT a website-rendered artifact -> not exposed, not servable
    assert [lid for lid, _ in rb.final_artifacts()] == ["logA"]
    assert all(a["path"] != "artifacts/logA/logA_helper.png" for _l, a in rb.final_artifacts())
    with pytest.raises(ArtifactNotServableError):
        rb.resolve_artifact("artifacts/logA/logA_helper.png")


def test_artifact_checksum_drift_rejected(tmp_path):
    store, _ = stored(tmp_path)
    rb = StaticBundleConsumer(store, enable=True).open_latest()
    rel = "artifacts/logA/logA_s1_redline_stroke.png"
    assert rb.resolve_artifact(rel)["data"]  # ok first
    # tamper the on-disk artifact -> sha256 drift -> refuse to serve
    (rb.bundle_root / rel).write_bytes(b"TAMPERED-DIFFERENT-BYTES")
    with pytest.raises(ArtifactNotServableError):
        rb.resolve_artifact(rel)


def test_gate_is_default_off(tmp_path, monkeypatch):
    store, _ = stored(tmp_path)
    monkeypatch.delenv(CONSUMER_OPTIN_ENV, raising=False)
    assert consumer_enabled() is False
    with pytest.raises(ConsumerDisabledError):
        StaticBundleConsumer(store)           # default-OFF: no env, no explicit enable
    with pytest.raises(ConsumerDisabledError):
        StaticBundleConsumer(store, enable=False)  # explicit disable overrides even env
    monkeypatch.setenv(CONSUMER_OPTIN_ENV, "1")
    assert consumer_enabled() is True
    assert StaticBundleConsumer(store).open_latest()      # env-enabled
    monkeypatch.delenv(CONSUMER_OPTIN_ENV, raising=False)
    assert StaticBundleConsumer(store, enable=True).open_latest()  # explicit enable


def test_website_read_contract_passes_for_valid_bundle(tmp_path):
    store, bid = stored(tmp_path)
    assert consumer_read_errors(store / BUNDLES_SUBDIR / bid) == []


def test_consumer_imports_no_render_or_engine_path():
    """Structural 'no live render': the consumer's own import lines reference only stdlib + the three
    pure contract modules -- never render / engine / solver / match / ingest packages."""
    forbidden = ("truelinev2.render", "truelinev2.match", "truelinev2.solve",
                 "truelinev2.ingest", "truelinev2.extract", "truelinev2.service")
    import_lines = [ln.strip() for ln in CONSUMER_MODULE.read_text(encoding="utf-8").splitlines()
                    if ln.strip().startswith(("import ", "from "))]
    assert import_lines, "expected import statements in the consumer module"
    for ln in import_lines:
        for bad in forbidden:
            assert bad not in ln, "consumer must not import %s (line: %s)" % (bad, ln)
    # the only truelinev2 imports are the three contract modules
    tl_imports = [ln for ln in import_lines if "truelinev2" in ln]
    assert tl_imports and all("truelinev2.contracts." in ln for ln in tl_imports)
